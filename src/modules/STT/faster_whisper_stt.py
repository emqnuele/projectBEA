"""Whisper on this machine, through faster-whisper.

The other two transcribers send the audio somewhere. This one does not: the
weights live under `data/models/whisper`, nothing leaves the room, and there is
no key and no per-minute bill. The cost is the first run, which downloads the
model, and a CPU that is busy while she listens.
"""

import os
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from src.core.config import BrainConfig
from src.interfaces.base_interfaces import STTInterface
from src.utils.huggingface import directory_bytes, download_hint, quiet, watched
from src.utils.logger import get_logger

logger = get_logger("bea.stt.faster_whisper")

DEFAULT_MODEL = "small"

# the hosted providers name the same weights differently, and a model id copied
# from a groq or openrouter config is the most likely thing to arrive here
ALIASES = {
    "whisper-large-v3-turbo": "large-v3-turbo",
    "whisper-large-v3": "large-v3",
    "whisper-large-v2": "large-v2",
    "whisper-1": "large-v3",
}


def normalize_model(name: str) -> str:
    """A faster-whisper model id, from whatever spelling the config carries."""
    name = (name or "").strip()
    if not name:
        return DEFAULT_MODEL
    if "/" in name:
        owner, _, tail = name.partition("/")
        # openai/whisper-large-v3-turbo is the hosted spelling; anything else
        # with a slash is a real huggingface repo and is left alone
        if owner.lower() == "openai" and tail in ALIASES:
            return ALIASES[tail]
        return name
    return ALIASES.get(name, name)


# --- the weights ------------------------------------------------------------

# only ever used to tell someone how long a download will take, so being a
# little off is harmless. Sizes for the four the wizard offers.
WEIGHTS_MB = {
    "tiny": 75,
    "base": 145,
    "small": 480,
    "large-v3-turbo": 1600,
}


def _download(model: str, root: str, local_files_only: bool = False) -> str:
    """The one call that fetches the weights, used by the engine and the wizard.

    `cache_dir`, never `output_dir`: `WhisperModel(download_root=…)` hands its
    folder over as a cache, and the two lay their files out differently. The
    wizard used to download with `output_dir`, which meant a person who waited
    through 480MB there waited through all of it again at her first startup,
    into a second copy, with nothing on screen to say why. `output_dir` also
    carries a symlink argument the hub has deprecated and warns about.
    """
    from faster_whisper.utils import download_model

    return download_model(model, cache_dir=root, local_files_only=local_files_only)


def weights_here(model: str, root: str, downloader: Optional[Callable[..., Any]] = None) -> bool:
    """Whether the weights are already on disk, asked of the library itself."""
    downloader = downloader or _download
    try:
        with quiet():
            downloader(normalize_model(model), root, local_files_only=True)
        return True
    except Exception:
        return False


def fetch_weights(model: str, root: str, downloader: Optional[Callable[..., Any]] = None,
                  on_progress: Optional[Callable[[int], None]] = None,
                  tick: float = 0.3) -> Optional[Exception]:
    """Downloads the weights, reporting bytes as they land. Never raises."""
    downloader = downloader or _download
    return watched(lambda: downloader(normalize_model(model), root), root, on_progress, tick)


def stale_weights(root: str) -> int:
    """Bytes of a pre-cache download sitting loose in `root`, read by nothing.

    Setups run before the layout was fixed left the files directly in the
    folder, where `WhisperModel` does not look. Deleting files on someone's
    disk is not this program's business; saying which ones are dead is.
    """
    if not (Path(root) / "model.bin").is_file():
        return 0
    return sum(entry.stat().st_size for entry in Path(root).iterdir() if entry.is_file())


@contextmanager
def announce_download(model: str, root: str,
                      report: Optional[Callable[[str], None]] = None,
                      tick: float = 2.0) -> Iterator[None]:
    """Says out loud that the first start is a download, while it is happening.

    Her first start on a fresh machine is a few hundred megabytes arriving
    with no bar and no line of log — a program that looks hung for anywhere
    between one minute and ten. Nothing here downloads anything: the model
    builder below does that, exactly as it always has. This only watches the
    folder fill up and says so, and only when there is something to say.
    """
    if weights_here(model, root):
        yield
        return

    say = report or logger.warning
    size = WEIGHTS_MB.get(model)
    say(f"First run: downloading the {model!r} whisper weights"
        + (f" (~{size} MB)" if size else "")
        + f" into {root}. This happens once, and she cannot hear until it lands.")

    done = threading.Event()

    def watch() -> None:
        reported = 0
        while not done.wait(tick):
            if not size:
                continue
            percent = min(99, int(directory_bytes(root) * 100 / (size * 1_000_000)))
            # every tenth: a ten-minute download is ten lines, not two thousand
            if percent >= reported + 10:
                reported = percent - percent % 10
                say(f"whisper {model}: {reported}% of ~{size} MB")

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        yield
    finally:
        done.set()
        watcher.join(timeout=tick)


# `language` reaches the hosted providers as free text and they shrug at a code
# they do not know. Whisper raises, so the same config must not be able to
# break only this backend — `jp` is one of the dashboard's own choices
LANGUAGE_ALIASES = {"jp": "ja", "cn": "zh", "gr": "el", "kr": "ko"}


def normalize_language(code: Optional[str]) -> Optional[str]:
    """A language whisper knows, or None to let it work the language out itself."""
    code = (code or "").strip().lower()
    if not code:
        return None
    code = LANGUAGE_ALIASES.get(code, code)

    from faster_whisper.tokenizer import _LANGUAGE_CODES

    if code not in _LANGUAGE_CODES:
        logger.warning(f"Whisper does not know the language {code!r}; detecting instead.")
        return None
    return code


def _wanted(config: BrainConfig) -> tuple:
    """The raw config the model was built from. Compared, not resolved."""
    return (normalize_model(config.stt_model),
            config.faster_whisper_device or "auto",
            config.faster_whisper_compute_type or "auto",
            config.faster_whisper_download_root or None)


def _resolve_device(config: BrainConfig) -> tuple:
    """A concrete device and precision, from a config that may say "auto".

    `auto` used to reach ctranslate2 unresolved, which picked the gpu — while
    the precision stayed at int8, the cpu choice. An explicit device is taken
    at face value; a load failure still falls back to cpu, in `_load`.
    """
    from src.core import perf as perf_module

    want_device = (config.faster_whisper_device or "auto").strip().lower() or "auto"
    want_compute = (config.faster_whisper_compute_type or "auto").strip() or "auto"
    if not perf_module.perf_enabled():
        # the old behaviour, before any of this existed
        return want_device, (want_compute if want_compute != "auto"
                             else "float16" if want_device == "cuda" else "int8")
    device = want_device
    if device == "auto":
        device = "cuda" if _cuda_count() > 0 else "cpu"
    if want_compute != "auto":
        return device, want_compute
    # ctranslate2's own `default` keeps full precision, several times slower
    # on a cpu for no accuracy anyone can hear
    return device, "float16" if device == "cuda" else "int8"


def _cuda_count() -> int:
    """GPUs ctranslate2 can see. Zero on any error: no gpu is the safe answer."""
    try:
        import ctranslate2

        return max(0, int(ctranslate2.get_cuda_device_count()))
    except Exception:
        return 0


def device_advice() -> str:
    """What to do about a device that will not run, on this machine.

    A gpu ctranslate2 can see is not a gpu it can use: on windows the CUDA
    Toolkit DLLs (cuBLAS and friends) do not come with the pip wheels, so the
    card is visible, the model loads, and every transcription fails.
    """
    if sys.platform.startswith("win"):
        return ("On windows the gpu needs the CUDA Toolkit 12.x libraries "
                "(cuBLAS DLLs) on PATH; without them she runs on cpu instead. "
                "Either install them, or set `faster_whisper_device` to "
                "\"cpu\" and stop asking for a gpu she cannot use.")
    if sys.platform == "darwin":
        return ("Macs have no CUDA, so cpu is the only device and that is "
                "normal — if this still fails the install itself is broken "
                "(`uv sync`).")
    return ("Linux usually gets CUDA through the nvidia pip wheels; without a "
            "driver and matching CUDA libraries she runs on cpu instead. Set "
            "`faster_whisper_device` to \"cpu\" to stop retrying the gpu.")


def _build(stt: "FasterWhisperSTT"):
    """The model, with the thread pool sized for the cores that exist."""
    from faster_whisper import WhisperModel

    from src.core import perf as perf_module

    kwargs: dict = {}
    if perf_module.perf_enabled():
        # one worker: several would each hold the model, and the turns already
        # run concurrently — throughput here is latency somewhere else
        kwargs = {"cpu_threads": perf_module.physical_cores(), "num_workers": 1}
    return WhisperModel(stt.model_name, device=stt.device,
                        compute_type=stt.compute_type,
                        download_root=stt.download_root, **kwargs)


class FasterWhisperSTT(STTInterface):
    def __init__(self, config: BrainConfig):
        self.config = config
        self.model_name = normalize_model(config.stt_model)
        # raw config, for the reload comparison below: `device` holds what the
        # probe resolved, and comparing resolved against configured would
        # rebuild the model on every unrelated save
        self._configured = _wanted(config)
        self.device, self.compute_type = _resolve_device(config)
        self.download_root = config.faster_whisper_download_root or None
        self.vad = bool(config.faster_whisper_vad)
        self.model = None
        # honest state: whether she hears as configured, and the last reason
        # she did not. The dashboard and the doctor read this instead of
        # guessing from the config.
        self.degraded = False
        self.last_error: Optional[str] = None
        self._load()
        self._probe()

    def _load(self) -> None:
        """Builds the model, or leaves it None and says why.

        A missing model must not take the whole engine down on startup: she is
        still perfectly usable typed at, exactly as with no transcriber at all.
        """
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except ImportError:
            logger.error("faster-whisper is not installed — run `uv sync`.")
            return

        if self.download_root:
            os.makedirs(self.download_root, exist_ok=True)

        try:
            # the weights are fetched by the builder on a fresh machine, and
            # that is the longest silence in the whole first run
            with announce_download(self.model_name, self.download_root or ""):
                self.model = _build(self)
            logger.info(f"Local whisper ready: {self.model_name} on {self.device}")
        except Exception as e:
            if self.device != "cpu" or self.compute_type != "int8":
                # a cuda card that was there at probe time and gone at load
                # time — old drivers, a container without the device — is not
                # worth losing her ears over
                logger.warning(f"Local whisper on {self.device} failed ({e}); "
                               f"falling back to cpu/int8.")
                self.device, self.compute_type = "cpu", "int8"
                try:
                    self.model = _build(self)
                    logger.info(f"Local whisper ready: {self.model_name} on cpu "
                                f"(fallback).")
                    return
                except Exception as fallback_error:
                    e = fallback_error
            logger.error(f"Could not load local whisper {self.model_name!r}: {e}")
            hint = download_hint(e)
            if hint:
                logger.error(hint)

    def _use_cpu(self, reason: str) -> bool:
        """Rebuilds on cpu/int8 after a device proved unusable. Returns built."""
        self.device, self.compute_type = "cpu", "int8"
        self.degraded = True
        try:
            self.model = _build(self)
            logger.warning(f"Local whisper on cpu/int8 ({reason}). {device_advice()}")
            return True
        except Exception as e:
            self.model = None
            self.last_error = str(e)
            logger.error(f"Local whisper would not build on cpu either ({e}).")
            return False

    def _probe(self) -> None:
        """One silent second through the model, at startup rather than mid-call.

        Loading is not hearing: a device ctranslate2 can see but cannot use
        (missing CUDA libraries) loads fine and then fails every real turn.
        A failed probe falls back before the first person speaks, loudly.
        """
        if self.model is None:
            return
        try:
            import numpy as np

            silence = np.zeros(16000, dtype="float32")
            self.model.transcribe(silence, language=None, temperature=0.0,
                                  vad_filter=False)
            return
        except Exception as e:
            if self.device == "cpu":
                self.model = None
                self.degraded = True
                self.last_error = str(e)
                logger.error(f"Local whisper cannot transcribe even on cpu ({e}); "
                             f"ears are off. {device_advice()}")
                return
            logger.warning(f"Local whisper on {self.device} loads but cannot "
                           f"transcribe ({e}); trying cpu before anyone speaks. "
                           f"{device_advice()}")
            self.last_error = str(e)
            if self._use_cpu(f"boot probe failed: {e}"):
                try:
                    import numpy as np

                    self.model.transcribe(np.zeros(16000, dtype="float32"),
                                          language=None, temperature=0.0,
                                          vad_filter=False)
                except Exception as cpu_error:
                    self.model = None
                    self.last_error = str(cpu_error)
                    logger.error(f"Local whisper cannot transcribe even on cpu "
                                 f"({cpu_error}); ears are off. {device_advice()}")

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        lang = language if language else self.config.language

        if not self.model:
            logger.error("Local whisper is not loaded.")
            return ""

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found at {audio_path}")
            return ""

        try:
            return self._transcribe_file(audio_path, lang)
        except Exception as e:
            if self.device == "cpu":
                self.last_error = str(e)
                logger.error(f"Local transcription failed: {e}")
                return ""
            # the turn is retried, not dropped: whoever spoke already waited
            # through the first attempt
            logger.warning(f"Transcription on {self.device} failed ({e}); "
                           f"falling back to cpu and retrying this audio. "
                           f"{device_advice()}")
            self.last_error = str(e)
            if self._use_cpu(f"transcription failed: {e}"):
                try:
                    return self._transcribe_file(audio_path, lang)
                except Exception as retry_error:
                    e = retry_error
            self.last_error = str(e)
            logger.error(f"Local transcription failed: {e}")
            return ""

    def _transcribe_file(self, audio_path: str, lang: Optional[str]) -> str:
        """One attempt, raising. The caller decides what a failure is worth."""
        model = self.model
        if model is None:
            raise RuntimeError("Local whisper is not loaded.")
        segments, _ = model.transcribe(audio_path,
                                       language=normalize_language(lang),
                                       temperature=0.0,
                                       vad_filter=self.vad)
        text = "".join(segment.text for segment in segments).strip()
        logger.info(f"Local transcription result: '{text}'")
        return text

    def status(self) -> dict:
        """Honest runtime state, for /status and the dashboard."""
        return {
            "provider": "faster_whisper",
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "loaded": self.model is not None,
            "degraded": self.degraded,
            "last_error": self.last_error,
        }

    def reload_config(self, config) -> None:
        """Rebuilds the model, but only when something about it actually changed.

        Loading is seconds and a possible download, so an unrelated save from
        the dashboard must not pay for it.
        """
        self.config = config
        wanted = _wanted(config)
        self.vad = bool(config.faster_whisper_vad)

        if wanted == self._configured:
            return

        self._configured = wanted
        self.model_name, _, _, self.download_root = wanted
        self.device, self.compute_type = _resolve_device(config)
        # a new device gets a clean verdict: the probe below re-marks it
        self.degraded = False
        self.last_error = None
        logger.info(f"Reloading local whisper: {self.model_name} on {self.device}")
        self.model = None
        self._load()
        self._probe()

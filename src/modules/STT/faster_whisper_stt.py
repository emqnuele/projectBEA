"""Whisper on this machine, through faster-whisper.

The other two transcribers send the audio somewhere. This one does not: the
weights live under `data/models/whisper`, nothing leaves the room, and there is
no key and no per-minute bill. The cost is the first run, which downloads the
model, and a CPU that is busy while she listens.
"""

import os
from typing import Optional

from src.core.config import BrainConfig
from src.interfaces.base_interfaces import STTInterface
from src.utils.huggingface import download_hint
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
        self._load()

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

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        lang = language if language else self.config.language

        if not self.model:
            logger.error("Local whisper is not loaded.")
            return ""

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found at {audio_path}")
            return ""

        try:
            segments, _ = self.model.transcribe(audio_path,
                                                language=normalize_language(lang),
                                                temperature=0.0,
                                                vad_filter=self.vad)
            text = "".join(segment.text for segment in segments).strip()
            logger.info(f"Local transcription result: '{text}'")
            return text
        except Exception as e:
            logger.error(f"Local transcription failed: {e}")
            return ""

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
        logger.info(f"Reloading local whisper: {self.model_name} on {self.device}")
        self.model = None
        self._load()

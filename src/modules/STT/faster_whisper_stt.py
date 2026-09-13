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
from src.utils.logger import get_logger

logger = get_logger("bea.stt.faster_whisper")

DEFAULT_MODEL = "small"

TOKEN_HINT = (
    "Hugging Face refused the download. The weights are public, so this is "
    "almost always a shared or office IP being rate-limited: wait a few minutes, "
    "or put HF_TOKEN=<your token> in .env (https://huggingface.co/settings/tokens) "
    "and it will be used for the download."
)

OFFLINE_HINT = (
    "The weights could not be reached. Check the connection, then start her "
    "again — the download resumes where it stopped."
)

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


def download_hint(error: Exception) -> Optional[str]:
    """A line the person reading the log can act on, for a download that failed.

    The library raises whatever huggingface_hub raised, which says `401` at
    someone who never knew an account was involved. Only the two cases with a
    real answer get a hint; everything else is left to speak for itself.
    """
    text = f"{type(error).__name__}: {error}".lower()

    if any(word in text for word in ("401", "403", "429", "gated", "rate limit",
                                     "too many requests", "unauthorized")):
        return TOKEN_HINT
    if any(word in text for word in ("connection", "timeout", "timed out",
                                     "network", "dns", "offline", "unreachable")):
        return OFFLINE_HINT
    return None


class FasterWhisperSTT(STTInterface):
    def __init__(self, config: BrainConfig):
        self.config = config
        self.model_name = normalize_model(config.stt_model)
        self.device = config.faster_whisper_device or "auto"
        self.compute_type = config.faster_whisper_compute_type or "auto"
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
            from faster_whisper import WhisperModel
        except ImportError:
            logger.error("faster-whisper is not installed — run `uv sync`.")
            return

        if self.download_root:
            os.makedirs(self.download_root, exist_ok=True)

        try:
            self.model = WhisperModel(self.model_name, device=self.device,
                                      compute_type=self._compute_type(),
                                      download_root=self.download_root)
            logger.info(f"Local whisper ready: {self.model_name} on {self.device}")
        except Exception as e:
            logger.error(f"Could not load local whisper {self.model_name!r}: {e}")
            hint = download_hint(e)
            if hint:
                logger.error(hint)

    def _compute_type(self) -> str:
        """`auto` means int8 on a cpu and float16 on a gpu, which is what you want.

        ctranslate2's own `default` keeps the weights at full precision, and on
        the cpu most people run this on that is several times slower for no
        accuracy anyone can hear.
        """
        if self.compute_type != "auto":
            return self.compute_type
        return "float16" if self.device == "cuda" else "int8"

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
        wanted = (normalize_model(config.stt_model),
                  config.faster_whisper_device or "auto",
                  config.faster_whisper_compute_type or "auto",
                  config.faster_whisper_download_root or None)
        self.vad = bool(config.faster_whisper_vad)

        if wanted == (self.model_name, self.device, self.compute_type, self.download_root):
            return

        self.model_name, self.device, self.compute_type, self.download_root = wanted
        logger.info(f"Reloading local whisper: {self.model_name} on {self.device}")
        self.model = None
        self._load()

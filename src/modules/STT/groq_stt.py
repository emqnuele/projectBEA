
import os
from typing import Optional

import httpx
from groq import DefaultHttpxClient, Groq, omit

from src.core.config import BrainConfig
from src.core.language import whisper_code
from src.interfaces.base_interfaces import STTInterface
from src.modules.STT.heard import HeardLanguage, clip_seconds
from src.utils.logger import get_logger

logger = get_logger("bea.stt.groq")

# how long the connection waits for the next turn. The sdk's own five seconds is
# shorter than most pauses in a call, so nearly every turn paid a new handshake:
# ~200ms in front of the transcription, measured with eight seconds between turns
KEEPALIVE_SECONDS = 90.0


class _KeptClient(DefaultHttpxClient):
    # the sdk closes a client it made itself once it is dropped, and one handed
    # in is left open: a new key would otherwise strand the old connections
    def __del__(self) -> None:
        if self.is_closed:
            return
        try:
            self.close()
        except Exception:
            pass


def _client(key: str) -> Groq:
    return Groq(api_key=key, http_client=_KeptClient(limits=httpx.Limits(
        max_connections=100, max_keepalive_connections=20,
        keepalive_expiry=KEEPALIVE_SECONDS)))


class GroqSTT(STTInterface):
    def __init__(self, config: BrainConfig):
        self.config = config

        # get key priority: config > env
        key = self.config.groq_key
        if not key:
            key = os.getenv("GROQ_API_KEY")

        if not key:
            logger.error("No API Key found.")
            self.client = None
        else:
            self.client = _client(key)

        self.model = self.config.stt_model or "whisper-large-v3-turbo"
        # a turn too short to place borrows the last one that was not. Same
        # problem here as on the local engine: it is the audio, not the api
        self.heard = HeardLanguage()

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        # resolved rather than passed through: the api rejects `jp` and `it-IT`,
        # and an unset language has to become "detect it" rather than the word
        lang = whisper_code(language if language else self.config.language)

        if not self.client:
            logger.error("Client not initialized.")
            return ""

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found at {audio_path}")
            return ""

        seconds = clip_seconds(audio_path)
        pin = self.heard.pin_for(lang, seconds)

        try:
            with open(audio_path, "rb") as file:
                transcription = self.client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), file.read()),
                    model=self.model,
                    # zero here means the opposite of what it means to the local
                    # library: this api raises the temperature itself until the
                    # decode clears its thresholds, which is the fallback the
                    # local one had to be given back by hand
                    temperature=0.0,
                    # the sdk's own sentinel rather than None: "detect it" is an
                    # omitted field here, and null is not a value it declares
                    language=pin if pin else omit,
                    response_format="verbose_json",
                )
                # verbose_json answers with what it heard, as a name rather than
                # a code — `src.core.language` knows both
                if pin is None:
                    self.heard.remember(getattr(transcription, "language", None), seconds)
                logger.info(f"Transcription result: '{transcription.text}'")
                return transcription.text
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ""

    def reload_config(self, config) -> None:
        """Updates model and re-initializes client if the API key changed."""
        if config.stt_model and config.stt_model != self.model:
            self.model = config.stt_model
            logger.info(f"Model updated to {self.model}")

        new_key = config.groq_key or os.getenv("GROQ_API_KEY")
        if new_key:
            current_key = getattr(self.client, 'api_key', None) if self.client else None
            if current_key != new_key:
                self.client = _client(new_key)
                logger.info("API client re-initialized with updated key.")
        elif not self.client:
            logger.warning("No API key available for reload.")

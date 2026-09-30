"""Whisper on any server speaking OpenAI's `/audio/transcriptions`.

speaches, LocalAI, a whisper.cpp server, vLLM, OpenAI itself: the owner brings
the url, the model and, when the server wants one, the key. Nothing here knows
which of them it is talking to, so everything a server may not implement is
asked for once and dropped when it is refused.
"""

import mimetypes
import os
from typing import Optional

import requests

from src.core.config import BrainConfig
from src.core.language import whisper_code
from src.interfaces.base_interfaces import STTInterface
from src.modules.STT.heard import HeardLanguage, clip_seconds
from src.utils.connections import stale
from src.utils.logger import get_logger
from src.utils.warm import Warmer

logger = get_logger("bea.stt.openai_compat")

# the openai name, and the one most self-hosted servers alias to their default
DEFAULT_MODEL = "whisper-1"
TIMEOUT_S = 30


def transcriptions_url(base_url: str) -> str:
    return base_url.strip().rstrip("/") + "/audio/transcriptions"


class OpenAICompatSTT(STTInterface):
    def __init__(self, config: BrainConfig):
        self.config = config
        self.base_url = (config.stt_compat_base_url or "").strip()
        self.key = config.stt_compat_key or ""
        self.model = config.stt_model or DEFAULT_MODEL
        # verbose_json is what says which language it heard; a server that
        # rejects it is asked for plain json from then on
        self.verbose = True
        self.heard = HeardLanguage()
        self._http = requests.Session()
        # honest state for /status and the dashboard, as the local engine keeps
        self.last_error: Optional[str] = None
        self.warm = Warmer(self._open_connection)
        if not self.base_url:
            logger.error("stt_compat_base_url is not set; she will not hear voice input.")

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        lang = whisper_code(language if language else self.config.stt_language)

        if not self.base_url:
            logger.error("No endpoint configured.")
            return ""
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found at {audio_path}")
            return ""

        seconds = clip_seconds(audio_path)
        pin = self.heard.pin_for(lang, seconds)

        try:
            with open(audio_path, "rb") as file:
                audio = file.read()
            response = self._send(audio_path, audio, pin)
            if response.status_code == 400 and self.verbose:
                logger.info("the endpoint refused verbose_json; asking for json from now on")
                self.verbose = False
                response = self._send(audio_path, audio, pin)
            if response.status_code != 200:
                self.last_error = f"{response.status_code}: {response.text[:300]}"
                logger.error(f"STT API error {self.last_error}")
                return ""
            result = response.json()
            text = result.get("text", "")
            if pin is None:
                self.heard.remember(result.get("language"), seconds)
            self.last_error = None
            logger.info(f"Transcription result: '{text}'")
            return text
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Transcription failed: {e}")
            return ""

    def status(self) -> dict:
        return {
            "provider": "openai_compat",
            "model": self.model,
            "endpoint": self.base_url,
            "loaded": bool(self.base_url),
            "degraded": self.last_error is not None,
            "last_error": self.last_error,
        }

    def _open_connection(self) -> None:
        if self.base_url:
            self._http.head(transcriptions_url(self.base_url), timeout=(10, 5)).close()

    def _send(self, audio_path: str, audio: bytes, pin: Optional[str]):
        data = {
            "model": self.model,
            "response_format": "verbose_json" if self.verbose else "json",
            "temperature": "0",
        }
        if pin:
            data["language"] = pin
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        mime = mimetypes.guess_type(audio_path)[0] or "application/octet-stream"
        files = {"file": (os.path.basename(audio_path), audio, mime)}
        url = transcriptions_url(self.base_url)
        try:
            return self._http.post(url, headers=headers, data=data, files=files, timeout=TIMEOUT_S)
        except requests.ConnectionError as e:
            if not stale(e):
                raise
            logger.debug(f"the kept connection had gone ({e}); sending again")
            return self._http.post(url, headers=headers, data=data, files=files, timeout=TIMEOUT_S)

    def reload_config(self, config) -> None:
        self.config = config
        model = config.stt_model or DEFAULT_MODEL
        if model != self.model:
            self.model = model
            logger.info(f"Model updated to {self.model}")
        url = (config.stt_compat_base_url or "").strip()
        if url != self.base_url:
            self.base_url = url
            # a different server may well speak verbose_json, and owes no old failure
            self.verbose = True
            self.last_error = None
            logger.info("Endpoint updated.")
        self.key = config.stt_compat_key or ""

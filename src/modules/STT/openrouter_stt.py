import base64
import os
from typing import Optional

import requests
from urllib3.exceptions import NewConnectionError

from src.core.config import BrainConfig
from src.core.language import whisper_code
from src.interfaces.base_interfaces import STTInterface
from src.modules.STT.heard import HeardLanguage, clip_seconds
from src.utils.logger import get_logger

logger = get_logger("bea.stt.openrouter")

class OpenRouterSTT(STTInterface):
    def __init__(self, config: BrainConfig):
        self.config = config

        # get key priority: config > env
        self.key = self.config.openrouter_key
        if not self.key:
            self.key = os.getenv("OPENROUTER_API_KEY")

        if not self.key:
            logger.error("No OpenRouter API Key found.")

        raw_model = self.config.stt_model or "openai/whisper-large-v3-turbo"
        if raw_model == "whisper-large-v3-turbo":
            self.model = "openai/whisper-large-v3-turbo"
        else:
            self.model = raw_model

        # a turn too short to place borrows the last one that was not. Same
        # problem here as on the local engine: it is the audio, not the api
        self.heard = HeardLanguage()
        # one connection kept between turns: a bare `requests.post` opened a new
        # one for every transcription, handshake and all
        self._http = requests.Session()

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        # resolved rather than passed through: the api rejects `jp` and `it-IT`,
        # and an unset language has to become "detect it" rather than the word
        lang = whisper_code(language if language else self.config.stt_language)

        if not self.key:
            logger.error("OpenRouter API Key not configured.")
            return ""

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found at {audio_path}")
            return ""

        seconds = clip_seconds(audio_path)
        pin = self.heard.pin_for(lang, seconds)

        try:
            # get audio format from file extension
            ext = os.path.splitext(audio_path)[1].lower().strip(".")
            if not ext:
                ext = "wav"

            with open(audio_path, "rb") as file:
                audio_data = base64.b64encode(file.read()).decode('utf-8')

            url = "https://openrouter.ai/api/v1/audio/transcriptions"
            headers = {
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "input_audio": {
                    "data": audio_data,
                    "format": ext
                }
            }
            if pin:
                payload["language"] = pin

            response = self._post(url, headers, payload)
            if response.status_code == 200:
                result = response.json()
                text = result.get("text", "")
                # not every model behind this endpoint says what it heard; one
                # that does not simply never settles a language, which leaves
                # short turns exactly where they were
                if pin is None:
                    self.heard.remember(result.get("language"), seconds)
                logger.info(f"OpenRouter Transcription result: '{text}'")
                return text
            else:
                logger.error(f"OpenRouter STT API error {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            logger.error(f"OpenRouter transcription failed: {e}")
            return ""

    def _post(self, url: str, headers: dict, payload: dict):
        """One request, sent again once if the kept connection had gone.

        The far end closes an idle connection when it likes, and the request
        that finds out fails before it was ever read — so it is the same
        request, not a second one. A timeout is not that, and is not retried.
        """
        try:
            return self._http.post(url, headers=headers, json=payload, timeout=30)
        except requests.ConnectionError as e:
            if not _stale(e):
                raise
            logger.debug(f"the kept connection had gone ({e}); sending again")
            return self._http.post(url, headers=headers, json=payload, timeout=30)

    def reload_config(self, config) -> None:
        """Updates model and API key if they changed."""
        raw_model = config.stt_model or "openai/whisper-large-v3-turbo"
        if raw_model == "whisper-large-v3-turbo":
            new_model = "openai/whisper-large-v3-turbo"
        else:
            new_model = raw_model

        if new_model != self.model:
            self.model = new_model
            logger.info(f"Model updated to {self.model}")

        new_key = config.openrouter_key or os.getenv("OPENROUTER_API_KEY")
        if new_key and new_key != self.key:
            self.key = new_key
            logger.info("OpenRouter API key reloaded.")


def _stale(error: requests.ConnectionError) -> bool:
    """A kept connection that had gone, rather than a host that cannot be reached.

    A new connection that fails — refused, unresolvable, a bad certificate —
    would only fail again, and a timeout would be waited out twice.
    """
    if isinstance(error, (requests.Timeout, requests.exceptions.SSLError)):
        return False
    reason = getattr(error.args[0], "reason", None) if error.args else None
    return not isinstance(reason, NewConnectionError)

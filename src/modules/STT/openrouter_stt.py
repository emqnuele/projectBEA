import os
import base64
from typing import Optional
import requests
from src.interfaces.base_interfaces import STTInterface
from src.core.config import BrainConfig
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

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        # use provided language or fall back to global config
        lang = language if language else self.config.language
        
        if not self.key:
            logger.error("OpenRouter API Key not configured.")
            return ""

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found at {audio_path}")
            return ""

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
            if lang:
                payload["language"] = lang

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                text = result.get("text", "")
                logger.info(f"OpenRouter Transcription result: '{text}'")
                return text
            else:
                logger.error(f"OpenRouter STT API error {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            logger.error(f"OpenRouter transcription failed: {e}")
            return ""

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

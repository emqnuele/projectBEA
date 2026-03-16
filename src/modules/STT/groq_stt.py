
import os
from typing import Optional
from groq import Groq
from src.interfaces.base_interfaces import STTInterface
from src.core.config import BrainConfig
from src.utils.logger import get_logger

logger = get_logger("bea.stt.groq")

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
            self.client = Groq(api_key=key)
            
        self.model = self.config.stt_model or "whisper-large-v3-turbo"

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        # use provided language or fall back to global config
        lang = language if language else self.config.language
        
        if not self.client:
            logger.error("Client not initialized.")
            return ""

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found at {audio_path}")
            return ""

        try:
            with open(audio_path, "rb") as file:
                transcription = self.client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), file.read()),
                    model=self.model,
                    temperature=0.0,
                    language=lang,
                    response_format="verbose_json",
                )
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
                self.client = Groq(api_key=new_key)
                logger.info("API client re-initialized with updated key.")
        elif not self.client:
            logger.warning("No API key available for reload.")

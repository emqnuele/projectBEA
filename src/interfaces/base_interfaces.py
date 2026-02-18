from abc import ABC, abstractmethod
from typing import Optional, Tuple, Union, Dict
from pathlib import Path
import asyncio

class LLMInterface(ABC):
    
    @abstractmethod
    def chat(self, user_input: str, system_prompt: Optional[str] = None, history: list = None) -> Tuple[str, str, Dict]:
        """
        Sends user input to the LLM and returns (mood, message, metadata).
        history: List of dictionaries [{"role": "user"|"assistant", "content": "..."}]
        """
        pass
    
    @abstractmethod
    def chat_audio(self, audio_path: str, system_prompt: Optional[str] = None, history: list = None) -> Tuple[str, str, Dict]:
        """
        Sends audio input to the LLM and returns (mood, message, metadata).
        """
    @abstractmethod
    def reload_config(self, config) -> None:
        """
        Reloads configuration (e.g. API keys, models) without restarting.
        """
        pass

    @abstractmethod
    def generate_json(self, user_input: str, system_prompt: Optional[str] = None, history: list = None) -> Dict:
        """
        Generates a JSON response from the LLM.
        Returns a dictionary parsed from the JSON output.
        """
        pass

class TTSInterface(ABC):
    @abstractmethod
    async def speak(self, text: str, output_device_id: int) -> None:
        """
        Generates audio from text and plays it to the specified device.
        """
        pass

    @abstractmethod
    async def generate_audio(self, text: str) -> Tuple[object, int]:
        """
        Generates audio from text.
        Returns (audio_data, sample_rate).
        audio_data: numpy array or valid sounddevice input.
        """
        pass

    @abstractmethod
    def reload_config(self, config) -> None:
        """
        Reloads configuration (e.g. voice, API keys) without restarting.
        """
        pass

class OBSInterface(ABC):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def reload_config(self, config) -> None:
        """
        Reloads configuration (e.g. host, port) without restarting.
        """
        pass

    @abstractmethod
    def set_image(self, image_path: Union[str, Path]) -> None:
        """
        Updates the image source in OBS.
        """
        pass

    @abstractmethod
    def set_media(self, media_path: Union[str, Path]) -> None:
        """
        Updates the media source in OBS.
        """
        pass

    @abstractmethod
    async def type_text(self, text: str, source_name: str, **kwargs) -> int:
        """
        Types text into the OBS text source with animation.
        Returns the final font size used.
        """
        pass
        
    @abstractmethod
    def set_text(self, text: str, source_name: str, font_size: Optional[int] = None) -> None:
        """
        Sets text immediately without animation.
        """
        pass

class STTInterface(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str, language: str = "en") -> str:
        """
        Transcribes audio file to text.
        audio_path: Absolute path to the audio file.
        language: Language code (default: "en").
        Returns the transcribed text.
        """
        pass

    @abstractmethod
    def reload_config(self, config) -> None:
        """
        Reloads configuration (e.g. API key, model) without restarting.
        """
        pass

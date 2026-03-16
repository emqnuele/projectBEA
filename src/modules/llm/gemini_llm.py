import os
import mimetypes
from pathlib import Path
from typing import Optional, Tuple, Union, Dict
import google.genai as genai
from src.interfaces.base_interfaces import LLMInterface
from src.utils.llm_utils import parse_llm_json
from src.utils.logger import get_logger

logger = get_logger("bea.llm.gemini")

class GeminiLLM(LLMInterface):
    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def reload_config(self, config) -> None:
        if config.gemini_key != self.api_key:
            logger.info("API Key updated. Re-initializing client...")
            self.api_key = config.gemini_key
            self.client = genai.Client(api_key=self.api_key)
        
        if config.gemini_model != self.model_name:
             logger.info(f"Model updated to {config.gemini_model}")
             self.model_name = config.gemini_model

    def _send_request(self, contents: list, system_prompt: Optional[str] = None, history: list = None) -> Tuple[str, str, dict]:
        # use the sdk's explicit type for configuration
        generate_config = genai.types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=system_prompt
        )

        # prepare messages properly
        
        final_contents = []
        
        if history:
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                final_contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        
        # append current user input/content
        # normalize 'contents' to ensure all parts are valid part objects (dicts)
        normalized_parts = []
        for item in contents:
            if isinstance(item, str):
                normalized_parts.append({"text": item})
            else:
                normalized_parts.append(item)
        
        final_contents.append({"role": "user", "parts": normalized_parts})

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=final_contents,
                config=generate_config
            )
            text = response.text or ""
            return parse_llm_json(text)
        except Exception as e:
            logger.error(f"API Error: {e}")
            return "sad", "There's some problem with my AI", {}

    def chat(self, user_input: str, system_prompt: Optional[str] = None, history: list = None) -> Tuple[str, str, dict]:
        return self._send_request([user_input], system_prompt, history)

    def chat_audio(self, audio_path: Union[str, Path], system_prompt: Optional[str] = None, history: list = None) -> Tuple[str, str, dict]:
        path_obj = Path(audio_path)
        if not path_obj.exists():
             return "confused", "I cannot hear you (audio file missing).", {}
        
        mime_type, _ = mimetypes.guess_type(path_obj)
        mime_type = mime_type or "audio/wav"
        
        audio_bytes = path_obj.read_bytes()
        audio_part = {"inline_data": {"mime_type": mime_type, "data": audio_bytes}}
        
        # append prompt to audio
        contents = [audio_part, "Please reply to this audio message in JSON format with 'mood' and 'message'."]
        
        return self._send_request(contents, system_prompt, history)

    def generate_json(self, user_input: str, system_prompt: Optional[str] = None, history: list = None) -> Union[Dict, list]:
        
        # if system_prompt is none, create one
        if not system_prompt:
             system_prompt = "You are a helpful assistant. Output ONLY valid JSON."
        else:
             system_prompt += "\nOutput ONLY valid JSON."
        
        generate_config = genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=system_prompt
        )
        
        contents = [{"role": "user", "parts": [{"text": user_input}]}]
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=generate_config
            )
            text = response.text or "{}"
            _, _, data = parse_llm_json(text)
            return data
        except Exception as e:
            logger.error(f"JSON generation error: {e}")
            return {}

from typing import Optional, Tuple, Union, Dict
from groq import Groq
from src.interfaces.base_interfaces import LLMInterface, STTInterface
from src.utils.llm_utils import parse_llm_json
from src.utils.logger import get_logger

logger = get_logger("bea.llm.groq")

class GroqLLM(LLMInterface):
    def __init__(self, api_key: str, model_name: str = "llama3-70b-8192", stt_interface: Optional[STTInterface] = None):
        self.api_key = api_key
        # ensure we have a key before initializing client ideally, but client checks too.
        self.client = Groq(api_key=api_key)
        self.model_name = model_name
        self.stt = stt_interface

    def reload_config(self, config) -> None:
        if config.groq_key != self.api_key:
            self.api_key = config.groq_key
            self.client = Groq(api_key=self.api_key)
        
        if config.groq_model != self.model_name:
             self.model_name = config.groq_model

    def chat(self, user_input: str, system_prompt: Optional[str] = None, history: list = None) -> Tuple[str, str, dict]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        
        messages.append({"role": "user", "content": user_input})

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7 
            )
            
            reply_content = response.choices[0].message.content
            return parse_llm_json(reply_content)
        except Exception as e:
            logger.error(f"API Error: {e}")
            return "sad", f"Groq Error: {str(e)[:50]}...", {}

    def chat_audio(self, audio_path: str, system_prompt: Optional[str] = None, history: list = None) -> Tuple[str, str, dict]:
        if not self.stt:
            return "neutral", "I cannot hear you (STT module not configured).", {}
            
        # 1. transcribe
        transcription = self.stt.transcribe(audio_path)
        if not transcription:
            logger.info("Transcription empty.")
            return "neutral", "I heard nothing.", {}
            
        logger.info(f"Delegating transcription to chat: {transcription}")
        
        return self.chat(transcription, system_prompt, history)

    def generate_json(self, user_input: str, system_prompt: Optional[str] = None, history: list = None) -> Union[Dict, list]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        messages.append({"role": "user", "content": user_input})

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7 
            )
            
            reply_content = response.choices[0].message.content
            _, _, data = parse_llm_json(reply_content)
            return data
        except Exception as e:
            logger.error(f"JSON generation error: {e}")
            return {}

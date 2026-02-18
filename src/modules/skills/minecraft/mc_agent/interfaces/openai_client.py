from openai import OpenAI, OpenAIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Dict, Any, Optional, List
import json
from ..core.config import Config
from .llm_interface import LLMInterface
from ..utils.logger import setup_logger

logger = setup_logger("OpenAIClient")

class OpenAIClient(LLMInterface):
    def __init__(self):
        Config.validate()
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL
        logger.info(f"Initialized OpenAI Client with model: {self.model}")

    @retry(
        retry=retry_if_exception_type(OpenAIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def generate_response(
        self, 
        system_prompt: str, 
        user_message: str, 
        tools: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Generates a response using OpenAI Chat Completion API.
        Includes automatic retries for network/API errors.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        logger.info("Sending request to OpenAI (JSON Mode)...")
        
        try:
            # we use response_format={"type": "json_object"} to ensure validity
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"} 
            )

            choice = response.choices[0]
            content_str = choice.message.content
            
            if not content_str:
                raise ValueError("Received empty response from OpenAI")

            logger.debug(f"Raw LLM Response: {content_str}")

            # parse json
            try:
                response_data = json.loads(content_str)
            except json.JSONDecodeError as e:
                logger.error(f"LLM returned invalid JSON: {content_str}")
                raise e
            
            return response_data

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            raise e

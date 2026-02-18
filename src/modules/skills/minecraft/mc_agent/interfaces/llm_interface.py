from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class LLMInterface(ABC):
    """Abstract Base Class for LLM Providers"""
    
    @abstractmethod
    def generate_response(
        self, 
        system_prompt: str, 
        user_message: str, 
        tools: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Generates a response from the LLM.
        
        Args:
            system_prompt (str): The persistent system instruction.
            user_message (str): The current state/context from the user.
            tools (list, optional): List of functional tools available to the Model.
            
        Returns:
            Dict[str, Any]: Standardized response containing either text or tool calls.
            Structure:
            {
                "content": str,          # Text response (reasoning)
                "tool_calls": list       # List of tool calls (name, arguments)
            }
        """
        pass

import datetime
import json
from pathlib import Path
from typing import List, Dict, Optional
from rich.console import Console
from src.interfaces.base_interfaces import LLMInterface

console = Console()

class DiaryGenerator:
    def __init__(self, llm: LLMInterface):
        self.llm = llm
        self._load_prompt()

    def _load_prompt(self):
        try:
            prompt_path = Path(__file__).parent / "diary_prompt.txt"
            if prompt_path.exists():
                self.prompt_template = prompt_path.read_text(encoding="utf-8")
            else:
                self.prompt_template = "You are a diary writer. Summarize the following conversation in JSON."
        except Exception as e:
            console.print(f"[red]DiaryGenerator: Error loading prompt: {e}[/red]")
            self.prompt_template = ""

    async def generate_diary(self, history: List[Dict]) -> Optional[Dict]:
        console.print(f"[cyan]DiaryGenerator: Generating diary with active LLM...[/cyan]")
        
        # 1. format history
        conversation_text = ""
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            conversation_text += f"{role}: {content}\n"

        # 2. prepare prompt
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        system_prompt = self.prompt_template.replace("{date}", today_str)
        user_prompt = f"CONVERSATION HISTORY:\n{conversation_text}\n\nExisting Tags: []"

        # 3. call llm        
        try:
            return self.llm.generate_json(user_prompt, system_prompt)
        except Exception as e:
            console.print(f"[red]DiaryGenerator: Generation failed: {e}[/red]")
            return None

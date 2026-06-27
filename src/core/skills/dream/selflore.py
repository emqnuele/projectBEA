import json
from pathlib import Path
from typing import Any, Dict, List

from src.utils.logger import get_logger

logger = get_logger("bea.skills.dream.selflore")

DEFAULT_SELF = """\
# What's true about me right now

(this is my own evolving memory of myself — separate from my soul, which never
changes. things I learn about myself, running jokes with chat, recent wins.)
"""


class SelfLore:
    """Bea's evolving self-knowledge: stable facts about HER (not her soul).

    `self.md` is free text, always injected. `self_profile.json` holds the few
    structured bits the morning pass needs (e.g. birthday) without parsing prose.
    The dreamer is allowed to grow this; the soul stays untouched.
    """

    def __init__(self, self_path: str = "data/memory/self.md",
                 profile_path: str = "data/memory/self_profile.json"):
        self.self_path = Path(self_path)
        self.profile_path = Path(profile_path)
        self.self_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.self_path.exists():
            self.self_path.write_text(DEFAULT_SELF, encoding="utf-8")

    def render(self) -> str:
        try:
            text = self.self_path.read_text(encoding="utf-8").strip()
            return text
        except Exception as e:
            logger.error(f"SelfLore: failed to read: {e}")
            return ""

    def render_for_prompt(self, max_facts: int = 15) -> str:
        """Capped view for the system prompt: header + the most recent facts only,
        so a growing self-lore never bloats the context."""
        facts = self.facts()
        if not facts:
            return ""
        shown = facts[-max_facts:]
        return "\n".join(f"- {f}" for f in shown)

    def facts(self) -> List[str]:
        out = []
        for line in self.render().splitlines():
            s = line.strip()
            if s.startswith("- "):
                out.append(s[2:].strip())
        return out

    def append_fact(self, fact: str) -> bool:
        fact = fact.strip()
        if not fact or fact in self.facts():
            return False
        try:
            with self.self_path.open("a", encoding="utf-8") as f:
                f.write(f"\n- {fact}")
            return True
        except Exception as e:
            logger.error(f"SelfLore: failed to append: {e}")
            return False

    def profile(self) -> Dict[str, Any]:
        if not self.profile_path.exists():
            return {}
        try:
            return json.loads(self.profile_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

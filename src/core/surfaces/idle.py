from typing import Optional

from src.core.surfaces.base import Surface
from src.utils.prompts import load_text


class IdleSurface(Surface):
    """The passage of time. Contributes the idle/monologue behaviour rules.

    It pushes no input itself — the bus synthesises IDLE perceptions via
    `wait_or_idle`. This surface only supplies the prompt section telling Bea how
    to behave when nothing is happening (go on a tangent, no needy questions).
    """

    name = "idle"

    def initialize(self) -> None:
        path = self.config.skills.get("monologue", {}).get("prompt_path", "data/prompts/monologue.md")
        self._rules = load_text(path)

    async def start(self) -> None:
        self.active = True

    @property
    def context_section(self) -> Optional[str]:
        return self._rules or None

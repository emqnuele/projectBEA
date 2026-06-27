class Notebook:
    """The agent's private, in-memory working memory.

    A single freeform text blob the model fully rewrites via `update`. It is
    re-injected into the agent's perception every cycle so the plan survives
    history trimming, but it is never spoken — it is the persona's scratchpad,
    not output.
    """

    def __init__(self) -> None:
        self.content = ""

    def update(self, notes: str) -> str:
        self.content = (notes or "").strip()
        return "Notebook saved." if self.content else "Notebook cleared."

    def render(self) -> str:
        return self.content or "(empty — think about your goal and write a detailed plan before acting)"

"""What fell out of the rolling context.

`_trim` used to keep the system message and the last N turns and drop the rest
on the floor. An hour into a stream the first half had, as far as she was
concerned, never happened — she would ask something she had already been told,
or lose an argument she had already won.

So the dropped turns are held, and once enough of them pile up the background
model condenses them into one line she keeps carrying.
"""

from typing import Any, Dict, List

from src.utils.logger import get_logger

logger = get_logger("bea.mind.recap")

# one line she carries every turn: it has to stay cheap
MAX_RECAP_CHARS = 400

# how many dropped turns are worth a model call
CONDENSE_AFTER = 8

# what is worth keeping at all
_WORTH_KEEPING = {"user", "assistant"}

SYSTEM = (
    "You keep a running one-line memory of a conversation for someone who cannot "
    "see the beginning of it any more. Given what came before and what has just "
    "scrolled out of view, write ONE short paragraph, at most 60 words, in the "
    "second person ('you...'), covering what happened and what still matters. "
    "Facts and threads only — no commentary, no preamble."
)


class SessionRecap:
    """The story so far, in one line."""

    def __init__(self, condense_after: int = CONDENSE_AFTER):
        self.condense_after = max(1, int(condense_after))
        self._summary = ""
        self._dropped: List[str] = []

    # --- collecting ---------------------------------------------------------

    def drop(self, messages: List[Dict[str, Any]]) -> None:
        """Hands over what the context is about to forget."""
        for message in messages:
            if message.get("role") not in _WORTH_KEEPING:
                continue
            content = (message.get("content") or "").strip()
            if content:
                self._dropped.append(f"{message['role']}: {content}")

    @property
    def pending(self) -> int:
        return len(self._dropped)

    @property
    def due(self) -> bool:
        return self.pending >= self.condense_after

    # --- condensing ---------------------------------------------------------

    def set(self, summary: str) -> None:
        self._summary = (summary or "").strip()[:MAX_RECAP_CHARS]

    async def condense(self, llm) -> bool:
        """Folds what was dropped into the summary. Keeps it on failure."""
        if not self._dropped:
            return False
        payload = "\n".join(self._dropped)
        if self._summary:
            payload = f"THE STORY SO FAR:\n{self._summary}\n\nJUST SCROLLED OUT:\n{payload}"

        try:
            reply = await llm.complete([
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": payload},
            ])
        except Exception as e:
            # losing the model call must not also lose the turns it was for
            logger.warning(f"Could not condense the session recap: {e}")
            return False

        text = (getattr(reply, "content", "") or "").strip()
        if not text:
            return False
        self.set(text)
        self._dropped.clear()
        return True

    # --- what she sees ------------------------------------------------------

    def render(self) -> str:
        if not self._summary:
            return ""
        return f"[EARLIER THIS SESSION]\n{self._summary}"

    def reset(self) -> None:
        self._summary = ""
        self._dropped.clear()

"""The slow clock: one pass over everything she might do without being asked.

Kept separate from the loop that runs it so "what happens on a tick" is a
thing you can test in a millisecond instead of a thing you wait fifteen
minutes for.
"""


from src.utils.logger import get_logger

logger = get_logger("bea.social.rhythm")


class RhythmTick:
    """Runs the kept intentions, then the idle-chatter pass."""

    def __init__(self, *, agenda=None, spontaneous=None):
        self.agenda = agenda
        self.spontaneous = spontaneous

    async def run_once(self) -> int:
        """Returns how many conversations she opened. One failure never stops the rest."""
        # intentions first: having a reason beats having a gap, and filling the
        # silence with small talk right before remembering she meant to say
        # something is exactly how a bot gives itself away
        started = 0
        for label, runner in (("agenda", self.agenda), ("spontaneous", self.spontaneous)):
            if runner is None:
                continue
            try:
                started += await runner.run_once() or 0
            except Exception as e:
                logger.error(f"Rhythm pass '{label}' failed: {e}")
        return started

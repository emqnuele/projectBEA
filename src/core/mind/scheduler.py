"""One turn at a time per conversation; different conversations in parallel.

Without this, two messages in the SAME channel would be answered concurrently:
replies out of order, or one reply per message (flood). Different channels stay
concurrent, which is the whole point — Bea holds a conversation at the bar and
answers her phone at the same time.

The coalescing is the interesting half, and it adds **no artificial latency**:
messages that arrive *while* a turn is generating do not start a new turn, they
mark the running one to re-run. When it finishes, one extra pass re-reads the
history, which by then already contains them. So three messages in a row get one
answer, and the first message waits no longer than it otherwise would.

Ported from riba/engine/scheduler.py.
"""

import asyncio
from typing import Awaitable, Callable, Dict

from src.utils.logger import get_logger

logger = get_logger("bea.mind.scheduler")


class _State:
    __slots__ = ("running", "pending")

    def __init__(self) -> None:
        self.running = False   # a turn is executing for this key
        self.pending = False   # more arrived during it → re-run


class ConversationScheduler:
    """Runs turns serialized per key, coalescing messages that arrive together."""

    def __init__(self, *, max_coalesced_runs: int = 3) -> None:
        # safety cap: in a very busy channel we do not want endless re-runs.
        # past the cap new messages simply do not force another pass — the next
        # real turn will cover them anyway.
        self._max = max(1, max_coalesced_runs)
        self._states: Dict[str, _State] = {}

    @property
    def active_keys(self) -> list:
        return [k for k, s in self._states.items() if s.running]

    def is_running(self, key: str) -> bool:
        state = self._states.get(key)
        return bool(state and state.running)

    async def submit(self, key: str, turn: Callable[[bool], Awaitable[None]]) -> bool:
        """Runs `turn` serialized under `key`.

        `turn(first)` gets True on the first execution and False on coalescing
        re-runs, so the caller can (for example) quote the original message only
        once. Returns True if the turn ran, False if it was folded into one
        already in flight.
        """
        state = self._states.setdefault(key, _State())
        if state.running:
            state.pending = True
            return False

        state.running = True
        try:
            await turn(True)
            runs = 1
            while state.pending and runs < self._max:
                state.pending = False
                runs += 1
                await turn(False)
            if state.pending:
                logger.info(f"'{key}' hit the coalescing cap; the next turn will cover the rest.")
        finally:
            # no awaits between here and the pop, so no other submit can
            # interleave and the state stays consistent
            state.running = False
            self._states.pop(key, None)
        return True

    async def drain(self, timeout: float = 5.0) -> None:
        """Waits for the in-flight turns to finish (used on shutdown)."""
        deadline = asyncio.get_event_loop().time() + timeout
        while self.active_keys and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)

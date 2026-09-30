"""Opening a connection before the request that needs it.

A remote engine's first request after a quiet spell pays a tcp and tls
handshake — measured at ~200ms in front of a groq transcription. Opening the
socket while somebody is still talking, or while the mind is still thinking,
takes that off the turn. Once is enough while the pool still holds it.
"""

import threading
import time
from typing import Callable

from src.utils.logger import get_logger

logger = get_logger("bea.warm")

# well inside the keepalive every engine here keeps: a warm socket is not re-warmed
EVERY_S = 20.0


class Warmer:
    def __init__(self, open_connection: Callable[[], None], every_s: float = EVERY_S):
        self._open = open_connection
        self._every = every_s
        self._last = float("-inf")
        self._lock = threading.Lock()

    def __call__(self) -> None:
        """Opens the connection unless it was opened a moment ago. Never raises."""
        with self._lock:
            now = time.monotonic()
            if now - self._last < self._every:
                return
            self._last = now
        try:
            self._open()
        except Exception as e:
            # found out again, properly, by the request it was meant to speed up
            logger.debug(f"warming a connection failed: {e}")

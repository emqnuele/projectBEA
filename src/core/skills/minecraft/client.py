import asyncio
import json
import threading
import time
from typing import Any, Dict, List, Optional

import websocket

from src.utils.logger import get_logger

logger = get_logger("bea.skills.minecraft.client")

# how long to wait for a mod completion event before giving up on an action
ACTION_TIMEOUT = 60.0

# statuses the mod sends when a long-running action finishes
_COMPLETION = {"FINISHED", "IDLE"}

# packets that are senses rather than answers: they are handed to the surface
_TYPED_EVENTS = {"chat", "player_event", "combat", "death_event"}


class MinecraftClient:
    """WebSocket bridge to the Minecraft mod, exposed as the agent's environment.

    The mod streams game-state packets and sends status events when an action
    completes. `execute()` sends a command and awaits its completion event,
    turning the async mod protocol into a simple "call tool -> get observation"
    contract for the agent loop. All state mutation happens on the asyncio loop
    thread via `call_soon_threadsafe`, so no locks are needed.
    """

    def __init__(self, url: str, loop: asyncio.AbstractEventLoop, on_event=None):
        self.url = url
        self.loop = loop
        # typed packets (chat, player_event, combat, death) go straight to the
        # surface: they are senses, not the result of an action she asked for
        self.on_event = on_event
        self.ws: Optional[websocket.WebSocketApp] = None
        self.keep_running = True
        self.is_connected = False

        self.latest_state: Dict[str, Any] = {}
        self._pending: Optional[asyncio.Future] = None
        self._events: "asyncio.Queue[str]" = asyncio.Queue()
        self._connected = asyncio.Event()
        self._first_state = asyncio.Event()

        self._thread = threading.Thread(target=self._run_forever, daemon=True)

    # --- lifecycle ---

    def connect(self) -> None:
        logger.info(f"Connecting to Minecraft mod at {self.url}")
        self._thread.start()

    def stop(self) -> None:
        self.keep_running = False
        if self.ws:
            self.ws.close()
        if self._thread.is_alive():
            self._thread.join(timeout=0.2)
        logger.info("MinecraftClient stopped.")

    async def wait_until_ready(self) -> None:
        """Resolves once connected and the first game state has arrived."""
        await self._connected.wait()
        await self._first_state.wait()

    # --- agent-facing api ---

    async def execute(self, action: str, params: Dict[str, Any], instant: bool = False) -> str:
        """Sends a command and returns the resulting observation.

        For `instant` actions (chat, screenshot, ...) the mod emits no
        completion event, so we return immediately. Otherwise we await the
        next FINISHED/IDLE/INTERRUPTED event.
        """
        payload = {"action": action, "parameters": params}

        if instant:
            self._send(payload)
            return "SENT"

        fut = self.loop.create_future()
        self._pending = fut
        self._send(payload)
        try:
            return await asyncio.wait_for(fut, timeout=ACTION_TIMEOUT)
        except asyncio.TimeoutError:
            return "TIMEOUT: no completion event from the mod (action may still be running)."
        finally:
            self._pending = None

    def drain_events(self) -> List[str]:
        """Returns and clears any notable events (interrupts) seen since last call."""
        events: List[str] = []
        while not self._events.empty():
            events.append(self._events.get_nowait())
        return events

    async def wait_for_event_or_timeout(self, timeout: float) -> None:
        """Blocks until an interrupt event arrives or `timeout` elapses (pacing)."""
        try:
            event = await asyncio.wait_for(self._events.get(), timeout=timeout)
            self._events.put_nowait(event)  # put it back for drain_events
        except asyncio.TimeoutError:
            pass

    # --- websocket plumbing (runs on background thread) ---

    def _send(self, data: Dict[str, Any]) -> None:
        if self.ws and self.is_connected:
            try:
                self.ws.send(json.dumps(data))
            except Exception as e:
                logger.error(f"Failed to send: {e}")
        else:
            logger.warning("Tried to send while disconnected.")

    def _run_forever(self) -> None:
        while self.keep_running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=lambda ws, e: logger.error(f"WS error: {e}"),
                    on_close=self._on_close,
                )
                self.ws.run_forever()
                if self.keep_running:
                    logger.warning("Connection lost. Retrying in 5s...")
                    time.sleep(5)
            except Exception as e:
                logger.error(f"Connection loop error: {e}")
                time.sleep(5)

    def _on_open(self, ws) -> None:
        self.is_connected = True
        logger.info("Connected to Minecraft mod.")
        self.loop.call_soon_threadsafe(self._connected.set)

    def _on_close(self, ws, code, msg) -> None:
        self.is_connected = False
        logger.info("Disconnected from Minecraft mod.")

    def _on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from mod: {message[:120]}")
            return
        # hand off to the asyncio loop thread for all state handling
        self.loop.call_soon_threadsafe(self._handle, data)

    def _handle(self, data: Dict[str, Any]) -> None:
        """Dispatches on `type` FIRST, then on `status`.

        Half of what the mod sends used to fall on the floor here: it only
        recognised packets with a `player` key and the FINISHED/IDLE/INTERRUPTED
        statuses. The full death event — cause, coordinates, what she lost — was
        already being sent, and was silently discarded every time.
        """
        kind = data.get("type")
        if kind in _TYPED_EVENTS:
            self._emit(kind, data)
            # a death also ends whatever she was doing: leaving the caller to
            # time out for 60 seconds would be a lie about what happened
            if kind == "death_event":
                self._resolve_pending("INTERRUPTED: you died.")
            return

        status = data.get("status")

        # game-state snapshot
        if "player" in data or kind == "game_state":
            self.latest_state = data
            if not self._first_state.is_set():
                self._first_state.set()

        if status == "ENGAGED_AUTO_ACTION":
            # self-defence kicked in on its own; she should know she is fighting
            self._emit("auto_action", data)
            return

        if status == "INTERRUPTED":
            reason = data.get("reason") or data.get("event", {}).get("reason", "unknown emergency")
            observation = f"INTERRUPTED: {reason}"
            logger.warning(observation)
            if self._pending and not self._pending.done():
                self._pending.set_result(observation)
            else:
                self._events.put_nowait(observation)
            return

        if status in _COMPLETION:
            result = data.get("result", "SUCCESS")
            message = data.get("message", "")
            observation = f"{result}" + (f": {message}" if message else "")
            if self._pending and not self._pending.done():
                self._pending.set_result(observation)

    def _emit(self, kind: str, data: Dict[str, Any]) -> None:
        if self.on_event is None:
            logger.debug(f"No handler for mod event '{kind}'.")
            return
        try:
            self.on_event(kind, data)
        except Exception as e:
            logger.error(f"Handling mod event '{kind}' failed: {e}")

    def _resolve_pending(self, observation: str) -> None:
        if self._pending and not self._pending.done():
            self._pending.set_result(observation)

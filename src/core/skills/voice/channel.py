"""The live audio link to the bot: the only way sound reaches a call.

Before this, audio could only leave the brain as the return value of an HTTP
request the bot had made — so Bea could answer, and nothing else. She could not
speak into a silence, could not react to something she overheard, and a turn
that said two sentences delivered only the first one to the room.

This is the missing pipe, and it is deliberately dumb: it moves frames and
reports what was actually played. Every decision — whether to speak, when to
stop, what to say — stays above it.

Wire format, brain -> bot:
  binary  [uint32 header length][header json][pcm payload]
  text    {"type": "stop" | "duck" | "cancel", ...}

The header travels with its payload in one frame on purpose: a reconnect in the
middle of an utterance then loses that utterance, not the parser's mind.
"""

import asyncio
import json
import struct
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from src.core.expression.pcm import duration_ms
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice.channel")

# how many finished utterances stay addressable for a late playback report
HISTORY = 8


def frame(header: Dict[str, Any], payload: bytes = b"") -> bytes:
    """One self-contained binary frame. Pure: the socket is somebody else's job."""
    blob = json.dumps(header, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(blob)) + blob + payload


def unframe(data: bytes) -> "tuple[Dict[str, Any], bytes]":
    """The inverse, for the tests and for anyone reading a capture."""
    if len(data) < 4:
        raise ValueError("frame too short to hold a header length")
    (size,) = struct.unpack(">I", data[:4])
    if len(data) < 4 + size:
        raise ValueError("frame shorter than its declared header")
    return json.loads(data[4:4 + size].decode("utf-8")), data[4 + size:]


@dataclass
class Utterance:
    """One thing she said out loud, and how much of it the room actually got."""

    id: str
    text: str = ""
    sent_ms: int = 0
    played_ms: int = 0
    state: str = "pending"  # pending | playing | done | stopped
    done: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def complete(self) -> bool:
        """Whether the room heard essentially all of it.

        The tolerance is one player frame: the bot reports what it has pushed,
        and demanding an exact match would report a clean finish as a cut-off.
        """
        return self.state == "done" or self.played_ms >= self.sent_ms - 60


class VoiceChannel:
    """The bot's audio socket, plus what is playing on it right now.

    One socket, because there is one bot process. `live` is the question every
    caller actually has: can sound reach a room right now?
    """

    def __init__(self):
        self._ws = None
        self.channel_id: Optional[str] = None
        self.listeners: int = 0
        self.utterances: "OrderedDict[str, Utterance]" = OrderedDict()
        self.current: Optional[Utterance] = None
        # the bot is the authority on which call she is in: she can be dragged
        # into one, or pulled out of one, without the brain having asked
        self.on_call_change: Optional[Callable[[Optional[str], int], None]] = None
        # the bot heard-it-first report: the only honest end of the latency clock
        self.on_first_sound: Optional[Callable[[], None]] = None

    # --- the socket ---------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._ws is not None

    @property
    def live(self) -> bool:
        """Connected *and* sitting in a voice channel: sound would be heard."""
        return self._ws is not None and self.channel_id is not None

    def attach(self, ws) -> None:
        if self._ws is not None:
            logger.warning("a second bot connected to the voice channel; keeping the newer one")
        self._ws = ws
        logger.info("voice push channel attached")

    def detach(self, ws=None) -> None:
        """Drops the socket. A stale socket must not silently swallow her voice."""
        if ws is not None and ws is not self._ws:
            return
        self._ws = None
        self.channel_id = None
        self.listeners = 0
        self._abandon_current("the bot went away")
        self._announce_call()
        logger.info("voice push channel detached")

    # --- brain -> bot -------------------------------------------------------

    async def play(self, pcm: bytes, *, utterance_id: str, text: str = "",
                   seq: int = 0, last: bool = True) -> bool:
        """Queues audio in the call. Returns whether it left the building."""
        if not pcm:
            return False
        utterance = self.utterances.get(utterance_id)
        if utterance is None:
            utterance = self._track(Utterance(id=utterance_id, text=text))
            self.current = utterance
        utterance.sent_ms += duration_ms(pcm)
        return await self._send(frame(
            {"type": "play", "utterance_id": utterance_id, "seq": seq, "last": last},
            pcm,
        ))

    async def end(self, utterance_id: str) -> bool:
        """Closes an utterance: the last sentence has been sent, nothing follows."""
        if utterance_id not in self.utterances:
            return False
        return await self._send(frame(
            {"type": "play", "utterance_id": utterance_id, "seq": -1, "last": True}, b"",
        ))

    async def stop(self, ramp_ms: int = 200, timeout: float = 1.0) -> Optional[Utterance]:
        """Fades out what is playing and waits to hear how far it got.

        The answer is the point: without it she believes she said the whole
        sentence, and refers later to half a line nobody heard.
        """
        utterance = self.current
        if utterance is None:
            return None
        await self._send_json({"type": "stop", "utterance_id": utterance.id,
                               "ramp_ms": ramp_ms})
        try:
            await asyncio.wait_for(utterance.done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug(f"no playback report for {utterance.id}; assuming it all played")
            utterance.played_ms = utterance.sent_ms
        return utterance

    async def duck(self, gain: float, ramp_ms: int = 250) -> bool:
        """Turns her down without stopping her — the soft half of a barge-in."""
        if self.current is None:
            return False
        return await self._send_json({"type": "duck", "utterance_id": self.current.id,
                                      "gain": max(0.0, min(1.0, gain)), "ramp_ms": ramp_ms})

    async def cancel_pending(self) -> bool:
        """Drops what has not started yet, leaving what is already sounding alone."""
        if self.current is None:
            return False
        return await self._send_json({"type": "cancel", "utterance_id": self.current.id})

    # --- bot -> brain -------------------------------------------------------

    def on_message(self, message: Dict[str, Any]) -> None:
        """Folds one report from the bot into the state. Never raises."""
        kind = str(message.get("type", ""))
        if kind == "joined":
            self.channel_id = str(message.get("channel_id") or "") or None
            self.listeners = int(message.get("listeners") or 0)
            logger.info(f"bot joined voice channel {self.channel_id} ({self.listeners} listener(s))")
            self._announce_call()
        elif kind == "left":
            self.channel_id = None
            self.listeners = 0
            self._abandon_current("she left the call")
            self._announce_call()
        elif kind == "members":
            self.listeners = int(message.get("listeners") or 0)
            self._announce_call()
        elif kind == "playback":
            self._on_playback(message)

    def _announce_call(self) -> None:
        if self.on_call_change is None:
            return
        try:
            self.on_call_change(self.channel_id, self.listeners)
        except Exception as e:  # a listener must never break the socket loop
            logger.debug(f"call-change listener failed: {e}")

    def _on_playback(self, message: Dict[str, Any]) -> None:
        utterance = self.utterances.get(str(message.get("utterance_id", "")))
        if utterance is None:
            return
        if utterance.state == "pending" and self.on_first_sound is not None:
            try:
                self.on_first_sound()
            except Exception as e:
                logger.debug(f"first-sound listener failed: {e}")
        utterance.played_ms = max(utterance.played_ms, int(message.get("played_ms") or 0))
        state = str(message.get("state") or "playing")
        utterance.state = state
        if state in ("done", "stopped"):
            utterance.done.set()
            if self.current is utterance:
                self.current = None

    # --- internals ----------------------------------------------------------

    def _track(self, utterance: Utterance) -> Utterance:
        self.utterances[utterance.id] = utterance
        while len(self.utterances) > HISTORY:
            self.utterances.popitem(last=False)
        return utterance

    def _abandon_current(self, why: str) -> None:
        if self.current is None:
            return
        logger.debug(f"utterance {self.current.id} abandoned: {why}")
        self.current.state = "stopped"
        self.current.done.set()
        self.current = None

    async def _send_json(self, message: Dict[str, Any]) -> bool:
        return await self._send(json.dumps(message, separators=(",", ":")))

    async def _send(self, payload) -> bool:
        """A dead socket is a fact to report, never an exception to propagate."""
        ws = self._ws
        if ws is None:
            return False
        try:
            if isinstance(payload, bytes):
                await ws.send_bytes(payload)
            else:
                await ws.send_text(payload)
            return True
        except Exception as e:
            logger.warning(f"voice push channel failed mid-send: {e}")
            self.detach(ws)
            return False

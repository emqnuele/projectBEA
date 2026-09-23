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

bot -> brain:
  text    {"type": "joined" | "left" | "members" | "playback" | "hearing", ...}

The header travels with its payload in one frame on purpose: a reconnect in the
middle of an utterance then loses that utterance, not the parser's mind.
"""

import asyncio
import json
import struct
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.core.expression.pcm import duration_ms
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice.channel")

# how many finished utterances stay addressable for a late playback report
HISTORY = 8

# how far back to look when asking what she has just said. Longer than the
# longest turn the bot will ever send, so a line still counts as recent while
# its own echo is still being gathered up and transcribed.
RECENT_SECONDS = 25.0

# how long somebody can be believed to be talking without the bot saying they
# stopped. Past the longest turn the bot sends, so only a lost message hits it.
TALKING_MAX_S = 35.0

# how long a turn can be on its way to the transcriber before it is given up on
TRANSCRIPT_MAX_S = 15.0


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
    # how many times the bot had to resume this line on a fresh stream. Purely
    # for the record: a resume is when the player ran dry and the count could
    # have started over, so it is worth seeing in production
    resumed: int = 0
    state: str = "pending"  # pending | playing | done | stopped
    done: asyncio.Event = field(default_factory=asyncio.Event)
    # monotonic: this is only ever used to ask "how long ago", and a wall clock
    # that steps backwards would answer that with a negative number
    at: float = field(default_factory=time.monotonic)

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
        # who is talking right now, and since when
        self.talking: Dict[str, float] = {}
        # turns that left the bot and have not been transcribed yet, oldest first
        self.awaiting: Dict[str, List[float]] = {}
        # somebody started, sent a turn, or stopped: (user_id, state)
        self.on_hearing: Optional[Callable[[str, str], None]] = None
        self._hearing_changed = asyncio.Event()

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
        had = self._ws is not None or self.channel_id is not None
        self._ws = None
        self.channel_id = None
        self.listeners = 0
        self._forget_hearing()
        self._abandon_current("the bot went away")
        self._announce_call()
        if had:
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
        # a line arrives in pieces and the first of them is not all of it
        if text and len(text) > len(utterance.text):
            utterance.text = text
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
            # no report is not proof she was heard. Claiming the whole line
            # would make a cut-off look complete, and she would go on referring
            # to words the room never got
            logger.debug(f"no playback report for {utterance.id}; not assuming it played")
            utterance.state = "stopped"
            # the bot not answering does not mean it still holds the floor: left
            # set, `current` outlived the utterance and every later turn read her
            # as still speaking — against a call nobody was hearing
            utterance.done.set()
            if self.current is utterance:
                self.current = None
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
            self._forget_hearing()
            self._abandon_current("she left the call")
            self._announce_call()
        elif kind == "members":
            self.listeners = int(message.get("listeners") or 0)
            self._announce_call()
        elif kind == "playback":
            self._on_playback(message)
        elif kind == "hearing":
            self._on_hearing(message)

    # --- somebody talking -----------------------------------------------------

    def busy(self) -> bool:
        """Whether somebody is talking, or a turn of theirs is still being transcribed.

        A turn only reaches the mind once it is over and transcribed, seconds
        after the person started it. This is the part of it she can know sooner:
        the rest of a sentence is on its way.
        """
        now = time.monotonic()
        if any(now - since <= TALKING_MAX_S for since in self.talking.values()):
            return True
        return any(now - sent <= TRANSCRIPT_MAX_S
                   for turns in self.awaiting.values() for sent in turns)

    def transcribed(self, user_id: Optional[str]) -> None:
        """A turn of theirs is transcribed, whatever came of it."""
        turns = self.awaiting.get(str(user_id)) if user_id is not None else None
        if not turns:
            return
        turns.pop(0)
        if not turns:
            del self.awaiting[str(user_id)]
        self._hearing_changed.set()

    async def until_quiet(self, timeout: float) -> bool:
        """Waits until nobody is talking and nothing is on its way. False at the limit."""
        deadline = time.monotonic() + timeout
        while self.busy():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._hearing_changed.clear()
            # woken by a change, or often enough to notice a state timing out
            try:
                await asyncio.wait_for(self._hearing_changed.wait(), timeout=min(remaining, 0.25))
            except asyncio.TimeoutError:
                pass
        return True

    def _on_hearing(self, message: Dict[str, Any]) -> None:
        user = str(message.get("user_id") or "")
        state = str(message.get("state") or "")
        if not user:
            return
        now = time.monotonic()
        if state == "start":
            self.talking[user] = now
        elif state == "sent":
            self.awaiting.setdefault(user, []).append(now)
        elif state == "end":
            self.talking.pop(user, None)
        else:
            return
        self._hearing_changed.set()
        if self.on_hearing is not None:
            try:
                self.on_hearing(user, state)
            except Exception as e:  # a listener must never break the socket loop
                logger.debug(f"hearing listener failed: {e}")

    def _forget_hearing(self) -> None:
        self.talking.clear()
        self.awaiting.clear()
        self._hearing_changed.set()

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
        resumed = int(message.get("resumed") or 0)
        if resumed > utterance.resumed:
            utterance.resumed = resumed
            logger.info(f"utterance {utterance.id} resumed {resumed} time(s) after the player ran dry")
        state = str(message.get("state") or "playing")
        utterance.state = state
        if state in ("done", "stopped"):
            utterance.done.set()
            if self.current is utterance:
                self.current = None

    # --- internals ----------------------------------------------------------

    def recent_texts(self, within: float = RECENT_SECONDS) -> "list[str]":
        """What she has said out loud in the last few seconds, newest first.

        Read by the echo guard, which has to tell her own voice coming back off
        somebody's speakers from something they actually said. Bounded in time
        on purpose: the same sentence ten minutes later is somebody quoting her.
        """
        now = time.monotonic()
        return [u.text for u in reversed(self.utterances.values())
                if u.text and now - u.at <= within]

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

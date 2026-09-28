"""Her voice on this machine: one output stream, kept open, fed by one thread.

The obvious way — `sounddevice.play()` once per sentence — is what sounddevice
itself calls a convenience for small scripts, and it breaks in three ways that
are all worse on an output with some latency (a bluetooth headset, most USB
interfaces, plenty of Windows and Linux setups):

- every sentence stops the stream of the one before and opens a new one: a gap,
  and on bluetooth the tail of the sentence before is still in the pipe and is
  thrown away;
- opening and closing are synchronous and cost 50-230 ms each time, on the one
  event loop the brain, the call and the dashboard share;
- it feeds the device from a python callback asked for every few hundred
  samples, so any other thread holding the GIL starves it into crackles.

So one stream stays open while she talks, in blocking mode, and a thread of
its own writes into it in short chunks. `write()` releases the GIL while it
waits, which is what keeps her voice whole while the rest of the engine works.
Only a little is ever written ahead (`audio_buffer_ms`), so a barge-in is heard
within that much plus the device's own latency.

Everything that has to match what the room hears — the mouth, the caption of a
sentence, a change of face, the end of the line — is scheduled on the moment
the audio reaches the speaker: what is still queued, plus the device's latency.

The device is chosen by name, never by position: a monitor or a headset
plugged in moves every index along. PortAudio only learns about devices when it
starts, so it is restarted whenever the stream is about to be opened again.
"""

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple, Union

import numpy as np

from src.utils.logger import get_logger

logger = get_logger("bea.expression.player")

# how much audio is written ahead of the speaker by default
DEFAULT_BUFFER_MS = 100
# the floor under it: less and the writer cannot keep up with a busy machine
MIN_BUFFER_MS = 20

# how long an idle stream stays open before the device is let go
DEFAULT_IDLE_CLOSE_S = 30.0

# holes are said at most this often: a busy stretch is one warning, not one per sentence
HOLES_WARNING_EVERY_S = 30.0

# the least room worth waking up to fill: small enough that a stop lands quickly
CHUNK_MS = 10

# a stop fades out over this much instead of clicking
FADE_MS = 12

# what every bundled engine produces; a line opens the stream in this format before its first piece
# exists, and an engine that makes something else costs one reopen at that piece
FIRST_FORMAT = (24000, 1)

# only what this module does to portaudio may run at once: a restart under a
# device listing on another thread is a crash in C
PORTAUDIO_LOCK = threading.RLock()

Selector = Union[str, int, None]

# where windows' mme api cuts a device name
MME_NAME_LENGTH = 31


def _backend():
    import sounddevice as sd
    return sd


# --- choosing a device ---------------------------------------------------------


def output_devices(sd=None) -> List[Dict[str, Any]]:
    """Every output portaudio can see, with its index, name and whether it is the default."""
    sd = sd or _backend()
    with PORTAUDIO_LOCK:
        devices = list(sd.query_devices())
        default = _default_output(sd)
    return [
        {"id": index, "name": str(device.get("name", f"Device {index}")),
         "channels": int(device.get("max_output_channels", 0)),
         "latency_ms": round(float(device.get("default_low_output_latency", 0.0) or 0.0) * 1000),
         "default": index == default}
        for index, device in enumerate(devices)
        if int(device.get("max_output_channels", 0) or 0) > 0
    ]


def _default_output(sd) -> Optional[int]:
    try:
        default = sd.default.device
        index = default[1] if isinstance(default, (list, tuple)) else default
        index = int(index)
        return index if index >= 0 else None
    except Exception:
        return None


def selector_of(config) -> Selector:
    """What the config asks for: a device name, a legacy index, or None for the system default."""
    name = str(getattr(config, "audio_device", "") or "").strip()
    if name:
        return name
    index = getattr(config, "audio_device_id", None)
    return int(index) if isinstance(index, int) and not isinstance(index, bool) else None


def resolve(selector: Selector, devices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The output a selector means today, or None when it is not there.

    A name matches exactly first, then without case, then as the start of a
    longer name when the shorter one is 31 characters long: Windows' oldest host
    api cuts names there, so the same device can be listed shortened.
    """
    if selector is None:
        return next((d for d in devices if d["default"]), devices[0] if devices else None)
    if isinstance(selector, int):
        return next((d for d in devices if d["id"] == selector), None)
    wanted = selector.strip()
    folded = wanted.casefold()
    for match in (
        lambda d: d["name"] == wanted,
        lambda d: d["name"].casefold() == folded,
        lambda d: _truncated_match(folded, d["name"].casefold()),
    ):
        found = [d for d in devices if match(d)]
        if found:
            # the default's own entry first, so the host api the system prefers wins a tie
            return next((d for d in found if d["default"]), found[0])
    return None


def _truncated_match(a: str, b: str) -> bool:
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= MME_NAME_LENGTH and longer.startswith(shorter)


def candidates(selector: Selector, devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The asked-for output first, then the system default, then any other output."""
    out: List[Dict[str, Any]] = []
    for device in (resolve(selector, devices), resolve(None, devices), *devices):
        if device is not None and device not in out:
            out.append(device)
    return out


# --- what the writer is handed ---------------------------------------------------


@dataclass
class _Piece:
    audio: np.ndarray
    rate: int
    loop: asyncio.AbstractEventLoop
    # resolved when the next piece may be queued behind this one without a gap
    handoff: asyncio.Future
    generation: int
    # run on the loop when the first sample reaches the speaker
    on_heard: Optional[Callable[[], None]] = None


@dataclass
class _Mark:
    """A point in what has been queued; `fire` runs on the loop when the room hears it."""

    loop: asyncio.AbstractEventLoop
    fire: Callable[[], None]
    generation: int
    # fired even after a flush: somebody is waiting on it, not decorating with it
    always: bool = False


@dataclass
class _Open:
    """The stream the writer holds, and what it was opened for."""

    stream: Any
    device: Dict[str, Any]
    rate: int
    channels: int
    # the most write_available has read: the size of portaudio's ring
    capacity: int
    # the device's own delay after the ring, as portaudio reports it
    latency: float
    last_used: float = field(default_factory=time.monotonic)


def as_playable(audio) -> np.ndarray:
    """Float32 in [-1, 1], mono or (frames, channels), whatever the engine handed over."""
    data = np.asarray(audio)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    return np.ascontiguousarray(data, dtype=np.float32)


class LocalPlayer:
    """The local sound card, as a queue that never makes the event loop wait."""

    def __init__(self, *, backend=None, clock: Callable[[], float] = time.monotonic,
                 selector: Selector = None, buffer_ms: int = DEFAULT_BUFFER_MS,
                 idle_close_s: float = DEFAULT_IDLE_CLOSE_S, latency_s: float = 0.0) -> None:
        self._sd = backend
        self._clock = clock
        self._selector: Selector = selector
        self._buffer_ms = max(MIN_BUFFER_MS, int(buffer_ms))
        self._idle_close_s = float(idle_close_s)
        # 0 asks portaudio for its own default, the quickest to the speaker; more buys a bigger ring
        self._latency_s = max(0.0, float(latency_s))
        self._queue: Deque[Union[_Piece, _Mark]] = deque()
        self._wake = threading.Condition()
        self._thread: Optional[threading.Thread] = None
        # which writer is the live one: a writer from before a close stops, even while a new one starts
        self._runner = 0
        # bumped by every flush: whatever was queued before it is dropped
        self._generation = 0
        self._open: Optional[_Open] = None
        # the rate and channels of the last piece, so a line can have the stream ready before its first
        self._last_format: Tuple[int, int] = FIRST_FORMAT
        self._want_prepare = False
        self._want_reopen = False
        # when the last thing timed on her voice is heard, and in which generation: nothing queued
        # after it may fire before it, and a flush starts the count again
        self._last_heard: Tuple[int, float] = (0, 0.0)
        # a device that refused, warned about once until it works again
        self._warned: set = set()
        self._silent_warned = False
        # counters a test or a probe can read
        self.starved = 0
        self.opened = 0
        self._holes_said_at: Optional[float] = None

    # --- what the loop calls ------------------------------------------------

    def configure(self, *, selector: Selector, buffer_ms: int = DEFAULT_BUFFER_MS,
                  idle_close_s: float = DEFAULT_IDLE_CLOSE_S, latency_s: float = 0.0) -> None:
        """New settings. A different device takes effect at the next piece, never mid-word."""
        latency_s = max(0.0, float(latency_s))
        with self._wake:
            if selector != self._selector or latency_s != self._latency_s:
                self._selector = selector
                self._latency_s = latency_s
                self._want_reopen = True
                self._warned.clear()
                self._silent_warned = False
            self._buffer_ms = max(MIN_BUFFER_MS, int(buffer_ms))
            self._idle_close_s = float(idle_close_s)
            self._wake.notify_all()

    def prepare(self) -> None:
        """A line is starting: have the stream open by the time its first piece is made."""
        with self._wake:
            self._want_prepare = True
            self._wake_writer()

    async def play(self, audio, rate: int, on_heard: Optional[Callable[[], None]] = None) -> None:
        """Queues one piece and returns once the next may be queued behind it without a gap.

        `on_heard` runs on this loop when the piece's first sample reaches the
        speaker. Cancelling the wait stops everything queued.
        """
        data = as_playable(audio)
        if data.size == 0:
            return
        loop = asyncio.get_running_loop()
        with self._wake:
            handoff = loop.create_future()
            self._queue.append(_Piece(data, int(rate), loop, handoff, self._generation, on_heard))
            self._wake_writer()
        try:
            await handoff
        except asyncio.CancelledError:
            self.flush()
            raise

    def mark(self, fire: Callable[[], None]) -> None:
        """Runs `fire` on this loop when everything queued so far has started being heard."""
        loop = asyncio.get_running_loop()
        with self._wake:
            self._queue.append(_Mark(loop, fire, self._generation))
            self._wake_writer()

    async def drained(self) -> None:
        """Returns when the room has heard the end of everything queued, or it was flushed."""
        loop = asyncio.get_running_loop()
        done = loop.create_future()

        def finish() -> None:
            if not done.done():
                done.set_result(None)

        with self._wake:
            self._queue.append(_Mark(loop, finish, self._generation, always=True))
            self._wake_writer()
        await done

    def flush(self) -> None:
        """Stops her now: the chunk being written fades out and everything queued is dropped."""
        with self._wake:
            self._generation += 1
            dropped = list(self._queue)
            self._queue.clear()
            self._wake.notify_all()
        # nobody may be left waiting on a piece that will never be heard
        _let_go(dropped)

    def close(self) -> None:
        """Lets the device go. Best-effort and quick: it runs on the way down."""
        self.flush()
        with self._wake:
            self._runner += 1
            thread, self._thread = self._thread, None
            self._wake.notify_all()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.5)

    @property
    def device_name(self) -> Optional[str]:
        current = self._open
        return current.device["name"] if current is not None else None

    # --- the writer ---------------------------------------------------------

    def _wake_writer(self) -> None:
        """Called holding the lock: wakes the writer, or starts one when there is none."""
        self._wake.notify_all()
        if self._thread is None:
            self._runner += 1
            self._thread = threading.Thread(target=self._run, args=(self._runner,), daemon=True, name="voice-out")
            self._thread.start()

    def _stopped(self, runner: int) -> bool:
        return runner != self._runner

    def _run(self, runner: int) -> None:
        try:
            while True:
                with self._wake:
                    while not self._queue and not self._want_prepare and not self._stopped(runner):
                        if self._open is None:
                            # nothing to say and no device held: the writer goes, and the next piece starts one
                            if self._thread is threading.current_thread():
                                self._thread = None
                            return
                        timeout = self._idle_timeout()
                        if timeout is not None and timeout <= 0:
                            break
                        self._wake.wait(timeout)
                    if self._stopped(runner):
                        break
                    item = self._queue.popleft() if self._queue else None
                    prepare, self._want_prepare = self._want_prepare, False
                if item is None:
                    idle = self._idle_timeout()
                    if prepare:
                        self._stream_for(*self._last_format)
                    elif self._open is not None and idle is not None and idle <= 0:
                        logger.debug(f"letting go of {self._open.device['name']} after {self._idle_close_s:.0f} s of silence")
                        self._close_stream()
                    continue
                if isinstance(item, _Mark):
                    self._schedule(item)
                else:
                    self._write_piece(item)
        except Exception as e:
            logger.error(f"the voice output stopped: {type(e).__name__}: {e}")
            with self._wake:
                if self._thread is threading.current_thread():
                    self._thread = None
        # a writer replaced after a close must not touch what its successor holds
        with self._wake:
            owner = self._thread is None
        if owner:
            self._close_stream()
            self._release_all()

    def _idle_timeout(self) -> Optional[float]:
        current = self._open
        if current is None or self._idle_close_s <= 0:
            return None
        return current.last_used + self._idle_close_s - self._clock()

    def _heard_in(self) -> float:
        """Seconds until a sample written now reaches the speaker."""
        current = self._open
        if current is None:
            return 0.0
        return self._queued(current) / current.rate + current.latency

    def _heard_at(self) -> float:
        """The monotonic moment a sample written now is heard, never before anything timed earlier."""
        at = time.monotonic() + self._heard_in()
        generation, last = self._last_heard
        if generation == self._generation:
            at = max(at, last + 1e-6)
        self._last_heard = (self._generation, at)
        return at

    def _queued(self, current: _Open) -> int:
        try:
            available = int(current.stream.write_available)
        except Exception:
            return 0
        # the ring reads smaller right after it starts than it is: the most room ever seen is its size
        if available > current.capacity:
            current.capacity = available
        return current.capacity - available

    def _schedule(self, mark: _Mark) -> None:
        if mark.generation != self._generation:
            if mark.always:
                _post(mark.loop, mark.fire)
            return
        _post_at(mark.loop, mark.fire, self._heard_at(), self, mark.generation, mark.always)

    def _write_piece(self, piece: _Piece) -> None:
        if piece.generation != self._generation:
            _resolve(piece.loop, piece.handoff)
            return
        channels = 1 if piece.audio.ndim == 1 else int(piece.audio.shape[1])
        self._last_format = (piece.rate, channels)
        current = self._stream_for(piece.rate, channels)
        if current is None:
            self._pace_silently(piece)
            return
        data = self._fit(piece.audio, current.channels)
        position = 0
        total = len(data)
        chunk = max(1, current.rate * CHUNK_MS // 1000)
        retried = False
        handed = False
        holes = 0
        while position < total:
            if piece.generation != self._generation or self._thread is not threading.current_thread():
                self._fade_out(current, data[position:])
                break
            lead = current.rate * self._buffer_ms // 1000
            queued = self._queued(current)
            # never more than the ring has free, so the write returns at once and a stop is never stuck behind it
            room = min(lead, current.capacity) - queued
            if room < min(chunk, total - position):
                # sleeping until a chunk's worth is free, never for a fixed tick: the writer wakes when it is needed
                time.sleep(min(0.02, max(0.001, (chunk - room) / current.rate)))
                continue
            # all the room at once: a writer that woke late (the gil was busy) catches up in one write
            end = min(total, position + room)
            if position == 0 and piece.on_heard is not None:
                # timed here, with the stream open and the queue ahead of it known
                _post_at(piece.loop, piece.on_heard, self._heard_at(), self, piece.generation)
            try:
                underflow = current.stream.write(data[position:end])
            except Exception as e:
                if retried:
                    logger.error(f"{current.device['name']} stopped taking audio ({e}); the rest of this piece is lost")
                    break
                retried = True
                logger.warning(f"{current.device['name']} stopped taking audio ({e}); reopening")
                self._close_stream()
                reopened = self._stream_for(piece.rate, channels)
                if reopened is None:
                    break
                current = reopened
                data = self._fit(piece.audio, current.channels)
                continue
            if underflow and position > 0:
                # mid-piece, not between two: the writer fell behind and the room heard a hole
                self.starved += 1
                holes += 1
            position = end
            current.last_used = self._clock()
            if not handed and total - position <= lead:
                handed = True
                _resolve(piece.loop, piece.handoff)
        if not handed:
            _resolve(piece.loop, piece.handoff)
        if holes:
            self._say_holes(holes, current)

    def _say_holes(self, holes: int, current: _Open) -> None:
        # a recording is where these are heard, long after the moment: the log is the only witness
        now = self._clock()
        if self._holes_said_at is not None and now - self._holes_said_at < HOLES_WARNING_EVERY_S:
            return
        self._holes_said_at = now
        logger.warning(f"her voice skipped {holes} time(s) on {current.device['name']}: this process "
                       f"was too busy to keep the speaker fed ({self.starved} since start)")

    def _pace_silently(self, piece: _Piece) -> None:
        # no device at all: the line still takes as long as it would have, so everything timed on it holds
        duration = len(piece.audio) / max(1, piece.rate)
        deadline = self._clock() + duration
        while self._clock() < deadline:
            if piece.generation != self._generation or self._thread is not threading.current_thread():
                break
            time.sleep(min(0.02, max(0.0, deadline - self._clock())))
        _resolve(piece.loop, piece.handoff)

    def _fade_out(self, current: _Open, rest: np.ndarray) -> None:
        frames = min(len(rest), current.rate * FADE_MS // 1000)
        if frames <= 0:
            return
        ramp = np.linspace(1.0, 0.0, frames, dtype=np.float32)
        tail = rest[:frames] * (ramp if rest.ndim == 1 else ramp[:, None])
        try:
            current.stream.write(np.ascontiguousarray(tail, dtype=np.float32))
        except Exception as e:
            logger.debug(f"the fade-out did not reach the device: {e}")

    @staticmethod
    def _fit(audio: np.ndarray, channels: int) -> np.ndarray:
        if audio.ndim == 1:
            return audio
        if audio.shape[1] == channels:
            return audio
        if channels == 1:
            return np.ascontiguousarray(audio.mean(axis=1), dtype=np.float32)
        return np.ascontiguousarray(audio[:, :channels], dtype=np.float32)

    # --- the stream ---------------------------------------------------------

    def _stream_for(self, rate: int, channels: int) -> Optional[_Open]:
        """The open stream if it fits this audio, or a new one on the best output there is."""
        current = self._open
        if current is not None and not self._want_reopen and current.rate == rate \
                and current.channels == min(channels, current.device["channels"]):
            # a line about to start counts as use: the idle timer must not close it under her first word
            current.last_used = self._clock()
            return current
        if current is not None:
            self._drain(current)
            self._close_stream()
        self._want_reopen = False
        return self._open_best(rate, channels)

    def _drain(self, current: _Open) -> None:
        # a new stream must not cut the end of the audio still in the old one
        deadline = self._clock() + self._queued(current) / current.rate + current.latency
        while self._clock() < deadline and self._thread is threading.current_thread():
            time.sleep(0.005)

    def _open_best(self, rate: int, channels: int) -> Optional[_Open]:
        sd = self._sd or _backend()
        self._sd = sd
        with PORTAUDIO_LOCK:
            _restart(sd)
            devices = output_devices(sd)
        wanted = resolve(self._selector, devices)
        for device in candidates(self._selector, devices):
            try:
                opened = self._open_on(sd, device, rate, channels)
            except Exception as e:
                if device["name"] not in self._warned:
                    self._warned.add(device["name"])
                    logger.warning(f"could not open {device['name']} for her voice ({e})")
                continue
            self._warned.discard(device["name"])
            if wanted is None or device["id"] != wanted["id"]:
                asked = self._selector if self._selector is not None else "the system default"
                logger.warning(f"audio output {asked!r} is not available; speaking on {device['name']} instead")
            else:
                logger.info(f"speaking on {device['name']} (about {opened.latency * 1000:.0f} ms to the speaker)")
            self._open = opened
            self._silent_warned = False
            return opened
        if not self._silent_warned:
            self._silent_warned = True
            logger.error("no usable audio output device found; her voice is silent here")
        return None

    def _open_on(self, sd, device: Dict[str, Any], rate: int, channels: int) -> _Open:
        fitted = max(1, min(channels, device["channels"]))
        with PORTAUDIO_LOCK:
            extra = {"latency": self._latency_s} if self._latency_s > 0 else {}
            stream = sd.OutputStream(samplerate=rate, device=device["id"], channels=fitted, dtype="float32", **extra)
            try:
                stream.start()
                capacity = int(stream.write_available)
            except Exception:
                stream.close()
                raise
        self.opened += 1
        return _Open(stream=stream, device=device, rate=rate, channels=fitted, capacity=capacity,
                     latency=float(device.get("latency_ms", 0)) / 1000.0, last_used=self._clock())

    def _close_stream(self) -> None:
        current, self._open = self._open, None
        if current is None:
            return
        with PORTAUDIO_LOCK:
            try:
                current.stream.abort()
            except Exception:
                pass
            try:
                current.stream.close()
            except Exception as e:
                logger.debug(f"closing the voice output failed: {e}")

    def _release_all(self) -> None:
        with self._wake:
            dropped = list(self._queue)
            self._queue.clear()
        _let_go(dropped)


def _let_go(dropped: List[Union[_Piece, _Mark]]) -> None:
    """Wakes everyone waiting on items that will never play."""
    for item in dropped:
        if isinstance(item, _Piece):
            _resolve(item.loop, item.handoff)
        elif item.always:
            _post(item.loop, item.fire)


def _restart(sd) -> None:
    """Makes portaudio list the devices there are now, not the ones there were when it started."""
    terminate = getattr(sd, "_terminate", None)
    initialize = getattr(sd, "_initialize", None)
    if terminate is None or initialize is None:
        return
    try:
        terminate()
        initialize()
    except Exception as e:
        logger.debug(f"refreshing the audio devices failed: {e}")


def _resolve(loop: asyncio.AbstractEventLoop, future: asyncio.Future) -> None:
    def settle() -> None:
        if not future.done():
            future.set_result(None)
    _post(loop, settle)


def _post(loop: asyncio.AbstractEventLoop, fn: Callable[[], None]) -> None:
    try:
        loop.call_soon_threadsafe(fn)
    except RuntimeError:
        # the loop is gone: whoever waited on it is gone with it
        pass


def _post_at(loop: asyncio.AbstractEventLoop, fn: Callable[[], None], at: float,
             player: "LocalPlayer", generation: int, always: bool = False) -> None:
    """Runs `fn` on the loop at the monotonic moment `at`, in the order the moments were given."""

    def fire() -> None:
        # a flush between queueing and hearing means the room never heard it
        if generation != player._generation and not always:
            return
        try:
            fn()
        except Exception as e:
            logger.error(f"something timed on her voice failed: {e}")

    def arm() -> None:
        loop.call_at(at - time.monotonic() + loop.time(), fire)
    _post(loop, arm)

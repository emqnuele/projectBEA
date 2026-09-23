import asyncio
import contextlib
import uuid
from typing import Any, List, Optional, Tuple

import numpy as np

from src.core.config import BrainConfig
from src.core.events import EventCategory, EventManager
from src.core.expression.live import LiveLine, Rendered
from src.core.expression.pcm import ENVELOPE_FPS, CallResampler, duration_ms, envelope
from src.core.expression.prosody import for_mood
from src.core.mind.moods import DEFAULT_MOOD, normalize_mood
from src.interfaces.base_interfaces import AvatarInterface, CaptionInterface, TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.expression")


class Expression:
    """The single output sink for everything Bea expresses.

    Owns the VOICE actuator: TTS generation, local audio playback, the avatar and
    the caption and barge-in/interruption. Every surface that
    used to roll its own speech path (chat, discord voice, minecraft thoughts,
    monologue) routes through here so the rendering logic lives in one place.

    It drives two ports and knows neither of their backends: whether the avatar
    is a PNG in OBS, a VRM in a browser source or a Live2D model in VTube Studio
    is a line of config, not a branch in here.

    Routes:
    - "local"  -> generate audio and play it on the configured device (stream/OBS).
    - "call"   -> generate audio, drive only the visuals, and push the samples
                  into the live voice call through the push channel.

    The call is a sink she *owns*, not a reply she hands back: nothing outside
    this class puts sound anywhere, which is the only reason ducking, stopping
    and knowing how far a sentence got can live in one place.
    """

    def __init__(self, config: BrainConfig, tts: TTSInterface, avatar: AvatarInterface,
                 caption: CaptionInterface, event_manager: EventManager):
        self.config = config
        self.tts = tts
        self.avatar = avatar
        self.caption = caption
        self.event_manager = event_manager

        # the last mood she was seen in, so a state change (falling asleep)
        # does not silently reset her face to neutral
        self._mood = DEFAULT_MOOD

        # what she goes back to when a line ends. `idle` most of the time, but
        # she is still listening after a line in a call and still asleep after
        # one she talked in her sleep: snapping back to idle would throw that away
        self._resting = "idle"

        self._is_speaking = False
        self.current_typing_task: Optional[asyncio.Task] = None
        self.current_speech_task: Optional[asyncio.Task] = None
        self.audio_lock = asyncio.Lock()

        self._playback_device_id = None

        # the live call, when there is one; the voice skill hands it over
        self.call = None
        # how she has been feeling; the brain hands it over, None means neutral
        self.affect = None
        # the last utterance a barge-in cut short, for the mind to be told about
        self.interrupted = None
        # the line being said right now, when there is one
        self._line: Optional[LiveLine] = None
        # how a word she wrote inline becomes something she actually has. The
        # brain swaps these for ones that match by meaning; on their own they
        # only recognise what is already spelled correctly.
        self._match_mood = normalize_mood
        self._match_clip = lambda word: word

        # a call line's visuals run in their own task; it must be held onto, or
        # the garbage collector can cancel it between two sentences
        self._visual_tasks = set()

    def set_state(self, state: str, mood: Optional[str] = None) -> None:
        """A visible state that is not speech: sleeping, listening, idle.

        The state travels beside the mood rather than in place of it, so falling
        asleep does not also decide what her face is doing.
        """
        if mood is not None:
            self._mood = mood
        self._resting = state
        if self.is_speaking:
            # mid-line. Someone walking into the call is where she goes *back* to,
            # not a reason to take the talking face off her halfway through a word
            return
        self.avatar.show(self._mood, state)

    def set_ports(self, avatar: AvatarInterface, caption: CaptionInterface) -> None:
        """Swaps the backends under her, mid-run, without dropping the mood."""
        self.avatar = avatar
        self.caption = caption
        self.avatar.show(self._mood, self._resting)

    def reload_config(self, config: BrainConfig) -> None:
        self.config = config
        self.avatar.reload_config(config)
        self.caption.reload_config(config)

    # --- VOICE actuator -----------------------------------------------------

    @property
    def is_speaking(self) -> bool:
        """Sound of hers is coming out of something, somewhere, right now.

        The call has the last word: the OBS animation used to stand in for this,
        and it only ever knew the *estimated* length of the audio, not whether
        the room was still hearing it.
        """
        call = self.call
        if call is not None and call.current is not None:
            return True
        return self._is_speaking

    @is_speaking.setter
    def is_speaking(self, value: bool) -> None:
        self._is_speaking = bool(value)

    def set_call(self, call) -> None:
        """Hands over the live voice call, or None when there is none."""
        self.call = call

    def set_affect(self, affect) -> None:
        """Hands over what her standing mood is read from."""
        self.affect = affect

    def set_matchers(self, mood=None, clip=None) -> None:
        """How the words she writes inline are turned into things she has."""
        if mood is not None:
            self._match_mood = mood
        if clip is not None:
            self._match_clip = clip

    def match_mood(self, word: str) -> str:
        return self._match_mood(word)

    def match_clip(self, word: str) -> str:
        return self._match_clip(word)

    def prosody_for(self, mood: str, feeling=None):
        """How this line should sound, or None when nothing should colour it.

        `feeling` is how she felt when she decided to say it. The mind hands it
        down because local speech is rendered in a task that starts after the
        turn has already moved on — reading it here would colour the line with
        its own mood and flatten the difference between a first sharp remark and
        twenty minutes of being furious.
        """
        if self.affect is None or not self.affect.enabled:
            return None
        return for_mood(mood, self.affect.current if feeling is None else feeling)

    @property
    def pieces_in_flight(self) -> int:
        """How many pieces of a line the engine may be making at once."""
        return int(getattr(self.tts, "pieces_in_flight", 1) or 1)

    @property
    def call_is_live(self) -> bool:
        """Whether sound she makes right now would be heard in a room."""
        return bool(self.call is not None and self.call.live)

    async def speak(self, mood: str, message: str, *, route: str = "local", feeling=None):
        """Renders a spoken turn. Returns the Utterance when route='call'."""
        line = self.open_line(mood, route=route, feeling=feeling, caption=message)
        if line is None:
            return None
        line.say(message)
        return await line.close()

    def open_line(self, mood: str, *, route: str = "local", feeling=None,
                  caption: Optional[str] = None) -> Optional[LiveLine]:
        """A line she can start saying before it has finished being written.

        `caption` is the whole line when the caller already has it: knowing it up
        front is what lets the words on screen be typed once instead of starting
        again at every sentence. Returns None when the route cannot be served —
        there is no call to speak into — so a caller can fall back rather than
        talk to nobody.
        """
        if route == "call" and self.call is None:
            return None
        line = LiveLine(self, mood, route=route, feeling=feeling)
        line.caption = caption
        return line

    async def _play_audio(self, audio_data, sample_rate, device_id):
        """Plays audio via sounddevice while tracking playback for barge-in."""
        # nothing to play needs no audio library: a failed synthesis hands back
        # an empty array, and on a headless box importing this raises
        if len(audio_data) == 0:
            return

        import sounddevice as sd

        self._safe_play(sd, audio_data, sample_rate, device_id)

        duration = len(audio_data) / sample_rate
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            sd.stop()
            raise

    def _safe_play(self, sd, audio_data, sample_rate, device_id):
        """Plays on the first device that actually accepts the audio.

        The configured id may not be an output at all (on CoreAudio the mic and the
        speakers of one headset are separate devices), or may be an output that
        portaudio still refuses to open — a bluetooth headset switched to headset
        mode raises -9986. So walk the candidates instead of trusting the config.
        """
        for candidate in self._output_candidates(sd, device_id):
            try:
                data = self._fit_channels(audio_data, self._device_channels(sd, candidate))
                sd.play(data, samplerate=sample_rate, device=candidate, blocking=False)
                if candidate != device_id:
                    logger.warning(
                        f"audio device {device_id} unusable; playing on "
                        f"{self._device_name(sd, candidate)} (id {candidate}) instead"
                    )
                self._playback_device_id = candidate
                return
            except Exception as e:
                logger.debug(f"audio device {candidate} failed ({e})")

        logger.error("no usable audio output device found; speech is silent")

    def _output_candidates(self, sd, device_id) -> list:
        """Configured device first, then the system default, then any real output."""
        candidates = []

        def add(index) -> None:
            if index is None or index in candidates:
                return
            if self._device_channels(sd, index) > 0:
                candidates.append(index)

        add(device_id)

        try:
            default = sd.default.device
            add(default[1] if isinstance(default, (list, tuple)) else default)
        except Exception:
            pass

        try:
            for index in range(len(sd.query_devices())):
                add(index)
        except Exception:
            pass

        # a cached working device beats the config order on later turns
        cached = self._playback_device_id
        if cached in candidates:
            candidates.remove(cached)
            candidates.insert(0, cached)

        return candidates

    @staticmethod
    def _device_name(sd, device_id) -> str:
        try:
            return sd.query_devices(device_id).get("name", str(device_id))
        except Exception:
            return str(device_id)

    @staticmethod
    def _device_channels(sd, device_id) -> int:
        """Output channels of a device, or 0 when it cannot play anything."""
        try:
            info = sd.query_devices(device_id)
            return max(0, int(info.get("max_output_channels", 0)))
        except Exception:
            return 0

    @staticmethod
    def _fit_channels(audio_data, channels: int):
        """Reshapes mono/stereo audio to at most `channels` columns."""

        if getattr(audio_data, "ndim", 1) == 1:
            return audio_data
        cols = audio_data.shape[1]
        if cols <= channels:
            return audio_data
        if channels == 1:
            return audio_data.mean(axis=1)
        return audio_data[:, :channels]

    # --- the sink one live line drives --------------------------------------
    #
    # `LiveLine` owns the order things happen in; everything below is what one
    # beat actually does. Split that way so the ordering can be tested without
    # a sound card and the rendering without a queue.

    def playback_lock(self, line: LiveLine):
        """Only one line at a time may hold the local sound card."""
        return self.audio_lock if line.route != "call" else contextlib.nullcontext()

    def line_opened(self, line: LiveLine) -> None:
        """She has started saying something: dress the stage for it."""
        self._line = line
        self._mood = line.mood
        preview = (line.caption or "")[:50]

        if line.route == "call":
            line.state = {"id": uuid.uuid4().hex, "seq": 0, "spoken_ms": 0, "frames": []}
            self.event_manager.publish(
                EventCategory.OUTPUT, "tts", f"Speaking in the call: {preview}...",
                metadata={"utterance_id": line.state["id"]},
            )
            return

        self.is_speaking = True
        logger.info(f"Mood: {line.mood}")

        if self.current_typing_task and not self.current_typing_task.done():
            logger.info("Interrupting previous typing task...")
            self.current_typing_task.cancel()
        if self.current_speech_task and not self.current_speech_task.done():
            logger.info("Interrupting previous speech task...")
            self.current_speech_task.cancel()

        self.caption.clear()
        self.avatar.show(line.mood, "talking")
        self.event_manager.publish(
            EventCategory.OUTPUT, "tts", f"Speaking: {preview}...",
            metadata={"device_id": self.config.audio_device_id},
        )
        if line.caption:
            self.current_typing_task = asyncio.create_task(self.caption.say(line.caption))

    async def render(self, line: LiveLine, text: str, prosody,
                     into: Optional[Rendered] = None) -> Optional[List[Tuple[Any, int]]]:
        """What the engine makes of one piece, or None to abandon the line.

        Abandoning is not an error: it is the room having moved on while the
        rest of the line was still being made, and every piece not rendered
        after that is one nobody was going to hear anyway.

        `into` receives each part as the engine hands it over, so the call can
        start hearing a piece an engine streams before the end of it exists.
        """
        if line.route != "call":
            logger.info(f"Message: {text}")
            return [await self.tts.generate_audio(text, prosody)]

        state = line.state
        if self._call_moved_on(state["id"], state["seq"]):
            return None

        parts: List[Tuple[Any, int]] = into.parts if into is not None else []
        async for audio, rate in self.tts.generate_stream(text, prosody):
            # against what has actually been pushed, never against what is only
            # rendered: nothing is playing yet while the first piece is made
            if self._call_moved_on(state["id"], state["seq"]):
                return None
            if into is not None:
                into.add((audio, rate))
            else:
                parts.append((audio, rate))
        return parts

    def plays_as_made(self, line: LiveLine) -> bool:
        """Whether a piece can be heard while it is still being made.

        In a call playing is a push, so a part goes out the moment it exists.
        On the local device a piece is timed, lip-synced and captioned whole.
        """
        return line.route == "call"

    async def play(self, line: LiveLine, item: Rendered) -> None:
        """One rendered piece, out loud, now."""
        if line.route == "call":
            await self._push(line, item)
            return

        if line.caption is None:
            # a line still being written has no whole caption to type, so the
            # words follow the voice one sentence at a time
            if self.current_typing_task and not self.current_typing_task.done():
                self.current_typing_task.cancel()
            self.current_typing_task = asyncio.create_task(self.caption.say(item.beat.value))

        for audio, rate in item.parts:
            # the mouth is told before playback starts, so the page has the whole
            # shape of the piece and can run it off its own clock
            self._move_mouth(audio, rate)
            self.current_speech_task = asyncio.create_task(
                self._play_audio(audio, rate, self.config.audio_device_id)
            )
            await self.current_speech_task

    async def _push(self, line: LiveLine, item: Rendered) -> None:
        """One rendered piece into the live call, part by part as it is made."""
        # taken once rather than read per piece: she can be pulled out of the
        # call between two sentences, and half a line should not raise
        call = self.call
        if call is None:
            return
        state = line.state
        # one conversion across the whole piece, so its parts meet exactly
        # where they would have in one piece
        resampler = CallResampler()
        sent = 0
        while True:
            while sent < len(item.parts):
                audio, rate = item.parts[sent]
                sent += 1
                last = sent == len(item.parts) and (item.job is None or item.job.done())
                await self._send(call, line, resampler.push(audio, rate, last=last))
            # a piece still being made: wait for more of it, or for its end
            job = item.job
            if job is None or job.done():
                if sent >= len(item.parts):
                    break
                continue
            item.grew.clear()
            if sent < len(item.parts) or job.done():
                continue
            await item.grew.wait()
        await self._send(call, line, resampler.flush())
        # the mouth over the whole piece, the way a piece made in one go gets it:
        # a part is normalised against its own loudest moment and loses the
        # last fraction of a frame, and the mouth drifts ahead of the voice
        pieces = [audio for audio, _ in item.parts if getattr(audio, "size", 0)]
        if pieces:
            whole = pieces[0] if len(pieces) == 1 else np.concatenate(pieces)
            state["frames"].extend(envelope(whole, item.parts[0][1], self._lipsync_fps))

    async def _send(self, call, line: LiveLine, pcm: bytes) -> None:
        if not pcm:
            return
        state = line.state
        await call.play(pcm, utterance_id=state["id"], text=line.caption or line.written,
                        seq=state["seq"], last=False)
        state["spoken_ms"] += duration_ms(pcm)
        state["seq"] += 1

    def wear(self, line: LiveLine, word: str) -> None:
        """Direction inside the line: her face changes from this word on."""
        mood = self.match_mood(word)
        line.mood = mood
        self._mood = mood
        self.avatar.show(mood, "talking")

    def behave(self, line: LiveLine, word: str) -> None:
        """Direction inside the line: she does something while she says it."""
        clip = self.match_clip(word)
        if clip:
            self.avatar.perform(clip)

    async def line_closed(self, line: LiveLine):
        """The line is over. Returns the Utterance when it went to a call."""
        # a line that was interrupted is closed after the one that replaced it
        # has already started: it must not put that one's face away
        mine = self._line is line
        if mine:
            self._line = None

        if line.route == "call":
            state = line.state
            if line.abandoned or self.call is None:
                return self.call.utterances.get(state["id"]) if self.call else None
            await self.call.end(state["id"])
            task = asyncio.create_task(self._visual_only(
                line.mood, line.caption or line.spoken,
                state["spoken_ms"] / 1000.0, state["frames"],
            ))
            self._visual_tasks.add(task)
            task.add_done_callback(self._visual_tasks.discard)
            return self.call.utterances.get(state["id"])

        if self.current_typing_task and not self.current_typing_task.done():
            try:
                await self.current_typing_task
            except asyncio.CancelledError:
                logger.info("Output tasks cancelled (Interruption).")

        if mine:
            self.caption.clear()
            self.avatar.show(self._mood, self._resting)
            self.is_speaking = False
        return None

    async def line_cancelled(self, line: LiveLine) -> None:
        """A call line dropped halfway still has to be ended in the room.

        Without its last frame the bot holds the utterance open, waiting for
        more of a line that is never coming.
        """
        call = self.call
        if line.route != "call" or call is None or not line.state.get("seq"):
            return
        current = call.current
        # already over, or another line has the call now: leave it alone
        if current is None or current.id != line.state["id"]:
            return
        await call.end(line.state["id"])

    def _call_moved_on(self, utterance_id: str, seq: int) -> bool:
        """Whether it is still worth synthesising the rest of this line.

        Barge-in lands while the later sentences are still being generated:
        without this she keeps paying for words the room already stopped hearing.
        """
        call = self.call
        if call is None or not call.live:
            return True
        if seq == 0:
            return False
        current = call.current
        return current is None or current.id != utterance_id

    @property
    def _lipsync_fps(self) -> int:
        return int((getattr(self.config, "stage", None) or {}).get("lipsync_fps", ENVELOPE_FPS))

    def _move_mouth(self, audio_data, sample_rate: int) -> None:
        """Hands the avatar the loudness of the line she is about to say."""
        fps = self._lipsync_fps
        try:
            self.avatar.mouth(envelope(audio_data, sample_rate, fps), fps)
        except Exception as e:
            # a mouth that fails must never stop her from speaking
            logger.error(f"Lip sync failed: {e}")

    async def _visual_only(self, mood: str, message: str, duration: float,
                           frames=None):
        """Drives the visuals for a line the room hears, without playing it here."""
        self.is_speaking = True
        self._mood = mood
        try:
            self.avatar.show(mood, "talking")
            if frames:
                self.avatar.mouth(frames, self._lipsync_fps)

            # held where barge-in can reach it: the caption for a line the room
            # hears is typed here, and an interruption has to stop it mid-word
            self.current_typing_task = asyncio.create_task(self.caption.say(message))
            # a caption backend that shows nothing returns at once, and the
            # visuals would snap back before the room finished hearing her
            await asyncio.gather(self.current_typing_task, asyncio.sleep(duration))

            self.avatar.show(mood, self._resting)
            self.caption.clear()
        finally:
            self.is_speaking = False

    # --- barge-in -----------------------------------------------------------

    async def interrupt(self, ramp_ms: int = 200) -> str:
        """Stops current speech/typing, in the call and on the local device alike.

        The call answers with how far it actually got — that answer is what stops
        her believing she said a whole sentence the room only half heard.
        """
        logger.info("Interruption Signal Received!")

        # stop making the rest of the line before stopping the sound: whatever
        # is still being synthesised is already words nobody will hear
        line, self._line = self._line, None
        if line is not None:
            await line.cancel()

        call = self.call
        if call is not None and call.live:
            self.interrupted = await call.stop(ramp_ms=ramp_ms)

        try:
            import sounddevice as sd
            sd.stop()
        except Exception as e:
            logger.debug(f"Error stopping sounddevice: {e}")

        if self.current_speech_task and not self.current_speech_task.done():
            self.current_speech_task.cancel()
        if self.current_typing_task and not self.current_typing_task.done():
            self.current_typing_task.cancel()

        self.caption.clear()
        self.avatar.show(self._mood, self._resting)

        self.is_speaking = False
        return "Interrupted"

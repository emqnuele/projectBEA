import asyncio
import time
import uuid
from typing import Optional

from src.core.config import BrainConfig
from src.core.events import EventCategory, EventManager
from src.core.expression.chunking import split_for_speech
from src.core.expression.pcm import duration_ms, to_call_pcm
from src.core.expression.prosody import for_mood
from src.core.mind.moods import DEFAULT_MOOD
from src.interfaces.base_interfaces import AvatarInterface, CaptionInterface, TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.expression")


class Expression:
    """The single output sink for everything Bea expresses.

    Owns the VOICE actuator: TTS generation, local audio playback, the avatar and
    the caption, barge-in/interruption and the resume buffer. Every surface that
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

        # the last mood she was seen in, so a state change (falling asleep, a
        # resumed sentence) does not silently reset her face to neutral
        self._mood = DEFAULT_MOOD

        self._is_speaking = False
        self.current_typing_task: Optional[asyncio.Task] = None
        self.current_speech_task: Optional[asyncio.Task] = None
        self.audio_lock = asyncio.Lock()

        self.current_audio_buffer = None
        self.playback_start_time = 0.0
        self.playback_sample_rate = 24000
        self.resume_buffer = None
        self._playback_device_id = None

        # the live call, when there is one; the voice skill hands it over
        self.call = None
        # how she has been feeling; the brain hands it over, None means neutral
        self.affect = None
        # the last utterance a barge-in cut short, for the mind to be told about
        self.interrupted = None

    def set_state(self, state: str, mood: Optional[str] = None) -> None:
        """A visible state that is not speech: sleeping, listening, idle.

        A state is not a mood. Passing `"sleeping"` where a mood belonged is
        exactly why the sleeping avatar was never once seen: it resolved to
        `normal` without a word of complaint.
        """
        if mood is not None:
            self._mood = mood
        self.avatar.show(self._mood, state)

    def set_ports(self, avatar: AvatarInterface, caption: CaptionInterface) -> None:
        """Swaps the backends under her, mid-run, without dropping the mood."""
        self.avatar = avatar
        self.caption = caption
        self.avatar.show(self._mood, "idle")

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
        call = getattr(self, "call", None)
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

    def _prosody(self, mood: str, feeling=None):
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
    def call_is_live(self) -> bool:
        """Whether sound she makes right now would be heard in a room."""
        return bool(self.call is not None and self.call.live)

    async def speak(self, mood: str, message: str, *, route: str = "local", feeling=None):
        """Renders a spoken turn. Returns the Utterance when route='call'."""
        if route == "call":
            return await self._speak_call(mood, message, feeling)
        await self._speak_local(mood, message, feeling)
        return None

    async def _play_audio(self, audio_data, sample_rate, device_id):
        """Plays audio via sounddevice while tracking playback for barge-in."""
        # nothing to play needs no audio library: a failed synthesis hands back
        # an empty array, and on a headless box importing this raises
        if len(audio_data) == 0:
            return

        import sounddevice as sd

        self.current_audio_buffer = audio_data
        self.playback_sample_rate = sample_rate
        self.playback_start_time = time.time()

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
        cached = getattr(self, "_playback_device_id", None)
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

    async def _speak_local(self, mood: str, message: str, feeling=None):
        """Audio + visual output on the local device (stream/OBS)."""
        self.is_speaking = True
        self._mood = mood
        try:
            logger.info(f"Mood: {mood}")
            logger.info(f"Message: {message}")

            if self.current_typing_task and not self.current_typing_task.done():
                logger.info("Interrupting previous typing task...")
                self.current_typing_task.cancel()

            if self.current_speech_task and not self.current_speech_task.done():
                logger.info("Interrupting previous speech task...")
                self.current_speech_task.cancel()

            self.caption.clear()
            self.avatar.show(mood, "talking")

            async with self.audio_lock:
                self.current_typing_task = asyncio.create_task(self.caption.say(message))

                self.event_manager.publish(
                    EventCategory.OUTPUT, "tts", f"Speaking: {message[:50]}...",
                    metadata={"device_id": self.config.audio_device_id},
                )

                if message:
                    audio_data, fs = await self.tts.generate_audio(
                        message, self._prosody(mood, feeling))
                    self.current_speech_task = asyncio.create_task(
                        self._play_audio(audio_data, fs, self.config.audio_device_id)
                    )

                    try:
                        await asyncio.gather(self.current_typing_task, self.current_speech_task)
                    except asyncio.CancelledError:
                        logger.info("Output tasks cancelled (Interruption).")

            self.caption.clear()
            self.avatar.show(mood, "idle")
        finally:
            self.is_speaking = False

    async def _speak_call(self, mood: str, message: str, feeling=None):
        """Synthesises piece by piece and pushes each one as it is ready.

        The room hears the first sentence while the second is still being
        generated, so the time to first sound stops depending on how much she
        had to say. The seams sit on sentence boundaries, where a person would
        breathe anyway.
        """
        if self.call is None:
            return None

        utterance_id = uuid.uuid4().hex
        self.event_manager.publish(
            EventCategory.OUTPUT, "tts", f"Speaking in the call: {message[:50]}...",
            metadata={"utterance_id": utterance_id},
        )

        seq = 0
        spoken_ms = 0
        # read once per turn: the second half of a sentence must not drift into
        # a different mood from the first
        prosody = self._prosody(mood, feeling)
        for sentence in split_for_speech(message):
            async for audio_data, sample_rate in self.tts.generate_stream(sentence, prosody):
                if self._call_moved_on(utterance_id, seq):
                    return self.call.utterances.get(utterance_id)
                pcm = to_call_pcm(audio_data, sample_rate)
                if not pcm:
                    continue
                await self.call.play(pcm, utterance_id=utterance_id, text=message,
                                     seq=seq, last=False)
                spoken_ms += duration_ms(pcm)
                seq += 1

        await self.call.end(utterance_id)
        asyncio.create_task(self._visual_only(mood, message, spoken_ms / 1000.0))
        return self.call.utterances.get(utterance_id)

    def _call_moved_on(self, utterance_id: str, seq: int) -> bool:
        """Whether it is still worth synthesising the rest of this line.

        Barge-in lands while the later sentences are still being generated:
        without this she keeps paying for words the room already stopped hearing.
        """
        if seq == 0:
            return not self.call_is_live
        current = self.call.current
        return not self.call_is_live or current is None or current.id != utterance_id

    async def _visual_only(self, mood: str, message: str, duration: float):
        """Drives the visuals for a line the room hears, without playing it here."""
        self.is_speaking = True
        self._mood = mood
        try:
            self.avatar.show(mood, "talking")

            typed = asyncio.create_task(self.caption.say(message))
            # a caption backend that shows nothing returns at once, and the
            # visuals would snap back before the room finished hearing her
            await asyncio.gather(typed, asyncio.sleep(duration))

            self.avatar.show(mood, "idle")
            self.caption.clear()
        finally:
            self.is_speaking = False

    # --- barge-in / resume --------------------------------------------------

    async def interrupt(self, ramp_ms: int = 200) -> str:
        """Stops current speech/typing, in the call and on the local device alike.

        The call answers with how far it actually got — that answer is what stops
        her believing she said a whole sentence the room only half heard.
        """
        logger.info("Interruption Signal Received!")

        if self.call_is_live:
            self.interrupted = await self.call.stop(ramp_ms=ramp_ms)

        if self.is_speaking and self.current_audio_buffer is not None:
            try:
                elapsed = time.time() - self.playback_start_time
                consumed_samples = int(elapsed * self.playback_sample_rate)
                total_samples = len(self.current_audio_buffer)

                if consumed_samples < total_samples:
                    remaining = self.current_audio_buffer[consumed_samples:]
                    if len(remaining) > (0.5 * self.playback_sample_rate):
                        self.resume_buffer = remaining
                        logger.info(f"Buffered {len(remaining)/self.playback_sample_rate:.2f}s for resume.")
                    else:
                        self.resume_buffer = None
                else:
                    self.resume_buffer = None
            except Exception as e:
                logger.error(f"Error calculating resume buffer: {e}")
                self.resume_buffer = None

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
        self.avatar.show(self._mood, "idle")

        self.is_speaking = False
        return "Interrupted"

    async def resume(self):
        """Resumes speech from the buffered tail, if any."""
        if self.resume_buffer is None:
            logger.info("No resume buffer found.")
            return

        logger.info("Resuming speech...")
        self.is_speaking = True
        try:
            async with self.audio_lock:
                # the mood she was cut off in, not `normal`: finishing an angry
                # sentence with a neutral face is worse than not finishing it
                self.avatar.show(self._mood, "talking")

                self.current_speech_task = asyncio.create_task(
                    self._play_audio(self.resume_buffer, self.playback_sample_rate, self.config.audio_device_id)
                )
                try:
                    await self.current_speech_task
                except asyncio.CancelledError:
                    pass

                self.resume_buffer = None
        finally:
            self.is_speaking = False
            self.avatar.show(self._mood, "idle")

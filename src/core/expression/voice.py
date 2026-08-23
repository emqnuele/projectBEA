import asyncio
import io
import time
from pathlib import Path
from typing import Optional, Tuple

from src.core.config import BrainConfig
from src.core.events import EventCategory, EventManager
from src.core.resources import resolve_mood_paths
from src.interfaces.base_interfaces import OBSInterface, TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.expression")


class Expression:
    """The single output sink for everything Bea expresses.

    Owns the VOICE actuator: TTS generation, local audio playback, OBS avatar/text
    animation, barge-in/interruption and the resume buffer. Every surface that used
    to roll its own speech path (chat, discord voice, minecraft thoughts, monologue)
    routes through here so the rendering logic lives in exactly one place.

    Routes:
    - "local"   -> generate audio and play it on the configured device (stream/OBS).
    - "remote"  -> generate audio, drive only the OBS visuals, and return the WAV
                   bytes to the caller (Discord voice playback happens in the bot).
    """

    def __init__(self, config: BrainConfig, tts: TTSInterface, obs: OBSInterface, event_manager: EventManager):
        self.config = config
        self.tts = tts
        self.obs = obs
        self.event_manager = event_manager

        self.png_map = {}

        self.is_speaking = False
        self.current_typing_task: Optional[asyncio.Task] = None
        self.current_speech_task: Optional[asyncio.Task] = None
        self.audio_lock = asyncio.Lock()

        self.current_audio_buffer = None
        self.playback_start_time = 0.0
        self.playback_sample_rate = 24000
        self.resume_buffer = None

    def set_png_map(self, png_map) -> None:
        self.png_map = png_map

    def set_mood_avatar(self, mood: str) -> None:
        """Set a static (idle) avatar for a mood without speaking — e.g. sleeping."""
        self._set_idle(mood)

    def reload_config(self, config: BrainConfig) -> None:
        self.config = config

    # --- VOICE actuator -----------------------------------------------------

    async def speak(self, mood: str, message: str, *, route: str = "local") -> Optional[bytes]:
        """Renders a spoken turn. Returns WAV bytes when route='remote'."""
        if route == "remote":
            return await self._speak_remote(mood, message)
        await self._speak_local(mood, message)
        return None

    async def _play_audio(self, audio_data, sample_rate, device_id):
        """Plays audio via sounddevice while tracking playback for barge-in."""
        import sounddevice as sd

        if len(audio_data) == 0:
            return

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
        """Plays on the configured device, falling back to the default on failure.

        Device 0 (or a misconfigured id) may not support the channel count of the
        rendered audio, raising PaErrorCode -9998. Downmix to what the device can
        take, and if it still fails drop to the system default device.
        """
        try:
            channels = self._device_channels(sd, device_id)
            data = self._fit_channels(audio_data, channels)
            sd.play(data, samplerate=sample_rate, device=device_id, blocking=False)
        except Exception as e:
            logger.warning(f"Audio device {device_id} failed ({e}); using default device.")
            try:
                sd.play(audio_data, samplerate=sample_rate, blocking=False)
            except Exception as e2:
                logger.error(f"Default audio device also failed: {e2}")

    @staticmethod
    def _device_channels(sd, device_id) -> int:
        try:
            info = sd.query_devices(device_id, "output")
            return max(1, int(info.get("max_output_channels", 1)))
        except Exception:
            return 1

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

    async def _speak_local(self, mood: str, message: str):
        """Audio + visual output on the local device (stream/OBS)."""
        self.is_speaking = True
        font_used = self.config.text_font_size
        try:
            logger.info(f"Mood: {mood}")
            logger.info(f"Message: {message}")

            if self.current_typing_task and not self.current_typing_task.done():
                logger.info("Interrupting previous typing task...")
                self.current_typing_task.cancel()

            if self.current_speech_task and not self.current_speech_task.done():
                logger.info("Interrupting previous speech task...")
                self.current_speech_task.cancel()

            if self.config.obs_text_source:
                self.obs.set_text("", self.config.obs_text_source)

            idle_path, talking_path = self._resolve_paths(mood)

            if self.config.obs_source_type == "media":
                self.obs.set_media(talking_path)
            else:
                self.obs.set_image(talking_path)

            async with self.audio_lock:
                self.current_typing_task = None
                if self.config.obs_text_source:
                    self.current_typing_task = asyncio.create_task(self._type(message))

                self.event_manager.publish(
                    EventCategory.OUTPUT, "tts", f"Speaking: {message[:50]}...",
                    metadata={"device_id": self.config.audio_device_id},
                )

                if message:
                    audio_data, fs = await self.tts.generate_audio(message)
                    self.current_speech_task = asyncio.create_task(
                        self._play_audio(audio_data, fs, self.config.audio_device_id)
                    )

                    font_used = self.config.text_font_size
                    try:
                        if self.current_typing_task:
                            results = await asyncio.gather(self.current_typing_task, self.current_speech_task)
                            font_used = results[0]
                        else:
                            await self.current_speech_task
                    except asyncio.CancelledError:
                        logger.info("Output tasks cancelled (Interruption).")

            if self.config.obs_text_source:
                self.obs.set_text("", self.config.obs_text_source, font_size=font_used)

            self._set_idle(mood)
        finally:
            self.is_speaking = False

    async def _speak_remote(self, mood: str, message: str) -> bytes:
        """Generates WAV bytes (for the Discord bot) and drives OBS visuals only."""
        import soundfile as sf

        audio_data, sample_rate = await self.tts.generate_audio(message)

        byte_io = io.BytesIO()
        sf.write(byte_io, audio_data, sample_rate, format="WAV")
        audio_bytes = byte_io.getvalue()

        duration = len(audio_data) / sample_rate if sample_rate else 0
        asyncio.create_task(self._visual_only(mood, message, duration))
        return audio_bytes

    async def _visual_only(self, mood: str, message: str, duration: float):
        """Updates OBS visuals/text without playing local audio."""
        self.is_speaking = True
        try:
            _, talking_path = self._resolve_paths(mood)
            if self.config.obs_source_type == "media":
                self.obs.set_media(talking_path)
            else:
                self.obs.set_image(talking_path)

            if self.config.obs_text_source:
                await self._type(message)
            else:
                await asyncio.sleep(duration)

            self._set_idle(mood)
            if self.config.obs_text_source:
                self.obs.set_text("", self.config.obs_text_source)
        finally:
            self.is_speaking = False

    async def _type(self, message: str) -> int:
        return await self.obs.type_text(
            text=message,
            source_name=self.config.obs_text_source,
            line_width=self.config.text_line_width,
            max_lines=self.config.text_lines,
            base_font_size=self.config.text_font_size,
            min_font_size=self.config.text_min_font_size,
            font_step=self.config.text_font_step,
            typing_delay=self.config.typing_delay,
            min_page_duration=self.config.text_min_duration,
        )

    def _resolve_paths(self, mood: str) -> Tuple[Path, Path]:
        try:
            return resolve_mood_paths(self.png_map, mood)
        except KeyError:
            logger.warning(f"Could not resolve mood {mood}, falling back to 'normal'.")
            if "normal" in self.png_map:
                return self.png_map["normal"]
            return Path("placeholder.png"), Path("placeholder.png")

    def _set_idle(self, mood: str):
        try:
            idle_path, _ = self._resolve_paths(mood)
        except Exception:
            idle_path = self.png_map.get("normal", (Path("placeholder.png"),))[0]
        if self.config.obs_source_type == "media":
            self.obs.set_media(idle_path)
        else:
            self.obs.set_image(idle_path)

    # --- barge-in / resume --------------------------------------------------

    async def interrupt(self) -> str:
        """Stops current speech/typing immediately, buffering the tail for resume."""
        logger.info("Interruption Signal Received!")
        import sounddevice as sd

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
            sd.stop()
        except Exception as e:
            logger.error(f"Error stopping sounddevice: {e}")

        if self.current_speech_task and not self.current_speech_task.done():
            self.current_speech_task.cancel()
        if self.current_typing_task and not self.current_typing_task.done():
            self.current_typing_task.cancel()

        if self.config.obs_text_source:
            self.obs.set_text("", self.config.obs_text_source)

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
                if "normal" in self.png_map:
                    _, talking_path = self.png_map["normal"]
                    if self.config.obs_source_type == "media":
                        self.obs.set_media(talking_path)
                    else:
                        self.obs.set_image(talking_path)

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
            if "normal" in self.png_map:
                idle_path, _ = self.png_map["normal"]
                if self.config.obs_source_type == "media":
                    self.obs.set_media(idle_path)
                else:
                    self.obs.set_image(idle_path)

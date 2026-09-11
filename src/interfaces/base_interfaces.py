from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional, Sequence, Tuple, Union


class LLMInterface(ABC):

    @abstractmethod
    def chat(self, user_input: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Tuple[str, str, Dict]:
        """
        Sends user input to the LLM and returns (mood, message, metadata).
        history: List of dictionaries [{"role": "user"|"assistant", "content": "..."}]
        """
        pass

    @abstractmethod
    def chat_audio(self, audio_path: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Tuple[str, str, Dict]:
        """
        Sends audio input to the LLM and returns (mood, message, metadata).
        """
    @abstractmethod
    def reload_config(self, config) -> None:
        """
        Reloads configuration (e.g. API keys, models) without restarting.
        """
        pass

    @abstractmethod
    def generate_json(self, user_input: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Union[Dict, list]:
        """
        Generates a JSON response from the LLM.
        Returns a dictionary parsed from the JSON output.
        """
        pass

class TTSInterface(ABC):
    @abstractmethod
    async def speak(self, text: str, output_device_id: int) -> None:
        """
        Generates audio from text and plays it to the specified device.
        """
        pass

    @abstractmethod
    async def generate_audio(self, text: str, prosody=None) -> Tuple[Any, int]:
        """
        Generates audio from text.
        Returns (audio_data, sample_rate).
        audio_data: numpy array or valid sounddevice input.
        `prosody` is a deviation from the configured voice; None is no change,
        and an engine with no knobs for it may ignore it.
        """
        pass

    async def generate_stream(self, text: str, prosody=None) -> AsyncIterator[Tuple[Any, int]]:
        """Yields (audio_data, sample_rate) as it becomes available.

        Deliberately not abstract. The default is one chunk — the whole thing,
        exactly as `generate_audio` produced it — so every existing engine keeps
        working untouched, and an engine whose source is already chunked (a
        streaming HTTP response) overrides this and starts sounding sooner.
        """
        yield await self.generate_audio(text, prosody)

    @abstractmethod
    def reload_config(self, config) -> None:
        """
        Reloads configuration (e.g. voice, API keys) without restarting.
        """
        pass

class OBSInterface(ABC):
    # which OBS source her body is drawn into. The brain sets it from config
    # before connecting, so renaming the source in the UI takes effect without
    # a restart — which is why it is an attribute and not a constructor argument.
    source_name: str = ""

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def reload_config(self, config) -> None:
        """
        Reloads configuration (e.g. host, port) without restarting.
        """
        pass

    @abstractmethod
    def set_image(self, image_path: Union[str, Path]) -> None:
        """
        Updates the image source in OBS.
        """
        pass

    @abstractmethod
    def set_media(self, media_path: Union[str, Path]) -> None:
        """
        Updates the media source in OBS.
        """
        pass

    @abstractmethod
    async def type_text(self, text: str, source_name: str, **kwargs) -> int:
        """
        Types text into the OBS text source with animation.
        Returns the final font size used.
        """
        pass

    @abstractmethod
    def set_text(self, text: str, source_name: str, font_size: Optional[int] = None) -> None:
        """
        Sets text immediately without animation.
        """
        pass

# what a mouth is told, per frame: how open it is and what shape it is in
MouthFrames = Sequence[Sequence[float]]


class AvatarInterface(ABC):
    """How Bea looks. Knows nothing about files, OBS or three.js.

    The engine hands down what she *is* — a mood and a state — and each backend
    decides what that means: a PNG swap, a blend of VRM expressions, a VTube
    Studio hotkey. Every method is synchronous, so a backend that needs the
    network queues the work instead of holding up the turn she is speaking in.
    """

    @abstractmethod
    def show(self, mood: str, state: str) -> None:
        """Her mood, and what she is doing: idle, talking, listening, sleeping."""
        pass

    @abstractmethod
    def perform(self, clip: str) -> None:
        """Play a named behaviour. A backend without behaviours ignores it."""
        pass

    @abstractmethod
    def mouth(self, envelope: MouthFrames, fps: int) -> None:
        """What her mouth does over the line about to be heard.

        One `[how open, what shape]` pair per frame, both in [0, 1]: how open
        comes from loudness, what shape from where the sound sits between a
        dark vowel and a bright one. A backend with one mouth parameter uses
        the first and ignores the second.

        Deliberately the whole utterance at once rather than a value per frame:
        a page can replay it against its own clock, and a backend that needs a
        stream (VTube Studio wants one message per frame) can pace it itself.
        A backend with no mouth ignores it entirely.
        """
        pass

    @abstractmethod
    def reload_config(self, config) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        """Release whatever the backend holds.

        Abstract rather than a no-op default: a backend that opens a socket and
        forgets to close it leaks a task for the life of the process, and every
        backend saying out loud whether it holds anything is cheaper than
        finding that out on a stream.
        """
        pass


class CaptionInterface(ABC):
    """The words on screen while she talks, if the setup shows them at all."""

    @abstractmethod
    async def say(self, text: str) -> None:
        """Put a line on screen, with whatever animation the backend has.

        Awaitable because the OBS backend animates over time and barge-in
        cancels the task mid-sentence.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Take the words away. Safe to call when there are none."""
        pass

    @abstractmethod
    def reload_config(self, config) -> None:
        pass


class STTInterface(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str, language: str = "en") -> str:
        """
        Transcribes audio file to text.
        audio_path: Absolute path to the audio file.
        language: Language code (default: "en").
        Returns the transcribed text.
        """
        pass

    @abstractmethod
    def reload_config(self, config) -> None:
        """
        Reloads configuration (e.g. API key, model) without restarting.
        """
        pass

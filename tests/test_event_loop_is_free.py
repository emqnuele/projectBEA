"""Nothing slow is allowed to run on the event loop.

Transcribing is hundreds of milliseconds. On the loop, that is hundreds of
milliseconds in which nothing else she is doing can make progress: the audio
already playing is not topped up, a barge-in is not noticed, the dashboard
stops being answered. From the outside it reads as a stutter, not as a stall,
which is why it survived three correct call sites and one wrong one.

The assertion is not "it was written with to_thread" — that is the fix, not the
property. It is that the loop kept turning while the work happened.
"""

import asyncio
import threading

from src.core.brain import AIVtuberBrain
from src.core.mind.moods import DEFAULT_MOOD

# long enough that a blocked loop cannot hide inside scheduling noise
WORK_SECONDS = 0.2


class SlowSTT:
    def __init__(self):
        self.thread = None

    def transcribe(self, path):
        self.thread = threading.current_thread()
        # a real transcription, in miniature: cpu-bound work the loop cannot await
        threading.Event().wait(WORK_SECONDS)
        return "ciao"


class Surface:
    def perceive_voice(self, text, meta=None):
        return None


class Brain:
    """Only what `generate_audio_response` actually reaches for."""

    generate_audio_response = AIVtuberBrain.generate_audio_response

    def __init__(self, stt):
        self.stt = stt
        self.consciousness = object()

    def _surface(self, name):
        return Surface()

    async def _perceive_and_wait(self, putter, route):
        return None


async def _ticks_during(coro) -> int:
    """How many times the loop came back round while `coro` ran."""
    counter = 0

    async def tick():
        nonlocal counter
        while True:
            await asyncio.sleep(0.005)
            counter += 1

    ticker = asyncio.create_task(tick())
    try:
        await coro
    finally:
        ticker.cancel()
        await asyncio.gather(ticker, return_exceptions=True)
    return counter


async def test_transcribing_does_not_stall_the_loop():
    brain = Brain(SlowSTT())
    ticks = await _ticks_during(brain.generate_audio_response("some.wav"))
    # a blocked loop scores zero; a free one gets ~40 in this window
    assert ticks > 5


async def test_transcribing_happens_off_the_main_thread():
    stt = SlowSTT()
    await Brain(stt).generate_audio_response("some.wav")
    assert stt.thread is not threading.main_thread()


async def test_the_transcript_still_comes_back():
    """Moving the work must not lose its result."""
    mood, message, transcript = await Brain(SlowSTT()).generate_audio_response("some.wav")
    assert transcript == "ciao"
    assert (mood, message) == (DEFAULT_MOOD, "")


async def test_no_transcriber_is_not_an_error():
    brain = Brain(None)
    _, _, transcript = await brain.generate_audio_response("some.wav")
    assert transcript == ""

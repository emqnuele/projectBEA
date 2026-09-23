"""Her voice through the real socket into the real bot, with no discord in it.

Everything else about the call is tested one side at a time. This is the one
place both halves run together: `/voice/ws` and `VoiceChannel` here, BrainLink,
VoiceManager and a real AudioPlayer in node. It exists for the failure no side
can see alone — a sentence late enough for the player to give up on the stream
used to end the utterance in the bot, the brain read that as the room having
moved on, and the rest of her line was dropped while she was recorded as having
said all of it.
"""

import asyncio
import contextlib
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.core.expression.voice import Expression
from src.core.skills.voice.channel import VoiceChannel
from src.interfaces.base_interfaces import TTSInterface
from tests.fakes import FakeAvatar, FakeCaption

BOT = Path(__file__).resolve().parents[1] / "src/core/skills/voice/bot"
# the player's gap, short so the test is: the stall below is longer than it
GAP_MS = 200
STALL = 1.5

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not (BOT / "node_modules/@discordjs/voice").exists(),
    reason="needs node and the discord bot's node_modules",
)


class Config:
    text_font_size = 40
    text_line_width = 30
    text_lines = 3
    text_min_font_size = 20
    text_font_step = 2
    typing_delay = 0.0
    text_min_duration = 0.0
    obs_text_source = ""
    obs_source_type = "image"
    audio_device_id = None


class Events:
    def publish(self, *a, **k):
        pass


class LateSecondSentence(TTSInterface):
    """Half a second of voice a piece; the second one is late."""

    def __init__(self):
        self.made = 0

    async def generate_audio(self, text, prosody=None):
        self.made += 1
        if self.made == 2:
            await asyncio.sleep(STALL)
        return (np.sin(np.arange(12000) / 7) * 0.2).astype(np.float32), 24000

    def reload_config(self, config):
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def serving(monkeypatch, tmp_path, script: str = "", brain=None):
    """A live call: the brain's socket served here, the bot's half in node.

    `script` is somebody in the call talking, as "talk ms, pause ms, ...", and
    `brain` answers the turns the bot sends while they do.
    """
    import uvicorn
    from fastapi import FastAPI

    from src.web.deps import get_brain
    from src.web.routers import voice as voice_router

    monkeypatch.chdir(tmp_path)
    channel = VoiceChannel()
    surface = SimpleNamespace(channel=channel, transport=SimpleNamespace(api_token="tok"))
    stub = brain(channel) if brain is not None else SimpleNamespace()
    stub.skill_registry = {"voice:discord": surface}
    monkeypatch.setattr(voice_router, "get_brain", lambda: stub)
    app = FastAPI()
    app.include_router(voice_router.router)
    app.dependency_overrides[get_brain] = lambda: stub
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    served = asyncio.create_task(server.serve())

    env = dict(os.environ, BRAIN_API_URL=f"http://127.0.0.1:{port}", API_TOKEN="tok",
               BEA_DATA_DIR=str(tmp_path))
    bot = subprocess.Popen(["node", "test/support/call.js", str(GAP_MS), script], cwd=BOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            if channel.live:
                break
            await asyncio.sleep(0.05)
        assert channel.live, "the bot never joined the call"
        yield channel, stub
    finally:
        bot.terminate()
        bot.wait(timeout=5)
        server.should_exit = True
        await served


@pytest.fixture
async def call(monkeypatch, tmp_path):
    async with serving(monkeypatch, tmp_path) as (channel, _):
        yield channel


async def test_a_sentence_later_than_the_player_waits_is_still_heard(call):
    e = Expression(Config(), LateSecondSentence(), FakeAvatar(), FakeCaption(), Events())
    e.set_call(call)
    line = e.open_line("neutral", route="call")
    line.say("Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga.")
    utterance = await asyncio.wait_for(line.close(), timeout=10)
    await asyncio.wait_for(utterance.done.wait(), timeout=10)

    assert not line.abandoned, "the rest of the line was dropped"
    assert line.spoken == "Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga."
    assert utterance.state == "done"
    assert utterance.sent_ms == 1000
    assert utterance.played_ms == 1000, "the count started over halfway"


class SlowAfterTheFirst(TTSInterface):
    """Two seconds of voice for the first piece; the rest never finish."""

    def __init__(self):
        self.made = 0

    async def generate_audio(self, text, prosody=None):
        self.made += 1
        if self.made > 1:
            await asyncio.Event().wait()
        return (np.sin(np.arange(48000) / 7) * 0.2).astype(np.float32), 24000

    def reload_config(self, config):
        pass


async def test_talked_over_while_the_turn_waits_on_the_line_she_is_cut_off(call):
    """The bot's /interrupt lands while the mind is still closing the line: she
    stops, and she knows how little of it the room heard."""
    avatar = FakeAvatar()
    e = Expression(Config(), SlowAfterTheFirst(), avatar, FakeCaption(), Events())
    e.set_call(call)
    line = e.open_line("neutral", route="call")
    e._line = line
    line.say("Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga. "
             "Terza frase, lunga come le altre due.")
    closing = asyncio.create_task(line.close())
    while call.current is None or call.current.state != "playing":
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.5)

    await e.interrupt()
    utterance = await asyncio.wait_for(closing, timeout=5)

    assert utterance is e.interrupted
    assert utterance.state == "stopped"
    assert not utterance.complete, "the stop found a line that had finished"
    assert utterance.played_ms < utterance.sent_ms
    assert call.current is None
    # the face stays put down: a cut line used to go on miming its whole length
    await asyncio.sleep(0.05)
    assert avatar.shown[-1][1] != "talking", "she went back to talking after being cut off"
    assert not e._visual_tasks


# --- somebody who pauses in the middle of a sentence --------------------------


# what a real turn takes between the transcript and her first sound, at its
# fastest: a model call and the first piece of speech. The hold can only catch
# somebody who starts again inside the hangover, the transcription and this;
# anybody later finds her already talking, and that is the barge-in's business.
THINKING = 1.0


class InstantVoice(TTSInterface):
    async def generate_audio(self, text, prosody=None):
        return (np.sin(np.arange(4800) / 7) * 0.2).astype(np.float32), 24000

    def reload_config(self, config):
        pass


class EagerBrain:
    """Transcribes every turn at once, and starts answering the first one."""

    def __init__(self, channel):
        self.channel = channel
        self.turns = []
        self.answering = None

    async def process_discord_interaction(self, path, username, user_id=None, **kw):
        self.turns.append(time.monotonic())
        self.channel.transcribed(user_id)
        if self.answering is None:
            self.answering = asyncio.get_running_loop().create_future()
            self.answering.set_result(len(self.turns))
        return "..."


async def test_a_pause_in_the_middle_of_a_sentence_does_not_get_answered(monkeypatch, tmp_path):
    """Half a sentence, a breath longer than the hangover, the rest. The bot
    splits it in two, as any detector would; her line waits for the second half
    instead of starting over the person still saying it."""
    heard = []
    async with serving(monkeypatch, tmp_path, script="700,900,700", brain=EagerBrain) as (call, brain):
        call.on_hearing = lambda user, state: heard.append((state, time.monotonic()))
        e = Expression(Config(), InstantVoice(), FakeAvatar(), FakeCaption(), Events())
        e.set_call(call)
        played = []
        play = call.play

        async def recording_play(pcm, **kw):
            played.append(time.monotonic())
            return await play(pcm, **kw)

        call.play = recording_play

        # the moment the first half is transcribed, she starts answering it
        for _ in range(200):
            if brain.answering is not None:
                break
            await asyncio.sleep(0.05)
        assert brain.answering is not None, "the first half never reached the brain"
        await asyncio.sleep(THINKING)
        await asyncio.wait_for(e.speak("neutral", "Ti rispondo subito.", route="call"), timeout=15)

    states = [state for state, _ in heard]
    assert states == ["start", "sent", "end", "start", "sent", "end"], states
    last_end = [at for state, at in heard if state == "end"][-1]
    assert len(brain.turns) == 2, "the sentence was not split, so this proves nothing"
    assert played and played[0] >= last_end, "she talked over the second half of the sentence"

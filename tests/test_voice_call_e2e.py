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
import os
import shutil
import socket
import subprocess
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


async def test_a_sentence_later_than_the_player_waits_is_still_heard(monkeypatch):
    import uvicorn
    from fastapi import FastAPI

    from src.web.routers import voice as voice_router

    channel = VoiceChannel()
    surface = SimpleNamespace(channel=channel, transport=SimpleNamespace(api_token="tok"))
    monkeypatch.setattr(voice_router, "get_brain",
                        lambda: SimpleNamespace(skill_registry={"voice:discord": surface}))
    app = FastAPI()
    app.include_router(voice_router.router)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    serving = asyncio.create_task(server.serve())

    env = dict(os.environ, BRAIN_API_URL=f"http://127.0.0.1:{port}", API_TOKEN="tok")
    bot = subprocess.Popen(["node", "test/support/call.js", str(GAP_MS)], cwd=BOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            if channel.live:
                break
            await asyncio.sleep(0.05)
        assert channel.live, "the bot never joined the call"

        e = Expression(Config(), LateSecondSentence(), FakeAvatar(), FakeCaption(), Events())
        e.set_call(channel)
        line = e.open_line("neutral", route="call")
        line.say("Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga.")
        utterance = await asyncio.wait_for(line.close(), timeout=10)
        await asyncio.wait_for(utterance.done.wait(), timeout=10)

        assert not line.abandoned, "the rest of the line was dropped"
        assert line.spoken == "Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga."
        assert utterance.state == "done"
        assert utterance.sent_ms == 1000
        assert utterance.played_ms == 1000, "the count started over halfway"
    finally:
        bot.terminate()
        bot.wait(timeout=5)
        server.should_exit = True
        await serving

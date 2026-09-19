"""Stopping her: what ctrl+c is allowed to interrupt, and what it is not.

The steps of a shutdown are not optional. ctrl+c cancels the task running
`main`, the cancellation lands on the first `await` of the shutdown, and
`except Exception` never caught it — so the save ate the interrupt and
everything after it was skipped. The discord bot outlived the brain, kept the
port it was listening on, and the next start died on that port instead.
"""

import asyncio
import socket

import pytest

from src import cli
from src.core.skills.voice.transport import LOOPBACK, DiscordTransport


class Memory:
    """The memory skill, whose save is the slow step ctrl+c arrives during."""

    def __init__(self, enabled=True, delay=0.0, error=None):
        self.enabled = enabled
        self.delay = delay
        self.error = error
        self.saved = False

    async def save_all_pending(self):
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        self.saved = True


class Brain:
    def __init__(self, memory_skill=None, stop_delay=0.0):
        self.memory_skill = memory_skill
        self.stop_delay = stop_delay
        self.stopped = False
        self.shut_down = False

    async def stop_skills(self):
        await asyncio.sleep(self.stop_delay)
        self.stopped = True

    def shutdown(self):
        self.shut_down = True


# --- the steps happen ---------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_saves_stops_and_closes():
    brain = Brain(Memory())

    await cli.shutdown(brain)

    assert brain.memory_skill.saved
    assert brain.stopped and brain.shut_down


@pytest.mark.asyncio
async def test_a_failed_save_does_not_keep_the_bot_alive():
    brain = Brain(Memory(error=RuntimeError("the llm is down")))

    await cli.shutdown(brain)

    assert brain.stopped and brain.shut_down


@pytest.mark.asyncio
async def test_nothing_is_saved_when_memory_is_off():
    brain = Brain(Memory(enabled=False))

    await cli.shutdown(brain)

    assert not brain.memory_skill.saved
    assert brain.stopped and brain.shut_down


# --- ctrl+c, which is how this program is stopped -----------------------------


@pytest.mark.asyncio
async def test_a_cancelled_save_still_lets_the_skills_stop():
    """The bug, exactly: the interrupt landed on the save and took the rest."""
    brain = Brain(Memory(delay=5.0))

    task = asyncio.ensure_future(cli.shutdown(brain))
    await asyncio.sleep(0)  # let it reach the save
    task.cancel()
    await task

    assert brain.stopped and brain.shut_down


@pytest.mark.asyncio
async def test_a_hanging_save_is_given_up_on(monkeypatch):
    """A second ctrl+c has to get her out, so every step is bounded."""
    monkeypatch.setattr(cli, "SAVE_GRACE", 0.05)
    brain = Brain(Memory(delay=30.0))

    await asyncio.wait_for(cli.shutdown(brain), timeout=5)

    assert not brain.memory_skill.saved
    assert brain.stopped and brain.shut_down


# --- the port the bot listens on ---------------------------------------------


class Cfg:
    def __init__(self, **discord):
        self.skills = {"discord": {"enabled": True, **discord}}


def test_a_free_port_is_free():
    with socket.socket() as probe:
        probe.bind((LOOPBACK, 0))
        free = probe.getsockname()[1]

    assert not DiscordTransport(Cfg(api_port=free)).port_is_taken()


def test_a_bot_that_never_left_is_seen_before_a_second_one_is_started():
    """What the crash left behind: a node bot still holding 3030."""
    with socket.socket() as squatter:
        squatter.bind((LOOPBACK, 0))
        squatter.listen(1)
        port = squatter.getsockname()[1]

        assert DiscordTransport(Cfg(api_port=port)).port_is_taken()


def test_the_busy_port_is_said_out_loud_and_nothing_is_spawned(monkeypatch, tmp_path, caplog):
    """Three restarts and a lecture about the token, for a port in use."""
    (tmp_path / "node_modules").mkdir()
    with socket.socket() as squatter:
        squatter.bind((LOOPBACK, 0))
        squatter.listen(1)
        port = squatter.getsockname()[1]

        transport = DiscordTransport(Cfg(api_port=port))
        transport.bot_dir = tmp_path
        monkeypatch.setenv("DISCORD_TOKEN", "a-token")
        monkeypatch.setattr("src.core.skills.voice.transport.executable", lambda name: "node")
        monkeypatch.setattr("subprocess.Popen", _never)

        assert transport.start() is False

    assert "already in use" in caplog.text


def _never(*args, **kwargs):
    raise AssertionError("the bot must not be started onto a port that is taken")

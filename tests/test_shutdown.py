"""Stopping her: what ctrl+c is allowed to interrupt, and what it is not.

The steps of a shutdown are not optional. ctrl+c cancels the task running
`main`, the cancellation lands on the first `await` of the shutdown, and
`except Exception` never caught it — so the save ate the interrupt and
everything after it was skipped. The discord bot outlived the brain, kept the
port it was listening on, and the next start died on that port instead.
"""

import asyncio
import socket
import subprocess

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


# --- once asked to stop, the bot stays down ----------------------------------


class DeadTransport:
    """A transport whose subprocess has died: the supervisor's trigger."""

    def __init__(self):
        self.starts = 0

    def start(self) -> bool:
        self.starts += 1
        return True

    def poll_exit(self):
        return -2  # SIGINT: what ctrl+c used to do to the bot

    def stop(self) -> None:
        pass

    def terminate(self) -> None:
        pass

    async def close(self) -> None:
        pass


def _voice_surface(transport):
    from src.core.skills.voice.surface import VoiceSurface

    surface = VoiceSurface(Cfg(), bus=None, expression=None)
    surface.initialize()
    surface.transport = transport
    surface.active = True
    surface.restart_backoff = 0.0
    return surface


@pytest.mark.asyncio
async def test_a_stopping_supervisor_does_not_bring_the_bot_back():
    """The shutdown race: the bot died with the terminal's SIGINT while the
    supervisor was still active, and was restarted mid-shutdown."""
    surface = _voice_surface(DeadTransport())
    surface._shutting_down = True

    await surface.supervise_once()

    assert surface.transport.starts == 0


@pytest.mark.asyncio
async def test_stop_disarms_the_supervisor():
    surface = _voice_surface(DeadTransport())

    await surface.stop()

    assert surface._shutting_down is True
    assert surface.active is False
    await surface.supervise_once()
    assert surface.transport.starts == 0


class FakeProcess:
    """A subprocess that leaves when asked to."""

    def __init__(self, exit_on_terminate=True):
        self.pid = 4242
        self.terminated = False
        self.killed = False
        self._exit_on_terminate = exit_on_terminate

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        if self.killed or (self.terminated and self._exit_on_terminate):
            return 0
        raise subprocess.TimeoutExpired("node index.js", timeout)


def test_stop_asks_before_it_kills():
    """SIGKILL mid-word was the abrupt voice drop; SIGTERM lets the bot
    leave the call and the gateway first."""
    transport = DiscordTransport(Cfg())
    proc = FakeProcess()
    transport.bot_process = proc

    transport.stop()

    assert proc.terminated is True
    assert proc.killed is False
    assert transport.bot_process is None


def test_stop_kills_what_ignores_the_ask():
    transport = DiscordTransport(Cfg())
    proc = FakeProcess(exit_on_terminate=False)
    transport.bot_process = proc

    transport.stop()

    assert proc.terminated is True
    assert proc.killed is True
    assert transport.bot_process is None


# --- one hung skill does not starve the rest ---------------------------------


def _mind(timeout=0.05):
    from src.core.consciousness import Consciousness

    mind = Consciousness.__new__(Consciousness)
    mind._SURFACE_STOP_TIMEOUT = timeout
    return mind


class QuickSkill:
    name = "quick"

    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


class HungSkill:
    name = "hung"

    async def stop(self):
        await asyncio.sleep(30.0)


@pytest.mark.asyncio
async def test_a_hung_skill_is_carried_past():
    await asyncio.wait_for(_mind()._stop_surface(HungSkill()), timeout=5)


@pytest.mark.asyncio
async def test_a_failing_skill_does_not_take_the_shutdown_with_it():
    class Failing:
        name = "failing"

        async def stop(self):
            raise RuntimeError("telegram is having a day")

    # raises nothing: the failure is said out loud instead
    await _mind()._stop_surface(Failing())


# --- the streams end when the server does, not on timeout ---------------------


async def test_close_ends_the_event_streams_quietly():
    """Force-closing the connections cancelled the streaming responses
    mid-sentence: a CancelledError traceback on every shutdown."""
    from src.core.events import EventManager

    m = EventManager()
    queue = m.subscribe(backlog=0)

    m.close()

    assert queue.get_nowait() == {"shutdown": True}
    assert m.subscriber_count == 0
    assert len(m.events) == 0  # the history is not the streams


def test_close_hands_the_page_its_last_patch_first():
    from src.core.stage import StageChannel

    channel = StageChannel()
    queue = channel.subscribe()

    channel.close()

    assert queue.get_nowait() == {"closed": True}


# --- the shutdown starts on signal, before the graceful wait -----------------


class RecordingTransport(DeadTransport):
    def __init__(self):
        super().__init__()
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True


def test_begin_shutdown_stands_down_and_asks():
    transport = RecordingTransport()
    surface = _voice_surface(transport)

    surface.begin_shutdown()

    assert surface._shutting_down is True
    assert surface.active is False
    assert transport.terminated is True
    # idempotent: a second signal changes nothing
    surface.begin_shutdown()
    assert transport.starts == 0


def test_terminate_is_fire_and_forget():
    """The signal handler cannot wait: the wait (and the kill fallback)
    still happens later, on the skills' way down."""
    transport = DiscordTransport(Cfg())
    proc = FakeProcess()
    transport.bot_process = proc

    transport.terminate()

    assert proc.terminated is True
    assert proc.killed is False
    assert transport.bot_process is proc


def test_terminate_with_no_bot_is_nothing():
    DiscordTransport(Cfg()).terminate()


def test_terminate_survives_a_process_that_is_already_gone():
    transport = DiscordTransport(Cfg())

    class Gone:
        def terminate(self):
            raise OSError(3, "no such process")

    transport.bot_process = Gone()
    transport.terminate()

    assert isinstance(transport.bot_process, Gone)  # reaped later, by stop()


@pytest.mark.asyncio
async def test_the_signal_starts_the_shutdown_before_the_wait(monkeypatch):
    """Uvicorn drains its connections before it runs the lifespan shutdown,
    so the bot kept retrying a dead address through the whole graceful wait.
    The signal itself now stands the supervisor down, asks the bot to leave
    and ends the streams — the wait finds nothing left to wait for."""
    import signal as signal_module
    import types

    import uvicorn

    from src.core.events import EventManager
    from src.core.stage import StageChannel
    from src.web import server as web_server
    from src.web.app import app

    transport = RecordingTransport()
    surface = _voice_surface(transport)
    events = EventManager()
    event_queue = events.subscribe(backlog=0)
    stage = StageChannel()
    stage_queue = stage.subscribe()
    brain = types.SimpleNamespace(
        skill_registry=types.SimpleNamespace(get=lambda name: surface),
        stage=stage, event_manager=events)

    servers = []

    class SignalledServer:
        def __init__(self, config):
            self.signals = []
            self.handle_exit = self._original
            servers.append(self)

        def _original(self, sig, frame):
            self.signals.append(sig)

        async def serve(self):
            async with app.router.lifespan_context(app):
                pass

    monkeypatch.setattr(uvicorn, "Server", SignalledServer)

    await web_server.run_server(brain, on_shutdown=None)

    servers[0].handle_exit(signal_module.SIGINT, None)

    assert servers[0].signals == [signal_module.SIGINT]
    assert transport.terminated is True
    assert surface._shutting_down is True and surface.active is False
    assert event_queue.get_nowait() == {"shutdown": True}
    assert stage_queue.get_nowait() == {"closed": True}


@pytest.mark.asyncio
async def test_the_brain_shuts_down_with_the_server(monkeypatch):
    """ctrl+c used to park on 'Waiting for connections to close' (the
    dashboard's streams) with every skill still up, and only then shut the
    brain down. The shutdown now rides the server's lifespan instead."""
    import uvicorn

    from src.web import server as web_server
    from src.web.app import app
    from src.web.deps import current_brain

    done = []
    seen = {}

    async def on_shutdown():
        done.append(True)

    class FakeServer:
        def __init__(self, config):
            seen["graceful_timeout"] = config.timeout_graceful_shutdown

        async def serve(self):
            # what uvicorn does around serve(): lifespan in, then out again
            async with app.router.lifespan_context(app):
                pass

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    before = app.router.lifespan_context
    brain = object()

    await web_server.run_server(brain, on_shutdown=on_shutdown)

    assert done == [True]
    assert seen["graceful_timeout"] == web_server.GRACEFUL_TIMEOUT
    assert current_brain() is brain
    # the app object is shared with the tests: the lifespan must not leak out
    assert app.router.lifespan_context is before

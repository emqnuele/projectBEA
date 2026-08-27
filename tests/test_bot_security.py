"""The Discord bot's command API must not be usable by anyone who can reach it.

The bot is a node subprocess with an HTTP API that can write messages, send
DMs and create invites. Before this, it listened on every interface with no
credential at all: anyone on the same network could drive Bea's account.

These tests run against a real aiohttp server, so what is asserted is what
actually goes over the wire.
"""

import pytest
from aiohttp import web

from src.core.skills.voice.transport import DiscordTransport


class Config:
    def __init__(self, **discord):
        self.skills = {"discord": {"enabled": True, **discord}}


class Echo:
    """A stand-in for the node bot: records the requests it was sent."""

    def __init__(self):
        self.requests = []
        self._runner = None
        self.port = 0

    async def start(self) -> int:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _handle(self, request):
        self.requests.append({
            "path": request.path,
            "headers": dict(request.headers),
        })
        return web.json_response({"success": True})

    @property
    def last(self):
        return self.requests[-1]


@pytest.fixture
async def bot():
    server = Echo()
    await server.start()
    yield server
    await server.stop()


def transport_for(server: Echo) -> DiscordTransport:
    t = DiscordTransport(Config(api_port=server.port))
    t.api_url = f"http://127.0.0.1:{server.port}"
    # the surface sets this when it starts the subprocess; here there is none
    t.bot_process = object()
    return t


# --- the shared secret -------------------------------------------------------


def test_a_transport_mints_its_own_secret():
    a = DiscordTransport(Config())
    b = DiscordTransport(Config())
    assert len(a.api_token) >= 32
    assert a.api_token != b.api_token


async def test_every_command_carries_the_secret(bot):
    t = transport_for(bot)
    await t.send_message("123", "ciao")
    assert bot.last["headers"].get("Authorization") == f"Bearer {t.api_token}"


async def test_a_read_carries_it_too(bot):
    t = transport_for(bot)
    await t.list_voice_channels()
    assert bot.last["headers"].get("Authorization") == f"Bearer {t.api_token}"


async def test_the_secret_reaches_the_subprocess():
    t = DiscordTransport(Config())
    env = t.subprocess_env("a-token")
    assert env["API_TOKEN"] == t.api_token


async def test_the_bot_is_told_to_stay_on_loopback():
    t = DiscordTransport(Config())
    assert t.subprocess_env("a-token")["BIND_HOST"] == "127.0.0.1"


# --- the session -------------------------------------------------------------


async def test_the_transport_reuses_one_session(bot):
    t = transport_for(bot)
    await t.send_message("123", "uno")
    first = t._session
    await t.send_message("123", "due")
    assert t._session is first
    await t.close()


async def test_closing_the_transport_releases_the_session(bot):
    t = transport_for(bot)
    await t.send_message("123", "ciao")
    await t.close()
    assert t._session is None


# --- an offline bot ----------------------------------------------------------


async def test_a_command_to_a_dead_bot_fails_cleanly():
    t = DiscordTransport(Config())
    result = await t.send_message("123", "ciao")
    assert result["ok"] is False
    assert "offline" in result["error"]


async def test_stopping_only_reaches_for_taskkill_on_windows(monkeypatch):
    """`taskkill` does not exist off Windows; calling it there is noise."""
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: calls.append(a))

    class Proc:
        pid = 4711

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    t = DiscordTransport(Config())
    t.bot_process = Proc()
    monkeypatch.setattr("sys.platform", "darwin")
    t.stop()
    assert calls == []


# --- supervision -------------------------------------------------------------


class FlakyTransport:
    """A transport whose subprocess dies once, then stays up."""

    def __init__(self, deaths: int = 1):
        self.starts = 0
        self.deaths = deaths
        self.api_token = "t"

    def start(self) -> bool:
        self.starts += 1
        return True

    def poll_exit(self):
        if self.deaths > 0:
            self.deaths -= 1
            return 1
        return None

    def stop(self) -> None:
        pass

    async def close(self) -> None:
        pass


async def test_a_dead_bot_is_started_again():
    from src.core.skills.voice.surface import VoiceSurface

    surface = VoiceSurface(Config(), bus=None, expression=None)
    surface.transport = FlakyTransport(deaths=1)
    surface.active = True
    surface.restart_backoff = 0.0

    await surface.supervise_once()
    assert surface.transport.starts == 1
    assert surface.active is True


async def test_a_living_bot_is_left_alone():
    from src.core.skills.voice.surface import VoiceSurface

    surface = VoiceSurface(Config(), bus=None, expression=None)
    surface.transport = FlakyTransport(deaths=0)
    surface.active = True

    await surface.supervise_once()
    assert surface.transport.starts == 0


async def test_a_bot_that_will_not_come_back_goes_inactive():
    from src.core.skills.voice.surface import VoiceSurface

    class Dead(FlakyTransport):
        def start(self) -> bool:
            self.starts += 1
            return False

    surface = VoiceSurface(Config(), bus=None, expression=None)
    surface.transport = Dead(deaths=1)
    surface.active = True
    surface.restart_backoff = 0.0

    await surface.supervise_once()
    assert surface.active is False


async def test_stopping_the_surface_releases_the_session():
    from src.core.skills.voice.surface import VoiceSurface

    closed = []

    class Watched(FlakyTransport):
        async def close(self) -> None:
            closed.append(True)

    surface = VoiceSurface(Config(), bus=None, expression=None)
    surface.transport = Watched()
    surface.active = True
    await surface.stop()
    assert closed == [True]

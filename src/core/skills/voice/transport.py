import errno
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from src.core.config import BrainConfig
from src.setup.node import executable
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice.transport")

# the bot's command API can write messages, send DMs and create invites. It is
# reachable over TCP, so it gets a credential and stays off the network.
LOOPBACK = "127.0.0.1"

# what `brain_api_url` means when nobody chose anything: the engine's own
# default address. `--port`/`--host` move the engine, so an untouched default
# follows them (see `apply_cli_address`); a customized value always wins.
DEFAULT_BRAIN_API_URL = "http://127.0.0.1:8000"


def _dial_host(host: str) -> str:
    """The host the bot can actually call back on.

    The server may bind `0.0.0.0` (every interface), which is not a dialable
    address — the bot lives on this machine, so it calls back on loopback.
    """
    host = (host or "").strip() or LOOPBACK
    if host == "0.0.0.0":
        return LOOPBACK
    return host


def effective_brain_api_url(config: BrainConfig, host: str, port: int) -> str:
    """The engine URL the bot should call, without writing anything down.

    Untouched (absent or still the default) follows `--host`/`--port`;
    anything else was chosen on purpose and wins as-is.
    """
    configured = config.skills.get("discord", {}).get("brain_api_url", DEFAULT_BRAIN_API_URL)
    if configured and configured != DEFAULT_BRAIN_API_URL:
        return configured
    return f"http://{_dial_host(host)}:{port}"


def apply_cli_address(config: BrainConfig, host: str, port: int) -> str:
    """Point an untouched `brain_api_url` at this launch's engine address.

    In-memory only: nothing is written to config.json here, so a later dashboard
    save is still the moment a value gets pinned down. Returns the URL in force
    and warns when a customized value points elsewhere than this launch.
    """
    from urllib.parse import urlparse

    effective = effective_brain_api_url(config, host, port)
    discord = config.skills.setdefault("discord", {})
    if "brain_api_url" not in discord or discord.get("brain_api_url") == DEFAULT_BRAIN_API_URL:
        discord["brain_api_url"] = effective
        return effective
    try:
        configured_port = urlparse(str(discord.get("brain_api_url"))).port
    except Exception:
        configured_port = None
    if configured_port is not None and configured_port != int(port):
        logger.warning(
            f"discord.brain_api_url points at port {configured_port} but the engine "
            f"is on :{port} (--port). The bot keeps calling the configured URL; "
            f"change Engine URL in Settings -> Discord if that is not what you want."
        )
    return str(discord.get("brain_api_url"))


class DiscordTransport:
    """Owns the Discord bot: a node.js subprocess (bot/) plus its HTTP send API.

    This is the transport layer of the voice capability. The VoiceSurface starts
    and stops it; perceptions come back into the brain via the HTTP endpoints the
    bot calls. It is not a Skill itself — it's infrastructure the voice skill owns.
    """

    def __init__(self, config: BrainConfig):
        self.config = config
        self.bot_process: Optional[subprocess.Popen] = None
        self.bot_dir = Path(__file__).parent / "bot"
        self.api_url = f"http://{LOOPBACK}:{self._port()}"
        # minted per process and handed to the subprocess: never written to disk
        self.api_token = secrets.token_urlsafe(32)
        self._session: Optional[aiohttp.ClientSession] = None

    def _port(self) -> int:
        return self.config.skills.get("discord", {}).get("api_port", 3030)

    def port_is_taken(self) -> bool:
        """Is something already listening on the bot's API port?

        The node bot binds the port only after it has logged into discord, so a
        collision used to read as "the bot quit immediately" — three restarts
        and a lecture about the token, for a port. Asking first costs one bind
        and says the true thing instead.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            # no SO_REUSEADDR on purpose: the question is whether the address is
            # free, and reusing it is exactly what must not be allowed here
            try:
                probe.bind((LOOPBACK, self._port()))
            except OSError as e:
                return e.errno in (errno.EADDRINUSE, errno.EACCES)
        return False

    def _brain_api_url(self) -> str:
        # where the node bot calls back into the brain (its senses)
        return self.config.skills.get("discord", {}).get("brain_api_url", DEFAULT_BRAIN_API_URL)

    @property
    def running(self) -> bool:
        return self.bot_process is not None

    def subprocess_env(self, token: str) -> Dict[str, str]:
        """The environment the node bot is started with."""
        dcfg = self.config.skills.get("discord", {})
        env = os.environ.copy()
        env["DISCORD_TOKEN"] = token
        # where the bot keeps its runtime state (whitelist): outside the
        # source tree, so it never reads as local changes to the updater
        root = Path(__file__).resolve().parents[4]
        env.setdefault("BEA_DATA_DIR", str(root / "data"))
        env["PORT"] = str(self._port())
        env["BIND_HOST"] = LOOPBACK
        env["API_TOKEN"] = self.api_token
        env["BRAIN_API_URL"] = self._brain_api_url()
        env["ADMIN_ID"] = str(dcfg.get("admin_id", "") or os.getenv("DISCORD_ADMIN_ID", ""))
        env["ACCESS_MODE"] = str(dcfg.get("access_mode", "strict"))
        env["DUCK_THRESHOLD_MS"] = str(dcfg.get("duck_threshold_ms", 400))
        env["INTERRUPT_THRESHOLD_MS"] = str(dcfg.get("interrupt_threshold_ms", 4000))
        env["INVITE_MAX_AGE"] = str(dcfg.get("invite_max_age_seconds", 3600))
        env["INVITE_MAX_USES"] = str(dcfg.get("invite_max_uses", 1))
        return env

    def start(self) -> bool:
        if self.running:
            return True

        token = os.getenv("DISCORD_TOKEN", "") or self.config.skills.get("discord", {}).get("token", "")
        if not token:
            logger.error("Discord token not configured (env DISCORD_TOKEN or config).")
            return False

        if not (self.bot_dir / "node_modules").exists():
            logger.error("The discord bot's packages are not installed. "
                         "Run `uv run bea --install-node`.")
            return False

        node = executable("node")
        if node is None:
            logger.error("The discord bot is a node program and node is not installed. "
                         "Get node 20 or newer from https://nodejs.org.")
            return False

        if self.port_is_taken():
            logger.error(f"Port {LOOPBACK}:{self._port()} is already in use, so the discord "
                         "bot has nowhere to listen. Another copy of her is probably still "
                         "running — close it, or give this one a different discord.api_port.")
            return False

        self.api_url = f"http://{LOOPBACK}:{self._port()}"

        try:
            self.bot_process = subprocess.Popen(
                [node, "index.js"], cwd=str(self.bot_dir), env=self.subprocess_env(token),
                stdout=sys.stdout, stderr=sys.stderr, shell=False,
            )
            logger.info(f"Discord bot started with PID {self.bot_process.pid}.")
            return True
        except Exception as e:
            logger.error(f"Failed to start Discord bot: {e}")
            self.bot_process = None
            return False

    def stop(self) -> None:
        if not self.bot_process:
            return
        logger.info("Stopping Discord bot...")
        try:
            self.bot_process.kill()
            if sys.platform.startswith("win"):
                # windows leaves the child tree behind after a kill
                subprocess.run(f"taskkill /F /T /PID {self.bot_process.pid}", shell=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.bot_process.wait(timeout=2)
        except Exception as e:
            logger.error(f"Error stopping Discord bot: {e}")
        finally:
            self.bot_process = None

    async def close(self) -> None:
        """Releases the shared HTTP session."""
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as e:
                logger.debug(f"Closing the discord session failed: {e}")
            finally:
                self._session = None

    def poll_exit(self) -> Optional[int]:
        """Returns the exit code if the process died, else None (and clears it)."""
        if not self.bot_process:
            return None
        ret = self.bot_process.poll()
        if ret is not None:
            logger.error(f"Discord bot exited unexpectedly with code {ret}.")
            self.bot_process = None
        return ret

    # --- command API (brain -> bot) ----------------------------------------
    # every method returns a dict {"ok": bool, ...} so the tool layer can turn it
    # into a clean observation for Bea instead of raising.

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, method: str, path: str,
                       payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.running:
            return {"ok": False, "error": "discord bot is offline"}
        url = f"{self.api_url}{path}"
        try:
            session = await self._get_session()
            async with session.request(method, url, json=payload,
                                       headers=self._headers()) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = {"raw": await resp.text()}
                if resp.status == 200:
                    return {"ok": True, **(data if isinstance(data, dict) else {"data": data})}
                logger.error(f"Discord API {path} -> {resp.status}: {data}")
                return {"ok": False, "error": data.get("error", f"http {resp.status}")
                        if isinstance(data, dict) else f"http {resp.status}"}
        except Exception as e:
            logger.error(f"Discord API request {path} failed: {e}")
            return {"ok": False, "error": str(e)}

    async def send_message(self, channel_id: str, content: str) -> Dict[str, Any]:
        return await self._request("POST", "/send", {"channelId": channel_id, "content": content})

    async def reply_message(self, channel_id: str, message_id: str, content: str) -> Dict[str, Any]:
        return await self._request("POST", "/reply",
                                   {"channelId": channel_id, "messageId": message_id, "content": content})

    async def typing(self, channel_id: str) -> Dict[str, Any]:
        """Shows the "is typing" indicator; cosmetic, so failures are not surfaced."""
        return await self._request("POST", "/typing", {"channelId": channel_id})

    async def react_message(self, channel_id: str, message_id: str, emoji: str) -> Dict[str, Any]:
        return await self._request("POST", "/react",
                                   {"channelId": channel_id, "messageId": message_id, "emoji": emoji})

    async def send_dm(self, user_id: str, content: str) -> Dict[str, Any]:
        return await self._request("POST", "/dm", {"userId": user_id, "content": content})

    async def summon(self, user_id: str, channel_id: str, content: Optional[str] = None) -> Dict[str, Any]:
        return await self._request("POST", "/summon",
                                   {"userId": user_id, "channelId": channel_id, "content": content})

    async def list_voice_channels(self) -> Dict[str, Any]:
        return await self._request("GET", "/voice/channels")

    async def join_voice(self, channel_id: str) -> Dict[str, Any]:
        return await self._request("POST", "/voice/join", {"channelId": channel_id})

    async def leave_voice(self) -> Dict[str, Any]:
        return await self._request("POST", "/voice/leave", {})

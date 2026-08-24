import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from src.core.config import BrainConfig
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice.transport")


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
        self.api_url = f"http://localhost:{self._port()}"

    def _port(self) -> int:
        return self.config.skills.get("discord", {}).get("api_port", 3030)

    def _brain_api_url(self) -> str:
        # where the node bot calls back into the brain (its senses)
        return self.config.skills.get("discord", {}).get("brain_api_url", "http://127.0.0.1:8000")

    @property
    def running(self) -> bool:
        return self.bot_process is not None

    def start(self) -> bool:
        if self.running:
            return True

        token = os.getenv("DISCORD_TOKEN", "") or self.config.skills.get("discord", {}).get("token", "")
        if not token:
            logger.error("Discord token not configured (env DISCORD_TOKEN or config).")
            return False

        if not (self.bot_dir / "node_modules").exists():
            logger.error("node_modules not found. Run 'npm install' in the bot directory.")
            return False

        self.api_url = f"http://localhost:{self._port()}"
        dcfg = self.config.skills.get("discord", {})
        env = os.environ.copy()
        env["DISCORD_TOKEN"] = token
        env["PORT"] = str(self._port())
        env["BRAIN_API_URL"] = self._brain_api_url()
        env["ADMIN_ID"] = str(dcfg.get("admin_id", "") or os.getenv("DISCORD_ADMIN_ID", ""))
        env["INTERRUPT_THRESHOLD_MS"] = str(dcfg.get("interrupt_threshold_ms", 2000))

        try:
            self.bot_process = subprocess.Popen(
                ["node", "index.js"], cwd=str(self.bot_dir), env=env,
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
            # windows fallback to fully kill the tree
            subprocess.run(f"taskkill /F /T /PID {self.bot_process.pid}", shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.bot_process.wait(timeout=2)
        except Exception as e:
            logger.error(f"Error stopping Discord bot: {e}")
        finally:
            self.bot_process = None

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

    async def _request(self, method: str, path: str,
                       payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.running:
            return {"ok": False, "error": "discord bot is offline"}
        url = f"{self.api_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, json=payload) as resp:
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

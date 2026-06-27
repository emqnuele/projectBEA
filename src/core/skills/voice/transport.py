import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

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
        env = os.environ.copy()
        env["DISCORD_TOKEN"] = token
        env["PORT"] = str(self._port())

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

    async def send_message(self, channel_id: str, content: str) -> bool:
        if not self.running:
            logger.warning("Cannot send message: Discord bot is offline.")
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/send", json={"channelId": channel_id, "content": content}
                ) as resp:
                    if resp.status == 200:
                        return True
                    logger.error(f"Failed to send message: {await resp.text()}")
                    return False
        except Exception as e:
            logger.error(f"Discord send request failed: {e}")
            return False

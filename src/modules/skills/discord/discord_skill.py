import asyncio
import subprocess
import os
import signal
import aiohttp
import sys
from typing import Optional
from src.core.config import BrainConfig
from src.modules.skills.base_skill import BaseSkill
from pathlib import Path

class DiscordSkill(BaseSkill):
    def __init__(self, name: str, config: BrainConfig, context):
        super().__init__(name, config, context)
        self.bot_process: Optional[subprocess.Popen] = None
        self.bot_dir = Path(__file__).parent / "bot"
        api_port = config.skills.get("discord", {}).get("api_port", 3030)
        self.api_url = f"http://localhost:{api_port}"

    def initialize(self):
        pass

    async def start(self):
        if self.is_active:
            self.log("Discord Bot already running.")
            return

        # priority: env var → config → None  (matches universal secret-field behaviour)
        discord_token = os.getenv("DISCORD_TOKEN", "")
        if not discord_token:
            discord_token = self.skill_config.get("token", "")

        if not discord_token:
            self.log("Error: Discord Token not configured (Config or Env 'DISCORD_TOKEN').")
            return

        self.log("Starting Discord Bot...")
        
        # env vars
        api_port = self.skill_config.get("api_port", 3030)
        self.api_url = f"http://localhost:{api_port}"
        env = os.environ.copy()
        env["DISCORD_TOKEN"] = discord_token
        env["PORT"] = str(api_port) 
        
        # check if node_modules exists
        if not (self.bot_dir / "node_modules").exists():
            self.log("Error: node_modules not found. Please run 'npm install' in the bot directory.")
            return

        try:
            # shell=False for correct termination
            self.bot_process = subprocess.Popen(
                ["node", "index.js"],
                cwd=str(self.bot_dir),
                env=env,
                stdout=sys.stdout, 
                stderr=sys.stderr,
                shell=False
            )
            await super().start()  # sets self.is_active = True
            self.log(f"Discord Bot started with PID {self.bot_process.pid}")
            
        except Exception as e:
            self.log(f"Failed to start Discord Bot: {e}")
            self.is_active = False

    async def stop(self):
        if not self.bot_process:
            self.log("Discord Bot is not running.")
            return

        self.log("Stopping Discord Bot...")
        try:
            # force kill the process
            if self.bot_process:
                self.bot_process.kill()
                
                # taskkill to be sure
                subprocess.run(f"taskkill /F /T /PID {self.bot_process.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                self.bot_process.wait(timeout=2)
            
            self.bot_process = None
            self.is_active = False
            await super().stop()
        except Exception as e:
            self.log(f"Error stopping Discord Bot: {e}")

    async def update(self):
        # monitor process
        if self.bot_process:
            ret = self.bot_process.poll()
            if ret is not None:
                self.log(f"Discord Bot process exited unexpectedly with code {ret}")
                self.bot_process = None
                self.is_active = False

    async def send_message(self, channel_id: str, content: str):
        if not self.is_active:
            self.log("Cannot send message: Bot is offline.")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/send", 
                    json={"channelId": channel_id, "content": content}
                ) as resp:
                    if resp.status == 200:
                        self.log(f"Message sent to {channel_id}")
                        return True
                    else:
                        text = await resp.text()
                        self.log(f"Failed to send message: {text}")
                        return False
        except Exception as e:
            self.log(f"API Request failed: {e}")
            return False

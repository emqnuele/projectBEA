import asyncio
import json
from typing import Any, Dict, List, Optional

from src.core.agent.tools import Tool
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import Skill
from src.core.skills.voice.transport import DiscordTransport
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice")


class VoiceSurface(Skill):
    """Discord capability (voice + text). Owns the bot transport (node subprocess).

    Input: voice transcripts and text messages arrive via the HTTP endpoints the
    bot calls -> perceive() / perceive_text(), and land on the bus as perceptions.
    Output: Bea acts on discord through tools() (join/leave/send/reply/dm/...) and
    her rendered voice (Expression route='remote') is handed back to the bot.
    """

    name = "voice:discord"
    skill_name = "discord"

    def initialize(self) -> None:
        self.transport = DiscordTransport(self.config)
        self._monitor: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if not self.enabled:
            logger.info("VoiceSurface inactive (discord skill disabled).")
            return
        if self.transport.start():
            self.active = True
            self._monitor = asyncio.create_task(self._watch_transport())
            logger.info("VoiceSurface started.")

    async def stop(self) -> None:
        self.active = False
        if self._monitor:
            self._monitor.cancel()
            self._monitor = None
        self.transport.stop()
        logger.info("VoiceSurface stopped.")

    async def _watch_transport(self) -> None:
        """If the bot process dies, the capability goes inactive."""
        while self.active:
            if self.transport.poll_exit() is not None:
                self.active = False
                break
            await asyncio.sleep(2)

    # --- senses (bot -> bus) -----------------------------------------------

    def _author(self, user: str, user_id: Optional[str]) -> Author:
        # native_id is the stable discord user id; display_name can change
        return Author(platform="discord", native_id=user_id or user, display_name=user)

    def perceive(self, transcript: str, user: str, meta: Optional[Dict[str, Any]] = None,
                 user_id: Optional[str] = None) -> Perception:
        p = Perception(
            kind=PerceptionKind.VOICE,
            surface=self.name,
            content=f"[{user}] (voice): {transcript}",
            salience=0.85,
            meta={**(meta or {}), "user": user, "user_id": user_id},
            author=self._author(user, user_id),
        )
        self.bus.put(p)
        return p

    def perceive_text(self, text: str, user: str, channel_id: str,
                      message_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None,
                      user_id: Optional[str] = None, is_dm: bool = False) -> Perception:
        # text from discord flows through the same single consciousness as voice;
        # the ids are rendered inline so Bea can act on them (reply/react/send)
        kind = "dm" if is_dm else "text"
        route = f"channel_id={channel_id}"
        if message_id:
            route += f", message_id={message_id}"
        p = Perception(
            kind=PerceptionKind.CHAT,
            surface=self.name,
            content=f"[{user}] (discord {kind}, {route}): {text}",
            salience=0.8,
            meta={**(meta or {}), "user": user, "user_id": user_id,
                  "channel_id": channel_id, "message_id": message_id, "is_dm": is_dm},
            author=self._author(user, user_id),
        )
        self.bus.put(p)
        return p

    # --- prompt context -----------------------------------------------------

    @property
    def context_section(self) -> Optional[str]:
        if not self.active:
            return None
        return (
            "## DISCORD\n"
            "You are connected to Discord. Some perceptions are tagged `(discord ...)` "
            "and carry a `channel_id` (and a `message_id` for text messages).\n"
            "- `speak` is your LIVE VOICE — use it when you're in a voice call or on stream.\n"
            "- For Discord TEXT, do NOT use `speak`. Answer with `discord_reply` "
            "(to the message_id) or `discord_send_message` (to the channel_id). React with "
            "`discord_react`. DM with `discord_send_dm`.\n"
            "- You decide on your own whether a message is worth answering. You may also "
            "act first: check `discord_list_voice_channels`, `discord_join_voice` to hang "
            "out, or `discord_summon` to call someone in."
        )

    # --- output sink --------------------------------------------------------

    async def emit_text(self, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
        channel_id = (meta or {}).get("channel_id")
        if channel_id:
            await self.transport.send_message(str(channel_id), text)

    # --- tools (brain -> bot) ----------------------------------------------

    def tools(self) -> List[Tool]:
        if not self.active:
            return []
        return [
            Tool(
                "discord_list_voice_channels",
                "List the discord voice channels and who is currently in each. Use this to "
                "see where people are before deciding to join a call.",
                {"type": "object", "properties": {}, "required": []},
                self._tool_list_voice_channels,
            ),
            Tool(
                "discord_join_voice",
                "Join a specific discord voice channel by its id, to talk with the people in it.",
                {"type": "object", "properties": {"channel_id": {"type": "string"}},
                 "required": ["channel_id"]},
                self._tool_join_voice,
            ),
            Tool(
                "discord_leave_voice",
                "Leave the discord voice channel you are currently in.",
                {"type": "object", "properties": {}, "required": []},
                self._tool_leave_voice,
            ),
            Tool(
                "discord_send_message",
                "Write a text message in a discord channel (by channel id).",
                {"type": "object", "properties": {
                    "channel_id": {"type": "string"}, "text": {"type": "string"}},
                 "required": ["channel_id", "text"]},
                self._tool_send_message,
            ),
            Tool(
                "discord_reply",
                "Reply to a specific discord message (by channel id + message id).",
                {"type": "object", "properties": {
                    "channel_id": {"type": "string"}, "message_id": {"type": "string"},
                    "text": {"type": "string"}},
                 "required": ["channel_id", "message_id", "text"]},
                self._tool_reply,
            ),
            Tool(
                "discord_react",
                "React to a discord message with a single emoji (by channel id + message id).",
                {"type": "object", "properties": {
                    "channel_id": {"type": "string"}, "message_id": {"type": "string"},
                    "emoji": {"type": "string"}},
                 "required": ["channel_id", "message_id", "emoji"]},
                self._tool_react,
            ),
            Tool(
                "discord_send_dm",
                "Send a private direct message to a discord user (by user id).",
                {"type": "object", "properties": {
                    "user_id": {"type": "string"}, "text": {"type": "string"}},
                 "required": ["user_id", "text"]},
                self._tool_send_dm,
            ),
            Tool(
                "discord_summon",
                "Call someone into a voice channel: DMs them an invite link to join you. "
                "A bot cannot ring, so this is how you 'call' a person.",
                {"type": "object", "properties": {
                    "user_id": {"type": "string"}, "channel_id": {"type": "string"},
                    "text": {"type": "string", "description": "optional extra line in the DM"}},
                 "required": ["user_id", "channel_id"]},
                self._tool_summon,
            ),
        ]

    @staticmethod
    def _fmt(result: Dict[str, Any], ok_msg: str) -> str:
        if result.get("ok"):
            return ok_msg
        return f"FAILED: {result.get('error', 'unknown error')}"

    async def _tool_list_voice_channels(self) -> str:
        res = await self.transport.list_voice_channels()
        if not res.get("ok"):
            return self._fmt(res, "")
        channels = res.get("channels", [])
        if not channels:
            return "No voice channels visible (or nobody is in any)."
        return json.dumps(channels, ensure_ascii=False)

    async def _tool_join_voice(self, channel_id: str) -> str:
        return self._fmt(await self.transport.join_voice(channel_id),
                         f"Joined voice channel {channel_id}.")

    async def _tool_leave_voice(self) -> str:
        return self._fmt(await self.transport.leave_voice(), "Left the voice channel.")

    async def _tool_send_message(self, channel_id: str, text: str) -> str:
        return self._fmt(await self.transport.send_message(channel_id, text), "Message sent.")

    async def _tool_reply(self, channel_id: str, message_id: str, text: str) -> str:
        return self._fmt(await self.transport.reply_message(channel_id, message_id, text), "Replied.")

    async def _tool_react(self, channel_id: str, message_id: str, emoji: str) -> str:
        return self._fmt(await self.transport.react_message(channel_id, message_id, emoji), "Reacted.")

    async def _tool_send_dm(self, user_id: str, text: str) -> str:
        return self._fmt(await self.transport.send_dm(user_id, text), "DM sent.")

    async def _tool_summon(self, user_id: str, channel_id: str, text: str = "") -> str:
        return self._fmt(await self.transport.summon(user_id, channel_id, text or None),
                         f"Summoned user {user_id} to {channel_id}.")

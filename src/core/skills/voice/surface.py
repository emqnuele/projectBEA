import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from src.core.agent.tools import Tool
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.platform import PlatformSkill
from src.core.skills.voice.transport import DiscordTransport
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice")


class VoiceSurface(PlatformSkill):
    """Discord capability (voice + text). Owns the bot transport (node subprocess).

    Input: voice transcripts and text messages arrive via the HTTP endpoints the
    bot calls -> perceive() / perceive_text(), and land on the bus as perceptions.
    Output: Bea acts on discord through tools() (join/leave/send/reply/dm/...) and
    her rendered voice (Expression route='remote') is handed back to the bot.
    """

    name = "voice:discord"
    skill_name = "discord"
    platform = "discord"

    # how long to wait before bringing a crashed bot back up
    restart_backoff: float = 3.0

    def initialize(self) -> None:
        super().initialize()
        self.transport = DiscordTransport(self.config)
        self._monitor: Optional[asyncio.Task] = None
        self.voice_channel: Optional[str] = None
        self._alone_since: Optional[float] = None

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
        if getattr(self, "_monitor", None):
            self._monitor.cancel()
            self._monitor = None
        self.transport.stop()
        await self.transport.close()
        logger.info("VoiceSurface stopped.")

    async def supervise_once(self) -> None:
        """One supervision pass: bring the bot back if it died.

        A node process that dies takes voice, DMs and every discord tool with
        it. Going quietly inactive was the wrong answer — she simply vanished
        from discord until someone noticed.
        """
        if self.transport.poll_exit() is None:
            return
        logger.warning("Discord bot died; restarting it.")
        await asyncio.sleep(self.restart_backoff)
        if self.transport.start():
            logger.info("Discord bot is back up.")
            return
        logger.error("Discord bot could not be restarted; the capability is off.")
        self.active = False

    # --- being left alone ---------------------------------------------------

    @property
    def _auto_leave_seconds(self) -> float:
        return float(self.config.skills.get("discord", {}).get("auto_leave_seconds", 120))

    def _forget_call(self) -> None:
        self.voice_channel = None
        self._alone_since = None

    async def check_solitude(self, now: Optional[float] = None) -> None:
        """Leaves a call everyone else walked out of.

        Sitting alone in an empty channel forever is the most obviously
        non-human thing she can do.
        """
        if not self.voice_channel or self._auto_leave_seconds <= 0:
            return
        now = time.time() if now is None else now

        result = await self.transport.list_voice_channels()
        if not result.get("ok"):
            return
        channel = next((c for c in result.get("channels", [])
                        if str(c.get("channelId")) == self.voice_channel), None)
        if channel is None:
            # she is not in it any more, whoever ended it
            self._forget_call()
            return

        others = [m for m in channel.get("members", []) if str(m.get("id")) != "bot"]
        if others:
            self._alone_since = None
            return

        if self._alone_since is None:
            self._alone_since = now
            return
        if now - self._alone_since >= self._auto_leave_seconds:
            logger.info("Alone in the voice channel; leaving.")
            await self.transport.leave_voice()
            self._forget_call()

    async def _watch_transport(self) -> None:
        while self.active:
            try:
                await self.supervise_once()
                await self.check_solitude()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Discord supervision failed: {e}")
            await asyncio.sleep(2)

    # --- transport (what PlatformSkill calls) -------------------------------

    async def send_text(self, channel_id: str, text: str,
                        reply_to: Optional[str] = None) -> bool:
        if reply_to:
            result = await self.transport.reply_message(channel_id, reply_to, text)
            if result.get("ok"):
                return True
            # the message may have been deleted: fall back to a plain send
        return bool((await self.transport.send_message(channel_id, text)).get("ok"))

    async def send_typing(self, channel_id: str) -> None:
        await self.transport.typing(channel_id)

    async def react(self, channel_id: str, message_id: str, emoji: str) -> bool:
        return bool((await self.transport.react_message(channel_id, message_id, emoji)).get("ok"))

    async def send_dm(self, native_id: str, text: str) -> Optional[str]:
        """A discord DM lives in its own channel, so the bot reports which one."""
        result = await self.transport.send_dm(str(native_id), text)
        if not result.get("ok"):
            logger.warning(f"Discord DM to {native_id} failed: {result.get('error')}")
            return None
        return str(result.get("channelId") or native_id)

    # --- senses (bot -> bus) -----------------------------------------------

    def _author(self, user: str, user_id: Optional[str]) -> Author:
        # native_id is the stable discord user id; display_name can change
        return self.build_author(user_id or user, user)

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
            salience=0.9 if is_dm else 0.8,
            meta={**(meta or {}), "user": user, "user_id": user_id,
                  "channel_id": channel_id, "message_id": message_id, "is_dm": is_dm,
                  "conversation_key": self.conversation_key(channel_id)},
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
            "You are connected to Discord.\n"
            "- `speak` is your LIVE VOICE — the voice call and the stream. Use it here.\n"
            "- Text messages people send you are handled in their own thread, one per "
            "channel, while you keep doing whatever you're doing. You don't answer them "
            "from here — you'll find yourself in that conversation on its own.\n"
            "- What you CAN do from here is act first: `discord_send_message` to write in "
            "a channel unprompted, `discord_send_dm` to message someone privately, "
            "`discord_list_voice_channels` to see where people are, `discord_join_voice` "
            "to go hang out, `discord_summon` to call someone in.\n"
            "- When you write, every LINE becomes a separate message with a typing pause "
            "in between. Two short lines beat one paragraph."
        )

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
                "Write a text message in a discord channel (by channel id). Each LINE you "
                "write is sent as its own message, with a typing pause in between — so "
                "write like you text: short lines, one thought each.",
                {"type": "object", "properties": {
                    "channel_id": {"type": "string"}, "text": {"type": "string"}},
                 "required": ["channel_id", "text"]},
                self._tool_send_message,
            ),
            Tool(
                "discord_reply",
                "Reply to a specific discord message (by channel id + message id). Each LINE "
                "is sent as its own message; only the first one quotes theirs.",
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
        result = await self.transport.join_voice(channel_id)
        if result.get("ok"):
            self.voice_channel = str(channel_id)
            self._alone_since = None
        return self._fmt(result, f"Joined voice channel {channel_id}.")

    async def _tool_leave_voice(self) -> str:
        result = await self.transport.leave_voice()
        self._forget_call()
        return self._fmt(result, "Left the voice channel.")

    async def _tool_send_message(self, channel_id: str, text: str) -> str:
        sent = await self.deliver(channel_id, text)
        return f"Sent ({len(sent)} message(s))." if sent else "FAILED: nothing was sent."

    async def _tool_reply(self, channel_id: str, message_id: str, text: str) -> str:
        sent = await self.deliver(channel_id, text, reply_to=message_id)
        return f"Replied ({len(sent)} message(s))." if sent else "FAILED: nothing was sent."

    async def _tool_react(self, channel_id: str, message_id: str, emoji: str) -> str:
        return self._fmt(await self.transport.react_message(channel_id, message_id, emoji), "Reacted.")

    async def _tool_send_dm(self, user_id: str, text: str) -> str:
        return self._fmt(await self.transport.send_dm(user_id, text), "DM sent.")

    async def _tool_summon(self, user_id: str, channel_id: str, text: str = "") -> str:
        return self._fmt(await self.transport.summon(user_id, channel_id, text or None),
                         f"Summoned user {user_id} to {channel_id}.")

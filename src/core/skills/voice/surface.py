import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from src.core.agent.tools import Tool
from src.core.events import EventCategory
from src.core.floor import FloorController
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.platform import PlatformSkill
from src.core.skills.voice.channel import VoiceChannel
from src.core.skills.voice.latency import TRANSPORT, VoiceLatency
from src.core.skills.voice.transport import DiscordTransport
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice")

# how much quieter someone she has not been introduced to arrives
STRANGER_DAMPING = 0.55


class VoiceSurface(PlatformSkill):
    """Discord capability (voice + text). Owns the bot transport (node subprocess).

    Input: voice transcripts and text messages arrive via the HTTP endpoints the
    bot calls -> perceive() / perceive_text(), and land on the bus as perceptions.
    Output: Bea acts on discord through tools() (join/leave/send/reply/dm/...) and
    her voice reaches the call through the push channel (Expression route='call'),
    whenever she decides to speak rather than only when asked.
    """

    name = "voice:discord"
    skill_name = "discord"
    platform = "discord"

    # how long to wait before bringing a crashed bot back up
    restart_backoff: float = 3.0

    # a bot that never gets as far as logging in is not crashing, it is refusing
    # to run: a bad token is the usual reason, and no number of restarts will
    # change that. Restarting it forever buried the one line that said why under
    # a stack trace every three seconds.
    healthy_after: float = 20.0
    max_failed_starts: int = 3

    # how the supervisor tells "it crashed" apart from "it never ran". Class
    # attributes, so a surface is supervisable before it has been initialized.
    _started_at: float = 0.0
    _failed_starts: int = 0

    def initialize(self) -> None:
        super().initialize()
        self.transport = DiscordTransport(self.config)
        self._monitor: Optional[asyncio.Task] = None
        self.voice_channel: Optional[str] = None
        self._alone_since: Optional[float] = None
        self.latency = VoiceLatency(events=getattr(self.context, "event_manager", None))

        # the push channel is the audio out; Expression owns it as a sink so that
        # nothing else in the codebase can put sound in a room
        self.channel = VoiceChannel()
        self.channel.on_call_change = self._on_call_change
        self.channel.on_first_sound = self._on_first_sound
        if self.expression is not None:
            self.expression.set_call(self.channel)

        # the reflex: it decides when the door opens, never what comes through it
        self.floor = FloorController(
            config=self.config, bus=self.bus, channel=self.channel,
            expression=self.expression, surface_name=self.name,
            events=getattr(self.context, "event_manager", None),
        )
        self._floor_task: Optional[asyncio.Task] = None

    def _on_first_sound(self) -> None:
        """Sound actually reached the room: that, and not the send, ends the clock."""
        self.latency.mark(TRANSPORT)
        self.latency.close()

    def _on_call_change(self, channel_id: Optional[str], listeners: int) -> None:
        """The bot is the authority: she can be dragged into a call, or out of one."""
        self.voice_channel = channel_id
        if channel_id is None:
            self._alone_since = None
        if self.expression is not None:
            # sitting in a call is the one moment she is plainly listening rather
            # than idle, and it is where her face should say so between lines
            self.expression.set_state("listening" if channel_id else "idle")

    async def start(self) -> None:
        if not self.enabled:
            logger.info("VoiceSurface inactive (discord skill disabled).")
            return
        if self.transport.start():
            self.active = True
            self._started_at = time.time()
            self._failed_starts = 0
            self._monitor = asyncio.create_task(self._watch_transport())
            self._floor_task = asyncio.create_task(self._watch_floor())
            logger.info("VoiceSurface started.")

    @property
    def in_call(self) -> bool:
        """Connected to the bot and sitting in a channel: she can be heard."""
        return self.channel.live

    async def stop(self) -> None:
        self.active = False
        self.channel.detach()
        # both are set in `initialize`, so there is nothing here `getattr` was
        # protecting against — and reading them straight says what they are
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None
        if self._floor_task is not None:
            self._floor_task.cancel()
            self._floor_task = None
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

        # it ran long enough to have been working: whatever killed it now is not
        # the reason it would not start, so the count starts again
        if time.time() - self._started_at >= self.healthy_after:
            self._failed_starts = 0
        self._failed_starts += 1

        if self._failed_starts > self.max_failed_starts:
            self._give_up()
            return

        logger.warning(f"Discord bot died; restarting it "
                       f"({self._failed_starts}/{self.max_failed_starts}).")
        await asyncio.sleep(self.restart_backoff)
        if self.transport.start():
            self._started_at = time.time()
            logger.info("Discord bot is back up.")
            return
        logger.error("Discord bot could not be restarted; the capability is off.")
        self.active = False

    def _give_up(self) -> None:
        """Says the thing the restart loop was drowning out, once, and stops."""
        reason = ("The discord bot has quit immediately every time it was started. "
                  "Its own output above says why — an invalid DISCORD_TOKEN is the "
                  "usual answer. Discord is off until that is fixed.")
        logger.error(reason)
        events = getattr(self.context, "event_manager", None)
        if events is not None:
            events.publish(EventCategory.ERROR, "discord", reason)
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

    async def _watch_floor(self) -> None:
        """Ticks on a clock of seconds, not of turns.

        Its own task, and a fast one: the supervision loop polls the bot over
        HTTP, and a silence measured in seconds cannot be watched at that price.
        """
        while self.active:
            try:
                self.floor.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Floor tick failed: {e}")
            await asyncio.sleep(0.5)

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
                 user_id: Optional[str] = None, whitelisted: bool = True,
                 listeners: Optional[int] = None) -> Perception:
        # `listeners` is how many humans are in the call with her. At one, every
        # word is said to her and the gate can stop rolling dice — the rule has
        # always been in attention/rules.py, nobody was ever setting the flag
        extra: Dict[str, Any] = {}
        if listeners is not None:
            extra["listeners"] = listeners
            extra["alone_with_speaker"] = listeners <= 1
        p = Perception(
            kind=PerceptionKind.VOICE,
            surface=self.name,
            content=f"[{user}] (voice): {transcript}",
            # same reasoning as the text path: a stranger in the room is heard,
            # just not loudly enough to pull her out of what she is doing
            salience=0.85 * (1.0 if whitelisted else STRANGER_DAMPING),
            meta={**(meta or {}), "user": user, "user_id": user_id,
                  "whitelisted": whitelisted, **extra},
            author=self._author(user, user_id),
        )
        self.floor.heard()
        self.bus.put(p)
        return p

    def perceive_text(self, text: str, *, author: Author, channel_id: Any,
                      message_id: Optional[str] = None, is_dm: bool = False,
                      mentions_self: bool = False, reply_to_self: bool = False,
                      salience: Optional[float] = None,
                      meta: Optional[Dict[str, Any]] = None) -> Perception:
        """Discord text, shaped the way discord text has to be.

        Same contract as every other platform — it took a different one for a
        long time, which meant nothing could hand a message to whichever surface
        it came from. What is discord's own is the body: the ids go *into the
        sentence* rather than only into the metadata, because acting on a
        message here means naming its channel back to a tool, and a stranger
        arrives quieter than someone she knows.
        """
        whitelisted = bool((meta or {}).get("whitelisted", True))
        kind = "dm" if is_dm else "text"
        route = f"channel_id={channel_id}"
        if message_id:
            route += f", message_id={message_id}"

        if salience is None:
            # a stranger is heard, just not loudly: she notices them without
            # them interrupting whatever she is doing. That is what lets the
            # roster promote someone over time instead of never seeing them
            salience = (0.9 if is_dm else 0.8) * (1.0 if whitelisted else STRANGER_DAMPING)

        p = Perception(
            kind=PerceptionKind.CHAT,
            surface=self.name,
            content=f"[{author.display_name}] (discord {kind}, {route}): {text}",
            salience=salience,
            meta={**(meta or {}), "user": author.display_name,
                  "user_id": author.native_id,
                  "channel_id": str(channel_id), "message_id": message_id,
                  "is_dm": is_dm, "mentions_self": mentions_self,
                  "reply_to_self": reply_to_self, "whitelisted": whitelisted,
                  "conversation_key": self.conversation_key(channel_id)},
            author=author,
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
            + (
                "- You are in a voice call right now. `discord_leave_voice` walks out of "
                "it, and that is yours to decide: you do not have to ask, and nobody has "
                "to dismiss you. Leave when you are bored, when you have had enough, or "
                "when you want to go do something else — say goodbye first if it would "
                "be rude not to.\n"
                if self.voice_channel else ""
            )
            + "- When you write, every LINE becomes a separate message with a typing pause "
            "in between. Two short lines beat one paragraph."
        )

    # --- tools (brain -> bot) ----------------------------------------------

    def tools(self) -> List[Tool]:
        if not self.active:
            return []
        tools = [
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

        # only while she is actually in one: an absent tool is a stronger
        # guarantee than a rule in the prompt, and it also stops her being
        # offered a door she is not standing at
        if self.voice_channel:
            tools.append(Tool(
                "discord_leave_voice",
                "Leave the voice call you are in. Yours to decide — you do not need "
                "anyone's permission and you do not owe an explanation. Say goodbye "
                "first if it would be rude not to.",
                {"type": "object", "properties": {
                    "reason": {"type": "string",
                               "description": "optional: why, for your own record"}},
                 "required": []},
                self._tool_leave_voice,
            ))
        return tools

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

    async def _tool_leave_voice(self, reason: str = "") -> str:
        result = await self.transport.leave_voice()
        if not result.get("ok"):
            # she is still in it: forgetting the channel here would leave her
            # sitting in a call she believes she walked out of
            return self._fmt(result, "")
        reason = (reason or "").strip()
        self._announce_departure(reason)
        self._forget_call()
        return f"Left the call — {reason}." if reason else "Left the call."

    def _announce_departure(self, reason: str) -> None:
        events = getattr(self, "events", None) or getattr(self.context, "event_manager", None)
        if events is None:
            return
        try:
            events.publish(
                EventCategory.SYSTEM, self.name,
                f"left the voice call{f' — {reason}' if reason else ''}",
                metadata={"reason": reason},
            )
        except Exception as e:
            logger.debug(f"Could not publish the departure: {e}")

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

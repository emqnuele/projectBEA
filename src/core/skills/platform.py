"""What every text platform has in common, so it is written once.

Discord, Telegram and Twitch differ in their transport and almost nothing else:
each one turns an incoming message into a `Perception` with a correct `Author`,
and sends text back out through the humanizer. Everything above that — the
roster, the person cards, the attention gate, the scoped conversation turns — is
keyed on `Author` and `conversation_key`, so it works on a new platform the
moment those two are built correctly.

A subclass owes three things: `platform`, a way to build an `Author`, and a way
to actually send text.
"""

from typing import Any, Dict, List, Optional

from src.core.agent.tools import Tool
from src.core.expression.humanizer import TextHumanizer
from src.core.mind.routing import STAGE
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import Skill
from src.utils.logger import get_logger

logger = get_logger("bea.skills.platform")


class PlatformSkill(Skill):
    """Base for a text platform Bea can read and write."""

    platform: str = "platform"

    # Does a channel here deserve its own conversation thread, or does it belong
    # to the stage? A Discord channel is an asynchronous exchange with a few
    # people — its own thread. A twitch chat is the audience standing in the same
    # room as her voice: she answers it out loud, so it stays on the stage.
    scoped_conversations: bool = True

    def initialize(self) -> None:
        self.humanizer = TextHumanizer()

    # --- identity -----------------------------------------------------------

    def build_author(self, native_id: Any, display_name: str, *,
                     is_owner: bool = False, **extra) -> Author:
        """The stable identity behind a message.

        `native_id` is the account id, never the display name: names change, and
        a roster keyed on them would merge two people or split one.
        """
        return Author(
            platform=self.platform,
            native_id=str(native_id),
            display_name=display_name or str(native_id),
            is_owner=is_owner,
            extra=extra,
        )

    def conversation_key(self, channel_id: Any) -> str:
        return f"{self.platform}:{channel_id}" if self.scoped_conversations else STAGE

    # --- perceiving ---------------------------------------------------------

    def perceive_text(self, text: str, *, author: Author, channel_id: Any,
                      message_id: Optional[str] = None, is_dm: bool = False,
                      mentions_self: bool = False, reply_to_self: bool = False,
                      salience: Optional[float] = None,
                      meta: Optional[Dict[str, Any]] = None) -> Perception:
        """Puts one incoming message on the bus.

        The flags matter more than they look: `is_dm`, `mentions_self` and
        `reply_to_self` are what `is_addressed` reads to decide, deterministically,
        that this message is *for her* — and being addressed is the one thing that
        bypasses cooldowns and quiet hours.
        """
        perception = Perception(
            kind=PerceptionKind.CHAT,
            surface=self.name,
            content=f"[{author.display_name}] {text}",
            # a one-to-one message pulls harder than a line in a busy room
            salience=(0.9 if is_dm else 0.8) if salience is None else salience,
            meta={
                **(meta or {}),
                "channel_id": str(channel_id),
                "message_id": str(message_id) if message_id else None,
                "is_dm": is_dm,
                "mentions_self": mentions_self,
                "reply_to_self": reply_to_self,
                "conversation_key": self.conversation_key(channel_id),
            },
            author=author,
        )
        self.bus.put(perception)
        return perception

    # --- sending ------------------------------------------------------------

    async def send_text(self, channel_id: str, text: str,
                        reply_to: Optional[str] = None) -> bool:
        """Sends ONE message. Subclasses implement the transport. Returns success."""
        raise NotImplementedError

    async def send_typing(self, channel_id: str) -> None:
        """Shows "is typing". Cosmetic: a failure here must never lose a message."""

    async def deliver(self, channel_id: str, text: str,
                      reply_to: Optional[str] = None) -> List[str]:
        """Writes the way a person does: line by line, with typing in between.

        Returns what actually went out — history must record what was sent, not
        what was generated.
        """
        first = {"done": False}

        async def send(chunk: str) -> None:
            target = reply_to if reply_to and not first["done"] else None
            first["done"] = True
            if not await self.send_text(channel_id, chunk, reply_to=target):
                raise RuntimeError("send failed")

        async def typing() -> None:
            await self.send_typing(channel_id)

        return await self.humanizer.deliver(text, send_text=send, send_typing=typing)

    async def emit_text(self, text: str, meta: Optional[Dict[str, Any]] = None) -> List[str]:
        meta = meta or {}
        channel_id = meta.get("channel_id")
        if not channel_id:
            return []
        return await self.deliver(str(channel_id), text, reply_to=meta.get("message_id"))

    # --- scoped conversation tools ------------------------------------------

    def conversation_tools(self, channel_id: Optional[str],
                           reply_to: Optional[str] = None) -> List[Tool]:
        """`reply`, `send_message`, `react` — with the ids already bound.

        No `speak` and no body actions here, by construction: inside a written
        conversation those are not hers to use, and an absent tool is a stronger
        guarantee than a rule in the prompt.
        """
        if not self.active or not channel_id:
            return []

        tools = [Tool(
            "send_message",
            "Write in this conversation. Each LINE becomes its own message, with a "
            "typing pause in between — write like you text.",
            {"type": "object", "properties": {"text": {"type": "string"}},
             "required": ["text"]},
            lambda text: self._tool_send(channel_id, text),
        )]
        if reply_to:
            tools.insert(0, Tool(
                "reply",
                "Answer the last message directly (it gets quoted). Each LINE becomes "
                "its own message; only the first one quotes theirs.",
                {"type": "object", "properties": {"text": {"type": "string"}},
                 "required": ["text"]},
                lambda text: self._tool_send(channel_id, text, reply_to=reply_to),
            ))
            if self.supports_reactions:
                tools.append(Tool(
                    "react",
                    "React to the last message with a single emoji, instead of writing.",
                    {"type": "object", "properties": {"emoji": {"type": "string"}},
                     "required": ["emoji"]},
                    lambda emoji: self._tool_react(channel_id, reply_to, emoji),
                ))
        return tools

    supports_reactions: bool = True

    async def _tool_send(self, channel_id: str, text: str,
                         reply_to: Optional[str] = None) -> str:
        sent = await self.deliver(channel_id, text, reply_to=reply_to)
        return f"Sent ({len(sent)} message(s))." if sent else "FAILED: nothing was sent."

    async def _tool_react(self, channel_id: str, message_id: str, emoji: str) -> str:
        ok = await self.react(channel_id, message_id, emoji)
        return "Reacted." if ok else "FAILED: could not react."

    async def react(self, channel_id: str, message_id: str, emoji: str) -> bool:
        return False

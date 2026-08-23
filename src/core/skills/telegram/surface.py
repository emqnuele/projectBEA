"""Telegram, in-process.

Unlike Discord — which needs a node subprocess for voice — Telegram is text only,
so it runs inside the Python process with no second runtime to babysit. That is
also the point of the phase: if `PlatformSkill` is a real abstraction, a whole
new platform is a transport plus an `Author` builder, and everything above it
(roster, person cards, attention, scoped turns) simply works.
"""

import asyncio
from typing import Any, List, Optional

from src.core.perception.types import Author
from src.core.skills.platform import PlatformSkill
from src.core.skills.telegram.handlers import (
    display_name,
    is_bot_called,
    is_private,
    message_text,
)
from src.utils.logger import get_logger

logger = get_logger("bea.skills.telegram")


class TelegramSkill(PlatformSkill):
    """Reads a group or a DM, and writes back through the humanizer."""

    name = "chat:telegram"
    skill_name = "telegram"
    platform = "telegram"
    # telegram reactions exist but are a restricted set; writing is the honest path
    supports_reactions = False

    def initialize(self) -> None:
        super().initialize()
        self.app = None
        self._task: Optional[asyncio.Task] = None
        self._me: Any = None

    @property
    def skill_config(self) -> dict:
        return self.config.skills.get("telegram", {})

    def _token(self) -> str:
        import os
        return os.getenv("TELEGRAM_TOKEN", "") or self.skill_config.get("token", "")

    def _trigger_words(self) -> List[str]:
        return list(getattr(self.config, "attention", {}).get("trigger_words", ["bea"]))

    def _owner_id(self) -> str:
        return str(self.skill_config.get("owner_id", "") or "")

    def _allowed(self, chat_id: Any) -> bool:
        """An empty allowlist means every chat; otherwise only the listed ones."""
        allowed = [str(c) for c in self.skill_config.get("allowed_chats", []) if str(c)]
        return not allowed or str(chat_id) in allowed

    # --- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if not self.enabled:
            logger.info("TelegramSkill stays inactive (telegram toggle off).")
            return
        token = self._token()
        if not token:
            logger.error("Telegram token not configured (set TELEGRAM_TOKEN).")
            return

        try:
            from telegram.ext import Application, MessageHandler, filters
        except ImportError:
            logger.error("python-telegram-bot is not installed; telegram stays off.")
            return

        try:
            # concurrent updates: several chats are read at once, and the
            # per-conversation scheduler is what keeps each one serialized
            self.app = Application.builder().token(token).concurrent_updates(True).build()
            self.app.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND, self._on_message
            ))
            await self.app.initialize()
            await self.app.start()
            self._me = await self.app.bot.get_me()
            await self.app.updater.start_polling(drop_pending_updates=True)
        except Exception as e:
            logger.error(f"Telegram failed to start: {e}")
            await self._shutdown()
            return

        self.active = True
        logger.info(f"TelegramSkill started as @{getattr(self._me, 'username', '?')}.")

    async def stop(self) -> None:
        self.active = False
        await self._shutdown()
        logger.info("TelegramSkill stopped.")

    async def _shutdown(self) -> None:
        if self.app is None:
            return
        try:
            if self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        except Exception as e:
            logger.error(f"Error stopping telegram: {e}")
        finally:
            self.app = None

    # --- senses -------------------------------------------------------------

    async def _on_message(self, update, context) -> None:
        """Extract, build the author, deposit. No decision is made here."""
        try:
            message = getattr(update, "message", None)
            if message is None:
                return
            text = message_text(message)
            if not text:
                return

            chat_id = message.chat.id
            if not self._allowed(chat_id):
                return

            user = getattr(message, "from_user", None)
            if user is None or getattr(user, "is_bot", False):
                return

            reply = getattr(message, "reply_to_message", None)
            reply_user_id = getattr(getattr(reply, "from_user", None), "id", None)
            bot_id = getattr(self._me, "id", None)

            private = is_private(message)
            called = is_bot_called(
                text,
                bot_username=getattr(self._me, "username", "") or "",
                bot_id=bot_id,
                reply_to_user_id=reply_user_id,
                trigger_words=self._trigger_words(),
            )

            self.perceive_text(
                text,
                author=self._author(user),
                channel_id=chat_id,
                message_id=message.message_id,
                is_dm=private,
                mentions_self=called,
                reply_to_self=bool(bot_id is not None and reply_user_id == bot_id),
                meta={"chat_title": getattr(message.chat, "title", "") or ""},
            )
        except Exception as e:
            # an handler must never take the bot down
            logger.error(f"Telegram message handling failed: {e}")

    def _author(self, user) -> Author:
        owner = self._owner_id()
        return self.build_author(
            user.id, display_name(user),
            is_owner=bool(owner and str(user.id) == owner),
            username=getattr(user, "username", "") or "",
        )

    # --- transport ----------------------------------------------------------

    async def send_text(self, channel_id: str, text: str,
                        reply_to: Optional[str] = None) -> bool:
        if self.app is None:
            return False
        try:
            await self.app.bot.send_message(
                chat_id=int(channel_id), text=text,
                reply_to_message_id=int(reply_to) if reply_to else None,
            )
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def send_typing(self, channel_id: str) -> None:
        if self.app is None:
            return
        try:
            await self.app.bot.send_chat_action(chat_id=int(channel_id), action="typing")
        except Exception as e:
            logger.debug(f"Telegram typing failed: {e}")

    # --- prompt context -----------------------------------------------------

    @property
    def context_section(self) -> Optional[str]:
        if not self.active:
            return None
        return (
            "## TELEGRAM\n"
            "You are on Telegram. Messages people send you are handled in their own "
            "thread, one per chat, while you keep doing whatever you're doing — you "
            "don't answer them from here.\n"
            "- `telegram_send_message` writes in a chat unprompted, if you feel like "
            "saying something first."
        )

    def tools(self) -> List:
        from src.core.agent.tools import Tool
        if not self.active:
            return []
        return [Tool(
            "telegram_send_message",
            "Write in a telegram chat on your own initiative (by chat id). Each LINE "
            "becomes its own message.",
            {"type": "object", "properties": {
                "chat_id": {"type": "string"}, "text": {"type": "string"}},
             "required": ["chat_id", "text"]},
            self._tool_send_message,
        )]

    async def _tool_send_message(self, chat_id: str, text: str) -> str:
        sent = await self.deliver(str(chat_id), text)
        return f"Sent ({len(sent)} message(s))." if sent else "FAILED: nothing was sent."

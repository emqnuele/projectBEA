"""Twitch IRC over asyncio, by hand: the protocol we need is a dozen lines.

Read-only works anonymously (`justinfan<random>`, no password); a token is only
needed to write back. The parsing half is pure; the connection half reconnects
and answers PINGs.
"""

import asyncio
import random
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger("bea.skills.twitch.irc")

HOST = "irc.chat.twitch.tv"
PORT = 6697  # tls

# tags carry the one thing that matters: user-id, the stable identity. Without
# them a display name is all we would have, and names are not identities.
CAPABILITIES = "twitch.tv/tags twitch.tv/commands"

_LINE_RE = re.compile(
    r"^(?:@(?P<tags>[^ ]*) )?"          # optional IRCv3 tags
    r":(?P<nick>[^!]+)![^ ]+ "          # nick!user@host
    r"PRIVMSG #(?P<channel>[^ ]+) "
    r":(?P<message>.*)$"
)

# subs, resubs, gifts and raids all arrive here, not as PRIVMSG. The parser used
# to see only PRIVMSG, which meant a raid — the biggest moment of a stream —
# never reached her at all.
_NOTICE_RE = re.compile(
    r"^@(?P<tags>[^ ]*) :tmi\.twitch\.tv USERNOTICE #(?P<channel>[^ ]+)"
    r"(?: :(?P<message>.*))?$"
)

# the msg-id values worth waking her for; everything else is chrome
EVENT_KINDS = frozenset({
    "sub", "resub", "subgift", "submysterygift", "raid", "announcement",
})

# what one sub is worth, so a gift lands on the same scale as a donation
SUB_UNITS = {"1000": 5.0, "2000": 10.0, "3000": 25.0, "Prime": 5.0}
DEFAULT_SUB_UNITS = 5.0


@dataclass
class ChatLine:
    """One message from twitch chat."""

    nick: str
    channel: str
    text: str
    user_id: str = ""
    display_name: str = ""
    bits: int = 0
    is_moderator: bool = False
    is_subscriber: bool = False
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.display_name or self.nick


def parse_tags(raw: str) -> Dict[str, str]:
    """IRCv3 tags: `key=value;key2=value2`, with escaped separators."""
    out: Dict[str, str] = {}
    for chunk in (raw or "").split(";"):
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        out[key] = (value.replace(r"\s", " ").replace(r"\:", ";")
                    .replace(r"\\", "\\").replace(r"\r", "").replace(r"\n", ""))
    return out


def parse_line(line: str):
    """One raw line into a `ChatLine`, a `ChatEvent`, or None."""
    match = _LINE_RE.match(line.strip())
    if not match:
        return parse_notice(line)
    tags = parse_tags(match.group("tags") or "")
    try:
        bits = int(tags.get("bits", "0") or 0)
    except ValueError:
        bits = 0
    return ChatLine(
        nick=match.group("nick"),
        channel=match.group("channel"),
        text=match.group("message"),
        user_id=tags.get("user-id", ""),
        display_name=tags.get("display-name", ""),
        bits=bits,
        is_moderator=tags.get("mod") == "1",
        is_subscriber=tags.get("subscriber") == "1",
        tags=tags,
    )


@dataclass
class ChatEvent:
    """Something that happened in the channel that is not someone talking."""

    kind: str
    channel: str
    nick: str = ""
    display_name: str = ""
    user_id: str = ""
    text: str = ""
    viewers: int = 0
    months: int = 0
    gifts: int = 0
    recipient: str = ""
    plan: str = ""
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.display_name or self.nick or "someone"

    @property
    def units(self) -> float:
        """Roughly what it is worth, on the same scale as a donation."""
        if self.kind == "raid":
            return 0.0
        each = SUB_UNITS.get(self.plan, DEFAULT_SUB_UNITS)
        return each * max(1, self.gifts)

    def render(self) -> str:
        if self.kind == "raid":
            return f"{self.name} raided with {self.viewers} people"
        if self.kind == "sub":
            line = f"{self.name} just subscribed"
        elif self.kind == "resub":
            line = f"{self.name} resubscribed — {self.months} months now"
        elif self.kind == "subgift":
            line = f"{self.name} gifted a sub to {self.recipient or 'someone'}"
        elif self.kind == "submysterygift":
            line = f"{self.name} gifted {self.gifts} subs to the channel"
        else:
            line = f"{self.name}: announcement"
        return f"{line}: {self.text}" if self.text else line


def _int(tags: Dict[str, str], key: str) -> int:
    try:
        return int(tags.get(key, "0") or 0)
    except ValueError:
        return 0


def parse_notice(line: str) -> Optional[ChatEvent]:
    """A USERNOTICE into a `ChatEvent`, or None for the kinds nobody cares about."""
    match = _NOTICE_RE.match(line.strip())
    if not match:
        return None
    tags = parse_tags(match.group("tags") or "")
    kind = tags.get("msg-id", "")
    if kind not in EVENT_KINDS:
        return None
    return ChatEvent(
        kind=kind,
        channel=match.group("channel"),
        nick=tags.get("login", ""),
        display_name=tags.get("display-name", ""),
        user_id=tags.get("user-id", ""),
        text=(match.group("message") or "").strip(),
        viewers=_int(tags, "msg-param-viewerCount"),
        months=_int(tags, "msg-param-cumulative-months"),
        gifts=_int(tags, "msg-param-mass-gift-count"),
        recipient=tags.get("msg-param-recipient-display-name", ""),
        plan=tags.get("msg-param-sub-plan", ""),
        tags=tags,
    )


class TwitchIRC:
    """Connects, joins a channel, and calls `on_message` for every line."""

    def __init__(self, channel: str, *, nick: str = "", token: str = "",
                 on_message: Optional[Callable[[ChatLine], Awaitable[None]]] = None,
                 on_event: Optional[Callable[["ChatEvent"], Awaitable[None]]] = None):
        self.channel = channel.lstrip("#").lower()
        self.token = token
        # anonymous read-only: no credentials needed to follow a chat
        self.nick = (nick or f"justinfan{random.randint(10000, 99999)}").lower()
        self.on_message = on_message
        self.on_event = on_event
        self.connected = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._close()

    async def _loop(self) -> None:
        backoff = 2.0
        while self._running:
            try:
                await self._connect()
                backoff = 2.0
                await self._read()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Twitch connection lost ({e}); retrying in {backoff:.0f}s.")
            finally:
                await self._close()
            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(HOST, PORT, ssl=True)
        await self._send(f"CAP REQ :{CAPABILITIES}")
        if self.token:
            token = self.token if self.token.startswith("oauth:") else f"oauth:{self.token}"
            await self._send(f"PASS {token}")
        await self._send(f"NICK {self.nick}")
        await self._send(f"JOIN #{self.channel}")
        self.connected = True
        logger.info(f"Twitch: joined #{self.channel} as {self.nick}.")

    async def _read(self) -> None:
        assert self._reader is not None
        while self._running:
            raw = await self._reader.readline()
            if not raw:
                raise ConnectionError("stream closed")
            for line in raw.decode("utf-8", errors="replace").splitlines():
                await self._handle(line)

    async def _handle(self, line: str) -> None:
        if line.startswith("PING"):
            # miss these and twitch drops the connection after a few minutes
            await self._send("PONG :tmi.twitch.tv")
            return
        parsed = parse_line(line)
        if parsed is None:
            return
        handler = self.on_event if isinstance(parsed, ChatEvent) else self.on_message
        if handler is None:
            return
        try:
            await handler(parsed)
        except Exception as e:
            logger.error(f"Twitch handler failed: {e}")

    async def say(self, text: str) -> bool:
        if not self.connected or not self.token:
            return False
        try:
            await self._send(f"PRIVMSG #{self.channel} :{text}")
            return True
        except Exception as e:
            logger.error(f"Twitch send failed: {e}")
            return False

    async def _send(self, line: str) -> None:
        if self._writer is None:
            raise ConnectionError("not connected")
        self._writer.write((line + "\r\n").encode("utf-8"))
        await self._writer.drain()

    async def _close(self) -> None:
        self.connected = False
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = self._writer = None

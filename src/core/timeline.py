"""Where she is in time.

She knew the date and nothing else: no clock, no weekday, no idea whether a
message in her batch had arrived two seconds or forty minutes ago. Meanwhile
the quiet hours were silencing her at 3am off a clock she could not see.

Everything here is pure, so the whole thing is testable against a fixed moment
instead of against whatever time the suite happens to run at.
"""

from datetime import datetime, tzinfo
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("bea.timeline")

# under a minute everything in a batch is "now", and a stamp would be noise on
# every line. It is also the floor that keeps "0 min ago" from ever being said.
STAMP_AFTER_SECONDS = 60.0

# a session shorter than this is not worth telling her about
MENTION_UPTIME_AFTER = 300.0

MINUTE = 60.0
HOUR = 3600.0
DAY = 86400.0


def relative(seconds: float) -> str:
    """How long ago, the way a person would say it."""
    seconds = max(0.0, float(seconds))
    if seconds < STAMP_AFTER_SECONDS:
        return "just now"
    if seconds < HOUR:
        return f"{int(seconds // MINUTE)} min ago"
    if seconds < DAY:
        return f"{int(seconds // HOUR)}h ago"
    days = int(seconds // DAY)
    return "yesterday" if days == 1 else f"{days} days ago"


def stamp_for(age_seconds: float) -> str:
    """The prefix a perception of this age deserves, or nothing."""
    if age_seconds < STAMP_AFTER_SECONDS:
        return ""
    return f"({relative(age_seconds)}) "


def _duration(seconds: float) -> str:
    if seconds < HOUR:
        return f"{int(seconds // MINUTE)} min"
    hours, rest = divmod(int(seconds), int(HOUR))
    minutes = int(rest // MINUTE)
    return f"{hours}h{minutes:02d}" if minutes else f"{hours}h"


def resolve_timezone(name: str) -> Optional[tzinfo]:
    """The named zone, or None for the machine's own clock."""
    name = (name or "").strip()
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception as e:
        logger.warning(f"Unknown timezone {name!r} ({e}); using the system clock.")
        return None


def now_block(
    now: datetime,
    *,
    awake_seconds: Optional[float] = None,
    last_spoke_seconds: Optional[float] = None,
    in_conversation: bool = False,
    timezone: str = "",
) -> str:
    """`[RIGHT NOW]` — the two or three lines that place her in time.

    It goes into every turn, so it stays short: the day and the clock, how long
    she has been up, and when she last spoke where she is.
    """
    stamp = now.strftime("%A %-d %B %Y, %H:%M")
    if timezone:
        stamp += f" ({timezone})"
    lines = ["[RIGHT NOW]", stamp]

    if awake_seconds is not None and awake_seconds >= MENTION_UPTIME_AFTER:
        lines.append(f"You've been up for {_duration(awake_seconds)}.")

    if last_spoke_seconds is not None:
        lines.append(f"You last spoke here {relative(last_spoke_seconds)}.")
    elif in_conversation:
        lines.append("You have not said anything here yet.")

    return "\n".join(lines)

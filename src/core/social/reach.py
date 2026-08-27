"""Reaching a person, wherever they are.

Bea knows people, not channels: one card carries every account someone owns.
This is the other direction — given a person, where can she reach them, and
how does she start the conversation herself. It is what makes "she talked to
you in the call, then messaged you on Telegram" a thing she can decide to do
rather than a thing that only happens when you write first.
"""

from dataclasses import dataclass
from typing import List

from src.utils.logger import get_logger

logger = get_logger("bea.social.reach")


@dataclass(frozen=True)
class Channel:
    """One way to reach one person."""

    platform: str
    native_id: str
    display_name: str
    last_seen: float
    reachable: bool

    @property
    def identity(self) -> str:
        return f"{self.platform}:{self.native_id}"


@dataclass(frozen=True)
class Delivered:
    ok: bool
    error: str = ""
    platform: str = ""
    conversation_key: str = ""


class Reach:
    """The address book, and the act of using it."""

    def __init__(self, *, memory, surfaces=None):
        self.memory = memory
        self.surfaces = surfaces

    # --- finding --------------------------------------------------------

    def find(self, who: str):
        """A person by name, or by one of their `platform:id` handles."""
        who = (who or "").strip()
        if not who:
            return None
        if ":" in who:
            card = self.memory.people.get_by_identity(who)
            if card:
                return card
        return self.memory.people.find_by_name(who)

    # --- where ----------------------------------------------------------

    def _skill_for(self, platform: str):
        if self.surfaces is None:
            return None
        for skill in self.surfaces.active():
            if getattr(skill, "platform", None) == platform:
                return skill
        return None

    def _can_reach(self, platform: str) -> bool:
        skill = self._skill_for(platform)
        return bool(skill and getattr(skill, "supports_dm", False))

    def channels(self, person_id: str) -> List[Channel]:
        """Every account of theirs, most recently seen first."""
        rows = self.memory.db.query(
            "SELECT platform, native_id, display_name, last_seen FROM identities "
            "WHERE person_id = ? ORDER BY last_seen DESC",
            (person_id,),
        )
        return [
            Channel(
                platform=r["platform"], native_id=r["native_id"],
                display_name=r["display_name"], last_seen=r["last_seen"],
                reachable=self._can_reach(r["platform"]),
            )
            for r in rows
        ]

    def describe(self, who: str) -> str:
        """One line per way to reach them, for her own use in a prompt."""
        card = self.find(who)
        if card is None:
            return f"You don't know anyone called '{who}'."
        channels = self.channels(card.person_id)
        if not channels:
            return f"{card.primary_name}: no account on record."
        lines = [
            f"- {c.platform}" + ("" if c.reachable else " (that platform is off right now)")
            for c in channels
        ]
        return f"{card.primary_name}:\n" + "\n".join(lines)

    # --- reaching -------------------------------------------------------

    async def message(self, who: str, text: str, platform: str = "") -> Delivered:
        """Opens a private conversation with them and says something."""
        card = self.find(who)
        if card is None:
            return Delivered(False, f"You don't know anyone called '{who}'.")

        known = self.channels(card.person_id)
        channels = [c for c in known if c.reachable]
        if platform:
            channels = [c for c in channels if c.platform == platform]
        if not channels:
            elsewhere = sorted({c.platform for c in known}) or ["nowhere"]
            where = platform or "any platform that is on"
            return Delivered(
                False,
                f"You can't reach {card.primary_name} on {where} right now "
                f"(you know them on: {', '.join(elsewhere)}).",
            )

        channel = channels[0]
        skill = self._skill_for(channel.platform)
        try:
            conversation_id = await skill.send_dm(channel.native_id, text)
        except Exception as e:
            logger.error(f"Reaching {card.primary_name} on {channel.platform} failed: {e}")
            return Delivered(False, str(e), channel.platform)

        if not conversation_id:
            return Delivered(False, f"The message to {card.primary_name} did not go through.",
                             channel.platform)

        key = f"{channel.platform}:{conversation_id}"
        # her own opening line belongs in that thread, or the reply arrives with
        # no idea what it is answering
        self.memory.conversations.add(
            conversation_key=key, role="bea", content=text,
            platform=channel.platform, channel_id=str(conversation_id),
            display_name="Bea",
        )
        logger.info(f"Bea reached {card.primary_name} on {channel.platform}.")
        return Delivered(True, "", channel.platform, key)

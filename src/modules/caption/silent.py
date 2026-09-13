"""No words on screen at all.

An explicit backend rather than an empty `obs_text_source`: "off" is a choice
someone makes on purpose, and it should read that way in the dashboard instead
of being expressed by blanking a source name.
"""

from src.interfaces.base_interfaces import CaptionInterface


class SilentCaption(CaptionInterface):
    async def say(self, text: str) -> None:
        """She speaks; nothing is written."""

    def clear(self) -> None:
        """Nothing to take away."""

    def reload_config(self, config) -> None:
        """Nothing to reload."""

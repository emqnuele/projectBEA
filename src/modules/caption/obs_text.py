"""The speech bubble, typed character by character into an OBS text source.

The size a line settles at is kept here: a long line shrinks to fit, and
clearing the source at the configured size instead would resize the box on
screen between one line and the next.
"""

from typing import Optional

from src.interfaces.base_interfaces import CaptionInterface, OBSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.caption.obs")


class ObsTextCaption(CaptionInterface):
    """Writes into the OBS text source named by `obs_text_source`."""

    def __init__(self, config, obs: OBSInterface):
        self.config = config
        self.obs = obs
        self._font_size: Optional[int] = None

    def reload_config(self, config) -> None:
        self.config = config

    @property
    def source(self) -> str:
        return self.config.obs_text_source or ""

    async def say(self, text: str) -> None:
        if not self.source:
            return
        self._font_size = await self.obs.type_text(
            text=text,
            source_name=self.source,
            line_width=self.config.text_line_width,
            max_lines=self.config.text_lines,
            base_font_size=self.config.text_font_size,
            min_font_size=self.config.text_min_font_size,
            font_step=self.config.text_font_step,
            typing_delay=self.config.typing_delay,
            min_page_duration=self.config.text_min_duration,
        )

    def clear(self) -> None:
        if not self.source:
            return
        # the size it was actually typed at, not the configured one: a long line
        # shrinks to fit, and clearing at the base size resizes the box on screen
        self.obs.set_text("", self.source, font_size=self._font_size)

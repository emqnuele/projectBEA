"""Her words, typed in the browser source instead of in OBS.

The OBS backend sends one WebSocket request per character — 159 of them, and
29.7 KB of JSON, for a 158-character line, because each one re-sends the whole
font block. Here the line crosses the wire once and the page animates it.
"""

import uuid

from src.core.stage import StageChannel
from src.interfaces.base_interfaces import CaptionInterface
from src.utils.logger import get_logger

logger = get_logger("bea.caption.stage")


class StageCaption(CaptionInterface):
    def __init__(self, config, channel: StageChannel):
        self.config = config
        self.channel = channel

    def reload_config(self, config) -> None:
        self.config = config

    async def say(self, text: str) -> None:
        # an id per line so a page that reconnects mid-sentence can tell a line
        # it has already typed from a new one it has not
        self.channel.publish({"caption": text, "caption_id": uuid.uuid4().hex})

    def clear(self) -> None:
        self.channel.publish({"caption": "", "caption_id": ""})

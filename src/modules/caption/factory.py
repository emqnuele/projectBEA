"""The one place that knows how to build a caption backend."""

from src.interfaces.base_interfaces import CaptionInterface, OBSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.caption.factory")

DEFAULT_BACKEND = "obs"


def build_caption(config, obs: OBSInterface) -> CaptionInterface:
    """The caption described by `stage.caption_backend`."""
    from src.modules.caption.obs_text import ObsTextCaption

    return ObsTextCaption(config, obs)

"""The one place that knows how to build a caption backend."""

from typing import Callable, Dict

from src.interfaces.base_interfaces import CaptionInterface, OBSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.caption.factory")

DEFAULT_BACKEND = "obs"


def _obs(config, obs, publisher):
    from src.modules.caption.obs_text import ObsTextCaption
    return ObsTextCaption(config, obs)


def _off(config, obs, publisher):
    from src.modules.caption.silent import SilentCaption
    return SilentCaption()


BUILDERS: Dict[str, Callable[..., CaptionInterface]] = {
    "obs": _obs,
    "off": _off,
}


def backend_name(config) -> str:
    """The configured backend, or the default when it is not one we have."""
    name = (getattr(config, "stage", None) or {}).get("caption_backend", DEFAULT_BACKEND)
    if name in BUILDERS:
        return name
    logger.warning(
        f"Unknown caption backend {name!r}; falling back to {DEFAULT_BACKEND!r}. "
        f"Valid: {', '.join(sorted(BUILDERS))}."
    )
    return DEFAULT_BACKEND


def build_caption(config, obs: OBSInterface, publisher=None) -> CaptionInterface:
    """The caption described by `stage.caption_backend`."""
    name = backend_name(config)
    caption = BUILDERS[name](config, obs, publisher)
    logger.info(f"Caption backend: {name}")
    return caption

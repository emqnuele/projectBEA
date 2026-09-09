"""The one place that knows how to build an avatar backend.

Same shape as `llm/factory.py`: the engine asks for a backend by name and never
imports a concrete one, so adding a way for Bea to have a body is a branch here
and nothing else.
"""

from src.interfaces.base_interfaces import AvatarInterface, OBSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.avatar.factory")

DEFAULT_BACKEND = "png"


def build_avatar(config, obs: OBSInterface) -> AvatarInterface:
    """The avatar described by `stage.avatar_backend`."""
    from src.modules.avatar.png import PngAvatar

    return PngAvatar(config, obs)

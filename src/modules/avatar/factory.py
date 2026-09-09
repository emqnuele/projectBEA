"""The one place that knows how to build an avatar backend.

Same shape as `llm/factory.py`: the engine asks for a backend by name and never
imports a concrete one, so giving Bea a new kind of body is a branch here and
nothing else.
"""

from typing import Callable, Dict

from src.interfaces.base_interfaces import AvatarInterface, OBSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.avatar.factory")

DEFAULT_BACKEND = "png"


def _png(config, obs, publisher):
    from src.modules.avatar.png import PngAvatar
    return PngAvatar(config, obs)


def _model(config, obs, publisher):
    from src.modules.avatar.model3d import Model3DAvatar
    return Model3DAvatar(config, publisher)


# name -> builder. Imports live inside the builders so that choosing the PNG
# backend never pays for the ones it is not using.
BUILDERS: Dict[str, Callable[..., AvatarInterface]] = {
    "png": _png,
    "model": _model,
}

# backends that cannot work without somewhere to publish to
NEEDS_PUBLISHER = frozenset({"model"})


def backend_name(config) -> str:
    """The configured backend, or the default when it is not one we have."""
    name = (getattr(config, "stage", None) or {}).get("avatar_backend", DEFAULT_BACKEND)
    if name in BUILDERS:
        return name
    # a typo in config.json must not leave her invisible for a whole stream
    logger.warning(
        f"Unknown avatar backend {name!r}; falling back to {DEFAULT_BACKEND!r}. "
        f"Valid: {', '.join(sorted(BUILDERS))}."
    )
    return DEFAULT_BACKEND


def build_avatar(config, obs: OBSInterface, publisher=None) -> AvatarInterface:
    """The avatar described by `stage.avatar_backend`.

    `publisher` is how a backend reaches the browser source; the backends that
    do not need one ignore it.
    """
    name = backend_name(config)
    if name in NEEDS_PUBLISHER and publisher is None:
        logger.warning(f"The {name!r} avatar needs a stage channel; using {DEFAULT_BACKEND!r}.")
        name = DEFAULT_BACKEND
    avatar = BUILDERS[name](config, obs, publisher)
    logger.info(f"Avatar backend: {name}")
    return avatar

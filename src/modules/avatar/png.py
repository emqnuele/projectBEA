"""One image per mood, swapped in an OBS source.

The only place that knows whether the scene holds an image source or a media
source, so nothing above the port has to ask.
"""

from pathlib import Path
from typing import Dict, Sequence, Tuple, Union

from src.core.mind.moods import DEFAULT_MOOD
from src.core.resources import load_avatar_resources, resolve_mood_paths
from src.interfaces.base_interfaces import AvatarInterface, OBSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.avatar.png")

# states that are not speech and deserve a picture of their own if one exists
_STATE_SLOTS = ("sleeping", "listening")


class PngAvatar(AvatarInterface):
    """One idle image and one talking image per mood, swapped in an OBS source."""

    def __init__(self, config, obs: OBSInterface):
        self.obs = obs
        self.config = config
        self.png_map: Dict[str, Tuple[Path, Path]] = {}
        self._warned: set = set()
        self._load()

    def _load(self) -> None:
        self.png_map = load_avatar_resources(self.config.avatar_map)
        if not self.png_map:
            logger.warning("No avatar resources loaded from avatar_map.")

    def reload_config(self, config) -> None:
        self.config = config
        self._load()

    # --- the port -----------------------------------------------------------

    def show(self, mood: str, state: str) -> None:
        # a state gets a slot of its own rather than resolving to a mood's image
        if state in _STATE_SLOTS:
            slot = self.png_map.get(state)
            if slot:
                self._swap(slot[0])
                return
            self._warn_once(state)

        idle, talking = self._paths(mood)
        self._swap(talking if state == "talking" else idle)

    def perform(self, clip: str) -> None:
        """A still image has no behaviours."""

    def mouth(self, envelope: Sequence[float], fps: int) -> None:
        """A still image has no mouth: the talking frame already stands in for it."""

    def close(self) -> None:
        """Takes her picture down. It is the only thing this backend holds.

        The OBS client belongs to the brain, but the image left in the source
        does not: another backend taking over mid-stream, or the engine stopping,
        would otherwise leave a face on screen with nothing behind it.
        """
        self._swap("")

    # --- internals ----------------------------------------------------------

    def _paths(self, mood: str) -> Tuple[Path, Path]:
        try:
            return resolve_mood_paths(self.png_map, mood)
        except KeyError:
            logger.warning(f"Could not resolve mood {mood}, falling back to '{DEFAULT_MOOD}'.")
            return self.png_map.get(DEFAULT_MOOD, (Path("placeholder.png"), Path("placeholder.png")))

    def _swap(self, path: Union[str, Path]) -> None:
        if self.config.obs_source_type == "media":
            self.obs.set_media(path)
        else:
            self.obs.set_image(path)

    def _warn_once(self, state: str) -> None:
        if state in self._warned:
            return
        self._warned.add(state)
        logger.warning(
            f"No avatar image for the '{state}' state; showing the mood image instead. "
            f"Add a '{state}' entry to avatar_map to give it its own picture."
        )

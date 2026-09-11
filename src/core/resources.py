from pathlib import Path
from typing import Dict, Tuple

from src.core.mind.moods import DEFAULT_MOOD
from src.utils.logger import get_logger

logger = get_logger("bea.resources")

def load_avatar_resources(avatar_map: Dict[str, Dict[str, str]]) -> Dict[str, Tuple[Path, Path]]:
    """The configured avatar images, checked, as mood -> (idle, talking).

    A mood missing either path declaration is dropped. A *file* that is not on
    disk is kept with a warning and falls back later (see `resolve_mood_paths`):
    deleting a png mid-stream must not be the thing that blanks the mood it had.
    """
    processed_map: Dict[str, Tuple[Path, Path]] = {}

    for mood, paths in avatar_map.items():
        idle_str = paths.get("idle")
        talking_str = paths.get("talking")

        if not idle_str or not talking_str:
            logger.warning(f"Mood '{mood}' incomplete. Missing 'idle' or 'talking' path.")
            continue

        idle_path = Path(idle_str).resolve()
        talking_path = Path(talking_str).resolve()

        # warning if not found
        if not idle_path.exists():
            logger.warning(f"Idle image for mood '{mood}' not found at: {idle_path}")
        if not talking_path.exists():
             logger.warning(f"Talking image for mood '{mood}' not found at: {talking_path}")

        processed_map[mood] = (idle_path, talking_path)

    return processed_map

def resolve_mood_paths(png_map: Dict[str, Tuple[Path, Path]], mood: str) -> Tuple[Path, Path]:
    """The pair of images for a mood, falling back rather than raising."""
    # 1. exact match
    if mood in png_map:
        return png_map[mood]

    # 2. fallback al default
    if DEFAULT_MOOD in png_map:
        return png_map[DEFAULT_MOOD]

    # 3. fallback any
    if png_map:
        return next(iter(png_map.values()))

    # 4. last resort
    return (Path("placeholder_idle.png"), Path("placeholder_talking.png"))

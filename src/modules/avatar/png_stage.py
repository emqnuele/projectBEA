"""The PNG avatar, drawn by the browser source instead of swapped in OBS.

Same pictures, same `avatar_map`, but nothing crosses the OBS socket: the page
is told which pictures belong to the face she is wearing and flaps the mouth
from the envelope the 3D body already gets. A mood may add two optional
pictures, `talking_closed` (the mouth shut mid-sentence) and `blink`.

What is published is keys (`mood/slot`), never paths: the page fetches them
through `/stage/preview`, which only serves what `avatar_map` names.
"""

from typing import Dict, Optional

from src.core.expression.pcm import ENVELOPE_FPS
from src.core.mind.moods import DEFAULT_MOOD
from src.core.stage import StageChannel
from src.interfaces.base_interfaces import AvatarInterface, MouthFrames

# states that are not speech and deserve a picture of their own if one exists
STATE_SLOTS = ("sleeping", "listening")


def _complete(avatar_map: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    # the obs backend drops a mood without both pictures; the page follows the same rule
    return {mood: slots for mood, slots in (avatar_map or {}).items()
            if (slots or {}).get("idle") and (slots or {}).get("talking")}


def frames_for(avatar_map: Dict[str, Dict[str, str]], mood: str, state: str) -> Optional[Dict[str, Optional[str]]]:
    """The picture keys for one face: at rest, mouth open, mouth shut, blinking."""
    moods = _complete(avatar_map)
    name = mood if mood in moods else DEFAULT_MOOD if DEFAULT_MOOD in moods else next(iter(moods), None)
    if name is None:
        return None
    slots = moods[name]
    idle = f"{name}/idle"
    rest = idle
    if state in STATE_SLOTS and ((avatar_map or {}).get(state) or {}).get("idle"):
        rest = f"{state}/idle"
    return {
        "rest": rest,
        "open": f"{name}/talking",
        "closed": f"{name}/talking_closed" if slots.get("talking_closed") else idle,
        "blink": f"{name}/blink" if slots.get("blink") and state != "sleeping" else None,
    }


class PngStageAvatar(AvatarInterface):
    """Publishes which pictures she is wearing; the browser source draws them."""

    def __init__(self, config, channel: StageChannel):
        self.config = config
        self.channel = channel

    def reload_config(self, config) -> None:
        self.config = config

    def show(self, mood: str, state: str) -> None:
        self.channel.publish({
            "mood": mood,
            "state": state,
            "png": frames_for(getattr(self.config, "avatar_map", {}) or {}, mood, state),
        })

    def perform(self, clip: str) -> None:
        """A still image has no behaviours."""

    def mouth(self, envelope: MouthFrames, fps: int = ENVELOPE_FPS) -> None:
        if not len(envelope):
            return
        self.channel.publish({"envelope": list(envelope), "envelope_fps": int(fps)})

    def close(self) -> None:
        """The channel outlives the backend; the brain closes it."""

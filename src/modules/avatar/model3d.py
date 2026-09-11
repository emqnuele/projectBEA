"""A 3D body, drawn by the browser source and driven from here.

Nothing in this file knows about three.js. It turns a mood into expression
weights and a behaviour name, and publishes them; the page owns the rendering.
That split is deliberate — it is what lets the renderer be replaced without the
engine noticing, and what keeps this testable without a browser.
"""

from src.core.expression.face import weights_for
from src.core.expression.pcm import ENVELOPE_FPS
from src.core.stage import StageChannel
from src.interfaces.base_interfaces import AvatarInterface, MouthFrames
from src.utils.logger import get_logger

logger = get_logger("bea.avatar.model")


class Model3DAvatar(AvatarInterface):
    """Publishes what she is; the browser source turns it into pixels."""

    def __init__(self, config, channel: StageChannel):
        self.config = config
        self.channel = channel
        self._warned_missing = False
        self._check_model()

    @property
    def _stage(self) -> dict:
        return getattr(self.config, "stage", None) or {}

    def _check_model(self) -> None:
        if not self._stage.get("model_path") and not self._warned_missing:
            self._warned_missing = True
            logger.warning(
                "The 3D avatar has no model_path. No model ships with projectBEA: "
                "run `make model` for the free sample, or point it at your own .vrm."
            )

    def reload_config(self, config) -> None:
        self.config = config
        self._warned_missing = False
        self._check_model()

    # --- the port -----------------------------------------------------------

    def show(self, mood: str, state: str) -> None:
        patch = {
            "mood": mood,
            "state": state,
            # the weights, not the mood name: the vocabulary of moods stays in
            # Python where it is tested, and the page only lerps toward numbers
            "expressions": weights_for(mood),
        }
        clip = (self._stage.get("mood_clips") or {}).get(mood)
        if clip and state == "talking":
            patch["perform"] = clip
        self.channel.publish(patch)

    def perform(self, clip: str) -> None:
        if not clip:
            return
        self.channel.publish({"perform": clip})

    def mouth(self, envelope: MouthFrames, fps: int = ENVELOPE_FPS) -> None:
        if not len(envelope):
            return
        self.channel.publish({"envelope": list(envelope), "envelope_fps": int(fps)})

    def close(self) -> None:
        """The channel outlives the backend; the brain closes it."""

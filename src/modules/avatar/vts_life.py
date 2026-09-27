"""The life the 3D page gives her, for a Live2D model in VTube Studio.

Without a webcam a VTube Studio model only moves with its own idle motion. This
computes what `life.js` does for the 3D body — a wandering gaze, eyes that jump,
a head that follows them late, nods while listening, a look away while
thinking, a dip with her voice, a droop asleep, blinks — from the same state
table (`src/web/frontend/src/stage/states.json`), as plain numbers per frame.

Pure: time only moves when `step` is called, and randomness comes from the
`random.Random` it is given, so it is tested without a clock.

Signals: `yaw`, `pitch`, `roll` in degrees (pitch positive is looking down,
as on the page), `eye_x`, `eye_y` in [-1, 1] and `blink` in [0, 1] (1 is shut).
"""

import json
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATES_FILE = Path(__file__).resolve().parents[2] / "web" / "frontend" / "src" / "stage" / "states.json"

# how fast a new state's numbers replace the old ones, as on the page
STATE_RATE = 3.0

# a blink is fast to close and slower to open; a symmetrical one reads as a wink
BLINK_SECONDS = 0.16
BLINK_CLOSE = 0.35

# how fast her head follows the loudness of her voice
VOICE_RATE = 10.0

# a live2d head turns with the gaze far more than a 3d neck, whose eyes carry most of it; a starting value
HEAD_GAIN = 4.0

# the eye angle, in degrees, that reads as the eye parameter at its limit; a starting value
EYE_RANGE_DEG = 20.0

EASED = ("wander", "head", "headRate", "sway", "voice", "droop")


@lru_cache(maxsize=1)
def states() -> Dict[str, Dict[str, Any]]:
    return json.loads(STATES_FILE.read_text(encoding="utf-8"))


def state_named(name: str) -> Dict[str, Any]:
    table = states()
    return table.get(name) or table["idle"]


def _ease(current: float, target: float, rate: float, dt: float) -> float:
    return current + (target - current) * (1 - math.exp(-rate * dt))


class LifeSignals:
    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.t = self.rng.random() * 1000
        self.state = state_named("idle")
        self.now = {key: float(self.state[key]) for key in EASED}
        self.look = [float(v) for v in self.state["look"]]
        self.blink_in = 1 + self.rng.random() * 3
        self.blinking = 0.0
        self.lids = 0.0
        self.saccade_in = 0.0
        self.saccade = (0.0, 0.0)
        self.nod_in = 1.0
        self.nod_at = -1.0
        self.voice = 0.0
        self.yaw = 0.0
        self.pitch = 0.0

    def set_state(self, name: str) -> None:
        state = state_named(name)
        if state is self.state:
            return
        self.state = state
        self.saccade_in = 0.0
        nod = state.get("nod")
        self.nod_in = self._nod_wait(nod) if nod else 1.0

    def _nod_wait(self, nod: Dict[str, float]) -> float:
        return max(nod["length"], nod["every"] + (self.rng.random() * 2 - 1) * nod["jitter"])

    def _saccade_wait(self, saccade: Dict[str, float]) -> float:
        spread = max(saccade["mean"] - saccade["gap"], 0.0)
        return saccade["gap"] - math.log(1 - min(self.rng.random(), 0.999999)) * spread

    def _blink(self, dt: float) -> float:
        if self.state["eyesShut"]:
            self.lids = _ease(self.lids, 1.0, 4.0, dt)
            return self.lids
        if self.lids > 0.001:
            self.lids = _ease(self.lids, 0.0, 3.0, dt)
            return self.lids
        self.lids = 0.0
        self.blink_in -= dt
        if self.blink_in <= 0 and self.blinking <= 0:
            low, high = self.state["blink"]
            self.blink_in = low + self.rng.random() * (high - low)
            self.blinking = BLINK_SECONDS
        if self.blinking <= 0:
            return 0.0
        self.blinking = max(0.0, self.blinking - dt)
        gone = 1 - self.blinking / BLINK_SECONDS
        return gone / BLINK_CLOSE if gone < BLINK_CLOSE else 1 - (gone - BLINK_CLOSE) / (1 - BLINK_CLOSE)

    def _nod(self, dt: float) -> float:
        nod = self.state.get("nod")
        if not nod:
            self.nod_at = -1.0
            return 0.0
        if self.nod_at >= 0:
            self.nod_at += dt
            if self.nod_at >= nod["length"]:
                self.nod_at = -1.0
        else:
            self.nod_in -= dt
            if self.nod_in <= 0:
                self.nod_at = 0.0
                self.nod_in = self._nod_wait(nod)
        if self.nod_at < 0:
            return 0.0
        return nod["depth"] * math.sin(math.pi * self.nod_at / nod["length"]) ** 2

    def step(self, dt: float, loudness: float = 0.0) -> Dict[str, float]:
        self.t += dt
        state, now, t = self.state, self.now, self.t
        for key in EASED:
            now[key] = _ease(now[key], float(state[key]), STATE_RATE, dt)
        self.look = [_ease(self.look[i], float(state["look"][i]), STATE_RATE, dt) for i in range(2)]

        # where attention sits, as an angle off the camera: two sines per axis that never line up
        x = self.look[0] + (math.sin(t * 0.31) * 0.6 + math.sin(t * 0.13) * 0.4) * now["wander"]
        y = self.look[1] + (math.sin(t * 0.23) * 0.5 + math.sin(t * 0.07) * 0.5) * now["wander"] * 0.6

        saccade = state.get("saccade")
        if saccade:
            self.saccade_in -= dt
            if self.saccade_in <= 0:
                r = saccade["radius"] * math.sqrt(self.rng.random())
                a = 2 * math.pi * self.rng.random()
                self.saccade = (r * math.cos(a), r * math.sin(a))
                self.saccade_in = self._saccade_wait(saccade)
        else:
            self.saccade = (0.0, 0.0)

        eye_x = math.degrees(math.atan(x)) + self.saccade[0]
        eye_y = math.degrees(math.atan(y)) + self.saccade[1]

        # the head aims where attention is, not where the eyes jumped, and gets there late
        self.yaw = _ease(self.yaw, math.atan(x) * now["head"], now["headRate"], dt)
        self.pitch = _ease(self.pitch, -math.atan(y) * now["head"], now["headRate"], dt)
        self.voice = _ease(self.voice, loudness, VOICE_RATE, dt)
        dip = self._nod(dt) + self.voice * now["voice"] + now["droop"]
        lean = math.sin(t * 0.29) * 0.014 * now["sway"]

        return {
            "yaw": math.degrees(self.yaw) * HEAD_GAIN,
            "pitch": math.degrees(self.pitch + dip) * HEAD_GAIN,
            "roll": math.degrees(lean) * HEAD_GAIN,
            "eye_x": max(-1.0, min(1.0, eye_x / EYE_RANGE_DEG)),
            "eye_y": max(-1.0, min(1.0, eye_y / EYE_RANGE_DEG)),
            "blink": self._blink(dt),
        }


# signal -> vts input parameters; a leading "-" inverts it. the signs are not verified against
# a running vtube studio, so `stage.vts_life_params` can replace any entry
DEFAULT_PARAMS: Dict[str, List[str]] = {
    "yaw": ["FaceAngleX"],
    "pitch": ["-FaceAngleY"],
    "roll": ["FaceAngleZ"],
    "eye_x": ["EyeLeftX", "EyeRightX"],
    "eye_y": ["EyeLeftY", "EyeRightY"],
    "blink": ["EyeOpenLeft", "EyeOpenRight"],
}

ANGLES = ("yaw", "pitch", "roll")


def life_values(signals: Dict[str, float], ranges: Dict[str, Tuple[float, float]],
                mapping: Optional[Dict[str, List[str]]] = None) -> List[Tuple[str, float]]:
    """The parameters to inject for one frame, only those vtube studio said it has, inside their range."""
    out: List[Tuple[str, float]] = []
    for signal, names in {**DEFAULT_PARAMS, **(mapping or {})}.items():
        if signal not in signals:
            continue
        for raw in names:
            name = raw.lstrip("-")
            if name not in ranges:
                continue
            low, high = ranges[name]
            value = -signals[signal] if raw.startswith("-") else signals[signal]
            if signal in ANGLES:
                mapped = value
            elif signal == "blink":
                mapped = low + (1.0 - value) * (high - low)
            else:
                mapped = low + (value + 1.0) / 2.0 * (high - low)
            out.append((name, round(min(max(mapped, low), high), 3)))
    return out

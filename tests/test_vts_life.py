"""The 3D page's life, as numbers a Live2D model in VTube Studio can take."""

import json
import random
from pathlib import Path

from src.modules.avatar.vts_life import DEFAULT_PARAMS, LifeSignals, life_values, states

RANGES = {"FaceAngleX": (-30, 30), "FaceAngleY": (-30, 30), "FaceAngleZ": (-30, 30),
          "EyeLeftX": (-1, 1), "EyeRightX": (-1, 1), "EyeLeftY": (-1, 1), "EyeRightY": (-1, 1),
          "EyeOpenLeft": (0, 1), "EyeOpenRight": (0, 1)}


def run(state, seconds=6.0, loudness=0.0, seed=1):
    life = LifeSignals(random.Random(seed))
    life.set_state(state)
    frames = [life.step(1 / 30, loudness) for _ in range(int(seconds * 30))]
    return frames[int(len(frames) / 2):]


def test_the_page_and_vtube_studio_read_one_table():
    page = Path("src/web/frontend/src/stage/states.json")
    assert states() == json.loads(page.read_text())
    assert set(states()) == {"idle", "listening", "thinking", "talking", "sleeping"}


def test_thinking_looks_up_and_to_the_side():
    frames = run("thinking")
    assert all(f["pitch"] < 0 for f in frames), "pitch is positive looking down, so up is negative"
    assert all(f["yaw"] > 0 for f in frames)


def test_asleep_the_head_hangs_and_the_eyes_stay_shut():
    frames = run("sleeping")
    assert all(f["pitch"] > 0 for f in frames)
    assert frames[-1]["blink"] > 0.99


def test_listening_nods():
    pitches = [f["pitch"] for f in run("listening", seconds=12)]
    assert max(pitches) - min(pitches) > 1.0


def test_talking_dips_with_her_voice():
    quiet = sum(f["pitch"] for f in run("talking", loudness=0.0)) / 90
    loud = sum(f["pitch"] for f in run("talking", loudness=1.0)) / 90
    assert loud > quiet


def test_she_blinks_while_awake():
    blinks = [f["blink"] for f in run("idle", seconds=20)]
    assert max(blinks) > 0.8 and min(blinks) == 0.0


def test_the_same_seed_is_the_same_life():
    assert run("idle", seed=4) == run("idle", seed=4)


def test_only_parameters_vtube_studio_has_are_sent_and_inside_their_range():
    signals = {"yaw": 90.0, "pitch": -5.0, "roll": 0.0, "eye_x": 1.0, "eye_y": -1.0, "blink": 1.0}
    values = dict(life_values(signals, {k: v for k, v in RANGES.items() if k != "FaceAngleZ"}))
    assert "FaceAngleZ" not in values
    assert values["FaceAngleX"] == 30, "clamped to the range vtube studio reported"
    assert values["FaceAngleY"] == 5.0, "inverted by the default mapping"
    assert values["EyeLeftX"] == 1 and values["EyeLeftY"] == -1
    assert values["EyeOpenLeft"] == 0, "a shut eye is the bottom of the open range"


def test_the_mapping_can_be_replaced_one_signal_at_a_time():
    values = dict(life_values({"pitch": -5.0}, RANGES, {"pitch": ["FaceAngleY"]}))
    assert values == {"FaceAngleY": -5.0}
    assert DEFAULT_PARAMS["pitch"] == ["-FaceAngleY"]

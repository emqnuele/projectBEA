"""How Bea appears is a port, not a branch in the speech path.

`Expression` used to resolve file paths itself and ask `if obs_source_type ==
"media"` in six different places. It now hands down a mood and a state and never
learns what they turn into.
"""

from pathlib import Path

import numpy as np
import pytest

from src.core.expression import Expression
from src.interfaces.base_interfaces import AvatarInterface, CaptionInterface
from src.modules.avatar.png import PngAvatar
from src.modules.caption.obs_text import ObsTextCaption
from tests.fakes import FakeAvatar, FakeCaption


class RecordingObs:
    """Records the OBS calls an adapter makes, and nothing else."""

    def __init__(self):
        self.images = []
        self.media = []
        self.texts = []
        self.typed = []
        self.font_size = 42

    def set_image(self, path):
        self.images.append(str(path))

    def set_media(self, path):
        self.media.append(str(path))

    def set_text(self, text, source_name, font_size=None):
        self.texts.append((text, source_name, font_size))

    async def type_text(self, **kwargs):
        self.typed.append(kwargs)
        return self.font_size


class Config:
    obs_source_type = "image"
    obs_text_source = "AIText"
    text_line_width = 30
    text_lines = 3
    text_font_size = 75
    text_min_font_size = 20
    text_font_step = 2
    typing_delay = 0.0
    text_min_duration = 0.0
    audio_device_id = None

    def __init__(self, **avatar_map):
        self.avatar_map = avatar_map or {
            "normal": {"idle": "n/idle.png", "talking": "n/talk.png"},
            "angry": {"idle": "a/idle.png", "talking": "a/talk.png"},
        }


class SilentTTS:
    async def generate_audio(self, text, prosody=None):
        return np.zeros(240, dtype=np.float32), 24000

    async def speak(self, text, output_device_id):
        pass

    def reload_config(self, config):
        pass


class Events:
    def publish(self, *a, **k):
        pass


def name_of(path: str) -> str:
    return "/".join(Path(path).parts[-2:])


# --- the port itself ---------------------------------------------------------


def test_both_backends_satisfy_the_port_they_claim():
    """A backend that forgets a method must fail at import, not on stream."""
    assert issubclass(PngAvatar, AvatarInterface)
    assert issubclass(ObsTextCaption, CaptionInterface)


def test_a_png_avatar_ignores_the_behaviours_it_cannot_perform():
    """A still image has no gestures and no mouth; it must not raise over it."""
    obs = RecordingObs()
    avatar = PngAvatar(Config(), obs)

    avatar.perform("wave")
    avatar.mouth([0.1, 0.9, 0.2], fps=30)

    assert obs.images == []
    assert obs.media == []


def test_closing_the_png_backend_takes_her_picture_down():
    """Switching to the 3D body mid-stream used to leave the old PNG on screen."""
    obs = RecordingObs()
    avatar = PngAvatar(Config(), obs)
    avatar.show("angry", "talking")

    avatar.close()

    assert obs.images[-1] == ""


def test_taking_her_picture_down_goes_through_the_source_that_holds_it():
    """A media source is cleared as a media source, not as an image one."""
    config = Config()
    config.obs_source_type = "media"
    obs = RecordingObs()

    PngAvatar(config, obs).close()

    assert obs.media == [""] and obs.images == []


def test_the_media_branch_now_lives_in_exactly_one_place():
    """The same `if` used to be copied into six methods of the speech path."""
    config = Config()
    config.obs_source_type = "media"
    obs = RecordingObs()

    PngAvatar(config, obs).show("angry", "talking")

    assert obs.media and not obs.images
    assert name_of(obs.media[0]) == "a/talk.png"


def test_talking_and_idle_pick_the_two_slots_the_mood_declares():
    obs = RecordingObs()
    avatar = PngAvatar(Config(), obs)

    avatar.show("angry", "talking")
    avatar.show("angry", "idle")

    assert [name_of(p) for p in obs.images] == ["a/talk.png", "a/idle.png"]


# --- the bug this port closes ------------------------------------------------


def test_sleeping_is_a_state_with_its_own_slot_not_a_mood():
    """`set_mood_avatar("sleeping")` resolved to `normal` and was never seen.

    "sleeping" is not in MOODS, is not a near miss, and default_avatar_map()
    gives it no slot — so the sleeping avatar silently showed her normal face
    for as long as the feature has existed.
    """
    config = Config(
        normal={"idle": "n/idle.png", "talking": "n/talk.png"},
        sleeping={"idle": "z/sleep.png", "talking": "z/sleep.png"},
    )
    obs = RecordingObs()

    PngAvatar(config, obs).show("angry", "sleeping")

    assert name_of(obs.images[0]) == "z/sleep.png"


def test_an_unmapped_state_falls_back_to_the_mood_and_says_so_once(caplog):
    """Silence was the bug. Falling back is fine; doing it quietly is not."""
    obs = RecordingObs()
    avatar = PngAvatar(Config(), obs)

    with caplog.at_level("WARNING"):
        avatar.show("angry", "sleeping")
        avatar.show("angry", "sleeping")

    assert name_of(obs.images[0]) == "a/idle.png"
    warnings = [r for r in caplog.records if "sleeping" in r.message]
    assert len(warnings) == 1, "one warning per missing state, not one per frame"


# --- the caption -------------------------------------------------------------


async def test_the_caption_keeps_the_font_size_instead_of_handing_it_back():
    """`type_text` returned it only so Expression could pass it back on clear."""
    obs = RecordingObs()
    obs.font_size = 55
    caption = ObsTextCaption(Config(), obs)

    await caption.say("una battuta lunga abbastanza da rimpicciolire il testo")
    caption.clear()

    assert obs.texts[-1] == ("", "AIText", 55)


async def test_a_caption_with_no_source_configured_does_nothing():
    """An empty `obs_text_source` is how you turn the bubble off."""
    config = Config()
    config.obs_text_source = ""
    obs = RecordingObs()
    caption = ObsTextCaption(config, obs)

    await caption.say("ciao")
    caption.clear()

    assert obs.typed == [] and obs.texts == []


# --- what Expression is left knowing ----------------------------------------


async def test_a_line_ends_in_the_state_she_was_resting_in():
    """She is in a call, so she goes back to listening, not to idle.

    `idle` was hardcoded at the end of every line, which quietly threw away the
    state she was actually in the moment she opened her mouth.
    """
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())

    e.set_state("listening")
    await e.speak("normal", "ci sono")

    assert avatar.states == ["listening", "talking", "listening"]


async def test_falling_asleep_survives_a_line_talked_in_her_sleep():
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())

    e.set_state("sleeping")
    await e.speak("normal", "mh")

    assert avatar.states[-1] == "sleeping"


async def test_waking_up_puts_her_back_to_idle():
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())

    e.set_state("sleeping")
    e.set_state("idle", mood="normal")
    await e.speak("normal", "eccomi")

    assert avatar.states[-1] == "idle"


async def test_someone_joining_the_call_does_not_take_her_face_mid_word():
    """The bot reports the room on every join and leave, whatever she is doing."""
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())
    e.is_speaking = True

    e.set_state("listening")

    assert avatar.shown == [], "her talking face was replaced halfway through a line"

    e.is_speaking = False
    await e.speak("normal", "dicevo")
    assert avatar.states[-1] == "listening", "and she still goes back to it after"


async def test_swapping_backends_keeps_the_state_she_is_in():
    """Picking another avatar in the dashboard must not wake her or deafen her."""
    e = Expression(Config(), SilentTTS(), FakeAvatar(), FakeCaption(), Events())
    e.set_state("listening")

    fresh = FakeAvatar()
    e.set_ports(fresh, FakeCaption())

    assert fresh.shown == [("normal", "listening")]


async def test_expression_drives_the_ports_and_never_a_file_path():
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())

    await e.speak("angry", "ma dai")

    assert avatar.shown == [("angry", "talking"), ("angry", "idle")]
    assert caption.said == ["ma dai"]
    assert not hasattr(e, "png_map")
    assert not hasattr(e, "obs")


async def test_a_resumed_line_keeps_the_mood_it_was_cut_off_in():
    """Resume used to hardcode `normal`: an angry sentence finished neutral."""
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())

    await e.speak("angry", "stavo dicendo")
    e.resume_buffer = np.zeros(24000, dtype=np.float32)
    await e.resume()

    assert ("normal", "talking") not in avatar.shown
    assert avatar.shown[-2:] == [("angry", "talking"), ("angry", "idle")]


def test_a_state_change_does_not_reset_the_face_she_was_wearing():
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())

    e.set_state("listening", mood="angry")
    e.set_state("sleeping")

    assert avatar.shown == [("angry", "listening"), ("angry", "sleeping")]


def test_waking_up_is_allowed_to_reset_the_mood_because_it_says_so():
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())

    e.set_state("sleeping", mood="cry")
    e.set_state("idle", mood="normal")

    assert avatar.shown[-1] == ("normal", "idle")


async def test_an_interruption_clears_the_caption_and_settles_the_avatar():
    avatar, caption = FakeAvatar(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())

    await e.speak("shock", "aspetta")
    caption.clears = 0
    await e.interrupt()

    assert caption.clears == 1
    assert avatar.shown[-1] == ("shock", "idle")


def test_reloading_the_config_reaches_both_ports():
    class Recorder(FakeAvatar):
        reloaded = 0

        def reload_config(self, config):
            type(self).reloaded += 1

    avatar, caption = Recorder(), FakeCaption()
    e = Expression(Config(), SilentTTS(), avatar, caption, Events())
    e.reload_config(Config())

    assert Recorder.reloaded == 1


@pytest.mark.parametrize("state", ["idle", "talking", "listening", "sleeping"])
def test_every_state_the_engine_uses_resolves_to_something_showable(state):
    obs = RecordingObs()
    PngAvatar(Config(), obs).show("normal", state)
    assert obs.images, f"the '{state}' state showed nothing at all"


def test_swapping_the_backend_mid_run_keeps_the_face_she_was_wearing():
    """Changing the dropdown must not reset her to neutral on stream."""
    e = Expression(Config(), SilentTTS(), FakeAvatar(), FakeCaption(), Events())
    e.set_state("idle", mood="angry")

    replacement = FakeAvatar()
    e.set_ports(replacement, FakeCaption())

    assert replacement.shown == [("angry", "idle")]

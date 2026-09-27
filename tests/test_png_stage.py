"""The PNG avatar drawn by the browser source: same pictures, no OBS socket."""

from src.core.config import BrainConfig
from src.core.stage import StageChannel, public_config
from src.modules.avatar.factory import backend_key, build_avatar
from src.modules.avatar.png import PngAvatar
from src.modules.avatar.png_stage import PngStageAvatar, frames_for

MAP = {
    "neutral": {"idle": "n/idle.png", "talking": "n/talk.png"},
    "happy": {"idle": "h/idle.png", "talking": "h/talk.png", "talking_closed": "h/shut.png", "blink": "h/blink.png"},
    "sad": {"idle": "s/idle.png", "talking": ""},
    "sleeping": {"idle": "z/idle.png", "talking": "z/idle.png"},
}


class Obs:
    def set_image(self, *a, **k):
        raise AssertionError("the browser-source png must never touch obs")

    set_media = set_image


def config(**stage):
    cfg = BrainConfig()
    cfg.avatar_map = MAP
    cfg.stage = {**cfg.stage, **stage}
    return cfg


def test_a_mood_with_every_picture_uses_every_picture():
    assert frames_for(MAP, "happy", "talking") == {
        "rest": "happy/idle", "open": "happy/talking", "closed": "happy/talking_closed", "blink": "happy/blink"}


def test_without_a_shut_mouth_picture_the_mouth_flaps_between_idle_and_talking():
    assert frames_for(MAP, "neutral", "talking") == {
        "rest": "neutral/idle", "open": "neutral/talking", "closed": "neutral/idle", "blink": None}


def test_a_mood_missing_a_picture_falls_back_the_way_obs_does():
    assert frames_for(MAP, "sad", "idle")["rest"] == "neutral/idle"
    assert frames_for(MAP, "no-such-mood", "idle")["rest"] == "neutral/idle"


def test_a_state_with_its_own_picture_rests_on_it_and_does_not_blink_asleep():
    frames = frames_for(MAP, "happy", "sleeping")
    assert frames["rest"] == "sleeping/idle"
    assert frames["blink"] is None


def test_nothing_mapped_publishes_nothing_to_draw():
    assert frames_for({}, "happy", "idle") is None


def test_it_publishes_keys_and_an_envelope_and_never_calls_obs():
    channel = StageChannel()
    queue = channel.subscribe()
    avatar = build_avatar(config(png_render="stage"), Obs(), channel)
    assert isinstance(avatar, PngStageAvatar)

    avatar.show("happy", "talking")
    avatar.mouth([[0.5, 0.2], [0.0, 0.5]], 30)

    first, second = queue.get_nowait(), queue.get_nowait()
    assert first["png"]["open"] == "happy/talking"
    assert "h/" not in str(first), "a path reached the page"
    assert second == {"envelope": [[0.5, 0.2], [0.0, 0.5]], "envelope_fps": 30}
    assert channel.snapshot()["png"] == first["png"], "a reconnecting page is told the pictures"


def test_the_obs_picture_is_still_the_default():
    assert isinstance(build_avatar(config(), Obs(), StageChannel()), PngAvatar)
    assert backend_key(config()) == "png"


def test_switching_where_it_is_drawn_rebuilds_the_backend():
    assert backend_key(config(png_render="stage")) != backend_key(config(png_render="obs"))


def test_without_a_stage_channel_it_falls_back_to_obs(caplog):
    class Quiet(Obs):
        def set_image(self, *a, **k):
            pass

    assert isinstance(build_avatar(config(png_render="stage"), Quiet(), None), PngAvatar)


def test_the_page_is_told_where_the_png_is_drawn():
    assert public_config(config(png_render="stage"))["png_render"] == "stage"


async def test_the_doctor_does_not_ask_for_obs_when_nothing_goes_through_it():
    from src.setup.doctor import check_obs

    found = await check_obs(config(avatar_backend="png", png_render="stage", caption_backend="stage"))
    assert found.ok
    assert "not needed" in found.detail

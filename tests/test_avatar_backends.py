"""Choosing how she appears is configuration, not a code change.

The factories are the only place that knows a backend by name; everything above
them sees `AvatarInterface` and `CaptionInterface` and nothing else.
"""

import pytest

from src.core.config import BrainConfig
from src.interfaces.base_interfaces import AvatarInterface, CaptionInterface
from src.modules.avatar.factory import BUILDERS as AVATAR_BUILDERS
from src.modules.avatar.factory import backend_name as avatar_backend
from src.modules.avatar.factory import build_avatar
from src.modules.caption.factory import BUILDERS as CAPTION_BUILDERS
from src.modules.caption.factory import backend_name as caption_backend
from src.modules.caption.factory import build_caption


class Obs:
    def set_image(self, *a, **k):
        pass

    def set_media(self, *a, **k):
        pass

    def set_text(self, *a, **k):
        pass

    async def type_text(self, **kwargs):
        return 0


def config(**stage) -> BrainConfig:
    cfg = BrainConfig()
    cfg.stage = {**cfg.stage, **stage}
    return cfg


# --- the defaults ------------------------------------------------------------


def test_the_default_setup_is_the_one_that_already_worked():
    """Upgrading must not move anybody's stream."""
    cfg = BrainConfig()
    assert cfg.stage["avatar_backend"] == "png"
    assert cfg.stage["caption_backend"] == "obs"


def test_a_config_written_before_the_stage_existed_still_loads():
    """`deep_merge` fills the block in; an old config.json has no `stage` key."""
    cfg = BrainConfig()
    cfg.stage.pop("avatar_backend")
    assert avatar_backend(cfg) == "png"


# --- the dispatch ------------------------------------------------------------


def test_every_registered_backend_builds_something_that_honours_the_port():
    for name in AVATAR_BUILDERS:
        avatar = build_avatar(config(avatar_backend=name), Obs())
        assert isinstance(avatar, AvatarInterface), f"{name} is not an avatar"
    for name in CAPTION_BUILDERS:
        caption = build_caption(config(caption_backend=name), Obs())
        assert isinstance(caption, CaptionInterface), f"{name} is not a caption"


@pytest.mark.parametrize("name", ["", "3d", "Png", "vtube studio", None])
def test_an_unknown_backend_falls_back_instead_of_leaving_her_invisible(name, caplog):
    """A typo in config.json must cost a warning, not a whole stream."""
    with caplog.at_level("WARNING"):
        avatar = build_avatar(config(avatar_backend=name), Obs())
    assert isinstance(avatar, AvatarInterface)
    assert any("Unknown avatar backend" in r.message for r in caplog.records)


def test_the_caption_can_be_turned_off_on_purpose():
    """"Off" is a choice, not a blanked-out source name."""
    caption = build_caption(config(caption_backend="off"), Obs())
    assert isinstance(caption, CaptionInterface)


async def test_a_silent_caption_writes_nothing_and_raises_nothing():
    caption = build_caption(config(caption_backend="off"), Obs())
    await caption.say("qualcosa")
    caption.clear()


# --- the two choices are independent ----------------------------------------


def test_the_avatar_and_the_caption_are_chosen_separately():
    """"PNG avatar with the nicer browser caption" has to be expressible."""
    cfg = config(avatar_backend="png", caption_backend="off")
    assert avatar_backend(cfg) == "png"
    assert caption_backend(cfg) == "off"

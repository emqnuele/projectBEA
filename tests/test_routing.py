"""Where a perception goes. The invariant: exactly one destination, always."""

import pytest

from src.core.mind.routing import STAGE, conversation_key, is_stage, route
from src.core.perception.types import Author, Perception, PerceptionKind


def p(**kwargs) -> Perception:
    base = dict(kind=PerceptionKind.CHAT, surface="voice:discord", content="ciao", salience=0.5)
    base.update(kwargs)
    return Perception(**base)


def discord(name="marco", channel="123", **kwargs) -> Perception:
    return p(
        meta={"channel_id": channel, **kwargs.pop("meta", {})},
        author=Author(platform="discord", native_id="4711", display_name=name),
        **kwargs,
    )


# --- what belongs on the stage ----------------------------------------------


@pytest.mark.parametrize("kind", [PerceptionKind.VOICE, PerceptionKind.GAME,
                                  PerceptionKind.ACTION, PerceptionKind.IDLE])
def test_her_voice_body_and_time_are_the_stage(kind):
    assert conversation_key(p(kind=kind)) == STAGE


def test_the_console_is_the_stage():
    assert conversation_key(p(surface="chat:ui")) == STAGE


def test_a_voice_message_stays_on_stage_even_with_a_channel():
    """She is in the call: that IS the stage."""
    assert is_stage(p(kind=PerceptionKind.VOICE, meta={"channel_id": "999"})) is True


def test_an_awaited_caller_always_stays_on_stage():
    """The HTTP caller is blocked on the live loop's correlation; a scoped turn
    could not resolve it, and they would hang until the timeout."""
    waiting = discord(meta={"correlation_id": "abc"})
    stage, scoped = route([waiting])
    assert stage == [waiting] and scoped == {}


# --- what becomes a scoped conversation --------------------------------------


def test_a_discord_text_message_is_its_own_conversation():
    assert conversation_key(discord(channel="123")) == "discord:123"


def test_the_key_uses_the_author_platform():
    perception = p(
        meta={"channel_id": "77"},
        author=Author(platform="telegram", native_id="9", display_name="luca"),
        surface="chat:telegram",
    )
    assert conversation_key(perception) == "telegram:77"


def test_a_text_message_without_a_channel_falls_back_to_the_stage():
    assert conversation_key(p(author=Author("discord", "1", "marco"))) == STAGE


def test_an_explicit_key_wins():
    assert conversation_key(p(meta={"conversation_key": "minecraft:server"})) == \
        "minecraft:server"


def test_an_explicit_stage_key_is_honoured():
    assert conversation_key(p(meta={"conversation_key": "stage"})) == STAGE


def test_an_unknown_surface_stays_on_stage():
    assert conversation_key(p(surface="something:new", meta={"channel_id": "1"})) == STAGE


# --- the split ----------------------------------------------------------------


def test_an_empty_batch_splits_into_nothing():
    assert route([]) == ([], {})


def test_channels_are_kept_apart():
    a, b = discord(channel="1"), discord(channel="2")
    stage, scoped = route([a, b])
    assert stage == []
    assert scoped == {"discord:1": [a], "discord:2": [b]}


def test_messages_in_the_same_channel_travel_together():
    a, b = discord(channel="1"), discord(channel="1")
    _, scoped = route([a, b])
    assert scoped["discord:1"] == [a, b]


def test_a_mixed_batch_is_split_cleanly():
    game = p(kind=PerceptionKind.GAME, surface="game:mc")
    message = discord(channel="1")
    stage, scoped = route([game, message])
    assert stage == [game]
    assert scoped == {"discord:1": [message]}


def test_every_perception_lands_in_exactly_one_place():
    """The rule that must never break: answering twice, from two contexts that
    know nothing about each other, is the worst failure mode here."""
    batch = [
        p(kind=PerceptionKind.GAME, surface="game:mc"),
        discord(channel="1"),
        discord(channel="2"),
        p(surface="chat:ui"),
        discord(channel="1", meta={"correlation_id": "x"}),
    ]
    stage, scoped = route(batch)
    routed = list(stage) + [x for group in scoped.values() for x in group]
    assert len(routed) == len(batch)
    assert {id(x) for x in routed} == {id(x) for x in batch}

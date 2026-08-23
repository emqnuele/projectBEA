"""The attention decision as a table of cases — the point of keeping it pure."""

import pytest

from src.core.attention.rules import in_quiet_hours, is_addressed, score
from src.core.perception.types import Author, Perception, PerceptionKind

TRIGGERS = ["bea", "beatrice"]


def perception(**kwargs) -> Perception:
    base = dict(
        kind=PerceptionKind.CHAT,
        surface="discord:text",
        content="hello there",
        salience=0.5,
    )
    base.update(kwargs)
    return Perception(**base)


def author(**kwargs) -> Author:
    base = dict(platform="discord", native_id="4711", display_name="marco")
    base.update(kwargs)
    return Author(**base)


# --- in_quiet_hours ---------------------------------------------------------


@pytest.mark.parametrize("hour,expected", [(2, False), (3, True), (8, True), (9, False), (14, False)])
def test_quiet_hours_are_half_open(hour, expected):
    assert in_quiet_hours(hour, 3, 9) is expected


@pytest.mark.parametrize("hour,expected", [(23, True), (0, True), (5, True), (6, False), (12, False)])
def test_quiet_hours_wrap_around_midnight(hour, expected):
    assert in_quiet_hours(hour, 22, 6) is expected


def test_an_empty_quiet_window_is_never_quiet():
    assert in_quiet_hours(5, 5, 5) is False


# --- is_addressed -----------------------------------------------------------


def test_a_stranger_saying_nothing_special_is_not_addressed():
    assert is_addressed(perception(author=author()), trigger_words=TRIGGERS) is None


def test_the_owner_is_always_addressed():
    p = perception(author=author(platform="ui", is_owner=True))
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:owner"


def test_a_donation_is_always_addressed():
    p = perception(author=author(extra={"amount": 5.0}))
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:donation"


def test_a_dm_is_addressed():
    p = perception(meta={"is_dm": True}, author=author())
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:dm"


def test_her_name_addresses_her():
    p = perception(content="[marco] ciao bea come stai", author=author())
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:name"


def test_a_name_lookalike_does_not():
    p = perception(content="[marco] what a beautiful beach", author=author())
    assert is_addressed(p, trigger_words=TRIGGERS) is None


def test_a_reply_to_one_of_her_messages_is_addressed():
    p = perception(meta={"reply_to_author_id": "bot-99"}, author=author())
    assert is_addressed(p, trigger_words=TRIGGERS, self_ids=["bot-99"]) == "addressed:reply"


def test_a_reply_to_someone_else_is_not():
    p = perception(meta={"reply_to_author_id": "other"}, author=author())
    assert is_addressed(p, trigger_words=TRIGGERS, self_ids=["bot-99"]) is None


def test_a_body_action_result_always_comes_back_to_her():
    p = perception(kind=PerceptionKind.ACTION, content="[mine] result: FINISHED")
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:body"


def test_death_always_reaches_her():
    p = perception(kind=PerceptionKind.GAME, meta={"event": "death"})
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:death"


def test_being_hit_by_a_player_is_a_social_event():
    p = perception(kind=PerceptionKind.GAME, meta={"event": "hurt", "source": "player"})
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:attacked"


def test_being_hit_by_a_mob_is_not_addressed():
    p = perception(kind=PerceptionKind.GAME, meta={"event": "hurt", "source": "mob"})
    assert is_addressed(p, trigger_words=TRIGGERS) is None


def test_a_whisper_in_game_is_addressed():
    p = perception(surface="chat:mc", meta={"whisper": True}, author=author(platform="minecraft"))
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:whisper"


def test_someone_standing_next_to_her_is_addressing_her():
    p = perception(surface="chat:mc", meta={"distance": 3.0}, author=author(platform="minecraft"))
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:nearby"


def test_someone_shouting_from_far_away_is_not():
    p = perception(surface="chat:mc", meta={"distance": 40.0}, author=author(platform="minecraft"))
    assert is_addressed(p, trigger_words=TRIGGERS) is None


def test_a_one_to_one_voice_call_is_all_addressed_to_her():
    p = perception(kind=PerceptionKind.VOICE, meta={"alone_with_speaker": True}, author=author())
    assert is_addressed(p, trigger_words=TRIGGERS) == "addressed:voice-1on1"


# --- score ------------------------------------------------------------------


def base_score(**kwargs) -> float:
    args = dict(
        kind=PerceptionKind.CHAT,
        salience=0.5,
        text="something happened",
        seconds_since_spoke=300.0,
        recent_activity=0,
        hour=14,
    )
    args.update(kwargs)
    return score(**args)


def test_a_dead_room_scores_near_zero():
    assert base_score() == pytest.approx(0.0)


def test_the_cooldown_is_a_hard_gate():
    assert base_score(seconds_since_spoke=5.0, recent_activity=5) == 0.0


def test_quiet_hours_are_a_hard_gate():
    assert base_score(hour=4, recent_activity=5, text="bea!", hot_names=["bea"]) == 0.0


def test_a_busy_room_raises_the_score():
    quiet = base_score(recent_activity=0)
    busy = base_score(recent_activity=5)
    assert busy > quiet


def test_activity_saturates():
    assert base_score(recent_activity=5) == pytest.approx(base_score(recent_activity=50))


def test_a_hot_name_pulls_her_in_hard():
    assert base_score(text="did you see marco", hot_names=["marco"]) > 0.4


def test_someone_she_knows_counts_more_than_a_stranger():
    known = base_score(recent_activity=3, author_promoted=True)
    stranger = base_score(recent_activity=3)
    assert known > stranger


def test_a_question_adds_a_little():
    assert base_score(recent_activity=3, text="are you there?") > base_score(recent_activity=3, text="are you there")


def test_long_silence_makes_her_more_likely_to_chime_in():
    assert base_score(recent_activity=3, seconds_since_spoke=900.0) > \
           base_score(recent_activity=3, seconds_since_spoke=100.0)


def test_never_having_spoken_counts_as_long_silence():
    assert base_score(recent_activity=3, seconds_since_spoke=None) > 0.0


def test_low_salience_damps_the_score():
    loud = base_score(recent_activity=5, salience=0.9)
    quiet = base_score(recent_activity=5, salience=0.15)
    assert quiet < loud


def test_salience_alone_cannot_manufacture_interest():
    assert base_score(recent_activity=0, salience=1.0) == pytest.approx(0.0)


def test_the_score_stays_in_range():
    everything = base_score(
        recent_activity=50, text="bea?? marco??", hot_names=["bea", "marco"],
        author_promoted=True, donation=100.0, salience=1.0, seconds_since_spoke=None,
    )
    assert 0.0 <= everything <= 1.0

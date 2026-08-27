"""If you answer her, she answers back. Every time.

The attention gate is probabilistic on purpose — "does this concern me" is a
judgement call. But "is this person talking to me right now" is not, and
rolling a die on it is precisely what makes a bot feel broken: you reply to
her, and she ignores you.

This is a separate, deterministic gate. It also skips the cooldown, because
answering someone who just spoke to you is not being pushy.
"""

import pytest

from src.core.attention.followup import Turn, is_followup
from src.core.memory.store import MemoryStore

WINDOW = 180.0
MAX_TURNS = 3
MAX_INTERPOSED = 3


def check(history, *, identity="telegram:2", since=10.0, activity=0, **kwargs):
    return is_followup(
        history, identity=identity, seconds_since_bea=since,
        recent_activity=activity, window_seconds=WINDOW,
        max_turns=MAX_TURNS, max_interposed=MAX_INTERPOSED,
        **kwargs,
    )


def bea(to: str = "telegram:2") -> Turn:
    return Turn(role="bea", identity="", addressee=to)


def said(identity: str = "telegram:2", text: str = "ok") -> Turn:
    return Turn(role="user", identity=identity, addressee="", content=text)


# --- the plain case ----------------------------------------------------------


def test_answering_her_reaches_her():
    assert check([said(), bea()]) is True


def test_someone_else_answering_does_not():
    assert check([said(), bea("telegram:9")]) is False


def test_an_empty_history_is_not_a_follow_up():
    assert check([]) is False


def test_a_conversation_she_never_spoke_in_is_not_a_follow_up():
    assert check([said(), said()]) is False


def test_she_has_to_have_spoken_at_some_point():
    assert check([said(), bea()], since=None) is False


# --- how long it stays open --------------------------------------------------


def test_a_reply_much_later_is_a_new_conversation():
    assert check([said(), bea()], since=WINDOW + 1) is False


def test_a_reply_just_inside_the_window_still_counts():
    assert check([said(), bea()], since=WINDOW - 1) is True


# --- messages in between -----------------------------------------------------


def test_a_couple_of_messages_in_between_are_fine():
    history = [said(), bea(), said("telegram:9"), said("telegram:9")]
    assert check(history) is True


def test_a_wall_of_messages_in_between_means_the_moment_passed():
    history = [said(), bea()] + [said("telegram:9") for _ in range(6)]
    assert check(history) is False


def test_a_busy_room_is_allowed_more_room():
    """In a fast group, other people always land between her line and the reply."""
    history = [said(), bea()] + [said("telegram:9") for _ in range(6)]
    assert check(history, activity=10, active_bonus=8) is True


# --- not being a limpet ------------------------------------------------------


def test_she_stops_after_a_few_turns_in_a_row():
    history = [said(), bea(), said(), bea(), said(), bea()]
    assert check(history) is False


def test_being_called_by_name_resets_her_patience():
    history = [
        said(), bea(),
        said(text="bea guarda qui"), bea(),
        said(), bea(),
    ]
    assert check(history, trigger_words=["bea"]) is True


def test_a_chain_with_someone_else_in_it_does_not_count_against_them():
    history = [said(), bea("telegram:9"), said(), bea()]
    assert check(history) is True


# --- what the store has to remember ------------------------------------------


@pytest.fixture
def memory():
    return MemoryStore(":memory:")


def test_her_reply_records_who_it_was_for(memory):
    memory.conversations.add(
        conversation_key="telegram:2", role="bea", content="ciao",
        addressee_identity="telegram:7",
    )
    assert memory.conversations.history("telegram:2")[0]["addressee_identity"] == "telegram:7"


def test_a_reply_with_nobody_in_particular_records_nothing(memory):
    memory.conversations.add(conversation_key="telegram:2", role="bea", content="ciao")
    assert memory.conversations.history("telegram:2")[0]["addressee_identity"] == ""


def test_the_history_comes_back_as_turns_the_gate_understands(memory):
    memory.conversations.add(conversation_key="telegram:2", role="user",
                             content="ciao", author_identity="telegram:7")
    memory.conversations.add(conversation_key="telegram:2", role="bea",
                             content="ehi", addressee_identity="telegram:7")
    turns = memory.conversations.turns("telegram:2")
    assert [t.role for t in turns] == ["user", "bea"]
    assert turns[0].identity == "telegram:7"
    assert turns[1].addressee == "telegram:7"


def test_only_the_recent_tail_is_looked_at(memory):
    for i in range(50):
        memory.conversations.add(conversation_key="telegram:2", role="user",
                                 content=f"m{i}", author_identity="telegram:7")
    assert len(memory.conversations.turns("telegram:2", limit=10)) == 10


# --- wired into the gate -----------------------------------------------------


class Cfg:
    def __init__(self, **attention):
        self.attention = {
            "enabled": True, "cooldown_seconds": 20, "interject_threshold": 0.45,
            "quiet_hours": [3, 9], "trigger_words": ["bea"], "hot_names": [],
            "self_ids": [], "followup_enabled": True,
            **attention,
        }
        self.skills = {}


def _perception(identity="telegram:2", text="e quindi?"):
    from src.core.perception.types import Author, Perception, PerceptionKind

    platform, _, native = identity.partition(":")
    return Perception(
        PerceptionKind.CHAT, "chat:telegram", f"[Ema] {text}", salience=0.4,
        meta={"conversation_key": "telegram:2", "channel_id": "2"},
        author=Author(platform=platform, native_id=native, display_name="Ema"),
    )


def gate(memory, **attention):
    import random
    from datetime import datetime

    from src.core.attention.gate import Attention

    rng = random.Random()
    rng.uniform = lambda a, b: 0.0
    noon = datetime(2026, 6, 15, 12, 0).timestamp()
    return Attention(Cfg(**attention), rng=rng, clock=lambda: noon,
                     conversations=memory.conversations)


def _exchange(memory, addressee="telegram:2"):
    memory.conversations.add(conversation_key="telegram:2", role="user",
                             content="ciao", author_identity="telegram:2")
    memory.conversations.add(conversation_key="telegram:2", role="bea",
                             content="ehi", addressee_identity=addressee)


def test_a_reply_to_her_gets_through_the_gate(memory):

    _exchange(memory)
    g = gate(memory)
    g.mark_spoke("telegram:2")  # she just spoke: the cooldown would normally block
    react, _noted = g.judge([_perception()])
    assert [p.content for p in react] == ["[Ema] e quindi?"]


def test_a_reply_to_someone_else_does_not(memory):
    _exchange(memory, addressee="telegram:9")
    g = gate(memory)
    g.mark_spoke("telegram:2")
    react, noted = g.judge([_perception()])
    assert react == []
    assert len(noted) == 1


def test_the_reason_says_it_was_a_follow_up(memory):
    verdicts = []
    _exchange(memory)
    g = gate(memory)
    g.mark_spoke("telegram:2")
    g._on_verdict = lambda p, v: verdicts.append(v)
    g.judge([_perception()])
    assert verdicts[0].reason == "addressed:follow-up"


def test_the_follow_up_gate_can_be_switched_off(memory):
    _exchange(memory)
    g = gate(memory, followup_enabled=False)
    g.mark_spoke("telegram:2")
    react, _ = g.judge([_perception()])
    assert react == []


def test_without_a_store_the_gate_still_works(memory):
    import random

    from src.core.attention.gate import Attention

    rng = random.Random()
    rng.uniform = lambda a, b: 0.0
    react, _ = Attention(Cfg(), rng=rng).judge([_perception()])
    assert isinstance(react, list)


# --- her reply records who it was for ----------------------------------------


async def test_answering_someone_records_that_it_was_for_them(memory):
    """Without this the follow-up gate has nothing to read."""
    from src.core.mind.conversation import ConversationMind
    from src.core.mind.scheduler import ConversationScheduler
    from src.core.perception.types import Author, Perception, PerceptionKind
    from src.core.skills.base import SkillRegistry

    class C:
        skills = {}
        attention = {}
        consciousness = {}

    mind = ConversationMind(
        config=C(), llm=None, memory=memory, surfaces=SkillRegistry(),
        soul_getter=lambda: "", operating_getter=lambda: "",
        scheduler=ConversationScheduler(),
    )
    incoming = [Perception(
        PerceptionKind.CHAT, "chat:telegram", "[Ema] ciao", salience=0.5,
        author=Author(platform="telegram", native_id="2", display_name="Ema"),
    )]
    mind._record_outgoing("telegram:2", ["ehi"], incoming)
    assert memory.conversations.history("telegram:2")[0]["addressee_identity"] == "telegram:2"


async def test_a_line_to_nobody_in_particular_records_nobody(memory):
    from src.core.mind.conversation import ConversationMind
    from src.core.mind.scheduler import ConversationScheduler
    from src.core.skills.base import SkillRegistry

    class C:
        skills = {}
        attention = {}
        consciousness = {}

    mind = ConversationMind(
        config=C(), llm=None, memory=memory, surfaces=SkillRegistry(),
        soul_getter=lambda: "", operating_getter=lambda: "",
        scheduler=ConversationScheduler(),
    )
    mind._record_outgoing("telegram:2", ["ehi"], [])
    assert memory.conversations.history("telegram:2")[0]["addressee_identity"] == ""

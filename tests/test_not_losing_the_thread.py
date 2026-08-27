"""Three ways she used to lose the thread.

The rolling context dropped the oldest messages and nobody wrote down what was
in them, so an hour into a stream the first half had simply never happened. The
people in the room were only named if they already had a card. And the one line
telling a written turn what she was doing knew about Minecraft and nothing
else — not the call she was sitting in, not what she was supposed to be doing
today.
"""

import pytest

from src.core.mind.recap import MAX_RECAP_CHARS, SessionRecap

# --- what falls out of the context ------------------------------------------


def test_a_fresh_recap_says_nothing():
    assert SessionRecap().render() == ""


def test_what_was_dropped_is_remembered_until_it_can_be_condensed():
    recap = SessionRecap()
    recap.drop([{"role": "user", "content": "parliamo del setup"}])
    assert recap.pending == 1


def test_tool_noise_is_not_worth_remembering():
    recap = SessionRecap()
    recap.drop([{"role": "tool", "content": "Spoken."}])
    assert recap.pending == 0


def test_an_empty_message_is_not_worth_remembering():
    recap = SessionRecap()
    recap.drop([{"role": "assistant", "content": ""}])
    assert recap.pending == 0


def test_it_renders_a_summary_once_it_has_one():
    recap = SessionRecap()
    recap.set("You spent the first hour setting up the stream and complaining about it.")
    assert "EARLIER THIS SESSION" in recap.render()
    assert "first hour" in recap.render()


def test_a_summary_never_grows_past_its_budget():
    recap = SessionRecap()
    recap.set("x" * (MAX_RECAP_CHARS + 500))
    assert len(recap.render()) < MAX_RECAP_CHARS + 100


def test_it_only_condenses_once_enough_has_fallen_out():
    recap = SessionRecap(condense_after=5)
    recap.drop([{"role": "user", "content": "una cosa"}])
    assert recap.due is False


def test_it_is_due_once_enough_has():
    recap = SessionRecap(condense_after=2)
    recap.drop([{"role": "user", "content": "uno"}, {"role": "user", "content": "due"}])
    assert recap.due is True


async def test_condensing_asks_the_model_and_keeps_the_answer():
    from src.core.agent.types import AssistantMessage
    from tests.fakes import FakeLLMClient

    llm = FakeLLMClient([AssistantMessage(content="She argued about pizza for a while.")])
    recap = SessionRecap(condense_after=1)
    recap.drop([{"role": "user", "content": "la pizza con l'ananas è buona"}])
    await recap.condense(llm)
    assert "pizza" in recap.render()
    assert recap.pending == 0


async def test_what_was_already_summarised_is_carried_forward():
    from src.core.agent.types import AssistantMessage
    from tests.fakes import FakeLLMClient

    llm = FakeLLMClient([AssistantMessage(content="new summary")])
    recap = SessionRecap(condense_after=1)
    recap.set("the story so far")
    recap.drop([{"role": "user", "content": "altro"}])
    await recap.condense(llm)
    assert "the story so far" in llm.calls[0][-1]["content"]


async def test_a_model_that_fails_does_not_lose_what_was_dropped():
    from tests.fakes import FakeLLMClient

    llm = FakeLLMClient()
    llm.fail_with = RuntimeError("no")
    recap = SessionRecap(condense_after=1)
    recap.drop([{"role": "user", "content": "importante"}])
    await recap.condense(llm)
    assert recap.pending == 1


# --- the live loop uses it ---------------------------------------------------


class Cfg:
    def __init__(self, history_limit=6):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "history_limit": history_limit,
                              "correlation_timeout": 5.0}
        self.attention = {}
        self.skills = {}
        self.persona = {}
        self.timezone = ""


def _mind(config=None):
    from src.core.attention.gate import Attention
    from src.core.consciousness import Consciousness
    from src.core.perception.bus import PerceptionBus
    from src.core.skills.base import SkillRegistry
    from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents

    config = config or Cfg()
    return Consciousness(
        config=config, llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=SkillRegistry(),
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "", operating_getter=lambda: "",
        attention=Attention(config),
    )


def test_trimming_hands_what_it_drops_to_the_recap():
    mind = _mind(Cfg(history_limit=4))
    mind.context = [{"role": "system", "content": "s"}] + [
        {"role": "user", "content": f"messaggio {i}"} for i in range(20)
    ]
    mind._trim()
    assert mind.recap.pending > 0


def test_trimming_still_keeps_the_context_short():
    mind = _mind(Cfg(history_limit=4))
    mind.context = [{"role": "system", "content": "s"}] + [
        {"role": "user", "content": f"messaggio {i}"} for i in range(20)
    ]
    mind._trim()
    assert len(mind.context) <= 5


def test_the_recap_reaches_her_context():
    mind = _mind()
    mind.recap.set("You spent an hour on the stream setup.")
    assert "stream setup" in mind._system_message([])["content"]


def test_nothing_is_added_when_there_is_nothing_to_recap():
    mind = _mind()
    assert "EARLIER THIS SESSION" not in mind._system_message([])["content"]


# --- what she is doing, for a written turn -----------------------------------


def test_the_now_line_mentions_the_call_she_is_in():
    from src.core.skills.base import SkillRegistry
    from src.core.skills.voice.surface import VoiceSurface

    class DiscordCfg:
        skills = {"discord": {"enabled": True}}
        attention = {}
        persona = {}

    surface = VoiceSurface(DiscordCfg(), bus=None, expression=None)
    surface.initialize()
    surface.active = True
    surface.voice_channel = "vc1"

    mind = _mind()
    registry = SkillRegistry()
    registry.register(surface)
    mind.surfaces = registry
    assert "voice call" in mind.now_line()


def test_the_now_line_says_nothing_about_a_call_she_left():
    from src.core.skills.base import SkillRegistry
    from src.core.skills.voice.surface import VoiceSurface

    class DiscordCfg:
        skills = {"discord": {"enabled": True}}
        attention = {}
        persona = {}

    surface = VoiceSurface(DiscordCfg(), bus=None, expression=None)
    surface.initialize()
    surface.active = True

    mind = _mind()
    registry = SkillRegistry()
    registry.register(surface)
    mind.surfaces = registry
    assert "voice call" not in mind.now_line()


# --- who is in the room ------------------------------------------------------


@pytest.fixture
def social():
    from src.core.memory.store import MemoryStore
    from src.core.skills.social.social import SocialMemory

    class Cfg2:
        skills = {"social_memory": {"enabled": True}}
        attention = {}
        persona = {}

    class Ctx:
        pass

    ctx = Ctx()
    ctx.memory = MemoryStore(":memory:")
    ctx.history_manager = None
    skill = SocialMemory(Cfg2(), bus=None, expression=None, context=ctx)
    skill.initialize()
    skill.active = True
    return skill


def _chat(name, identity="twitch:1"):
    from src.core.perception.types import Author, Perception, PerceptionKind

    platform, _, native = identity.partition(":")
    return Perception(
        PerceptionKind.CHAT, "chat:twitch", f"[{name}] ciao", salience=0.4,
        meta={"tallied": True},
        author=Author(platform=platform, native_id=native, display_name=name),
    )


def test_someone_without_a_card_is_still_named(social):
    """Otherwise the people she has not met yet are invisible in her context."""
    context = social.context_for([_chat("Marco")])
    assert "Marco" in (context or "")


def test_the_room_is_labelled_so_she_can_read_it(social):
    context = social.context_for([_chat("Marco")])
    assert "WHO'S HERE" in (context or "").upper()


def test_a_crowd_does_not_fill_her_context(social):
    batch = [_chat(f"utente{i}", f"twitch:{i}") for i in range(40)]
    context = social.context_for(batch) or ""
    assert context.count("utente") <= 12


def test_an_empty_batch_adds_nothing(social):
    assert social.context_for([]) in (None, "")

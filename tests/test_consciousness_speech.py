"""What reaches the audience: nothing raw from the model, ever."""

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.perception.bus import PerceptionBus
from src.core.skills.base import SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, settle


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0}
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}


def mind() -> Consciousness:
    config = Config()
    c = Consciousness(
        config=config, llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=SkillRegistry(),
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        attention=Attention(config),
    )
    c.context = [c._system_message([])]
    return c


async def speak(c, mood: str, message: str) -> str:
    # local speech is fire-and-forget by design: give the task a chance to run
    result = await c._speak(mood, message)
    await settle()
    return result


async def test_a_clean_line_is_spoken_as_is():
    c = mind()
    await speak(c, "normal", "ma che vuoi")
    assert c.expression.spoken == [("normal", "ma che vuoi", "local")]


async def test_a_leaked_think_block_is_never_pronounced():
    c = mind()
    await speak(c, "normal", "<think>should I be mean</think>ovviamente no")
    assert c.expression.spoken == [("normal", "ovviamente no", "local")]


async def test_special_tokens_never_reach_the_tts():
    c = mind()
    await speak(c, "normal", "eccomi<|endoftext|>")
    assert c.expression.spoken == [("normal", "eccomi", "local")]


async def test_an_all_scaffolding_output_makes_her_stay_silent():
    """Better silence than pronouncing the model's inner monologue."""
    c = mind()
    result = await speak(c, "normal", "<think>only thinking here</think>")
    assert c.expression.spoken == []
    assert result == "Staying silent."


async def test_only_what_was_really_said_enters_the_history():
    c = mind()
    await speak(c, "normal", "<think>hmm</think>ciao")
    assert [m["content"] for m in c.history.messages] == ["ciao"]


async def test_a_missing_mood_falls_back_to_normal():
    c = mind()
    await speak(c, "", "eccomi")
    assert c.expression.spoken[0][0] == "normal"

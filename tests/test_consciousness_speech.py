"""What reaches the audience: nothing raw from the model, ever."""

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.skills.base import SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, settle


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "correlation_timeout": 5.0}
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}


def mind() -> Consciousness:
    config = Config()
    c = Consciousness(
        config=config, llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=SkillRegistry(),
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        memory=MemoryStore(":memory:"), profiler=None, attention=Attention(config),
    )
    c.context = [c._system_message()]
    return c


async def speak(c, mood: str, message: str) -> str:
    # local speech is fire-and-forget by design: give the task a chance to run
    result = await c._speak(mood, message)
    await settle()
    return result


async def test_a_clean_line_is_spoken_as_is():
    c = mind()
    await speak(c, "neutral", "ma che vuoi")
    assert c.expression.spoken == [("neutral", "ma che vuoi", "local")]


async def test_a_leaked_think_block_is_never_pronounced():
    c = mind()
    await speak(c, "neutral", "<think>should I be mean</think>ovviamente no")
    assert c.expression.spoken == [("neutral", "ovviamente no", "local")]


async def test_special_tokens_never_reach_the_tts():
    c = mind()
    await speak(c, "neutral", "eccomi<|endoftext|>")
    assert c.expression.spoken == [("neutral", "eccomi", "local")]


async def test_an_all_scaffolding_output_makes_her_stay_silent():
    """Better silence than pronouncing the model's inner monologue."""
    c = mind()
    result = await speak(c, "neutral", "<think>only thinking here</think>")
    assert c.expression.spoken == []
    assert result == "Staying silent."


async def test_only_what_was_really_said_enters_the_history():
    c = mind()
    await speak(c, "neutral", "<think>hmm</think>ciao")
    assert [m["content"] for m in c.history.messages] == ["ciao"]


async def test_a_missing_mood_falls_back_to_normal():
    c = mind()
    await speak(c, "", "eccomi")
    assert c.expression.spoken[0][0] == "neutral"


async def test_her_context_is_built_while_she_fades_out_not_after():
    """A barge-in waits for the call to say how far she got; nothing before the
    frame needs that answer, so nothing before the frame waits for it."""
    import asyncio
    from types import SimpleNamespace

    from src.core.perception.types import Author, Perception, PerceptionKind
    from tests.fakes import speaks

    c = mind()
    c.llm = FakeLLMClient([speaks("eccomi")])
    order = []
    fading = asyncio.Event()
    loop = asyncio.get_running_loop()

    async def interrupt(ramp_ms=200):
        order.append("fade started")
        await fading.wait()
        c.expression.interrupted = SimpleNamespace(
            complete=False, text="stavo dicendo una cosa lunga", played_ms=500, sent_ms=2000)
        order.append("fade over")

    def dynamic(batch):
        # on a worker thread: the fade is only let finish once this has run
        order.append("context")
        loop.call_soon_threadsafe(fading.set)
        return []

    c.expression.is_speaking = True
    c.expression.interrupt = interrupt
    c.surfaces.dynamic_context = dynamic
    heard = Perception(PerceptionKind.VOICE, "voice:discord", "[marco] (voice): aspetta",
                       salience=0.9, author=Author("discord", "1", "marco"))

    # bounded: were the context built only after the fade, the two would wait on each other
    await asyncio.wait_for(c._turn([heard]), timeout=5)

    assert order.index("context") < order.index("fade over"), \
        "the context waited for her to finish fading out"
    assert "fade started" in order
    # the frame still knows where she was cut off
    frame = next(m for m in c.llm.calls[0] if m["role"] == "user")
    assert "[YOU WERE CUT OFF]" in frame["content"]

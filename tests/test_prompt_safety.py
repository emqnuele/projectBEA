"""The prompts stay editable files. They just cannot fail silently.

Everything under data/prompts/ is meant to be opened and edited — that is the
point of keeping them as files. What was missing is the floor: a deleted file
used to leave an empty string in the prompt, a mood table that could drift from
the code that enforces it, and a manual that could name a tool nobody registers
any more. All three failed with a log line nobody reads.
"""

import pytest

from src.core.mind.moods import (
    DEFAULT_MOOD,
    MOODS,
    mood_table,
    normalize_mood,
)
from src.core.mind.operating import BUILTIN_OPERATING, missing_tools
from src.utils.prompts import load_text

# --- a missing file has a floor ---------------------------------------------


def test_a_missing_prompt_falls_back_to_what_it_was_given():
    assert load_text("data/prompts/nope.md", fallback="fallback text") == "fallback text"


def test_a_present_prompt_still_wins(tmp_path):
    path = tmp_path / "soul.md"
    path.write_text("the real thing")
    assert load_text(str(path), fallback="fallback text") == "the real thing"


def test_an_empty_file_falls_back_too(tmp_path):
    """An empty operating manual is the same failure as a missing one."""
    path = tmp_path / "operating.md"
    path.write_text("   \n\n  ")
    assert load_text(str(path), fallback="fallback text") == "fallback text"


def test_the_builtin_manual_is_not_empty():
    assert len(BUILTIN_OPERATING) > 500


def test_the_builtin_manual_still_teaches_her_to_speak():
    assert "speak" in BUILTIN_OPERATING
    assert "stay_silent" in BUILTIN_OPERATING


def test_the_brain_never_ends_up_with_no_manual(tmp_path, monkeypatch):
    from src.core.brain import AIVtuberBrain

    class Config:
        operating_prompt_path = str(tmp_path / "gone.md")
        system_prompt_path = str(tmp_path / "also-gone.md")

    rules = AIVtuberBrain._load_operating_rules(type("B", (), {"config": Config()})())
    assert "speak" in rules


# --- one list of moods -------------------------------------------------------


def test_there_is_one_list_of_moods():
    assert MOODS
    assert DEFAULT_MOOD in MOODS


def test_every_mood_is_a_plain_lowercase_id():
    for mood in MOODS:
        assert mood == mood.lower()
        assert " " not in mood


def test_a_known_mood_passes_through():
    assert normalize_mood("angry") == "angry"


def test_case_and_padding_do_not_matter():
    assert normalize_mood("  ANGRY ") == "angry"


@pytest.mark.parametrize("said,expected", [
    ("happy", "love"),
    ("sad", "cry"),
    ("excited", "love"),
    ("neutral", "normal"),
    ("disgusted", "ew"),
    ("surprised", "shock"),
])
def test_a_near_miss_lands_on_the_closest_real_mood(said, expected):
    """The model will invent moods. An avatar that silently fails to change is
    worse than picking the nearest one."""
    assert normalize_mood(said) == expected


def test_something_unrecognisable_falls_back_rather_than_breaking():
    assert normalize_mood("zxcvbnm") == DEFAULT_MOOD
    assert normalize_mood("") == DEFAULT_MOOD
    assert normalize_mood(None) == DEFAULT_MOOD


def test_the_table_shown_to_her_covers_every_mood():
    table = mood_table()
    for mood in MOODS:
        assert f"`{mood}`" in table


# --- the code enforces what the manual explains ------------------------------


def test_the_speak_tool_only_accepts_real_moods():
    from src.core.mind.tools import MindTools
    from src.core.skills.base import SkillRegistry

    tools = MindTools(SkillRegistry(), speak=lambda **k: "", stay_silent=lambda **k: "")
    speak = tools.registry().get("speak")
    assert speak.parameters["properties"]["mood"]["enum"] == list(MOODS)


def test_the_default_avatar_map_has_a_slot_for_every_mood():
    from src.core.config import BrainConfig

    assert set(BrainConfig().avatar_map) >= set(MOODS)


# --- the manual and the registry cannot drift apart --------------------------


def test_nothing_is_missing_from_the_real_manual():
    assert missing_tools(BUILTIN_OPERATING, ["speak", "stay_silent"]) == []


def test_a_tool_the_manual_never_mentions_is_reported():
    assert missing_tools("call speak to talk", ["speak", "teleport"]) == ["teleport"]


def test_the_check_is_only_given_the_tools_the_manual_owns():
    """A skill's tools are explained by its own context_section, so the startup
    check hands over the mind's terminal set and nothing else — a set defined in
    code, which means it follows a rename."""
    from src.core.consciousness import Consciousness

    assert Consciousness._TERMINAL_TOOLS == {"speak", "stay_silent"}
    assert missing_tools(BUILTIN_OPERATING, sorted(Consciousness._TERMINAL_TOOLS)) == []


def test_the_shipped_manual_names_every_terminal_tool():
    """If someone renames `speak`, this is what tells them before a stream does."""
    from pathlib import Path

    shipped = Path("data/prompts/operating.md").read_text()
    assert missing_tools(shipped, ["speak", "stay_silent"]) == []


# --- the mind actually uses the normaliser -----------------------------------


async def test_an_invented_mood_is_normalised_before_it_reaches_the_avatar():
    """`speak(mood="happy")` used to reach set_mood_avatar and match nothing."""
    from src.core.attention.gate import Attention
    from src.core.consciousness import Consciousness
    from src.core.perception.bus import PerceptionBus
    from src.core.skills.base import SkillRegistry
    from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, settle

    class Config:
        consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                         "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0}
        attention = {}
        skills = {}

    expression = FakeExpression()
    mind = Consciousness(
        config=Config(), llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=expression, surfaces=SkillRegistry(), history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "", operating_getter=lambda: "",
        attention=Attention(Config()),
    )
    await mind._speak("happy", "ciao")
    await settle()
    assert expression.spoken[0][0] == "love"


async def test_a_real_mood_is_left_alone():
    from src.core.attention.gate import Attention
    from src.core.consciousness import Consciousness
    from src.core.perception.bus import PerceptionBus
    from src.core.skills.base import SkillRegistry
    from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, settle

    class Config:
        consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                         "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0}
        attention = {}
        skills = {}

    expression = FakeExpression()
    mind = Consciousness(
        config=Config(), llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=expression, surfaces=SkillRegistry(), history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "", operating_getter=lambda: "",
        attention=Attention(Config()),
    )
    await mind._speak("angry", "ciao")
    await settle()
    assert expression.spoken[0][0] == "angry"


# --- the shipped file and the code cannot drift ------------------------------


def test_the_shipped_manual_lists_exactly_the_moods_the_code_knows():
    """The table is prose for whoever edits the file; this is what stops it
    saying something the enum will refuse."""
    import re
    from pathlib import Path

    shipped = Path("data/prompts/operating.md").read_text()
    listed = set(re.findall(r"^\| `([a-z]+)`", shipped, re.M))
    assert listed == set(MOODS)


# --- the startup check ------------------------------------------------------


def _brain_stub(manual: str, events):
    from src.core.brain import AIVtuberBrain

    class Stub:
        pass

    stub = Stub()
    stub.event_manager = events
    stub.system_prompt = manual
    stub.check_prompt_integrity = AIVtuberBrain.check_prompt_integrity.__get__(stub)
    return stub


class Events:
    def __init__(self):
        self.published = []

    def publish(self, category, source, message, metadata=None):
        self.published.append((category, source, message, metadata or {}))


def test_a_healthy_prompt_says_nothing():
    events = Events()
    assert _brain_stub(BUILTIN_OPERATING, events).check_prompt_integrity() == []
    assert events.published == []


def test_a_prompt_that_forgot_a_tool_is_reported_loudly():
    events = Events()
    missing = _brain_stub("just a soul, no manual", events).check_prompt_integrity()
    assert set(missing) == {"speak", "stay_silent"}
    assert events.published, "a broken prompt must reach the dashboard, not just a log"
    assert "speak" in events.published[0][2]


def test_the_report_is_an_error_the_dashboard_can_show():
    from src.core.events import EventCategory

    events = Events()
    _brain_stub("nothing useful", events).check_prompt_integrity()
    assert events.published[0][0] is EventCategory.ERROR

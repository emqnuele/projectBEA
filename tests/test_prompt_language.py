"""The prompts carry a language, and none of them carries a hardcoded name.

Two separate leaks. The system prompt never said which language to answer in,
so ~16k characters of English instructions outweighed one Japanese message and
she replied in English. And the two background prompts — the diary and the
dreamer — were the only ones that spelled "Bea" out instead of using `{name}`,
so a renamed persona had a subconscious that still called her something else.
"""

import re
from pathlib import Path

from src.core.language import directive
from src.core.persona import DEFAULT_NAME, Persona
from src.core.skills.dream.dreamer import DEFAULT_PROMPT_PATH as DREAMER_PROMPT
from src.core.skills.memory.generator import DEFAULT_PROMPT_PATH as DIARY_PROMPT
from src.utils.prompts import load_text

PROMPTS = Path("data/prompts")

# every prompt that reaches a model, wherever it is loaded from
EVERY_PROMPT = sorted(PROMPTS.glob("*.md"))


# --- no name is written into a prompt ---------------------------------------


def test_the_prompts_we_ship_are_where_the_editable_ones_live():
    """These two used to sit in `src/`, invisible to the dashboard and the updater."""
    assert Path(DIARY_PROMPT) == PROMPTS / "diary.md"
    assert Path(DREAMER_PROMPT) == PROMPTS / "dreamer.md"
    assert Path(DIARY_PROMPT).is_file()
    assert Path(DREAMER_PROMPT).is_file()
    assert not Path("src/core/skills/memory/diary_prompt.txt").exists()
    assert not Path("src/core/skills/dream/dreamer_prompt.txt").exists()


def test_no_shipped_prompt_spells_her_name_out():
    """Renaming her must not leave one prompt calling her something else."""
    # a whole word: "beat" in a prompt is a word, not her
    name = re.compile(rf"\b{re.escape(DEFAULT_NAME)}\b", re.IGNORECASE)
    offenders = [p.name for p in EVERY_PROMPT
                 if name.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], offenders


def test_a_renamed_persona_reaches_the_background_prompts():
    persona = Persona(name="Mika")
    for path in (DIARY_PROMPT, DREAMER_PROMPT):
        filled = persona.fill(load_text(path))
        assert "Mika" in filled
        assert "{name}" not in filled


def test_the_json_shape_survives_being_filled():
    """`fill` must not touch the braces the output format is written in."""
    filled = Persona(name="Mika").fill(load_text(DREAMER_PROMPT))
    assert '"self_facts": []' in filled
    assert '"ttl_days": 3' in filled


# --- every prompt is told which language to write in -------------------------


def test_the_background_prompts_have_a_language_slot():
    for path in (DIARY_PROMPT, DREAMER_PROMPT):
        assert "{language}" in load_text(path), path


def test_the_diary_is_told_which_language_to_write_in():
    from src.core.skills.memory.generator import DiaryGenerator

    built = []

    class FakeLLM:
        async def complete_json(self, payload, system=None, history=None):
            built.append(system)
            return {}

    import asyncio
    asyncio.run(DiaryGenerator(FakeLLM(), language="ja").generate_diary(
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hi"}]))

    assert "Japanese" in built[0]
    assert "{language}" not in built[0]
    assert "{date}" not in built[0]


def test_detection_tells_a_background_pass_to_follow_the_conversation():
    from src.core.skills.memory.generator import DiaryGenerator

    built = []

    class FakeLLM:
        async def complete_json(self, payload, system=None, history=None):
            built.append(system)
            return {}

    import asyncio
    asyncio.run(DiaryGenerator(FakeLLM(), language="auto").generate_diary(
        [{"role": "user", "content": "ciao"}, {"role": "assistant", "content": "ciao"}]))

    assert "language the conversation is in" in built[0]


def test_the_handoff_recap_is_written_in_the_right_language():
    from src.core.mind.handoff import HandoffWorker

    worker = HandoffWorker(language="it")
    assert worker.language == "it"


def test_the_person_profiler_is_told_too():
    from src.core.memory.profiler import Profiler

    assert Profiler(None, None, language="ja").language == "ja"


# --- the system prompt ------------------------------------------------------


def test_the_system_prompt_carries_the_directive():
    """Assembled the way the mind assembles it, not asserted on a substring."""
    from src.utils.prompts import compose

    soul = load_text("data/prompts/soul.md")
    operating = load_text("data/prompts/operating.md")
    built = compose(soul, directive("it"), operating)

    assert "language you were addressed in" in built
    assert "speak Italiano" in built
    # it sits above the operating manual, so the manual's own English does not
    # get the last word on how to answer
    assert built.index("## LANGUAGE") < built.index(operating[:40])

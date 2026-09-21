"""The morning picks conversations up from the dream's recaps.

`_yesterday` used to read the rolling summaries table, written every 30
messages by a background pass. That writer is gone: the same thread the
consolidation already keeps per conversation key is what the morning reads,
newest first.
"""

from types import SimpleNamespace

from src.core.memory.store import MemoryStore
from src.core.skills.dream.surface import DreamSkill


class Config:
    def __init__(self):
        self.skills = {"dream": {"enabled": True}}
        self.language = ""


def skill_for(memory):
    context = SimpleNamespace(memory=memory, consciousness=None, skill_registry=None,
                              history_manager=None, model_for=None)
    skill = DreamSkill(Config(), bus=None, expression=None, context=context)
    skill.initialize()
    skill.active = True
    return skill


def recap(memory, key, text, at):
    memory.db.execute(
        "INSERT INTO memories (scope, scope_key, text, source, created_at) "
        "VALUES ('conversation', ?, ?, 'person', ?)", (key, text, at),
    )


def test_the_morning_finds_the_latest_conversation_recap():
    memory = MemoryStore(":memory:")
    try:
        recap(memory, "telegram:55", "marco aspetta la patch di minecraft", 100.0)
        recap(memory, "discord:77", "luca organizza la serata film", 200.0)

        lines = skill_for(memory)._yesterday()

        assert lines[0].startswith("last time in discord:77")
        assert "luca organizza la serata film" in lines[0]
        assert any("telegram:55" in line for line in lines)
    finally:
        memory.close()


def test_an_empty_store_means_a_quiet_morning():
    memory = MemoryStore(":memory:")
    try:
        assert skill_for(memory)._yesterday() == []
    finally:
        memory.close()


def test_the_morning_pass_surfaces_the_recap_as_a_hot_fact():
    memory = MemoryStore(":memory:")
    try:
        recap(memory, "telegram:55", "marco aspetta la patch di minecraft", 100.0)
        skill = skill_for(memory)

        skill.morning_pass()

        assert any("marco aspetta la patch" in f.text for f in memory.hot.active())
    finally:
        memory.close()

"""Does the whole thing actually assemble?

Every skill is tested on its own, which says nothing about whether the brain
hands each one what it expects. This builds the real composition root with
fakes at the edges — no network, no audio, no subprocess — and is the test
that catches a skill reaching for an attribute the brain does not have.
"""

import pytest

from src.core.brain import SKILL_CLASSES, AIVtuberBrain
from src.core.config import BrainConfig
from tests.fakes import FakeLLMClient


class FakeRegistry:
    def __init__(self):
        self.client = FakeLLMClient()

    def get(self, role="mind"):
        return self.client

    def reload_config(self, config):
        pass


class FakeTTS:
    def synthesize(self, *a, **k):
        return b""

    def reload_config(self, config):
        pass


class FakeOBS:
    connected = False

    def connect(self, *a, **k):
        return False

    def reload_config(self, config):
        pass


class FakeSTT:
    def transcribe(self, path):
        return ""

    def reload_config(self, config):
        pass


class FakeEmbedder:
    """Deterministic and instant. The real one downloads 100MB of ONNX."""

    model_name = "test-embedder"
    dim = 4

    def __init__(self, *args, **kwargs):
        pass

    def embed(self, texts):
        return [[float(len(t) % 7), 1.0, 0.0, 0.5] for t in texts]


@pytest.fixture
def brain(tmp_path, monkeypatch):
    from src.core import config as config_module
    from src.core.memory import embedder as embedder_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")
    monkeypatch.setattr(embedder_module, "FastEmbedEmbedder", FakeEmbedder)

    config = BrainConfig()
    config.skills["memory"]["db_path"] = ":memory:"
    # every platform stays off: this is about wiring, not connections
    for key in ("discord", "telegram", "twitch", "minecraft", "donations", "dream"):
        config.skills.setdefault(key, {})["enabled"] = False

    engine = AIVtuberBrain(config, FakeRegistry(), FakeTTS(), FakeSTT(), FakeOBS())
    engine._build_consciousness()
    return engine


def test_every_skill_is_built_and_registered(brain):
    names = {type(s) for s in brain.skill_registry.all()}
    assert names == set(SKILL_CLASSES)


def test_nothing_blew_up_on_the_way(brain):
    assert brain.consciousness is not None
    assert brain.conversations is not None
    assert brain.perception_bus is not None


def test_the_slow_clock_is_wired(brain):
    assert brain.rhythm is not None
    assert brain.rhythm.agenda is not None
    assert brain.rhythm.spontaneous is not None


def test_the_gate_can_read_the_conversations(brain):
    """Without this the follow-up gate silently never fires."""
    assert brain.attention.conversations is brain.memory.conversations


def test_she_has_an_address_book(brain):
    assert brain.reach.surfaces is brain.skill_registry


def test_the_presence_skill_found_its_registry(brain):
    presence = brain.skill_registry.get("social:presence")
    assert presence is not None
    assert presence.reach.surfaces is brain.skill_registry


def test_telegram_got_the_ear_it_needs_for_voice_notes(brain):
    telegram = brain.skill_registry.get("chat:telegram")
    assert telegram.stt is brain.stt


def test_the_agenda_survives_a_round_trip(brain):
    brain.memory.agenda.add("chiedere a ema com'è andata", due_ts=1.0)
    assert [i.note for i in brain.memory.agenda.due(now=2.0)] == ["chiedere a ema com'è andata"]


async def test_a_tick_with_nothing_to_do_is_harmless(brain):
    assert await brain.rhythm.run_once() == 0


def test_the_settings_schema_covers_every_toggleable_skill(brain):
    """A skill you cannot configure from the dashboard may as well not exist."""
    from src.core.settings_schema import SECTIONS

    described = {s.key for s in SECTIONS}
    toggles = {s.skill_name for s in brain.skill_registry.toggleable()}
    # monologue and social_memory have no knobs worth a screen of their own
    assert toggles - described <= {"monologue", "social_memory", "memory"}

"""The mind must be handed the things it writes memory with.

A refactor once moved the durable logging into `Consciousness` and left its
dependency behind in the class that was deleted. Nothing broke loudly: the two
methods that write the stream start with `if self.memory is None: return`, so
she ran for days with the log silently off. These tests build the real
composition root and assert the wiring exists, which is the only thing that
would have caught it.
"""

import pytest

from src.core.brain import AIVtuberBrain
from src.core.config import BrainConfig
from src.core.events import EventManager
from src.core.memory.store import MemoryStore
from src.core.persona import persona_of
from src.utils.history_manager import HistoryManager
from tests.fakes import FakeExpression, FakeLLMClient


class Brain:
    """Everything `_build_consciousness` reads, and nothing else."""

    def __init__(self, storage_dir: str):
        self.config = BrainConfig()
        self.config.consciousness = {"enabled": True}
        self.llm = FakeLLMClient()
        self.expression = FakeExpression()
        self.memory = MemoryStore(":memory:")
        self.history_manager = HistoryManager(storage_dir=storage_dir)
        self.event_manager = EventManager()
        self.soul = ""
        self.skill_registry = None
        self.consciousness = None

    @property
    def persona(self):
        return persona_of(self.config)

    @property
    def surface_registry(self):
        return self.skill_registry

    def model_for(self, _role):
        return self.llm

    def _load_operating_rules(self) -> str:
        return ""


@pytest.fixture
def brain(tmp_path):
    built = Brain(str(tmp_path / "conversations"))
    yield built
    built.memory.close()


def test_the_mind_is_given_the_durable_log(brain):
    AIVtuberBrain._build_consciousness(brain)

    assert brain.consciousness.memory is brain.memory


def test_the_mind_is_given_the_profiler(brain):
    AIVtuberBrain._build_consciousness(brain)

    assert brain.consciousness.profiler is brain.profiler

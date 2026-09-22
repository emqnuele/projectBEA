"""The "does this work" buttons test what the engine really uses."""

from fastapi.testclient import TestClient

from src.core.agent.types import AssistantMessage
from src.web import deps
from src.web.app import app


class PooledModel:
    """Shaped like `RotatingClient`: `complete` and nothing more."""

    def __init__(self):
        self.asked = []

    async def complete(self, messages, tools=None, response_format=None):
        self.asked.append(messages)
        return AssistantMessage(content="ok")


class Config:
    llm_provider = "openrouter"


class BrainStub:
    def __init__(self):
        self.config = Config()
        self.llm = PooledModel()


def test_the_model_probe_works_on_a_pool_of_models():
    """A mind pool of two or more models is a client without `chat`, and the
    probe used to report every such setup as broken."""
    stub = BrainStub()
    previous = deps.brain_instance
    deps.brain_instance = stub
    try:
        answer = TestClient(app).post("/test/llm").json()
    finally:
        deps.brain_instance = previous

    assert answer["ok"] is True
    assert answer["detail"] == "ok"
    assert len(stub.llm.asked) == 1

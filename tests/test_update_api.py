"""The dashboard's door to the updater.

`POST /update/apply` executes code — a pull, a `uv sync`, an `npm install` that
runs whatever scripts the new version declares. That is legitimate and it is
what the button is for, but it means the interesting tests here are not the
happy path: they are the refusals, and the fact that a file name arriving from
a browser never becomes a path we write to.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.core.config import BrainConfig
from src.core.update import runner


@pytest.fixture
def client(tmp_path, monkeypatch):
    from src.web import app as web
    from src.web import deps
    from src.web.routers import updates

    prompts = tmp_path / "data" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "soul.md").write_text("mine", encoding="utf-8")

    class BrainStub:
        def __init__(self):
            self.config = BrainConfig()
            self.reloads = 0
            self.skill_registry = None
            self.history_manager = SimpleNamespace(session_id="test")
            self.is_speaking = False
            self.is_sleeping = False

        def reload_configuration(self):
            self.reloads += 1

    brain = BrainStub()
    monkeypatch.setattr(deps, "brain_instance", brain)
    monkeypatch.setattr(updates, "ROOT", tmp_path)
    monkeypatch.setattr(updates, "_run", None)
    monkeypatch.setattr(runner, "_cached", None)

    with TestClient(web.app) as test_client:
        test_client.brain = brain
        test_client.root = tmp_path
        yield test_client


def test_a_plain_directory_reports_why_it_cannot_update(client):
    body = client.get("/update").json()

    assert body["supported"] is False
    assert body["can_apply"] is False
    # which refusal it is depends on the machine running the suite — a box
    # without git answers before the checkout is ever looked at
    assert body["reason"]


def test_a_machine_without_git_says_so_rather_than_failing(client, monkeypatch):
    """Nothing in the engine needs git, so a box without it loses the updater
    and nothing else. The screen has to explain that instead of going blank."""
    from src.core.update.gitrepo import Repo

    monkeypatch.setattr(Repo, "available", lambda self: False)
    body = client.get("/update?force=true").json()

    assert body["supported"] is False
    assert body["can_apply"] is False
    assert "git is not installed" in body["reason"]
    assert body["reviews"] == []


def test_the_check_can_be_switched_off(client):
    client.brain.config.updates = {"check": False, "allow_web_apply": True}

    body = client.get("/update").json()

    assert body["supported"] is False
    assert "switched off" in body["reason"]


def test_applying_from_the_dashboard_can_be_revoked(client):
    client.brain.config.updates = {"check": True, "allow_web_apply": False}

    response = client.post("/update/apply")

    assert response.status_code == 403
    assert "bea --update" in response.json()["detail"]


def test_a_config_without_the_block_still_works(client):
    """A config.json written before this feature existed must not 500 the screen."""
    delattr(client.brain.config, "updates")

    assert client.get("/update").status_code == 200


def test_a_second_apply_while_one_runs_is_refused(client, monkeypatch):
    from src.web.routers import updates

    monkeypatch.setattr(updates, "_run", {"state": "running", "steps": [], "report": None})

    assert client.post("/update/apply").status_code == 409


def test_there_is_nothing_to_review_on_a_clean_install(client):
    assert client.get("/update/reviews").json() == {"reviews": []}


def test_an_unknown_review_is_not_found(client):
    assert client.get("/update/reviews/soul.md").status_code == 404


@pytest.mark.parametrize("name", ["../../../etc/passwd", "..%2fconfig.json", "soul.md", "operating.md"])
def test_a_name_from_the_browser_never_becomes_a_path(client, name):
    """Only names the updater itself flagged are accepted, so nothing is ever joined.

    Asserted against the resolver rather than the route, because a traversal in
    a URL is normalised away long before it reaches a handler — the property
    worth pinning is that an unflagged name has no path at all, whatever it
    looks like.
    """
    from fastapi import HTTPException

    from src.web.routers.updates import _review_path

    with pytest.raises(HTTPException) as refused:
        _review_path(name)
    assert refused.value.status_code == 404


def test_a_nonsense_resolution_is_rejected(client):
    assert client.post("/update/reviews/soul.md", json={"choice": "burn it"}).status_code == 422


def test_the_status_endpoint_carries_the_version(client):
    body = client.get("/status").json()

    assert body["version"] and body["version"] != "unknown"

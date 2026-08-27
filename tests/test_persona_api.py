"""Editing who she is, from the dashboard.

The soul stays a file — that is the whole point, it is meant to be openable.
This is the other way in: a screen that reads and writes that one file, plus
the structured bits (name, pronouns) that live in config because six other
paths need them.

Writing files over HTTP is the part to be careful about, so most of what is
tested here is what the endpoint refuses.
"""

import pytest

from src.core.config import BrainConfig
from src.core.persona import DEFAULT_NAME


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.core import config as config_module
    from src.web import app as web

    prompts = tmp_path / "data" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "soul.md").write_text("# SOUL\n\nYou are **{name}**.")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")

    class BrainStub:
        def __init__(self):
            from src.core.memory.store import MemoryStore
            from tests.fakes import FakeLLMClient

            self.config = BrainConfig()
            self.config.soul_path = "data/prompts/soul.md"
            self.reloads = 0
            self.memory = MemoryStore(":memory:")
            self.llm = FakeLLMClient(json_script=[
                {"identity": ["Sarcastica e curiosa."], "voice": ["Corta e secca."]},
            ])

        # the real brain has this; a stub without it hides a wiring break
        def model_for(self, role="background"):
            return self.llm

        @property
        def persona(self):
            from src.core.persona import persona_of

            return persona_of(self.config)

        def reload_configuration(self):
            self.reloads += 1

        async def set_skill_enabled(self, name, enable):
            pass

    stub = BrainStub()
    previous = web.brain_instance
    web.brain_instance = stub
    try:
        yield TestClient(web.app), stub, tmp_path
    finally:
        web.brain_instance = previous


# --- reading -----------------------------------------------------------------


def test_the_persona_is_served(client):
    api, _, _ = client
    body = api.get("/persona").json()
    assert body["name"] == DEFAULT_NAME
    assert body["pronouns"] == "she/her"


def test_the_soul_comes_with_it(client):
    api, _, _ = client
    assert "You are" in api.get("/persona").json()["soul"]


def test_the_words_she_answers_to_are_shown(client):
    api, _, _ = client
    body = api.get("/persona").json()
    assert body["trigger_words"] == ["bea"]
    assert body["derived_triggers"] is True


def test_a_missing_soul_file_reads_as_empty_not_as_an_error(client, tmp_path):
    api, _, _ = client
    (tmp_path / "data/prompts/soul.md").unlink()
    assert api.get("/persona").status_code == 200
    assert api.get("/persona").json()["soul"] == ""


# --- writing -----------------------------------------------------------------


def test_the_soul_is_written_to_the_file(client, tmp_path):
    api, _, _ = client
    res = api.put("/persona", json={"soul": "# SOUL\n\nYou are **{name}**, a gremlin."})
    assert res.status_code == 200
    assert "gremlin" in (tmp_path / "data/prompts/soul.md").read_text()


def test_saving_reloads_her_so_the_change_is_live(client):
    api, stub, _ = client
    api.put("/persona", json={"soul": "new soul"})
    assert stub.reloads == 1


def test_the_name_is_written_to_the_config(client):
    api, stub, _ = client
    api.put("/persona", json={"name": "Luna"})
    assert stub.config.persona["name"] == "Luna"


def test_renaming_her_changes_what_she_answers_to(client):
    api, _, _ = client
    api.put("/persona", json={"name": "Luna"})
    assert api.get("/persona").json()["trigger_words"] == ["luna"]


def test_words_you_set_yourself_are_kept(client):
    api, stub, _ = client
    api.put("/persona", json={"name": "Luna", "trigger_words": ["lu", "lulu"]})
    assert stub.config.attention["trigger_words"] == ["lu", "lulu"]
    assert api.get("/persona").json()["derived_triggers"] is False


def test_clearing_them_goes_back_to_following_the_name(client):
    api, _, _ = client
    api.put("/persona", json={"name": "Luna", "trigger_words": ["lu"]})
    api.put("/persona", json={"trigger_words": []})
    assert api.get("/persona").json()["trigger_words"] == ["luna"]


def test_a_partial_write_leaves_the_rest_alone(client, tmp_path):
    api, stub, _ = client
    api.put("/persona", json={"name": "Luna"})
    assert "You are" in (tmp_path / "data/prompts/soul.md").read_text()
    assert stub.config.persona["pronouns"] == "she/her"


# --- keeping the previous version --------------------------------------------


def test_the_previous_soul_is_kept_next_to_it(client, tmp_path):
    """A bad edit from a text box must not be the end of a persona."""
    api, _, _ = client
    api.put("/persona", json={"soul": "something worse"})
    assert (tmp_path / "data/prompts/soul.md.bak").read_text().startswith("# SOUL")


def test_the_backup_is_the_one_before_the_last_write(client, tmp_path):
    api, _, _ = client
    api.put("/persona", json={"soul": "first"})
    api.put("/persona", json={"soul": "second"})
    assert (tmp_path / "data/prompts/soul.md.bak").read_text() == "first"


# --- what it refuses ---------------------------------------------------------


def test_it_will_not_write_outside_the_data_directory(client, tmp_path):
    """The endpoint takes no path, but the configured one must still be checked."""
    api, stub, _ = client
    stub.config.soul_path = "../../etc/bea-soul.md"
    assert api.put("/persona", json={"soul": "nope"}).status_code == 403


def test_it_will_not_write_an_absolute_path(client, stub_path=None):
    api, stub, _ = client
    stub.config.soul_path = "/etc/bea-soul.md"
    assert api.put("/persona", json={"soul": "nope"}).status_code == 403


def test_a_soul_longer_than_a_persona_should_be_is_refused(client):
    api, _, _ = client
    assert api.put("/persona", json={"soul": "x" * 200_000}).status_code == 413


def test_a_nameless_persona_is_refused(client):
    api, _, _ = client
    assert api.put("/persona", json={"name": "   "}).status_code == 422


def test_an_unknown_field_is_refused_rather_than_ignored(client):
    api, _, _ = client
    assert api.put("/persona", json={"colour": "blue"}).status_code == 422


def test_a_refused_write_leaves_the_file_untouched(client, tmp_path):
    api, _, _ = client
    api.put("/persona", json={"soul": "x" * 200_000})
    assert "You are" in (tmp_path / "data/prompts/soul.md").read_text()


# --- has it ever been set up? ------------------------------------------------


def test_a_fresh_install_reports_it_has_not_been_set_up(client, tmp_path):
    """The onboarding needs to know, and "the file exists" is not the answer —
    it always exists, we ship it."""
    api, _, _ = client
    (tmp_path / "data/prompts/soul.md").write_text(
        __import__("pathlib").Path(__file__).parents[1].joinpath(
            "data/prompts/soul.md").read_text()
    )
    assert api.get("/persona").json()["customised"] is False


def test_an_edited_soul_counts_as_set_up(client):
    api, _, _ = client
    api.put("/persona", json={"soul": "# SOUL\n\nYou are a gremlin called {name}."})
    assert api.get("/persona").json()["customised"] is True


# --- onboarding --------------------------------------------------------------


def test_the_questions_are_served(client):
    api, _, _ = client
    body = api.get("/onboarding").json()
    assert [q["key"] for q in body["questions"]][0] == "name"


def test_a_fresh_install_is_told_it_needs_setting_up(client, tmp_path):
    api, _, _ = client
    from pathlib import Path

    (tmp_path / "data/prompts/soul.md").write_text(
        Path(__file__).parents[1].joinpath("data/prompts/soul.md").read_text()
    )
    assert api.get("/onboarding").json()["needed"] is True


def test_once_the_soul_is_written_it_is_not_needed(client):
    api, _, _ = client
    api.put("/persona", json={"soul": "# SOUL\n\nYou are a gremlin."})
    assert api.get("/onboarding").json()["needed"] is False


def test_skipping_it_is_remembered(client):
    api, _, _ = client
    assert api.post("/onboarding/skip").status_code == 200
    assert api.get("/onboarding").json()["needed"] is False


def test_a_draft_is_generated_without_saving_anything(client, tmp_path):
    api, _, _ = client
    res = api.post("/onboarding/draft", json={
        "name": "Luna", "adjectives": "sarcastica, curiosa",
    })
    assert res.status_code == 200
    assert "Sarcastica e curiosa." in res.json()["soul"]
    # nothing is committed until you press save
    assert "Sarcastica" not in (tmp_path / "data/prompts/soul.md").read_text()


def test_a_draft_needs_a_name(client):
    api, _, _ = client
    assert api.post("/onboarding/draft", json={"adjectives": "x"}).status_code == 422


def test_the_draft_keeps_the_name_as_a_placeholder(client):
    api, _, _ = client
    body = api.post("/onboarding/draft", json={"name": "Luna"}).json()
    assert "{name}" in body["soul"]
    assert body["name"] == "Luna"


# --- the dashboard and the engine agree on this too --------------------------


def test_the_menu_has_a_personality_screen():
    import re
    from pathlib import Path

    nav = Path(__file__).parents[1].joinpath("src/web/frontend/src/lib/nav.js").read_text()
    assert "id: 'personality'" in nav
    sections = Path(__file__).parents[1].joinpath(
        "src/web/frontend/src/pages/settings/sections.jsx").read_text()
    assert re.search(r"^\s+personality:", sections, re.M)


def test_the_onboarding_route_exists():
    from pathlib import Path

    app = Path(__file__).parents[1].joinpath("src/web/frontend/src/App.jsx").read_text()
    assert 'path="onboarding"' in app


def test_the_dashboard_asks_for_every_endpoint_that_exists():
    """A typo in the client is a 404 the user sees and nobody else does."""
    from pathlib import Path

    client = Path(__file__).parents[1].joinpath("src/web/frontend/src/api.js").read_text()
    for path in ("/persona", "/onboarding", "/onboarding/draft", "/onboarding/skip"):
        assert f"'{path}'" in client or f'`{path}' in client

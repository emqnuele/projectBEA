"""Places she remembers: per world, on disk, and the one where she died."""

import asyncio
import json

import pytest

from src.core.skills.minecraft.notebook import Notebook
from src.core.skills.minecraft.places import DEATH, Places
from src.core.skills.minecraft.tools import build_minecraft_tools


class FakeClient:
    def __init__(self, x=10.5, y=-57.0, z=3.2, server="play.example.net", dimension="minecraft:overworld"):
        self.latest_state = {"player": {"position": {"x": x, "y": y, "z": z}},
                             "world": {"server": server, "dimension": dimension}}
        self.sent = []

    async def execute(self, action, params, timeout=None):
        self.sent.append((action, params, timeout))
        return "SUCCESS: Arrived."


def call(registry, tool, **args):
    out = registry.get(tool).handler(**args)
    return asyncio.run(out) if asyncio.iscoroutine(out) else out


@pytest.fixture
def book(tmp_path):
    return Places(tmp_path / "places.json")


def test_a_place_is_kept_where_she_stands_and_walked_back_to(book, tmp_path):
    client = FakeClient()
    tools = build_minecraft_tools(client, Notebook(), places=book)
    assert call(tools, "remember_place", name="My Home") == "remembered my_home at (10, -57, 3)."
    saved = json.loads((tmp_path / "places.json").read_text())
    assert saved["play.example.net"]["my_home"]["x"] == 10

    client.latest_state["player"]["position"] = {"x": 0.5, "y": -57.0, "z": 0.5}
    assert call(tools, "go_to_place", name="my home") == "SUCCESS: Arrived."
    assert client.sent[-1][:2] == ("move_to", {"x": 10, "y": -57, "z": 3})


def test_places_belong_to_their_world(book):
    here = build_minecraft_tools(FakeClient(server="a.example"), Notebook(), places=book)
    there = build_minecraft_tools(FakeClient(server="b.example"), Notebook(), places=book)
    call(here, "remember_place", name="home")
    assert call(there, "go_to_place", name="home") == \
        "ERROR: you remember no place called home; you know: none yet."


def test_a_place_in_another_dimension_is_not_walked_to(book):
    client = FakeClient()
    tools = build_minecraft_tools(client, Notebook(), places=book)
    call(tools, "remember_place", name="base")
    client.latest_state["world"]["dimension"] = "minecraft:the_nether"
    assert call(tools, "go_to_place", name="base").startswith("FAILURE_OTHER_DIMENSION: base is in overworld")
    assert client.sent == []


def test_the_state_lists_them_with_the_distance(book):
    book.remember("s", "home", 10, -57, 3)
    book.remember("s", "portal", 0, 70, 0, dimension="minecraft:the_nether")
    assert book.render("s", (0.5, -57.0, 0.5)) == "home (10, -57, 3) 10m, portal (0, 70, 0) in the_nether"


def test_the_oldest_goes_when_there_are_too_many_but_never_the_death(book):
    book.remember("s", DEATH, 0, 0, 0)
    book._data["s"][DEATH]["saved_at"] = 0
    for i in range(30):
        book.remember("s", f"p{i}", i, 0, 0)
    names = book.names("s")
    assert DEATH in names and len(names) == 24


def test_a_death_is_remembered_for_her(tmp_path):
    from src.core.skills.minecraft.surface import MinecraftSurface
    from tests.test_minecraft_social import Config

    async def die():
        s = MinecraftSurface(Config(), bus=_Bus(), expression=None)
        s.initialize()
        s.places = Places(tmp_path / "places.json")
        s.client = FakeClient(server="play.example.net")
        from pathlib import Path
        real = json.loads((Path(__file__).parent / "fixtures/minecraft_packets/death_event.json").read_text())
        s._on_death(real)
        await asyncio.gather(*s._saving)
        return s

    s = asyncio.run(die())
    assert s.places.get("play.example.net", DEATH) == {**s.places.get("play.example.net", DEATH),
                                                        "x": 3, "y": -57, "z": 0}
    assert (tmp_path / "places.json").exists()
    assert "last_death (3, -57, 0)" in s._places_line()


class _Bus:
    def put(self, perception):
        pass


def test_the_body_reads_its_places_with_the_state():
    from src.core.agent.tools import ToolRegistry
    from src.core.skills.minecraft.agent import GameAgent

    agent = GameAgent(llm=None, registry=ToolRegistry(), notebook=Notebook(), state_getter=lambda: {},
                      places=lambda: "home (10, -57, 3) 10m")
    assert "PLACES YOU REMEMBER: home (10, -57, 3) 10m" in agent._state_note()
    quiet = GameAgent(llm=None, registry=ToolRegistry(), notebook=Notebook(), state_getter=lambda: {})
    assert "PLACES" not in quiet._state_note()


def test_the_real_state_names_the_server():
    from pathlib import Path

    from src.core.skills.minecraft.places import server_of
    real = json.loads((Path(__file__).parent / "fixtures/minecraft_packets/game_state.json").read_text())
    assert server_of(real) == "127.0.0.1:25565"
    assert server_of({}) == "unknown"


def test_saves_at_once_never_fail_and_the_newest_wins(tmp_path):
    book = Places(tmp_path / "places.json")

    async def storm():
        tasks = []
        for i in range(1200):
            book.remember("s", f"p{i % 20}", i, 0, 0)
            tasks.append(asyncio.create_task(book.save()))
        await asyncio.gather(*tasks)

    asyncio.run(storm())
    on_disk = json.loads((tmp_path / "places.json").read_text())
    assert on_disk == book._data
    assert sorted(p.name for p in tmp_path.iterdir()) == ["places.json"]


def test_an_older_snapshot_never_lands_over_a_newer_one(tmp_path):
    book = Places(tmp_path / "places.json")
    book.remember("s", "home", 1, 0, 0)
    old = book.snapshot()
    book.remember("s", "home", 2, 0, 0)
    new = book.snapshot()
    book.write(*new)
    book.write(*old)
    assert json.loads((tmp_path / "places.json").read_text())["s"]["home"]["x"] == 2

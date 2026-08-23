"""Phase 8B: the game chat enters the social stack.

The point of the phase is that almost no new code is needed — everything above
`Author` (the roster, person cards, the attention gate) already works, as long as
the sensor produces a correct, stable identity.
"""

import asyncio

import pytest

from src.core.attention.rules import is_addressed
from src.core.memory.store import MemoryStore
from src.core.mind.routing import STAGE, conversation_key
from src.core.perception.bus import PerceptionBus
from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.state import render_state
from src.core.skills.minecraft.surface import MinecraftSurface
from tests.fakes import FakeHistory

MARCO = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
BEA = "11111111-2222-3333-4444-555555555555"


class Context:
    def __init__(self, store):
        self.memory = store
        self.history_manager = FakeHistory()


class Config:
    def __init__(self):
        self.skills = {"minecraft": {"enabled": True, "server_url": "ws://127.0.0.1:8080"}}
        self.attention = {"trigger_words": ["bea"]}


@pytest.fixture
def surface():
    store = MemoryStore(":memory:")
    bus = PerceptionBus(window=0.0)
    s = MinecraftSurface(Config(), bus=bus, expression=None, context=Context(store))
    s.initialize()
    s.active = True
    s.client = _FakeClient()
    yield s, store, bus
    store.close()


class _FakeClient:
    """Just enough of MinecraftClient for the surface to read state from."""

    def __init__(self):
        self.latest_state = {"player": {"uuid": BEA, "name": "Bea", "health": 20, "food": 20}}


def chat(text="ciao", uuid=MARCO, name="Marco", kind="player", distance=None):
    packet = {"type": "chat", "kind": kind, "text": text, "ts": 1}
    if kind == "player":
        packet["author"] = {"uuid": uuid, "name": name}
        if distance is not None:
            packet["distance"] = distance
    return packet


# --- the client dispatches on type ------------------------------------------


def client_with_recorder():
    seen = []
    client = MinecraftClient("ws://127.0.0.1:8080", asyncio.new_event_loop(),
                             on_event=lambda kind, data: seen.append((kind, data)))
    return client, seen


def test_a_chat_packet_reaches_the_surface():
    client, seen = client_with_recorder()
    client._handle(chat())
    assert [kind for kind, _ in seen] == ["chat"]


def test_a_death_packet_is_no_longer_thrown_away():
    """The full account of the death was already being sent, and was discarded
    every single time because the dispatch only looked at `status`."""
    client, seen = client_with_recorder()
    client._handle({"type": "death_event", "status": "DIED",
                    "details": {"cause": "zombie", "lost_items": ["diamond x3"]}})
    assert seen[0][0] == "death_event"
    assert seen[0][1]["details"]["cause"] == "zombie"


def test_dying_also_ends_whatever_she_was_doing():
    """Leaving the caller to time out for a minute would misreport what happened."""
    loop = asyncio.new_event_loop()
    client = MinecraftClient("ws://x", loop, on_event=lambda k, d: None)
    client._pending = loop.create_future()
    client._handle({"type": "death_event", "details": {}})
    assert client._pending.done()
    assert "died" in client._pending.result()


def test_a_combat_packet_reaches_the_surface():
    client, seen = client_with_recorder()
    client._handle({"type": "combat", "event": "hurt", "source": "player"})
    assert seen[0][0] == "combat"


def test_self_defence_is_reported():
    client, seen = client_with_recorder()
    client._handle({"status": "ENGAGED_AUTO_ACTION", "event": {"attacker": "Zombie"}})
    assert seen[0][0] == "auto_action"


def test_a_state_snapshot_still_updates_the_state():
    client, _ = client_with_recorder()
    client._handle({"type": "game_state", "player": {"health": 12}})
    assert client.latest_state["player"]["health"] == 12


def test_completion_events_still_resolve_an_action():
    loop = asyncio.new_event_loop()
    client = MinecraftClient("ws://x", loop)
    client._pending = loop.create_future()
    client._handle({"status": "FINISHED", "result": "SUCCESS", "message": "mined 3 logs"})
    assert client._pending.result() == "SUCCESS: mined 3 logs"


# --- the surface builds a real identity --------------------------------------


def test_someone_talking_becomes_a_perception_with_an_identity(surface):
    s, _, bus = surface
    s._on_mod_event("chat", chat("ciao a tutti"))
    p = bus.drain_nowait()[0]
    assert p.author.identity == f"minecraft:{MARCO}"
    assert p.author.display_name == "Marco"
    assert "ciao a tutti" in p.content


def test_the_identity_is_the_uuid_not_the_name(surface):
    """Names change on a server; the UUID does not."""
    s, _, bus = surface
    s._on_mod_event("chat", chat("uno", name="Marco"))
    s._on_mod_event("chat", chat("due", name="Marco_Renamed"))
    a, b = bus.drain_nowait()
    assert a.author.identity == b.author.identity


def test_her_own_messages_do_not_come_back_to_her(surface):
    s, _, bus = surface
    s._on_mod_event("chat", chat("sono io", uuid=BEA, name="Bea"))
    assert bus.drain_nowait() == []


def test_server_lines_have_no_author(surface):
    s, _, bus = surface
    s._on_mod_event("chat", chat("Marco joined the game", kind="system"))
    p = bus.drain_nowait()[0]
    assert p.author is None
    assert p.salience < 0.5


def test_an_empty_message_is_ignored(surface):
    s, _, bus = surface
    s._on_mod_event("chat", chat("   "))
    assert bus.drain_nowait() == []


def test_game_chat_belongs_to_the_stage(surface):
    """She is standing in that world: she answers out loud AND in chat, which a
    scoped text turn (no voice) could not do."""
    s, _, bus = surface
    s._on_mod_event("chat", chat())
    assert conversation_key(bus.drain_nowait()[0]) == STAGE


# --- what the attention gate makes of it -------------------------------------


def test_being_named_in_game_reaches_her(surface):
    s, _, bus = surface
    s._on_mod_event("chat", chat("bea vieni qui"))
    assert is_addressed(bus.drain_nowait()[0], trigger_words=["bea"]) == "addressed:name"


def test_a_whisper_always_reaches_her(surface):
    s, _, bus = surface
    s._on_mod_event("chat", chat("Marco whispers to you: guarda"))
    p = bus.drain_nowait()[0]
    assert p.meta["whisper"] is True
    assert is_addressed(p, trigger_words=["bea"]) == "addressed:whisper"


def test_someone_standing_next_to_her_is_talking_to_her(surface):
    s, _, bus = surface
    s._on_mod_event("chat", chat("guarda qua", distance=3.0))
    assert is_addressed(bus.drain_nowait()[0], trigger_words=["bea"]) == "addressed:nearby"


def test_someone_shouting_from_across_the_map_is_not(surface):
    s, _, bus = surface
    s._on_mod_event("chat", chat("qualcosa", distance=80.0))
    assert is_addressed(bus.drain_nowait()[0], trigger_words=["bea"]) is None


def test_being_hit_by_a_player_always_reaches_her(surface):
    """Somebody hitting you made a decision about you: that is social, not damage."""
    s, _, bus = surface
    s._on_mod_event("combat", {"type": "combat", "event": "hurt", "source": "player",
                               "damage": 3.0, "health": 17.0,
                               "by": {"uuid": MARCO, "name": "Marco", "distance": 2.0}})
    p = bus.drain_nowait()[0]
    assert is_addressed(p, trigger_words=["bea"]) == "addressed:attacked"
    assert p.author.identity == f"minecraft:{MARCO}"
    assert "Marco just hit you" in p.content


def test_being_hit_by_a_mob_is_not_a_social_event(surface):
    s, _, bus = surface
    s._on_mod_event("combat", {"type": "combat", "event": "hurt", "source": "mob",
                               "damage": 2.0, "health": 18.0, "by": {"name": "Zombie"}})
    p = bus.drain_nowait()[0]
    assert p.author is None
    assert is_addressed(p, trigger_words=["bea"]) is None


def test_fall_damage_is_just_damage(surface):
    s, _, bus = surface
    s._on_mod_event("combat", {"type": "combat", "event": "hurt", "source": "environment",
                               "damage": 6.0, "health": 14.0})
    assert "took 6 damage" in bus.drain_nowait()[0].content


def test_dying_reaches_her_with_the_whole_story(surface):
    s, _, bus = surface
    s._on_mod_event("death_event", {
        "type": "death_event",
        "details": {"cause": "Marco", "death_pos": {"x": 12.0, "y": 64.0, "z": -8.0},
                    "lost_items": ["diamond_pickaxe x1", "cobblestone x64"]},
    })
    p = bus.drain_nowait()[0]
    assert is_addressed(p, trigger_words=["bea"]) == "addressed:death"
    assert "Marco" in p.content
    assert "diamond_pickaxe x1" in p.content
    assert "(12, 64, -8)" in p.content


def test_someone_joining_is_noticed(surface):
    s, _, bus = surface
    s._on_mod_event("player_event", {"type": "player_event", "event": "join",
                                     "player": {"uuid": MARCO, "name": "Marco"}})
    p = bus.drain_nowait()[0]
    assert "Marco joined" in p.content
    assert p.author.identity == f"minecraft:{MARCO}"


def test_her_own_join_is_not_news(surface):
    s, _, bus = surface
    s._on_mod_event("player_event", {"type": "player_event", "event": "join",
                                     "player": {"uuid": BEA, "name": "Bea"}})
    assert bus.drain_nowait() == []


# --- the social stack comes for free -----------------------------------------


def test_the_social_stack_needs_no_minecraft_specific_code(surface):
    """Three sessions with the same player and she has a card — with nothing in
    the social layer that knows Minecraft exists."""
    from src.core.skills.social.people import promotion_reason, should_promote

    _, store, _ = surface
    identity = f"minecraft:{MARCO}"
    for session in ("s1", "s2", "s3"):
        store.roster.record(identity=identity, display_name="Marco",
                            platform="minecraft", session_id=session)

    entry = store.roster.get(identity)
    assert should_promote(entry) is True
    assert promotion_reason(entry) == "a regular"


def test_a_player_and_a_discord_account_can_be_the_same_person(surface):
    _, store, _ = surface
    store.roster.record(identity="discord:4711", display_name="marco", platform="discord")
    store.roster.record(identity=f"minecraft:{MARCO}", display_name="Marco", platform="minecraft")
    entry = store.roster.get("discord:4711")
    card = store.people.create_from_entry(entry, reason="a regular")
    store.people.link_identity(card.person_id, f"minecraft:{MARCO}")

    assert store.people.get_by_identity(f"minecraft:{MARCO}").person_id == card.person_id


# --- the state renderer sees players -----------------------------------------


def test_players_are_called_out_among_the_entities():
    state = {
        "player": {"health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}},
        "entities": [
            {"name": "Marco", "type": "minecraft:player", "distance": 4.0,
             "is_player": True, "uuid": MARCO},
            {"name": "Zombie", "type": "minecraft:zombie", "distance": 9.0},
        ],
    }
    rendered = render_state(state)
    assert "PLAYER Marco 4m" in rendered
    assert "Zombie 9m" in rendered


# --- playing with people (phase 8C) ------------------------------------------


def test_the_interaction_tools_are_armed(surface):
    from src.core.skills.minecraft.notebook import Notebook
    from src.core.skills.minecraft.tools import build_minecraft_tools

    s, _, _ = surface
    names = {t.name for t in build_minecraft_tools(_RecordingClient(), Notebook()).tools()}
    assert {"goto_player", "follow_player", "look_at_player", "give_item"} <= names


async def test_looking_at_a_player_uses_the_look_skill():
    """One mod skill, told who to look at instead of where."""
    from src.core.skills.minecraft.notebook import Notebook
    from src.core.skills.minecraft.tools import build_minecraft_tools

    client = _RecordingClient()
    registry = build_minecraft_tools(client, Notebook())
    await registry.get("look_at_player").handler(name="Marco")
    assert client.calls == [("look_at", {"player": "Marco"})]


async def test_giving_something_carries_the_count():
    from src.core.skills.minecraft.notebook import Notebook
    from src.core.skills.minecraft.tools import build_minecraft_tools

    client = _RecordingClient()
    registry = build_minecraft_tools(client, Notebook())
    await registry.get("give_item").handler(name="Marco", item="oak_log", count=5)
    assert client.calls == [("give_item", {"name": "Marco", "item": "oak_log", "count": 5})]


async def test_following_is_a_body_action():
    """It runs for as long as she wants it to, so it must not block reasoning."""
    from src.core.skills.minecraft.notebook import Notebook
    from src.core.skills.minecraft.tools import build_minecraft_tools

    registry = build_minecraft_tools(_RecordingClient(), Notebook())
    assert registry.get("follow_player").long_running is True


class _RecordingClient:
    def __init__(self):
        self.calls = []

    async def execute(self, action, params, instant=False):
        self.calls.append((action, params))
        return "SUCCESS"

"""The wire between the brain and the mod, held against packets the mod really sent.

Every fixture in tests/fixtures/minecraft_packets was recorded from a live
BeaCraft (the `v1_` ones from a protocol-1 jar, the rest from protocol 2).
Hand-written packets are how a completion that the real mod never sends kept
the brain's tests green while every explanation it did send was dropped.
"""

import asyncio
import json
import logging
from pathlib import Path

import pytest

from src.core.skills.minecraft.client import MinecraftClient

PACKETS = Path(__file__).parent / "fixtures" / "minecraft_packets"


def packet(name: str) -> dict:
    return json.loads((PACKETS / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def client_on(loop, handshake: str = "handshake", events=None) -> MinecraftClient:
    """A client that has already heard the mod introduce itself."""
    client = MinecraftClient(
        "ws://x", loop, on_event=(lambda kind, data: events.append((kind, data))) if events is not None else None)
    client._handle(packet(handshake))
    return client


def waiting(client: MinecraftClient, loop, request_id: str):
    fut = loop.create_future()
    client._waiting[request_id] = fut
    return fut


# --- the handshake -------------------------------------------------------------


def test_a_protocol_2_mod_says_what_it_runs_beside_the_body(loop):
    client = client_on(loop)
    assert client.protocol == 2
    assert client.mc_version == "26.2"
    assert {"chat", "check_death_log", "look_at"} <= client.concurrent
    assert client.concurrent <= client.actions


def test_an_outdated_jar_still_plays_but_says_so(loop, caplog):
    with caplog.at_level(logging.ERROR, logger="bea.skills.minecraft.client"):
        client = client_on(loop, "v1_handshake")
    assert client.protocol == 1
    assert any("outdated" in r.getMessage() for r in caplog.records)


# --- answers -------------------------------------------------------------------


def test_an_answer_reads_as_result_and_explanation(loop):
    client = client_on(loop)
    fut = waiting(client, loop, "h1")
    client._handle(packet("finished"))
    assert fut.result() == "SUCCESS: Place action executed"


def test_an_old_jar_explanation_under_details_is_not_dropped(loop):
    """Protocol 1 put the sentence in `details.message`; the brain read only the top."""
    client = client_on(loop, "v1_handshake")
    fut = waiting(client, loop, "r1")
    client._handle(packet("v1_finished"))
    assert fut.result() == "SUCCESS: Pillar action finished"


def test_an_old_jar_failure_under_the_error_key_is_read_too(loop):
    client = client_on(loop, "v1_handshake")
    fut = waiting(client, loop, "r1")
    client._handle(packet("v1_failure_error_key"))
    assert fut.result() == "FAILURE: Crafting failed (Verified: 0 -> 0)"


def test_an_interruption_says_what_took_the_body_away(loop):
    client = client_on(loop)
    fut = waiting(client, loop, "h2")
    client._handle(packet("interrupted"))
    assert fut.result() == "INTERRUPTED: interrupted (stopped by request)"


def test_the_log_travels_with_the_answer(loop):
    client = client_on(loop)
    fut = waiting(client, loop, "r9")
    answer = dict(packet("finished"), id="r9", log=[f"step {i}" for i in range(1, 12)])
    client._handle(answer)
    lines = fut.result().splitlines()
    assert lines[0] == "SUCCESS: Place action executed"
    assert lines[1:] == [f"step {i}" for i in range(4, 12)]


def test_an_answer_without_an_id_never_resolves_a_waiter(loop):
    """What the mod does on its own is not the answer to anything."""
    client = client_on(loop)
    fut = waiting(client, loop, "r1")
    client._handle(packet("v1_unsolicited_eat"))
    assert not fut.done()


def test_each_caller_gets_exactly_its_own_answer_in_any_order(loop):
    client = client_on(loop)
    walking, placing, stopping = (waiting(client, loop, i) for i in ("h2", "h1", "h4"))
    client._handle(packet("finished_stop_moving"))
    client._handle(packet("interrupted"))
    client._handle(packet("finished"))
    assert walking.result().startswith("INTERRUPTED")
    assert placing.result().startswith("SUCCESS: Place")
    assert stopping.result() == "SUCCESS: stopped move_to"


def test_an_answer_nobody_waits_for_is_not_handed_to_the_next_caller(loop):
    client = client_on(loop)
    other = waiting(client, loop, "r77")
    client._handle(packet("interrupted"))
    assert not other.done()


def test_a_protocol_1_jar_is_still_answered_in_order(loop, caplog):
    client = client_on(loop, "v1_handshake")
    first, second = waiting(client, loop, "r1"), waiting(client, loop, "r2")
    client._handle(packet("v1_interrupted"))
    client._handle(packet("v1_finished"))
    assert first.result() == "INTERRUPTED"
    assert second.result() == "SUCCESS: Pillar action finished"


# --- what the body does on its own ---------------------------------------------


@pytest.mark.parametrize("name", ["reflex_eat_started", "reflex_eat_finished", "reflex_respawn_started"])
def test_a_reflex_is_an_event_for_the_surface(loop, name):
    events = []
    client = client_on(loop, events=events)
    fut = waiting(client, loop, "r1")
    client._handle(packet(name))
    assert events and events[-1][0] == "reflex"
    assert events[-1][1]["message"]
    assert not fut.done()


def test_a_death_interrupts_the_request_by_name_and_is_an_event(loop):
    events = []
    client = client_on(loop, events=events)
    walking = waiting(client, loop, "h5")
    client._handle(packet("interrupted_by_death"))
    client._handle(packet("reflex_respawn_started"))
    client._handle(packet("death_event"))
    assert walking.result() == "INTERRUPTED: interrupted (death)"
    assert [kind for kind, _ in events] == ["reflex", "death_event"]


# --- every recorded packet parses -----------------------------------------------


@pytest.mark.parametrize("path", sorted(PACKETS.glob("*.json")), ids=lambda p: p.stem)
def test_every_recorded_packet_is_handled(loop, path):
    client = client_on(loop, "v1_handshake" if path.stem.startswith("v1_") else "handshake", events=[])
    client._handle(json.loads(path.read_text(encoding="utf-8")))


def test_the_game_state_becomes_the_latest_state(loop):
    client = client_on(loop)
    client._handle(packet("game_state"))
    assert client.latest_state["player"]["name"] == "Bea"


def test_a_query_is_answered_with_a_sentence(loop):
    client = client_on(loop)
    fut = waiting(client, loop, "h6")
    client._handle(packet("finished_check_death_log"))
    assert fut.result().startswith("SUCCESS: you died at (3, -57, 0)")


# --- sending -------------------------------------------------------------------


def test_every_action_is_awaited_on_protocol_2(loop):
    """chat and check_death_log used to come back as a bare "SENT"."""
    client = client_on(loop)
    client.is_connected = True
    sent = []
    client._send = sent.append

    async def ask():
        task = asyncio.ensure_future(client.execute("chat", {"message": "hi"}, timeout=1))
        await asyncio.sleep(0)
        client._handle(dict(packet("finished_concurrent_chat"), id=sent[0]["id"]))
        return await task

    assert loop.run_until_complete(ask()) == "SUCCESS: Chat packet sent"


def test_an_old_jar_is_not_waited_on_for_what_it_never_answers(loop):
    client = client_on(loop, "v1_handshake")
    client.is_connected = True
    client._send = lambda payload: None
    assert loop.run_until_complete(client.execute("check_death_log", {})) == "SENT"


# --- how long the brain waits ---------------------------------------------------


class _TimedClient:
    def __init__(self):
        self.timeouts = {}

    async def execute(self, action, params, timeout=None):
        self.timeouts[action] = timeout
        return "SUCCESS"


@pytest.mark.parametrize("tool, wait", [
    ("find_block", 240.0), ("move_to", 120.0), ("smelt_item", 180.0), ("mine_block", 70.0),
    ("craft_item", 60.0),
])
def test_the_brain_waits_longer_than_the_mod_works(loop, tool, wait):
    from src.core.skills.minecraft.notebook import Notebook
    from src.core.skills.minecraft.tools import _TOOLS, build_minecraft_tools

    client = _TimedClient()
    registry = build_minecraft_tools(client, Notebook())
    required = _TOOLS[tool][1].get("required", [])
    args = {k: 1 for k in required}
    loop.run_until_complete(registry.get(tool).handler(**args))
    assert client.timeouts[tool] == wait


# --- the mod's budgets -----------------------------------------------------------


def test_the_mod_announces_how_long_each_action_may_run(loop):
    client = client_on(loop)
    assert client.budgets["find_block"] == 180
    assert client.budgets["follow_player"] == 0


def test_the_brain_never_waits_less_than_the_mod_works(loop):
    """The mod gives up first and says why; the other way round its late answer was lost."""
    from src.core.skills.minecraft.tools import ACTION_TIMEOUTS, DEFAULT_TIMEOUT

    client = client_on(loop)
    for action, budget in client.budgets.items():
        if action == "default" or budget <= 0:
            continue
        assert ACTION_TIMEOUTS.get(action, DEFAULT_TIMEOUT) > budget, action
        assert client.wait_for(action, 1.0) >= budget + 5
    assert client.wait_for("pillar_up", None) >= client.budgets["default"] + 5


def test_an_open_ended_action_keeps_the_brain_timeout(loop):
    client = client_on(loop)
    assert client.wait_for("follow_player", 60.0) == 60.0


def test_a_build_reporting_in_is_an_event_not_an_answer(loop):
    events = []
    client = client_on(loop, events=events)
    future = waiting(client, loop, "h1")
    client._handle(packet("progress_build"))
    assert events[-1] == ("progress", packet("progress_build"))
    assert not future.done()


def test_an_unfinished_build_says_what_is_missing_and_where(loop):
    client = client_on(loop)
    future = waiting(client, loop, "h1")
    client._handle(packet("finished_build_incomplete"))
    observation = future.result()
    assert observation.startswith(
        "FAILURE_INCOMPLETE: built 20/25 cells of the build; missing 5 cobblestone.")
    assert "still wrong: (7, -57, 3) holds air, wanted cobblestone" in observation

"""The brain may only send parameters the mod actually reads.

The mod is a separate repository, so this holds the tool schemas against a
fixture generated from its sources by `tools/mc_contract.py`. Two ways to fail:
a parameter the brain sends and the mod ignores (the model thinks it asked for
something and nothing happened), and a parameter the mod offers that nobody has
decided about — new mod capability has to be either exposed or deliberately
left out, never merely unnoticed.
"""

import json
from pathlib import Path

import pytest

from src.core.skills.minecraft.tools import _ALIASES, _QUICK, _TOOLS

CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures/minecraft_contract.json").read_text(encoding="utf-8"))
ACTIONS = CONTRACT["actions"]

# tools that never reach the mod
LOCAL_ONLY = {"update_notebook", "goal_done", "goal_blocked"}

# mod parameters the brain deliberately does not offer, and why. Anything the
# mod accepts that is neither exposed nor listed here fails the test on purpose.
OMITTED = {
    # she bridges away from where she stands; picking a start block is the
    # mod's own business and a wrong one strands her mid-air
    "bridge": {"x", "z"},
    # looking somewhere is a coordinate or a person, never a compass word
    "look_at": {"direction"},
    # she knows the people around her by name; the uuid is the mod's index
    "follow_player": {"uuid"},
    "goto_player": {"uuid"},
    # the whole tree and the drops are what mining is for; single blocks without
    # pickup are for the mod's own paths and pillars, never her decision
    "mine_block": {"vein", "pickup"},
}


def exposed_by(action: str) -> set:
    """Every parameter the brain can send to one mod action, after renames."""
    sent = set()
    for name, (_description, schema) in _TOOLS.items():
        target, renames = _ALIASES.get(name, (name, {}))
        if target != action:
            continue
        sent |= {renames.get(p, p) for p in (schema.get("properties") or {})}
    return sent


@pytest.mark.parametrize("tool", sorted(set(_TOOLS) - LOCAL_ONLY))
def test_every_tool_names_an_action_the_mod_knows(tool):
    action, _renames = _ALIASES.get(tool, (tool, {}))
    assert action in CONTRACT["known_actions"], f"{tool} -> {action} is not a mod action"


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_the_mod_reads_every_parameter_the_brain_sends(action):
    accepted = set(ACTIONS[action]["accepts"])
    dropped = exposed_by(action) - accepted
    assert not dropped, (
        f"{action}: the brain sends {sorted(dropped)} and the mod never reads it — "
        f"it accepts {sorted(accepted)}")


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_no_mod_parameter_is_left_undecided(action):
    accepted = set(ACTIONS[action]["accepts"])
    unclaimed = accepted - exposed_by(action) - OMITTED.get(action, set())
    assert not unclaimed, (
        f"{action}: the mod accepts {sorted(unclaimed)} and the brain neither sends it "
        f"nor lists it in OMITTED — expose it or say why not")


def test_the_mod_never_takes_a_parameter_it_fills_in_itself():
    for action, spec in ACTIONS.items():
        clash = exposed_by(action) & set(spec["injected_by_mod"])
        assert not clash, f"{action}: the brain overrides {sorted(clash)}, which the mod sets"


def test_what_the_mod_runs_beside_the_body_is_declared_known():
    assert set(CONTRACT["concurrent_actions"]) <= set(CONTRACT["known_actions"])


def test_what_the_mod_runs_beside_the_body_is_quick_for_the_brain():
    """A glance or a chat line is answered at once; nothing about it runs long."""
    for action in CONTRACT["concurrent_actions"]:
        assert action in _QUICK, f"{action} runs beside the body in the mod but not in the brain"

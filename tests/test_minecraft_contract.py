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

# mod actions she is not given, and why
NOT_EXPOSED = {
    # nothing of hers looks at an image yet: a screenshot would be a slow, blind call
    "request_screenshot",
    # equip_item puts the thing in her hand from anywhere; a slot number is a guess about her hotbar
    "select_slot",
}

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
    # the placer walks without digging so it never takes apart what it built;
    # her own walks keep the right to dig through terrain
    "move_to": {"allowMining"},
    # the old count of crafts; count (items wanted) is the one that means what she thinks
    "craft_item": {"quantity"},
    # the old names of item and fuel, still read for brains that send them
    "smelt_item": {"input_item", "fuel_item"},
    # the chest skill shared with store/retrieve: a look moves nothing
    "view_container": {"item", "count"},
    # the point to flee from is the flee reflex's; asked for, she moves away from where she is
    "move_away": {"from_x", "from_z"},
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


@pytest.mark.parametrize("tool", sorted(_TOOLS))
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


def test_every_mod_action_is_a_tool_or_left_out_on_purpose():
    exposed = {_ALIASES.get(t, (t, {}))[0] for t in _TOOLS}
    undecided = set(CONTRACT["known_actions"]) - exposed - NOT_EXPOSED
    assert not undecided, f"the mod offers {sorted(undecided)} and she has no tool for it"
    assert not (NOT_EXPOSED & exposed), "an action listed as left out is exposed after all"


@pytest.mark.parametrize("action", sorted(set(ACTIONS) - NOT_EXPOSED))
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


def test_what_the_mod_runs_beside_an_action_is_declared_known():
    assert set(CONTRACT["concurrent_actions"]) <= set(CONTRACT["known_actions"])


def test_what_the_mod_runs_beside_an_action_is_quick_for_the_brain():
    """A glance or a chat line is answered at once; nothing about it runs long."""
    quick = {_ALIASES.get(t, (t, {}))[0] for t in _QUICK}
    for action in CONTRACT["concurrent_actions"]:
        assert action in quick, f"{action} runs beside an action in the mod but not in the brain"

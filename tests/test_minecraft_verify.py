"""A goal closes because the world says so, not because the model does.

`goal_done` used to be an assertion: the body called it, the goal went DONE, and
nothing ever compared the summary to the inventory. A goal that carries a
`requires` is checked against the state the mod last sent before it may close.
"""


from src.core.skills.minecraft.goal import DONE, RUNNING, STUCK, unmet
from src.core.skills.minecraft.state import count_items
from tests.fakes import FakeLLMClient
from tests.test_game_agent import FakeClient, agent, calls, done, play


def carrying(**items):
    """A state packet holding exactly these items, in the mod's shape."""
    return {
        "player": {"health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}},
        "inventory": {
            "hand_main": {"item": "minecraft:air", "count": 0},
            "hotbar": [{"item": f"minecraft:{n}", "count": c} for n, c in items.items()],
            "main": [],
        },
    }


# --- counting what she has ---------------------------------------------------


def test_what_she_carries_is_counted_by_short_name():
    assert count_items(carrying(iron_ingot=5))["iron_ingot"] == 5


def test_the_same_item_in_two_stacks_adds_up():
    state = carrying()
    state["inventory"]["hotbar"] = [{"item": "minecraft:oak_log", "count": 60},
                                    {"item": "minecraft:oak_log", "count": 4}]
    assert count_items(state)["oak_log"] == 64


def test_the_held_item_is_not_counted_twice():
    # hand_main is one of the hotbar slots, not a slot of its own
    state = carrying(stone_pickaxe=1)
    state["inventory"]["hand_main"] = {"item": "minecraft:stone_pickaxe", "count": 1}
    assert count_items(state)["stone_pickaxe"] == 1


def test_armour_she_is_wearing_still_counts_as_having_it():
    state = carrying()
    state["inventory"]["armor"] = [{"item": "minecraft:iron_chestplate", "count": 1}]
    state["inventory"]["hand_off"] = {"item": "minecraft:shield", "count": 1}
    counted = count_items(state)
    assert counted["iron_chestplate"] == 1 and counted["shield"] == 1


# --- deciding whether a goal is met ------------------------------------------


def test_a_kind_of_log_satisfies_a_request_for_logs():
    assert unmet({"log": 4}, {"oak_log": 3, "birch_log": 2}) == ""


def test_a_pickaxe_made_of_stone_is_not_stone():
    # the trap: substring matching would read stone_pickaxe as five stone
    assert unmet({"stone": 5}, {"stone_pickaxe": 1}) != ""


def test_what_is_missing_is_named_with_the_numbers():
    assert unmet({"iron_ingot": 5}, {"iron_ingot": 2}) == "iron_ingot 2/5"


def test_nothing_missing_reads_as_met():
    assert unmet({"iron_ingot": 5}, {"iron_ingot": 5}) == ""


# --- the body may not close a goal the world disagrees with ------------------


async def test_a_goal_it_has_not_achieved_will_not_close():
    client = FakeClient()
    client.latest_state = carrying(iron_ingot=2)
    llm = FakeLLMClient([done("got the iron"), done("really, got it"),
                         calls("goal_blocked", reason="cannot find more")])
    a = agent(llm, client=client)
    goal = await play(a, "get 5 iron", requires={"iron_ingot": 5})
    assert goal.status == STUCK


async def test_the_refusal_tells_it_what_it_is_short_of():
    client = FakeClient()
    client.latest_state = carrying(iron_ingot=2)
    a = agent(FakeLLMClient([done("got it")]), client=client)
    a.set_goal("get 5 iron", requires={"iron_ingot": 5})
    answer = a._tool_done("got it")
    assert answer.startswith("FAILURE") and "iron_ingot 2/5" in answer
    assert a.goal.status == RUNNING


async def test_it_closes_the_moment_the_world_agrees():
    client = FakeClient()
    client.latest_state = carrying(iron_ingot=5)
    llm = FakeLLMClient([done("five iron, as asked")])
    goal = await play(agent(llm, client=client), "get 5 iron",
                      requires={"iron_ingot": 5})
    assert goal.status == DONE and goal.outcome == "five iron, as asked"


async def test_a_goal_with_nothing_to_check_still_closes_on_its_word():
    llm = FakeLLMClient([done("built the house")])
    goal = await play(agent(llm), "build a house")
    assert goal.status == DONE


async def test_being_blocked_is_never_second_guessed():
    # she is saying she cannot, which is not a claim about the inventory
    client = FakeClient()
    client.latest_state = carrying(iron_ingot=0)
    llm = FakeLLMClient([calls("goal_blocked", reason="no iron in this biome")])
    goal = await play(agent(llm, client=client), "get 5 iron",
                      requires={"iron_ingot": 5})
    assert goal.status == STUCK and "no iron" in goal.outcome


async def test_with_no_inventory_to_read_it_is_taken_at_its_word():
    # a body that cannot see its own bag must not be trapped in a goal forever
    client = FakeClient()
    client.latest_state = {"player": {"health": 20, "food": 20}}
    llm = FakeLLMClient([done("got the iron")])
    goal = await play(agent(llm, client=client), "get 5 iron",
                      requires={"iron_ingot": 5})
    assert goal.status == DONE

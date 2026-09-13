"""What happened on stream twenty minutes ago.

The dashboard shows a turn happening and then loses it. This is the record that
survives it — and the rule that matters more than anything it records is that
nothing here may ever cost a turn.
"""

import datetime
import json

from src.core.agent.types import Usage
from src.core.mind.turnlog import MAX_FIELD_CHARS, TurnLog, turn_record


class Calendar:
    """A clock a test can move, so a day can roll over without waiting for one."""

    def __init__(self, day: str = "2026-06-15", hour: int = 12):
        self.at = datetime.datetime.fromisoformat(f"{day}T{hour:02d}:00:00")

    def __call__(self):
        return self.at

    def skip(self, days: int):
        self.at += datetime.timedelta(days=days)


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def log(tmp_path, clock=None, **kwargs) -> TurnLog:
    return TurnLog(str(tmp_path / "turns"), clock=clock or Calendar(), **kwargs)


# --- what is written ----------------------------------------------------------


def test_a_turn_becomes_one_line(tmp_path):
    turns = log(tmp_path)
    turns.write({"steps": 1, "spoke": {"mood": "angry", "message": "ma tu guarda"}})

    written = lines(turns.path_for("2026-06-15"))
    assert len(written) == 1
    assert written[0]["spoke"]["message"] == "ma tu guarda"


def test_every_line_says_when_it_was(tmp_path):
    turns = log(tmp_path)
    turns.write({"steps": 1})
    assert lines(turns.path_for("2026-06-15"))[0]["at"].startswith("2026-06-15T12:00")


def test_turns_accumulate_rather_than_replace_each_other(tmp_path):
    turns = log(tmp_path)
    for step in range(3):
        turns.write({"steps": step})
    assert [line["steps"] for line in lines(turns.path_for("2026-06-15"))] == [0, 1, 2]


def test_a_new_day_is_a_new_file(tmp_path):
    clock = Calendar()
    turns = log(tmp_path, clock=clock)
    turns.write({"steps": 1})
    clock.skip(1)
    turns.write({"steps": 2})

    assert lines(turns.path_for("2026-06-15"))[0]["steps"] == 1
    assert lines(turns.path_for("2026-06-16"))[0]["steps"] == 2


def test_accents_survive_the_round_trip(tmp_path):
    turns = log(tmp_path)
    turns.write({"spoke": {"message": "però no, guarda"}})
    assert lines(turns.path_for("2026-06-15"))[0]["spoke"]["message"] == "però no, guarda"


def test_one_runaway_retrieval_cannot_bury_a_whole_day(tmp_path):
    turns = log(tmp_path)
    turns.write({"briefing": "x" * (MAX_FIELD_CHARS + 5000)})

    kept = lines(turns.path_for("2026-06-15"))[0]["briefing"]
    assert len(kept) < MAX_FIELD_CHARS + 100
    assert kept.endswith("chars)")


# --- and what is thrown away --------------------------------------------------


def test_days_that_have_aged_out_are_dropped(tmp_path):
    clock = Calendar()
    turns = log(tmp_path, clock=clock, keep_days=7)
    turns.write({"steps": 1})
    old = turns.path_for("2026-06-15")

    clock.skip(30)
    turns.write({"steps": 2})

    assert not old.exists()
    assert turns.path_for("2026-07-15").exists()


def test_a_day_still_inside_the_window_is_kept(tmp_path):
    clock = Calendar()
    turns = log(tmp_path, clock=clock, keep_days=7)
    turns.write({"steps": 1})

    clock.skip(2)
    turns.write({"steps": 2})

    assert turns.path_for("2026-06-15").exists()


def test_keeping_them_forever_is_a_setting(tmp_path):
    clock = Calendar()
    turns = log(tmp_path, clock=clock, keep_days=0)
    turns.write({"steps": 1})
    clock.skip(400)
    turns.write({"steps": 2})

    assert turns.path_for("2026-06-15").exists()


# --- and what it must never do ------------------------------------------------


def test_a_disk_that_will_not_take_it_does_not_cost_a_turn(tmp_path):
    blocked = tmp_path / "turns"
    blocked.write_text("this is a file, not a directory")

    turns = TurnLog(str(blocked), clock=Calendar())
    turns.write({"steps": 1})

    assert not turns.enabled


def test_it_gives_up_once_rather_than_every_turn(tmp_path, caplog):
    blocked = tmp_path / "turns"
    blocked.write_text("this is a file, not a directory")
    turns = TurnLog(str(blocked), clock=Calendar())

    for _ in range(5):
        turns.write({"steps": 1})

    assert sum("no longer being written" in r.message for r in caplog.records) == 1


def test_something_that_will_not_serialise_is_still_written_down(tmp_path):
    """A tool that answered with an object is a turn worth keeping, not a crash."""
    turns = log(tmp_path)
    turns.write({"tools": [{"result": object()}]})

    assert lines(turns.path_for("2026-06-15"))


# --- the shape of a turn ------------------------------------------------------


def record(**kwargs):
    base = dict(
        context=[{"role": "system", "content": "who she is"},
                 {"role": "system", "content": "what is true right now"},
                 {"role": "user", "content": "[PERCEPTIONS]"}],
        perceptions=["[marco] ciao"],
        calls=[{"tool": "speak", "arguments": {"mood": "happy"}, "result": "Spoken."}],
        spoke={"mood": "happy", "message": "ciao"},
        usage=Usage(prompt_tokens=1200, completion_tokens=40, cached_tokens=1024),
        steps=1,
        ms=812.4,
    )
    base.update(kwargs)
    return turn_record(**base)


def test_the_two_halves_of_the_prompt_are_kept_apart():
    """The same split the prompt itself makes: one half a provider should be
    caching, the other what changed this turn."""
    written = record()
    assert written["prompt"] == "who she is"
    assert written["briefing"] == "what is true right now"


def test_what_it_cost_is_part_of_the_turn_and_not_a_separate_metric():
    written = record()
    assert written["prompt_tokens"] == 1200
    assert written["cached_tokens"] == 1024
    assert written["ms"] == 812


def test_the_tools_she_reached_for_are_kept_with_their_answers():
    written = record()
    assert written["tools"][0]["tool"] == "speak"
    assert written["tools"][0]["result"] == "Spoken."


def test_a_turn_she_said_nothing_in_is_still_a_turn():
    written = record(spoke=None, calls=[{"tool": "stay_silent", "result": "Staying silent."}])
    assert written["spoke"] is None
    assert written["tools"][0]["tool"] == "stay_silent"


# --- what the file does not have to hold twice -------------------------------


def test_the_prompt_is_written_once_and_pointed_at_after_that(tmp_path):
    """It is thousands of characters and the same on almost every turn.

    Writing it every time is most of the file, for a value that does not move.
    """
    log = TurnLog(str(tmp_path), clock=lambda: datetime.datetime(2026, 3, 1, 12, 0))
    for _ in range(3):
        log.write({"prompt": "you are bea" * 200, "steps": 1})

    lines = [json.loads(line) for line in
             (tmp_path / "2026-03-01.jsonl").read_text().splitlines()]

    assert "prompt" in lines[0], "the first line of a day has to carry it"
    assert all("prompt" not in line for line in lines[1:])
    assert len({line["prompt_id"] for line in lines}) == 1, "every line names it"


def test_a_prompt_that_changed_is_written_out_again(tmp_path):
    """Which also makes an edit to it visible in the log rather than inferred."""
    log = TurnLog(str(tmp_path), clock=lambda: datetime.datetime(2026, 3, 1, 12, 0))
    log.write({"prompt": "you are bea", "steps": 1})
    log.write({"prompt": "you are bea", "steps": 1})
    log.write({"prompt": "you are someone else", "steps": 1})

    lines = [json.loads(line) for line in
             (tmp_path / "2026-03-01.jsonl").read_text().splitlines()]

    assert [("prompt" in line) for line in lines] == [True, False, True]
    assert lines[0]["prompt_id"] != lines[2]["prompt_id"]


def test_each_day_carries_the_prompt_of_its_own(tmp_path):
    """A file nobody can read without the one before it is not a log."""
    day = {"at": datetime.datetime(2026, 3, 1, 12, 0)}
    log = TurnLog(str(tmp_path), clock=lambda: day["at"])
    log.write({"prompt": "you are bea", "steps": 1})
    log.write({"prompt": "you are bea", "steps": 1})

    day["at"] = datetime.datetime(2026, 3, 2, 12, 0)
    log.write({"prompt": "you are bea", "steps": 1})

    second = json.loads((tmp_path / "2026-03-02.jsonl").read_text().splitlines()[0])
    assert "prompt" in second


def test_a_long_string_buried_in_a_tool_call_is_capped_too(tmp_path):
    """The longest string in a turn is usually what a tool came back with."""
    log = TurnLog(str(tmp_path), clock=lambda: datetime.datetime(2026, 3, 1, 12, 0))
    log.write({"tools": [{"name": "recall", "result": "x" * (MAX_FIELD_CHARS + 5000)}]})

    line = json.loads((tmp_path / "2026-03-01.jsonl").read_text())
    kept = line["tools"][0]["result"]
    assert len(kept) < MAX_FIELD_CHARS + 100
    assert kept.endswith("chars)")

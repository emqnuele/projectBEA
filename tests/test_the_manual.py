"""The operating manual, and the two copies of it that must not drift.

`data/prompts/operating.md` is a file somebody edits; `BUILTIN_OPERATING` is
what she gets when that file is missing or emptied by a bad save. A section
fixed in one and not the other is a fix that only half the installs get.
"""

import re

from src.core.expression.tags import direction_help
from src.core.mind.operating import BUILTIN_OPERATING, missing_tools
from src.utils.prompts import load_text

SHIPPED = load_text("data/prompts/operating.md")


def section(manual: str, name: str) -> str:
    """One `## SECTION` of a manual, without its heading."""
    match = re.search(rf"^## {name}\n(.*?)(?=\n## |\Z)", manual, re.S | re.M)
    assert match, f"no '{name}' section"
    return match.group(1).strip()


# --- the two copies agree ----------------------------------------------------


def test_both_manuals_say_the_same_thing_about_speaking():
    assert section(SHIPPED, "HOW YOU EXPRESS YOURSELF") == \
        section(BUILTIN_OPERATING, "HOW YOU EXPRESS YOURSELF")


def test_the_direction_section_is_the_one_the_parser_generates():
    """It is generated from the tags this codebase understands, so a tag
    renamed in the parser cannot stay named the old way in the manual."""
    assert section(SHIPPED, "DIRECTION") == direction_help().strip()
    assert section(BUILTIN_OPERATING, "DIRECTION") == direction_help().strip()


def test_both_manuals_still_name_the_tools_that_end_a_turn():
    from src.core.consciousness import Consciousness

    terminal = sorted(Consciousness._TERMINAL_TOOLS)
    assert missing_tools(SHIPPED, terminal) == []
    assert missing_tools(BUILTIN_OPERATING, terminal) == []


# --- and what they tell her about plain text ---------------------------------


def test_the_manual_puts_a_price_on_thinking_out_loud():
    """88% of everything she generated was prose nobody heard, written before
    the tool call that said the same thing again."""
    for manual in (SHIPPED, BUILTIN_OPERATING):
        rules = section(manual, "HOW YOU EXPRESS YOURSELF").lower()
        assert "delay" in rules
        assert "never write it twice" in rules


def test_the_manual_says_an_empty_turn_is_not_an_answer():
    for manual in (SHIPPED, BUILTIN_OPERATING):
        rules = section(manual, "HOW YOU EXPRESS YOURSELF").lower()
        assert "nobody heard" in rules
        assert "stay_silent" in rules


def test_the_manual_says_where_a_tag_belongs():
    """She was writing `<do:...>` and an invented `<speak>` in plain text,
    where they mean nothing, and then saying the line again properly."""
    for manual in (SHIPPED, BUILTIN_OPERATING):
        assert "<speak>" in manual
        assert "inside" in section(manual, "DIRECTION").lower()

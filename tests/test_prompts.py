"""Prompt assembly and the birthday countdown the morning pass depends on."""

import datetime

from src.core.skills.dream.surface import _days_until
from src.utils.prompts import compose, load_text, prompt_for


def test_compose_joins_with_a_blank_line():
    assert compose("a", "b") == "a\n\nb"


def test_compose_drops_empty_and_whitespace_parts():
    assert compose("a", "", None, "   ", "b") == "a\n\nb"


def test_compose_strips_each_part():
    assert compose("  a  ", "\nb\n") == "a\n\nb"


def test_compose_of_nothing_is_empty():
    assert compose() == ""


def test_load_text_returns_the_fallback_when_missing(tmp_path):
    assert load_text(str(tmp_path / "nope.md"), fallback="fb") == "fb"


def test_load_text_reads_and_strips(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("  hello\n", encoding="utf-8")
    assert load_text(str(p)) == "hello"


def test_days_until_today_is_zero():
    today = datetime.date.today()
    assert _days_until(f"{today.month:02d}-{today.day:02d}") == 0


def test_days_until_tomorrow_is_one():
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    # a birthday on jan 1st rolls to next year, which is still 1 day away
    assert _days_until(f"{tomorrow.month:02d}-{tomorrow.day:02d}") == 1


def test_days_until_a_past_date_rolls_to_next_year():
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    days = _days_until(f"{yesterday.month:02d}-{yesterday.day:02d}")
    assert days is not None and days >= 364


def test_days_until_rejects_garbage():
    assert _days_until("not-a-date") is None
    assert _days_until("13-45") is None


# --- instructions typed in the dashboard vs the file that ships -------------


def test_what_was_typed_in_the_dashboard_wins(tmp_path):
    """The Minecraft editor saved prose the skill never read.

    It wrote `system_prompt` while the surface only loaded the file named by
    `system_prompt_path`, so everything typed into it was stored in config.json
    and silently ignored.
    """
    shipped = tmp_path / "minecraft.md"
    shipped.write_text("the shipped rules", encoding="utf-8")
    block = {"system_prompt": "play nice", "system_prompt_path": str(shipped)}

    assert prompt_for(block, "system_prompt", "nope.md") == "play nice"


def test_an_empty_editor_means_the_file(tmp_path):
    # exactly what the editor's own placeholder promises
    shipped = tmp_path / "minecraft.md"
    shipped.write_text("the shipped rules", encoding="utf-8")
    block = {"system_prompt": "   ", "system_prompt_path": str(shipped)}

    assert prompt_for(block, "system_prompt", "nope.md") == "the shipped rules"


def test_nothing_typed_at_all_means_the_file(tmp_path):
    shipped = tmp_path / "minecraft.md"
    shipped.write_text("the shipped rules", encoding="utf-8")

    assert prompt_for({"system_prompt_path": str(shipped)}, "system_prompt", "nope.md") \
        == "the shipped rules"


def test_the_default_path_is_used_when_none_is_configured(tmp_path):
    shipped = tmp_path / "default.md"
    shipped.write_text("the default", encoding="utf-8")

    assert prompt_for({}, "system_prompt", str(shipped)) == "the default"


def test_typed_instructions_are_stripped():
    assert prompt_for({"system_prompt": "  hello  "}, "system_prompt", "nope.md") == "hello"

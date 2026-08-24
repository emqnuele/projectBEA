"""Prompt assembly and the birthday countdown the morning pass depends on."""

import datetime

from src.core.skills.dream.surface import _days_until
from src.utils.prompts import compose, load_text


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

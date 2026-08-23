"""Who earns a rich PersonCard, and why: the rule that decides what Bea keeps."""

import pytest

from src.core.skills.social.people import (
    REGULAR_SESSION_THRESHOLD,
    promotion_reason,
    should_promote,
)
from src.core.skills.social.roster import RosterEntry


def entry(**kwargs) -> RosterEntry:
    base = dict(identity="discord:1", display_name="marco", platform="discord")
    base.update(kwargs)
    return RosterEntry(**base)


def test_a_stranger_earns_nothing():
    assert should_promote(entry()) is False


def test_a_donation_promotes_immediately():
    assert should_promote(entry(donation_total=5.0)) is True
    assert promotion_reason(entry(donation_total=5.0)) == "donated"


def test_bea_marking_someone_promotes_them():
    assert should_promote(entry(marked_by_bea=True)) is True
    assert promotion_reason(entry(marked_by_bea=True)) == "you marked them"


def test_a_one_on_one_promotes():
    assert should_promote(entry(had_1on1=True)) is True
    assert promotion_reason(entry(had_1on1=True)) == "had a 1:1 with you"


def test_a_regular_promotes_at_the_threshold():
    sessions = [f"s{i}" for i in range(REGULAR_SESSION_THRESHOLD)]
    assert should_promote(entry(sessions=sessions[:-1])) is False
    assert should_promote(entry(sessions=sessions)) is True
    assert promotion_reason(entry(sessions=sessions)) == "a regular"


def test_already_promoted_never_promotes_twice():
    assert should_promote(entry(donation_total=99.0, promoted=True)) is False


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"donation_total": 1.0, "marked_by_bea": True}, "donated"),
        ({"marked_by_bea": True, "had_1on1": True}, "you marked them"),
        ({"had_1on1": True, "sessions": ["a", "b", "c"]}, "had a 1:1 with you"),
    ],
)
def test_reason_reports_the_strongest_signal(kwargs, expected):
    assert promotion_reason(entry(**kwargs)) == expected

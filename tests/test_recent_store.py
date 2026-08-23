"""Hot facts decay: they are 'right now', not memory."""

from src.core.skills.dream.recent import RecentStore

DAY = 86400.0


def store(tmp_path) -> RecentStore:
    return RecentStore(str(tmp_path / "recent.json"))


def test_a_fresh_fact_is_active(tmp_path):
    s = store(tmp_path)
    s.add("marco just donated", DAY)
    assert [f.text for f in s.active()] == ["marco just donated"]


def test_an_expired_fact_is_gone(tmp_path):
    s = store(tmp_path)
    s.add("stale", ttl_seconds=-1)
    assert s.active() == []


def test_blank_facts_are_ignored(tmp_path):
    s = store(tmp_path)
    s.add("   ", DAY)
    assert s.active() == []


def test_same_text_and_source_does_not_duplicate(tmp_path):
    s = store(tmp_path)
    s.add("your birthday is in 3 days", DAY, source="morning_pass")
    s.add("your birthday is in 3 days", DAY, source="morning_pass")
    assert len(s.active()) == 1


def test_same_text_from_another_source_is_kept(tmp_path):
    s = store(tmp_path)
    s.add("same", DAY, source="morning_pass")
    s.add("same", DAY, source="dreamer")
    assert len(s.active()) == 2


def test_clear_source_only_drops_that_source(tmp_path):
    s = store(tmp_path)
    s.add("derived", DAY, source="morning_pass")
    s.add("dreamt", DAY, source="dreamer")
    s.clear_source("morning_pass")
    assert [f.text for f in s.active()] == ["dreamt"]


def test_facts_survive_a_reload(tmp_path):
    s = store(tmp_path)
    s.add("persisted", DAY)
    assert [f.text for f in store(tmp_path).active()] == ["persisted"]


def test_render_is_empty_without_facts(tmp_path):
    assert store(tmp_path).render() == ""


def test_render_caps_the_number_of_lines(tmp_path):
    s = store(tmp_path)
    for i in range(10):
        s.add(f"fact {i}", DAY)
    rendered = s.render(max_items=3)
    assert rendered.startswith("[RIGHT NOW]")
    assert rendered.count("\n- ") == 3

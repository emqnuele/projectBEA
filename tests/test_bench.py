"""The measuring tool has to keep working, or nobody measures.

Nothing here asserts a duration. CI runners vary by tens of percent between
runs on the same commit, and a timing gate there produces flakes, then gets
disabled, then gets deleted. What is checked is that the harness still builds a
corpus this revision of the store understands and still produces numbers —
which is the failure that would otherwise be discovered months later, by
someone who needed a before-and-after and found the tool broken.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _bench():
    spec = importlib.util.spec_from_file_location("bench", ROOT / "tools" / "bench.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bench():
    return _bench()


def test_the_corpus_is_the_shape_the_store_expects(bench):
    with bench.corpus(50) as (db, rag):
        assert rag.count() == 50
        assert db.query("SELECT COUNT(*) AS n FROM memories WHERE embedding IS NOT NULL")[0]["n"] == 50


def test_the_corpus_is_reproducible(bench):
    """A seeded corpus, or two runs are not comparable and the tool is a toy."""
    with bench.corpus(20) as (_, first):
        a = [r.text for r in first.recall("qualcosa", scope="diary", k=5)]
    with bench.corpus(20) as (_, second):
        b = [r.text for r in second.recall("qualcosa", scope="diary", k=5)]
    assert a == b


def test_a_scenario_produces_numbers(bench):
    rows = bench.scenario_recall(sizes=(50,))
    assert rows
    for row in rows:
        assert row.note or row.p50 > 0


def test_both_retrieval_paths_are_measured(bench):
    """The comparison is the point: one row per path, in the same run."""
    details = {r.detail for r in bench.scenario_recall(sizes=(50,))}
    assert any("vec" in d for d in details)
    assert any("python" in d for d in details)


def test_p95_is_not_below_p50(bench):
    result = bench.Result("x", "y", 1, [0.001, 0.002, 0.003, 0.010])
    assert result.p95 >= result.p50


def test_the_voice_scenario_measures_the_local_path(bench):
    """The one part of a turn that runs on this machine, so it is the one part
    a before-and-after is reproducible for."""
    rows = bench.scenario_voice()
    assert {r.name for r in rows} == {"voice_convert", "voice_first_frame"}
    assert all(r.p50 > 0 for r in rows)


def test_a_skipped_scenario_says_so_instead_of_reporting_zero(bench):
    result = bench.skipped("stt", "local whisper", "no model")
    assert "skipped" in result.row()
    assert result.as_dict()["note"]


def test_every_scenario_is_listed(bench):
    """A scenario nobody can select is a scenario nobody runs."""
    assert set(bench.FAST) <= set(bench.SCENARIOS)
    assert bench.main(["--list"]) == 0

"""The search chain: whatever the owner configured first, the free search last.

No provider is contacted here — every answer comes from a stub. What is
asserted is the shape Claude worried about: Google-grade flakiness must cost
results, never the search, and a key pasted in the dashboard must apply to the
next search rather than the one after the cache expires.
"""

import aiohttp
import pytest

import src.core.skills.web.search as S
from src.core.skills.web.search import (
    Brave,
    DuckDuckGo,
    Result,
    Searcher,
    SearchError,
    SearchSettings,
    SearXNG,
    Tavily,
    _dedupe,
    chain,
)


class Stub:
    """A provider that answers from a script: results, or an error to raise."""

    name = "stub"

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    async def search(self, session, query, count, safesearch):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_the_chain_is_keyed_providers_first_and_the_free_one_last():
    providers = chain(SearchSettings(brave_key="k", tavily_key="t",
                                     searxng_url="https://s.example"))
    assert [p.name for p in providers] == ["searxng", "brave", "tavily", "duckduckgo"]
    assert isinstance(providers[-1], DuckDuckGo)


def test_with_nothing_configured_she_still_searches():
    assert [p.name for p in chain(SearchSettings())] == ["duckduckgo"]


def test_a_pinned_provider_without_its_key_falls_back_to_free():
    assert [p.name for p in chain(SearchSettings(provider="brave"))] == ["duckduckgo"]


def test_a_pinned_provider_with_its_key_stands_alone_but_for_free():
    providers = chain(SearchSettings(provider="tavily", tavily_key="k"))
    assert [p.name for p in providers] == ["tavily", "duckduckgo"]


def test_an_unknown_provider_choice_is_free_search():
    assert [p.name for p in chain(SearchSettings(provider="google"))] == ["duckduckgo"]


async def _run(searcher, query="rain in milan", count=5):
    async with aiohttp.ClientSession() as session:
        searcher._session = session
        try:
            return await searcher.search(query, count)
        finally:
            searcher._session = None


async def test_the_first_answer_wins_and_the_rest_are_never_asked(monkeypatch):
    first = Stub([Result("a", "https://a.example", "x")])
    second = Stub([Result("b", "https://b.example", "y")])
    monkeypatch.setattr(S, "chain", lambda settings, timeout=10: [first, second])
    searcher = Searcher(lambda: SearchSettings(), timeout=5)
    try:
        name, results = await _run(searcher)
    finally:
        await searcher.close()
    assert name == "stub"
    assert [r.url for r in results] == ["https://a.example"]
    assert second.calls == 0


async def test_a_dead_provider_costs_results_not_the_search(monkeypatch):
    dead = Stub(SearchError("Brave is out of quota or rate limiting (429)"))
    alive = Stub([Result("a", "https://a.example", "x")])
    monkeypatch.setattr(S, "chain", lambda settings, timeout=10: [dead, alive])
    searcher = Searcher(lambda: SearchSettings(), timeout=5)
    try:
        _, results = await _run(searcher)
    finally:
        await searcher.close()
    assert [r.url for r in results] == ["https://a.example"]


async def test_when_everybody_is_down_she_is_told_why(monkeypatch):
    monkeypatch.setattr(S, "chain", lambda settings, timeout=10: [Stub(SearchError("no."))])
    searcher = Searcher(lambda: SearchSettings(), timeout=5)
    try:
        with pytest.raises(SearchError, match="no."):
            await _run(searcher)
    finally:
        await searcher.close()


async def test_there_is_nothing_to_search_for():
    searcher = Searcher(lambda: SearchSettings())
    try:
        with pytest.raises(SearchError, match="nothing to search for"):
            await _run(searcher, query="   ")
    finally:
        await searcher.close()


async def test_a_key_pasted_in_the_dashboard_applies_to_the_next_search(monkeypatch):
    settings = SearchSettings()
    keyed = Stub([Result("k", "https://k.example", "")])
    keyed.name = "keyed"
    free = Stub([])
    free.name = "free"
    seen = []

    def fake_chain(s, timeout=10):
        seen.append(bool(s.brave_key))
        return [keyed, free] if s.brave_key else [free]

    monkeypatch.setattr(S, "chain", fake_chain)
    searcher = Searcher(lambda: settings, timeout=5, cache_ttl=600)
    try:
        name, _ = await _run(searcher)
        assert name == "free"
        settings.brave_key = "BSA-new"
        name, _ = await _run(searcher)
        assert name == "keyed"
    finally:
        await searcher.close()
    assert seen == [False, True]


def test_duplicate_links_are_answered_once():
    results = _dedupe([
        Result("a", "https://a.example/", "x"),
        Result("a again", "https://a.example", "y"),
        Result("b", "https://b.example", "z"),
    ])
    assert [r.url for r in results] == ["https://a.example/", "https://b.example"]


def test_keyed_providers_carry_their_credentials():
    assert Brave("k").key == "k"
    assert Tavily("k").key == "k"
    assert SearXNG("https://s.example/").base_url == "https://s.example"

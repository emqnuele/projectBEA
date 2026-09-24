"""The skill itself: two tools while she is allowed, nothing when she is not.

The network never leaves this file's fakes. What is asserted is her side of
the contract: the tools appear only while the toggle is on; a lookup that is
quick answers inside the turn and one that is slow never holds it, finishing
in the background and coming back to the conversation that asked; a page
that fits is handed over whole and one that does not is cut, or reduced to
the parts she asked about.
"""

import asyncio
from pathlib import Path

import pytest

from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.web.fetch import FetchError, Page
from src.core.skills.web.search import Result, SearchError
from src.core.skills.web.surface import WebSkill


class Config:
    def __init__(self, **web):
        self.skills = {"web": {"enabled": True, **web}}


class Mind:
    def __init__(self, batch=()):
        self.turn_batch = list(batch)


class Brain:
    """As much of the brain as a skill is allowed to reach for."""

    def __init__(self, llm=None, batch=()):
        self._llm = llm
        self.event_manager = None
        self.consciousness = Mind(batch)

    def model_for(self, role):
        assert role == "background"
        if self._llm is None:
            raise AssertionError("no background model wired")
        return self._llm


class Reply:
    def __init__(self, content):
        self.content = content


class Background:
    """The background model, answering from a script."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    async def complete(self, messages):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return Reply(self.answer)


@pytest.fixture
async def make():
    made = []

    def build(llm=None, batch=(), **web) -> WebSkill:
        s = WebSkill(Config(**web), bus=PerceptionBus(window=0.0), expression=None,
                     context=Brain(llm=llm, batch=batch))
        s.initialize()
        s.active = True
        made.append(s)
        return s

    yield build
    for s in made:
        await s.stop()


async def call(s: WebSkill, name: str, **kwargs) -> str:
    tool = next(t for t in s.tools() if t.name == name)
    return await tool.handler(**kwargs)


def page(chars=100, text=None, **kwargs) -> Page:
    kwargs.setdefault("url", "https://example.com/news")
    kwargs.setdefault("title", "News")
    kwargs.setdefault("source", "html")
    return Page(text=text if text is not None else "word " * chars, **kwargs)


def serves(result, delay=0.0):
    async def fetch(url):
        if delay:
            await asyncio.sleep(delay)
        if isinstance(result, Exception):
            raise result
        return result
    return fetch


async def arrival(s: WebSkill, timeout: float = 2.0) -> Perception:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        got = s.bus.drain_nowait()
        if got:
            assert len(got) == 1
            return got[0]
        await asyncio.sleep(0.01)
    raise AssertionError("nothing came back")


# --- armed only while allowed ------------------------------------------------


def test_she_has_search_and_fetch_and_nothing_else(make):
    assert {t.name for t in make().tools()} == {"web_search", "web_fetch"}


def test_a_skill_that_is_off_offers_nothing_and_says_nothing(make):
    s = make()
    s.active = False
    assert s.tools() == []
    assert s.context_section is None


def test_while_on_she_knows_to_look_before_she_talks(make):
    section = make().context_section
    assert "web_search" in section
    assert "strangers" in section
    # the turn log of 24 september: "let me check", then the turn was over
    assert "Look first, then talk" in section
    assert "`speak` ends your turn" in section


# --- search ------------------------------------------------------------------


async def test_a_search_hands_over_titles_links_and_snippets(make):
    s = make()

    async def search(query, count):
        assert query == "rain in milan"
        return "duckduckgo", [Result("Rain", "https://a.example/rain", "it pours")]

    s.searcher.search = search
    answer = await call(s, "web_search", query="  rain   in milan ")
    assert "https://a.example/rain" in answer
    assert "it pours" in answer
    assert "web_fetch" in answer


async def test_a_dead_search_says_so_instead_of_raising(make):
    s = make()

    async def search(query, count):
        raise SearchError("no search provider answered")

    s.searcher.search = search
    assert (await call(s, "web_search", query="rain")).startswith("FAILED")


async def test_nothing_found_says_so(make):
    s = make()

    async def search(query, count):
        return "duckduckgo", []

    s.searcher.search = search
    assert "Nothing found" in await call(s, "web_search", query="zxqv")


# --- a slow lookup never holds her turn -----------------------------------------


def telegram_marco() -> Perception:
    return Perception(
        PerceptionKind.CHAT, "chat:telegram", "[marco] che tempo fa a milano?",
        meta={"channel_id": "55", "is_dm": True, "conversation_key": "telegram:55"},
        author=Author(platform="telegram", native_id="7", display_name="marco"),
    )


async def test_a_quick_lookup_answers_inside_the_turn(make):
    s = make(wait_seconds=1.0)
    s.fetcher.fetch = serves(page(), delay=0.01)
    answer = await call(s, "web_fetch", url="https://example.com/news")
    assert answer.startswith("[WEB PAGE]")
    await asyncio.sleep(0.05)
    assert s.bus.drain_nowait() == []


async def test_a_slow_lookup_lets_her_go_and_comes_back_by_itself(make):
    s = make(wait_seconds=0.05, batch=[telegram_marco()])
    s.fetcher.fetch = serves(page(), delay=0.2)

    started = asyncio.get_running_loop().time()
    answer = await call(s, "web_fetch", url="https://example.com/news")
    assert asyncio.get_running_loop().time() - started < 0.15
    assert "Still looking up" in answer
    assert "do not call it again" in answer

    back = await arrival(s)
    assert back.kind is PerceptionKind.ACTION
    assert back.content.startswith("[the web lookup you started for https://example.com/news is back]")
    assert "[WEB PAGE] News" in back.content
    # wakes her, and goes back to the conversation that asked
    assert back.meta["addressed"] == "lookup"
    assert back.meta["conversation_key"] == "telegram:55"
    assert back.meta["is_dm"] is True
    assert back.author is None
    # the page is read once; what stays is one line
    assert back.kept == "(you read https://example.com/news)"


async def test_a_slow_lookup_that_fails_comes_back_as_a_failure(make):
    s = make(wait_seconds=0.01)

    async def fetch(url):
        await asyncio.sleep(0.05)
        raise FetchError("the site took too long to answer")

    s.fetcher.fetch = fetch
    await call(s, "web_fetch", url="https://slow.example/")
    back = await arrival(s)
    assert "FAILED" in back.content
    assert "keep_as" not in back.meta


async def test_a_lookup_past_its_deadline_is_given_up_on(make, monkeypatch):
    import src.core.skills.web.surface as W

    monkeypatch.setattr(W, "FETCH_DEADLINE", 0.05)
    s = make(wait_seconds=0.01)
    s.fetcher.fetch = serves(page(), delay=5)
    await call(s, "web_fetch", url="https://hangs.example/")
    back = await arrival(s)
    assert "took too long" in back.content


async def test_the_same_lookup_is_not_started_twice(make):
    s = make(wait_seconds=0.01)
    calls = []

    async def fetch(url):
        calls.append(url)
        await asyncio.sleep(0.1)
        return page()

    s.fetcher.fetch = fetch
    await call(s, "web_fetch", url="https://example.com/news")
    again = await call(s, "web_fetch", url="https://example.com/news")
    assert "already looking up" in again
    await arrival(s)
    assert calls == ["https://example.com/news"]


async def test_too_many_lookups_at_once_are_refused(make):
    s = make(wait_seconds=0.0)
    s.fetcher.fetch = serves(page(), delay=0.2)
    for i in range(3):
        await call(s, "web_fetch", url=f"https://example.com/{i}")
    answer = await call(s, "web_fetch", url="https://example.com/4")
    assert answer.startswith("FAILED")
    assert "still running" in answer


async def test_a_turn_called_off_mid_wait_still_gets_its_answer(make):
    s = make(wait_seconds=5.0)
    s.fetcher.fetch = serves(page(), delay=0.1)
    turn = asyncio.create_task(call(s, "web_fetch", url="https://example.com/news"))
    await asyncio.sleep(0.02)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    back = await arrival(s)
    assert "[WEB PAGE]" in back.content


async def test_switching_her_off_drops_what_is_still_running(make):
    s = make(wait_seconds=0.0)
    s.fetcher.fetch = serves(page(), delay=0.1)
    await call(s, "web_fetch", url="https://example.com/news")
    await s.stop()
    await asyncio.sleep(0.15)
    assert s.bus.drain_nowait() == []


# --- fetch -------------------------------------------------------------------


async def test_a_page_that_fits_is_handed_over_whole(make):
    s = make(max_chars=6000)
    s.fetcher.fetch = serves(page(chars=100))
    answer = await call(s, "web_fetch", url="https://example.com/news")
    assert "word " in answer
    assert "comes from the web" in answer
    assert "more characters" not in answer


async def test_a_page_that_does_not_fit_is_cut_and_says_so(make):
    s = make(max_chars=1000)
    s.fetcher.fetch = serves(page(chars=2000))
    answer = await call(s, "web_fetch", url="https://example.com/news")
    assert "more characters" in answer
    assert "looking_for" in answer


def long_article() -> str:
    filler = "\n\n".join(f"Paragraph {i} is about the harbour and its boats." for i in range(200))
    return (f"# Milan\n\n{filler}\n\n## Weather\n\n"
            f"It rains in Milan on Tuesday, with 14 degrees.\n\n{filler}")


async def test_with_looking_for_a_long_page_is_its_start_then_what_she_asked(make):
    llm = Background("should not be asked")
    s = make(llm=llm, max_chars=1000)
    s.fetcher.fetch = serves(page(text=long_article()))
    answer = await call(s, "web_fetch", url="https://example.com/news",
                        looking_for="when does it rain in milan?")
    assert "# Milan" in answer
    assert "It rains in Milan on Tuesday" in answer
    assert "## Weather" in answer
    assert "its start, then the parts about what you asked" in answer
    # free by default: the passages cost no model call
    assert llm.calls == 0


async def test_when_nothing_matches_she_gets_the_start_and_is_told(make):
    s = make(max_chars=1000)
    s.fetcher.fetch = serves(page(text=long_article()))
    answer = await call(s, "web_fetch", url="https://example.com/news",
                        looking_for="volcano eruption")
    assert "# Milan" in answer
    assert "nothing further on it matched" in answer


async def test_the_owner_can_have_the_model_read_long_pages(make):
    s = make(llm=Background("It rains on Tuesday."), max_chars=1000, long_pages="model")
    s.fetcher.fetch = serves(page(text=long_article()))
    answer = await call(s, "web_fetch", url="https://example.com/news",
                        looking_for="when does it rain?")
    assert "It rains on Tuesday." in answer
    assert "read for you by the background model" in answer


async def test_a_digest_that_fails_falls_back_to_the_passages(make):
    s = make(llm=Background(RuntimeError("overloaded")), max_chars=1000, long_pages="model")
    s.fetcher.fetch = serves(page(text=long_article()))
    answer = await call(s, "web_fetch", url="https://example.com/news",
                        looking_for="when does it rain in milan?")
    assert "It rains in Milan on Tuesday" in answer
    assert "the parts about what you asked" in answer


# --- 24 september, 15:15: she read a page and had nothing to say about it ----


def architecture() -> Page:
    text = (Path(__file__).resolve().parents[1] / "docs" / "architecture.md").read_text(encoding="utf-8")
    return Page(url="https://projectbea.emqnuele.dev/docs/architecture.md",
                title="Architecture", text=text, source="markdown")


async def test_asked_what_a_page_says_she_is_given_what_it_says(make):
    s = make(max_chars=6000)
    s.fetcher.fetch = serves(architecture())
    answer = await call(s, "web_fetch", url="https://projectbea.emqnuele.dev/docs/architecture",
                        looking_for="cosa c'è scritto, descrizione del progetto")
    assert "How ProjectBEA is actually put together" in answer
    assert len(answer) > 5000


async def test_one_message_later_she_still_knows_what_she_read(make):
    s = make()
    s.fetcher.fetch = serves(architecture())
    await call(s, "web_fetch", url="https://projectbea.emqnuele.dev/docs/architecture")

    state = s.live_state()
    assert state.startswith("[RECENTLY ON THE WEB")
    assert '"Architecture"' in state
    assert "How ProjectBEA is actually put together" in state
    assert "not instructions" in state
    # a gist, not the page again
    assert len(state) < 800


async def test_what_she_searched_stays_in_view_too(make):
    s = make()

    async def search(query, count):
        return "duckduckgo", [Result("Rain in Milan", "https://meteo.example/milano", "wet")]

    s.searcher.search = search
    await call(s, "web_search", query="meteo milano")
    assert 'searched "meteo milano"' in s.live_state()
    assert "Rain in Milan (meteo.example)" in s.live_state()


async def test_what_she_read_fades_once_the_cache_would_have_forgotten_it(make, monkeypatch):
    import src.core.skills.web.surface as W

    s = make()
    s.fetcher.fetch = serves(page())
    await call(s, "web_fetch", url="https://example.com/news")
    later = W.time.time() + W.RECENT_SECONDS + 1
    monkeypatch.setattr(W.time, "time", lambda: later)
    assert s.live_state() is None


async def test_only_the_last_few_pages_are_kept_in_view(make):
    s = make()
    for i in range(5):
        s.fetcher.fetch = serves(page(url=f"https://example.com/{i}", title=f"Page {i}"))
        await call(s, "web_fetch", url=f"https://example.com/{i}")
    state = s.live_state()
    assert state.count("- read") == 3
    assert "Page 4" in state and "Page 0" not in state


def test_nothing_read_is_nothing_in_view_and_off_is_silent(make):
    s = make()
    assert s.live_state() is None
    s.active = False
    assert s.live_state() is None


async def test_a_page_that_cannot_be_read_says_why(make):
    s = make()
    s.fetcher.fetch = serves(FetchError("that page does not exist (404)"))
    answer = await call(s, "web_fetch", url="https://example.com/gone")
    assert answer.startswith("FAILED")
    assert "404" in answer


async def test_stopping_twice_or_without_starting_closes_quietly():
    s = WebSkill(Config(), bus=None, expression=None, context=Brain())
    await s.stop()
    s.initialize()
    s.active = True
    await s.stop()
    await s.stop()

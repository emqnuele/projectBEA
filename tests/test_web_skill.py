"""The skill itself: two tools while she is allowed, nothing when she is not.

The network never leaves this file's fakes. What is asserted is her side of
the contract: the tools appear only while the toggle is on, a page that fits
is handed over whole, one that does not is cut — or read for her when she
said what she is after — and a digest that fails costs her the cut page,
never the page itself.
"""


from src.core.skills.web.fetch import FetchError, Page
from src.core.skills.web.search import Result, SearchError
from src.core.skills.web.surface import WebSkill


class Config:
    def __init__(self, **web):
        self.skills = {"web": {"enabled": True, **web}}


class Brain:
    """The much of the brain a skill is allowed to reach for."""

    def __init__(self, llm=None):
        self._llm = llm
        self.event_manager = None

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

    async def complete(self, messages):
        if isinstance(self.answer, Exception):
            raise self.answer
        return Reply(self.answer)


def skill(**web) -> WebSkill:
    s = WebSkill(Config(**web), bus=None, expression=None, context=Brain())
    s.initialize()
    s.active = True
    return s


def tool(s: WebSkill, name: str):
    return next(t for t in s.tools() if t.name == name)


async def call(s: WebSkill, name: str, **kwargs) -> str:
    return await tool(s, name).handler(**kwargs)


async def close(s: WebSkill):
    await s.stop()

async def _async_page(chars):
    return _page(chars=chars)




# --- armed only while allowed ------------------------------------------------


def test_she_has_search_and_fetch_and_nothing_else():
    assert {t.name for t in skill().tools()} == {"web_search", "web_fetch"}


def test_a_skill_that_is_off_offers_nothing_and_says_nothing():
    s = skill()
    s.active = False
    assert s.tools() == []
    assert s.context_section is None


def test_while_on_she_knows_the_rules():
    section = skill().context_section
    assert "web_search" in section
    assert "strangers" in section


# --- search ------------------------------------------------------------------


async def test_a_search_hands_over_titles_links_and_snippets():
    s = skill()

    async def search(query, count):
        assert query == "rain in milan"
        return "duckduckgo", [Result("Rain", "https://a.example/rain", "it pours")]

    s.searcher.search = search
    try:
        answer = await call(s, "web_search", query="rain in milan")
    finally:
        await close(s)
    assert "https://a.example/rain" in answer
    assert "it pours" in answer
    assert "web_fetch" in answer


async def test_a_dead_search_says_so_instead_of_raising():
    s = skill()

    async def search(query, count):
        raise SearchError("no search provider answered")

    s.searcher.search = search
    try:
        answer = await call(s, "web_search", query="rain")
    finally:
        await close(s)
    assert answer.startswith("FAILED")


async def test_nothing_found_says_so():
    s = skill()

    async def search(query, count):
        return "duckduckgo", []

    s.searcher.search = search
    try:
        answer = await call(s, "web_search", query="zxqv")
    finally:
        await close(s)
    assert "Nothing found" in answer


# --- fetch -------------------------------------------------------------------


def _page(chars=100, **kwargs):
    kwargs.setdefault("url", "https://example.com/news")
    kwargs.setdefault("title", "News")
    kwargs.setdefault("text", "word " * chars)
    kwargs.setdefault("source", "html")
    return Page(**kwargs)


async def test_a_page_that_fits_is_handed_over_whole():
    s = skill(max_chars=6000)
    s.fetcher.fetch = lambda url: _async_page(chars=100)
    try:
        answer = await call(s, "web_fetch", url="https://example.com/news")
    finally:
        await close(s)
    assert "word " in answer
    assert "comes from the web" in answer
    assert "more characters" not in answer


async def test_a_page_that_does_not_fit_is_cut_and_says_so():
    s = skill(max_chars=1000)
    s.fetcher.fetch = lambda url: _async_page(chars=2000)
    try:
        answer = await call(s, "web_fetch", url="https://example.com/news")
    finally:
        await close(s)
    assert "more characters" in answer
    assert "looking_for" in answer


async def test_with_looking_for_a_long_page_is_read_for_her():
    s = WebSkill(Config(max_chars=1000), bus=None, expression=None,
                 context=Brain(llm=Background("It rains on Tuesday.")))
    s.initialize()
    s.active = True
    s.fetcher.fetch = lambda url: _async_page(chars=2000)
    try:
        answer = await call(s, "web_fetch", url="https://example.com/news",
                            looking_for="when does it rain?")
    finally:
        await close(s)
    assert "It rains on Tuesday." in answer
    assert "only the part you asked for" in answer


async def test_a_digest_that_fails_costs_her_the_cut_page_not_the_page():
    s = WebSkill(Config(max_chars=1000), bus=None, expression=None,
                 context=Brain(llm=Background(RuntimeError("overloaded"))))
    s.initialize()
    s.active = True
    s.fetcher.fetch = lambda url: _async_page(chars=2000)
    try:
        answer = await call(s, "web_fetch", url="https://example.com/news",
                            looking_for="when does it rain?")
    finally:
        await close(s)
    assert "word " in answer
    assert "more characters" in answer


async def test_without_a_background_model_there_is_no_digest_either():
    s = skill(max_chars=1000)
    s.fetcher.fetch = lambda url: _async_page(chars=2000)
    try:
        answer = await call(s, "web_fetch", url="https://example.com/news",
                            looking_for="when does it rain?")
    finally:
        await close(s)
    assert "more characters" in answer


async def test_a_page_that_cannot_be_read_says_why():
    s = skill()

    async def fetch(url):
        raise FetchError("that page does not exist (404)")

    s.fetcher.fetch = fetch
    try:
        answer = await call(s, "web_fetch", url="https://example.com/gone")
    finally:
        await close(s)
    assert answer.startswith("FAILED")
    assert "404" in answer


async def test_stopping_twice_or_without_starting_closes_quietly():
    s = WebSkill(Config(), bus=None, expression=None, context=Brain())
    await s.stop()
    s.initialize()
    s.active = True
    await s.stop()
    await s.stop()

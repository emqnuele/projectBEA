"""Searching the web without depending on any one search engine staying friendly.

Scraping a single engine is a dependency on its mood: Google in particular
blocks automated queries within a handful of requests. So there is a chain.
Whatever the owner has configured with a key or an instance goes first — an
API is the only thing that is reliable by contract — and the keyless search
always sits at the end, so she can search out of the box and still search
when a key runs out of quota.

The keyless search is `ddgs`, which queries several engines at once and
merges them: one of them blocking a request costs results, not the search.
"""

import asyncio
import html
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiohttp

from src.utils.logger import get_logger

logger = get_logger("bea.skills.web.search")

PROVIDERS = ("auto", "duckduckgo", "brave", "tavily", "searxng")

SAFESEARCH = ("strict", "moderate", "off")

SNIPPET_CHARS = 300

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


class SearchError(Exception):
    """A search that could not be made, with a reason she can be told."""


@dataclass
class Result:
    title: str
    url: str
    snippet: str


def _clean(text: Any, limit: int = SNIPPET_CHARS) -> str:
    text = _SPACE.sub(" ", html.unescape(_TAG.sub("", str(text or "")))).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _results(rows: List[Dict[str, Any]], title: str, url: str, snippet: str) -> List[Result]:
    out = []
    for row in rows:
        link = str(row.get(url) or "").strip()
        if link.startswith(("http://", "https://")):
            out.append(Result(_clean(row.get(title), 150) or link, link, _clean(row.get(snippet))))
    return out


# --- providers ---------------------------------------------------------------


class Provider:
    name = "provider"

    async def search(self, session: aiohttp.ClientSession, query: str, count: int,
                     safesearch: str) -> List[Result]:
        raise NotImplementedError


class DuckDuckGo(Provider):
    """Keyless. `ddgs` spreads the query across engines and merges the answers."""

    name = "duckduckgo"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def search(self, session, query, count, safesearch):
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException

        level = {"strict": "on"}.get(safesearch, safesearch)

        def run() -> List[Dict[str, Any]]:
            try:
                return DDGS(timeout=self.timeout).text(
                    query, max_results=count, safesearch=level, backend="auto")
            except DDGSException as e:
                # ddgs reports an honest empty result as an exception
                if str(e).startswith("No results"):
                    return []
                raise

        # ddgs is synchronous and blocks on the network
        rows = await asyncio.to_thread(run)
        return _results(rows, "title", "href", "body")


class Brave(Provider):
    name = "brave"
    URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, key: str):
        self.key = key

    async def search(self, session, query, count, safesearch):
        async with session.get(
            self.URL,
            params={"q": query, "count": min(count, 20), "safesearch": safesearch},
            headers={"Accept": "application/json", "X-Subscription-Token": self.key},
        ) as resp:
            _raise_for(resp, "Brave")
            data = await resp.json()
        return _results((data.get("web") or {}).get("results") or [], "title", "url", "description")


class Tavily(Provider):
    name = "tavily"
    URL = "https://api.tavily.com/search"

    def __init__(self, key: str):
        self.key = key

    async def search(self, session, query, count, safesearch):
        # tavily has no safe-search switch; it filters adult content on its own
        async with session.post(
            self.URL,
            json={"query": query, "max_results": min(count, 20), "search_depth": "basic"},
            headers={"Authorization": f"Bearer {self.key}"},
        ) as resp:
            _raise_for(resp, "Tavily")
            data = await resp.json()
        return _results(data.get("results") or [], "title", "url", "content")


class SearXNG(Provider):
    name = "searxng"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def search(self, session, query, count, safesearch):
        level = {"off": 0, "moderate": 1, "strict": 2}.get(safesearch, 1)
        async with session.get(
            f"{self.base_url}/search",
            params={"q": query, "format": "json", "safesearch": level},
        ) as resp:
            if resp.status == 403:
                raise SearchError("SearXNG refused JSON: add `json` to search.formats "
                                  "in the instance's settings.yml")
            _raise_for(resp, "SearXNG")
            data = await resp.json(content_type=None)
        return _results(data.get("results") or [], "title", "url", "content")[:count]


def _raise_for(resp: aiohttp.ClientResponse, label: str) -> None:
    if resp.status in (401, 403):
        raise SearchError(f"{label} rejected the key ({resp.status})")
    if resp.status == 429:
        raise SearchError(f"{label} is out of quota or rate limiting (429)")
    if resp.status >= 400:
        raise SearchError(f"{label} answered {resp.status}")


# --- the chain ---------------------------------------------------------------


@dataclass
class SearchSettings:
    provider: str = "auto"
    brave_key: str = ""
    tavily_key: str = ""
    searxng_url: str = ""
    safesearch: str = "moderate"


def chain(settings: SearchSettings, timeout: int = 10) -> List[Provider]:
    """The providers to try, in order. The keyless one is always last."""
    configured: Dict[str, Provider] = {}
    if settings.searxng_url:
        configured["searxng"] = SearXNG(settings.searxng_url)
    if settings.brave_key:
        configured["brave"] = Brave(settings.brave_key)
    if settings.tavily_key:
        configured["tavily"] = Tavily(settings.tavily_key)

    choice = settings.provider if settings.provider in PROVIDERS else "auto"
    if choice == "auto":
        order = list(configured.values())
    elif choice == "duckduckgo":
        order = []
    elif choice in configured:
        order = [configured[choice]]
    else:
        logger.warning(f"Web search is set to {choice}, which has no key or URL; "
                       "searching without it.")
        order = []
    return [*order, DuckDuckGo(timeout=timeout)]


class Searcher:
    """Runs a query down the chain until one provider answers."""

    def __init__(self, settings: Callable[[], SearchSettings], timeout: float = 10.0,
                 cache_ttl: float = 600.0, cache_size: int = 64):
        # a getter, not a value: a key pasted in the dashboard applies to the next search
        self._settings = settings
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        self._cache: "OrderedDict[tuple, Tuple[float, str, List[Result]]]" = OrderedDict()
        self._session: Optional[aiohttp.ClientSession] = None

    def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def search(self, query: str, count: int) -> Tuple[str, List[Result]]:
        """(who answered, results). Raises SearchError when nobody could."""
        query = _SPACE.sub(" ", query or "").strip()
        if not query:
            raise SearchError("there is nothing to search for")
        settings = self._settings()
        # what the answer depends on, besides the words: a key pasted in the
        # dashboard must apply to the next search, not the one after the cache
        # expires. Presence, never the key itself.
        key = (query.lower(), count, settings.provider, settings.safesearch,
               bool(settings.brave_key), bool(settings.tavily_key), settings.searxng_url)
        hit = self._cache.get(key)
        if hit is not None and time.monotonic() - hit[0] <= self.cache_ttl:
            return hit[1], hit[2]

        reasons: List[str] = []
        for provider in chain(settings, timeout=int(self.timeout)):
            try:
                results = await asyncio.wait_for(
                    provider.search(self._client(), query, count, settings.safesearch),
                    timeout=self.timeout + 2)
            except SearchError as e:
                reason = str(e)
            except asyncio.TimeoutError:
                reason = f"{provider.name} took too long"
            except Exception as e:
                reason = f"{provider.name} failed ({type(e).__name__}: {e})"
            else:
                results = _dedupe(results)[:count]
                self._store(key, provider.name, results)
                return provider.name, results
            logger.warning(f"Web search via {provider.name} failed: {reason}")
            reasons.append(reason)
        raise SearchError("; ".join(reasons) or "no search provider answered")

    def _store(self, key, provider: str, results: List[Result]) -> None:
        self._cache[key] = (time.monotonic(), provider, results)
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)


def _dedupe(results: List[Result]) -> List[Result]:
    seen = set()
    out = []
    for r in results:
        marker = r.url.rstrip("/")
        if marker not in seen:
            seen.add(marker)
            out.append(r)
    return out

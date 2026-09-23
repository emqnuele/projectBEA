"""Reading a web page the way a model should read it: as text, not as HTML.

The cheapest good version of a page is tried first. A server that answers
`Accept: text/markdown`, or advertises a markdown alternate, has already done
the conversion; only when neither exists is the HTML reduced to its main
content, which is what almost every page actually needs. A front page also
brings the site's `llms.txt` when it has one: the site describing itself to a
model, next to what the page says right now.
"""

import asyncio
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp

from src.core.skills.web.guard import BlockedAddress, BlockedURL, PublicOnlyResolver, normalize
from src.core.update.version import current_version
from src.utils.logger import get_logger

logger = get_logger("bea.skills.web.fetch")

USER_AGENT = (f"Mozilla/5.0 (compatible; ProjectBEA/{current_version()}; "
              "+https://github.com/emqnuele/projectBEA)")

# markdown first, so a server that can skip the conversion does
ACCEPT = ("text/markdown, text/html;q=0.9, application/xhtml+xml;q=0.9, "
          "text/plain;q=0.8, */*;q=0.5")

MAX_REDIRECTS = 5

_REDIRECTS = {301, 302, 303, 307, 308}
_HTML = ("text/html", "application/xhtml+xml")
_MARKDOWN = ("text/markdown", "text/x-markdown")
_TEXT = ("text/plain", "application/json", "text/csv", "text/xml", "application/xml",
         "application/rss+xml", "application/atom+xml")

# an extraction shorter than this is a page that is mostly script, not a short page
MIN_EXTRACTED = 200

MAX_LINKS = 25

_ALTERNATE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r'([a-zA-Z-]+)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)')
_MD_LINK = re.compile(r"(!?)\[([^\]]*)\]\((\S+?)(?:\s+\"[^\"]*\")?\)")
_CITATION = re.compile(r"<sup>.*?</sup>", re.DOTALL)


class FetchError(Exception):
    """A page that could not be read, with a reason she can be told."""


@dataclass
class Page:
    url: str
    title: str
    text: str
    # where the text came from: llms.txt, markdown, html or text
    source: str
    links: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class _Response:
    url: str
    status: int
    content_type: str
    charset: Optional[str]
    body: bytes

    def decoded(self) -> str:
        return self.body.decode(self.charset or "utf-8", errors="replace")


class Fetcher:
    """Fetches public pages and turns them into markdown she can read."""

    def __init__(self, timeout: float = 15.0, max_bytes: int = 3_000_000,
                 cache_ttl: float = 900.0, cache_size: int = 32):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        self._cache: "OrderedDict[str, Tuple[float, Page]]" = OrderedDict()
        self._session: Optional[aiohttp.ClientSession] = None

    def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(resolver=PublicOnlyResolver(), limit=8),
                timeout=aiohttp.ClientTimeout(total=self.timeout, sock_connect=5),
                headers={"User-Agent": USER_AGENT},
                # a proxy resolves the name itself, out of the guard's sight
                trust_env=False,
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    # --- the page ------------------------------------------------------------

    async def fetch(self, url: str) -> Page:
        try:
            url = normalize(url)
        except BlockedURL as e:
            raise FetchError(str(e)) from e

        cached = self._cached(url)
        if cached is not None:
            return cached

        page = await self._read(url)
        self._store(url, page)
        return page

    async def _read(self, url: str) -> Page:
        parts = urlsplit(url)
        if parts.path not in ("", "/") or parts.query:
            return await self._page(url)

        # a front page: what is on it right now, and what the site says about
        # itself for models. Asked for together, so the index costs no latency
        page, index = await asyncio.gather(self._page(url), self._llms_txt(parts),
                                           return_exceptions=True)
        if isinstance(index, BaseException):
            index = None
        if isinstance(page, BaseException):
            if index is not None:
                return index
            raise page
        if index is None:
            return page
        return _merged(page, index)

    async def _page(self, url: str) -> Page:
        resp = await self._get(url, accept=ACCEPT)
        kind = resp.content_type

        if kind in _MARKDOWN:
            return _markdown_page(resp.url, resp.decoded(), "markdown")

        # a server that sends no type gets octet-stream from aiohttp; sniff it
        untyped = kind in ("", "application/octet-stream")
        if kind in _HTML or (untyped and resp.body.lstrip()[:1] == b"<"):
            alternate = _markdown_alternate(resp.body, resp.url)
            if alternate:
                page = await self._alternate(alternate)
                if page is not None:
                    return page
            return await asyncio.to_thread(_html_page, resp.url, resp.body)

        if kind.startswith("text/") or kind in _TEXT:
            return Page(url=resp.url, title="", text=resp.decoded().strip(), source="text")

        raise FetchError(f"that link is a {kind or 'file of unknown type'}, not a page you can read")

    async def _llms_txt(self, parts) -> Optional[Page]:
        """The site's own summary for models, when it has one.

        Every failure is silent: most sites have none, and its absence must
        never cost the page itself.
        """
        index = urlunsplit((parts.scheme, parts.netloc, "/llms.txt", "", ""))
        try:
            resp = await self._get(index, accept="text/markdown, text/plain")
        except FetchError:
            return None
        text = resp.decoded().lstrip()
        # the format requires an H1; a single-page app answers every path with
        # its shell, and that is not an index
        if resp.content_type not in ("text/plain", *_MARKDOWN) or not text.startswith("# "):
            return None
        logger.info(f"Found {index}.")
        return _markdown_page(resp.url, text, "llms.txt")

    async def _alternate(self, url: str) -> Optional[Page]:
        try:
            resp = await self._get(url, accept="text/markdown, text/plain;q=0.9")
        except FetchError:
            return None
        if resp.content_type not in ("text/plain", *_MARKDOWN):
            return None
        return _markdown_page(resp.url, resp.decoded(), "markdown")

    # --- the wire --------------------------------------------------------------

    async def _get(self, url: str, accept: str) -> _Response:
        """One GET, following redirects by hand so every hop is checked."""
        session = self._client()
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with session.get(url, headers={"Accept": accept},
                                       allow_redirects=False) as resp:
                    if resp.status in _REDIRECTS and "Location" in resp.headers:
                        url = normalize(urljoin(url, resp.headers["Location"]))
                        continue
                    if resp.status >= 400:
                        raise FetchError(_status_reason(resp.status))
                    body = await self._body(resp)
                    return _Response(url=str(resp.url), status=resp.status,
                                     content_type=(resp.content_type or "").lower(),
                                     charset=resp.charset, body=body)
            except BlockedURL as e:
                raise FetchError(f"it redirects somewhere you may not go ({e})") from e
            except aiohttp.ClientConnectorError as e:
                if isinstance(e.os_error, BlockedAddress) or isinstance(e.__cause__, BlockedAddress):
                    raise FetchError("that address is on a private network") from e
                raise FetchError(f"could not reach {urlsplit(url).hostname}") from e
            except asyncio.TimeoutError as e:
                raise FetchError("the site took too long to answer") from e
            except aiohttp.ClientError as e:
                raise FetchError(f"the connection failed ({type(e).__name__})") from e
        raise FetchError("it redirects too many times")

    async def _body(self, resp: aiohttp.ClientResponse) -> bytes:
        """The body, cut at `max_bytes`: a page is read, never downloaded whole."""
        chunks: List[bytes] = []
        size = 0
        async for chunk in resp.content.iter_chunked(65536):
            chunks.append(chunk)
            size += len(chunk)
            if size >= self.max_bytes:
                break
        return b"".join(chunks)[:self.max_bytes]

    # --- cache ---------------------------------------------------------------

    def _cached(self, url: str) -> Optional[Page]:
        hit = self._cache.get(url)
        if hit is None:
            return None
        stored, page = hit
        if time.monotonic() - stored > self.cache_ttl:
            del self._cache[url]
            return None
        self._cache.move_to_end(url)
        return page

    def _store(self, url: str, page: Page) -> None:
        self._cache[url] = (time.monotonic(), page)
        self._cache.move_to_end(url)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)


# --- turning bytes into text ---------------------------------------------------


def _status_reason(status: int) -> str:
    if status in (401, 403):
        return f"the site refused ({status}) — it may block automated readers"
    if status == 404:
        return "that page does not exist (404)"
    if status == 429:
        return "the site is rate limiting (429) — try again later"
    return f"the site answered with an error ({status})"


def _markdown_alternate(body: bytes, base: str) -> Optional[str]:
    """The markdown version a page advertises in its head, if it does."""
    head = body[:65536].decode("utf-8", errors="replace")
    for tag in _ALTERNATE.findall(head):
        attrs = {k.lower(): v.strip("\"'") for k, v in _ATTR.findall(tag)}
        if (attrs.get("rel", "").lower() == "alternate"
                and attrs.get("type", "").lower() in _MARKDOWN and attrs.get("href")):
            try:
                return normalize(urljoin(base, attrs["href"]))
            except BlockedURL:
                return None
    return None


def _markdown_page(url: str, text: str, source: str) -> Page:
    text = text.strip()
    title = ""
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    body, links = _split_links(text, url)
    return Page(url=url, title=title, text=body, source=source, links=links)


def _merged(page: Page, index: Page) -> Page:
    """The front page first — it is what she asked for — then the site's own index."""
    text = f"{page.text}\n\n## What the site says about itself (llms.txt)\n\n{index.text}"
    seen = {href for _, href in page.links}
    links = page.links + [(label, href) for label, href in index.links if href not in seen]
    return Page(url=page.url, title=page.title or index.title, text=text,
                source=f"{page.source} + llms.txt", links=links[:MAX_LINKS])


def _html_page(url: str, raw: bytes) -> Page:
    """The main content of an HTML page, as markdown. Runs in a thread: lxml is CPU."""
    import trafilatura

    tree = trafilatura.load_html(raw)
    if tree is None:
        raise FetchError("the page could not be parsed")
    meta = trafilatura.extract_metadata(tree, default_url=url)
    title = (meta.title or "").strip() if meta else ""
    description = (meta.description or "").strip() if meta else ""

    body = trafilatura.extract(
        raw, url=url, output_format="markdown", include_links=True,
        include_formatting=True, include_tables=True, include_comments=False,
        include_images=False,
    ) or ""
    if len(body) < MIN_EXTRACTED:
        # nothing that looks like an article: every visible word beats none
        body = trafilatura.html2txt(raw) or body

    body = _CITATION.sub("", body)
    body, links = _split_links(body, url)

    # the description often says what the page is better than its body does
    if description and description[:80] not in body:
        body = f"{description}\n\n{body}" if body else description
    if not body.strip():
        raise FetchError("the page has no readable text (it may need a browser to render)")
    return Page(url=url, title=title, text=body.strip(), source="html", links=links)


def _split_links(text: str, page_url: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Inline links out of the prose, into a short list after it.

    Inline, a link costs more tokens than the words it sits on; listed once at
    the end, she can still follow any of them.
    """
    here = page_url.split("#", 1)[0]
    links: List[Tuple[str, str]] = []
    seen = set()

    def keep(match: "re.Match[str]") -> str:
        image, label, href = match.group(1), match.group(2).strip(), match.group(3)
        if image:
            return ""
        target = urljoin(page_url, href)
        if (target.startswith(("http://", "https://")) and target.split("#", 1)[0] != here
                and len(label) >= 3 and target not in seen and len(links) < MAX_LINKS):
            seen.add(target)
            links.append((label, target))
        return label

    return _MD_LINK.sub(keep, text), links

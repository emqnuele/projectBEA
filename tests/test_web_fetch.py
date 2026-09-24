"""Reading a page as text, without touching the network.

The wire is covered by `test_web_guard.py` (what she may open) and one live
smoke test the author runs by hand. What is asserted here is everything after
the bytes arrive: markdown taken as it is, HTML reduced to its main content,
links moved out of the prose, and a site's own index merged after the page —
never instead of it.
"""

import pytest

from src.core.skills.web import fetch as F
from src.core.skills.web.fetch import Fetcher, FetchError
from src.core.skills.web.surface import _cut


def test_a_short_page_is_handed_over_whole():
    assert _cut("hello", 6000) == "hello"


def test_a_long_page_is_cut_at_a_paragraph_not_mid_word():
    text = "first paragraph.\n\nsecond paragraph that goes on a while. " * 500
    cut = _cut(text, 1000)
    assert len(cut) <= 1000
    assert cut.endswith("paragraph.") or cut.endswith("…")
    assert "paragraph. second" not in cut[len(cut) - 50:]


def test_a_markdown_page_keeps_its_title_and_lists_its_links():
    page = F._markdown_page(
        "https://example.com/guide",
        "# The Guide\n\nRead [the docs](https://example.com/docs) first.\n",
        "markdown",
    )
    assert page.title == "The Guide"
    assert "the docs" in page.text
    assert "[the docs](https://example.com/docs)" not in page.text
    assert ("the docs", "https://example.com/docs") in page.links
    assert page.source == "markdown"


def test_images_and_same_page_anchors_are_not_links_to_follow():
    page = F._markdown_page(
        "https://example.com/p",
        "# P\n\n![logo](https://example.com/logo.png) and "
        "[here](#intro) and [out](https://example.com/out).\n",
        "markdown",
    )
    assert page.links == [("out", "https://example.com/out")]


def test_an_html_article_becomes_its_main_content():
    raw = b"""<html><head><title>News</title>
        <meta name="description" content="What happened today."></head>
        <body><nav>home about contact login subscribe advertise</nav>
        <article><h1>Big thing</h1>
        <p>The council voted yes after a long debate about the budget.</p>
        <p>Everyone went home late and nobody was unhappy.</p></article>
        <script>var x = 1;</script></body></html>"""
    page = F._html_page("https://example.com/news", raw)
    assert page.title == "Big thing"
    assert "voted yes" in page.text
    assert "var x" not in page.text


def test_a_script_shell_with_no_readable_text_is_refused():
    with pytest.raises(FetchError, match="no readable text"):
        F._html_page("https://example.com/app",
                     b"<html><body><script>window.app=true;</script></body></html>")


def test_a_page_advertising_markdown_is_followed():
    raw = (b'<html><head><link rel="alternate" type="text/markdown" '
           b'href="/page.md"></head><body>x</body></html>')
    assert F._markdown_alternate(raw, "https://example.com/page") == \
        "https://example.com/page.md"


def test_an_alternate_pointing_inside_is_ignored_not_followed():
    raw = (b'<html><head><link rel="alternate" type="text/markdown" '
           b'href="http://127.0.0.1/secret.md"></head><body>x</body></html>')
    assert F._markdown_alternate(raw, "https://example.com/page") is None


def test_the_front_page_comes_first_and_the_index_after():
    page = F.Page(url="https://example.com/", title="Today",
                  text="Today: rain.", source="html")
    index = F.Page(url="https://example.com/llms.txt", title="Example",
                   text="# Example\nWe sell hats.", source="llms.txt",
                   links=[("hats", "https://example.com/hats")])
    merged = F._merged(page, index)
    assert merged.text.index("rain") < merged.text.index("hats")
    assert merged.url == "https://example.com/"
    assert ("hats", "https://example.com/hats") in merged.links


def test_refusals_say_why_in_her_words():
    assert "block automated readers" in F._status_reason(403)
    assert "404" in F._status_reason(404)
    assert "rate limiting" in F._status_reason(429)


async def test_a_fetcher_without_sessions_closes_quietly():
    await Fetcher().close()


def test_a_link_whose_address_has_parentheses_is_lifted_out_whole():
    page = F._markdown_page(
        "https://it.wikipedia.org/wiki/Milano",
        "# Milano\n\nIn [Lombardia](<https://it.wikipedia.org/wiki/Regione_(Italia)>) today.\n",
        "markdown",
    )
    assert "In Lombardia today." in page.text
    assert ("Lombardia", "https://it.wikipedia.org/wiki/Regione_(Italia)") in page.links


def test_wikipedia_references_do_not_survive_as_noise():
    converted = "duca.[\\[N 6\\]](https://it.wikipedia.org#cite_note-78) fine"
    assert F._REFERENCE.sub("", converted) == "duca. fine"
    kept = "see [the docs](https://example.com/docs)"
    assert F._REFERENCE.sub("", kept) == kept


# --- the wire, against a real server on loopback --------------------------------
#
# The guard refuses loopback, which is the point of it; here it is opened for
# 127.0.0.1 alone, so every other private address stays refused and the
# redirect checks are exercised for real.


ARTICLE = (b"<html><head><title>News</title></head><body><nav>home about</nav><article>"
           b"<h1>Big thing</h1><p>The council voted yes after a long debate about the "
           b"budget, and the meeting ran late into the evening.</p><p>Everyone went "
           b"home late and nobody was unhappy with how it ended.</p>"
           + b"<p>The mayor thanked the members for their patience and promised that the "
           b"next session would start earlier, with the agenda sent out a week ahead.</p>" * 3
           + b"</article></body></html>")


@pytest.fixture
async def site(monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    from src.core.skills.web import guard

    real = guard.is_public
    monkeypatch.setattr(guard, "is_public", lambda a: a == "127.0.0.1" or real(a))

    hits = []
    app = web.Application()

    def route(path, handler):
        async def counted(request):
            hits.append(request.path)
            return await handler(request)
        app.router.add_get(path, counted)

    async def article(request):
        return web.Response(body=ARTICLE, content_type="text/html")

    async def negotiates(request):
        if "text/markdown" in request.headers.get("Accept", ""):
            return web.Response(text="# Guide\n\nAlready markdown.", content_type="text/markdown")
        return web.Response(body=ARTICLE, content_type="text/html")

    async def advertises(request):
        return web.Response(
            body=b'<html><head><link rel="alternate" type="text/markdown" href="/doc.md">'
                 b'</head><body>x</body></html>', content_type="text/html")

    async def doc_md(request):
        return web.Response(text="# Doc\n\nThe markdown twin.", content_type="text/plain")

    async def front(request):
        return web.Response(body=ARTICLE, content_type="text/html")

    async def llms(request):
        return web.Response(text="# Example\n\n> We sell hats.", content_type="text/plain")

    async def to_private(request):
        raise web.HTTPFound("http://10.0.0.1/admin")

    async def loop(request):
        raise web.HTTPFound("/loop")

    async def nowhere(request):
        return web.Response(status=302)

    async def huge(request):
        return web.Response(text="a" * 50_000, content_type="text/plain")

    async def binary(request):
        return web.Response(body=b"\x89PNG....", content_type="image/png")

    async def untyped(request):
        response = web.Response(body=ARTICLE)
        response.headers["Content-Type"] = ""
        return response

    for path, handler in [("/article", article), ("/negotiates", negotiates),
                          ("/advertises", advertises), ("/doc.md", doc_md), ("/", front),
                          ("/llms.txt", llms), ("/to-private", to_private), ("/loop", loop), ("/nowhere-redirect", nowhere),
                          ("/huge", huge), ("/binary", binary), ("/untyped", untyped)]:
        route(path, handler)

    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    fetcher = Fetcher(timeout=5, max_bytes=10_000)
    try:
        yield (lambda path: str(server.make_url(path))), fetcher, hits
    finally:
        await fetcher.close()
        await server.close()


async def test_an_html_page_is_read_as_its_main_content(site):
    url, fetcher, _ = site
    page = await fetcher.fetch(url("/article"))
    assert page.source == "html"
    assert "voted yes" in page.text
    assert "home about" not in page.text


async def test_a_server_that_speaks_markdown_is_taken_at_its_word(site):
    url, fetcher, _ = site
    page = await fetcher.fetch(url("/negotiates"))
    assert page.source == "markdown"
    assert page.text.endswith("Already markdown.")


async def test_an_advertised_markdown_twin_is_read_instead(site):
    url, fetcher, hits = site
    page = await fetcher.fetch(url("/advertises"))
    assert page.source == "markdown"
    assert "The markdown twin." in page.text
    assert hits == ["/advertises", "/doc.md"]


async def test_a_front_page_brings_the_sites_llms_txt_after_it(site):
    url, fetcher, hits = site
    page = await fetcher.fetch(url("/"))
    assert page.source == "html + llms.txt"
    assert page.text.index("voted yes") < page.text.index("We sell hats")
    assert sorted(hits) == ["/", "/llms.txt"]


async def test_a_redirect_into_the_private_network_is_refused(site):
    url, fetcher, _ = site
    with pytest.raises(FetchError, match="redirects somewhere you may not go"):
        await fetcher.fetch(url("/to-private"))


async def test_a_redirect_loop_is_given_up_on(site):
    url, fetcher, hits = site
    with pytest.raises(FetchError, match="too many times"):
        await fetcher.fetch(url("/loop"))
    assert len(hits) == F.MAX_REDIRECTS + 1


async def test_a_redirect_without_a_destination_is_not_mistaken_for_the_page(site):
    url, fetcher, _ = site
    with pytest.raises(FetchError, match="without saying where"):
        await fetcher.fetch(url("/nowhere-redirect"))


async def test_a_huge_body_is_read_up_to_the_cap_and_no_further(site):
    url, fetcher, _ = site
    page = await fetcher.fetch(url("/huge"))
    assert len(page.text) == 10_000


async def test_a_file_that_is_not_a_page_is_refused(site):
    url, fetcher, _ = site
    with pytest.raises(FetchError, match="image/png"):
        await fetcher.fetch(url("/binary"))


async def test_a_page_served_without_a_type_is_recognised_as_html(site):
    url, fetcher, _ = site
    page = await fetcher.fetch(url("/untyped"))
    assert page.source == "html"


async def test_a_missing_page_says_404(site):
    url, fetcher, _ = site
    with pytest.raises(FetchError, match="404"):
        await fetcher.fetch(url("/nowhere"))


async def test_a_page_read_twice_is_fetched_once(site):
    url, fetcher, hits = site
    first = await fetcher.fetch(url("/article#top"))
    second = await fetcher.fetch(url("/article"))
    assert first is second
    assert hits == ["/article"]


async def test_other_private_addresses_stay_refused_while_loopback_is_open(site):
    _, fetcher, _ = site
    with pytest.raises(FetchError, match="private network"):
        await fetcher.fetch("http://192.168.1.1/")

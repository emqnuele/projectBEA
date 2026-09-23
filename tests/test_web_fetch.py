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

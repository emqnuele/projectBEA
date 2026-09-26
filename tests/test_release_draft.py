import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from release_draft import notes, previous_tag, tag_of, what_changes  # noqa: E402

TEMPLATE_BODY = """## What this changes

<!-- One change per pull request. -->
She waits for the rest of a sentence.

- the bot says when speech starts

## What breaks if it is wrong

She answers half a sentence.

## Checks

- [x] `make test` passes
"""


def test_the_notes_are_only_what_the_pull_request_changes():
    text = what_changes(TEMPLATE_BODY)
    assert text.startswith("She waits for the rest of a sentence.")
    assert "- the bot says when speech starts" in text
    assert "What breaks" not in text and "make test" not in text
    assert "<!--" not in text


def test_a_body_without_the_template_is_kept_whole():
    assert what_changes("fixed the thing\r\nand the other") == "fixed the thing\nand the other"


def test_the_previous_tag_ignores_the_mods_and_newer_ones():
    tags = ["bea-v2.5.0", "mc-mod-v3.0.0+26.2", "bea-v2.6.1", "bea-v2.6.0", "bea-v2.7.0", "v1.0.0"]
    assert previous_tag(tags, (2, 7, 0)) == "bea-v2.6.1"
    assert previous_tag(tags, (2, 10, 0)) == "bea-v2.7.0"
    assert previous_tag(["mc-mod-v3.0.0+26.2"], (2, 7, 0)) is None


def test_a_draft_names_its_pull_request_and_links_the_comparison():
    pr = {"number": 70, "title": "Wait for the rest of a sentence", "body": TEMPLATE_BODY}
    title, text = notes((2, 7, 0), "owner/repo", pr, "bea-v2.6.1", "abcdef1234")
    assert title == "ProjectBEA v2.7.0: Wait for the rest of a sentence"
    assert "From #70." in text
    assert "https://github.com/owner/repo/compare/bea-v2.6.1...bea-v2.7.0" in text
    assert "What breaks" not in text


def test_a_push_without_a_pull_request_still_gets_a_draft():
    title, text = notes((2, 7, 1), "owner/repo", None, None, "abcdef1234")
    assert title == "ProjectBEA v2.7.1"
    assert "abcdef1" in text and "compare" not in text


def test_the_tag_is_the_apps():
    assert tag_of((2, 6, 1)) == "bea-v2.6.1"

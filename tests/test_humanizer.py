"""Written output that reads as a person typing, not a webhook posting."""

import random

from src.core.expression.humanizer import HARD_LIMIT, SOFT_SPLIT_THRESHOLD, TextHumanizer


def humanizer(rng_value: float = 1.0, **kwargs) -> TextHumanizer:
    rng = random.Random()
    rng.uniform = lambda a, b: rng_value
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    h = TextHumanizer(sleep=sleep, rng=rng, **kwargs)
    h.slept = slept  # exposed so tests can assert on the pacing
    return h


def texts(chunks):
    return [c.value for c in chunks]


# --- split ------------------------------------------------------------------


def test_nothing_splits_to_nothing():
    assert humanizer().split("") == []
    assert humanizer().split("   \n  \n ") == []


def test_one_line_is_one_message():
    assert texts(humanizer().split("ciao")) == ["ciao"]


def test_each_line_becomes_its_own_message():
    assert texts(humanizer().split("ciao\ncome va\nbene")) == ["ciao", "come va", "bene"]


def test_blank_lines_are_dropped():
    assert texts(humanizer().split("ciao\n\n\ncome va")) == ["ciao", "come va"]


def test_lines_are_stripped():
    assert texts(humanizer().split("  ciao  \n\tcome va\t")) == ["ciao", "come va"]


def test_a_short_line_with_sentences_stays_whole():
    line = "Prima. Seconda. Terza."
    assert texts(humanizer().split(line)) == [line]


def test_a_long_line_is_soft_split_by_sentence():
    line = ("Questa e' una frase. " * 30).strip()
    chunks = texts(humanizer().split(line))
    assert len(chunks) > 1
    assert all(c.endswith(".") for c in chunks)


def test_a_long_line_with_no_sentences_stays_whole():
    line = "a" * (SOFT_SPLIT_THRESHOLD + 50)
    assert texts(humanizer().split(line)) == [line]


def test_nothing_ever_exceeds_the_platform_limit():
    line = "x" * (HARD_LIMIT * 2 + 17)
    chunks = texts(humanizer().split(line))
    assert all(len(c) <= HARD_LIMIT for c in chunks)
    assert "".join(chunks) == line


# --- delay_for --------------------------------------------------------------


def test_a_longer_message_takes_longer_to_type():
    h = humanizer()
    assert h.delay_for("x" * 100) > h.delay_for("x" * 10)


def test_the_delay_has_a_floor():
    assert humanizer(min_delay=0.5).delay_for("k") == 0.5


def test_the_delay_has_a_ceiling():
    assert humanizer(max_typing_delay=2.0).delay_for("x" * 10_000) == 2.0


def test_variance_makes_two_identical_messages_differ():
    fast, slow = humanizer(rng_value=0.7), humanizer(rng_value=1.3)
    assert fast.delay_for("x" * 100) < slow.delay_for("x" * 100)


# --- deliver ----------------------------------------------------------------


async def test_delivery_sends_one_message_per_line():
    sent = []
    h = humanizer()
    result = await h.deliver("ciao\ncome va", send_text=lambda t: _record(sent, t))
    assert sent == ["ciao", "come va"]
    assert result == sent


async def test_typing_is_shown_before_every_chunk():
    typing = []
    h = humanizer()

    async def send_typing():
        typing.append(1)

    await h.deliver("uno\ndue\ntre", send_text=lambda t: _noop(), send_typing=send_typing)
    assert len(typing) == 3


async def test_a_pause_precedes_every_chunk():
    h = humanizer()
    await h.deliver("uno\ndue", send_text=lambda t: _noop())
    assert len(h.slept) == 2


async def test_a_broken_typing_indicator_never_blocks_a_message():
    sent = []
    h = humanizer()

    async def send_typing():
        raise RuntimeError("discord hiccup")

    result = await h.deliver("ciao", send_text=lambda t: _record(sent, t), send_typing=send_typing)
    assert sent == ["ciao"] and result == ["ciao"]


async def test_the_transcript_reports_only_what_actually_went_out():
    """History must record what was sent, not what was generated: a chunk that
    never left teaches her she said something she didn't."""
    sent = []
    h = humanizer()

    async def send(text):
        if text == "due":
            raise RuntimeError("rate limited")
        sent.append(text)

    result = await h.deliver("uno\ndue\ntre", send_text=send)
    assert result == ["uno"]
    assert sent == ["uno"]


async def test_delivering_nothing_sends_nothing():
    sent = []
    result = await humanizer().deliver("   ", send_text=lambda t: _record(sent, t))
    assert result == [] and sent == []


async def _noop():
    return None


async def _record(bucket, text):
    bucket.append(text)

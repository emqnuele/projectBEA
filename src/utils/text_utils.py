import re
import textwrap
import unicodedata
from typing import List, Optional, Tuple

# The scripts written without spaces between words: Japanese kana and the Han
# characters Japanese and Chinese share. Korean spaces its words like a
# European language does and needs none of this.
CJK = "぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ"

_HAS_CJK = re.compile(f"[{CJK}]")
_HAS_SPACE = re.compile(r"\s")

# what east_asian_width calls the characters that take two columns
_WIDE = ("W", "F")

# A sentence ends on . ! ? … — but only when what follows is a space or the end,
# so "3.14" and "gg.wp" stay one thought. Closing quotes and brackets belong to
# the sentence they close. 。！？ are the same thing in Japanese and Chinese and
# take no space after them, which is why requiring one left those lines whole.
# An ellipsis ends a thought the same way when what follows it is Japanese or
# Chinese — "待って…分かった" is two — while "wait…what" stays one, as before.
SENTENCE_END = re.compile(
    r"[.!?…][\"'”’)\]]*(?=\s|$)"
    r"|[。！？]+[\"'”’)\]」』）]*"
    rf"|…+[\"'”’)\]」』）]*(?=[{CJK}])")


def written_without_spaces(text: str) -> bool:
    """True for a stretch of Japanese or Chinese: no word boundaries to keep."""
    return bool(_HAS_CJK.search(text)) and not _HAS_SPACE.search(text.strip())


def display_width(text: str) -> int:
    """How many columns `text` takes, not how many characters it has.

    A kana or a kanji is drawn twice as wide as a latin letter, so every budget
    written in characters is half as generous in Japanese as it reads. Counting
    columns is what those budgets always meant.
    """
    return sum(2 if unicodedata.east_asian_width(c) in _WIDE else 1 for c in text)


def sentences(text: str) -> List[str]:
    """`text` cut at its sentence ends, in either kind of script.

    One rule for the spoken and the written side alike: two regexes that
    disagreed about what a sentence is meant the same line was one message on
    telegram and three pieces of speech.
    """
    text = (text or "").strip()
    if not text:
        return []
    out, start = [], 0
    for match in SENTENCE_END.finditer(text):
        piece = text[start:match.end()].strip()
        if piece:
            out.append(piece)
        start = match.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return out


def _last_space(line: List[str]) -> Optional[int]:
    """Where to break a full line so a latin word survives it, or None."""
    for i in range(len(line) - 1, 0, -1):
        if line[i].isspace():
            return i
    return None


def join_sentences(pieces: List[str]) -> str:
    """Sentences back into a paragraph, with a space only where one belongs.

    Joining on " " unconditionally put spaces inside Japanese, which is not how
    the script is written and reads as a stutter on the caption.
    """
    out = ""
    for piece in pieces:
        if not out:
            out = piece
            continue
        out += ("" if written_without_spaces(out[-1] + piece[0]) else " ") + piece
    return out


def wrap_to_width(message: str, width: int) -> List[str]:
    """Wrap to a column budget, breaking mid-run where a script has no spaces.

    `textwrap` counts characters and breaks on spaces, so a Japanese caption was
    twice as wide as the box it was measured for and had no break to find.
    """
    message = message or ""
    width = max(1, width)
    # Any Japanese or Chinese at all, not a line made only of it: one latin
    # word in an otherwise Japanese caption used to hand the whole line back
    # to `textwrap`, which counts characters and drew it twice too wide.
    if not _HAS_CJK.search(message):
        return textwrap.wrap(message, width=width)

    lines, line, used = [], [], 0
    for char in message:
        step = display_width(char)
        if used + step > width and line:
            cut = _last_space(line)
            if cut is None:
                lines.append("".join(line))
                line, used = [], 0
            else:
                # a space in reach is still the better break, even here
                lines.append("".join(line[:cut]).rstrip())
                line = line[cut + 1:]
                used = display_width("".join(line))
        if char.isspace() and not line:
            continue
        line.append(char)
        used += step
    if line:
        lines.append("".join(line).rstrip())
    return [line for line in lines if line]


def paginate_text_for_box(
    message: str,
    *,
    line_width: int,
    max_lines: Optional[int],
    base_font_size: int,
    min_font_size: int,
    font_step: int
) -> Tuple[List[str], int]:
    """Text split into pages, broken at sentence boundaries where it can be."""
    target_size = base_font_size
    target_width = max(1, line_width)
    clean_message = message.replace("\n", " ").strip()
    pieces = sentences(clean_message) or [clean_message]

    pages = []
    current_page_sentences = []

    def measure_lines(text_chunk):
        return len(wrap_to_width(text_chunk, target_width))

    if max_lines is None or max_lines <= 0:
        return ["\n".join(wrap_to_width(message, target_width))], target_size

    for sent in pieces:
        # try adding to current page
        candidate_list = current_page_sentences + [sent]
        candidate_text = join_sentences(candidate_list)

        if measure_lines(candidate_text) <= max_lines:
            current_page_sentences.append(sent)
        else:
            # if current page has content, flush it
            if current_page_sentences:
                pages.append("\n".join(
                    wrap_to_width(join_sentences(current_page_sentences), target_width)))
                current_page_sentences = []

            # now handle the new sentence
            if measure_lines(sent) <= max_lines:
                current_page_sentences.append(sent)
            else:
                # big sentence, must chunk
                wrapped_sent = wrap_to_width(sent, target_width)
                # chunk list of lines
                for i in range(0, len(wrapped_sent), max_lines):
                    chunk = wrapped_sent[i:i + max_lines]
                    pages.append("\n".join(chunk))
                # current_sentences remains empty as we fully flushed this big sentence

    if current_page_sentences:
        pages.append("\n".join(
            wrap_to_width(join_sentences(current_page_sentences), target_width)))

    return pages, target_size

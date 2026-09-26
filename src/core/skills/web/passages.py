"""A long page cut down to what she can use, without a model.

A model reading the page for her is the best answer and the slowest one: a
whole extra call, seconds of her standing there, and tokens for every page.
Most questions are about a few paragraphs that share words with the question,
and finding those is arithmetic. So this is the default, and the model is
something the owner can choose instead.

The start of the page always comes first. It is where a page says what it is,
which is the whole answer to "what does it say" — a question that shares no
word with the paragraph that answers it — and without it she was once handed
four stray fragments of a page and nothing to say about it.
"""

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Set

_WORD = re.compile(r"\w+", re.UNICODE)

# a word in more than this share of the paragraphs says nothing about which one answers
COMMON = 0.3

# a paragraph scoring under this share of the best one is left out
MIN_SHARE = 0.5

# how much of the budget the start of the page is sure of, before any match
LEAD_SHARE = 0.3

# budget left below this is not worth another paragraph
MIN_ROOM = 80

# words that are in every question and say nothing about which paragraph answers it
_STOP = {
    "the", "and", "for", "are", "was", "were", "what", "when", "where", "who", "why",
    "how", "which", "that", "this", "with", "from", "about", "does", "did", "has",
    "have", "had", "can", "could", "will", "would", "there", "their", "they", "into",
    "page", "tell", "find", "many", "much", "some", "any", "you",
    "quanti", "quanto", "quanta", "quante", "qual", "hanno", "fatto", "essere",
    "stato", "stata", "cui", "tra", "fra", "sul", "sulla", "dal", "dalla", "anche",
    "che", "chi", "cosa", "come", "quando", "dove", "perche", "perché", "quale",
    "quali", "sono", "del", "della", "delle", "dei", "degli", "nel", "nella", "per",
    "con", "una", "uno", "gli", "le", "questo", "questa", "quello", "quella", "c'è",
    # words about the page rather than its subject: "what does it say", "describe it"
    "says", "written", "describe", "description", "content", "contents", "site",
    "website", "article", "link", "summary", "summarize", "overview", "scritto", "scritta", "dice", "descrizione", "descrivi", "contenuto", "parla",
    "riguarda", "sito", "pagina", "articolo", "riassunto", "riassumi",
}


def _stem(word: str) -> str:
    # Suffix stripping instead of a fixed 4-letter prefix: "progetto" and
    # "progress" share "prog" but are different words, while "open"/"opening",
    # "lion"/"lions" and "piove"/"piovere" still meet. Measured on docs/*.md
    # (7 general-query hits with [:4], 5 with this): the two extra hits were
    # exactly the prog collisions, and the remaining ones are stop-word gaps.
    for suffix in ("ing", "ere", "are", "ire", "ed", "es"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    if word.endswith("s") and not word.endswith("ss") and len(word) - 1 >= 4:
        return word[:-1]
    if word[-1:] in ("e", "a", "i", "o") and len(word) - 1 >= 4:
        return word[:-1]
    return word


def _terms(text: str) -> Set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if len(w) >= 3 and w not in _STOP}


def _blocks(text: str) -> List[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


@dataclass
class Passages:
    text: str
    # how many paragraphs past the start were picked for matching the question
    matched: int


def pick(text: str, looking_for: str, limit: int) -> Passages:
    """The start of the page, then the paragraphs about `looking_for`, in page order.

    Whatever budget the matches leave is spent carrying the start further, so
    a question nothing answers still gets the most of the page that fits.
    """
    blocks = _blocks(text)
    if not blocks:
        return Passages(text="", matched=0)

    shown: Dict[int, str] = {}
    used = 0

    def take(group: List[int], room: int) -> bool:
        """All of `group` or none of it: a heading without its paragraph answers nothing."""
        nonlocal used
        group = [i for i in group if i not in shown]
        cost = sum(len(blocks[i]) + len(_GAP) for i in group)
        if used + cost > room:
            return False
        for i in group:
            shown[i] = blocks[i]
        used += cost
        return True

    # the start, up to its share. A first paragraph longer than that is cut
    # rather than dropped: it is the one that says what the page is
    lead_room = max(1, int(limit * LEAD_SHARE))
    lead_end = 0
    while lead_end < len(blocks) and take([lead_end], lead_room):
        lead_end += 1
    if not shown:
        shown[0] = blocks[0][:lead_room - 1].rstrip() + "…"
        used = len(shown[0]) + len(_GAP)
        lead_end = 1

    matched = 0
    for i in _ranked(blocks, looking_for, after=lead_end):
        if i not in shown and take(_with_context(blocks, i), limit):
            matched += 1

    # the budget the matches left carries the start on. A block too big for
    # what is left is stepped over rather than ending it: one long code sample
    # must not cost every paragraph after it
    for i in range(lead_end, len(blocks)):
        if limit - used < MIN_ROOM:
            break
        take([i], limit)

    out: List[str] = []
    previous = None
    for i in sorted(shown):
        if previous is not None and i != previous + 1:
            out.append("…")
        out.append(shown[i])
        previous = i
    return Passages(text="\n\n".join(out)[:limit], matched=matched)


_GAP = "\n\n…\n\n"


def _ranked(blocks: List[str], looking_for: str, after: int) -> List[int]:
    """Paragraphs past `after` that answer the question, best first; weak ones left out."""
    wanted = _terms(looking_for)
    if not wanted:
        return []
    block_terms = [_terms(b) for b in blocks]
    total = len(blocks)
    df = {t: sum(t in bt for bt in block_terms) for t in wanted}
    # a word on most of the page is what the page is about ("milano" on milan's
    # page): it tells no paragraph apart, so it only counts when nothing else does
    telling = {t for t in wanted if df[t] <= max(1, total * COMMON)}
    if telling:
        wanted = telling
    idf = {t: math.log(1 + total / (1 + df[t])) for t in wanted}

    scores = []
    for i in range(after, total):
        score = sum(idf[t] for t in wanted & block_terms[i])
        if score and blocks[i].startswith("#"):
            # a matching heading is a signpost, the paragraph after it is the answer
            score *= 0.5
        if score:
            scores.append((score, i))
    if not scores:
        return []
    # the weak matches are filler: a page mentioning the word once is not an answer
    floor = max(score for score, _ in scores) * MIN_SHARE
    return [i for score, i in sorted(scores, key=lambda item: (-item[0], item[1]))
            if score >= floor]


def _with_context(blocks: List[str], i: int) -> List[int]:
    """A match with what makes it readable: its heading, or the text under it."""
    if blocks[i].startswith("#"):
        # a heading alone answers nothing; the paragraph under it does
        after = i + 1
        if after < len(blocks) and not blocks[after].startswith("#"):
            return [i, after]
        return [i]
    for j in range(i - 1, max(-1, i - 4), -1):
        if blocks[j].startswith("#"):
            return [j, i]
    return [i]

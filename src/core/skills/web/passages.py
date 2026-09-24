"""The parts of a long page that are about what she asked, without a model.

A model reading the page for her is the best answer and the slowest one: a
whole extra call, seconds of her standing there, and tokens for every page.
Most questions are about a few paragraphs that share words with the question,
and finding those is arithmetic. So this is the default, and the model is
something the owner can choose instead.
"""

import math
import re
from typing import List, Optional, Set

_WORD = re.compile(r"\w+", re.UNICODE)

# a word in more than this share of the paragraphs says nothing about which one answers
COMMON = 0.3

# a paragraph scoring under this share of the best one is left out
MIN_SHARE = 0.5

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
}


def _stem(word: str) -> str:
    # a crude stem is enough to match "opening" with "open" and "piove" with "piovere"
    return word[:4]


def _terms(text: str) -> Set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if len(w) >= 3 and w not in _STOP}


def _blocks(text: str) -> List[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def pick(text: str, looking_for: str, limit: int) -> Optional[str]:
    """The best-matching paragraphs, in page order, within `limit` characters.

    None when nothing on the page shares a word with the question: better to
    say so than to hand over paragraphs that only look like an answer.
    """
    wanted = _terms(looking_for)
    blocks = _blocks(text)
    if not wanted or not blocks:
        return None

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
    for i, (block, terms) in enumerate(zip(blocks, block_terms, strict=True)):
        score = sum(idf[t] for t in wanted & terms)
        if score and block.startswith("#"):
            # a matching heading is a signpost, the paragraph after it is the answer
            score *= 0.5
        scores.append((score, i))
    best = max(score for score, _ in scores)
    if not best:
        return None
    # the weak matches are filler: a page mentioning the word once is not an answer
    floor = best * MIN_SHARE

    chosen: Set[int] = set()
    used = 0
    for score, i in sorted(scores, key=lambda item: (-item[0], item[1])):
        if score < floor:
            break
        extra = [j for j in _with_context(blocks, i) if j not in chosen]
        # the joins, and a gap marker at worst, are part of what she is handed
        cost = sum(len(blocks[j]) + len("\n\n…\n\n") for j in extra)
        if used + cost > limit:
            if chosen:
                continue
            # the single best match is longer than the budget: its start beats nothing
            return blocks[i][:limit - 1].rstrip() + "…"
        chosen.update(extra)
        used += cost

    out: List[str] = []
    previous = None
    for i in sorted(chosen):
        if previous is not None and i != previous + 1:
            out.append("…")
        out.append(blocks[i])
        previous = i
    return "\n\n".join(out)


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

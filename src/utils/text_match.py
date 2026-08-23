"""Whole-word matching for trigger words and hot names.

A plain `in` makes "bea" fire on "beautiful", "beach", "bead" — Bea would think
she was being called when she wasn't. Here we match on word boundaries, and
offer a fuzzy variant that tolerates one typo so "beatrcie" still reaches her.

Ported from riba/core/text_match.py.
"""

import re
from functools import lru_cache
from typing import Iterable


@lru_cache(maxsize=512)
def _pattern(word: str) -> re.Pattern:
    # (?<!\w) … (?!\w): tight boundaries — underscores count as word characters,
    # which is what we want for usernames
    return re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.IGNORECASE)


def contains_any_word(text: str, words: Iterable[str]) -> bool:
    """True if any of `words` appears in `text` as a whole word."""
    if not text:
        return False
    return any(_pattern(w).search(text) for w in words if w)


def first_matching_word(text: str, words: Iterable[str]) -> str:
    """The first of `words` present as a whole word, or "" — useful for logging why."""
    if not text:
        return ""
    for w in words:
        if w and _pattern(w).search(text):
            return w
    return ""


# Real words one edit away from a likely trigger. Without this the fuzzy match
# fires on ordinary chat: "beat", "bear", "best" are not people calling Bea.
# Add to this list whenever a hot name turns out to collide with a real word.
_FUZZY_BLOCKLIST = frozenset({
    "beat", "beats", "bear", "bears", "beast", "bean", "beans", "best", "beach",
    "bead", "beer", "beta", "bella", "belt", "bene", "beau",
    "seat", "heat", "meat", "neat", "peat", "team", "tea",
})

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)
_REPEAT_RE = re.compile(r"(.)\1+")

# below this length a single edit changes the word too much: fuzzy matching on
# short tokens is pure noise
_MIN_FUZZY_LEN = 4


def _squeeze(word: str) -> str:
    """Collapses repeated letters: "beaaa" and "bbea" both become "bea"."""
    return _REPEAT_RE.sub(r"\1", word)


def _within_one_edit(a: str, b: str) -> bool:
    """True if `a` and `b` are at most one operation apart (Damerau-Levenshtein)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
        if len(diff) == 1:
            return True
        if len(diff) == 2 and diff[1] == diff[0] + 1:
            i = diff[0]
            return a[i] == b[i + 1] and a[i + 1] == b[i]
        return False
    # different lengths: exactly one insertion/deletion
    short, long = (a, b) if la < lb else (b, a)
    i = j = 0
    skipped = False
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
            continue
        if skipped:
            return False
        skipped = True
        j += 1
    return True


def contains_any_word_fuzzy(text: str, words: Iterable[str]) -> bool:
    """Like `contains_any_word`, but tolerates one typo per token.

    People mistype names constantly, and a bot that ignores "beatrcie" reads as
    broken. Tokens that are real words (see `_FUZZY_BLOCKLIST`) and tokens that
    are too short stay out.
    """
    if not text:
        return False
    targets = [w.lower() for w in words if w]
    if not targets:
        return False
    if contains_any_word(text, targets):
        return True

    fuzzy_targets = [w for w in targets if len(w) >= _MIN_FUZZY_LEN]
    if not fuzzy_targets:
        return False

    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) < _MIN_FUZZY_LEN or token in _FUZZY_BLOCKLIST:
            continue
        squeezed = _squeeze(token)
        if squeezed in _FUZZY_BLOCKLIST:
            continue
        for target in fuzzy_targets:
            if _within_one_edit(token, target) or _within_one_edit(squeezed, _squeeze(target)):
                return True
    return False

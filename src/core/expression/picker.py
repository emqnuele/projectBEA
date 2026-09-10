"""Matching a word she wrote to something she actually has.

She invents. Asked for a mood she writes `smug`, `wistful`, `deadpan`; asked for
a behaviour she writes `shrug` when the file is called `dismissive_wave`. A fixed
table of near-misses answers the first twenty of those and then silently returns
the default forever, which on screen is a face that never changes.

So the table stays as the fast path — it costs nothing and covers what she says
most of the time — and anything it misses is matched by meaning against the
names that exist. Below `threshold` there is no match and the fallback stands:
landing on the nearest thing is better than nothing, but only while "nearest"
still means something.

The embedder is optional everywhere. Without one, this degrades to exactly the
fast path, which is where the project already was.
"""

from typing import Callable, Dict, Iterable, List, Optional, Sequence

from src.utils.logger import get_logger

logger = get_logger("bea.expression.picker")

# cosine below this is not a match, it is the nearest of several wrong answers
DEFAULT_THRESHOLD = 0.45

# how many distinct words are worth remembering the answer to. She repeats
# herself far more than she invents, so this is almost always a hit.
CACHE_LIMIT = 512


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class Picker:
    """Maps free text onto a fixed set of names, by meaning.

    `aliases` widens what each name covers: the embedding is taken of the
    synonyms rather than of the bare name, which is the difference between
    `ew` catching `disgusted` and `ew` catching nothing at all.
    """

    def __init__(self, names: Iterable[str], *, aliases: Optional[Dict[str, str]] = None,
                 embedder=None, threshold: float = DEFAULT_THRESHOLD,
                 fallback: str = "", exact: Optional[Callable[[str], Optional[str]]] = None):
        self.names: List[str] = [n for n in names if n]
        self.aliases = dict(aliases or {})
        self.embedder = embedder
        self.threshold = threshold
        self.fallback = fallback or (self.names[0] if self.names else "")
        self._exact = exact
        self._vectors: Optional[List[List[float]]] = None
        self._cache: Dict[str, str] = {}
        self._warned = False

    def pick(self, word: str) -> str:
        """The name she meant, or the fallback when nothing is close enough."""
        wanted = (word or "").strip().lower()
        if not wanted:
            return self.fallback
        if wanted in self.names:
            return wanted

        if self._exact is not None:
            hit = self._exact(wanted)
            if hit:
                return hit

        if wanted in self._cache:
            return self._cache[wanted]

        chosen = self._nearest(wanted)
        if len(self._cache) < CACHE_LIMIT:
            self._cache[wanted] = chosen
        return chosen

    # --- internals ----------------------------------------------------------

    def _nearest(self, wanted: str) -> str:
        vectors = self._candidates()
        if not vectors:
            return self.fallback
        try:
            query = self.embedder.embed([wanted])[0]
        except Exception as e:
            self._give_up(e)
            return self.fallback

        scored = [(cosine(query, vector), name)
                  for vector, name in zip(vectors, self.names, strict=True)]
        score, name = max(scored)
        if score < self.threshold:
            logger.debug(f"'{wanted}' is not close to anything ({name} at {score:.2f})")
            return self.fallback
        logger.debug(f"'{wanted}' -> '{name}' ({score:.2f})")
        return name

    def _candidates(self) -> List[List[float]]:
        """The names, embedded once, on the first word the fast path missed.

        Lazily rather than at construction: most sessions never invent a word,
        and no startup should wait on a model it may not end up using.
        """
        if self._vectors is not None:
            return self._vectors
        if self.embedder is None or not self.names:
            self._vectors = []
            return self._vectors
        try:
            self._vectors = self.embedder.embed(
                [self.aliases.get(name, name) for name in self.names]
            )
        except Exception as e:
            self._give_up(e)
            self._vectors = []
        return self._vectors

    def _give_up(self, error: Exception) -> None:
        """Say it once. A picker that logs per word would drown the session."""
        if self._warned:
            return
        self._warned = True
        logger.warning(f"Cannot match words by meaning ({error}); using the fallback.")

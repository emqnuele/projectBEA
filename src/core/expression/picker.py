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

import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from src.core.mind.moods import COVERS, DEFAULT_MOOD, MOODS, known_mood
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
                 fallback: Optional[str] = None,
                 exact: Optional[Callable[[str], Optional[str]]] = None):
        self.names: List[str] = [n for n in names if n]
        # a clip is a file name, so it arrives with whatever capitals it was
        # saved with; nothing she writes will have them
        self._by_name = {name.lower(): name for name in self.names}
        self.aliases = dict(aliases or {})
        self.embedder = embedder
        self.threshold = threshold
        # an empty string is a fallback — "do nothing" — and not the absence of
        # one, so it cannot be told apart from unset by truthiness
        self.fallback = fallback if fallback is not None else (
            self.names[0] if self.names else "")
        self._exact = exact
        self._vectors: Optional[List[List[float]]] = None
        self._cache: Dict[str, str] = {}
        self._warned = False

    def pick(self, word: str) -> str:
        """The name she meant, or the fallback when nothing is close enough."""
        wanted = (word or "").strip().lower()
        if not wanted:
            return self.fallback
        if wanted in self._by_name:
            return self._by_name[wanted]

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

    @property
    def ready(self) -> bool:
        """Whether a word can be matched right now without loading anything."""
        return self._vectors is not None

    def warm(self) -> None:
        """Load the model and embed the names, on whatever thread this is called on.

        The only way a picker becomes able to match, and meant to be called once
        at startup from a thread nobody is waiting on. Nothing below does this
        work on demand, because the one moment it would otherwise happen is the
        first word she invents — which lands in the middle of a line already
        going out to the room, and costs the best part of a second on a machine
        that has the model and a download on one that does not.

        Until then `pick` still answers everything the tables know, which is
        most of what she writes, and falls back for the rest.
        """
        self._candidates()

    # --- internals ----------------------------------------------------------

    def _nearest(self, wanted: str) -> str:
        if self.embedder is None:
            return self.fallback
        vectors = self._vectors
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
        """The names, embedded once. Only ever reached through `warm`."""
        if self._vectors is not None:
            return self._vectors
        if self.embedder is None or not self.names:
            self._vectors = []
            return self._vectors
        try:
            self._vectors = list(self.embedder.embed(
                [self.aliases.get(name, name) for name in self.names]
            ))
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


def mood_picker(embedder=None) -> Picker:
    """The seven moods, reachable by any word that means one of them.

    The table in `moods.py` answers first and costs nothing; `COVERS` is what
    gets embedded when it does not, because `disgusted` on its own is close to
    a handful of words and the whole row is close to most of the ways she would
    ever write it.
    """
    return Picker(MOODS, aliases=COVERS, embedder=embedder,
                  fallback=DEFAULT_MOOD, exact=known_mood)


def clip_picker(names: Iterable[str], embedder=None) -> Picker:
    """The behaviours installed, reachable by what they look like.

    File names are not vocabulary — a clip called `dismissive_wave_01` is what
    she means when she writes `<do:shrug>`, and expecting her to remember the
    filename is expecting her to read the folder. Underscores and the numbering
    people leave on exported clips are stripped before matching, and the name
    handed back is still the real one.

    The fallback is nothing rather than the first clip: playing the wrong
    behaviour is worse than playing none, because it is what the audience sees.
    """
    installed = [name for name in names if name]
    aliases = {name: _readable(name) for name in installed}
    return Picker(installed, aliases=aliases, embedder=embedder, fallback="")


def _readable(name: str) -> str:
    """`003_dismissive_wave.vrma` as the two words it is actually about."""
    words = re.sub(r"[_\-.]+", " ", name)
    words = re.sub(r"\b\d+\b", " ", words)
    return re.sub(r"\s+", " ", words).strip().lower() or name

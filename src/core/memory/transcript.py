"""One sitting of the stream, rendered for a model to read.

Everything that happened lands in one table in arrival order, which is how it
should be stored and not how it should be read: a DM with marco interleaved
line by line with a death in minecraft is a pile, and a consolidation pass
reading a pile invents a conversation that never took place. So the rows are
grouped by the conversation they belong to and labelled with where that was,
and only then flattened.

Pure: no clock, no database, no io. It takes the rows `Conversations.stream`
returns and gives back text.
"""

from typing import Any, Dict, Iterable, List

from src.core.mind.routing import STAGE

# how her own lines are labelled, so the pass never reads them as someone else's
SELF = "you"

# a sitting with fewer spoken lines than this had nobody actually say
# anything in it: marked done without waking the model, and no diary page
MIN_SPOKEN_LINES = 2


def _speaker(row: Dict[str, Any]) -> str:
    return str(row.get("display_name") or row.get("author_identity") or "")


def _line(row: Dict[str, Any]) -> str:
    """One row as the pass reads it.

    A perception already carries its speaker inside the text ("[marco] ciao"),
    because that is how she saw it — relabelling it here would say the same
    name twice. Her own lines and things that happened by themselves are the
    two cases that need one.
    """
    content = str(row.get("content") or "").strip()
    if not content:
        return ""
    role = row.get("role")
    if role == "bea":
        return f"{SELF}: {content}"
    if role == "world":
        return f"({row.get('kind') or 'event'}) {content}"
    return content


def _header(key: str, rows: List[Dict[str, Any]]) -> str:
    """Where this stretch of conversation happened, and who was in it."""
    names: List[str] = []
    surfaces: List[str] = []
    for row in rows:
        name = _speaker(row)
        if row.get("role") == "user" and name and name not in names:
            names.append(name)
        surface = str(row.get("surface") or "")
        if surface and surface not in surfaces:
            surfaces.append(surface)
    where = key if key != STAGE else "stage (the live room)"
    parts = [where]
    if surfaces:
        parts.append("via " + ", ".join(surfaces))
    if names:
        parts.append("with " + ", ".join(names))
    return f"--- {' | '.join(parts)} ---"


def group_by_conversation(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Rows per conversation key, first-seen order, each group in stream order."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get("conversation_key") or STAGE), []).append(row)
    return groups


def render_stream(rows: Iterable[Dict[str, Any]]) -> str:
    """One sitting as labelled blocks, one per conversation."""
    blocks = []
    for key, group in group_by_conversation(rows).items():
        lines = [line for line in (_line(r) for r in group) if line]
        if not lines:
            continue
        blocks.append(_header(key, group) + "\n" + "\n".join(lines))
    return "\n\n".join(blocks)


def spoken_count(rows: Iterable[Dict[str, Any]]) -> int:
    """Rows that are somebody talking, hers or theirs.

    The threshold under which a session is not worth a pass counts these: a
    sitting made of nothing but game heartbeats has nothing to consolidate.
    """
    return sum(1 for r in rows if r.get("role") in ("user", "bea"))

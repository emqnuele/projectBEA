import json
import re
from typing import Dict, Iterator, Optional, Tuple

# matches a trailing comma right before a closing } or ] (a common llm mistake)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _iter_json_objects(text: str) -> Iterator[str]:
    """Yields every balanced `{...}` substring, respecting string literals.

    Brace counting alone breaks when a string value contains `{` or `}`, so we
    track whether we're inside a quoted string (and honor backslash escapes).
    Objects are yielded left-to-right; scanning resumes after each one, so a
    reply like `blah {a} blah {b}` surfaces both candidates.
    """
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        for j in range(i, n):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    yield text[i : j + 1]
                    break
        else:
            # no balanced close from here on; nothing more to find
            return
        i = j + 1


def _try_load(candidate: str) -> Optional[Dict]:
    """Parses a candidate, retrying once after stripping trailing commas."""
    try:
        return json.loads(candidate)
    except Exception:
        pass
    try:
        return json.loads(_TRAILING_COMMA.sub(r"\1", candidate))
    except Exception:
        return None


def extract_json(reply: str) -> Optional[Dict]:
    """Best-effort extraction of a JSON object embedded anywhere in `reply`.

    Tries fenced ```json blocks first, then any balanced object found in the
    text. Among the objects that parse, prefers one carrying our schema keys
    (`message`/`mood`) so leading examples or stray braces don't win.
    """
    candidates = []

    # fenced code blocks (greedy body; the scanner below balances it)
    for block in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", reply, flags=re.DOTALL | re.IGNORECASE):
        candidates.append(block)
    # then every balanced object in the raw text
    candidates.extend(_iter_json_objects(reply))

    with_mood: Optional[Dict] = None
    any_dict: Optional[Dict] = None
    for candidate in candidates:
        data = _try_load(candidate)
        if not isinstance(data, dict):
            continue
        # the real answer carries the spoken text; prefer it over bare examples
        if "message" in data:
            return data
        if with_mood is None and "mood" in data:
            with_mood = data
        if any_dict is None:
            any_dict = data
    return with_mood or any_dict


def parse_llm_json(reply: str) -> Tuple[str, str, Dict]:
    """Extracts (mood, message, full_dict) from an LLM reply.

    Resilient to prose around the JSON, fenced blocks, nested objects, braces
    inside string values and trailing commas. Falls back to treating the whole
    reply as the spoken message when no JSON object can be recovered.
    """
    data = extract_json(reply or "")
    if not isinstance(data, dict):
        return "normal", (reply or "").strip(), {}

    mood = data.get("mood", "normal")
    message = data.get("message", "")
    return str(mood), str(message), data

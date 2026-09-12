"""Reading and writing `.env` in place.

Secrets belong here and nowhere else: `BrainConfig.save_to_file` strips them on
the way out, so a key written to config.json is lost the first time the
dashboard saves. The wizard rewrites keys where they already sit rather than
regenerating the file, so a hand-edited `.env` stays hand-edited.
"""

import re
from typing import Dict

# KEY=value, tolerating `export`, surrounding spaces and quotes
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")

HEADER = "# --- written by `bea --setup` ---"


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def _quote(value: str) -> str:
    # anything a shell-style parse would mangle gets quoted; keys are left bare
    if re.search(r"[\s#\"']", value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def parse_env(text: str) -> Dict[str, str]:
    """Every KEY=value in `text`, with surrounding quotes stripped."""
    values: Dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE.match(line)
        if match:
            values[match.group(1)] = _unquote(match.group(2))
    return values


def merge_env(text: str, updates: Dict[str, str], *, empty_clears: bool = False) -> str:
    """`text` with `updates` applied: comments, order and untouched keys survive.

    Empty values are dropped rather than written as blank keys, so declining a
    wizard question never overwrites a key that is already set. `empty_clears`
    is the dashboard's case instead: a field the user emptied is an instruction
    to forget the value, so the key is blanked where it sits — and a key that
    was never in the file is not added just to say it is empty.
    """
    pending = dict(updates) if empty_clears else {k: v for k, v in updates.items() if v}
    lines = text.splitlines()
    rewritten = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE.match(line)
        if not match or match.group(1) not in pending:
            continue
        key = match.group(1)
        lines[i] = f"{key}={_quote(pending[key])}"
        rewritten.add(key)

    added = [key for key in pending if key not in rewritten and pending[key]]
    if added:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(HEADER)
        lines.extend(f"{key}={_quote(pending[key])}" for key in added)

    return "\n".join(lines).rstrip("\n") + "\n"

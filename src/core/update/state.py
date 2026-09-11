"""Which revision each editable file was last reconciled against.

A three-way merge needs a base, and the base is *not* the commit you are on. If
an update ends in a conflict the user never resolves, their file is still built
on the revision from before that update — so the next update has to merge from
there, or the changes they never took would look like deletions they made and
get thrown away a second time, silently.

Git cannot tell us this: as far as it is concerned the file is simply modified.
So we keep it ourselves, one line per file, in a small untracked JSON.

The rules are short:

* the base advances when a file is untouched, or when a merge lands cleanly
* the base does **not** advance on a conflict — nothing was reconciled
* the base advances on an explicit resolution, which is the only place a human
  decides instead of the merge

Anything unreadable here degrades to "no base", and no base means we refuse to
merge and hand the user both versions instead. Losing this file costs a round
of manual reconciliation; trusting a wrong base would cost their edits.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from src.utils.files import atomic_write_text
from src.utils.logger import get_logger

logger = get_logger("bea.update.state")

STATE_FILE = Path("data/.prompt_base.json")
FORMAT = 1


@dataclass
class BaseMap:
    """Repo-relative path -> the sha its current contents were reconciled against."""

    bases: Dict[str, str] = field(default_factory=dict)

    def get(self, path: str) -> Optional[str]:
        sha = self.bases.get(path)
        return sha if isinstance(sha, str) and len(sha) >= 7 else None

    def set(self, path: str, sha: str) -> None:
        self.bases[path] = sha

    def forget(self, path: str) -> None:
        self.bases.pop(path, None)


def load(root: Path) -> BaseMap:
    path = Path(root) / STATE_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return BaseMap()
    except (OSError, json.JSONDecodeError) as e:
        # a corrupt map is treated as an absent one: every file falls back to
        # "hand both versions over", which is the safe half of the design
        logger.warning(f"Could not read {STATE_FILE}, starting from scratch: {e}")
        return BaseMap()

    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        logger.warning(f"{STATE_FILE} is in an unknown format, starting from scratch")
        return BaseMap()

    bases = payload.get("bases")
    if not isinstance(bases, dict):
        return BaseMap()
    return BaseMap({str(k): str(v) for k, v in bases.items() if isinstance(v, str)})


def save(root: Path, state: BaseMap) -> None:
    path = Path(root) / STATE_FILE
    body = json.dumps({"format": FORMAT, "bases": state.bases}, indent=2, sort_keys=True)
    try:
        atomic_write_text(path, body + "\n")
    except OSError as e:
        # not fatal: the next update falls back to handing over both versions
        logger.error(f"Could not write {STATE_FILE}: {e}")

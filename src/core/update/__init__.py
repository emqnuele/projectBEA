"""Updating her without overwriting anything the user wrote.

`git pull` is not an updater. The prompts under `data/prompts` ship with the
engine *and* are meant to be edited, so a pull either refuses to run or leaves
conflict markers inside the file her personality is read from. Everything here
exists to make the same operation safe for someone who has never used git.

    from src.core.update import check, apply

    status = check()          # is there anything new? (cached, read-only)
    report = apply()          # do it, and tell me exactly what happened

`reconcile.resolve` is the other entry point: the human ending to a conflict the
merge could not settle on its own.
"""

from src.core.update.runner import (
    STEPS,
    Availability,
    Report,
    apply,
    check,
    in_docker,
    invalidate,
)
from src.core.update.version import current_version

__all__ = [
    "STEPS",
    "Availability",
    "Report",
    "apply",
    "check",
    "current_version",
    "in_docker",
    "invalidate",
]

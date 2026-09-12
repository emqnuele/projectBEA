"""The dashboard's side of the updater: check, apply, and settle a conflict.

`POST /update/apply` runs `git pull` and a build, which is to say it executes
code, so it is the most powerful endpoint in the app. Three things keep it
honest: the API binds to loopback and its CORS list is closed, the update
itself refuses to touch anything the user modified outside `data/prompts`, and
`updates.allow_web_apply` in config turns this door off entirely for anyone who
would rather update from a terminal.

The run happens on a worker thread. It shells out to git, uv and npm for
minutes at a time, and doing that on the event loop would freeze every other
screen — including the one drawing the progress bar for this very run.
"""

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.update import runner
from src.core.update import state as base_state
from src.core.update.gitrepo import Repo
from src.core.update.reconcile import new_file_for, pending_reviews, resolve
from src.core.update.runner import ROOT
from src.utils.logger import get_logger
from src.web.deps import current_brain

logger = get_logger("bea.web.update")

router = APIRouter(prefix="/update", tags=["update"])

# the run in flight, or the last one that finished. One at a time — the file
# lock enforces that across processes, this guards the two threads in ours.
_run: Optional[Dict[str, Any]] = None
_guard = threading.Lock()


class Resolution(BaseModel):
    choice: str = Field(..., pattern="^(mine|theirs)$")


def _config_flag(name: str, default: bool = True) -> bool:
    brain = current_brain()
    block = getattr(brain.config, "updates", None) if brain else None
    if not isinstance(block, dict):
        return default
    return bool(block.get(name, default))


def _reload() -> None:
    """Re-reads the prompts from disk, so a merge is live without a restart."""
    brain = current_brain()
    if brain is None:
        return
    try:
        brain.reload_configuration()
    except Exception as e:  # noqa: BLE001 - a stale prompt is not worth a 500
        logger.warning(f"Could not reload after the update: {e}")


# --- what is out there -------------------------------------------------------


@router.get("")
def update_status(force: bool = False) -> Dict[str, Any]:
    """Everything the update screens need: what is new, what is running, what needs a look."""
    if not _config_flag("check"):
        return {
            "supported": False,
            "available": False,
            "reason": "Update checks are switched off in your settings.",
            "can_apply": False,
            "reviews": _reviews(),
            "run": _snapshot_run(),
        }

    status = runner.check(root=ROOT, force=force)
    return {
        **status.describe(),
        "can_apply": status.supported and _config_flag("allow_web_apply"),
        "reviews": _reviews(),
        "run": _snapshot_run(),
    }


@router.post("/check")
def force_check() -> Dict[str, Any]:
    return update_status(force=True)


# --- doing it ----------------------------------------------------------------


@router.post("/apply", status_code=202)
def start_update() -> Dict[str, Any]:
    if not _config_flag("allow_web_apply"):
        raise HTTPException(
            status_code=403,
            detail="Updating from the dashboard is switched off. Run `uv run bea --update` in a terminal.",
        )

    global _run
    with _guard:
        if _run is not None and _run["state"] == "running":
            raise HTTPException(status_code=409, detail="An update is already running.")
        _run = {
            "state": "running",
            "started_at": time.time(),
            "steps": [{"id": step_id, "label": label, "status": "pending", "detail": ""}
                      for step_id, label in runner.STEPS],
            "report": None,
        }

    threading.Thread(target=_work, name="bea-update", daemon=True).start()
    return _snapshot_run() or {}


@router.get("/run")
def run_progress() -> Optional[Dict[str, Any]]:
    """Polled while the bar is on screen. Returns the last run once it is over."""
    return _snapshot_run()


def _work() -> None:
    global _run

    def progress(step: runner.Step) -> None:
        with _guard:
            if _run is None:
                return
            for entry in _run["steps"]:
                if entry["id"] == step.id:
                    entry["status"] = step.status
                    entry["detail"] = step.detail
                    break

    report = runner.apply(root=ROOT, source="dashboard", progress=progress)

    with _guard:
        if _run is not None:
            # steps that never ran would otherwise pulse forever on a failure
            for entry in _run["steps"]:
                if entry["status"] in ("pending", "running"):
                    entry["status"] = "skipped" if report.ok else "pending"
            _run["state"] = "done"
            _run["finished_at"] = time.time()
            _run["report"] = report.describe()

    if report.status == runner.UPDATED:
        _reload()


def _snapshot_run() -> Optional[Dict[str, Any]]:
    with _guard:
        return dict(_run) if _run is not None else None


# --- the conflicts the merge could not settle --------------------------------


@router.get("/reviews")
def list_reviews() -> Dict[str, Any]:
    return {"reviews": _reviews()}


@router.get("/reviews/{name}")
def read_review(name: str) -> Dict[str, Any]:
    path = _review_path(name)
    return {
        "name": name,
        "path": path,
        "mine": _text(ROOT / path),
        "theirs": _text(new_file_for(ROOT, path)),
    }


@router.post("/reviews/{name}")
def settle_review(name: str, body: Resolution) -> Dict[str, Any]:
    path = _review_path(name)
    repo = Repo(ROOT)

    try:
        outcome = resolve(ROOT, repo, path, body.choice, repo.head())
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # the only place outside a clean merge where a file's base is allowed to
    # move: a human has just said which version is the one to build on
    bases = base_state.load(ROOT)
    if outcome.base:
        bases.set(path, outcome.base)
    base_state.save(ROOT, bases)

    _reload()
    return {"resolved": outcome.describe(), "reviews": _reviews()}


def _reviews() -> List[Dict[str, str]]:
    try:
        repo = Repo(ROOT)
        if not repo.is_repo():
            return []
        return [{"name": Path(p).name, "path": p} for p in pending_reviews(ROOT, repo)]
    except Exception as e:  # noqa: BLE001 - a missing list is not worth a 500
        logger.warning(f"Could not list the prompts awaiting review: {e}")
        return []


def _review_path(name: str) -> str:
    """Turns a file name from the browser into a path, or refuses.

    Only names the updater itself has flagged are accepted, so nothing the
    caller sends is ever joined onto a path we then write to.
    """
    for review in _reviews():
        if review["name"] == name:
            return review["path"]
    raise HTTPException(status_code=404, detail=f"{name} is not waiting for a decision.")


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

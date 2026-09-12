"""`bea --doctor`, run from the dashboard.

The checks were written for a terminal, and that is where people who already
know they have a problem go. The people who need them most are the ones who do
not know yet — she is quiet, or she will not hear them, and nothing on screen
says which of the nine things between a microphone and a reply gave up. So the
same sequence is exposed here, findings streamed as they land.

It is never run on its own: the checks build a voice, transcribe a line and
call the mind, which costs real money at somebody's provider. It runs when a
person asks for it, and at no other time.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from src.utils.logger import get_logger
from src.web.deps import current_brain

logger = get_logger("bea.web.health")

router = APIRouter(prefix="/doctor", tags=["doctor"])

_run: Optional[Dict[str, Any]] = None
_task: Optional[asyncio.Task] = None


@router.get("")
def doctor_status() -> Dict[str, Any]:
    """The last run, or nothing. Polled while the checks are landing."""
    return _run or {"state": "idle", "findings": [], "verdict": None}


@router.post("/run", status_code=202)
async def run_doctor() -> Dict[str, Any]:
    global _run, _task

    if _run is not None and _run["state"] == "running":
        raise HTTPException(status_code=409, detail="The checks are already running.")

    brain = current_brain()
    if brain is None:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    from src.setup.doctor import CHECKS

    _run = {
        "state": "running",
        "started_at": time.time(),
        "total": len(CHECKS),
        "findings": [],
        "verdict": None,
    }
    _task = asyncio.create_task(_work(brain.config))
    return _run


async def _work(config) -> None:
    global _run

    from src.setup.doctor import diagnose

    def landed(title, finding) -> None:
        if _run is None:
            return
        _run["findings"].append({
            "title": title,
            "ok": finding.ok,
            "detail": finding.detail,
            "fix": finding.fix,
            "blocking": finding.blocking,
            "stops": finding.stops,
        })

    try:
        await diagnose(config, report=landed)
    except Exception as e:  # noqa: BLE001 - the run is the product; report the failure as one
        logger.exception("The checks could not run")
        if _run is not None:
            _run["findings"].append({
                "title": "The checks themselves",
                "ok": False, "detail": f"{type(e).__name__}: {e}",
                "fix": "", "blocking": True, "stops": True,
            })

    if _run is not None:
        _run["state"] = "done"
        _run["finished_at"] = time.time()
        _run["verdict"] = _verdict(_run["findings"], _run["total"])


def _verdict(findings: List[Dict[str, Any]], total: int) -> Dict[str, Any]:
    """The same reading the terminal gives: one blocker beats any number of warnings."""
    blocking = [f["title"] for f in findings if f["stops"]]
    warnings = [f["title"] for f in findings if not f["ok"] and not f["blocking"]]

    if blocking:
        return {
            "level": "blocked",
            "headline": f"{blocking[0]} is in the way",
            # the sequence stops at the first blocker, so the rest never ran and
            # their silence must not read as a pass
            "detail": f"{total - len(findings)} check(s) below it never ran.",
            "blocking": blocking,
            "warnings": warnings,
        }
    if warnings:
        return {
            "level": "warning",
            "headline": "She will run",
            "detail": f"{len(warnings)} thing(s) will not work as well as they could.",
            "blocking": [],
            "warnings": warnings,
        }
    return {
        "level": "ok",
        "headline": "Everything checks out",
        "detail": f"All {len(findings)} checks passed.",
        "blocking": [],
        "warnings": [],
    }

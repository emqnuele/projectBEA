"""How she is right now: state, skills, the event stream, and the home screen."""

import asyncio
import json
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.core.brain import AIVtuberBrain
from src.core.skills.base import Skill
from src.core.update.version import current_version
from src.web.deps import current_brain, get_brain
from src.web.routers.memory import counts as memory_counts
from src.web.routers.plan import summary as plan_summary

router = APIRouter(tags=["status"])

STARTED_AT = time.time()


def _engine_summary(brain: AIVtuberBrain) -> Dict[str, Any]:
    config = brain.config
    # every provider keeps its model in `<provider>_model`
    model = str(getattr(config, f"{config.llm_provider}_model", "") or "")
    stt = getattr(brain, "stt", None)
    stt_state: Dict[str, Any] = (
        stt.status() if stt is not None and hasattr(stt, "status")
        else {"provider": config.stt_provider, "loaded": stt is not None}
    )
    return {
        "llm_provider": config.llm_provider,
        "model": model,
        "tts_provider": config.tts_provider,
        "stt_provider": config.stt_provider,
        "stt": stt_state,
        "language": config.language,
        "obs_connected": bool(getattr(brain.obs, "client", None)),
    }


def _toggleable(brain: AIVtuberBrain) -> List[Skill]:
    return brain.skill_registry.toggleable() if brain.skill_registry is not None else []


def _status(brain: AIVtuberBrain) -> Dict[str, Any]:
    active_skills = [skill.skill_name for skill in _toggleable(brain) if skill.active]
    return {
        "is_speaking": brain.is_speaking,
        "is_sleeping": brain.is_sleeping,
        "active_skills": active_skills,
        "session_id": brain.history_manager.session_id,
        "uptime": time.time() - STARTED_AT,
        "version": current_version(),
    }


@router.get("/status")
def get_status(brain: AIVtuberBrain = Depends(get_brain)):
    return _status(brain)


@router.post("/dream/run")
async def run_dream(brain: AIVtuberBrain = Depends(get_brain)):
    """Put Bea to sleep and run a consolidation (dream) pass, then wake her."""
    result = await brain.run_dream()
    return {"status": "success" if result.get("ok") else "error", "result": result}


@router.post("/dream/wake")
async def wake_bea(brain: AIVtuberBrain = Depends(get_brain)):
    brain.wake_up()
    return {"status": "success", "is_sleeping": brain.is_sleeping}


@router.get("/skills")
def list_skills(brain: AIVtuberBrain = Depends(get_brain)):
    return {
        skill.skill_name: {
            "enabled": skill.enabled,
            "config": brain.config.skills.get(skill.skill_name, {}),
            "active": skill.active,
        }
        for skill in _toggleable(brain) if skill.skill_name
    }


@router.post("/skills/{name}/toggle")
async def toggle_skill(name: str, enable: bool, brain: AIVtuberBrain = Depends(get_brain)):
    if brain.skill_registry is None or not brain.skill_registry.get_by_key(name):
        raise HTTPException(status_code=404, detail="Skill not found")

    await brain.set_skill_enabled(name, enable)
    return {"status": "success", "enabled": enable}


@router.get("/skills/logs")
def get_skill_logs(brain: AIVtuberBrain = Depends(get_brain)):
    # backward compatibility
    events = brain.event_manager.get_events(limit=100)
    return [
        {"timestamp": e["timestamp"], "skill": e["source"], "message": e["message"]}
        for e in events if e["category"] in ["skill", "thought", "error"]
    ]


@router.get("/events")
def get_events(limit: int = 50, brain: AIVtuberBrain = Depends(get_brain)):
    return brain.event_manager.get_events(limit=limit)


@router.get("/events/stream")
async def stream_events(
    request: Request, backlog: int = 50, brain: AIVtuberBrain = Depends(get_brain)
):
    """Server-sent events: the dashboard stops polling every two seconds.

    Polling three endpoints on a timer meant the UI was always slightly stale and
    the brain paid for a request whether or not anything had happened. Here the
    events arrive when they occur.
    """
    queue = brain.event_manager.subscribe(backlog=backlog)

    async def pump():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # a comment keeps proxies from closing an idle connection
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            brain.event_manager.unsubscribe(queue)

    return StreamingResponse(pump(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # nginx would otherwise buffer the stream away
    })


@router.get("/overview")
def overview(brain: AIVtuberBrain = Depends(get_brain)):
    """One call for the home screen: status, plan, skills, memory and engine."""
    skills = [{"name": skill.skill_name, "enabled": skill.enabled, "active": skill.active}
              for skill in _toggleable(brain)]

    history = brain.history_manager
    dream = brain.dream_skill
    try:
        last_night = dream.last_night() if dream is not None else ""
    except Exception:
        last_night = ""
    return {
        "status": _status(brain),
        "session": {
            "id": history.session_id,
            "title": history.title,
            "message_count": len(history.history),
        },
        "plan": plan_summary(brain),
        "skills": skills,
        "memory": memory_counts(brain),
        "engine": _engine_summary(brain),
        "dream": {"last_night": last_night},
        "context": (brain.consciousness.window_status()
                    if brain.consciousness is not None else {"enabled": False}),
    }


@router.get("/health")
def health():
    return {"status": "ok", "brain": current_brain() is not None}


@router.get("/context")
def context_window(brain: AIVtuberBrain = Depends(get_brain)):
    """The one sliding window: budget, handoff state, continuity."""
    mind = getattr(brain, "consciousness", None)
    if mind is None:
        return {"enabled": False}
    return {"enabled": True, **mind.window_status()}

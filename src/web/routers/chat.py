"""Talking to her from the dashboard, and the sessions that hold it."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.core.brain import AIVtuberBrain
from src.web.deps import get_brain

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("message cannot be empty or whitespace-only")
        return stripped


class SessionRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


def _safe_session_id(session_id: str) -> str:
    """Session ids address files on disk, so a path separator must never survive."""
    clean = Path(session_id).name
    if not clean or clean != session_id:
        raise HTTPException(status_code=400, detail="Invalid session id")
    return clean


@router.get("/history")
def get_history(brain: AIVtuberBrain = Depends(get_brain)):
    try:
        return brain.memory.conversations.dashboard_history(limit=50)
    except Exception:
        return brain.history_manager.get_recent_history(limit=50)


@router.get("/sessions")
def list_sessions(brain: AIVtuberBrain = Depends(get_brain)):
    active = brain.history_manager.session_id
    return [{**s, "active": s.get("id") == active} for s in brain.list_sessions()]


@router.post("/sessions")
async def create_session(brain: AIVtuberBrain = Depends(get_brain)):
    session_id = brain.create_new_session()
    return {"status": "success", "session_id": session_id}


@router.post("/sessions/{session_id}/activate")
async def activate_session(session_id: str, brain: AIVtuberBrain = Depends(get_brain)):
    if brain.load_session(_safe_session_id(session_id)):
        return {"status": "success", "message": f"Session {session_id} activated"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.patch("/sessions/{session_id}")
def rename_session(
    session_id: str, request: SessionRename, brain: AIVtuberBrain = Depends(get_brain)
):
    if brain.history_manager.set_session_title(_safe_session_id(session_id), request.title.strip()):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, brain: AIVtuberBrain = Depends(get_brain)):
    if brain.history_manager.delete_session(_safe_session_id(session_id)):
        return {"status": "success"}
    raise HTTPException(
        status_code=409, detail="Session not found, or it is the one currently open"
    )


@router.post("/chat")
async def chat(request: ChatRequest, brain: AIVtuberBrain = Depends(get_brain)):
    # she speaks it herself; this only waits to hand the words back
    mood, message = await brain.generate_response(request.message)
    return {
        "status": "success",
        "response": {
            "role": "assistant",
            "content": message,
            "mood": mood
        }
    }


@router.post("/interrupt")
async def interrupt_speech(brain: AIVtuberBrain = Depends(get_brain)):
    await brain.interrupt()
    return {"status": "success", "message": "Interrupted"}

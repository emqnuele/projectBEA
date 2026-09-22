"""Her body in the game, reached from the dashboard.

async on purpose: a goal wakes the body's asyncio loop, which a worker thread must not touch.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.brain import AIVtuberBrain
from src.web.deps import get_brain

router = APIRouter(tags=["minecraft"])

NOT_PLAYING = "She is not in the game right now"


class GoalRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=500)


@router.post("/minecraft/ask")
async def ask_what_she_is_doing(brain: AIVtuberBrain = Depends(get_brain)):
    """Asking her what she is doing, off the clock.

    The same perception she gets on her own every `commentary_seconds`, so the
    button cannot drift away from the behaviour it stands in for.
    """
    if not brain.ask_minecraft_for_a_word():
        raise HTTPException(status_code=409, detail=NOT_PLAYING)
    return {"status": "asked"}


@router.get("/minecraft/body")
async def what_the_body_is_doing(brain: AIVtuberBrain = Depends(get_brain)):
    """The goal, how far it has got, and what it is thinking.

    The same three things her own context carries, so the dashboard and she
    are never looking at different bodies.
    """
    snapshot = brain.minecraft_body()
    if snapshot is None:
        return {"active": False, "connected": False, "status": "off"}
    return snapshot


@router.post("/minecraft/goal")
async def point_the_body_at_something(request: GoalRequest,
                                brain: AIVtuberBrain = Depends(get_brain)):
    """The owner setting the goal instead of her."""
    result = brain.direct_minecraft_body(request.goal)
    if result is None:
        raise HTTPException(status_code=409, detail=NOT_PLAYING)
    return {"status": "set", "detail": result}


@router.post("/minecraft/stop")
async def put_the_body_down(brain: AIVtuberBrain = Depends(get_brain)):
    result = brain.stop_minecraft_body()
    if result is None:
        raise HTTPException(status_code=409, detail=NOT_PLAYING)
    return {"status": "stopped", "detail": result}

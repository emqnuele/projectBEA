"""Her game, reached from the dashboard.

async on purpose: stopping her hands talks to the mod on the brain's asyncio loop,
which a worker thread must not touch.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.core.brain import AIVtuberBrain
from src.web.deps import get_brain

router = APIRouter(tags=["minecraft"])

NOT_PLAYING = "She is not in the game right now"


@router.post("/minecraft/ask")
async def ask_what_she_is_doing(brain: AIVtuberBrain = Depends(get_brain)):
    """Asking her what she is doing, off the clock."""
    if not brain.ask_minecraft_for_a_word():
        raise HTTPException(status_code=409, detail=NOT_PLAYING)
    return {"status": "asked"}


@router.get("/minecraft/now")
async def what_she_is_doing(brain: AIVtuberBrain = Depends(get_brain)):
    """The action in her hands, how long it has been going, and the last one she finished.

    The same things her own frame carries, so the dashboard and she are never
    looking at different games.
    """
    snapshot = brain.minecraft_now()
    if snapshot is None:
        return {"active": False, "connected": False, "doing": "", "elapsed": 0.0,
                "progress": "", "last": ""}
    return snapshot


@router.post("/minecraft/stop")
async def put_her_hands_down(brain: AIVtuberBrain = Depends(get_brain)):
    result = await brain.stop_minecraft()
    if result is None:
        raise HTTPException(status_code=409, detail=NOT_PLAYING)
    return {"status": "stopped", "detail": result}

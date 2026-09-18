"""Her body in the game, reached from the dashboard."""

from fastapi import APIRouter, Depends, HTTPException

from src.core.brain import AIVtuberBrain
from src.web.deps import get_brain

router = APIRouter(tags=["minecraft"])


@router.post("/minecraft/ask")
def ask_what_she_is_doing(brain: AIVtuberBrain = Depends(get_brain)):
    """Asking her what she is doing, off the clock.

    The same perception she gets on her own every `commentary_seconds`, so the
    button cannot drift away from the behaviour it stands in for.
    """
    if not brain.ask_minecraft_for_a_word():
        raise HTTPException(status_code=409, detail="She is not in the game right now")
    return {"status": "asked"}

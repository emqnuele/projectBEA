"""Who she is: the structured fields, and the six questions that draft them."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from src.core.agent.registry import BACKGROUND
from src.core.brain import AIVtuberBrain
from src.core.onboarding import QUESTIONS, draft_soul
from src.core.onboarding import needed as onboarding_needed
from src.core.persona_store import PersonaRefused, mark_onboarding_completed, onboarding_completed
from src.core.persona_store import apply as persona_apply
from src.core.persona_store import describe as persona_describe
from src.web.deps import get_brain

router = APIRouter(tags=["persona"])


@router.get("/persona")
def get_persona(brain: AIVtuberBrain = Depends(get_brain)):
    return persona_describe(brain.config)


@router.put("/persona")
def update_persona(payload: Dict[str, Any], brain: AIVtuberBrain = Depends(get_brain)):
    try:
        result = persona_apply(brain.config, payload)
    except PersonaRefused as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e

    brain.config.save_to_file()
    if "soul" in payload:
        mark_onboarding_completed(getattr(brain, "memory", None))
    # the brain re-reads the soul on reload, so the change is live immediately
    brain.reload_configuration()
    return result


@router.get("/onboarding")
def get_onboarding(brain: AIVtuberBrain = Depends(get_brain)):
    return {
        "questions": [q.describe() for q in QUESTIONS],
        "needed": onboarding_needed(
            customised=persona_describe(brain.config)["customised"],
            completed=onboarding_completed(getattr(brain, "memory", None)),
        ),
    }


@router.post("/onboarding/draft")
async def draft_onboarding(answers: Dict[str, Any], brain: AIVtuberBrain = Depends(get_brain)):
    """Writes nothing: you see the persona before it becomes hers."""
    name = str(answers.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="She needs a name.")

    llm = brain.model_for(BACKGROUND) if hasattr(brain, "model_for") else brain.llm
    return {"name": name, "soul": await draft_soul(llm, answers)}


@router.post("/onboarding/skip")
def skip_onboarding(brain: AIVtuberBrain = Depends(get_brain)):
    mark_onboarding_completed(getattr(brain, "memory", None))
    return {"status": "success"}

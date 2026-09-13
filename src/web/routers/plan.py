"""The stream plan: the standing directive, and the objectives under it."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.core.brain import AIVtuberBrain
from src.core.memory.plan import STATUSES
from src.web.deps import get_brain

router = APIRouter(tags=["plan"])


class DirectiveRequest(BaseModel):
    text: str = Field(default="", max_length=2000)


class ObjectiveRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    detail: str = Field(default="", max_length=1000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("an objective needs some text")
        return stripped


class ObjectiveUpdate(BaseModel):
    text: Optional[str] = Field(default=None, max_length=500)
    detail: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[str] = None
    outcome: Optional[str] = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def known_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        return v


class PlanOrder(BaseModel):
    ids: list


def payload(brain: AIVtuberBrain) -> Dict[str, Any]:
    plan = brain.plan
    return {
        "directive": plan.directive,
        "objectives": [o.as_dict() for o in plan.all()],
    }


def summary(brain: AIVtuberBrain) -> Dict[str, Any]:
    """The short form the home screen shows, beside everything else."""
    objectives = brain.plan.all()
    counts = {status: 0 for status in STATUSES}
    for objective in objectives:
        counts[objective.status] = counts.get(objective.status, 0) + 1
    return {
        "directive": brain.plan.directive,
        "total": len(objectives),
        "counts": counts,
        "closed": counts.get("done", 0) + counts.get("dropped", 0),
        "objectives": [o.as_dict() for o in objectives[:6]],
    }


@router.get("/plan")
def get_plan(brain: AIVtuberBrain = Depends(get_brain)):
    return payload(brain)


@router.post("/plan/directive")
def set_directive(request: DirectiveRequest, brain: AIVtuberBrain = Depends(get_brain)):
    brain.plan.set_directive(request.text)
    brain.plan_changed()
    return payload(brain)


@router.post("/plan/objectives")
def add_objective(request: ObjectiveRequest, brain: AIVtuberBrain = Depends(get_brain)):
    if brain.plan.add(request.text, request.detail) is None:
        raise HTTPException(status_code=400, detail="An objective needs some text")
    brain.plan_changed()
    return payload(brain)


@router.patch("/plan/objectives/{objective_id}")
def update_objective(
    objective_id: int, request: ObjectiveUpdate, brain: AIVtuberBrain = Depends(get_brain)
):
    updated = brain.plan.update(
        objective_id, text=request.text, detail=request.detail,
        status=request.status, outcome=request.outcome,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="No such objective")
    return payload(brain)


@router.delete("/plan/objectives/{objective_id}")
def delete_objective(objective_id: int, brain: AIVtuberBrain = Depends(get_brain)):
    if not brain.plan.remove(objective_id):
        raise HTTPException(status_code=404, detail="No such objective")
    brain.plan_changed()
    return payload(brain)


@router.post("/plan/order")
def reorder_plan(request: PlanOrder, brain: AIVtuberBrain = Depends(get_brain)):
    brain.plan.reorder([int(i) for i in request.ids])
    return payload(brain)


@router.post("/plan/reset")
def reset_plan(brain: AIVtuberBrain = Depends(get_brain)):
    """A new stream: the old plan goes away entirely."""
    brain.plan.clear()
    brain.plan_changed()
    return payload(brain)

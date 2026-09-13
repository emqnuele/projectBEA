"""The donation webhook. Money always earns a reaction."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.brain import AIVtuberBrain
from src.web.deps import get_brain

router = APIRouter(tags=["donations"])


class DonationRequest(BaseModel):
    name: str = Field(default="someone", max_length=200)
    amount: float = Field(..., ge=0)
    currency: str = Field(default="EUR", max_length=16)
    message: str = Field(default="", max_length=1000)
    platform: str = Field(default="donation", max_length=64)
    donorId: Optional[str] = None
    eventId: Optional[str] = None


@router.post("/webhook/donation")
async def donation_webhook(
    request: DonationRequest,
    secret: Optional[str] = None,
    brain: AIVtuberBrain = Depends(get_brain),
):
    """Receives a donation from StreamElements / Ko-fi / anything else.

    Anyone who can reach this endpoint could fake a donation, so a shared secret
    is checked when one is configured (`DONATION_SECRET`).
    """
    skill = brain.donation_skill
    if skill is None or not skill.active:
        raise HTTPException(status_code=503, detail="Donations are not enabled")
    if not skill.authorized(secret):
        raise HTTPException(status_code=403, detail="Bad secret")

    perception = skill.receive(
        name=request.name, amount=request.amount, currency=request.currency,
        message=request.message, platform=request.platform,
        donor_id=request.donorId, event_id=request.eventId,
    )
    if perception is None:
        return {"status": "duplicate"}
    return {"status": "perceived"}

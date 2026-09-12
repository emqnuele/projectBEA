"""What she remembers: the people, the roster, her own lore, and recall."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from src.core.affect.rules import warmth_phrase
from src.core.brain import AIVtuberBrain
from src.utils.logger import get_logger
from src.web.deps import get_brain

logger = get_logger("bea.web.memory")

router = APIRouter(tags=["memory"])


def counts(brain: AIVtuberBrain) -> Dict[str, Any]:
    """How much she is holding, for the home screen and the memory screen."""
    memory = brain.memory
    try:
        return {
            "people": len(memory.people.all()),
            "roster": len(memory.roster.all()),
            "memories": memory.rag.count() if memory.rag else 0,
            "hot_facts": len(memory.hot.active()),
            "self_facts": len(memory.selflore.facts()),
            "rag_ready": memory.rag is not None,
        }
    except Exception as e:
        logger.warning(f"Memory counts unavailable: {e}")
        return {"people": 0, "roster": 0, "memories": 0, "hot_facts": 0,
                "self_facts": 0, "rag_ready": False}


@router.post("/memory/save")
async def save_memory(brain: AIVtuberBrain = Depends(get_brain)):
    if not brain.memory_skill:
        raise HTTPException(status_code=400, detail="Memory skill not initialized")

    if brain.memory_skill.save_current_session():
        return {"status": "success", "message": "Memory saving triggered."}
    else:
        return {"status": "error", "message": "Could not save memory (Skill disabled or empty session)."}


@router.get("/memory/overview")
def memory_overview(brain: AIVtuberBrain = Depends(get_brain)):
    return counts(brain)


@router.get("/memory/people")
def memory_people(brain: AIVtuberBrain = Depends(get_brain)):
    return [
        {
            "person_id": card.person_id,
            "name": card.primary_name,
            "names": card.display_names,
            "identities": card.identities,
            "facts": card.facts,
            "attitude": card.bea_attitude,
            "mood": warmth_phrase(card.warmth),
            "reason": card.promoted_reason,
            "created_at": card.created_at,
            "last_updated": card.last_updated,
        }
        for card in brain.memory.people.all()
    ]


@router.get("/memory/roster")
def memory_roster(limit: int = 60, brain: AIVtuberBrain = Depends(get_brain)):
    entries = brain.memory.roster.all()[: max(1, min(limit, 500))]
    return [
        {
            "identity": e.identity,
            "name": e.display_name,
            "platform": e.platform,
            "first_seen": e.first_seen,
            "last_seen": e.last_seen,
            "message_count": e.message_count,
            "session_count": e.session_count,
            "donation_total": e.donation_total,
            "promoted": e.promoted,
            "marked": e.marked_by_bea,
            "person_id": e.person_id,
        }
        for e in entries
    ]


@router.get("/memory/self")
def memory_self(brain: AIVtuberBrain = Depends(get_brain)):
    return {
        "facts": brain.memory.selflore.facts(),
        "profile": brain.memory.selflore.profile(),
        "hot_facts": [
            {"text": f.text, "source": f.source, "expires_at": f.expires_at}
            for f in brain.memory.hot.active()
        ],
    }


@router.get("/memory/search")
def memory_search(q: str, k: int = 8, brain: AIVtuberBrain = Depends(get_brain)):
    """Semantic recall, split the way she reads it: facts apart from her own lines."""
    if brain.memory.rag is None:
        raise HTTPException(status_code=400, detail="Recall needs the memory skill enabled")
    query = (q or "").strip()
    if not query:
        return {"facts": [], "hers": []}

    def shape(recollections) -> List[Dict[str, Any]]:
        return [
            {
                "text": r.text, "who": r.who, "source": r.source,
                "similarity": round(r.similarity, 4),
                "created_at": r.created_at, "scope_key": r.scope_key,
            }
            for r in recollections
        ]

    facts, hers = brain.memory.rag.recall_split(query, k=max(1, min(k, 30)))
    return {"facts": shape(facts), "hers": shape(hers)}

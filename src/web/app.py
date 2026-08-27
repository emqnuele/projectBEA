import asyncio
import inspect
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from src.core.brain import AIVtuberBrain
from src.core.config import MASK, SECRET_SKILL_FIELDS
from src.core.memory.plan import STATUSES
from src.core.settings_schema import ValidationError, apply_section, describe
from src.core.settings_schema import restart_needed as _restart_needed
from src.core.settings_schema import section as _section
from src.utils.logger import get_logger

logger = get_logger("bea.web")

app = FastAPI(title="ProjectBEA Brain API")

# the dashboard is served from this same origin; a wildcard would let any page
# the browser has open read the brain's state and drive it
DEFAULT_ORIGINS = [
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:5173", "http://127.0.0.1:5173",  # vite dev server
]


def _allowed_origins() -> list:
    extra = os.getenv("BEA_ALLOWED_ORIGINS", "")
    return DEFAULT_ORIGINS + [o.strip() for o in extra.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# global brain instance
brain_instance: Optional[AIVtuberBrain] = None

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("message cannot be empty or whitespace-only")
        return stripped

class ConfigUpdateRequest(BaseModel):
    config: Dict[str, Any]

STARTED_AT = time.time()


def get_brain() -> AIVtuberBrain:
    if not brain_instance:
        raise HTTPException(status_code=503, detail="Brain not initialized")
    return brain_instance


def _safe_session_id(session_id: str) -> str:
    """Session ids address files on disk, so a path separator must never survive."""
    clean = Path(session_id).name
    if not clean or clean != session_id:
        raise HTTPException(status_code=400, detail="Invalid session id")
    return clean


def _merge_skills(current: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    """Folds a (possibly partial) skills payload into the live config.

    The UI reads secrets back as `MASK`; writing that value would replace a real
    token with asterisks, so masked fields are dropped instead of applied.
    """
    for skill_key, block in incoming.items():
        if not isinstance(block, dict):
            current[skill_key] = block
            continue
        clean = {k: v for k, v in block.items() if v != MASK}
        current.setdefault(skill_key, {}).update(clean)

@app.get("/config")
def get_config():
    brain = get_brain()
    return brain.config.public_dict()

@app.post("/config")
def update_config(request: ConfigUpdateRequest):
    brain = get_brain()
    try:
        current_tts = brain.config.tts_provider
        current_stt = brain.config.stt_provider
        restart_required = False

        # uppdate config object
        for key, value in request.config.items():
            if hasattr(brain.config, key):
                if key == "skills" and isinstance(value, dict):
                    # merge, so a partial post never drops the skills it omitted
                    # (and a masked secret never overwrites the real one)
                    _merge_skills(brain.config.skills, value)
                    continue
                setattr(brain.config, key, value)

                # check for critical changes
                if key == "tts_provider" and value != current_tts:
                    restart_required = True
                if key == "stt_provider" and value != current_stt:
                    restart_required = True

        # save to file
        brain.config.save_to_file()

        # hot reload
        brain.reload_configuration()

        msg = "Configuration updated."
        if restart_required:
            msg += " RESTART REQUIRED to apply new provider settings."

        return {
            "status": "success",
            "message": msg,
            "restart_required": restart_required
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

# --- settings: one schema, rendered by the dashboard ------------------------


@app.get("/settings")
def get_settings():
    return describe(get_brain().config)


@app.get("/settings/{key}")
def get_settings_section(key: str):
    data = describe(get_brain().config)
    for block in data["sections"]:
        if block["key"] == key:
            return block
    raise HTTPException(status_code=404, detail=f"Unknown settings section: {key}")


@app.post("/settings/{key}")
async def update_settings_section(key: str, payload: Dict[str, Any]):
    brain = get_brain()
    try:
        sec = _section(key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown settings section: {key}") from e

    try:
        changed = apply_section(brain.config, key, payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    brain.config.save_to_file()

    # a platform's on/off switch is the skill registry's business: it starts and
    # stops a live connection, which a config reload does not do
    if sec.toggleable and "enabled" in changed:
        try:
            await brain.set_skill_enabled(key, bool(changed["enabled"]))
        except Exception as e:
            logger.error(f"Toggling {key} failed: {e}")

    brain.reload_configuration()

    return {
        "status": "success",
        "changed": changed,
        "restart_required": _restart_needed(key, changed),
    }


@app.get("/history")
def get_history():
    brain = get_brain()
    return brain.history_manager.get_recent_history(limit=50)

@app.get("/sessions")
def list_sessions():
    brain = get_brain()
    active = brain.history_manager.session_id
    return [{**s, "active": s.get("id") == active} for s in brain.list_sessions()]

@app.post("/sessions")
async def create_session():
    brain = get_brain()
    session_id = brain.create_new_session()
    return {"status": "success", "session_id": session_id}

@app.post("/sessions/{session_id}/activate")
async def activate_session(session_id: str):
    brain = get_brain()
    if brain.load_session(_safe_session_id(session_id)):
        return {"status": "success", "message": f"Session {session_id} activated"}
    raise HTTPException(status_code=404, detail="Session not found")


class SessionRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


@app.patch("/sessions/{session_id}")
def rename_session(session_id: str, request: SessionRename):
    brain = get_brain()
    if brain.history_manager.set_session_title(_safe_session_id(session_id), request.title.strip()):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    brain = get_brain()
    if brain.history_manager.delete_session(_safe_session_id(session_id)):
        return {"status": "success"}
    raise HTTPException(
        status_code=409, detail="Session not found, or it is the one currently open"
    )

@app.post("/memory/save")
async def save_memory():
    brain = get_brain()
    if not brain.memory_skill:
        raise HTTPException(status_code=400, detail="Memory skill not initialized")

    if brain.memory_skill.save_current_session():
        return {"status": "success", "message": "Memory saving triggered."}
    else:
        return {"status": "error", "message": "Could not save memory (Skill disabled or empty session)."}

@app.get("/status")
def get_status():
    brain = get_brain()
    active_skills = []
    if brain.skill_registry is not None:
        active_skills = [
            skill.skill_name for skill in brain.skill_registry.toggleable()
            if skill.active and skill.skill_name is not None
        ]
    return {
        "is_speaking": brain.is_speaking,
        "is_sleeping": brain.is_sleeping,
        "active_skills": active_skills,
        "session_id": brain.history_manager.session_id,
        "uptime": time.time() - STARTED_AT,
    }

@app.post("/dream/run")
async def run_dream():
    """Put Bea to sleep and run a consolidation (dream) pass, then wake her."""
    brain = get_brain()
    result = await brain.run_dream()
    return {"status": "success" if result.get("ok") else "error", "result": result}

@app.post("/dream/wake")
async def wake_bea():
    brain = get_brain()
    brain.wake_up()
    return {"status": "success", "is_sleeping": brain.is_sleeping}

@app.post("/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    brain = get_brain()

    # 1. generate text
    mood, message = await brain.generate_response(request.message)

    # 2. schedule output
    background_tasks.add_task(brain.perform_output_task, mood, message)

    return {
        "status": "success",
        "response": {
            "role": "assistant",
            "content": message,
            "mood": mood
        }
    }

@app.post("/interrupt")
async def interrupt_speech():
    brain = get_brain()
    # execute interruption
    await brain.interrupt()
    return {"status": "success", "message": "Interrupted"}

@app.post("/audio")
async def upload_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    brain = get_brain()

    # save temp file
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    # the client names this file: anything with a path in it would escape `temp/`
    suffix = Path(file.filename or "").suffix[:8] or ".wav"
    temp_file = temp_dir / f"upload_{uuid.uuid4().hex}{suffix}"

    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # process
    mood, message, transcript = await brain.generate_audio_response(str(temp_file))

    # schedule output
    background_tasks.add_task(brain.perform_output_task, mood, message)

    # cleanup
    if temp_file.exists():
        os.remove(temp_file)

    return {
        "status": "success",
        "response": {
            "role": "assistant",
            "content": message,
            "mood": mood,
            "user_transcript": transcript
        }
    }

class DiscordChatRequest(BaseModel):
    username: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=4000)
    channelId: str = "unknown"
    userId: Optional[str] = None
    messageId: Optional[str] = None
    isDm: bool = False

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("message cannot be empty or whitespace-only")
        return stripped

@app.post("/discord/chat")
async def discord_chat(request: DiscordChatRequest):
    brain = get_brain()

    logger.info(f"Discord Chat from {request.username}: {request.message}")

    # one mind: deposit a perception and return immediately. Bea answers on her
    # own via the discord tools (reply/send_message), not via a synchronous reply.
    brain.perceive_discord_text(
        request.message, request.username, request.channelId,
        message_id=request.messageId, user_id=request.userId, is_dm=request.isDm,
    )
    return {"status": "perceived"}

@app.post("/discord/audio")
async def discord_audio_interaction(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    username: str = Form(...),
    flush_buffer: str = Form(default="false"),
    user_id: Optional[str] = Form(default=None),
):
    brain = get_brain()

    # save temp file
    temp_dir = Path("temp_discord")
    temp_dir.mkdir(exist_ok=True)
    temp_file = temp_dir / f"{username}_{int(os.times().elapsed)}.wav"

    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # process
        status, text_response, transcript, audio_bytes = await brain.process_discord_interaction(str(temp_file), username, user_id=user_id)

        # convert audio to base64
        import base64
        audio_b64 = ""
        if audio_bytes:
             audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')

        return {
            "status": status, # "success" or "resume"
            "text": text_response,
            "transcript": transcript,
            "audio_base64": audio_b64
        }
    except Exception as e:
        logger.error(f"Discord Audio Error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        # cleanup
        if temp_file.exists():
            os.remove(temp_file)

@app.post("/voice/transcript")
async def buffer_voice_transcript(
    file: UploadFile = File(...),
    username: str = Form(...),
    user_id: Optional[str] = Form(default=None)
):
    """
    Overheard speech: transcribes a short snippet and feeds it to the
    consciousness as a VOICE perception (steering), without waiting for a reply.
    Bea decides on her own whether it's worth reacting to.
    """
    brain = get_brain()

    # save temp file
    temp_dir = Path("temp_discord")
    temp_dir.mkdir(exist_ok=True)
    temp_file = temp_dir / f"buf_{username}_{int(os.times().elapsed)}.wav"

    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    transcript = ""
    try:
        if brain.stt:
            transcript = brain.stt.transcribe(str(temp_file))
            logger.info(f"Overheard: [{username}] '{transcript}'")

        if transcript and transcript.strip() and transcript != "[Unintelligible]":
            if brain.surface_registry is not None:
                voice = brain.surface_registry.get("voice:discord")
                if voice is not None and hasattr(voice, "perceive"):
                    voice.perceive(transcript, username, user_id=user_id)

        return {"status": "perceived", "transcript": transcript}
    except Exception as e:
        logger.error(f"Overheard transcript error: {e}")
        return {"status": "error", "transcript": "", "error": str(e)}
    finally:
        if temp_file.exists():
            os.remove(temp_file)

class DonationRequest(BaseModel):
    name: str = Field(default="someone", max_length=200)
    amount: float = Field(..., ge=0)
    currency: str = Field(default="EUR", max_length=16)
    message: str = Field(default="", max_length=1000)
    platform: str = Field(default="donation", max_length=64)
    donorId: Optional[str] = None
    eventId: Optional[str] = None


@app.post("/webhook/donation")
async def donation_webhook(request: DonationRequest, secret: Optional[str] = None):
    """Receives a donation from StreamElements / Ko-fi / anything else.

    Anyone who can reach this endpoint could fake a donation, so a shared secret
    is checked when one is configured (`DONATION_SECRET`).
    """
    brain = get_brain()
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


@app.get("/skills")
def list_skills():
    brain = get_brain()
    skills_data = {}
    if brain.skill_registry is not None:
        for skill in brain.skill_registry.toggleable():
            key = skill.skill_name
            if key is not None:
                skills_data[key] = {
                    "enabled": skill.enabled,
                    "config": brain.config.skills.get(key, {}),
                    "active": skill.active,
                }
    return skills_data

@app.post("/skills/{name}/toggle")
async def toggle_skill(name: str, enable: bool):
    brain = get_brain()
    if brain.skill_registry is None or not brain.skill_registry.get_by_key(name):
        raise HTTPException(status_code=404, detail="Skill not found")

    await brain.set_skill_enabled(name, enable)
    return {"status": "success", "enabled": enable}

@app.get("/skills/logs")
def get_skill_logs():
    brain = get_brain()
    # backward compatibility
    events = brain.event_manager.get_events(limit=100)
    return [
        {"timestamp": e["timestamp"], "skill": e["source"], "message": e["message"]}
        for e in events if e["category"] in ["skill", "thought", "error"]
    ]

@app.get("/events")
def get_events(limit: int = 50):
    brain = get_brain()
    return brain.event_manager.get_events(limit=limit)

@app.get("/events/stream")
async def stream_events(request: Request, backlog: int = 50):
    """Server-sent events: the dashboard stops polling every two seconds.

    Polling three endpoints on a timer meant the UI was always slightly stale and
    the brain paid for a request whether or not anything had happened. Here the
    events arrive when they occur.
    """
    brain = get_brain()
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


# --- the stream plan --------------------------------------------------------

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


def _plan_payload(brain: AIVtuberBrain) -> Dict[str, Any]:
    plan = brain.plan
    return {
        "directive": plan.directive,
        "objectives": [o.as_dict() for o in plan.all()],
    }


@app.get("/plan")
def get_plan():
    return _plan_payload(get_brain())


@app.post("/plan/directive")
def set_directive(request: DirectiveRequest):
    brain = get_brain()
    brain.plan.set_directive(request.text)
    brain.plan_changed()
    return _plan_payload(brain)


@app.post("/plan/objectives")
def add_objective(request: ObjectiveRequest):
    brain = get_brain()
    if brain.plan.add(request.text, request.detail) is None:
        raise HTTPException(status_code=400, detail="An objective needs some text")
    brain.plan_changed()
    return _plan_payload(brain)


@app.patch("/plan/objectives/{objective_id}")
def update_objective(objective_id: int, request: ObjectiveUpdate):
    brain = get_brain()
    updated = brain.plan.update(
        objective_id, text=request.text, detail=request.detail,
        status=request.status, outcome=request.outcome,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="No such objective")
    return _plan_payload(brain)


@app.delete("/plan/objectives/{objective_id}")
def delete_objective(objective_id: int):
    brain = get_brain()
    if not brain.plan.remove(objective_id):
        raise HTTPException(status_code=404, detail="No such objective")
    brain.plan_changed()
    return _plan_payload(brain)


@app.post("/plan/order")
def reorder_plan(request: PlanOrder):
    brain = get_brain()
    brain.plan.reorder([int(i) for i in request.ids])
    return _plan_payload(brain)


@app.post("/plan/reset")
def reset_plan():
    """A new stream: the old plan goes away entirely."""
    brain = get_brain()
    brain.plan.clear()
    brain.plan_changed()
    return _plan_payload(brain)


# --- the overview: everything the home screen needs, in one request ---------


def _plan_summary(brain: AIVtuberBrain) -> Dict[str, Any]:
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


def _memory_counts(brain: AIVtuberBrain) -> Dict[str, Any]:
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


def _engine_summary(brain: AIVtuberBrain) -> Dict[str, Any]:
    config = brain.config
    model = {
        "openrouter": config.openrouter_model,
        "openai": config.openai_model,
        "groq": config.groq_model,
    }.get(config.llm_provider, "")
    return {
        "llm_provider": config.llm_provider,
        "model": model,
        "tts_provider": config.tts_provider,
        "stt_provider": config.stt_provider,
        "language": config.language,
        "obs_connected": bool(getattr(brain.obs, "client", None)),
    }


@app.get("/overview")
def overview():
    """One call for the home screen: status, plan, skills, memory and engine."""
    brain = get_brain()
    skills = []
    if brain.skill_registry is not None:
        for skill in brain.skill_registry.toggleable():
            if skill.skill_name is None:
                continue
            skills.append({
                "name": skill.skill_name,
                "enabled": skill.enabled,
                "active": skill.active,
            })

    history = brain.history_manager
    return {
        "status": get_status(),
        "session": {
            "id": history.session_id,
            "title": history.title,
            "message_count": len(history.history),
        },
        "plan": _plan_summary(brain),
        "skills": skills,
        "memory": _memory_counts(brain),
        "engine": _engine_summary(brain),
    }


# --- what she remembers -----------------------------------------------------


@app.get("/memory/overview")
def memory_overview():
    return _memory_counts(get_brain())


@app.get("/memory/people")
def memory_people():
    brain = get_brain()
    return [
        {
            "person_id": card.person_id,
            "name": card.primary_name,
            "names": card.display_names,
            "identities": card.identities,
            "facts": card.facts,
            "attitude": card.bea_attitude,
            "reason": card.promoted_reason,
            "created_at": card.created_at,
            "last_updated": card.last_updated,
        }
        for card in brain.memory.people.all()
    ]


@app.get("/memory/roster")
def memory_roster(limit: int = 60):
    brain = get_brain()
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


@app.get("/memory/self")
def memory_self():
    brain = get_brain()
    return {
        "facts": brain.memory.selflore.facts(),
        "profile": brain.memory.selflore.profile(),
        "hot_facts": [
            {"text": f.text, "source": f.source, "expires_at": f.expires_at}
            for f in brain.memory.hot.active()
        ],
    }


@app.get("/memory/search")
def memory_search(q: str, k: int = 8):
    """Semantic recall, split the way she reads it: facts apart from her own lines."""
    brain = get_brain()
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


# --- does this actually work? -----------------------------------------------


class TestResult(BaseModel):
    ok: bool
    message: str
    detail: str = ""


@app.post("/test/llm", response_model=TestResult)
async def test_llm():
    brain = get_brain()
    try:
        started = time.perf_counter()
        result = brain.llm.chat("Reply with the single word: ok.", system_prompt="You are a test probe.")
        if inspect.isawaitable(result):
            result = await result
        elapsed = int((time.perf_counter() - started) * 1000)
        return TestResult(ok=True, message=f"{brain.config.llm_provider} answered in {elapsed} ms",
                          detail=str(result[1] if isinstance(result, tuple) and len(result) > 1 else result)[:200])
    except Exception as e:
        return TestResult(ok=False, message="The model did not answer", detail=str(e)[:300])


@app.post("/test/tts", response_model=TestResult)
async def test_tts():
    brain = get_brain()
    if brain.tts is None:
        return TestResult(ok=False, message="No voice engine is loaded")
    try:
        started = time.perf_counter()
        audio, rate = await brain.tts.generate_audio("Voice check.")
        elapsed = int((time.perf_counter() - started) * 1000)
        samples = len(audio) if audio is not None else 0
        return TestResult(ok=samples > 0,
                          message=f"{brain.config.tts_provider} rendered {samples / max(rate, 1):.1f}s in {elapsed} ms",
                          detail=f"{samples} samples at {rate} Hz")
    except Exception as e:
        return TestResult(ok=False, message="The voice engine failed", detail=str(e)[:300])


@app.post("/test/obs", response_model=TestResult)
def test_obs():
    brain = get_brain()
    if brain.obs is None:
        return TestResult(ok=False, message="OBS is not configured")
    try:
        brain.obs.connect()
        connected = bool(getattr(brain.obs, "client", None))
        return TestResult(
            ok=connected,
            message="Connected to OBS" if connected else "OBS refused the connection",
            detail=f"{brain.config.obs_host}:{brain.config.obs_port}",
        )
    except Exception as e:
        return TestResult(ok=False, message="Could not reach OBS", detail=str(e)[:300])


@app.get("/secrets")
def secrets_state():
    """Which secrets are set — never their values.

    `public_dict()` strips them entirely, so the UI could not tell a missing key
    from a stored one and every field looked empty.
    """
    config = get_brain().config
    state = {key: bool(getattr(config, key, None)) for key in config.SECRET_KEYS}
    for skill_key, field_name in SECRET_SKILL_FIELDS:
        state[f"{skill_key}.{field_name}"] = bool(config.skills.get(skill_key, {}).get(field_name))
    return state


@app.get("/audio/devices")
def audio_devices():
    """Output devices, so picking one is not guesswork about an integer."""
    try:
        import sounddevice as sd

        return [
            {"id": index, "name": device.get("name", f"Device {index}"),
             "channels": device.get("max_output_channels", 0)}
            for index, device in enumerate(sd.query_devices())
            if device.get("max_output_channels", 0) > 0
        ]
    except Exception as e:
        logger.warning(f"Could not enumerate audio devices: {e}")
        return []


@app.get("/health")
def health():
    return {"status": "ok", "brain": brain_instance is not None}

# mount static files
frontend_path = Path(__file__).parent / "frontend" / "dist"
if frontend_path.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")
else:
    logger.warning(f"Frontend build not found at {frontend_path}. Run 'npm run build' in src/web/frontend.")

# --- SPA CATCH-ALL ROUTE ---

@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    # verify api route mismatch
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API Endpoint not found")

    if not frontend_path.exists():
        return {"error": "Frontend not found"}

    # a real file in the build — the favicon, the icon the sidebar shows — must
    # not be answered with index.html just because it lives outside /assets
    if full_path:
        root = frontend_path.resolve()
        candidate = (root / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)

    return FileResponse(frontend_path / "index.html")

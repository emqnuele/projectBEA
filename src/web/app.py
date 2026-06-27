from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional
import shutil
import os
from pathlib import Path
from src.core.config import BrainConfig
from src.core.brain import AIVtuberBrain
from src.utils.logger import get_logger

logger = get_logger("bea.web")

app = FastAPI(title="AI Vtuber Brain API")

# cors
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
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

def get_brain():
    if not brain_instance:
        raise HTTPException(status_code=503, detail="Brain not initialized")
    return brain_instance

@app.get("/config")
def get_config():
    brain = get_brain()
    # eeturn as dict
    from dataclasses import asdict
    return asdict(brain.config)

@app.post("/config")
def update_config(request: ConfigUpdateRequest):
    brain = get_brain()
    try:
        current_tts = brain.config.tts_provider
        restart_required = False

        # uppdate config object
        for key, value in request.config.items():
            if hasattr(brain.config, key):
                setattr(brain.config, key, value)
                
                # check for critical changes
                if key == "tts_provider" and value != current_tts:
                    restart_required = True
        
        # save to file
        brain.config.save_to_file()
        
        # hot reload
        brain.reload_configuration()
        
        msg = "Configuration updated."
        if restart_required:
            msg += " RESTART REQUIRED to apply new TTS provider."
            
        return {
            "status": "success", 
            "message": msg,
            "restart_required": restart_required
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
def get_history():
    brain = get_brain()
    return brain.history_manager.get_recent_history(limit=50)

@app.get("/sessions")
def list_sessions():
    brain = get_brain()
    return brain.list_sessions()

@app.post("/sessions")
async def create_session():
    brain = get_brain()
    session_id = brain.create_new_session()
    return {"status": "success", "session_id": session_id}

@app.post("/sessions/{session_id}/activate")
async def activate_session(session_id: str):
    brain = get_brain()
    if brain.load_session(session_id):
        return {"status": "success", "message": f"Session {session_id} activated"}
    raise HTTPException(status_code=404, detail="Session not found")

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
    active_skills = [
        skill.skill_name for skill in brain.skill_registry.toggleable()
        if skill.active
    ]
    return {
        "is_speaking": brain.is_speaking,
        "is_sleeping": brain.is_sleeping,
        "active_skills": active_skills
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
    filename = file.filename or "audio_upload.wav"
    temp_file = temp_dir / filename
    
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
        raise HTTPException(status_code=500, detail=str(e))
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
            voice = brain.surface_registry.get("voice:discord")
            if voice:
                voice.perceive(transcript, username, user_id=user_id)

        return {"status": "perceived", "transcript": transcript}
    except Exception as e:
        logger.error(f"Overheard transcript error: {e}")
        return {"status": "error", "transcript": "", "error": str(e)}
    finally:
        if temp_file.exists():
            os.remove(temp_file)

@app.get("/skills")
def list_skills():
    brain = get_brain()
    skills_data = {}
    for skill in brain.skill_registry.toggleable():
        key = skill.skill_name
        skills_data[key] = {
            "enabled": skill.enabled,
            "config": brain.config.skills.get(key, {}),
            "active": skill.active,
        }
    return skills_data

@app.post("/skills/{name}/toggle")
async def toggle_skill(name: str, enable: bool):
    brain = get_brain()
    if not brain.skill_registry.get_by_key(name):
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

@app.get("/health")
def health():
    return {"status": "ok"}

# mount static files
frontend_path = Path(__file__).parent / "frontend" / "dist"
if frontend_path.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")
else:
    logger.warning(f"Frontend build not found at {frontend_path}. Run 'npm run build' in src/web/frontend.")

# --- SPA CATCH-ALL ROUTE ---
from fastapi.responses import FileResponse

@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    # verify api route mismatch
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API Endpoint not found")

    # serve index.html
    if frontend_path.exists():
        return FileResponse(frontend_path / "index.html")
    return {"error": "Frontend not found"}

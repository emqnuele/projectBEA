"""What reaches her ears: uploaded audio, the call, and the bot's audio link."""

import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field, field_validator

from src.core.brain import AIVtuberBrain
from src.utils.logger import get_logger
from src.web.deps import get_brain

logger = get_logger("bea.web.voice")

router = APIRouter(tags=["voice"])


class DiscordChatRequest(BaseModel):
    username: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=4000)
    channelId: str = "unknown"
    userId: Optional[str] = None
    messageId: Optional[str] = None
    isDm: bool = False
    whitelisted: bool = True

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("message cannot be empty or whitespace-only")
        return stripped


@router.websocket("/voice/ws")
async def voice_push_channel(ws: WebSocket):
    """The bot's audio link: her voice out, playback reports back.

    It carries her actual voice and can be reached over TCP, so it presents the
    same per-process token as the bot's own command API. The loop here does no
    thinking: it hands every report to the channel and keeps the socket alive.
    """
    voice = getattr(get_brain(), "surface_registry", None)
    voice = voice.get("voice:discord") if voice is not None else None
    channel = getattr(voice, "channel", None)
    expected = getattr(getattr(voice, "transport", None), "api_token", None)

    if channel is None or not expected:
        await ws.close(code=1011)
        return
    if ws.headers.get("authorization") != f"Bearer {expected}":
        logger.warning("Refused an unauthenticated connection to the voice channel")
        await ws.close(code=1008)
        return

    await ws.accept()
    channel.attach(ws)
    try:
        while True:
            try:
                channel.on_message(json.loads(await ws.receive_text()))
            except json.JSONDecodeError:
                logger.debug("ignoring a malformed frame on the voice channel")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Voice channel closed: {e}")
    finally:
        channel.detach(ws)


@router.post("/audio")
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    brain: AIVtuberBrain = Depends(get_brain),
):
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


@router.post("/discord/chat")
async def discord_chat(request: DiscordChatRequest, brain: AIVtuberBrain = Depends(get_brain)):
    logger.info(f"Discord Chat from {request.username}: {request.message}")

    # one mind: deposit a perception and return immediately. Bea answers on her
    # own via the discord tools (reply/send_message), not via a synchronous reply.
    brain.perceive_discord_text(
        request.message, request.username, request.channelId,
        message_id=request.messageId, user_id=request.userId, is_dm=request.isDm,
        whitelisted=request.whitelisted,
    )
    return {"status": "perceived"}


@router.post("/discord/audio")
async def discord_audio_interaction(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    username: str = Form(...),
    user_id: Optional[str] = Form(default=None),
    whitelisted: bool = Form(default=True),
    listeners: Optional[int] = Form(default=None),
    brain: AIVtuberBrain = Depends(get_brain),
):
    """Speech from the call: transcribe it and hand it to the mind.

    The bot does not wait for audio here — whatever she decides to say is pushed
    into the call over /voice/ws, whenever she decides to say it.
    """
    # save temp file
    temp_dir = Path("temp_discord")
    temp_dir.mkdir(exist_ok=True)
    temp_file = temp_dir / f"{username}_{int(os.times().elapsed)}.wav"

    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        transcript = await brain.process_discord_interaction(
            str(temp_file), username, user_id=user_id,
            whitelisted=whitelisted, listeners=listeners,
        )
        return {"status": "perceived", "transcript": transcript}
    except Exception as e:
        # the whole exception goes to the log, where it is useful; what comes
        # back over http is not the place for a stack of absolute paths and
        # driver internals
        logger.error(f"Discord Audio Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Could not transcribe that. Check the engine log."
        ) from e
    finally:
        # cleanup
        if temp_file.exists():
            os.remove(temp_file)


@router.post("/voice/transcript")
async def buffer_voice_transcript(
    file: UploadFile = File(...),
    username: str = Form(...),
    user_id: Optional[str] = Form(default=None),
    whitelisted: bool = Form(default=True),
    listeners: Optional[int] = Form(default=None),
    brain: AIVtuberBrain = Depends(get_brain),
):
    """
    Overheard speech: transcribes a short snippet and feeds it to the
    consciousness as a VOICE perception (steering), without waiting for a reply.
    Bea decides on her own whether it's worth reacting to.
    """
    # save temp file
    temp_dir = Path("temp_discord")
    temp_dir.mkdir(exist_ok=True)
    temp_file = temp_dir / f"buf_{username}_{int(os.times().elapsed)}.wav"

    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    transcript = ""
    try:
        if brain.stt:
            # off the loop: a transcription here froze every other channel too
            transcript = await asyncio.to_thread(brain.stt.transcribe, str(temp_file))
            logger.info(f"Overheard: [{username}] '{transcript}'")

        if transcript and transcript.strip() and transcript != "[Unintelligible]":
            if brain.surface_registry is not None:
                # the registry is keyed by name, and each name has its own
                # interface: what this one perceives is not what the others do
                voice: Any = brain.surface_registry.get("voice:discord")
                if voice is not None and hasattr(voice, "perceive"):
                    voice.perceive(transcript, username, user_id=user_id,
                                   whitelisted=whitelisted, listeners=listeners)

        return {"status": "perceived", "transcript": transcript}
    except Exception as e:
        logger.error(f"Overheard transcript error: {e}")
        return {"status": "error", "transcript": "", "error": str(e)}
    finally:
        if temp_file.exists():
            os.remove(temp_file)

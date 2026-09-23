"""What reaches her ears: uploaded audio, the call, and the bot's audio link."""

import asyncio
import json
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from fastapi import (
    APIRouter,
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


@contextmanager
def _saved(file: UploadFile, folder: str) -> Iterator[Path]:
    """the upload on disk for as long as the block runs, then removed."""
    directory = Path(folder)
    directory.mkdir(exist_ok=True)
    # named by a uuid, never by the client: a username or a filename is a path
    suffix = Path(file.filename or "").suffix[:8] or ".wav"
    path = directory / f"{uuid.uuid4().hex}{suffix}"
    try:
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        yield path
    finally:
        path.unlink(missing_ok=True)


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
    voice = getattr(get_brain(), "skill_registry", None)
    voice = voice.get("voice:discord") if voice is not None else None
    channel = getattr(voice, "channel", None)
    expected = getattr(getattr(voice, "transport", None), "api_token", None)

    if channel is None or not expected:
        await ws.close(code=1011)
        return
    if ws.headers.get("authorization") != f"Bearer {expected}":
        # the usual sender is a bot left over from a previous run: it holds the
        # token that process minted, and nothing on this one will take it
        logger.warning("Refused an unauthenticated connection to the voice channel "
                       "(a discord bot from an earlier run?)")
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
    file: UploadFile = File(...),
    brain: AIVtuberBrain = Depends(get_brain),
):
    with _saved(file, "temp") as path:
        mood, message, transcript = await brain.generate_audio_response(str(path))

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
    try:
        with _saved(file, "temp_discord") as path:
            transcript = await brain.process_discord_interaction(
                str(path), username, user_id=user_id,
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
    transcript = ""
    try:
        with _saved(file, "temp_discord") as path:
            if brain.stt:
                # off the loop: a transcription here froze every other channel too
                transcript = await asyncio.to_thread(brain.stt.transcribe, str(path))
                logger.info(f"Overheard: [{username}] '{transcript}'")

        if transcript and transcript.strip() and transcript != "[Unintelligible]":
            # the registry is keyed by name, and each name has its own
            # interface: what this one perceives is not what the others do
            voice: Any = brain.skill_registry.get("voice:discord") if brain.skill_registry else None
            if voice is not None and hasattr(voice, "perceive"):
                voice.perceive(transcript, username, user_id=user_id,
                               whitelisted=whitelisted, listeners=listeners)

        return {"status": "perceived", "transcript": transcript}
    except Exception as e:
        logger.error(f"Overheard transcript error: {e}")
        return {"status": "error", "transcript": "", "error": str(e)}
    finally:
        # after the perception is on the bus: the mind may be waiting for it
        voice_surface: Any = brain.skill_registry.get("voice:discord") if brain.skill_registry else None
        if voice_surface is not None and hasattr(voice_surface, "transcribed"):
            voice_surface.transcribed(user_id)

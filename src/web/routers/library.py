"""The model library: what is on this machine, what can be fetched, and which one is on stage.

The engine, the voice and the call share this process's one event loop, so
nothing here reads a model on it: listing, thumbnails and files are sync
handlers (the threadpool), downloads run on their own thread, and an upload is
written by a thread while the loop only moves bytes. Choosing a model rebuilds
the stage alone — never the whole configuration, which would reload the
language model, the voice and the ears for a change of clothes.

Unauthenticated like the rest of the stage: the server listens on loopback and
CORS is closed, and nothing here writes outside the models and clips folders.
"""

import asyncio
import queue
import threading
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.core.brain import AIVtuberBrain
from src.core.expression.face import weights_for
from src.core.mind.moods import MOODS
from src.core.stage import clips_dir
from src.modules.avatar import catalog, library
from src.utils.logger import get_logger
from src.web.deps import get_brain

logger = get_logger("bea.web.library")

router = APIRouter(tags=["stage"])

DOWNLOADS = library.Downloads()

_END = object()


class Pick(BaseModel):
    id: str


@router.get("/stage/library")
def library_overview(brain: AIVtuberBrain = Depends(get_brain)) -> Dict[str, Any]:
    config = brain.config
    return {
        "models": library.list_models(config),
        "catalog": library.list_catalog(config, DOWNLOADS),
        "clips": library.list_clips(config),
        "models_dir": str(library.models_dir(config)),
        "clips_dir": str(clips_dir(config)),
        "upload_limit": library.UPLOAD_LIMIT,
    }


@router.get("/stage/library/downloads")
def library_downloads() -> Dict[str, Dict[str, Any]]:
    return DOWNLOADS.snapshot()


@router.post("/stage/library/download", status_code=202)
def library_download(pick: Pick, brain: AIVtuberBrain = Depends(get_brain)) -> Dict[str, Any]:
    asset = catalog.find(pick.id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Nothing called {pick.id!r} in the catalog")
    into = library.models_dir(brain.config) if asset.kind == "model" else clips_dir(brain.config)
    if not DOWNLOADS.start(asset, into):
        raise HTTPException(status_code=409, detail=f"{asset.name} is already downloading")
    return {"id": asset.id, "state": "running"}


@router.get("/stage/library/models/{model_id}/thumbnail")
def library_thumbnail(model_id: str, brain: AIVtuberBrain = Depends(get_brain)):
    found = library.model_thumbnail(brain.config, model_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No picture for that model")
    mime, data = found
    # the url carries the file's version, so a cached picture is never a stale one
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=604800"})


@router.get("/stage/library/models/{model_id}/file")
def library_file(model_id: str, brain: AIVtuberBrain = Depends(get_brain)):
    path = library.resolve_model(brain.config, model_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No model called {model_id!r}")
    return FileResponse(path, media_type="model/gltf-binary")


@router.delete("/stage/library/models/{model_id}")
def library_delete(model_id: str, brain: AIVtuberBrain = Depends(get_brain)) -> Dict[str, Any]:
    try:
        path = library.delete_model(brain.config, model_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"No model called {model_id!r}") from e
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    logger.info(f"Deleted {path.name} from the model library")
    return {"deleted": path.name}


# async like the config save: the stage rebuild touches avatar ports that live on the loop
@router.post("/stage/library/select")
async def library_select(pick: Pick, brain: AIVtuberBrain = Depends(get_brain)) -> Dict[str, Any]:
    path = await asyncio.to_thread(library.resolve_model, brain.config, pick.id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No model called {pick.id!r}")
    brain.config.stage = {**(brain.config.stage or {}), "model_path": str(path)}
    await asyncio.to_thread(brain.config.save_to_file)
    brain.reload_stage()
    return {"model_path": str(path)}


async def _upload(request: Request, name: str, folder, kind: str) -> Dict[str, Any]:
    declared = int(request.headers.get("content-length") or 0)
    if declared > library.UPLOAD_LIMIT:
        raise HTTPException(status_code=413, detail="That file is too large for the library.")

    chunks: "queue.Queue[Any]" = queue.Queue(maxsize=32)
    finished = threading.Event()

    def drain():
        while True:
            chunk = chunks.get()
            if chunk is _END:
                return
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk

    def write():
        try:
            return library.save_upload(drain(), name, folder, kind)
        finally:
            finished.set()

    def offer(item) -> bool:
        # a writer that already gave up reads nothing more, and a blocking put would wait forever
        while not finished.is_set():
            try:
                chunks.put(item, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    loop = asyncio.get_running_loop()
    writer = loop.run_in_executor(None, write)
    try:
        async for chunk in request.stream():
            if chunk and not await loop.run_in_executor(None, offer, chunk):
                break
    except BaseException:
        await loop.run_in_executor(None, offer, ConnectionError("the upload was cut off"))
        await asyncio.gather(writer, return_exceptions=True)
        raise
    await loop.run_in_executor(None, offer, _END)
    try:
        path = await writer
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=f"{e} is already in the library") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    logger.info(f"Added {path.name} to {folder}")
    return {"file": path.name}


@router.post("/stage/library/models/upload", status_code=201)
async def library_upload_model(request: Request, name: str, brain: AIVtuberBrain = Depends(get_brain)):
    """The .vrm is the request body; `name` is its file name."""
    return await _upload(request, name, library.models_dir(brain.config), "model")


@router.post("/stage/library/clips/upload", status_code=201)
async def library_upload_clip(request: Request, name: str, brain: AIVtuberBrain = Depends(get_brain)):
    """The .vrma is the request body; `name` is its file name."""
    return await _upload(request, name, clips_dir(brain.config), "clip")


@router.get("/stage/moods")
def stage_moods() -> Dict[str, Dict[str, float]]:
    """Every mood's expression weights, so the preview can wear one without the engine."""
    return {mood: weights_for(mood) for mood in MOODS}


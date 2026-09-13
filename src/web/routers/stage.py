"""The stage: what an OBS browser source draws, and what it is allowed to read."""

import asyncio
import json
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from src.core.brain import AIVtuberBrain
from src.core.stage import clips_dir, public_config
from src.web.deps import frontend_path, get_brain

router = APIRouter(tags=["stage"])


def _avatar_files(config) -> Dict[str, Path]:
    """Every image the avatar map names, keyed `mood/state`.

    The allow-list for the preview: an endpoint that served any path the query
    string asked for would read any file on the machine.
    """
    out: Dict[str, Path] = {}
    for mood, slots in (config.avatar_map or {}).items():
        for state, raw in (slots or {}).items():
            if raw:
                out[f"{mood}/{state}"] = Path(raw).resolve()
    return out


@router.get("/stage/config")
def stage_config(brain: AIVtuberBrain = Depends(get_brain)):
    """What the browser source needs to draw her. Never a secret."""
    return public_config(brain.config)


@router.get("/stage/model")
def stage_model(brain: AIVtuberBrain = Depends(get_brain)):
    """The .vrm the browser source draws.

    Served by the engine rather than by a path in the page, so the model can
    live anywhere on the machine without the browser needing file access.
    """
    raw = (getattr(brain.config, "stage", {}) or {}).get("model_path")
    if not raw:
        raise HTTPException(status_code=404, detail="No model is configured")
    path = Path(raw).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Configured, but not on disk: {path}")
    return FileResponse(path, media_type="model/gltf-binary")


@router.get("/stage/clips")
def stage_clips(brain: AIVtuberBrain = Depends(get_brain)):
    """The behaviours installed, by name — what the dashboard offers you."""
    folder = clips_dir(brain.config)
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.vrma"))


@router.get("/stage/clips/{name}")
def stage_clip(name: str, brain: AIVtuberBrain = Depends(get_brain)):
    """One .vrma behaviour, by the name `/stage/clips` listed."""
    folder = clips_dir(brain.config).resolve()
    path = (folder / f"{name}.vrma").resolve()
    # the name comes from a page: it must not be able to walk out of the folder
    if not path.is_relative_to(folder) or not path.is_file():
        raise HTTPException(status_code=404, detail=f"No behaviour called {name!r}")
    return FileResponse(path, media_type="model/gltf-binary")


@router.get("/stage/stream")
async def stage_stream(request: Request, brain: AIVtuberBrain = Depends(get_brain)):
    """Server-sent events for the browser source.

    A snapshot first, then patches. No backlog on purpose: OBS reloads a browser
    source whenever it is toggled, and replaying what already happened would
    have her act out the last minute of the stream a second time.
    """
    queue = brain.stage.subscribe()

    async def pump():
        yield f"data: {json.dumps({'type': 'snapshot', **brain.stage.snapshot()})}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    patch = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps({'type': 'patch', **patch})}\n\n"
        finally:
            brain.stage.unsubscribe(queue)

    return StreamingResponse(pump(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router.get("/stage")
def stage_page():
    """The page you point an OBS Browser Source at."""
    page = frontend_path / "stage.html"
    if not page.is_file():
        raise HTTPException(
            status_code=404,
            detail="The stage page is not built. Run `uv run bea --install-node`.",
        )
    return FileResponse(page)


@router.get("/stage/preview")
def stage_preview(mood: str, state: str = "idle", brain: AIVtuberBrain = Depends(get_brain)):
    """One avatar image, for the preview in the dashboard."""
    path = _avatar_files(brain.config).get(f"{mood}/{state}")
    if path is None:
        raise HTTPException(status_code=404, detail="No image is mapped for that mood and state")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Mapped, but not on disk: {path}")
    return FileResponse(path)

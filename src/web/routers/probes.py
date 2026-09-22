"""Does this actually work? One button per thing that can be misconfigured."""

import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.core.brain import AIVtuberBrain
from src.web.deps import get_brain

router = APIRouter(tags=["probes"])


class TestResult(BaseModel):
    ok: bool
    message: str
    detail: str = ""


@router.post("/test/llm", response_model=TestResult)
async def test_llm(brain: AIVtuberBrain = Depends(get_brain)):
    try:
        started = time.perf_counter()
        # `complete` is the contract every client and every pool honours
        reply = await brain.llm.complete([
            {"role": "system", "content": "You are a test probe."},
            {"role": "user", "content": "Reply with the single word: ok."},
        ])
        elapsed = int((time.perf_counter() - started) * 1000)
        return TestResult(ok=True, message=f"{brain.config.llm_provider} answered in {elapsed} ms",
                          detail=(reply.content or "")[:200])
    except Exception as e:
        return TestResult(ok=False, message="The model did not answer", detail=str(e)[:300])


@router.post("/test/tts", response_model=TestResult)
async def test_tts(brain: AIVtuberBrain = Depends(get_brain)):
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


@router.post("/test/obs", response_model=TestResult)
def test_obs(brain: AIVtuberBrain = Depends(get_brain)):
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


@router.post("/test/vts", response_model=TestResult)
async def test_vts(brain: AIVtuberBrain = Depends(get_brain)):
    """Whether she can reach VTube Studio, and what your model can do."""
    from src.modules.avatar.vtube_studio import probe

    found = await probe(brain.config)
    # "" and not None: `detail` is a str, and the failure path is exactly the
    # one that would have hit a validation error instead of reporting the failure
    detail = ""
    if found["ok"]:
        detail = f"{len(found['expressions'])} expressions, {len(found['hotkeys'])} hotkeys"
    return TestResult(ok=found["ok"], message=found["message"], detail=detail)


@router.get("/vts/model")
async def vts_model(brain: AIVtuberBrain = Depends(get_brain)):
    """The expressions and hotkeys of the model VTube Studio has loaded.

    So the dashboard offers what your own model actually has, instead of a text
    box where a typo is silent until you are live.
    """
    from src.modules.avatar.vtube_studio import probe

    return await probe(brain.config)

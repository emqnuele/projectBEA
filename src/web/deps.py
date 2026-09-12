"""What every router needs: the brain, and where the built dashboard is.

Both used to live in `app.py`, which is also the module that registers the
routers — so a router reaching for either had to import it from inside a
function to break the cycle. They live here instead, below everything, and
nothing has to be deferred.
"""

from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from src.core.brain import AIVtuberBrain

# the one brain this process serves. Set by `run_server` before uvicorn starts,
# and by the tests, which stand a double in its place.
brain_instance: Optional[AIVtuberBrain] = None

# the dashboard build. Absent until `bea --install-node` has run, which is why
# every reader checks rather than assuming.
frontend_path = Path(__file__).parent / "frontend" / "dist"


def set_brain(brain: Optional[AIVtuberBrain]) -> None:
    global brain_instance
    brain_instance = brain


def current_brain() -> Optional[AIVtuberBrain]:
    """The brain, or None. For the callers that have something to say about it."""
    return brain_instance


def get_brain() -> AIVtuberBrain:
    """The brain, or a 503. The dependency almost every endpoint takes."""
    if not brain_instance:
        raise HTTPException(status_code=503, detail="Brain not initialized")
    return brain_instance

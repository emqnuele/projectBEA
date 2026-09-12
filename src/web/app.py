"""The brain API and the dashboard that drives it.

Every endpoint lives in `routers/`, one module per thing it is about. This file
is what is left over once they do: the app, who may talk to it, where the built
dashboard is served from, and the catch-all that hands everything else to the
single-page app.
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.utils.logger import get_logger
from src.web import routers
from src.web.deps import frontend_path

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

# before the SPA catch-all below, which answers every GET registered after it
for router in routers.ALL:
    app.include_router(router)

# mount static files
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

"""Every router the app serves, in the order it registers them.

Order matters in one place only: the SPA catch-all in `app.py` answers every
GET registered after it, so it goes on last and everything here goes on first.
Between themselves these are independent — each owns its own paths.

The modules are imported, not their routers: binding `updates` to a router here
would shadow `src.web.routers.updates` for everyone who imports it by name.
"""

from typing import Tuple

from fastapi import APIRouter

from src.web.routers import (
    chat,
    donations,
    health,
    memory,
    persona,
    plan,
    probes,
    settings,
    stage,
    status,
    updates,
    voice,
)

ALL: Tuple[APIRouter, ...] = (
    settings.router,
    persona.router,
    chat.router,
    voice.router,
    donations.router,
    status.router,
    plan.router,
    memory.router,
    probes.router,
    stage.router,
    updates.router,
    health.router,
)

__all__ = ["ALL"]

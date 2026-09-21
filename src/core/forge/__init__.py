"""FORGE — frontend/avatar state contract for ProjectSHURA.

See docs/design/SHURA_PRESENCE.md and docs/FORGE_CANONICALIZATION_OPTIONS.md
for the design context. This module is the code realization of the FORGE
boundary: it consumes core interfaces and produces semantic state only.

FORGE does NOT import brain, consciousness, expression, or any renderer.
The dependency direction is:

    identity → brain/consciousness → events → presence → dream
                                          ↑
                            ATLAS consumes events; provides snapshot
                                          ↑
                            FORGE consumes presence + ATLAS + dream + events
"""

from .contract import (
    ForgeState,
    ForgePresenceState,
    ForgeProjection,
)

__all__ = [
    "ForgeState",
    "ForgePresenceState",
    "ForgeProjection",
]

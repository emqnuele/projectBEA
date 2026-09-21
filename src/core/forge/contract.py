"""FORGE — semantic state contract for the SHURA frontend/avatar layer.

FORGE is the human-facing workspace/avatar environment. It consumes stable
interfaces from ProjectSHURA core (events, presence, dream projection) and
ATLAS (project/work snapshot) and produces a single semantic state object
(ForgeState) that any renderer can consume.

FORGE must never emit:
  - PNG paths
  - Live2D model indexes
  - OBS scene names
  - UI coordinates
  - Frontend widget IDs
  - Arbitrary CSS state
  - Renderer-specific animation instructions

FORGE must always emit:
  - Semantic presence state (offline, idle, listening, thinking, speaking,
    interrupted, dreaming, error)
  - Semantic emotion (mapped to legacy mood IDs where applicable)
  - Activity description (what SHURA is currently doing, in plain language)
  - ATLAS project/work context (what we're building, what's active)
  - Recent events (for the activity feed)
  - Notifications (for user attention)

Any renderer (PNG sprite, Live2D, 3D, desktop overlay, web UI) maps
ForgeState to its own visual representation independently.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


# ------------------------------------------------------------------
# Semantic presence state (mirrors PresenceState from presence/runtime.py)
# ------------------------------------------------------------------

class ForgePresenceState(str, Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    DREAMING = "dreaming"
    ERROR = "error"


# ------------------------------------------------------------------
# ForgeState — the single semantic state object FORGE consumes
# ------------------------------------------------------------------

@dataclass
class ForgeState:
    """Semantic, renderer-agnostic state snapshot for the FORGE frontend.

    Aggregates:
      - Presence state (from PresenceRuntime via events/projection)
      - ATLAS context (active project, recent work items, milestones)
      - Dream state (from DreamStateProjection)
      - Recent events (for activity feed, bounded)
      - Notifications (user-attention items)

    No PNG paths, OBS scene names, Live2D indices, UI coordinates, CSS
    state, or renderer-specific animation instructions.
    """

    # --- Presence ---
    presence_state: str = ForgePresenceState.OFFLINE.value
    is_connected: bool = False
    emotion: Optional[str] = None          # semantic emotion label
    motion: Optional[str] = None          # semantic motion label

    # --- Runtime ---
    is_speaking: bool = False
    is_sleeping: bool = False
    is_dreaming: bool = False

    # --- ATLAS context ---
    active_project: Optional[Dict[str, Any]] = None
    recent_work_items: List[Dict[str, Any]] = field(default_factory=list)
    active_milestones: List[Dict[str, Any]] = field(default_factory=list)
    recent_decisions: List[Dict[str, Any]] = field(default_factory=list)

    # --- Dream state (from DreamStateProjection) ---
    dream_state: Optional[Dict[str, Any]] = None

    # --- Activity feed ---
    recent_events: List[Dict[str, Any]] = field(default_factory=list)

    # --- Notifications ---
    notifications: List[Dict[str, Any]] = field(default_factory=list)

    # --- Metadata ---
    projected_at: float = field(default_factory=_now)
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "presence_state": self.presence_state,
            "is_connected": self.is_connected,
            "emotion": self.emotion,
            "motion": self.motion,
            "is_speaking": self.is_speaking,
            "is_sleeping": self.is_sleeping,
            "is_dreaming": self.is_dreaming,
            "active_project": self.active_project,
            "recent_work_items": self.recent_work_items,
            "active_milestones": self.active_milestones,
            "recent_decisions": self.recent_decisions,
            "dream_state": self.dream_state,
            "recent_events": self.recent_events,
            "notifications": self.notifications,
            "projected_at": self.projected_at,
            "run_id": self.run_id,
        }


# ------------------------------------------------------------------
# ForgeProjection — builds ForgeState from core interfaces
# ------------------------------------------------------------------

class ForgeProjection:
    """Builds ForgeState from ProjectSHURA core interfaces.

    Consumes:
      - EventManager (for recent events, presence event replay)
      - PresenceRuntime (for current presence state, emotion, motion)
      - AtlasService.snapshot() (for project/work context)
      - DreamStateProjection (for dream state)

    The projection is read-only. It never mutates any core object.
    """

    def __init__(
        self,
        event_manager: Any,
        presence_runtime: Any,
        atlas_snapshot_fn: Any,
        dream_projection_fn: Any,
        is_speaking: bool = False,
        is_sleeping: bool = False,
    ):
        self.events = event_manager
        self.presence = presence_runtime
        self._atlas_snapshot = atlas_snapshot_fn
        self._dream_projection = dream_projection_fn
        self._is_speaking = is_speaking
        self._is_sleeping = is_sleeping

    def build_state(self, run_id: Optional[str] = None) -> ForgeState:
        """Build a ForgeState from current core state. Read-only."""
        state = ForgeState()
        state.projected_at = _now()
        state.run_id = run_id

        # --- Presence (from PresenceRuntime directly — the source of truth) ---
        pr = self.presence
        state.presence_state = pr.state.value
        state.is_connected = pr.connected
        state.emotion = pr.emotion
        state.motion = pr.motion

        # --- Runtime flags (provided by the brain, not inferred) ---
        state.is_speaking = self._is_speaking
        state.is_sleeping = self._is_sleeping

        # --- ATLAS context ---
        try:
            snap = self._atlas_snapshot()
            if snap.active_project_id:
                for p in snap.projects:
                    if p.project_id == snap.active_project_id:
                        state.active_project = {
                            "project_id": p.project_id,
                            "name": p.name,
                            "description": p.description,
                            "status": p.status,
                        }
                        break
            state.recent_work_items = [
                {
                    "item_id": w.item_id,
                    "project_id": w.project_id,
                    "title": w.title,
                    "status": w.status,
                    "priority": w.priority,
                    "work_type": w.work_type,
                    "assigned_to": w.assigned_to,
                }
                for w in snap.work_items[-10:]
            ]
            state.active_milestones = [
                {
                    "milestone_id": m.milestone_id,
                    "project_id": m.project_id,
                    "name": m.name,
                    "status": m.status,
                    "order": m.order,
                }
                for m in snap.milestones if m.status != "completed"
            ]
            state.recent_decisions = [
                {
                    "decision_id": d.decision_id,
                    "project_id": d.project_id,
                    "title": d.title,
                    "status": d.status,
                    "decided_at": d.decided_at,
                }
                for d in snap.decisions[-5:]
            ]
        except Exception:
            # ATLAS snapshot must never crash FORGE state build
            pass

        # --- Dream state ---
        try:
            dp = self._dream_projection(run_id)
            state.dream_state = {
                "run_id": dp.run_id,
                "run_state": dp.run_state,
                "snapshot_id": dp.snapshot_id,
                "replay_sequence_count": dp.replay_sequence_count,
                "replayed_lifecycle_events": dp.replayed_lifecycle_events,
                "active_concepts": dp.active_concepts,
                "unresolved_threads": dp.unresolved_threads,
                "contradictions": dp.contradictions,
            }
            if dp.run_state not in ("created", "unknown"):
                state.is_dreaming = True
        except Exception:
            pass

        # --- Recent events (for activity feed) ---
        try:
            recent = self.events.get_events(limit=20)
            state.recent_events = [
                {
                    "event_id": e.get("event_id"),
                    "event_type": e.get("event_type"),
                    "category": e.get("category"),
                    "source": e.get("source"),
                    "message": e.get("message"),
                    "subsystem": e.get("subsystem"),
                    "severity": e.get("severity"),
                    "timestamp": e.get("timestamp"),
                    "payload_summary": {
                        k: v for k, v in (e.get("payload") or {}).items()
                        if isinstance(v, (str, int, float, bool, list, dict))
                    },
                }
                for e in recent
            ]
        except Exception:
            pass

        # --- Notifications ---
        # Notifications are currently empty; the runtime emits them through
        # future mechanisms. This field exists for the frontend to consume.
        state.notifications = []

        return state

"""ProjectSHURA custom endpoints: ATLAS operational layer, FORGE projection, Dream observation.

These endpoints observe or mutate ProjectSHURA-specific domain state.
They are registered alongside the upstream BEA routers in src/web/app.py.
"""

from fastapi import APIRouter, Depends, Form, HTTPException
from typing import Optional

from src.web.deps import get_brain
from src.core.brain import AIVtuberBrain

router = APIRouter()


# --- FORGE: semantic state for the frontend/avatar layer --------------------

@router.get("/forge/state")
def forge_state():
    """Aggregate semantic state for the FORGE frontend/avatar layer.

    Delegates to brain.get_forge_state() — the brain owns the projection
    construction, not the web layer. This endpoint is read-only; it does
    not mutate any state.
    """
    brain = get_brain()
    return brain.get_forge_state()


# --- Dream: read-only observation -------------------------------------------

@router.get("/dream/projection")
def dream_projection(run_id: Optional[str] = None):
    """Read-only dream run projection for the FORGE frontend.

    Projection layer: event replay only, no domain mutation. Does not import
    brain/consciousness internals for mutation logic.
    """
    brain = get_brain()
    from src.core.dream.projection import build_projection, DreamRun, DreamState
    domain_run = DreamRun(run_id=run_id or "unknown", state=DreamState.CREATED)
    proj = build_projection(
        run=domain_run,
        event_manager=brain.event_manager,
    )
    return proj.to_dict()


@router.get("/workspace/dream-events")
def workspace_dream_events(limit: int = 20):
    """Read-only dream event journal for the workspace layer."""
    brain = get_brain()
    all_events = brain.event_manager.get_events(limit=limit * 5)
    dream_events = [e for e in all_events if e.get("category") == "dream"]
    return dream_events[:limit]


# --- ATLAS: project/work/milestone/decision management ---------------------

@router.get("/atlas/snapshot")
def atlas_snapshot():
    """Read-only ATLAS domain snapshot."""
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    return brain.atlas_service.snapshot().to_dict()


@router.post("/atlas/projects")
def atlas_create_project(name: str = Form(...), description: str = Form(default="")):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    project = brain.atlas_service.create_project(name=name, description=description)
    return {"status": "success", "project": _project_to_dict(project)}


@router.get("/atlas/projects")
def atlas_list_projects():
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    return {"projects": [_project_to_dict(p) for p in brain.atlas_service.list_projects()]}


@router.get("/atlas/projects/{project_id}")
def atlas_get_project(project_id: str):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        return _project_to_dict(brain.atlas_service.get_project(project_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/atlas/projects/{project_id}/active")
def atlas_set_active_project(project_id: str):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        project = brain.atlas_service.set_active_project(project_id)
        return {"status": "success", "active_project": _project_to_dict(project)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/atlas/projects/{project_id}")
def atlas_update_project(
    project_id: str,
    description: Optional[str] = Form(default=None),
    name: Optional[str] = Form(default=None),
):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        kwargs = {}
        if description is not None:
            kwargs["description"] = description
        if name is not None:
            kwargs["name"] = name
        project = brain.atlas_service.update_project(project_id, **kwargs)
        return {"status": "success", "project": _project_to_dict(project)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/atlas/projects/{project_id}/delete")
def atlas_delete_project(project_id: str):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        brain.atlas_service.delete_project(project_id)
        return {"status": "success"}
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/atlas/projects/{project_id}/work-items")
def atlas_create_work_item(
    project_id: str,
    title: str = Form(...),
    description: str = Form(default=""),
    priority: str = Form(default="medium"),
    work_type: str = Form(default="task"),
    assigned_to: str = Form(default=""),
    depends_on: str = Form(default=""),
):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        deps = [d.strip() for d in depends_on.split(",") if d.strip()] if depends_on else []
        item = brain.atlas_service.create_work_item(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            work_type=work_type,
            assigned_to=assigned_to,
            depends_on=deps or None,
        )
        return {"status": "success", "work_item": _work_item_to_dict(item)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/atlas/projects/{project_id}/work-items")
def atlas_list_work_items(project_id: str, status: Optional[str] = None):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        brain.atlas_service.get_project(project_id)  # verify exists
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    items = brain.atlas_service.list_work_items(project_id=project_id, status=status)
    return {"work_items": [_work_item_to_dict(w) for w in items]}


@router.post("/atlas/work-items/{item_id}/transition")
def atlas_transition_work_item(item_id: str, new_status: str = Form(...)):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        item = brain.atlas_service.transition_work_item(item_id, new_status)
        return {"status": "success", "work_item": _work_item_to_dict(item)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Work item not found")


@router.get("/atlas/work-items/{item_id}")
def atlas_get_work_item(item_id: str):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        return _work_item_to_dict(brain.atlas_service.get_work_item(item_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Work item not found")


@router.post("/atlas/milestones")
def atlas_create_milestone(
    project_id: str = Form(...),
    name: str = Form(...),
    description: str = Form(default=""),
    order: int = Form(default=0),
):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        ms = brain.atlas_service.create_milestone(
            project_id=project_id, name=name, description=description, order=order
        )
        return {"status": "success", "milestone": _milestone_to_dict(ms)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/atlas/milestones")
def atlas_list_milestones(project_id: Optional[str] = None):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    milestones = brain.atlas_service.list_milestones(project_id=project_id)
    return {"milestones": [_milestone_to_dict(m) for m in milestones]}


@router.post("/atlas/milestones/{milestone_id}/complete")
def atlas_complete_milestone(milestone_id: str):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        ms = brain.atlas_service.complete_milestone(milestone_id)
        return {"status": "success", "milestone": _milestone_to_dict(ms)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Milestone not found")


@router.post("/atlas/decisions")
def atlas_create_decision(
    project_id: str = Form(...),
    title: str = Form(...),
    context: str = Form(default=""),
    decision: str = Form(default=""),
    rationale: str = Form(default=""),
    impact: str = Form(default=""),
):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        d = brain.atlas_service.create_decision(
            project_id=project_id,
            title=title,
            context=context,
            decision=decision,
            rationale=rationale,
            impact=impact,
        )
        return {"status": "success", "decision": _decision_to_dict(d)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/atlas/decisions")
def atlas_list_decisions(project_id: Optional[str] = None):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    decisions = brain.atlas_service.list_decisions(project_id=project_id)
    return {"decisions": [_decision_to_dict(d) for d in decisions]}


@router.post("/atlas/artifacts")
def atlas_create_artifact(
    project_id: str = Form(...),
    name: str = Form(...),
    content: str = Form(default=""),
    artifact_type: str = Form(default="note"),
):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        a = brain.atlas_service.create_artifact(
            project_id=project_id,
            name=name,
            content=content,
            artifact_type=artifact_type,
        )
        return {"status": "success", "artifact": _artifact_to_dict(a)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/atlas/artifacts")
def atlas_list_artifacts(project_id: Optional[str] = None):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    artifacts = brain.atlas_service.list_artifacts(project_id=project_id)
    return {"artifacts": [_artifact_to_dict(a) for a in artifacts]}


@router.post("/atlas/artifacts/{artifact_id}/delete")
def atlas_delete_artifact(artifact_id: str):
    brain = get_brain()
    if brain.atlas_service is None:
        raise HTTPException(status_code=503, detail="ATLAS service not initialized")
    try:
        brain.atlas_service.delete_artifact(artifact_id)
        return {"status": "success"}
    except KeyError:
        raise HTTPException(status_code=404, detail="Artifact not found")


# --- Serialization helpers --------------------------------------------------

def _project_to_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "active": p.active,
        "created_at": p.created_at,
    }


def _work_item_to_dict(w):
    return {
        "id": w.id,
        "title": w.title,
        "description": w.description,
        "status": w.status,
        "priority": w.priority,
        "work_type": w.work_type,
        "assigned_to": w.assigned_to,
        "depends_on": w.depends_on,
        "created_at": w.created_at,
        "updated_at": w.updated_at,
    }


def _milestone_to_dict(m):
    return {
        "id": m.id,
        "name": m.name,
        "description": m.description,
        "order": m.order,
        "completed": m.completed,
        "completed_at": m.completed_at,
    }


def _decision_to_dict(d):
    return {
        "id": d.id,
        "title": d.title,
        "context": d.context,
        "decision": d.decision,
        "rationale": d.rationale,
        "impact": d.impact,
        "created_at": d.created_at,
    }


def _artifact_to_dict(a):
    return {
        "id": a.id,
        "name": a.name,
        "content": a.content,
        "artifact_type": a.artifact_type,
        "created_at": a.created_at,
    }

"""The shape of the API, now that it is assembled from routers.

`app.py` was one file with sixty endpoints in it. Splitting it up cannot change
what the API serves, and the one thing that can go wrong when it is assembled
from parts is order: a route registered earlier answers for a URL that belongs
to a later one, and the endpoint simply stops existing with nothing raised
anywhere. These pin both — the full set of paths, and that nothing is shadowed.
"""

import re
from types import SimpleNamespace
from typing import Any, List, Optional, cast

import pytest
from fastapi.routing import APIRouter

from src.core.brain import AIVtuberBrain
from src.web import routers
from src.web.app import app

# a concrete value for every path parameter the api declares
SAMPLES = {
    "key": "discord",
    "session_id": "abc",
    "objective_id": "7",
    "name": "clipname",
    "full_path": "some/spa/route",
}

# the whole API, as it stood when app.py was one file. A path leaving this list
# is a path that was dropped; one arriving is one that has to be added here on
# purpose rather than by accident.
EXPECTED_PATHS = {
    "/config", "/settings", "/settings/{key}", "/secrets", "/audio/devices",
    "/persona", "/onboarding", "/onboarding/draft", "/onboarding/skip",
    "/history", "/sessions", "/sessions/{session_id}",
    "/sessions/{session_id}/activate", "/chat", "/interrupt",
    "/voice/ws", "/audio", "/voice/transcript", "/discord/chat", "/discord/audio",
    "/webhook/donation",
    "/status", "/dream/run", "/dream/wake", "/skills", "/skills/{name}/toggle",
    "/skills/logs", "/events", "/events/stream", "/overview", "/health",
    "/plan", "/plan/directive", "/plan/objectives",
    "/plan/objectives/{objective_id}", "/plan/order", "/plan/reset",
    "/memory/save", "/memory/overview", "/memory/people", "/memory/roster",
    "/memory/self", "/memory/search",
    "/test/llm", "/test/tts", "/test/obs", "/test/vts", "/vts/model",
    "/stage", "/stage/config", "/stage/model", "/stage/clips",
    "/stage/clips/{name}", "/stage/stream", "/stage/preview",
    "/update", "/update/check", "/update/apply", "/update/run",
    "/update/reviews", "/update/reviews/{name}",
    "/doctor", "/doctor/run",
    "/{full_path:path}",
    # fastapi's own
    "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
}


def flatten(routes, out: Optional[List[Any]] = None) -> List[Any]:
    """Every leaf route, in the order starlette will try them.

    Recent fastapi wraps an included router rather than splicing its routes into
    the app, so `app.routes` is a tree and matching order is a walk of it.
    """
    out = [] if out is None else out
    for route in routes:
        inner = getattr(route, "original_router", None)
        sub = getattr(inner, "routes", None)
        if sub is None and isinstance(route, APIRouter):
            sub = route.routes
        if sub:
            flatten(sub, out)
        else:
            out.append(route)
    return out


@pytest.fixture(scope="module")
def leaves() -> List[Any]:
    """Routes that answer a url. A Mount is a subtree, not an endpoint."""
    return [r for r in flatten(app.routes) if type(r).__name__ != "Mount"]


def concrete(path: str) -> str:
    return re.sub(r"\{(\w+)(?::[^}]+)?\}", lambda m: SAMPLES.get(m.group(1), "x"), path)


# --- everything is still there ----------------------------------------------


def test_every_endpoint_is_registered(leaves):
    assert {r.path for r in leaves} == EXPECTED_PATHS


def test_every_router_in_the_index_is_mounted(leaves):
    registered = {r.path for r in leaves}
    for router in routers.ALL:
        paths = {getattr(r, "path", None) for r in router.routes}
        assert paths, "a router with no routes is a module that was never wired up"
        assert paths <= registered


def test_no_two_endpoints_answer_to_the_same_name(leaves):
    # two handlers sharing a name means one module was copied from another and
    # the paths would be impossible to tell apart in a log
    names = [r.name for r in leaves if r.name != "catch_all"]
    assert len(names) == len(set(names)), sorted(
        n for n in names if names.count(n) > 1
    )


# --- and nothing sits in front of anything else -----------------------------


def resolve(leaves: List[Any], method: str, url: str) -> Optional[Any]:
    """The route starlette would pick: first full match wins.

    Typed loosely on purpose: what comes back is an APIRoute, an
    APIWebSocketRoute or a plain Route, and only `.name` and `.path` are read.
    """
    scope = {
        "type": "http", "method": method, "path": url, "path_params": {},
        "root_path": "", "headers": [], "query_string": b"",
    }
    for route in leaves:
        try:
            match, _ = route.matches(scope)
        except Exception:
            continue
        if match.name == "FULL":
            return route
    return None


def test_no_endpoint_is_shadowed_by_an_earlier_one(leaves):
    """The failure the split could cause, and the only one order can cause."""
    shadowed = []
    for target in leaves:
        if target.name == "catch_all" or "WebSocket" in type(target).__name__:
            continue
        for method in sorted(getattr(target, "methods", None) or ["GET"]):
            winner = resolve(leaves, method, concrete(target.path))
            if winner is not target:
                shadowed.append(
                    f"{method} {concrete(target.path)} belongs to {target.name}, "
                    f"answered by {getattr(winner, 'name', None)}"
                )
    assert not shadowed, "\n".join(shadowed)


def test_the_spa_catch_all_is_the_very_last_route(leaves):
    """It answers every GET registered after it, so nothing may be."""
    assert leaves[-1].path == "/{full_path:path}"


def test_an_unknown_path_falls_through_to_the_dashboard(leaves):
    found = resolve(leaves, "GET", "/some/page/the/spa/owns")
    assert found is not None
    assert found.name == "catch_all"


@pytest.mark.parametrize("method,url,expected", [
    ("GET", "/settings", "get_settings"),
    ("GET", "/settings/discord", "get_settings_section"),
    ("GET", "/stage", "stage_page"),
    ("GET", "/stage/clips", "stage_clips"),
    ("GET", "/stage/clips/wave", "stage_clip"),
    ("GET", "/skills/logs", "get_skill_logs"),
    ("POST", "/skills/telegram/toggle", "toggle_skill"),
    ("GET", "/memory/search", "memory_search"),
    ("POST", "/memory/save", "save_memory"),
    ("GET", "/update/reviews", "list_reviews"),
    ("GET", "/update/reviews/soul.md", "read_review"),
])
def test_the_paths_that_could_have_swallowed_each_other(leaves, method, url, expected):
    """The literal-vs-parameter pairs, named one by one."""
    found = resolve(leaves, method, url)
    assert found is not None, f"{method} {url} reaches nothing at all"
    assert found.name == expected


# --- the brain the routers depend on ----------------------------------------


def test_without_a_brain_every_endpoint_answers_503():
    from fastapi.testclient import TestClient

    from src.web import deps

    previous = deps.brain_instance
    deps.brain_instance = None
    try:
        api = TestClient(app)
        assert api.get("/config").status_code == 503
        assert api.get("/status").status_code == 503
        assert api.get("/plan").status_code == 503
    finally:
        deps.brain_instance = previous


def test_health_answers_without_a_brain():
    """It is the endpoint you call precisely when you suspect there is none."""
    from fastapi.testclient import TestClient

    from src.web import deps

    previous = deps.brain_instance
    deps.brain_instance = None
    try:
        answer = TestClient(app).get("/health")
        assert answer.status_code == 200
        assert answer.json() == {"status": "ok", "brain": False}
    finally:
        deps.brain_instance = previous


def test_the_server_hands_the_brain_over_through_deps():
    # `run_server` sets it, and every router reads it from the same place
    from src.web import deps

    previous = deps.brain_instance
    try:
        sentinel = cast(AIVtuberBrain, SimpleNamespace(name="a brain"))
        deps.set_brain(sentinel)
        assert deps.current_brain() is sentinel
        assert deps.get_brain() is sentinel
    finally:
        deps.set_brain(previous)

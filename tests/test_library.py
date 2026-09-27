"""The model library: listing, fetching, uploading, choosing and deleting models.

Every model here is a tiny GLB built in the test; nothing reaches the network.
"""

import asyncio
import threading
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.core.config import BrainConfig
from src.core.stage import StageChannel
from src.modules.avatar import catalog, library
from tests.glb import PNG, glb, vrm1, vrma


def config(tmp_path, **stage):
    cfg = BrainConfig()
    cfg.stage = {**cfg.stage, "models_dir": str(tmp_path / "models"), "clips_dir": str(tmp_path / "clips"),
                 "model_path": "", **stage}
    (tmp_path / "models").mkdir(exist_ok=True)
    (tmp_path / "clips").mkdir(exist_ok=True)
    return cfg


# --- the module -----------------------------------------------------------------


def test_models_are_listed_with_what_they_say_about_themselves(tmp_path):
    cfg = config(tmp_path)
    vrm1(tmp_path / "models" / "bea.vrm", name="Bea")
    vrm1(tmp_path / "models" / "mute.vrm", presets=("happy",))
    cfg.stage["model_path"] = str(tmp_path / "models" / "bea.vrm")

    models = {m["id"]: m for m in library.list_models(cfg)}
    assert set(models) == {"bea.vrm", "mute.vrm"}
    assert models["bea.vrm"]["active"] and not models["mute.vrm"]["active"]
    assert models["bea.vrm"]["name"] == "Bea" and models["bea.vrm"]["vrm"] == "1.0"
    assert any("'aa'" in w for w in models["mute.vrm"]["warnings"])


def test_a_model_outside_the_folder_is_listed_as_external(tmp_path):
    elsewhere = vrm1(tmp_path / "mine.vrm")
    cfg = config(tmp_path, model_path=str(elsewhere))
    [entry] = library.list_models(cfg)
    assert entry["id"] == library.EXTERNAL and entry["external"] and entry["active"]
    assert library.resolve_model(cfg, library.EXTERNAL) == elsewhere.resolve()


def test_a_file_that_is_not_a_vrm_is_listed_with_why(tmp_path):
    cfg = config(tmp_path)
    (tmp_path / "models" / "broken.vrm").write_bytes(b"not a model")
    [entry] = library.list_models(cfg)
    assert entry["vrm"] is None and entry["warnings"]


def test_the_page_can_only_name_what_was_listed(tmp_path):
    cfg = config(tmp_path)
    vrm1(tmp_path / "models" / "bea.vrm")
    (tmp_path / "secret.vrm").write_bytes(b"x")
    for name in ("../secret.vrm", "/etc/passwd", "bea", "..", "", "sub/bea.vrm"):
        assert library.resolve_model(cfg, name) is None, name
    assert library.resolve_model(cfg, "bea.vrm") == (tmp_path / "models" / "bea.vrm").resolve()


def test_the_description_is_read_once_per_version_of_the_file(tmp_path, monkeypatch):
    path = vrm1(tmp_path / "bea.vrm")
    calls = []
    real = library.describe
    monkeypatch.setattr(library, "describe", lambda p: calls.append(p) or real(p))
    library.described(path)
    library.described(path)
    assert len(calls) == 1
    vrm1(path, name="Changed")
    import os
    os.utime(path, (1, 1))
    assert library.described(path)["title"] == "Changed"
    assert len(calls) == 2


def test_the_model_on_stage_cannot_be_deleted(tmp_path):
    cfg = config(tmp_path)
    vrm1(tmp_path / "models" / "bea.vrm")
    vrm1(tmp_path / "models" / "old.vrm")
    cfg.stage["model_path"] = str(tmp_path / "models" / "bea.vrm")

    with pytest.raises(PermissionError):
        library.delete_model(cfg, "bea.vrm")
    with pytest.raises(PermissionError):
        library.delete_model(cfg, library.EXTERNAL)
    library.delete_model(cfg, "old.vrm")
    assert not (tmp_path / "models" / "old.vrm").exists()
    assert (tmp_path / "models" / "bea.vrm").exists()


def test_clips_are_listed_with_their_role_and_length(tmp_path):
    cfg = config(tmp_path, idle_clip="idle_loop")
    vrma(tmp_path / "clips" / "idle_loop.vrma")
    doc = {"asset": {"version": "2.0"}, "accessors": [{"max": [2.5]}],
           "animations": [{"samplers": [{"input": 0}]}],
           "extensions": {"VRMC_vrm_animation": {"humanoid": {"humanBones": {"head": {}, "neck": {}}},
                                                 "lookAt": {}}}}
    (tmp_path / "clips" / "wave.vrma").write_bytes(glb(doc))

    clips = {c["name"]: c for c in library.list_clips(cfg)}
    assert clips["idle_loop"]["role"] == "base" and clips["wave"]["role"] == "gesture"
    assert clips["wave"]["duration"] == 2.5 and clips["wave"]["bones"] == 2 and clips["wave"]["drives_gaze"]


def test_the_catalog_says_what_is_already_installed(tmp_path):
    cfg = config(tmp_path)
    asset = catalog.find("idle-loop")
    (tmp_path / "clips" / asset.filename).write_bytes(b"\0" * asset.size)
    entries = {e["id"]: e for e in library.list_catalog(cfg, library.Downloads())}
    assert entries["idle-loop"]["installed"]
    assert not entries["avatar-sample-b"]["installed"]
    assert entries["seed-san"]["credit"]


def test_a_download_runs_on_its_own_thread_and_only_once_at_a_time(tmp_path):
    release = threading.Event()
    seen = []

    def slow_fetch(asset, into, progress=None):
        seen.append(threading.current_thread().name)
        progress(5, 10)
        release.wait(2)
        return into / asset.filename

    downloads = library.Downloads()
    asset = catalog.find("seed-san")
    started = time.perf_counter()
    assert downloads.start(asset, tmp_path, fetch=slow_fetch)
    assert time.perf_counter() - started < 0.05, "starting a download waited on it"
    assert not downloads.start(asset, tmp_path, fetch=slow_fetch), "a second download of the same file started"
    deadline = time.monotonic() + 1
    while downloads.snapshot()["seed-san"]["written"] != 5 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert downloads.snapshot()["seed-san"] == {"state": "running", "written": 5, "total": 10, "error": ""}
    release.set()
    while downloads.snapshot()["seed-san"]["state"] == "running" and time.monotonic() < deadline + 1:
        time.sleep(0.01)
    assert downloads.snapshot()["seed-san"]["state"] == "done"
    assert seen and seen[0] != threading.main_thread().name


def test_a_failed_download_says_why(tmp_path):
    def broken(asset, into, progress=None):
        raise catalog.FetchError("checksum mismatch")

    downloads = library.Downloads()
    downloads.start(catalog.find("seed-san"), tmp_path, fetch=broken)
    deadline = time.monotonic() + 1
    while downloads.snapshot()["seed-san"]["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert downloads.snapshot()["seed-san"]["state"] == "failed"
    assert "checksum" in downloads.snapshot()["seed-san"]["error"]


def test_an_upload_is_checked_before_it_takes_a_name(tmp_path):
    folder = tmp_path / "models"
    with pytest.raises(ValueError):
        library.save_upload([b"PK not a model"], "fake.vrm", folder, "model")
    with pytest.raises(ValueError, match="not a VRM"):
        library.save_upload([glb({"asset": {"version": "2.0"}})], "cube.vrm", folder, "model")
    assert list(folder.iterdir()) == [], "a rejected upload left a file behind"

    good = (tmp_path / "src.vrm")
    vrm1(good)
    data = good.read_bytes()
    saved = library.save_upload([data[:100], data[100:]], "../../Bea Model.vrm", folder, "model")
    assert saved == folder / "Bea Model.vrm" and saved.read_bytes() == data


def test_an_upload_never_replaces_a_file(tmp_path):
    folder = tmp_path / "models"
    good = vrm1(tmp_path / "src.vrm").read_bytes()
    library.save_upload([good], "bea.vrm", folder, "model")
    with pytest.raises(FileExistsError):
        library.save_upload([b"other"], "bea.vrm", folder, "model")
    assert (folder / "bea.vrm").read_bytes() == good


def test_an_upload_over_the_limit_is_refused_and_leaves_nothing(tmp_path):
    folder = tmp_path / "models"
    with pytest.raises(ValueError, match="over"):
        library.save_upload([b"x" * 10, b"x" * 10], "big.vrm", folder, "model", limit=15)
    assert list(folder.iterdir()) == []


def test_names_are_made_safe_or_refused():
    assert library.safe_name("../../evil.vrm", ".vrm") == "evil.vrm"
    assert library.safe_name("bea.vrm.exe", ".vrm") == ""
    assert library.safe_name(".vrm", ".vrm") == ""
    assert library.safe_name("C:\\Users\\x\\bea.vrm", ".vrm").endswith(".vrm")


# --- the router ---------------------------------------------------------------


class BrainStub:
    def __init__(self, cfg):
        self.config = cfg
        self.stage = StageChannel()
        self.stage_reloads = 0
        self.full_reloads = 0

    def reload_stage(self):
        self.stage_reloads += 1

    def reload_configuration(self):
        self.full_reloads += 1
        raise AssertionError("choosing a model reloaded the llm, the voice and the ears")


@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.web import app as web
    from src.web import deps

    monkeypatch.chdir(tmp_path)
    cfg = config(tmp_path)
    stub = BrainStub(cfg)
    previous = deps.brain_instance
    deps.brain_instance = stub
    try:
        yield TestClient(web.app), stub, tmp_path
    finally:
        deps.brain_instance = previous


def test_choosing_a_model_rebuilds_the_stage_and_nothing_else(api):
    client, stub, tmp_path = api
    vrm1(tmp_path / "models" / "bea.vrm")

    response = client.post("/stage/library/select", json={"id": "bea.vrm"})

    assert response.status_code == 200
    assert stub.stage_reloads == 1 and stub.full_reloads == 0
    assert Path(stub.config.stage["model_path"]) == (tmp_path / "models" / "bea.vrm").resolve()
    import json
    saved = json.loads((tmp_path / "config.json").read_text())
    assert Path(saved["stage"]["model_path"]) == (tmp_path / "models" / "bea.vrm").resolve()


def test_choosing_a_model_that_was_not_listed_changes_nothing(api):
    client, stub, _ = api
    assert client.post("/stage/library/select", json={"id": "../../etc/passwd"}).status_code == 404
    assert stub.stage_reloads == 0 and stub.config.stage["model_path"] == ""


def test_the_thumbnail_is_the_models_own_picture(api):
    client, _, tmp_path = api
    vrm1(tmp_path / "models" / "bea.vrm")
    response = client.get("/stage/library/models/bea.vrm/thumbnail")
    assert response.status_code == 200 and response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert client.get("/stage/library/models/nope.vrm/thumbnail").status_code == 404


def test_the_route_refuses_a_name_that_walks_out(api):
    from src.web.routers import library as route

    _, stub, tmp_path = api
    (tmp_path / "secret.vrm").write_bytes(b"x")
    for name in ("../secret.vrm", "/etc/passwd"):
        with pytest.raises(HTTPException) as raised:
            route.library_file(name, brain=stub)
        assert raised.value.status_code == 404


def test_uploading_through_the_route(api):
    client, _, tmp_path = api
    data = vrm1(tmp_path / "src.vrm").read_bytes()
    assert client.post("/stage/library/models/upload?name=new.vrm", content=data).status_code == 201
    assert (tmp_path / "models" / "new.vrm").read_bytes() == data
    assert client.post("/stage/library/models/upload?name=new.vrm", content=data).status_code == 409
    assert client.post("/stage/library/models/upload?name=x.vrm", content=b"junk").status_code == 422
    assert client.post("/stage/library/clips/upload?name=wave.vrma",
                       content=vrma(tmp_path / "w.vrma").read_bytes()).status_code == 201
    assert (tmp_path / "clips" / "wave.vrma").is_file()


def test_the_overview_lists_models_catalog_and_clips(api):
    client, _, tmp_path = api
    vrm1(tmp_path / "models" / "bea.vrm")
    body = client.get("/stage/library").json()
    assert [m["id"] for m in body["models"]] == ["bea.vrm"]
    assert {c["id"] for c in body["catalog"]} == {a.id for a in catalog.CATALOG}
    assert body["clips"] == []


def test_deleting_through_the_route(api):
    client, stub, tmp_path = api
    vrm1(tmp_path / "models" / "bea.vrm")
    vrm1(tmp_path / "models" / "old.vrm")
    stub.config.stage["model_path"] = str(tmp_path / "models" / "bea.vrm")
    assert client.delete("/stage/library/models/bea.vrm").status_code == 409
    assert client.delete("/stage/library/models/old.vrm").status_code == 200
    assert client.delete("/stage/library/models/old.vrm").status_code == 404


def test_every_mood_has_weights_for_the_preview(api):
    client, _, _ = api
    from src.core.mind.moods import MOODS
    assert set(client.get("/stage/moods").json()) == set(MOODS)


async def test_a_slow_download_does_not_hold_the_loop(api, monkeypatch):
    """The download endpoint is a sync handler that only starts a thread."""
    from src.web.routers import library as route

    _, stub, tmp_path = api
    release = threading.Event()
    monkeypatch.setattr(route.DOWNLOADS, "start",
                        lambda asset, into: threading.Thread(target=release.wait, args=(2,), daemon=True).start() or True)
    started = time.perf_counter()
    await asyncio.to_thread(route.library_download, route.Pick(id="seed-san"), stub)
    assert time.perf_counter() - started < 0.1
    release.set()

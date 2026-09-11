"""What `bea --doctor` is for: being told what is broken and what to type.

The thing being tested is not really the individual checks — it is the shape of
the answer. A check that says "TTS error" and stops is worth nothing; a check
that says which engine, why, and the one command that fixes it is the whole
difference between a project people use and one they abandon at the first red
line.
"""



from src.core.config import BrainConfig
from src.setup import doctor
from src.setup.doctor import (
    CHECKS,
    check_config,
    check_dashboard,
    check_discord,
    check_keys,
    check_manual,
    check_python,
    check_stage,
    diagnose,
    failed,
    passed,
    warned,
)


def config(**kwargs) -> BrainConfig:
    settings = BrainConfig()
    for key, value in kwargs.items():
        setattr(settings, key, value)
    return settings


# --- what a finding is --------------------------------------------------------


def test_a_pass_stops_nothing():
    assert not passed("fine").stops


def test_a_blocking_failure_stops_the_run():
    assert failed("no key").stops


def test_a_warning_does_not():
    """Her Twitch channel being unset is not a reason to stop testing her voice."""
    assert not warned("no twitch channel").stops


def test_a_failure_carries_what_to_do_about_it():
    """The whole point. A red line with no fix under it is a log entry."""
    assert failed("no key", "uv run bea --setup").fix


# --- the order they run in ----------------------------------------------------


async def report_of(*findings):
    """Runs a made-up sequence of checks and returns what came back."""
    seen = []

    async def run(settings):
        return findings[len(seen)]

    original = list(CHECKS)
    CHECKS[:] = [(f"check {i}", run) for i in range(len(findings))]
    try:
        return await diagnose(config(), report=lambda title, f: seen.append(title))
    finally:
        CHECKS[:] = original


async def test_it_stops_at_the_first_thing_in_the_way():
    """A page of red is a page nobody reads, and the rest of it is caused."""
    found = await report_of(passed(), failed("no config"), passed())
    assert [f.ok for _title, f in found] == [True, False]


async def test_a_warning_is_not_in_the_way():
    found = await report_of(warned("no .env"), passed(), passed())
    assert len(found) == 3


async def test_every_check_is_reported_as_it_lands():
    """Twenty seconds of nothing on screen reads as a hang."""
    seen = []

    async def slow(settings):
        return passed()

    original = list(CHECKS)
    CHECKS[:] = [("one", slow), ("two", slow)]
    try:
        await diagnose(config(), report=lambda title, f: seen.append(title))
    finally:
        CHECKS[:] = original
    assert seen == ["one", "two"]


async def test_a_check_that_falls_over_is_a_finding_and_not_a_crash():
    """The check after it may be the one that explains why."""
    async def explodes(settings):
        raise RuntimeError("something unexpected")

    original = list(CHECKS)
    CHECKS[:] = [("boom", explodes), ("after", lambda s: _ok())]
    try:
        found = await diagnose(config())
    finally:
        CHECKS[:] = original

    assert len(found) == 2
    assert "could not run" in found[0][1].detail


async def _ok():
    return passed()


# --- the checks themselves ----------------------------------------------------


async def test_the_python_it_is_running_on_is_the_one_it_reports():
    import sys

    found = await check_python(config())
    assert f"{sys.version_info.major}.{sys.version_info.minor}" in found.detail


async def test_a_missing_config_file_says_which_command_writes_one(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.config_module, "CONFIG_FILE", str(tmp_path / "nope.json"))
    found = await check_config(config())

    assert found.stops
    assert "--setup" in found.fix


async def test_a_missing_env_file_is_a_warning_and_not_a_wall(monkeypatch, tmp_path):
    """Keys can perfectly well come from the environment."""
    settings = tmp_path / "config.json"
    settings.write_text("{}")
    monkeypatch.setattr(doctor.config_module, "CONFIG_FILE", str(settings))
    monkeypatch.setattr(doctor, "ENV_FILE", tmp_path / "nope.env")

    found = await check_config(config())
    assert not found.ok and not found.stops


async def test_a_pool_naming_a_provider_with_no_key_names_the_variable(monkeypatch):
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = config(models={"mind": ["groq:a/model"], "background": []},
                      groq_key=None, openrouter_key=None, openai_key=None)

    found = await check_keys(settings)
    assert found.stops
    assert "GROQ_API_KEY" in found.fix


async def test_a_pool_whose_keys_are_all_there_passes():
    settings = config(models={"mind": ["groq:a/model"], "background": []}, groq_key="k")
    assert (await check_keys(settings)).ok


async def test_the_provider_is_checked_when_no_pool_names_one(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = config(models={"mind": [], "background": []},
                      llm_provider="openrouter", openrouter_key=None)

    found = await check_keys(settings)
    assert "openrouter" in found.detail


# --- the manual, which is a file people edit ---------------------------------


async def test_a_manual_that_stopped_naming_her_tools_is_in_the_way(tmp_path):
    manual = tmp_path / "operating.md"
    manual.write_text("Be funny. Say things.", encoding="utf-8")

    found = await check_manual(config(operating_prompt_path=str(manual),
                                      system_prompt_path=str(manual)))
    assert found.stops
    assert "speak" in found.detail


async def test_a_manual_that_lost_the_direction_is_only_a_warning(tmp_path):
    """She still talks; her face just stops changing part-way through a line."""
    manual = tmp_path / "operating.md"
    manual.write_text("Call speak to talk, or stay_silent.", encoding="utf-8")

    found = await check_manual(config(operating_prompt_path=str(manual),
                                      system_prompt_path=str(manual)))
    assert not found.ok and not found.stops


async def test_the_manual_that_ships_passes_its_own_check():
    assert (await check_manual(BrainConfig())).ok


# --- her body -----------------------------------------------------------------


async def test_a_3d_body_with_no_model_says_how_to_get_one():
    found = await check_stage(config(stage={"avatar_backend": "model", "model_path": ""}))
    assert found.stops
    assert "make model" in found.fix


async def test_a_model_path_that_is_not_on_disk_is_named(tmp_path):
    missing = str(tmp_path / "her.vrm")
    found = await check_stage(config(stage={"avatar_backend": "model",
                                            "model_path": missing}))
    assert found.stops and missing in found.detail


async def test_a_3d_body_that_is_there_counts_what_it_can_do(tmp_path):
    model = tmp_path / "her.vrm"
    model.write_bytes(b"not really a vrm, but it is on disk")
    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "wave.vrma").write_bytes(b"")

    found = await check_stage(config(stage={"avatar_backend": "model",
                                            "model_path": str(model),
                                            "clips_dir": str(clips)}))
    assert found.ok and "1 behaviour" in found.detail


async def test_an_avatar_image_that_was_moved_is_named(tmp_path):
    found = await check_stage(config(
        stage={"avatar_backend": "png"},
        avatar_map={"happy": {"idle": str(tmp_path / "gone.png"), "talking": ""}},
    ))
    assert found.stops and "happy/idle" in found.detail


async def test_avatar_slots_nobody_filled_in_are_not_a_failure():
    """An empty slot is "she has no picture for that", not a broken path."""
    found = await check_stage(config(
        stage={"avatar_backend": "png"},
        avatar_map={"happy": {"idle": "", "talking": ""}},
    ))
    assert found.ok


async def test_vtube_studio_that_is_not_running_says_where_to_turn_it_on(monkeypatch):
    monkeypatch.setattr(doctor, "_reachable", lambda *a, **k: False)
    found = await check_stage(config(stage={"avatar_backend": "vtube_studio",
                                            "vts_host": "127.0.0.1", "vts_port": 8001}))
    assert found.stops
    assert "plugin api" in found.fix.lower()


# --- the dashboard ------------------------------------------------------------


async def test_an_unbuilt_dashboard_is_fatal_when_her_stage_needs_it(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "DASHBOARD", tmp_path / "never-built.html")
    found = await check_dashboard(config(stage={"avatar_backend": "model",
                                                "caption_backend": "obs"}))
    assert found.stops and found.fix == "make frontend"


async def test_an_unbuilt_dashboard_is_only_a_warning_otherwise(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "DASHBOARD", tmp_path / "never-built.html")
    found = await check_dashboard(config(stage={"avatar_backend": "png",
                                                "caption_backend": "obs"}))
    assert not found.ok and not found.stops


# --- the exit code a script would read ---------------------------------------


class Quiet:
    def print(self, *a, **k):
        pass

    def rule(self, *a, **k):
        pass


def test_everything_passing_exits_zero():
    assert doctor._verdict(Quiet(), [("one", passed()), ("two", passed())]) == 0


def test_a_warning_still_exits_zero():
    """She runs. Something is worse than it could be, which is not a failure."""
    assert doctor._verdict(Quiet(), [("one", warned("no ears"))]) == 0


def test_something_in_the_way_exits_one():
    assert doctor._verdict(Quiet(), [("one", failed("no key"))]) == 1


# --- the one part of her that is not python ----------------------------------


async def test_a_discord_skill_nobody_turned_on_is_not_a_problem():
    assert (await check_discord(config(skills={"discord": {"enabled": False}}))).ok


async def test_the_bot_cannot_log_in_without_a_token(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    found = await check_discord(config(skills={"discord": {"enabled": True}}))

    assert not found.ok
    assert "DISCORD_TOKEN" in found.fix
    # her voice goes quiet; everything else about her still works
    assert not found.blocking


async def test_a_machine_without_node_is_told_so_and_told_what_to_install(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    found = await check_discord(config(skills={"discord": {"enabled": True}}))

    assert not found.ok
    assert "node" in found.detail
    assert "npm ci" in found.fix


async def test_packages_that_were_never_installed_are_named(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.chdir(tmp_path)  # no bot/node_modules anywhere here
    found = await check_discord(config(skills={"discord": {"enabled": True}}))

    assert not found.ok
    assert "npm ci" in found.fix

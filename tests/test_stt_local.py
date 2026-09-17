"""Local whisper: the model id it ends up asking for, the precision it picks,
and the promise that a model it could not load degrades instead of crashing."""

import sys
import time
from types import SimpleNamespace

import pytest

from src.core.config import BrainConfig
from src.modules.STT.factory import BUILDERS, LOCAL, build_stt
from src.modules.STT.faster_whisper_stt import (
    DEFAULT_MODEL,
    FasterWhisperSTT,
    device_advice,
    normalize_language,
    normalize_model,
)


def config(tmp_path, monkeypatch, **overrides) -> BrainConfig:
    monkeypatch.chdir(tmp_path)
    settings = BrainConfig()
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


@pytest.fixture
def loaded(monkeypatch):
    """Records what WhisperModel was asked for, without loading anything."""
    calls = []

    class FakeModel:
        def __init__(self, name, device=None, compute_type=None, download_root=None,
                     **kwargs):
            calls.append({"name": name, "device": device,
                          "compute_type": compute_type, "download_root": download_root,
                          **kwargs})

        def transcribe(self, path, **kwargs):
            calls.append({"path": path, **kwargs})
            return ([], None)

    import faster_whisper
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    return calls


# --- model ids -------------------------------------------------------------


def test_an_empty_model_falls_back_to_one_that_exists():
    assert normalize_model("") == DEFAULT_MODEL
    assert normalize_model(None) == DEFAULT_MODEL


def test_a_hosted_spelling_becomes_the_local_one():
    """config.json ships the groq id, and switching provider must not break it."""
    assert normalize_model("whisper-large-v3-turbo") == "large-v3-turbo"
    assert normalize_model("openai/whisper-large-v3-turbo") == "large-v3-turbo"


def test_a_real_huggingface_repo_is_left_alone():
    assert normalize_model("Systran/faster-distil-whisper-large-v3") == \
        "Systran/faster-distil-whisper-large-v3"


def test_a_size_it_already_knows_passes_through():
    assert normalize_model("small") == "small"


# --- languages -------------------------------------------------------------


def test_the_dashboards_own_japanese_is_translated_for_whisper():
    """The language picker offers `jp`, which whisper would refuse outright."""
    assert normalize_language("jp") == "ja"


def test_a_language_whisper_does_not_know_becomes_detection():
    assert normalize_language("klingon") is None
    assert normalize_language("") is None


# --- how it runs -----------------------------------------------------------


def test_auto_means_int8_on_a_cpu_and_float16_on_a_gpu(tmp_path, monkeypatch, loaded):
    FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base"))
    # model constructions only: the boot probe transcribes, it never rebuilds
    builds = [call for call in loaded if "name" in call]
    assert builds[0]["compute_type"] == "int8"

    FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base",
                            faster_whisper_device="cuda"))
    builds = [call for call in loaded if "name" in call]
    assert builds[1]["compute_type"] == "float16"


def test_a_chosen_precision_is_not_second_guessed(tmp_path, monkeypatch, loaded):
    FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base",
                            faster_whisper_compute_type="float32"))
    assert loaded[0]["compute_type"] == "float32"


def test_the_weights_go_where_the_config_says(tmp_path, monkeypatch, loaded):
    FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base"))
    assert loaded[0]["download_root"] == "data/models/whisper"
    assert (tmp_path / "data" / "models" / "whisper").is_dir()


# --- degrading -------------------------------------------------------------


def test_a_model_that_will_not_load_does_not_take_the_engine_down(tmp_path, monkeypatch):
    import faster_whisper

    def explode(*args, **kwargs):
        raise RuntimeError("no such model")

    monkeypatch.setattr(faster_whisper, "WhisperModel", explode)
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="nonsense"))
    assert stt.model is None
    assert stt.transcribe("whatever.wav") == ""


def test_audio_that_is_not_there_is_an_empty_transcript(tmp_path, monkeypatch, loaded):
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base"))
    assert stt.transcribe(str(tmp_path / "gone.wav")) == ""


# --- the device it actually runs on -----------------------------------------


def test_auto_is_resolved_to_something_concrete(tmp_path, monkeypatch, loaded):
    """`auto` used to reach ctranslate2 unresolved, with the cpu precision."""
    monkeypatch.delenv("BEA_PERF", raising=False)
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base"))
    assert stt.device in ("cpu", "cuda")
    assert loaded[0]["device"] == stt.device


def test_auto_means_cuda_when_there_is_one(tmp_path, monkeypatch, loaded):
    import src.modules.STT.faster_whisper_stt as stt_module

    monkeypatch.delenv("BEA_PERF", raising=False)
    monkeypatch.setattr(stt_module, "_cuda_count", lambda: 2)
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base"))
    assert stt.device == "cuda"
    assert loaded[0]["compute_type"] == "float16"


def test_a_gpu_that_vanishes_at_load_time_falls_back_to_cpu(tmp_path, monkeypatch):
    """Old drivers, a container without the device: ears over precision."""
    import faster_whisper

    seen = []

    class FlakyModel:
        def __init__(self, name, device=None, **kwargs):
            seen.append(device)
            if device == "cuda":
                raise RuntimeError("CUDA failed to initialize")

        def transcribe(self, path, **kwargs):
            return ([], None)

    monkeypatch.setattr(faster_whisper, "WhisperModel", FlakyModel)
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base",
                                  faster_whisper_device="cuda"))
    assert stt.model is not None
    assert (stt.device, stt.compute_type) == ("cpu", "int8")
    assert seen == ["cuda", "cpu"]


def test_the_pool_is_sized_for_the_cores_that_exist(tmp_path, monkeypatch, loaded):
    from src.core.perf import physical_cores

    monkeypatch.delenv("BEA_PERF", raising=False)
    FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base"))
    assert loaded[0]["cpu_threads"] == physical_cores()
    assert loaded[0]["num_workers"] == 1


def test_perf_off_restores_the_old_behaviour(tmp_path, monkeypatch, loaded):
    """The switch: raw values through, default pools, no probing."""
    import src.modules.STT.faster_whisper_stt as stt_module

    monkeypatch.setenv("BEA_PERF", "off")
    monkeypatch.setattr(stt_module, "_cuda_count",
                        lambda: (_ for _ in ()).throw(AssertionError("must not probe")))
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base"))
    assert (stt.device, stt.compute_type) == ("auto", "int8")
    assert "cpu_threads" not in loaded[0]


# --- reloading -------------------------------------------------------------


def test_an_unrelated_save_does_not_reload_the_model(tmp_path, monkeypatch, loaded):
    """Loading is seconds and possibly a download; a saved OBS port is not."""
    settings = config(tmp_path, monkeypatch, stt_model="base")
    stt = FasterWhisperSTT(settings)
    settings.obs_port = 4456
    stt.reload_config(settings)
    # model constructions only: the boot probe transcribes, it never rebuilds
    assert len([call for call in loaded if "name" in call]) == 1


def test_a_new_model_does_reload(tmp_path, monkeypatch, loaded):
    settings = config(tmp_path, monkeypatch, stt_model="base")
    stt = FasterWhisperSTT(settings)
    settings.stt_model = "small"
    stt.reload_config(settings)
    assert [call["name"] for call in loaded if "name" in call] == ["base", "small"]


# --- the factory -----------------------------------------------------------


def test_the_factory_builds_it(tmp_path, monkeypatch, loaded):
    settings = config(tmp_path, monkeypatch, stt_provider="faster_whisper", stt_model="base")
    assert isinstance(build_stt(settings), FasterWhisperSTT)


def test_every_local_provider_is_one_the_factory_can_build():
    assert LOCAL <= set(BUILDERS)


# --- a download that failed -------------------------------------------------


def test_the_hint_reaches_the_log_when_the_download_is_refused(tmp_path, monkeypatch, caplog):
    """`401` means nothing to someone who never knew an account was involved."""
    import faster_whisper

    from src.utils.huggingface import TOKEN_HINT

    def refused(*args, **kwargs):
        raise OSError("401 Client Error: Unauthorized")

    monkeypatch.setattr(faster_whisper, "WhisperModel", refused)
    with caplog.at_level("ERROR"):
        FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base"))
    assert TOKEN_HINT in caplog.text


# --- a device that loads but cannot hear --------------------------------------


def _said(text):
    return ([SimpleNamespace(text=text)], None)


class CudaDeafModel:
    """Loads anywhere, transcribes only on cpu: the missing-cuBLAS machine."""

    def __init__(self, name, device=None, **kwargs):
        self.device = device

    def transcribe(self, path, **kwargs):
        if self.device == "cuda":
            raise RuntimeError("Library cublas64_12.dll is not found")
        return _said("ciao")


def test_the_boot_probe_falls_back_before_anyone_speaks(tmp_path, monkeypatch, caplog):
    """The windows failure: visible gpus, no CUDA libraries, load succeeds."""
    import faster_whisper

    monkeypatch.setattr(faster_whisper, "WhisperModel", CudaDeafModel)
    with caplog.at_level("WARNING"):
        stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base",
                                      faster_whisper_device="cuda"))
    assert (stt.device, stt.compute_type) == ("cpu", "int8")
    assert stt.model is not None
    assert stt.degraded is True
    assert "cublas" in (stt.last_error or "")
    assert "cpu" in caplog.text


def test_a_failed_turn_is_retried_on_cpu_not_dropped(tmp_path, monkeypatch):
    """The probe hears silence fine; the first real turn is what breaks."""

    import faster_whisper

    class FlakyCudaModel:
        def __init__(self, name, device=None, **kwargs):
            self.device = device

        def transcribe(self, path, **kwargs):
            if isinstance(path, str) and self.device == "cuda":
                raise RuntimeError("Library cublas64_12.dll is not found")
            return _said("parola")

    monkeypatch.setattr(faster_whisper, "WhisperModel", FlakyCudaModel)
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base",
                                  faster_whisper_device="cuda"))
    assert stt.degraded is False

    wav = tmp_path / "turn.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 100)
    assert stt.transcribe(str(wav)) == "parola"
    assert (stt.device, stt.compute_type) == ("cpu", "int8")
    assert stt.degraded is True


def test_a_cpu_that_cannot_hear_says_so(tmp_path, monkeypatch):
    """No retry loop: on cpu a failure is a failure, recorded honestly."""
    import faster_whisper

    class DeafModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, **kwargs):
            raise RuntimeError("no backend at all")

    monkeypatch.setattr(faster_whisper, "WhisperModel", DeafModel)
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base",
                                  faster_whisper_device="cpu"))
    assert stt.model is None
    assert stt.degraded is True
    assert "no backend" in (stt.last_error or "")

    wav = tmp_path / "turn.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 100)
    assert stt.transcribe(str(wav)) == ""


def test_status_reports_the_device_and_the_fallback(tmp_path, monkeypatch):
    import faster_whisper

    monkeypatch.setattr(faster_whisper, "WhisperModel", CudaDeafModel)
    stt = FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base",
                                  faster_whisper_device="cuda"))
    state = stt.status()
    assert state["provider"] == "faster_whisper"
    assert state["device"] == "cpu"
    assert state["degraded"] is True
    assert state["loaded"] is True
    assert "cublas" in (state["last_error"] or "")


def test_a_fresh_device_gets_a_fresh_verdict(tmp_path, monkeypatch):
    """Switching the device clears the old degradation instead of keeping it."""
    import faster_whisper

    monkeypatch.setattr(faster_whisper, "WhisperModel", CudaDeafModel)
    settings = config(tmp_path, monkeypatch, stt_model="base",
                      faster_whisper_device="cuda")
    stt = FasterWhisperSTT(settings)
    assert stt.degraded is True
    settings.faster_whisper_device = "cpu"
    stt.reload_config(settings)
    assert stt.degraded is False
    assert stt.last_error is None


# --- advice for this machine --------------------------------------------------


def test_the_advice_names_the_platform_problem(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert "CUDA Toolkit" in device_advice()
    monkeypatch.setattr(sys, "platform", "darwin")
    assert "no CUDA" in device_advice()
    monkeypatch.setattr(sys, "platform", "linux")
    assert "nvidia" in device_advice()


def test_the_doctor_names_the_device_fix(tmp_path, monkeypatch):
    from src.setup.doctor import _ears_fix

    fix = _ears_fix(config(tmp_path, monkeypatch, stt_provider="faster_whisper"))
    assert "cpu" in fix.lower()


# --- the weights on disk ----------------------------------------------------


def test_the_weights_are_fetched_into_the_cache_the_engine_reads(monkeypatch):
    """The wizard and the engine must not download into two different layouts.

    `WhisperModel(download_root=…)` passes that folder to faster-whisper as a
    *cache*. The wizard used to fetch with `output_dir`, which lays the same
    files out flat — so a fresh install downloaded 480MB in the wizard and then
    480MB again at her first startup, into a second copy in the same folder.
    """
    import faster_whisper.utils as whisper_utils

    from src.modules.STT.faster_whisper_stt import _download

    asked = {}
    monkeypatch.setattr(whisper_utils, "download_model",
                        lambda model, **kwargs: asked.update(model=model, **kwargs) or "path")

    _download("small", "data/models/whisper")

    assert asked["cache_dir"] == "data/models/whisper"
    assert "output_dir" not in asked, "that is the other layout, and nothing reads it"
    assert "local_dir_use_symlinks" not in asked, "deprecated, and the hub warns about it"


def test_the_probe_asks_for_the_same_folder_it_would_download_into(monkeypatch):
    import faster_whisper.utils as whisper_utils

    from src.modules.STT.faster_whisper_stt import weights_here

    seen = {}

    def offline(model, **kwargs):
        seen.update(model=model, **kwargs)
        return "path"

    monkeypatch.setattr(whisper_utils, "download_model", offline)

    assert weights_here("small", "some/root")
    assert seen == {"model": "small", "cache_dir": "some/root", "local_files_only": True}


def test_weights_that_are_not_there_are_reported_as_missing(tmp_path):
    from src.modules.STT.faster_whisper_stt import weights_here

    def missing(model, root, local_files_only=False):
        raise OSError("not cached")

    assert not weights_here("small", str(tmp_path), downloader=missing)


def test_an_old_flat_copy_of_the_weights_is_counted(tmp_path):
    """So the doctor can say which few hundred megabytes are dead."""
    from src.modules.STT.faster_whisper_stt import stale_weights

    assert stale_weights(str(tmp_path)) == 0
    (tmp_path / "model.bin").write_bytes(b"x" * 100)
    (tmp_path / "config.json").write_bytes(b"y" * 5)
    assert stale_weights(str(tmp_path)) == 105


def test_a_proper_cache_is_not_mistaken_for_an_old_copy(tmp_path):
    from src.modules.STT.faster_whisper_stt import stale_weights

    blobs = tmp_path / "models--Systran--faster-whisper-small" / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "abc123").write_bytes(b"x" * 100)
    assert stale_weights(str(tmp_path)) == 0


# --- saying that the first run is a download --------------------------------


def announced(monkeypatch, here: bool, tmp_path):
    from src.modules.STT import faster_whisper_stt as whisper

    said: list = []
    monkeypatch.setattr(whisper, "weights_here", lambda *a, **k: here)
    with whisper.announce_download("small", str(tmp_path), report=said.append, tick=0.01):
        pass
    return said


def test_the_first_run_says_it_is_downloading_before_the_silence(monkeypatch, tmp_path):
    """Three hundred megabytes with no output is a program that looks hung."""
    said = announced(monkeypatch, here=False, tmp_path=tmp_path)

    assert said and "First run" in said[0]
    assert "480 MB" in said[0]
    assert str(tmp_path) in said[0]


def test_nothing_is_said_when_the_weights_are_already_there(monkeypatch, tmp_path):
    assert announced(monkeypatch, here=True, tmp_path=tmp_path) == []


def test_the_download_notice_never_touches_the_network(monkeypatch, tmp_path):
    """It only watches the folder: the model builder does the downloading."""
    from src.modules.STT import faster_whisper_stt as whisper

    monkeypatch.setattr(whisper, "weights_here", lambda *a, **k: False)
    monkeypatch.setattr(whisper, "fetch_weights",
                        lambda *a, **k: pytest.fail("the notice downloaded something"))
    with whisper.announce_download("small", str(tmp_path), report=lambda line: None,
                                   tick=0.01):
        pass


def test_the_progress_of_the_download_is_reported_as_it_lands(monkeypatch, tmp_path):
    from src.modules.STT import faster_whisper_stt as whisper

    said: list = []
    monkeypatch.setattr(whisper, "weights_here", lambda *a, **k: False)
    monkeypatch.setattr(whisper, "WEIGHTS_MB", {"small": 1})

    with whisper.announce_download("small", str(tmp_path), report=said.append, tick=0.01):
        (tmp_path / "model.bin").write_bytes(b"x" * 600_000)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and len(said) < 2:
            time.sleep(0.01)

    assert any("%" in line for line in said), said

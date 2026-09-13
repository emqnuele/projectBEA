"""Local whisper: the model id it ends up asking for, the precision it picks,
and the promise that a model it could not load degrades instead of crashing."""

import pytest

from src.core.config import BrainConfig
from src.modules.STT.factory import BUILDERS, LOCAL, build_stt
from src.modules.STT.faster_whisper_stt import (
    DEFAULT_MODEL,
    FasterWhisperSTT,
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
        def __init__(self, name, device=None, compute_type=None, download_root=None):
            calls.append({"name": name, "device": device,
                          "compute_type": compute_type, "download_root": download_root})

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
    assert loaded[0]["compute_type"] == "int8"

    FasterWhisperSTT(config(tmp_path, monkeypatch, stt_model="base",
                            faster_whisper_device="cuda"))
    assert loaded[1]["compute_type"] == "float16"


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


# --- reloading -------------------------------------------------------------


def test_an_unrelated_save_does_not_reload_the_model(tmp_path, monkeypatch, loaded):
    """Loading is seconds and possibly a download; a saved OBS port is not."""
    settings = config(tmp_path, monkeypatch, stt_model="base")
    stt = FasterWhisperSTT(settings)
    settings.obs_port = 4456
    stt.reload_config(settings)
    assert len(loaded) == 1


def test_a_new_model_does_reload(tmp_path, monkeypatch, loaded):
    settings = config(tmp_path, monkeypatch, stt_model="base")
    stt = FasterWhisperSTT(settings)
    settings.stt_model = "small"
    stt.reload_config(settings)
    assert [call["name"] for call in loaded] == ["base", "small"]


# --- the factory -----------------------------------------------------------


def test_the_factory_builds_it(tmp_path, monkeypatch, loaded):
    settings = config(tmp_path, monkeypatch, stt_provider="faster_whisper", stt_model="base")
    assert isinstance(build_stt(settings), FasterWhisperSTT)


def test_every_local_provider_is_one_the_factory_can_build():
    assert LOCAL <= set(BUILDERS)

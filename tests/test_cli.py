"""The entrypoint: what it does to the environment, and what wins over what.

Two things had never been pinned down. The first is that importing the module
must not have side effects — the environment setup used to sit between the
imports, so tidying them was a silent regression. The second is the precedence
the whole configuration rests on: a flag on the command line beats config.json,
and config.json beats the default.
"""

import argparse
import dataclasses
import os

import pytest

from src import cli
from src.core.config import BrainConfig


def parsed(*argv) -> argparse.Namespace:
    """The real parser, so the test moves when the flags do."""
    return cli.parse_args(list(argv))


# --- importing is not running -----------------------------------------------


def test_importing_the_cli_touches_nothing(monkeypatch):
    monkeypatch.delenv("TOKENIZERS_PARALLELISM", raising=False)

    import importlib

    importlib.reload(cli)

    assert "TOKENIZERS_PARALLELISM" not in os.environ


def test_bootstrap_sets_the_environment(monkeypatch):
    monkeypatch.delenv("TOKENIZERS_PARALLELISM", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)

    cli.bootstrap()

    assert os.environ["TOKENIZERS_PARALLELISM"] == "false"


def test_bootstrap_never_overwrites_a_deliberate_setting(monkeypatch):
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "true")
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)

    cli.bootstrap()

    assert os.environ["TOKENIZERS_PARALLELISM"] == "true"


def test_bootstrap_leaves_the_same_environment_twice(monkeypatch):
    monkeypatch.delenv("TOKENIZERS_PARALLELISM", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)

    cli.bootstrap()
    first = dict(os.environ)
    cli.bootstrap()

    assert dict(os.environ) == first


# --- cli arg > config.json > default -----------------------------------------


def test_a_flag_that_was_passed_wins():
    config = BrainConfig()
    cli.apply_cli_overrides(config, parsed("--tts-provider", "kokoro"))

    assert config.tts_provider == "kokoro"


def test_a_flag_that_was_not_passed_leaves_the_config_alone():
    config = BrainConfig()
    before = config.tts_provider

    cli.apply_cli_overrides(config, parsed("--web"))

    assert config.tts_provider == before


def test_zero_is_a_value_and_not_an_absence():
    # `--device-id 0` is the first audio device, not "no device given"
    config = BrainConfig()
    config.audio_device_id = 7

    cli.apply_cli_overrides(config, parsed("--device-id", "0"))

    assert config.audio_device_id == 0


def test_an_empty_string_is_a_value_too():
    # clearing the OBS password from the command line has to reach the config
    config = BrainConfig()
    config.obs_password = "hunter2"

    cli.apply_cli_overrides(config, parsed("--obs-password", ""))

    assert config.obs_password == ""


def test_a_flag_that_is_not_a_setting_never_reaches_the_config():
    # --web, --host and --port drive the process, not the persona
    config = BrainConfig()

    cli.apply_cli_overrides(config, parsed("--web", "--host", "0.0.0.0", "--port", "9000"))

    assert not hasattr(config, "web")
    assert not hasattr(config, "host")
    assert not hasattr(config, "port")


def test_the_diverging_flags_land_on_their_real_fields():
    # these four are spelled differently from the field they set, so they are
    # the ones a rename would quietly strand
    config = BrainConfig()

    cli.apply_cli_overrides(config, parsed(
        "--system-file", "prompts/other.md",
        "--kokoro-file", "model.onnx",
        "--kokoro-voices", "voices.bin",
        "--device-id", "3",
    ))

    assert config.system_prompt_path == "prompts/other.md"
    assert config.kokoro_model == "model.onnx"
    assert config.kokoro_voices_file == "voices.bin"
    assert config.audio_device_id == 3


def test_no_flag_overrides_a_field_that_does_not_exist():
    # the pairing is derived, so this is the guard that it stays derivable:
    # every dest that looks like a setting has to actually be one
    fields = {f.name for f in dataclasses.fields(BrainConfig)}
    dests = set(vars(parsed()))
    process_flags = {"setup", "doctor", "update", "no_rebuild", "install_node",
                     "web", "host", "port"}

    assert dests - process_flags <= fields


def test_the_stt_flag_offers_every_transcriber_the_factory_can_build():
    """A backend you can configure but not pass on the command line is a trap."""
    from src.modules.STT.factory import BUILDERS

    for name in BUILDERS:
        assert parsed("--stt-provider", name).stt_provider == name


@pytest.mark.parametrize("flag,value,field", [
    ("--llm-provider", "groq", "llm_provider"),
    ("--stt-provider", "faster_whisper", "stt_provider"),
    ("--obs-port", "4460", "obs_port"),
    ("--typing-delay", "0.5", "typing_delay"),
    ("--png-dir", "somewhere/else", "png_dir"),
])
def test_the_flags_reach_the_fields_they_name(flag, value, field):
    config = BrainConfig()
    cli.apply_cli_overrides(config, parsed(flag, value))

    assert str(getattr(config, field)) == value

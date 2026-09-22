"""The bot calls back where the engine actually is.

`brain_api_url` defaulted to `:8000` whatever `--port` said, so the engine
listened on `:9000` while the bot still called `:8000`. An untouched value now
follows the launch address; a customized one always wins and is never rewritten.
"""

from src import cli
from src.core.config import BrainConfig
from src.core.skills.voice.transport import (
    DEFAULT_BRAIN_API_URL,
    apply_cli_address,
    effective_brain_api_url,
)


def _config(**discord):
    config = BrainConfig()
    config.skills["discord"] = {"api_port": 3030, **discord}
    return config


def test_an_untouched_url_follows_the_port():
    config = _config()
    assert effective_brain_api_url(config, "127.0.0.1", 9000) == "http://127.0.0.1:9000"


def test_an_explicit_default_follows_the_port_too():
    config = _config(brain_api_url=DEFAULT_BRAIN_API_URL)
    assert effective_brain_api_url(config, "127.0.0.1", 9000) == "http://127.0.0.1:9000"


def test_a_customized_url_wins_over_the_flag():
    config = _config(brain_api_url="http://192.168.1.10:8000")
    assert effective_brain_api_url(config, "127.0.0.1", 9000) == "http://192.168.1.10:8000"


def test_a_bind_all_host_is_dialled_back_as_loopback():
    config = _config()
    assert effective_brain_api_url(config, "0.0.0.0", 9000) == "http://127.0.0.1:9000"


def test_applying_points_the_runtime_at_the_launch_without_a_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = _config()
    url = apply_cli_address(config, "127.0.0.1", 9000)
    assert url == "http://127.0.0.1:9000"
    assert config.skills["discord"]["brain_api_url"] == url
    assert not (tmp_path / "config.json").exists()


def test_applying_leaves_a_customized_url_alone():
    config = _config(brain_api_url="http://192.168.1.10:8000")
    assert apply_cli_address(config, "127.0.0.1", 9000) == "http://192.168.1.10:8000"


def test_the_cli_still_treats_host_and_port_as_process_flags():
    config = BrainConfig()
    cli.apply_cli_overrides(
        config, cli.parse_args(["--web", "--host", "0.0.0.0", "--port", "9000"]))
    assert not hasattr(config, "host")
    assert not hasattr(config, "port")

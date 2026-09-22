"""The mind is always on: there is no off switch to leave her mute.

`consciousness.enabled: false` used to build the mind without ever starting
it, so every dashboard chat waited out the 90s correlation timeout and then
heard silence as if she had chosen it. The flag is gone; an old file carrying
it is migrated, and `start_skills` always starts the loop.
"""

import asyncio
import json

from src.core.config import BrainConfig


def test_the_default_carries_no_enabled_flag():
    assert "enabled" not in BrainConfig().consciousness


def test_an_old_enabled_flag_is_dropped_on_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"consciousness": {"enabled": False}}), encoding="utf-8")
    config = BrainConfig()
    config.load_from_file()
    assert "enabled" not in config.consciousness


def test_start_skills_always_starts_the_loop():
    from src.core.brain import AIVtuberBrain

    started = {}

    class FakeConsciousness:
        async def start(self):
            started["yes"] = True

    class Brain(AIVtuberBrain):
        def __init__(self, config):
            self.config = config
            self.consciousness = FakeConsciousness()
            self._warmup_task = None
            self._rhythm_task = None

        async def _warmup(self):
            pass

    config = BrainConfig()
    config.consciousness = {}
    config.rhythm = {"enabled": False}
    asyncio.run(Brain(config).start_skills())
    assert started.get("yes") is True


def test_the_correlation_fallback_matches_the_config_default():
    from src.core.consciousness import Consciousness

    assert BrainConfig().consciousness["correlation_timeout"] == 90.0

    class Probe:
        pass

    probe = Probe()
    Consciousness._read_knobs(probe, {})
    assert probe.correlation_timeout == 90.0

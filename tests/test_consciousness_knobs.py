"""Every knob the mind reads is declared somewhere the dashboard can show.

`window_persist_after_turn` and `dynamic_context_timeout` used to be read
with `.get()` and exist nowhere else: they worked, but no screen could show
them and no validation could reject a nonsense value. They now have config
defaults and schema entries, so the window section edits the whole window.
"""

from src.core.config import BrainConfig
from src.core.settings_schema import apply_section, section


def test_the_knobs_have_config_defaults():
    config = BrainConfig()

    assert config.consciousness["window_persist_after_turn"] is True
    assert config.consciousness["dynamic_context_timeout"] == 5.0


def test_the_schema_describes_both_knobs():
    keys = {s.key for s in section("consciousness").settings}

    assert "window_persist_after_turn" in keys
    assert "dynamic_context_timeout" in keys


def test_the_window_section_accepts_them():
    config = BrainConfig()

    changed = apply_section(
        config, "consciousness",
        {"window_persist_after_turn": False, "dynamic_context_timeout": 2.5},
    )

    assert changed == {"window_persist_after_turn": False, "dynamic_context_timeout": 2.5}
    assert config.consciousness["dynamic_context_timeout"] == 2.5

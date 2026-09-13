"""Every core module has to import on its own, in any order.

A cycle only shows up when something imports the two halves in the wrong order,
which the suite does not control: pytest has already pulled half the package in
by the time any test runs. So each one is imported first, in its own process.

`memory.store` and `affect.state` are the pair that actually broke: the store
reads the pure affect rules, and the state reads the store back through the
social promotion rules.
"""

import os
import subprocess
import sys

import pytest

MODULES = [
    "src.core.memory.store",
    "src.core.affect.state",
    "src.core.affect.rules",
    "src.core.expression.prosody",
    "src.core.expression.voice",
    "src.core.skills.social.people",
    "src.core.consciousness",
    "src.core.brain",
]


@pytest.mark.parametrize("module", MODULES)
def test_it_imports_first(module):
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


# importing one of these used to pull in `sounddevice`, which raises outright
# when PortAudio is missing — so the whole suite failed to collect on a runner
# with no sound card. Synthesising audio is not playing it.
HEADLESS = [
    "src.modules.tts.edge_tts_wrapper",
    "src.modules.tts.kokoro_tts_wrapper",
    "src.modules.tts.orpheus_tts_wrapper",
    "src.core.expression.voice",
    "src.web.app",
]


@pytest.mark.parametrize("module", HEADLESS)
def test_it_imports_on_a_machine_with_no_sound_card(module, tmp_path):
    (tmp_path / "sounddevice.py").write_text("raise OSError('PortAudio library not found')\n")
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

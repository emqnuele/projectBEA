import sys
import types
from pathlib import Path

import pytest

# tests import `src.*` directly; keep them runnable without an editable install
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _SilentDevice:
    """Stands in for PortAudio so the suite never reaches the sound card.

    `Expression._play_audio` imports sounddevice where it is used and hands it
    whatever the TTS produced. A test that returns real samples rather than
    zeros would play them — out loud, on the machine running the tests — and a
    headless box has no PortAudio to import in the first place.
    """

    def __init__(self):
        self.played = []
        self.stops = 0
        self.default = types.SimpleNamespace(device=(0, 0))

    def play(self, data, samplerate=None, device=None, blocking=False):
        self.played.append((len(data), samplerate, device))

    def stop(self):
        self.stops += 1

    def query_devices(self, index=None):
        device = {"name": "silent", "max_output_channels": 2, "max_input_channels": 2}
        return device if index is not None else [device]


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    """No test reads the config.json of whoever is running it.

    `BrainConfig()` loads the file from the working directory, so a developer
    who has configured their own stream would see tests fail on their machine
    and pass in CI. Pointed at this test's own `tmp_path`, which starts empty —
    so the defaults are the defaults, and a test that wants a config file can
    still write one there.
    """
    from src.core import config as config_module

    monkeypatch.setattr(config_module, "CONFIG_FILE", str(tmp_path / "config.json"))


@pytest.fixture(autouse=True)
def silent_audio(monkeypatch):
    """No test plays sound. Not quiet sound: none."""
    device = _SilentDevice()
    monkeypatch.setitem(sys.modules, "sounddevice", device)
    return device

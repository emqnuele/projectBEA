import os
import sys
from pathlib import Path

import pytest

# tests import `src.*` directly; keep them runnable without an editable install
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fakes import SilentDevice  # noqa: E402


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
def isolated_env_file(monkeypatch, tmp_path):
    """No test writes the `.env` of whoever is running it.

    The dashboard persists secrets there now, so a test that saves one would
    otherwise rewrite the developer's own keys — and `persist` moves the
    process environment with the file, which would leak into the tests after
    it. Both are pointed somewhere harmless and put back.
    """
    from src.core import secrets as secrets_module

    monkeypatch.setattr(secrets_module, "ENV_FILE", str(tmp_path / ".env"))
    before = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(before)


@pytest.fixture(autouse=True)
def silent_audio(monkeypatch):
    """No test plays sound. Not quiet sound: none."""
    device = SilentDevice()
    monkeypatch.setitem(sys.modules, "sounddevice", device)
    return device


@pytest.fixture(autouse=True)
def turns_stay_out_of_the_repo(monkeypatch, tmp_path):
    """A test that runs a whole turn writes that turn down, like the real loop.

    It just must not write it into `data/turns/` of the checkout it is running
    in. The log is still real and still readable — `mind.turns.path_for(day)`
    points at this test's own directory.
    """
    from src.core import consciousness as consciousness_module
    from src.core.mind.turnlog import TurnLog

    def sandboxed(directory="data/turns", keep_days=14, clock=None):
        return TurnLog(str(tmp_path / "turns"), keep_days, clock)

    monkeypatch.setattr(consciousness_module, "TurnLog", sandboxed)

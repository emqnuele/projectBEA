"""Opening the app with obs closed and the models on disk prints nothing scary."""

import logging
import subprocess
import sys
import time

from src.modules.obs.obs_websocket import OBSController


def test_quiet_leaves_the_hub_able_to_turn_its_bars_back_on():
    # a subprocess: the hub freezes its env flag at first import, per process
    script = (
        "import os, warnings\n"
        "os.environ.pop('HF_HUB_DISABLE_PROGRESS_BARS', None)\n"
        "from src.utils.huggingface import quiet\n"
        "with quiet():\n"
        "    from huggingface_hub.utils import are_progress_bars_disabled\n"
        "    assert are_progress_bars_disabled()\n"
        "from huggingface_hub.utils import enable_progress_bars\n"
        "warnings.simplefilter('error')\n"
        "enable_progress_bars()\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_obs_closed_is_one_warning_not_a_traceback(caplog):
    caplog.set_level(logging.DEBUG)
    obs = OBSController("127.0.0.1", 1, "", "avatar")
    obs.connect()
    try:
        # the socket is opened on the obs worker, so its warning arrives from there
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not any("OBS not connected" in r.message for r in caplog.records):
            time.sleep(0.01)
        assert obs.client is None
        assert [r for r in caplog.records if "OBS not connected" in r.message], "no warning at all"
        assert not any(record.exc_info for record in caplog.records)
    finally:
        obs.disconnect()

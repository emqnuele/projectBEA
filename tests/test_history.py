"""The session file must survive a crash, and bursts must share one write."""

import json
import time

from src.utils import history_manager as hm_module
from src.utils.history_manager import HistoryManager


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_a_message_lands_on_disk_as_valid_json(tmp_path):
    hm = HistoryManager(storage_dir=str(tmp_path))
    hm.add_message("user", "ciao bea")
    try:
        data = _read(hm.current_session_file)
    finally:
        hm.flush()
    assert [m["content"] for m in data["messages"]] == ["ciao bea"]
    # the temp file is renamed, never left behind
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_burst_shares_one_write_until_flush(tmp_path, monkeypatch):
    writes = []
    real = hm_module._atomic_write

    def counting(path, data):
        writes.append(path)
        real(path, data)

    monkeypatch.setattr(hm_module, "_atomic_write", counting)
    hm = HistoryManager(storage_dir=str(tmp_path), debounce_seconds=3600.0)
    try:
        for i in range(5):
            hm.add_message("user", f"message {i}")
        # the first write goes out right away; the rest waits
        assert len(writes) == 1
        hm.flush()
        assert len(writes) == 2
        assert len(_read(hm.current_session_file)["messages"]) == 5
    finally:
        hm.flush()


def test_creating_a_session_flushes_the_previous_one(tmp_path):
    hm = HistoryManager(storage_dir=str(tmp_path), debounce_seconds=3600.0)
    try:
        hm.add_message("user", "first session words")
        hm.add_message("user", "still first session")
        old = hm.current_session_file
        hm.create_session()
        assert len(_read(old)["messages"]) == 2
        assert _read(hm.current_session_file)["messages"] == []
    finally:
        hm.flush()


def test_loading_a_session_flushes_the_previous_one(tmp_path):
    hm = HistoryManager(storage_dir=str(tmp_path), debounce_seconds=3600.0)
    try:
        hm.add_message("user", "words before the switch")
        old = hm.current_session_file
        old_id = hm.session_id
        hm.create_session()
        assert hm.load_session(old_id)
        assert [m["content"] for m in hm.history] == ["words before the switch"]
        assert old.exists()
    finally:
        hm.flush()


def test_renaming_the_open_session_keeps_pending_messages(tmp_path):
    hm = HistoryManager(storage_dir=str(tmp_path), debounce_seconds=3600.0)
    try:
        hm.add_message("user", "a pending message")
        assert hm.set_session_title(hm.session_id, "a title") is True
        data = _read(hm.current_session_file)
        assert data["title"] == "a title"
        assert [m["content"] for m in data["messages"]] == ["a pending message"]
    finally:
        hm.flush()


def test_perf_off_writes_every_message_at_once(tmp_path, monkeypatch):
    """The switch restores the old behaviour: no debouncing at all."""
    monkeypatch.setenv("BEA_PERF", "off")
    hm = HistoryManager(storage_dir=str(tmp_path))
    try:
        assert hm.debounce_seconds == 0.0
        hm.add_message("user", "first")
        hm.add_message("user", "second")
        assert len(_read(hm.current_session_file)["messages"]) == 2
    finally:
        hm.flush()


def test_the_deferred_write_arrives_on_its_own(tmp_path):
    hm = HistoryManager(storage_dir=str(tmp_path), debounce_seconds=0.05)
    try:
        hm.add_message("user", "first")
        hm.add_message("user", "second")
        deadline = time.time() + 5.0
        while len(_read(hm.current_session_file)["messages"]) < 2:
            assert time.time() < deadline
            time.sleep(0.02)
    finally:
        hm.flush()

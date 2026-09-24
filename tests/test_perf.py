"""The performance numbers must be visible, and never load-bearing."""

from src.core import perf as perf_module
from src.core.config import BrainConfig
from src.setup.doctor import check_perf


def _config(**kwargs) -> BrainConfig:
    settings = BrainConfig()
    for key, value in kwargs.items():
        setattr(settings, key, value)
    return settings


class FakeEmbedder:
    dim = 2

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_core_count_is_a_positive_number():
    assert isinstance(perf_module.physical_cores(), int)
    assert perf_module.physical_cores() >= 1


def test_provider_list_is_honest_on_any_machine():
    providers = perf_module.onnx_providers()
    assert isinstance(providers, list)
    assert all(isinstance(p, str) for p in providers)


def test_the_summary_line_names_everything():
    line = perf_module.describe(vec="on(schema=2)", providers=["CPUExecutionProvider"],
                                threads=8, whisper="cuda/float16", memories=1234)
    for part in ("vec=on(schema=2)", "CPUExecutionProvider", "threads=8",
                 "whisper=cuda/float16", "memories=1234"):
        assert part in line


async def test_the_perf_check_reports_the_store(tmp_path, monkeypatch):
    """Vector state, providers, threads, whisper, count and a timed recall."""
    import src.core.memory.embedder as embedder_module

    monkeypatch.setattr(embedder_module, "FastEmbedEmbedder", FakeEmbedder)
    settings = _config(skills={"memory": {"db_path": str(tmp_path / "bea.db")}})
    found = await check_perf(settings)
    assert found.ok
    for part in ("vec=", "threads=", "whisper=", "memories=0", "recall="):
        assert part in found.detail


def test_the_switch_is_on_unless_asked_otherwise(monkeypatch):
    monkeypatch.delenv("BEA_PERF", raising=False)
    assert perf_module.perf_enabled() is True
    for value in ("off", "OFF", "0", "false", "no"):
        monkeypatch.setenv("BEA_PERF", value)
        assert perf_module.perf_enabled() is False
    monkeypatch.setenv("BEA_PERF", "on")
    assert perf_module.perf_enabled() is True


async def test_the_perf_line_says_when_it_is_off(monkeypatch, tmp_path):
    """With the switch off the engine runs the old paths; the line must say so."""
    import src.core.memory.embedder as embedder_module

    monkeypatch.setattr(embedder_module, "FastEmbedEmbedder", FakeEmbedder)
    monkeypatch.setenv("BEA_PERF", "off")
    settings = _config(skills={"memory": {"db_path": str(tmp_path / "bea.db")}})
    found = await check_perf(settings)
    assert found.ok and "perf=off" in found.detail


async def test_the_perf_check_never_blocks_the_run(tmp_path):
    """A store that will not open is a warning, not a wall."""
    settings = _config(skills={"memory": {"db_path": str(tmp_path)}})
    found = await check_perf(settings)
    assert not found.ok and not found.stops


def _record(relationship: int, size: int) -> bytes:
    import struct

    return struct.pack("<II", relationship, size) + bytes(size - 8)


def test_windows_core_records_are_walked_by_their_own_size():
    """Records vary in size; a fixed stride would count garbage as cores."""
    raw = _record(0, 48) + _record(0, 80) + _record(2, 32) + _record(0, 48)
    assert perf_module._core_records(raw) == 3


def test_a_truncated_or_corrupt_windows_buffer_does_not_loop():
    assert perf_module._core_records(b"") == 0
    assert perf_module._core_records(_record(0, 48)[:20]) == 1
    assert perf_module._core_records(b"\x00\x00\x00\x00\x00\x00\x00\x00") == 0


def test_windows_asks_the_kernel_rather_than_counting_threads(monkeypatch):
    monkeypatch.setattr(perf_module.sys, "platform", "win32")
    monkeypatch.setattr(perf_module, "_windows_physical_cores", lambda: 6)
    monkeypatch.setattr(perf_module.os, "cpu_count", lambda: 12)
    assert perf_module.physical_cores() == 6


def test_windows_falls_back_to_the_os_count_when_the_kernel_will_not_say(monkeypatch):
    monkeypatch.setattr(perf_module.sys, "platform", "win32")
    monkeypatch.setattr(perf_module, "_windows_physical_cores", lambda: 0)
    monkeypatch.setattr(perf_module.os, "cpu_count", lambda: 12)
    assert perf_module.physical_cores() == 12

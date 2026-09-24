"""The machine's answer to "what can the hot paths spend".

One place for the numbers every thread pool, model loader and log line agrees
on: how many cores are really there, which onnx providers exist, and the
one-line summary the startup log and the doctor check both print. Anything
that tunes itself reads it from here rather than re-deriving it.
"""

import os
import struct
import subprocess
import sys
from typing import List

# the one switch that turns every optimisation off again. Anything introduced
# for performance checks this and only this; bisecting a regression is one
# variable, and the suite runs with it set so the old paths never rot.
PERF_ENV_VAR = "BEA_PERF"


def perf_enabled() -> bool:
    """False only when the owner asked for the pre-optimisation engine."""
    return os.environ.get(PERF_ENV_VAR, "on").strip().lower() not in (
        "off", "0", "false", "no")


def physical_cores() -> int:
    """Cores with their own execution unit, not threads the os schedules.

    `os.cpu_count` counts the threads, which on an intel box is twice the
    cores and sizes every pool for a machine that is not there. Each platform
    is asked its own way; anything unexpected falls back to what the os
    claims, which is wrong in the safe direction.
    """
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.physicalcpu"],
                                 capture_output=True, text=True, timeout=5)
            return max(1, int(out.stdout.strip()))
        if sys.platform.startswith("linux"):
            return max(1, _linux_physical_cores())
        if sys.platform.startswith("win"):
            return max(1, _windows_physical_cores() or os.cpu_count() or 1)
    except Exception:
        pass
    return max(1, os.cpu_count() or 1)


def _linux_physical_cores() -> int:
    """Distinct core ids in /proc/cpuinfo, or the os count when unreadable."""
    try:
        seen = set()
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            current: dict = {}
            for line in f:
                line = line.strip()
                if not line:
                    if "core id" in current:
                        seen.add((current.get("physical id", "?"),
                                  current["core id"]))
                    current = {}
                elif ":" in line:
                    key, _, value = line.partition(":")
                    current[key.strip()] = value.strip()
            if "core id" in current:
                seen.add((current.get("physical id", "?"), current["core id"]))
        if seen:
            return len(seen)
    except OSError:
        pass
    return max(1, os.cpu_count() or 1)


# LOGICAL_PROCESSOR_RELATIONSHIP: one record per physical core
RELATION_PROCESSOR_CORE = 0


def _windows_physical_cores() -> int:
    """Physical cores from the kernel, or 0 when it will not say.

    Unimplemented until this existed, so windows got the thread count: twice
    the cores on any hyperthreaded cpu, and whisper sized for a machine that
    is not there. Measured on 10 cores, 20 threads cost 3x the latency.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # pyright: ignore[reportAttributeAccessIssue]
    call = kernel32.GetLogicalProcessorInformationEx
    call.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    call.restype = wintypes.BOOL

    length = wintypes.DWORD(0)
    # the first call fails on purpose and says how big the buffer has to be
    call(RELATION_PROCESSOR_CORE, None, ctypes.byref(length))
    if not length.value:
        return 0
    buffer = ctypes.create_string_buffer(length.value)
    if not call(RELATION_PROCESSOR_CORE, buffer, ctypes.byref(length)):
        return 0
    return _core_records(buffer.raw[: length.value])


def _core_records(raw: bytes) -> int:
    """Counts the per-core records in a GetLogicalProcessorInformationEx buffer.

    Each record starts with its relationship and its own size, and the sizes
    vary, so the walk follows them instead of assuming a stride.
    """
    count, at = 0, 0
    while at + 8 <= len(raw):
        relationship, size = struct.unpack_from("<II", raw, at)
        if size < 8:
            break
        if relationship == RELATION_PROCESSOR_CORE:
            count += 1
        at += size
    return count


def onnx_providers() -> List[str]:
    """Execution providers onnxruntime can actually use here, in its order."""
    try:
        import onnxruntime

        return list(onnxruntime.get_available_providers())
    except Exception:
        return []


def describe(*, vec: str, providers: List[str], threads: int,
             whisper: str, memories: object = "?") -> str:
    """The one line both the startup log and the doctor check print."""
    return (f"vec={vec} providers=[{','.join(providers)}] "
            f"threads={threads} whisper={whisper} memories={memories}")

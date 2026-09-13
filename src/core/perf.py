"""The machine's answer to "what can the hot paths spend".

One place for the numbers every thread pool, model loader and log line agrees
on: how many cores are really there, which onnx providers exist, and the
one-line summary the startup log and the doctor check both print. Anything
that tunes itself reads it from here rather than re-deriving it.
"""

import os
import subprocess
import sys
from typing import List


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

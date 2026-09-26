"""Places she remembers in a world: home, the mine, the spot where she died.

Kept per server (the address the mod announces in the state's `world.server`),
so a place from one world is never walked to in another. They live in RAM and
reach `data/minecraft/places.json` through `save()`: the text is taken on the
event loop, where the places change, and written in a thread.
"""

import asyncio
import json
import math
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PLACES_FILE = Path(__file__).resolve().parents[4] / "data" / "minecraft" / "places.json"
# a handful a world: more is a list nobody reads again
MAX_PLACES = 24
MAX_NAME = 32
DEATH = "last_death"


def normalize(name: str) -> str:
    """ "My Home " and "my_home" are one place."""
    return "_".join(str(name or "").strip().lower().split())[:MAX_NAME]


def server_of(state: Optional[Dict[str, Any]]) -> str:
    return str(((state or {}).get("world") or {}).get("server") or "unknown")


class Places:
    def __init__(self, path: Path = PLACES_FILE):
        self.path = path
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # two saves at once used to share one tmp file and serialise the places while the loop
        # changed them: 646 of 1200 concurrent saves failed. Now each write has its own tmp file,
        # one writes at a time, and an older snapshot never lands over a newer one
        self._write_lock = threading.Lock()
        self._taken = 0
        self._written = 0
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data = loaded
            except (OSError, ValueError):
                self._data = {}

    def remember(self, server: str, name: str, x: float, y: float, z: float,
                 dimension: str = "minecraft:overworld") -> str:
        """Store (or move) a place; returns the name it was kept under."""
        key = normalize(name)
        places = self._data.setdefault(server, {})
        places[key] = {"x": int(math.floor(x)), "y": int(math.floor(y)), "z": int(math.floor(z)),
                       "dimension": dimension, "saved_at": int(time.time())}
        if len(places) > MAX_PLACES:
            # the oldest goes first, but never where she last died
            oldest = min((k for k in places if k != DEATH), key=lambda k: places[k].get("saved_at", 0))
            del places[oldest]
        return key

    def get(self, server: str, name: str) -> Optional[Dict[str, Any]]:
        return self._data.get(server, {}).get(normalize(name))

    def forget(self, server: str, name: str) -> bool:
        return self._data.get(server, {}).pop(normalize(name), None) is not None

    def names(self, server: str) -> list:
        return sorted(self._data.get(server, {}))

    def render(self, server: str, here: Optional[Tuple[float, float, float]] = None,
               dimension: str = "minecraft:overworld") -> str:
        """ "home (10, -57, 3) 12m, last_death (0, -60, 5) in the_nether"; empty when there are none."""
        parts = []
        for name in self.names(server):
            p = self._data[server][name]
            where = f"{name} ({p['x']}, {p['y']}, {p['z']})"
            if p.get("dimension", dimension) != dimension:
                where += " in " + str(p.get("dimension", "")).split(":")[-1]
            elif here is not None:
                where += f" {math.dist(here, (p['x'], p['y'], p['z'])):.0f}m"
            parts.append(where)
        return ", ".join(parts)

    def snapshot(self) -> Tuple[int, str]:
        """The places as they are now, as the text to write, numbered in the order taken."""
        self._taken += 1
        return self._taken, json.dumps(self._data, indent=1, sort_keys=True)

    def write(self, number: int, text: str) -> None:
        """Write one snapshot atomically; blocking. A snapshot older than the one on disk is skipped."""
        with self._write_lock:
            if number <= self._written:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
            self._written = number

    async def save(self) -> None:
        """Snapshot here, on the loop; write in a thread."""
        number, text = self.snapshot()
        await asyncio.to_thread(self.write, number, text)

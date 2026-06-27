import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

from src.utils.logger import get_logger

logger = get_logger("bea.skills.dream.recent")


@dataclass
class HotFact:
    """A volatile 'right now' fact that decays. Kept few and always in context."""

    text: str
    created_at: float
    expires_at: float
    source: str  # "morning_pass" | "dreamer" | "live"

    @property
    def alive(self) -> bool:
        return time.time() < self.expires_at


class RecentStore:
    """JSON-backed list of HotFacts. Self-pruning on read/write."""

    def __init__(self, path: str = "data/memory/recent.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._facts: List[HotFact] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._facts = [HotFact(**d) for d in raw]
            self.prune()
        except Exception as e:
            logger.error(f"RecentStore: failed to load: {e}")

    def _save(self) -> None:
        try:
            data = [asdict(f) for f in self._facts]
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"RecentStore: failed to save: {e}")

    def prune(self) -> None:
        self._facts = [f for f in self._facts if f.alive]

    def clear_source(self, source: str) -> None:
        self._facts = [f for f in self._facts if f.source != source]
        self._save()

    def add(self, text: str, ttl_seconds: float, source: str = "dreamer") -> None:
        text = text.strip()
        if not text:
            return
        # dedup by text within the same source
        self._facts = [f for f in self._facts if not (f.text == text and f.source == source)]
        now = time.time()
        self._facts.append(HotFact(text=text, created_at=now, expires_at=now + ttl_seconds, source=source))
        self.prune()
        self._save()

    def active(self) -> List[HotFact]:
        self.prune()
        return list(self._facts)

    def render(self, max_items: int = 6) -> str:
        facts = self.active()[:max_items]
        if not facts:
            return ""
        lines = "\n".join(f"- {f.text}" for f in facts)
        return f"[RIGHT NOW]\n{lines}"

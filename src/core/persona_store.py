"""Reading and writing the persona: one file and two config fields.

The soul stays a markdown file so it can be opened, diffed and edited by hand.
This is the other way in — the dashboard — which means a web request ends up
writing to disk, so most of what is here is about refusing to.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.persona import DEFAULT_PRONOUNS, persona_of
from src.utils.logger import get_logger

logger = get_logger("bea.persona.store")

# a persona is prose, not a novel. Well past anything reasonable, and small
# enough that a runaway paste cannot fill the disk
MAX_SOUL_CHARS = 100_000

# every path the api may write to lives under here
WRITABLE_ROOT = "data"

WRITABLE_FIELDS = {"name", "pronouns", "soul", "trigger_words"}


class PersonaRefused(Exception):
    """A write that will not happen, with an HTTP status the API can use."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class SoulFile:
    path: Path

    @property
    def backup(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".bak")

    def read(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        except OSError as e:
            logger.error(f"Could not read the soul at {self.path}: {e}")
            return ""

    def write(self, text: str) -> None:
        # the previous version survives a bad edit from a text box
        if self.path.exists():
            try:
                self.backup.write_text(self.read(), encoding="utf-8")
            except OSError as e:
                logger.warning(f"Could not back up the soul: {e}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")


def soul_file(config) -> SoulFile:
    """The soul file for this config, refusing anything outside `data/`."""
    raw = Path(str(getattr(config, "soul_path", "") or ""))
    if raw.is_absolute():
        raise PersonaRefused(403, "The soul must live inside the data directory.")
    resolved = (Path.cwd() / raw).resolve()
    root = (Path.cwd() / WRITABLE_ROOT).resolve()
    if not resolved.is_relative_to(root):
        raise PersonaRefused(403, "The soul must live inside the data directory.")
    return SoulFile(resolved)


def _shipped_soul() -> str:
    """The persona we ship, used to tell "never touched" from "set up"."""
    try:
        return (Path(__file__).parents[2] / "data/prompts/soul.md").read_text(encoding="utf-8")
    except OSError:
        return ""


ONBOARDING_KEY = "onboarding.completed"


def onboarding_completed(memory) -> bool:
    """Whether someone has been through it, or said no. Never fails loudly."""
    if memory is None:
        return False
    try:
        return bool(memory.db.scalar(
            "SELECT value FROM settings WHERE key = ?", (ONBOARDING_KEY,), default=None,
        ))
    except Exception as e:
        logger.warning(f"Could not read the onboarding flag: {e}")
        return False


def mark_onboarding_completed(memory) -> None:
    if memory is None:
        return
    try:
        memory.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, '1') "
            "ON CONFLICT(key) DO UPDATE SET value = '1'", (ONBOARDING_KEY,),
        )
    except Exception as e:
        logger.warning(f"Could not record the onboarding flag: {e}")


def describe(config) -> Dict[str, Any]:
    """Everything the persona screen needs, safe to hand to a browser."""
    persona = persona_of(config)
    try:
        soul = soul_file(config).read()
    except PersonaRefused:
        soul = ""
    return {
        **persona.as_dict(),
        "soul": soul,
        # "the file exists" is not the question: it always does, we ship it
        "customised": bool(soul.strip()) and soul.strip() != _shipped_soul().strip(),
    }


def apply(config, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validates the whole payload, then writes it. Raises PersonaRefused."""
    unknown = sorted(set(payload) - WRITABLE_FIELDS)
    if unknown:
        raise PersonaRefused(422, f"Unknown field(s): {', '.join(unknown)}")

    soul: Optional[str] = None
    if "soul" in payload:
        soul = str(payload["soul"] or "")
        if len(soul) > MAX_SOUL_CHARS:
            raise PersonaRefused(413, f"A persona over {MAX_SOUL_CHARS} characters is not one.")

    if "name" in payload and not str(payload["name"] or "").strip():
        raise PersonaRefused(422, "She needs a name.")

    # resolve the path before writing anything, so a refusal changes nothing
    target = soul_file(config) if soul is not None else None

    block = dict(getattr(config, "persona", None) or {})
    if "name" in payload:
        block["name"] = str(payload["name"]).strip()
    if "pronouns" in payload:
        block["pronouns"] = str(payload["pronouns"] or "").strip() or DEFAULT_PRONOUNS
    config.persona = block

    if "trigger_words" in payload:
        raw = payload["trigger_words"]
        words = raw if isinstance(raw, list) else str(raw).split(",")
        attention = dict(getattr(config, "attention", None) or {})
        attention["trigger_words"] = [str(w).strip().lower() for w in words if str(w).strip()]
        config.attention = attention

    if target is not None:
        target.write(soul)

    return describe(config)

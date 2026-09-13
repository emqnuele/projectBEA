from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger("bea.prompts")


def load_text(path: str, fallback: str = "") -> str:
    """Reads a prompt file, falling back when it is missing, unreadable or blank.

    A file emptied by a bad save is the same failure as a deleted one, and both
    used to leave an empty string in the middle of her prompt.
    """
    try:
        p = Path(path)
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                return text
            logger.warning(f"Prompt file is empty: {path}")
        else:
            logger.warning(f"Prompt file not found: {path}")
    except Exception as e:
        logger.error(f"Error reading prompt '{path}': {e}")
    return fallback


def compose(*parts: str) -> str:
    """Joins prompt fragments (soul + context rules) into one system prompt."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def prompt_for(block: dict, name: str, default_path: str) -> str:
    """A skill's instructions: what was written in the dashboard, else the file.

    The editor in the dashboard saves prose under `<name>`, while the skill
    only ever read the file at `<name>_path` — so everything typed into it was
    stored and never used. An empty editor still means the shipped file, which
    is what its own placeholder promises.
    """
    written = str(block.get(name) or "").strip()
    if written:
        return written
    return load_text(block.get(f"{name}_path", default_path))

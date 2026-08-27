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

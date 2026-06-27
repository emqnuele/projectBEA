from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger("bea.prompts")


def load_text(path: str, fallback: str = "") -> str:
    """Reads a prompt file, returning `fallback` if it is missing or unreadable."""
    try:
        p = Path(path)
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
        logger.warning(f"Prompt file not found: {path}")
    except Exception as e:
        logger.error(f"Error reading prompt '{path}': {e}")
    return fallback


def compose(*parts: str) -> str:
    """Joins prompt fragments (soul + context rules) into one system prompt."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())

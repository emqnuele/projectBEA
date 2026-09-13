import logging
import os
from typing import Optional

from rich.logging import RichHandler

_loggers = {}

# set by quieten(): an explicit choice outranks the environment
_override: Optional[int] = None


def _level() -> int:
    """The level in force right now.

    Read per call rather than at import: `.env` is loaded by the entrypoint,
    which cannot happen before this module is imported, and resolving it once
    at import made LOG_LEVEL work or not work depending on import order.
    """
    if _override is not None:
        return _override
    return getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)


def _apply(logger: logging.Logger, level: int) -> None:
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    level = _level()

    cached = _loggers.get(name)
    if cached is not None:
        # a logger built before `.env` was read must not keep the old level
        if cached.level != level:
            _apply(cached, level)
        return cached

    logger = logging.getLogger(name)
    logger.setLevel(level)
    # avoid duplicate output with uvicorn
    logger.propagate = False

    if not logger.handlers:
        handler = RichHandler(rich_tracebacks=True, markup=False, show_path=False)
        handler.setLevel(level)
        logger.addHandler(handler)

    _loggers[name] = logger
    return logger


def quieten(level: int = logging.WARNING) -> None:
    """Turns the engine's running commentary down, and keeps it down.

    For the commands whose output *is* the point: a diagnostic that reports
    twelve findings, with forty lines of INFO about loading models threaded
    between them, is a diagnostic nobody can read.
    """
    global _override
    _override = level
    for logger in _loggers.values():
        _apply(logger, level)


logger = get_logger("bea")

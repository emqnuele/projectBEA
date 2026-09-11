import logging
import os

from rich.logging import RichHandler

_loggers = {}

# allow overriding log level without touching code
_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)


def get_logger(name: str) -> logging.Logger:
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(_level)
    # avoid duplicate output with uvicorn
    logger.propagate = False

    if not logger.handlers:
        handler = RichHandler(rich_tracebacks=True, markup=False, show_path=False)
        handler.setLevel(_level)
        logger.addHandler(handler)

    _loggers[name] = logger
    return logger


def quieten(level: int = logging.WARNING) -> None:
    """Turns the engine's running commentary down, and keeps it down.

    For the commands whose output *is* the point: a diagnostic that reports
    twelve findings, with forty lines of INFO about loading models threaded
    between them, is a diagnostic nobody can read.
    """
    global _level
    _level = level
    for logger in _loggers.values():
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)


logger = get_logger("bea")

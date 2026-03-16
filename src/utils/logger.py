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


logger = get_logger("bea")

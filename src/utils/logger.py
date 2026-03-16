import logging
from rich.logging import RichHandler


_loggers = {}


def get_logger(name: str) -> logging.Logger:
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # avoid duplicate output with uvicorn
    logger.propagate = False

    if not logger.handlers:
        handler = RichHandler(rich_tracebacks=True, markup=False, show_path=False)
        logger.addHandler(handler)

    _loggers[name] = logger
    return logger


logger = get_logger("bea")

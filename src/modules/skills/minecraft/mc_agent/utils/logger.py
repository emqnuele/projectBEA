import logging
import sys
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

class ColorFormatter(logging.Formatter):
    """Custom formatter to add colors to log levels"""
    
    COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, Fore.WHITE)
        message = super().format(record)
        return f"{color}{message}{Style.RESET_ALL}"

def setup_logger(name="AgentMiddleware", level=logging.INFO):
    """Sets up a logger with colored output"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # CRITICAL: Prevent bubbling to root logger (Uvicorn/FastAPI)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = ColorFormatter("[%(asctime)s] [MC-SKILL:%(name)s] %(message)s", datefmt="%H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

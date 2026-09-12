"""Where a secret typed into the dashboard actually goes.

`BrainConfig.save_to_file` strips every secret on the way to config.json by
design, and the wizard has always written them to `.env` instead. The dashboard
handed them to `save_to_file` anyway: the field reported saved, the running
engine used the value until it was stopped, and the next start came up without
it — the only trace being a warning in a log nobody reads.

So a secret the dashboard is given is written here, to the one file the engine
reads it back from, and the process environment is moved with it so a config
rebuilt in this same process sees what the file says.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.config import SECRET_ENV_VARS
from src.setup.env_file import merge_env
from src.utils.logger import get_logger

logger = get_logger("bea.secrets")

ENV_FILE = ".env"


def env_var(path: str) -> Optional[str]:
    """The environment variable carrying `path`, or None if it is not a secret."""
    return SECRET_ENV_VARS.get(path)


def is_secret(path: str) -> bool:
    return path in SECRET_ENV_VARS


def split(path: str) -> Tuple[Optional[str], str]:
    """`discord.token` -> ("discord", "token"); `groq_key` -> (None, "groq_key")."""
    skill, _, field = path.rpartition(".")
    return (skill or None), field


def persist(values: Dict[str, str]) -> List[str]:
    """Writes secrets to `.env` and moves the environment with them.

    `values` is keyed the way `SECRET_ENV_VARS` is. An empty value clears the
    variable rather than being ignored: an emptied field in the dashboard is an
    instruction to forget a key, not a question left unanswered.

    Returns the environment variables it wrote, so the caller can say so.
    """
    updates: Dict[str, str] = {}
    for path, value in values.items():
        name = SECRET_ENV_VARS.get(path)
        if name is None:
            continue
        updates[name] = value or ""

    if not updates:
        return []

    path = Path(ENV_FILE)
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(merge_env(existing, updates, empty_clears=True), encoding="utf-8")
    except OSError as e:
        # the caller has already applied the value in memory, so she keeps
        # working; what is lost is only the part that outlives the process
        logger.error(f"Could not write {ENV_FILE}: {e}")
        raise

    for name, value in updates.items():
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)

    logger.info(f"Wrote {', '.join(sorted(updates))} to {ENV_FILE}")
    return sorted(updates)

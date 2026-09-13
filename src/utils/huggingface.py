"""What to tell someone whose model download did not happen.

Two of her parts are fetched from Hugging Face on first use — whisper and the
embedder — and both hand back whatever huggingface_hub raised, which says `401`
at a person who never knew an account was involved.
"""

from typing import Optional

TOKEN_HINT = (
    "Hugging Face refused the download. The weights are public, so this is "
    "almost always a shared or office IP being rate-limited: wait a few minutes, "
    "or put HF_TOKEN=<your token> in .env (https://huggingface.co/settings/tokens) "
    "and it will be used for the download."
)

OFFLINE_HINT = (
    "The weights could not be reached. Check the connection, then start her "
    "again — the download resumes where it stopped."
)


def download_hint(error: Exception) -> Optional[str]:
    """A line the person reading the log can act on, or None.

    Only the two cases with a real answer get a hint; everything else is left
    to speak for itself rather than be guessed at.
    """
    text = f"{type(error).__name__}: {error}".lower()

    if any(word in text for word in ("401", "403", "429", "gated", "rate limit",
                                     "too many requests", "unauthorized")):
        return TOKEN_HINT
    if any(word in text for word in ("connection", "timeout", "timed out",
                                     "network", "dns", "offline", "unreachable")):
        return OFFLINE_HINT
    return None

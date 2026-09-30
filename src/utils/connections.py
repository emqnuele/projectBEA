"""Telling a kept connection that went away from a host that cannot be reached."""

import requests
from urllib3.exceptions import NewConnectionError


def stale(error: requests.ConnectionError) -> bool:
    """A kept connection that had gone, rather than a host that cannot be reached.

    A new connection that fails — refused, unresolvable, a bad certificate —
    would only fail again, and a timeout would be waited out twice.
    """
    if isinstance(error, (requests.Timeout, requests.exceptions.SSLError)):
        return False
    reason = getattr(error.args[0], "reason", None) if error.args else None
    return not isinstance(reason, NewConnectionError)

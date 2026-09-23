"""What she may open, checked where the connection is actually made.

Anyone in chat can hand her a link, so a fetch is a request made on behalf of
a stranger from inside the owner's network. Without this, "read
http://127.0.0.1:8000/config" or a cloud metadata address is one message away.

The check lives in two places because aiohttp consults the resolver only for
names: an address written as a literal skips it entirely, so every URL —
including every redirect hop — is checked here first, and every name is
checked again by the resolver at the moment it is resolved, which is what
closes DNS rebinding.
"""

import ipaddress
import re
import socket
from typing import List
from urllib.parse import urlsplit, urlunsplit

from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import ThreadedResolver


class BlockedURL(ValueError):
    """A URL she is not allowed to open, with a reason she can be told."""


class BlockedAddress(OSError):
    """A name that resolved somewhere private."""


# a scheme written without `://`: javascript:, data:, ftp: and friends. Checked
# before the bare-host shortcut below, so `javascript:alert(1)` is refused as a
# scheme instead of being read as a host called `javascript`.
_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")


def is_public(address: str) -> bool:
    """Whether an address is on the open internet."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    # ::ffff:127.0.0.1 is loopback wearing a v6 costume
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


def normalize(url: str) -> str:
    """The URL she meant, or BlockedURL saying why it cannot be opened."""
    url = (url or "").strip()
    if not url:
        raise BlockedURL("there is no URL")
    if "://" not in url:
        bare_scheme = _SCHEME.match(url)
        if bare_scheme:
            raise BlockedURL(
                f"only web pages can be opened, not {bare_scheme.group(1).lower()}: links")
        # models write "example.com/page" as often as the full thing
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BlockedURL(f"only web pages can be opened, not {parts.scheme}: links")
    if parts.username or parts.password:
        raise BlockedURL("links carrying a login are not opened")
    host = parts.hostname
    if not host:
        raise BlockedURL("that is not a web address")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not is_public(host):
            raise BlockedURL("that address is on a private network")
    # the fragment is for the browser, never sent to the server
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


class PublicOnlyResolver(AbstractResolver):
    """Resolves like the default resolver, and refuses anything private.

    Every address a name returns has to be public, not just one: a record set
    mixing a public and a private address is the shape of a rebinding attempt.
    """

    def __init__(self) -> None:
        self._inner = ThreadedResolver()

    async def resolve(self, host: str, port: int = 0,
                      family: socket.AddressFamily = socket.AF_INET) -> List[ResolveResult]:
        results = await self._inner.resolve(host, port, family)
        private = [r["host"] for r in results if not is_public(r["host"])]
        if private:
            raise BlockedAddress(f"{host} points to a private address")
        return results

    async def close(self) -> None:
        await self._inner.close()

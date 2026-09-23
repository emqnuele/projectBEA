"""A link from a stranger must never reach the owner's own network."""

import socket

import pytest

from src.core.skills.web.fetch import Fetcher, FetchError
from src.core.skills.web.guard import BlockedAddress, BlockedURL, PublicOnlyResolver, is_public, normalize


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.10", "169.254.169.254",
    "100.64.0.1", "0.0.0.0", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1",
    "224.0.0.1", "not an address",
])
def test_private_addresses_are_not_public(address):
    assert not is_public(address)


@pytest.mark.parametrize("address", ["93.184.215.14", "1.1.1.1", "2606:4700:4700::1111"])
def test_internet_addresses_are_public(address):
    assert is_public(address)


def test_a_bare_host_becomes_an_https_url_without_its_fragment():
    assert normalize("example.com/docs#intro") == "https://example.com/docs"
    assert normalize("http://example.com") == "http://example.com/"


@pytest.mark.parametrize("url", [
    "", "file:///etc/passwd", "ftp://example.com/", "javascript:alert(1)",
    "http://user:pass@example.com/", "http://127.0.0.1:8000/config",
    "http://[::1]/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/",
])
def test_urls_she_may_not_open_are_refused(url):
    with pytest.raises(BlockedURL):
        normalize(url)


def _results(*hosts):
    return [{"hostname": "x", "host": h, "port": 80, "family": socket.AF_INET,
             "proto": 0, "flags": 0} for h in hosts]


async def test_the_resolver_refuses_a_name_that_points_inside(monkeypatch):
    resolver = PublicOnlyResolver()

    async def resolve(host, port=0, family=socket.AF_INET):
        return _results("1.1.1.1", "127.0.0.1")

    monkeypatch.setattr(resolver._inner, "resolve", resolve)
    with pytest.raises(BlockedAddress):
        await resolver.resolve("rebind.example", 80)
    await resolver.close()


async def test_the_resolver_passes_a_public_name(monkeypatch):
    resolver = PublicOnlyResolver()

    async def resolve(host, port=0, family=socket.AF_INET):
        return _results("1.1.1.1")

    monkeypatch.setattr(resolver._inner, "resolve", resolve)
    assert [r["host"] for r in await resolver.resolve("example.com", 80)] == ["1.1.1.1"]
    await resolver.close()


async def test_a_name_resolving_to_loopback_is_refused_at_connect_time():
    """`localhost` is a name, so this goes through the resolver, not normalize."""
    fetcher = Fetcher(timeout=5)
    try:
        with pytest.raises(FetchError, match="private network"):
            await fetcher.fetch("http://localhost:9/")
    finally:
        await fetcher.close()


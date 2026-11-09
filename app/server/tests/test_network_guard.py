"""The session network guard refuses any address that is not loopback."""

import socket

import pytest


def test_guard_refuses_a_public_address() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.1)
        with pytest.raises(RuntimeError, match="network guard"):
            sock.connect(("1.1.1.1", 443))


def test_guard_refuses_connect_ex() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(RuntimeError, match="network guard"),
    ):
        sock.connect_ex(("93.184.216.34", 80))


@pytest.mark.parametrize("host", ["example.com", "93.184.216.34", "10.0.0.1", b"x.org"])
def test_guard_refuses_a_public_name_lookup(host: str | bytes) -> None:
    with pytest.raises(RuntimeError, match="network guard"):
        socket.getaddrinfo(host, 443)


@pytest.mark.parametrize(
    "host",
    [None, "localhost", "LOCALHOST", "127.0.0.1", "127.0.0.2", "::1", b"localhost"],
)
def test_guard_resolves_loopback_names(host: str | bytes | None) -> None:
    assert socket.getaddrinfo(host, 80)


def test_guard_blocks_the_name_lookup_behind_create_connection() -> None:
    with pytest.raises(RuntimeError, match="network guard"):
        socket.create_connection(("example.com", 80), timeout=0.1)

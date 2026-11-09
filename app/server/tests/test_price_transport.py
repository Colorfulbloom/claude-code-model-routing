"""Tests for price_transport. A fake opener or handler stands in for every socket."""

import io
import urllib.error
import urllib.request
import urllib.response
from collections.abc import Callable
from email.message import Message
from http.client import HTTPMessage
from typing import Any, cast

import pytest

import price_transport
from price_transport import (
    LITELLM_URL,
    OPENROUTER_URL,
    FetchError,
    SameHostRedirect,
    UrllibTransport,
)


class FakeResponse:
    """A response that serves a body in the sizes it is asked for."""

    def __init__(
        self,
        body: bytes = b"",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        read_error: BaseException | None = None,
    ) -> None:
        self._body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}
        self.served = 0
        self.closed = False
        self._read_error = read_error

    def read(self, amt: int = -1, /) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        chunk = self._body.read(amt)
        self.served += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    """Records the request and returns or raises what the test set up."""

    def __init__(self, outcome: FakeResponse | BaseException) -> None:
        self.outcome = outcome
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []

    def open(
        self,
        fullurl: urllib.request.Request,
        data: None = None,
        timeout: float = 0,
    ) -> FakeResponse:
        self.requests.append(fullurl)
        self.timeouts.append(timeout)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def fetch(opener: FakeOpener, url: str = LITELLM_URL, max_bytes: int = 1000) -> bytes:
    return UrllibTransport(opener).fetch(url, timeout=10.0, max_bytes=max_bytes)


def reason(opener: FakeOpener, url: str = LITELLM_URL, max_bytes: int = 1000) -> str:
    with pytest.raises(FetchError) as caught:
        fetch(opener, url, max_bytes)
    return caught.value.reason_code


def test_returns_the_body_and_closes_the_response() -> None:
    response = FakeResponse(b'{"a": 1}')
    assert fetch(FakeOpener(response)) == b'{"a": 1}'
    assert response.closed


@pytest.mark.parametrize("url", [LITELLM_URL, OPENROUTER_URL])
def test_both_fixed_urls_are_allowed(url: str) -> None:
    opener = FakeOpener(FakeResponse(b"{}"))
    assert fetch(opener, url) == b"{}"
    assert opener.requests[0].full_url == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/prices.json",
        "http://raw.githubusercontent.com/BerriAI/litellm/main/"
        "model_prices_and_context_window.json",
        LITELLM_URL + "?x=1",
        "file:///etc/passwd",
        "",
    ],
)
def test_any_other_url_is_refused_before_the_opener_runs(url: str) -> None:
    opener = FakeOpener(FakeResponse(b"{}"))
    assert reason(opener, url) == "fetch_failed"
    assert opener.requests == []


def test_both_urls_are_https() -> None:
    assert LITELLM_URL.startswith("https://")
    assert OPENROUTER_URL.startswith("https://")
    assert {LITELLM_URL, OPENROUTER_URL} == price_transport.ALLOWED_URLS


def test_sends_a_custom_user_agent_and_no_cookie_header() -> None:
    opener = FakeOpener(FakeResponse(b"{}"))
    fetch(opener)
    request = opener.requests[0]
    agent = request.get_header("User-agent")
    assert agent is not None
    assert agent.startswith("BarTab/")
    assert "python-urllib" not in agent.lower()
    assert not request.has_header("Cookie")
    assert request.get_method() == "GET"
    assert request.data is None


def test_passes_the_timeout_to_the_opener() -> None:
    opener = FakeOpener(FakeResponse(b"{}"))
    UrllibTransport(opener).fetch(LITELLM_URL, timeout=7.5, max_bytes=100)
    assert opener.timeouts == [7.5]


def test_the_default_timeout_is_ten_seconds() -> None:
    assert price_transport.DEFAULT_TIMEOUT == 10.0


def test_a_body_exactly_at_the_cap_is_returned() -> None:
    assert len(fetch(FakeOpener(FakeResponse(b"x" * 1000)), max_bytes=1000)) == 1000


def test_a_body_one_byte_over_the_cap_is_refused() -> None:
    assert reason(FakeOpener(FakeResponse(b"x" * 1001)), max_bytes=1000) == "too_large"


def test_reads_at_most_the_cap_plus_one_byte() -> None:
    response = FakeResponse(b"x" * 500_000)
    assert reason(FakeOpener(response), max_bytes=1000) == "too_large"
    assert response.served == 1001
    assert response.closed


def test_a_declared_length_over_the_cap_is_refused_without_reading() -> None:
    response = FakeResponse(b"x" * 10, headers={"Content-Length": "5000"})
    assert reason(FakeOpener(response), max_bytes=1000) == "too_large"
    assert response.served == 0


def test_a_junk_content_length_is_ignored() -> None:
    response = FakeResponse(b"{}", headers={"Content-Length": "lots"})
    assert fetch(FakeOpener(response)) == b"{}"


def test_a_slow_connection_is_a_timeout() -> None:
    assert reason(FakeOpener(TimeoutError())) == "timeout"


def test_a_url_error_that_wraps_a_timeout_is_a_timeout() -> None:
    assert reason(FakeOpener(urllib.error.URLError(TimeoutError()))) == "timeout"


def test_a_timeout_in_the_middle_of_the_body_is_a_timeout() -> None:
    assert reason(FakeOpener(FakeResponse(read_error=TimeoutError()))) == "timeout"


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("no route"),
        urllib.error.HTTPError(LITELLM_URL, 403, "Forbidden", Message(), None),
        ConnectionResetError(),
        OSError("boom"),
    ],
)
def test_other_network_errors_are_fetch_failed(error: BaseException) -> None:
    assert reason(FakeOpener(error)) == "fetch_failed"


def test_a_read_error_in_the_middle_of_the_body_is_fetch_failed() -> None:
    response = FakeResponse(read_error=ConnectionResetError())
    assert reason(FakeOpener(response)) == "fetch_failed"


@pytest.mark.parametrize("status", [204, 301, 403, 404, 500])
def test_a_status_other_than_200_is_fetch_failed(status: int) -> None:
    assert reason(FakeOpener(FakeResponse(b"{}", status=status))) == "fetch_failed"


def test_a_fetch_error_from_the_opener_passes_through() -> None:
    assert reason(FakeOpener(FetchError("redirect_refused"))) == "redirect_refused"


def test_a_fetch_error_carries_only_its_code() -> None:
    error = FetchError("timeout")
    assert error.reason_code == "timeout"
    assert str(error) == "timeout"


# --- the redirect handler -------------------------------------------------


def redirect(newurl: str, old: str = LITELLM_URL) -> urllib.request.Request | None:
    return SameHostRedirect().redirect_request(
        urllib.request.Request(old),  # noqa: S310
        io.BytesIO(b""),
        302,
        "Found",
        HTTPMessage(),
        newurl,
    )


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/model_prices_and_context_window.json",
        "https://raw.githubusercontent.com.evil.example/x.json",
        "https://github.com/BerriAI/litellm/raw/main/x.json",
        "http://raw.githubusercontent.com/BerriAI/litellm/main/x.json",
        "ftp://raw.githubusercontent.com/x.json",
    ],
)
def test_a_redirect_to_another_host_or_scheme_is_refused(target: str) -> None:
    with pytest.raises(FetchError) as caught:
        redirect(target)
    assert caught.value.reason_code == "redirect_refused"


def test_a_redirect_on_the_same_host_is_followed() -> None:
    target = "https://raw.githubusercontent.com/BerriAI/litellm/other/x.json"
    followed = redirect(target)
    assert followed is not None
    assert followed.full_url == target


def test_the_opener_has_the_handler_and_no_cookie_processor() -> None:
    opener = price_transport.build_opener()
    handlers: list[object] = cast("Any", opener).handlers
    assert any(isinstance(h, SameHostRedirect) for h in handlers)
    assert not any(isinstance(h, urllib.request.HTTPCookieProcessor) for h in handlers)


class _CannedHTTPS(urllib.request.HTTPSHandler):
    """Answers every HTTPS request from a script, so no socket opens."""

    def __init__(self, script: Callable[[urllib.request.Request], Any]) -> None:
        super().__init__()
        self._script = script
        self.seen: list[str] = []

    def https_open(self, req: urllib.request.Request) -> Any:
        self.seen.append(req.full_url)
        return self._script(req)


def _canned(code: int, headers: dict[str, str], body: bytes = b"") -> Any:
    message = HTTPMessage()
    for key, value in headers.items():
        message[key] = value
    response = urllib.response.addinfourl(io.BytesIO(body), message, "x", code)
    response.msg = "canned"  # pyright: ignore[reportAttributeAccessIssue]
    return response


def test_a_redirect_to_another_host_through_the_real_opener_is_refused() -> None:
    canned = _CannedHTTPS(
        lambda _req: _canned(302, {"Location": "https://evil.example/prices.json"})
    )
    transport = UrllibTransport(price_transport.build_opener(canned))
    with pytest.raises(FetchError) as caught:
        transport.fetch(LITELLM_URL, timeout=10.0, max_bytes=1000)
    assert caught.value.reason_code == "redirect_refused"
    assert canned.seen == [LITELLM_URL]


def test_a_same_host_redirect_through_the_real_opener_reaches_the_body() -> None:
    moved = "https://raw.githubusercontent.com/BerriAI/litellm/main/moved.json"

    def script(req: urllib.request.Request) -> Any:
        if req.full_url == LITELLM_URL:
            return _canned(301, {"Location": moved})
        return _canned(200, {}, b'{"ok": true}')

    canned = _CannedHTTPS(script)
    transport = UrllibTransport(price_transport.build_opener(canned))
    assert transport.fetch(LITELLM_URL, timeout=10.0, max_bytes=1000) == b'{"ok": true}'
    assert canned.seen == [LITELLM_URL, moved]


def test_the_user_agent_survives_a_redirect_through_the_real_opener() -> None:
    moved = "https://raw.githubusercontent.com/BerriAI/litellm/main/moved.json"
    agents: list[str | None] = []

    def script(req: urllib.request.Request) -> Any:
        agents.append(req.get_header("User-agent"))
        if req.full_url == LITELLM_URL:
            return _canned(301, {"Location": moved})
        return _canned(200, {}, b"{}")

    transport = UrllibTransport(price_transport.build_opener(_CannedHTTPS(script)))
    transport.fetch(LITELLM_URL, timeout=10.0, max_bytes=1000)
    assert agents == [price_transport.USER_AGENT, price_transport.USER_AGENT]

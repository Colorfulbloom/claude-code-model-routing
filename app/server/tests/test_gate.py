"""Tests for the ASGI gate. They assert refusal (a 4xx), not exact codes."""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.types import ASGIApp

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import timing_policy

import gate
import main
from access import AccessState

PORT = 47123
AsgiCaller = Any
SWAP_BODY = json.dumps({"code": "no-such-code"}).encode()
GOOD_ORIGIN = f"http://127.0.0.1:{PORT}"


def _is_refused(status: int) -> bool:
    return 400 <= status < 500


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({"Host": "evil.example"}, id="host-other"),
        pytest.param({"Host": f"evil.example:{PORT}"}, id="host-other-with-port"),
        pytest.param({"Host": "127.0.0.1:1"}, id="host-wrong-port"),
        pytest.param({"Host": "127.0.0.1"}, id="host-no-port"),
    ],
)
def test_bad_host_is_refused(
    client: Any, key_headers: dict[str, str], headers: dict[str, str]
) -> None:
    response = client.get("/api/app", headers={**key_headers, **headers})
    assert _is_refused(response.status_code)
    assert "evil" not in response.text


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        f"http://evil.example:{PORT}",
        f"https://127.0.0.1:{PORT}",
        "http://127.0.0.1:1",
        "null",
    ],
)
def test_bad_origin_is_refused(
    client: Any, origin: str, key_headers: dict[str, str]
) -> None:
    post = client.post(
        "/api/access/swap", content=SWAP_BODY, headers={"Origin": origin}
    )
    get = client.get("/api/app", headers={**key_headers, "Origin": origin})
    assert _is_refused(post.status_code)
    assert _is_refused(get.status_code)
    assert "evil" not in post.text


@pytest.mark.parametrize("site", ["cross-site", "same-site", "bogus"])
def test_cross_site_fetch_is_refused(
    client: Any, key_headers: dict[str, str], site: str
) -> None:
    response = client.get("/api/app", headers={**key_headers, "Sec-Fetch-Site": site})
    assert _is_refused(response.status_code)


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_same_origin_fetch_passes(
    client: Any, key_headers: dict[str, str], site: str
) -> None:
    response = client.get("/api/app", headers={**key_headers, "Sec-Fetch-Site": site})
    assert response.status_code == 200


def test_localhost_host_and_origin_pass(
    client: Any, key_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/app",
        headers={
            **key_headers,
            "Host": f"localhost:{PORT}",
            "Origin": f"http://localhost:{PORT}",
        },
    )
    assert response.status_code == 200


def test_browser_post_without_origin_is_refused(client: Any) -> None:
    response = client.post(
        "/api/access/swap",
        content=SWAP_BODY,
        headers={"Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"},
    )
    assert _is_refused(response.status_code)


def test_post_without_origin_or_fetch_site_passes(client: Any) -> None:
    response = client.post(
        "/api/access/swap",
        content=SWAP_BODY,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "code_unknown"


@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data", ""],
)
def test_post_with_wrong_content_type_is_refused(
    client: Any, content_type: str
) -> None:
    headers = {"Content-Type": content_type} if content_type else {}
    response = client.post(
        "/api/access/swap",
        content=SWAP_BODY,
        headers={**headers, "Origin": GOOD_ORIGIN},
    )
    assert _is_refused(response.status_code)


def test_json_content_type_with_charset_passes(client: Any) -> None:
    response = client.post(
        "/api/access/swap",
        content=SWAP_BODY,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert response.status_code == 403


def test_body_over_cap_is_refused(client: Any) -> None:
    big = json.dumps({"code": "x" * (gate.BODY_CAP + 10)}).encode()
    response = client.post(
        "/api/access/swap",
        content=big,
        headers={"Content-Type": "application/json", "Origin": GOOD_ORIGIN},
    )
    assert _is_refused(response.status_code)


@pytest.mark.parametrize("method", ["DELETE", "PUT", "PATCH", "OPTIONS"])
def test_other_methods_are_refused(
    client: Any, key_headers: dict[str, str], method: str
) -> None:
    response = client.request(method, "/api/app", headers=key_headers)
    assert _is_refused(response.status_code)


def test_get_with_a_body_is_refused(client: Any, key_headers: dict[str, str]) -> None:
    response = client.request("GET", "/api/app", headers=key_headers, content=b"x")
    assert _is_refused(response.status_code)


@pytest.mark.parametrize("path", ["/api/app", "/api/projects", "/api/unknown"])
@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="missing"),
        pytest.param({"X-Bartab-Key": ""}, id="empty"),
        pytest.param({"X-Bartab-Key": "wrong"}, id="wrong"),
        pytest.param({"X-Bartab-Mint": "wrong"}, id="mint-secret-is-not-a-key"),
    ],
)
def test_missing_or_wrong_key_is_refused(
    client: Any, path: str, headers: dict[str, str]
) -> None:
    response = client.get(path, headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] in {"no_key", "bad_key"}


def test_read_key_is_not_the_mint_secret(
    client: Any, key_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/access/mint",
        json={"project": None},
        headers={**key_headers, "Origin": GOOD_ORIGIN},
    )
    assert response.status_code == 401


def test_duplicate_key_header_is_refused(
    app: ASGIApp, asgi_call: AsgiCaller, state: AccessState
) -> None:
    result = asyncio.run(
        asgi_call(
            app,
            path="/api/app",
            headers=[
                ("host", f"127.0.0.1:{PORT}"),
                ("x-bartab-key", state.read_key),
                ("x-bartab-key", state.read_key),
            ],
        )
    )
    assert result.status is not None
    assert _is_refused(result.status)


def test_duplicate_host_is_refused(app: ASGIApp, asgi_call: AsgiCaller) -> None:
    result = asyncio.run(
        asgi_call(
            app,
            path="/",
            headers=[("host", f"127.0.0.1:{PORT}"), ("host", f"127.0.0.1:{PORT}")],
        )
    )
    assert result.status is not None
    assert _is_refused(result.status)


def test_static_and_index_need_no_key(client: Any) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200


def test_swap_needs_no_key(client: Any) -> None:
    response = client.post("/api/access/swap", json={"code": "00000000.x"})
    assert response.status_code == 403


def test_mint_needs_the_secret(client: Any, state: AccessState) -> None:
    refused = client.post("/api/access/mint", json={"project": None})
    wrong = client.post(
        "/api/access/mint",
        json={"project": None},
        headers={"X-Bartab-Mint": "wrong"},
    )
    allowed = client.post(
        "/api/access/mint",
        json={"project": None},
        headers={"X-Bartab-Mint": state.mint_secret},
    )
    assert refused.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 200


def _post_headers(extra: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    base = [
        ("host", f"127.0.0.1:{PORT}"),
        ("origin", GOOD_ORIGIN),
        ("content-type", "application/json"),
    ]
    return base + (extra or [])


def test_short_body_that_never_completes_is_refused_within_about_3_seconds(
    app: ASGIApp, asgi_call: AsgiCaller
) -> None:
    started = time.monotonic()
    result = asyncio.run(
        asgi_call(
            app,
            method="POST",
            path="/api/access/swap",
            headers=_post_headers([("content-length", "40")]),
            messages=[{"type": "http.request", "body": b'{"co', "more_body": True}],
            hang=True,
        )
    )
    elapsed = time.monotonic() - started
    assert result.status is not None
    assert _is_refused(result.status)
    # The gate's own timer is 3 s, so this is a wait, not CPU work (see timing_policy).
    assert elapsed < timing_policy.wait_limit(4.0)


def test_body_timeout_is_configurable(
    app: ASGIApp, asgi_call: AsgiCaller, state: AccessState
) -> None:
    quick = gate.GateMiddleware(app, PORT, state, body_timeout=0.05)
    started = time.monotonic()
    result = asyncio.run(
        asgi_call(
            quick,
            method="POST",
            path="/api/access/swap",
            headers=_post_headers([("content-length", "40")]),
            hang=True,
        )
    )
    assert result.status == 408
    assert time.monotonic() - started < timing_policy.wait_limit(1.0)


@pytest.mark.parametrize(
    ("extra", "messages"),
    [
        pytest.param([], [], id="no-content-length"),
        pytest.param([("content-length", "abc")], [], id="non-numeric-length"),
        pytest.param([("content-length", "+7")], [], id="signed-length"),
        pytest.param([("content-length", "0x7")], [], id="hex-length"),
        pytest.param(
            [("content-length", "7"), ("content-length", "7")], [], id="two-lengths"
        ),
        pytest.param(
            [("content-length", "7"), ("transfer-encoding", "chunked")],
            [],
            id="chunked",
        ),
        pytest.param(
            [("content-length", "7")],
            [{"type": "http.disconnect"}],
            id="client-leaves-early",
        ),
        pytest.param(
            [("content-length", "3")],
            [{"type": "http.request", "body": b"abcdef", "more_body": False}],
            id="body-longer-than-declared",
        ),
        pytest.param(
            [("content-length", "100000")],
            [],
            id="declared-over-cap",
        ),
    ],
)
def test_bad_body_framing_is_refused(
    app: ASGIApp,
    asgi_call: AsgiCaller,
    extra: list[tuple[str, str]],
    messages: list[dict[str, object]],
) -> None:
    result = asyncio.run(
        asgi_call(
            app,
            method="POST",
            path="/api/access/swap",
            headers=_post_headers(extra),
            messages=messages,  # type: ignore[arg-type]
        )
    )
    assert result.status is not None
    assert _is_refused(result.status)


def test_streamed_body_over_cap_is_refused(app: ASGIApp, asgi_call: AsgiCaller) -> None:
    chunk = b"x" * 40_000
    result = asyncio.run(
        asgi_call(
            app,
            method="POST",
            path="/api/access/swap",
            headers=_post_headers([("content-length", str(gate.BODY_CAP))]),
            messages=[
                {"type": "http.request", "body": chunk, "more_body": True},
                {"type": "http.request", "body": chunk, "more_body": True},
            ],
        )
    )
    assert result.status == 413


def test_refusal_is_small_json_that_closes_the_connection(
    client: Any,
) -> None:
    response = client.get("/api/app", headers={"Host": "marker.example"})
    assert response.headers["content-type"] == "application/json"
    assert response.headers["connection"] == "close"
    assert response.json() == {"code": "bad_host", "path": None}
    assert "marker" not in response.text


def test_websocket_is_closed(app: ASGIApp) -> None:
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    asyncio.run(app({"type": "websocket", "path": "/ws", "headers": []}, receive, send))  # type: ignore[arg-type]
    assert sent == [{"type": "websocket.close", "code": 1008}]


def test_port_constant_matches_the_settings_fixture(settings: main.Settings) -> None:
    assert settings.port == PORT

"""Tests for the error envelope. It must not echo input or file paths."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI

import main
from access import AccessState
from csp import SecurityHeadersMiddleware
from gate import GateMiddleware

SECRET_TEXT = "/work/secret-folder/notes.txt"  # noqa: S105


def test_422_has_no_input_and_no_path_text(client: Any) -> None:
    response = client.post(
        "/api/access/swap",
        json={"code": 5, SECRET_TEXT: SECRET_TEXT},
    )
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"code", "path"}
    assert body["code"] == "invalid_request"
    assert "input" not in response.text
    assert "secret-folder" not in response.text
    assert "notes.txt" not in response.text


def test_extra_field_name_is_not_echoed(client: Any) -> None:
    response = client.post("/api/access/swap", json={"code": "x", "evil_name": 1})
    assert response.status_code == 422
    assert "evil_name" not in response.text
    assert response.json()["path"] == ["body"]


def test_wrong_type_names_the_field(client: Any) -> None:
    response = client.post("/api/access/swap", json={"code": 5})
    assert response.json() == {"code": "invalid_request", "path": ["body", "code"]}


def test_query_value_is_not_echoed(client: Any, key_headers: dict[str, str]) -> None:
    response = client.get(
        "/api/app", params={"project": SECRET_TEXT}, headers=key_headers
    )
    assert response.status_code == 422
    assert "secret-folder" not in response.text
    assert response.json()["path"] == ["query", "project"]


def test_malformed_json_body_is_422_without_text(client: Any) -> None:
    response = client.post(
        "/api/access/swap",
        content=b'{"code": "/work/secret-folder',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "secret-folder" not in response.text


def test_method_not_allowed_uses_the_envelope(
    client: Any, key_headers: dict[str, str]
) -> None:
    response = client.post("/api/app", json={}, headers=key_headers)
    assert response.status_code == 405
    assert response.json() == {"code": "method_not_allowed", "path": None}


def test_unexpected_error_leaks_nothing(
    tmp_path: Path, dist_dir: Path, state: AccessState, open_client: Any
) -> None:
    settings = main.Settings(
        port=47123,
        data_dir=tmp_path / "data",
        dist_dir=dist_dir,
        access_state=state,
    )
    fastapi_app: FastAPI = main.build_app(settings)

    @fastapi_app.get("/api/boom")
    def boom() -> None:
        msg = f"cannot read {SECRET_TEXT}"
        raise RuntimeError(msg)

    # The catch-all static route was added first, so move the new route ahead of it.
    fastapi_app.router.routes.insert(0, fastapi_app.router.routes.pop())
    wrapped = GateMiddleware(SecurityHeadersMiddleware(fastapi_app), 47123, state)
    with open_client(wrapped) as test:
        response = test.get("/api/boom", headers={"X-Bartab-Key": state.read_key})
    assert response.status_code == 500
    assert response.json() == {"code": "internal_error", "path": None}
    assert "secret-folder" not in response.text


def test_not_found_does_not_echo_the_path(
    client: Any, key_headers: dict[str, str]
) -> None:
    response = client.get(f"/api/{SECRET_TEXT.strip('/')}", headers=key_headers)
    assert response.status_code == 404
    assert "secret-folder" not in response.text

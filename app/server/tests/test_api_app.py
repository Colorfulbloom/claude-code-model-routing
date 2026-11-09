"""Tests for the app-wide reads and for the key rule on every route."""

import re
from typing import Any

import pytest

import main

PATH_PARAM = re.compile(r"\{[^}]+\}")


def _operations(settings: main.Settings) -> list[tuple[str, str, dict[str, Any]]]:
    """Walk every route the app declares, as (path, METHOD, operation).

    FastAPI 0.162 keeps included routers lazy, so ``app.routes`` holds only private
    wrapper objects. The generated schema lists every included route.
    """
    schema = main.build_app(settings).openapi()
    return [
        (path, method.upper(), operation)
        for path, methods in schema["paths"].items()
        if path.startswith("/api")
        for method, operation in methods.items()
    ]


def test_route_walk_finds_the_expected_routes(settings: main.Settings) -> None:
    found = {(path, method) for path, method, _ in _operations(settings)}
    assert found >= {
        ("/api/app", "GET"),
        ("/api/projects", "GET"),
        ("/api/access/swap", "POST"),
        ("/api/access/mint", "POST"),
    }


def test_every_get_under_api_needs_the_key(
    client: Any, settings: main.Settings, key_headers: dict[str, str]
) -> None:
    gets = [path for path, method, _ in _operations(settings) if method == "GET"]
    assert gets
    for route in gets:
        url = PATH_PARAM.sub("x", route)
        assert client.get(url).status_code == 401, route
        assert client.get(url, headers={"X-Bartab-Key": "wrong"}).status_code == 401
        assert client.get(url, headers=key_headers).status_code != 401, route


def test_every_post_except_swap_needs_a_secret(
    client: Any, settings: main.Settings, key_headers: dict[str, str]
) -> None:
    posts = [
        path
        for path, method, _ in _operations(settings)
        if method == "POST" and path != "/api/access/swap"
    ]
    assert posts
    for route in posts:
        url = PATH_PARAM.sub("x", route)
        assert client.post(url, json={}).status_code == 401, route
        assert client.post(url, json={}, headers=key_headers).status_code == 401


def test_every_api_route_declares_a_response_model(settings: main.Settings) -> None:
    for path, method, operation in _operations(settings):
        content = operation["responses"]["200"]["content"]["application/json"]
        assert "$ref" in content["schema"], f"{method} {path}"


def test_get_app_demo(client: Any, key_headers: dict[str, str]) -> None:
    response = client.get(
        "/api/app", params={"project": "tidewater-reporting"}, headers=key_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "server_time",
        "instance",
        "claude_version",
        "ingest",
        "running",
        "to_fix_count",
        "editable_projects",
    }
    assert body["claude_version"] == "2.1.310"
    assert body["to_fix_count"] == 4
    assert body["ingest"]["state"] == "done"
    assert body["running"] == [
        {"project": "tidewater-reporting", "session": "a1b2c3d4"}
    ]
    assert body["editable_projects"] == []
    assert body["server_time"].startswith("1970-01-12T")


def test_get_app_without_project_has_null_count(
    client: Any, key_headers: dict[str, str]
) -> None:
    body = client.get("/api/app", headers=key_headers).json()
    assert body["to_fix_count"] is None


@pytest.mark.parametrize(
    ("project", "count"),
    [("saltmarsh", 0), ("driftwood", 0), ("not-in-fixture", None)],
)
def test_to_fix_count_per_project(
    client: Any,
    key_headers: dict[str, str],
    project: str,
    count: int | None,
) -> None:
    body = client.get(
        "/api/app", params={"project": project}, headers=key_headers
    ).json()
    assert body["to_fix_count"] == count


@pytest.mark.parametrize("project", ["", "UPPER", "-lead", "a" * 64, "has space"])
def test_bad_project_key_is_422(
    client: Any, key_headers: dict[str, str], project: str
) -> None:
    response = client.get("/api/app", params={"project": project}, headers=key_headers)
    assert response.status_code == 422


def test_get_projects_demo(client: Any, key_headers: dict[str, str]) -> None:
    body = client.get("/api/projects", headers=key_headers).json()
    projects = body["projects"]
    assert [p["key"] for p in projects] == [
        "tidewater-reporting",
        "saltmarsh",
        "driftwood",
    ]
    assert [p["state"] for p in projects] == [
        "ok",
        "no_claude_folder",
        "folder_not_found",
    ]
    assert [p["running"] for p in projects] == [True, False, False]
    for project in projects:
        assert set(project) == {"key", "name", "display_path", "state", "running"}
        assert project["display_path"].startswith("/work/")

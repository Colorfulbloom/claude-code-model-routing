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
        ("/api/prices", "GET"),
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
        schema = content["schema"]
        refs = schema.get("anyOf", [schema])
        assert all("$ref" in item for item in refs), f"{method} {path}"


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
        "as_of",
        "pass_running_since",
        "etag",
        "ingest",
        "history",
        "running",
        "to_fix_count",
        "to_fix",
        "editable_projects",
        "mode",
        "clock",
    }
    assert body["to_fix"] == {"state": "ok", "count": 4, "etag": None}
    assert body["mode"] == "fixture"
    assert body["clock"] == {"kind": "real", "rate_n": None}
    assert body["claude_version"] == "2.1.310"
    assert body["to_fix_count"] == 4
    assert body["ingest"]["state"] == "done"
    assert body["running"] == [
        {"project": "tidewater-reporting", "session": "a1b2c3d4"}
    ]
    assert body["editable_projects"] == []
    assert body["server_time"].startswith("1970-01-12T")
    assert set(body["ingest"]) == {
        "state",
        "files_done",
        "files_total",
        "bytes_done",
        "bytes_total",
        "error",
        "retrying",
        "retry_at",
    }
    assert set(body["history"]) == {
        "oldest",
        "first_ingest",
        "last_backup",
        "backup_failed",
        "pass_error",
        "unreadable_files",
        "kept_files",
        "no_usage_rows",
    }
    assert body["as_of"] is not None
    assert body["pass_running_since"] is None
    assert body["etag"]
    assert body["history"]["pass_error"] is None


def test_get_app_without_project_has_null_count(
    client: Any, key_headers: dict[str, str]
) -> None:
    body = client.get("/api/app", headers=key_headers).json()
    assert body["to_fix_count"] is None
    assert body["to_fix"] == {"state": "unchecked", "count": None, "etag": None}


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
    assert body["to_fix"]["count"] == count
    assert body["to_fix"]["state"] == ("unchecked" if count is None else "ok")


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
        assert set(project) == {
            "key",
            "name",
            "display_path",
            "state",
            "running",
            "listed",
        }
        assert project["listed"] is True
        assert project["display_path"].startswith("/work/")


def test_get_prices_demo(client: Any, key_headers: dict[str, str]) -> None:
    body = client.get("/api/prices", headers=key_headers).json()
    assert set(body) == {"source", "as_of", "etag", "cross_check", "models"}
    assert body["source"] == "litellm"
    assert body["as_of"] == "2026-10-28"
    assert body["cross_check"] == {"state": "agree", "models": []}
    first = body["models"][0]
    assert set(first) == {
        "model",
        "source",
        "input",
        "output",
        "cache_read",
        "cache_write_5m",
        "cache_write_1h",
        "tiers",
        "modifiers",
        "relative",
    }
    assert isinstance(first["input"], float)
    tiers = [t for m in body["models"] for t in m["tiers"]]
    assert tiers
    assert set(tiers[0]) == {
        "prompt_tokens_over",
        "input",
        "output",
        "cache_read",
        "cache_write_5m",
        "cache_write_1h",
    }


def test_get_prices_needs_the_key(client: Any) -> None:
    assert client.get("/api/prices").status_code == 401

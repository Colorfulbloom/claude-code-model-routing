"""Tests for the Setup routes, over the real app with a fixture provider.

The provider reads a corpus case (``corpus_world``) or the demo build with the setup
overlay applied (``demo_world``). The store-backed answers (usage, unreadable
transcripts, plugin agents that ran) are in ``test_setup_store.py``.
"""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_api_helpers as sah

import fixture_provider
from models import SETUP_PARTS

PROJECT = "proj"


@pytest.fixture(scope="module")
def complex_api(tmp_path_factory: pytest.TempPathFactory) -> Iterator[sah.Api]:
    base = tmp_path_factory.mktemp("api-complex")
    world = fixture_provider.corpus_world("complex", base / "w")
    with sah.served(world, base) as api:
        yield api


@pytest.fixture(scope="module")
def demo_api(
    tmp_path_factory: pytest.TempPathFactory, demo_build: Path
) -> Iterator[sah.Api]:
    demo = sah.overlaid_demo(tmp_path_factory, demo_build)
    base = tmp_path_factory.mktemp("api-demo")
    with sah.served(fixture_provider.demo_world(demo), base) as api:
        yield api


def path(route: str, project: str = PROJECT, **more: str) -> str:
    query = "&".join(f"{k}={v}" for k, v in {"project": project, **more}.items())
    return f"/api/{route}?{query}"


# ------------------------------------------------------------------ the shapes


def test_setup_answers_the_map(complex_api: sah.Api) -> None:
    body = complex_api.ok(path("setup"))
    assert set(body) == {
        "project",
        "server_time",
        "as_of",
        "etag",
        "unchanged",
        "parts",
        "notices",
        "server_started_at",
        "listed",
    }
    assert body["project"] == PROJECT
    assert body["unchanged"] is False
    assert body["listed"] is True
    assert [p["part"] for p in body["parts"]] == list(SETUP_PARTS)
    first = body["parts"][0]
    assert set(first) == {
        "part",
        "summary",
        "statuses",
        "counted_problems",
        "unreadable",
        "empty",
        "scopes",
    }
    assert len(first["scopes"]) == 7


def test_setup_part_answers_items_groups_unreadable_and_empty(
    complex_api: sah.Api,
) -> None:
    for part in SETUP_PARTS:
        body = complex_api.ok(path(f"setup/{part}"))
        assert set(body) == {
            "project",
            "server_time",
            "as_of",
            "etag",
            "unchanged",
            "part",
            "items",
            "groups",
            "unreadable",
            "empty",
        }
        assert body["part"] == part
        assert all(item["part"] == part for item in body["items"])
        assert [i["order"] for i in body["items"]] == list(range(len(body["items"])))


def test_problems_answers_rows_and_the_counted_total(complex_api: sah.Api) -> None:
    body = complex_api.ok(path("problems"))
    assert set(body) == {
        "project",
        "server_time",
        "as_of",
        "etag",
        "unchanged",
        "rows",
        "counted",
    }
    assert body["counted"] == 2
    assert {r["code"] for r in body["rows"]} == {"plugin_field_ignored"}
    row = body["rows"][0]
    assert set(row) == {
        "id",
        "kind",
        "group",
        "code",
        "thing",
        "part",
        "item_id",
        "file",
        "full_path",
        "line",
        "params",
        "confidence",
        "fix",
    }


def test_the_three_answers_share_one_etag_and_app_repeats_it(
    complex_api: sah.Api,
) -> None:
    etags = {
        complex_api.ok(path("setup"))["etag"],
        complex_api.ok(path("setup/agents"))["etag"],
        complex_api.ok(path("problems"))["etag"],
    }
    assert len(etags) == 1
    app = complex_api.ok(path("app").replace("/api/app", "/api/app"))
    assert app["to_fix"] == {"state": "ok", "count": 2, "etag": etags.pop()}
    assert app["to_fix_count"] == 2


# ----------------------------------------------------------------------- etag


@pytest.mark.parametrize("route", ["setup", "setup/mcp", "problems"])
def test_a_matching_etag_gets_the_short_answer(
    complex_api: sah.Api, route: str
) -> None:
    etag = complex_api.ok(path(route))["etag"]
    short = complex_api.ok(path(route, etag=etag))
    assert set(short) == {"project", "server_time", "etag", "unchanged"}
    assert short["unchanged"] is True
    assert short["etag"] == etag
    stale = complex_api.ok(path(route, etag="stale"))
    assert stale["unchanged"] is False


# --------------------------------------------------------------------- errors


@pytest.mark.parametrize("route", ["setup", "setup/skills", "problems"])
def test_a_missing_or_repeated_project_is_bad_request(
    complex_api: sah.Api, route: str
) -> None:
    missing = complex_api.get(f"/api/{route}")
    assert missing.status_code == 400
    assert missing.json() == {"code": "bad_request", "path": ["query", "project"]}
    twice = complex_api.get(f"/api/{route}?project=proj&project=proj")
    assert twice.status_code == 400
    assert twice.json()["path"] == ["query", "project"]


@pytest.mark.parametrize("route", ["setup", "setup/skills", "problems"])
def test_a_repeated_etag_is_bad_request(complex_api: sah.Api, route: str) -> None:
    reply = complex_api.get(f"/api/{route}?project=proj&etag=a&etag=b")
    assert reply.status_code == 400
    assert reply.json() == {"code": "bad_request", "path": ["query", "etag"]}


@pytest.mark.parametrize("route", ["setup", "setup/skills", "problems"])
def test_an_unknown_project_is_404(complex_api: sah.Api, route: str) -> None:
    reply = complex_api.get(f"/api/{route}?project=nope")
    assert reply.status_code == 404
    assert reply.json() == {"code": "unknown_project", "path": None}


@pytest.mark.parametrize("name", ["settings2", "Agents", "agent", "x"])
def test_an_unknown_part_is_404(complex_api: sah.Api, name: str) -> None:
    reply = complex_api.get(f"/api/setup/{name}?project=proj")
    assert reply.status_code == 404
    assert reply.json() == {"code": "unknown_part", "path": None}


def test_a_bad_project_key_or_etag_is_422(complex_api: sah.Api) -> None:
    assert complex_api.get("/api/setup?project=UPPER").status_code == 422
    assert complex_api.get("/api/setup?project=proj&etag=%20").status_code == 422


def test_the_routes_need_the_read_key() -> None:
    # The gate answers 401 before a route runs (see test_gate); here the schema only.
    from main import Settings, build_app

    app = build_app(
        Settings(port=1, data_dir=Path("/work/d"), dist_dir=Path("/work/x"))
    )
    paths = app.openapi()["paths"]
    for route in ("/api/setup", "/api/setup/{part}", "/api/problems"):
        assert "get" in paths[route]


def test_a_provider_without_a_setup_world_answers_unknown_project(
    tmp_path: Path,
) -> None:
    base = tmp_path
    with sah.served(fixture_provider.SetupWorld({}), base) as api:
        for route in ("setup", "setup/agents", "problems"):
            assert (
                api.get(path(route, project="tidewater-reporting")).status_code == 404
            )


def test_an_unlisted_project_reads_not_read_here_with_a_notice(
    tmp_path: Path,
) -> None:
    world = fixture_provider.corpus_world("scope-unlisted", tmp_path / "w")
    with sah.served(world, tmp_path) as api:
        body = api.ok(path("setup"))
        assert body["listed"] is False
        # The fixture scenario reports 2.1.310, so the version gap follows.
        assert [n["code"] for n in body["notices"]] == [
            "project_not_listed",
            "version_gap",
        ]
        assert body["notices"][1]["params"]["due"] == "84"
        for part in body["parts"]:
            cells = {c["scope"]: c["state"] for c in part["scopes"]}
            assert cells["project"] == "not_visible"
            assert cells["project_local"] == "not_visible"
        perms = api.ok(path("setup/permissions"))
        assert all(
            s["scope"] not in ("project", "project_local")
            for item in perms["items"]
            for s in item["sources"]
        )


# ----------------------------------------------------------------- the demo


def test_the_demo_has_eight_projects_and_every_one_answers(demo_api: sah.Api) -> None:
    keys = set(demo_api.provider._world.contexts)  # pyright: ignore[reportPrivateUsage, reportOptionalMemberAccess]
    assert {"setup-empty", "setup-broken", "setup-large"} <= keys
    assert len(keys) == 8
    for key in sorted(keys):
        assert demo_api.ok(path("setup", key))["listed"] is True
        assert demo_api.ok(path("problems", key))["etag"]


def test_the_empty_demo_project_has_empty_states_to_act_on(demo_api: sah.Api) -> None:
    body = demo_api.ok(path("setup", "setup-empty"))
    empties = {p["part"]: p["empty"] for p in body["parts"] if p["empty"]}
    # The user's own files still show, so only the part nothing sets is empty.
    assert set(empties) == {"output_style"}
    assert empties["output_style"]["reason"] == "none_found"
    assert empties["output_style"]["action"] == "copy_path"
    assert empties["output_style"]["target"].endswith(
        "projects/setup-empty/.claude/output-styles"
    )
    # Its only finding is the user file's effortLevel, which Opus 5.5 ignores (Not as
    # set). The shell's empty CLAUDE_CODE_EFFORT_LEVEL is the same as unset, so it adds
    # no row of its own.
    feed = demo_api.ok(path("problems", "setup-empty"))
    assert [(r["code"], r["group"], r["params"]["key"]) for r in feed["rows"]] == [
        ("ignored", "not_as_set", "effortLevel")
    ]
    assert feed["counted"] == len(feed["rows"]) == 1


def test_the_broken_demo_project_lists_its_problems(demo_api: sah.Api) -> None:
    rows = demo_api.ok(path("problems", "setup-broken"))["rows"]
    codes = {r["code"] for r in rows}
    assert {"json_invalid", "mcp_bad_entry", "import_missing"} <= codes
    assert "frontmatter_invalid" in codes
    assert demo_api.ok(path("problems", "setup-broken"))["counted"] == len(
        [r for r in rows if r["group"] in ("couldnt_read", "wont_load", "not_as_set")]
    )


def test_the_large_demo_project_answers_every_part(demo_api: sah.Api) -> None:
    perms = demo_api.ok(path("setup/permissions", "setup-large"))
    assert len(perms["items"]) >= 120
    assert perms["groups"][0]["key"] == "deny"
    agents = demo_api.ok(path("setup/agents", "setup-large"))
    assert len(agents["items"]) >= 40


def test_the_demo_user_and_local_mcp_servers_show_their_remove_command(
    demo_api: sah.Api,
) -> None:
    items = demo_api.ok(path("setup/mcp", "tidewater-reporting"))["items"]
    by_name = {i["name"]: i for i in items}
    notes = by_name["notes"]
    assert notes["read_only_reason"]["code"] == "claude_json_command"
    command = notes["read_only_reason"]["command"]
    assert command["text"] == "claude mcp remove notes -s user"
    scratch = by_name["scratch"]
    assert scratch["read_only_reason"]["command"]["text"] == (
        "claude mcp remove scratch -s local"
    )


def test_the_demo_masks_the_values_that_hold_secrets(demo_api: sah.Api) -> None:
    items: list[dict[str, Any]] = demo_api.ok(path("setup/mcp", "tidewater-reporting"))[
        "items"
    ]
    ledger = next(i for i in items if i["name"] == "ledger")
    env = ledger["facts"]["mcp"]["env"]["LEDGER_API_KEY"]
    assert env["masked"] is True
    assert "FAKEDEMOENV" not in env["text"]

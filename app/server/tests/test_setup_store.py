"""Tests for the Setup answers on a store-backed server: the overlaid demo, ingested.

A fresh demo build gets the setup overlay applied in place (so the project paths
match its transcripts), one subagent's type is renamed to a plugin's (``routing-
dashboard:scout``), and a server ingests it. The tests then read what only the store
can say: runs per agent, unreadable transcripts, the nav's To fix count, which
projects are listed, and the plugin agents on the Agents page and in the Model check.
"""

import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import legacy_answers as la
from conftest import DEMO_BUILDER, DEMO_NOW, DEMO_TZ

import fixture_provider
import history
from store_paths import StoreLayout

TIDE = "tidewater-reporting"
PLUGIN_TYPE = "routing-dashboard:scout"
PLUGIN_ITEM = "agents:routing-dashboard:scout"


class World:
    """A served, ingested, overlaid demo and the facts a test needs about it."""

    def __init__(self, client: Any, headers: dict[str, str], base: Path) -> None:
        self.client = client
        self.headers = headers
        self.base = base
        self.session: str = ""
        self.store = StoreLayout(base / "store")

    def ok(self, path: str) -> Any:
        reply = self.client.get(path, headers=self.headers)
        assert reply.status_code == 200, reply.text
        return reply.json()


PLUGIN_AGENTS = {
    "routing-dashboard/0.1.7/agents/scout.md": (
        "---\nname: scout\ndescription: Read-only scout from the plugin.\n"
        "model: haiku\n---\nYou are a read-only scout.\n"
    ),
    "hivemind/0.1.3/agents/curator.md": (
        "---\nname: curator\ndescription: Keeps the notes tidy.\n"
        "model: sonnet\n---\nYou keep the notes tidy.\n"
    ),
}


def _add_plugin_agents(demo: Path) -> None:
    """Give the two installed plugins an agent each (the overlay installs none)."""
    base = demo / "config" / "plugins" / "cache" / "bartab-demo"
    for rel, text in PLUGIN_AGENTS.items():
        file = base / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")


def _rename_one_agent(demo: Path) -> str:
    """Rename one tidewater subagent's type to a plugin's. Returns its session id."""
    metas = (demo / "config" / "projects").glob("*tidewater*/*/subagents/*.meta.json")
    # The newest run, so it sits inside every range the tests ask for.
    for meta in sorted(metas, key=lambda m: (m.stat().st_mtime, m.name), reverse=True):
        data = json.loads(meta.read_text(encoding="utf-8"))
        if data.get("agentType") == "reviewer":
            stat = meta.stat()
            data["agentType"] = PLUGIN_TYPE
            meta.write_text(json.dumps(data), encoding="utf-8")
            os.utime(meta, (stat.st_atime, stat.st_mtime))
            return meta.parent.parent.name
    msg = "the demo has no tidewater reviewer run"
    raise AssertionError(msg)


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[World]:
    base = tmp_path_factory.mktemp("setup-store")
    demo = base / "demo"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(DEMO_BUILDER),
            str(demo),
            "--now",
            DEMO_NOW,
            "--tz",
            DEMO_TZ,
        ],
        check=True,
        timeout=120,
        capture_output=True,
    )
    fixture_provider.demo_world(demo)  # applies the overlay in place
    _add_plugin_agents(demo)
    session = _rename_one_agent(demo)
    with la.served_demo(demo, base / "srv") as (client, headers):
        found = World(client, headers, base / "srv")
        found.session = session
        yield found


def path(route: str, project: str = TIDE, **more: str) -> str:
    query = "&".join(f"{k}={v}" for k, v in {"project": project, **more}.items())
    return f"/api/{route}?{query}"


# ----------------------------------------------------------------- projects


def test_projects_say_which_are_listed(world: World) -> None:
    rows = {p["key"]: p for p in world.ok("/api/projects")["projects"]}
    assert rows[TIDE]["listed"] is True
    assert rows["setup-broken"]["listed"] is True
    assert all(p["listed"] is True for p in rows.values())
    body = world.ok(path("setup"))
    assert body["listed"] is True
    assert body["notices"] == []


# ------------------------------------------------------------- app's To fix


def test_app_reports_the_to_fix_count_from_the_same_pass_as_problems(
    world: World,
) -> None:
    feed = world.ok(path("problems", "setup-broken"))
    app = world.ok(path("app", "setup-broken").replace("/api/app?", "/api/app?"))
    assert feed["counted"] > 0
    assert app["to_fix"] == {
        "state": "ok",
        "count": feed["counted"],
        "etag": feed["etag"],
    }
    assert app["to_fix_count"] == feed["counted"]


def test_app_is_unchecked_for_no_project_and_an_unknown_one(world: World) -> None:
    for query in ("", "?project=nope"):
        body = world.ok("/api/app" + query)
        assert body["to_fix"] == {"state": "unchecked", "count": None, "etag": None}
        assert body["to_fix_count"] is None


def test_the_demo_project_has_one_row_to_fix_and_app_agrees(world: World) -> None:
    feed = world.ok(path("problems"))
    # The one finding is the local settings file that lowers the project's model.
    assert [(r["code"], r["group"]) for r in feed["rows"]] == [
        ("lowered", "not_as_set")
    ]
    assert feed["counted"] == 1
    assert world.ok(path("app"))["to_fix"]["count"] == 1


# ------------------------------------------------------------------ usage


def test_agents_show_their_runs_over_30_days_and_a_no_runs_group(
    world: World,
) -> None:
    body = world.ok(path("setup/agents"))
    by_id = {i["id"]: i for i in body["items"]}
    builder = by_id["agents:builder"]
    assert builder["usage"]["code"] == "agent_runs"
    assert builder["usage"]["params"]["days"] == "30"
    assert int(builder["usage"]["params"]["runs"]) > 0
    assert builder["group"] == "ran"
    plugin = by_id[PLUGIN_ITEM]
    assert int(plugin["usage"]["params"]["runs"]) == 1
    assert plugin["group"] == "ran"
    quiet = [i for i in body["items"] if i["group"] == "no_runs"]
    assert quiet
    assert [g["key"] for g in body["groups"]] == ["ran", "no_runs"]
    assert sum(g["count"] for g in body["groups"]) == len(body["items"])


def test_the_map_counts_agents_with_no_runs_and_main_runs_at_the_value(
    world: World,
) -> None:
    body = world.ok(path("setup"))
    agents = next(p for p in body["parts"] if p["part"] == "agents")
    assert int(agents["summary"]["params"]["no_runs"]) >= 1
    items = world.ok(path("setup/settings"))["items"]
    model = next(i for i in items if i["id"] == "settings:model")
    assert model["usage"]["code"] == "runs_at_value"
    assert int(model["usage"]["params"]["total"]) > 0


# ------------------------------------------------------- unreadable transcripts


def test_an_unreadable_transcript_is_a_couldnt_read_row(world: World) -> None:
    before = world.ok(path("problems"))
    assert not any(r["code"] == "transcript_unreadable" for r in before["rows"])
    conn = sqlite3.connect(world.store.db, isolation_level=None, timeout=20)
    try:
        conn.execute("PRAGMA busy_timeout = 20000")
        victim = conn.execute(
            "SELECT path FROM files WHERE kind = 'main' AND folder LIKE ? LIMIT 1",
            ("%tidewater%",),
        ).fetchone()
        assert victim is not None
        conn.execute("UPDATE files SET read_errors = 1 WHERE path = ?", (victim[0],))
        conn.execute(
            "UPDATE files SET no_usage = 1 WHERE kind = 'agent' AND folder LIKE ?",
            ("%tidewater%",),
        )
        # A finished pass moves the marker the cached read is keyed on.
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (history.KEY_AS_OF, "2026-10-30T22:30:00.000Z"),
        )
    finally:
        conn.close()
    after = world.ok(path("problems"))
    rows = [r for r in after["rows"] if r["code"] == "transcript_unreadable"]
    assert len(rows) == 1
    row = rows[0]
    assert row["group"] == "couldnt_read"
    assert row["part"] is None
    assert row["full_path"] == victim[0]
    assert not row["file"].startswith("/")
    assert row["file"].startswith("~/")
    assert row["fix"] == {"kind": "copy_path", "target": victim[0], "reason": None}
    assert after["counted"] == before["counted"] + 1
    assert after["etag"] != before["etag"]
    notice = [r for r in after["rows"] if r["code"] == "rows_no_usage"]
    assert len(notice) == 1
    assert notice[0]["group"] == "notice"
    assert world.ok(path("app"))["to_fix"]["count"] == after["counted"]


# ------------------------------------------------------ plugin agents widening


def test_a_plugin_agent_that_ran_is_its_own_row_with_scope_plugin(
    world: World,
) -> None:
    body = world.ok(path("agents", range="30d"))
    ran = {r["agent"]: r for r in body["ran"]}
    plugin = ran[PLUGIN_TYPE]
    assert plugin["scope"] == "plugin"
    assert plugin["item_id"] == PLUGIN_ITEM
    assert plugin["plugin"] == "routing-dashboard"
    assert plugin["status"] is None
    assert plugin["reason_code"] == "agent_source_unchecked"
    assert plugin["set_reason"] != "no_file"
    # A file agent carries the item id its setup page uses. Main and unnamed carry none.
    assert ran["builder"]["item_id"] == "agents:builder"
    assert ran["builder"]["plugin"] is None
    assert ran["builder"]["scope"] in ("user", "project")
    assert ran["@main"]["item_id"] is None
    assert ran["@main"]["scope"] == "main"


def test_plugin_agents_that_did_not_run_are_in_never_ran(world: World) -> None:
    body = world.ok(path("agents", range="30d"))
    never = {r["agent"]: r for r in body["never_ran"]}
    plugin_rows = [r for r in never.values() if r["scope"] == "plugin"]
    assert plugin_rows
    for row in plugin_rows:
        assert row["plugin"]
        assert row["item_id"] == f"agents:{row['agent']}"
        assert row["agent"] != PLUGIN_TYPE  # it ran, so it is not here
    file_rows = [r for r in never.values() if r["scope"] in ("user", "project")]
    assert all(r["item_id"] == f"agents:{r['agent']}" for r in file_rows)
    assert all(r["plugin"] is None for r in file_rows)


def test_a_plugin_agent_that_ran_leaves_never_ran_and_one_that_did_not_stays(
    world: World,
) -> None:
    body = world.ok(path("agents", range="30d"))
    never = {r["agent"]: r for r in body["never_ran"]}
    assert PLUGIN_TYPE not in never
    curator = never["hivemind:curator"]
    assert curator["scope"] == "plugin"
    assert curator["plugin"] == "hivemind"
    assert curator["item_id"] == "agents:hivemind:curator"
    assert curator["set"]["model"]["value"] == "sonnet"


def test_the_timeline_model_check_rows_name_their_item(world: World) -> None:
    body = world.ok(f"/api/sessions/{world.session}/timeline?project={TIDE}")
    rows = {r["agent"]: r for r in body["model_check"]["rows"]}
    assert rows[PLUGIN_TYPE]["item_id"] == PLUGIN_ITEM
    assert rows[None]["item_id"] is None  # the main session
    named = [a for a in rows if a not in (None, PLUGIN_TYPE, "unnamed")]
    assert named
    for agent in named:
        assert rows[agent]["item_id"] == f"agents:{agent}"


def test_the_summary_model_check_rows_name_their_item_too(world: World) -> None:
    body = world.ok(path("summary", range="30d"))
    rows = {r["agent"]: r for r in body["model_check"]["rows"]}
    assert rows[PLUGIN_TYPE]["item_id"] == PLUGIN_ITEM
    assert rows["builder"]["item_id"] == "agents:builder"


def test_the_setup_page_and_the_agents_page_name_one_item(world: World) -> None:
    ids = {i["id"] for i in world.ok(path("setup/agents"))["items"]}
    agents = world.ok(path("agents", range="30d"))
    linked = [r["item_id"] for r in agents["ran"] if r["item_id"] is not None]
    linked += [r["item_id"] for r in agents["never_ran"] if r["item_id"] is not None]
    assert linked
    assert set(linked) <= ids

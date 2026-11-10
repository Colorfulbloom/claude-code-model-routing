"""The M2 and M3 answers keep their shape: task 9 only adds fields.

``app/fixtures/oracle/m3-answers/answers.json`` holds the Agents answer, the Summary's
Model check and every timeline's Model check, recorded on the plain demo build before
task 9 changed them. A fresh run must equal that snapshot once the new fields are
stripped: ``item_id`` and ``plugin`` on Agents rows, ``item_id`` on Model check rows.
The strip is the first allowance, so a changed value, a lost field or a moved row
fails. The second is task 21 item 10: a run is any agent run, the main session
included, so the ``@main`` row's ``runs`` was 0 in the snapshot and is now its own
``sessions`` count, one run per main session. The expected value is derived from the
snapshot row, never a wildcard.
The M2 timeline oracle and the M3 differential run on their own and stay green.
"""

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import legacy_answers as la

NEW_ON_AGENT_ROWS = ("item_id", "plugin")
NEW_ON_CHECK_ROWS = ("item_id",)


@pytest.fixture(scope="module")
def fresh(
    tmp_path_factory: pytest.TempPathFactory, demo_build: Path
) -> Iterator[dict[str, Any]]:
    base = tmp_path_factory.mktemp("legacy")
    with la.served_demo(demo_build, base) as (client, headers):
        yield la.record(client, headers)


def strip(answers: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``answers`` without the fields task 9 added."""
    out: dict[str, Any] = json.loads(json.dumps(answers))
    for key, value in out.items():
        if key.startswith("agents/"):
            for group in ("ran", "never_ran"):
                for row in value[group]:
                    for name in NEW_ON_AGENT_ROWS:
                        row.pop(name)
        else:
            for row in value["rows"]:
                for name in NEW_ON_CHECK_ROWS:
                    row.pop(name)
    return out


def old_main_runs_as_sessions(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``snapshot`` with each ``@main`` row's runs set to its sessions.

    The old app counted no run for the main session, so the snapshot row has ``runs`` 0
    and the ``sessions`` it ran in. The new rule gives one run per main session.
    """
    out: dict[str, Any] = json.loads(json.dumps(snapshot))
    for key, value in out.items():
        if not key.startswith("agents/"):
            continue
        for row in value["ran"] + value["never_ran"]:
            if row["scope"] == "main":
                assert row["runs"] == 0, key
                row["runs"] = row["sessions"]
    return out


def test_the_snapshot_covers_every_project_range_and_session() -> None:
    snapshot = json.loads(la.SNAPSHOT.read_text(encoding="utf-8"))
    kinds = {key.split("/")[0] for key in snapshot}
    assert kinds == {"agents", "summary-model-check", "timeline-model-check"}
    assert len(snapshot) >= 90


def test_a_fresh_run_equals_the_snapshot_once_the_new_fields_are_stripped(
    fresh: dict[str, Any],
) -> None:
    snapshot = json.loads(la.SNAPSHOT.read_text(encoding="utf-8"))
    expected = old_main_runs_as_sessions(snapshot)
    assert sorted(fresh) == sorted(snapshot)
    stripped = strip(fresh)
    changed = [key for key in snapshot if stripped[key] != expected[key]]
    assert changed == []


def test_the_main_rows_changed_by_exactly_their_sessions(
    fresh: dict[str, Any],
) -> None:
    snapshot = json.loads(la.SNAPSHOT.read_text(encoding="utf-8"))
    seen = 0
    for key, value in snapshot.items():
        if not key.startswith("agents/"):
            continue
        before = {r["agent"]: r for r in value["ran"] + value["never_ran"]}
        for row in fresh[key]["ran"] + fresh[key]["never_ran"]:
            old = before[row["agent"]]
            if row["scope"] == "main":
                seen += 1
                assert old["runs"] == 0
                assert row["runs"] == old["sessions"] == row["sessions"], key
            else:
                assert row.get("runs") == old.get("runs"), (key, row["agent"])
    assert seen == 6


def test_only_the_new_fields_were_added(fresh: dict[str, Any]) -> None:
    snapshot = json.loads(la.SNAPSHOT.read_text(encoding="utf-8"))
    for key, value in fresh.items():
        rows: list[dict[str, Any]]
        before: list[dict[str, Any]]
        if key.startswith("agents/"):
            rows = value["ran"] + value["never_ran"]
            before = snapshot[key]["ran"] + snapshot[key]["never_ran"]
            added = set(NEW_ON_AGENT_ROWS)
        else:
            rows, before = value["rows"], snapshot[key]["rows"]
            added = set(NEW_ON_CHECK_ROWS)
        assert len(rows) == len(before), key
        for now, then in zip(rows, before, strict=True):
            assert set(now) - set(then) == added, key
            assert set(then) <= set(now), key


def test_a_plain_demo_has_no_plugin_rows_so_nothing_widened(
    fresh: dict[str, Any],
) -> None:
    for key, value in fresh.items():
        if not key.startswith("agents/"):
            continue
        for row in value["ran"] + value["never_ran"]:
            assert row["scope"] in ("user", "project", "main", "unnamed", "no_file")
            assert row["plugin"] is None


def test_file_agents_name_their_item_and_main_and_unnamed_do_not(
    fresh: dict[str, Any],
) -> None:
    for key, value in fresh.items():
        if not key.startswith("agents/"):
            continue
        for row in value["ran"] + value["never_ran"]:
            if row["scope"] in ("user", "project"):
                assert row["item_id"] == f"agents:{row['agent']}", key
            else:
                assert row["item_id"] is None, key

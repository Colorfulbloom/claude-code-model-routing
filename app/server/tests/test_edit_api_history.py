"""History, the recheck read, drift, seen and the open warning (m6-build.md 4.2, 3.9).

These routes stay mounted with edits off, because Changes must work on the default
start. A test saves with edits on, then opens a second app over the same folders with
edits off, and reads what the first one wrote.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_api_helpers import Api, OpenClient, dump, open_api, write_json

import edit_history
import edit_store
import write_guard
from edit_store import RowStatus


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


def seed(config: Path, project: Path) -> None:
    write_json(config / "settings.json", dump({"model": "sonnet"}))
    write_json(
        project / ".claude" / "settings.json",
        dump({"effortLevel": "low", "other": 1}),
    )


def saved(api: Api, value: str = "high", scope: str = "project") -> str:
    response = api.save(value, scope)
    assert response.status_code == 200, response.text
    return response.json()["row_id"]


def rows_of(api: Api) -> list[dict[str, Any]]:
    response = api.history()
    assert response.status_code == 200
    return response.json()["rows"]


# ---------------------------------------------------------------- history


def test_history_lists_a_save_with_every_field(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        body = api.history().json()
    assert set(body) == {"server_time", "rows", "older", "backup_folder", "edits"}
    assert body["older"] == {"count": 0, "rows": []}
    assert body["edits"]["state"] == "on"
    (row,) = body["rows"]
    assert set(row) == {
        "id",
        "time",
        "subject",
        "field",
        "from",
        "to",
        "scope",
        "display_path",
        "real_path",
        "op",
        "undo_state",
        "undone_at",
        "recheck",
        "not_undoable_reason",
    }
    assert row["id"] == row_id
    assert row["subject"] == {"kind": "main", "name": None}
    assert row["field"] == "effortLevel"
    assert (row["from"], row["to"]) == ("low", "high")
    assert row["scope"] == "project"
    assert row["op"] == "set"
    assert row["display_path"] == ".claude/settings.json"
    assert row["undo_state"] == "can_undo"
    assert row["undone_at"] is None
    assert row["not_undoable_reason"] is None
    assert row["recheck"] == {
        "state": "checking",
        "changed_keys": [],
        "ours_survived": None,
        "seen": False,
    }


def test_history_names_the_real_backup_folder(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        folder = api.history().json()["backup_folder"]
    assert folder["real"] == str(
        os.path.realpath(edit_config / "routing-dashboard" / "backups")
    )
    assert folder["display"].endswith("routing-dashboard/backups")


def test_history_is_newest_first_and_only_the_newest_row_can_be_undone(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        first = saved(api, "medium")
        api.clock.advance(60)
        second = saved(api, "high")
        rows = rows_of(api)
    assert [row["id"] for row in rows] == [second, first]
    assert rows[0]["undo_state"] == "can_undo"
    assert rows[1]["undo_state"] == "not_undoable"
    assert rows[1]["not_undoable_reason"] == "not_newest"


def test_an_undone_row_says_when_and_the_undo_row_is_never_undoable(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        api.clock.advance(60)
        undone = api.undo(row_id).json()["row_id"]
        rows = {row["id"]: row for row in rows_of(api)}
    assert rows[row_id]["undo_state"] == "undone"
    assert rows[row_id]["undone_at"] == rows[undone]["time"]
    assert rows[undone]["op"] == "undo"
    assert rows[undone]["undo_state"] == "not_undoable"
    assert rows[undone]["not_undoable_reason"] == "undo_row"


def test_a_create_is_a_create_row_that_deletes_a_file_on_undo(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project) as api:
        saved(api, "high", "local")
        (row,) = rows_of(api)
    assert row["op"] == "create"
    assert row["undo_state"] == "deletes_file"
    assert row["from"] is None
    assert row["to"] == "high"
    assert row["scope"] == "local"


def test_a_file_changed_since_the_save_is_changed_since_with_undo_anyway(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        saved(api)
        write_json(api.project_file(), dump({"effortLevel": "high", "other": 7}))
        (row,) = rows_of(api)
    assert row["undo_state"] == "changed_since"
    assert row["not_undoable_reason"] is None


def test_a_word_the_writer_adds_reads_as_file_refused(
    open_client: OpenClient,
    edit_config: Path,
    edit_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        saved(api)

        def odd(self: Any, target: Any, row: Any) -> RowStatus:
            del self, target, row
            return RowStatus("not_undoable", "something_new", False)

        monkeypatch.setattr(edit_store.EditStore, "row_status", odd)
        (row,) = rows_of(api)
    assert row["undo_state"] == "not_undoable"
    assert row["not_undoable_reason"] == "file_refused"


def test_every_reason_the_writer_gives_maps_into_the_closed_set() -> None:
    for word in (
        "not_newest",
        "undo_row",
        "restore_row",
        "backup_pruned",
        "backup_damaged",
    ):
        status = RowStatus("not_undoable", word, False)
        assert edit_history.reason_of(status) == word
    assert (
        edit_history.reason_of(RowStatus("not_undoable", None, False)) == "file_refused"
    )
    assert edit_history.reason_of(RowStatus("can_undo", None, False)) is None
    assert (
        edit_history.reason_of(RowStatus("changed_since", "changed_since_save", True))
        is None
    )


def test_a_row_the_old_app_wrote_shows_as_the_main_session(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        ledger_path = api.backups / edit_store.target_id_of(
            os.path.realpath(api.project_file())
        )
        ledger = json.loads((ledger_path / "ledger.json").read_text())
        for name in (
            "project",
            "field",
            "subject",
            "scope",
            "display_path",
            "real_path",
            "app",
            "request_id",
            "recheck",
        ):
            ledger["rows"][0].pop(name, None)
        (ledger_path / "ledger.json").write_text(json.dumps(ledger))
        (row,) = rows_of(api)
    assert row["id"] == row_id
    assert row["subject"] == {"kind": "main", "name": None}
    assert row["field"] == "effortLevel"
    assert row["scope"] == "project"
    assert row["recheck"] is None
    assert row["display_path"] == ".claude/settings.json"


def test_history_leaves_out_a_row_that_names_another_project(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        saved(api)
        ledger_path = api.backups / edit_store.target_id_of(
            os.path.realpath(api.project_file())
        )
        ledger = json.loads((ledger_path / "ledger.json").read_text())
        ledger["rows"][0]["project"] = "someone-else"
        (ledger_path / "ledger.json").write_text(json.dumps(ledger))
        assert rows_of(api) == []


def test_history_scans_other_ledgers_for_this_projects_rows(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        ledger_path = api.backups / edit_store.target_id_of(
            os.path.realpath(api.project_file())
        )
        rows = json.loads((ledger_path / "ledger.json").read_text())["rows"]
        mine = {**rows[0], "id": "a" * 16, "time": "2026-01-01T00:00:00+00:00"}
        theirs = {**rows[0], "id": "b" * 16, "project": "someone-else"}
        gone = api.backups / ("c" * 16)
        gone.mkdir(mode=0o700)
        (gone / "ledger.json").write_text(
            json.dumps({"version": 1, "rows": [mine, theirs]})
        )
        body = api.history().json()
    assert [row["id"] for row in body["rows"]] == [row_id]
    assert body["older"]["count"] == 1
    (older,) = body["older"]["rows"]
    assert older["id"] == "a" * 16
    assert older["undo_state"] == "not_undoable"
    assert older["not_undoable_reason"] == "file_refused"


def test_rows_past_the_newest_twenty_of_a_file_are_older(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        saved(api)
        ledger_path = api.backups / edit_store.target_id_of(
            os.path.realpath(api.project_file())
        )
        ledger = json.loads((ledger_path / "ledger.json").read_text())
        base = ledger["rows"][0]
        ledger["rows"] = [
            {**base, "id": f"{i:016x}", "time": f"2026-01-01T00:00:{i:02d}+00:00"}
            for i in range(1, 22)
        ] + [base]
        (ledger_path / "ledger.json").write_text(json.dumps(ledger))
        body = api.history().json()
    assert len(body["rows"]) == 20
    assert body["older"]["count"] == 2
    assert len(body["older"]["rows"]) == 2


def test_history_on_a_project_with_no_edits_is_empty(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.history().json()
    assert body["rows"] == []
    assert body["older"] == {"count": 0, "rows": []}


def test_history_checks_the_project(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project) as api:
        unknown = api.client.get("/api/edit/history?project=no-such-project")
        missing = api.client.get("/api/edit/history")
    assert unknown.status_code == 404
    assert missing.status_code == 400


def test_history_with_edits_off_reads_what_an_earlier_run_wrote(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
    with open_api(open_client, edit_config, edit_project, edits="off") as off:
        body = off.history().json()
        assert body["edits"]["state"] == "off"
        assert [row["id"] for row in body["rows"]] == [row_id]
        assert body["rows"][0]["undo_state"] == "can_undo"
        assert off.row(row_id).status_code == 200
        assert off.drift(row_id).status_code == 200
        assert off.open_warning().status_code == 200
        undo = off.client.post(
            "/api/edit/undo",
            json={
                "project": "edit-project",
                "row_id": row_id,
                "request_id": "off-undo-0001",
            },
        )
        assert undo.status_code == 403


# ---------------------------------------------------------------- rechecks


def test_a_recheck_that_ran_is_confirmed_when_nothing_changed(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        assert api.row(row_id).json()["state"] == "checking"
        api.run_timers()
        body = api.row(row_id).json()
        history_row = rows_of(api)[0]
    assert set(body) == {
        "server_time",
        "state",
        "changed_keys",
        "ours_survived",
        "checked_at",
        "seen",
    }
    assert body["state"] == "confirmed"
    assert body["ours_survived"] is True
    assert body["changed_keys"] == []
    assert body["checked_at"]
    assert history_row["recheck"]["state"] == "confirmed"


def test_another_program_overwriting_the_file_is_overwritten_with_the_keys(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        write_json(api.project_file(), dump({"effortLevel": "high", "other": 2}))
        api.run_timers()
        survived = api.row(row_id).json()
        write_json(api.project_file(), dump({"effortLevel": "low", "other": 2}))
        api.store.run_recheck(api.targets()[1], row_id)
        lost = api.row(row_id).json()
    assert survived["state"] == "overwritten"
    assert survived["changed_keys"] == ["other"]
    assert survived["ours_survived"] is True
    assert lost["changed_keys"] == ["effortLevel", "other"]
    assert lost["ours_survived"] is False


def test_a_recheck_lost_to_a_restart_runs_when_the_row_is_read_past_its_due_time(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        api.timers.clear()  # the process "restarted": no timer is left
        api.clock.advance(5)
        early = api.row(row_id).json()
        assert early["state"] == "checking"  # not due yet
        api.clock.advance(11)  # 16 s after the save, past 10 s plus the margin
        late = api.row(row_id).json()
        assert late["state"] == "confirmed"
        assert late["checked_at"]
        # the answer was stored on the row, so history shows it too
        assert rows_of(api)[0]["recheck"]["state"] == "confirmed"


def test_a_lost_recheck_is_found_through_history_too(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        saved(api)
        write_json(api.project_file(), dump({"effortLevel": "low", "other": 3}))
        api.timers.clear()
        api.clock.advance(20)
        (row,) = rows_of(api)
    assert row["recheck"]["state"] == "overwritten"
    assert row["recheck"]["ours_survived"] is False


def test_with_edits_off_a_lost_recheck_stays_checking_and_nothing_is_written(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        clock = api.clock
        ledger = api.backups / edit_store.target_id_of(
            os.path.realpath(api.project_file())
        )
        before = (ledger / "ledger.json").read_bytes()
    clock.advance(60)
    with open_api(
        open_client, edit_config, edit_project, edits="off", clock=clock
    ) as off:
        assert off.row(row_id).json()["state"] == "checking"
        assert off.history().json()["rows"][0]["recheck"]["state"] == "checking"
    assert (ledger / "ledger.json").read_bytes() == before


def test_a_late_recheck_runs_once_at_a_time(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        api.timers.clear()
        api.clock.advance(60)
        calls: list[str] = []
        real = api.store.run_recheck

        def counting(target: Any, rid: str) -> Any:
            calls.append(rid)
            return real(target, rid)

        api.store.run_recheck = counting  # type: ignore[method-assign]
        api.row(row_id)
        api.row(row_id)  # the first run stored its answer, so there is nothing to run
    assert calls == [row_id]


def test_a_row_of_another_ledger_or_unknown_id_is_a_404(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        assert api.row("0123456789abcdef").status_code == 404
        assert api.row("../../etc").status_code in (404, 422)
        assert api.drift("0123456789abcdef").status_code == 404
        assert api.seen("0123456789abcdef").status_code == 404


# ---------------------------------------------------------------- drift


def test_drift_is_the_diff_from_what_bar_tab_wrote_to_the_file_now(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        write_json(api.project_file(), dump({"effortLevel": "high", "other": 2}))
        body = api.drift(row_id).json()
    assert set(body) == {"server_time", "lines", "code"}
    assert body["code"] is None
    removed = [line["text"].strip() for line in body["lines"] if line["kind"] == "del"]
    added = [line["text"].strip() for line in body["lines"] if line["kind"] == "add"]
    assert removed == ['"other": 1']
    assert added == ['"other": 2']
    assert all(
        set(line) == {"kind", "old_n", "new_n", "text"} for line in body["lines"]
    )


def test_drift_with_an_unchanged_file_has_no_lines(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        body = api.drift(row_id).json()
    assert body["lines"] == []


def test_drift_says_cant_rebuild_when_the_backup_is_gone(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        folder = api.backups / edit_store.target_id_of(
            os.path.realpath(api.project_file())
        )
        for backup in folder.glob("*.bak"):
            backup.unlink()
        response = api.drift(row_id)
    assert response.status_code == 200
    assert response.json()["code"] == "cant_rebuild"
    assert response.json()["lines"] is None


def test_drift_of_a_file_another_program_broke_still_masks(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        api.project_file().write_text(
            '{ // comment\n  "effortLevel": "high",\n  "apiKey": "sk-ant-LOOSE",\n}\n'
        )
        response = api.drift(row_id)
    assert response.status_code == 200
    assert "sk-ant-LOOSE" not in response.text


# ---------------------------------------------------------------- seen and open


def overwritten(api: Api) -> str:
    row_id = saved(api)
    write_json(api.project_file(), dump({"effortLevel": "high", "other": 9}))
    api.run_timers()
    return row_id


def test_an_overwritten_row_not_yet_seen_is_the_open_warning(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = overwritten(api)
        any_item = api.open_warning().json()
        item = api.open_warning("settings:effortLevel").json()
        other_item = api.open_warning("settings:model").json()
        unedited = api.open_warning("settings:alwaysThinkingEnabled").json()
    assert set(any_item) == {"server_time", "row"}
    assert any_item["row"]["id"] == row_id
    assert item["row"]["id"] == row_id
    assert item["row"]["recheck"]["state"] == "overwritten"
    assert other_item["row"] is None
    assert unedited["row"] is None


def test_marking_a_row_seen_stops_the_warning_and_works_with_edits_off(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = overwritten(api)
        clock = api.clock
    with open_api(
        open_client, edit_config, edit_project, edits="off", clock=clock
    ) as off:
        response = off.seen(row_id)
        assert response.status_code == 200
        assert response.json()["seen"] is True
        assert response.json()["state"] == "overwritten"
        assert off.open_warning().json()["row"] is None
        assert off.history().json()["rows"][0]["recheck"]["seen"] is True
        assert off.row(row_id).json()["seen"] is True


def test_a_seen_mark_survives_a_restart(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = overwritten(api)
        assert api.seen(row_id).status_code == 200
        marks = api.store_root / "edit-seen.json"
        assert marks.exists()
        assert oct(marks.stat().st_mode & 0o777) == "0o600"
    with open_api(open_client, edit_config, edit_project) as again:
        assert again.row(row_id).json()["seen"] is True
        assert again.open_warning().json()["row"] is None


def test_a_seen_mark_for_a_row_that_does_not_exist_is_refused(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        response = api.seen("0123456789abcdef")
        body_missing = api.client.post("/api/edit/rows/abc/seen", json={})
        assert not (api.store_root / "edit-seen.json").exists()
    assert response.status_code == 404
    assert response.json()["code"] == "unknown_edit"
    assert body_missing.status_code == 422


def test_the_open_warning_is_empty_for_a_row_that_is_still_confirmed(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        saved(api)
        api.run_timers()
        assert api.open_warning().json()["row"] is None

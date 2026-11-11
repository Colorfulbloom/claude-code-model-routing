"""``POST /api/edit/save`` and ``/undo``: results, 409s and refusals (m6-build 3.7).

The 409 answers carry what the page needs to recover without a second read. A save that
meets a changed file gets a fresh preview, the keys that changed on disk and whether the
edited key was among them. An undo of a changed file gets the undo diff and its own
token, and "Undo anyway" sends that token back.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_api_helpers import Api, OpenClient, dump, open_api, write_json

import write_guard


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def seed(config: Path, project: Path) -> None:
    write_json(config / "settings.json", dump({"model": "sonnet"}))
    write_json(
        project / ".claude" / "settings.json",
        dump({"effortLevel": "low", "other": 1}),
    )


def test_a_save_writes_the_value_and_answers_with_the_row_and_the_recheck_delay(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        response = api.save("high")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"server_time", "row_id", "saved_at", "recheck_after_ms"}
        assert body["recheck_after_ms"] == 2000
        assert len(body["row_id"]) == 16
        assert read(api.project_file()) == {"effortLevel": "high", "other": 1}
        assert len(api.timers) == 2  # the two server rechecks are scheduled


def test_a_save_leaves_every_other_byte_of_the_file_alone(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    text = '{\n    "other":   1,\n    "effortLevel": "low"  ,\n  "z": [1,2]\n}\n'
    write_json(edit_project / ".claude" / "settings.json", text)
    with open_api(open_client, edit_config, edit_project) as api:
        assert api.save("high").status_code == 200
        after = api.project_file().read_text(encoding="utf-8")
    assert after == text.replace('"low"', '"high"')


def test_a_save_to_a_new_file_creates_it_and_the_folder(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    (edit_project / ".claude").rmdir()
    with open_api(open_client, edit_config, edit_project) as api:
        assert api.save("high", "project").status_code == 200
        assert read(api.project_file()) == {"effortLevel": "high"}


def test_a_repeat_press_with_the_same_request_id_returns_the_first_result(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        shown = api.preview("high").json()
        first = api.save("high", version=shown["version"], rid="same-request-id")
        second = api.save("high", version=shown["version"], rid="same-request-id")
        other = api.save("medium", version=shown["version"], rid="same-request-id")
    assert first.status_code == second.status_code == 200
    assert first.json()["row_id"] == second.json()["row_id"]
    assert other.status_code == 422
    assert other.json()["code"] == "request_reused"


def test_a_changed_file_is_a_409_with_a_fresh_preview_and_the_changed_keys(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        shown = api.preview("high").json()
        write_json(
            api.project_file(), dump({"effortLevel": "low", "other": 2, "added": True})
        )
        response = api.save("high", version=shown["version"])
        body = response.json()
        assert response.status_code == 409
        assert body["code"] == "changed"
        assert body["changed_keys"] == ["added", "other"]
        assert body["edited_key_changed"] is False
        assert body["preview"]["version"] != shown["version"]
        assert body["preview"]["seq"] == 2
        assert body["preview"]["effect"]["set"] == {"from": "low", "to": "high"}
        # nothing was written: the file is still the other program's
        assert read(api.project_file())["other"] == 2
        assert list(api.backups.rglob("*.bak")) == []  # no backup, no row
        # the fresh token saves
        again = api.save("high", version=body["preview"]["version"])
        assert again.status_code == 200


def test_the_409_says_when_the_edited_key_itself_changed(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        shown = api.preview("high").json()
        write_json(api.project_file(), dump({"effortLevel": "medium", "other": 1}))
        body = api.save("high", version=shown["version"]).json()
    assert body["changed_keys"] == ["effortLevel"]
    assert body["edited_key_changed"] is True
    assert body["preview"]["effect"]["set"] == {"from": "medium", "to": "high"}


def test_a_body_that_differs_from_the_previewed_one_is_a_preview_mismatch(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        shown = api.preview("high").json()
        response = api.save("medium", version=shown["version"])
        body = response.json()
        assert response.status_code == 409
        assert body["code"] == "preview_mismatch"
        assert body["changed_keys"] == []
        assert body["edited_key_changed"] is False
        assert body["preview"]["effect"]["set"]["to"] == "medium"
        assert read(api.project_file())["effortLevel"] == "low"


def test_a_token_the_server_never_made_is_a_bad_version(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        junk = api.save("high", version="not-a-token")
        other_run = api.save("high", version="e30.AAAA")
    assert junk.status_code == other_run.status_code == 422
    assert junk.json()["code"] == other_run.json()["code"] == "bad_version"
    assert set(junk.json()) == {"server_time", "code", "params"}


def test_a_changed_file_without_the_kept_preview_names_no_keys(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    # After a restart, or once the 64-entry cache dropped the preview, the refusal says
    # the file changed and lists no keys.
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        shown = api.preview("high").json()
        api.store._previews.clear()  # pyright: ignore[reportPrivateUsage]
        write_json(api.project_file(), dump({"effortLevel": "low", "other": 5}))
        body = api.save("high", version=shown["version"]).json()
    assert body["code"] == "changed"
    assert body["changed_keys"] == []
    assert body["edited_key_changed"] is False
    assert body["preview"] is not None


def test_a_refused_save_is_a_422_with_its_code(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", '{"model": }')
    with open_api(open_client, edit_config, edit_project) as api:
        shown = api.preview("opus", "user", "model").json()
        response = api.save("opus", "user", "model", version=shown["version"])
    assert shown["refusal"]["code"] == "unparsed"
    assert response.status_code == 422
    assert response.json()["code"] == "unparsed"


def test_a_value_the_field_refuses_is_a_422(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        shown = api.preview("high").json()
        response = api.save("turbo", version=shown["version"])
    assert response.status_code == 422
    assert response.json()["code"] == "bad_value"


def test_a_save_with_edits_off_is_refused(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project, edits="off") as api:
        response = api.client.post(
            "/api/edit/save",
            json={
                **api.body("high"),
                "version": "x",
                "request_id": "abcdefgh12345678",
            },
        )
    assert response.status_code == 403
    assert response.json()["code"] == "edits_off"
    assert read(edit_project / ".claude" / "settings.json")["effortLevel"] == "low"


# ---------------------------------------------------------------- undo


def saved(api: Api, value: str = "high") -> str:
    response = api.save(value)
    assert response.status_code == 200, response.text
    return response.json()["row_id"]


def test_an_undo_of_an_unchanged_file_applies_at_once(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    original = (edit_project / ".claude" / "settings.json").read_bytes()
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        response = api.undo(row_id)
        assert response.status_code == 200
        assert set(response.json()) == {"server_time", "row_id"}
        assert response.json()["row_id"] != row_id
        assert api.project_file().read_bytes() == original


def test_an_undo_of_a_changed_file_is_a_409_with_the_undo_diff_and_its_own_token(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        write_json(api.project_file(), dump({"effortLevel": "high", "other": 99}))
        response = api.undo(row_id)
        body = response.json()
        assert response.status_code == 409
        assert body["code"] == "changed_since_save"
        preview = body["undo_preview"]
        assert set(preview) == {"diff", "version"}
        kinds = {line["kind"] for line in preview["diff"]["lines"]}
        assert kinds == {"ctx", "add", "del"}
        text = {line["text"].strip() for line in preview["diff"]["lines"]}
        assert '"other": 99' in text  # the other program's value goes
        assert '"other": 1' in text  # and the backup's comes back
        # nothing changed yet
        assert read(api.project_file())["other"] == 99
        # without the token, "anyway" is refused
        without = api.undo(row_id, anyway=True)
        assert without.status_code == 422
        assert without.json()["code"] == "bad_version"
        # with it, the undo goes through
        confirmed = api.undo(row_id, anyway=True, version=preview["version"])
        assert confirmed.status_code == 200
        assert read(api.project_file()) == {"effortLevel": "low", "other": 1}


def test_an_undo_anyway_token_is_bound_to_its_row_and_the_file(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        write_json(api.project_file(), dump({"effortLevel": "high", "other": 99}))
        token = api.undo(row_id).json()["undo_preview"]["version"]
        write_json(api.project_file(), dump({"effortLevel": "high", "other": 100}))
        stale = api.undo(row_id, anyway=True, version=token)
        fresh = api.undo(row_id)
    assert stale.status_code == 422
    assert stale.json()["code"] == "changed"
    # asking again without "anyway" gives a new diff and a new token
    assert fresh.status_code == 409
    assert fresh.json()["undo_preview"]["version"] != token


def test_only_the_newest_row_of_a_file_can_be_undone(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        first = saved(api, "medium")
        saved(api, "high")
        response = api.undo(first)
    assert response.status_code == 422
    assert response.json() == {
        **response.json(),
        "code": "not_undoable",
        "params": {"reason": "not_newest"},
    }


def test_an_undo_of_a_create_deletes_the_file_and_the_folder_the_save_made(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    (edit_project / ".claude").rmdir()
    with open_api(open_client, edit_config, edit_project) as api:
        row_id = saved(api)
        assert api.project_file().exists()
        assert api.undo(row_id).status_code == 200
        assert not api.project_file().exists()
        assert not (edit_project / ".claude").exists()


def test_an_undo_of_an_unknown_row_is_a_404(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project) as api:
        response = api.undo("0123456789abcdef")
    assert response.status_code == 404
    assert response.json()["code"] == "unknown_edit"


def test_an_undo_with_edits_off_is_refused(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    seed(edit_config, edit_project)
    with open_api(open_client, edit_config, edit_project, edits="off") as api:
        response = api.client.post(
            "/api/edit/undo",
            json={
                "project": "edit-project",
                "row_id": "0123456789abcdef",
                "request_id": "abcdefgh12345678",
            },
        )
    assert response.status_code == 403
    assert response.json()["code"] == "edits_off"


def test_a_row_another_project_made_is_a_forged_row_for_undo(
    open_client: OpenClient, edit_config: Path, edit_project: Path, tmp_path: Path
) -> None:
    seed(edit_config, edit_project)
    other = tmp_path / "other-project"
    (other / ".claude").mkdir(parents=True)
    with open_api(open_client, edit_config, edit_project, other=other) as api:
        row_id = saved(api, "high")
        # the user file is shared by both projects, so save there from project one
        user_row = api.client.post(
            "/api/edit/preview", json=api.body("opus", "user", "model")
        ).json()
        made = api.client.post(
            "/api/edit/save",
            json={
                **api.body("opus", "user", "model", 3),
                "version": user_row["version"],
                "request_id": "user-save-0001",
            },
        ).json()["row_id"]
        # project two asks to undo project one's row
        forged = api.client.post(
            "/api/edit/undo",
            json={
                "project": "other-project",
                "row_id": made,
                "request_id": "forged-undo-01",
            },
        )
    assert row_id
    assert forged.status_code == 422
    assert forged.json()["code"] == "forged_row"

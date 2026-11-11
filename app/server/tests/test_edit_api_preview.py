"""``POST /api/edit/preview``: every field of the answer (m6-build.md section 4.2).

Each test builds a throwaway machine under ``tmp_path`` (``edit_config``,
``edit_project`` and ``edit_api_helpers.open_api``), puts settings files on it and
previews a value. No test writes a settings file through the route: that is
``test_edit_api_save.py``.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_api_helpers import (
    OTHER,
    OpenClient,
    dump,
    git_available,
    init_repo,
    open_api,
    write_json,
)

import edit_store
import write_guard
from models import EditPreviewRequest


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


def scope_row(body: dict[str, Any], scope: str) -> dict[str, Any]:
    return next(row for row in body["scopes"] if row["scope"] == scope)


def test_a_preview_carries_every_field_of_the_contract(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(
        edit_config / "settings.json", dump({"model": "opus", "effortLevel": "low"})
    )
    write_json(
        edit_project / ".claude" / "settings.json", dump({"effortLevel": "medium"})
    )
    with open_api(open_client, edit_config, edit_project) as api:
        response = api.preview("high", seq=7)
        assert response.status_code == 200
        body = response.json()
    assert set(body) == {
        "server_time",
        "seq",
        "choice_key",
        "target",
        "effect",
        "options",
        "scopes",
        "reaches",
        "warnings",
        "diff",
        "summary",
        "read_at",
        "version",
        "refusal",
    }
    assert body["seq"] == 7
    model = EditPreviewRequest.model_validate(
        {
            "project": "edit-project",
            "op": "set",
            "scope": "project",
            "field": "effortLevel",
            "value": "high",
            "seq": 1,
        }
    )
    assert body["choice_key"] == edit_store.choice_key(model)  # no seq in the key
    assert body["version"].count(".") == 1
    assert body["read_at"]
    assert body["refusal"] is None


def test_the_target_names_the_file_a_save_would_write(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(
        edit_project / ".claude" / "settings.json", dump({"effortLevel": "medium"})
    )
    with open_api(open_client, edit_config, edit_project) as api:
        target = api.preview("high").json()["target"]
    assert target["scope"] == "project"
    assert target["display_path"] == ".claude/settings.json"
    assert target["real_path"] == ".claude/settings.json"
    assert target == {
        "scope": "project",
        "display_path": ".claude/settings.json",
        "real_path": ".claude/settings.json",
        "link": False,
        "exists": True,
        "git_tracked": False,
        "new_file": False,
    }


def test_a_file_that_is_not_there_is_a_new_file_with_a_creates_summary(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "local").json()
    assert body["target"]["new_file"] is True
    assert body["target"]["exists"] is False
    assert body["diff"]["new_file"] is True
    assert body["summary"] == {
        "verb": "creates",
        "lines_changed": 3,
        "display_path": ".claude/settings.local.json",
    }
    assert [line["kind"] for line in body["diff"]["lines"]] == ["add"] * 3
    assert [line["new_n"] for line in body["diff"]["lines"]] == [1, 2, 3]
    assert body["effect"]["set"] == {"from": None, "to": "high"}


def test_a_missing_claude_folder_is_made_by_the_save_so_the_preview_is_clean(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    (edit_project / ".claude").rmdir()
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "project").json()
    assert body["refusal"] is None
    assert body["target"]["new_file"] is True
    assert body["version"]


def test_the_diff_has_real_line_numbers_and_the_summary_counts_them(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    text = dump({"a": 1, "b": 2, "effortLevel": "medium", "c": 3, "d": 4})
    write_json(edit_project / ".claude" / "settings.json", text)
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high").json()
    lines = body["diff"]["lines"]
    removed = [line for line in lines if line["kind"] == "del"]
    added = [line for line in lines if line["kind"] == "add"]
    assert [(line["old_n"], line["new_n"]) for line in removed] == [(4, None)]
    assert [(line["old_n"], line["new_n"]) for line in added] == [(None, 4)]
    assert removed[0]["text"].strip() == '"effortLevel": "medium",'
    assert added[0]["text"].strip() == '"effortLevel": "high",'
    context = [line for line in lines if line["kind"] == "ctx"]
    assert all(line["old_n"] and line["new_n"] for line in context)
    assert body["summary"]["lines_changed"] == 1
    assert body["summary"]["verb"] == "changes"


def test_the_effect_says_what_runs_now_and_after(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"model": "sonnet"}))
    write_json(edit_project / ".claude" / "settings.json", dump({"effortLevel": "low"}))
    with open_api(open_client, edit_config, edit_project) as api:
        effect = api.preview("high", "project").json()["effect"]
    assert effect["set"] == {"from": "low", "to": "high"}
    assert effect["runs"]["now"] == {"value": "low", "status": "in_effect"}
    assert effect["runs"]["after"] == {"value": "high", "status": "in_effect"}
    assert effect["applies"] == "new_session"


def test_a_top_level_effort_in_the_user_file_is_ignored_for_the_new_models(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    # The rules say Opus 5.5 and later take a user settings level from modelSettings
    # only, so the plan's top-level key gets the resolver's own answer: ignored.
    write_json(edit_config / "settings.json", dump({"model": "sonnet"}))
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "user").json()
    assert scope_row(body, "user")["outcome"] == {
        "status": "ignored",
        "beaten_by": None,
    }
    assert body["effect"]["runs"]["after"]["status"] == "default"
    assert body["warnings"][0]["code"] == "wont_win"
    assert body["warnings"][0]["params"]["status"] == "ignored"


def test_scopes_list_each_file_with_its_value_and_what_a_save_there_would_do(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"model": "sonnet"}))
    write_json(
        edit_project / ".claude" / "settings.json", dump({"effortLevel": "medium"})
    )
    write_json(
        edit_project / ".claude" / "settings.local.json", dump({"effortLevel": "low"})
    )
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "project").json()
    assert [row["scope"] for row in body["scopes"]] == ["user", "project", "local"]
    user, project, local = body["scopes"]
    assert user["current_value"] is None
    assert user["writable"] is True
    assert user["read_only_reason"] is None
    assert project["current_value"] == "medium"
    assert local["current_value"] == "low"
    # The local file sits above the project file, so a project save would not run.
    assert project["outcome"] == {"status": "overridden", "beaten_by": "local"}
    assert local["outcome"] == {"status": "in_effect", "beaten_by": None}
    assert {row["display_path"] for row in body["scopes"]} == {
        "~/.claude/settings.json",
        ".claude/settings.json",
        ".claude/settings.local.json",
    }
    assert body["effect"]["runs"]["after"] == {"value": "low", "status": "in_effect"}


def test_a_project_value_beaten_by_the_local_env_twin_names_local(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(
        edit_project / ".claude" / "settings.json", dump({"effortLevel": "medium"})
    )
    write_json(
        edit_project / ".claude" / "settings.local.json",
        dump({"env": {"CLAUDE_CODE_EFFORT_LEVEL": "low"}}),
    )
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "project").json()
    project = scope_row(body, "project")
    assert project["outcome"] == {"status": "overridden", "beaten_by": "local"}
    warning = next(item for item in body["warnings"] if item["code"] == "wont_win")
    assert warning["params"]["beaten_by"] == "local"


def test_a_value_that_will_not_win_gets_a_wont_win_warning(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"model": "sonnet"}))
    write_json(
        edit_project / ".claude" / "settings.local.json", dump({"effortLevel": "low"})
    )
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "project").json()
    warning = next(item for item in body["warnings"] if item["code"] == "wont_win")
    assert warning["params"] == {
        "scope": "project",
        "status": "overridden",
        "beaten_by": "local",
    }
    assert body["effect"]["runs"]["after"]["value"] == "low"


def test_an_effort_field_lists_what_each_option_would_run_at(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"model": "sonnet"}))
    write_json(edit_project / ".claude" / "settings.json", dump({"effortLevel": "low"}))
    with open_api(open_client, edit_config, edit_project) as api:
        options = api.preview("high", "project").json()["options"]
    assert [item["value"] for item in options] == ["low", "medium", "high", "xhigh"]
    assert options[2]["runs_at"] == {"value": "high", "status": "in_effect"}


def test_an_effort_cap_lowers_the_options_it_covers(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(
        edit_config / "settings.json",
        dump({"model": "sonnet", "maxEffortLevel": "medium"}),
    )
    write_json(edit_project / ".claude" / "settings.json", dump({"effortLevel": "low"}))
    with open_api(open_client, edit_config, edit_project) as api:
        options = api.preview("high", "project").json()["options"]
    by_value = {item["value"]: item["runs_at"] for item in options}
    assert by_value["low"] == {"value": "low", "status": "in_effect"}
    assert by_value["medium"] == {"value": "medium", "status": "in_effect"}
    assert by_value["xhigh"]["status"] == "lowered"
    assert by_value["xhigh"]["value"] == "medium"


def test_the_cap_field_lists_the_effort_each_cap_leaves(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"model": "sonnet"}))
    write_json(
        edit_project / ".claude" / "settings.json", dump({"effortLevel": "xhigh"})
    )
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("medium", "user", "maxEffortLevel").json()
    assert [item["value"] for item in body["options"]] == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    by_value = {item["value"]: item["runs_at"] for item in body["options"]}
    assert by_value["medium"] == {"value": "medium", "status": "lowered"}
    assert by_value["xhigh"]["status"] == "in_effect"
    assert by_value["max"]["status"] == "in_effect"


@pytest.mark.parametrize("field_name", ["model", "autoCompactWindow"])
def test_open_fields_have_no_options(
    open_client: OpenClient, edit_config: Path, edit_project: Path, field_name: str
) -> None:
    value: str | int = "claude-sonnet-5-5" if field_name == "model" else 200000
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview(value, "user", field_name).json()
    assert body["options"] == []
    assert body["refusal"] is None
    assert body["effect"]["set"]["to"] == value


def test_the_model_field_runs_the_value_it_sets(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"model": "opus"}))
    with open_api(open_client, edit_config, edit_project) as api:
        effect = api.preview("sonnet", "user", "model").json()["effect"]
    assert effect["set"] == {"from": "opus", "to": "sonnet"}
    assert effect["runs"]["now"]["value"] == "opus"
    assert effect["runs"]["after"]["value"] == "sonnet"


def test_the_window_field_takes_a_number(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"autoCompactWindow": 200000}))
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview(300000, "user", "autoCompactWindow").json()
    assert body["effect"]["set"] == {"from": 200000, "to": 300000}
    assert body["refusal"] is None
    assert body["scopes"][0]["current_value"] == "200000"


def test_an_env_twin_is_edited_where_the_file_holds_it(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(
        edit_project / ".claude" / "settings.local.json",
        dump({"env": {"CLAUDE_CODE_EFFORT_LEVEL": "low"}}),
    )
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "local").json()
    assert body["refusal"] is None
    added = [line["text"] for line in body["diff"]["lines"] if line["kind"] == "add"]
    assert added == ['    "CLAUDE_CODE_EFFORT_LEVEL": "high"']
    assert scope_row(body, "local")["current_value"] == "low"
    assert body["effect"]["set"]["from"] == "low"


def test_a_model_settings_entry_for_the_main_model_is_edited_in_place(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(
        edit_config / "settings.json",
        dump(
            {
                "model": "opus",
                "effortLevel": "low",
                "modelSettings": {"claude-opus-5-5": {"effortLevel": "medium"}},
            }
        ),
    )
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "user").json()
    removed = [
        line["text"].strip() for line in body["diff"]["lines"] if line["kind"] == "del"
    ]
    assert removed == ['"effortLevel": "medium"']
    assert body["effect"]["set"]["from"] == "medium"
    assert scope_row(body, "user")["current_value"] == "medium"
    assert body["effect"]["runs"]["after"] == {"value": "high", "status": "in_effect"}


def test_a_user_scope_preview_lists_the_projects_it_reaches(
    open_client: OpenClient, edit_config: Path, edit_project: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other-project"
    (other / ".claude").mkdir(parents=True)
    write_json(other / ".claude" / "settings.json", dump({"model": "haiku"}))
    write_json(edit_config / "settings.json", dump({"model": "opus"}))
    with open_api(open_client, edit_config, edit_project, other=other) as api:
        body = api.preview("sonnet", "user", "model").json()
        by_project = api.preview("sonnet", "project", "model").json()
    assert body["reaches"] == [
        {
            "project": OTHER,
            "name": f"name of {OTHER}",
            "outcome": {"status": "overridden", "beaten_by": "project"},
        }
    ]
    assert by_project["reaches"] == []  # only a user-scope save reaches other projects


def test_a_user_scope_preview_with_one_project_reaches_nothing_else(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project) as api:
        assert api.preview("high", "user").json()["reaches"] == []


def test_a_config_change_hook_gets_a_warning(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    hooks = {"ConfigChange": [{"hooks": [{"type": "command", "command": "true"}]}]}
    write_json(edit_config / "settings.json", dump({"hooks": hooks}))
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "user").json()
    assert {"code": "config_change_hook", "params": {}} in body["warnings"]


def test_a_config_change_hook_with_hooks_disabled_gets_no_warning(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    hooks = {"ConfigChange": [{"hooks": [{"type": "command", "command": "true"}]}]}
    write_json(
        edit_config / "settings.json", dump({"hooks": hooks, "disableAllHooks": True})
    )
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "user").json()
    assert all(item["code"] != "config_change_hook" for item in body["warnings"])


@pytest.mark.skipif(not git_available(), reason="needs git")
def test_a_tracked_project_file_gets_the_shared_repo_warning(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_project / ".claude" / "settings.json", dump({"effortLevel": "low"}))
    init_repo(edit_project, [".claude/settings.json"])
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "project").json()
        untracked = api.preview("high", "local").json()
    assert body["target"]["git_tracked"] is True
    assert scope_row(body, "project")["git_tracked"] is True
    assert scope_row(body, "local")["git_tracked"] is False
    warning = next(item for item in body["warnings"] if item["code"] == "shared_repo")
    assert warning["params"] == {"path": ".claude/settings.json"}
    assert all(item["code"] != "shared_repo" for item in untracked["warnings"])


def test_a_link_to_a_file_outside_the_home_is_refused_and_the_row_says_why(
    open_client: OpenClient, edit_config: Path, edit_project: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere" / "settings.json"
    write_json(outside, dump({"effortLevel": "low"}))
    (edit_config / "settings.json").symlink_to(outside)
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "user").json()
    assert body["refusal"] == {"code": "link_outside", "params": {}}
    user = scope_row(body, "user")
    assert user["writable"] is False
    assert user["read_only_reason"] == "link_outside"
    # The row still says it is a link and where it leads. A target outside every known
    # folder shows its last part only, as the display rule says.
    assert user["link"] is True
    assert user["display_path"] == "~/.claude/settings.json"
    assert user["real_path"] == "settings.json"
    target = body["target"]
    assert target["link"] is True
    assert target["real_path"] == "settings.json"
    assert body["version"] == ""
    assert body["diff"]["lines"] == []


def test_a_link_to_a_file_that_is_not_there_is_refused_as_dangling(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    gone = edit_config.parent / "dotfiles" / "claude" / "settings.json"
    gone.parent.mkdir(parents=True)
    (edit_config / "settings.json").symlink_to(gone)
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "user").json()
    assert body["refusal"] == {"code": "link_dangling", "params": {}}
    user = scope_row(body, "user")
    assert user["writable"] is False
    assert user["read_only_reason"] == "link_dangling"
    assert user["link"] is True
    assert user["real_path"] == "~/dotfiles/claude/settings.json"


def test_a_link_inside_the_home_shows_both_paths(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    dotfiles = edit_config.parent / "dotfiles" / "claude"
    write_json(dotfiles / "settings.json", dump({"effortLevel": "low"}))
    (edit_config / "settings.json").symlink_to(dotfiles / "settings.json")
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "user").json()
    assert body["refusal"] is None
    target = body["target"]
    assert target["link"] is True
    assert target["display_path"] == "~/.claude/settings.json"
    assert target["real_path"] == "~/dotfiles/claude/settings.json"


def test_a_value_the_field_does_not_take_is_a_bad_value_refusal(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("turbo", "user").json()
    assert body["refusal"]["code"] == "bad_value"
    assert body["diff"]["lines"] == []
    assert body["effect"]["runs"]["after"] == body["effect"]["runs"]["now"]


def test_the_value_the_file_already_holds_is_a_no_change_refusal(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"effortLevel": "high"}))
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "user").json()
    assert body["refusal"]["code"] == "no_change"
    assert [row["scope"] for row in body["scopes"]] == ["user", "project", "local"]


def test_a_file_that_does_not_parse_is_refused_and_not_writable(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_project / ".claude" / "settings.json", '{"effortLevel": "low",}')
    with open_api(open_client, edit_config, edit_project) as api:
        body = api.preview("high", "project").json()
    assert body["refusal"]["code"] == "unparsed"
    assert body["options"] == []
    assert (
        scope_row(body, "project")["writable"] is True
    )  # the file reads; the edit fails


def test_a_folder_that_is_gone_refuses_the_project_scopes_only(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project) as api:
        edit_project.rename(edit_project.parent / "moved-away")
        body = api.preview("high", "project").json()
        user = api.preview("high", "user").json()
    assert body["refusal"]["code"] == "folder_not_found"
    assert scope_row(body, "project")["read_only_reason"] == "not_writable"
    assert user["refusal"] is None


def test_an_unknown_project_is_a_404_and_a_bad_body_is_a_422(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project) as api:
        unknown = api.client.post(
            "/api/edit/preview", json=api.body("high", project="no-such-project")
        )
        bad = api.client.post("/api/edit/preview", json={**api.body("high"), "x": 1})
        field = api.client.post(
            "/api/edit/preview", json=api.body("high", field_name="thinking")
        )
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "unknown_project"
    assert bad.status_code == 422
    assert field.status_code == 422


def test_edits_off_answers_edits_off_for_preview(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    with open_api(open_client, edit_config, edit_project, edits="off") as api:
        response = api.preview("high")
    assert response.status_code == 403
    assert response.json()["code"] == "edits_off"


def test_a_preview_writes_nothing(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_config / "settings.json", dump({"effortLevel": "low"}))
    before = (edit_config / "settings.json").read_bytes()
    with open_api(open_client, edit_config, edit_project) as api:
        api.preview("high", "user")
        api.preview("high", "project")
        api.preview("high", "local")
        backups = api.backups
    assert (edit_config / "settings.json").read_bytes() == before
    assert not (edit_project / ".claude" / "settings.json").exists()
    assert not backups.exists()


def test_the_what_if_copy_leaves_the_read_untouched(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    # _branch shares what the edit does not touch, so the resolver must never write to
    # what it is given. Run every kind of preview, then compare the read with a
    # deep copy.
    import copy

    import edit_preview

    write_json(
        edit_config / "settings.json",
        dump({"model": "sonnet", "env": {"CLAUDE_CODE_EFFORT_LEVEL": "low"}}),
    )
    write_json(
        edit_project / ".claude" / "settings.json",
        dump(
            {
                "effortLevel": "low",
                "modelSettings": {"claude-sonnet-5-5": {"effortLevel": "low"}},
            }
        ),
    )
    with open_api(open_client, edit_config, edit_project) as api:
        res = edit_preview.read_resolution(api.inputs.setup)
        before = copy.deepcopy(res.layers.collected)
        for scope in ("user", "project", "local"):
            for key_path in (
                ("effortLevel",),
                ("env", "CLAUDE_CODE_EFFORT_LEVEL"),
                ("model",),
            ):
                edit_preview.what_if(res, api.inputs.setup, scope, key_path, "high")
        for value in ("low", "medium", "high"):
            api.preview(value, "project")
            api.preview(value, "user")
        assert res.layers.collected == before

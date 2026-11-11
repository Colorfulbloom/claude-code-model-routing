"""The M6 edit contract: models, codes, the field registry and the edit fixtures.

Nothing here writes a user file. The collector runs on a scratch tree in a temp folder.
"""

import json
import sys
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc
from conftest import assert_outside_git

import collect_settings
import edit_fields
import models
import resolve
import settings_layers

REFUSAL_CODES = {
    "changed",
    "preview_mismatch",
    "bad_version",
    "changed_since_save",
    "raced",
    "link_outside",
    "link_dangling",
    "not_regular",
    "hard_link",
    "not_owner",
    "too_large",
    "managed",
    "forbidden_path",
    "folder_not_found",
    "unknown_project",
    "not_editable",
    "bad_value",
    "no_change",
    "unparsed",
    "key_missing",
    "key_present",
    "parent_not_object",
    "repeated_key",
    "oracle_failed",
    "lock_busy",
    "write_failed",
    "ledger_damaged",
    "backup_damaged",
    "not_undoable",
    "unknown_edit",
    "forged_row",
    "request_reused",
    "cant_rebuild",
    "edits_off",
    "edit_key_unknown",
}


def _runs(value: str | None = "high", status: str = "in_effect") -> dict[str, Any]:
    return {"value": value, "status": status}


def _outcome(status: str = "in_effect", beaten_by: str | None = None) -> dict[str, Any]:
    return {"status": status, "beaten_by": beaten_by}


def _preview() -> dict[str, Any]:
    line = {"kind": "ctx", "old_n": 1, "new_n": 1, "text": "{"}
    return {
        "server_time": "2026-11-11T12:00:00Z",
        "seq": 3,
        "choice_key": "a" * 64,
        "target": {
            "scope": "local",
            "display_path": "proj/.claude/settings.local.json",
            "real_path": "/work/proj/.claude/settings.local.json",
            "link": False,
            "exists": True,
            "git_tracked": False,
            "new_file": False,
        },
        "effect": {
            "set": {"from": "medium", "to": "high"},
            "runs": {"now": _runs("medium"), "after": _runs("high")},
            "applies": "new_session",
        },
        "options": [{"value": "low", "runs_at": _runs("low")}],
        "scopes": [
            {
                "scope": "user",
                "display_path": "~/.claude/settings.json",
                "real_path": "/work/cfg/.claude/settings.json",
                "link": False,
                "git_tracked": False,
                "writable": True,
                "read_only_reason": None,
                "current_value": "medium",
                "outcome": _outcome("overridden", "local"),
            }
        ],
        "reaches": [{"project": "proj", "name": "proj", "outcome": _outcome()}],
        "warnings": [{"code": "wont_win", "params": {"scope": "local"}}],
        "diff": {
            "lines": [line, {"kind": "del", "old_n": 2, "new_n": None, "text": "x"}],
            "new_file": False,
        },
        "summary": {
            "verb": "changes",
            "lines_changed": 1,
            "display_path": "proj/.claude/settings.local.json",
        },
        "read_at": "2026-11-11T12:00:00Z",
        "version": "token",
        "refusal": None,
    }


# ---------------------------------------------------------------- models


def test_the_refusal_codes_are_the_contract() -> None:
    assert set(get_args(models.EditRefusalCode)) == REFUSAL_CODES
    assert len(get_args(models.EditRefusalCode)) == len(REFUSAL_CODES)


def test_the_small_code_types() -> None:
    assert get_args(models.EditWarningCode) == (
        "wont_win",
        "config_change_hook",
        "shared_repo",
    )
    assert get_args(models.EditReadOnlyCode) == (
        "field_until_m7",
        "risky_until_m8",
        "managed",
        "plugin",
        "not_writable",
        "link_outside",
        "link_dangling",
    )
    assert get_args(models.RecheckState) == ("checking", "confirmed", "overwritten")
    assert get_args(models.UndoState) == (
        "can_undo",
        "changed_since",
        "undone",
        "deletes_file",
        "not_undoable",
    )
    assert get_args(models.EditOp) == ("set",)
    assert get_args(models.EditScope) == ("user", "project", "local")
    assert get_args(models.SettingsEditField) == (
        "model",
        "effortLevel",
        "maxEffortLevel",
        "autoCompactWindow",
    )
    assert get_args(models.EditApplies) == ("new_session", "new_run", "picked_up")
    assert get_args(models.DiffKind) == ("ctx", "add", "del")
    assert get_args(models.HistoryOp) == ("set", "create", "undo", "restore")
    assert get_args(models.EditsMode) == ("on", "off", "unavailable")


def test_an_edit_preview_round_trips() -> None:
    sample = _preview()
    got = models.EditPreview.model_validate(sample)
    assert got.effect.set.from_ == "medium"
    assert got.effect.runs.after.status == "in_effect"
    assert json.loads(got.model_dump_json()) == json.loads(
        models.EditPreview.model_validate(
            json.loads(got.model_dump_json())
        ).model_dump_json()
    )
    assert got.model_dump(mode="json")["effect"] == sample["effect"]


def test_from_serializes_as_from() -> None:
    change = models.EditSetChange.model_validate({"from_": "low", "to": "high"})
    assert models.EditSetChange.model_validate({"from": "low", "to": "high"}) == change
    assert models.EditSetChange(from_="low", to="high") == change
    assert change.model_dump() == {"from": "low", "to": "high"}
    assert '"from":"low"' in change.model_dump_json()
    assert (
        models.EditSetChange.model_validate({"from": None, "to": 200000}).from_ is None
    )

    row = models.HistoryRow.model_validate(
        {
            "id": "r1",
            "time": "2026-11-11T12:00:00Z",
            "subject": {"kind": "main", "name": None},
            "field": "effortLevel",
            "from": "low",
            "to": "high",
            "scope": "user",
            "display_path": "~/.claude/settings.json",
            "real_path": "/work/cfg/.claude/settings.json",
            "op": "set",
            "undo_state": "can_undo",
            "undone_at": None,
            "recheck": {
                "state": "checking",
                "changed_keys": [],
                "ours_survived": None,
                "seen": False,
            },
            "not_undoable_reason": None,
        }
    )
    assert "from" in row.model_dump()
    assert "from_" not in row.model_dump()


def test_the_closed_enums_refuse_a_new_value() -> None:
    sample = _preview()
    sample["refusal"] = {"code": "made_up", "params": {}}
    with pytest.raises(ValidationError):
        models.EditPreview.model_validate(sample)
    with pytest.raises(ValidationError):
        models.EditError.model_validate(
            {"server_time": "2026-11-11T12:00:00Z", "code": "nope", "params": {}}
        )


def test_the_edit_requests_are_strict() -> None:
    body: dict[str, Any] = {
        "project": "proj",
        "op": "set",
        "scope": "local",
        "field": "effortLevel",
        "value": "high",
        "seq": 1,
    }
    assert models.EditPreviewRequest.model_validate(body).value == "high"
    save = {**body, "version": "tok", "request_id": "abcd1234"}
    assert models.EditSaveRequest.model_validate(save).request_id == "abcd1234"
    for bad in (
        {**body, "extra": 1},
        {**body, "value": True},
        {**body, "scope": "managed"},
        {**body, "op": "create_agent"},
        {**body, "seq": "1"},
    ):
        with pytest.raises(ValidationError):
            models.EditPreviewRequest.model_validate(bad)
    for bad_id in ("short", "has space!", "x" * 65):
        with pytest.raises(ValidationError):
            models.EditSaveRequest.model_validate({**save, "request_id": bad_id})
    with pytest.raises(ValidationError):
        models.EditSaveRequest.model_validate({**body, "version": "tok"})

    undo = models.EditUndoRequest.model_validate(
        {"project": "proj", "row_id": "r1", "request_id": "abcd1234"}
    )
    assert (undo.version, undo.anyway) == (None, False)


def test_app_info_and_project_gain_their_fields() -> None:
    assert models.AppInfo.model_fields["edits"].is_required()
    assert models.Project.model_fields["edit_block"].default is None
    state = models.EditsState(state="off", instance="ab12cd34")
    assert state.model_dump() == {"state": "off", "instance": "ab12cd34"}


# ---------------------------------------------------------------- registry


def test_every_field_has_a_registry_entry() -> None:
    assert set(edit_fields.FIELDS) == set(get_args(models.SettingsEditField))
    for name, field in edit_fields.FIELDS.items():
        assert field.name == name


def test_the_registry_agrees_with_the_resolver() -> None:
    mains = {
        key: skey
        for (scope, key), skey in resolve.SETTINGS_KEYS.items()
        if scope == "main"
    }
    variables: dict[str, set[str]] = {}
    for var in settings_layers.rules()["variables"]:
        for row in var["rows"]:
            if row["scope"] == "main":
                variables.setdefault(row["key"], set()).add(var["name"])
    for name, field in edit_fields.FIELDS.items():
        assert mains[name] == field.top_key
        assert set(field.env_twins) == variables.get(name, set())
        assert set(field.model_settings_fields) == {
            key
            for key, target in resolve.MODEL_SETTINGS_FIELDS.items()
            if target == name
        }
        assert field.item_id == f"settings:{field.top_key}"


def _rule_values(rule_id: str) -> list[str]:
    rule = next(r for r in settings_layers.rules()["rules"] if r["rule_id"] == rule_id)
    values = [c["values"] for c in rule["conditions"] if "values" in c]
    assert all(v == values[0] for v in values)
    return values[0]


def test_the_effort_values_match_the_rules() -> None:
    assert list(edit_fields.EFFORT_FILE_LEVELS) == _rule_values(
        "effort-level-settings-values"
    )
    assert list(edit_fields.EFFORT_CAP_LEVELS) == _rule_values(
        "max-effort-level-values"
    )


def test_the_value_checks() -> None:
    ok = edit_fields.accepts

    def no(
        field: models.SettingsEditField, value: object, *, nested: bool = False
    ) -> bool:
        return not edit_fields.accepts(field, value, nested=nested)

    assert ok("effortLevel", "xhigh")
    assert no("effortLevel", "max")
    assert no("effortLevel", "")
    assert ok("maxEffortLevel", "max")
    assert no("maxEffortLevel", "ultra")
    assert ok("autoCompactWindow", 100000)
    assert ok("autoCompactWindow", 1000000)
    assert no("autoCompactWindow", 99999)
    assert no("autoCompactWindow", 1000001)
    assert no("autoCompactWindow", True)
    assert no("autoCompactWindow", "250000")
    assert no("autoCompactWindow", "auto")
    assert ok("autoCompactWindow", "auto", nested=True)
    assert ok("model", "opus")
    assert ok("model", "m" * 200)
    assert no("model", "m" * 201)
    assert no("model", "")
    assert no("model", "   ")
    assert no("model", "opus\n")
    assert no("model", "op\x00us")
    assert no("model", 5)
    assert edit_fields.options("effortLevel") == ("low", "medium", "high", "xhigh")
    assert edit_fields.options("model") is None


def test_the_item_helpers() -> None:
    assert edit_fields.field_for_item("settings:effortLevel") == "effortLevel"
    assert (
        edit_fields.field_for_item("settings:autoCompactWindow") == "autoCompactWindow"
    )
    assert edit_fields.field_for_item("settings:promptCacheTtl") is None
    assert edit_fields.field_for_item("agents:x") is None
    for item_id in edit_fields.FIELD_UNTIL_M7_ITEMS:
        assert edit_fields.read_only_code_for_item(item_id) == "field_until_m7"
        assert edit_fields.field_for_item(item_id) is None
    assert edit_fields.read_only_code_for_item("settings:model") is None
    assert edit_fields.read_only_code_for_item("hooks:x") is None


def test_the_item_ids_exist_in_what_the_collector_makes(tmp_path: Path) -> None:
    settings = {
        "model": "opus",
        "effortLevel": "high",
        "maxEffortLevel": "xhigh",
        "autoCompactWindow": 200000,
        "alwaysThinkingEnabled": True,
        "promptCacheTtl": "1h",
        "availableModels": ["opus"],
        "fallbackModel": "sonnet",
    }
    ctx = sc.scratch(tmp_path, {"home/.claude/settings.json": json.dumps(settings)})
    got = collect_settings.COLLECTOR.read(ctx, {})
    ids = {item.id for item in got.items["settings"]}
    assert ids >= edit_fields.FIELD_UNTIL_M7_ITEMS
    assert {field.item_id for field in edit_fields.FIELDS.values()} <= ids


# ---------------------------------------------------------------- fixtures


def test_edit_config_moves_home(edit_config: Path) -> None:
    import os

    assert edit_config.name == ".claude"
    assert edit_config.is_dir()
    assert list(edit_config.iterdir()) == []
    assert os.environ["CLAUDE_CONFIG_DIR"] == str(edit_config)
    assert os.environ["HOME"] == str(edit_config.parent)
    assert_outside_git(edit_config)


def test_edit_project_has_an_empty_claude_folder(edit_project: Path) -> None:
    assert list((edit_project / ".claude").iterdir()) == []
    assert_outside_git(edit_project)


def test_the_git_check_fails_inside_a_work_tree(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    inner = tmp_path / "a" / "b"
    inner.mkdir(parents=True)
    with pytest.raises(pytest.fail.Exception):
        assert_outside_git(inner)

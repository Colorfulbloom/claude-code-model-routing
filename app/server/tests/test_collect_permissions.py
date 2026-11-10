"""The Permissions part: rules, ``defaultMode`` and extra folders (m4-build.md task 4).

The corpus cases (typical, complex, stress, broken-settings) are checked in
``test_collect_settings.py``. These tests build small worlds for the rest.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import collect_permissions
import collect_settings
from models import SetupItem
from setup_contract import Collected

COLLECTOR = collect_settings.COLLECTOR


def run(tmp_path: Path, files: dict[str, str]) -> Collected:
    return COLLECTOR.read(sc.scratch(tmp_path, files), {})


def perms(got: Collected) -> dict[str, SetupItem]:
    return {i.id: i for i in got.items["permissions"]}


def settings(**block: object) -> str:
    return json.dumps({"permissions": block}, indent=2)


@pytest.mark.parametrize(
    ("rule", "tool", "pattern"),
    [
        ("Bash", "Bash", None),
        ("Bash(git status)", "Bash", "git status"),
        ("Bash(npm run test:*)", "Bash", "npm run test:*"),
        ("Read(./.env)", "Read", "./.env"),
        ("WebFetch(domain:example.com)", "WebFetch", "domain:example.com"),
        ("mcp__server__tool", "mcp__server__tool", None),
        ("Bash(echo (hi))", "Bash", "echo (hi)"),
        (" Edit(src/**) ", "Edit", "src/**"),
    ],
)
def test_a_valid_rule_parses_to_tool_and_pattern(
    rule: str, tool: str, pattern: str | None
) -> None:
    assert collect_permissions.parse_rule(rule) == (True, tool, pattern)


@pytest.mark.parametrize(
    "rule", ["Bash(git status", "Bash()", "(x)", "", "Bash git", 7, None, ["Bash"]]
)
def test_a_rule_with_bad_syntax_is_invalid(rule: object) -> None:
    assert collect_permissions.parse_rule(rule) == (False, None, None)


def test_items_group_deny_ask_allow_then_scope_in_file_order(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {
            "managed/managed-settings.json": settings(deny=["Bash(curl:*)"]),
            "home/.claude/settings.json": settings(
                allow=["Read(a)", "Read(b)"],
                ask=["Bash(rm:*)"],
                deny=["Read(.env)"],
                defaultMode="plan",
                additionalDirectories=["../shared"],
            ),
            "proj/.claude/settings.json": settings(
                allow=["Bash(ls)"], deny=["Read(p)"]
            ),
            "proj/.claude/settings.local.json": settings(
                allow=["Bash(pwd)"], additionalDirectories=["../mine"]
            ),
        },
    )
    assert [(i.group, i.scope, i.key) for i in got.items["permissions"]] == [
        ("deny", "managed", "Bash(curl:*)"),
        ("deny", "project", "Read(p)"),
        ("deny", "user", "Read(.env)"),
        ("ask", "user", "Bash(rm:*)"),
        ("allow", "project_local", "Bash(pwd)"),
        ("allow", "project", "Bash(ls)"),
        ("allow", "user", "Read(a)"),
        ("allow", "user", "Read(b)"),
        ("default_mode", "user", "defaultMode"),
        ("directory", "project_local", "../mine"),
        ("directory", "user", "../shared"),
    ]
    assert [i.order for i in got.items["permissions"]] == list(range(11))


def test_facts_carry_kind_tool_and_pattern(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {
            "home/.claude/settings.json": settings(
                allow=["Bash(git status)", "Read"],
                defaultMode="plan",
                additionalDirectories=["/x"],
            )
        },
    )
    items = perms(got)
    fact = items["permissions:allow:Bash(git status)"].facts.permission
    assert fact is not None
    assert (fact.kind, fact.tool, fact.pattern) == ("allow", "Bash", "git status")
    fact = items["permissions:allow:Read"].facts.permission
    assert fact is not None
    assert (fact.kind, fact.tool, fact.pattern) == ("allow", "Read", None)
    fact = items["permissions:defaultMode"].facts.permission
    assert fact is not None
    assert (fact.kind, fact.tool, fact.pattern) == ("default_mode", None, None)
    fact = items["permissions:directory:/x"].facts.permission
    assert fact is not None
    assert fact.kind == "directory"
    for item in items.values():
        assert item.label_known is True
        assert item.confidence.level == "documented"
        assert [r.scope for r in item.reach] == [
            "managed",
            "project_local",
            "project",
            "user",
        ]


def test_a_rule_in_two_scopes_is_one_item_with_two_sources(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {
            "home/.claude/settings.json": settings(allow=["Bash(ls)"]),
            "proj/.claude/settings.json": settings(allow=["Bash(ls)"]),
        },
    )
    item = perms(got)["permissions:allow:Bash(ls)"]
    assert [(s.scope, s.status) for s in item.sources] == [
        ("project", "in_effect"),
        ("user", "in_effect"),
    ]
    assert item.scope == "project"
    assert item.winner == 0


def test_a_rule_line_is_its_own_line_even_when_repeated(tmp_path: Path) -> None:
    text = json.dumps({"permissions": {"allow": ["A", "B", "A"]}}, indent=2) + "\n"
    got = run(tmp_path, {"home/.claude/settings.json": text})
    (item,) = [i for i in got.items["permissions"] if i.key == "A"]
    assert [s.line for s in item.sources] == [4, 6]
    assert perms(got)["permissions:allow:B"].sources[0].line == 5


def test_a_rule_with_bad_syntax_is_wont_load(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {
            "home/.claude/settings.json": settings(
                allow=["Bash(git status", "Read"], deny=[5]
            )
        },
    )
    items = perms(got)
    assert items["permissions:allow:Bash(git status"].status == "invalid"
    assert items["permissions:allow:Read"].status == "in_effect"
    assert items["permissions:deny:5"].status == "invalid"
    rows = [r for r in got.problems if r.code == "permission_rule_invalid"]
    assert [(r.group, r.kind, r.part, r.item_id) for r in rows] == [
        ("wont_load", "problem", "permissions", "permissions:allow:Bash(git status"),
        ("wont_load", "problem", "permissions", "permissions:deny:5"),
    ]
    assert rows[0].fix.kind == "open_item"
    assert rows[0].fix.target == "permissions:allow:Bash(git status"
    assert rows[0].thing == "Bash(git status"


@pytest.mark.parametrize("mode", ["auto", "bypassPermissions"])
@pytest.mark.parametrize(
    "scope_file", ["proj/.claude/settings.json", "proj/.claude/settings.local.json"]
)
def test_default_mode_auto_and_bypass_are_ignored_from_project_files(
    tmp_path: Path, mode: str, scope_file: str
) -> None:
    got = run(tmp_path, {scope_file: settings(defaultMode=mode)})
    item = perms(got)["permissions:defaultMode"]
    assert item.status == "ignored"
    assert item.scope is None
    assert item.effective is not None
    assert (item.effective.origin, item.effective.value.text) == ("default", "default")  # pyright: ignore[reportOptionalMemberAccess]
    assert item.sources[0].status == "ignored"
    rows = [r for r in got.problems if r.part == "permissions"]
    assert [(r.group, r.code, r.item_id) for r in rows] == [
        ("not_as_set", "ignored", "permissions:defaultMode")
    ]


@pytest.mark.parametrize("mode", ["auto", "bypassPermissions"])
def test_default_mode_auto_and_bypass_count_from_user_and_managed(
    tmp_path: Path, mode: str
) -> None:
    for file in ("home/.claude/settings.json", "managed/managed-settings.json"):
        got = run(tmp_path / file.split("/")[0], {file: settings(defaultMode=mode)})
        item = perms(got)["permissions:defaultMode"]
        assert item.status == "in_effect"
        assert item.effective is not None
        assert item.effective.value.text == mode  # pyright: ignore[reportOptionalMemberAccess]
        assert [r for r in got.problems if r.part == "permissions"] == []


def test_a_project_auto_mode_loses_to_a_user_mode_and_still_reads_ignored(
    tmp_path: Path,
) -> None:
    got = run(
        tmp_path,
        {
            "proj/.claude/settings.json": settings(defaultMode="auto"),
            "home/.claude/settings.json": settings(defaultMode="acceptEdits"),
        },
    )
    item = perms(got)["permissions:defaultMode"]
    assert item.scope == "user"
    assert [(s.scope, s.status) for s in item.sources] == [
        ("project", "ignored"),
        ("user", "in_effect"),
    ]
    assert item.effective is not None
    assert item.effective.value.text == "acceptEdits"  # pyright: ignore[reportOptionalMemberAccess]


def test_a_lower_default_mode_is_overridden(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {
            "proj/.claude/settings.json": settings(defaultMode="plan"),
            "home/.claude/settings.json": settings(defaultMode="acceptEdits"),
        },
    )
    item = perms(got)["permissions:defaultMode"]
    assert [(s.scope, s.status) for s in item.sources] == [
        ("project", "in_effect"),
        ("user", "overridden"),
    ]
    assert [r for r in got.problems if r.part == "permissions"] == []


def test_a_default_mode_that_is_not_a_mode_is_a_bad_value(tmp_path: Path) -> None:
    got = run(tmp_path, {"home/.claude/settings.json": settings(defaultMode="yolo")})
    item = perms(got)["permissions:defaultMode"]
    assert item.status == "invalid"
    rows = [r for r in got.problems if r.part == "permissions"]
    assert [(r.group, r.code) for r in rows] == [("wont_load", "value_invalid")]


def test_manual_is_a_known_mode(tmp_path: Path) -> None:
    got = run(tmp_path, {"home/.claude/settings.json": settings(defaultMode="manual")})
    assert perms(got)["permissions:defaultMode"].status == "in_effect"


def test_a_rule_that_holds_a_secret_is_masked_and_ids_stay_unique(
    tmp_path: Path,
) -> None:
    got = run(
        tmp_path,
        {
            "home/.claude/settings.json": settings(
                allow=["sk-live-AAAA", "sk-live-BBBB", "Bearer abc"]
            )
        },
    )
    ids = [i.id for i in got.items["permissions"]]
    assert len(ids) == len(set(ids)) == 3
    dump = json.dumps([i.model_dump() for i in got.items["permissions"]])
    assert "AAAA" not in dump
    assert "BBBB" not in dump


def test_a_managed_rule_is_read_only(tmp_path: Path) -> None:
    got = run(
        tmp_path, {"managed/managed-settings.json": settings(deny=["Bash(curl:*)"])}
    )
    item = perms(got)["permissions:deny:Bash(curl:*)"]
    assert item.read_only_reason is not None
    assert item.read_only_reason.code == "managed"


def test_a_file_that_did_not_parse_has_no_rules_and_one_settings_row(
    tmp_path: Path,
) -> None:
    got = run(tmp_path, {"home/.claude/settings.json": '{"permissions": '})
    assert got.items["permissions"] == []
    assert [r.code for r in got.problems] == ["json_invalid"]


def test_a_permissions_value_that_is_not_an_object_is_skipped(tmp_path: Path) -> None:
    got = run(tmp_path, {"home/.claude/settings.json": '{"permissions": ["Bash"]}'})
    assert got.items["permissions"] == []

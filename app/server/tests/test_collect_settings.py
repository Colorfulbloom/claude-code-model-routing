"""The Settings, Permissions and Output style collector (m4-build.md task 4).

Every corpus case's expected.json is the oracle for the three parts, then the states
the corpus can't hold (Couldn't read, a value moved between scopes), the order across
two reads, masking, the shell and the flags. Every run reads its own copy of the corpus
inside a temp folder, never a real folder.
"""

import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import collect_settings
from models import SetupItem
from setup_contract import Collected

PARTS = ("settings", "permissions", "output_style")
COLLECTOR = collect_settings.COLLECTOR


def read(root: Path) -> Collected:
    return COLLECTOR.read(sc.context(root), {})


def by_id(got: Collected, part: str) -> dict[str, SetupItem]:
    return {i.id: i for i in got.items[part]}  # pyright: ignore[reportArgumentType]


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def world(tmp_path: Path, setup_corpus: Path) -> Path:
    """A fresh copy of the typical case."""
    return sc.world("typical", tmp_path / "world", setup_corpus)


# ---------------------------------------------------------------- the corpus


@pytest.mark.parametrize("case", sc.CASES)
@pytest.mark.parametrize("part", PARTS)
def test_items_match_the_expected_json(
    case: str, part: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = COLLECTOR.read(sc.context(root), {})
    made, wanted = sc.compare_items(got, case, part)  # pyright: ignore[reportArgumentType]
    assert made == wanted


@pytest.mark.parametrize("case", sc.CASES)
def test_problems_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = COLLECTOR.read(sc.context(root), {})
    made, wanted = sc.compare_problems(got, case, PARTS)
    assert made == wanted


@pytest.mark.parametrize("case", sc.CASES)
def test_unreadable_files_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = COLLECTOR.read(sc.context(root), {})
    wanted = [
        (u["file"], u["scope"], u["reason"])
        for part in PARTS
        for u in sc.expected(case)["parts"].get(part, {}).get("unreadable", [])
    ]
    assert [(u.file, u.scope, u.reason) for u in got.unreadable] == wanted


def test_the_always_items_are_the_only_extras(
    setup_corpus: Path, tmp_path: Path
) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    got = COLLECTOR.read(sc.context(root), {})
    assert [i.id for i in got.items["settings"]] == [
        "settings:effortLevel",
        "settings:model",
    ]
    assert got.items["permissions"] == []
    assert got.items["output_style"] == []
    assert got.problems == []
    for item in got.items["settings"]:
        assert item.sources == []
        assert item.effective is not None
        assert item.effective.origin == "default"
        assert item.scope is None


# ---------------------------------------------------------------- item fields


def test_the_item_fields_of_a_set_key(world: Path) -> None:
    got = read(world)
    model = by_id(got, "settings")["settings:model"]
    assert (model.part, model.key, model.name, model.label_known) == (
        "settings",
        "model",
        "model",
        True,
    )
    assert model.scope == "user"
    assert model.writable is False
    assert model.read_only_reason is None
    assert model.feature == "core"
    assert model.risk_tier is None
    assert model.usage is None
    assert model.not_read is None
    assert model.winner == 0
    assert model.reason is not None
    assert model.reason.code == "in_effect"
    assert model.reason.rule_id == "model-main-session-order"
    assert model.confidence.level == "tested"
    assert model.confidence.tested_on == "2.1.302"
    source = model.sources[0]
    assert source.file == "~/.claude/settings.json"
    assert source.full_path is not None
    assert source.full_path.endswith("/.claude/settings.json")
    assert Path(source.full_path).is_absolute()


def test_reach_lists_the_scopes_and_what_is_hidden(world: Path) -> None:
    items = by_id(read(world), "settings")
    assert [(r.scope, r.visible) for r in items["settings:model"].reach] == [
        ("managed", True),
        ("command_line", False),
        ("project_local", True),
        ("project", True),
        ("user", True),
        ("shell", False),
    ]
    # A key with no flag and no variable has neither hidden scope.
    got = read(world)
    plain = next(i for i in got.items["settings"] if i.key == "env.DISABLE_TELEMETRY")
    assert [r.scope for r in plain.reach] == [
        "managed",
        "project_local",
        "project",
        "user",
        "shell",
    ]
    assert [r.visible for r in plain.reach if r.scope == "shell"] == [False]


def test_label_known_follows_the_labelled_keys(world: Path) -> None:
    put(
        world / "home" / ".claude" / "settings.json",
        json.dumps(
            {
                "cleanupPeriodDays": 7,
                "model": "claude-opus-5-5",
                "env": {"ANTHROPIC_MODEL": "x", "MY_OWN": "y"},
            }
        ),
    )
    items = by_id(read(world), "settings")
    assert items["settings:cleanupPeriodDays"].label_known is False
    assert items["settings:model"].label_known is True
    assert items["settings:env.ANTHROPIC_MODEL"].label_known is True
    assert items["settings:env.MY_OWN"].label_known is False


def test_keys_other_parts_own_are_not_settings_items(world: Path) -> None:
    owned = {
        "permissions",
        "hooks",
        "enabledPlugins",
        "outputStyle",
        "enabledMcpjsonServers",
        "disableAllHooks",
    }
    ids = {i.id.split(":")[1].split(".")[0] for i in read(world).items["settings"]}
    assert ids
    assert not ids & owned


def test_a_key_with_no_resolver_row_is_top_wins(world: Path) -> None:
    put(world / "home" / ".claude" / "settings.json", '{"cleanupPeriodDays": 7}')
    put(
        world / "work" / "parent" / "proj" / ".claude" / "settings.json",
        '{\n  "cleanupPeriodDays": 3\n}',
    )
    item = by_id(read(world), "settings")["settings:cleanupPeriodDays"]
    assert [
        (s.scope, s.status, s.value.text if s.value else None) for s in item.sources
    ] == [
        ("project", "in_effect", "3"),
        ("user", "overridden", "7"),
    ]
    assert item.scope == "project"
    assert item.effective is not None
    assert item.effective.value is not None
    assert item.effective.value.text == "3"
    assert item.reason is not None
    assert item.reason.rule_id is None
    assert item.confidence.level == "documented"
    assert [s.line for s in item.sources] == [2, 1]


def test_a_managed_value_is_read_only(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    model = by_id(read(root), "settings")["settings:model"]
    assert model.read_only_reason is not None
    assert model.read_only_reason.code == "managed"
    assert model.scope == "managed"


# ---------------------------------------------------------------- the resolver


def test_a_lowered_value_names_its_cap(world: Path) -> None:
    put(
        world / "home" / ".claude" / "settings.json",
        '{\n  "model": "claude-sonnet-5-5",\n  "maxEffortLevel": "low"\n}',
    )
    put(
        world / "work" / "parent" / "proj" / ".claude" / "settings.json",
        '{\n  "effortLevel": "high"\n}',
    )
    got = read(world)
    effort = by_id(got, "settings")["settings:effortLevel"]
    assert effort.status == "lowered"
    assert effort.effective is not None
    assert effort.effective.origin == "cap"
    assert effort.effective.by_item == "settings:maxEffortLevel"
    assert effort.effective.value is not None
    assert effort.effective.value.text == "low"
    assert effort.reason is not None
    assert effort.reason.ref_item == "settings:maxEffortLevel"
    assert "settings:maxEffortLevel" in by_id(got, "settings")
    rows = [r for r in got.problems if r.item_id == "settings:effortLevel"]
    assert [(r.group, r.code) for r in rows] == [("not_as_set", "lowered")]
    assert rows[0].id == "lowered:settings:effortLevel:2"


def test_an_invalid_value_is_wont_load(world: Path) -> None:
    put(
        world / "work" / "parent" / "proj" / ".claude" / "settings.json",
        '{\n  "effortLevel": "turbo"\n}',
    )
    got = read(world)
    effort = by_id(got, "settings")["settings:effortLevel"]
    assert effort.sources[0].status == "invalid"
    rows = [r for r in got.problems if r.code == "value_invalid"]
    assert [(r.group, r.kind, r.item_id, r.line) for r in rows] == [
        ("wont_load", "problem", "settings:effortLevel", 2)
    ]
    assert rows[0].params["value"] == "turbo"


def test_an_ignored_value_that_nothing_beats_is_not_as_set(world: Path) -> None:
    """A user effortLevel on Opus 5.5 is skipped. With no higher value it is a row."""
    put(
        world / "work" / "parent" / "proj" / ".claude" / "settings.json",
        "{}",
    )
    got = read(world)
    effort = by_id(got, "settings")["settings:effortLevel"]
    assert effort.status == "ignored" or effort.sources[0].status == "ignored"
    assert [(r.group, r.code) for r in got.problems if r.part == "settings"] == [
        ("not_as_set", "ignored")
    ]


def test_an_overridden_value_is_never_a_problem(world: Path) -> None:
    put(
        world / "work" / "parent" / "proj" / ".claude" / "settings.json",
        '{"cleanupPeriodDays": 1}',
    )
    put(world / "home" / ".claude" / "settings.json", '{"cleanupPeriodDays": 9}')
    got = read(world)
    assert [r for r in got.problems if r.part == "settings"] == []


def test_a_file_that_did_not_parse_is_one_row_not_two(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("broken-settings", tmp_path / "w", setup_corpus)
    got = read(root)
    model = by_id(got, "settings")["settings:model"]
    assert model.status == "unknown"
    assert not [r for r in got.problems if r.code == "unknown"]
    assert model.reason is not None
    assert model.reason.rule_id is not None
    assert model.reason.code == "unknown"


def test_the_reason_never_carries_prose_or_an_absolute_path(
    tmp_path: Path, setup_corpus: Path
) -> None:
    for case in ("typical", "complex", "broken-settings"):
        root = sc.world(case, tmp_path / case, setup_corpus)
        for part in PARTS:
            for item in read(root).items[part]:
                shown = item.model_dump()
                for src in shown["sources"]:
                    assert Path(src["full_path"] or "/").is_absolute()
                    src["full_path"] = None  # the absolute path is for Copy path
                shown["real_path"] = None
                assert str(root) not in json.dumps(shown)
                assert item.reason is not None
                assert item.reason.code in {
                    "in_effect", "overridden", "ignored", "lowered", "invalid",
                    "default", "unknown",
                }  # fmt: skip


# ---------------------------------------------------------------- the shell


def test_a_shell_value_is_assumed_and_not_visible(world: Path) -> None:
    ctx = dataclasses.replace(
        sc.context(world), shell_env={"ANTHROPIC_MODEL": "claude-haiku-5-5"}
    )
    got = COLLECTOR.read(ctx, {})
    model = by_id(got, "settings")["settings:model"]
    assert model.scope == "shell"
    assert model.sources[0].scope == "shell"
    assert model.sources[0].key == "env.ANTHROPIC_MODEL"
    assert model.sources[0].file is None
    assert model.sources[0].full_path is None
    assert model.confidence.level == "assumed"
    assert model.read_only_reason is not None
    assert model.read_only_reason.code == "not_visible"
    assert [
        (r.scope, r.visible)
        for r in model.reach
        if r.scope in ("shell", "command_line")
    ] == [
        ("command_line", False),
        ("shell", False),
    ]
    env = by_id(got, "settings")["settings:env.ANTHROPIC_MODEL"]
    assert env.scope == "shell"
    assert env.confidence.level == "assumed"


def _effort_rows(got: Collected) -> list[Any]:
    return [r for r in got.problems if r.item_id == "settings:effortLevel"]


def test_an_empty_effort_variable_is_shown_as_ignored_but_is_not_a_problem(
    tmp_path: Path,
) -> None:
    # The rule effort-env-empty-ignored (tested on 2.1.302) says Claude Code treats an
    # empty value as not set. The Claude Code docs are silent on the empty case, so
    # the page says nothing to fix, and the source stays on the item.
    ctx = sc.scratch(
        tmp_path,
        {
            "proj/.claude/settings.json": json.dumps({"effortLevel": "high"}),
            "home/.claude/settings.json": json.dumps({"model": "claude-opus-5-5"}),
        },
    )
    ctx = dataclasses.replace(ctx, shell_env={"CLAUDE_CODE_EFFORT_LEVEL": ""})
    got = COLLECTOR.read(ctx, {})
    effort = by_id(got, "settings")["settings:effortLevel"]
    shell = [s for s in effort.sources if s.scope == "shell"]
    assert [(s.key, s.status) for s in shell] == [
        ("env.CLAUDE_CODE_EFFORT_LEVEL", "ignored")
    ]
    assert effort.status == "in_effect"
    assert effort.scope == "project"
    assert _effort_rows(got) == []


def test_one_cause_makes_one_row_for_an_empty_effort_variable(
    tmp_path: Path,
) -> None:
    # Opus 5.5 ignores a top-level effortLevel in the user file. That is a cause of its
    # own, so it keeps its one row. The empty variable adds none.
    ctx = sc.scratch(
        tmp_path,
        {
            "home/.claude/settings.json": json.dumps(
                {"model": "claude-opus-5-5", "effortLevel": "xhigh"}
            ),
        },
    )
    quiet = COLLECTOR.read(ctx, {})
    empty = COLLECTOR.read(
        dataclasses.replace(ctx, shell_env={"CLAUDE_CODE_EFFORT_LEVEL": ""}), {}
    )
    assert [(r.code, r.params["key"]) for r in _effort_rows(quiet)] == [
        ("ignored", "effortLevel")
    ]
    assert [(r.code, r.params["key"]) for r in _effort_rows(empty)] == [
        ("ignored", "effortLevel")
    ]
    assert len(empty.problems) == len(quiet.problems)


def test_a_set_effort_variable_makes_no_problem_row(tmp_path: Path) -> None:
    ctx = sc.scratch(
        tmp_path,
        {"home/.claude/settings.json": json.dumps({"model": "claude-opus-5-5"})},
    )
    got = COLLECTOR.read(
        dataclasses.replace(ctx, shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "low"}), {}
    )
    assert _effort_rows(got) == []


# ---------------------------------------------------------------- Couldn't read


def _unreadable(root: Path, kind: str, rel: str) -> Collected:
    sc.bc.make_unreadable(root, kind, rel)
    return read(root)


def test_a_file_that_is_not_utf8_is_couldnt_read(world: Path) -> None:
    got = _unreadable(world, "not_utf8", "home/.claude/settings.json")
    assert [(u.file, u.scope, u.reason) for u in got.unreadable] == [
        ("~/.claude/settings.json", "user", "not_utf8")
    ]
    assert got.unreadable[0].full_path is not None
    items = by_id(got, "settings")
    assert items["settings:model"].may_change is True
    # The project's own values still read. A user file can't change a project value.
    assert items["settings:effortLevel"].scope == "project"
    assert items["settings:effortLevel"].may_change is False
    assert by_id(got, "permissions")  # the project's rules are still items


def test_a_file_over_the_cap_is_couldnt_read(world: Path) -> None:
    got = _unreadable(world, "too_large", "home/.claude/settings.json")
    assert [(u.scope, u.reason) for u in got.unreadable] == [("user", "too_large")]


@pytest.mark.skipif(os.geteuid() == 0, reason="mode 000 does not stop root")
def test_a_file_at_mode_000_is_couldnt_read(world: Path) -> None:
    got = _unreadable(world, "mode000", "home/.claude/settings.json")
    assert [(u.scope, u.reason) for u in got.unreadable] == [("user", "permission")]
    (world / "home" / ".claude" / "settings.json").chmod(0o600)


def test_an_unreadable_managed_folder_lists_what_it_can(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    sc.bc.make_unreadable(root, "not_utf8", "managed/managed-settings.d/10-extra.json")
    got = read(root)
    assert [u.reason for u in got.unreadable] == ["not_utf8"]
    assert got.unreadable[0].scope == "managed"
    # The other managed file still loads.
    assert "settings:env.ORG_POLICY" in by_id(got, "settings")


def test_a_managed_folder_that_will_not_list_is_one_row(
    tmp_path: Path, setup_corpus: Path
) -> None:
    if os.geteuid() == 0:
        pytest.skip("mode 000 does not stop root")
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    folder = root / "managed" / "managed-settings.d"
    folder.chmod(0)
    try:
        got = read(root)
    finally:
        folder.chmod(0o700)
    assert [u.reason for u in got.unreadable] == ["folder_unlistable"]


def test_a_missing_file_is_not_a_failure(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    assert read(root).unreadable == []


# ---------------------------------------------------------------- ids and order


def test_ids_stay_when_a_value_moves_between_scopes(world: Path) -> None:
    before = read(world)
    user = world / "home" / ".claude" / "settings.json"
    project = world / "work" / "parent" / "proj" / ".claude" / "settings.json"
    user_data = json.loads(user.read_text("utf-8"))
    project_data = json.loads(project.read_text("utf-8"))
    project_data["model"] = user_data.pop("model")
    project_data["permissions"]["allow"].append(
        user_data["permissions"]["allow"].pop(0)
    )
    put(user, json.dumps(user_data, indent=2))
    put(project, json.dumps(project_data, indent=2))
    after = read(world)
    for part in PARTS:
        assert sorted(i.id for i in before.items[part]) == sorted(
            i.id for i in after.items[part]
        )
    assert by_id(before, "settings")["settings:model"].scope == "user"
    assert by_id(after, "settings")["settings:model"].scope == "project"
    assert (
        by_id(after, "permissions")["permissions:allow:Bash(git status)"].scope
        == "project"
    )


def test_two_reads_give_the_same_answer(tmp_path: Path, setup_corpus: Path) -> None:
    for case in ("typical", "complex", "stress"):
        root = sc.world(case, tmp_path / case, setup_corpus)
        first, second = read(root), read(root)
        for part in PARTS:
            assert [i.model_dump() for i in first.items[part]] == [
                i.model_dump() for i in second.items[part]
            ]
            assert [i.order for i in first.items[part]] == list(
                range(len(first.items[part]))
            )
        assert [r.model_dump() for r in first.problems] == [
            r.model_dump() for r in second.problems
        ]


def test_item_ids_are_unique(tmp_path: Path, setup_corpus: Path) -> None:
    for case in sc.CASES:
        root = sc.world(case, tmp_path / case, setup_corpus)
        got = read(root)
        for part in PARTS:
            ids = [i.id for i in got.items[part]]
            assert len(ids) == len(set(ids)), (case, part)
        rows = [r.id for r in got.problems]
        assert len(rows) == len(set(rows)), case


# ---------------------------------------------------------------- masking


def test_no_secret_of_the_corpus_reaches_an_answer(
    tmp_path: Path, setup_corpus: Path
) -> None:
    secrets = json.loads((sc.CORPUS / "secrets.json").read_text("utf-8"))
    values = [s["value"] for s in secrets["secrets"] + secrets["never"]]
    assert values
    for case in sc.CASES:
        root = sc.world(case, tmp_path / case, setup_corpus)
        got = read(root)
        dump = json.dumps(
            {
                "items": {p: [i.model_dump() for i in v] for p, v in got.items.items()},
                "problems": [r.model_dump() for r in got.problems],
                "unreadable": [u.model_dump() for u in got.unreadable],
            }
        )
        leaked = [v for v in values if v in dump]
        assert leaked == [], case


def test_secret_looking_values_are_masked_and_say_so(world: Path) -> None:
    put(
        world / "home" / ".claude" / "settings.json",
        json.dumps(
            {
                "model": "claude-opus-5-5",
                "apiKeyHelper": "/bin/get-key",
                "endpoint": "https://alice:hunter2@example.test/v1",
                "note": "plain words",
                "env": {
                    "MY_API_KEY": "plain-but-named-secret",
                    "OTHER": "sk-ant-api03-FAKEVALUE",
                    "MAX_THINKING_TOKENS": "8000",
                },
            }
        ),
    )
    items = by_id(read(world), "settings")

    def shown(item_id: str) -> tuple[str, bool]:
        value = items[item_id].effective.value  # pyright: ignore[reportOptionalMemberAccess]
        assert value is not None
        return value.text, value.masked

    assert shown("settings:env.MY_API_KEY") == ("hidden", True)
    assert shown("settings:env.OTHER") == ("hidden", True)
    assert shown("settings:env.MAX_THINKING_TOKENS") == ("8000", False)
    assert shown("settings:apiKeyHelper") == ("hidden", True)
    assert shown("settings:note") == ("plain words", False)
    text, masked = shown("settings:endpoint")
    assert masked is True
    assert "hunter2" not in text
    assert "alice" in text
    for item in items.values():
        for src in item.sources:
            assert src.value is None or "hunter2" not in src.value.text


# ---------------------------------------------------------------- the handoff


def test_the_handoff_carries_plugins_and_approvals(world: Path) -> None:
    got = read(world)
    settings: dict[str, Any] = got.handoff["settings"]  # pyright: ignore[reportAssignmentType]
    plugins = settings["enabledPlugins"]
    assert plugins[0]["scope"] == "user"
    assert plugins[0]["file"] == "~/.claude/settings.json"
    assert plugins[0]["line"] == 22
    assert plugins[0]["value"] == {
        "routing-dashboard@bartab-demo": True,
        "hivemind@bartab-demo": True,
    }
    approvals = settings["approvals"]
    assert approvals["enabledMcpjsonServers"][0]["scope"] == "project_local"
    assert approvals["enabledMcpjsonServers"][0]["value"] == ["docs"]
    assert approvals["disabledMcpjsonServers"] == []
    assert settings["layers"].ctx.project_key == "proj"


# ---------------------------------------------------------------- the signature


def test_the_signature_is_stat_only_and_changes_with_a_file(world: Path) -> None:
    ctx = sc.context(world)
    got = COLLECTOR.read(ctx, {})
    first = COLLECTOR.signature(ctx, got)
    assert COLLECTOR.signature(ctx, got) == first
    assert COLLECTOR.signature(ctx, None) == COLLECTOR.signature(ctx, None)
    path = world / "home" / ".claude" / "settings.json"
    put(path, path.read_text("utf-8").replace("opus", "haiku"))
    assert COLLECTOR.signature(ctx, got) != first
    # A new style file changes the folder's signature too.
    before = COLLECTOR.signature(ctx, got)
    put(world / "home" / ".claude" / "output-styles" / "new.md", "# new\n")
    assert COLLECTOR.signature(ctx, got) != before


def test_the_collector_has_the_contract_shape() -> None:
    assert COLLECTOR.name == "settings"
    assert list(COLLECTOR.parts) == ["settings", "permissions", "output_style"]


def test_what_a_case_says_is_never_read_is_in_no_answer(
    tmp_path: Path, setup_corpus: Path
) -> None:
    checked = 0
    for case in sc.CASES:
        never = [v for v in sc.expected(case).get("never", []) if v != "hidden"]
        root = sc.world(case, tmp_path / case, setup_corpus)
        got = read(root)
        dump = json.dumps(
            [i.model_dump() for part in PARTS for i in got.items[part]]
            + [r.model_dump() for r in got.problems]
        )
        for value in never:
            assert value not in dump, (case, value)
            checked += 1
    assert checked >= 3

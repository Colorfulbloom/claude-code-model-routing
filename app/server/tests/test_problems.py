"""Tests for the problems feed: rows, sorting, counting and the fix rules.

The corpus supplies the collectors' own rows. Unreadable files are made at test time
(git cannot hold them). The ingest's facts (unreadable transcripts, no-usage files) are
handed in as ``Transcripts``.
"""

import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_api_helpers as sah
import setup_case_helpers as sc

import claude_json
import problems
import setup_answers
import setup_codes
import setup_items
from models import ProblemFix, ProblemRow, ReadOnly, UnreadableFile
from problem_rows import make_row
from setup_contract import Collected

ROOT = os.geteuid() == 0


def bundle(
    case: str, factory: pytest.TempPathFactory, **kw: Any
) -> setup_answers.Bundle:
    claude_json.clear_cache()
    ctx = sah.materialized(factory, case)
    return setup_answers.build_bundle(sah.request_of(ctx, **kw))


def by_id(rows: list[ProblemRow]) -> dict[str, ProblemRow]:
    return {r.id: r for r in rows}


# ------------------------------------------------------------ the feed itself


@pytest.mark.parametrize("case", sc.CASES)
def test_rows_are_sorted_by_group_part_file_and_line(
    case: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    rows = bundle(case, tmp_path_factory).problems
    assert rows == setup_items.sort_problems(rows)
    assert len({r.id for r in rows}) == len(rows)


@pytest.mark.parametrize("case", sc.CASES)
def test_overridden_is_never_a_row_and_counted_covers_three_groups(
    case: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    found = bundle(case, tmp_path_factory)
    assert all("overridden" not in r.code for r in found.problems)
    want = sum(
        1
        for r in found.problems
        if r.group in ("couldnt_read", "wont_load", "not_as_set")
    )
    assert found.counted == want == problems.counted(found.problems)


def test_the_corpus_expectations_match_the_feed(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    for case in ("broken-settings", "broken-skills", "broken-agents", "broken-mcp"):
        rows = bundle(case, tmp_path_factory).problems
        got = [(r.id, r.group, r.code, r.part) for r in rows]
        want = [
            (p["id"], p["group"], p["code"], p["part"])
            for p in sc.expected(case)["problems"]
        ]
        assert sorted(got) == sorted(want), case


def test_a_clean_case_has_nothing_to_fix(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    for case in ("typical", "simple", "empty"):
        found = bundle(case, tmp_path_factory)
        assert found.problems == []
        assert found.counted == 0


# --------------------------------------------------------------- fix rules


def fixes(case: str, factory: pytest.TempPathFactory) -> dict[str, ProblemFix]:
    return {r.id: r.fix for r in bundle(case, factory).problems}


def test_a_row_about_an_item_opens_the_item(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    got = fixes("broken-settings", tmp_path_factory)
    fix = got["permission_rule_invalid:permissions:allow:Bash(git status:5"]
    assert fix == ProblemFix(
        kind="open_item", target="permissions:allow:Bash(git status", reason=None
    )


def test_a_row_about_a_whole_file_copies_its_path(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    rows = by_id(bundle("broken-settings", tmp_path_factory).problems)
    row = rows["json_invalid:.claude/settings.local.json:3"]
    assert row.fix.kind == "copy_path"
    assert row.fix.target == row.full_path
    assert row.full_path is not None
    assert Path(row.full_path).name == "settings.local.json"


def test_a_managed_file_cant_be_fixed_here(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    got = fixes("broken-settings", tmp_path_factory)
    fix = got["managed_invalid:managed/managed-settings.json:1"]
    assert fix == ProblemFix(kind="cant_fix_here", target=None, reason="managed")
    hooks = by_id(bundle("broken-hooks", tmp_path_factory).problems)
    only = hooks["hooks_disabled:hooks:allowManagedHooksOnly:2"]
    assert only.fix == ProblemFix(kind="cant_fix_here", target=None, reason="managed")
    # The same code about a user file opens the item.
    user = hooks["hooks_disabled:hooks:disableAllHooks:2"]
    assert user.fix.kind == "open_item"


def test_a_plugins_own_file_cant_be_fixed_here_but_its_enabling_setting_can(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    rows = by_id(bundle("broken-plugins", tmp_path_factory).problems)
    manifest = next(r for r in rows.values() if r.code == "plugin_manifest_invalid")
    assert manifest.fix == ProblemFix(
        kind="cant_fix_here", target=None, reason="plugin"
    )
    # A plugin that is enabled but not installed is fixed in the settings file.
    missing = next(r for r in rows.values() if r.code == "plugin_not_installed")
    assert missing.file == "~/.claude/settings.json"
    assert missing.fix == ProblemFix(
        kind="open_item", target="plugins:beta@bartab-demo", reason=None
    )


def test_a_field_a_plugin_agent_ignores_is_the_plugins_to_fix(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    rows = [r for r in bundle("complex", tmp_path_factory).problems]
    assert {r.code for r in rows} == {"plugin_field_ignored"}
    for row in rows:
        assert row.group == "not_as_set"
        assert row.fix == ProblemFix(kind="cant_fix_here", target=None, reason="plugin")


def _lowered_agent_feed(
    factory: pytest.TempPathFactory, *, managed_cap: bool
) -> list[ProblemRow]:
    """The feed for one lowered agent row, with a cap item that is user or managed."""
    found = bundle("typical", factory)
    agent = found.items["agents"][0]
    cap = found.items["settings"][0].model_copy(
        update={
            "id": "settings:maxEffortLevel",
            "scope": "managed" if managed_cap else "user",
            "read_only_reason": ReadOnly(code="managed", params={}, command=None)
            if managed_cap
            else None,
        }
    )
    row = make_row(
        code="agent_lowered",
        group="not_as_set",
        thing=agent.name,
        part="agents",
        item_id=agent.id,
        file="~/.claude/agents/a.md",
        full_path="/work/builder/.claude/agents/a.md",
        line=5,
        level="documented",
        params={
            "setting": "effort",
            "value": "high",
            "runs": "medium",
            "cap": "maxEffortLevel",
        },
        fix=ProblemFix(kind="open_item", target=cap.id, reason=None),
    )
    return problems.build_rows(
        [(Collected(problems=[row]), ("agents",))],
        {agent.id: agent, cap.id: cap},
        problems.Transcripts(),
        scope_of=lambda _p: "user",
        display=lambda p: p,
    )


def test_a_lowered_agent_opens_the_cap_that_lowers_it(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    [row] = _lowered_agent_feed(tmp_path_factory, managed_cap=False)
    assert row.fix == ProblemFix(
        kind="open_item", target="settings:maxEffortLevel", reason=None
    )


def test_a_lowered_agent_whose_cap_is_managed_cant_be_fixed_here(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    [row] = _lowered_agent_feed(tmp_path_factory, managed_cap=True)
    assert row.fix == ProblemFix(kind="cant_fix_here", target=None, reason="managed")


def test_a_user_mcp_server_offers_the_masked_remove_command(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "broken-claude-json-entry")
    claude_json.clear_cache()
    found = setup_answers.build_bundle(sah.request_of(ctx))
    rows = {r.code: r for r in found.problems}
    # The bad entry row is about a file, so it copies the file's path.
    assert rows["not_object"].fix.kind == "copy_path"
    # A user server that is itself the problem gets the command, built from the item.
    item = found.items["mcp"][0]
    assert item.read_only_reason is not None
    assert item.read_only_reason.code == "claude_json_command"
    command = item.read_only_reason.command
    assert command is not None
    row = setup_items.make_problem(
        code="mcp_bad_entry",
        group="wont_load",
        kind="problem",
        part="mcp",
        thing=item.name,
        item=item,
        file="~/.claude.json",
        full_path=None,
        line=3,
        params={},
        confidence=setup_items.DOCUMENTED,
        fix=ProblemFix(kind="open_item", target=item.id, reason=None),
    )
    fixed = problems.build_rows(
        [(Collected(problems=[row]), ("mcp",))],
        {item.id: item},
        problems.Transcripts(),
        scope_of=lambda _p: None,
        display=lambda p: p,
    )
    assert fixed[0].fix == ProblemFix(
        kind="copy_command", target=command.text, reason=None
    )
    assert command.text.startswith("claude mcp remove ")


def test_a_cant_tell_row_about_a_user_mcp_server_keeps_open_item(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "broken-claude-json-entry")
    claude_json.clear_cache()
    item = setup_answers.build_bundle(sah.request_of(ctx)).items["mcp"][0]
    row = setup_items.make_problem(
        code="env_not_visible",
        group="cant_tell",
        kind="cant_tell",
        part="mcp",
        thing=item.name,
        item=item,
        file=None,
        full_path=None,
        line=None,
        params={},
        confidence=setup_items.DOCUMENTED,
        fix=ProblemFix(kind="copy_command", target="claude mcp remove x", reason=None),
    )
    fixed = problems.build_rows(
        [(Collected(problems=[row]), ("mcp",))],
        {item.id: item},
        problems.Transcripts(),
        scope_of=lambda _p: None,
        display=lambda p: p,
    )
    assert fixed[0].fix == ProblemFix(kind="open_item", target=item.id, reason=None)


# ------------------------------------------------------------- Couldn't read


@pytest.mark.skipif(ROOT, reason="mode 000 files read fine as root")
def test_a_file_that_cant_be_read_is_a_row_that_copies_its_full_path(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    root = sah.fresh(tmp_path_factory, "typical")
    sc.bc.make_unreadable(root, "mode000", "home/.claude/agents/scribe.md")
    sc.bc.make_unreadable(root, "too_large", "home/.claude/agents/huge.md")
    claude_json.clear_cache()
    found = setup_answers.build_bundle(sah.request_of(sc.context(root)))
    rows = by_id([r for r in found.problems if r.group == "couldnt_read"])
    assert sorted(rows) == [
        "permission:~/.claude/agents/scribe.md",
        "too_large:~/.claude/agents/huge.md",
    ]
    for row in rows.values():
        assert row.kind == "read_failure"
        assert row.part == "agents"
        assert row.item_id is None
        assert row.line is None
        assert row.full_path is not None
        assert row.fix == ProblemFix(
            kind="copy_path", target=row.full_path, reason=None
        )
        assert row.file is not None
        assert not row.file.startswith("/")
    assert found.counted == 2


def test_a_file_outside_the_roots_makes_no_row(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = bundle("scope-symlink", tmp_path_factory)
    assert not any(r.group == "couldnt_read" for r in found.problems)
    outside = [
        u
        for part in found.unreadable.values()
        for u in part
        if u.reason in setup_codes.NOT_READ_REASONS
    ]
    assert outside
    assert all(u.problem is None for u in outside)


def test_a_vanished_file_and_an_unlistable_folder_are_rows_too() -> None:
    gone = UnreadableFile(
        file="~/.claude/agents/x.md",
        full_path="/work/me/.claude/agents/x.md",
        scope="user",
        reason="vanished",
        problem=None,
        part="agents",
    )
    folder = UnreadableFile(
        file="~/.claude/skills",
        full_path="/work/me/.claude/skills",
        scope="user",
        reason="folder_unlistable",
        problem=None,
        part=None,
    )
    rows = problems.build_rows(
        [(Collected(unreadable=[gone, folder]), ("agents", "skills"))],
        {},
        problems.Transcripts(),
        scope_of=lambda _p: None,
        display=lambda p: p,
    )
    got = {r.code: r for r in rows}
    assert got["vanished"].part == "agents"
    # A file with no part goes to the first part of its collector.
    assert got["folder_unlistable"].part == "agents"
    assert all(r.group == "couldnt_read" for r in rows)


def test_the_same_failed_file_reported_twice_is_one_row() -> None:
    one = UnreadableFile(
        file="~/.claude/settings.json",
        full_path="/work/me/.claude/settings.json",
        scope="user",
        reason="permission",
        problem=None,
        part=None,
    )
    rows = problems.build_rows(
        [
            (Collected(unreadable=[one]), ("settings", "permissions")),
            (Collected(unreadable=[one]), ("plugins",)),
        ],
        {},
        problems.Transcripts(),
        scope_of=lambda _p: None,
        display=lambda p: p,
    )
    assert [r.id for r in rows] == ["permission:~/.claude/settings.json"]


# -------------------------------------------------------- the ingest's facts


def test_unreadable_transcripts_are_couldnt_read_rows_coded_transcript_unreadable(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")
    path = str(ctx.config_dir / "projects" / "-work-proj" / "abc123.jsonl")
    other = str(ctx.config_dir / "projects" / "-work-proj" / "def456.jsonl")
    claude_json.clear_cache()
    found = setup_answers.build_bundle(
        sah.request_of(ctx, transcripts=problems.Transcripts(unreadable=(path, other)))
    )
    rows = [r for r in found.problems if r.code == "transcript_unreadable"]
    assert [r.thing for r in rows] == ["abc123.jsonl", "def456.jsonl"]
    first = rows[0]
    assert first.group == "couldnt_read"
    assert first.kind == "read_failure"
    assert first.part is None
    assert first.file == "~/.claude/projects/-work-proj/abc123.jsonl"
    assert first.full_path == path
    assert first.fix == ProblemFix(kind="copy_path", target=path, reason=None)
    assert (
        first.id == "transcript_unreadable:~/.claude/projects/-work-proj/abc123.jsonl"
    )
    assert found.counted == 2
    # They sit among the other Couldn't read rows, first in the feed.
    assert [r.group for r in found.problems] == ["couldnt_read", "couldnt_read"]


def test_files_without_usage_make_one_uncounted_notice(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = bundle(
        "typical", tmp_path_factory, transcripts=problems.Transcripts(no_usage_rows=3)
    )
    assert [(r.code, r.group, r.kind, r.params) for r in found.problems] == [
        ("rows_no_usage", "notice", "notice", {"count": "3"})
    ]
    assert found.counted == 0
    assert [(n.code, n.params) for n in found.notices] == [
        ("rows_no_usage", {"count": "3"})
    ]
    assert found.problems[0].fix.kind == "cant_fix_here"
    assert found.problems[0].fix.reason in setup_codes.CANT_FIX_REASONS


def test_read_failure_id_is_the_reason_and_the_display_file() -> None:
    assert problems.read_failure_id("not_utf8", "CLAUDE.md") == "not_utf8:CLAUDE.md"
    assert problems.is_read_failure(
        UnreadableFile(
            file="a", full_path=None, scope=None, reason="permission", problem=None
        )
    )
    assert not problems.is_read_failure(
        UnreadableFile(
            file="a", full_path=None, scope=None, reason="outside_scope", problem=None
        )
    )


def test_a_row_without_a_path_or_item_cant_be_fixed_here() -> None:
    file = UnreadableFile(
        file="~/.claude/x",
        full_path=None,
        scope=None,
        reason="permission",
        problem=None,
    )
    rows = problems.build_rows(
        [(Collected(unreadable=[file]), ("settings",))],
        {},
        problems.Transcripts(),
        scope_of=lambda _p: None,
        display=lambda p: p,
    )
    assert rows[0].fix == ProblemFix(
        kind="cant_fix_here", target=None, reason="not_visible"
    )

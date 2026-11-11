"""The closed-enum test: every code a collector emits is in ``setup_codes``.

Three ways to catch a code that has no entry. A run over every corpus case (and the
unreadable-file variants git cannot hold, and the overlaid demo) checks the problem
codes, the groups they sit in, the item reason codes, the unreadable reasons, the parts,
scopes, fix kinds and read-only codes of what the collectors really return. A scan of
the collector sources checks the literal codes they write. The registry's own tables
are checked for consistency. Task 12 writes the page's strings against the same module.
"""

import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_api_helpers as sah
import setup_case_helpers as sc

import claude_json
import fixture_provider
import setup_answers
import setup_codes
from models import SETUP_PARTS, SETUP_SCOPES, Coded, ProblemRow, SetupItem

SERVER = Path(__file__).resolve().parents[1]
CODE_SOURCES = (
    "collect_agents.py",
    "collect_hooks.py",
    "collect_instructions.py",
    "collect_mcp.py",
    "collect_output_style.py",
    "collect_permissions.py",
    "collect_plugins.py",
    "collect_settings.py",
    "collect_skills.py",
    "claude_json.py",
    "setup_items.py",
    "problem_rows.py",
    "problems.py",
)
LITERAL = re.compile(r"""\bcode=["']([a-z_]+)["']""")
ROOT = os.geteuid() == 0

# A damaged file per kind, in the cases that hold the file.
DAMAGE = (
    ("mode000", "typical", "home/.claude/settings.json"),
    ("mode000", "typical", "home/.claude/agents/scribe.md"),
    ("mode000", "typical", "work/parent/proj/CLAUDE.md"),
    ("mode000", "typical", "work/parent/proj/.mcp.json"),
    ("not_utf8", "typical", "home/.claude/settings.json"),
    ("not_utf8", "typical", "work/parent/proj/.claude/settings.local.json"),
    ("not_utf8", "typical", "home/.claude/skills/standup-notes/SKILL.md"),
    ("too_large", "typical", "home/.claude/agents/huge.md"),
    ("too_large", "typical", "work/parent/proj/CLAUDE.md"),
    ("claude_json_too_large", "typical", "home/.claude.json"),
)


def _emitted(bundle: setup_answers.Bundle) -> dict[str, Any]:
    """Return every coded thing a bundle holds, by kind."""
    items: list[SetupItem] = [i for part in SETUP_PARTS for i in bundle.items[part]]
    return {
        "problems": list(bundle.problems),
        "items": items,
        "unreadable": [u for part in SETUP_PARTS for u in bundle.unreadable[part]],
        "rows": bundle.rows,
        "notices": bundle.notices,
    }


def _check(  # noqa: PLR0912 - one branch per kind of coded thing
    bundle: setup_answers.Bundle, where: str
) -> None:
    got = _emitted(bundle)
    row: ProblemRow
    for row in got["problems"]:
        assert row.code in setup_codes.PROBLEM_CODES, f"{where}: problem {row.code}"
        assert setup_codes.PROBLEM_CODES[row.code] == row.group, (
            f"{where}: {row.code} is in group {row.group}"
        )
        assert row.fix.kind in setup_codes.FIX_KINDS, where
        if row.fix.kind == "cant_fix_here":
            assert row.fix.reason in setup_codes.CANT_FIX_REASONS, where
        assert row.part is None or row.part in SETUP_PARTS, where
    item: SetupItem
    for item in got["items"]:
        assert item.part in SETUP_PARTS, where
        if item.reason is not None:
            assert item.reason.code in setup_codes.ITEM_REASON_CODES, (
                f"{where}: reason {item.reason.code} on {item.id}"
            )
        for src in item.sources:
            assert src.scope in SETUP_SCOPES, where
        for reach in item.reach:
            assert reach.scope in SETUP_SCOPES, where
        if item.read_only_reason is not None:
            assert item.read_only_reason.code in setup_codes.READ_ONLY_CODES, where
        if item.loads is not None:
            assert item.loads.kind in setup_codes.LOADS_KINDS, where
        if item.facts.instruction is not None:
            for ref in item.facts.instruction.imports:
                assert ref.state in setup_codes.IMPORT_STATES, where
        if item.facts.permission is not None:
            assert item.facts.permission.kind in setup_codes.PERMISSION_KINDS, where
        if item.usage is not None:
            assert item.usage.code in setup_codes.USAGE_CODES, where
        if item.part == "agents" and item.group is not None:
            assert item.group in setup_codes.AGENT_GROUPS, where
    for file in got["unreadable"]:
        assert file.reason in setup_codes.UNREADABLE_REASONS, where
        if file.scope is not None:
            assert file.scope in SETUP_SCOPES, where
    for part_row in got["rows"]:
        assert part_row.summary.code == setup_codes.SUMMARY_CODES[part_row.part], where
        for cell in part_row.scopes:
            if cell.summary is not None:
                assert cell.summary.code in setup_codes.CELL_CODES, where
        if part_row.empty is not None:
            assert part_row.empty.reason in setup_codes.EMPTY_REASONS, where
            if part_row.empty.action is not None:
                assert part_row.empty.action in setup_codes.EMPTY_ACTIONS, where
    notice: Coded
    for notice in got["notices"]:
        assert notice.code in setup_codes.NOTICE_CODES, where


@pytest.mark.parametrize("case", sc.CASES)
def test_every_corpus_case_emits_registered_codes(
    case: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    ctx = sah.materialized(tmp_path_factory, case)
    claude_json.clear_cache()
    _check(setup_answers.build_bundle(sah.request_of(ctx)), case)


def test_the_notice_codes_are_the_three_the_map_can_carry() -> None:
    assert sorted(setup_codes.NOTICE_CODES) == [
        "project_not_listed",
        "rows_no_usage",
        "version_gap",
    ]


@pytest.mark.parametrize("version", ["2.1.310", ""])
def test_a_version_gap_notice_is_a_registered_code(
    version: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")
    claude_json.clear_cache()
    bundle = setup_answers.build_bundle(sah.request_of(ctx, claude_version=version))
    _check(bundle, f"version {version!r}")
    assert [n.code for n in bundle.notices] == (["version_gap"] if version else [])
    for notice in bundle.notices:
        assert set(notice.params) == {"installed", "checked_on", "due"}
        assert notice.params["due"].isdigit()


@pytest.mark.skipif(ROOT, reason="mode 000 files read fine as root")
@pytest.mark.parametrize(("kind", "case", "rel"), DAMAGE)
def test_unreadable_variants_emit_registered_codes(
    kind: str, case: str, rel: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    root = sah.fresh(tmp_path_factory, case)
    sc.bc.make_unreadable(root, kind, rel)
    claude_json.clear_cache()
    bundle = setup_answers.build_bundle(sah.request_of(sc.context(root)))
    _check(bundle, f"{kind} {rel}")
    codes = {row.code for row in bundle.problems if row.group == "couldnt_read"}
    wanted = {"mode000": "permission", "not_utf8": "not_utf8"}.get(kind, "too_large")
    assert wanted in codes, (kind, rel, codes)


def test_the_overlaid_demo_emits_registered_codes(
    tmp_path_factory: pytest.TempPathFactory, demo_build: Path
) -> None:
    demo = sah.overlaid_demo(tmp_path_factory, demo_build)
    world = fixture_provider.demo_world(demo)
    assert len(world.contexts) >= 8
    for key, ctx in world.contexts.items():
        claude_json.clear_cache()
        _check(setup_answers.build_bundle(sah.request_of(ctx)), key)


def test_the_collector_sources_write_only_registered_codes() -> None:
    known = (
        set(setup_codes.PROBLEM_CODES)
        | set(setup_codes.ITEM_REASON_CODES)
        | set(setup_codes.READ_ONLY_CODES)
        | set(setup_codes.UNREADABLE_REASONS)
    )
    missing: list[str] = []
    for name in CODE_SOURCES:
        text = (SERVER / name).read_text(encoding="utf-8")
        missing += [
            f"{name}: {code}" for code in LITERAL.findall(text) if code not in known
        ]
    assert missing == []


def test_the_agents_page_unchecked_reason_is_registered() -> None:
    import agent_setup

    assert agent_setup.UNCHECKED_CODE in setup_codes.AGENT_CHECK_CODES
    assert agent_setup.UNCHECKED_CODE not in setup_codes.PROBLEM_CODES


def test_every_problem_group_a_code_names_is_a_group() -> None:
    groups = {"couldnt_read", "wont_load", "not_as_set", "cant_tell", "notice"}
    assert set(setup_codes.PROBLEM_CODES.values()) <= groups
    assert groups <= set(setup_codes.PROBLEM_CODES.values())


def test_a_read_failure_reason_is_a_couldnt_read_code() -> None:
    for reason in setup_codes.READ_FAILURE_REASONS:
        assert setup_codes.group_of(reason) == "couldnt_read"
    assert setup_codes.group_of("transcript_unreadable") == "couldnt_read"
    assert setup_codes.group_of("not_a_code") is None
    assert setup_codes.NOT_READ_REASONS.isdisjoint(setup_codes.READ_FAILURE_REASONS)


def test_the_plan_codes_are_all_registered() -> None:
    plan = (  # noqa: SIM905 - a word list reads better than a list of quoted words
        "permission not_utf8 too_large folder_unlistable transcript_unreadable "
        "json_invalid not_object managed_invalid value_invalid frontmatter_invalid "
        "agent_no_name agent_no_description agent_not_md same_name_in_folder "
        "skill_no_md import_missing import_too_deep import_cycle hook_bad_event "
        "hook_bad_handler mcp_bad_entry plugin_not_installed plugin_manifest_invalid "
        "output_style_missing permission_rule_invalid ignored lowered "
        "plugin_field_ignored hooks_disabled unknown import_out_of_scope "
        "env_not_visible plugin_format_unknown walk_stopped rows_no_usage"
    ).split()
    assert [c for c in plan if c not in setup_codes.PROBLEM_CODES] == []
    beyond = sorted(set(setup_codes.PROBLEM_CODES) - set(plan))
    assert beyond == [
        "agent_lowered",
        "frontmatter_reader_gap",
        "plugin_outside_plugins",
        "vanished",
    ]

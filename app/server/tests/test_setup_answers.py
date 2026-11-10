"""Tests for the setup answer builder: the map, a part, the cache and the etag.

The corpus cases are the inputs. Each test names the case it reads and what it must
say, from the case's hand-written expectations (``expected.json``) or from the
contract in ``models.py``.
"""

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_api_helpers as sah
import setup_case_helpers as sc

import claude_json
import setup_answers
import setup_codes
from models import (
    SETUP_PARTS,
    SETUP_SCOPES,
    SetupMap,
    SetupPartAnswer,
    Unchanged,
)
from problems import Transcripts

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
STARTED = datetime(2026, 11, 9, 11, 0, tzinfo=UTC)
ROOT = os.geteuid() == 0


def service() -> setup_answers.SetupService:
    return setup_answers.SetupService(started_at=STARTED)


def the_map(case: str, factory: pytest.TempPathFactory, **kw: Any) -> SetupMap:
    ctx = sah.materialized(factory, case)
    claude_json.clear_cache()
    found = service().setup_map(sah.request_of(ctx, **kw), None, NOW)
    assert isinstance(found, SetupMap)
    return found


def a_part(
    case: str, part: Any, factory: pytest.TempPathFactory, **kw: Any
) -> SetupPartAnswer:
    ctx = sah.materialized(factory, case)
    claude_json.clear_cache()
    found = service().setup_part(sah.request_of(ctx, **kw), part, None, NOW)
    assert isinstance(found, SetupPartAnswer)
    return found


# ------------------------------------------------------------------- the map


def test_the_map_has_the_ten_parts_in_order_each_with_seven_scope_cells(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = the_map("typical", tmp_path_factory)
    assert [row.part for row in found.parts] == list(SETUP_PARTS)
    for row in found.parts:
        assert [cell.scope for cell in row.scopes] == list(SETUP_SCOPES)
    assert found.server_started_at == STARTED
    assert found.listed is True
    assert found.unchanged is False


def test_the_settings_row_says_the_model_and_effort_that_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    row = the_map("complex", tmp_path_factory).parts[0]
    assert row.part == "settings"
    assert row.summary.code == "model_effort"
    assert row.summary.params == {"model": "claude-sonnet-5-5", "effort": "medium"}


def test_part_summaries_count_what_the_part_holds(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    rows = {r.part: r for r in the_map("complex", tmp_path_factory).parts}
    assert rows["agents"].summary.params == {"count": "5"}
    assert rows["instructions"].summary.params["count"] == "9"
    assert rows["rules"].summary.params == {
        "count": "3",
        "on_demand": "1",
        "globs": "src/**/*.ts",
    }
    assert rows["hooks"].summary.params == {"count": "5", "events": "3"}
    assert rows["permissions"].summary.params == {
        "allow": "2",
        "ask": "1",
        "deny": "2",
        "mode": "acceptEdits",
    }
    assert rows["mcp"].summary.params == {"count": "5", "not_approved": "0"}
    assert rows["plugins"].summary.params == {"count": "2", "enabled": "2"}
    assert rows["output_style"].summary.params == {"active": "review-voice"}


def test_status_counts_are_worst_first_and_add_up_to_the_items(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "broken-agents")
    bundle = setup_answers.build_bundle(sah.request_of(ctx))
    row = next(r for r in bundle.rows if r.part == "agents")
    assert sum(s.count for s in row.statuses) == len(bundle.items["agents"])
    order = [
        "invalid",
        "overridden",
        "ignored",
        "unknown",
        "lowered",
        "default",
        "in_effect",
    ]
    seen = [order.index(s.status) for s in row.statuses]
    assert seen == sorted(seen)


def test_counted_problems_land_on_the_part_they_belong_to(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = the_map("broken-settings", tmp_path_factory)
    by_part = {r.part: r.counted_problems for r in found.parts}
    expected = sc.expected("broken-settings")["problems"]
    for part in SETUP_PARTS:
        want = sum(
            1
            for p in expected
            if p["part"] == part
            and p["group"] in ("couldnt_read", "wont_load", "not_as_set")
        )
        assert by_part[part] == want, part


def test_an_empty_part_says_why_and_offers_an_action(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "empty")
    found = service().setup_map(sah.request_of(ctx), None, NOW)
    assert isinstance(found, SetupMap)
    rows = {r.part: r for r in found.parts}
    assert rows["settings"].empty is None  # model and effort are always there
    assert rows["hooks"].empty is not None
    assert rows["hooks"].empty.action == "docs"
    assert rows["hooks"].empty.target == "https://code.claude.com/docs/en/hooks"
    folder = rows["agents"].empty
    assert folder is not None
    assert folder.action == "copy_path"
    assert folder.target == str(ctx.project_dir / ".claude" / "agents")  # type: ignore[operator]
    file = rows["instructions"].empty
    assert file is not None
    assert file.target == str(ctx.project_dir / "CLAUDE.md")  # type: ignore[operator]
    assert all(r.empty is None or r.empty.reason == "none_found" for r in found.parts)


def test_scope_cells_say_set_not_set_and_not_visible(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = the_map("typical", tmp_path_factory)
    cells = {r.part: {c.scope: c for c in r.scopes} for r in found.parts}
    # Command line is never visible, and only Settings sees the shell.
    assert all(cells[p]["command_line"].state == "not_visible" for p in SETUP_PARTS)
    assert cells["settings"]["shell"].state in ("set", "not_set")
    assert cells["agents"]["shell"].state == "not_visible"
    assert cells["agents"]["user"].state == "set"
    assert cells["agents"]["user"].summary is not None
    assert cells["agents"]["user"].summary.code == "count"
    assert cells["agents"]["managed"].state == "not_set"
    assert cells["agents"]["managed"].summary is None
    user = cells["settings"]["user"]
    assert user.state == "set"
    assert user.summary is not None
    assert user.summary.code in ("model_effort", "count")


def test_a_project_that_is_not_listed_reads_not_read_here_with_a_notice(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = the_map("scope-unlisted", tmp_path_factory)
    assert found.listed is False
    assert [n.code for n in found.notices] == ["project_not_listed"]
    for row in found.parts:
        by_scope = {c.scope: c for c in row.scopes}
        assert by_scope["project"].state == "not_visible"
        assert by_scope["project_local"].state == "not_visible"
        assert by_scope["project"].summary is None


def test_a_listed_project_has_no_not_listed_notice(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    assert the_map("typical", tmp_path_factory).notices == []


@pytest.mark.skipif(ROOT, reason="mode 000 files read fine as root")
def test_a_part_with_an_unreadable_file_is_flagged_and_its_scope_cell_says_so(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    root = sah.fresh(tmp_path_factory, "typical")
    sc.bc.make_unreadable(root, "mode000", "home/.claude/agents/scribe.md")
    claude_json.clear_cache()
    found = service().setup_map(sah.request_of(sc.context(root)), None, NOW)
    assert isinstance(found, SetupMap)
    agents = next(r for r in found.parts if r.part == "agents")
    assert agents.unreadable is True
    assert {c.scope: c.state for c in agents.scopes}["user"] == "unreadable"
    assert agents.counted_problems == 1
    others = [r for r in found.parts if r.part != "agents"]
    assert not any(r.unreadable for r in others)


# ------------------------------------------------------------------- a part


def test_items_come_in_their_order_and_groups_in_order_with_counts(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    perms = a_part("complex", "permissions", tmp_path_factory)
    assert [i.order for i in perms.items] == list(range(len(perms.items)))
    assert [(g.key, g.count) for g in perms.groups] == [
        ("deny", 2),
        ("ask", 1),
        ("allow", 2),
        ("default_mode", 1),
        ("directory", 1),
    ]
    hooks = a_part("complex", "hooks", tmp_path_factory)
    assert [g.key for g in hooks.groups] == [
        "SessionStart",
        "PreToolUse",
        "PostToolUse",
    ]
    assert sum(g.count for g in hooks.groups) == len(hooks.items)


def test_a_part_without_groups_has_none(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    assert a_part("complex", "skills", tmp_path_factory).groups == []


def test_an_empty_part_answers_no_items_and_its_empty_info(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = a_part("empty", "skills", tmp_path_factory)
    assert found.items == []
    assert found.empty is not None
    assert found.empty.action == "copy_path"
    assert a_part("complex", "skills", tmp_path_factory).empty is None


def test_unreadable_files_are_split_by_part_with_their_problem_ids(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    if ROOT:
        pytest.skip("mode 000 files read fine as root")
    root = sah.fresh(tmp_path_factory, "typical")
    sc.bc.make_unreadable(root, "mode000", "home/.claude/settings.json")
    sc.bc.make_unreadable(root, "not_utf8", "work/parent/proj/CLAUDE.md")
    claude_json.clear_cache()
    svc = service()
    request = sah.request_of(sc.context(root))
    settings = svc.setup_part(request, "settings", None, NOW)
    perms = svc.setup_part(request, "permissions", None, NOW)
    instr = svc.setup_part(request, "instructions", None, NOW)
    agents = svc.setup_part(request, "agents", None, NOW)
    assert isinstance(settings, SetupPartAnswer)
    assert isinstance(perms, SetupPartAnswer)
    assert isinstance(instr, SetupPartAnswer)
    assert isinstance(agents, SetupPartAnswer)
    # A settings file feeds Settings, Permissions and Output style alike.
    assert [u.reason for u in settings.unreadable] == ["permission"]
    assert [u.reason for u in perms.unreadable] == ["permission"]
    assert settings.unreadable[0].problem == "permission:~/.claude/settings.json"
    assert settings.unreadable[0].part == "settings"
    assert perms.unreadable[0].part == "permissions"
    assert [(u.file, u.reason) for u in instr.unreadable] == [("CLAUDE.md", "not_utf8")]
    assert instr.unreadable[0].problem == "not_utf8:CLAUDE.md"
    assert agents.unreadable == []
    feed = svc.problems(request, None, NOW)
    ids = {r.id for r in feed.rows}  # type: ignore[union-attr]
    assert settings.unreadable[0].problem in ids
    assert instr.unreadable[0].problem in ids


def test_a_file_outside_the_roots_is_not_read_here_and_has_no_problem_id(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = a_part("scope-unlisted", "instructions", tmp_path_factory)
    del found
    skills = a_part("complex", "plugins", tmp_path_factory)
    for file in skills.unreadable:
        assert file.reason in setup_codes.NOT_READ_REASONS
        assert file.problem is None


# --------------------------------------------------------------------- usage


def usage(agent_runs: dict[str, int]) -> setup_answers.SetupUsage:
    return setup_answers.SetupUsage(
        days=30,
        agent_runs=agent_runs,
        main_pairs={
            ("claude-sonnet-5-5", "medium"): 4,
            ("claude-opus-5-5", "high"): 1,
            ("claude-sonnet-5-5-20260101", None): 2,
        },
    )


def test_agents_get_runs_and_a_no_runs_group_from_the_store(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = a_part(
        "typical",
        "agents",
        tmp_path_factory,
        usage=usage({"builder": 7, "planner": 1}),
    )
    by_id = {i.id: i for i in found.items}
    assert by_id["agents:builder"].usage is not None
    assert by_id["agents:builder"].usage.code == "agent_runs"
    assert by_id["agents:builder"].usage.params == {"runs": "7", "days": "30"}
    assert by_id["agents:builder"].group == "ran"
    assert by_id["agents:scribe"].usage is not None
    assert by_id["agents:scribe"].usage.params["runs"] == "0"
    assert by_id["agents:scribe"].group == "no_runs"
    assert [(g.key, g.count) for g in found.groups] == [("ran", 2), ("no_runs", 3)]
    # Rows keep the part's own order, so a run never reorders the list.
    assert [i.id for i in found.items] == sorted(i.id for i in found.items)


def test_a_plugin_agent_counts_runs_under_its_namespaced_type(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = a_part(
        "complex",
        "agents",
        tmp_path_factory,
        usage=usage({"routing-dashboard:scout": 3}),
    )
    plugin = next(i for i in found.items if i.id == "agents:routing-dashboard:scout")
    assert plugin.usage is not None
    assert plugin.usage.params["runs"] == "3"
    assert plugin.group == "ran"
    plain = next(i for i in found.items if i.id == "agents:scout")
    assert plain.group == "no_runs"


def test_without_store_data_agents_have_no_usage_and_no_groups(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = a_part("typical", "agents", tmp_path_factory)
    assert found.groups == []
    assert all(i.usage is None and i.group is None for i in found.items)
    row = next(
        r for r in the_map("typical", tmp_path_factory).parts if r.part == "agents"
    )
    assert "no_runs" not in row.summary.params


def test_the_map_counts_agents_with_no_recent_runs(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = the_map("typical", tmp_path_factory, usage=usage({"builder": 2}))
    row = next(r for r in found.parts if r.part == "agents")
    assert row.summary.params == {"count": "5", "no_runs": "4"}


def test_model_and_effort_settings_get_the_runs_that_used_their_value(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = a_part("complex", "settings", tmp_path_factory, usage=usage({}))
    by_id = {i.id: i for i in found.items}
    model, effort = by_id["settings:model"], by_id["settings:effortLevel"]
    assert model.usage is not None
    assert model.usage.code == "runs_at_value"
    # claude-sonnet-5-5 and its dated name are one model: 4 + 2 of 7 main runs.
    assert model.usage.params == {
        "value": "claude-sonnet-5-5",
        "runs": "6",
        "total": "7",
        "days": "30",
    }
    assert effort.usage is not None
    assert effort.usage.params["runs"] == "4"
    others = [i for i in found.items if i.id not in (model.id, effort.id)]
    assert all(i.usage is None for i in others)


# ----------------------------------------------------- the cache and the etag


def test_one_read_serves_the_three_answers_with_one_etag(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")
    svc = service()
    request = sah.request_of(ctx)
    one = svc.setup_map(request, None, NOW)
    two = svc.setup_part(request, "agents", None, NOW)
    three = svc.problems(request, None, NOW)
    assert isinstance(one, SetupMap)
    assert isinstance(two, SetupPartAnswer)
    assert not isinstance(three, Unchanged)
    assert one.etag == two.etag == three.etag
    assert len(one.etag) == 32
    assert svc.bundle(request) is svc.bundle(request)


def test_a_matching_etag_gives_the_short_answer(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")
    svc = service()
    request = sah.request_of(ctx)
    etag = svc.bundle(request).etag
    for short in (
        svc.setup_map(request, etag, NOW),
        svc.setup_part(request, "hooks", etag, NOW),
        svc.problems(request, etag, NOW),
    ):
        assert isinstance(short, Unchanged)
        assert short.unchanged is True
        assert short.etag == etag
        assert short.project == "proj"
    assert isinstance(svc.setup_map(request, "stale", NOW), SetupMap)


def test_a_cached_read_is_not_rebuilt_while_nothing_changes(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")
    svc = service()
    request = sah.request_of(ctx)
    svc.bundle(request)
    built: list[int] = []
    real = setup_answers.build_bundle

    def counting(req: setup_answers.SetupRequest) -> setup_answers.Bundle:
        built.append(1)
        return real(req)

    monkeypatch.setattr(setup_answers, "build_bundle", counting)
    for _ in range(3):
        svc.bundle(request)
    assert built == []


def test_a_changed_file_drops_the_cache_and_moves_the_etag(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    root = sah.fresh(tmp_path_factory, "simple")
    ctx = sc.context(root)
    svc = service()
    request = sah.request_of(ctx)
    before = svc.bundle(request)
    target = ctx.config_dir / "settings.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    after = svc.bundle(request)
    assert after is not before
    assert after.etag != before.etag


def test_a_new_data_version_drops_the_cache(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")
    svc = service()
    one = svc.bundle(sah.request_of(ctx, version="pass-1"))
    two = svc.bundle(sah.request_of(ctx, version="pass-2"))
    assert two is not one
    assert two.etag != one.etag


def test_the_cache_keeps_a_bounded_number_of_projects(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "empty")
    svc = service()
    for n in range(setup_answers.CACHE_MAX + 4):
        svc.bundle(
            setup_answers.SetupRequest(
                project=f"p{n}",
                ctx=ctx,
                listed=True,
                version="",
                as_of=None,
                usage=lambda: None,
                transcripts=Transcripts,
            )
        )
    assert len(svc._cache) == setup_answers.CACHE_MAX  # pyright: ignore[reportPrivateUsage]


# ------------------------------------------------------------ failure paths


def test_a_collector_that_raises_leaves_the_others_and_fails_the_nav(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")

    def broken(_ctx: Any, _handoff: Any) -> Any:
        msg = "SECRET-IN-THE-MESSAGE"
        raise RuntimeError(msg)

    monkeypatch.setattr(setup_answers._BY_NAME["mcp"], "read", broken)  # pyright: ignore[reportPrivateUsage]
    svc = service()
    request = sah.request_of(ctx)
    with caplog.at_level(logging.ERROR):
        found = svc.setup_map(request, None, NOW)
    assert isinstance(found, SetupMap)
    rows = {r.part: r for r in found.parts}
    assert rows["mcp"].summary.params["count"] == "0"
    assert rows["agents"].summary.params["count"] == "5"
    assert svc.to_fix(request).state == "failed"
    assert svc.to_fix(request).count is None
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "setup collector mcp failed (RuntimeError)" in text
    assert "SECRET-IN-THE-MESSAGE" not in text


def test_a_failing_signature_forces_a_fresh_read_each_time(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")

    def broken(_ctx: Any, _last: Any) -> str:
        msg = "no"
        raise OSError(msg)

    monkeypatch.setattr(setup_answers._BY_NAME["hooks"], "signature", broken)  # pyright: ignore[reportPrivateUsage]
    svc = service()
    request = sah.request_of(ctx)
    one = svc.bundle(request)
    assert "hooks=error-" in one.signature
    # The failing fingerprint never matches the cached one, so the read is rebuilt.
    assert svc.bundle(request) is not one


def test_a_store_failure_leaves_usage_and_transcripts_out(
    tmp_path_factory: pytest.TempPathFactory, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")

    def usage_fails() -> Any:
        raise sqlite_error()

    def transcripts_fail() -> Any:
        raise sqlite_error()

    request = setup_answers.SetupRequest(
        project="proj",
        ctx=ctx,
        listed=True,
        version="",
        as_of=None,
        usage=usage_fails,
        transcripts=transcripts_fail,
    )
    with caplog.at_level(logging.ERROR):
        bundle = setup_answers.build_bundle(request)
        found = service().setup_part(request, "agents", None, NOW)
    assert isinstance(found, SetupPartAnswer)
    assert all(i.usage is None for i in found.items)
    assert found.groups == []
    assert bundle.counted == 0
    assert "setup usage failed (OperationalError)" in caplog.text
    assert "setup transcripts failed (OperationalError)" in caplog.text


def test_usage_is_fetched_by_the_map_and_part_answers_only_and_once(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    ctx = sah.materialized(tmp_path_factory, "typical")
    calls: list[int] = []

    def fetch() -> setup_answers.SetupUsage:
        calls.append(1)
        return usage({"builder": 1})

    request = setup_answers.SetupRequest(
        project="proj",
        ctx=ctx,
        listed=True,
        version="",
        as_of=None,
        usage=fetch,
        transcripts=Transcripts,
    )
    svc = service()
    svc.agent_items(request)
    svc.problems(request, None, NOW)
    svc.to_fix(request)
    assert calls == []
    svc.setup_map(request, None, NOW)
    svc.setup_part(request, "agents", None, NOW)
    svc.setup_part(request, "settings", None, NOW)
    assert calls == [1]
    # The read the Agents page uses keeps its items free of run counts.
    assert all(i.usage is None for i in svc.agent_items(request))


def sqlite_error() -> Exception:
    import sqlite3

    return sqlite3.OperationalError("disk I/O error")


def test_the_registry_names_every_part_summary_code() -> None:
    assert set(setup_codes.SUMMARY_CODES) == set(SETUP_PARTS)

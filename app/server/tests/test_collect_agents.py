"""Tests for the agents collector (m4-build.md task 6).

The corpus cases are held to their expected.json. Crafted folders cover the resolver's
statuses, the sources and the value that runs, the same-name rules, plugin agents, the
read audit, and the Couldn't read state.
"""

import builtins
import json
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import agent_collect_helpers as h
import read_audit_helpers as audit
from agent_collect_helpers import Mini, lines

import agent_setup
import collect_agents
import collect_plugins
import model_check
import read_scope
from collect_plugins import PluginComponents
from models import SetupItem
from setup_contract import FILE_CAP_BYTES, Collected

NOT_ROOT = os.geteuid() != 0
AGENT_CASES = sorted(
    p.name
    for p in h.CORPUS.iterdir()
    if p.is_dir() and "agents" in h.expected(p.name)["parts"]
)


@pytest.fixture
def mini(tmp_path: Path) -> Mini:
    return Mini(tmp_path)


def agent(name: str, description: str | None = "d", *extra: str) -> str:
    rows = ["---", f"name: {name}"]
    if description is not None:
        rows.append(f"description: {description}")
    return lines(*rows, *extra, "---", "Body text.")


def user_agent(mini: Mini, name: str, *extra: str, file: str | None = None) -> Path:
    return mini.write(
        mini.config / "agents" / f"{file or name}.md", agent(name, "d", *extra)
    )


def project_agent(mini: Mini, name: str, *extra: str) -> Path:
    return mini.write(
        mini.project / ".claude" / "agents" / f"{name}.md", agent(name, "d", *extra)
    )


def read(mini: Mini, handoff: dict[str, object] | None = None) -> Collected:
    return collect_agents.COLLECTOR.read(mini.ctx, handoff or {})


def by_id(col: Collected) -> dict[str, SetupItem]:
    return {i.id: i for i in col.items["agents"]}


def sources(item: SetupItem, key: str) -> list[tuple[str, str | None, int | None, str]]:
    """(scope, file, line, status) of the sources with one key."""
    return [(s.scope, s.file, s.line, s.status) for s in item.sources if s.key == key]


# ---------------------------------------------------------------- the corpus


@pytest.mark.parametrize("case", AGENT_CASES)
def test_the_corpus_cases_meet_their_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world(case, tmp_path / "w", setup_corpus)
    result = h.run(w.ctx)
    want = h.expected(case)
    assert h.compare("agents", result.agents, want, result.problems()) == []


def test_a_case_with_no_agents_part_makes_no_items(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("empty", tmp_path / "w", setup_corpus)
    got = h.run(w.ctx).agents
    assert got.items["agents"] == []
    assert got.problems == []
    assert got.unreadable == []


def test_the_stress_case_has_fifty_agents_in_id_order(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("stress", tmp_path / "w", setup_corpus)
    got = h.run(w.ctx).agents.items["agents"]
    assert len(got) == 50
    assert [i.id for i in got] == sorted(i.id for i in got)
    assert [i.order for i in got] == list(range(50))


def test_complex_has_two_items_for_the_shared_name(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("complex", tmp_path / "w", setup_corpus)
    got = by_id(h.run(w.ctx).agents)
    plugin, plain = got["agents:routing-dashboard:scout"], got["agents:scout"]
    assert (plugin.scope, plain.scope) == ("plugin", "user")
    assert plugin.key == plain.key == "scout"
    assert plugin.facts.agent is not None
    assert plugin.facts.agent.plugin == "routing-dashboard"
    assert plain.facts.agent is not None
    assert plain.facts.agent.plugin is None
    # The plugin agent's hooks and permissionMode are ignored but keep value and line.
    fields = {f.name: f for f in plugin.facts.agent.fields}
    assert (fields["hooks"].ignored, fields["hooks"].line) == (True, 7)
    assert fields["hooks"].value is not None
    assert "PreToolUse" in fields["hooks"].value.text
    assert (fields["permissionMode"].ignored, fields["permissionMode"].line) == (
        True,
        6,
    )
    assert fields["model"].ignored is False
    assert plugin.read_only_reason is not None
    assert plugin.read_only_reason.code == "plugin"
    assert plugin.read_only_reason.params == {"plugin": "routing-dashboard"}
    assert plain.read_only_reason is None
    policy = got["agents:policy"]
    assert policy.read_only_reason is not None
    assert policy.read_only_reason.code == "managed"


def test_the_plugin_field_rows_are_not_as_set(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("complex", tmp_path / "w", setup_corpus)
    rows = [p for p in h.run(w.ctx).agents.problems]
    assert [(r.code, r.group, r.kind, r.line) for r in rows] == [
        ("plugin_field_ignored", "not_as_set", "problem", 6),
        ("plugin_field_ignored", "not_as_set", "problem", 7),
    ]
    assert [r.params for r in rows] == [
        {"field": "permissionMode", "plugin": "routing-dashboard"},
        {"field": "hooks", "plugin": "routing-dashboard"},
    ]
    assert {r.thing for r in rows} == {"scout"}


# ---------------------------------------------------- statuses and the value that runs


def test_setup_agrees_with_agent_setup(tmp_path: Path, setup_corpus: Path) -> None:
    """Live, Review and setup read the same scope and the same model and effort."""
    for case in ("typical", "complex", "scope-symlink", "simple"):
        w = h.world(case, tmp_path / case, setup_corpus)
        got = by_id(h.run(w.ctx).agents)
        setup = agent_setup.load_setup(
            w.ctx.config_dir, w.ctx.project_dir, w.ctx.managed_dir, w.ctx.shell_env
        )
        assert not setup.failed
        for name, found in setup.files.items():
            item = got[f"agents:{name}"]
            if item.scope == "managed":
                continue
            assert item.scope == found.scope, (case, name)
            shown = (
                item.effective.value.text
                if item.effective and item.effective.value
                else ""
            )
            for pin in (
                found.set.model if found.set else None,
                found.set.effort if found.set else None,
            ):
                if pin is not None and pin.scope == "agent":
                    assert pin.value in shown, (case, name, shown)


def test_a_project_agent_beats_a_user_agent_and_reports_both(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("typical", tmp_path / "w", setup_corpus)
    item = by_id(h.run(w.ctx).agents)["agents:reviewer"]
    assert sources(item, "name") == [
        ("project", ".claude/agents/reviewer.md", 2, "in_effect"),
        ("user", "~/.claude/agents/reviewer.md", 2, "overridden"),
    ]
    assert (item.status, item.scope, item.winner) == ("in_effect", "project", 0)
    # Model and effort, as the resolver rules them: the front matter of the winner.
    assert sources(item, "model")[0] == (
        "project",
        ".claude/agents/reviewer.md",
        4,
        "in_effect",
    )
    assert sources(item, "effort")[0] == (
        "project",
        ".claude/agents/reviewer.md",
        5,
        "in_effect",
    )
    assert item.effective is not None
    assert item.effective.value is not None
    assert item.effective.value.text == "claude-sonnet-5-5 / high"
    assert (item.effective.origin, item.effective.by_item) == ("set", None)
    assert item.reason is not None
    assert item.reason.code == "agent_overrides"
    assert item.reason.params["other_file"] == "~/.claude/agents/reviewer.md"
    assert item.confidence.level == "documented"


def test_every_source_carries_a_full_path_for_files(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("typical", tmp_path / "w", setup_corpus)
    item = by_id(h.run(w.ctx).agents)["agents:reviewer"]
    for source in item.sources:
        assert source.full_path is not None
        assert Path(source.full_path).is_file()
        assert source.file is not None


def test_a_settings_effort_beats_nothing_and_an_agent_file_beats_settings(
    mini: Mini,
) -> None:
    mini.write(
        mini.project / ".claude" / "settings.json",
        json.dumps({"effortLevel": "low"}, indent=2),
    )
    user_agent(mini, "plain", "model: claude-sonnet-5-5")
    user_agent(mini, "pinned", "model: claude-sonnet-5-5", "effort: high")
    got = by_id(read(mini))
    plain, pinned = got["agents:plain"], got["agents:pinned"]
    assert sources(plain, "effortLevel") == [
        ("project", ".claude/settings.json", 2, "in_effect")
    ]
    assert plain.effective is not None
    assert plain.effective.value is not None
    assert plain.effective.value.text == "claude-sonnet-5-5 / low"
    assert [s[0] for s in sources(pinned, "effort")] == ["user"]
    assert pinned.effective is not None
    assert pinned.effective.value is not None
    assert pinned.effective.value.text == "claude-sonnet-5-5 / high"


def test_a_cap_lowers_an_effort_and_names_the_setting_item(mini: Mini) -> None:
    mini.write(
        mini.config / "settings.json",
        json.dumps({"maxEffortLevel": "medium"}, indent=2),
    )
    user_agent(mini, "capped", "model: claude-opus-5-5", "effort: high")
    item = by_id(read(mini))["agents:capped"]
    assert item.effective is not None
    assert (item.effective.origin, item.effective.by_item) == (
        "cap",
        "settings:maxEffortLevel",
    )
    assert item.effective.value is not None
    assert item.effective.value.text.endswith("/ medium")
    effort = [s for s in item.sources if s.key == "effort"]
    assert [s.status for s in effort] == ["lowered"]
    caps = [s for s in item.sources if s.key == "maxEffortLevel"]
    assert [(s.scope, s.line, s.status) for s in caps] == [("user", 2, "in_effect")]


def test_a_lowered_agent_makes_a_not_as_set_row_that_opens_the_cap(mini: Mini) -> None:
    mini.write(
        mini.config / "settings.json",
        json.dumps({"maxEffortLevel": "medium"}, indent=2),
    )
    user_agent(mini, "capped", "model: claude-opus-5-5", "effort: high")
    col = read(mini)
    item = by_id(col)["agents:capped"]
    assert item.status == "lowered"
    assert item.check is not None
    assert item.check.code == "lowered_by_cap"
    [row] = [r for r in col.problems if r.code == "agent_lowered"]
    effort = next(s for s in item.sources if s.key == "effort")
    assert (row.group, row.kind, row.part) == ("not_as_set", "problem", "agents")
    assert (row.item_id, row.thing) == ("agents:capped", "capped")
    assert (row.file, row.line) == (effort.file, effort.line)
    assert row.params == {
        "setting": "effort",
        "value": "high",
        "runs": "medium",
        "cap": "maxEffortLevel",
    }
    assert (row.fix.kind, row.fix.target) == ("open_item", "settings:maxEffortLevel")
    assert row.confidence == item.confidence


def test_an_overridden_agent_makes_no_row(mini: Mini) -> None:
    # A higher scope winning is by design, so Overridden is not a thing to fix.
    mini.ctx = replace(mini.ctx, shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "low"})
    user_agent(mini, "over", "model: claude-opus-5-5", "effort: high")
    col = read(mini)
    item = by_id(col)["agents:over"]
    assert item.status == "overridden"
    assert item.check is not None
    assert item.check.code == "pin_overridden"
    assert [r for r in col.problems if r.code == "agent_lowered"] == []


def test_a_worse_status_on_the_other_setting_keeps_the_lowered_row(mini: Mini) -> None:
    # The model is ignored (the force variable is on) and a cap lowers the effort. The
    # pill and the check name the worse cause, but the row is per setting, so the
    # lowered effort still shows and opens its cap.
    mini.write(
        mini.config / "settings.json",
        json.dumps(
            {
                "maxEffortLevel": "medium",
                "env": {
                    "CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-5-5",
                    "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
                },
            },
            indent=2,
        ),
    )
    user_agent(mini, "mixed", "model: claude-opus-5-5", "effort: high")
    col = read(mini)
    item = by_id(col)["agents:mixed"]
    assert item.status == "ignored"
    assert item.check is not None
    assert item.check.code == "pin_ignored"
    [row] = [r for r in col.problems if r.code == "agent_lowered"]
    effort = next(s for s in item.sources if s.key == "effort")
    assert (row.group, row.item_id, row.thing) == ("not_as_set", item.id, "mixed")
    assert (row.file, row.line) == (effort.file, effort.line)
    assert row.params == {
        "setting": "effort",
        "value": "high",
        "runs": "medium",
        "cap": "maxEffortLevel",
    }
    assert (row.fix.kind, row.fix.target) == ("open_item", "settings:maxEffortLevel")
    # The ignored model is its own cause and makes no lowered row.
    assert [r.params["setting"] for r in col.problems if r.code == "agent_lowered"] == [
        "effort"
    ]


def test_an_environment_variable_source_names_the_variable(mini: Mini) -> None:
    mini.ctx = replace(
        mini.ctx, shell_env={"CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-5-5"}
    )
    user_agent(mini, "a", "model: claude-sonnet-5-5")
    item = by_id(read(mini))["agents:a"]
    shell = [s for s in item.sources if s.scope == "shell"]
    assert [(s.key, s.file, s.value.text if s.value else None) for s in shell] == [
        ("CLAUDE_CODE_SUBAGENT_MODEL", None, "claude-haiku-5-5")
    ]


def test_an_env_block_source_is_keyed_env_dot_name(mini: Mini) -> None:
    mini.write(
        mini.config / "settings.json",
        json.dumps(
            {"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-5-5"}}, indent=2
        ),
    )
    user_agent(mini, "a", "model: claude-sonnet-5-5")
    item = by_id(read(mini))["agents:a"]
    env = [s for s in item.sources if s.key.startswith("env.")]
    assert [(s.scope, s.key, s.line) for s in env] == [
        ("user", "env.CLAUDE_CODE_SUBAGENT_MODEL", 3)
    ]


def test_an_agent_that_sets_nothing_has_no_value_that_runs(mini: Mini) -> None:
    user_agent(mini, "plain")
    item = by_id(read(mini))["agents:plain"]
    assert item.effective is not None
    assert item.effective.value is None
    assert item.effective.origin in ("unknown", "default")
    assert item.usage is None
    assert item.group is None


def test_the_resolver_failing_leaves_the_items_with_no_model_or_effort(
    mini: Mini, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_kwargs: object) -> list[dict[str, Any]]:
        raise OSError("no")

    monkeypatch.setattr(model_check, "resolve_entries", fail)
    user_agent(mini, "a", "model: claude-sonnet-5-5")
    mini.write(
        mini.config / "agents" / "gap.md",
        "---\nname: gap\ndescription: >\n  folded\n---\n",
    )
    got = by_id(read(mini))
    assert got["agents:a"].status == "in_effect"
    effective = got["agents:a"].effective
    assert effective is not None
    assert effective.value is None
    assert effective.origin == "unknown"
    assert got["agents:gap"].status == "unknown"


# ------------------------------------------------------ where agents come from


def test_managed_beats_project_beats_user(mini: Mini) -> None:
    mini.write(
        mini.managed / ".claude" / "agents" / "same.md",
        agent("same", "managed one", "model: haiku"),
    )
    project_agent(mini, "same", "model: claude-sonnet-5-5")
    user_agent(mini, "same")
    item = by_id(read(mini))["agents:same"]
    assert sources(item, "name") == [
        ("managed", "managed/.claude/agents/same.md", 2, "in_effect"),
        ("project", ".claude/agents/same.md", 2, "overridden"),
        ("user", "~/.claude/agents/same.md", 2, "overridden"),
    ]
    assert (item.scope, item.status, item.winner) == ("managed", "in_effect", 0)
    assert item.read_only_reason is not None
    assert item.read_only_reason.code == "managed"
    # The resolver has no managed layer, so the winner's model is shown but not ruled.
    model = [s for s in item.sources if s.key == "model"]
    assert [(s.scope, s.status) for s in model] == [("managed", "unknown")]
    assert item.effective is not None
    assert item.effective.origin == "unknown"


def test_a_plugin_agent_is_its_own_item_even_with_the_same_name(mini: Mini) -> None:
    user_agent(mini, "scout")
    root = mini.config / "plugins" / "cache" / "m" / "kit" / "1"
    mini.write(root / "agents" / "scout.md", agent("scout", "from the plugin"))
    comp = PluginComponents(
        item_id="plugins:kit@m", plugin_id="kit@m", name="kit", root=str(root),
        agents=[str(root / "agents")],
    )  # fmt: skip
    got = by_id(read(mini, {"plugin_components": [comp, "junk"]}))
    assert sorted(got) == ["agents:kit:scout", "agents:scout"]
    assert (got["agents:kit:scout"].scope, got["agents:scout"].scope) == (
        "plugin",
        "user",
    )
    assert got["agents:kit:scout"].sources[0].plugin == "kit"


def test_plugins_in_a_bad_handoff_are_ignored(mini: Mini) -> None:
    user_agent(mini, "a")
    assert sorted(by_id(read(mini, {"plugin_components": "nope"}))) == ["agents:a"]


def test_two_files_with_one_name_in_a_plugin_report_the_second(mini: Mini) -> None:
    root = mini.config / "plugins" / "cache" / "m" / "kit" / "1"
    mini.write(root / "agents" / "a.md", agent("dup"))
    mini.write(root / "agents" / "b.md", agent("dup"))
    comp = PluginComponents(
        item_id="plugins:kit@m", plugin_id="kit@m", name="kit", root=str(root),
        agents=[str(root / "agents")],
    )  # fmt: skip
    got = read(mini, {"plugin_components": [comp]})
    assert [
        (p.code, p.item_id, p.file.rsplit("/", 1)[-1] if p.file else None)
        for p in got.problems
    ] == [("same_name_in_folder", "agents:kit:dup", "b.md")]
    item = by_id(got)["agents:kit:dup"]
    assert item.confidence.level == "assumed"
    assert [s.status for s in item.sources if s.key == "name"] == [
        "in_effect",
        "invalid",
    ]


def test_a_plugin_file_that_is_not_an_agent_is_reported(mini: Mini) -> None:
    root = mini.config / "plugins" / "cache" / "m" / "kit" / "1"
    mini.write(root / "agents" / "README.txt", "x")
    comp = PluginComponents(
        item_id="plugins:kit@m", plugin_id="kit@m", name="kit", root=str(root),
        agents=[str(root / "agents")],
    )  # fmt: skip
    got = read(mini, {"plugin_components": [comp]})
    assert [p.code for p in got.problems] == ["agent_not_md"]
    assert got.items["agents"] == []


def test_without_a_managed_folder_or_a_project_only_user_agents_load(
    mini: Mini,
) -> None:
    user_agent(mini, "u")
    project_agent(mini, "p")
    mini.write(mini.managed / ".claude" / "agents" / "m.md", agent("m"))
    mini.ctx = replace(mini.ctx, managed_dir=None, project_dir=None)
    got = read(mini)
    assert sorted(by_id(got)) == ["agents:u"]
    reach = {r.scope: r.visible for r in got.items["agents"][0].reach}
    assert reach == {
        "managed": False,
        "command_line": False,
        "project": False,
        "user": True,
        "plugin": True,
    }


def test_the_command_line_scope_is_never_visible(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("typical", tmp_path / "w", setup_corpus)
    for item in h.run(w.ctx).agents.items["agents"]:
        assert [
            (r.scope, r.visible) for r in item.reach if r.scope == "command_line"
        ] == [("command_line", False)]
        assert item.applies is None
        assert (item.writable, item.risk_tier, item.feature) == (False, None, "core")


def test_the_agent_files_go_on_to_the_hooks_collector(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("complex", tmp_path / "w", setup_corpus)
    handed = h.run(w.ctx).agents.handoff["agent_files"]
    names = sorted(f.name for f in handed)  # type: ignore[attr-defined]
    assert names == ["builder", "policy", "reviewer", "reviewer", "scout", "scout"]


# ---------------------------------------------------------------- files with problems


def test_each_problem_file_has_a_row_and_the_right_item(mini: Mini) -> None:
    root = mini.config / "agents"
    mini.write(root / "nofront.md", "No front matter here.\n")
    mini.write(root / "noname.md", "---\ndescription: x\n---\n")
    mini.write(root / "notes.txt", "x")
    mini.write(root / "nodesc.md", agent("nodesc", None))
    mini.write(root / "ok.md", agent("ok"))
    got = read(mini)
    rows = {(p.code, p.item_id, p.file) for p in got.problems}
    assert rows == {
        ("frontmatter_invalid", None, "~/.claude/agents/nofront.md"),
        ("agent_no_name", None, "~/.claude/agents/noname.md"),
        ("agent_not_md", None, "~/.claude/agents/notes.txt"),
        ("agent_no_description", "agents:nodesc", "~/.claude/agents/nodesc.md"),
    }
    assert sorted(by_id(got)) == ["agents:nodesc", "agents:ok"]
    for row in got.problems:
        assert row.part == "agents"
        assert row.group == "wont_load"
        assert row.kind == "problem"
        assert row.full_path is not None
        assert row.fix.kind in ("open_item", "copy_path")


def test_a_managed_problem_cannot_be_fixed_here(mini: Mini) -> None:
    mini.write(mini.managed / ".claude" / "agents" / "bad.md", "no front matter\n")
    (row,) = read(mini).problems
    assert (row.fix.kind, row.fix.reason) == ("cant_fix_here", "managed")


def test_the_reader_gap_keeps_the_resolver_status_and_says_cant_tell(
    mini: Mini,
) -> None:
    mini.write(
        mini.config / "agents" / "nested.md",
        lines(
            "---", "name: nested", "description: d", "allowed-tools: Read",
            "hooks:", "  PreToolUse:", "    - matcher: Bash", "---",
        ),
    )  # fmt: skip
    got = read(mini)
    (row,) = got.problems
    assert (row.code, row.group, row.kind, row.item_id) == (
        "frontmatter_reader_gap", "cant_tell", "cant_tell", "agents:nested",
    )  # fmt: skip
    item = by_id(got)["agents:nested"]
    assert item.status == "unknown"  # the resolver's word for this file
    assert item.confidence.level == "assumed"
    # Every field still parses, with its line.
    assert item.facts.agent is not None
    assert [f.name for f in item.facts.agent.fields] == [
        "name", "description", "hooks", "allowed-tools",
    ]  # fmt: skip


def test_an_unclosed_bracket_makes_an_item_that_loads_with_a_cant_tell_row(
    mini: Mini,
) -> None:
    # Claude Code loads this file (tested on 2.1.302). ruamel cannot parse it, but the
    # item still exists, and the one row says Can't tell, never Won't load.
    mini.write(
        mini.config / "agents" / "probe.md",
        lines("---", "name: probe", "description: [Made-up agent", "---", "Body."),
    )
    got = read(mini)
    item = by_id(got)["agents:probe"]
    assert item.status == "unknown"  # the resolver's word for this file
    assert item.reason is not None
    assert item.reason.code == "frontmatter_reader_gap"
    (row,) = got.problems
    assert (row.code, row.group, row.item_id, row.line) == (
        "frontmatter_reader_gap",
        "cant_tell",
        "agents:probe",
        3,
    )


def test_the_reader_gap_is_checked_before_the_description(mini: Mini) -> None:
    # A description written as a flow mapping is no string, but the strict reader
    # rejects the file, so nobody can say it has no description.
    mini.write(
        mini.config / "agents" / "probe.md",
        lines("---", "name: probe", "description: {text: Made-up}", "---", "Body."),
    )
    got = read(mini)
    assert by_id(got)["agents:probe"].status == "unknown"
    assert [(r.code, r.group) for r in got.problems] == [
        ("frontmatter_reader_gap", "cant_tell")
    ]


def test_two_files_with_one_name_in_one_folder_first_in_sorted_order_wins(
    mini: Mini,
) -> None:
    mini.write(mini.config / "agents" / "b.md", agent("twin", "second"))
    mini.write(mini.config / "agents" / "a.md", agent("twin", "first"))
    mini.write(mini.config / "agents" / "z" / "c.md", agent("twin", "third"))
    got = read(mini)
    item = by_id(got)["agents:twin"]
    assert [(s.file, s.status) for s in item.sources if s.key == "name"] == [
        ("~/.claude/agents/a.md", "in_effect"),
        ("~/.claude/agents/b.md", "invalid"),
        ("~/.claude/agents/z/c.md", "invalid"),
    ]
    assert item.confidence.level == "assumed"
    assert item.reason is not None
    assert item.reason.code == "same_name_in_folder"
    assert item.reason.rule_id == "agent-file-same-name-one-tree"
    assert sorted(p.file or "" for p in got.problems) == [
        "~/.claude/agents/b.md",
        "~/.claude/agents/z/c.md",
    ]
    assert {p.code for p in got.problems} == {"same_name_in_folder"}


def test_a_file_without_a_description_does_not_take_a_name_from_the_others(
    mini: Mini,
) -> None:
    mini.write(mini.config / "agents" / "a.md", agent("same", None))
    mini.write(mini.config / "agents" / "b.md", agent("same", "has one"))
    got = read(mini)
    assert [p.code for p in got.problems] == ["agent_no_description"]
    item = by_id(got)["agents:same"]
    # The file that has a description is the one that loads.
    assert (item.status, item.winner) == ("in_effect", 1)
    assert [s.status for s in item.sources if s.key == "name"] == [
        "invalid",
        "in_effect",
    ]


# ---------------------------------------------------------------- order and stability


def test_two_reads_give_the_same_answer(tmp_path: Path, setup_corpus: Path) -> None:
    w = h.world("complex", tmp_path / "w", setup_corpus)
    first, second = h.run(w.ctx), h.run(w.ctx)
    assert first.everything() == second.everything()


def test_an_agent_that_moves_from_user_to_project_keeps_its_id_and_place(
    mini: Mini,
) -> None:
    user_agent(mini, "a")
    moving = user_agent(mini, "m", "model: claude-sonnet-5-5")
    user_agent(mini, "z")
    before = read(mini).items["agents"]
    target = mini.project / ".claude" / "agents" / "m.md"
    target.parent.mkdir(parents=True)
    moving.rename(target)
    after = read(mini).items["agents"]
    assert (
        [i.id for i in before]
        == [i.id for i in after]
        == ["agents:a", "agents:m", "agents:z"]
    )
    assert [i.order for i in after] == [0, 1, 2]
    assert [i.scope for i in before] == ["user", "user", "user"]
    assert [i.scope for i in after] == ["user", "project", "user"]


def test_items_sort_by_id_with_plugin_ids_among_them(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("complex", tmp_path / "w", setup_corpus)
    ids = [i.id for i in h.run(w.ctx).agents.items["agents"]]
    assert ids == sorted(ids)
    assert "agents:routing-dashboard:scout" in ids


# ---------------------------------------------------------------- masking


def test_no_corpus_secret_is_in_any_item(tmp_path: Path, setup_corpus: Path) -> None:
    secrets = json.loads((h.CORPUS / "secrets.json").read_text("utf-8"))
    values = [s["value"] for s in [*secrets["secrets"], *secrets["never"]]]
    for case in sorted(p.name for p in h.CORPUS.iterdir() if p.is_dir()):
        w = h.world(case, tmp_path / case, setup_corpus)
        dump = h.run(w.ctx).everything()
        for value in values:
            assert value not in dump, (case, value)


def test_a_secret_in_an_agent_field_is_masked_in_the_item(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "s.md",
        lines(
            "---", "name: s", "description: d", "apiKey: plainsecret0001",
            "mcpServers:", "  - name: srv", "    env:", "      API_TOKEN: tok0002",
            "initialPrompt: sk-ant-api03-FAKEINITIAL0003", "---",
        ),
    )  # fmt: skip
    col = read(mini)
    dump = h.Result(plugins=Collected(), agents=col).everything()
    for secret in ("plainsecret0001", "tok0002", "FAKEINITIAL0003"):
        assert secret not in dump
    item = by_id(col)["agents:s"]
    assert item.facts.agent is not None
    masked = {f.name for f in item.facts.agent.fields if f.value and f.value.masked}
    assert masked == {"apiKey", "mcpServers", "initialPrompt"}


# ---------------------------------------------------------------- Couldn't read


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_file_with_no_permission_is_unreadable_and_the_rest_still_read(
    mini: Mini,
) -> None:
    user_agent(mini, "ok")
    locked = user_agent(mini, "locked")
    locked.chmod(0)
    try:
        got = read(mini)
    finally:
        locked.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert [(u.reason, u.file, u.scope) for u in got.unreadable] == [
        ("permission", "~/.claude/agents/locked.md", "user")
    ]
    assert sorted(by_id(got)) == ["agents:ok"]
    assert by_id(got)["agents:ok"].may_change is True
    assert {u.part for u in got.unreadable} == {"agents"}


def test_a_file_that_is_not_utf8_is_unreadable_and_the_rest_still_read(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("typical", tmp_path / "w", setup_corpus)
    path = w.lay.config / "agents" / "planner.md"
    path.write_bytes(b"---\nname: planner\ndescription: \xff\xfe\n---\n")
    got = h.run(w.ctx).agents
    assert [(u.reason, u.file) for u in got.unreadable] == [
        ("not_utf8", "~/.claude/agents/planner.md")
    ]
    assert sorted(i.id for i in got.items["agents"]) == [
        "agents:builder", "agents:reviewer", "agents:scribe", "agents:tester",
    ]  # fmt: skip
    assert all(i.may_change for i in got.items["agents"])


def test_a_file_over_the_cap_is_unreadable(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "huge.md",
        b"---\nname: huge\n---\n" + b"x" * FILE_CAP_BYTES,
    )
    got = read(mini)
    assert [(u.reason, u.file) for u in got.unreadable] == [
        ("too_large", "~/.claude/agents/huge.md")
    ]
    assert got.items["agents"] == []


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_folder_that_will_not_list_is_unreadable(mini: Mini) -> None:
    user_agent(mini, "a")
    folder = mini.config / "agents"
    folder.chmod(0)
    try:
        got = read(mini)
    finally:
        folder.chmod(stat.S_IRWXU)
    assert [u.reason for u in got.unreadable] == ["folder_unlistable"]
    assert got.items["agents"] == []


def test_a_symlinked_agents_subfolder_out_of_the_roots_is_not_read_here(
    mini: Mini,
) -> None:
    outside = mini.root / "outside"
    mini.write(outside / "evil.md", agent("evil"))
    mini.config.joinpath("agents").mkdir()
    mini.config.joinpath("agents", "linked").symlink_to(outside)
    got = read(mini)
    assert [(u.reason, u.file) for u in got.unreadable] == [
        ("outside_scope", "~/.claude/agents/linked")
    ]
    assert got.items["agents"] == []


# ---------------------------------------------------------------- the read audit


def test_every_open_and_listing_passes_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decoys = audit.build_decoys(tmp_path)
    ctx = replace(decoys.context(), managed_dir=tmp_path / "no-managed")
    # An agent the decoy tree does not have: a plugin install under the plugins folder.
    mini_root = decoys.config / "plugins" / "cache" / "ok" / "kit" / "1"
    (mini_root / "agents").mkdir(parents=True)
    (mini_root / "agents" / "k.md").write_text(agent("k"), encoding="utf-8")
    installed = {
        "version": 2,
        "plugins": {
            "kit@ok": [{"scope": "user", "installPath": str(mini_root)}],
            "elsewhere@market": [
                {
                    "scope": "user",
                    "installPath": str(decoys.outside / "plugin-elsewhere"),
                }
            ],
        },
    }
    (decoys.config / "plugins" / "installed_plugins.json").write_text(
        json.dumps(installed), encoding="utf-8"
    )
    (decoys.config / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"kit@ok": True, "elsewhere@market": True}}),
        encoding="utf-8",
    )
    log: list[tuple[str, str]] = []
    h.spy_on_reads(monkeypatch, log)
    plugins = collect_plugins.COLLECTOR.read(ctx, {})
    agents = collect_agents.COLLECTOR.read(ctx, plugins.handoff)
    monkeypatch.undo()
    assert sorted(i.id for i in agents.items["agents"]) == [
        "agents:kit:k", "agents:mine", "agents:user-agent",
    ]  # fmt: skip
    # The folder link that leaves the roots is listed as not read, never entered.
    assert any(u.reason == "outside_scope" for u in agents.unreadable)
    assert {i.key: i.not_read for i in plugins.items["plugins"]} == {
        "kit@ok": None,
        "elsewhere@market": "plugin_outside_plugins",
    }
    audit.assert_reads_allowed(
        log, decoys, scope=read_scope.Scope(ctx), followed=[decoys.followed]
    )
    assert any(path.endswith("k.md") for _event, path in log)


def test_the_signature_is_stat_only_and_follows_the_files(
    mini: Mini, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = user_agent(mini, "a")
    col = read(mini)
    before = collect_agents.COLLECTOR.signature(mini.ctx, col)

    def refuse(*_args: object, **_kwargs: object) -> object:
        pytest.fail("signature opened a file")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(os, "open", refuse)
    again = collect_agents.COLLECTOR.signature(mini.ctx, col)
    cold = collect_agents.COLLECTOR.signature(mini.ctx, None)
    monkeypatch.undo()
    assert again == before
    assert cold != before
    path.write_text(agent("a", "changed"), encoding="utf-8")
    assert collect_agents.COLLECTOR.signature(mini.ctx, col) != before
    user_agent(mini, "b")
    assert collect_agents.COLLECTOR.signature(mini.ctx, None) != cold


def test_the_collector_names_its_part() -> None:
    assert collect_agents.COLLECTOR.name == "agents"
    assert list(collect_agents.COLLECTOR.parts) == ["agents"]

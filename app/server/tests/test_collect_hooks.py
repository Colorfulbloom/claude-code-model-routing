"""The Hooks collector (m4-build.md task 8).

Every corpus case's expected.json is the oracle for the part. Crafted folders then cover
the event order, the switches, the handler shapes, plugin and agent hooks, masking, the
Couldn't read state, the order across two reads and the signature. Every run reads its
own copy inside a temp folder, never a real folder.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import hook_mcp_helpers as hm
import setup_case_helpers as sc

import collect_hooks
import collect_plugins
import collect_settings
from models import SetupItem
from setup_contract import Collected, SetupContext

COLLECTOR = collect_hooks.COLLECTOR
NOT_ROOT = os.geteuid() != 0


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def hooks_doc(event: str, command: str = "echo hi", matcher: str | None = None) -> str:
    group: dict[str, object] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        group["matcher"] = matcher
    return json.dumps({"hooks": {event: [group]}}, indent=2) + "\n"


def run(ctx: SetupContext) -> Collected:
    return hm.chain(ctx)["hooks"]


def by_id(got: Collected) -> dict[str, SetupItem]:
    return {i.id: i for i in got.items["hooks"]}


@pytest.fixture
def mini(tmp_path: Path) -> SetupContext:
    return sc.scratch(tmp_path, {})


# ---------------------------------------------------------------- the corpus


@pytest.mark.parametrize("case", sc.CASES)
def test_items_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = run(sc.context(root))
    made, wanted = sc.compare_items(got, case, "hooks")
    assert made == wanted


@pytest.mark.parametrize("case", sc.CASES)
def test_problems_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = run(sc.context(root))
    made, wanted = sc.compare_problems(got, case, ("hooks",))
    assert made == wanted


@pytest.mark.parametrize("case", sc.CASES)
def test_the_source_line_holds_the_handler(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    """Expected sources say ``line_has``: the named line really holds that text."""
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = run(sc.context(root))
    wanted = sc.expected(case)["parts"].get("hooks", {"items": []})["items"]
    made = {i.id: i for i in got.items["hooks"]}
    for item in wanted:
        for at, src in enumerate(item["sources"]):
            if "line_has" not in src:
                continue
            path = Path(made[item["id"]].sources[at].full_path or "")
            lines = path.read_text("utf-8").splitlines()
            assert src["line_has"] in lines[src["line"] - 1], item["id"]


def test_a_case_with_no_hooks_has_no_items(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    got = run(sc.context(root))
    assert got.items["hooks"] == []
    assert got.problems == []
    assert got.unreadable == []


# ---------------------------------------------------------------- the docs order


def test_there_are_thirty_three_events_in_the_pages_order() -> None:
    events = collect_hooks.EVENTS
    assert len(events) == 33
    assert len(set(events)) == 33
    assert events[0] == "SessionStart"
    assert events.index("PreToolUse") < events.index("PostToolUse")
    assert events.index("UserPromptSubmit") < events.index("PreToolUse")
    assert events.index("Stop") < events.index("SessionEnd")
    assert events[-1] == "ElicitationResult"


def test_hooks_come_in_lifecycle_order_not_alphabetical_order(
    mini: SetupContext, tmp_path: Path
) -> None:
    doc = {
        "hooks": {
            event: [{"hooks": [{"type": "command", "command": "x"}]}]
            for event in ("SessionEnd", "PostToolUse", "Stop", "SessionStart")
        }
    }
    put(tmp_path / "home" / ".claude" / "settings.json", json.dumps(doc, indent=2))
    got = run(mini)
    assert [i.key for i in got.items["hooks"]] == [
        "SessionStart",
        "PostToolUse",
        "Stop",
        "SessionEnd",
    ]
    assert [i.order for i in got.items["hooks"]] == [0, 1, 2, 3]


# ---------------------------------------------------------------- the facts


def test_the_facts_of_a_command_hook(mini: SetupContext, tmp_path: Path) -> None:
    doc = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "bash run.sh", "timeout": 5}
                    ],
                }
            ]
        }
    }
    put(tmp_path / "proj" / ".claude" / "settings.json", json.dumps(doc, indent=2))
    item = by_id(run(mini))["hooks:PreToolUse:Bash:0"]
    fact = item.facts.hook
    assert fact is not None
    assert (fact.event, fact.matcher, fact.handler_type) == (
        "PreToolUse",
        "Bash",
        "command",
    )
    assert fact.command is not None
    assert (fact.command.text, fact.command.masked) == ("bash run.sh", False)
    assert fact.timeout == 5
    assert item.scope == "project"
    assert item.group == "PreToolUse"
    assert item.writable is False
    assert item.read_only_reason is None
    assert item.feature == "core"
    assert [(r.scope, r.visible) for r in item.reach][:1] == [("managed", True)]


def test_a_hook_without_a_matcher_reads_as_a_star(
    mini: SetupContext, tmp_path: Path
) -> None:
    put(tmp_path / "home" / ".claude" / "settings.json", hooks_doc("Stop"))
    got = by_id(run(mini))
    assert list(got) == ["hooks:Stop:*:0"]
    assert got["hooks:Stop:*:0"].facts.hook is not None
    assert got["hooks:Stop:*:0"].facts.hook.matcher is None


def test_the_other_handler_types_show_what_they_call(
    mini: SetupContext, tmp_path: Path
) -> None:
    doc = {
        "hooks": {
            "PostToolUse": [
                {
                    "hooks": [
                        {"type": "http", "url": "https://u:pw@hooks.example.test/x"},
                        {"type": "mcp_tool", "server": "docs", "tool": "scan"},
                        {"type": "prompt", "prompt": "BODY-NEVER-SHOWN"},
                        {"type": "agent", "prompt": "BODY-NEVER-SHOWN"},
                    ]
                }
            ]
        }
    }
    put(tmp_path / "home" / ".claude" / "settings.json", json.dumps(doc))
    got = run(mini)
    facts = [i.facts.hook for i in got.items["hooks"]]
    assert [f.handler_type for f in facts if f] == [
        "http",
        "mcp_tool",
        "prompt",
        "agent",
    ]
    assert facts[0] is not None
    assert facts[0].command is not None
    assert facts[0].command.text == "https://u:hidden@hooks.example.test/x"
    assert facts[1] is not None
    assert facts[1].command is not None
    assert facts[1].command.text == "docs scan"
    assert facts[2] is not None
    assert facts[2].command is None
    assert "BODY-NEVER-SHOWN" not in hm.everything({"hooks": got})


def test_an_exec_form_hook_shows_its_args_masked(
    mini: SetupContext, tmp_path: Path
) -> None:
    doc = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3",
                            "args": [
                                "run.py",
                                "--token",
                                "ghp_FAKEFAKEFAKEFAKEFAKE0000",
                            ],
                        }
                    ]
                }
            ]
        }
    }
    put(tmp_path / "home" / ".claude" / "settings.json", json.dumps(doc))
    item = by_id(run(mini))["hooks:Stop:*:0"]
    assert item.facts.hook is not None
    assert item.facts.hook.command is not None
    assert item.facts.hook.command.text == "python3 run.py --token hidden"
    assert item.facts.hook.command.masked is True


def test_scope_order_numbers_the_handlers_of_one_event_and_matcher(
    mini: SetupContext, tmp_path: Path
) -> None:
    put(tmp_path / "home" / ".claude" / "settings.json", hooks_doc("Stop", "user", "A"))
    put(tmp_path / "proj" / ".claude" / "settings.json", hooks_doc("Stop", "proj", "A"))
    put(
        tmp_path / "proj" / ".claude" / "settings.local.json",
        hooks_doc("Stop", "local", "A"),
    )
    put(tmp_path / "managed" / "managed-settings.json", hooks_doc("Stop", "mgr", "A"))
    got = run(mini)
    assert [(i.id, i.scope) for i in got.items["hooks"]] == [
        ("hooks:Stop:A:0", "managed"),
        ("hooks:Stop:A:1", "project_local"),
        ("hooks:Stop:A:2", "project"),
        ("hooks:Stop:A:3", "user"),
    ]
    managed = got.items["hooks"][0]
    assert managed.read_only_reason is not None
    assert managed.read_only_reason.code == "managed"
    assert got.items["hooks"][3].read_only_reason is None


# ---------------------------------------------------------------- the switches


def test_disable_all_hooks_ignores_user_hooks_and_makes_one_row(
    mini: SetupContext, tmp_path: Path
) -> None:
    put(
        tmp_path / "home" / ".claude" / "settings.json",
        json.dumps(
            {
                "disableAllHooks": True,
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": "a"}]},
                        {"hooks": [{"type": "command", "command": "b"}]},
                    ]
                },
            },
            indent=2,
        ),
    )
    got = run(mini)
    items = by_id(got)
    assert items["hooks:disableAllHooks"].status == "in_effect"
    assert items["hooks:Stop:*:0"].status == "ignored"
    assert items["hooks:Stop:*:1"].status == "ignored"
    reason = items["hooks:Stop:*:0"].reason
    assert reason is not None
    assert (reason.code, reason.ref_item) == ("hooks_disabled", "hooks:disableAllHooks")
    rows = [r for r in got.problems if r.code == "hooks_disabled"]
    assert len(rows) == 1
    assert rows[0].item_id == "hooks:disableAllHooks"
    assert rows[0].params["count"] == "2"
    assert rows[0].group == "not_as_set"


def test_a_switch_set_to_false_ignores_nothing(
    mini: SetupContext, tmp_path: Path
) -> None:
    doc = json.loads(hooks_doc("Stop"))
    doc["disableAllHooks"] = False
    put(tmp_path / "home" / ".claude" / "settings.json", json.dumps(doc))
    got = run(mini)
    assert by_id(got)["hooks:Stop:*:0"].status == "in_effect"
    assert got.problems == []
    switch = by_id(got)["hooks:disableAllHooks"]
    assert switch.effective is not None
    assert switch.effective.value is not None
    assert switch.effective.value.text == "false"


def test_disable_all_hooks_outside_managed_leaves_managed_hooks_running(
    mini: SetupContext, tmp_path: Path
) -> None:
    doc = json.loads(hooks_doc("Stop", "user"))
    doc["disableAllHooks"] = True
    put(tmp_path / "home" / ".claude" / "settings.json", json.dumps(doc))
    put(tmp_path / "managed" / "managed-settings.json", hooks_doc("Stop", "mgr"))
    items = by_id(run(mini))
    assert items["hooks:Stop:*:0"].scope == "managed"
    assert items["hooks:Stop:*:0"].status == "in_effect"
    assert items["hooks:Stop:*:1"].status == "ignored"


def test_disable_all_hooks_in_managed_turns_off_managed_hooks_too(
    mini: SetupContext, tmp_path: Path
) -> None:
    doc = json.loads(hooks_doc("Stop", "mgr"))
    doc["disableAllHooks"] = True
    put(tmp_path / "managed" / "managed-settings.json", json.dumps(doc))
    got = run(mini)
    assert by_id(got)["hooks:Stop:*:0"].status == "ignored"
    row = next(r for r in got.problems if r.code == "hooks_disabled")
    assert row.fix.kind == "cant_fix_here"
    assert row.fix.reason == "managed"


def test_a_higher_scope_can_switch_hooks_back_on(
    mini: SetupContext, tmp_path: Path
) -> None:
    user = json.loads(hooks_doc("Stop"))
    user["disableAllHooks"] = True
    put(tmp_path / "home" / ".claude" / "settings.json", json.dumps(user))
    put(
        tmp_path / "proj" / ".claude" / "settings.json",
        json.dumps({"disableAllHooks": False}),
    )
    items = by_id(run(mini))
    assert items["hooks:Stop:*:0"].status == "in_effect"
    switch = items["hooks:disableAllHooks"]
    assert [s.status for s in switch.sources] == ["in_effect", "overridden"]
    assert switch.scope == "project"


def test_allow_managed_hooks_only_blocks_everything_but_managed_hooks(
    mini: SetupContext, tmp_path: Path
) -> None:
    put(tmp_path / "home" / ".claude" / "settings.json", hooks_doc("Stop", "user"))
    managed = json.loads(hooks_doc("Stop", "mgr"))
    managed["allowManagedHooksOnly"] = True
    put(tmp_path / "managed" / "managed-settings.json", json.dumps(managed))
    items = by_id(run(mini))
    assert items["hooks:Stop:*:0"].status == "in_effect"
    assert items["hooks:Stop:*:1"].status == "ignored"
    reason = items["hooks:Stop:*:1"].reason
    assert reason is not None
    assert reason.ref_item == "hooks:allowManagedHooksOnly"


def test_allow_managed_hooks_only_outside_managed_settings_does_nothing(
    mini: SetupContext, tmp_path: Path
) -> None:
    doc = json.loads(hooks_doc("Stop"))
    doc["allowManagedHooksOnly"] = True
    put(tmp_path / "home" / ".claude" / "settings.json", json.dumps(doc, indent=2))
    got = run(mini)
    items = by_id(got)
    assert items["hooks:Stop:*:0"].status == "in_effect"
    switch = items["hooks:allowManagedHooksOnly"]
    assert switch.status == "ignored"
    assert switch.sources[0].status == "ignored"
    assert switch.confidence.level == "assumed"
    assert [r.code for r in got.problems] == ["ignored"]


def test_a_switch_with_a_bad_value_is_invalid(
    mini: SetupContext, tmp_path: Path
) -> None:
    put(
        tmp_path / "home" / ".claude" / "settings.json",
        json.dumps({"disableAllHooks": "yes"}, indent=2),
    )
    got = run(mini)
    switch = by_id(got)["hooks:disableAllHooks"]
    assert switch.status == "invalid"
    assert [r.code for r in got.problems] == ["value_invalid"]


def test_a_plugin_hook_survives_allow_managed_hooks_only_when_managed_enables_it(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("typical", tmp_path / "w", setup_corpus)
    put(
        root / "managed" / "managed-settings.json",
        json.dumps(
            {
                "allowManagedHooksOnly": True,
                "enabledPlugins": {"hivemind@bartab-demo": True},
            }
        ),
    )
    got = run(sc.context(root))
    items = by_id(got)
    assert items["hooks:PreToolUse:Bash:0"].status == "ignored"  # the user's own
    plugin = items["hooks:PreToolUse:Bash:1"]
    assert plugin.scope == "plugin"
    assert plugin.status == "in_effect"


def test_a_plugin_hook_is_blocked_when_managed_does_not_enable_it(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("typical", tmp_path / "w", setup_corpus)
    put(
        root / "managed" / "managed-settings.json",
        json.dumps({"allowManagedHooksOnly": True}),
    )
    items = by_id(run(sc.context(root)))
    assert items["hooks:PreToolUse:Bash:1"].status == "ignored"


# ---------------------------------------------------------------- bad shapes


def bad_doc() -> str:
    return (
        "{\n"
        '  "hooks": {\n'
        '    "NotAnEvent": [{"hooks": [{"type": "command", "command": "x"}]}],\n'
        '    "Stop": "not a list",\n'
        '    "PreToolUse": [\n'
        '      "not a group",\n'
        '      {"matcher": 5, "hooks": []},\n'
        '      {"matcher": "A", "hooks": "nope"},\n'
        '      {"matcher": "B", "hooks": [\n'
        "        3,\n"
        '        {"command": "no type"},\n'
        '        {"type": "carrier-pigeon"},\n'
        '        {"type": "command"},\n'
        '        {"type": "command", "command": "x", "args": [[1]]},\n'
        '        {"type": "http"},\n'
        '        {"type": "mcp_tool", "server": "s"},\n'
        '        {"type": "prompt"},\n'
        '        {"type": "command", "command": "fine"}\n'
        "      ]}\n"
        "    ]\n"
        "  }\n"
        "}\n"
    )


def test_every_bad_shape_makes_one_row_and_no_item(
    mini: SetupContext, tmp_path: Path
) -> None:
    put(tmp_path / "home" / ".claude" / "settings.json", bad_doc())
    got = run(mini)
    rows = {(r.code, r.line): r for r in got.problems}
    assert ("hook_bad_event", 3) in rows
    assert rows[("hook_bad_event", 3)].group == "wont_load"
    assert rows[("hook_bad_event", 3)].params == {"event": "NotAnEvent"}
    assert ("hook_bad_handler", 4) in rows  # Stop is not a list
    assert ("hook_bad_handler", 6) in rows  # a group that is a string
    assert ("hook_bad_handler", 7) in rows  # a matcher that is a number
    assert ("hook_bad_handler", 8) in rows  # a hooks value that is not a list
    whys = {
        r.params["why"]
        for r in got.problems
        if r.code == "hook_bad_handler" and r.line is not None and r.line >= 10
    }
    assert whys == {
        "not_object",
        "no_type",
        "unknown_type",
        "no_command",
        "bad_args",
        "no_url",
        "no_tool",
        "no_prompt",
    }
    assert [i.id for i in got.items["hooks"]] == ["hooks:PreToolUse:B:0"]
    assert all(r.code in ("hook_bad_event", "hook_bad_handler") for r in got.problems)


def test_a_hooks_key_that_is_not_an_object_is_a_bad_handler_row(
    mini: SetupContext, tmp_path: Path
) -> None:
    put(tmp_path / "home" / ".claude" / "settings.json", '{"hooks": [1]}\n')
    got = run(mini)
    assert [(r.code, r.line) for r in got.problems] == [("hook_bad_handler", 1)]
    assert got.items["hooks"] == []


def test_a_settings_file_that_does_not_parse_adds_no_hooks_row(
    mini: SetupContext, tmp_path: Path
) -> None:
    """The settings collector reports the bad file. This part shows no hooks of it."""
    put(tmp_path / "home" / ".claude" / "settings.json", '{"hooks": ')
    got = run(mini)
    assert got.items["hooks"] == []
    assert got.problems == []


def test_two_bad_handlers_on_one_line_make_one_row(
    mini: SetupContext, tmp_path: Path
) -> None:
    put(
        tmp_path / "home" / ".claude" / "settings.json",
        '{"hooks": {"Stop": [{"hooks": [1, 2]}]}}\n',
    )
    got = run(mini)
    assert len(got.problems) == 1
    assert len({r.id for r in got.problems}) == 1


# ---------------------------------------------------------------- plugin hooks


def plugin_world(
    tmp_path: Path, hooks_text: str, manifest: str | None = None
) -> SetupContext:
    """A user config with one enabled plugin whose hooks file holds ``hooks_text``."""
    home = tmp_path / "home" / ".claude"
    install = home / "plugins" / "cache" / "m" / "p" / "1.0"
    put(
        home / "settings.json",
        json.dumps({"enabledPlugins": {"p@m": True}}),
    )
    put(
        home / "plugins" / "installed_plugins.json",
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "p@m": [
                        {"scope": "user", "installPath": str(install), "version": "1.0"}
                    ]
                },
            }
        ),
    )
    put(install / ".claude-plugin" / "plugin.json", manifest or '{"name": "p"}')
    put(install / "hooks" / "hooks.json", hooks_text)
    return sc.scratch(tmp_path, {})


def test_a_plugin_hooks_file_with_bad_json_is_json_invalid(tmp_path: Path) -> None:
    ctx = plugin_world(tmp_path, '{\n  "hooks": {"Stop": \n')
    got = run(ctx)
    assert [(r.code, r.line, r.group) for r in got.problems] == [
        ("json_invalid", 3, "wont_load")
    ]
    row = got.problems[0]
    assert row.fix.kind == "cant_fix_here"
    assert row.fix.reason == "plugin"
    assert row.part == "hooks"
    assert got.items["hooks"] == []


def test_a_plugin_hooks_file_that_is_not_an_object_is_not_object(
    tmp_path: Path,
) -> None:
    got = run(plugin_world(tmp_path, "[1]"))
    assert [r.code for r in got.problems] == ["not_object"]


def test_a_plugin_hooks_file_may_hold_the_events_with_no_wrapper(
    tmp_path: Path,
) -> None:
    got = run(
        plugin_world(
            tmp_path,
            '{\n"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]\n}\n',
        )
    )
    item = by_id(got)["hooks:Stop:*:0"]
    assert item.sources[0].line == 2
    assert item.scope == "plugin"
    assert item.sources[0].plugin == "p"


def test_a_plugin_hooks_file_with_no_hooks_adds_nothing(tmp_path: Path) -> None:
    got = run(plugin_world(tmp_path, '{"description": "nothing"}'))
    assert got.items["hooks"] == []
    assert got.problems == []


def test_a_plugin_hook_is_read_only_and_names_its_plugin(tmp_path: Path) -> None:
    got = run(plugin_world(tmp_path, hooks_doc("Stop")))
    item = by_id(got)["hooks:Stop:*:0"]
    assert item.read_only_reason is not None
    assert item.read_only_reason.code == "plugin"
    assert item.read_only_reason.params == {"plugin": "p"}


def test_hooks_written_inline_in_a_manifest_are_read_with_their_lines(
    tmp_path: Path,
) -> None:
    manifest = (
        "{\n"
        '  "name": "p",\n'
        '  "hooks": {\n'
        '    "Stop": [{"hooks": [{"type": "command", "command": "inline"}]}]\n'
        "  }\n"
        "}\n"
    )
    ctx = plugin_world(tmp_path, '{"description": "x"}', manifest)
    handoff = hm.chain(ctx)
    item = by_id(handoff["hooks"])["hooks:Stop:*:0"]
    assert item.sources[0].file is not None
    assert item.sources[0].file.endswith("plugin.json")
    assert item.sources[0].line == 4


def test_plugin_input_in_the_components_shape_is_read_too(tmp_path: Path) -> None:
    ctx = plugin_world(tmp_path, hooks_doc("Stop"))
    settings = collect_settings.COLLECTOR.read(ctx, {})
    plugins = collect_plugins.COLLECTOR.read(ctx, settings.handoff)
    comps = plugins.handoff[collect_plugins.HANDOFF_COMPONENTS]
    got = COLLECTOR.read(
        ctx,
        {**settings.handoff, collect_plugins.HANDOFF_PLUGINS: comps},
    )
    assert [i.id for i in got.items["hooks"]] == ["hooks:Stop:*:0"]


def test_a_plugin_hooks_file_outside_the_plugin_folder_is_not_read_here(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(tmp_path, {})
    outside = put(tmp_path / "elsewhere" / "hooks.json", hooks_doc("Stop"))
    got = COLLECTOR.read(
        ctx,
        {"plugins": {"hooks": [{"plugin": "p@m", "name": "p", "path": str(outside)}]}},
    )
    assert got.items["hooks"] == []
    assert [(u.reason, u.part) for u in got.unreadable] == [
        ("plugin_outside_plugins", "hooks")
    ]


# ---------------------------------------------------------------- agent hooks


def test_agent_front_matter_hooks_are_listed_and_stop_becomes_subagent_stop(
    tmp_path: Path,
) -> None:
    agent = (
        "---\n"
        "name: checker\n"
        "description: Checks things.\n"
        "hooks:\n"
        "  Stop:\n"
        "    - hooks:\n"
        "        - type: command\n"
        "          command: ./scripts/done.sh\n"
        "---\n"
        "BODY\n"
    )
    put(tmp_path / "proj" / ".claude" / "agents" / "checker.md", agent)
    ctx = sc.scratch(tmp_path, {})
    got = run(ctx)
    item = by_id(got)["hooks:SubagentStop:*:0"]
    assert item.scope == "project"
    assert item.sources[0].file == ".claude/agents/checker.md"
    assert item.sources[0].line == 4
    assert item.sources[0].key == "hooks.Stop"
    assert item.facts.hook is not None
    assert item.facts.hook.event == "SubagentStop"


def test_a_plugin_agents_hooks_are_not_listed(tmp_path: Path) -> None:
    agent = (
        "---\nname: p-agent\ndescription: x.\nhooks:\n  Stop:\n"
        "    - hooks:\n        - type: command\n          command: x\n---\nBODY\n"
    )
    ctx = plugin_world(tmp_path, '{"description": "x"}')
    install = tmp_path / "home" / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0"
    put(install / "agents" / "p-agent.md", agent)
    got = run(ctx)
    assert got.items["hooks"] == []


def test_agent_hooks_with_a_bad_event_make_a_row(tmp_path: Path) -> None:
    agent = (
        "---\nname: a\ndescription: x.\nhooks:\n  Nope:\n"
        "    - hooks:\n        - type: command\n          command: x\n---\nBODY\n"
    )
    put(tmp_path / "proj" / ".claude" / "agents" / "a.md", agent)
    got = run(sc.scratch(tmp_path, {}))
    assert [(r.code, r.line) for r in got.problems] == [("hook_bad_event", 4)]


# ---------------------------------------------------------------- skill hooks


def skill_text(event: str = "PreToolUse", command: str = "./v.sh") -> str:
    return (
        f"---\nname: s\ndescription: x.\nhooks:\n  {event}:\n"
        f"    - matcher: Bash\n      hooks:\n        - type: command\n"
        f"          command: {command}\n---\nBODY\n"
    )


def test_skill_front_matter_hooks_are_listed_after_agent_hooks(
    tmp_path: Path,
) -> None:
    agent = skill_text().replace("name: s", "name: a")
    put(tmp_path / "proj" / ".claude" / "agents" / "a.md", agent)
    put(tmp_path / "proj" / ".claude" / "skills" / "s" / "SKILL.md", skill_text())
    put(
        tmp_path / "proj" / ".claude" / "settings.json",
        hooks_doc("PreToolUse", "x", "Bash"),
    )
    got = run(sc.scratch(tmp_path, {}))
    rows = [i for i in got.items["hooks"] if i.id.startswith("hooks:PreToolUse")]
    assert [r.sources[0].file for r in rows] == [
        ".claude/settings.json",
        ".claude/agents/a.md",
        ".claude/skills/s/SKILL.md",
    ]
    skill = rows[2]
    assert (skill.scope, skill.sources[0].key) == ("project", "hooks.PreToolUse")
    assert skill.sources[0].line == 4  # the ``hooks`` key line


def test_a_skill_stop_hook_stays_stop(tmp_path: Path) -> None:
    put(
        tmp_path / "proj" / ".claude" / "skills" / "s" / "SKILL.md",
        skill_text("Stop"),
    )
    got = run(sc.scratch(tmp_path, {}))
    assert [i.id for i in got.items["hooks"]] == ["hooks:Stop:Bash:0"]


def test_a_plugin_skills_hooks_are_listed(tmp_path: Path) -> None:
    ctx = plugin_world(tmp_path, '{"description": "x"}')
    install = tmp_path / "home" / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0"
    put(install / "skills" / "ps" / "SKILL.md", skill_text())
    got = run(ctx)
    [item] = got.items["hooks"]
    assert item.scope == "plugin"
    assert item.sources[0].plugin == "p"


def test_a_skill_that_loses_its_name_does_not_hand_its_hooks_on(
    tmp_path: Path,
) -> None:
    put(tmp_path / "home" / ".claude" / "skills" / "s" / "SKILL.md", skill_text())
    put(tmp_path / "proj" / ".claude" / "skills" / "s" / "SKILL.md", skill_text("Stop"))
    got = run(sc.scratch(tmp_path, {}))
    # The user skill beats the project one, so only its hooks are listed.
    assert [i.id for i in got.items["hooks"]] == ["hooks:PreToolUse:Bash:0"]


def test_skill_hooks_with_a_bad_event_make_a_row(tmp_path: Path) -> None:
    put(
        tmp_path / "proj" / ".claude" / "skills" / "s" / "SKILL.md",
        skill_text("Nope"),
    )
    got = run(sc.scratch(tmp_path, {}))
    assert [(r.code, r.line) for r in got.problems] == [("hook_bad_event", 4)]


# ---------------------------------------------------------------- masking


def test_a_secret_inside_a_hook_command_is_hidden(
    mini: SetupContext, tmp_path: Path
) -> None:
    commands = [
        "python3 c.py --api-key sk-ant-api03-SECRETONE",
        "run API_KEY=hunter2 go",
        "curl -H 'Authorization: Bearer abc.def' https://u:p4ss@h.test/x",
        "tool --password=hunter3 --user me",
        "echo sk-live-SECRETTWO",
    ]
    doc = {
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": c} for c in commands]}]
        }
    }
    put(tmp_path / "home" / ".claude" / "settings.json", json.dumps(doc))
    got = run(mini)
    shown = [
        i.facts.hook.command.text
        for i in got.items["hooks"]
        if i.facts.hook and i.facts.hook.command
    ]
    assert shown == [
        "python3 c.py --api-key hidden",
        "run API_KEY=hidden go",
        "curl -H 'Authorization: Bearer hidden' https://u:hidden@h.test/x",
        "tool --password=hidden --user me",
        "echo hidden",
    ]
    text = hm.everything({"hooks": got})
    for secret in (
        "SECRETONE",
        "hunter2",
        "abc.def",
        "p4ss",
        "hunter3",
        "SECRETTWO",
    ):
        assert secret not in text


# ---------------------------------------------------------------- Couldn't read


def test_a_plugin_hooks_file_that_is_not_utf8_is_couldnt_read(tmp_path: Path) -> None:
    ctx = plugin_world(tmp_path, hooks_doc("Stop"))
    install = tmp_path / "home" / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0"
    (install / "hooks" / "hooks.json").write_bytes(b'{"hooks": \xff\xfe}')
    got = run(ctx)
    assert [(u.reason, u.part, u.scope) for u in got.unreadable] == [
        ("not_utf8", "hooks", "plugin")
    ]
    assert got.items["hooks"] == []
    assert got.problems == []


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_plugin_hooks_file_at_mode_000_is_couldnt_read(tmp_path: Path) -> None:
    ctx = plugin_world(tmp_path, hooks_doc("Stop"))
    install = tmp_path / "home" / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0"
    target = install / "hooks" / "hooks.json"
    target.chmod(0)
    try:
        got = run(ctx)
    finally:
        target.chmod(0o644)
    assert [(u.reason, u.part) for u in got.unreadable] == [("permission", "hooks")]


def test_a_plugin_hooks_file_over_the_cap_is_couldnt_read(tmp_path: Path) -> None:
    ctx = plugin_world(tmp_path, hooks_doc("Stop"))
    install = tmp_path / "home" / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0"
    (install / "hooks" / "hooks.json").write_bytes(b" " * (1024 * 1024 + 1))
    got = run(ctx)
    assert [(u.reason, u.part) for u in got.unreadable] == [("too_large", "hooks")]


def test_every_unreadable_file_names_its_part(tmp_path: Path) -> None:
    ctx = plugin_world(tmp_path, hooks_doc("Stop"))
    install = tmp_path / "home" / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0"
    (install / "hooks" / "hooks.json").write_bytes(b"\xff")
    for file in run(ctx).unreadable:
        assert file.part == "hooks"


# ---------------------------------------------------------------- stability


def test_ids_and_order_are_stable_over_two_reads(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    ctx = sc.context(root)
    first = run(ctx)
    second = run(ctx)
    assert [i.model_dump() for i in first.items["hooks"]] == [
        i.model_dump() for i in second.items["hooks"]
    ]
    assert [p.model_dump() for p in first.problems] == [
        p.model_dump() for p in second.problems
    ]
    assert [i.order for i in first.items["hooks"]] == list(
        range(len(first.items["hooks"]))
    )


def test_the_ids_follow_the_documented_shape(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    pattern = re.compile(
        r"^hooks:(?:[A-Za-z]+:[^:]+:\d+|disableAllHooks|allowManagedHooksOnly)$"
    )
    for item in run(sc.context(root)).items["hooks"]:
        assert pattern.match(item.id), item.id


def test_the_signature_follows_the_plugin_hook_files(tmp_path: Path) -> None:
    ctx = plugin_world(tmp_path, hooks_doc("Stop"))
    got = run(ctx)
    before = COLLECTOR.signature(ctx, got)
    assert COLLECTOR.signature(ctx, got) == before
    install = tmp_path / "home" / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0"
    put(install / "hooks" / "hooks.json", hooks_doc("Stop", "a different command"))
    assert COLLECTOR.signature(ctx, got) != before
    assert COLLECTOR.signature(ctx, None)  # a first signature has no touched list


def test_the_collector_is_the_hooks_part_only(mini: SetupContext) -> None:
    assert COLLECTOR.name == "hooks"
    assert list(COLLECTOR.parts) == ["hooks"]
    assert set(run(mini).items) == {"hooks"}


def test_the_collector_reads_the_settings_itself_when_nothing_is_handed(
    tmp_path: Path,
) -> None:
    put(tmp_path / "home" / ".claude" / "settings.json", hooks_doc("Stop"))
    ctx = sc.scratch(tmp_path, {})
    got = COLLECTOR.read(ctx, {})
    assert [i.id for i in got.items["hooks"]] == ["hooks:Stop:*:0"]


def test_an_unlisted_project_marks_its_scopes_not_visible(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("scope-unlisted", tmp_path / "w", setup_corpus)
    put(root / "home" / ".claude" / "settings.json", hooks_doc("Stop"))
    got = run(sc.context(root))
    item = got.items["hooks"][0]
    hidden = {r.scope for r in item.reach if not r.visible}
    assert hidden == {"project_local", "project"}

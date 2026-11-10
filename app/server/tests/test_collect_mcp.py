"""The MCP collector (m4-build.md task 8).

Every corpus case's expected.json is the oracle for the part, run through the same
chain the answer builder uses (settings, plugins, agents, the masked reader, hooks,
MCP). Crafted folders then cover precedence, approvals, the kinds of bad entry,
masking, read-only owners, Couldn't read, the order across two reads and the
signature.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import hook_mcp_helpers as hm
import setup_case_helpers as sc

import claude_json
import collect_mcp
import mcp_entry
from models import SetupItem
from setup_contract import Collected, SetupContext

COLLECTOR = collect_mcp.COLLECTOR
NOT_ROOT = os.geteuid() != 0


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def servers(**table: object) -> str:
    return json.dumps({"mcpServers": table}, indent=2) + "\n"


def run(ctx: SetupContext) -> Collected:
    return hm.chain(ctx)["mcp"]


def by_id(got: Collected) -> dict[str, SetupItem]:
    return {i.id: i for i in got.items["mcp"]}


STDIO = {"command": "node", "args": ["a.js"]}
HTTP = {"type": "http", "url": "https://x.example.test/mcp"}


@pytest.fixture
def mini(tmp_path: Path) -> SetupContext:
    return sc.scratch(tmp_path, {})


def settings_with(tmp_path: Path, **keys: object) -> None:
    put(tmp_path / "proj" / ".claude" / "settings.json", json.dumps(keys))


# ---------------------------------------------------------------- the corpus


@pytest.mark.parametrize("case", sc.CASES)
def test_items_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = run(sc.context(root))
    made, wanted = sc.compare_items(got, case, "mcp")
    assert made == wanted


@pytest.mark.parametrize("case", sc.CASES)
def test_the_mcp_and_reader_problems_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    """The reader's rows belong to the mcp part, so the two collectors share them."""
    root = sc.world(case, tmp_path / "w", setup_corpus)
    answers = hm.chain(sc.context(root))
    made = [sc.problem_view(r) for r in hm.problems(answers, ("mcp",))]
    wanted = [
        {k: row[k] for k in ("id", "group", "code", "part", "item_id", "file", "line")}
        for row in sc.expected(case)["problems"]
        if row["part"] == "mcp"
    ]
    assert made == wanted


def test_a_case_with_no_servers_has_no_items(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    got = run(sc.context(root))
    assert got.items["mcp"] == []
    assert got.problems == []
    assert got.unreadable == []


# ---------------------------------------------------------------- item fields


def test_the_facts_of_a_stdio_and_a_remote_server(tmp_path: Path) -> None:
    put(
        tmp_path / "proj" / ".mcp.json",
        servers(
            local={
                "command": "npx",
                "args": ["-y", "pkg", "--token", "ghp_FAKEFAKEFAKEFAKEFAKE0001"],
                "env": {"PLAIN": "value", "API_KEY": "sk-live-FAKE0002"},
            },
            remote={
                "type": "streamable-http",
                "url": "https://user:pw0003@api.example.test/mcp",
                "headers": {"X-Api-Key": "k-0004", "Accept": "text/plain"},
            },
        ),
    )
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    items = by_id(run(sc.scratch(tmp_path, {})))
    stdio = items["mcp:local"].facts.mcp
    assert stdio is not None
    assert stdio.transport == "stdio"
    assert stdio.command is not None
    assert stdio.command.text == "npx"
    assert [a.text for a in stdio.args] == ["-y", "pkg", "--token", "hidden"]
    assert [a.masked for a in stdio.args] == [False, False, False, True]
    assert {k: (v.text, v.masked) for k, v in stdio.env.items()} == {
        "PLAIN": ("value", False),
        "API_KEY": ("hidden", True),
    }
    assert stdio.url is None
    assert stdio.approved is True
    remote = items["mcp:remote"].facts.mcp
    assert remote is not None
    assert remote.transport == "http"  # streamable-http is an alias
    assert remote.url is not None
    assert (remote.url.text, remote.url.masked) == (
        "https://user:hidden@api.example.test/mcp",
        True,
    )
    assert {k: v.text for k, v in remote.headers.items()} == {
        "X-Api-Key": "hidden",
        "Accept": "text/plain",
    }
    assert remote.command is None


def test_the_shared_item_fields(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    for item in run(sc.context(root)).items["mcp"]:
        assert item.part == "mcp"
        assert item.writable is False
        assert item.feature == "core"
        assert item.label_known is True
        assert item.key == item.name
        sources = item.sources
        plugin = sources[0].plugin if sources else None
        assert item.id == (
            f"mcp:{plugin}:{item.name}" if plugin else f"mcp:{item.name}"
        )
        assert item.winner == 0
        assert item.confidence.level == "documented"
        assert item.effective is None
        assert item.loads is None
        assert item.group is None


def test_ids_are_sorted_and_numbered(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    items = run(sc.context(root)).items["mcp"]
    assert [i.id for i in items] == sorted(i.id for i in items)
    assert [i.order for i in items] == list(range(len(items)))


# ---------------------------------------------------------------- read-only owners


def test_user_and_local_servers_are_read_only_with_the_claude_mcp_command(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("typical", tmp_path / "w", setup_corpus)
    items = by_id(run(sc.context(root)))
    user = items["mcp:notes"].read_only_reason
    assert user is not None
    assert user.code == "claude_json_command"
    assert user.command is not None
    assert user.command.text == "claude mcp remove notes -s user"
    local = items["mcp:scratch"].read_only_reason
    assert local is not None
    assert local.code == "claude_json_command"
    assert local.command is not None
    assert local.command.text == "claude mcp remove scratch -s local"


def test_a_server_name_with_odd_characters_is_quoted_in_the_command(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    put(home / ".claude.json", json.dumps({"mcpServers": {"my server": STDIO}}))
    item = by_id(run(sc.scratch(tmp_path, {})))["mcp:my server"]
    assert item.read_only_reason is not None
    assert item.read_only_reason.command is not None
    assert item.read_only_reason.command.text == "claude mcp remove 'my server' -s user"


def test_managed_plugin_and_project_servers_carry_their_own_owners(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    items = by_id(run(sc.context(root)))
    managed = items["mcp:corp-wiki"].read_only_reason
    assert managed is not None
    assert managed.code == "managed"
    plugin = items["mcp:routing-dashboard:dash-metrics"].read_only_reason
    assert plugin is not None
    assert (plugin.code, plugin.params) == ("plugin", {"plugin": "routing-dashboard"})
    assert items["mcp:docs"].read_only_reason is None


def test_a_user_server_with_no_command_or_url_offers_the_copy_command(
    tmp_path: Path,
) -> None:
    """Owner decision 8: Bar Tab only copies ``claude mcp remove``, never runs it."""
    put(tmp_path / "home" / ".claude.json", json.dumps({"mcpServers": {"dead": {}}}))
    answers = hm.chain(sc.scratch(tmp_path, {}))
    item = by_id(answers["mcp"])["mcp:dead"]
    assert item.status == "invalid"
    assert item.read_only_reason is not None
    assert item.read_only_reason.code == "claude_json_command"
    assert item.read_only_reason.command is not None
    assert item.read_only_reason.command.text == "claude mcp remove dead -s user"
    row = answers["mcp"].problems[0]
    assert row.code == "mcp_bad_entry"
    assert (row.fix.kind, row.fix.target) == (
        "copy_command",
        "claude mcp remove dead -s user",
    )
    assert row.params == {"name": "dead", "why": "no_command_or_url"}


def test_a_local_server_with_no_command_offers_the_local_command(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(tmp_path, {})
    project = str(ctx.project_dir)
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps({"projects": {project: {"mcpServers": {"gone": {"env": {}}}}}}),
    )
    answers = hm.chain(ctx)
    row = answers["mcp"].problems[0]
    assert row.fix.target == "claude mcp remove gone -s local"


# ---------------------------------------------------------------- precedence


def test_local_beats_project_beats_user_and_managed_beats_all(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {
                "mcpServers": {"same": STDIO, "mu": STDIO},
                "projects": {str(ctx.project_dir): {"mcpServers": {"same": STDIO}}},
            }
        ),
    )
    put(tmp_path / "proj" / ".mcp.json", servers(same=STDIO, mp=STDIO))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    put(tmp_path / "managed" / "managed-mcp.json", servers(same=HTTP, mp=HTTP, mu=HTTP))
    items = by_id(run(ctx))
    same = items["mcp:same"]
    assert [(s.scope, s.status) for s in same.sources] == [
        ("managed", "in_effect"),
        ("project_local", "overridden"),
        ("project", "overridden"),
        ("user", "overridden"),
    ]
    assert same.scope == "managed"
    assert same.winner == 0
    assert same.facts.mcp is not None
    assert same.facts.mcp.transport == "http"
    assert [s.scope for s in items["mcp:mp"].sources] == ["managed", "project"]
    assert [s.scope for s in items["mcp:mu"].sources] == ["managed", "user"]


def test_without_a_managed_server_local_wins(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {
                "mcpServers": {"same": {"command": "user"}},
                "projects": {
                    str(ctx.project_dir): {"mcpServers": {"same": {"command": "local"}}}
                },
            }
        ),
    )
    put(tmp_path / "proj" / ".mcp.json", servers(same={"command": "project"}))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    item = by_id(run(ctx))["mcp:same"]
    assert item.scope == "project_local"
    assert item.facts.mcp is not None
    assert item.facts.mcp.command is not None
    assert item.facts.mcp.command.text == "local"
    assert item.confidence.level == "documented"


def test_a_bad_entry_above_the_winner_does_not_shadow_it_but_lowers_confidence(
    tmp_path: Path,
) -> None:
    put(tmp_path / "home" / ".claude.json", json.dumps({"mcpServers": {"x": STDIO}}))
    put(tmp_path / "proj" / ".mcp.json", servers(x={}))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    item = by_id(run(sc.scratch(tmp_path, {})))["mcp:x"]
    assert [(s.scope, s.status) for s in item.sources] == [
        ("project", "invalid"),
        ("user", "in_effect"),
    ]
    assert item.winner == 1
    assert item.status == "in_effect"
    assert item.confidence.level == "assumed"


def test_a_plugin_server_never_meets_a_server_of_the_same_name(
    tmp_path: Path,
) -> None:
    ctx = plugin_world(tmp_path, servers(dup=STDIO))
    put(tmp_path / "home" / ".claude.json", json.dumps({"mcpServers": {"dup": HTTP}}))
    items = by_id(run(ctx))
    assert set(items) == {"mcp:dup", "mcp:p:dup"}
    assert items["mcp:dup"].scope == "user"
    assert items["mcp:p:dup"].scope == "plugin"
    assert items["mcp:p:dup"].sources[0].plugin == "p"


def test_a_plugin_server_with_a_unique_name_still_gets_the_plugin_id(
    tmp_path: Path,
) -> None:
    items = by_id(run(plugin_world(tmp_path, servers(only=STDIO))))
    assert list(items) == ["mcp:p:only"]


# ---------------------------------------------------------------- approvals


def test_an_unapproved_project_server_is_ignored_with_no_problem_row(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO))
    got = run(sc.scratch(tmp_path, {}))
    item = by_id(got)["mcp:a"]
    assert item.status == "ignored"
    assert item.sources[0].status == "ignored"
    assert item.winner is None
    assert item.reason is not None
    assert item.reason.code == "mcp_not_approved"
    assert item.facts.mcp is not None
    assert item.facts.mcp.approved is False
    assert got.problems == []


def test_enabled_servers_approve_by_name(tmp_path: Path) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO, b=STDIO))
    settings_with(tmp_path, enabledMcpjsonServers=["a"])
    items = by_id(run(sc.scratch(tmp_path, {})))
    assert items["mcp:a"].status == "in_effect"
    assert items["mcp:b"].status == "ignored"
    assert items["mcp:a"].facts.mcp is not None
    assert items["mcp:a"].facts.mcp.approved is True


def test_disabled_beats_enabled_and_enable_all_from_any_settings_file(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO, b=STDIO, c=STDIO))
    put(
        tmp_path / "home" / ".claude" / "settings.json",
        json.dumps(
            {"disabledMcpjsonServers": ["a"], "enableAllProjectMcpServers": True}
        ),
    )
    settings_with(tmp_path, enabledMcpjsonServers=["a"])
    items = by_id(run(sc.scratch(tmp_path, {})))
    assert items["mcp:a"].status == "ignored"
    assert items["mcp:a"].reason is not None
    assert items["mcp:a"].reason.params["by"] == "disabledMcpjsonServers"
    assert items["mcp:b"].status == "in_effect"
    assert items["mcp:c"].status == "in_effect"


def test_enable_all_set_false_by_a_higher_scope_approves_nothing(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO))
    put(
        tmp_path / "home" / ".claude" / "settings.json",
        json.dumps({"enableAllProjectMcpServers": True}),
    )
    settings_with(tmp_path, enableAllProjectMcpServers=False)
    assert by_id(run(sc.scratch(tmp_path, {})))["mcp:a"].status == "ignored"


def test_the_old_approval_keys_in_the_home_file_count_too(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO, b=STDIO, c=STDIO))
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {
                "projects": {
                    str(ctx.project_dir): {
                        "enabledMcpjsonServers": ["a", 3],
                        "disabledMcpjsonServers": ["b"],
                        "enableAllProjectMcpServers": True,
                    }
                }
            }
        ),
    )
    items = by_id(run(ctx))
    assert [items[f"mcp:{n}"].status for n in "abc"] == [
        "in_effect",
        "ignored",
        "in_effect",
    ]


def put_toggled(ctx: SetupContext, tmp_path: Path, **extra: object) -> None:
    """Write the home file with a user server and the project's off switches."""
    entry: dict[str, object] = {
        "mcpServers": {"l": STDIO},
        "disabledMcpServers": ["u", "m", "l", "plugin:p:pm", "a"],
    }
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {
                "mcpServers": {"u": STDIO, "kept": STDIO},
                "projects": {str(ctx.project_dir): entry | extra},
            }
        ),
    )


def test_a_server_the_mcp_panel_turned_off_is_ignored_and_names_the_key(
    tmp_path: Path,
) -> None:
    ctx = plugin_world(tmp_path, servers(pm=STDIO))
    put(tmp_path / "managed" / "managed-mcp.json", servers(m=STDIO))
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    put_toggled(ctx, tmp_path)
    got = run(ctx)
    items = by_id(got)
    for item_id in ("mcp:u", "mcp:m", "mcp:l", "mcp:p:pm"):
        item = items[item_id]
        assert item.status == "ignored", item_id
        assert item.winner is None
        assert item.reason is not None
        assert item.reason.params["by"] == "disabledMcpServers"
    assert items["mcp:kept"].status == "in_effect"
    assert got.problems == []


def test_the_toggle_list_does_not_touch_a_project_mcp_file_server(
    tmp_path: Path,
) -> None:
    """The two kinds of list cover disjoint servers (mcp.md)."""
    ctx = plugin_world(tmp_path, servers(pm=STDIO))
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    put_toggled(ctx, tmp_path)
    assert by_id(run(ctx))["mcp:a"].status == "in_effect"


def test_a_plugin_server_is_matched_by_its_scoped_name_and_marked_assumed(
    tmp_path: Path,
) -> None:
    ctx = plugin_world(tmp_path, servers(pm=STDIO, other=STDIO))
    put_toggled(ctx, tmp_path)
    items = by_id(run(ctx))
    assert items["mcp:p:pm"].status == "ignored"
    assert items["mcp:p:pm"].confidence.level == "assumed"
    assert items["mcp:p:other"].status == "in_effect"


def test_a_toggled_off_server_does_not_shadow_the_one_below_it(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(tmp_path / "managed" / "managed-mcp.json", servers(dup=STDIO))
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {
                "mcpServers": {"dup": HTTP},
                "projects": {str(ctx.project_dir): {"disabledMcpServers": ["dup"]}},
            }
        ),
    )
    item = by_id(run(ctx))["mcp:dup"]
    # Both definitions share the name, so the toggle turns both off.
    assert item.status == "ignored"
    assert [s.status for s in item.sources] == ["ignored", "ignored"]


def test_user_local_and_managed_servers_need_no_approval(tmp_path: Path) -> None:
    put(tmp_path / "home" / ".claude.json", json.dumps({"mcpServers": {"u": STDIO}}))
    put(tmp_path / "managed" / "managed-mcp.json", servers(m=STDIO))
    items = by_id(run(sc.scratch(tmp_path, {})))
    assert items["mcp:u"].status == items["mcp:m"].status == "in_effect"
    assert items["mcp:u"].facts.mcp is not None
    assert items["mcp:u"].facts.mcp.approved is None


# ---------------------------------------------------------------- bad entries


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        ({}, "no_command_or_url"),
        ({"env": {"A": "b"}}, "no_command_or_url"),
        ({"url": "https://a.test"}, "url_without_type"),
        ({"type": "http"}, "no_url"),
        ({"type": "sse", "command": "x"}, "no_url"),
        ({"type": "stdio", "url": "https://a.test"}, "no_command"),
        ({"type": "carrier-pigeon", "command": "x"}, "unknown_type"),
        ({"type": 5, "command": "x"}, "bad_type"),
        ({"command": 5}, "bad_field"),
        ({"command": "x", "args": "no"}, "bad_field"),
        ({"command": "x", "args": [[1]]}, "bad_field"),
        ({"command": "x", "env": []}, "bad_field"),
        ({"command": "x", "env": {"A": {"b": 1}}}, "bad_field"),
        ({"command": "x", "headers": "no"}, "bad_field"),
        ("a string", "not_object"),
        ([1], "not_object"),
        (None, "not_object"),
    ],
)
def test_each_bad_shape_is_mcp_bad_entry_with_its_reason(
    entry: object, why: str, tmp_path: Path
) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(bad=entry))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    got = run(sc.scratch(tmp_path, {}))
    item = by_id(got)["mcp:bad"]
    assert item.status == "invalid"
    assert [(r.code, r.group, r.kind) for r in got.problems] == [
        ("mcp_bad_entry", "wont_load", "problem")
    ]
    assert got.problems[0].params["why"] == why
    assert got.problems[0].fix.kind == "open_item"
    assert got.problems[0].item_id == "mcp:bad"


@pytest.mark.parametrize(
    "entry",
    [
        STDIO,
        {"command": "x", "args": [1, 2.5, True]},
        {"type": "stdio", "command": "x"},
        {"type": "ws", "url": "wss://a.test/s"},
        {"type": "sse", "url": "https://a.test/s", "headers": {"A": 1}},
        {"command": "x", "unknown_key": {"nested": "ignored"}},
    ],
)
def test_good_shapes_are_in_effect(entry: object, tmp_path: Path) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(ok=entry))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    got = run(sc.scratch(tmp_path, {}))
    assert by_id(got)["mcp:ok"].status == "in_effect"
    assert got.problems == []


def test_two_bad_servers_on_one_line_of_two_files_keep_distinct_rows(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", '{"mcpServers": {\n"x": {}}}\n')
    put(tmp_path / "managed" / "managed-mcp.json", '{"mcpServers": {\n"x": {}}}\n')
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    got = run(sc.scratch(tmp_path, {}))
    assert len(got.problems) == 2
    assert len({r.id for r in got.problems}) == 2


def test_a_file_that_is_not_json_is_json_invalid_and_keeps_the_others(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", '{\n  "mcpServers": {\n    "a": \n')
    put(tmp_path / "managed" / "managed-mcp.json", servers(m=STDIO))
    got = run(sc.scratch(tmp_path, {}))
    assert [(r.code, r.line, r.file) for r in got.problems] == [
        ("json_invalid", 4, ".mcp.json")
    ]
    assert got.problems[0].fix.kind == "copy_path"
    assert list(by_id(got)) == ["mcp:m"]


def test_a_managed_file_that_is_not_json_cannot_be_fixed_here(tmp_path: Path) -> None:
    put(tmp_path / "managed" / "managed-mcp.json", "{")
    got = run(sc.scratch(tmp_path, {}))
    assert got.problems[0].fix.kind == "cant_fix_here"
    assert got.problems[0].fix.reason == "managed"


def test_a_server_file_whose_top_level_is_an_array_is_not_object(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", "[]")
    got = run(sc.scratch(tmp_path, {}))
    assert [(r.code, r.line) for r in got.problems] == [("not_object", 1)]


def test_mcp_servers_that_is_not_an_object_is_not_object_at_its_line(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", '{\n  "other": 1,\n  "mcpServers": []\n}\n')
    got = run(sc.scratch(tmp_path, {}))
    assert [(r.code, r.line, r.params) for r in got.problems] == [
        ("not_object", 3, {"key": "mcpServers"})
    ]


def test_a_file_with_no_servers_key_adds_nothing(tmp_path: Path) -> None:
    put(tmp_path / "proj" / ".mcp.json", '{"note": "empty"}')
    got = run(sc.scratch(tmp_path, {}))
    assert got.items["mcp"] == []
    assert got.problems == []


# ---------------------------------------------------------------- ${VAR}


def test_a_variable_with_no_default_is_cant_tell(tmp_path: Path) -> None:
    put(
        tmp_path / "proj" / ".mcp.json",
        servers(
            a={"command": "node", "args": ["${A_FILE}"]},
            b={"command": "${B_BIN}"},
            c={"type": "http", "url": "${BASE}/mcp", "headers": {"H": "${C_HDR}"}},
            d={"command": "node", "env": {"K": "${D_ENV}", "L": "${D_ENV}"}},
        ),
    )
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    got = run(sc.scratch(tmp_path, {}))
    items = by_id(got)
    assert {i.id: i.status for i in items.values()} == {
        "mcp:a": "unknown",
        "mcp:b": "unknown",
        "mcp:c": "unknown",
        "mcp:d": "unknown",
    }
    rows = {r.item_id: r for r in got.problems}
    assert {r.code for r in got.problems} == {"env_not_visible"}
    assert all(r.group == "cant_tell" and r.kind == "cant_tell" for r in got.problems)
    assert rows["mcp:a"].params["vars"] == "A_FILE"
    assert rows["mcp:c"].params["vars"] == "BASE,C_HDR"
    assert rows["mcp:d"].params["vars"] == "D_ENV"
    assert items["mcp:a"].reason is not None
    assert items["mcp:a"].reason.code == "env_not_visible"


def test_a_variable_with_a_default_is_fine(tmp_path: Path) -> None:
    put(
        tmp_path / "proj" / ".mcp.json",
        servers(
            a={"command": "node", "args": ["${DIR:-.}", "${EMPTY:-}"]},
            b={"type": "http", "url": "${BASE:-https://x.test}/mcp"},
        ),
    )
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    got = run(sc.scratch(tmp_path, {}))
    assert {i.status for i in got.items["mcp"]} == {"in_effect"}
    assert got.problems == []


def test_plugin_variables_are_known_only_in_a_plugin_entry(tmp_path: Path) -> None:
    entry = {
        "command": "${CLAUDE_PLUGIN_ROOT}/bin/s",
        "args": ["${CLAUDE_PROJECT_DIR}"],
    }
    ctx = plugin_world(tmp_path, servers(inplugin=entry))
    put(tmp_path / "proj" / ".mcp.json", servers(inproject=entry))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    items = by_id(run(ctx))
    assert items["mcp:p:inplugin"].status == "in_effect"
    assert items["mcp:inproject"].status == "unknown"


def test_a_variable_on_an_ignored_or_overridden_server_makes_no_row(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(a={"command": "${X}"}))
    got = run(sc.scratch(tmp_path, {}))  # not approved
    assert by_id(got)["mcp:a"].status == "ignored"
    assert got.problems == []


def test_an_overridden_variable_entry_makes_no_row(tmp_path: Path) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(a={"command": "${X}"}))
    put(tmp_path / "managed" / "managed-mcp.json", servers(a=STDIO))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    got = run(sc.scratch(tmp_path, {}))
    assert got.problems == []


# ---------------------------------------------------------------- plugins


def plugin_world(
    tmp_path: Path, mcp_text: str, manifest: str | None = None
) -> SetupContext:
    """A user config with one enabled plugin whose ``.mcp.json`` holds ``mcp_text``."""
    home = tmp_path / "home" / ".claude"
    install = home / "plugins" / "cache" / "m" / "p" / "1.0"
    put(home / "settings.json", json.dumps({"enabledPlugins": {"p@m": True}}))
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
    put(install / ".mcp.json", mcp_text)
    return sc.scratch(tmp_path, {})


def test_plugin_servers_carry_their_plugin_and_the_file_line(tmp_path: Path) -> None:
    items = by_id(run(plugin_world(tmp_path, servers(srv=STDIO))))
    src = items["mcp:p:srv"].sources[0]
    assert (src.scope, src.plugin, src.key, src.line) == (
        "plugin",
        "p",
        "mcpServers.srv",
        3,
    )
    assert src.file is not None
    assert src.file.endswith(".mcp.json")


def test_servers_written_inline_in_a_manifest_are_read_with_their_lines(
    tmp_path: Path,
) -> None:
    manifest = (
        '{\n  "name": "p",\n  "mcpServers": {\n    "inline": {"command": "x"}\n  }\n}\n'
    )
    items = by_id(run(plugin_world(tmp_path, "{}", manifest)))
    src = items["mcp:p:inline"].sources[0]
    assert src.line == 4
    assert src.file is not None
    assert src.file.endswith("plugin.json")


def test_a_plugin_file_that_is_not_json_makes_a_row_that_cannot_be_fixed_here(
    tmp_path: Path,
) -> None:
    got = run(plugin_world(tmp_path, "{"))
    assert [r.code for r in got.problems] == ["json_invalid"]
    assert got.problems[0].fix.reason == "plugin"


def test_a_plugin_mcp_file_outside_the_plugin_folder_is_not_read_here(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(tmp_path, {})
    outside = put(tmp_path / "elsewhere" / ".mcp.json", servers(x=STDIO))
    got = COLLECTOR.read(
        ctx,
        {"plugins": {"mcp": [{"plugin": "p@m", "name": "p", "path": str(outside)}]}},
    )
    assert got.items["mcp"] == []
    assert [(u.reason, u.part) for u in got.unreadable] == [
        ("plugin_outside_plugins", "mcp")
    ]


def test_without_any_handoff_the_collector_reads_the_settings_and_the_home_file(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    put(tmp_path / "home" / ".claude.json", json.dumps({"mcpServers": {"u": STDIO}}))
    claude_json.clear_cache()
    got = COLLECTOR.read(sc.scratch(tmp_path, {}), {})
    assert {i.id: i.status for i in got.items["mcp"]} == {
        "mcp:a": "in_effect",
        "mcp:u": "in_effect",
    }


# ---------------------------------------------------------------- Couldn't read


def test_a_server_file_that_is_not_utf8_is_couldnt_read(tmp_path: Path) -> None:
    target = tmp_path / "proj" / ".mcp.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"mcpServers": \xff}')
    got = run(sc.scratch(tmp_path, {}))
    assert [(u.reason, u.part, u.scope) for u in got.unreadable] == [
        ("not_utf8", "mcp", "project")
    ]
    assert got.items["mcp"] == []
    assert got.problems == []


def test_a_server_file_over_the_cap_is_couldnt_read(tmp_path: Path) -> None:
    target = tmp_path / "managed" / "managed-mcp.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b" " * (1024 * 1024 + 1))
    got = run(sc.scratch(tmp_path, {}))
    assert [(u.reason, u.scope) for u in got.unreadable] == [("too_large", "managed")]


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_server_file_at_mode_000_is_couldnt_read(tmp_path: Path) -> None:
    target = put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO))
    target.chmod(0)
    try:
        got = run(sc.scratch(tmp_path, {}))
    finally:
        target.chmod(0o644)
    assert [(u.reason, u.part) for u in got.unreadable] == [("permission", "mcp")]


def test_a_failed_file_marks_the_items_it_could_change(tmp_path: Path) -> None:
    target = tmp_path / "proj" / ".mcp.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff")
    put(tmp_path / "home" / ".claude.json", json.dumps({"mcpServers": {"u": STDIO}}))
    put(tmp_path / "managed" / "managed-mcp.json", servers(m=STDIO))
    items = by_id(run(sc.scratch(tmp_path, {})))
    assert items["mcp:u"].may_change is True  # a project file ranks above user
    assert items["mcp:m"].may_change is False  # and below managed


def test_a_failed_home_file_could_change_every_scope_but_managed(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(tmp_path, {})
    (tmp_path / "home" / ".claude.json").write_bytes(b"\xff")
    put(tmp_path / "proj" / ".mcp.json", servers(p=STDIO))
    put(tmp_path / "managed" / "managed-mcp.json", servers(m=STDIO))
    settings_with(tmp_path, enableAllProjectMcpServers=True)
    items = by_id(run(ctx))
    assert items["mcp:p"].may_change is True
    assert items["mcp:m"].may_change is False


# ---------------------------------------------------------------- stability


def test_ids_and_order_are_stable_over_two_reads(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    ctx = sc.context(root)
    first = run(ctx)
    second = run(ctx)
    assert [i.model_dump() for i in first.items["mcp"]] == [
        i.model_dump() for i in second.items["mcp"]
    ]
    assert [p.model_dump() for p in first.problems] == [
        p.model_dump() for p in second.problems
    ]


def test_the_signature_follows_the_server_files(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO))
    got = run(ctx)
    before = COLLECTOR.signature(ctx, got)
    assert COLLECTOR.signature(ctx, got) == before
    put(tmp_path / "proj" / ".mcp.json", servers(a=STDIO, b=STDIO))
    assert COLLECTOR.signature(ctx, got) != before
    assert COLLECTOR.signature(ctx, None)


def test_the_collector_is_the_mcp_part_only(tmp_path: Path) -> None:
    assert COLLECTOR.name == "mcp"
    assert list(COLLECTOR.parts) == ["mcp"]
    assert set(run(sc.scratch(tmp_path, {})).items) == {"mcp"}


def test_an_unlisted_project_reads_no_project_file(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("scope-unlisted", tmp_path / "w", setup_corpus)
    put(root / "work" / "parent" / "proj" / ".mcp.json", servers(hidden=STDIO))
    got = run(sc.context(root))
    assert got.items["mcp"] == []
    put(root / "home" / ".claude.json", json.dumps({"mcpServers": {"u": STDIO}}))
    items = run(sc.context(root)).items["mcp"]
    assert [i.id for i in items] == ["mcp:u"]
    hidden = {r.scope for r in items[0].reach if not r.visible}
    assert hidden == {"project_local", "project"}


# ---------------------------------------------------------------- the entry builder


def test_the_entry_builder_never_keeps_an_unknown_key() -> None:
    entry = mcp_entry.build(
        "x",
        {
            "command": "node",
            "oauth": {"token": "KEEP-OUT-SENTINEL"},
            "extra": "KEEP-OUT",
        },
        1,
    )
    assert "KEEP-OUT" not in repr(entry)


def test_the_entry_builder_masks_every_place_a_secret_lives() -> None:
    entry = mcp_entry.build(
        "x",
        {
            "command": "run --api-key sk-ant-0001",
            "args": ["--secret=0002", "plain", "Bearer 0003"],
            "env": {"MY_TOKEN": "0004", "N": "sk-0005"},
            "url": "https://a:0006@h.test",
            "headers": {"Authorization": "Basic 0007", "Cookie": "0008"},
        },
        2,
    )
    text = repr(entry)
    for number in range(1, 9):
        assert f"000{number}" not in text

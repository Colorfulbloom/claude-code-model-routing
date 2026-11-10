"""Tests for ``agent_files``: finding agent files and parsing every front matter field.

The files are made in a temp folder. Nothing here reads the real config folder.
"""

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from agent_collect_helpers import Mini, lines

import agent_files
from setup_contract import FILE_CAP_BYTES

NOT_ROOT = os.geteuid() != 0
text = lines


@pytest.fixture
def mini(tmp_path: Path) -> Mini:
    return Mini(tmp_path)


def only(found: agent_files.Found) -> agent_files.AgentFile:
    assert len(found.files) == 1, found.files
    return found.files[0]


# ---------------------------------------------------------------- parsing


def test_a_plain_agent_parses_with_lines(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "a.md",
        text(
            "---", "name: a", "description: Does a thing", "model: haiku", "---", "Body"
        ),
    )
    got = only(mini.find(mini.config / "agents"))
    assert (got.name, got.has_description, got.code, got.gap) == (
        "a",
        True,
        None,
        False,
    )
    assert got.name_line == 2
    assert [(f.name, f.line) for f in got.fields] == [
        ("name", 2),
        ("description", 3),
        ("model", 4),
    ]
    assert got.display == "~/.claude/agents/a.md"
    assert got.rel == "a.md"


def test_hyphenated_keys_and_nested_hooks_parse(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "n.md",
        text(
            "---",
            "name: n",
            "description: Nested",
            "allowed-tools: Read, Grep",
            "hooks:",
            "  PreToolUse:",
            "    - matcher: Bash",
            "      hooks:",
            "        - type: command",
            "          command: echo hi",
            "---",
        ),
    )
    got = only(mini.find(mini.config / "agents"))
    assert got.code is None
    assert got.gap is True  # the strict reader rejects both
    assert got.strict_line is not None
    fields = {f.name: f for f in got.fields}
    assert fields["allowed-tools"].line == 4
    assert fields["hooks"].line == 5
    hooks = fields["hooks"].value
    assert hooks is not None
    assert "PreToolUse" in hooks.text
    assert "echo hi" in hooks.text


def test_known_fields_come_first_in_the_documented_order(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "o.md",
        text("---", "extra: 1", "effort: high", "name: o", "description: d", "---"),
    )
    got = only(mini.find(mini.config / "agents"))
    assert [f.name for f in got.fields] == ["name", "description", "effort", "extra"]


def test_values_of_other_types_become_text(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "t.md",
        text(
            "---",
            "name: t",
            "description: d",
            "maxTurns: 5",
            "background: true",
            "memory:",
            "skills: [a, b]",
            "---",
        ),
    )
    got = only(mini.find(mini.config / "agents"))
    fields = {f.name: f.value for f in got.fields}
    assert fields["maxTurns"] is not None
    assert fields["maxTurns"].text == "5"
    assert fields["background"] is not None
    assert fields["background"].text == "true"
    assert fields["memory"] is None
    assert fields["skills"] is not None
    assert fields["skills"].text == '["a", "b"]'


def test_quoted_and_repeated_keys(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "q.md",
        text("---", '"name": q', "description: first", "description: second", "---"),
    )
    got = only(mini.find(mini.config / "agents"))
    assert got.name == "q"
    assert got.name_line == 2
    desc = next(f for f in got.fields if f.name == "description")
    assert desc.value is not None
    assert desc.value.text == "first"  # ruamel keeps the first of a repeated key
    assert desc.line == 3


def test_a_name_that_is_a_number_is_kept_as_text(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "n.md",
        text("---", "name: 42", "description: d", "---"),
    )
    assert only(mini.find(mini.config / "agents")).name == "42"


@pytest.mark.parametrize(
    ("body", "code", "line"),
    [
        ("Just text\n", "frontmatter_invalid", 1),
        ("---\nname: x\nno closing fence\n", "frontmatter_invalid", 1),
        # ruamel notices an unclosed bracket where the block ends.
        ("---\nname: [unclosed\n---\n", "frontmatter_invalid", 3),
        ("---\n- a\n- b\n---\n", "frontmatter_invalid", 2),
        ("---\n---\n", "agent_no_name", 1),
        ("---\ndescription: d\n---\n", "agent_no_name", 1),
        ("---\nname:\ndescription: d\n---\n", "agent_no_name", 1),
        ("---\nname: [a]\ndescription: d\n---\n", "agent_no_name", 1),
        ("---\nname: true\ndescription: d\n---\n", "agent_no_name", 1),
    ],
)
def test_files_with_no_usable_name_have_a_code(
    mini: Mini, body: str, code: str, line: int
) -> None:
    mini.write(mini.config / "agents" / "bad.md", body)
    got = only(mini.find(mini.config / "agents"))
    assert (got.code, got.line, got.name) == (code, line, None)


def test_an_unclosed_bracket_in_a_value_still_gives_the_file_a_name(mini: Mini) -> None:
    # Claude Code loads this file (rule agent-file-reader-rejected, tested on 2.1.302),
    # though ruamel cannot parse it, so the values are read as raw text.
    mini.write(
        mini.config / "agents" / "probe.md",
        text(
            "---", "name: probe", "description: [Made-up agent", "model: haiku", "---"
        ),
    )
    got = only(mini.find(mini.config / "agents"))
    assert (got.code, got.name, got.gap, got.has_description) == (
        None,
        "probe",
        True,
        True,
    )
    assert (got.name_line, got.strict_line) == (2, 3)
    assert [
        (f.name, f.line, f.value.text if f.value else None) for f in got.fields
    ] == [
        ("name", 2, "probe"),
        ("description", 3, "[Made-up agent"),
        ("model", 4, "haiku"),
    ]


def test_a_value_that_stops_the_load_is_not_salvaged(mini: Mini) -> None:
    # An unterminated quote did not load in the same experiment, so the file is
    # invalid and keeps no name.
    mini.write(
        mini.config / "agents" / "q.md",
        text("---", "name: q", 'description: "never closed', "---"),
    )
    got = only(mini.find(mini.config / "agents"))
    assert (got.code, got.name) == ("frontmatter_invalid", None)


def test_a_blank_description_does_not_count(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "b.md",
        text("---", "name: b", "description: ' '", "---"),
    )
    assert only(mini.find(mini.config / "agents")).has_description is False


def test_plugin_agents_flag_the_ignored_fields_but_keep_value_and_line(
    mini: Mini,
) -> None:
    folder = mini.config / "plugins" / "cache" / "m" / "p" / "1" / "agents"
    mini.write(
        folder / "x.md",
        text(
            "---",
            "name: x",
            "description: d",
            "permissionMode: plan",
            "mcpServers:",
            "  - name: s",
            "hooks:",
            "  Stop:",
            "    - hooks: []",
            "---",
        ),
    )
    got = only(mini.find(folder, "plugin", "p"))
    assert got.ignored_fields() == ["permissionMode", "mcpServers", "hooks"]
    mode = next(f for f in got.fields if f.name == "permissionMode")
    assert mode.ignored is True
    assert mode.value is not None
    assert mode.value.text == "plan"
    assert mode.line == 4


def test_the_same_fields_on_a_user_agent_are_not_ignored(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "x.md",
        text("---", "name: x", "description: d", "permissionMode: plan", "---"),
    )
    assert only(mini.find(mini.config / "agents")).ignored_fields() == []


def test_secrets_in_fields_are_masked(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "s.md",
        text(
            "---",
            "name: s",
            "description: sk-ant-api03-FAKEAGENTDESC000001",
            "apiKey: plainsecretvalue000002",
            "mcpServers:",
            "  - name: srv",
            "    env:",
            "      API_TOKEN: tok000003",
            "initialPrompt: use https://user:pw000004@host.test/x",
            "---",
        ),
    )
    got = only(mini.find(mini.config / "agents"))
    dump = repr(got)
    for secret in (
        "FAKEAGENTDESC000001",
        "plainsecretvalue000002",
        "tok000003",
        "pw000004",
    ):
        assert secret not in dump
    fields = {f.name: f.value for f in got.fields}
    for name in ("description", "apiKey", "mcpServers", "initialPrompt"):
        value = fields[name]
        assert value is not None
        assert value.masked is True
    plain = next(f.value for f in got.fields if f.name == "name")
    assert plain is not None
    assert plain.masked is False


def test_no_body_text_is_kept(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "b.md",
        text("---", "name: b", "description: d", "---", "BODY-SENTINEL-TEXT"),
    )
    got = only(mini.find(mini.config / "agents"))
    assert "BODY-SENTINEL-TEXT" not in repr(got)


# ---------------------------------------------------------------- finding


def test_subfolders_are_searched_and_hidden_names_skipped(mini: Mini) -> None:
    root = mini.config / "agents"
    body = text("---", "name: {n}", "description: d", "---")
    mini.write(root / "top.md", body.format(n="top"))
    mini.write(root / "team" / "deep" / "inner.md", body.format(n="inner"))
    mini.write(root / ".hidden.md", body.format(n="hidden"))
    mini.write(root / ".dot" / "x.md", body.format(n="dotted"))
    mini.write(root / "notes.txt", "not an agent")
    got = mini.find(root)
    assert [f.rel for f in got.files] == ["notes.txt", "team/deep/inner.md", "top.md"]
    by_rel = {f.rel: f for f in got.files}
    assert by_rel["notes.txt"].code == "agent_not_md"
    assert by_rel["team/deep/inner.md"].name == "inner"


def test_a_missing_folder_is_no_problem(mini: Mini) -> None:
    got = mini.find(mini.config / "agents")
    assert got.files == []
    assert got.unreadable == []
    assert mini.config / "agents" in got.touched


def test_a_single_file_root_is_read(mini: Mini) -> None:
    path = mini.write(
        mini.config / "one.md", text("---", "name: one", "description: d", "---")
    )
    found = agent_files.find(mini.scope(), [str(path)], "user")
    assert only(found).name == "one"


def test_a_symlink_loop_does_not_run_forever(mini: Mini) -> None:
    root = mini.config / "agents"
    mini.write(root / "a.md", text("---", "name: a", "description: d", "---"))
    (root / "loop").symlink_to(root)
    got = mini.find(root)
    assert [f.rel for f in got.files] == ["a.md"]


def test_a_folder_link_that_leaves_the_roots_is_not_entered(mini: Mini) -> None:
    outside = mini.root / "outside"
    mini.write(outside / "evil.md", text("---", "name: evil", "description: d", "---"))
    root = mini.config / "agents"
    root.mkdir()
    (root / "linked").symlink_to(outside)
    got = mini.find(root)
    assert got.files == []
    assert [(u.reason, u.file) for u in got.unreadable] == [
        ("outside_scope", "~/.claude/agents/linked")
    ]


def test_a_file_link_that_leaves_the_roots_is_followed_and_reported(
    mini: Mini,
) -> None:
    outside = mini.root / "outside"
    target = mini.write(
        outside / "linked.md", text("---", "name: linked", "description: d", "---")
    )
    root = mini.config / "agents"
    root.mkdir()
    (root / "linked.md").symlink_to(target)
    got = only(mini.find(root))
    assert got.name == "linked"
    assert got.real_path == "linked.md"  # outside the roots: the last part only


def test_a_link_that_stays_inside_shows_its_real_path_display(mini: Mini) -> None:
    root = mini.config / "agents"
    mini.write(root / "real.md", text("---", "name: r", "description: d", "---"))
    (root / "alias.md").symlink_to(root / "real.md")
    got = {f.rel: f for f in mini.find(root).files}
    assert got["real.md"].real_path is None
    assert got["alias.md"].real_path == "~/.claude/agents/real.md"


def test_invalid_utf8_is_unreadable_not_parsed(mini: Mini) -> None:
    root = mini.config / "agents"
    mini.write(root / "bad.md", b"---\nname: \xff\xfe\n---\n")
    got = mini.find(root)
    assert got.files == []
    assert [u.reason for u in got.unreadable] == ["not_utf8"]


def test_a_file_over_the_cap_is_unreadable(mini: Mini) -> None:
    root = mini.config / "agents"
    mini.write(root / "huge.md", b"x" * (FILE_CAP_BYTES + 1))
    got = mini.find(root)
    assert got.files == []
    assert [u.reason for u in got.unreadable] == ["too_large"]


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_file_with_no_permission_is_unreadable(mini: Mini) -> None:
    root = mini.config / "agents"
    locked = mini.write(
        root / "locked.md", text("---", "name: l", "description: d", "---")
    )
    locked.chmod(0)
    try:
        got = mini.find(root)
    finally:
        locked.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert got.files == []
    assert [u.reason for u in got.unreadable] == ["permission"]


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_folder_that_will_not_list_is_unreadable(mini: Mini) -> None:
    root = mini.config / "agents"
    mini.write(root / "a.md", text("---", "name: a", "description: d", "---"))
    root.chmod(0)
    try:
        got = mini.find(root)
    finally:
        root.chmod(stat.S_IRWXU)
    assert got.files == []
    assert [u.reason for u in got.unreadable] == ["folder_unlistable"]


def test_the_item_id_forms() -> None:
    assert agent_files.agent_item_id("scout") == "agents:scout"
    assert agent_files.agent_item_id("scout", "kit") == "agents:kit:scout"

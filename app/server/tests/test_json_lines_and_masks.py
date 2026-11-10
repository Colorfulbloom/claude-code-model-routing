"""The small helpers under the hooks, MCP and masked-reader parts (m4-build.md task 8).

``json_lines`` finds lines and steps over values. ``command_mask`` hides secrets in
free text. ``plugin_inputs`` reads the plugin handoff in both shapes. ``mcp_entry`` is
covered beside the MCP collector, and these tests add what only the helpers reach.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path

import command_mask
import json_lines
import plugin_inputs
from collect_plugins import PluginComponents

# ---------------------------------------------------------------- json_lines

DOC = """{
  "a": 1,
  "hooks": {
    "Stop": [
      {"hooks": [{"type": "command"}, {"type": "http"}]},
      {"matcher": "x"}
    ],
    "Other": {"deep": [1, [2, 3]]}
  },
  "z": [10, 20]
}
"""


def test_index_lists_keys_and_array_elements_under_a_prefix() -> None:
    lines = json_lines.index(DOC, ("hooks",))
    assert lines[("hooks",)] == 3
    assert lines[("hooks", "Stop")] == 4
    assert lines[("hooks", "Stop", 0)] == 5
    assert lines[("hooks", "Stop", 0, "hooks", 1)] == 5
    assert lines[("hooks", "Stop", 1)] == 6
    assert lines[("hooks", "Other", "deep", 1, 0)] == 8
    assert ("a",) not in lines
    assert ("z", 0) not in lines


def test_index_with_no_prefix_lists_everything() -> None:
    lines = json_lines.index(DOC)
    assert lines[("a",)] == 2
    assert lines[("z",)] == 10
    assert lines[("z", 1)] == 10
    assert lines[("hooks", "Other", "deep", 1, 1)] == 8


def test_index_follows_only_objects_to_the_prefix() -> None:
    assert json_lines.index('{"a": [{"b": 1}]}', ("a", "b")) == {}
    assert json_lines.index("[1, 2]", ("a",)) == {}
    assert json_lines.index("[1, 2]") == {(0,): 1, (1,): 1}


def test_index_gives_the_last_of_a_repeated_key() -> None:
    lines = json_lines.index('{\n"a": {"x": 1},\n"a": {"y": 2}\n}', ())
    assert lines[("a",)] == 3
    assert ("a", "x") not in lines
    assert lines[("a", "y")] == 3


def test_index_never_raises_on_text_it_cannot_follow() -> None:
    assert json_lines.index("") == {}
    assert json_lines.index("{") == {}
    assert isinstance(json_lines.index('{"a": '), dict)
    assert json_lines.index("{}") == {}
    assert json_lines.index("[]") == {}


def test_index_stops_at_the_depth_cap_without_recursing_forever() -> None:
    text = '{"a": ' + "[" * 500 + "]" * 500 + "}"
    lines = json_lines.index(text)
    assert lines[("a",)] == 1
    assert len(lines) < 200


def test_cursor_skips_every_kind_of_value() -> None:
    text = '{"k": [1, {"x": "]}"}], "m": "a\\"b", "n": -1.5e2, "o": true}'
    cur = json_lines.Cursor(text)
    start = text.index("[")
    assert text[cur.skip(start) :].startswith(', "m"')
    start = text.index('"a\\"b"')
    assert text[cur.skip(start) :].startswith(', "n"')
    start = text.index("-1.5e2")
    assert text[cur.skip(start) :].startswith(', "o"')
    start = text.index("true")
    assert text[cur.skip(start) :] == "}"


def test_cursor_counts_lines_forward_and_back() -> None:
    text = "a\nb\nc\nd"
    cur = json_lines.Cursor(text)
    assert cur.line(0) == 1
    assert cur.line(4) == 3
    assert cur.line(6) == 4
    assert cur.line(2) == 2  # going back counts again from the top
    assert cur.line(2) == 2


def test_cursor_decodes_one_value_and_a_string() -> None:
    cur = json_lines.Cursor('  {"a": [1, 2]} "tail"')
    assert cur.ws(0) == 2
    assert cur.decode(2) == ({"a": [1, 2]}, 15)
    assert cur.string(16) == ("tail", 22)


# ---------------------------------------------------------------- command_mask


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("plain command --flag value", "plain command --flag value"),
        ("run --api-key abc", "run --api-key hidden"),
        ("run --api-key=abc", "run --api-key=hidden"),
        ("run -token abc x", "run -token hidden x"),
        ("API_KEY=abc run", "API_KEY=hidden run"),
        ("MAX_THINKING_TOKENS=100 run", "MAX_THINKING_TOKENS=100 run"),
        ("echo sk-ant-1234", "echo hidden"),
        ("echo 'sk-ant-1234'", "echo hidden"),
        (
            "curl -H 'Authorization: Bearer abc' x",
            "curl -H 'Authorization: Bearer hidden' x",
        ),
        ("curl -H Basic abc", "curl -H Basic hidden"),
        (
            "git clone https://u:pw@h.test/r.git",
            "git clone https://u:hidden@h.test/r.git",
        ),
        ("git clone https://tok@h.test/r.git", "git clone https://hidden@h.test/r.git"),
        ("echo eyJhbGciOiJIUzI1NiJ9.e30.sig", "echo hidden"),
        ("  keep   the   spacing  ", "  keep   the   spacing  "),
        ("", ""),
        ("--secret", "--secret"),
        ("x --secret", "x --secret"),
    ],
)
def test_mask_command(raw: str, shown: str) -> None:
    assert command_mask.mask_command(raw) == shown


def test_masked_command_says_whether_it_hid_anything() -> None:
    hid = command_mask.masked_command("run --token abc")
    assert (hid.text, hid.masked) == ("run --token hidden", True)
    kept = command_mask.masked_command("run --fast")
    assert (kept.text, kept.masked) == ("run --fast", False)


# ---------------------------------------------------------------- plugin_inputs


def test_rows_reads_the_mapping_shape_and_skips_junk() -> None:
    handoff: dict[str, object] = {
        "plugins": {
            "hooks": [
                {"plugin": "a@m", "name": "a", "path": "/p/a/hooks.json"},
                {"plugin": "b@m", "path": "/p/b/plugin.json", "inline": {"Stop": []}},
                {"plugin": 5, "path": "/x"},
                "junk",
                {"plugin": "c@m"},
            ],
            "mcp": [{"plugin": "a@m", "name": "a", "path": "/p/a/.mcp.json"}],
        }
    }
    hooks = plugin_inputs.rows(handoff, "hooks")
    assert [(r.plugin_id, r.name, r.path, r.inline) for r in hooks] == [
        ("a@m", "a", "/p/a/hooks.json", None),
        ("b@m", "b", "/p/b/plugin.json", {"Stop": []}),
    ]
    assert [r.path for r in plugin_inputs.rows(handoff, "mcp")] == ["/p/a/.mcp.json"]


def test_rows_reads_plugin_components() -> None:
    comp = PluginComponents(
        item_id="plugins:a@m",
        plugin_id="a@m",
        name="a",
        root="/p/a",
        hooks_files=["/p/a/hooks/hooks.json"],
        hooks_inline={"Stop": []},
        mcp_files=["/p/a/.mcp.json"],
        mcp_inline={"s": {}},
    )
    hooks = plugin_inputs.rows({"plugins": [comp, "junk"]}, "hooks")
    assert [(r.path, r.inline is not None) for r in hooks] == [
        ("/p/a/hooks/hooks.json", False),
        ("/p/a/.claude-plugin/plugin.json", True),
    ]
    mcp = plugin_inputs.rows({"plugins": [comp]}, "mcp")
    assert [(r.path, r.inline is not None) for r in mcp] == [
        ("/p/a/.mcp.json", False),
        ("/p/a/.claude-plugin/plugin.json", True),
    ]


@pytest.mark.parametrize("raw", [None, "text", 5, [], {}, {"hooks": "no"}])
def test_rows_gives_nothing_for_other_shapes(raw: object) -> None:
    assert plugin_inputs.rows({"plugins": raw}, "hooks") == []
    assert plugin_inputs.rows({}, "mcp") == []


def test_the_docs_event_list_is_a_json_safe_tuple() -> None:
    import collect_hooks

    assert json.dumps(list(collect_hooks.EVENTS))

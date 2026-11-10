"""The masked reader of the home Claude settings file (m4-build.md task 8).

The reader keeps three key groups and drops every other key at parse time. These tests
read the corpus cases, then prove the line with crafted files that hold sentinel values
under keys the reader must never keep: none reaches an item, a problem row, a log record
or an exception text. They also cover the moved-config-folder rule, the stat cache, the
cap, the Couldn't read states and the scanner's edge cases.
"""

import json
import logging
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import hook_mcp_helpers as hm
import setup_case_helpers as sc

import claude_json
import read_scope
from setup_contract import CLAUDE_JSON_CAP_BYTES, Collected, SetupContext

COLLECTOR = claude_json.COLLECTOR
NOT_ROOT = os.geteuid() != 0
SENTINELS = (
    "SENTINEL-ACCOUNT-0001",
    "SENTINEL-HISTORY-0002",
    "SENTINEL-OTHER-PROJECT-0003",
    "SENTINEL-PROJECT-KEY-0004",
    "SENTINEL-UNKNOWN-IN-SERVER-0005",
    "SENTINEL-NESTED-0006",
)


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read(ctx: SetupContext) -> claude_json.ClaudeJson:
    claude_json.clear_cache()
    return claude_json.read(read_scope.Scope(ctx))


def collected(ctx: SetupContext) -> Collected:
    claude_json.clear_cache()
    return COLLECTOR.read(ctx, {})


def fake_file(project: str) -> str:
    """A fake home file with sentinel values under every key the reader must drop."""
    return json.dumps(
        {
            "numStartups": 7,
            "oauthAccount": {"emailAddress": SENTINELS[0]},
            "history": [SENTINELS[1], {"nested": SENTINELS[5]}],
            "mcpServers": {
                "user-one": {
                    "command": "node",
                    "oauth": {"clientSecret": SENTINELS[4]},
                    "note": SENTINELS[4],
                }
            },
            "projects": {
                SENTINELS[3]: {"mcpServers": {"leak": {"command": SENTINELS[2]}}},
                "/some/other/place": {
                    "mcpServers": {"leak2": {"command": SENTINELS[2]}},
                    "allowedTools": [SENTINELS[2]],
                },
                project: {
                    "history": [SENTINELS[1]],
                    "lastCost": 12.5,
                    "mcpServers": {"local-one": {"command": "python3"}},
                    "enabledMcpjsonServers": ["a"],
                    # The /mcp toggle list is kept. Its opt-in twin is not.
                    "disabledMcpServers": ["off-one", 5],
                    "enabledMcpServers": [SENTINELS[2]],
                    "exampleFiles": [SENTINELS[5]],
                },
            },
            "tipsHistory": {"x": SENTINELS[0]},
        },
        indent=2,
    )


# ---------------------------------------------------------------- the corpus


@pytest.mark.parametrize("case", sc.CASES)
def test_the_readers_problems_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = collected(sc.context(root))
    made, wanted = sc.compare_problems(got, case, ("mcp",))
    # The reader owns the rows that name the home file. The MCP collector owns the rest.
    home = [w for w in wanted if (w["file"] or "").endswith(".claude.json")]
    assert made == home


def test_a_missing_file_is_absent_and_says_nothing(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    got = collected(sc.context(root))
    assert got.problems == []
    assert got.unreadable == []
    assert got.items == {}
    state = got.handoff[claude_json.HANDOFF_KEY]
    assert isinstance(state, claude_json.ClaudeJson)
    assert state.state == "absent"
    assert state.user == ()
    assert state.local == ()


def test_the_typical_file_gives_user_and_local_servers_with_lines(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("typical", tmp_path / "w", setup_corpus)
    got = read(sc.context(root))
    assert got.state == "ok"
    assert got.display == "~/.claude.json"
    assert [(e.name, e.line) for e in got.user] == [("notes", 6)]
    assert [(e.name, e.line) for e in got.local] == [("scratch", 16)]
    assert got.user[0].facts.transport == "sse"
    assert got.user[0].facts.headers["X-Api-Key"].text == "hidden"
    local = got.local[0].facts
    assert [a.text for a in local.args] == ["scratch.js", "--password=hidden"]
    assert local.env["SCRATCH_TOKEN"].text == "hidden"


def test_the_collector_has_no_part_and_hands_the_state_on(
    tmp_path: Path, setup_corpus: Path
) -> None:
    assert COLLECTOR.name == "claude_json"
    assert list(COLLECTOR.parts) == []
    root = sc.world("typical", tmp_path / "w", setup_corpus)
    got = collected(sc.context(root))
    assert got.items == {}
    assert isinstance(got.handoff["claude_json"], claude_json.ClaudeJson)
    assert [Path(p).name for p in got.touched] == [".claude.json"]


# ---------------------------------------------------------------- bad files


def test_bad_json_is_json_invalid_with_a_line_and_never_the_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(
        tmp_path / "home" / ".claude.json",
        '{\n  "oauth": "SENTINEL-BAD-0001"\n  "x": "SENTINEL-BAD-0002"\n}\n',
    )
    with caplog.at_level(logging.DEBUG):
        got = collected(ctx)
    assert [(r.code, r.line, r.file) for r in got.problems] == [
        ("json_invalid", 3, "~/.claude.json")
    ]
    assert got.problems[0].group == "wont_load"
    assert got.problems[0].fix.kind == "copy_path"
    text = hm.everything({"claude_json": got})
    assert "SENTINEL-BAD" not in text
    assert "SENTINEL-BAD" not in caplog.text


def test_a_top_level_that_is_not_an_object_is_not_object(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    for text in ("[1, 2]", "5", '"s"', "null", "  \n[]"):
        put(tmp_path / "home" / ".claude.json", text)
        got = collected(ctx)
        assert [(r.code, r.line) for r in got.problems] == [("not_object", 1)], text


def test_an_empty_file_is_json_invalid(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(tmp_path / "home" / ".claude.json", "")
    assert [r.code for r in collected(ctx).problems] == ["json_invalid"]


def test_a_project_entry_that_is_not_an_object_is_not_object_for_that_entry(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("broken-claude-json-entry", tmp_path / "w", setup_corpus)
    got = read(sc.context(root))
    assert got.state == "ok"
    assert got.entry_line == 6
    assert [e.name for e in got.user] == ["notes"]
    assert got.local == ()
    rows = claude_json.problems_of(got)
    assert [(r.code, r.line, r.params) for r in rows] == [
        ("not_object", 6, {"key": "projects"})
    ]


def test_mcp_servers_that_is_not_an_object_is_reported_at_its_line(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(tmp_path, {})
    project = str(ctx.project_dir)
    put(
        tmp_path / "home" / ".claude.json",
        '{\n  "mcpServers": [],\n  "projects": {\n    "'
        + project
        + '": {\n      "mcpServers": "no"\n    }\n  }\n}\n',
    )
    got = read(ctx)
    assert (got.user_bad_line, got.local_bad_line) == (2, 5)
    rows = claude_json.problems_of(got)
    assert [(r.code, r.line, r.params["key"]) for r in rows] == [
        ("not_object", 2, "mcpServers"),
        ("not_object", 5, "projects.mcpServers"),
    ]


def test_a_projects_key_that_is_not_an_object_keeps_the_user_servers(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps({"projects": [1], "mcpServers": {"u": {"command": "x"}}}),
    )
    got = read(ctx)
    assert [e.name for e in got.user] == ["u"]
    assert got.entry_line is None


# ---------------------------------------------------------------- the three key groups


def test_no_value_of_an_unwanted_key_reaches_any_answer(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(tmp_path / "home" / ".claude.json", fake_file(str(ctx.project_dir)))
    with caplog.at_level(logging.DEBUG):
        answers = hm.chain(ctx)
    state = answers["claude_json"].handoff["claude_json"]
    assert isinstance(state, claude_json.ClaudeJson)
    assert [e.name for e in state.user] == ["user-one"]
    assert [e.name for e in state.local] == ["local-one"]
    assert state.approvals.enabled == ("a",)
    assert state.approvals.toggled_off == ("off-one",)
    blob = hm.everything(answers) + repr(state) + caplog.text
    for sentinel in SENTINELS:
        assert sentinel not in blob, sentinel
    # The server entry's unknown keys are dropped by the entry builder.
    assert "clientSecret" not in blob


def test_the_corpus_never_list_is_absent_from_every_answer(
    tmp_path: Path, setup_corpus: Path, caplog: pytest.LogCaptureFixture
) -> None:
    for case in ("typical", "complex"):
        root = sc.world(case, tmp_path / case, setup_corpus)
        with caplog.at_level(logging.DEBUG):
            answers = hm.chain(sc.context(root))
        blob = hm.everything(answers) + caplog.text
        for entry in hm.never():
            assert entry["value"] not in blob, (case, entry["kind"])


def test_a_parse_error_text_and_an_exception_carry_no_value(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(
        tmp_path / "home" / ".claude.json",
        '{"oauth": "SENTINEL-ERR-0001", "mcpServers": {"a": }}',
    )
    got = read(ctx)
    assert got.state == "json_invalid"
    assert "SENTINEL-ERR" not in repr(got)


def test_only_the_listed_project_entry_is_kept(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    other = str(tmp_path / "somewhere-else")
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps({"projects": {other: {"mcpServers": {"nope": {"command": "x"}}}}}),
    )
    assert read(ctx).local == ()


def test_an_unlisted_project_reads_user_servers_only(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    unlisted = SetupContext(
        project_key="x",
        config_dir=ctx.config_dir,
        home=ctx.home,
        project_dir=None,
        managed_dir=ctx.managed_dir,
    )
    put(tmp_path / "home" / ".claude.json", fake_file(str(ctx.project_dir)))
    got = read(unlisted)
    assert [e.name for e in got.user] == ["user-one"]
    assert got.local == ()
    assert got.approvals == claude_json.Approvals()


def test_a_symlinked_project_path_matches_by_either_spelling(tmp_path: Path) -> None:
    real = tmp_path / "real-proj"
    real.mkdir()
    link = tmp_path / "link-proj"
    link.symlink_to(real)
    config = tmp_path / "home" / ".claude"
    config.mkdir(parents=True)
    ctx = SetupContext(
        project_key="p",
        config_dir=config.resolve(),
        home=(tmp_path / "home").resolve(),
        project_dir=link,
        managed_dir=None,
    )
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {"projects": {str(real.resolve()): {"mcpServers": {"l": {"command": "x"}}}}}
        ),
    )
    assert [e.name for e in read(ctx).local] == ["l"]


def test_a_repeated_name_or_project_key_keeps_the_last(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    project = json.dumps(str(ctx.project_dir))
    put(
        tmp_path / "home" / ".claude.json",
        '{"mcpServers": {"a": {"command": "first"}, "a": {"command": "second"}},'
        f'"projects": {{{project}: {{"mcpServers": {{"x": {{"command": "one"}}}}}},'
        f'{project}: {{"mcpServers": {{"y": {{"command": "two"}}}}}}}}}}',
    )
    got = read(ctx)
    assert [e.facts.command.text for e in got.user if e.facts.command] == ["second"]
    assert [e.name for e in got.local] == ["y"]


def test_the_scanner_steps_over_tricky_values(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    tricky = (
        '{"junk": {"a": "}{][\\"\\\\", "b": [1, [2, {"c": "]"}], "x}"], "d": -1.5e3, '
        '"e": true, "f": null},\r\n'
        '"mcp\\u0053ervers": {"esc\\u00e9": {"command": "x"}},\r\n'
        '"more": ["{", "}"], "tail": 5}'
    )
    put(tmp_path / "home" / ".claude.json", tricky)
    got = read(ctx)
    assert got.state == "ok"
    assert [(e.name, e.line) for e in got.user] == [("escé", 2)]


def test_lines_count_crlf_files_the_way_json_does(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    body = '{\r\n"a": 1,\r\n"mcpServers": {\r\n"s": {"command": "x"}\r\n}\r\n}\r\n'
    (tmp_path / "home" / ".claude.json").write_bytes(body.encode())
    assert [(e.name, e.line) for e in read(ctx).user] == [("s", 4)]


def test_unusual_servers_are_still_masked_entries(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps({"mcpServers": {"bad": 5, "ok": {"command": "x"}, "e": {}}}),
    )
    got = read(ctx)
    assert {e.name: e.why_bad for e in got.user} == {
        "bad": "not_object",
        "ok": None,
        "e": "no_command_or_url",
    }


def test_approval_keys_of_the_wrong_type_are_ignored(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {
                "projects": {
                    str(ctx.project_dir): {
                        "enabledMcpjsonServers": "a",
                        "disabledMcpjsonServers": {"b": 1},
                        "disabledMcpServers": "all",
                        "enableAllProjectMcpServers": "yes",
                    }
                }
            }
        ),
    )
    assert read(ctx).approvals == claude_json.Approvals()


# ---------------------------------------------------------------- which file


def moved_config(tmp_path: Path) -> SetupContext:
    """A config folder that is not ``<home>/.claude``, as ``CLAUDE_CONFIG_DIR`` sets."""
    root = tmp_path.resolve()
    (root / "elsewhere").mkdir()
    (root / "home").mkdir()
    (root / "proj").mkdir()
    return SetupContext(
        project_key="p",
        config_dir=root / "elsewhere",
        home=root / "home",
        project_dir=root / "proj",
        managed_dir=None,
    )


def test_a_moved_config_folder_reads_only_its_own_copy(tmp_path: Path) -> None:
    ctx = moved_config(tmp_path)
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps({"mcpServers": {"from-home": {"command": "x"}}}),
    )
    put(
        tmp_path / "elsewhere" / ".claude.json",
        json.dumps({"mcpServers": {"from-config": {"command": "x"}}}),
    )
    got = read(ctx)
    assert [e.name for e in got.user] == ["from-config"]
    assert got.display == "~/elsewhere/.claude.json"


def test_a_moved_config_folder_never_opens_the_home_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = moved_config(tmp_path)
    home_file = put(tmp_path / "home" / ".claude.json", '{"mcpServers": {}}')
    seen: list[str] = []
    real_open = os.open

    def spy(path: str | bytes | os.PathLike[str], *args: int, **kwargs: int) -> int:
        seen.append(os.fsdecode(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    got = collected(ctx)
    assert str(home_file.resolve()) not in [str(Path(p).resolve()) for p in seen]
    assert got.problems == []
    state = got.handoff["claude_json"]
    assert isinstance(state, claude_json.ClaudeJson)
    assert state.state == "absent"


def test_the_default_config_folder_reads_the_home_file(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(tmp_path / "home" / ".claude.json", json.dumps({"mcpServers": {"h": {}}}))
    assert [e.name for e in read(ctx).user] == ["h"]
    assert read(ctx).display == "~/.claude.json"


# ---------------------------------------------------------------- the stat cache


def test_a_matching_signature_does_not_parse_again(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    put(tmp_path / "home" / ".claude.json", fake_file(str(ctx.project_dir)))
    claude_json.clear_cache()
    scope = read_scope.Scope(ctx)
    before = claude_json.STATS["parses"]
    first = claude_json.read(scope)
    assert claude_json.STATS["parses"] == before + 1
    second = claude_json.read(scope)
    third = claude_json.read(read_scope.Scope(ctx))
    assert claude_json.STATS["parses"] == before + 1
    assert second is first
    assert third is first


def test_a_changed_signature_parses_again(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    target = put(
        tmp_path / "home" / ".claude.json",
        json.dumps({"mcpServers": {"one": {"command": "x"}}}),
    )
    claude_json.clear_cache()
    scope = read_scope.Scope(ctx)
    assert [e.name for e in claude_json.read(scope).user] == ["one"]
    count = claude_json.STATS["parses"]
    # A longer file changes the size.
    put(target, json.dumps({"mcpServers": {"one": {"command": "x"}, "two": {}}}))
    assert [e.name for e in claude_json.read(scope).user] == ["one", "two"]
    assert claude_json.STATS["parses"] == count + 1
    # The same size with a new modification time changes the signature too.
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    claude_json.read(scope)
    assert claude_json.STATS["parses"] == count + 2


def test_a_file_that_appears_or_vanishes_changes_the_answer(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    scope = read_scope.Scope(ctx)
    claude_json.clear_cache()
    assert claude_json.read(scope).state == "absent"
    target = put(tmp_path / "home" / ".claude.json", '{"mcpServers": {"a": {}}}')
    assert claude_json.read(scope).state == "ok"
    target.unlink()
    assert claude_json.read(scope).state == "absent"


def test_the_cache_is_per_project(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    other = tmp_path / "other-proj"
    other.mkdir()
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {
                "projects": {
                    str(ctx.project_dir): {"mcpServers": {"mine": {"command": "x"}}},
                    str(other.resolve()): {"mcpServers": {"theirs": {"command": "x"}}},
                }
            }
        ),
    )
    claude_json.clear_cache()
    mine = claude_json.read(read_scope.Scope(ctx))
    ctx_other = SetupContext(
        project_key="o",
        config_dir=ctx.config_dir,
        home=ctx.home,
        project_dir=other.resolve(),
        managed_dir=None,
    )
    theirs = claude_json.read(read_scope.Scope(ctx_other))
    assert [e.name for e in mine.local] == ["mine"]
    assert [e.name for e in theirs.local] == ["theirs"]


def test_the_cache_is_bounded(tmp_path: Path) -> None:
    claude_json.clear_cache()
    for number in range(claude_json.CACHE_MAX + 5):
        root = tmp_path / f"w{number}"
        ctx = sc.scratch(root, {})
        put(root / "home" / ".claude.json", "{}")
        claude_json.read(read_scope.Scope(ctx))
    assert claude_json.cache_size() == claude_json.CACHE_MAX


def test_the_collector_signature_follows_the_file(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    target = put(tmp_path / "home" / ".claude.json", "{}")
    got = collected(ctx)
    before = COLLECTOR.signature(ctx, got)
    assert COLLECTOR.signature(ctx, None) == before
    put(target, '{"mcpServers": {}}')
    assert COLLECTOR.signature(ctx, got) != before


# ---------------------------------------------------------------- Couldn't read


def test_a_file_that_is_not_utf8_is_couldnt_read(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    (tmp_path / "home" / ".claude.json").write_bytes(b'{"mcpServers": \xff}')
    got = collected(ctx)
    assert [(u.reason, u.part, u.scope, u.file) for u in got.unreadable] == [
        ("not_utf8", "mcp", "user", "~/.claude.json")
    ]
    assert got.problems == []
    assert got.unreadable[0].full_path == str(
        tmp_path.resolve() / "home" / ".claude.json"
    )


def test_a_file_over_32_mib_is_couldnt_read_too_large(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    sc.bc.make_unreadable(root, "claude_json_too_large")
    got = collected(sc.context(root))
    assert [(u.reason, u.part) for u in got.unreadable] == [("too_large", "mcp")]
    assert CLAUDE_JSON_CAP_BYTES == 32 * 1024 * 1024
    state = got.handoff["claude_json"]
    assert isinstance(state, claude_json.ClaudeJson)
    assert state.state == "unreadable"


def test_a_file_at_the_cap_still_reads(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    head = '{"mcpServers": {"a": {"command": "x"}}}'
    target = tmp_path / "home" / ".claude.json"
    target.write_text(
        head + " " * (CLAUDE_JSON_CAP_BYTES - len(head)), encoding="utf-8"
    )
    assert target.stat().st_size == CLAUDE_JSON_CAP_BYTES
    assert [e.name for e in read(ctx).user] == ["a"]


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_file_at_mode_000_is_couldnt_read(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    target = put(tmp_path / "home" / ".claude.json", "{}")
    target.chmod(0)
    try:
        got = collected(ctx)
    finally:
        target.chmod(0o644)
    assert [(u.reason, u.part) for u in got.unreadable] == [("permission", "mcp")]


def test_a_big_file_with_many_other_keys_reads_and_keeps_three_groups(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(tmp_path, {})
    project = str(ctx.project_dir)
    others = {
        f"/work/p{n}": {
            "history": [f"SENTINEL-BULK-{n}-{i}" for i in range(20)],
            "mcpServers": {f"s{n}": {"command": f"SENTINEL-BULK-CMD-{n}"}},
        }
        for n in range(4000)
    }
    others[project] = {"mcpServers": {"mine": {"command": "x"}}}
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps({"projects": others, "mcpServers": {"u": {"command": "x"}}}),
    )
    assert (tmp_path / "home" / ".claude.json").stat().st_size > 2_000_000
    got = read(ctx)
    assert [e.name for e in got.user] == ["u"]
    assert [e.name for e in got.local] == ["mine"]
    assert "SENTINEL-BULK" not in repr(got)

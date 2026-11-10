"""Model check reads agent files as the Agents part does (m4-build.md item 3).

``model_check.resolve_entries`` finds and reads the project and user agent files
through ``agent_files`` and ``read_scope``, not through the old collector's plain
``open``. So the 1 MiB cap, strict UTF-8 and the outside-scope refusal hold for both,
and a file the Agents part leaves out of what runs is not a file the Model check says
runs. The decoy test holds the two to the same answer.
"""

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from agent_collect_helpers import Mini, lines

import agent_files
import agent_setup
import collect
import collect_agents
import model_catalog
import model_check
from models import ModelCheckRow, SetupScope
from setup_contract import FILE_CAP_BYTES, Collected
from usage import Row

CATALOG = model_catalog.load_catalog()


@pytest.fixture
def mini(tmp_path: Path) -> Mini:
    return Mini(tmp_path)


def agent_text(name: str, *extra: str) -> str:
    return lines("---", f"name: {name}", "description: d", *extra, "---", "Body.")


def entries_of(mini: Mini) -> list[Row]:
    return model_check.resolve_entries(
        claude_dir=mini.config,
        project_dir=mini.project,
        managed_dir=None,
        shell_env={},
    )


def agent_entries(entries: list[Row]) -> list[Row]:
    return [e for e in entries if e.get("key") == "agentFile"]


def row_for(entries: list[Row], name: str) -> ModelCheckRow:
    """The Model check row of an agent type that ran once."""
    run: Row = {"run_id": "r1", "model": "opus", "effort": None}
    check = model_check.build_model_check_from_runs(
        entries=entries, runs_by_agent={name: [run]}, catalog=CATALOG
    )
    return next(r for r in check.rows if r.agent == name)


def agents_part(mini: Mini) -> Collected:
    return collect_agents.COLLECTOR.read(mini.ctx, {})


# ---------------------------------------------------------------- the decoy


def test_a_symlinked_agents_folder_out_of_the_roots_runs_in_neither(
    mini: Mini,
) -> None:
    outside = mini.root / "outside" / "agents"
    mini.write(outside / "decoy.md", agent_text("decoy", "model: opus"))
    (mini.project / ".claude").mkdir()
    (mini.project / ".claude" / "agents").symlink_to(outside)
    # A real agent in the user folder keeps both reads from being empty.
    mini.write(mini.config / "agents" / "real.md", agent_text("real", "model: opus"))

    got = agents_part(mini)
    assert [i.name for i in got.items["agents"]] == ["real"]
    assert [u.reason for u in got.unreadable] == ["outside_scope"]

    entries = entries_of(mini)
    shown = [str(e.get("file")) for e in agent_entries(entries)]
    assert shown == ["~/.claude/agents/real.md"]
    assert not any("decoy" in str(v) for e in entries for v in e.values())
    assert "decoy" not in agent_setup.from_entries(entries).files
    claimed = row_for(entries, "decoy")
    assert claimed.status is None
    assert claimed.reason_code == "no_agent_file"
    assert row_for(entries, "real").status is not None


def test_an_outside_agents_folder_alone_leaves_no_agent_entry(mini: Mini) -> None:
    outside = mini.root / "outside" / "agents"
    mini.write(outside / "decoy.md", agent_text("decoy", "model: opus"))
    (mini.project / ".claude").mkdir()
    (mini.project / ".claude" / "agents").symlink_to(outside)
    assert agents_part(mini).items["agents"] == []
    assert agent_entries(entries_of(mini)) == []


# ---------------------------------------------------------------- cap and UTF-8


def _big() -> bytes:
    pad = "x" * (FILE_CAP_BYTES + 1)
    return agent_text("odd", "model: opus", f"note: {pad}").encode()


def _bad_utf8() -> bytes:
    return b"---\nname: odd\ndescription: d\nmodel: opus\n---\nBody \xff\xfe\n"


@pytest.mark.parametrize(
    ("content", "reason"),
    [(_big, "too_large"), (_bad_utf8, "not_utf8")],
    ids=["over the cap", "bad utf-8"],
)
def test_a_file_the_scope_refuses_is_left_out_of_both(
    mini: Mini, content: Callable[[], bytes], reason: str
) -> None:
    mini.write(mini.project / ".claude" / "agents" / "odd.md", content())
    mini.write(mini.project / ".claude" / "agents" / "ok.md", agent_text("ok"))

    got = agents_part(mini)
    assert [i.name for i in got.items["agents"]] == ["ok"]
    assert [u.reason for u in got.unreadable] == [reason]

    entries = entries_of(mini)
    assert [e["file"] for e in agent_entries(entries)] == [".claude/agents/ok.md"]
    assert not any("odd" in str(e.get("file")) for e in entries)
    assert row_for(entries, "odd").status is None
    assert "odd" not in agent_setup.from_entries(entries).files


def test_a_file_at_the_cap_is_read_by_both(mini: Mini) -> None:
    head = agent_text("edge", "model: opus")
    room = FILE_CAP_BYTES - len(head.encode())
    text = head + ("x" * 79 + "\n") * (room // 80)  # body lines, padded up to the cap
    assert FILE_CAP_BYTES - 80 < len(text.encode()) <= FILE_CAP_BYTES
    mini.write(mini.project / ".claude" / "agents" / "edge.md", text)
    assert [i.name for i in agents_part(mini).items["agents"]] == ["edge"]
    assert [e["file"] for e in agent_entries(entries_of(mini))] == [
        ".claude/agents/edge.md"
    ]


# ---------------------------------------------------------------- same records


def test_the_records_match_the_old_collector_on_a_plain_tree(mini: Mini) -> None:
    for where, name in (
        (mini.project / ".claude" / "agents" / "b.md", "b"),
        (mini.project / ".claude" / "agents" / "a" / "deep.md", "deep"),
        (mini.project / ".claude" / "agents" / "z.md", "z"),
        (mini.config / "agents" / "u.md", "u"),
    ):
        mini.write(where, agent_text(name, "model: opus", "effort: high"))
    # A file the strict reader rejects keeps its errors and its line.
    mini.write(
        mini.project / ".claude" / "agents" / "bad.md",
        lines("---", "name: bad", "tools: [a, b", "---"),
    )
    mini.write(mini.project / ".claude" / "agents" / ".hidden.md", agent_text("h"))
    roots: list[tuple[SetupScope, str]] = [
        ("project", str(mini.project / ".claude" / "agents")),
        ("user", str(mini.config / "agents")),
    ]
    new = agent_files.find_records(mini.scope(), roots)
    old = collect.collect_agents(str(mini.config), str(mini.project))
    assert [r["path"] for r in new] == [r["path"] for r in old]
    assert new == old

"""The Model check equals the old pin check on the four Live scenarios.

Each ``live_flow`` scenario is built with ``flow_build``, ingested into a temp store,
and the timeline is built at the scenario clock with the model check from
``model_check``. Every row is compared with the pin check the old dashboard recorded
in ``app/fixtures/oracle/live/<scenario>/pincheck.json``. Unit cases cover each
status mapping.
"""

import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import ingest
import model_catalog
import model_check
import prices
import store
import timeline
import usage_query
from models import ModelCheck, ModelCheckRow, Timeline, TimelineRun
from store_paths import StoreLayout
from usage import Row

ORACLE = Path(__file__).resolve().parents[2] / "fixtures" / "oracle" / "live"
PROJECT = "tidewater-reporting"
SCENARIOS = ("busy", "many", "unlinked", "empty")
CATALOG = model_catalog.load_catalog()
# The old state words, as the status the row now carries.
OLD_STATE_STATUS = {"matches_lowered": "lowered", "matches": "in_effect"}


def _load(name: str) -> Any:
    return json.loads((ORACLE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def stores(
    flow_build: Callable[[str], Path], tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Callable[[str], sqlite3.Connection]]:
    """Ingest each scenario once into its own temp store."""
    opened: dict[str, sqlite3.Connection] = {}

    def get(scenario: str) -> sqlite3.Connection:
        if scenario not in opened:
            base = tmp_path_factory.mktemp(f"model-check-{scenario}")
            conn = store.open_writer(StoreLayout(base / "bartab"))
            store.migrate(conn)
            ingest.Ingestor(conn, flow_build(scenario) / "config").run_pass(
                ingest.PassScope("full")
            )
            conn.execute("UPDATE sessions SET project_key = ?", (PROJECT,))
            opened[scenario] = conn
        return opened[scenario]

    yield get
    for conn in opened.values():
        conn.close()


def _entries(build: Path) -> list[Row]:
    session = json.loads((build / "session.json").read_text(encoding="utf-8"))
    return model_check.resolve_entries(
        claude_dir=build / "config",
        project_dir=build / "projects" / PROJECT,
        managed_dir=build / "managed",
        shell_env=session.get("shell_env") or {},
    )


def _timeline(
    conn: sqlite3.Connection, build: Path, scenario: str
) -> tuple[Timeline, list[Row]]:
    manifest = _load("manifest.json")["scenarios"][scenario]
    entries = _entries(build)

    def check(_key: str, runs: Sequence[TimelineRun]) -> ModelCheck:
        return model_check.build_model_check(
            entries=entries, runs=runs, catalog=CATALOG
        )

    built = timeline.build_timeline(
        conn,
        session_id=manifest["session"],
        project_key=PROJECT,
        folder_keys={
            str(row[0]): PROJECT
            for row in conn.execute("SELECT DISTINCT folder FROM sessions")
        },
        now=datetime.fromisoformat(manifest["clock"]).astimezone(UTC),
        pricer=usage_query.Pricer(prices.load_prices()),
        catalog=CATALOG,
        model_check_fn=check,
        prices=timeline.bundled_prices(datetime(2026, 10, 30, tzinfo=UTC).date()),
    )
    assert built is not None
    return built, entries


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_each_row_equals_the_recorded_pin_check(
    scenario: str,
    stores: Callable[[str], sqlite3.Connection],
    flow_build: Callable[[str], Path],
) -> None:
    old = _load(f"{scenario}/pincheck.json")["agents"]
    built, _entries_used = _timeline(stores(scenario), flow_build(scenario), scenario)
    rows = {
        ("@main" if r.agent is None else r.agent): r for r in built.model_check.rows
    }
    # One row per agent type that ran, the main session included
    assert set(rows) == set(old)
    for name, was in old.items():
        row = rows[name]
        if was is None:
            assert row.status is None, name
            assert row.reason_code == "no_agent_file", name
            assert (row.set.model, row.set.effort) == (None, None), name
            assert row.mismatched_runs == 0, name
            continue
        assert row.status == OLD_STATE_STATUS[was["state"]], name
        assert row.runs == was["total_runs"], name
        assert row.mismatched_runs == was["mismatched_runs"], name
        for kind in ("model", "effort"):
            pinned = was[kind]["pinned"]
            shown = getattr(row.set, kind)
            assert shown is not None, (name, kind)
            assert shown.value == pinned["value"], (name, kind)
            assert shown.line == pinned["line"], (name, kind)
            # The old file is relative to the build root, the new one to the
            # project or to the Claude folder.
            assert shown.file is not None
            assert pinned["file"].endswith(shown.file.removeprefix("~/")), (name, kind)
            assert not shown.file.startswith("/"), (name, kind)
        assert row.ran.model == was["model"]["ran"][0], name
        assert row.ran.effort == was["effort"]["ran"][0], name
        assert row.ran.mixed is False, name


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_only_lowered_row_is_the_main_sessions_effort(
    scenario: str,
    stores: Callable[[str], sqlite3.Connection],
    flow_build: Callable[[str], Path],
) -> None:
    built, _entries_used = _timeline(stores(scenario), flow_build(scenario), scenario)
    old = _load(f"{scenario}/pincheck.json")["agents"]["@main"]
    lowered = [r for r in built.model_check.rows if r.status == "lowered"]
    assert [r.agent for r in lowered] == [None]
    row = lowered[0]
    assert row.reason_code == "lowered_by_cap"
    cap = old["effort"]["cap"]
    assert row.params == {
        "setting": "effort",
        "settings": "effort",
        "value": "xhigh",
        "expected": "high",
        "cap_key": "maxEffortLevel",
        "cap_value": "high",
        "cap_model": "claude-opus-5-5",
        "cap_file": ".claude/settings.json",
        "cap_line": "3",
    }
    assert cap["file"].endswith(row.params["cap_file"])
    assert row.set.model is not None
    assert (row.set.model.value, row.set.model.scope) == ("claude-opus-5-5", "user")
    assert row.set.model.file == "~/config/settings.json"
    assert row.set.effort is not None
    assert row.set.effort.file == ".claude/settings.local.json"
    assert row.set.effort.scope == "env"
    assert built.model_check.in_effect_count == 0
    # The main session leads, the agents without a file follow by name
    names = [r.agent for r in built.model_check.rows]
    assert names == sorted(names, key=lambda n: (n is not None, n or ""))


def test_a_busy_run_has_no_judge_file(
    stores: Callable[[str], sqlite3.Connection],
    flow_build: Callable[[str], Path],
) -> None:
    built, entries = _timeline(stores("busy"), flow_build("busy"), "busy")
    judge = next(r for r in built.model_check.rows if r.agent == "judge")
    assert judge.reason_code == "no_agent_file"
    assert not any(e.get("agent") == "judge" for e in entries)


# ---------------------------------------------------------------- unit cases


def _run(
    agent: str | None,
    model: str | None = None,
    effort: str | None = None,
    n: int = 1,
) -> TimelineRun:
    return TimelineRun.model_construct(
        run_id=f"{agent or 'main'}-{n}", agent=agent, model=model, effort=effort
    )


def _entry(**fields: object) -> Row:
    base: Row = {
        "key": "model",
        "value": None,
        "status": "in_effect",
        "layer": "agent",
        "file": ".claude/agents/judge.md",
        "scope": "agent",
        "agent": "judge",
        "line": 4,
    }
    return base | fields


def _agent_file(name: str = "judge") -> Row:
    return _entry(key="agentFile", agent=name, line=1)


def _check(entries: list[Row], runs: Sequence[TimelineRun]) -> ModelCheck:
    return model_check.build_model_check(entries=entries, runs=runs, catalog=CATALOG)


def _one(entries: list[Row], runs: Sequence[TimelineRun]) -> ModelCheckRow:
    rows = _check(entries, runs).rows
    assert len(rows) == 1
    return rows[0]


def test_in_effect_when_the_runs_match_the_file() -> None:
    entries = [
        _agent_file(),
        _entry(value="sonnet"),
        _entry(key="effort", value="high", line=5),
    ]
    runs = [_run("judge", "claude-sonnet-5-5", "high")] * 2
    row = _one(entries, runs)
    assert (row.status, row.reason_code) == ("in_effect", "in_effect")
    assert row.params == {
        "setting": "model",
        "settings": "model,effort",
        "value": "sonnet",
    }
    assert row.set.model is not None
    assert (row.set.model.file, row.set.model.line, row.set.model.scope) == (
        ".claude/agents/judge.md",
        4,
        "agent",
    )
    assert (row.runs, row.mismatched_runs) == (2, 0)
    assert _check(entries, runs).in_effect_count == 1


def test_default_status_comes_from_the_pin() -> None:
    entries = [
        _entry(
            scope="main",
            agent=None,
            layer="default",
            status="default",
            value="claude-opus-5-5",
            file="default",
            line=None,
        )
    ]
    row = _one(entries, [_run(None, "claude-opus-5-5", None)])
    assert (row.status, row.reason_code) == ("default", "default")


def test_a_default_with_no_value_sets_nothing_on_that_side() -> None:
    """The resolver's default has the value None when no file sets it.

    The row shows no value for that side, never the string "None".
    """
    entries = [
        _entry(
            key=key,
            scope="main",
            agent=None,
            layer="default",
            status="default",
            value=None,
            file="default",
            line=None,
        )
        for key in ("model", "effortLevel")
    ]
    row = _one(entries, [_run(None, "claude-opus-5-5", "high")])
    assert (row.set.model, row.set.effort) == (None, None)
    assert row.status is not None  # the runs are still judged


def test_lowered_by_a_cap_names_the_cap() -> None:
    entries = [
        _entry(
            scope="main",
            agent=None,
            key="effortLevel",
            layer="env",
            status="lowered",
            value="xhigh",
            becomes="high",
            model="claude-opus-5-5",
        ),
        _entry(
            scope="main",
            agent=None,
            key="maxEffortLevel",
            layer="project",
            value="high",
            model="claude-opus-5-5",
            file=".claude/settings.json",
            line=3,
        ),
    ]
    row = _one(entries, [_run(None, None, "high")])
    assert (row.status, row.reason_code) == ("lowered", "lowered_by_cap")
    assert row.params["cap_file"] == ".claude/settings.json"
    assert row.params["cap_line"] == "3"
    assert row.set.effort is not None
    assert row.set.effort.scope == "env"


def test_lowered_and_the_runs_used_the_pin_anyway() -> None:
    entries = [
        _entry(
            scope="main",
            agent=None,
            key="effortLevel",
            layer="env",
            status="lowered",
            value="xhigh",
            becomes="high",
            model="claude-opus-5-5",
        )
    ]
    row = _one(entries, [_run(None, None, "xhigh")])
    assert (row.status, row.reason_code) == ("lowered", "lowered_ran_at_pin")
    assert "cap_file" not in row.params
    assert row.mismatched_runs == 0


def test_a_pin_that_lost_is_overridden_and_names_the_winner() -> None:
    entries = [
        _agent_file(),
        _entry(value="opus", status="overridden"),
        _entry(
            value="haiku",
            layer="env",
            file=".claude/settings.json",
            line=9,
            via="CLAUDE_CODE_SUBAGENT_MODEL",
        ),
    ]
    row = _one(entries, [_run("judge", "claude-opus-5-5")])
    assert (row.status, row.reason_code) == ("overridden", "pin_overridden")
    assert row.params["by_file"] == ".claude/settings.json"
    assert row.params["by_line"] == "9"
    assert row.params["by_via"] == "CLAUDE_CODE_SUBAGENT_MODEL"
    assert row.params["expected"] == "haiku"


@pytest.mark.parametrize(
    ("pin_status", "status", "code"),
    [("ignored", "ignored", "pin_ignored"), ("invalid", "invalid", "pin_invalid")],
)
def test_ignored_and_invalid_pins_keep_their_resolver_word(
    pin_status: str, status: str, code: str
) -> None:
    entries = [
        _agent_file(),
        _entry(key="effort", value="xhigh", status=pin_status, line=5),
    ]
    row = _one(entries, [_run("judge", None, "high")])
    assert (row.status, row.reason_code) == (status, code)
    assert row.params["value"] == "xhigh"


def test_an_unknown_expected_value_reads_unknown() -> None:
    entries = [_agent_file(), _entry(value="mystery", status="unknown")]
    row = _one(entries, [_run("judge", "claude-sonnet-5-5")])
    assert (row.status, row.reason_code) == ("unknown", "expected_unknown")


def test_a_status_word_the_module_does_not_know_reads_unknown() -> None:
    entries = [
        _agent_file(),
        _entry(value="sonnet", status="weird"),
        _entry(value="haiku", layer="env"),
    ]
    row = _one(entries, [_run("judge", None, None)])
    assert (row.status, row.reason_code) == ("unknown", "unknown_status")


def test_runs_that_differ_from_the_pin_read_overridden() -> None:
    entries = [_agent_file(), _entry(value="sonnet")]
    row = _one(entries, [_run("judge", "claude-haiku-4-5")] * 3)
    assert (row.status, row.reason_code) == ("overridden", "ran_differs")
    assert row.params["ran"] == "claude-haiku-4-5"
    assert (row.runs, row.mismatched_runs) == (3, 3)
    assert row.ran.mixed is False


def test_runs_split_between_values_read_overridden_and_mixed() -> None:
    entries = [_agent_file(), _entry(value="sonnet")]
    runs = [
        _run("judge", "claude-sonnet-5-5", n=1),
        _run("judge", "claude-haiku-4-5", n=2),
        _run("judge", "claude-haiku-4-5", n=3),
    ]
    row = _one(entries, runs)
    assert (row.status, row.reason_code) == ("overridden", "ran_mixed")
    assert row.params["ran"] == "claude-haiku-4-5, claude-sonnet-5-5"
    assert (row.runs, row.mismatched_runs) == (3, 2)
    assert row.ran.model == "claude-haiku-4-5"
    assert row.ran.mixed is True


def test_the_worse_setting_gives_the_row_status() -> None:
    entries = [
        _agent_file(),
        _entry(value="sonnet"),
        _entry(key="effort", value="high", line=5),
    ]
    row = _one(entries, [_run("judge", "claude-sonnet-5-5", "low")])
    assert (row.status, row.reason_code) == ("overridden", "ran_differs")
    assert row.params["setting"] == "effort"
    assert row.params["settings"] == "effort"
    assert row.mismatched_runs == 1


def test_no_file_no_pin_and_an_unnamed_agent_carry_no_status() -> None:
    entries = [_agent_file("scribe")]
    check = _check(
        entries, [_run("judge", "x"), _run("scribe", "x"), _run("unnamed", "x")]
    )
    codes = {r.agent: (r.status, r.reason_code) for r in check.rows}
    assert codes == {
        "judge": (None, "no_agent_file"),
        "scribe": (None, "no_pin"),
        "unnamed": (None, "unnamed_agent"),
    }
    assert all(r.params == {} for r in check.rows)


def test_rows_sort_worst_first_then_by_name_with_main_ahead() -> None:
    entries = [
        _agent_file("zed"),
        _entry(agent="zed", value="sonnet"),
        _agent_file("amy"),
        _entry(agent="amy", value="sonnet"),
        _agent_file("bob"),
        _entry(agent="bob", value="sonnet"),
        _entry(scope="main", agent=None, layer="user", value="opus", file="s.json"),
    ]
    runs = [
        _run("zed", "claude-sonnet-5-5"),
        _run("amy", "claude-sonnet-5-5"),
        _run("bob", "claude-haiku-4-5"),
        _run(None, "claude-opus-5-5"),
        _run("gus", "claude-sonnet-5-5"),
    ]
    check = _check(entries, runs)
    assert [(r.agent, r.status) for r in check.rows] == [
        ("bob", "overridden"),
        ("gus", None),
        (None, "in_effect"),
        ("amy", "in_effect"),
        ("zed", "in_effect"),
    ]
    assert check.in_effect_count == 3


def test_an_empty_session_has_no_rows() -> None:
    assert _check([], []) == ModelCheck(rows=[], in_effect_count=0)


# ---------------------------------------------------------------- resolve_entries


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _display_world(tmp_path: Path) -> Mapping[str, Path]:
    claude = tmp_path / ".claude"
    project = tmp_path / "work" / "proj"
    managed = tmp_path / "managed" / "ClaudeCode"
    _write(claude / "settings.json", '{\n  "model": "opus"\n}\n')
    _write(
        project / ".claude" / "agents" / "judge.md",
        "---\nname: judge\ndescription: Judges.\nmodel: sonnet\n"
        "effort: high\n---\nJudge.\n",
    )
    _write(managed / "managed-settings.json", '{"effortLevel": "low"}\n')
    return {"claude": claude, "project": project, "managed": managed}


def test_resolve_entries_shows_display_paths_only(tmp_path: Path) -> None:
    world = _display_world(tmp_path)
    entries = model_check.resolve_entries(
        claude_dir=world["claude"],
        project_dir=world["project"],
        managed_dir=world["managed"],
        shell_env={},
    )
    files = {str(e["file"]) for e in entries if "file" in e}
    assert ".claude/agents/judge.md" in files
    assert "~/.claude/settings.json" in files
    assert "ClaudeCode/managed-settings.json" in files
    assert not any(f.startswith("/") for f in files)
    judge = [e for e in entries if e.get("agent") == "judge" and e["key"] == "model"]
    assert judge[0]["value"] == "sonnet"
    assert judge[0]["line"] == 4


def test_resolve_entries_without_a_project_reads_user_files_only(
    tmp_path: Path,
) -> None:
    world = _display_world(tmp_path)
    entries = model_check.resolve_entries(
        claude_dir=world["claude"],
        project_dir=None,
        managed_dir=None,
        shell_env={},
    )
    assert not any(e.get("agent") == "judge" for e in entries)
    assert any(e["key"] == "model" and e["value"] == "opus" for e in entries)
    assert not any(str(e.get("file", "")).startswith("/") for e in entries)


def test_resolve_entries_reads_the_shell_env_it_is_given(tmp_path: Path) -> None:
    world = _display_world(tmp_path)
    quiet = model_check.resolve_entries(
        claude_dir=world["claude"], project_dir=None, managed_dir=None, shell_env={}
    )
    loud = model_check.resolve_entries(
        claude_dir=world["claude"],
        project_dir=None,
        managed_dir=None,
        shell_env={"ANTHROPIC_MODEL": "haiku"},
    )
    assert any(e.get("via") == "ANTHROPIC_MODEL" for e in loud)
    assert not any(e.get("via") == "ANTHROPIC_MODEL" for e in quiet)

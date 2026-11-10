"""The setup half of the Agents page: agent files, the check over a range, never ran.

Crafted folders cover a user agent, a project agent that overrides a user one, a file
that sets nothing, an agent type with no file and a setup that cannot be read. A
differential then builds each demo project's runs for 30 days from the ingested demo
and compares ``check_agent`` with the old ``by_agent[].pin`` in
``app/fixtures/oracle/demo/usage-30d-<project>.json``.

The old pin has a state, and the new check has a status. M2 maps one to the other in
the ``model_check`` docstring. The state words ``differs`` and ``mixed`` have NO CLEAN
MAPPING there: the resolver cannot see what beat the pin, so the new status is
``overridden``. Those are the only differences the differential allows, and it names
them. Every other state must map as the docstring says.
"""

import json
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import agent_setup
import ingest
import model_check
import prices
import project_map
import projects
import store
import usage_query
from models import SetPair
from store_paths import StoreLayout
from usage import Row

ORACLE = Path(__file__).resolve().parents[2] / "fixtures" / "oracle" / "demo"
USER_AGENT = (
    "---\nname: scout\ndescription: Scouts.\nmodel: claude-sonnet-5-5\n"
    "effort: high\n---\nScout.\n"
)
SETS_NOTHING = "---\nname: plain\ndescription: Plain.\n---\nPlain.\n"
# Old state words the new statuses have no clean mapping for (model_check docstring).
NO_CLEAN_MAPPING = ("differs", "mixed")
OLD_MAPPED = {
    "matches": ("in_effect", "default"),
    "matches_lowered": ("lowered",),
    "overridden": ("overridden",),
    "cannot_check": ("unknown",),
}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _runs(*pairs: tuple[str | None, str | None]) -> list[Row]:
    return [
        {"run_id": f"r{n}", "model": model, "effort": effort, "requests": 3}
        for n, (model, effort) in enumerate(pairs)
    ]


@dataclass(frozen=True)
class Folders:
    """The three folders a crafted setup reads."""

    claude: Path
    project: Path
    managed: Path

    def load(
        self, shell_env: Mapping[str, str] | None = None
    ) -> agent_setup.AgentSetup:
        return agent_setup.load_setup(
            self.claude, self.project, self.managed, shell_env or {}
        )


@pytest.fixture
def folders(tmp_path: Path) -> Folders:
    claude = tmp_path / ".claude"
    project = tmp_path / "work" / "proj"
    managed = tmp_path / "managed" / "ClaudeCode"
    _write(claude / "settings.json", '{\n  "model": "claude-opus-5-5"\n}\n')
    _write(claude / "agents" / "scout.md", USER_AGENT)
    _write(claude / "agents" / "plain.md", SETS_NOTHING)
    _write(
        claude / "agents" / "judge.md",
        "---\nname: judge\ndescription: User judge.\nmodel: claude-haiku-4-5\n"
        "effort: low\n---\nJudge.\n",
    )
    _write(
        project / ".claude" / "agents" / "judge.md",
        "---\nname: judge\ndescription: Project judge.\nmodel: claude-opus-5-5\n"
        "effort: high\n---\nJudge.\n",
    )
    return Folders(claude, project, managed)


# ---------------------------------------------------------------- crafted setups


def test_a_user_agent_shows_its_pins_with_display_paths(folders: Folders) -> None:
    setup = folders.load()
    check = agent_setup.check_agent(
        setup,
        "scout",
        _runs(("claude-sonnet-5-5", "high"), ("claude-sonnet-5-5", "high")),
    )
    assert check.scope == "user"
    assert check.set_reason is None
    assert check.set is not None
    assert check.set.model is not None
    assert check.set.model.value == "claude-sonnet-5-5"
    assert check.set.model.file == "~/.claude/agents/scout.md"
    assert check.set.model.line == 4
    assert check.set.model.scope == "agent"
    assert check.set.effort is not None
    assert check.set.effort.value == "high"
    assert check.set.effort.line == 5
    assert (check.status, check.reason_code) == ("in_effect", "in_effect")
    assert (check.runs_as_set, check.runs_not_as_set) == (2, 0)


def test_a_project_agent_wins_over_a_user_agent_of_the_same_name(
    folders: Folders,
) -> None:
    setup = folders.load()
    assert setup.files["judge"].scope == "project"
    check = agent_setup.check_agent(setup, "judge", _runs(("claude-opus-5-5", "high")))
    assert check.scope == "project"
    assert check.set is not None
    assert check.set.model is not None
    assert check.set.model.value == "claude-opus-5-5"
    assert check.set.model.file == ".claude/agents/judge.md"
    assert check.status == "in_effect"
    rows = [r for r in agent_setup.never_ran(setup, []) if r.agent == "judge"]
    assert [(r.scope, r.set_reason) for r in rows] == [("project", None)]


def test_runs_that_differ_from_the_pin_count_as_not_as_set(folders: Folders) -> None:
    setup = folders.load()
    runs = _runs(
        ("claude-sonnet-5-5", "high"),
        ("claude-haiku-5-5", "high"),
        ("claude-sonnet-5-5", "high"),
    )
    check = agent_setup.check_agent(setup, "scout", runs)
    assert (check.status, check.reason_code) == ("overridden", "ran_mixed")
    assert (check.runs_as_set, check.runs_not_as_set) == (2, 1)
    assert check.params["expected"] == "claude-sonnet-5-5"


def test_a_file_that_sets_neither_model_nor_effort_has_no_status(
    folders: Folders,
) -> None:
    setup = folders.load()
    check = agent_setup.check_agent(setup, "plain", _runs(("claude-haiku-5-5", None)))
    assert check.scope == "user"
    assert check.set is None
    assert check.set_reason == "sets_nothing"
    assert (check.status, check.reason_code) == (None, "no_pin")
    assert (check.runs_as_set, check.runs_not_as_set) == (None, None)


def test_one_pin_gives_a_pair_with_the_other_side_empty(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    _write(
        claude / "agents" / "half.md",
        "---\nname: half\ndescription: Half.\nmodel: claude-haiku-5-5\n---\nHalf.\n",
    )
    setup = agent_setup.load_setup(claude, None, None, {})
    found = setup.files["half"]
    assert found.set is not None
    assert found.set.model is not None
    assert found.set.effort is None
    assert found.set_reason is None


def test_a_type_with_no_file_is_no_file(folders: Folders) -> None:
    setup = folders.load()
    check = agent_setup.check_agent(setup, "Explore", _runs(("claude-haiku-5-5", None)))
    assert check.scope == "no_file"
    assert check.set is None
    assert check.set_reason == "no_file"
    assert (check.status, check.reason_code) == (None, "no_agent_file")
    assert (check.runs_as_set, check.runs_not_as_set) == (None, None)


def test_the_main_session_reads_its_pins_from_settings(folders: Folders) -> None:
    setup = folders.load()
    check = agent_setup.check_agent(
        setup, "@main", _runs(("claude-opus-5-5", "medium"))
    )
    assert check.scope == "main"
    assert check.set is not None
    assert check.set.model is not None
    assert check.set.model.value == "claude-opus-5-5"
    assert check.set.model.file == "~/.claude/settings.json"
    assert check.set.model.scope == "user"
    assert check.status is not None
    assert check.runs_as_set == 1
    assert setup.main == check.set


def test_an_unnamed_agent_has_no_file_and_no_status(folders: Folders) -> None:
    check = agent_setup.check_agent(
        folders.load(), "@unnamed", _runs(("claude-haiku-5-5", None))
    )
    assert check.scope == "unnamed"
    assert (check.set, check.set_reason) == (None, "no_file")
    assert (check.status, check.reason_code) == (None, "unnamed_agent")


def test_a_side_with_no_value_is_none_beside_a_side_that_is_set(tmp_path: Path) -> None:
    """A settings file that sets only the effort leaves the model side None."""
    claude = tmp_path / ".claude"
    _write(claude / "settings.json", '{\n  "effortLevel": "high"\n}\n')
    setup = agent_setup.load_setup(claude, None, None, {})
    assert setup.main is not None
    assert setup.main_reason is None
    assert setup.main.model is None
    assert setup.main.effort is not None
    assert setup.main.effort.value == "high"
    assert setup.main.effort.scope == "user"


def test_the_main_session_with_no_settings_sets_nothing(tmp_path: Path) -> None:
    """No settings file leaves resolver defaults with no value, so nothing is set.

    The resolver's default entry for the model and the effort has the value None.
    That side of the pair is None, not the string "None", and with neither side set
    ``main`` shows no pair and the reason ``sets_nothing``. The timeline's Model
    check reads the same function, so Live agrees.
    """
    claude = tmp_path / ".claude"
    claude.mkdir()
    setup = agent_setup.load_setup(claude, None, None, {})
    assert setup.main is None
    assert setup.main_reason == "sets_nothing"
    check = agent_setup.check_agent(setup, "@main", _runs(("claude-opus-5-5", "high")))
    assert check.set is None
    assert check.set_reason == "sets_nothing"
    assert check.status is not None  # the check itself still judges the runs
    verdict = model_check.judge_agent(setup.entries, "@main", [], setup.catalog)
    assert verdict.set == SetPair(model=None, effort=None)


def test_never_ran_lists_files_without_a_run_sorted_by_name(folders: Folders) -> None:
    setup = folders.load()
    rows = agent_setup.never_ran(setup, ["scout", "@main", "Explore"])
    assert [r.agent for r in rows] == ["judge", "plain"]
    plain = rows[1]
    assert (plain.scope, plain.set, plain.set_reason) == ("user", None, "sets_nothing")
    assert agent_setup.never_ran(setup, ["judge", "plain", "scout"]) == []


def test_never_ran_skips_a_file_that_does_not_load(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    _write(claude / "agents" / "notes.txt", "not an agent")
    _write(claude / "agents" / "nameless.md", "---\ndescription: No name.\n---\nx\n")
    setup = agent_setup.load_setup(claude, None, None, {})
    assert "notes" not in setup.files
    assert not setup.failed


# ---------------------------------------------------------------- unreadable setup


def test_a_setup_that_raises_is_failed_and_reads_failed(tmp_path: Path) -> None:
    # A null byte in a path makes open() raise ValueError, which collect does not catch.
    setup = agent_setup.load_setup(Path(str(tmp_path / "bad\0folder")), None, None, {})
    assert setup.failed
    assert setup.files == {}
    assert agent_setup.never_ran(setup, []) == []
    check = agent_setup.check_agent(
        setup, "scout", _runs(("claude-sonnet-5-5", "high"))
    )
    assert check.scope == "no_file"
    assert check.set is None
    assert check.set_reason == "read_failed"
    assert (check.status, check.reason_code) == (None, None)
    assert (check.runs_as_set, check.runs_not_as_set) == (None, None)
    main = agent_setup.check_agent(setup, "@main", [])
    assert (main.scope, main.set_reason) == ("main", "read_failed")


@pytest.mark.parametrize("error", [OSError("disk"), ValueError("rules disagree")])
def test_the_errors_collect_and_resolve_raise_make_a_failed_setup(
    folders: Folders, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def boom(**_: object) -> list[Row]:
        raise error

    monkeypatch.setattr(model_check, "resolve_entries", boom)
    assert folders.load().failed


def test_any_other_error_is_not_swallowed(
    folders: Folders, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**_: object) -> list[Row]:
        msg = "a bug"
        raise RuntimeError(msg)

    monkeypatch.setattr(model_check, "resolve_entries", boom)
    with pytest.raises(RuntimeError):
        folders.load()


def test_from_entries_builds_the_same_setup_as_load_setup(folders: Folders) -> None:
    entries = model_check.resolve_entries(
        claude_dir=folders.claude,
        project_dir=folders.project,
        managed_dir=folders.managed,
        shell_env={},
    )
    built = agent_setup.from_entries(entries)
    assert built.files == folders.load().files
    assert built.main == folders.load().main


# ---------------------------------------------------------------- demo differential


@dataclass(frozen=True)
class World:
    """The demo build ingested into a store, with its project map."""

    conn: sqlite3.Connection
    prices: prices.PricesDoc
    mapped: list[project_map.MappedProject]
    root: Path
    shell_env: dict[str, str]


@pytest.fixture(scope="module")
def world(
    demo_build: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[World]:
    root = demo_build.resolve()
    layout = StoreLayout(tmp_path_factory.mktemp("agent-setup") / "bartab")
    conn = store.open_writer(layout)
    store.migrate(conn)
    ingest.Ingestor(
        conn,
        root / "config",
        clock=lambda: datetime(2026, 10, 30, 22, 0, tzinfo=UTC),
    ).run_pass(ingest.PassScope("full"))
    ctx = projects.ProjectsContext(
        config_dir=str(root / "config"),
        project_dir=str(root / "project"),
        root=str(root),
    )
    session = json.loads((root / "session.json").read_text(encoding="utf-8"))
    try:
        yield World(
            conn,
            prices.load_prices(),
            project_map.map_projects(ctx, conn),
            root,
            session.get("shell_env") or {},
        )
    finally:
        conn.close()


_CELLS = (
    "SELECT mu.session_id, mu.run_key,"
    " CASE WHEN mu.run_key = 'main' THEN '@main'"
    " WHEN r.agent_type IS NULL OR r.agent_type = '' THEN '@unnamed'"
    " ELSE r.agent_type END,"
    " mu.model, mu.effort, SUM(mu.requests)"
    " FROM minute_usage mu"
    " JOIN sessions s ON s.session_id = mu.session_id"
    " LEFT JOIN runs r ON r.session_id = mu.session_id AND r.run_id = mu.run_key"
    " WHERE mu.minute >= ? AND mu.minute < ? AND s.folder IN ({marks})"
    " GROUP BY mu.session_id, mu.run_key, mu.minute, mu.model, mu.effort"
    " ORDER BY mu.minute"
)
_MINUTE = "%Y-%m-%dT%H:%M"


def _minute_text(moment: datetime, *, up: bool) -> str:
    utc = moment.astimezone(UTC)
    floor = utc.replace(second=0, microsecond=0)
    if up and floor != utc:
        floor += timedelta(minutes=1)
    return floor.strftime(_MINUTE)


def _demo_runs(
    world: World, folders: frozenset[str], start: datetime, end: datetime
) -> dict[str, list[Row]]:
    """Build the runs per agent key as the old pin_fn got them.

    A run is a (session, run) pair and the main session is one run per session. Its
    model (the catalog id, else the raw name) and effort are its most-used pair by
    requests, a tie going to the pair seen first.
    """
    ordered = sorted(folders)
    sql = _CELLS.format(marks=",".join("?" * len(ordered)))
    args = [_minute_text(start, up=False), _minute_text(end, up=True), *ordered]
    pricer = usage_query.Pricer(world.prices)
    pairs: dict[tuple[str, str], dict[tuple[str, str | None], int]] = {}
    agents: dict[tuple[str, str], str] = {}
    for session, run_key, agent, model, effort, requests in world.conn.execute(
        sql, args
    ):
        pair = (pricer.label(str(model))[0], effort or None)
        mine = pairs.setdefault((session, run_key), {})
        mine[pair] = mine.get(pair, 0) + int(requests)
        agents[(session, run_key)] = agent
    out: dict[str, list[Row]] = {}
    for key, counts in pairs.items():
        top = max(counts.values())
        model, effort = next(p for p, n in counts.items() if n == top)
        run_id = key[0] if key[1] == "main" else key[1]
        out.setdefault(agents[key], []).append(
            {
                "run_id": run_id,
                "model": model,
                "effort": effort,
                "requests": sum(counts.values()),
            }
        )
    return out


def _oracle(project: str) -> dict[str, Any]:
    return json.loads(
        (ORACLE / f"usage-30d-{project}.json").read_text(encoding="utf-8")
    )


def _ids(path: str) -> tuple[Path, ...]:
    return tuple(sorted(ORACLE.glob(path)))


PROJECTS = [
    name
    for p in _ids("usage-30d-*.json")
    if (name := p.name.removeprefix("usage-30d-").removesuffix(".json")) != "all"
]


@pytest.mark.parametrize("project", PROJECTS)
def test_check_agent_equals_the_old_pin_on_the_demo(world: World, project: str) -> None:
    payload = _oracle(project)
    view = payload["views"]["30d"]
    (found,) = (p for p in world.mapped if p.key == project)
    project_dir = world.root / "projects" / project
    setup = agent_setup.load_setup(
        world.root / "config",
        project_dir if project_dir.is_dir() else None,
        world.root / "managed",
        world.shell_env,
    )
    assert not setup.failed
    runs = _demo_runs(
        world,
        found.folders,
        datetime.fromisoformat(view["start"]),
        datetime.fromisoformat(view["end"]),
    )
    old = {row["route_key"]: row for row in view["by_agent"]}
    assert set(runs) == set(old), project
    lines: list[str] = []
    for key, rows in sorted(runs.items()):
        pin = old[key]["pin"]
        check = agent_setup.check_agent(setup, key, rows)
        if pin is None:
            if check.status is not None:
                lines.append(f"{key}: old pin None, new {check.status}")
            continue
        state = pin["state"]
        wanted = ("overridden",) if state in NO_CLEAN_MAPPING else OLD_MAPPED[state]
        if check.status not in wanted:
            lines.append(f"{key}: old {state}, new {check.status}, wanted {wanted}")
        if (check.runs_as_set, check.runs_not_as_set) != (
            pin["total_runs"] - pin["mismatched_runs"],
            pin["mismatched_runs"],
        ):
            lines.append(
                f"{key}: runs {check.runs_as_set}/{check.runs_not_as_set},"
                f" old {pin['total_runs']}/{pin['mismatched_runs']}"
            )
        for kind in ("model", "effort"):
            pinned = pin[kind]["pinned"]
            shown = getattr(check.set, kind) if check.set else None
            if shown is None or shown.value != pinned["value"]:
                lines.append(f"{key}.{kind}: set {shown}, old {pinned['value']}")
            elif (pinned["file"] is None) != (shown.file is None) or (
                pinned["file"] is not None
                and not pinned["file"].endswith(shown.file.removeprefix("~/"))
            ):
                lines.append(f"{key}.{kind}: file {shown.file}, old {pinned['file']}")
            elif shown.line != pinned["line"]:
                lines.append(f"{key}.{kind}: line {shown.line}, old {pinned['line']}")
    assert lines == [], "\n".join(lines)


def test_the_differences_with_no_clean_mapping_are_the_known_ones() -> None:
    """Only the old differs state, on the scribe agent, whose file pins haiku-4-5.

    The demo's scribe runs haiku-5-5, so the old pin says differs. The new status is
    overridden, the word the model_check docstring gives that case (NO CLEAN MAPPING).
    The differential above allows exactly these and no other difference.
    """
    seen = sorted(
        (project, row["route_key"], row["pin"]["state"])
        for project in PROJECTS
        for row in _oracle(project)["views"]["30d"]["by_agent"]
        if row.get("pin") and row["pin"]["state"] in NO_CLEAN_MAPPING
    )
    assert seen == [
        ("driftwood", "scribe", "differs"),
        ("harbor-light", "scribe", "differs"),
        ("tidewater-reporting", "scribe", "differs"),
    ]


def test_the_demo_never_ran_list_is_empty_when_every_file_ran(world: World) -> None:
    view = _oracle("tidewater-reporting")["views"]["30d"]
    setup = agent_setup.load_setup(
        world.root / "config",
        world.root / "projects" / "tidewater-reporting",
        world.root / "managed",
        world.shell_env,
    )
    ran = [row["route_key"] for row in view["by_agent"]]
    assert agent_setup.never_ran(setup, ran) == []
    left = agent_setup.never_ran(setup, [k for k in ran if k != "builder"])
    assert [r.agent for r in left] == ["builder"]
    assert left[0].set is not None
    assert left[0].set.model is not None
    assert left[0].set.model.value == "claude-fable-5-1"

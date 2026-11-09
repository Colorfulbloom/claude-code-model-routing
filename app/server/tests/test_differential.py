"""Differential tests: the new totals against the old app's recorded answers.

The oracle files in ``app/fixtures/oracle/demo/`` hold what the old ``api_usage.usage``
and ``api_usage.api_projects`` answered on the demo build, plus the demo's own
``truth.json``. These tests ingest the same demo build into a store, price it with
``prices-old.json`` and compare, per project and for "all", the totals, the agents, the
models and the days of today, 7 and 30 days, and the 30-day totals against truth.

A difference must be zero or listed in ``allowed-differences.json`` with its path, a
reason and a plan reference. An unlisted difference fails with a readable diff. Money
agrees within 1e-6 and every token and count agrees exactly.

The store is built from the demo build in place. The routing-dashboard.json list holds
absolute paths into the build, so a copy at another path would not match its folders.
Ingest only reads the build.

Old "all" is every transcript folder, quarry-notes included (the old ALL_PROJECTS_SCOPE
is ``every_folder``), so the new "all" is ``folders=None``.
"""

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import ingest
import prices
import project_map
import projects
import store
import usage_query
from store_paths import StoreLayout

ORACLE = Path(__file__).resolve().parents[2] / "fixtures" / "oracle" / "demo"
MONEY_TOLERANCE = 1e-6
FIELDS = (
    "input",
    "output",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "thinking",
    "requests",
    "cost",
    "unpriced_requests",
)
Flat = dict[str, float | int]


def _json(name: str) -> Any:
    return json.loads((ORACLE / name).read_text(encoding="utf-8"))


MANIFEST = _json("manifest.json")
TZ: str = MANIFEST["build_args"]["tz"]
USAGE_QUERIES: list[dict[str, Any]] = [
    q for q in MANIFEST["queries"] if q["call"] == "usage"
]


@dataclass(frozen=True)
class World:
    """The demo build ingested into a store, with its project map."""

    conn: sqlite3.Connection
    prices: prices.PricesDoc
    mapped: list[project_map.MappedProject]
    root: Path


@pytest.fixture(scope="module")
def world(
    demo_build: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[World]:
    root = demo_build.resolve()
    layout = StoreLayout(tmp_path_factory.mktemp("differential") / "bartab")
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
    try:
        yield World(
            conn, prices.load_prices(), project_map.map_projects(ctx, conn), root
        )
    finally:
        conn.close()


# ---------------------------------------------------------------- allowed list


def _allowed() -> dict[str, dict[str, str]]:
    return {e["path"]: e for e in _json("allowed-differences.json")["differences"]}


def test_every_allowed_difference_names_a_path_a_reason_and_a_plan_ref() -> None:
    doc = _json("allowed-differences.json")
    for entry in doc["differences"]:
        for field in ("path", "reason", "plan_ref"):
            assert isinstance(entry.get(field), str), entry
            assert entry[field].strip(), entry
    paths = [e["path"] for e in doc["differences"]]
    assert len(paths) == len(set(paths)), "a path is listed twice"


def _same(name: str, old: object, new: object) -> bool:
    if name.endswith(".cost") and isinstance(old, int | float):
        return isinstance(new, int | float) and abs(old - new) <= MONEY_TOLERANCE
    return old == new


def _unlisted(prefix: str, old: Flat, new: Flat) -> list[str]:
    """Return one readable line per difference that is not in the allowed list."""
    allowed = _allowed()
    lines: list[str] = []
    for name in sorted(set(old) | set(new)):
        before, after = old.get(name), new.get(name)
        path = f"{prefix}{name}"
        if _same(name, before, after) or path in allowed:
            continue
        lines.append(f"  {path}: old {before!r}, new {after!r}")
    return lines


def _fail_on(lines: list[str], what: str) -> None:
    if lines:
        text = "\n".join(lines[:40])
        more = f"\n  ... and {len(lines) - 40} more" if len(lines) > 40 else ""
        pytest.fail(
            f"{len(lines)} unlisted difference(s) in {what}. Fix the code or list "
            "each in allowed-differences.json with a reason and plan_ref.\n"
            f"{text}{more}"
        )


# ---------------------------------------------------------------- usage


def _fields(prefix: str, row: dict[str, Any]) -> Flat:
    """The nine compared fields of an old row or a new Usage, null read as 0."""
    return {f"{prefix}.{f}": row.get(f) or 0 for f in FIELDS}


def _old_flat(view: dict[str, Any]) -> Flat:
    flat = _fields("totals", view["totals"])
    for row in view["by_agent"]:
        flat.update(_fields(f"by_agent.{row['route_key']}", row))
    for row in view["by_model"]:
        flat.update(_fields(f"by_model.{row['model']}", row))
    for bucket in view["buckets"]:
        if not bucket["tokens"]:
            continue
        # Today is hourly in the old answer. A day is the sum of its hours.
        day = f"by_day.{bucket['date']}"
        flat[f"{day}.tokens"] = flat.get(f"{day}.tokens", 0) + bucket["tokens"]
        for model, tokens in bucket["by_model"].items():
            key = f"{day}.by_model.{model}"
            flat[key] = flat.get(key, 0) + tokens
    return flat


def _usage_row(usage: usage_query.Usage) -> dict[str, Any]:
    return {f: getattr(usage, f) for f in FIELDS}


def _new_flat(result: usage_query.Totals) -> Flat:
    flat = _fields("totals", _usage_row(result.total))
    for agent, usage in result.by_agent.items():
        flat.update(_fields(f"by_agent.{agent}", _usage_row(usage)))
    for model, usage in result.by_model.items():
        flat.update(_fields(f"by_model.{model}", _usage_row(usage)))
    for date, day in result.by_day.items():
        flat[f"by_day.{date}.tokens"] = day.usage.tokens
        for model, tokens in day.tokens_by_model.items():
            flat[f"by_day.{date}.by_model.{model}"] = tokens
    return flat


def _folders(world: World, scope: str) -> frozenset[str] | None:
    if scope == "all":
        return None
    (found,) = (p for p in world.mapped if p.key == scope)
    return found.folders


@pytest.mark.parametrize(
    "query", USAGE_QUERIES, ids=[q["file"].removesuffix(".json") for q in USAGE_QUERIES]
)
def test_totals_equal_the_recorded_usage_answer(
    world: World, query: dict[str, Any]
) -> None:
    payload = _json(query["file"])
    view = payload["views"][query["range"]]
    result = usage_query.totals(
        world.conn,
        world.prices,
        folders=_folders(world, query["query"]["project"][0]),
        start=datetime.fromisoformat(view["start"]),
        end=datetime.fromisoformat(view["end"]),
        tz=TZ,
    )
    prefix = f"{query['file']}:views.{query['range']}."
    _fail_on(_unlisted(prefix, _old_flat(view), _new_flat(result)), query["file"])


def test_the_demo_has_usage_to_compare(world: World) -> None:
    """A guard against a comparison that passes because both sides are empty."""
    view = _json("usage-30d-all.json")["views"]["30d"]
    assert view["totals"]["requests"] == 3913
    assert view["totals"]["unpriced_requests"] == 150
    result = usage_query.totals(
        world.conn,
        world.prices,
        folders=None,
        start=datetime.fromisoformat(view["start"]),
        end=datetime.fromisoformat(view["end"]),
        tz=TZ,
    )
    assert result.total.requests == 3913
    assert result.total.unpriced_requests == 150
    assert set(result.by_agent) == {"@main", "builder", "reviewer", "scribe"}
    assert len(result.by_day) > 10


def test_a_changed_price_changes_the_cost_and_nothing_else(world: World) -> None:
    """Prices apply at query time, so doubling a rate doubles that model's cost."""
    view = _json("usage-30d-harbor-light.json")["views"]["30d"]
    args: dict[str, Any] = {
        "folders": _folders(world, "harbor-light"),
        "start": datetime.fromisoformat(view["start"]),
        "end": datetime.fromisoformat(view["end"]),
        "tz": TZ,
    }
    base = usage_query.totals(world.conn, world.prices, **args)
    doubled = json.loads(json.dumps(world.prices))
    for field in prices.PRICE_FIELDS:
        doubled["models"]["claude-sonnet-5-5"][field] *= 2
    after = usage_query.totals(world.conn, doubled, **args)
    assert after.total.requests == base.total.requests
    assert (
        after.by_model["claude-opus-5-5"].cost == base.by_model["claude-opus-5-5"].cost
    )
    assert after.by_model["claude-sonnet-5-5"].cost == pytest.approx(
        2 * base.by_model["claude-sonnet-5-5"].cost
    )


# ---------------------------------------------------------------- truth


def test_30_day_totals_equal_truth_per_project(world: World) -> None:
    truth = _json("truth.json")
    window = truth["window"]
    by_name = {p.name: p for p in world.mapped}
    lines: list[str] = []
    for name, expected in truth["projects"].items():
        result = usage_query.totals(
            world.conn,
            world.prices,
            folders=by_name[name].folders,
            start=datetime.fromisoformat(window["start"].replace("Z", "+00:00")),
            end=datetime.fromisoformat(window["end"].replace("Z", "+00:00")),
            tz=window["tz"],
        )
        old = _fields("", expected)
        new = _fields("", _usage_row(result.total))
        lines += _unlisted(f"truth.json:projects.{name}", old, new)
    _fail_on(lines, "truth.json")


# ---------------------------------------------------------------- projects


def _old_projects() -> Flat:
    flat: Flat = {}
    for row in _json("projects.json")["projects"]:
        flat[f".{row['key']}.name"] = row["name"]  # type: ignore[assignment]
        flat[f".{row['key']}.state"] = row["state"]  # type: ignore[assignment]
        flat[f".{row['key']}.path_display"] = row["path_display"]  # type: ignore[assignment]
    return flat


def _new_projects(world: World) -> Flat:
    flat: Flat = {}
    for p in world.mapped:
        flat[f".{p.key}.name"] = p.name  # type: ignore[assignment]
        flat[f".{p.key}.state"] = p.state  # type: ignore[assignment]
        flat[f".{p.key}.path_display"] = p.display_path  # type: ignore[assignment]
    return flat


def test_project_map_equals_the_recorded_api_projects(world: World) -> None:
    _fail_on(
        _unlisted("projects.json:projects", _old_projects(), _new_projects(world)),
        "projects.json",
    )


def test_project_map_lists_quarry_notes_as_an_unlisted_extra(world: World) -> None:
    listed = [p.key for p in world.mapped if p.listed]
    assert listed == [
        "tidewater-reporting",
        "driftwood",
        "harbor-light",
        "saltmarsh",
        "lantern",
    ]
    assert [p.key for p in world.mapped if not p.listed] == ["quarry-notes"]
    quarry = world.mapped[-1]
    assert quarry.name == "quarry-notes"
    assert len(quarry.folders) == 1
    assert quarry.state == projects.STATE_FOLDER_NOT_FOUND
    by_key = {p.key: p for p in world.mapped}
    assert by_key["lantern"].state == projects.STATE_FOLDER_NOT_FOUND
    assert by_key["saltmarsh"].folders == frozenset()
    assert by_key["lantern"].folders == frozenset()
    claimed = [f for p in world.mapped for f in p.folders]
    assert len(claimed) == len(set(claimed)) == 4

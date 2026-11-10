"""Differential tests for Review: the new sums against the old app and a longer build.

Two oracles, fixtures only.

* ``app/fixtures/oracle/demo/usage-<range>-<project>.json`` holds what the old
  ``api_usage.usage`` answered on the demo build for today, 7 and 30 days, per project
  and for "all". For every one of the 18 files this ingests the same build, builds the
  window with ``review_windows`` (which must equal the recorded window), sums it with
  ``review_query.scan`` and compares the totals, the previous window, the deltas, the
  agents, the models, the buckets and the session list.
* ``app/fixtures/oracle/demo-long/truth-long.json`` holds sums the recorder made from
  the generator's own request list on a 400-day build, for 30 and 90 days, 12 months
  and all. The new sums must equal it for the current and the prior window, per model,
  per agent and per local day.

Money agrees within 1e-6, ratios within 1e-9 and every count exactly. A difference
must be zero or listed in ``allowed-differences.json`` with a path, a reason and a
plan reference. A path may hold ``*``, which matches any run of characters, so one
entry covers a rule that holds in every file. Every unlisted difference fails with a
readable diff.

How old values are read

* ``thinking`` is null in the old answer when no request had it, and 0 here.
* The old share is a whole percent by largest remainder (``usage.py _shares``), so the
  test runs that rule on the new costs, in the old row order, and compares the
  percents. The new fraction must also sit within one percent of the old number.
* The old agent names of a session are display names. "Main session" is ``@main``
  and "Unnamed agent" is ``@unnamed``.
* The old buckets hold tokens only, so bucket cost has no oracle here. It is checked
  against the totals and, on the long build, against ``by_day``.
* The old app has no previous window when the oldest request falls after its start.
  The new window keeps it and says ``prior_partial``. The test requires the two to
  agree on when that happens.
"""

import fnmatch
import json
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

import ingest
import prices
import project_map
import projects
import review_query as rq
import review_windows as rw
import store
from models import ReviewRange
from store_paths import StoreLayout

ORACLE = Path(__file__).resolve().parents[2] / "fixtures" / "oracle"
DEMO = ORACLE / "demo"
LONG = ORACLE / "demo-long"
MONEY_TOLERANCE = 1e-6
RATIO_TOLERANCE = 1e-9
SESSION_PAGE = 50

Flat = dict[str, object]


def _json(folder: Path, name: str) -> Any:
    return json.loads((folder / name).read_text(encoding="utf-8"))


MANIFEST = _json(DEMO, "manifest.json")
TZ: str = MANIFEST["build_args"]["tz"]
USAGE_QUERIES: list[dict[str, Any]] = [
    q for q in MANIFEST["queries"] if q["call"] == "usage"
]
DISPLAY = {"Main session": "@main", "Unnamed agent": "@unnamed"}


@dataclass(frozen=True)
class World:
    """A build ingested into a store, with its project map and prices."""

    conn: sqlite3.Connection
    prices: prices.PricesDoc
    mapped: list[project_map.MappedProject]


def _ingest(root: Path, base: Path) -> World:
    root = root.resolve()
    conn = store.open_writer(StoreLayout(base / "bartab"))
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
    return World(conn, prices.load_prices(), project_map.map_projects(ctx, conn))


@pytest.fixture(scope="module")
def world(
    demo_build: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[World]:
    found = _ingest(demo_build, tmp_path_factory.mktemp("review-diff"))
    try:
        yield found
    finally:
        found.conn.close()


@pytest.fixture(scope="module")
def long_world(
    long_demo_build: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[World]:
    found = _ingest(long_demo_build, tmp_path_factory.mktemp("review-diff-long"))
    try:
        yield found
    finally:
        found.conn.close()


# ---------------------------------------------------------------- allowed list


def _allowed() -> list[dict[str, str]]:
    return list(_json(DEMO, "allowed-differences.json")["differences"])


def _is_allowed(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, e["path"]) for e in _allowed())


def _same(name: str, old: object, new: object) -> bool:
    if isinstance(old, bool) or isinstance(new, bool) or old is None or new is None:
        return old == new
    if isinstance(old, float) or isinstance(new, float):
        assert isinstance(old, int | float)
        assert isinstance(new, int | float)
        if "cost" in name:
            return abs(old - new) <= MONEY_TOLERANCE
        return abs(old - new) <= RATIO_TOLERANCE * max(1.0, abs(old))
    return old == new


def _unlisted(prefix: str, old: Flat, new: Flat) -> list[str]:
    """Return one readable line per difference that is not in the allowed list."""
    lines: list[str] = []
    for name in sorted(set(old) | set(new)):
        before, after = old.get(name), new.get(name)
        path = f"{prefix}{name}"
        if _same(name, before, after) or _is_allowed(path):
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


def test_the_allowed_list_is_well_formed() -> None:
    paths = [e["path"] for e in _allowed()]
    assert len(paths) == len(set(paths)), "a path is listed twice"
    for entry in _allowed():
        for field in ("path", "reason", "plan_ref"):
            assert isinstance(entry.get(field), str), entry
            assert entry[field].strip(), entry


def test_a_wildcard_entry_matches_one_path_shape() -> None:
    assert fnmatch.fnmatchcase("a.json:views.30d.previous", "a.json:views.*.previous")
    assert not fnmatch.fnmatchcase("a.json:views.30d.totals", "a.json:views.*.previous")


# ---------------------------------------------------------------- flattening

GROUP_COUNTS = (
    "input",
    "output",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "thinking",
    "requests",
    "runs",
    "sessions",
    "unpriced_requests",
    "tokens",
)
KINDS = ("input", "output", "cache_read", "cache_write")


def _old_group(prefix: str, row: dict[str, Any]) -> Flat:
    """The compared fields of an old totals row, null read as 0 where 0 is the rule."""
    flat: Flat = {f"{prefix}.{f}": row.get(f) or 0 for f in GROUP_COUNTS}
    flat[f"{prefix}.cost"] = row.get("cost") or 0.0
    flat[f"{prefix}.hit_rate"] = row.get("hit_rate")
    for kind in KINDS:
        flat[f"{prefix}.cost_by_kind.{kind}"] = row["cost_by_kind"][kind]
    return flat


def _new_group(prefix: str, sums: rq.Sums) -> Flat:
    flat: Flat = {f"{prefix}.{f}": getattr(sums, f) for f in GROUP_COUNTS[:7]}
    flat[f"{prefix}.runs"] = sums.runs
    flat[f"{prefix}.sessions"] = sums.sessions
    flat[f"{prefix}.unpriced_requests"] = sums.unpriced.requests
    flat[f"{prefix}.tokens"] = sums.tokens
    flat[f"{prefix}.cost"] = sums.cost or 0.0
    flat[f"{prefix}.hit_rate"] = sums.hit_rate
    for kind in KINDS:
        flat[f"{prefix}.cost_by_kind.{kind}"] = getattr(sums.cost_by_kind, kind)
    return flat


def _shares(values: Sequence[float]) -> list[int]:
    """The old whole percents (``dashboard/usage.py _shares``, largest remainder)."""
    total = float(sum(values))
    if total <= 0:
        return [0 for _ in values]
    raw = [round(100.0 * v / total, 9) for v in values]
    base = [int(r // 1) for r in raw]
    deficit = 100 - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[: max(deficit, 0)]:
        base[i] += 1
    return base


def _rel_pct(cur: float, prev: float | None) -> float | None:
    if prev is None or not prev:
        return None
    return (cur - prev) / float(prev) * 100.0


def _deltas(total: rq.Sums, prior: rq.Sums | None) -> Flat:
    """The old ``_deltas``, from the new sums."""
    if prior is None:
        return {
            "tokens_pct": None,
            "cost_pct": None,
            "runs_pct": None,
            "hit_rate_pts": None,
        }
    points = None
    if total.hit_rate is not None and prior.hit_rate is not None:
        points = (total.hit_rate - prior.hit_rate) * 100.0
    return {
        "tokens_pct": _rel_pct(total.tokens, prior.tokens),
        "cost_pct": _rel_pct(total.cost or 0.0, prior.cost or 0.0),
        "runs_pct": _rel_pct(total.runs, prior.runs),
        "hit_rate_pts": points,
    }


def _names(values: Sequence[str]) -> str:
    """Agent names, display words mapped to keys, sorted and joined."""
    return "|".join(sorted(DISPLAY.get(a, a) for a in values))


def _folders(world: World, scope: str) -> frozenset[str] | None:
    if scope == "all":
        return None
    (found,) = (p for p in world.mapped if p.key == scope)
    return found.folders


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


# ---------------------------------------------------------------- the old payloads


def _compare(world: World, query: dict[str, Any]) -> list[str]:
    payload = _json(DEMO, query["file"])
    name: ReviewRange = query["range"]
    view = payload["views"][name]
    folders = _folders(world, query["query"]["project"][0])
    now = _utc(view["end"])
    oldest = rq.oldest_request(world.conn, folders)
    window = rw.review_window(name, now, TZ, oldest)
    chart = rw.chart_window(name, now, TZ, oldest)
    cur = rq.scan(
        world.conn,
        world.prices,
        folders=folders,
        start=window.start,
        end=window.end,
        tz=TZ,
        now=now,
        bars=chart.bars,
        sessions=True,
    )
    assert window.prior_start is not None
    assert window.prior_end is not None
    prior = rq.scan(
        world.conn,
        world.prices,
        folders=folders,
        start=window.prior_start,
        end=window.prior_end,
        tz=TZ,
    )
    prefix = f"{query['file']}:views.{name}."
    lines: list[str] = []

    # The window itself.
    lines += _unlisted(
        prefix,
        {
            "start": _utc(view["start"]),
            "end": _utc(view["end"]),
            "previous_start": _utc(view["previous_start"]),
            "previous_end": _utc(view["previous_end"]),
        },
        {
            "start": window.start,
            "end": window.end,
            "previous_start": window.prior_start,
            "previous_end": window.prior_end,
        },
    )

    # Totals and the previous window.
    old: Flat = _old_group("totals", view["totals"])
    new: Flat = _new_group("totals", cur.total)
    old_previous = view["previous"]
    kept = not window.prior_partial and oldest is not None
    old["previous.available"] = old_previous is not None
    new["previous.available"] = kept
    if old_previous is not None:
        old.update(_old_group("previous", old_previous))
        new.update(_new_group("previous", prior.total))
    elif prior.total.requests:
        old["previous"] = None
        new["previous"] = f"kept {prior.total.requests} requests"
    old.update({f"deltas.{k}": v for k, v in view["deltas"].items()})
    new.update(
        {
            f"deltas.{k}": v
            for k, v in _deltas(cur.total, prior.total if kept else None).items()
        }
    )

    # Agents, with what each ran with.
    for row in view["by_agent"]:
        key = row["route_key"]
        old.update(_old_group(f"by_agent.{key}", row))
        old.update(
            {
                f"by_agent.{key}.ran_with.{r['model']}|{r['effort']}": r["runs"]
                for r in row["ran_with"]
                if r["runs"]
            }
        )
    for key, agent in cur.by_agent.items():
        new.update(_new_group(f"by_agent.{key}", agent.sums))
        new.update(
            {
                f"by_agent.{key}.ran_with.{p.model}|{p.effort}": p.runs
                for p in agent.ran_pairs
            }
        )

    # Models, their agents and their shares.
    rows = view["by_model"]
    percents = _shares([cur.by_model[r["model"]].sums.cost or 0.0 for r in rows])
    for row, percent in zip(rows, percents, strict=True):
        key = row["model"]
        old.update(_old_group(f"by_model.{key}", row))
        old[f"by_model.{key}.agents"] = _names(row["agents"])
        old[f"by_model.{key}.share_pct"] = row["share_pct"]
        new[f"by_model.{key}.share_pct"] = percent
        share = cur.by_model[key].share
        assert share is None or abs(share * 100.0 - row["share_pct"]) <= 1.0, key
    for key, model in cur.by_model.items():
        new.update(_new_group(f"by_model.{key}", model.sums))
        new[f"by_model.{key}.agents"] = "|".join(sorted(model.agents))
    lines += _unlisted(prefix, old, new)

    lines += _unlisted(prefix, *_buckets(view, chart, cur))
    lines += _unlisted(prefix, *_sessions(view, cur))
    return lines


def _buckets(
    view: dict[str, Any], chart: rw.ChartWindow, cur: rq.Scan
) -> tuple[Flat, Flat]:
    old: Flat = {"bucket_unit": view["bucket_unit"]}
    new: Flat = {"bucket_unit": chart.unit}
    for bucket in view["buckets"]:
        if not bucket["tokens"]:
            continue
        key = f"buckets.{_utc(bucket['start']).isoformat()}"
        old[f"{key}.tokens"] = bucket["tokens"]
        for model, tokens in bucket["by_model"].items():
            old[f"{key}.by_model.{model}"] = tokens
    for bar, sums in zip(chart.bars, cur.bars, strict=True):
        if not sums.models:
            continue
        key = f"buckets.{bar.start.isoformat()}"
        new[f"{key}.tokens"] = sum(m.tokens for m in sums.models.values())
        for model, part in sums.models.items():
            new[f"{key}.by_model.{model}"] = part.tokens
    return old, new


def _sessions(view: dict[str, Any], cur: rq.Scan) -> tuple[Flat, Flat]:
    old: Flat = {"count": len(view["sessions"])}
    new: Flat = {"count": len(cur.sessions)}
    for row in view["sessions"]:
        key = f"sessions.{row['session_id']}"
        old[f"{key}.tokens"] = row["tokens"]
        old[f"{key}.cost"] = row["cost"] or 0.0
        old[f"{key}.runs"] = row["runs"]
        old[f"{key}.unpriced_requests"] = row["unpriced_requests"]
        old[f"{key}.agents"] = "|".join(r["agent"] or "@main" for r in row["by_agent"])
        old[f"{key}.subagents"] = _names(row["agents"])
    for session in cur.sessions:
        key = f"sessions.{session.id}"
        new[f"{key}.tokens"] = session.tokens
        new[f"{key}.cost"] = session.cost or 0.0
        new[f"{key}.runs"] = session.runs
        new[f"{key}.unpriced_requests"] = session.unpriced.requests
        new[f"{key}.agents"] = "|".join(session.agents)
        new[f"{key}.subagents"] = "|".join(
            sorted(a for a in session.agents if a != "@main")
        )
    return old, new


@pytest.mark.parametrize(
    "query", USAGE_QUERIES, ids=[q["file"].removesuffix(".json") for q in USAGE_QUERIES]
)
def test_review_numbers_equal_the_recorded_usage_answer(
    world: World, query: dict[str, Any]
) -> None:
    _fail_on(_compare(world, query), query["file"])


def test_the_demo_has_review_numbers_to_compare(world: World) -> None:
    """A guard against a comparison that passes because both sides are empty."""
    query = next(q for q in USAGE_QUERIES if q["file"] == "usage-30d-all.json")
    view = _json(DEMO, query["file"])["views"]["30d"]
    assert view["totals"]["requests"] == 3913
    assert view["totals"]["runs"] == 220
    assert view["totals"]["sessions"] == 71
    assert len(view["sessions"]) == 71
    assert len(view["by_agent"]) == 4
    now = _utc(view["end"])
    window = rw.review_window("30d", now, TZ, rq.oldest_request(world.conn, None))
    got = rq.scan(
        world.conn,
        world.prices,
        folders=None,
        start=window.start,
        end=window.end,
        tz=TZ,
        sessions=True,
    )
    assert got.total.requests == 3913
    assert got.total.runs == 220
    assert got.total.sessions == 71
    assert len(got.sessions) == 71
    assert got.total.unpriced.requests == 150
    assert rq.no_usage_sessions(world.conn, None, window.start, window.end) == 0
    assert {p.model for a in got.by_agent.values() for p in a.ran_pairs} >= {
        "claude-opus-5-5",
        "claude-fable-5-1",
    }


def test_partial_prior_windows_agree_with_the_old_missing_previous(
    world: World,
) -> None:
    """Old ``previous`` is null exactly when the new window says ``prior_partial``."""
    seen: set[bool] = set()
    for query in USAGE_QUERIES:
        view = _json(DEMO, query["file"])["views"][query["range"]]
        folders = _folders(world, query["query"]["project"][0])
        oldest = rq.oldest_request(world.conn, folders)
        window = rw.review_window(query["range"], _utc(view["end"]), TZ, oldest)
        partial = window.prior_partial or oldest is None
        assert (view["previous"] is None) == partial, query["file"]
        seen.add(partial)
    assert seen == {True, False}, "the demo should hold both cases"


def test_the_whole_days_rule_changes_only_the_prior_end(world: World) -> None:
    now = _utc(_json(DEMO, "usage-30d-all.json")["views"]["30d"]["end"])
    oldest = rq.oldest_request(world.conn, None)
    same = rw.review_window("30d", now, TZ, oldest, "same_time")
    whole = rw.review_window("30d", now, TZ, oldest, "whole_days")
    assert whole.prior_end == same.start
    assert whole.prior_end != same.prior_end
    assert same.prior_start is not None
    assert same.prior_end is not None
    assert whole.prior_start is not None
    assert whole.prior_end is not None
    a = rq.scan(
        world.conn,
        world.prices,
        folders=None,
        tz=TZ,
        start=same.prior_start,
        end=same.prior_end,
    )
    b = rq.scan(
        world.conn,
        world.prices,
        folders=None,
        tz=TZ,
        start=whole.prior_start,
        end=whole.prior_end,
    )
    assert b.total.requests > a.total.requests


# ---------------------------------------------------------------- consistency


@pytest.mark.parametrize("name", ["today", "7d", "30d"])
def test_bars_agents_and_models_add_up_to_the_total(
    world: World, name: ReviewRange
) -> None:
    now = _utc(_json(DEMO, "usage-30d-all.json")["views"]["30d"]["end"])
    oldest = rq.oldest_request(world.conn, None)
    window = rw.review_window(name, now, TZ, oldest)
    chart = rw.chart_window(name, now, TZ, oldest)
    got = rq.scan(
        world.conn,
        world.prices,
        folders=None,
        start=window.start,
        end=window.end,
        tz=TZ,
        bars=chart.bars,
        days=True,
    )
    total = got.total.cost
    assert total is not None
    assert sum(a.sums.cost or 0.0 for a in got.by_agent.values()) == pytest.approx(
        total
    )
    assert sum(m.sums.cost or 0.0 for m in got.by_model.values()) == pytest.approx(
        total
    )
    assert sum(
        m.cost or 0.0 for b in got.bars for m in b.models.values()
    ) == pytest.approx(total)
    assert sum(d.cost or 0.0 for d in got.by_day.values()) == pytest.approx(total)
    assert sum(m.requests for b in got.bars for m in b.models.values()) == (
        got.total.requests
    )
    assert sum(
        m.kinds.output for b in got.bars for m in b.models.values()
    ) == pytest.approx(got.total.cost_by_kind.output)
    shares = [a.share for a in got.by_agent.values() if a.share is not None]
    assert sum(shares) == pytest.approx(1.0, abs=1e-9)
    for model in got.by_model.values():
        if model.sums.cost is not None:
            assert model.share == pytest.approx(model.sums.cost / total, abs=1e-12)


# ---------------------------------------------------------------- the long build


LONG_FIELDS = (
    "input",
    "output",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "thinking",
    "requests",
    "runs",
    "sessions",
    "cost",
    "unpriced_requests",
)
LONG_RANGES: tuple[ReviewRange, ...] = ("30d", "90d", "12m", "all")


def _truth_flat(prefix: str, row: dict[str, Any] | None) -> Flat:
    if row is None:
        return {}
    return {f"{prefix}.{f}": row[f] for f in LONG_FIELDS}


def _sums_flat(prefix: str, sums: rq.Sums) -> Flat:
    flat: Flat = {f"{prefix}.{f}": getattr(sums, f) for f in LONG_FIELDS[:9]}
    flat[f"{prefix}.cost"] = sums.cost or 0.0
    flat[f"{prefix}.unpriced_requests"] = sums.unpriced.requests
    return flat


def _long_lines(world: World, name: str, rng: ReviewRange, truth: Any) -> list[str]:
    scope = f"truth-long.json:projects.{name}.{rng}"
    (found,) = (p for p in world.mapped if p.name == name)
    window_truth = _json(LONG, "truth-long.json")["windows"][rng]
    now = _utc(window_truth["end"])
    oldest = rq.oldest_request(world.conn, found.folders)
    window = rw.review_window(rng, now, TZ, oldest)
    lines: list[str] = []
    if rng == "all":
        lines += _unlisted(
            f"{scope}.",
            {"start": _utc(truth["start"])},
            {"start": window.start.replace(microsecond=0)},
        )
        assert window.prior_start is None
        assert truth["prior"] is None
    else:
        lines += _unlisted(
            f"{scope}.",
            {
                "start": _utc(window_truth["start"]),
                "prior_start": _utc(window_truth["prior_start"]),
                "prior_end": _utc(window_truth["prior_end"]),
            },
            {
                "start": window.start,
                "prior_start": window.prior_start,
                "prior_end": window.prior_end,
            },
        )
    cur = rq.scan(
        world.conn,
        world.prices,
        folders=found.folders,
        start=window.start,
        end=window.end,
        tz=TZ,
        days=True,
    )
    old: Flat = _truth_flat("current", truth["current"])
    new: Flat = _sums_flat("current", cur.total)
    if window.prior_start is not None and window.prior_end is not None:
        prior = rq.scan(
            world.conn,
            world.prices,
            folders=found.folders,
            start=window.prior_start,
            end=window.prior_end,
            tz=TZ,
        )
        old.update(_truth_flat("prior", truth["prior"]))
        new.update(_sums_flat("prior", prior.total))
    for model, row in truth["by_model"].items():
        old.update(_truth_flat(f"by_model.{model}", row))
    for model, model_sums in cur.by_model.items():
        new.update(_sums_flat(f"by_model.{model}", model_sums.sums))
    for agent, row in truth["by_agent"].items():
        old.update(_truth_flat(f"by_agent.{agent}", row))
    for agent, agent_sums in cur.by_agent.items():
        new.update(_sums_flat(f"by_agent.{agent}", agent_sums.sums))
    for day, row in truth["by_day"].items():
        old.update(_truth_flat(f"by_day.{day}", row))
    for day, day_sums in cur.by_day.items():
        new.update(_sums_flat(f"by_day.{day.isoformat()}", day_sums))
    lines += _unlisted(f"{scope}.", old, new)
    return lines


def _long_cases() -> list[tuple[str, ReviewRange]]:
    truth = _json(LONG, "truth-long.json")
    return [(name, rng) for name in truth["projects"] for rng in LONG_RANGES]


@pytest.mark.parametrize(
    ("name", "rng"), _long_cases(), ids=[f"{n}-{r}" for n, r in _long_cases()]
)
def test_long_ranges_equal_the_long_truth(
    long_world: World, name: str, rng: ReviewRange
) -> None:
    truth = _json(LONG, "truth-long.json")["projects"][name][rng]
    _fail_on(_long_lines(long_world, name, rng, truth), f"{name} {rng}")


def test_the_long_truth_holds_what_the_demo_lacks(long_world: World) -> None:
    """A guard: the long build has a year of history that the demo does not."""
    truth = _json(LONG, "truth-long.json")["projects"]["Tidewater reporting"]
    assert truth["all"]["current"]["requests"] > 30000
    assert truth["12m"]["prior"]["requests"] > 0
    oldest = rq.oldest_request(long_world.conn, None)
    assert oldest is not None
    assert oldest < datetime(2025, 10, 1, tzinfo=UTC)
    now = datetime(2026, 10, 30, 22, 0, tzinfo=UTC)
    chart = rw.chart_window("all", now, TZ, oldest)
    assert chart.bars[0].holds_oldest
    assert len(chart.bars) >= 13
    # The newest page of a 12 month chart holds the 12 month window.
    twelve = rw.chart_window("12m", now, TZ, oldest)
    assert twelve.has_earlier is True  # the oldest request is in September 2025
    assert rw.chart_window("12m", now, TZ, oldest, 1).has_earlier is False


def test_a_chart_window_sums_to_its_range(long_world: World) -> None:
    """The legend total over the newest chart window equals the range's total."""
    now = datetime(2026, 10, 30, 22, 0, tzinfo=UTC)
    oldest = rq.oldest_request(long_world.conn, None)
    for rng in ("90d", "12m", "all"):
        name: ReviewRange = rng  # type: ignore[assignment]
        window = rw.review_window(name, now, TZ, oldest)
        chart = rw.chart_window(name, now, TZ, oldest)
        assert (chart.start, chart.end) == (window.start, window.end)
        got = rq.scan(
            long_world.conn,
            long_world.prices,
            folders=None,
            start=chart.start,
            end=chart.end,
            tz=TZ,
            bars=chart.bars,
            days=True,
        )
        assert got.total.cost is not None
        in_bars = sum(m.cost or 0.0 for b in got.bars for m in b.models.values())
        assert in_bars == pytest.approx(got.total.cost)
        assert sum(m.requests for b in got.bars for m in b.models.values()) == (
            got.total.requests
        )
        first_day = min(got.by_day)
        assert first_day >= chart.start.astimezone(rw.ZoneInfo(TZ)).date()
        assert max(got.by_day) <= date(2026, 10, 30)


def test_the_session_list_pages_over_a_year(long_world: World) -> None:
    """Fifty rows a page, newest first, joined across pages with no repeat."""
    now = datetime(2026, 10, 30, 22, 0, tzinfo=UTC)
    oldest = rq.oldest_request(long_world.conn, None)
    window = rw.review_window("all", now, TZ, oldest)
    rows = rq.scan(
        long_world.conn,
        long_world.prices,
        folders=None,
        start=window.start,
        end=window.end,
        tz=TZ,
        now=now,
        sessions=True,
    ).sessions
    assert len(rows) > SESSION_PAGE
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        page, cursor = rq.page_sessions(rows, cursor)
        seen += [r.id for r in page]
        pages += 1
        if cursor is None:
            break
    assert seen == [r.id for r in rows]
    assert len(set(seen)) == len(seen)
    assert pages == -(-len(rows) // SESSION_PAGE)
    keys = [r.sort_key for r in rows]
    assert keys == sorted(keys, reverse=True)

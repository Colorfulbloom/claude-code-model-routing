#!/usr/bin/env python3
"""Record the old app's answers on fixture builds as JSON oracle files.

Run from the repo root with the system Python:

    /usr/bin/python3 app/oracle/record.py [--only usage|live|long|settings]

Usage part. It builds the demo set into a temp folder outside the repo, builds a
context with dashboard/server.py fixture_context, and calls the old
api_usage.usage and api_usage.api_projects in process. The output goes to
app/fixtures/oracle/demo/.

Live part. It builds each live_flow scenario (busy, many, unlinked, empty) with
tests/fixtures/live_flow/build_flow.py, and for every sampled clock time T it
rewrites session.json "now", builds a fresh fixture context and calls the old
api_live.live in process. A reduced projection of each answer goes to
app/fixtures/oracle/live/<scenario>/at-<T>.json. The old pin check for each agent
of the session goes to <scenario>/pincheck.json, at the scenario clock.

Long part. It builds the 400-day demo with app/oracle/long_demo.py into a temp
folder and sums the generator's own request list per project, window, model,
agent type and local day. The output goes to app/fixtures/oracle/demo-long/.

Settings part (M4). It builds the demo into a temp folder and calls the old
api_settings.settings in process for each listed project, then copies each of the
122 folders of tests/fixtures/resolution to a temp folder (the repo's git root sits
above the originals) and calls it once on each copy. The answer minus its rules and
models tables goes to app/fixtures/oracle/settings/demo/<project>.json and
resolution/<folder>.json. --settings-out writes somewhere else, for the byte-stability
test. A temp path in a payload is replaced by /work/settings, and the manifest says so.

No server starts and no port opens. Python 3.9 standard library only. The old code
is imported and run, never changed.

Same inputs give the same bytes. Temp build folders are replaced by /work/demo or
/work/<scenario> in every payload (also in the encoded folder names), keys are
sorted and no timestamp is written.
"""

import argparse
import datetime as dt
import importlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import zoneinfo
from collections.abc import Callable
from pathlib import Path
from typing import Any

import long_demo

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "app" / "fixtures" / "oracle" / "demo"
BUILD_SCRIPT = REPO / "tests" / "fixtures" / "demo" / "build_demo.py"
NOW = "2026-10-30T18:00"
TZ = "America/New_York"
FAKE_ROOT = "/work/demo"
RANGES = ("today", "7d", "30d")
OLD_COMMIT_REF = "ad32428"
HTTP_OK = 200

LIVE_OUT = REPO / "app" / "fixtures" / "oracle" / "live"
FLOW_SCRIPT = REPO / "tests" / "fixtures" / "live_flow" / "build_flow.py"
SCENARIOS = ("busy", "many", "unlinked", "empty")
PROJECT_KEY = "tidewater-reporting"
START = dt.datetime(2026, 10, 30, 22, 10, 0, tzinfo=dt.timezone.utc)
EDGE_SECONDS = (59, 61)
SESSION_KEYS = ("started", "last_request", "active")
RUN_KEYS = (
    "run_id",
    "route_key",
    "agent",
    "label_n",
    "model",
    "effort",
    "parent",
    "parent_known",
    "dispatch_order",
    "together",
    "started",
    "last_request",
    "active_at",
    "state",
    "rounds",
    "tokens",
    "cost",
)
MINUTE_KEYS = ("start", "tokens", "by_model", "cache_read")
REQUEST_KEYS = (
    "id",
    "ts",
    "route_key",
    "model",
    "effort",
    "tokens",
    "cache_read",
    "output",
    "cost",
)

DOC = (
    "Each entry is {path, reason, plan_ref}. path names a payload field, for "
    "example usage-30d-all.json:views.30d.totals.cost. reason says why the new "
    "answer may differ from the old one. plan_ref points to the plan section "
    "that allows it."
)


def _git(*args: str) -> str:
    """Run git in the repo and return its trimmed output."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def _write(path: Path, text: str) -> None:
    """Write text as UTF-8 with LF line ends."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _dumps(payload: Any) -> str:  # noqa: ANN401
    """Return the stable JSON text of a payload."""
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _old(name: str) -> Any:  # noqa: ANN401
    """Import one module of the old dashboard."""
    path = str(REPO / "dashboard")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(name)


def _record_usage() -> None:
    """Build the demo, ask the old usage routes, write the demo files."""
    api_usage = _old("api_usage")
    resolve = _old("resolve")
    server = _old("server")
    transcripts = _old("transcripts")

    tmp = Path(tempfile.mkdtemp(prefix="oracle-")).resolve()
    try:
        folder = tmp / "demo"
        subprocess.run(  # noqa: S603
            [sys.executable, str(BUILD_SCRIPT), str(folder), "--now", NOW, "--tz", TZ],
            check=True,
            capture_output=True,
        )
        ctx = server.fixture_context(
            str(folder), None, None, resolve.load_rules(), resolve.load_agent_fields()
        )
        real = sorted({str(folder), str(folder.absolute())}, key=len, reverse=True)
        encoded = sorted(
            {transcripts.sanitize(item) for item in real}, key=len, reverse=True
        )
        fake_encoded = transcripts.sanitize(FAKE_ROOT)

        def clean(text: str) -> str:
            for item in real:
                text = text.replace(item, FAKE_ROOT)
            for item in encoded:
                text = text.replace(item, fake_encoded)
            return text

        status, listing = api_usage.api_projects(ctx, {})
        if status != HTTP_OK:
            msg = f"api_projects answered {status}"
            raise RuntimeError(msg)
        scopes = [row["key"] for row in listing["projects"]] + ["all"]

        files: dict[str, str] = {"projects.json": clean(_dumps(listing))}
        queries: list[dict[str, Any]] = [
            {"call": "api_projects", "file": "projects.json", "query": {}}
        ]
        for scope in scopes:
            query = {"project": [scope]}
            status, payload = api_usage.usage(ctx, query)
            if status != HTTP_OK:
                msg = f"usage answered {status} for {scope}"
                raise RuntimeError(msg)
            for rng in RANGES:
                part = dict(payload)
                part["views"] = {rng: payload["views"][rng]}
                name = f"usage-{rng}-{scope}.json"
                files[name] = clean(_dumps(part))
                queries.append(
                    {"call": "usage", "file": name, "query": query, "range": rng}
                )

        truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
        files["truth.json"] = clean(_dumps(truth))

        OUT.mkdir(parents=True, exist_ok=True)
        allowed = OUT / "allowed-differences.json"
        if not allowed.is_file():
            _write(allowed, _dumps({"_doc": DOC, "differences": []}))
        keep = {*files, "allowed-differences.json", "manifest.json"}
        for old in OUT.glob("*.json"):
            if old.name not in keep:
                old.unlink()
        for name, text in files.items():
            _write(OUT / name, text)

        version = sys.version_info
        manifest = {
            "build_args": {
                "now": NOW,
                "script": "tests/fixtures/demo/build_demo.py",
                "tz": TZ,
            },
            "files": sorted(keep),
            "old_commit": _git(
                "log", "-1", "--format=%H", OLD_COMMIT_REF, "--", "dashboard"
            ),
            "python": f"{version[0]}.{version[1]}.{version[2]}",
            "queries": queries,
        }
        _write(OUT / "manifest.json", _dumps(manifest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


LIVE_DOC = (
    "Each entry is {id, fields, reason, plan_ref}. fields names the old /api/live "
    "fields (or the new timeline fields) whose values may differ from the recorded "
    "answer. reason says why. plan_ref points to the plan section that allows it. "
    "Any difference outside these entries fails."
)
LIVE_ALLOWED = [
    {
        "id": "runs-not-started",
        "fields": ["runs[]", "running"],
        "reason": (
            "Runs not started at T appear on the new timeline. The old answer at T "
            "never lists one, because Live at T is Live at now."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 1",
    },
    {
        "id": "state-words",
        "fields": ["runs[].state", "session.active"],
        "reason": (
            'The old "done" reads as finished, and the new run states are working, '
            "idle and finished."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 2",
    },
    {
        "id": "label-numbers",
        "fields": ["runs[].label_n", "runs[].together"],
        "reason": (
            "label_n follows first-seen order and never renames a shown row, so the "
            'old route\'s "scout" with one run and "scout 1" with two both read '
            '"scout" here. together counts the whole session.'
        ),
        "plan_ref": (
            "m2-build.md section 6, allowed difference 3, as amended in section 12"
        ),
    },
    {
        "id": "buckets-whole-session",
        "fields": ["minutes[]", "axis"],
        "reason": (
            "Buckets cover the whole session at bucket_seconds. Only the minutes "
            "inside the old 30-minute window are compared, and only when "
            "bucket_seconds is 60."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 4",
    },
    {
        "id": "model-ids",
        "fields": [
            "runs[].model_display",
            "requests[].model_display",
            "agents[].model_display",
            "by_model[].display_name",
        ],
        "reason": "Model names are ids. The old model_display is not compared.",
        "plan_ref": "m2-build.md section 6, allowed difference 5",
    },
    {
        "id": "last-minute-bucket",
        "fields": ["last_minute"],
        "reason": (
            'In the page-at-T oracle, "last minute" is the bucket that holds T, '
            "not a rolling 60 seconds."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 6",
    },
    {
        "id": "requests-at-t",
        "fields": ["runs[].tokens", "runs[].cost", "totals.tokens", "totals.cost"],
        "reason": (
            "The old answer counts every request stamped at or before T, and the flow "
            "builds put a request on most minute marks. The page-at-T oracle takes the "
            "requests the old answer lists at exactly T out of its numbers first."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 6",
    },
    {
        "id": "bucket-aligned-t",
        "fields": ["runs[].tokens", "runs[].cost", "totals.tokens", "totals.cost"],
        "reason": (
            "Cumulative numbers are bucket-granular. The page-at-T oracle compares "
            "per-run and total tokens and cost only at a T that falls on a bucket "
            "boundary. States, parents and rounds are compared at every T."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 4",
    },
    {
        "id": "shared-route-keys",
        "fields": ["runs[].tokens", "runs[].cost"],
        "reason": (
            "Several runs can share one route key, and the old answer does not say "
            "which run a request at exactly T belongs to. The page-at-T oracle skips "
            "per-run numbers for a shared route key only when a request at exactly T "
            "carries that key, and checks every other run."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 6",
    },
    {
        "id": "half-open-bucket",
        "fields": ["axis", "buckets[]"],
        "reason": (
            "A bucket holds [start, end), so a request stamped exactly on a boundary "
            "falls in the bucket that starts there, and the picker leaves it out at "
            "that T. The old answer counts ts <= T."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 4",
    },
    {
        "id": "no-session-list-oracle",
        "fields": ["/api/live/sessions"],
        "reason": (
            "The old route has no session list across projects, so "
            "/api/live/sessions has no oracle. Its tests use crafted stores."
        ),
        "plan_ref": "m2-build.md section 6, allowed difference 7",
    },
]


def _stamp(moment: dt.datetime) -> str:
    """Return the file-name stamp of a UTC moment, YYYYMMDDTHHMMSSZ."""
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Return the named keys of a row, keeping the old field names."""
    return {key: row.get(key) for key in keys}


def _project(status: int, answer: dict[str, Any]) -> dict[str, Any]:
    """Reduce one old /api/live answer to the fields the new tests compare."""
    if status != HTTP_OK:
        msg = f"live answered {status}"
        raise RuntimeError(msg)
    session = answer["session"]
    out: dict[str, Any] = {
        "running": [row["session_id"] for row in answer["running"]],
        "session": None,
        "session_gone": answer["session_gone"],
    }
    if session is None:
        return out
    out["session"] = {"id": session["session_id"], **_pick(session, SESSION_KEYS)}
    out["totals"] = session["totals"]
    out["last_minute"] = session["last_minute"]
    out["minutes"] = [_pick(row, MINUTE_KEYS) for row in session["minutes"]]
    out["runs"] = [_pick(row, RUN_KEYS) for row in session["runs"]]
    out["requests"] = [_pick(row, REQUEST_KEYS) for row in session["requests"]]
    return out


def _sample_times(
    clock: dt.datetime, edge_times: list[dt.datetime]
) -> list[dt.datetime]:
    """Every whole minute from the start to the clock, plus edge times in the window."""
    times = {START + dt.timedelta(minutes=n) for n in range(_minutes(clock) + 1)}
    for moment in edge_times:
        if START <= moment <= clock:
            times.add(moment)
    return sorted(times)


def _minutes(clock: dt.datetime) -> int:
    """Whole minutes from the session start to the clock."""
    return int((clock - START).total_seconds() // 60)


class _Live:
    """One scenario build with the old modules, asked at many clock times."""

    def __init__(self, folder: Path, flow: dict[str, Any]) -> None:
        """Keep the build folder and its flow.json."""
        self.server = _old("server")
        self.resolve = _old("resolve")
        self.api_live = _old("api_live")
        self.folder = folder
        self.flow = flow
        self.rules = self.resolve.load_rules()
        self.fields = self.resolve.load_agent_fields()
        self.session_path = folder / "session.json"
        self.session = json.loads(self.session_path.read_text(encoding="utf-8"))

    def context(self, moment: dt.datetime) -> Any:  # noqa: ANN401
        """Set the fixture clock to the moment and build a fresh context."""
        self.session["now"] = moment.isoformat()
        _write(self.session_path, _dumps(self.session))
        return self.server.fixture_context(
            str(self.folder), None, None, self.rules, self.fields
        )

    def ask(self, ctx: Any) -> tuple[int, dict[str, Any]]:  # noqa: ANN401
        """Call the old live route for the scenario's session."""
        query = {"project": [PROJECT_KEY], "session": [self.flow["session"]]}
        return self.api_live.live(ctx, query)

    def pincheck(self, ctx: Any, answer: dict[str, Any]) -> dict[str, Any]:  # noqa: ANN401
        """Run the old pin check per agent key of the session, as api_usage does."""
        api_usage = _old("api_usage")
        pincheck = _old("pincheck")
        projects = _old("projects")
        listing = projects.load(ctx)
        project = listing.find(PROJECT_KEY)
        entries = api_usage._entries(ctx, listing, project)
        catalog = ctx.rules["models"]
        by_key: dict[str, list[dict[str, Any]]] = {}
        for run in answer["session"]["runs"]:
            by_key.setdefault(run["route_key"], []).append(
                {
                    "run_id": run["run_id"],
                    "model": run["model"],
                    "effort": run["effort"],
                    "requests": None,
                }
            )
        out: dict[str, Any] = {}
        for key in sorted(by_key):
            pairs: dict[tuple[Any, Any], int] = {}
            for run in by_key[key]:
                pair = (run["model"], run["effort"])
                pairs[pair] = pairs.get(pair, 0) + 1
            ran_with = [
                {"model": m, "effort": e, "runs": n} for (m, e), n in pairs.items()
            ]
            out[key] = pincheck.check_agent(
                entries, key, ran_with, by_key[key], catalog
            )
        return {"entries_count": len(entries), "agents": out}


def _record_scenario(
    scenario: str, tmp: Path
) -> tuple[dict[str, str], list[str], dict[str, Any]]:
    """Build one scenario and return its files, sampled stamps and build info."""
    transcripts = _old("transcripts")
    folder = tmp / scenario
    subprocess.run(  # noqa: S603
        [sys.executable, str(FLOW_SCRIPT), str(folder), scenario],
        check=True,
        capture_output=True,
    )
    flow = json.loads((folder / "flow.json").read_text(encoding="utf-8"))
    clock = dt.datetime.fromisoformat(flow["now"])
    fake_root = f"/work/{scenario}"
    real = sorted({str(folder), str(folder.absolute())}, key=len, reverse=True)
    encoded = sorted(
        {transcripts.sanitize(item) for item in real}, key=len, reverse=True
    )
    fake_encoded = transcripts.sanitize(fake_root)

    def clean(text: str) -> str:
        for item in real:
            text = text.replace(item, fake_root)
        for item in encoded:
            text = text.replace(item, fake_encoded)
        return text

    live = _Live(folder, flow)
    # The scenario clock first: its runs give the edge times (59 s and 61 s after
    # each run's last request) for busy.
    ctx = live.context(clock)
    status, final = live.ask(ctx)
    _project(status, final)
    edge_times: list[dt.datetime] = []
    if scenario == "busy" and final["session"] is not None:
        for run in final["session"]["runs"]:
            last = dt.datetime.fromisoformat(run["last_request"])
            edge_times += [last + dt.timedelta(seconds=n) for n in EDGE_SECONDS]
    files: dict[str, str] = {}
    stamps: list[str] = []
    for moment in _sample_times(
        clock, [t.astimezone(dt.timezone.utc) for t in edge_times]
    ):
        status, answer = live.ask(live.context(moment))
        stamp = _stamp(moment)
        body = {"at": moment.isoformat(), **_project(status, answer)}
        files[f"at-{stamp}.json"] = clean(_dumps(body))
        stamps.append(stamp)
    ctx = live.context(clock)
    status, answer = live.ask(ctx)
    _project(status, answer)
    check: dict[str, Any]
    if answer["session"] is not None:
        check = {"at": clock.isoformat(), **live.pincheck(ctx, answer)}
    else:
        check = {"at": clock.isoformat(), "entries_count": 0, "agents": {}}
    files["pincheck.json"] = clean(_dumps(check))
    info = {
        "args": [scenario],
        "clock": flow["now"],
        "runs": len(flow["runs"]),
        "session": flow["session"],
    }
    return files, stamps, info


def _record_live() -> None:
    """Build each live_flow scenario, ask the old live route, write the files."""
    tmp = Path(tempfile.mkdtemp(prefix="oracle-")).resolve()
    try:
        scenarios: dict[str, Any] = {}
        listing: dict[str, list[str]] = {}
        for scenario in SCENARIOS:
            files, stamps, info = _record_scenario(scenario, tmp)
            target = LIVE_OUT / scenario
            target.mkdir(parents=True, exist_ok=True)
            for old in target.glob("at-*.json"):
                # Only stale at-files go. new-end.json belongs to oracle/timelines.py.
                if old.name not in files:
                    old.unlink()
            for name, text in files.items():
                _write(target / name, text)
            scenarios[scenario] = {**info, "sampled": stamps}
            listing[scenario] = sorted(files)
        _write(
            LIVE_OUT / "allowed-differences.json",
            _dumps({"_doc": LIVE_DOC, "differences": LIVE_ALLOWED}),
        )
        version = sys.version_info
        manifest = {
            "build_args": {
                "script": "tests/fixtures/live_flow/build_flow.py",
                "usage": "build_flow.py <out> <scenario>",
            },
            "files": {
                **listing,
                "top": ["allowed-differences.json", "manifest.json"],
            },
            "old_commit": _git("rev-parse", "HEAD"),
            "project": PROJECT_KEY,
            "python": f"{version[0]}.{version[1]}.{version[2]}",
            "scenarios": scenarios,
        }
        _write(LIVE_OUT / "manifest.json", _dumps(manifest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


LONG_OUT = REPO / "app" / "fixtures" / "oracle" / "demo-long"
TOKEN_FIELDS = (
    "input",
    "output",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "thinking",
)
LONG_RANGES = (("30d", 30), ("90d", 90), ("12m", 365))
ALL = "all"
STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
UTC = dt.timezone.utc


def _wall(tz: dt.tzinfo, day: dt.date, clock: dt.time) -> dt.datetime:
    """Local moment for a date and wall clock time, as the old _wall builds it."""
    naive = dt.datetime.combine(day, clock)
    return naive.replace(tzinfo=tz).astimezone(UTC).astimezone(tz)


def _window(
    tz: dt.tzinfo, now_local: dt.datetime, days: int
) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    """Return (start, prior_start, prior_end) as the old _window does."""
    today = now_local.date()
    one = dt.timedelta
    start = _wall(tz, today - one(days=days - 1), dt.time.min)
    prior_start = _wall(tz, today - one(days=2 * days - 1), dt.time.min)
    prior_end = _wall(tz, today - one(days=days), now_local.time())
    return start, prior_start, prior_end


def _demo_module() -> Any:  # noqa: ANN401
    """Import the demo builder module."""
    path = str(REPO / "tests" / "fixtures" / "demo")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("build_demo")


def _stamp_utc(moment: dt.datetime) -> str:
    """Return a moment as an ISO UTC string."""
    return moment.astimezone(UTC).strftime(STAMP_FORMAT)


def _totals(
    reqs: list[dict[str, Any]],
    cost_of: Any,  # noqa: ANN401
) -> dict[str, Any]:
    """Sum one request group with the same fields and rules as the builder's _truth."""
    costs = [c for c in (cost_of(r) for r in reqs) if c is not None]
    out: dict[str, Any] = {f: sum(r[f] for r in reqs) for f in TOKEN_FIELDS}
    out["requests"] = len(reqs)
    out["runs"] = len({(r["session"], r["run"]) for r in reqs if r["run"] is not None})
    out["sessions"] = len({r["session"] for r in reqs})
    out["cost"] = math.fsum(costs)
    out["unpriced_requests"] = len(reqs) - len(costs)
    return out


def _agent_types(folder: Path) -> dict[tuple[str, str], str]:
    """Map (session, run) to the agentType in each run's meta file."""
    found: dict[tuple[str, str], str] = {}
    pattern = "config/projects/*/*/subagents/agent-*.meta.json"
    for meta in sorted(folder.glob(pattern)):
        session = meta.parent.parent.name
        run = meta.name[len("agent-") : -len(".meta.json")]
        data = json.loads(meta.read_text(encoding="utf-8"))
        found[(session, run)] = str(data.get("agentType") or "@unnamed")
    return found


def _groups(
    reqs: list[dict[str, Any]],
    key: Any,  # noqa: ANN401
) -> dict[str, list[dict[str, Any]]]:
    """Group requests by a key function, keeping request order inside a group."""
    out: dict[str, list[dict[str, Any]]] = {}
    for req in reqs:
        out.setdefault(key(req), []).append(req)
    return out


def _long_truth(
    truth: dict[str, Any], requests: list[dict[str, Any]], folder: Path
) -> dict[str, Any]:
    """Sum the long build's request list per project, range, model, agent and day."""
    build_demo = _demo_module()
    tz = zoneinfo.ZoneInfo(long_demo.TZ)
    now_local = dt.datetime.fromisoformat(long_demo.NOW).replace(tzinfo=tz)
    now_utc = now_local.astimezone(UTC)
    agents = _agent_types(folder)

    def agent_of(req: dict[str, Any]) -> str:
        if req["run"] is None:
            return "@main"
        return agents.get((req["session"], req["run"]), "@unnamed")

    def model_of(req: dict[str, Any]) -> str:
        return str(req["model"])

    def local_day(req: dict[str, Any]) -> str:
        return req["ts"].astimezone(tz).date().isoformat()

    windows: dict[str, Any] = {}
    bounds: dict[str, tuple[dt.datetime, dt.datetime, dt.datetime]] = {}
    for name, days in LONG_RANGES:
        start, prior_start, prior_end = _window(tz, now_local, days)
        bounds[name] = (start, prior_start, prior_end)
        windows[name] = {
            "end": _stamp_utc(now_utc),
            "prior_end": _stamp_utc(prior_end),
            "prior_start": _stamp_utc(prior_start),
            "start": _stamp_utc(start),
        }
    windows[ALL] = {"end": _stamp_utc(now_utc), "prior_end": None,
                    "prior_start": None, "start": None}  # fmt: skip

    projects: dict[str, Any] = {}
    for key, prof in build_demo.PROJECTS.items():
        if prof["name"] is None:
            continue
        mine = [r for r in requests if r["project"] == key]
        out: dict[str, Any] = {}
        ranges = [*LONG_RANGES, (ALL, 0)]
        for name, _days in ranges:
            entry: dict[str, Any] = {"prior": None}
            if name == ALL:
                cur = [r for r in mine if r["ts"] <= now_utc]
                if cur:
                    entry["start"] = _stamp_utc(min(r["ts"] for r in cur))
            else:
                start, prior_start, prior_end = bounds[name]
                cur = [r for r in mine if start <= r["ts"] <= now_utc]
                prior = [r for r in mine if prior_start <= r["ts"] <= prior_end]
                entry["prior"] = _totals(prior, build_demo.cost_of)
            entry["current"] = _totals(cur, build_demo.cost_of)
            keyers: tuple[tuple[str, Callable[[dict[str, Any]], str]], ...] = (
                ("by_model", model_of),
                ("by_agent", agent_of),
                ("by_day", local_day),
            )
            for field, fn in keyers:
                entry[field] = {
                    group: _totals(rows, build_demo.cost_of)
                    for group, rows in sorted(_groups(cur, fn).items())
                }
            out[name] = entry
        projects[prof["name"]] = out

    # Self-check: the 30d window must equal the build's own truth.json numbers.
    for name, row in truth["projects"].items():
        if projects[name]["30d"]["current"] != row:
            msg = f"30d sums for {name} differ from the build's truth.json"
            raise RuntimeError(msg)
    return {"projects": projects, "windows": windows}


def _record_long() -> None:
    """Build the long demo, sum its requests per window, write the demo-long files."""
    tmp = Path(tempfile.mkdtemp(prefix="oracle-")).resolve()
    try:
        folder = tmp / "demo-long"
        truth, requests = long_demo.build_long(str(folder))
        payload = _long_truth(truth, requests, folder)
        files = {
            "truth-30d.json": _dumps(truth),
            "truth-long.json": _dumps(payload),
        }
        LONG_OUT.mkdir(parents=True, exist_ok=True)
        keep = {*files, "manifest.json"}
        for old in LONG_OUT.glob("*.json"):
            if old.name not in keep:
                old.unlink()
        for name, text in files.items():
            _write(LONG_OUT / name, text)
        version = sys.version_info
        build_demo = _demo_module()
        manifest = {
            "build_args": {
                "history_days": long_demo.LONG_HISTORY_DAYS,
                "now": long_demo.NOW,
                "script": "tests/fixtures/demo/build_demo.py",
                "seed": build_demo.SEED,
                "seed_note": "build_demo.SEED is fixed, so the same build repeats",
                "tz": long_demo.TZ,
                "via": "app/oracle/long_demo.py build_long",
            },
            "files": sorted(keep),
            "old_commit": _git(
                "log", "-1", "--format=%H", OLD_COMMIT_REF, "--", "dashboard"
            ),
            "python": f"{version[0]}.{version[1]}.{version[2]}",
            "requests": len(requests),
        }
        _write(LONG_OUT / "manifest.json", _dumps(manifest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


SETTINGS_OUT = REPO / "app" / "fixtures" / "oracle" / "settings"
RESOLUTION = REPO / "tests" / "fixtures" / "resolution"
SETTINGS_ROOT = "/work/settings"
# Fields the differential does not compare and the old answer repeats per project: the
# rules table (every quote of every rule named) and the model display names.
SETTINGS_DROPPED = ("rules", "models")
SETTINGS_DOC = (
    "differences holds entries {id, kind, cases, count, reason, plan_ref}. kind is the "
    "label the comparison gives a difference, cases is '*' or the payloads it applies "
    "to, and count is how many differences of that kind the payloads hold. reason says "
    "why the new answer differs and plan_ref names the plan section that allows it. "
    "Any difference outside these entries fails. mappings holds the rules the "
    "comparison applies first. This file is written once and then edited by hand."
)


def _settings_answer(
    api_settings: Any,  # noqa: ANN401
    ctx: Any,  # noqa: ANN401
    query: dict[str, list[str]],
) -> dict[str, Any]:
    """Ask the old settings route and drop the fields nobody compares."""
    status, answer = api_settings.settings(ctx, query)
    if status != HTTP_OK:
        msg = f"settings answered {status} for {query}"
        raise RuntimeError(msg)
    return {k: v for k, v in answer.items() if k not in SETTINGS_DROPPED}


def _clean_settings(text: str, real: list[str]) -> str:
    """Replace every real build folder spelling in a payload with the placeholder."""
    for item in real:
        text = text.replace(item, SETTINGS_ROOT)
    return text


def _settings_demo(
    tmp: Path, old: dict[str, Any]
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Ask the old settings route for each project of the demo build."""
    folder = tmp / "demo"
    subprocess.run(  # noqa: S603
        [sys.executable, str(BUILD_SCRIPT), str(folder), "--now", NOW, "--tz", TZ],
        check=True,
        capture_output=True,
    )
    ctx = old["server"].fixture_context(
        str(folder), None, None, old["rules"], old["fields"]
    )
    real = sorted({str(folder), str(folder.absolute())}, key=len, reverse=True)
    files: dict[str, str] = {}
    cases: list[dict[str, Any]] = []
    for project in old["projects"].load(ctx).projects:
        answer = _settings_answer(old["api_settings"], ctx, {"project": [project.key]})
        name = f"demo/{project.key}.json"
        files[name] = _clean_settings(_dumps(answer), real)
        cases.append({"file": name, "kind": "demo", "project": project.key})
    return files, cases


def _settings_resolution(
    tmp: Path, old: dict[str, Any]
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Ask the old settings route for each resolver folder, on a copy of it.

    The folders sit under the repo's git root, so each is copied to a temp folder
    first. Nothing above the copy can then add a repo-root local settings file.
    """
    root = tmp / "resolution"
    real = sorted({str(root), str(root.absolute())}, key=len, reverse=True)
    files: dict[str, str] = {}
    cases: list[dict[str, Any]] = []
    for source in sorted(p for p in RESOLUTION.iterdir() if p.is_dir()):
        folder = root / source.name
        shutil.copytree(source, folder, symlinks=True)
        ctx = old["server"].fixture_context(
            str(folder), None, None, old["rules"], old["fields"]
        )
        answer = _settings_answer(old["api_settings"], ctx, {})
        name = f"resolution/{source.name}.json"
        files[name] = _clean_settings(_dumps(answer), real)
        cases.append({"file": name, "kind": "resolution", "folder": source.name})
    return files, cases


def _record_settings(out: Path = SETTINGS_OUT) -> None:
    """Record the old /api/settings answers into out.

    One payload per project of the demo build and one per resolver folder. The default
    out is app/fixtures/oracle/settings/.
    """
    old = {
        name: _old(name) for name in ("api_settings", "projects", "resolve", "server")
    }
    old["rules"] = old["resolve"].load_rules()
    old["fields"] = old["resolve"].load_agent_fields()
    tmp = Path(tempfile.mkdtemp(prefix="oracle-")).resolve()
    try:
        files, cases = _settings_demo(tmp, old)
        more_files, more_cases = _settings_resolution(tmp, old)
        files.update(more_files)
        cases += more_cases
        for sub in ("demo", "resolution"):
            (out / sub).mkdir(parents=True, exist_ok=True)
            for stale in (out / sub).glob("*.json"):
                if f"{sub}/{stale.name}" not in files:
                    stale.unlink()
        for name, text in files.items():
            _write(out / name, text)
        allowed = out / "allowed-differences.json"
        if not allowed.is_file():
            _write(
                allowed,
                _dumps({"_doc": SETTINGS_DOC, "differences": [], "mappings": []}),
            )
        version = sys.version_info
        manifest = {
            "build_args": {
                "demo_now": NOW,
                "demo_script": "tests/fixtures/demo/build_demo.py",
                "demo_tz": TZ,
                "resolution_folders": "tests/fixtures/resolution",
            },
            "cases": cases,
            "dropped_fields": list(SETTINGS_DROPPED),
            "files": sorted([*files, "allowed-differences.json", "manifest.json"]),
            "old_call": (
                "api_settings.settings(server.fixture_context(folder, None, None,"
                " rules, fields), query), in process, on a copy of each folder"
            ),
            "old_commit": _git(
                "log", "-1", "--format=%H", OLD_COMMIT_REF, "--", "dashboard"
            ),
            "path_placeholder": {
                "placeholder": SETTINGS_ROOT,
                "stands_for": (
                    "the temp folder the recorder built the demo or copied the"
                    " resolver folders into"
                ),
                "note": (
                    "Old display paths are relative to that folder, so a payload"
                    " rarely holds the placeholder. Any absolute temp path is"
                    " replaced at record time."
                ),
            },
            "python": f"{version[0]}.{version[1]}.{version[2]}",
        }
        _write(out / "manifest.json", _dumps(manifest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    """Run the chosen recorders. Return the exit code."""
    parser = argparse.ArgumentParser(description="Record the old app's answers.")
    parser.add_argument(
        "--only", choices=("usage", "live", "long", "settings"), default=None
    )
    parser.add_argument(
        "--settings-out",
        type=Path,
        default=SETTINGS_OUT,
        help="where the settings part writes (default app/fixtures/oracle/settings)",
    )
    args = parser.parse_args()
    if args.only in (None, "usage"):
        _record_usage()
    if args.only in (None, "live"):
        _record_live()
    if args.only in (None, "long"):
        _record_long()
    if args.only in (None, "settings"):
        _record_settings(args.settings_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

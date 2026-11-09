#!/usr/bin/env python3
"""Record the old app's answers on fixture builds as JSON oracle files.

Run from the repo root with the system Python:

    /usr/bin/python3 app/oracle/record.py [--only usage|live]

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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

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


def main() -> int:
    """Run the chosen recorders. Return the exit code."""
    parser = argparse.ArgumentParser(description="Record the old app's answers.")
    parser.add_argument("--only", choices=("usage", "live"), default=None)
    args = parser.parse_args()
    if args.only in (None, "usage"):
        _record_usage()
    if args.only in (None, "live"):
        _record_live()
    return 0


if __name__ == "__main__":
    sys.exit(main())

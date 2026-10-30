#!/usr/bin/env python3
"""Build the demo set: made-up settings, agents and generated transcripts.

    build_demo.py <out_dir> [--now ISO] [--tz NAME]

The committed files next to this script (config/, projects/, session.json) are
copied into out_dir, then transcripts are written under
out_dir/config/projects/<sanitize(out_dir/projects/<name>)>/. Transcripts are
never committed. out_dir/managed/ is an empty stand-in for the managed folder,
so a run on the set never reads the real one.

Same arguments give the same bytes. One seeded random.Random(39) drives every
choice and every id. Local times convert to UTC through the named zone.

Public functions:

    build(out_dir, now=None, tz_name="America/New_York") -> truth dict
    inputs_for(out_dir, project_name, rules) -> resolve.Inputs

The truth is an independent count of what the generator wrote, kept before any
duplicate rows. It does not use dashboard/prices.py or dashboard/usage.py.
Everything here is made up.
"""
import argparse
import datetime as dt
import json
import math
import os
import random
import shutil
import sys
import uuid
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, "dashboard"))

import collect  # noqa: E402
import resolve  # noqa: E402
import transcripts  # noqa: E402

DEFAULT_NOW = "2026-10-30T18:00"
DEFAULT_TZ = "America/New_York"
SEED = 39
UTC = dt.timezone.utc
WINDOW_DAYS = 30
HISTORY_DAYS = 62  # a little past the reader's 61-day cutoff, so old files exist

# Names the committed routing-dashboard.json lists, and the folder of each.
# quarry-notes has a transcript folder but no entry in the list and no folder.
PROJECTS = {
    "tidewater": {
        "name": "Tidewater reporting", "dir": "tidewater-reporting",
        "main_model": "claude-opus-5-5", "main_effort": "high",
        "days_active": 0.8, "sessions_per_day": (1, 3), "branch": "feature/quarter-close",
        "agents": {"builder": ("claude-fable-5-1", "medium"),
                   "reviewer": ("claude-sonnet-5-5", "xhigh"),
                   "scribe": ("claude-haiku-5-5", "high")},
    },
    "driftwood": {
        "name": "Driftwood", "dir": "driftwood",
        "main_model": "claude-opus-6-preview", "main_effort": "medium",
        "days_active": 0.35, "sessions_per_day": (1, 1), "branch": "main",
        "agents": {"reviewer": ("claude-sonnet-5-5", "high"),
                   "scribe": ("claude-haiku-5-5", "medium")},
    },
    "harbor-light": {
        "name": "Harbor Light", "dir": "harbor-light",
        "main_model": "claude-opus-5-5", "main_effort": "medium",
        "days_active": 0.25, "sessions_per_day": (1, 1), "branch": "main",
        "agents": {"reviewer": ("claude-sonnet-5-5", "high"),
                   "scribe": ("claude-haiku-5-5", "medium")},
        "idle_today": True,
    },
    "quarry-notes": {
        "name": None, "dir": "quarry-notes",
        "main_model": "claude-sonnet-5-5", "main_effort": "medium",
        "days_active": 0.15, "sessions_per_day": (1, 1), "branch": "main",
        "agents": {"scribe": ("claude-haiku-5-5", "medium")},
    },
}

# Per-request token means: (input, output, cache_read, cache_write).
PROFILE = {
    "claude-opus-5-5": (1800, 900, 28000, 6000),
    "claude-opus-6-preview": (1600, 800, 24000, 5000),
    "claude-fable-5-1": (2500, 1600, 40000, 9000),
    "claude-sonnet-5-5": (1500, 700, 18000, 4000),
    "claude-haiku-5-5": (900, 400, 6000, 1500),
}

# Standard list prices in USD per million tokens, copied by hand so the truth
# does not depend on the dashboard's price code. Order: input, cache write 5m,
# cache write 1h, cache read, output. claude-opus-6-preview is made up and has
# no rate. Haiku's higher tier starts at 100000 prompt tokens, which no demo
# request reaches (checked in cost_of).
RATES = {
    "claude-opus-5-5": (4, 5, 8, 0.20, 20),
    "claude-fable-5-1": (10, 12.50, 20, 0.25, 50),
    "claude-sonnet-5-5": (2, 2.50, 4, 0.10, 10),
    "claude-haiku-5-5": (0.10, 0.125, 0.20, 0.01, 0.50),
}
TIER_LIMIT = 100000


def _uuid(rng):
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def _jitter(rng, mean, lo=0.5, hi=1.6):
    return max(0, int(mean * rng.uniform(lo, hi)))


def _parse_now(now, zone):
    """Aware datetime in zone, from None, a datetime or an ISO string."""
    if now is None:
        now = DEFAULT_NOW
    if isinstance(now, str):
        now = dt.datetime.fromisoformat(now.replace("Z", "+00:00"))
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def _stamp(ts):
    """UTC timestamp text with millisecond digits."""
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (ts.microsecond // 1000)


def _request_tokens(rng, model, hit_bias):
    i, o, cr, cw = PROFILE[model]
    cr = _jitter(rng, cr * hit_bias)
    cw = _jitter(rng, cw)
    one_hour = int(cw * rng.choice([0, 0, 0.3]))
    out = _jitter(rng, o)
    thinking = int(out * rng.uniform(0.1, 0.5))
    return {"input": _jitter(rng, i), "output": out, "cache_read": cr,
            "cache_write_5m": cw - one_hour, "cache_write_1h": one_hour, "thinking": thinking}


def _usage(tok, output, thinking):
    return {
        "input_tokens": tok["input"],
        "output_tokens": output,
        "cache_creation_input_tokens": tok["cache_write_5m"] + tok["cache_write_1h"],
        "cache_read_input_tokens": tok["cache_read"],
        "cache_creation": {"ephemeral_5m_input_tokens": tok["cache_write_5m"],
                           "ephemeral_1h_input_tokens": tok["cache_write_1h"]},
        "output_tokens_details": {"thinking_tokens": thinking},
        "service_tier": "standard", "speed": "standard", "inference_geo": "global",
    }


def _gen_requests(rng, start, now, cwd, sid, model, effort, branch, sidechain, count, hit_bias, ctx):
    """Rows and request records for one file. Stops before a row later than now."""
    rows, reqs = [], []
    t = start
    for _ in range(count):
        t = t + dt.timedelta(seconds=rng.randint(20, 240), milliseconds=rng.randint(0, 999))
        mid = "msg_" + _uuid(rng).hex[:24]
        rid = "req_" + _uuid(rng).hex[:24]
        tok = _request_tokens(rng, model, hit_bias)
        n_rows = rng.choice([1, 2, 2, 3])
        times = [t]
        for _k in range(n_rows - 1):
            times.append(times[-1] + dt.timedelta(milliseconds=rng.randint(20, 600)))
        if times[-1] > now:
            break
        for k, ts in enumerate(times):
            # A response grows as it streams: the last row carries the full count.
            out = tok["output"] if k == n_rows - 1 else max(1, tok["output"] * (k + 1) // n_rows)
            think = tok["thinking"] * out // tok["output"] if tok["output"] else 0
            rows.append({
                "type": "assistant", "timestamp": _stamp(ts), "cwd": cwd, "sessionId": sid,
                "gitBranch": branch, "isSidechain": sidechain, "effort": effort, "requestId": rid,
                "message": {"id": mid, "model": model, "role": "assistant",
                            "usage": _usage(tok, out, think),
                            "content": [{"type": "text", "text": "[content not stored]"}]},
            })
        reqs.append(dict(tok, ts=times[0], model=model, session=sid, run=ctx, project=None))
    return rows, reqs, t


def _write_lines(path, rows, mtime):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    os.utime(path, (mtime, mtime))


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=2) + "\n")


def cost_of(req):
    """USD for one request at standard prices, or None when the model has no rate."""
    rate = RATES.get(req["model"])
    if rate is None:
        return None
    prompt = req["input"] + req["cache_read"] + req["cache_write_5m"] + req["cache_write_1h"]
    if req["model"] == "claude-haiku-5-5" and prompt > TIER_LIMIT:
        raise ValueError("demo request above the Haiku tier limit")
    i, w5, w1, cr, o = rate
    return (req["input"] * i + req["cache_write_5m"] * w5 + req["cache_write_1h"] * w1
            + req["cache_read"] * cr + req["output"] * o) / 1e6


def _generate(rng, real_out, config_dir, now_utc, now_local, zone):
    """Write every transcript file. Returns the request records, in write order."""
    requests = []
    for key, prof in PROJECTS.items():
        cwd = os.path.join(real_out, "projects", prof["dir"])
        folder = os.path.join(config_dir, "projects", transcripts.sanitize(cwd))
        for day in range(HISTORY_DAYS, -1, -1):
            if prof.get("idle_today") and day == 0:
                continue
            d = now_local.date() - dt.timedelta(days=day)
            if rng.random() > prof["days_active"] and day != 0:
                continue
            if d.weekday() >= 5 and day != 0 and rng.random() < 0.7:
                continue
            for _s in range(rng.randint(*prof["sessions_per_day"])):
                sid = str(_uuid(rng))
                hour, minute = rng.randint(8, 17), rng.randint(0, 59)
                start = dt.datetime.combine(d, dt.time(hour, minute), tzinfo=zone).astimezone(UTC)
                if day == 0:
                    start = now_utc - dt.timedelta(hours=rng.randint(1, 6))
                n_main = rng.randint(6, 28)
                rows, reqs, _t = _gen_requests(rng, start, now_utc, cwd, sid, prof["main_model"],
                                               prof["main_effort"], prof["branch"], False, n_main, 1.0, None)
                for r in reqs:
                    r["project"] = key
                requests.extend(reqs)
                if rows:
                    _write_lines(os.path.join(folder, sid + ".jsonl"), rows,
                                 _epoch(rows[-1]["timestamp"]))
                for aname, (amodel, aeffort) in prof["agents"].items():
                    runs = rng.choice([0, 1, 1, 2]) if aname != "builder" else rng.choice([0, 1, 2, 3])
                    for _r in range(runs):
                        aid = _uuid(rng).hex[:12]
                        astart = start + dt.timedelta(seconds=rng.randint(60, 1800))
                        arows, areqs, _t = _gen_requests(
                            rng, astart, now_utc, cwd, sid, amodel, aeffort, prof["branch"], True,
                            rng.randint(4, 22), 0.6 if aname == "scribe" else 1.1, aid)
                        tool_id = "toolu_" + _uuid(rng).hex[:20]
                        if not arows:
                            continue
                        for r in areqs:
                            r["project"] = key
                        requests.extend(areqs)
                        base = os.path.join(folder, sid, "subagents", "agent-" + aid)
                        mtime = _epoch(arows[-1]["timestamp"])
                        _write_lines(base + ".jsonl", arows, mtime)
                        _write_json(base + ".meta.json", {
                            "agentType": aname, "description": "demo run", "parentAgentId": None,
                            "spawnDepth": 1, "toolUseId": tool_id})
                        os.utime(base + ".meta.json", (mtime, mtime))
    return requests


def _epoch(stamp):
    return dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC).timestamp()


def _truth(requests, win_start, now_utc):
    out = {}
    for key, prof in PROJECTS.items():
        if prof["name"] is None:
            continue
        mine = [r for r in requests if r["project"] == key and win_start <= r["ts"] <= now_utc]
        costs = [c for c in (cost_of(r) for r in mine) if c is not None]
        out[prof["name"]] = {
            "input": sum(r["input"] for r in mine),
            "output": sum(r["output"] for r in mine),
            "cache_read": sum(r["cache_read"] for r in mine),
            "cache_write_5m": sum(r["cache_write_5m"] for r in mine),
            "cache_write_1h": sum(r["cache_write_1h"] for r in mine),
            "thinking": sum(r["thinking"] for r in mine),
            "requests": len(mine),
            "runs": len({(r["session"], r["run"]) for r in mine if r["run"] is not None}),
            "sessions": len({r["session"] for r in mine}),
            "cost": math.fsum(costs),
            "unpriced_requests": len(mine) - len(costs),
        }
    return out


def _copy_committed(real_out):
    for name in ("config", "projects"):
        shutil.copytree(os.path.join(HERE, name), os.path.join(real_out, name))
    shutil.copyfile(os.path.join(HERE, "session.json"), os.path.join(real_out, "session.json"))
    os.makedirs(os.path.join(real_out, "managed"))
    # Project paths in the list are relative to the set. Make them absolute.
    path = os.path.join(real_out, "config", "routing-dashboard.json")
    with open(path, encoding="utf-8") as fh:
        listing = json.load(fh)
    for entry in listing["projects"]:
        entry["path"] = os.path.join(real_out, *entry["path"].split("/"))
    _write_json(path, listing)


def build(out_dir, now=None, tz_name=DEFAULT_TZ):
    """Build the set into out_dir and return the truth dict (also truth.json).

    The five paths the set owns inside out_dir are replaced, so a second build
    into the same folder leaves no stale transcripts.
    """
    real_out = os.path.realpath(out_dir)
    os.makedirs(real_out, exist_ok=True)
    for name in ("config", "projects", "managed"):
        shutil.rmtree(os.path.join(real_out, name), ignore_errors=True)
    for name in ("session.json", "truth.json"):
        if os.path.lexists(os.path.join(real_out, name)):
            os.remove(os.path.join(real_out, name))

    zone = ZoneInfo(tz_name)
    now_local = _parse_now(now, zone)
    now_utc = now_local.astimezone(UTC)
    win_start = dt.datetime.combine(now_local.date() - dt.timedelta(days=WINDOW_DAYS - 1),
                                    dt.time(0, 0), tzinfo=zone).astimezone(UTC)

    _copy_committed(real_out)
    rng = random.Random(SEED)
    requests = _generate(rng, real_out, os.path.join(real_out, "config"), now_utc, now_local, zone)

    truth = {
        "window": {"start": win_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "end": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "tz": tz_name},
        "projects": _truth(requests, win_start, now_utc),
    }
    _write_json(os.path.join(real_out, "truth.json"), truth)
    return truth


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def inputs_for(out_dir, project_name, rules):
    """resolve.Inputs for one listed project of a built set.

    Mirrors resolve.load_fixture, but the project comes from the list in
    config/routing-dashboard.json, and nothing reads the real managed folder,
    shell or ~/.claude. The shell comes from session.json:shell_env.
    """
    root = os.path.realpath(out_dir)
    listing = _read_json(os.path.join(root, "config", "routing-dashboard.json"))
    paths = {p["name"]: p["path"] for p in listing["projects"]}
    if project_name not in paths:
        raise KeyError("no project named %r in the list" % project_name)
    session = _read_json(os.path.join(root, "session.json"))
    collected = collect.collect(
        config_dir=os.path.join(root, "config"),
        project_dir=paths[project_name],
        managed_dir=os.path.join(root, "managed"),
        shell_env=dict(session.get("shell_env") or {}),
        rules=rules)
    return resolve.Inputs(collected=collected, flags=[], cli_settings=None,
                          plan=listing.get("plan"), home=None, root=root,
                          shell_label=resolve.LABEL_SHELL)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the demo set.")
    parser.add_argument("out_dir")
    parser.add_argument("--now", default=DEFAULT_NOW, help="demo clock, local time, ISO (default %(default)s)")
    parser.add_argument("--tz", default=DEFAULT_TZ, help="zone name (default %(default)s)")
    args = parser.parse_args(argv)
    truth = build(args.out_dir, args.now, args.tz)
    print("built %s (%d projects in the truth)" % (os.path.realpath(args.out_dir), len(truth["projects"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

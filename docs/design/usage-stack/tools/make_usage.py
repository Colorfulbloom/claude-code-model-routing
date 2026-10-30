#!/usr/bin/env python3
"""Write made-up transcript-shaped JSONL for the demo projects, 30 days, with the exact
field paths from usage-data-facts.md. Deterministic (seeded). Nothing here is real.
Layout: usage-set/<cwd-dashed>/<session>.jsonl and <session>/subagents/agent-<id>.jsonl + .meta.json
"""
import json, os, random, uuid, datetime as dt, sys
R3 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(R3, "usage-set")
random.seed(39)
NOW = dt.datetime(2026, 10, 30, 18, 0, 0)  # demo clock, UTC-4; rows are written in UTC like real transcripts
PROJECTS = {
  "tidewater":   {"cwd": "/Users/demo/Projects/clients/tidewater-reporting", "main_model": "claude-opus-5-5", "main_effort": "high", "days_active": 0.8, "sessions_per_day": (1, 3),
                  "agents": {"builder": ("claude-fable-5-1", "medium"), "reviewer": ("claude-sonnet-5-5", "xhigh"), "scribe": ("claude-haiku-5-5", "high")}, "branch": "feature/quarter-close"},
  "driftwood":   {"cwd": "/Users/demo/Projects/driftwood", "main_model": "claude-opus-6-preview", "main_effort": "medium", "days_active": 0.35, "sessions_per_day": (1, 1),
                  "agents": {"reviewer": ("claude-sonnet-5-5", "high"), "scribe": ("claude-haiku-5-5", "medium")}, "branch": "main"},
  "harbor-light":{"cwd": "/Users/demo/Projects/harbor-light", "main_model": "claude-opus-5-5", "main_effort": "medium", "days_active": 0.25, "sessions_per_day": (1, 1),
                  "agents": {"reviewer": ("claude-sonnet-5-5", "high"), "scribe": ("claude-haiku-5-5", "medium")}, "branch": "main"},
}
# per-request token profile by model: (input, output, cache_read, cache_write) means
PROFILE = {"claude-opus-5-5": (1800, 900, 28000, 6000), "claude-opus-6-preview": (1600, 800, 24000, 5000),
           "claude-fable-5-1": (2500, 1600, 40000, 9000), "claude-sonnet-5-5": (1500, 700, 18000, 4000), "claude-haiku-5-5": (900, 400, 6000, 1500)}

def dashed(cwd): return cwd.replace("/", "-")
def jitter(m, lo=0.5, hi=1.6): return max(0, int(m * random.uniform(lo, hi)))

def usage(model, hit_bias=1.0):
    i, o, cr, cw = PROFILE[model]
    cr = jitter(cr * hit_bias); cw = jitter(cw)
    one_h = int(cw * random.choice([0, 0, 0.3])); five = cw - one_h
    out = jitter(o)
    return {"input_tokens": jitter(i), "output_tokens": out, "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr,
            "cache_creation": {"ephemeral_5m_input_tokens": five, "ephemeral_1h_input_tokens": one_h},
            "output_tokens_details": {"thinking_tokens": int(out * random.uniform(0.1, 0.5))},
            "service_tier": "standard", "speed": "standard", "inference_geo": "us"}

def row(ts, cwd, sid, model, effort, branch, sidechain, u, mid, rid):
    return {"type": "assistant", "timestamp": (ts + dt.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "cwd": cwd, "sessionId": sid, "gitBranch": branch,
            "isSidechain": sidechain, "effort": effort, "requestId": rid,
            "message": {"id": mid, "model": model, "role": "assistant", "usage": u, "content": [{"type": "text", "text": "[content not stored]"}]}}

def write_rows(path, rows_):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        for r in rows_: fh.write(json.dumps(r) + "\n")

def gen_requests(start, cwd, sid, model, effort, branch, sidechain, n, hit_bias=1.0):
    rows_ = []; t = start
    for _ in range(n):
        t += dt.timedelta(seconds=random.randint(20, 240))
        mid = "msg_" + uuid.uuid4().hex[:24]; rid = "req_" + uuid.uuid4().hex[:24]
        u = usage(model, hit_bias)
        # one response lands as 2 or 3 rows with the same message.id and identical usage (the dedupe trap)
        for _k in range(random.choice([1, 2, 2, 3])):
            rows_.append(row(t, cwd, sid, model, effort, branch, sidechain, u, mid, rid))
    return rows_, t

index = []
for key, P in PROJECTS.items():
    pdir = os.path.join(OUT, dashed(P["cwd"]))
    for day in range(62, -1, -1):
        if key == "harbor-light" and day == 0: continue  # idle today, for the "No usage in this range" state
        d = (NOW - dt.timedelta(days=day)).date()
        if random.random() > P["days_active"] and day != 0: continue
        if d.weekday() >= 5 and random.random() < 0.7: continue
        for s in range(random.randint(*P["sessions_per_day"])):
            sid = str(uuid.uuid4()); start = dt.datetime.combine(d, dt.time(random.randint(8, 17), random.randint(0, 59)))
            if day == 0: start = NOW - dt.timedelta(hours=random.randint(1, 6))
            n_main = random.randint(6, 28)
            rows_, t = gen_requests(start, P["cwd"], sid, P["main_model"], P["main_effort"], P["branch"], False, n_main)
            write_rows(os.path.join(pdir, sid + ".jsonl"), rows_)
            agents_here = []
            for aname, (amodel, aeffort) in P["agents"].items():
                for _r in range(random.choice([0, 1, 1, 2]) if aname != "builder" else random.choice([0, 1, 2, 3])):
                    aid = uuid.uuid4().hex[:12]
                    astart = start + dt.timedelta(seconds=random.randint(60, 1800))
                    arows, _ = gen_requests(astart, P["cwd"], sid, amodel, aeffort, P["branch"], True, random.randint(4, 22), hit_bias=0.6 if aname == "scribe" else 1.1)
                    write_rows(os.path.join(pdir, sid, "subagents", "agent-%s.jsonl" % aid), arows)
                    json.dump({"agentType": aname, "description": "demo run", "parentAgentId": None, "spawnDepth": 1, "toolUseId": "toolu_" + uuid.uuid4().hex[:20]},
                              open(os.path.join(pdir, sid, "subagents", "agent-%s.meta.json" % aid), "w"))
                    agents_here.append(aname)
            index.append({"project": key, "session": sid, "start": start.isoformat(), "agents": agents_here})
json.dump(index, open(os.path.join(OUT, "_index.json"), "w"), indent=1)
print("sessions", len(index))

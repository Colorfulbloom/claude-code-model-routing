#!/usr/bin/env python3
"""Build a made-up transcript world for the Live page's dispatch canvas.

    build_flow.py <out_dir> <scenario>

Scenarios: busy, many, empty, unlinked (see README.md). The demo set is built into
out_dir first (build_demo.build, default clock), then one newer session is added to the
Tidewater reporting transcript folder, so it is the project's latest session. The built
session.json gets the scenario's clock ("now", UTC), which the Live page and the route read
instead of the real clock. flow.json beside it lists the scenario's clock, session id and
runs (name, agent type, run id, agent id).

Rows are compact JSON written the way Claude Code writes them: assistant rows with
message.id, model, usage, stop_reason and tool_use blocks, user rows for tool results,
dispatch links (toolUseResult {"status": "async_launched", "agentId": <child id>}) and
resumes (origin {"kind": "coordinator"} or {"kind": "peer", "from": <agent id>}). Children
live in <session>/subagents/agent-<id>.jsonl with agent-<id>.meta.json {"agentType": ...}.

Same arguments give the same bytes: one seeded random.Random(SEED) drives every choice
and every id, and every time is an offset from START. Everything here is made up.
"""
import argparse
import datetime as dt
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "demo"))

import build_demo  # noqa: E402

UTC = dt.timezone.utc
SEED = 71
PROJECT_DIR = "tidewater-reporting"
START = dt.datetime(2026, 10, 30, 22, 10, 0, tzinfo=UTC)
MAIN = ("claude-opus-5-5", "high")

# Models the dashboard prices (dashboard/rules.json), one pair per agent type.
PAIRS = {
    "deep-reasoner": ("claude-opus-5-5", "high"),
    "designer": ("claude-fable-5-1", "high"),
    "scout": ("claude-haiku-5-5", "medium"),
    "fast-worker": ("claude-sonnet-5-5", "medium"),
    "judge": ("claude-opus-5-5", "medium"),
    "tech-writer": ("claude-sonnet-5-5", "high"),
    "verifier": ("claude-opus-5-5", "high"),
}

# Scenario clocks, as seconds after START.
CLOCKS = {"busy": 1800, "many": 3600, "empty": 480, "unlinked": 1800}
SCENARIOS = tuple(CLOCKS)

TOOLS = (("Read", {"file_path": "notes/plan.md"}), ("Grep", {"pattern": "totals"}),
         ("Bash", {"command": "ls reports"}), ("Edit", {"file_path": "reports/q3.md"}))
BRIEFS = ("Check the quarter totals.", "Draft the summary table.", "List the open items.",
          "Compare the two exports.", "Tidy the notes.")


def at(seconds):
    return START + dt.timedelta(seconds=seconds)


class Run:
    """One agent file (or the main session). Segments are rounds; the first starts at dispatch."""

    def __init__(self, kind, model, effort, until, finish=None, linked=True):
        self.kind = kind            # agent type, or None for the main session
        self.model, self.effort = model, effort
        self.finish = finish        # "end_turn", "handback" or None (still going)
        self.linked = linked
        self.id = None              # assigned by the builder
        self.segs = [{"start": None, "until": until, "finish": finish, "origin": None}]
        self.groups = []            # (ts, [children]) launched from this file

    def resume(self, start, until, finish=None, origin=None):
        self.segs.append({"start": start, "until": until, "finish": finish,
                          "origin": origin or {"kind": "coordinator"}})
        return self


def lead(kind, until, finish=None, linked=True):
    model, effort = PAIRS[kind]
    return Run(kind, model, effort, until, finish, linked)


def dispatch(parent, ts, children):
    """Parent launches the children together at ts. Each child starts one second later."""
    for child in children:
        seg = child.segs[0]
        seg["start"] = ts + dt.timedelta(seconds=1)
        if isinstance(seg["until"], (int, float)):
            seg["until"] = seg["start"] + dt.timedelta(seconds=seg["until"])
    parent.groups.append((ts, list(children)))
    return children


class Writer:
    def __init__(self, folder, sid, cwd, rng):
        self.folder, self.sid, self.cwd, self.rng = folder, sid, cwd, rng
        self.ids = set()

    def hex(self, n):
        while True:
            value = "%032x" % self.rng.getrandbits(128)
            value = value[:n]
            if value not in self.ids:
                self.ids.add(value)
                return value

    def row_base(self, run, ts, kind):
        row = {"type": kind, "timestamp": build_demo._stamp(ts), "cwd": self.cwd,
               "sessionId": self.sid, "gitBranch": "feature/quarter-close",
               "isSidechain": run.kind is not None}
        if run.kind is not None:
            row["agentId"] = run.id
        return row

    def assistant(self, run, ts, mid, blocks, stop):
        tok = build_demo._request_tokens(self.rng, run.model, 1.0)
        row = self.row_base(run, ts, "assistant")
        row["effort"] = run.effort
        row["requestId"] = "req_" + self.hex(24)
        row["message"] = {"id": mid, "model": run.model, "role": "assistant", "type": "message",
                          "stop_reason": stop,
                          "usage": build_demo._usage(tok, tok["output"], tok["thinking"]),
                          "content": blocks}
        return row

    def user(self, run, ts, content, **extra):
        row = self.row_base(run, ts, "user")
        row["message"] = {"role": "user", "content": content}
        row.update(extra)
        return row

    def tool_result(self, run, ts, tool_id, **extra):
        return self.user(run, ts, [{"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}], **extra)

    def build_file(self, run):
        """All rows of one file as (ts, seq, row), sorted."""
        events = []

        def add(ts, row):
            events.append((ts, len(events), row))

        for index, seg in enumerate(run.segs):
            start, until = seg["start"], seg["until"]
            origin = seg["origin"]
            if index == 0:
                head = self.user(run, start, "Brief: " + self.rng.choice(BRIEFS) if run.kind else
                                 "Help me close the quarter.")
            else:
                text = "The coordinator sent a message while you were working:\nFollow-up: " + self.rng.choice(BRIEFS)
                if origin["kind"] == "peer":
                    sender = origin["from"].id if isinstance(origin["from"], Run) else origin["from"]
                    origin = {"kind": "peer", "from": sender, "body": "Follow-up.", "senderTaskId": sender}
                    text = ("Another Claude session sent a message while you were working:\n"
                            "Follow-up: " + self.rng.choice(BRIEFS))
                head = self.user(run, start, text, isMeta=True, origin=origin)
            add(start, head)

            groups = [g for g in run.groups if start <= g[0] <= until]
            items = []
            t = start + dt.timedelta(seconds=6)
            while t < until:
                items.append((t, "tool", None))
                t += dt.timedelta(seconds=self.rng.randint(25, 55), milliseconds=self.rng.randint(0, 900))
            for g in groups:
                items.append((g[0], "launch", g[1]))
            items.sort(key=lambda item: item[0])
            if items and until - items[-1][0] < dt.timedelta(seconds=3) and items[-1][1] == "tool":
                items.pop()
            items.append((until, "final", None))

            for k, (ts, what, payload) in enumerate(items):
                last = k == len(items) - 1
                if what == "launch":
                    mid = "msg_" + self.hex(24)
                    for i, child in enumerate(payload):
                        t_ts = ts + dt.timedelta(milliseconds=i * 40)
                        tool_id = "toolu_" + self.hex(20)
                        block = {"type": "tool_use", "id": tool_id, "name": "Agent", "input": {
                            "subagent_type": child.kind, "description": "Run %s" % child.kind,
                            "prompt": "Brief.", "run_in_background": child.linked}}
                        add(t_ts, self.assistant(run, t_ts, mid, [block], "tool_use"))
                        if child.linked:
                            l_ts = ts + dt.timedelta(milliseconds=500 + i * 10)
                            add(l_ts, self.tool_result(run, l_ts, tool_id, toolUseResult={
                                "status": "async_launched", "agentId": child.id,
                                "description": "Run %s" % child.kind}))
                    continue
                mid = "msg_" + self.hex(24)
                if what == "final" and seg["finish"] == "end_turn":
                    add(ts, self.assistant(run, ts, mid, [{"type": "text", "text": "Done."}], "end_turn"))
                    continue
                if what == "final" and seg["finish"] == "handback":
                    tool_id = "toolu_" + self.hex(20)
                    add(ts, self.assistant(run, ts, mid, [{"type": "tool_use", "id": tool_id,
                                                         "name": "SubagentHandback",
                                                         "input": {"message": "Done."}}], "tool_use"))
                    r_ts = ts + dt.timedelta(milliseconds=400)
                    add(r_ts, self.tool_result(run, r_ts, tool_id))
                    continue
                name, args = self.rng.choice(TOOLS)
                tool_id = "toolu_" + self.hex(20)
                add(ts, self.assistant(run, ts, mid, [{"type": "tool_use", "id": tool_id,
                                                     "name": name, "input": args}], "tool_use"))
                if not last:
                    r_ts = ts + dt.timedelta(milliseconds=400)
                    add(r_ts, self.tool_result(run, r_ts, tool_id))
        events.sort(key=lambda e: (e[0], e[1]))
        return [e[2] for e in events]

    def write(self, path, rows):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        last = dt.datetime.strptime(rows[-1]["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
        os.utime(path, (last.timestamp(), last.timestamp()))
        return last.timestamp()


def walk(run):
    """The run, then every child below it, in launch order."""
    yield run
    for _ts, children in run.groups:
        for child in children:
            for found in walk(child):
                yield found


def world(scenario):
    """The main Run of a scenario, with its children attached."""
    now = at(CLOCKS[scenario])
    main = Run(None, MAIN[0], MAIN[1], now - dt.timedelta(seconds=10))
    if scenario == "empty":
        return main
    if scenario in ("busy", "unlinked"):
        dr = dispatch(main, at(120), [lead("deep-reasoner", at(1760))])[0]
        dispatch(dr, at(240), [lead("scout", 170, "end_turn"), lead("scout", 205, "end_turn")])
        dispatch(dr, at(720), [lead("fast-worker", 330, "handback"), lead("fast-worker", 365, "handback")])
        dispatch(dr, at(1200), [lead("judge", at(1782))])
        tw = dispatch(main, at(600), [lead("tech-writer", 270, "end_turn")])[0]
        tw.resume(at(1752), at(1788))
        if scenario == "unlinked":
            dispatch(main, at(1680), [lead("scout", at(1785), linked=False)])
        return main
    # many: two leads with their workers, a writer and a verifier.
    dr = dispatch(main, at(60), [lead("deep-reasoner", at(3580))])[0]
    des = dispatch(main, at(90), [lead("designer", at(3570))])[0]
    r = random.Random(SEED + 1)

    def crew(kinds, working=()):
        out = []
        for i, kind in enumerate(kinds):
            if i in working:
                out.append(lead(kind, None))   # until is set from the caller
            else:
                out.append(lead(kind, r.randint(120, 300), "handback" if kind != "scout" else "end_turn"))
        return out

    for ts, kinds in ((300, ("scout", "scout", "scout")), (800, ("fast-worker", "fast-worker")),
                      (1400, ("fast-worker", "fast-worker", "fast-worker")),
                      (2200, ("fast-worker", "judge"))):
        group = dispatch(dr, at(ts), crew(kinds))
        if ts == 300:
            # The first scout is woken by the designer (a peer, not its dispatcher) after it finished.
            group[0].resume(at(2000), at(2060), "end_turn", {"kind": "peer", "from": des})
    last = crew(("fast-worker", "fast-worker"), working=(1,))
    last[1].segs[0]["until"] = at(3585)
    dispatch(dr, at(3300), last)
    for ts, kinds in ((450, ("scout", "scout")), (1200, ("fast-worker", "fast-worker", "judge"))):
        dispatch(des, at(ts), crew(kinds))
    last = crew(("fast-worker", "fast-worker", "fast-worker"), working=(2,))
    last[2].segs[0]["until"] = at(3575)
    dispatch(des, at(3200), last)
    dispatch(main, at(600), [lead("tech-writer", 240, "end_turn")])
    dispatch(main, at(3300), [lead("verifier", at(3590))])
    return main


def build(out_dir, scenario):
    """Build the demo set and the scenario's session into out_dir. Returns the flow dict."""
    if scenario not in CLOCKS:
        raise ValueError("scenario must be one of %s" % ", ".join(SCENARIOS))
    real_out = os.path.realpath(out_dir)
    build_demo.build(real_out)
    rng = random.Random(SEED)
    cwd = os.path.join(real_out, "projects", PROJECT_DIR)
    folder = os.path.join(real_out, "config", "projects", build_demo.transcripts.sanitize(cwd))
    sid = "%032x" % rng.getrandbits(128)
    sid = "%s-%s-%s-%s-%s" % (sid[:8], sid[8:12], sid[12:16], sid[16:20], sid[20:])
    writer = Writer(folder, sid, cwd, rng)
    main = world(scenario)
    runs = list(walk(main))
    for run in runs[1:]:
        run.id = writer.hex(16)
    main.segs[0]["start"] = at(0)
    listing = []
    for run in runs:
        rows = writer.build_file(run)
        if run.kind is None:
            writer.write(os.path.join(folder, sid + ".jsonl"), rows)
        else:
            base = os.path.join(folder, sid, "subagents", "agent-" + run.id)
            mtime = writer.write(base + ".jsonl", rows)
            with open(base + ".meta.json", "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps({"agentType": run.kind}, separators=(",", ":")) + "\n")
            os.utime(base + ".meta.json", (mtime, mtime))
        listing.append({"name": run.kind or "main", "agent_id": run.id, "linked": run.linked,
                        "rounds": len(run.segs), "finish": run.segs[-1]["finish"]})
    now = at(CLOCKS[scenario]).isoformat()
    session_path = os.path.join(real_out, "session.json")
    with open(session_path, encoding="utf-8") as fh:
        session = json.load(fh)
    session["now"] = now
    with open(session_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(session, indent=2, sort_keys=True) + "\n")
    flow = {"scenario": scenario, "now": now, "session": sid, "folder": folder, "runs": listing}
    with open(os.path.join(real_out, "flow.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(flow, indent=2) + "\n")
    return flow


def main_cli(argv=None):
    parser = argparse.ArgumentParser(description="Build a Live dispatch canvas world.")
    parser.add_argument("out_dir")
    parser.add_argument("scenario", choices=SCENARIOS)
    args = parser.parse_args(argv)
    flow = build(args.out_dir, args.scenario)
    print("built %s: %s, %d runs, now %s" % (os.path.realpath(args.out_dir), flow["scenario"],
                                              len(flow["runs"]), flow["now"]))
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())

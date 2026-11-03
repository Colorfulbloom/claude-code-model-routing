"""Tests for the live route (dashboard/api_live.py) and Reader.read_folder.

Every world is built by the test in a temp folder under the helpers' temp base:
a fixture session.json with a fixed clock, a project list and transcript files
the test writes row by row. Nothing reads the real ~/.claude or a real
transcript. The route runs in this process on a Context built by
server.fixture_context.
"""
import datetime
import hashlib
import json
import os
import sys
import threading
import unittest
from unittest import mock

import helpers
import test_server as ts

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import api_live  # noqa: E402
import api_usage  # noqa: E402
import prices as prices_mod  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402
import transcripts  # noqa: E402
import usage  # noqa: E402

RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
PRICES = prices_mod.load_prices()
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 30, 22, 0, 30, tzinfo=UTC)  # 18:00:30 in New York
ZONE = "America/New_York"
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
S3 = "33333333-3333-4333-8333-333333333333"
SECRET_TEXT = "SECRET-MESSAGE-TEXT"
SECRET_TOOL = "SECRET-TOOL-INPUT"
SECRET_CWD = "/secret/cwd/path"
OPUS, SONNET, MYSTERY = "claude-opus-5-5", "claude-sonnet-5-5", "mystery-model"
TOP_KEYS = {"project", "server_time", "etag", "unchanged", "unreadable", "running",
            "session_gone", "session"}
SESSION_KEYS = {"session_id", "started", "branch", "last_request", "active", "totals",
                "last_minute", "minutes", "axis", "by_model", "agents", "requests"}


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def cost_of(model, input_tokens, output, cache_read, cache_write):
    """USD for one standard-speed, global-region request, from prices.json."""
    rate = PRICES["models"].get(model)
    if rate is None:
        return None
    return (input_tokens * rate["input"] + output * rate["output"]
            + cache_read * rate["cache_read"] + cache_write * rate["cache_write_5m"]) / 1000000.0


class World(object):
    """A fixture session with a fixed clock and three listed projects.

    app has transcripts, other has its own, and empty has no transcript folder.
    """

    def __init__(self, case, now=NOW):
        self.case = case
        self.root = ts.make_root("mr-live-")
        case.addCleanup(helpers.rmtree_force, self.root)
        self.now = now
        ts.write_json(os.path.join(self.root, "session.json"), {"now": now.isoformat(), "tz": ZONE})
        self.paths = {}
        entries = []
        for name in ("app", "other", "empty"):
            path = os.path.join(self.root, "projects", name)
            os.makedirs(path)
            self.paths[name] = os.path.realpath(path)
            entries.append({"name": name, "path": self.paths[name]})
        ts.write_json(os.path.join(self.root, "config", "routing-dashboard.json"), {"projects": entries})
        self.ctx = server.fixture_context(self.root, None, None, RULES, FIELDS)
        self.agent_files = {}

    def new_ctx(self):
        return server.fixture_context(self.root, None, None, RULES, FIELDS)

    @property
    def top(self):
        return os.path.join(self.root, "config", "projects")

    def folder(self, name="app"):
        return os.path.join(self.top, transcripts.sanitize(self.paths[name]))

    def file(self, session, run=None, agent_type=None, name="app"):
        base = self.folder(name)
        if run is None:
            return os.path.join(base, session + ".jsonl")
        sub = os.path.join(base, session, "subagents")
        os.makedirs(sub, exist_ok=True)
        if agent_type is not None:
            with open(os.path.join(sub, "agent-%s.meta.json" % run), "w", encoding="utf-8") as fh:
                json.dump({"agentType": agent_type}, fh)
        return os.path.join(sub, "agent-%s.jsonl" % run)

    def add(self, session, ago, mid, input_tokens=0, output=0, cache_read=0, cache_write=0,
            model=OPUS, effort="high", run=None, agent_type=None, branch="main", name="app",
            cwd=SECRET_CWD, request_id=True):
        """Append one assistant row, `ago` seconds before the fixed now (negative: after it)."""
        path = self.file(session, run, agent_type, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = {
            "type": "assistant", "timestamp": iso(self.now - datetime.timedelta(seconds=ago)),
            "cwd": cwd, "sessionId": session, "gitBranch": branch, "isSidechain": run is not None,
            "effort": effort,
            "message": {"id": "msg_" + mid, "model": model, "role": "assistant",
                        "usage": {"input_tokens": input_tokens, "output_tokens": output,
                                  "cache_creation_input_tokens": cache_write,
                                  "cache_read_input_tokens": cache_read,
                                  "cache_creation": {"ephemeral_5m_input_tokens": cache_write,
                                                     "ephemeral_1h_input_tokens": 0},
                                  "service_tier": "standard", "speed": "standard",
                                  "inference_geo": "global"},
                        "content": [{"type": "text", "text": SECRET_TEXT},
                                    {"type": "tool_use", "name": "Bash", "input": {"command": SECRET_TOOL}}]},
        }
        if request_id:
            row["requestId"] = "req_" + mid
        with open(path, "ab") as fh:
            fh.write((json.dumps(row) + "\n").encode("utf-8"))
        return path

    def ask(self, ctx=None, **query):
        return api_live.live(ctx or self.ctx, {k: [v] if isinstance(v, str) else v for k, v in query.items()})

    def live(self, project="app", **query):
        status, payload = self.ask(project=project, **query)
        self.case.assertEqual(status, 200, payload)
        return payload


class Contract(unittest.TestCase):
    def test_bad_requests_get_400(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)
        for query in ({}, {"project": ""}, {"project": ["app", "other"]}, {"project": "app", "session": ["a", "b"]},
                      {"project": "app", "etag": ["a", "b"]}, {"session": S1}):
            self.assertEqual(w.ask(**query), (400, {"error": "bad_request"}), query)

    def test_project_all_asks_to_pick(self):
        w = World(self)
        self.assertEqual(w.ask(project="all"), (400, {"error": "pick_project"}))

    def test_an_unknown_project_is_404(self):
        w = World(self)
        self.assertEqual(w.ask(project="nope"), (404, {"error": "unknown_project"}))

    def test_the_route_is_registered(self):
        self.assertIs(server.ROUTES["/api/live"], api_live.live)

    def test_the_shape_and_times_in_the_page_zone(self):
        w = World(self)
        w.add(S1, 10, "a", 100, 10)
        payload = w.live()
        self.assertEqual(set(payload), TOP_KEYS)
        self.assertEqual(set(payload["session"]), SESSION_KEYS)
        self.assertEqual(payload["server_time"], "2026-10-30T18:00:30-04:00")
        self.assertIs(payload["unchanged"], False)
        self.assertIsNone(payload["unreadable"])
        self.assertEqual(len(payload["etag"]), 16)
        int(payload["etag"], 16)
        self.assertEqual(payload["session"]["last_request"], "2026-10-30T18:00:20-04:00")
        self.assertEqual(set(payload["running"][0]),
                         {"session_id", "started", "branch", "last_request", "requests"})

    def test_a_project_with_no_transcript_folder_has_nothing_running(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)
        payload = w.live("empty", session=S1)
        self.assertEqual(payload["running"], [])
        self.assertIsNone(payload["session"])
        self.assertIsNone(payload["unreadable"])
        self.assertEqual(set(payload), TOP_KEYS)

    def test_a_project_only_sees_its_own_folder(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)
        w.add(S2, 20, "b", 5, 5, name="other")
        self.assertEqual([r["session_id"] for r in w.live("app")["running"]], [S1])
        self.assertEqual([r["session_id"] for r in w.live("other")["running"]], [S2])


class Running(unittest.TestCase):
    def test_the_thirty_minute_window_edges(self):
        w = World(self)
        w.add(S1, 29 * 60 + 59, "in", 1, 1)
        w.add(S2, 30 * 60 + 1, "out", 1, 1)
        payload = w.live()
        self.assertEqual([r["session_id"] for r in payload["running"]], [S1])
        self.assertEqual(api_live.RUNNING_MINUTES, 30)

    def test_a_session_runs_while_any_of_its_files_has_a_recent_request(self):
        w = World(self)
        w.add(S1, 3000, "old", 1, 1)
        w.add(S1, 100, "sub", 1, 1, run="r1", agent_type="explorer")
        payload = w.live()
        self.assertEqual([r["session_id"] for r in payload["running"]], [S1])
        self.assertEqual(payload["running"][0]["requests"], 2)

    def test_running_is_newest_request_first_with_start_and_branch(self):
        w = World(self)
        w.add(S1, 500, "a1", 1, 1, branch="feature/one")
        w.add(S1, 300, "a2", 1, 1, branch="feature/two")
        w.add(S2, 100, "b1", 1, 1, branch="main")
        w.add(S3, 900, "c1", 1, 1, branch="dev")
        running = w.live()["running"]
        self.assertEqual([r["session_id"] for r in running], [S2, S1, S3])
        by_id = {r["session_id"]: r for r in running}
        self.assertEqual(by_id[S1]["branch"], "feature/one")
        self.assertEqual(by_id[S1]["started"], "2026-10-30T17:52:10-04:00")
        self.assertEqual(by_id[S1]["last_request"], "2026-10-30T17:55:30-04:00")
        self.assertEqual(by_id[S1]["requests"], 2)

    def test_records_after_the_fixed_now_are_ignored(self):
        w = World(self)
        w.add(S1, 10, "now", 100, 10)
        w.add(S1, -10, "future", 5000, 5000)
        w.add(S2, -5, "only-future", 1, 1)
        payload = w.live()
        self.assertEqual([r["session_id"] for r in payload["running"]], [S1])
        self.assertEqual(payload["running"][0]["requests"], 1)
        self.assertEqual(payload["session"]["totals"]["tokens"], 110)
        self.assertEqual(payload["session"]["last_request"], "2026-10-30T18:00:20-04:00")
        self.assertEqual(len(payload["session"]["requests"]), 1)

    def test_nothing_running(self):
        w = World(self)
        w.add(S1, 3600, "old", 1, 1)
        payload = w.live()
        self.assertEqual(payload["running"], [])
        self.assertIsNone(payload["session"])
        self.assertIs(payload["session_gone"], False)


class SessionChoice(unittest.TestCase):
    def world(self):
        w = World(self)
        w.add(S1, 600, "a", 10, 10)
        w.add(S2, 100, "b", 20, 20)
        return w

    def test_the_newest_session_is_the_default(self):
        payload = self.world().live()
        self.assertEqual(payload["session"]["session_id"], S2)
        self.assertIs(payload["session_gone"], False)

    def test_an_asked_running_session_is_chosen(self):
        payload = self.world().live(session=S1)
        self.assertEqual(payload["session"]["session_id"], S1)
        self.assertIs(payload["session_gone"], False)
        self.assertEqual(payload["session"]["totals"]["tokens"], 20)

    def test_an_asked_session_that_left_falls_back_and_says_so(self):
        w = self.world()
        w.add(S3, 4000, "old", 1, 1)
        for gone in (S3, "44444444-4444-4444-8444-444444444444"):
            payload = w.live(session=gone)
            self.assertIs(payload["session_gone"], True)
            self.assertEqual(payload["session"]["session_id"], S2)

    def test_session_gone_with_nothing_running(self):
        w = World(self)
        payload = w.live(session=S1)
        self.assertIs(payload["session_gone"], True)
        self.assertIsNone(payload["session"])

    def test_active_flips_at_sixty_seconds(self):
        w = World(self)
        w.add(S1, 59, "a", 1, 1)
        w.add(S2, 60, "b", 1, 1)
        w.add(S3, 61, "c", 1, 1)
        self.assertIs(w.live(session=S1)["session"]["active"], True)
        self.assertIs(w.live(session=S2)["session"]["active"], False)
        self.assertIs(w.live(session=S3)["session"]["active"], False)
        self.assertEqual(api_live.ACTIVE_SECONDS, 60)


class Dedupe(unittest.TestCase):
    def test_the_larger_row_of_one_message_wins(self):
        w = World(self)
        w.add(S1, 30, "m", 100, 50)
        w.add(S1, 29, "m", 100, 300)
        w.add(S1, 28, "m", 100, 200)  # smaller output later: the larger row stays
        session = w.live()["session"]
        self.assertEqual(session["totals"]["requests"], 1)
        self.assertEqual(session["totals"]["output"], 300)
        self.assertEqual(session["totals"]["tokens"], 400)
        self.assertEqual(len(session["requests"]), 1)

    def test_totals_never_step_back_as_a_row_grows(self):
        w = World(self)
        w.add(S1, 30, "other", 10, 10)
        seen = []
        for output in (5, 40, 40, 90):
            w.add(S1, 20, "grows", 100, output)
            seen.append(w.live()["session"]["totals"]["tokens"])
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(seen[-1], 20 + 190)

    def test_a_row_with_only_a_request_id_dedupes_on_it(self):
        w = World(self)
        for output in (10, 30):
            path = w.add(S1, 10, "same", 1, output)
        with open(path, "rb") as fh:
            lines = fh.read().splitlines()
        rows = [json.loads(line) for line in lines]
        for row in rows:
            del row["message"]["id"]
        with open(path, "wb") as fh:
            fh.write(b"".join((json.dumps(r) + "\n").encode("utf-8") for r in rows))
        session = w.live()["session"]
        self.assertEqual(session["totals"]["requests"], 1)
        self.assertEqual(session["totals"]["output"], 30)


# A session the numbers tests share. Each row: (file, ago seconds, id, input, output, cache read,
# cache write, model, effort). Times are before the fixed now of 22:00:30 UTC (18:00:30 New York).
MAIN = [
    (3000, "m1", 100, 50, 1000, 0, OPUS, "high"),     # 17:10:30, before the 30 buckets
    (1500, "m2", 10, 20, 0, 200, SONNET, "high"),     # 17:35:30, bucket 4
    (90, "m3", 40, 10, 500, 0, OPUS, "high"),         # 17:59:00, bucket 28
    (60, "m4", 5, 5, 0, 0, OPUS, "high"),             # 17:59:30, bucket 28, exactly 60 s old
    (59, "m5", 7, 3, 0, 0, OPUS, "high"),             # 17:59:31, bucket 28, in the last minute
    (0, "m6", 1, 2, 3, 4, MYSTERY, "high"),           # 18:00:30, bucket 29, unpriced
]
EXPLORER = [  # agent type "explorer": opus/low twice, sonnet/medium once
    (200, "e1", 3, 3, 0, 0, SONNET, "medium"),
    (100, "e2", 4, 4, 0, 0, OPUS, "low"),
    (60, "e3", 5, 5, 0, 0, OPUS, "low"),              # last request exactly 60 s ago: not active
]
UNNAMED = [  # no meta file: unnamed. A tie between two pairs goes to the first seen
    (80, "u1", 2, 2, 0, 0, SONNET, "high"),
    (59, "u2", 2, 2, 0, 0, OPUS, "high"),             # last request 59 s ago: active
]


def build_numbers(w):
    for ago, mid, i, o, cr, cw, model, effort in MAIN:
        w.add(S1, ago, mid, i, o, cr, cw, model=model, effort=effort)
    for ago, mid, i, o, cr, cw, model, effort in EXPLORER:
        w.add(S1, ago, mid, i, o, cr, cw, model=model, effort=effort, run="r1", agent_type="explorer")
    for ago, mid, i, o, cr, cw, model, effort in UNNAMED:
        w.add(S1, ago, mid, i, o, cr, cw, model=model, effort=effort, run="r2")
    w.add(S1, -10, "future", 9999, 9999)  # after now: ignored
    return MAIN + EXPLORER + UNNAMED


def tokens_of(row):
    return row[2] + row[3] + row[4] + row[5]


FIRST_BUCKET = datetime.datetime(2026, 10, 30, 21, 31, 0, tzinfo=UTC)


def expected_buckets(rows):
    """{bucket index: {model: tokens}} for rows, worked out from their times."""
    out = {}
    for row in rows:
        at = NOW - datetime.timedelta(seconds=row[0])
        index = int((at - FIRST_BUCKET).total_seconds() // 60)
        if 0 <= index < 30:
            slot = out.setdefault(index, {})
            slot[row[6]] = slot.get(row[6], 0) + tokens_of(row)
    return out


class Numbers(unittest.TestCase):
    def setUp(self):
        self.w = World(self)
        self.rows = build_numbers(self.w)
        self.payload = self.w.live()
        self.session = self.payload["session"]

    def test_totals(self):
        totals = self.session["totals"]
        rows = self.rows
        self.assertEqual(totals["requests"], len(rows))
        self.assertEqual(totals["input"], sum(r[2] for r in rows))
        self.assertEqual(totals["output"], sum(r[3] for r in rows))
        self.assertEqual(totals["cache_read"], sum(r[4] for r in rows))
        self.assertEqual(totals["cache_write"], sum(r[5] for r in rows))
        self.assertEqual(totals["tokens"], sum(tokens_of(r) for r in rows))
        self.assertEqual(totals["unpriced_requests"], 1)
        priced = sum(cost_of(r[6], r[2], r[3], r[4], r[5]) for r in rows if r[6] != MYSTERY)
        self.assertAlmostEqual(totals["cost"], priced, places=9)
        denom = totals["cache_read"] + totals["cache_write"] + totals["input"]
        self.assertAlmostEqual(totals["hit_rate"], totals["cache_read"] / float(denom))

    def test_the_last_minute_excludes_exactly_sixty_seconds(self):
        last = self.session["last_minute"]
        inside = [r for r in self.rows if r[0] < 60]
        self.assertEqual(last["requests"], len(inside))
        self.assertEqual(last["tokens"], sum(tokens_of(r) for r in inside))
        self.assertEqual(last["unpriced_requests"], 1)
        self.assertAlmostEqual(
            last["cost"], sum(cost_of(r[6], r[2], r[3], r[4], r[5]) for r in inside if r[6] != MYSTERY), places=9)
        cr = sum(r[4] for r in inside)
        denom = cr + sum(r[5] for r in inside) + sum(r[2] for r in inside)
        self.assertAlmostEqual(last["hit_rate"], cr / float(denom))
        self.assertEqual(set(last), {"tokens", "cost", "unpriced_requests", "hit_rate", "requests"})

    def test_hit_rate_is_none_when_nothing_could_hit(self):
        w = World(self)
        w.add(S1, 10, "z", 0, 0)
        session = w.live()["session"]
        self.assertIsNone(session["totals"]["hit_rate"])
        self.assertIsNone(session["last_minute"]["hit_rate"])

    def test_thirty_minute_aligned_buckets(self):
        minutes = self.session["minutes"]
        self.assertEqual(len(minutes), api_live.BUCKETS)
        self.assertEqual(minutes[0]["start"], "2026-10-30T17:31:00-04:00")
        self.assertEqual(minutes[-1]["start"], "2026-10-30T18:00:00-04:00")
        starts = [datetime.datetime.fromisoformat(m["start"]) for m in minutes]
        for before, after in zip(starts, starts[1:]):
            self.assertEqual(after - before, datetime.timedelta(minutes=1))
        for m in minutes:
            self.assertEqual(m["tokens"], sum(m["by_model"].values()))
        self.assertEqual(minutes[4]["by_model"], {SONNET: 230})
        self.assertEqual(minutes[29]["by_model"], {MYSTERY: 10})
        self.assertEqual(minutes[0]["tokens"], 0)
        self.assertEqual(minutes[0]["by_model"], {})
        want = expected_buckets(self.rows)
        for index, m in enumerate(minutes):
            self.assertEqual(m["by_model"], want.get(index, {}), index)
        # the row 3000 s ago is before the first bucket, and the future row is in none
        self.assertNotIn(1000 + 150, [m["tokens"] for m in minutes])

    def test_the_axis_follows_the_tallest_bucket(self):
        tallest = max(m["tokens"] for m in self.session["minutes"])
        top, ticks = usage.token_ticks(tallest)
        self.assertEqual(self.session["axis"], {"top": top, "ticks": ticks})
        self.assertGreaterEqual(top, tallest)

    def test_by_model_covers_the_buckets_in_catalog_order_then_others(self):
        rows = self.session["by_model"]
        self.assertEqual([r["model"] for r in rows], [OPUS, SONNET, MYSTERY])
        self.assertEqual([r["display_name"] for r in rows], ["Opus 5.5", "Sonnet 5.5", MYSTERY])
        want = {}
        for slot in expected_buckets(self.rows).values():
            for model, tokens in slot.items():
                want[model] = want.get(model, 0) + tokens
        for r in rows:
            self.assertEqual(r["tokens"], want[r["model"]])
        self.assertNotIn(0, [r["tokens"] for r in rows])

    def test_agents(self):
        agents = {a["route_key"]: a for a in self.session["agents"]}
        self.assertEqual(set(agents), {"@main", "explorer", "@unnamed"})
        main, explorer, unnamed = agents["@main"], agents["explorer"], agents["@unnamed"]
        self.assertIsNone(main["agent"])
        self.assertEqual(explorer["agent"], "explorer")
        self.assertIsNone(unnamed["agent"])
        self.assertEqual((explorer["model"], explorer["model_display"], explorer["effort"]),
                         (OPUS, "Opus 5.5", "low"))
        self.assertEqual((unnamed["model"], unnamed["effort"]), (SONNET, "high"))
        self.assertEqual((main["model"], main["effort"]), (OPUS, "high"))
        self.assertEqual(explorer["tokens"], sum(tokens_of(r) for r in EXPLORER))
        self.assertEqual(explorer["requests"], 3)
        self.assertAlmostEqual(explorer["cost"], sum(cost_of(r[6], r[2], r[3], r[4], r[5]) for r in EXPLORER), places=9)
        self.assertEqual(main["requests"], len(MAIN))
        self.assertEqual(explorer["last_request"], "2026-10-30T17:59:30-04:00")
        self.assertEqual(set(main), {"route_key", "agent", "model", "model_display", "effort", "tokens",
                                     "cost", "requests", "last_request", "active"})

    def test_agents_are_ordered_by_cost_then_tokens(self):
        keys = [(-a["cost"], -a["tokens"]) for a in self.session["agents"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(self.session["agents"][0]["route_key"], "@main")

    def test_an_agent_is_active_within_sixty_seconds(self):
        agents = {a["route_key"]: a for a in self.session["agents"]}
        self.assertIs(agents["explorer"]["active"], False)  # 60 s ago
        self.assertIs(agents["@unnamed"]["active"], True)   # 59 s ago
        self.assertIs(agents["@main"]["active"], True)      # 0 s ago

    def test_a_tie_between_pairs_goes_to_the_first_seen(self):
        w = World(self)
        w.add(S1, 30, "t1", 1, 1, model=SONNET, effort="low")
        w.add(S1, 20, "t2", 1, 1, model=OPUS, effort="high")
        agent = w.live()["session"]["agents"][0]
        self.assertEqual((agent["model"], agent["effort"]), (SONNET, "low"))

    def test_the_latest_eight_come_newest_first_with_stable_ids(self):
        latest = self.session["requests"]
        self.assertEqual(len(latest), api_live.LATEST)
        times = [datetime.datetime.fromisoformat(r["ts"]) for r in latest]
        self.assertEqual(times, sorted(times, reverse=True))
        self.assertEqual(latest[0]["ts"], "2026-10-30T18:00:30-04:00")
        self.assertEqual(latest[0]["model"], MYSTERY)
        self.assertIsNone(latest[0]["cost"])
        self.assertEqual(latest[0]["tokens"], 10)
        self.assertEqual(latest[0]["output"], 2)
        self.assertEqual(latest[0]["route_key"], "@main")
        self.assertIsNone(latest[0]["agent"])
        self.assertEqual(len({r["id"] for r in latest}), api_live.LATEST)
        for r in latest:
            self.assertEqual(len(r["id"]), 12)
            int(r["id"], 16)
        self.assertEqual(latest[0]["id"], hashlib.sha256(json.dumps([0, "msg_m6"]).encode()).hexdigest()[:12])
        for r in latest[1:]:
            self.assertIsNotNone(r["cost"], r)
        again = self.w.live()["session"]["requests"]
        self.assertEqual([r["id"] for r in again], [r["id"] for r in latest])
        self.w.add(S1, 0.5, "newer", 1, 1)  # lands between the two newest rows
        newer = self.w.live()["session"]["requests"]
        self.assertEqual(newer[0]["id"], latest[0]["id"])
        self.assertEqual(newer[1]["tokens"], 2)
        self.assertEqual([r["id"] for r in newer[2:]], [r["id"] for r in latest[1:-1]])

    def test_a_priced_request_has_its_list_price_cost(self):
        row = [r for r in self.session["requests"] if r["model"] == OPUS][0]
        src = [r for r in self.rows if r[6] == OPUS and tokens_of(r) == row["tokens"] and r[3] == row["output"]][0]
        self.assertAlmostEqual(row["cost"], cost_of(OPUS, src[2], src[3], src[4], src[5]), places=9)
        self.assertEqual(row["model_display"], "Opus 5.5")
        self.assertEqual(row["effort"], "high")

    def test_started_and_branch_come_from_the_main_transcript(self):
        running = self.payload["running"][0]
        self.assertEqual(running["started"], "2026-10-30T17:10:30-04:00")
        self.assertEqual(running["branch"], "main")
        self.assertEqual(running["requests"], len(self.rows))
        self.assertEqual(self.session["started"], running["started"])
        self.assertEqual(self.session["branch"], "main")


class Etag(unittest.TestCase):
    def test_an_unchanged_answer_is_exactly_four_keys(self):
        w = World(self)
        w.add(S1, 10, "a", 100, 10)
        first = w.live()
        again = w.live(etag=first["etag"])
        self.assertEqual(again, {"project": "app", "server_time": first["server_time"],
                                 "etag": first["etag"], "unchanged": True})
        self.assertEqual(set(again), {"project", "server_time", "etag", "unchanged"})

    def test_the_etag_covers_everything_but_server_time_and_itself(self):
        w = World(self)
        w.add(S1, 10, "a", 100, 10)
        payload = w.live()
        body = {k: v for k, v in payload.items() if k not in ("server_time", "etag")}
        want = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        self.assertEqual(payload["etag"], want)

    def test_a_different_etag_gets_the_full_answer(self):
        w = World(self)
        w.add(S1, 10, "a", 100, 10)
        payload = w.live(etag="0000000000000000")
        self.assertEqual(set(payload), TOP_KEYS)
        self.assertIs(payload["unchanged"], False)

    def test_the_etag_changes_when_a_line_is_appended(self):
        w = World(self)
        w.add(S1, 10, "a", 100, 10)
        first = w.live()
        w.add(S1, 5, "b", 1, 1)
        second = w.live(etag=first["etag"])
        self.assertNotEqual(second["etag"], first["etag"])
        self.assertIs(second["unchanged"], False)
        self.assertEqual(second["session"]["totals"]["requests"], 2)

    def test_the_etag_ignores_the_clock_inside_one_minute_bucket_with_no_new_data(self):
        w = World(self)
        w.add(S1, 100, "a", 100, 10)
        first = w.live()
        later = World(self, now=NOW + datetime.timedelta(seconds=5))
        later.add(S1, 105, "a", 100, 10)
        self.assertEqual(later.live()["etag"], first["etag"])

    def test_an_unchanged_answer_for_no_session(self):
        w = World(self)
        first = w.live()
        again = w.live(etag=first["etag"])
        self.assertIs(again["unchanged"], True)


class ReadFolder(unittest.TestCase):
    def spy(self):
        original = transcripts.Reader._parse
        calls = []

        def spy(item, offset, records, stats, agent_type):
            calls.append((item.path, offset))
            return original(item, offset, records, stats, agent_type)

        return mock.patch.object(transcripts.Reader, "_parse", staticmethod(spy)), calls

    def test_it_parses_only_the_appended_bytes(self):
        w = World(self)
        path = w.add(S1, 100, "a", 1, 1)
        reader = transcripts.Reader(w.ctx.config_dir)
        first = reader.read_folder(os.path.basename(w.folder()), NOW)
        self.assertEqual(len(first.records), 1)
        self.assertIs(first.unreadable, False)
        size = os.path.getsize(path)
        w.add(S1, 50, "b", 2, 2)
        patch, calls = self.spy()
        with patch:
            second = reader.read_folder(os.path.basename(w.folder()), NOW)
        self.assertEqual(calls, [(path, size)])
        self.assertEqual(len(second.records), 2)
        self.assertNotEqual(first.signature, second.signature)
        with patch:
            third = reader.read_folder(os.path.basename(w.folder()), NOW)
        self.assertEqual(len(calls), 1, "an unchanged file is not parsed again")
        self.assertEqual(third.signature, second.signature)

    def test_it_leaves_another_folders_cache_and_files_found_alone(self):
        w = World(self)
        a = w.add(S1, 100, "a", 1, 1)
        b = w.add(S2, 100, "b", 1, 1, name="other")
        reader = transcripts.Reader(w.ctx.config_dir)
        reader.read(NOW)
        found = reader.files_found
        self.assertEqual(found, 2)
        os.remove(b)  # gone from disk, but it is not in the folder read_folder looks at
        w.add(S3, 10, "c", 1, 1)  # a new file in the asked folder
        folder = os.path.basename(w.folder())
        result = reader.read_folder(folder, NOW)
        self.assertEqual(len(result.records), 2)
        self.assertIn(b, reader._cache)
        self.assertEqual(reader.files_found, found)
        os.remove(a)
        result = reader.read_folder(folder, NOW)
        self.assertNotIn(a, reader._cache, "a file of this folder that is gone leaves the cache")
        self.assertEqual(len(result.records), 1)
        self.assertIn(b, reader._cache)
        self.assertEqual(reader.files_found, found)
        reader.read(NOW)
        self.assertNotIn(b, reader._cache, "a full read still evicts it")

    def test_a_missing_folder_is_empty_not_unreadable(self):
        w = World(self)
        reader = transcripts.Reader(w.ctx.config_dir)
        result = reader.read_folder("no-such-folder", NOW)
        self.assertEqual((result.records, result.unreadable), ([], False))

    def test_a_folder_that_cannot_be_listed_is_unreadable(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)
        reader = transcripts.Reader(w.ctx.config_dir)
        real = transcripts._listdir_checked
        with mock.patch.object(transcripts, "_listdir_checked",
                               lambda p: None if p == w.folder() else real(p)):
            result = reader.read_folder(os.path.basename(w.folder()), NOW)
        self.assertEqual((result.records, result.unreadable), ([], True))

    def test_the_horizon_skips_old_files(self):
        w = World(self)
        path = w.add(S1, 10, "a", 1, 1)
        old = NOW.timestamp() - 62 * 86400
        os.utime(path, (old, old))
        reader = transcripts.Reader(w.ctx.config_dir)
        result = reader.read_folder(os.path.basename(w.folder()), NOW)
        self.assertEqual(result.records, [])
        self.assertIs(result.unreadable, False)

    def test_a_full_read_after_read_folder_gives_the_same_usage_answer(self):
        w = World(self)
        build_numbers(w)
        w.add(S2, 400, "o", 3, 3, name="other")
        key = "app"
        w.live(key)
        w.live("other")
        after = {}
        for scope in (key, "other", "all"):
            status, after[scope] = api_usage.usage(w.ctx, {"project": [scope]})
            self.assertEqual(status, 200)
        fresh = w.new_ctx()
        for scope in (key, "other", "all"):
            status, plain = api_usage.usage(fresh, {"project": [scope]})
            self.assertEqual(status, 200)
            self.assertEqual(after[scope], plain, scope)

    def test_a_cold_live_poll_does_not_change_what_a_later_read_finds(self):
        w = World(self)
        w.add(S1, 100, "a", 1, 1)
        reader = transcripts.Reader(w.ctx.config_dir)
        reader.read_folder(os.path.basename(w.folder()), NOW)
        full = reader.read(NOW)
        plain = transcripts.Reader(w.ctx.config_dir).read(NOW)
        self.assertEqual(full.records, plain.records)
        self.assertEqual(full.signature, plain.signature)


class Privacy(unittest.TestCase):
    def test_the_body_holds_no_message_text_tool_input_or_cwd(self):
        w = World(self)
        build_numbers(w)
        body = json.dumps(w.live())
        for planted in (SECRET_TEXT, SECRET_TOOL, SECRET_CWD, "cwd", "content", "Bash"):
            self.assertNotIn(planted, body)
        self.assertNotIn(w.root, body)
        unchanged = json.dumps(w.live(etag=json.loads(body)["etag"]))
        self.assertNotIn(SECRET_TEXT, unchanged)

    def test_the_reader_keeps_no_text(self):
        w = World(self)
        build_numbers(w)
        reader = transcripts.Reader(w.ctx.config_dir)
        result = reader.read_folder(os.path.basename(w.folder()), NOW)
        for rec in result.records:
            for value in rec:
                self.assertNotIn(SECRET_TEXT, str(value))
                self.assertNotIn(SECRET_TOOL, str(value))


class Unreadable(unittest.TestCase):
    def shown(self, w, *parts):
        return resolve.display_path(os.path.join(w.top, *parts), home=w.ctx.home, root=w.ctx.root)

    def test_a_folder_that_cannot_be_listed_is_named(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)
        folder = os.path.basename(w.folder())
        real = transcripts._listdir_checked
        with mock.patch.object(transcripts, "_listdir_checked",
                               lambda p: None if p == w.folder() else real(p)):
            payload = w.live()
        self.assertEqual(payload["unreadable"], self.shown(w, folder))
        self.assertTrue(payload["unreadable"].endswith(folder))
        self.assertEqual(payload["running"], [])
        self.assertIsNone(payload["session"])
        self.assertNotIn(w.root, json.dumps(payload))

    def test_a_folder_whose_files_all_fail_to_open_is_named(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)
        w.add(S2, 10, "b", 1, 1, name="other")
        folder = os.path.basename(w.folder())
        inside = w.folder() + os.sep
        real = transcripts.Reader._parse
        patch = mock.patch.object(
            transcripts.Reader, "_parse",
            staticmethod(lambda item, *rest: None if item.path.startswith(inside) else real(item, *rest)))
        with patch:
            payload = w.live()
            other = w.live("other")
        self.assertEqual(payload["unreadable"], self.shown(w, folder))
        self.assertIsNone(other["unreadable"])

    def test_one_failed_file_among_others_does_not_name_the_folder(self):
        w = World(self)
        first = w.add(S1, 10, "a", 1, 1)
        w.add(S2, 10, "b", 1, 1)
        real = transcripts.Reader._parse
        patch = mock.patch.object(
            transcripts.Reader, "_parse",
            staticmethod(lambda item, *rest: None if item.path == first else real(item, *rest)))
        with patch:
            payload = w.live()
        self.assertIsNone(payload["unreadable"])
        self.assertEqual([r["session_id"] for r in payload["running"]], [S2])

    def test_a_projects_folder_that_cannot_be_listed_is_named(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)  # makes the projects folder
        real = transcripts._listdir_checked
        with mock.patch.object(transcripts, "_listdir_checked", lambda p: None if p == w.top else real(p)):
            payload = w.live("empty")
        self.assertEqual(payload["unreadable"], self.shown(w))

    def test_a_project_with_no_folder_is_not_unreadable(self):
        w = World(self)
        self.assertIsNone(w.live("empty")["unreadable"])


class LongPaths(unittest.TestCase):
    def test_a_long_path_matches_on_the_prefix_and_the_first_cwd(self):
        w = World(self)
        long_dir = os.path.join(w.root, "projects", "L" * 210)
        os.makedirs(long_dir)
        real = os.path.realpath(long_dir)
        full = transcripts.sanitize(real) + "-abc123"
        self.assertGreater(len(transcripts._dashed(real)), 200)
        entries = [{"name": "app", "path": w.paths["app"]}, {"name": "long", "path": real}]
        ts.write_json(os.path.join(w.root, "config", "routing-dashboard.json"), {"projects": entries})
        folder = os.path.join(w.top, full)
        w.add(S1, 10, "a", 7, 3, name="app")
        os.makedirs(folder)
        row = {"type": "assistant", "timestamp": iso(NOW - datetime.timedelta(seconds=20)), "cwd": real,
               "sessionId": S2, "gitBranch": "main", "requestId": "req_l",
               "message": {"id": "msg_l", "model": OPUS, "usage": {"input_tokens": 11, "output_tokens": 4}}}
        with open(os.path.join(folder, S2 + ".jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        ctx = w.new_ctx()
        payload = api_live.live(ctx, {"project": ["long"]})[1]
        self.assertEqual([r["session_id"] for r in payload["running"]], [S2])
        self.assertEqual(payload["session"]["totals"]["tokens"], 15)
        reader = transcripts.Reader(w.ctx.config_dir)
        first_cwd = lambda name: reader.read_folder(name, NOW).records[0].cwd  # noqa: E731
        self.assertEqual(transcripts.folder_for_path(real, w.top, first_cwd), full)
        self.assertIsNone(transcripts.folder_for_path(real, w.top, lambda name: "/elsewhere"))
        self.assertIsNone(transcripts.folder_for_path(real, w.top))

    def test_a_short_path_is_its_dashed_real_path(self):
        w = World(self)
        self.assertEqual(transcripts.folder_for_path(w.paths["app"], w.top),
                         transcripts._dashed(w.paths["app"]))
        self.assertTrue(transcripts.folder_matches(w.paths["app"], transcripts.folder_for_path(w.paths["app"], w.top)))


class Locks(unittest.TestCase):
    def test_a_live_poll_does_not_wait_on_the_cache_lock(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)
        w.live()  # creates the reader and loads the prices
        results = []
        with w.ctx.usage_cache.lock:
            thread = threading.Thread(target=lambda: results.append(w.ask(project="app")))
            thread.start()
            thread.join(10)
            self.assertFalse(thread.is_alive(), "the live route waited on cache.lock")
        self.assertEqual(results[0][0], 200)

    def test_the_session_index_is_kept_until_a_file_changes(self):
        w = World(self)
        w.add(S1, 10, "a", 1, 1)
        w.live()
        kept = dict(w.ctx.usage_cache.live)
        self.assertEqual(list(kept), [os.path.basename(w.folder())])
        w.live()
        self.assertIs(w.ctx.usage_cache.live[os.path.basename(w.folder())][1],
                      kept[os.path.basename(w.folder())][1])
        w.add(S1, 5, "b", 1, 1)
        w.live()
        self.assertIsNot(w.ctx.usage_cache.live[os.path.basename(w.folder())][1],
                         kept[os.path.basename(w.folder())][1])


if __name__ == "__main__":
    unittest.main()

"""Tests for the usage routes (dashboard/api_usage.py).

The routes run two ways. A server process serves a built demo set with
--fixture, and the tests ask it over HTTP. Tests that need a lock, a counter
or a patched function call the routes in this process on a Context built by
server.fixture_context. Every set is the made-up demo set, or a copy of it in a
temp folder under the helpers' temp base. Nothing reads the real ~/.claude.

A copy of the set keeps the project list of the original, so its project paths
still point into the original set. That is enough: the routes only read.
"""
import dataclasses
import datetime
import json
import os
import shutil
import sys
import threading
import time
import unittest
import zoneinfo
from unittest import mock

import helpers
import test_server as ts

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import api_settings  # noqa: E402
import api_usage  # noqa: E402
import build_demo  # noqa: E402
import prices as prices_mod  # noqa: E402
import projects  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402
import transcripts  # noqa: E402
import usage  # noqa: E402

RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
UTC = datetime.timezone.utc
NAMES = ["Tidewater reporting", "Driftwood", "Harbor Light", "Saltmarsh", "Lantern"]
TIDEWATER = "Tidewater reporting"
RANGES = {"today", "7d", "30d"}
PAYLOAD_KEYS = {"project", "generated_at", "no_usage", "views", "model_names", "prices"}
TOTALS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h", "thinking",
          "requests", "runs", "sessions", "unpriced_requests")
WAIT = 30


def make_set(case, now=None):
    """Build a demo set in a temp folder. Returns (root, set folder, truth)."""
    root = ts.make_root("mr-usage-")
    case.addCleanup(helpers.rmtree_force, root)
    out = os.path.join(root, "set")
    truth = build_demo.build(out) if now is None else build_demo.build(out, now)
    return root, out, truth


def copy_set(root, out, name="copy"):
    dest = os.path.join(root, name)
    shutil.copytree(out, dest, symlinks=True)
    return dest


def make_ctx(folder):
    return server.fixture_context(folder, None, None, RULES, FIELDS)


def key_of(listing, name):
    return [p["key"] for p in listing["projects"] if p["name"] == name][0]


def call(ctx, route, **query):
    """Run a route in this process. Each keyword is one query value."""
    return route(ctx, {k: [v] if isinstance(v, str) else v for k, v in query.items()})


def jsonl_files(folder):
    for base, _dirs, files in os.walk(folder):
        for name in sorted(files):
            if name.endswith(".jsonl"):
                yield os.path.join(base, name)


def main_transcripts(copy, out):
    """The main-session transcripts of Tidewater in a copy of the set built at out.

    A copy keeps the folder names of the original, which come from the original path.
    """
    folder = os.path.join(copy, "config", "projects",
                          transcripts.sanitize(os.path.join(out, "projects", "tidewater-reporting")))
    found = [p for p in jsonl_files(folder) if os.sep + "subagents" + os.sep not in p]
    return sorted(found)


def spy_on_parse():
    """Patch Reader._parse to record (path, offset) on each call. Returns (patch, calls)."""
    original = transcripts.Reader._parse
    calls = []

    def spy(item, offset, records, stats, agent_type):
        calls.append((item.path, offset))
        return original(item, offset, records, stats, agent_type)

    return mock.patch.object(transcripts.Reader, "_parse", staticmethod(spy)), calls


def row_text(ts_utc, cwd, session, mid, input_tokens, output_tokens, model="claude-opus-5-5"):
    row = {
        "type": "assistant", "timestamp": ts_utc, "cwd": cwd, "sessionId": session,
        "gitBranch": "main", "isSidechain": False, "effort": "high", "requestId": "req_" + mid,
        "message": {"id": "msg_" + mid, "model": model, "role": "assistant",
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                              "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                              "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                                 "ephemeral_1h_input_tokens": 0},
                              "service_tier": "standard", "speed": "standard",
                              "inference_geo": "global"},
                    "content": [{"type": "text", "text": "[content not stored]"}]},
    }
    return json.dumps(row) + "\n"


def append_row(path, mid="appended", input_tokens=1000, output_tokens=500):
    """Append one complete assistant row to a transcript, in the file's own session."""
    with open(path, "rb") as fh:
        first = json.loads(fh.readline())
    text = row_text("2026-10-30T21:00:00.000Z", first["cwd"], first["sessionId"], mid,
                    input_tokens, output_tokens)
    with open(path, "ab") as fh:
        fh.write(text.encode("utf-8"))


# --------------------------------------------------------------------------
# The zone

class LocalZone(unittest.TestCase):
    def setUp(self):
        self.root = ts.make_root("mr-zone-")
        self.addCleanup(helpers.rmtree_force, self.root)

    def link(self, target, name="localtime"):
        path = os.path.join(self.root, name)
        os.symlink(target, path)
        return path

    def assert_zone(self, got, key):
        zone, label, fixed = got
        self.assertEqual((label, fixed), (key, False))
        self.assertIsInstance(zone, zoneinfo.ZoneInfo)
        self.assertEqual(zone.key, key)

    def assert_fixed(self, got):
        zone, label, fixed = got
        self.assertTrue(fixed)
        self.assertIsInstance(zone, datetime.timezone)
        self.assertIsInstance(label, str)
        self.assertTrue(label)

    def test_a_valid_tz_wins_over_the_link(self):
        link = self.link("../zoneinfo/Asia/Tokyo")
        self.assert_zone(api_usage.local_zone("America/New_York", link), "America/New_York")

    def test_a_leading_colon_is_dropped(self):
        self.assert_zone(api_usage.local_zone(":Europe/Paris", None), "Europe/Paris")

    def test_an_empty_tz_is_skipped(self):
        self.assert_fixed(api_usage.local_zone("", None))
        self.assert_fixed(api_usage.local_zone(":", None))
        self.assert_fixed(api_usage.local_zone(None, None))
        self.assert_zone(api_usage.local_zone("", self.link("../zoneinfo/Asia/Tokyo")), "Asia/Tokyo")

    def test_an_invalid_tz_falls_through_to_the_link(self):
        link = self.link("/some/where/zoneinfo/Europe/Paris")
        for bad in ("Not/AZone", "../up", "America", "/etc/passwd", "bad zone", ":Not/AZone"):
            self.assert_zone(api_usage.local_zone(bad, link), "Europe/Paris")

    def test_an_invalid_tz_with_no_link_is_fixed(self):
        for bad in ("Not/AZone", "../up", "America", "/etc/passwd"):
            self.assert_fixed(api_usage.local_zone(bad, None))

    def test_the_key_comes_after_zoneinfo_in_the_target(self):
        for target, key in (("/usr/share/zoneinfo/America/Chicago", "America/Chicago"),
                            ("/var/db/timezone/zoneinfo/Asia/Kolkata", "Asia/Kolkata"),
                            ("../zoneinfo/UTC", "UTC")):
            self.assert_zone(api_usage.local_zone(None, self.link(target, "l-" + key.replace("/", "-"))), key)

    def test_a_broken_or_odd_link_is_fixed(self):
        self.assert_fixed(api_usage.local_zone(None, os.path.join(self.root, "missing")))
        plain = ts.write(os.path.join(self.root, "plain"), "not a link")
        self.assert_fixed(api_usage.local_zone(None, plain))
        self.assert_fixed(api_usage.local_zone(None, self.link("/elsewhere/UTC", "no-marker")))
        self.assert_fixed(api_usage.local_zone(None, self.link("/x/zoneinfo/", "empty-key")))
        self.assert_fixed(api_usage.local_zone(None, self.link("/x/zoneinfo/Not/AZone", "bad-key")))
        self.assert_fixed(api_usage.local_zone(None, self.link("/x/zoneinfo/../up", "up-key")))

    def test_the_fixed_zone_is_the_current_offset_of_the_machine(self):
        zone, label, fixed = api_usage.local_zone(None, None)
        here = datetime.datetime.now().astimezone()
        self.assertTrue(fixed)
        self.assertEqual(zone.utcoffset(None), here.utcoffset())

    def test_project_all_key_matches_the_usage_scope(self):
        self.assertEqual(projects.ALL_KEY, usage.ALL)


class FixtureClock(unittest.TestCase):
    def setUp(self):
        self.root = ts.make_root("mr-clock-")
        self.addCleanup(helpers.rmtree_force, self.root)

    def ctx(self, session):
        folder = os.path.join(self.root, "fx%d" % len(os.listdir(self.root)))
        ts.write_json(os.path.join(folder, "session.json"), session)
        return server.fixture_context(folder, None, None, RULES, FIELDS)

    def test_a_good_now_and_tz_are_used(self):
        ctx = self.ctx({"now": "2026-10-30T22:00:00+00:00", "tz": "America/New_York"})
        self.assertEqual(ctx.fixed_now, datetime.datetime(2026, 10, 30, 22, 0, tzinfo=UTC))
        self.assertEqual(ctx.tz_name, "America/New_York")
        self.assertIsNone(ctx.localtime_link)
        status, payload = api_usage.api_projects(ctx, {})
        self.assertEqual(payload["tz"], "America/New_York")
        self.assertEqual(payload["now"], "2026-10-30T18:00:00-04:00")

    def test_an_offset_other_than_utc_is_kept(self):
        ctx = self.ctx({"now": "2026-10-30T18:00:00-04:00"})
        self.assertEqual(ctx.fixed_now.utcoffset(), datetime.timedelta(hours=-4))

    def test_bad_now_values_are_ignored(self):
        for bad in ("not a date", "", "2026-10-30T18:00:00", "2026-10-30", 5, 1.5, True, None,
                    ["2026-10-30T18:00:00+00:00"], {"a": 1}):
            self.assertIsNone(self.ctx({"now": bad}).fixed_now, bad)
        self.assertIsNone(self.ctx({}).fixed_now)

    def test_tz_comes_from_the_session_then_the_shell_env(self):
        self.assertEqual(self.ctx({"tz": "Asia/Tokyo", "shell_env": {"TZ": "Europe/Paris"}}).tz_name,
                         "Asia/Tokyo")
        self.assertEqual(self.ctx({"shell_env": {"TZ": "Europe/Paris"}}).tz_name, "Europe/Paris")
        self.assertEqual(self.ctx({"tz": 5, "shell_env": {"TZ": "Europe/Paris"}}).tz_name, "Europe/Paris")
        self.assertIsNone(self.ctx({"tz": 5, "shell_env": {"TZ": 7}}).tz_name)
        self.assertIsNone(self.ctx({}).tz_name)

    def test_a_fixture_without_now_reads_the_real_clock(self):
        ctx = self.ctx({"tz": "America/New_York"})
        before = datetime.datetime.now(UTC)
        _status, payload = api_usage.api_projects(ctx, {})
        after = datetime.datetime.now(UTC)
        self.assertTrue(before <= datetime.datetime.fromisoformat(payload["now"]) <= after)

    def test_live_context_ignores_the_session_keys(self):
        folder = os.path.join(self.root, "live")
        ts.write_json(os.path.join(folder, "session.json"),
                      {"now": "2026-10-30T22:00:00+00:00", "tz": "Asia/Tokyo",
                       "shell_env": {"TZ": "Europe/Paris"}})
        home = os.path.join(self.root, "home")
        ctx = server.live_context(os.path.join(home, "cfg"), os.path.join(home, "proj"),
                                  {"HOME": home, "TZ": "America/Chicago"}, "darwin", RULES, FIELDS)
        self.assertIsNone(ctx.fixed_now)
        self.assertEqual(ctx.tz_name, "America/Chicago")
        self.assertEqual(ctx.localtime_link, "/etc/localtime")
        unset = server.live_context(os.path.join(home, "cfg"), os.path.join(home, "proj"),
                                    {"HOME": home}, "darwin", RULES, FIELDS)
        self.assertIsNone(unset.tz_name)
        empty = server.live_context(os.path.join(home, "cfg"), os.path.join(home, "proj"),
                                    {"HOME": home, "TZ": ""}, "darwin", RULES, FIELDS)
        self.assertIsNone(empty.tz_name)

    def test_projects_carries_the_version_field(self):
        ctx = self.ctx({})
        self.assertIsNone(ctx.claude_version)
        self.assertIsNone(ctx.path_env)
        _status, payload = api_usage.api_projects(ctx, {})
        self.assertEqual(payload["version"], {"installed": None, "rules_oldest": "2.1.302"})
        # A fixed version in session.json shows as installed. Anything else is ignored.
        _status, payload = api_usage.api_projects(self.ctx({"claude_version": "2.1.310"}), {})
        self.assertEqual(payload["version"]["installed"], "2.1.310")
        for bad in (5, None, ["2.1.310"], {}):
            self.assertIsNone(self.ctx({"claude_version": bad}).claude_version, bad)
        _status, payload = api_usage.api_projects(
            dataclasses.replace(ctx, claude_version="2.2.0"), {})
        self.assertEqual(payload["version"]["installed"], "2.2.0")

    def test_live_context_searches_the_given_path(self):
        home = os.path.join(self.root, "home")
        ctx = server.live_context(os.path.join(home, "cfg"), os.path.join(home, "proj"),
                                  {"HOME": home, "PATH": "/a:/b"}, "darwin", RULES, FIELDS)
        self.assertEqual(ctx.path_env, "/a:/b")
        self.assertIsNone(ctx.claude_version)
        unset = server.live_context(os.path.join(home, "cfg"), os.path.join(home, "proj"),
                                    {"HOME": home}, "darwin", RULES, FIELDS)
        self.assertIsNone(unset.path_env)

    def test_each_context_has_its_own_cache(self):
        a, b = self.ctx({}), self.ctx({})
        self.assertIsNot(a.usage_cache, b.usage_cache)
        self.assertIsNotNone(a.usage_cache.lock)
        self.assertIsNone(a.usage_cache.reader)
        self.assertFalse(a.usage_cache.warm)


# --------------------------------------------------------------------------
# The routes over HTTP

class Routes(unittest.TestCase):
    """A server process on the demo set."""

    @classmethod
    def setUpClass(cls):
        cls.root = ts.make_root("mr-usage-")
        cls.out = os.path.join(cls.root, "set")
        cls.truth = build_demo.build(cls.out)
        cls.srv = ts.start(cls.root, ["--fixture", cls.out])
        _s, cls.listing = cls.get(cls.srv, "/api/projects")
        cls.keys = {name: key_of(cls.listing, name) for name in NAMES}
        cls.single = cls.get(cls.srv, "/api/usage?project=" + cls.keys[TIDEWATER])[1]
        cls.everything = cls.get(cls.srv, "/api/usage?project=all")[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
        helpers.rmtree_force(cls.root)

    @staticmethod
    def get(proc, path):
        status, _heads, body = proc.request("GET", path)
        return status, json.loads(body)

    def agent(self, key):
        return [r for r in self.single["views"]["30d"]["by_agent"] if r["route_key"] == key][0]

    # /api/projects

    def test_projects_keeps_its_old_fields(self):
        self.assertEqual(self.listing["current"], self.keys[TIDEWATER])
        self.assertEqual([p["name"] for p in self.listing["projects"]], NAMES)
        for row in self.listing["projects"]:
            self.assertEqual(set(row), {"key", "name", "path_display", "state"})

    def test_projects_adds_zone_clock_and_folder(self):
        self.assertEqual(self.listing["tz"], "America/New_York")
        shown = datetime.datetime.fromisoformat(self.listing["now"])
        demo_now = datetime.datetime.strptime(
            self.truth["window"]["end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        self.assertEqual(shown, demo_now)
        self.assertEqual(self.listing["now"], "2026-10-30T18:00:00-04:00")
        self.assertEqual(self.listing["transcripts_dir_display"], "config/projects")
        self.assertEqual(self.listing["config_file_display"], "config/routing-dashboard.json")
        self.assertFalse(os.path.isabs(self.listing["config_file_display"]))
        self.assertFalse(os.path.isabs(self.listing["transcripts_dir_display"]))
        self.assertNotIn(self.root, json.dumps(self.listing))

    def test_projects_carries_the_demo_version(self):
        # The demo's session.json fixes the installed version, newer than every rule.
        self.assertEqual(self.listing["version"], {"installed": "2.1.310", "rules_oldest": "2.1.302"})

    def test_projects_reports_the_reader(self):
        reader = self.listing["reader"]
        self.assertEqual(set(reader), {"readable", "warm", "files", "skipped"})
        self.assertIs(reader["readable"], True)
        self.assertIsInstance(reader["warm"], bool)
        # The usage calls in setUpClass have ended, so the reader has read.
        _s, after = self.get(self.srv, "/api/projects")
        want = sum(1 for _ in jsonl_files(os.path.join(self.out, "config", "projects")))
        self.assertEqual(after["reader"]["warm"], True)
        self.assertEqual(after["reader"]["files"], want)
        self.assertGreater(after["reader"]["skipped"], 0)
        self.assertLess(after["reader"]["skipped"], want)

    # /api/usage

    def test_a_single_project_has_the_whole_shape(self):
        self.assertEqual(set(self.single), PAYLOAD_KEYS)
        self.assertEqual(self.single["project"], self.keys[TIDEWATER])
        self.assertEqual(set(self.single["views"]), RANGES)
        for name, view in self.single["views"].items():
            self.assertEqual(view["range"], name)
            self.assertIn("totals", view)
            self.assertIn("by_agent", view)
        self.assertEqual(self.single["generated_at"], self.listing["now"])
        self.assertIsNone(self.single["views"]["30d"]["by_project"])

    def test_model_names_map_every_catalog_id_to_its_display_name(self):
        want = {m["id"]: m.get("display_name") or m["id"] for m in RULES["models"]}
        for payload in (self.single, self.everything):
            self.assertEqual(payload["model_names"], want)
        self.assertEqual(self.single["model_names"]["claude-opus-5-5"], "Opus 5.5")
        # every model an agent ran with can be named from the map
        for view in self.single["views"].values():
            for agent in view["by_agent"]:
                for row in agent["ran_with"]:
                    self.assertIn(row["model"], self.single["model_names"])

    def test_all_projects_has_the_whole_shape(self):
        self.assertEqual(set(self.everything), PAYLOAD_KEYS)
        self.assertEqual(self.everything["project"], "all")
        self.assertEqual(set(self.everything["views"]), RANGES)
        by_project = self.everything["views"]["30d"]["by_project"]
        self.assertTrue(by_project)
        self.assertGreater(self.everything["views"]["30d"]["totals"]["requests"],
                           self.single["views"]["30d"]["totals"]["requests"])

    def test_no_usage_body_holds_the_fixture_path_or_a_transcript_folder_name(self):
        folders = sorted(os.listdir(os.path.join(self.out, "config", "projects")))
        self.assertTrue(folders)
        for scope in (self.keys[TIDEWATER], "all"):
            _status, _heads, body = self.srv.request("GET", "/api/usage?project=" + scope)
            text = body.decode("utf-8")
            self.assertGreater(len(text), 1000, scope)
            self.assertNotIn(self.out, text, scope)
            self.assertNotIn(os.path.realpath(self.out), text, scope)
            self.assertNotIn(self.root, text, scope)
            for name in folders:
                self.assertTrue(name.startswith("-"), name)
                self.assertNotIn(name, text, scope + " " + name)

    def test_prices_carry_the_date_and_source(self):
        want = prices_mod.load_prices()
        for payload in (self.single, self.everything):
            self.assertEqual(payload["prices"], {"verified_on": want["verified_on"],
                                                 "source": want["source"]})

    def test_no_value_means_the_current_project(self):
        _s, payload = self.get(self.srv, "/api/usage")
        self.assertEqual(payload["project"], self.keys[TIDEWATER])
        self.assertEqual(payload["views"]["30d"]["totals"], self.single["views"]["30d"]["totals"])

    def test_the_30_day_totals_match_the_truth(self):
        totals = self.single["views"]["30d"]["totals"]
        want = self.truth["projects"][TIDEWATER]
        for field in TOTALS:
            self.assertEqual(totals[field], want[field], field)
        self.assertAlmostEqual(totals["cost"], want["cost"], places=6)
        self.assertGreater(totals["requests"], 0)

    def test_pin_is_filled_for_a_listed_project(self):
        self.assertEqual(self.agent("builder")["pin"]["state"], "overridden")
        self.assertEqual(self.agent("reviewer")["pin"]["state"], "overridden")
        self.assertEqual(self.agent("scribe")["pin"]["state"], "differs")
        self.assertEqual(self.agent("@main")["pin"]["state"], "matches_lowered")

    def test_pin_is_empty_for_all_projects(self):
        rows = self.everything["views"]["30d"]["by_agent"]
        self.assertTrue(rows)
        for row in rows:
            self.assertIsNone(row["pin"], row["route_key"])

    def test_no_usage_says_so(self):
        want = {TIDEWATER: False, "Driftwood": False, "Harbor Light": False,
                "Saltmarsh": True, "Lantern": True}
        for name, no_usage in want.items():
            _s, payload = self.get(self.srv, "/api/usage?project=" + self.keys[name])
            self.assertIs(payload["no_usage"], no_usage, name)
            self.assertEqual(set(payload), PAYLOAD_KEYS, name)
            self.assertEqual(set(payload["views"]), RANGES, name)
        self.assertIs(self.everything["no_usage"], False)

    def test_a_project_with_no_usage_has_empty_views(self):
        _s, payload = self.get(self.srv, "/api/usage?project=" + self.keys["Saltmarsh"])
        for view in payload["views"].values():
            self.assertEqual(view["totals"]["requests"], 0)
            self.assertEqual(view["by_agent"], [])

    def test_a_key_that_is_not_listed_is_refused(self):
        for query in ("project=nope", "project=quarry-notes", "project=ALL", "project=%2e%2e"):
            status, heads, body = self.srv.request("GET", "/api/usage?" + query)
            self.assertEqual(status, 404, query)
            self.assertEqual(json.loads(body), {"error": "unknown_project"})
            self.assertNotIn(b"views", body)
            self.assertNotIn(b"generated_at", body)

    def test_two_project_values_are_refused(self):
        key = self.keys[TIDEWATER]
        for query in ("project=%s&project=all" % key, "project=all&project=all",
                      "project=%s&project=%s" % (key, key)):
            status, _heads, body = self.srv.request("GET", "/api/usage?" + query)
            self.assertEqual(status, 400, query)
            self.assertEqual(json.loads(body), {"error": "bad_request"})

    def test_head_gets_no_body(self):
        status, heads, body = self.srv.request("HEAD", "/api/usage?project=all")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertGreater(int(heads["content-length"]), 100)


class WarmUp(ts.TempCase):
    def test_the_reader_warms_without_a_usage_call(self):
        out = os.path.join(self.root, "set")
        build_demo.build(out)
        proc = self.start(["--fixture", out])
        deadline = time.time() + WAIT
        reader = None
        while time.time() < deadline:
            _s, _h, body = proc.request("GET", "/api/projects")
            reader = json.loads(body)["reader"]
            if reader["warm"]:
                break
            time.sleep(0.05)
        self.assertTrue(reader and reader["warm"], reader)
        self.assertGreater(reader["files"], 0)
        self.assertIsNotNone(reader["skipped"])
        calls = [line for line in proc.stderr().splitlines() if "/api/usage" in line]
        self.assertEqual(calls, [])


# --------------------------------------------------------------------------
# The routes in this process

class InProcess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ts.make_root("mr-usage-")
        cls.out = os.path.join(cls.root, "set")
        cls.truth = build_demo.build(cls.out)
        listing = api_usage.api_projects(make_ctx(cls.out), {})[1]
        cls.keys = {name: key_of(listing, name) for name in NAMES}

    @classmethod
    def tearDownClass(cls):
        helpers.rmtree_force(cls.root)

    def totals(self, ctx, name=TIDEWATER, rng="30d"):
        status, payload = call(ctx, api_usage.usage, project=self.keys[name])
        self.assertEqual(status, 200)
        return payload["views"][rng]["totals"]

    # reader.readable

    def test_a_missing_transcripts_folder_is_not_readable(self):
        ctx = dataclasses.replace(make_ctx(self.out), config_dir=os.path.join(self.root, "no-such-config"))
        _status, payload = api_usage.api_projects(ctx, {})
        self.assertIs(payload["reader"]["readable"], False)

    def test_a_file_in_place_of_the_transcripts_folder_is_not_readable(self):
        config = os.path.join(self.root, "file-config")
        os.makedirs(config)
        with open(os.path.join(config, "projects"), "w") as handle:
            handle.write("not a folder")
        ctx = dataclasses.replace(make_ctx(self.out), config_dir=config)
        self.assertIs(api_usage.api_projects(ctx, {})[1]["reader"]["readable"], False)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can enter a folder with mode 000")
    def test_a_folder_without_access_is_not_readable(self):
        config = os.path.join(self.root, "locked-config")
        folder = os.path.join(config, "projects")
        os.makedirs(folder)
        os.chmod(folder, 0)
        self.addCleanup(os.chmod, folder, 0o755)
        if os.access(folder, os.R_OK):
            self.skipTest("this filesystem ignores folder modes")
        ctx = dataclasses.replace(make_ctx(self.out), config_dir=config)
        self.assertIs(api_usage.api_projects(ctx, {})[1]["reader"]["readable"], False)

    # lock and warm

    def test_a_warm_and_a_usage_call_parse_each_file_once(self):
        ctx = make_ctx(self.out)
        patch, calls = spy_on_parse()
        gate = threading.Barrier(2)
        results = []

        def warm():
            gate.wait()
            api_usage.warm(ctx)

        def ask():
            gate.wait()
            results.append(call(ctx, api_usage.usage, project=self.keys[TIDEWATER]))

        with patch:
            threads = [threading.Thread(target=warm), threading.Thread(target=ask)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(WAIT)
            self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(results[0][0], 200)
        paths = [path for path, _offset in calls]
        self.assertTrue(paths)
        self.assertEqual(len(paths), len(set(paths)), "a file was parsed twice")
        cache = ctx.usage_cache
        self.assertTrue(cache.warm)
        self.assertEqual(len(paths), cache.reader.files_found - cache.skipped)
        self.assertTrue(all(offset == 0 for _path, offset in calls))

    def test_start_warm_runs_on_a_daemon_thread(self):
        ctx = make_ctx(self.out)
        thread = api_usage.start_warm(ctx)
        self.assertTrue(thread.daemon)
        thread.join(WAIT)
        self.assertFalse(thread.is_alive())
        self.assertTrue(ctx.usage_cache.warm)

    def test_a_failed_warm_logs_the_class_and_stays_cold(self):
        ctx = make_ctx(self.out)
        planted = "planted-secret-in-an-error"
        with mock.patch.object(transcripts.Reader, "read", side_effect=OSError(planted)), \
                mock.patch.object(sys, "stderr") as err:
            api_usage.warm(ctx)
        self.assertFalse(ctx.usage_cache.warm)
        written = "".join(c.args[0] for c in err.write.call_args_list)
        self.assertIn("OSError", written)
        self.assertNotIn(planted, written)

    def test_only_usage_waits_on_the_reader(self):
        ctx = make_ctx(self.out)
        cache = ctx.usage_cache
        done = {}

        def run(name, route, **query):
            done[name] = call(ctx, route, **query)

        cache.lock.acquire()
        try:
            threads = [
                threading.Thread(target=run, args=("projects", api_usage.api_projects)),
                threading.Thread(target=run, args=("settings", api_settings.settings),
                                 kwargs={"project": self.keys[TIDEWATER]}),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
            self.assertFalse(any(t.is_alive() for t in threads), "a route waited on the lock")
            self.assertEqual(done["projects"][0], 200)
            self.assertEqual(done["projects"][1]["reader"],
                             {"readable": True, "warm": False, "files": None, "skipped": None})
            self.assertEqual(done["settings"][0], 200)
            waiting = threading.Thread(target=run, args=("usage", api_usage.usage),
                                       kwargs={"project": self.keys[TIDEWATER]})
            waiting.start()
            waiting.join(0.5)
            self.assertTrue(waiting.is_alive(), "usage did not wait on the lock")
        finally:
            cache.lock.release()
        waiting.join(WAIT)
        self.assertEqual(done["usage"][0], 200)

    def test_projects_reports_files_while_the_reader_runs(self):
        ctx = make_ctx(self.out)
        inside = threading.Event()
        release = threading.Event()
        original = transcripts.Reader._load

        def slow(reader, item):
            inside.set()
            release.wait(WAIT)
            return original(reader, item)

        with mock.patch.object(transcripts.Reader, "_load", slow):
            thread = api_usage.start_warm(ctx)
            try:
                self.assertTrue(inside.wait(WAIT))
                _s, payload = api_usage.api_projects(ctx, {})
                self.assertFalse(payload["reader"]["warm"])
                self.assertGreater(payload["reader"]["files"], 0)
                self.assertIsNone(payload["reader"]["skipped"])
            finally:
                release.set()
                thread.join(WAIT)
        self.assertTrue(ctx.usage_cache.warm)

    # appended bytes

    def test_a_second_load_parses_only_appended_bytes(self):
        copy = copy_set(self.root, self.out, "append")
        ctx = make_ctx(copy)
        before = self.totals(ctx)
        target = main_transcripts(copy, self.out)[-1]
        old_size = os.path.getsize(target)
        append_row(target)
        patch, calls = spy_on_parse()
        with patch:
            after = self.totals(ctx)
        self.assertEqual(calls, [(target, old_size)])
        self.assertEqual(after["requests"], before["requests"] + 1)
        self.assertEqual(after["input"], before["input"] + 1000)
        self.assertEqual(after["output"], before["output"] + 500)
        with patch:
            self.totals(ctx)
        self.assertEqual(len(calls), 1)

    # the kept answer

    def test_the_same_request_twice_builds_once(self):
        ctx = make_ctx(self.out)
        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            first = call(ctx, api_usage.usage, project=self.keys[TIDEWATER])
            second = call(ctx, api_usage.usage, project=self.keys[TIDEWATER])
            self.assertEqual(built.call_count, 1)
            self.assertEqual(first, second)
            call(ctx, api_usage.usage, project="all")
            self.assertEqual(built.call_count, 2)
            call(ctx, api_usage.usage, project="all")
            self.assertEqual(built.call_count, 2)
            call(ctx, api_usage.usage)  # no value is the current project: a hit
            self.assertEqual(built.call_count, 2)

    def test_an_appended_row_rebuilds(self):
        copy = copy_set(self.root, self.out, "rebuild-append")
        ctx = make_ctx(copy)
        target = main_transcripts(copy, self.out)[-1]
        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            before = self.totals(ctx)
            append_row(target)
            after = self.totals(ctx)
            self.assertEqual(built.call_count, 2)
        self.assertEqual(after["requests"], before["requests"] + 1)

    def test_a_settings_edit_rebuilds_and_changes_the_pin(self):
        copy = copy_set(self.root, self.out, "rebuild-settings")
        ctx = make_ctx(copy)
        key = self.keys[TIDEWATER]

        def main_pin():
            _s, payload = call(ctx, api_usage.usage, project=key)
            return [r for r in payload["views"]["30d"]["by_agent"]
                    if r["route_key"] == "@main"][0]["pin"]["state"]

        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            before = main_pin()
            self.assertEqual(main_pin(), before)
            self.assertEqual(built.call_count, 1)
            path = os.path.join(copy, "config", "settings.json")
            with open(path, encoding="utf-8") as fh:
                settings = json.load(fh)
            settings["model"] = "claude-haiku-5-5"
            ts.write_json(path, settings)
            after = main_pin()
            self.assertEqual(built.call_count, 2)
        self.assertEqual(before, "matches_lowered")
        self.assertNotEqual(after, before)

    def test_a_listed_project_whose_folder_is_gone_keeps_its_transcripts(self):
        root, out, _truth = make_set(self)
        shutil.rmtree(os.path.join(out, "projects", "tidewater-reporting"))
        ctx = make_ctx(out)
        listing = api_usage.api_projects(ctx, {})[1]
        row = [p for p in listing["projects"] if p["name"] == TIDEWATER][0]
        self.assertEqual(row["state"], "missing_folder")
        status, payload = call(ctx, api_usage.usage, project=row["key"])
        self.assertEqual(status, 200)
        self.assertIs(payload["no_usage"], False)
        self.assertGreater(payload["views"]["30d"]["totals"]["requests"], 0)
        rows = payload["views"]["30d"]["by_agent"]
        self.assertTrue(rows)
        for agent in rows:
            self.assertTrue(agent["pin"] is None or agent["pin"]["state"] is None, agent["route_key"])

    def test_a_list_edit_rebuilds(self):
        copy = copy_set(self.root, self.out, "rebuild-list")
        ctx = make_ctx(copy)
        path = os.path.join(copy, "config", "routing-dashboard.json")
        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            call(ctx, api_usage.usage, project="all")
            with open(path, encoding="utf-8") as fh:
                listing = json.load(fh)
            listing["projects"][1]["name"] = "Driftwood renamed"
            ts.write_json(path, listing)
            call(ctx, api_usage.usage, project="all")
            self.assertEqual(built.call_count, 2)

    def test_a_deleted_transcript_file_rebuilds(self):
        copy = copy_set(self.root, self.out, "rebuild-delete")
        ctx = make_ctx(copy)
        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            before = self.totals(ctx)
            self.assertEqual(self.totals(ctx), before)
            self.assertEqual(built.call_count, 1, "kept while nothing changed")
            os.remove(main_transcripts(copy, self.out)[-1])
            after = self.totals(ctx)
            self.assertEqual(built.call_count, 2)
        self.assertLess(after["requests"], before["requests"])

    def test_a_meta_file_change_rebuilds(self):
        copy = copy_set(self.root, self.out, "rebuild-meta")
        ctx = make_ctx(copy)
        metas = [os.path.join(base, name) for base, _dirs, files in os.walk(os.path.join(copy, "config", "projects"))
                 for name in sorted(files) if name.endswith(".meta.json")]
        self.assertTrue(metas)
        # The meta file of the newest agent transcript, so the file is well inside the horizon.
        metas = [m for m in metas if os.path.isfile(m[:-len(".meta.json")] + ".jsonl")]
        metas.sort(key=lambda m: (os.path.getmtime(m[:-len(".meta.json")] + ".jsonl"), m), reverse=True)

        def agents():
            _s, payload = call(ctx, api_usage.usage, project="all")
            return set(a["route_key"] for a in payload["views"]["30d"]["by_agent"])

        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            before = agents()
            self.assertEqual(agents(), before)
            self.assertEqual(built.call_count, 1, "kept while nothing changed")
            self.assertNotIn("renamed-by-meta-edit", before)
            with open(metas[0], encoding="utf-8") as fh:
                meta = json.load(fh)
            old_type = meta["agentType"]
            meta["agentType"] = "renamed-by-meta-edit"
            ts.write_json(metas[0], meta)
            after = agents()
            self.assertEqual(built.call_count, 2)
        self.assertIn("renamed-by-meta-edit", after)
        self.assertIn(old_type, before)

    def test_a_file_ageing_past_the_horizon_rebuilds_inside_the_age_limit(self):
        copy = copy_set(self.root, self.out, "rebuild-horizon")
        ctx = make_ctx(copy)
        step = datetime.timedelta
        target = main_transcripts(copy, self.out)[-1]
        # Thirty seconds inside the horizon at the first call, and thirty seconds past it ten seconds later.
        edge = (ctx.fixed_now - step(days=transcripts.Reader(copy).horizon_days)).timestamp() + 30
        os.utime(target, (edge, edge))
        later = dataclasses.replace(ctx, fixed_now=ctx.fixed_now + step(seconds=40))
        self.assertEqual(ctx.fixed_now.date(), later.fixed_now.date(), "no new local day to blame")
        self.assertEqual(ctx.fixed_now.utcoffset(), later.fixed_now.utcoffset())
        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            _s, first = call(ctx, api_usage.usage, project="all")
            skipped = first["views"]["30d"]["notes"]["skipped_old_files"]
            call(dataclasses.replace(ctx, fixed_now=ctx.fixed_now + step(seconds=10)), api_usage.usage, project="all")
            self.assertEqual(built.call_count, 1, "kept while the file is still inside the horizon")
            _s, second = call(later, api_usage.usage, project="all")
            self.assertEqual(built.call_count, 2)
        self.assertEqual(second["views"]["30d"]["notes"]["skipped_old_files"], skipped + 1)
        self.assertLess(second["views"]["30d"]["totals"]["requests"], first["views"]["30d"]["totals"]["requests"])

    def test_a_change_of_utc_offset_rebuilds_inside_the_age_limit(self):
        # New York falls back at 2:00 a.m. on November 1, 2026: 05:59:40Z is 1:59:40 EDT and 06:00:10Z is 1:00:10 EST.
        ctx = dataclasses.replace(make_ctx(self.out), tz_name="America/New_York")
        before = dataclasses.replace(ctx, fixed_now=datetime.datetime(2026, 11, 1, 5, 59, 40, tzinfo=UTC))
        after = dataclasses.replace(ctx, fixed_now=datetime.datetime(2026, 11, 1, 6, 0, 10, tzinfo=UTC))
        zone = zoneinfo.ZoneInfo("America/New_York")
        self.assertNotEqual(before.fixed_now.astimezone(zone).utcoffset(), after.fixed_now.astimezone(zone).utcoffset())
        self.assertEqual(before.fixed_now.astimezone(zone).date(), after.fixed_now.astimezone(zone).date())
        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            call(before, api_usage.usage, project=self.keys[TIDEWATER])
            call(dataclasses.replace(before, fixed_now=before.fixed_now + datetime.timedelta(seconds=5)),
                 api_usage.usage, project=self.keys[TIDEWATER])
            self.assertEqual(built.call_count, 1, "kept while the offset is the same")
            call(after, api_usage.usage, project=self.keys[TIDEWATER])
            self.assertEqual(built.call_count, 2)

    def test_time_moving_past_the_age_limit_rebuilds(self):
        ctx = make_ctx(self.out)
        step = datetime.timedelta
        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            call(ctx, api_usage.usage, project=self.keys[TIDEWATER])
            soon = dataclasses.replace(ctx, fixed_now=ctx.fixed_now + step(seconds=api_usage.MAX_AGE_SECONDS - 1))
            call(soon, api_usage.usage, project=self.keys[TIDEWATER])
            self.assertEqual(built.call_count, 1)
            late = dataclasses.replace(ctx, fixed_now=ctx.fixed_now + step(seconds=api_usage.MAX_AGE_SECONDS + 1))
            call(late, api_usage.usage, project=self.keys[TIDEWATER])
            self.assertEqual(built.call_count, 2)
            earlier = dataclasses.replace(ctx, fixed_now=ctx.fixed_now - step(seconds=5))
            call(earlier, api_usage.usage, project=self.keys[TIDEWATER])
            self.assertEqual(built.call_count, 3)

    def test_the_next_local_day_rebuilds_inside_the_age_limit(self):
        ctx = make_ctx(self.out)
        zone = zoneinfo.ZoneInfo("America/New_York")
        evening = datetime.datetime(2026, 10, 30, 23, 59, 40, tzinfo=zone)
        ctx = dataclasses.replace(ctx, fixed_now=evening, usage_cache=api_usage.Cache())
        after_midnight = dataclasses.replace(ctx, fixed_now=evening + datetime.timedelta(seconds=30))
        with mock.patch.object(usage, "build_views", wraps=usage.build_views) as built:
            call(ctx, api_usage.usage, project=self.keys[TIDEWATER])
            call(dataclasses.replace(ctx, fixed_now=evening + datetime.timedelta(seconds=5)),
                 api_usage.usage, project=self.keys[TIDEWATER])
            self.assertEqual(built.call_count, 1)
            _s, payload = call(after_midnight, api_usage.usage, project=self.keys[TIDEWATER])
            self.assertEqual(built.call_count, 2)
        self.assertTrue(payload["generated_at"].startswith("2026-10-31T00:00:10"))

    # the zone

    def test_tz_fixed_reaches_the_notes(self):
        ctx = make_ctx(self.out)
        _s, zoned = call(ctx, api_usage.usage, project="all")
        self.assertIs(zoned["views"]["30d"]["notes"]["tz_fixed"], False)
        fixed = dataclasses.replace(ctx, tz_name=None, usage_cache=api_usage.Cache())
        _s, payload = call(fixed, api_usage.usage, project="all")
        for view in payload["views"].values():
            self.assertIs(view["notes"]["tz_fixed"], True)
        _s, listing = api_usage.api_projects(fixed, {})
        self.assertTrue(listing["tz"])
        self.assertTrue(datetime.datetime.fromisoformat(listing["now"]).utcoffset() is not None)

    def test_the_zone_follows_the_context(self):
        ctx = make_ctx(self.out)
        tokyo = dataclasses.replace(ctx, tz_name="Asia/Tokyo", usage_cache=api_usage.Cache())
        _s, listing = api_usage.api_projects(tokyo, {})
        self.assertEqual(listing["tz"], "Asia/Tokyo")
        self.assertEqual(listing["now"], "2026-10-31T07:00:00+09:00")
        _s, payload = call(tokyo, api_usage.usage, project="all")
        self.assertEqual(payload["generated_at"], "2026-10-31T07:00:00+09:00")
        self.assertTrue(payload["views"]["today"]["start"].startswith("2026-10-31T00:00:00"))


# --------------------------------------------------------------------------
# Planted text

MARKER = "planted-marker-7f3a91c2"


def plant_marker(folder):
    """Put MARKER in message text, a tool_use input, a tool_result and an agent description.

    Returns how many files of each kind were changed.
    """
    changed = {"text": 0, "tool_use": 0, "tool_result": 0, "meta": 0}
    for path in jsonl_files(os.path.join(folder, "config", "projects")):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        out, planted = [], False
        for line in lines:
            row = json.loads(line)
            if not planted and row.get("type") == "assistant":
                content = row["message"]["content"]
                content[0]["text"] = "reply with " + MARKER
                content.append({"type": "tool_use", "id": "toolu_planted", "name": "Bash",
                                "input": {"command": "echo " + MARKER}})
                planted = True
                changed["text"] += 1
                changed["tool_use"] += 1
            out.append(json.dumps(row))
        if planted:
            out.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_planted", "content": MARKER}]}}))
            changed["tool_result"] += 1
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
    for base, _dirs, files in os.walk(os.path.join(folder, "config", "projects")):
        for name in files:
            if name.endswith(".meta.json"):
                meta_path = os.path.join(base, name)
                with open(meta_path, encoding="utf-8") as fh:
                    meta = json.load(fh)
                meta["description"] = "do " + MARKER
                ts.write_json(meta_path, meta)
                changed["meta"] += 1
    return changed


def count_marker(folder):
    """Files under folder that hold MARKER, by kind of file."""
    found = {"jsonl": 0, "meta": 0}
    for base, _dirs, files in os.walk(folder):
        for name in files:
            with open(os.path.join(base, name), "rb") as fh:
                if MARKER.encode() in fh.read():
                    found["meta" if name.endswith(".meta.json") else "jsonl"] += 1
    return found


class FolderGone(ts.TempCase):
    def test_the_list_says_missing_folder_while_usage_is_kept(self):
        _root, out, _truth = make_set(self)
        shutil.rmtree(os.path.join(out, "projects", "tidewater-reporting"))
        proc = self.start(["--fixture", out])
        _s, _h, body = proc.request("GET", "/api/projects")
        row = [p for p in json.loads(body)["projects"] if p["name"] == TIDEWATER][0]
        self.assertEqual(row["state"], "missing_folder")
        status, _h, body = proc.request("GET", "/api/usage?project=" + row["key"])
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIs(payload["no_usage"], False)
        self.assertGreater(payload["views"]["30d"]["totals"]["requests"], 0)


class Marker(ts.TempCase):
    def test_planted_text_appears_in_no_response(self):
        root, out, _truth = make_set(self)
        copy = copy_set(root, out, "marked")
        changed = plant_marker(copy)
        found = count_marker(os.path.join(copy, "config"))
        # Not vacuous: the marker is in every kind of file the test claims to cover.
        self.assertGreater(changed["text"], 3)
        self.assertEqual(changed["tool_use"], changed["text"])
        self.assertEqual(changed["tool_result"], changed["text"])
        self.assertGreater(changed["meta"], 3)
        self.assertEqual(found["jsonl"], changed["text"])
        self.assertEqual(found["meta"], changed["meta"])
        proc = self.start(["--fixture", copy])
        _s, _h, body = proc.request("GET", "/api/projects")
        listing = json.loads(body)
        keys = [p["key"] for p in listing["projects"]]
        self.assertEqual(len(keys), len(NAMES))
        bodies = [body]
        paths = ["/api/usage", "/api/usage?project=all"]
        paths += ["/api/usage?project=" + k for k in keys]
        paths += ["/api/settings?project=" + k for k in keys]
        for path in paths:
            status, heads, data = proc.request("GET", path)
            self.assertEqual(status, 200, path)
            bodies.append(json.dumps(heads).encode() + data)
        # The reader really read the planted files.
        usage_body = json.loads(proc.request("GET", "/api/usage?project=all")[2])
        self.assertGreater(usage_body["views"]["30d"]["totals"]["requests"], 0)
        proc.stop()
        everything = b"\n".join(bodies) + proc.stdout().encode() + proc.stderr().encode()
        self.assertNotIn(MARKER.encode(), everything)
        self.assertNotIn(b"planted-marker", everything)

    def test_the_reader_keeps_no_text(self):
        root, out, _truth = make_set(self)
        copy = copy_set(root, out, "marked")
        plant_marker(copy)
        result = transcripts.Reader(os.path.join(copy, "config")).read(
            datetime.datetime(2026, 10, 30, 22, 0, tzinfo=UTC))
        self.assertGreater(len(result.records), 100)
        self.assertNotIn(MARKER, repr(result))


# --------------------------------------------------------------------------
# No file written

class NothingWritten(ts.TempCase):
    def test_every_route_leaves_the_whole_tree_as_it_was(self):
        root, out, _truth = make_set(self)
        tree = os.path.join(root, "tree")
        script = ts.copy_tree(tree)
        self.assertTrue(os.path.isfile(os.path.join(tree, "dashboard", "api_usage.py")))
        watched = (tree, out, os.path.join(root, "home"), os.path.join(root, "home-cfg"))
        env = ts.base_env(root)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        before = ts.hash_tree(*watched)
        # No -B, so only the server's own setting keeps bytecode off. The -X option turns off
        # the cache folder Apple's python3 adds, which would hide writes from this test.
        proc = self.start(["--fixture", out], env=env, script=script,
                          python_args=["-X", "pycache_prefix="])
        deadline = time.time() + WAIT
        while time.time() < deadline:
            if json.loads(proc.request("GET", "/api/projects")[2])["reader"]["warm"]:
                break
            time.sleep(0.05)
        listing = json.loads(proc.request("GET", "/api/projects")[2])
        self.assertTrue(listing["reader"]["warm"])
        keys = [p["key"] for p in listing["projects"]]
        for path in ["/api/usage", "/api/usage?project=all", "/api/usage?project=nope",
                     "/api/usage?project=a&project=b"] + ["/api/usage?project=" + k for k in keys] \
                + ["/api/settings?project=" + k for k in keys]:
            proc.request("GET", path)
        proc.request("HEAD", "/api/usage?project=all")
        proc.request("POST", "/api/usage")
        proc.stop()
        self.assertEqual(ts.hash_tree(*watched), before)
        for folder in watched:
            self.assertEqual([d for d, _, _ in os.walk(folder) if "__pycache__" in d], [])

    def test_the_repo_is_not_dirtied_by_the_in_process_routes(self):
        _root, out, _truth = make_set(self)
        repo = [d for d, _, _ in os.walk(ts.DASHBOARD) if d.endswith("__pycache__")]
        before = ts.hash_tree(out)
        ctx = make_ctx(out)
        for scope in ("all", "tidewater-reporting", "saltmarsh"):
            call(ctx, api_usage.usage, project=scope)
        api_usage.api_projects(ctx, {})
        self.assertEqual(ts.hash_tree(out), before)
        self.assertEqual([d for d, _, _ in os.walk(ts.DASHBOARD) if d.endswith("__pycache__")], repo)


if __name__ == "__main__":
    unittest.main()

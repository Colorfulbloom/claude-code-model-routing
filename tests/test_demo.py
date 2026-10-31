"""Tests for the demo set (tests/fixtures/demo).

The set is built into a throwaway folder under the helpers sandbox, once per
class. Every planted case is checked through the transcript reader and the
resolver, so the set cannot drift. All data is made up. Nothing here reads the
real ~/.claude, the real managed folder or the real shell.
"""
import datetime
import hashlib
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

import helpers

DEMO = os.path.join(helpers.FIXTURES, "demo")
sys.path.insert(0, DEMO)
import build_demo  # noqa: E402
import resolve  # noqa: E402
import rules_schema  # noqa: E402
import transcripts  # noqa: E402

UTC = datetime.timezone.utc
LISTED = ["Tidewater reporting", "Driftwood", "Harbor Light", "Saltmarsh", "Lantern"]
WITH_FOLDER = ["Tidewater reporting", "Driftwood", "Harbor Light", "Saltmarsh"]
BY_DIR = {p["dir"]: p["name"] for p in build_demo.PROJECTS.values()}
TOTALS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h", "thinking")


def new_dir(case, prefix="d-"):
    path = os.path.realpath(tempfile.mkdtemp(prefix=prefix, dir=helpers._tmp_base()))
    case.addCleanup(helpers.rmtree_force, path)
    return path


def tree_hash(root):
    """One hash over every folder and file name and every file's bytes."""
    digest = hashlib.sha256()
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(dirs):
            digest.update(("D " + os.path.relpath(os.path.join(base, name), root) + "\n").encode())
        for name in sorted(files):
            path = os.path.join(base, name)
            digest.update(("F " + os.path.relpath(path, root) + "\n").encode())
            with open(path, "rb") as fh:
                digest.update(fh.read())
    return digest.hexdigest()


def parse_utc(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def files_under(root):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            yield os.path.join(base, name)


class Reproducible(unittest.TestCase):
    def test_same_arguments_same_bytes_and_arguments_are_used(self):
        out = os.path.join(new_dir(self), "set")
        build_demo.build(out)
        first = tree_hash(out)
        helpers.rmtree_force(out)
        build_demo.build(out)
        self.assertEqual(first, tree_hash(out), "same arguments, same bytes")

        helpers.rmtree_force(out)
        script = os.path.join(DEMO, "build_demo.py")
        subprocess.run([sys.executable, script, out], check=True, stdout=subprocess.DEVNULL)
        self.assertEqual(first, tree_hash(out), "the command line uses the same defaults")

        helpers.rmtree_force(out)
        build_demo.build(out, tz_name="America/Los_Angeles")
        self.assertNotEqual(first, tree_hash(out), "--tz changes the output")

        helpers.rmtree_force(out)
        build_demo.build(out, now="2026-10-29T18:00")
        self.assertNotEqual(first, tree_hash(out), "--now changes the output")

    def test_a_folder_that_is_not_a_demo_set_is_refused_and_left_alone(self):
        out = os.path.join(new_dir(self), "set")
        keep = os.path.join(out, "projects", "mine")
        os.makedirs(keep)
        with open(os.path.join(keep, "note.txt"), "w", encoding="utf-8") as fh:
            fh.write("not part of the demo")
        with self.assertRaises(ValueError):
            build_demo.build(out)
        self.assertTrue(os.path.isfile(os.path.join(keep, "note.txt")))
        self.assertFalse(os.path.exists(os.path.join(out, "truth.json")))

    def test_an_empty_folder_and_an_earlier_demo_set_are_both_fine(self):
        out = os.path.join(new_dir(self), "set")
        os.makedirs(out)
        build_demo.build(out)
        self.assertTrue(os.path.isfile(os.path.join(out, "truth.json")))
        build_demo.build(out)
        self.assertTrue(os.path.isfile(os.path.join(out, "truth.json")))

    def test_defaults(self):
        self.assertEqual(build_demo.DEFAULT_NOW, "2026-10-30T18:00")
        self.assertEqual(build_demo.DEFAULT_TZ, "America/New_York")

    def test_zone_has_daylight_saving(self):
        # A fixed offset would put sessions after the November 1 change an hour off.
        out = os.path.join(new_dir(self), "set")
        truth = build_demo.build(out, now="2026-11-10T18:00")
        now = parse_utc(truth["window"]["end"])
        zone = ZoneInfo("America/New_York")
        result = transcripts.Reader(os.path.join(out, "config")).read(now)
        firsts = {}
        for rec in result.records:
            if rec.run_id is None and (rec.session_id not in firsts or rec.ts_utc < firsts[rec.session_id]):
                firsts[rec.session_id] = rec.ts_utc
        after = [t.astimezone(zone) for t in firsts.values()
                 if t.astimezone(zone).date() > datetime.date(2026, 11, 1)
                 and t.astimezone(zone).date() < datetime.date(2026, 11, 10)]
        self.assertGreater(len(after), 3)
        for local in after:
            self.assertEqual(local.utcoffset(), datetime.timedelta(hours=-5))
            self.assertTrue(8 <= local.hour <= 18, local)


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix="d-", dir=helpers._tmp_base()))
        cls.out = os.path.join(cls.tmp, "set")
        cls.truth = build_demo.build(cls.out)
        cls.now = parse_utc(cls.truth["window"]["end"])
        cls.zone = ZoneInfo(build_demo.DEFAULT_TZ)
        cls.result = transcripts.Reader(os.path.join(cls.out, "config")).read(cls.now)
        cls.rules = resolve.load_rules()
        cls.fields = resolve.load_agent_fields()
        cls.confidence = {r["rule_id"]: r["confidence"] for r in cls.rules["rules"]}
        cls.entries = {}
        for name in LISTED:
            inputs = build_demo.inputs_for(cls.out, name, cls.rules)
            cls.entries[name] = resolve.resolve(inputs, cls.rules, cls.fields)

    @classmethod
    def tearDownClass(cls):
        helpers.rmtree_force(cls.tmp)

    # helpers

    def entry(self, project, key, scope="main", agent=None, layer=None):
        found = [e for e in self.entries[project]
                 if e["key"] == key and e["scope"] == scope and e.get("agent") == agent
                 and (layer is None or e["layer"] == layer)]
        self.assertEqual(len(found), 1, (project, key, scope, agent, layer, found))
        return found[0]

    def rows(self, project, key, scope="main", agent=None):
        return [e for e in self.entries[project]
                if e["key"] == key and e["scope"] == scope and e.get("agent") == agent]

    def project_of(self, rec):
        return BY_DIR[os.path.basename(rec.cwd)]

    def read_json(self, *parts):
        with open(os.path.join(*parts), encoding="utf-8") as fh:
            return json.load(fh)

    # files

    def test_config_files(self):
        for base in (DEMO, self.out):
            cfg = os.path.join(base, "config")
            for rel in ("settings.json", "agents/builder.md", "agents/reviewer.md",
                        "agents/scribe.md", "rules/writing.md", "routing-dashboard.json"):
                self.assertTrue(os.path.isfile(os.path.join(cfg, rel)), (base, rel))
        self.assertEqual(os.listdir(os.path.join(self.out, "managed")), [])
        self.assertEqual(self.read_json(DEMO, "session.json"), {"claude_version": "2.1.310", "shell_env": {"CLAUDE_CODE_EFFORT_LEVEL": ""}})
        # The build keeps the installed version and adds the clock and the zone.
        self.assertEqual(self.read_json(self.out, "session.json")["claude_version"], "2.1.310")

    def test_project_list(self):
        listing = self.read_json(self.out, "config", "routing-dashboard.json")
        self.assertEqual([p["name"] for p in listing["projects"]], LISTED)
        self.assertEqual(listing["plan"], "subscription")
        for p in listing["projects"]:
            self.assertTrue(os.path.isabs(p["path"]))
            self.assertEqual(os.path.dirname(p["path"]), os.path.join(self.out, "projects"))
        committed = self.read_json(DEMO, "config", "routing-dashboard.json")
        for p in committed["projects"]:
            self.assertFalse(os.path.isabs(p["path"]), p)
        self.assertEqual(set(listing), {"projects", "plan"})

    def test_project_folders(self):
        proj = os.path.join(self.out, "projects")
        self.assertTrue(os.path.isdir(os.path.join(proj, "tidewater-reporting", ".claude")))
        self.assertTrue(os.path.isdir(os.path.join(proj, "driftwood", ".claude")))
        self.assertTrue(os.path.isdir(os.path.join(proj, "saltmarsh", ".claude")))
        self.assertTrue(os.path.isdir(os.path.join(proj, "harbor-light")))
        self.assertEqual(os.listdir(os.path.join(proj, "harbor-light")), ["notes.txt"])
        self.assertFalse(os.path.exists(os.path.join(proj, "lantern")))
        self.assertFalse(os.path.exists(os.path.join(proj, "quarry-notes")))
        for rel in ("tidewater-reporting/.claude/settings.local.json", "driftwood/.claude/settings.local.json"):
            self.assertTrue(os.path.isfile(os.path.join(DEMO, "projects", rel)), rel)

    # reader

    def test_reader_is_clean(self):
        notes = self.result.notes
        self.assertEqual(notes["malformed_lines"], 0)
        self.assertEqual(notes["synthetic_rows"], 0)
        self.assertEqual(notes["no_id_rows"], 0)
        self.assertEqual(notes["ignored_files"], 0)
        self.assertGreater(len(self.result.records), 10000)

    def test_old_files_follow_the_cutoff(self):
        # Files whose last row is older than 61 days are skipped, as on a real machine.
        self.assertGreater(self.result.notes["skipped_old_files"], 0)
        cutoff = self.now - datetime.timedelta(days=61)
        for rec in self.result.records:
            self.assertGreater(rec.ts_utc, cutoff - datetime.timedelta(days=1))

    def test_every_row_is_global_standard(self):
        for rec in self.result.records:
            self.assertEqual(rec.inference_geo, "global")
            self.assertEqual(rec.speed, "standard")
            self.assertEqual(rec.service_tier, "standard")

    def test_folders_and_cwd(self):
        expected = set()
        for rec in self.result.records:
            self.assertTrue(rec.cwd.startswith(os.path.join(self.out, "projects") + os.sep), rec.cwd)
            self.assertEqual(rec.folder, transcripts.sanitize(rec.cwd))
            expected.add(rec.folder)
        self.assertEqual(set(os.listdir(os.path.join(self.out, "config", "projects"))), expected)
        self.assertEqual({os.path.basename(r.cwd) for r in self.result.records},
                         {"tidewater-reporting", "driftwood", "harbor-light", "quarry-notes"})

    def test_unlisted_folder(self):
        listed = {os.path.basename(p["path"]) for p in
                  self.read_json(self.out, "config", "routing-dashboard.json")["projects"]}
        self.assertNotIn("quarry-notes", listed)
        quarry = [r for r in self.result.records if os.path.basename(r.cwd) == "quarry-notes"]
        self.assertGreater(len(quarry), 20)
        self.assertFalse(os.path.exists(quarry[0].cwd))

    def test_saltmarsh_and_lantern_have_no_transcripts(self):
        proj = os.path.join(self.out, "projects")
        for name in ("saltmarsh", "lantern"):
            self.assertNotIn(transcripts.sanitize(os.path.join(proj, name)),
                             os.listdir(os.path.join(self.out, "config", "projects")))

    def test_harbor_light_has_no_row_today(self):
        today = self.now.astimezone(self.zone).date()
        harbor = [r for r in self.result.records if os.path.basename(r.cwd) == "harbor-light"]
        self.assertGreater(len(harbor), 50)
        self.assertNotIn(today, {r.ts_utc.astimezone(self.zone).date() for r in harbor})
        tide = [r for r in self.result.records if os.path.basename(r.cwd) == "tidewater-reporting"]
        self.assertIn(today, {r.ts_utc.astimezone(self.zone).date() for r in tide})

    def test_rows_never_pass_now_and_milliseconds_vary(self):
        self.assertLessEqual(max(r.ts_utc for r in self.result.records), self.now)
        millis = {r.ts_utc.microsecond // 1000 for r in self.result.records}
        self.assertGreater(len(millis), 500)

    def test_duplicate_rows_grow(self):
        groups = {}
        for rec in self.result.records:
            groups.setdefault(rec.message_id, []).append(rec)
        repeated = [g for g in groups.values() if len(g) > 1]
        self.assertGreater(len(repeated), 100)
        for group in repeated:
            outs = [r.output for r in sorted(group, key=lambda r: r.ts_utc)]
            self.assertEqual(outs, sorted(set(outs)), "earlier rows carry lower output_tokens")
            for r in group:
                self.assertLessEqual(r.thinking, r.output)

    def test_one_hour_cache_writes_and_thinking(self):
        five = sum(r.cache_write_5m for r in self.result.records)
        hour = sum(r.cache_write_1h for r in self.result.records)
        self.assertGreater(hour / float(five + hour), 0.03)
        self.assertGreater(sum(r.thinking for r in self.result.records), 0)

    def test_runs_per_agent(self):
        seen = {}
        for rec in self.result.records:
            if self.project_of(rec) == "Tidewater reporting":
                seen.setdefault(rec.agent_type, set()).add((rec.model_raw, rec.effort, rec.is_sidechain))
        self.assertEqual(seen, {
            None: {("claude-opus-5-5", "high", False)},
            "builder": {("claude-fable-5-1", "medium", True)},
            "reviewer": {("claude-sonnet-5-5", "xhigh", True)},
            "scribe": {("claude-haiku-5-5", "high", True)},
        })

    def test_driftwood_main_model_is_not_priced(self):
        models = {r.model_raw for r in self.result.records
                  if self.project_of(r) == "Driftwood" and r.agent_type is None}
        self.assertEqual(models, {"claude-opus-6-preview"})
        with open(os.path.join(helpers.REPO, "dashboard", "prices.json"), encoding="utf-8") as fh:
            self.assertNotIn("claude-opus-6-preview", json.load(fh)["models"])

    def test_meta_files_hold_only_made_up_text(self):
        count = 0
        for path in files_under(os.path.join(self.out, "config", "projects")):
            if path.endswith(".meta.json"):
                meta = self.read_json(path)
                self.assertIn(meta["agentType"], ("builder", "reviewer", "scribe"))
                self.assertEqual(meta["description"], "demo run")
                count += 1
        self.assertGreater(count, 20)

    # truth

    def test_reader_matches_truth(self):
        """Count the reader's rows the way a page would and compare with the truth."""
        latest = {}
        for rec in self.result.records:
            old = latest.get(rec.message_id)
            if old is None or rec.output > old.output:
                latest[rec.message_id] = rec
        start = parse_utc(self.truth["window"]["start"])
        for name in ("Tidewater reporting", "Driftwood", "Harbor Light"):
            mine = [r for r in latest.values()
                    if self.project_of(r) == name and start <= r.ts_utc <= self.now]
            want = self.truth["projects"][name]
            for field in TOTALS:
                self.assertEqual(sum(getattr(r, field) for r in mine), want[field], (name, field))
            self.assertEqual(len(mine), want["requests"], name)
            self.assertEqual(len({r.run_id for r in mine if r.run_id}), want["runs"], name)
            self.assertEqual(len({r.session_id for r in mine}), want["sessions"], name)
            unpriced = sum(1 for r in mine if r.model_raw == "claude-opus-6-preview")
            self.assertEqual(want["unpriced_requests"], unpriced, name)
            self.assertGreater(want["cost"], 0)
        self.assertEqual(self.truth["projects"]["Tidewater reporting"]["unpriced_requests"], 0)
        self.assertGreater(self.truth["projects"]["Driftwood"]["unpriced_requests"], 0)
        self.assertEqual(self.read_json(self.out, "truth.json"), self.truth)

    def test_window_starts_at_local_midnight(self):
        start = parse_utc(self.truth["window"]["start"]).astimezone(self.zone)
        self.assertEqual((start.year, start.month, start.day, start.hour, start.minute), (2026, 10, 1, 0, 0))
        self.assertEqual(self.now.astimezone(self.zone).strftime("%Y-%m-%dT%H:%M"), "2026-10-30T18:00")

    def test_readme_matches_truth(self):
        with open(os.path.join(DEMO, "README.md"), encoding="utf-8") as fh:
            text = fh.read()
        want = self.truth["projects"]["Tidewater reporting"]
        labels = {"input": "Input tokens", "output": "Output tokens", "cache_read": "Cache read tokens",
                  "cache_write_5m": "Cache write 5-minute tokens", "cache_write_1h": "Cache write 1-hour tokens",
                  "thinking": "Thinking tokens", "requests": "Requests", "runs": "Subagent runs",
                  "sessions": "Sessions"}
        for field, label in labels.items():
            m = re.search(r"\|\s*" + re.escape(label) + r"\s*\|\s*([0-9,]+)\s*\|", text)
            self.assertIsNotNone(m, label)
            self.assertEqual(int(m.group(1).replace(",", "")), want[field], label)
        m = re.search(r"\|\s*Cost\s*\|\s*\$([0-9,]+\.[0-9]{2})\s*\|", text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).replace(",", ""), "%.2f" % want["cost"])

    # resolver

    def test_status_and_confidence_words(self):
        statuses, confidences = set(), set()
        for name in WITH_FOLDER:
            for e in self.entries[name]:
                statuses.add(e["status"])
                ids = set(e.get("rule_ids") or []) | ({e["rule_id"]} if e.get("rule_id") else set())
                confidences.update(self.confidence[i] for i in ids)
        self.assertEqual(statuses, set(rules_schema.STATUS_WORDS))
        self.assertEqual(confidences, set(rules_schema.CONFIDENCE_WORDS))

    def test_tidewater_main_effort(self):
        rows = self.rows("Tidewater reporting", "effortLevel")
        winners = [e for e in rows if e["status"] in ("in_effect", "lowered")]
        losers = [e for e in rows if e["status"] in ("overridden", "ignored")]
        self.assertEqual(len(winners), 1)
        self.assertGreaterEqual(len(losers), 2)
        # The October 29 case: a top-level effortLevel in the user file that Opus 5.5 ignores.
        user = self.entry("Tidewater reporting", "effortLevel", layer="user")
        self.assertEqual((user["value"], user["status"], user["model"]), ("xhigh", "ignored", "claude-opus-5-5"))
        # Main xhigh, lowered to high: Matches pin, with the Lowered note.
        win = winners[0]
        self.assertEqual((win["value"], win["status"], win["becomes"]), ("xhigh", "lowered", "high"))

    def test_driftwood_main_effort_differs(self):
        tide = self.rows("Tidewater reporting", "effortLevel")
        drift = self.rows("Driftwood", "effortLevel")
        shown = lambda rows: [(e["status"], e["value"], e.get("becomes")) for e in rows]
        self.assertNotEqual(shown(tide), shown(drift))
        model = self.entry("Driftwood", "model", layer="local")
        self.assertEqual((model["value"], model["status"]), ("claude-opus-6-preview", "in_effect"))
        self.assertEqual(self.entry("Driftwood", "effortLevel", layer="local")["status"], "invalid")
        self.assertEqual(self.entry("Driftwood", "settingsFile")["status"], "ignored")

    def test_settings_cases(self):
        user = self.read_json(DEMO, "config", "settings.json")
        self.assertTrue(user["env"]["ANTHROPIC_API_KEY"].startswith("sk-ant-demo"))
        self.assertNotIn("maxEffortLevel", user)
        key = self.entry("Tidewater reporting", "env.ANTHROPIC_API_KEY")
        self.assertEqual(key["value"], "hidden")
        env = self.entry("Tidewater reporting", "env.CLAUDE_CODE_EFFORT_LEVEL", layer="local")
        self.assertEqual((env["value"], env["status"]), ("xhigh", "in_effect"))
        project = self.read_json(DEMO, "projects", "tidewater-reporting", ".claude", "settings.json")
        caps = project["modelSettings"]
        self.assertEqual(caps["claude-opus-5-5"], {"maxEffortLevel": "high"})
        self.assertEqual(caps["claude-fable-5-1"], {"maxEffortLevel": "medium"})
        self.assertNotIn("claude-sonnet-5-5", caps)
        self.assertNotIn("maxEffortLevel", project)
        layers = {e["layer"] for e in self.rows("Tidewater reporting", "rulesFile")}
        self.assertEqual(layers, {"project", "user"})

    def test_agent_cases(self):
        tide = "Tidewater reporting"
        # builder: pinned xhigh, env xhigh wins, the Fable cap lowers it to medium.
        pin = self.entry(tide, "effort", "agent", "builder", "agent")
        self.assertEqual((pin["value"], pin["status"]), ("xhigh", "overridden"))
        win = self.entry(tide, "effort", "agent", "builder", "env")
        self.assertEqual((win["value"], win["status"], win["becomes"]), ("xhigh", "lowered", "medium"))
        self.assertEqual(self.entry(tide, "model", "agent", "builder")["value"], "claude-fable-5-1")
        # reviewer: pinned high, env xhigh wins uncapped.
        pin = self.entry(tide, "effort", "agent", "reviewer", "agent")
        self.assertEqual((pin["value"], pin["status"]), ("high", "overridden"))
        win = self.entry(tide, "effort", "agent", "reviewer", "env")
        self.assertEqual((win["value"], win["status"]), ("xhigh", "in_effect"))
        self.assertNotIn("becomes", win)
        # scribe: pinned to Haiku 4.5 at medium, runs on Haiku 5.5 at high (see test_runs_per_agent).
        self.assertEqual(self.entry(tide, "model", "agent", "scribe")["value"], "claude-haiku-4-5")
        self.assertEqual(self.entry(tide, "effort", "agent", "scribe", "agent")["value"], "medium")

    def test_empty_states(self):
        self.assertFalse(os.path.exists(os.path.join(self.out, "projects", "lantern")))
        # Saltmarsh has settings, so its rows come from the user file and defaults only.
        self.assertTrue(self.entries["Saltmarsh"])
        self.assertTrue(self.entries["Lantern"])

    def test_nothing_comes_from_the_real_machine(self):
        for name in LISTED:
            for e in self.entries[name]:
                file = e.get("file")
                if file:
                    self.assertFalse(os.path.isabs(file), (name, e["key"], file))


class NoRealPaths(unittest.TestCase):
    def patterns(self):
        home = os.path.expanduser("~").encode()
        user = pwd.getpwuid(os.getuid()).pw_name.encode()
        pats = [re.compile(re.escape(b"/" + b"Users" + b"/")), re.compile(re.escape(b"/" + b"home" + b"/"))]
        if len(home) > 4:
            pats.append(re.compile(re.escape(home)))
        if len(user) > 3:
            pats.append(re.compile(rb"(?<![A-Za-z0-9])" + re.escape(user) + rb"(?![A-Za-z0-9])", re.I))
        return pats

    def scan(self, root, strip=None):
        pats = self.patterns()
        count = 0
        for path in files_under(root):
            with open(path, "rb") as fh:
                data = fh.read()
            if strip:
                data = data.replace(strip.encode(), b"")
            count += 1
            for pat in pats:
                self.assertIsNone(pat.search(data), (path, pat.pattern))
        return count

    def test_committed_files(self):
        self.assertGreater(self.scan(DEMO), 12)

    def test_built_files(self):
        out = os.path.join(new_dir(self), "set")
        build_demo.build(out)
        self.assertGreater(self.scan(out, strip=out), 100)


if __name__ == "__main__":
    unittest.main()

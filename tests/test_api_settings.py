"""Tests for the /api/settings route (dashboard/api_settings.py), the fields tickets #41 and #42 added.

The route is called through server.ROUTES with server.fixture_context, once per fixture in
tests/fixtures/resolution, then on small folders built here for the project states and on the demo
set. One test asks a real server over HTTP. Every run reads only the repo and its own temp folders.
"""
import dataclasses
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import api_settings  # noqa: E402
import build_demo  # noqa: E402
import projects  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402
import test_server  # noqa: E402

FIXTURE_DIR = os.path.join(helpers.FIXTURES, "resolution")
RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
ROUTE = server.ROUTES["/api/settings"]
ANSWER_KEYS = {
    "project", "state", "entries", "no_user_settings", "shell_label", "path_display",
    "config_dir_display", "config_file_display", "models", "rows", "rules", "files", "installed"}
REFERENCE_PAGE = os.path.join(helpers.REPO, "docs", "rules-reference.md")
REFERENCE_URL = "https://github.com/Colorfulbloom/claude-code-model-routing/blob/main/docs/rules-reference.md"
EXPERIMENT_BASE = "https://github.com/Colorfulbloom/claude-code-model-routing/blob/main/dashboard/"
WINNING = ("in_effect", "lowered", "default")


def fixture_names():
    return sorted(n for n in os.listdir(FIXTURE_DIR)
                  if os.path.isfile(os.path.join(FIXTURE_DIR, n, "expected.json")))


def context(folder, **kwargs):
    return server.fixture_context(folder, kwargs.pop("config_dir", None), kwargs.pop("project_dir", None),
                                  RULES, FIELDS, **kwargs)


def call(ctx, project=None):
    query = {} if project is None else {"project": [project]}
    return ROUTE(ctx, query)


def new_dir(case, prefix="api-"):
    path = os.path.realpath(tempfile.mkdtemp(prefix=prefix, dir=helpers._tmp_base()))
    case.addCleanup(helpers.rmtree_force, path)
    return path


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def main_value(payload, key):
    """The winner's value of a main-session row: the first entry with that key."""
    for entry in payload["entries"]:
        if entry["scope"] == "main" and entry["key"] == key:
            return entry["value"]
    raise AssertionError("no main row " + key)


class EveryFixture(unittest.TestCase):
    def test_added_fields_on_every_fixture(self):
        expected_models = {}
        for model in RULES["models"]:
            expected_models[model["id"]] = model["display_name"]
            for alias in model.get("aliases", []):
                expected_models[alias] = model["display_name"]
        for name in fixture_names():
            with self.subTest(name):
                folder = os.path.join(FIXTURE_DIR, name)
                status, payload = call(context(folder))
                self.assertEqual(status, 200)
                self.assertEqual(payload["shell_label"], resolve.LABEL_SHELL)
                self.assertEqual(payload["models"], expected_models)
                self.assertEqual(payload["config_dir_display"], "config")
                self.assertEqual(payload["config_file_display"], "config/routing-dashboard.json")
                self.assertEqual(payload["path_display"], "project")
                has_user_file = os.path.isfile(os.path.join(folder, "config", "settings.json"))
                # The implicit current project resolves even when its folder is missing.
                self.assertTrue(payload["entries"])
                self.assertEqual(payload["no_user_settings"], not has_user_file)
                self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_entries_are_unchanged_by_the_added_fields(self):
        folder = os.path.join(FIXTURE_DIR, "effort-user-top-level-xhigh-ignored-opus-5-5")
        ctx = context(folder)
        _status, payload = call(ctx)
        self.assertEqual(set(payload), ANSWER_KEYS)
        self.assertEqual(main_value(payload, "effortLevel"), "medium")

    def test_a_fixture_with_a_user_file_and_one_without(self):
        with_user = call(context(os.path.join(FIXTURE_DIR, "effort-user-top-level-xhigh-ignored-opus-5-5")))[1]
        without = call(context(os.path.join(FIXTURE_DIR, "model-main-default-unknown")))[1]
        self.assertIs(with_user["no_user_settings"], False)
        self.assertIs(without["no_user_settings"], True)

    def test_a_user_file_that_does_not_parse_still_counts_as_there(self):
        folder = os.path.join(FIXTURE_DIR, "settings-user-not-json-skipped")
        payload = call(context(folder))[1]
        self.assertIs(payload["no_user_settings"], False)


class ProjectStates(unittest.TestCase):
    def build(self, path_for):
        root = new_dir(self)
        config = os.path.join(root, "config")
        folder_path = path_for(root)
        write_json(os.path.join(config, projects.CONFIG_FILE),
                   {"projects": [{"name": "Listed", "path": folder_path}]})
        write_json(os.path.join(config, "settings.json"), {"model": "claude-opus-5-5"})
        os.makedirs(os.path.join(root, "work"))
        return context(root, config_dir=config, project_dir=os.path.join(root, "work"))

    def test_missing_folder_carries_the_display_fields_and_no_entries(self):
        ctx = self.build(lambda root: os.path.join(root, "gone"))
        status, payload = call(ctx, "listed")
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "missing_folder")
        self.assertEqual(payload["entries"], [])
        self.assertEqual(payload["path_display"], "gone")
        self.assertEqual(payload["config_dir_display"], "config")
        self.assertEqual(payload["config_file_display"], "config/routing-dashboard.json")
        self.assertEqual(payload["shell_label"], resolve.LABEL_SHELL)
        self.assertIn("claude-opus-5-5", payload["models"])

    def test_no_claude_folder_still_resolves_values(self):
        def bare(root):
            path = os.path.join(root, "bare")
            os.makedirs(path)
            return path
        ctx = self.build(bare)
        status, payload = call(ctx, "listed")
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "no_claude_folder")
        self.assertEqual(payload["path_display"], "bare")
        self.assertIs(payload["no_user_settings"], False)
        self.assertEqual(main_value(payload, "model"), "claude-opus-5-5")

    def test_no_user_settings_follows_the_file(self):
        ctx = self.build(lambda root: root)
        config = ctx.config_dir
        self.assertIs(call(ctx, "listed")[1]["no_user_settings"], False)
        os.remove(os.path.join(config, "settings.json"))
        payload = call(ctx, "listed")[1]
        self.assertIs(payload["no_user_settings"], True)
        write_json(os.path.join(config, "settings.json"), {})
        self.assertIs(call(ctx, "listed")[1]["no_user_settings"], False)

    def test_unknown_and_all_keep_their_answers(self):
        ctx = self.build(lambda root: root)
        self.assertEqual(call(ctx, "nope")[0], 404)
        self.assertEqual(call(ctx, "all")[0], 400)


class DisplayForms(unittest.TestCase):
    def test_live_context_uses_the_live_shell_label(self):
        folder = os.path.join(FIXTURE_DIR, "env-block-over-shell")
        ctx = dataclasses.replace(context(folder), shell_label=None)
        self.assertEqual(call(ctx)[1]["shell_label"], resolve.LIVE_SHELL_LABEL)

    def test_paths_under_home_show_with_a_tilde(self):
        root = new_dir(self)
        home = os.path.join(root, "home")
        config = os.path.join(home, ".claude")
        project = os.path.join(home, "work", "app")
        os.makedirs(os.path.join(project, ".claude"))
        os.makedirs(config)
        ctx = dataclasses.replace(context(root, config_dir=config, project_dir=project), home=home, root=None)
        payload = call(ctx)[1]
        self.assertEqual(payload["path_display"], "~/work/app")
        self.assertEqual(payload["config_dir_display"], "~/.claude")
        self.assertEqual(payload["config_file_display"], "~/.claude/routing-dashboard.json")
        self.assertIs(payload["no_user_settings"], True)


class DemoSet(unittest.TestCase):
    """The demo set is served the way `server.py --fixture <built set>` serves it."""

    def test_main_session_effort_differs_between_the_first_two_projects(self):
        out = new_dir(self, "api-demo-")
        build_demo.build(out)
        listing = projects.load(context(out))
        first, second = listing.projects[0], listing.projects[1]
        self.assertNotEqual(first.key, second.key)
        shown = []
        for project in (first, second):
            ctx = context(out, project_dir=project.path)
            status, payload = call(ctx, project.key)
            self.assertEqual(status, 200, project.key)
            winner = next(e for e in payload["entries"] if e["scope"] == "main" and e["key"] == "effortLevel")
            shown.append((winner["value"], winner["status"], winner.get("becomes")))
        # Both files say xhigh, but Tidewater's Opus 5.5 cap runs it as high and Driftwood's model is unknown.
        self.assertEqual(shown, [("xhigh", "lowered", "high"), ("xhigh", "unknown", None)])

    def test_main_session_effort_traces_to_winner_losers_rule_and_file_line(self):
        out = new_dir(self, "api-demo-trail-")
        build_demo.build(out)
        first = projects.load(context(out)).projects[0]
        ctx = context(out, project_dir=first.path)
        status, payload = call(ctx, first.key)
        self.assertEqual(status, 200)
        row = next(r for r in payload["rows"] if r["agent"] == "@main" and r["setting"] == "effortLevel")
        entries = [payload["entries"][i] for i in row["entries"]]
        # The winner, then the two values that lost, each with its file and line.
        self.assertEqual([(e["value"], e["status"]) for e in entries],
                         [("xhigh", "lowered"), ("medium", "overridden"), ("xhigh", "ignored")])
        winner = entries[0]
        self.assertEqual(winner["becomes"], "high")
        self.assertEqual(winner["via"], "CLAUDE_CODE_EFFORT_LEVEL")
        self.assertEqual((winner["file"], winner["line"]),
                         ("projects/tidewater-reporting/.claude/settings.local.json", 3))
        self.assertEqual((entries[1]["file"], entries[1]["line"]),
                         ("projects/tidewater-reporting/.claude/settings.json", 7))
        self.assertEqual((entries[2]["file"], entries[2]["line"]), ("config/settings.json", 3))
        for entry in entries:
            self.assertTrue(entry["reason"])
        # The rules behind the row, with their trail fields.
        self.assertEqual(row["rule_ids"], ["effort-lowered-by-cap", "effort-level-layer-order",
                                           "effort-level-user-settings-opus-5-5"])
        for rule_id in row["rule_ids"]:
            rule = payload["rules"][rule_id]
            self.assertEqual(rule["confidence"], "tested")
            self.assertTrue(rule["verified_on"]["claude_version"])
            self.assertEqual(rule["reference_url"], REFERENCE_URL + "#" + rule_id)
        # The model and the cap that the trail's meta block reads are rows of their own.
        model = next(r for r in payload["rows"] if r["agent"] == "@main" and r["setting"] == "model")
        self.assertEqual(payload["entries"][model["entries"][0]]["value"], "claude-opus-5-5")
        cap = next(r for r in payload["rows"] if r["agent"] == "@main" and r["setting"] == "maxEffortLevel")
        self.assertEqual(payload["entries"][cap["entries"][0]]["value"], "high")
        self.assertEqual([f["status"] for f in payload["files"]], ["ok", "ok", "ok"])
        self.assertEqual([f["layer"] for f in payload["files"]], ["local", "project", "user"])


def reference_headings():
    """The rule ids that have a "### <id>" heading in docs/rules-reference.md."""
    with open(REFERENCE_PAGE, encoding="utf-8") as fh:
        return set(re.findall(r"(?m)^### (\S+)\s*$", fh.read()))


class EveryRow(unittest.TestCase):
    """The trail's data, for every row of every fixture."""

    @classmethod
    def setUpClass(cls):
        cls.headings = reference_headings()
        cls.answers = {}
        for name in fixture_names():
            status, payload = call(context(os.path.join(FIXTURE_DIR, name)))
            assert status == 200, name
            cls.answers[name] = payload

    def test_there_are_fixtures_to_walk(self):
        self.assertGreater(len(self.answers), 60)

    def test_rows_cover_each_entry_exactly_once(self):
        for name, payload in self.answers.items():
            with self.subTest(name):
                seen = []
                for row in payload["rows"]:
                    seen.extend(row["entries"])
                self.assertEqual(sorted(seen), list(range(len(payload["entries"]))))
                self.assertEqual(len(seen), len(set(seen)))

    def test_agent_and_setting_are_unique_and_a_row_has_one_scope(self):
        for name, payload in self.answers.items():
            with self.subTest(name):
                keys = [(row["agent"], row["setting"]) for row in payload["rows"]]
                self.assertEqual(len(keys), len(set(keys)))
                for row in payload["rows"]:
                    entries = [payload["entries"][i] for i in row["entries"]]
                    self.assertEqual({e["scope"] for e in entries}, {row["scope"]})
                    self.assertEqual({e["key"] for e in entries}, {row["setting"]})
                    agents = {e.get("agent") or "@main" for e in entries}
                    self.assertEqual(agents, {row["agent"]})
                    self.assertEqual(row["entries"], sorted(row["entries"]))

    def test_the_first_entry_of_a_row_is_its_winner(self):
        for name, payload in self.answers.items():
            with self.subTest(name):
                for row in payload["rows"]:
                    for index in row["entries"][1:]:
                        self.assertNotIn(payload["entries"][index]["status"], WINNING, row)

    def test_every_entry_has_value_status_source_and_reason(self):
        for name, payload in self.answers.items():
            with self.subTest(name):
                for entry in payload["entries"]:
                    for field in ("value", "status", "layer", "file", "reason"):
                        self.assertIn(field, entry, entry)
                    self.assertIsInstance(entry["status"], str)
                    self.assertTrue(entry["status"])
                    self.assertIsInstance(entry["reason"], str)
                    self.assertTrue(entry["reason"].strip(), entry)
                    if entry["file"] is not None:
                        self.assertIsInstance(entry["file"], str)

    def test_row_rule_ids_join_the_entries_rule_ids_without_repeats(self):
        for name, payload in self.answers.items():
            with self.subTest(name):
                for row in payload["rows"]:
                    expected = []
                    for index in row["entries"]:
                        for rule_id in payload["entries"][index]["rule_ids"]:
                            if rule_id not in expected:
                                expected.append(rule_id)
                    self.assertEqual(row["rule_ids"], expected)
                    self.assertEqual(len(row["rule_ids"]), len(set(row["rule_ids"])))

    def test_every_rule_id_has_a_record_with_a_working_reference_link(self):
        for name, payload in self.answers.items():
            with self.subTest(name):
                named = {rule_id for row in payload["rows"] for rule_id in row["rule_ids"]}
                self.assertEqual(set(payload["rules"]), named)
                for rule_id in named:
                    rule = payload["rules"][rule_id]
                    self.assertEqual(rule["rule_id"], rule_id)
                    self.assertIn(rule["confidence"], ("tested", "documented", "assumed"))
                    self.assertTrue(rule["verified_on"]["claude_version"])
                    self.assertTrue(rule["verified_on"]["date"])
                    self.assertEqual(rule["reference_url"], REFERENCE_URL + "#" + rule_id)
                    self.assertIn(rule_id, self.headings, "docs/rules-reference.md has no ### " + rule_id)
                    self.assertIsInstance(rule["quotes"], list)
                    for quote in rule["quotes"]:
                        self.assertTrue(quote["doc_url"].startswith("https://"))
                        self.assertTrue(quote["quote"])

    def test_experiment_links_point_into_dashboard(self):
        seen = 0
        for payload in self.answers.values():
            for rule in payload["rules"].values():
                if rule["experiment"] is None:
                    self.assertIsNone(rule["experiment_url"])
                    continue
                seen += 1
                self.assertEqual(rule["experiment_url"], EXPERIMENT_BASE + rule["experiment"])
                self.assertTrue(os.path.isfile(os.path.join(helpers.REPO, "dashboard", rule["experiment"])),
                                rule["experiment"])
        self.assertGreater(seen, 0)

    def test_a_rule_record_has_exactly_the_trail_fields(self):
        for payload in self.answers.values():
            for rule in payload["rules"].values():
                self.assertEqual(set(rule), {"rule_id", "confidence", "verified_on", "due", "quotes", "experiment",
                                             "experiment_url", "reference_url"})
                self.assertEqual(set(rule["verified_on"]), {"claude_version", "date"})

    def test_files_match_the_settings_files_that_exist(self):
        for name, payload in self.answers.items():
            with self.subTest(name):
                self.assertEqual(payload["no_user_settings"], not any(f["layer"] == "user" for f in payload["files"]))
                for file in payload["files"]:
                    self.assertIn(file["status"], ("ok", "unparsed", "unreadable"))
                    self.assertIn(file["layer"], ("managed", "local", "project", "user"))
                    self.assertIsInstance(file["path"], str)
                    self.assertEqual("entry_status" in file, file["status"] != "ok", file)


class TrailData(unittest.TestCase):
    def test_a_file_that_did_not_parse_names_its_settingsfile_status(self):
        payload = call(context(os.path.join(FIXTURE_DIR, "settings-user-not-json-skipped")))[1]
        self.assertEqual(payload["files"], [
            {"layer": "project", "path": "project/.claude/settings.json", "status": "ok"},
            {"layer": "user", "path": "config/settings.json", "status": "unparsed", "entry_status": "ignored"}])
        row = next(r for r in payload["rows"] if r["setting"] == "settingsFile")
        self.assertEqual(payload["entries"][row["entries"][0]]["file"], "config/settings.json")

    def test_a_main_row_and_an_agent_row_use_their_keys(self):
        payload = call(context(os.path.join(FIXTURE_DIR, "agent-reader-rejected-but-loads")))[1]
        pairs = {(r["agent"], r["setting"]) for r in payload["rows"]}
        self.assertIn(("@main", "effortLevel"), pairs)
        self.assertIn(("probe", "effort"), pairs)
        self.assertIn(("probe", "agentFile"), pairs)

    def test_the_lowered_fixture_row(self):
        payload = call(context(os.path.join(FIXTURE_DIR, "effort-lowered-by-cap")))[1]
        row = next(r for r in payload["rows"] if r["agent"] == "@main" and r["setting"] == "effortLevel")
        self.assertEqual(row["scope"], "main")
        self.assertEqual(row["rule_ids"], ["effort-lowered-by-cap", "effort-level-layer-order"])
        rule = payload["rules"]["effort-lowered-by-cap"]
        self.assertEqual(rule["experiment_url"],
                         EXPERIMENT_BASE + "experiments/2026-10-29-effort-cap-transcript.json")
        self.assertEqual(rule["reference_url"], REFERENCE_URL + "#effort-lowered-by-cap")
        self.assertTrue(rule["quotes"])

    def test_a_missing_folder_has_no_rows_rules_or_files(self):
        root = new_dir(self)
        config = os.path.join(root, "config")
        write_json(os.path.join(config, projects.CONFIG_FILE),
                   {"projects": [{"name": "Listed", "path": os.path.join(root, "gone")}]})
        os.makedirs(os.path.join(root, "work"))
        ctx = context(root, config_dir=config, project_dir=os.path.join(root, "work"))
        payload = call(ctx, "listed")[1]
        self.assertEqual(payload["state"], "missing_folder")
        self.assertEqual((payload["rows"], payload["rules"], payload["files"]), ([], {}, []))
        self.assertEqual(set(payload), ANSWER_KEYS - {"no_user_settings"})

    def test_constants(self):
        self.assertEqual(api_settings.REFERENCE_URL, REFERENCE_URL)
        self.assertEqual(api_settings.EXPERIMENT_BASE, EXPERIMENT_BASE)


class VersionAndDue(unittest.TestCase):
    NAME = "effort-lowered-by-cap"

    def payload(self, **replace):
        ctx = context(os.path.join(FIXTURE_DIR, self.NAME))
        if replace:
            ctx = dataclasses.replace(ctx, **replace)
        return call(ctx)[1]

    def test_a_fixture_has_no_installed_version_and_no_rule_is_due(self):
        payload = self.payload()
        self.assertIsNone(payload["installed"])
        self.assertTrue(payload["rules"])
        for rule in payload["rules"].values():
            self.assertIs(rule["due"], False)

    def test_a_newer_install_makes_the_older_rules_due(self):
        payload = self.payload(claude_version="2.1.1000")
        self.assertEqual(payload["installed"], "2.1.1000")
        for rule in payload["rules"].values():
            self.assertIs(rule["due"], True, rule["rule_id"])

    def test_an_install_at_or_below_the_check_is_not_due(self):
        for installed in ("2.1.302", "2.1.5", "2.0"):
            payload = self.payload(claude_version=installed)
            self.assertEqual(payload["installed"], installed)
            for rule in payload["rules"].values():
                self.assertIs(rule["due"], False, (installed, rule["rule_id"]))

    def test_due_follows_each_rules_own_version(self):
        rule = dict(RULES["rules"][0])
        rule["verified_on"] = {"claude_version": "2.1.400", "date": "2026-10-29"}
        self.assertIs(api_settings._rule_record(rule, "2.1.500")["due"], True)
        self.assertIs(api_settings._rule_record(rule, "2.1.400")["due"], False)
        self.assertIs(api_settings._rule_record(rule, "2.1.399")["due"], False)
        self.assertIs(api_settings._rule_record(rule, None)["due"], False)

    def test_a_missing_folder_carries_installed_too(self):
        root = new_dir(self)
        config = os.path.join(root, "config")
        write_json(os.path.join(config, projects.CONFIG_FILE),
                   {"projects": [{"name": "Listed", "path": os.path.join(root, "gone")}]})
        os.makedirs(os.path.join(root, "work"))
        ctx = dataclasses.replace(
            context(root, config_dir=config, project_dir=os.path.join(root, "work")), claude_version="2.1.310")
        payload = call(ctx, "listed")[1]
        self.assertEqual(payload["installed"], "2.1.310")

    def test_version_field_counts_the_agent_field_table(self):
        ctx = context(os.path.join(FIXTURE_DIR, self.NAME))
        field = api_settings.version_field(ctx)
        self.assertEqual(field, {"installed": None, "rules_oldest": "2.1.302"})
        older_rules = {"rules": [dict(r, verified_on={"claude_version": "2.2.0", "date": "2026-10-29"})
                                 for r in RULES["rules"]]}
        field = api_settings.version_field(dataclasses.replace(ctx, rules=older_rules))
        # The table in agent_fields.json is the oldest here.
        self.assertEqual(field["rules_oldest"], "2.1.302")
        with mock.patch.object(api_settings, "_agent_fields_version", return_value=None):
            self.assertEqual(api_settings.version_field(
                dataclasses.replace(ctx, rules=older_rules))["rules_oldest"], "2.2.0")

    def test_an_unreadable_field_table_gives_none(self):
        with mock.patch.object(api_settings.agent_frontmatter, "FIELDS_PATH", "/nonexistent/agent_fields.json"):
            self.assertIsNone(api_settings._agent_fields_version())


ORDER = ["unknown", "lowered", "ignored", "overridden", "invalid"]


def attention_entry(status, value, key="effortLevel", agent=None):
    return {"key": key, "agent": agent, "scope": "main" if agent is None else "agent",
            "status": status, "value": value}


class OverHttp(test_server.TempCase):
    def test_a_real_request_returns_the_trail_fields(self):
        name = "effort-lowered-by-cap"
        folder = os.path.join(FIXTURE_DIR, name)
        expected = json.loads(json.dumps(call(context(folder))[1]))
        proc = self.start(["--fixture", folder], name=name)
        status, _, body = proc.request("GET", "/api/settings")
        self.assertEqual(status, 200)
        answer = json.loads(body)
        self.assertEqual(set(answer), ANSWER_KEYS)
        self.assertEqual(answer, expected)
        self.assertEqual(answer["rules"]["effort-lowered-by-cap"]["reference_url"],
                         REFERENCE_URL + "#effort-lowered-by-cap")


if __name__ == "__main__":
    unittest.main()

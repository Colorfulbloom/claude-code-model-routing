"""Tests for the /api/settings route (dashboard/api_settings.py), the fields ticket #41 added.

The route is called through server.ROUTES with server.fixture_context, once per fixture in
tests/fixtures/resolution, then on small folders built here for the project states and on the demo
set. Every run reads only the repo and its own temp folders.
"""
import dataclasses
import json
import os
import sys
import tempfile
import unittest

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import build_demo  # noqa: E402
import projects  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402

FIXTURE_DIR = os.path.join(helpers.FIXTURES, "resolution")
RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
ROUTE = server.ROUTES["/api/settings"]


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
        self.assertEqual(set(payload), {
            "project", "state", "entries", "no_user_settings", "shell_label", "path_display",
            "config_dir_display", "config_file_display", "models"})
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


if __name__ == "__main__":
    unittest.main()

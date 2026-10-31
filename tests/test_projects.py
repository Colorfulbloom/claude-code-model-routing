"""Tests for the project list: dashboard/projects.py, /api/projects and /api/settings.

Servers run through test_server's helpers, always with --fixture and a temp
folder. Every name and path here is made up. Secrets are strings that start
with "sk-planted-" and no other value in these tests contains "planted".
"""
import contextlib
import dataclasses
import io
import json
import os
import shutil
import sys
import unittest

import helpers
import test_server as ts

sys.path.insert(0, ts.DASHBOARD)
import projects  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402

CONFIG_FILE = "routing-dashboard.json"
FIXTURE_DIR = ts.FIXTURE_DIR


class Base(ts.TempCase):
    def setUp(self):
        super().setUp()
        self.fx = os.path.join(self.root, "fx")
        self.cfg = os.path.join(self.root, "cfg")
        os.makedirs(self.fx)
        os.makedirs(self.cfg)

    def make_project(self, name, claude=True, settings=None):
        path = os.path.join(self.root, "work", name)
        os.makedirs(path, exist_ok=True)
        if claude:
            ts.write_json(os.path.join(path, ".claude", "settings.json"), settings or {})
        return path

    def write_list(self, items, **extra):
        data = {"projects": items}
        data.update(extra)
        ts.write_json(os.path.join(self.cfg, CONFIG_FILE), data)

    def serve(self, project=None, folder=None, name="srv"):
        args = ["--fixture", folder or self.fx, "--config-dir", self.cfg]
        if project:
            args += ["--project", project]
        return self.start(args, name=name)

    def get(self, proc, path):
        status, _, body = proc.request("GET", path)
        return status, json.loads(body)

    def ctx(self, home=None):
        ctx = server.fixture_context(self.fx, self.cfg, None, ts.RULES, ts.FIELDS)
        return dataclasses.replace(ctx, home=home)

    def stderr_of(self, fn):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = fn()
        return result, buf.getvalue()


class Format(Base):
    def test_absolute_path(self):
        a = self.make_project("alpha")
        self.write_list([{"name": "Alpha", "path": a}])
        _, payload = projects.api_projects(self.ctx(), {})
        self.assertEqual(payload["projects"], [
            {"key": "alpha", "name": "Alpha", "path_display": a, "state": "ok"}])
        self.assertEqual(payload["current"], "alpha")

    def test_relative_path_resolves_against_the_config_folder(self):
        os.makedirs(os.path.join(self.cfg, "sub", "proj", ".claude"))
        os.makedirs(os.path.join(self.root, "rel-proj", ".claude"))
        self.write_list([{"name": "One", "path": "sub/proj"},
                         {"name": "Two", "path": "../rel-proj"}])
        _, payload = projects.api_projects(self.ctx(), {})
        self.assertEqual([p["state"] for p in payload["projects"]], ["ok", "ok"])
        self.assertEqual(payload["projects"][1]["path_display"],
                         os.path.join(self.root, "rel-proj"))

    def test_tilde_expands_with_home_and_displays_as_tilde(self):
        home = os.path.join(self.root, "fakehome")
        os.makedirs(os.path.join(home, "work", "shop", ".claude"))
        self.write_list([{"name": "Shop", "path": "~/work/shop"},
                         {"name": "Home", "path": "~"},
                         {"name": "Gone", "path": "~/work/gone"}])
        _, payload = projects.api_projects(self.ctx(home=home), {})
        rows = {p["key"]: p for p in payload["projects"]}
        self.assertEqual(rows["shop"]["path_display"], "~/work/shop")
        self.assertEqual(rows["shop"]["state"], "ok")
        self.assertEqual(rows["home"]["path_display"], "~")
        self.assertEqual(rows["home"]["state"], "no_claude_folder")
        self.assertEqual(rows["gone"]["path_display"], "~/work/gone")
        self.assertEqual(rows["gone"]["state"], "missing_folder")
        self.assertNotIn(home, json.dumps(payload))

    def test_tilde_without_a_home_stays_unexpanded_and_missing(self):
        self.write_list([{"name": "Shop", "path": "~/work/shop"}])
        _, payload = projects.api_projects(self.ctx(home=None), {})
        self.assertEqual(payload["projects"][0]["state"], "missing_folder")
        self.assertEqual(payload["projects"][0]["path_display"], "~/work/shop")

    def test_no_file_lists_the_current_project_only(self):
        ctx = self.ctx()
        _, payload = projects.api_projects(ctx, {})
        self.assertEqual(len(payload["projects"]), 1)
        self.assertEqual(payload["projects"][0]["name"], "project")
        self.assertEqual(payload["current"], "project")
        self.assertEqual(set(payload), {"projects", "current"})
        self.assertEqual(set(payload["projects"][0]),
                         {"key", "name", "path_display", "state"})

    def test_broken_json_falls_back_with_one_fixed_stderr_line(self):
        ts.write(os.path.join(self.cfg, CONFIG_FILE), "{not json sk-planted-broken-0001")
        (status, payload), err = self.stderr_of(lambda: projects.api_projects(self.ctx(), {}))
        self.assertEqual([p["name"] for p in payload["projects"]], ["project"])
        self.assertEqual(len(err.splitlines()), 1)
        self.assertNotIn("sk-planted", err)

    def test_non_object_falls_back_with_one_fixed_stderr_line(self):
        ts.write(os.path.join(self.cfg, CONFIG_FILE), '["sk-planted-array-0002"]')
        (status, payload), err = self.stderr_of(lambda: projects.api_projects(self.ctx(), {}))
        self.assertEqual([p["name"] for p in payload["projects"]], ["project"])
        self.assertEqual(len(err.splitlines()), 1)
        self.assertNotIn("sk-planted", err)

    def test_unreadable_file_falls_back(self):
        os.makedirs(os.path.join(self.cfg, CONFIG_FILE))  # a folder cannot be read as a file
        (status, payload), err = self.stderr_of(lambda: projects.api_projects(self.ctx(), {}))
        self.assertEqual([p["name"] for p in payload["projects"]], ["project"])
        self.assertEqual(len(err.splitlines()), 1)

    def test_no_valid_entry_falls_back(self):
        self.write_list([{"name": "", "path": "/x"}, {"name": "n"}, "text", 5,
                         {"name": 3, "path": "/y"}, {"name": "n", "path": ""}])
        (status, payload), err = self.stderr_of(lambda: projects.api_projects(self.ctx(), {}))
        self.assertEqual([p["name"] for p in payload["projects"]], ["project"])
        self.assertEqual(len(err.splitlines()), 1)

    def test_bad_entries_are_skipped_and_good_ones_kept(self):
        a = self.make_project("alpha")
        self.write_list(["text", {"name": "x"}, {"name": "Alpha", "path": a},
                         {"path": a}, None])
        _, payload = projects.api_projects(self.ctx(), {})
        self.assertEqual([p["name"] for p in payload["projects"]], ["Alpha"])

    def test_same_normalized_path_keeps_the_first(self):
        a = self.make_project("alpha")
        self.write_list([{"name": "First", "path": a},
                         {"name": "Second", "path": a + "/"},
                         {"name": "Third", "path": os.path.join(a, "..", "alpha")}])
        _, payload = projects.api_projects(self.ctx(), {})
        self.assertEqual([p["name"] for p in payload["projects"]], ["First"])

    def test_a_file_with_only_a_plan_lists_the_current_project_quietly(self):
        ts.write_json(os.path.join(self.cfg, CONFIG_FILE), {"plan": "api_key"})
        (status, payload), err = self.stderr_of(lambda: projects.api_projects(self.ctx(), {}))
        self.assertEqual([p["name"] for p in payload["projects"]], ["project"])
        self.assertEqual(err, "")


class Keys(Base):
    def keys_for(self, names):
        self.write_list([{"name": n, "path": "/nowhere/%d" % i} for i, n in enumerate(names)])
        _, payload = projects.api_projects(self.ctx(), {})
        return [p["key"] for p in payload["projects"]]

    def test_slug(self):
        self.assertEqual(self.keys_for(["  My Big_App!! v2  ", "--x--"]), ["my-big-app-v2", "x"])

    def test_all_is_reserved(self):
        self.assertEqual(self.keys_for(["All", "ALL"]), ["all-2", "all-3"])

    def test_duplicates_count_up_in_list_order(self):
        self.assertEqual(self.keys_for(["Shop", "shop", "SHOP!", "Shop 2"]),
                         ["shop", "shop-2", "shop-3", "shop-2-2"])

    def test_non_ascii_names(self):
        self.assertEqual(self.keys_for(["Café ☕", "日本", "日本語", "!!!"]),
                         ["caf", "project", "project-2", "project-3"])


class States(Base):
    def test_all_three_states(self):
        ok = self.make_project("withclaude")
        bare = self.make_project("bare", claude=False)
        gone = os.path.join(self.root, "work", "gone")
        file_path = ts.write(os.path.join(self.root, "work", "afile"), "x")
        self.write_list([{"name": "Ok", "path": ok}, {"name": "Bare", "path": bare},
                         {"name": "Gone", "path": gone}, {"name": "File", "path": file_path}])
        proc = self.serve()
        status, payload = self.get(proc, "/api/projects")
        self.assertEqual(status, 200)
        self.assertEqual([p["state"] for p in payload["projects"]],
                         ["ok", "no_claude_folder", "missing_folder", "missing_folder"])

    def test_missing_folder_settings_are_empty_and_unread(self):
        gone = os.path.join(self.root, "work", "gone")
        self.write_list([{"name": "Gone", "path": gone}])
        proc = self.serve()
        status, payload = self.get(proc, "/api/settings?project=gone")
        self.assertEqual(status, 200)
        self.assertEqual((payload["project"], payload["state"]), ("gone", "missing_folder"))
        # Nothing was read: only the names the empty state needs come back.
        self.assertEqual((payload["entries"], payload["rows"], payload["rules"], payload["files"]),
                         ([], [], {}, []))
        self.assertNotIn("no_user_settings", payload)

    def test_no_claude_folder_settings_still_resolve(self):
        bare = self.make_project("bare", claude=False)
        self.write_list([{"name": "Bare", "path": bare}])
        proc = self.serve()
        status, payload = self.get(proc, "/api/settings?project=bare")
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "no_claude_folder")
        self.assertGreater(len(payload["entries"]), 0)


class Current(Base):
    def test_explicit_project_is_added_first(self):
        a = self.make_project("alpha")
        extra = self.make_project("extra")
        self.write_list([{"name": "Alpha", "path": a}])
        proc = self.serve(project=extra)
        _, payload = self.get(proc, "/api/projects")
        self.assertEqual([p["name"] for p in payload["projects"]], ["extra", "Alpha"])
        self.assertEqual(payload["current"], "extra")

    def test_explicit_project_that_is_listed_is_not_added(self):
        a = self.make_project("alpha")
        b = self.make_project("beta")
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        proc = self.serve(project=b)
        _, payload = self.get(proc, "/api/projects")
        self.assertEqual([p["name"] for p in payload["projects"]], ["Alpha", "Beta"])
        self.assertEqual(payload["current"], "beta")

    def test_without_project_the_list_is_the_files_and_current_is_first(self):
        a = self.make_project("alpha")
        b = self.make_project("beta")
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        proc = self.serve()
        _, payload = self.get(proc, "/api/projects")
        self.assertEqual([p["name"] for p in payload["projects"]], ["Alpha", "Beta"])
        self.assertEqual(payload["current"], "alpha")

    def test_settings_without_a_key_answer_for_current(self):
        a = self.make_project("alpha")
        self.write_list([{"name": "Alpha", "path": a}])
        proc = self.serve()
        status, payload = self.get(proc, "/api/settings")
        self.assertEqual((status, payload["project"], payload["state"]), (200, "alpha", "ok"))

    def test_unlisted_transcript_folders_stay_out(self):
        a = self.make_project("alpha")
        self.write_list([{"name": "Alpha", "path": a}])
        ts.write(os.path.join(self.cfg, "projects", "-made-up-other", "s.jsonl"), "{}\n")
        proc = self.serve()
        text = proc.request("GET", "/api/projects")[2].decode("utf-8")
        self.assertNotIn("made-up-other", text)
        self.assertEqual(len(json.loads(text)["projects"]), 1)


class OwnValues(Base):
    def entries_text(self, payload):
        return "\n".join(ts.all_text(payload["entries"]))

    def test_two_projects_each_get_their_own_values(self):
        a = self.make_project("alpha", settings={"env": {"ANTHROPIC_MODEL": "claude-opus-5-5"}})
        b = self.make_project("beta", settings={"env": {"CLAUDE_CODE_EFFORT_LEVEL": "high"}})
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        proc = self.serve()
        _, one = self.get(proc, "/api/settings?project=alpha")
        _, two = self.get(proc, "/api/settings?project=beta")
        self.assertEqual((one["project"], two["project"]), ("alpha", "beta"))
        self.assertIn(os.path.join(a, ".claude", "settings.json"), self.entries_text(one))
        self.assertNotIn(os.path.join(b, ".claude", "settings.json"), self.entries_text(one))
        self.assertIn(os.path.join(b, ".claude", "settings.json"), self.entries_text(two))
        self.assertNotIn(os.path.join(a, ".claude", "settings.json"), self.entries_text(two))
        self.assertNotEqual(one["entries"], two["entries"])

    def test_an_edit_to_one_projects_file_shows_in_the_next_answer(self):
        a = self.make_project("alpha")
        b = self.make_project("beta", settings={"env": {"CLAUDE_CODE_EFFORT_LEVEL": "high"}})
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        proc = self.serve()
        before_a = self.get(proc, "/api/settings?project=alpha")[1]
        before_b = self.get(proc, "/api/settings?project=beta")[1]
        ts.write_json(os.path.join(b, ".claude", "settings.json"),
                      {"env": {"CLAUDE_CODE_EFFORT_LEVEL": "low"}})
        after_a = self.get(proc, "/api/settings?project=alpha")[1]
        after_b = self.get(proc, "/api/settings?project=beta")[1]
        self.assertEqual(before_a, after_a)
        self.assertNotEqual(before_b, after_b)
        self.assertIn("low", self.entries_text(after_b))

    def test_a_hand_edit_of_the_list_shows_in_the_next_request(self):
        a = self.make_project("alpha")
        b = self.make_project("beta")
        self.write_list([{"name": "Alpha", "path": a}])
        proc = self.serve()
        first = self.get(proc, "/api/projects")[1]
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        second = self.get(proc, "/api/projects")[1]
        self.assertEqual([p["key"] for p in first["projects"]], ["alpha"])
        self.assertEqual([p["key"] for p in second["projects"]], ["alpha", "beta"])
        self.assertEqual(self.get(proc, "/api/settings?project=beta")[0], 200)


class Refusals(Base):
    def setUp(self):
        super().setUp()
        self.a = self.make_project("alpha", settings={"env": {"ANTHROPIC_MODEL": "claude-opus-5-5"}})
        self.write_list([{"name": "Alpha", "path": self.a}])
        self.proc = self.serve()

    def test_unknown_keys_get_404_and_no_settings_data(self):
        for query in ("project=/some/path", "project=..", "project=%2Fetc%2Fpasswd",
                      "project=nope", "project=ALPHA", "project=" + self.a,
                      "project=alpha/../alpha", "project=planted-key-echo-0001"):
            status, heads, body = self.proc.request("GET", "/api/settings?" + query)
            self.assertEqual(status, 404, query)
            self.assertEqual(json.loads(body), {"error": "unknown_project"}, query)
            self.assertNotIn(b"entries", body)
            self.assertNotIn(b"planted", body)
        self.assertNotIn("planted", self.proc.stderr())

    def test_all_asks_for_one_project(self):
        status, _, body = self.proc.request("GET", "/api/settings?project=all")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body), {"error": "pick_project"})

    def test_more_than_one_project_value_is_a_bad_request(self):
        status, _, body = self.proc.request("GET", "/api/settings?project=alpha&project=alpha")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body), {"error": "bad_request"})

    def test_a_listed_key_still_works(self):
        self.assertEqual(self.proc.request("GET", "/api/settings?project=alpha")[0], 200)


class Plan(Base):
    CASES = "prompt-cache-plan-%s"

    def case_folder(self, name):
        dest = os.path.join(self.root, name)
        shutil.copytree(os.path.join(FIXTURE_DIR, name), dest)
        expected_path = os.path.join(dest, "expected.json")
        with open(expected_path, encoding="utf-8") as fh:
            expected = json.load(fh)
        os.remove(expected_path)
        os.remove(os.path.join(dest, "dashboard.json"))
        return dest, expected

    def entries_with(self, folder, config):
        """Serve the folder with config as routing-dashboard.json and return (entries, stderr)."""
        cfg = os.path.join(folder, "config")
        if config is not None:
            ts.write(os.path.join(cfg, CONFIG_FILE), config)
        proc = self.start(["--fixture", folder], name="p%d" % len(self._procs))
        status, payload = self.get(proc, "/api/settings")
        self.assertEqual(status, 200)
        return payload["entries"], proc.stderr()

    def plan_json(self, value):
        return json.dumps({"plan": value})

    def test_subscription_reaches_the_entry(self):
        folder, expected = self.case_folder("prompt-cache-plan-subscription-unknown")
        entries, _ = self.entries_with(folder, self.plan_json("subscription"))
        self.assertEqual(resolve.compare(entries, expected), [])

    def test_api_key_reaches_the_entry(self):
        folder, expected = self.case_folder("prompt-cache-plan-api-key-five-minutes")
        entries, _ = self.entries_with(folder, self.plan_json("api_key"))
        self.assertEqual(resolve.compare(entries, expected), [])

    def test_cloud_provider_reaches_the_entry(self):
        folder, expected = self.case_folder("prompt-cache-plan-api-key-five-minutes")
        entries, _ = self.entries_with(folder, self.plan_json("cloud_provider"))
        self.assertEqual(resolve.compare(entries, expected), [])

    def unset_entries(self, folder_name):
        inputs, _ = resolve.load_fixture(os.path.join(FIXTURE_DIR, folder_name), ts.RULES)
        inputs = dataclasses.replace(inputs, plan=None)
        return json.loads(json.dumps(resolve.resolve(inputs, ts.RULES, ts.FIELDS)))

    def test_missing_plan_shows_unknown(self):
        name = "prompt-cache-plan-api-key-five-minutes"
        folder, expected = self.case_folder(name)
        entries, _ = self.entries_with(folder, json.dumps({"projects": []}))
        self.assertEqual(entries, self.unset_entries(name))
        self.assertNotEqual(resolve.compare(entries, expected), [])

    def test_unknown_plan_behaves_as_unset_and_is_never_logged(self):
        name = "prompt-cache-plan-api-key-five-minutes"
        folder, _ = self.case_folder(name)
        for value in ("planted-plan-value-0001", 7, ["api_key"], "API_KEY"):
            entries, err = self.entries_with(folder, self.plan_json(value))
            self.assertEqual(entries, self.unset_entries(name))
            self.assertNotIn("planted-plan", err)
            self.assertIn("unknown plan", err)

    def test_the_file_wins_over_the_fixture_dashboard_json(self):
        name = "prompt-cache-plan-api-key-five-minutes"
        folder = os.path.join(self.root, "both")
        shutil.copytree(os.path.join(FIXTURE_DIR, name), folder)
        with open(os.path.join(folder, "expected.json"), encoding="utf-8") as fh:
            expected = json.load(fh)
        os.remove(os.path.join(folder, "expected.json"))
        entries, _ = self.entries_with(folder, self.plan_json("subscription"))
        self.assertNotEqual(resolve.compare(entries, expected), [])  # dashboard.json says api_key


class Secrets(Base):
    def test_a_planted_secret_reaches_no_body_and_no_log(self):
        secrets = {"alpha": "sk-planted-alpha-0001", "beta": "sk-planted-beta-0002"}
        a = self.make_project("alpha", settings={"env": {"ANTHROPIC_API_KEY": secrets["alpha"]},
                                                 "apiKeyHelper": secrets["alpha"]})
        b = self.make_project("beta", settings={"env": {"ANTHROPIC_AUTH_TOKEN": secrets["beta"]},
                                                "apiKeyHelper": secrets["beta"]})
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        proc = self.serve()
        bodies = []
        for path in ("/api/projects", "/api/settings", "/api/settings?project=alpha",
                     "/api/settings?project=beta", "/api/settings?project=all",
                     "/api/settings?project=zzz"):
            bodies.append(proc.request("GET", path)[2].decode("utf-8"))
        everything = "\n".join(bodies + [proc.stderr(), proc.stdout()])
        self.assertNotIn("planted", everything)


if __name__ == "__main__":
    unittest.main()

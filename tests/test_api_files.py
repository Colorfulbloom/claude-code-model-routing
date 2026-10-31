"""Tests for the /api/files route (dashboard/api_settings.py), the data behind the Installed files page (#65).

Most tests install into a sandbox (helpers.Sandbox) by running the real install.py with HOME and
CLAUDE_CONFIG_DIR inside a throwaway folder and a stub claude, the way tests/test_features.py does, then call the
route on that config folder with the sandbox's copy of the repo. Nothing reads or writes the real home or the real
~/.claude, and the real claude never runs. The demo test builds the made-up demo set into a temp folder.
"""
import contextlib
import dataclasses
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import api_settings  # noqa: E402
import build_demo  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402
import test_server  # noqa: E402

RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
ROUTE = server.ROUTES["/api/files"]
NOT_IN_PLAN = ("settings.json", "model-routing-manifest.txt")  # the installer writes these, the plan has no entry
SCOUT = "agents/scout.md"


def new_dir(case, prefix="files-"):
    path = os.path.realpath(tempfile.mkdtemp(prefix=prefix, dir=helpers._tmp_base()))
    case.addCleanup(helpers.rmtree_force, path)
    return path


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def states(payload):
    return {item["path"]: item["state"] for item in payload["files"]}


def tree_stats(root):
    """Every path under root with its kind, size and mtime in nanoseconds, links not followed."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            info = os.lstat(full)
            out[os.path.relpath(full, root)] = (oct(info.st_mode), info.st_size, info.st_mtime_ns)
    return out


class InstalledCase(unittest.TestCase):
    """A sandbox with a fresh install, and a Context that points at it."""

    def setUp(self):
        self.sb = helpers.Sandbox("new")
        self.addCleanup(self.sb.cleanup)
        self.cfg = self.sb.cfg

    def install(self, *args):
        step = self.sb.run(["--yes"] + list(args))
        self.assertEqual(step.code, 0, step.err)
        return step

    def ctx(self, **replace):
        base = server.fixture_context(self.sb.p("fixture"), self.cfg, None, RULES, FIELDS)
        kwargs = {"repo_dir": self.sb.src, "root": self.sb.root}
        kwargs.update(replace)
        return dataclasses.replace(base, **kwargs)

    def answer(self, **replace):
        status, payload = ROUTE(self.ctx(**replace), {})
        self.assertEqual(status, 200)
        return payload

    def shown(self, rel):
        """The display form of a file in the config folder, as the route writes it."""
        return "cfg/" + rel

    def installed_files(self):
        found = set()
        for dirpath, _dirs, names in os.walk(self.cfg):
            for name in names:
                rel = os.path.relpath(os.path.join(dirpath, name), self.cfg)
                if rel in NOT_IN_PLAN or rel.startswith("backups" + os.sep):
                    continue
                found.add(self.shown(rel.replace(os.sep, "/")))
        return found


class FreshInstall(InstalledCase):
    def test_every_file_matches_after_a_fresh_install(self):
        self.install()
        payload = self.answer()
        self.assertEqual(set(payload), {"files"})
        self.assertGreater(len(payload["files"]), 10)
        for item in payload["files"]:
            self.assertEqual(set(item), {"path", "state"})
            self.assertEqual(item["state"], "match", item["path"])

    def test_the_list_is_what_the_installer_wrote_less_the_manifest_and_settings(self):
        self.install()
        paths = [item["path"] for item in self.answer()["files"]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(set(paths), self.installed_files())
        for name in NOT_IN_PLAN:
            self.assertTrue(os.path.exists(os.path.join(self.cfg, name)), name)
            self.assertNotIn(self.shown(name), paths)

    def test_the_order_is_the_plans(self):
        self.install()
        paths = [item["path"] for item in self.answer()["files"]]
        self.assertEqual(paths[-1], self.shown("model-routing-choices.json"))
        agents = [p for p in paths if p.startswith(self.shown("agents/"))]
        self.assertEqual(agents, sorted(agents))
        self.assertLess(paths.index(agents[-1]), paths.index(self.shown("model-routing-choices.json")))
        self.assertLess(paths.index(agents[-1]), min(i for i, p in enumerate(paths) if "/rules/" in p))

    def test_nothing_installed_gives_missing_for_every_file(self):
        payload = self.answer()
        self.assertFalse(os.path.exists(self.cfg))
        self.assertGreater(len(payload["files"]), 10)
        self.assertEqual({item["state"] for item in payload["files"]}, {"missing"})

    def test_a_file_the_plan_does_not_name_does_not_show(self):
        self.install()
        write(os.path.join(self.cfg, "agents", "stray.md"), "---\nname: stray\n---\n")
        write(os.path.join(self.cfg, "rules", "extra.md"), "extra\n")
        write(os.path.join(self.cfg, "notes.txt"), "hello\n")
        paths = [item["path"] for item in self.answer()["files"]]
        for rel in ("agents/stray.md", "rules/extra.md", "notes.txt", "settings.json", "model-routing-manifest.txt"):
            self.assertNotIn(self.shown(rel), paths)
        self.assertEqual(set(paths) | {self.shown(r) for r in ("agents/stray.md", "rules/extra.md", "notes.txt")},
                         self.installed_files())


class Edits(InstalledCase):
    def test_a_hand_edit_to_an_agents_effort_differs_and_the_rest_match(self):
        self.install()
        path = os.path.join(self.cfg, SCOUT)
        text = read(path).decode("utf-8")
        edited = "".join(("effort: low\n" if line.startswith("effort:") and line != "effort: low\n" else
                          "effort: max\n" if line.startswith("effort:") else line)
                         for line in text.splitlines(True))
        self.assertNotEqual(edited, text)
        write(path, edited)
        got = states(self.answer())
        self.assertEqual(got.pop(self.shown(SCOUT)), "differs")
        self.assertEqual(set(got.values()), {"match"})

    def test_a_deleted_file_is_missing_and_the_rest_match(self):
        self.install()
        os.remove(os.path.join(self.cfg, SCOUT))
        got = states(self.answer())
        self.assertEqual(got.pop(self.shown(SCOUT)), "missing")
        self.assertEqual(set(got.values()), {"match"})

    def test_a_dangling_link_is_missing(self):
        self.install()
        path = os.path.join(self.cfg, SCOUT)
        os.remove(path)
        os.symlink(os.path.join(self.sb.root, "nowhere.md"), path)
        self.assertEqual(states(self.answer())[self.shown(SCOUT)], "missing")

    def test_a_link_to_the_same_bytes_matches(self):
        self.install()
        path = os.path.join(self.cfg, SCOUT)
        real = os.path.join(self.sb.root, "real-scout.md")
        os.replace(path, real)
        os.symlink(real, path)
        self.assertEqual(states(self.answer())[self.shown(SCOUT)], "match")

    def test_a_folder_where_a_file_belongs_differs(self):
        self.install()
        path = os.path.join(self.cfg, SCOUT)
        os.remove(path)
        os.makedirs(path)
        self.assertEqual(states(self.answer())[self.shown(SCOUT)], "differs")

    def test_a_file_where_a_folder_belongs_is_missing(self):
        self.install()
        folder = os.path.join(self.cfg, "rules")
        helpers.rmtree_force(folder)
        write(folder, "not a folder\n")
        got = states(self.answer())
        rules = [p for p in got if p.startswith(self.shown("rules/"))]
        self.assertTrue(rules)
        for rel in rules:
            self.assertEqual(got[rel], "missing", rel)

    def test_a_longer_file_and_a_shorter_file_differ(self):
        self.install()
        path = os.path.join(self.cfg, SCOUT)
        data = read(path)
        write(path, data + b"\n")
        self.assertEqual(states(self.answer())[self.shown(SCOUT)], "differs")
        write(path, data[:-1])
        self.assertEqual(states(self.answer())[self.shown(SCOUT)], "differs")
        write(path, b"")
        self.assertEqual(states(self.answer())[self.shown(SCOUT)], "differs")

    def test_a_file_that_cannot_be_read_differs(self):
        self.install()
        path = os.path.join(self.cfg, SCOUT)
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o644)
        self.assertEqual(states(self.answer())[self.shown(SCOUT)], "differs")

    def test_file_modes_are_not_compared(self):
        self.install()
        path = os.path.join(self.cfg, SCOUT)
        os.chmod(path, 0o600)
        self.assertEqual(states(self.answer())[self.shown(SCOUT)], "match")


class SavedChoices(InstalledCase):
    def test_a_saved_choice_that_changes_an_agent_still_matches(self):
        self.install("--agent", "scout=sonnet:high")
        installed = read(os.path.join(self.cfg, SCOUT))
        self.assertIn(b"model: sonnet\n", installed)
        self.assertIn(b"effort: high\n", installed)
        self.assertNotEqual(installed, read(os.path.join(self.sb.src, SCOUT)), "the choice must change the file")
        choices = json.loads(read(os.path.join(self.cfg, "model-routing-choices.json")))
        self.assertEqual(choices["agents"]["scout"], {"model": "sonnet", "effort": "high"})
        got = states(self.answer())
        self.assertEqual(got[self.shown(SCOUT)], "match")
        self.assertEqual(set(got.values()), {"match"})

    def test_a_copy_of_the_repo_file_differs_once_a_choice_changed_the_agent(self):
        self.install("--agent", "scout=sonnet:high")
        write(os.path.join(self.cfg, SCOUT), read(os.path.join(self.sb.src, SCOUT)))
        got = states(self.answer())
        self.assertEqual(got.pop(self.shown(SCOUT)), "differs")
        self.assertEqual(set(got.values()), {"match"})

    def test_a_choices_file_that_is_not_usable_falls_back_to_the_defaults(self):
        self.install()
        write(os.path.join(self.cfg, "model-routing-choices.json"), "not json")
        got = states(self.answer())
        self.assertEqual(got.pop(self.shown("model-routing-choices.json")), "differs")
        self.assertEqual(set(got.values()), {"match"})


class Display(InstalledCase):
    def test_paths_are_relative_to_the_fixture_root(self):
        self.install()
        paths = [item["path"] for item in self.answer()["files"]]
        self.assertTrue(all(p.startswith("cfg/") for p in paths), paths[:3])

    def test_paths_under_home_show_with_a_tilde(self):
        self.install()
        paths = [item["path"] for item in self.answer(root=None, home=self.sb.root)["files"]]
        self.assertTrue(all(p.startswith("~/cfg/") for p in paths), paths[:3])

    def test_other_paths_show_in_full(self):
        self.install()
        paths = [item["path"] for item in self.answer(root=None, home=None)["files"]]
        self.assertTrue(all(p.startswith(self.cfg + "/") for p in paths), paths[:3])


class ReadOnly(InstalledCase):
    def snapshot(self):
        return tree_stats(self.sb.root)

    def test_the_route_writes_nothing(self):
        self.install("--agent", "scout=sonnet:high")
        write(os.path.join(self.cfg, SCOUT), "edited\n")
        os.remove(os.path.join(self.cfg, "rules", sorted(os.listdir(os.path.join(self.cfg, "rules")))[0]))
        before = self.snapshot()
        payload = self.answer()
        self.answer()
        after = self.snapshot()
        self.assertEqual({"match", "differs", "missing"}, {i["state"] for i in payload["files"]})
        self.assertEqual(before, after)

    def test_the_route_writes_nothing_before_any_install(self):
        before = self.snapshot()
        self.answer()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(os.path.exists(self.cfg))

    def test_the_installer_functions_print_nothing(self):
        self.install("--agent", "scout=sonnet:high")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.answer()
            ROUTE(self.ctx(repo_dir=new_dir(self)), {})
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))

    def test_a_file_is_read_up_to_one_byte_past_the_plans(self):
        asked = []

        class Fake(io.BytesIO):
            def read(self, size=-1):
                asked.append(size)
                return super().read(size)

        with mock.patch.object(api_settings, "open", lambda path, mode: Fake(b"x" * 1000), create=True):
            self.assertEqual(api_settings._file_state("/a/file", b"abc"), "differs")
        self.assertEqual(asked, [4])

    def test_the_file_is_opened_for_reading_in_binary_only(self):
        modes = []

        def fake_open(path, mode="r", *args, **kwargs):
            modes.append(mode)
            return io.BytesIO(b"abc")

        with mock.patch.object(api_settings, "open", fake_open, create=True):
            self.assertEqual(api_settings._file_state("/a/file", b"abc"), "match")
        self.assertEqual(modes, ["rb"])


class InstallerErrors(unittest.TestCase):
    def ctx(self, repo):
        base = server.fixture_context(repo, os.path.join(repo, "config"), None, RULES, FIELDS)
        return dataclasses.replace(base, repo_dir=repo)

    def test_a_repo_with_nothing_to_install_gives_an_installer_error(self):
        repo = new_dir(self)
        self.assertEqual(ROUTE(self.ctx(repo), {}), (500, {"error": "installer"}))

    def test_an_agent_without_a_model_line_gives_an_installer_error(self):
        repo = new_dir(self)
        write(os.path.join(repo, "agents", "odd.md"), "---\nname: odd\ndescription: x\n---\nBody\n")
        self.assertEqual(ROUTE(self.ctx(repo), {}), (500, {"error": "installer"}))

    def test_a_repo_with_only_rules_still_answers(self):
        repo = new_dir(self)
        write(os.path.join(repo, "rules", "one.md"), "one\n")
        status, payload = ROUTE(self.ctx(repo), {})
        self.assertEqual(status, 200)
        self.assertEqual([i["path"] for i in payload["files"]],
                         ["config/rules/one.md", "config/model-routing-choices.json"])
        self.assertEqual({i["state"] for i in payload["files"]}, {"missing"})


class ContextRepo(unittest.TestCase):
    def test_the_default_is_the_repo_this_server_runs_from(self):
        self.assertEqual(server.REPO_DIR, helpers.REPO)
        ctx = server.fixture_context(os.path.join(helpers.FIXTURES, "resolution", "effort-lowered-by-cap"),
                                     None, None, RULES, FIELDS)
        self.assertEqual(ctx.repo_dir, server.REPO_DIR)
        live = server.live_context("/c", "/p", {"HOME": "/h"}, "linux", RULES, FIELDS)
        self.assertEqual(live.repo_dir, server.REPO_DIR)

    def test_a_fixture_with_a_repo_folder_uses_it(self):
        folder = new_dir(self)
        os.makedirs(os.path.join(folder, "repo"))
        ctx = server.fixture_context(folder, None, None, RULES, FIELDS)
        self.assertEqual(ctx.repo_dir, os.path.join(folder, "repo"))

    def test_a_repo_that_is_a_file_is_not_a_repo_folder(self):
        folder = new_dir(self)
        write(os.path.join(folder, "repo"), "x")
        self.assertEqual(server.fixture_context(folder, None, None, RULES, FIELDS).repo_dir, server.REPO_DIR)


class DemoSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = os.path.realpath(tempfile.mkdtemp(prefix="files-demo-", dir=helpers._tmp_base()))
        build_demo.build(cls.out)

    @classmethod
    def tearDownClass(cls):
        helpers.rmtree_force(cls.out)

    def test_the_demo_shows_all_three_states(self):
        ctx = server.fixture_context(self.out, None, None, RULES, FIELDS)
        self.assertEqual(ctx.repo_dir, os.path.join(self.out, "repo"))
        status, payload = ROUTE(ctx, {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["files"], [
            {"path": "config/agents/builder.md", "state": "match"},
            {"path": "config/agents/reviewer.md", "state": "match"},
            {"path": "config/agents/scribe.md", "state": "differs"},
            {"path": "config/agents/tech-writer.md", "state": "missing"},
            {"path": "config/rules/writing.md", "state": "match"},
            {"path": "config/model-routing-choices.json", "state": "match"},
        ])

    def test_the_demo_reads_no_real_file(self):
        ctx = server.fixture_context(self.out, None, None, RULES, FIELDS)
        self.assertTrue(helpers._inside(ctx.repo_dir, self.out))
        self.assertTrue(helpers._inside(ctx.config_dir, self.out))
        self.assertFalse(helpers._inside(ctx.repo_dir, helpers.REPO))

    def test_builder_matches_only_through_the_saved_choice(self):
        committed = os.path.join(helpers.FIXTURES, "demo")
        repo = read(os.path.join(committed, "repo", "agents", "builder.md"))
        config = read(os.path.join(committed, "config", "agents", "builder.md"))
        self.assertNotEqual(repo, config)
        self.assertEqual(repo.split(b"---\n")[2], config.split(b"---\n")[2], "only the model and effort lines differ")


class SweepTexts(unittest.TestCase):
    """tests/e2e_checks/files.json names texts the demo set shows. Check them against the route, no browser."""

    def test_the_texts_match_the_demo_answer(self):
        with open(os.path.join(helpers.REPO, "tests", "e2e_checks", "files.json"), encoding="utf-8") as fh:
            checks = json.load(fh)
        demo = server.fixture_context(os.path.join(helpers.FIXTURES, "demo"), None, None, RULES, FIELDS)
        payload = ROUTE(demo, {})[1]
        texts = checks["routes"][0]["texts"]
        paths = [item["path"] for item in payload["files"]]
        self.assertEqual([t for t in texts if t.startswith("config/")], paths)
        self.assertEqual({item["state"] for item in payload["files"]}, {"match", "differs", "missing"})
        for word in ("Matches", "Differs", "Missing", "Nothing to do",
                     "Run the installer again to update it", "Run the installer to add it"):
            self.assertIn(word, texts)
        for text in texts:  # the table head is upper case on screen, so the sweep leaves it out
            self.assertNotIn(text.lower(), ("file", "state", "what to do"))


class OverHttp(test_server.TempCase):
    def test_a_real_request_returns_the_demo_answer(self):
        out = os.path.join(self.root, "set")
        build_demo.build(out)
        proc = self.start(["--fixture", out], name="files")
        status, _, body = proc.request("GET", "/api/files")
        self.assertEqual(status, 200)
        answer = json.loads(body)
        self.assertEqual([i["state"] for i in answer["files"]],
                         ["match", "match", "differs", "missing", "match", "match"])
        self.assertEqual(answer["files"][0]["path"], "config/agents/builder.md")


if __name__ == "__main__":
    unittest.main()

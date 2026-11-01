"""Tests for dashboard/api_edit.py, the edit routes (#83).

Every test runs in process on temp folders: a throwaway config folder, a project
folder and a made-up managed folder, with a Context built by server.live_context
or server.fixture_context and an EditState with a fixed test token. No HTTP is
needed, because the gate belongs to tests/test_edit_server.py. Nothing reads the
real Claude config folder. Secrets are made-up strings that start with
"sk-planted-". The loops over every fixture work on a temp copy, so no save can
dirty the repo's tests/fixtures.
"""
import collections
import dataclasses
import datetime
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers

DASHBOARD = os.path.join(helpers.REPO, "dashboard")
sys.path.insert(0, DASHBOARD)
import api_edit  # noqa: E402
import api_settings  # noqa: E402
import edit_store  # noqa: E402
import git_check  # noqa: E402
import json_edit  # noqa: E402
import projects  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402

RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
TOKEN = "test-token-not-a-real-secret"
FIXED = datetime.datetime(2026, 10, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)
SECRET = "sk-planted-0123456789abcdef"
TESTS = Path(__file__).resolve().parent
TABLE = TESTS / "fixtures" / "edit_ref_table.json"
CHECKS = TESTS / "js" / "edit_ref_checks.mjs"
NODE = shutil.which("node")
FLAG = "--experimental-default-type=module"
FIXTURE_DIR = os.path.join(helpers.FIXTURES, "resolution")
LEVELS = ("low", "medium", "high", "xhigh")
LIMIT_KEYS = {"kind", "value", "layer", "file_display", "line", "editable", "target", "lock_reason"}
SOURCE = Path(api_edit.__file__.replace(".pyc", ".py"))
OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"


def dumps(obj):
    return json.dumps(obj, indent=2) + "\n"


class World:
    """A config folder, a project folder and a managed folder in a temp root, plus a Context on them."""

    def __init__(self, case, user=None, project=None, local=None, managed=None, agents=None,
                 shell_env=None, listed=None, edit=True):
        # A MR_TEST_TMP inside a repo must not lock every edit test. A test that wants a lock
        # sets its own return value on self.place.
        self.place = mock.patch.object(git_check, "repo_place", return_value="no_repo")
        self.place.start()
        case.addCleanup(self.place.stop)
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-api-edit-", dir=helpers._tmp_base()))
        case.addCleanup(helpers.rmtree_force, self.root)
        self.cfg = os.path.join(self.root, "config")
        self.proj = os.path.join(self.root, "project")
        self.managed = os.path.join(self.root, "managed")
        os.makedirs(self.cfg)
        os.makedirs(os.path.join(self.proj, ".claude"))
        for layer, content in (("user", user), ("project", project), ("local", local),
                               ("managed", managed)):
            if content is not None:
                self.write(layer, content)
        for name, text in (agents or {}).items():
            self.put(os.path.join(self.cfg, "agents", name + ".md"), text)
        if listed is not None:
            # {proj} and {root} stand for this world's folders in a listed project's path.
            items = [dict(item, path=item["path"].replace("{proj}", self.proj).replace("{root}", self.root))
                     for item in listed]
            self.put(os.path.join(self.cfg, "routing-dashboard.json"), dumps({"projects": items}))
        ctx = server.live_context(self.cfg, self.proj, dict(shell_env or {}), "linux", RULES, FIELDS)
        ctx = dataclasses.replace(ctx, managed_dir=self.managed, root=self.root)
        self.store = edit_store.Store(self.cfg, fixed_now=FIXED)
        if edit:
            ctx = dataclasses.replace(ctx, edit=api_edit.EditState(TOKEN, "launch-test", self.store))
        self.ctx = ctx
        self.key = projects.load(ctx).current

    # files

    def path(self, layer):
        return {"user": os.path.join(self.cfg, "settings.json"),
                "project": os.path.join(self.proj, ".claude", "settings.json"),
                "local": os.path.join(self.proj, ".claude", "settings.local.json"),
                "managed": os.path.join(self.managed, "managed-settings.json")}[layer]

    @staticmethod
    def put(path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if isinstance(content, (dict, list)):
            content = dumps(content)
        if isinstance(content, str):
            content = content.encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(content)

    def write(self, layer, content):
        self.put(self.path(layer), content)

    def read(self, layer):
        with open(self.path(layer), "rb") as fh:
            return fh.read()

    def snapshot(self):
        return helpers.tree_snapshot(self.root)

    def real(self, display):
        """Return the path on disk of a display path (these worlds show paths relative to the root)."""
        return os.path.join(self.root, *display.split("/"))

    # routes

    def targets(self, project=None):
        status, body = api_edit.targets(self.ctx, {"project": [project or self.key]})
        assert status == 200, (status, body)
        return body

    def body(self, target, value, **extra):
        out = {"project": self.key, "target": target, "value": value}
        out.update(extra)
        return out

    def preview(self, target, value, **extra):
        return api_edit.preview(self.ctx, self.body(target, value, **extra))

    def save_body(self, preview, target, value, **extra):
        out = self.body(target, value, base_file=preview["base_file"], base_trail=preview["base_trail"],
                        base_others=preview["base_others"])
        out.update(extra)
        return out

    def save(self, preview, target, value, **extra):
        return api_edit.save(self.ctx, self.save_body(preview, target, value, **extra))

    def edit(self, target, value):
        """Preview, then save. Returns the save body, and fails the test when either is not a 200."""
        status, pv = self.preview(target, value)
        assert status == 200, (status, pv)
        status, body = self.save(pv, target, value)
        assert status == 200, (status, body)
        return body

    def undo(self, edit_id, **extra):
        body = {"project": self.key, "edit": edit_id}
        body.update(extra)
        return api_edit.undo(self.ctx, body)

    def history(self, project=None):
        status, body = api_edit.history(self.ctx, {"project": [project or self.key]})
        assert status == 200, (status, body)
        return body


def lock_repo(case, world, place="subfolder"):
    """Make the world's project a repo subfolder (or "linked"), so every write locks."""
    world.place.stop()
    world.place = mock.patch.object(git_check, "repo_place", return_value=place)
    world.place.start()
    case.addCleanup(world.place.stop)


def target_of(body, layer, ends=None):
    """Return the one target row of a layer, optionally the one whose ref ends with `ends`."""
    found = [t for t in body["targets"] if t["layer"] == layer and (ends is None or ends in t["ref"])]
    assert len(found) == 1, (layer, ends, body["targets"])
    return found[0]


def level_of(body, level):
    return [row for row in body["levels"] if row["level"] == level][0]


def file_of(row, layer):
    """Return the row of one file in a level answer or in the top-level files list."""
    rows = row["files"] if isinstance(row, dict) else row
    return [f for f in rows if f["layer"] == layer][0]


def project_row(row):
    return file_of(row, "project")


def kinds(row):
    return [limit["kind"] for limit in row["limits"]]


def main_effort(payload):
    """Return the first entry of the main effort row of a settings payload (its winner)."""
    return api_edit._effort_row(payload["entries"])[0]


class Base(unittest.TestCase):
    def assert_limits(self, limits):
        for limit in limits:
            self.assertEqual(set(limit), LIMIT_KEYS)
            self.assertIs(limit["editable"], False)
            self.assertIsNone(limit["target"])


# --------------------------------------------------------------------------
# Constants, ids, the ref and its node twin

class Constants(Base):
    def test_levels_are_the_values_of_the_settings_rule(self):
        rule = [r for r in RULES["rules"] if r["rule_id"] == "effort-level-settings-values"][0]
        values = [c["values"] for c in rule["conditions"] if "values" in c]
        self.assertTrue(values)
        for found in values:
            self.assertEqual(list(api_edit.LEVELS), found)
        self.assertNotIn("max", api_edit.LEVELS)

    def test_the_editable_table_holds_two_key_paths(self):
        yes = [("effortLevel",), ("modelSettings", OPUS, "effortLevel"),
               ("modelSettings", "us.anthropic.claude-opus-5-5-v1:0", "effortLevel")]
        no = [(), ("model",), ("maxEffortLevel",), ("env", "CLAUDE_CODE_EFFORT_LEVEL"), ("hooks",),
              ("permissions", "allow"), ("apiKeyHelper",), ("autoCompactWindow",),
              ("modelSettings", OPUS, "maxEffortLevel"), ("modelSettings", "effortLevel"),
              ("modelSettings", OPUS, "effortLevel", "x"), ("modelSettings", 0, "effortLevel"),
              ("effortLevel", "x"), ("hooks", "effortLevel")]
        for key_path in yes:
            self.assertTrue(api_edit._key_allowed(key_path), key_path)
        for key_path in no:
            self.assertFalse(api_edit._key_allowed(key_path), key_path)

    def test_target_ids_are_stable_and_opaque(self):
        one = api_edit._target_id("user", ("effortLevel",))
        self.assertRegex(one, r"^t-[0-9a-f]{16}$")
        self.assertEqual(one, api_edit._target_id("user", ["effortLevel"]))
        others = {api_edit._target_id("project", ("effortLevel",)),
                  api_edit._target_id("user", ("modelSettings", OPUS, "effortLevel"))}
        self.assertNotIn(one, others)
        self.assertEqual(len(others), 2)

    def test_hmac_is_keyed_by_the_token_and_repeatable(self):
        ctx = World(self, user={}).ctx
        other = dataclasses.replace(ctx, edit=api_edit.EditState("another-token", "x", None))
        self.assertEqual(api_edit._hmac(ctx, b"abc"), api_edit._hmac(ctx, b"abc"))
        self.assertNotEqual(api_edit._hmac(ctx, b"abc"), api_edit._hmac(other, b"abc"))
        self.assertNotEqual(api_edit._hmac(ctx, b"abc"), api_edit._hmac(ctx, b"abd"))
        self.assertRegex(api_edit._hmac(ctx, b""), r"^[0-9a-f]{64}$")

    def test_the_module_writes_nothing_itself(self):
        text = SOURCE.read_text(encoding="utf-8")
        for banned in (r"\bopen\(", r"\.write\(", r"\.writelines\(", r"\bshutil\b", r"\btempfile\b",
                       r"\bsubprocess\b", r"os\.(remove|unlink|rename|replace|mkdir|makedirs|rmdir|chmod|symlink|link|truncate)\b"):
            self.assertIsNone(re.search(banned, text), banned)

    def test_edit_info_is_unchanged(self):
        world = World(self, user={})
        self.assertEqual(api_edit.edit_info(world.ctx, {}), (200, {"enabled": True, "launch_id": "launch-test"}))
        off = World(self, user={}, edit=False)
        self.assertEqual(api_edit.edit_info(off.ctx, {}), (200, {"enabled": False, "launch_id": None}))
        status, body = api_edit.targets(off.ctx, {})
        self.assertEqual((status, body["enabled"]), (200, False))
        self.assertEqual(api_edit.history(off.ctx, {}), (200, {"enabled": False}))


class RefTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(TABLE, encoding="utf-8") as fh:
            cls.rows = json.load(fh)

    def test_the_table_has_about_ten_rows(self):
        self.assertGreaterEqual(len(self.rows), 10)

    def test_python_builds_each_ref(self):
        for row in self.rows:
            self.assertEqual(api_edit.ref_of(row["entry"]), row["ref"], row["note"])

    def test_the_line_is_not_part_of_the_ref(self):
        entry = {"key": "effortLevel", "layer": "user", "file": "a.json", "line": 3}
        self.assertEqual(api_edit.ref_of(entry), api_edit.ref_of(dict(entry, line=900)))
        self.assertEqual(api_edit.ref_of(entry), api_edit.ref_of({k: v for k, v in entry.items() if k != "line"}))

    def test_the_agent_defaults_to_the_main_session_and_the_path_to_the_key(self):
        parts = json.loads(api_edit.ref_of({"key": "effortLevel", "layer": "user", "file": None, "path": ""}))
        self.assertEqual(parts, ["@main", "effortLevel", "user", None, "effortLevel"])

    @unittest.skipUnless(NODE, "node is not installed")
    def test_node_builds_the_same_refs(self):
        probe = subprocess.run([NODE, FLAG, "-e", "0"], capture_output=True, text=True, timeout=60)
        flags = [FLAG] if probe.returncode == 0 else []
        run = subprocess.run([NODE] + flags + [str(CHECKS)], capture_output=True, text=True, timeout=300)
        report = run.stdout + run.stderr
        if run.returncode != 0:
            sys.stderr.write(report)
        self.assertEqual(run.returncode, 0, report)
        self.assertIn("checks passed", run.stdout)
        self.assertNotIn("FAIL", run.stdout)


# --------------------------------------------------------------------------
# GET targets: shapes, matching and blocked rows

class TargetsShape(Base):
    def test_a_project_value_is_a_target_with_every_field(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual(set(body), {"enabled", "project", "state", "agent", "setting", "runs_as", "model",
                                     "levels_state", "project_lock", "targets", "adds", "blocked", "files",
                                     "levels", "saveable"})
        self.assertEqual((body["enabled"], body["project"], body["state"], body["agent"], body["setting"]),
                         (True, "project", "ok", "@main", "effortLevel"))
        self.assertEqual((body["runs_as"], body["model"], body["levels_state"]), ("high", SONNET, "ok"))
        row = target_of(body, "project")
        self.assertEqual(set(row), {"target", "ref", "layer", "file_display", "line", "current_value",
                                    "status", "shared", "in_effect", "remove"})
        self.assertEqual((row["file_display"], row["line"], row["current_value"], row["status"]),
                         ("project/.claude/settings.json", 2, "high", "in_effect"))
        self.assertIs(row["shared"], True)
        self.assertIs(row["in_effect"], True)
        self.assertEqual(row["ref"], '["@main","effortLevel","project","project/.claude/settings.json","effortLevel"]')

    def test_a_user_value_is_not_shared_and_a_loser_is_not_in_effect(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"effortLevel": "high"})
        body = world.targets()
        user = target_of(body, "user")
        project = target_of(body, "project")
        self.assertIs(user["shared"], False)
        self.assertIs(user["in_effect"], False)
        self.assertEqual(user["status"], "overridden")
        self.assertIs(project["in_effect"], True)
        self.assertTrue(user["ref"].endswith('"modelSettings.claude-opus-5-5.effortLevel"]'))

    def test_a_lowered_winner_is_in_effect_for_the_page(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "xhigh"})
        row = target_of(world.targets(), "project")
        self.assertEqual(row["status"], "lowered")
        self.assertIs(row["in_effect"], True)

    def test_a_dotted_model_name_keeps_its_key_path_from_the_raw_file(self):
        dotted = "us.anthropic.claude-opus-5-5-v1:0"
        world = World(self, user={"model": OPUS, "modelSettings": {
            dotted: {"effortLevel": "low"}, OPUS: {"effortLevel": "medium"}}})
        body = world.targets()
        self.assertEqual(len(body["targets"]), 2)
        listing = projects.load(world.ctx)
        view = api_edit._view(world.ctx, listing, listing.find(world.key))
        paths = sorted(t.key_path for t in view.targets)
        self.assertEqual(paths, sorted([("modelSettings", dotted, "effortLevel"),
                                        ("modelSettings", OPUS, "effortLevel")]))
        by_name = {t.key_path[1]: t for t in view.targets}
        self.assertEqual(by_name[dotted].entry["value"], "low")
        self.assertEqual(by_name[OPUS].entry["value"], "medium")
        # An edit through the dotted target changes only that line.
        pv = inner_preview(world, by_name[dotted].id, "high")  # the Opus entry wins, so the route refuses it
        changed = [line["text"] for hunk in pv["diff"]["hunks"] for line in hunk["lines"]
                   if line["kind"] in ("add", "del")]
        self.assertEqual(changed, ['      "effortLevel": "low"', '      "effortLevel": "high"'])

    def test_a_minified_file_gives_no_false_match(self):
        raw = ('{"model":"%s","effortLevel":"high","modelSettings":{"%s":{"effortLevel":"low"}}}'
               % (OPUS, OPUS))
        world = World(self, user=raw)
        body = world.targets()
        refs = [t["ref"] for t in body["targets"]] + [b["ref"] for b in body["blocked"]]
        self.assertEqual(len(refs), len(set(refs)))
        per_model = target_of(body, "user", "modelSettings.claude-opus-5-5.effortLevel")
        top = target_of(body, "user", '"effortLevel"]')
        self.assertNotEqual(per_model["ref"], top["ref"])
        self.assertEqual(per_model["line"], top["line"])
        status, pv = world.preview(per_model["target"], "medium")
        self.assertEqual(status, 200)
        world.save(pv, per_model["target"], "medium")
        self.assertEqual(world.read("user").decode(),
                         raw.replace('"effortLevel":"low"', '"effortLevel":"medium"'))

    def test_no_target_exposes_a_key_path_or_a_raw_path(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"effortLevel": "high"})
        body = world.targets()
        for row in body["targets"] + body["blocked"]:
            self.assertNotIn("key_path", row)
            self.assertNotIn("path", row)
        text = json.dumps(body)
        self.assertNotIn(world.root, text)

    def test_the_answer_is_the_same_bytes_twice(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"effortLevel": "high"}, managed={"maxEffortLevel": "xhigh"})
        first = json.dumps(world.targets())
        self.assertEqual(first, json.dumps(world.targets()))

    def test_the_project_value_rules(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"},
                      listed=[{"name": "alpha", "path": "{proj}"}])
        for asked, status, error in ((["alpha", "other"], 400, "bad_request"), (["all"], 400, "bad_request"),
                                     (["nope"], 404, "unknown_project")):
            got = api_edit.targets(world.ctx, {"project": asked})
            self.assertEqual(got, (status, {"error": error}), asked)
        # No value means the current project.
        plain = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        status, body = api_edit.targets(plain.ctx, {})
        self.assertEqual((status, body["project"]), (200, plain.key))

    def test_a_folder_that_is_missing_gives_no_targets_and_no_levels(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      listed=[{"name": "Gone", "path": "{root}/no-such-folder"}])
        self.assertEqual(world.key, "gone")
        body = world.targets()
        self.assertEqual((body["state"], body["levels_state"], body["targets"], body["blocked"], body["levels"]),
                         ("missing_folder", "model_unknown", [], [], []))
        self.assertEqual((body["runs_as"], body["model"]), (None, None))
        status, pv = world.preview(api_edit._target_id("user", ("effortLevel",)), "low")
        self.assertEqual((status, pv), (422, {"error": "file_missing"}))  # was 400 not_editable before creates


class BlockedRows(Base):
    def blocked(self, world):
        return {row["reason"]: row for row in world.targets()["blocked"]}

    def test_a_shell_variable_is_env_shell(self):
        world = World(self, user={"model": SONNET}, shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "low"})
        row = self.blocked(world)["env_shell"]
        self.assertEqual((row["layer"], row["value"]), ("env", "low"))
        self.assertIsNone(row["line"])
        self.assertEqual(set(row), {"ref", "layer", "file_display", "line", "value", "reason"})

    def test_an_env_block_is_env_file_with_a_line(self):
        world = World(self, user={"model": SONNET, "env": {"CLAUDE_CODE_EFFORT_LEVEL": "low"}})
        row = self.blocked(world)["env_file"]
        self.assertEqual((row["layer"], row["file_display"], row["line"]), ("env", "config/settings.json", 4))

    def test_managed_flag_and_cli_rows(self):
        world = World(self, user={"model": SONNET}, managed={"effortLevel": "medium"})
        world.ctx = dataclasses.replace(world.ctx, flags=("--effort", "high"), cli_settings={"effortLevel": "low"})
        got = self.blocked(world)
        for reason in ("managed", "flag", "cli"):
            self.assertIn(reason, got, reason)
            self.assertEqual(got[reason]["layer"], reason)
        self.assertEqual(got["managed"]["value"], "medium")
        self.assertEqual(got["managed"]["file_display"], "managed/managed-settings.json")

    def test_a_default_winner_is_a_blocked_row_with_reason_default(self):
        world = World(self, user={"model": OPUS})
        got = self.blocked(world)
        self.assertEqual(list(got), ["default"])
        self.assertEqual((got["default"]["layer"], got["default"]["file_display"]), ("default", None))

    def test_a_row_that_is_blocked_and_a_row_that_is_a_target_never_share_a_ref(self):
        world = World(self, user={"model": SONNET, "effortLevel": "low"}, managed={"effortLevel": "high"})
        body = world.targets()
        refs = [t["ref"] for t in body["targets"]] + [b["ref"] for b in body["blocked"]]
        self.assertEqual(len(refs), len(set(refs)))

    def test_a_symlinked_file_is_blocked_as_symlink(self):
        world = World(self, user={"model": SONNET})
        real = os.path.join(world.root, "elsewhere.json")
        world.put(real, {"effortLevel": "high"})
        os.symlink(real, world.path("project"))
        body = world.targets()
        self.assertEqual(self.blocked(world)["symlink"]["layer"], "project")
        self.assertEqual([t for t in body["targets"] if t["layer"] == "project"], [])

    def test_a_hard_linked_file_is_blocked_as_hard_link(self):
        world = World(self, user={"model": SONNET})
        real = os.path.join(world.root, "elsewhere.json")
        world.put(real, {"effortLevel": "high"})
        os.link(real, world.path("project"))
        self.assertEqual(self.blocked(world)["hard_link"]["layer"], "project")

    def test_a_file_over_one_mebibyte_is_blocked_as_too_large(self):
        world = World(self, user={"model": SONNET})
        pad = "x" * (edit_store.MAX_FILE + 10)
        world.write("project", json.dumps({"effortLevel": "high", "pad": pad}))
        self.assertEqual(self.blocked(world)["too_large"]["layer"], "project")

    def test_a_walk_that_fails_does_not_count_as_a_missing_folder(self):
        target = mock.Mock()
        for exc in (edit_store.Refused("not_owner"), OSError(5, "simulated")):
            with mock.patch.object(edit_store, "folder_missing", side_effect=exc):
                self.assertFalse(api_edit._folder_missing(target))

    def test_a_file_that_just_went_is_unparsed(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        with mock.patch.object(edit_store, "read_target", side_effect=edit_store.Refused("file_missing")):
            self.assertEqual(self.blocked(world)["unparsed"]["layer"], "project")

    def test_a_file_the_strict_parser_refuses_is_unparsed(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        with mock.patch.object(edit_store, "read_target", return_value=b"{not json"):
            self.assertEqual(self.blocked(world)["unparsed"]["layer"], "project")

    def test_a_path_that_matches_no_name_in_the_raw_file_is_unparsed(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}})
        with mock.patch.object(edit_store, "read_target", return_value=b'{"modelSettings": {}}'):
            self.assertEqual(self.blocked(world)["unparsed"]["layer"], "user")

    def test_a_target_that_went_blocked_answers_422_with_its_reason(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        project = target_of(world.targets(), "project")["target"]
        with mock.patch.object(edit_store, "read_target", return_value=b"{not json"):
            status, body = world.preview(project, "low")
        self.assertEqual((status, body), (422, {"error": "unparsed"}))
        # An id that is in neither list is not editable.
        self.assertEqual(world.preview("t-0000000000000000", "low"), (400, {"error": "not_editable"}))

    def test_a_secret_shaped_value_shows_hidden_in_blocked_rows_and_limits(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"},
                      shell_env={"CLAUDE_CODE_EFFORT_LEVEL": SECRET})
        body = world.targets()
        self.assertNotIn("sk-planted", json.dumps(body))
        self.assertEqual(self.blocked(world)["env_shell"]["value"], "hidden")


# --------------------------------------------------------------------------
# Levels

class Levels(Base):
    def test_a_level_per_name_with_the_row_fields(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual([row["level"] for row in body["levels"]], list(LEVELS))
        project = target_of(body, "project")["target"]
        for row in body["levels"]:
            self.assertEqual(set(row), {"level", "result", "runs_as", "certain", "limits", "files",
                                        "preselect", "saveable"})
            self.assertIs(row["certain"], True)
            self.assertEqual(row["limits"], [])
        self.assertEqual(level_of(body, "high"), {"level": "high", "result": "now", "runs_as": "high",
                                                  "certain": True, "limits": [], "files": [],
                                                  "preselect": None, "saveable": False})
        for name in ("low", "medium", "xhigh"):
            row = level_of(body, name)
            # The absent local file is a create that applies, so it is the preselect.
            self.assertEqual((row["result"], row["runs_as"], row["certain"], row["limits"], row["preselect"],
                              row["saveable"]),
                             ("reachable", name, True, [], file_of(row, "local")["target"], True))
            self.assertEqual(file_of(row, "local")["op"], "create")
            self.assertEqual([f["layer"] for f in row["files"]], ["local", "project", "user"])
            self.assertEqual(row["files"][1], {"layer": "project", "target": project, "op": "replace", "line": 2,
                                               "runs_as": name, "effect": "applies", "lock_reason": None,
                                               "pickable": True})

    def test_a_target_is_tried_winner_first_then_the_rest(self):
        # No model: the user file value is unknown and wins, the project "max" is invalid. Only the
        # project target can win after an edit, so it is found after the winner failed.
        world = World(self, user={"effortLevel": "medium"}, project={"effortLevel": "max"})
        body = world.targets()
        self.assertEqual((body["levels_state"], body["runs_as"]), ("model_unknown", None))
        self.assertEqual(target_of(body, "user")["status"], "unknown")
        self.assertEqual(target_of(body, "project")["status"], "invalid")
        project = target_of(body, "project")["target"]
        for name in LEVELS:
            row = level_of(body, name)
            # The absent local file is a create that applies, so it is the preselect.
            self.assertEqual((row["result"], row["certain"], row["preselect"]),
                             ("reachable", False, file_of(row, "local")["target"]))
            self.assertEqual(project_row(row)["target"], project)

    def test_the_order_is_winner_then_local_project_user_and_a_model_path_first(self):
        world = World(self, user={"model": OPUS, "effortLevel": "low",
                                  "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"effortLevel": "low"}, local={"effortLevel": "low"})
        listing = projects.load(world.ctx)
        view = api_edit._view(world.ctx, listing, listing.find(world.key))
        order = api_edit._order(view, api_edit._winner(view.effort))
        self.assertEqual([(t.layer, len(t.key_path)) for t in order],
                         [("local", 1), ("project", 1), ("user", 3), ("user", 1)])
        # A winner that is not on top is moved to the front.
        winner = view.targets[-1]
        moved = api_edit._order(view, winner.entry)
        self.assertEqual(moved[0].ref, winner.ref)

    def test_a_level_that_needs_two_changes_is_stopped_and_points_to_the_cap(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "low"})
        body = world.targets()
        self.assertEqual(level_of(body, "low")["result"], "now")
        for name in ("medium", "high", "xhigh"):
            row = level_of(body, name)
            self.assertEqual((row["result"], row["runs_as"]), ("stopped", "low"))
            self.assertNotIn("target", row)
            self.assertEqual(len(row["limits"]), 1)
            limit = row["limits"][0]
            self.assertEqual((limit["kind"], limit["value"], limit["layer"], limit["file_display"], limit["line"],
                              limit["lock_reason"]), ("cap", "low", "user", "config/settings.json", 3, "cap_later"))
            self.assert_limits(row["limits"])

    def test_a_cap_lists_every_cap_below_the_level_lowest_first(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "high"},
                      project={"effortLevel": "low", "maxEffortLevel": "medium"},
                      local={"maxEffortLevel": "low"})
        row = level_of(world.targets(), "xhigh")
        self.assertEqual(row["result"], "stopped")
        self.assertEqual([(l["layer"], l["value"]) for l in row["limits"]],
                         [("local", "low"), ("project", "medium"), ("user", "high")])
        self.assertEqual([l["lock_reason"] for l in row["limits"]], ["cap_later"] * 3)
        medium = level_of(world.targets(), "medium")
        self.assertEqual([(l["layer"], l["value"]) for l in medium["limits"]], [("local", "low")])

    def test_a_managed_cap_carries_the_layers_own_lock_reason(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"},
                      managed={"maxEffortLevel": "low"})
        limit = level_of(world.targets(), "high")["limits"][0]
        self.assertEqual((limit["kind"], limit["layer"], limit["lock_reason"]), ("cap", "managed", "managed"))

    def test_a_max_cap_is_left_out(self):
        world = World(self, user={"model": OPUS, "maxEffortLevel": "max"}, project={"effortLevel": "low"})
        body = world.targets()
        for name in ("medium", "high", "xhigh"):
            self.assertEqual(level_of(body, name)["result"], "reachable", name)
        self.assertEqual(api_edit._caps_below(
            [{"key": "maxEffortLevel", "scope": "main", "value": "max", "status": "in_effect"}], "xhigh"), [])

    def test_an_invalid_cap_is_left_out(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "turbo"}, project={"effortLevel": "low"})
        body = world.targets()
        self.assertEqual(level_of(body, "xhigh")["result"], "reachable")
        entry = {"key": "maxEffortLevel", "scope": "main", "value": "low", "status": "invalid"}
        self.assertEqual(api_edit._caps_below([entry], "xhigh"), [])

    def test_a_top_level_cap_replaced_by_a_same_file_per_model_cap_is_left_out(self):
        world = World(self, user={"model": OPUS, "maxEffortLevel": "low",
                                  "modelSettings": {OPUS: {"maxEffortLevel": "xhigh"}}},
                      project={"effortLevel": "low"})
        body = world.targets()
        for name in ("medium", "high", "xhigh"):
            row = level_of(body, name)
            self.assertEqual((row["result"], row["limits"]), ("reachable", []), name)

    def test_a_model_without_the_level_gives_a_model_limit_and_stops(self):
        world = World(self, user={"model": "claude-opus-4-6"}, project={"effortLevel": "low"})
        row = level_of(world.targets(), "xhigh")
        self.assertEqual((row["result"], row["runs_as"]), ("stopped", "high"))
        self.assertEqual(kinds(row), ["model"])
        limit = row["limits"][0]
        self.assertEqual((limit["value"], limit["lock_reason"], limit["layer"], limit["file_display"],
                          limit["line"]), ("high", "model", None, None, None))
        self.assert_limits(row["limits"])
        self.assertEqual(level_of(world.targets(), "high")["result"], "reachable")

    def test_a_model_limit_and_a_cap_limit_come_together(self):
        world = World(self, user={"model": "claude-opus-4-6", "maxEffortLevel": "medium"},
                      project={"effortLevel": "low"})
        row = level_of(world.targets(), "xhigh")
        self.assertEqual(kinds(row), ["cap", "model"])

    def test_no_limit_in_any_level_points_at_a_target(self):
        for kwargs in ({"user": {"model": SONNET, "maxEffortLevel": "low"}, "project": {"effortLevel": "low"}},
                       {"user": {"model": "claude-opus-4-6"}, "project": {"effortLevel": "low"}},
                       {"user": {"model": SONNET}, "project": {"effortLevel": "low"},
                        "shell_env": {"CLAUDE_CODE_EFFORT_LEVEL": "high"}}):
            for row in World(self, **kwargs).targets()["levels"]:
                self.assert_limits(row["limits"])


class WinnersThatCannotBeEdited(Base):
    def test_a_shell_variable_gives_a_winner_limit_with_env_shell(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"},
                      shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "high"})
        body = world.targets()
        self.assertEqual(body["runs_as"], "high")
        self.assertEqual(level_of(body, "high")["result"], "now")
        row = level_of(body, "medium")
        self.assertEqual((row["result"], row["runs_as"]), ("stopped", "high"))
        self.assertEqual(len(row["limits"]), 1)
        limit = row["limits"][0]
        self.assertEqual((limit["kind"], limit["value"], limit["layer"], limit["lock_reason"], limit["line"]),
                         ("winner", "high", "env", "env_shell", None))
        self.assert_limits(row["limits"])

    def test_an_env_block_gives_a_winner_limit_with_env_file_and_a_line(self):
        world = World(self, user={"model": SONNET, "env": {"CLAUDE_CODE_EFFORT_LEVEL": "high"}},
                      project={"effortLevel": "low"})
        limit = level_of(world.targets(), "medium")["limits"][0]
        self.assertEqual((limit["kind"], limit["layer"], limit["lock_reason"], limit["file_display"], limit["line"]),
                         ("winner", "env", "env_file", "config/settings.json", 4))

    def test_a_default_winner_gives_no_key_in_file(self):
        world = World(self, user={"model": OPUS})
        lock_repo(self, world)  # without the lock the user file could take a new line
        body = world.targets()
        self.assertEqual(body["targets"], [])
        self.assertEqual(body["levels_state"], "ok")
        stopped = [row for row in body["levels"] if row["result"] == "stopped"]
        self.assertEqual(len(stopped), 3)
        for row in stopped:
            self.assertEqual(kinds(row), ["winner"])
            limit = row["limits"][0]
            self.assertEqual((limit["layer"], limit["lock_reason"], limit["file_display"]), ("default", "no_key_in_file", None))
        self.assertEqual([row["result"] for row in body["levels"]].count("now"), 1)

    def test_a_blocked_symlink_file_gives_blocked_symlink_and_a_winner_limit(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}})
        real = os.path.join(world.root, "elsewhere.json")
        world.put(real, {"effortLevel": "high"})
        os.symlink(real, world.path("local"))
        body = world.targets()
        self.assertEqual([b["reason"] for b in body["blocked"] if b["layer"] == "local"], ["symlink"])
        self.assertEqual(body["runs_as"], "high")
        row = level_of(body, "medium")
        self.assertEqual(row["result"], "stopped")
        limit = row["limits"][0]
        self.assertEqual((limit["kind"], limit["layer"], limit["lock_reason"]), ("winner", "local", "symlink"))
        self.assert_limits(row["limits"])

    def test_a_file_value_that_came_back_unknown_has_the_lock_reason_unknown(self):
        view = mock.Mock(blocked_refs={}, levels_state="ok")
        entry = {"key": "effortLevel", "layer": "user", "file": "config/settings.json", "value": "high",
                 "status": "unknown"}
        self.assertEqual(api_edit._lock_reason(view, entry), "unknown")
        self.assertEqual(api_edit._lock_reason(view, dict(entry, layer="default", value=None)), "unknown")


class NoModelTable(Base):
    """One test per row of the table in the ticket's Notes."""

    def test_project_high_under_a_user_cap_of_low_with_no_model(self):
        world = World(self, user={"maxEffortLevel": "low"}, project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual((body["levels_state"], body["model"], body["runs_as"]), ("model_unknown", None, "low"))
        low = level_of(body, "low")
        self.assertEqual((low["result"], low["certain"]), ("now", False))
        for name in ("medium", "high", "xhigh"):
            row = level_of(body, name)
            self.assertEqual((row["result"], row["runs_as"], row["certain"]), ("stopped", "low", False), name)
            self.assertEqual(kinds(row), ["cap"], name)
            limit = row["limits"][0]
            self.assertEqual((limit["value"], limit["layer"], limit["lock_reason"]), ("low", "user", "cap_later"))
        # The resolver alone says in_effect here. The helper is what finds the cap.
        project = target_of(body, "project")
        self.assertEqual(project["status"], "in_effect")

    def test_a_project_target_is_reachable_with_certain_false_when_no_cap_is_below(self):
        world = World(self, project={"effortLevel": "high"}, user={"maxEffortLevel": "xhigh"})
        body = world.targets()
        project = target_of(body, "project")["target"]
        for name, result in (("low", "reachable"), ("medium", "reachable"), ("high", "now"),
                             ("xhigh", "reachable")):
            row = level_of(body, name)
            self.assertEqual((row["result"], row["certain"]), (result, False), name)
        low = level_of(body, "low")
        self.assertEqual(project_row(low)["target"], project)
        self.assertEqual(low["preselect"], file_of(low, "local")["target"])  # the absent local create, never the project

    def test_a_per_model_cap_with_no_model_is_not_a_limit(self):
        world = World(self, user={"modelSettings": {OPUS: {"maxEffortLevel": "low"}}},
                      project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual(body["levels_state"], "model_unknown")
        for name in ("low", "medium", "xhigh"):
            row = level_of(body, name)
            self.assertEqual((row["result"], row["limits"]), ("reachable", []), name)
        self.assertEqual(level_of(body, "high")["result"], "now")

    def test_the_user_file_effort_level_as_the_only_target_gives_model_unknown(self):
        world = World(self, user={"effortLevel": "high"}, project="{ not json",
                      local="{ not json")  # both locked, so only the user file offers a line
        body = world.targets()
        self.assertEqual((body["levels_state"], body["runs_as"]), ("model_unknown", None))
        self.assertEqual(target_of(body, "user")["status"], "unknown")
        for row in body["levels"]:
            self.assertEqual((row["result"], row["runs_as"], row["certain"]), ("stopped", None, False))
            self.assertEqual(len(row["limits"]), 1)
            self.assertEqual(row["limits"][0], {"kind": "model_unknown", "value": None, "layer": None,
                                                "file_display": None, "line": None, "editable": False,
                                                "target": None, "lock_reason": "model_unknown"})

    def test_haiku_4_5_has_no_effort_support(self):
        world = World(self, user={"model": "claude-haiku-4-5"}, project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual((body["levels_state"], body["levels"]), ("no_effort_support", []))
        self.assertTrue(target_of(body, "project")["ref"])
        status, pv = world.preview(target_of(body, "project")["target"], "low")
        self.assertEqual((status, pv), (400, {"error": "not_editable"}))

    def test_a_default_with_no_effort_support_says_so(self):
        world = World(self, user={"model": "claude-haiku-4-5"})
        view_listing = projects.load(world.ctx)
        view = api_edit._view(world.ctx, view_listing, view_listing.find(world.key))
        winner = api_edit._winner(view.effort)
        self.assertEqual(api_edit._lock_reason(view, winner), "no_effort_support")

    def test_a_no_model_default_winner_is_not_a_no_key_in_file(self):
        world = World(self, user={"maxEffortLevel": "high"}, project="{ not json",
                      local="{ not json")  # both locked, so they offer nothing
        body = world.targets()
        self.assertEqual(body["levels_state"], "model_unknown")
        for name in ("low", "medium", "high"):
            self.assertEqual(kinds(level_of(body, name)), ["model_unknown"], name)
        # The cap is below xhigh, so the cap is what stops that one.
        self.assertEqual(kinds(level_of(body, "xhigh")), ["cap"])


# --------------------------------------------------------------------------
# File rows and what each level does to each file (T19a)

def view_of(world):
    listing = projects.load(world.ctx)
    return api_edit._view(world.ctx, listing, listing.find(world.key))

def inner_preview(world, target, value):
    """Return the payload _preview builds for a target, skipping the route's pickable check.

    The preview and save routes refuse a row the file list marks not pickable. A few tests read a
    payload that only such a row gives (a change that leaves the level where it is, a winner that
    overrides it), so they build it here.
    """
    listing = projects.load(world.ctx)
    view = api_edit._view(world.ctx, listing, listing.find(world.key))
    return api_edit._preview(world.ctx, view, view.find(target), value).payload


class FileStates(Base):
    ROW_KEYS = {"layer", "file_display", "state", "line", "value", "status", "target", "shared", "lock_reason"}

    def files(self, world):
        return world.targets()["files"]

    def test_files_come_in_the_order_local_project_user_with_every_field(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        files = self.files(world)
        self.assertEqual([f["layer"] for f in files], ["local", "project", "user"])
        for row in files:
            self.assertEqual(set(row), self.ROW_KEYS)
        self.assertEqual([f["shared"] for f in files], [False, True, False])

    def test_has_line_takes_line_value_status_and_target_from_the_trail(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        body = world.targets()
        row = file_of(body["files"], "project")
        self.assertEqual(row, {"layer": "project", "file_display": "project/.claude/settings.json",
                               "state": "has_line", "line": 2, "value": "high", "status": "in_effect",
                               "target": target_of(body, "project")["target"], "shared": True,
                               "lock_reason": None})

    def test_no_line_when_the_file_holds_no_effort_line(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        row = file_of(self.files(world), "user")
        self.assertEqual((row["state"], row["lock_reason"], row["line"], row["value"], row["status"],
                          row["target"], row["file_display"]),
                         ("no_line", None, None, None, None, None, "config/settings.json"))

    def test_absent_when_the_leaf_is_gone(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        row = file_of(self.files(world), "local")
        self.assertEqual((row["state"], row["lock_reason"], row["target"], row["file_display"]),
                         ("absent", None, None, "project/.claude/settings.local.json"))

    def test_absent_when_the_claude_folder_is_gone(self):
        world = World(self, user={"model": SONNET})
        shutil.rmtree(os.path.join(world.proj, ".claude"))
        files = self.files(world)
        self.assertEqual([(f["layer"], f["state"], f["lock_reason"]) for f in files],
                         [("local", "absent", None), ("project", "absent", None),
                          ("user", "no_line", None)])

    def test_locked_by_a_symlink_at_the_leaf(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        real = os.path.join(world.root, "elsewhere.json")
        world.put(real, {"model": OPUS})
        os.symlink(real, world.path("local"))
        row = file_of(self.files(world), "local")
        self.assertEqual((row["state"], row["lock_reason"], row["target"], row["line"]),
                         ("locked", "symlink", None, None))

    def test_locked_by_a_hard_link(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"}, local={"model": OPUS})
        os.link(world.path("local"), os.path.join(world.root, "second.json"))
        row = file_of(self.files(world), "local")
        self.assertEqual((row["state"], row["lock_reason"]), ("locked", "hard_link"))

    def test_locked_by_a_file_that_does_not_parse(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"}, local="{ not json")
        row = file_of(self.files(world), "local")
        self.assertEqual((row["state"], row["lock_reason"], row["target"]), ("locked", "unparsed", None))

    def test_a_line_in_a_symlinked_file_is_locked_with_its_line_and_value(self):
        world = World(self, user={"model": SONNET})
        real = os.path.join(world.root, "elsewhere.json")
        world.put(real, {"effortLevel": "high"})
        os.symlink(real, world.path("local"))
        row = file_of(self.files(world), "local")
        self.assertEqual((row["state"], row["lock_reason"], row["line"], row["value"], row["status"],
                          row["target"]), ("locked", "symlink", 2, "high", "in_effect", None))

    def test_file_missing_when_the_project_folder_is_gone(self):
        world = World(self, user={"model": SONNET})
        view = view_of(world)
        shutil.rmtree(world.proj)
        rows = api_edit._file_states(view)
        self.assertEqual([(f["layer"], f["state"], f["lock_reason"]) for f in rows],
                         [("local", "locked", "file_missing"), ("project", "locked", "file_missing"),
                          ("user", "no_line", None)])

    def test_file_missing_when_the_config_folder_is_gone(self):
        world = World(self, project={"effortLevel": "high"})
        view = view_of(world)
        shutil.rmtree(world.cfg)
        self.assertEqual(file_of(api_edit._file_states(view), "user")["lock_reason"], "file_missing")

    def test_a_missing_project_gives_no_files_no_levels_and_not_saveable(self):
        world = World(self, user={"model": SONNET}, listed=[{"name": "gone", "path": "{root}/not-there"}])
        status, body = api_edit.targets(world.ctx, {"project": ["gone"]})
        self.assertEqual(status, 200)
        self.assertEqual((body["files"], body["levels"], body["saveable"]), ([], [], False))

    def test_no_effort_support_keeps_the_files_and_is_not_saveable(self):
        world = World(self, user={"model": "claude-haiku-4-5"}, project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual((body["levels"], body["saveable"]), ([], False))
        self.assertEqual(file_of(body["files"], "project")["state"], "has_line")

    def test_parent_not_object_for_a_model_settings_that_is_not_an_object(self):
        world = World(self, user={"model": OPUS}, project={"effortLevel": "high"},
                      local={"modelSettings": [1, 2]})
        row = file_of(self.files(world), "local")
        self.assertEqual((row["state"], row["lock_reason"]), ("locked", "parent_not_object"))

    def test_parent_not_object_for_a_model_entry_that_is_not_an_object(self):
        world = World(self, user={"model": OPUS}, project={"effortLevel": "high"},
                      local={"modelSettings": {OPUS: 5}})
        row = file_of(self.files(world), "local")
        self.assertEqual((row["state"], row["lock_reason"]), ("locked", "parent_not_object"))

    def test_an_entry_of_another_model_that_is_not_an_object_does_not_lock(self):
        world = World(self, user={"model": OPUS}, project={"effortLevel": "high"},
                      local={"modelSettings": {SONNET: 5}})
        self.assertEqual(file_of(self.files(world), "local")["state"], "no_line")

    def test_a_planted_secret_never_reaches_the_answer(self):
        world = World(self, user={"model": SONNET, "env": {"ANTHROPIC_API_KEY": SECRET}},
                      project={"effortLevel": SECRET},
                      local={"apiKeyHelper": SECRET, "modelSettings": {"x": {"token": SECRET}}})
        body = world.targets()
        self.assertNotIn(SECRET, json.dumps(body))
        self.assertEqual(file_of(body["files"], "project")["value"], "hidden")
        for level in body["levels"]:
            for row in level["files"]:
                self.assertNotIn(SECRET, json.dumps(row))

    def test_a_planted_secret_in_a_locked_file_with_a_line_is_masked(self):
        world = World(self, user={"model": SONNET})
        real = os.path.join(world.root, "elsewhere.json")
        world.put(real, {"effortLevel": SECRET})
        os.symlink(real, world.path("local"))
        body = world.targets()
        self.assertNotIn(SECRET, json.dumps(body))
        row = file_of(body["files"], "local")
        self.assertEqual((row["state"], row["value"]), ("locked", "hidden"))

    def test_the_row_locks_table_is_gone(self):
        self.assertFalse(hasattr(api_edit, "ROW_LOCKS"))

    def test_a_preview_and_a_save_do_not_build_the_level_answers(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        target = target_of(world.targets(), "project")["target"]
        with mock.patch.object(api_edit, "_levels", side_effect=AssertionError("called")):
            world.edit(target, "high")


class LevelFiles(Base):
    ROW_KEYS = {"layer", "target", "op", "line", "runs_as", "effect", "lock_reason", "pickable"}

    def test_every_non_running_level_has_one_row_per_file_in_file_order(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        body = world.targets()
        for level in body["levels"]:
            if level["result"] == "now":
                self.assertEqual((level["files"], level["preselect"], level["saveable"]), ([], None, False))
                continue
            self.assertEqual([f["layer"] for f in level["files"]], [f["layer"] for f in body["files"]])
            for row in level["files"]:
                self.assertEqual(set(row), self.ROW_KEYS)

    def test_an_absent_file_is_a_create_row_with_no_lock(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"})
        body = world.targets()
        row = level_of(body, "low")
        self.assertEqual(file_of(row, "local"), {"layer": "local", "target": add_of(body, "local", TOP)["target"],
                                                 "op": "create", "line": 2, "runs_as": "low",
                                                 "effect": "applies", "lock_reason": None, "pickable": True})
        user = file_of(row, "user")
        self.assertEqual((user["op"], user["lock_reason"], user["effect"], user["pickable"]),
                         ("insert", None, "wont_apply", False))  # the project line outranks the user file

    def test_applies_in_local_is_preselected(self):
        world = World(self, user={"model": SONNET}, local={"effortLevel": "high"})
        body = world.targets()
        local = target_of(body, "local")["target"]
        row = level_of(body, "low")
        self.assertEqual(file_of(row, "local"), {"layer": "local", "target": local, "op": "replace", "line": 2,
                                                 "runs_as": "low", "effect": "applies", "lock_reason": None,
                                                 "pickable": True})
        self.assertEqual((row["preselect"], row["saveable"]), (local, True))
        self.assertIs(body["saveable"], True)

    def test_lowered_by_a_cap_is_pickable_and_never_preselected(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "medium"}, local={"effortLevel": "low"})
        row = level_of(world.targets(), "xhigh")
        local = file_of(row, "local")
        self.assertEqual((local["effect"], local["runs_as"], local["pickable"]), ("lowered", "medium", True))
        self.assertEqual((row["preselect"], row["saveable"]), (None, True))

    def test_lowered_onto_todays_level_reads_wont_apply_and_is_not_pickable(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, local={"effortLevel": "low"})
        body = world.targets()
        row = level_of(body, "high")
        local = file_of(row, "local")
        self.assertEqual((local["effect"], local["runs_as"], local["lock_reason"], local["pickable"]),
                         ("wont_apply", "low", None, False))
        self.assertEqual((row["preselect"], row["saveable"]), (None, False))
        self.assertIs(body["saveable"], False)

    def test_an_overridden_line_reads_wont_apply(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"}, local={"effortLevel": "high"})
        row = level_of(world.targets(), "medium")
        project = file_of(row, "project")
        self.assertEqual((project["effect"], project["pickable"]), ("wont_apply", False))
        local = file_of(row, "local")
        self.assertEqual((local["effect"], local["pickable"]), ("applies", True))

    def test_unknown_with_no_model_is_pickable_and_not_preselected(self):
        # Local is locked, so the user file is the only row (a local create would apply with no model).
        world = World(self, user={"effortLevel": "high"}, local="{ not json")
        body = world.targets()
        for level in body["levels"]:
            user = file_of(level, "user")
            self.assertEqual((user["effect"], user["runs_as"], user["pickable"]), ("unknown", None, True))
            self.assertIsNone(level["preselect"])
            self.assertIs(level["saveable"], True)

    def test_a_file_with_a_top_level_and_a_model_line_takes_the_better_one(self):
        world = World(self, user={"model": OPUS, "effortLevel": "high",
                                  "modelSettings": {OPUS: {"effortLevel": "low"}}})
        body = world.targets()
        model_path = target_of(body, "user", "modelSettings.claude-opus-5-5.effortLevel")["target"]
        top = target_of(body, "user", '"effortLevel"]')["target"]
        self.assertNotEqual(model_path, top)
        view = view_of(world)
        by_id = {t.id: t for t in view.targets}
        self.assertEqual(api_edit._effect(view, by_id[top], "medium")[0], "wont_apply")
        for name in ("medium", "high", "xhigh"):
            user = file_of(level_of(body, name), "user")
            self.assertEqual((user["target"], user["effect"]), (model_path, "applies"), name)

    def test_a_target_the_json_editor_refuses_is_not_editable(self):
        world = World(self, user={"model": SONNET}, local={"effortLevel": "high"})
        view = view_of(world)
        with mock.patch.object(api_edit, "_simulate", return_value=None):
            row = api_edit._level_file(view, api_edit._file_states(view)[0], "low", view.targets)
        self.assertEqual((row["op"], row["effect"], row["runs_as"], row["lock_reason"], row["pickable"]),
                         ("replace", None, None, "not_editable", False))

    def test_a_level_where_every_row_is_grey_is_not_saveable(self):
        world = World(self, user={"model": OPUS})  # a default wins and no file holds a line
        lock_repo(self, world)  # the repo lock greys every row
        body = world.targets()
        self.assertIs(body["saveable"], False)
        for level in body["levels"]:
            self.assertEqual((level["preselect"], level["saveable"]), (None, False))
            for row in level["files"]:
                self.assertEqual((row["lock_reason"], row["pickable"], row["target"], row["effect"]),
                                 ("not_repo_root", False, None, None))

    def test_a_project_where_only_local_has_a_line_and_it_is_locked(self):
        world = World(self, user={"model": SONNET})
        real = os.path.join(world.root, "elsewhere.json")
        world.put(real, {"effortLevel": "high"})
        os.symlink(real, world.path("local"))
        body = world.targets()
        self.assertIs(body["saveable"], False)
        for level in body["levels"]:
            self.assertIsNone(level["preselect"])
            if level["result"] == "now":
                continue
            local = file_of(level, "local")
            self.assertEqual((local["lock_reason"], local["line"], local["pickable"]), ("symlink", 2, False))

    def test_a_line_only_in_the_project_file_is_pickable_and_never_preselected(self):
        # Local is locked, so the shared file is the only row (an absent local would be a create).
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"}, local="{ not json")
        body = world.targets()
        for name in ("low", "medium", "xhigh"):
            row = level_of(body, name)
            self.assertEqual(row["result"], "reachable")
            self.assertIsNone(row["preselect"], name)
            self.assertEqual((project_row(row)["pickable"], row["saveable"]), (True, True))

    def test_a_winner_in_the_project_file_does_not_make_it_the_preselect_when_local_could_reach(self):
        # Local holds an invalid "max", so the project value wins. The old answer pointed every
        # reachable level at the project file. Now local is the preselect and project is a choice.
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"}, local={"effortLevel": "max"})
        body = world.targets()
        self.assertEqual(target_of(body, "local")["status"], "invalid")
        local = target_of(body, "local")["target"]
        project = target_of(body, "project")["target"]
        view = view_of(world)
        self.assertEqual(api_edit._order(view, api_edit._winner(view.effort))[0].id, project)
        for name in ("low", "medium", "xhigh"):
            row = level_of(body, name)
            self.assertEqual(row["preselect"], local, name)
            self.assertTrue(project_row(row)["pickable"], name)
            self.assertNotEqual(row["preselect"], project)


# --------------------------------------------------------------------------
# Preview

class Preview(Base):
    def world(self, **kwargs):
        defaults = {"user": {"model": SONNET}, "project": {"effortLevel": "low"}}
        defaults.update(kwargs)
        return World(self, **defaults)

    def test_the_payload_has_every_field(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        status, pv = world.preview(target, "high")
        self.assertEqual(status, 200)
        self.assertEqual(set(pv), {"git_ignore", "target", "old_value", "new_value", "no_change", "before", "after",
                                   "changes", "warning", "diff", "base_file", "base_trail", "base_others",
                                   "op", "layer", "shared", "line", "ref", "new_file", "creates_dir",
                                   "ledger_damaged", "runs_before", "runs_after", "no_effect", "last_line"})
        self.assertEqual((pv["target"], pv["old_value"], pv["new_value"], pv["no_change"]),
                         (target, "low", "high", False))
        self.assertNotIn("new_raw", pv)
        for name in ("base_file", "base_trail"):
            self.assertRegex(pv[name], r"^[0-9a-f]{64}$")
        self.assertEqual(pv["base_others"], {"config/settings.json": api_edit._hmac(world.ctx, world.read("user")),
                                             "project/.claude/settings.local.json": "missing",
                                             "managed/managed-settings.json": "missing"})
        self.assertEqual(pv["base_file"], api_edit._hmac(world.ctx, world.read("project")))

    def test_the_new_fields_describe_the_edit(self):
        world = self.world(user={"model": SONNET, "maxEffortLevel": "medium"})
        body = world.targets()
        target = target_of(body, "project")
        status, pv = world.preview(target["target"], "xhigh")
        self.assertEqual(status, 200)
        self.assertEqual((pv["op"], pv["layer"], pv["shared"], pv["line"], pv["ref"]),
                         ("replace", "project", True, 2, target["ref"]))
        self.assertEqual((pv["new_file"], pv["creates_dir"], pv["ledger_damaged"]), (False, False, False))
        self.assertEqual((pv["runs_before"], pv["runs_after"]), ("low", "medium"))

    def test_a_user_edit_is_not_shared(self):
        world = self.world(user={"effortLevel": "low"}, project={})
        status, pv = world.preview(target_of(world.targets(), "user")["target"], "high")
        self.assertEqual((status, pv["layer"], pv["shared"]), (200, "user", False))

    def test_a_damaged_ledger_shows_in_the_preview(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        with mock.patch.object(world.store, "ledger_damaged", return_value=True):
            status, pv = world.preview(target, "high")
        self.assertEqual((status, pv["ledger_damaged"]), (200, True))

    def test_the_new_fields_stay_out_of_every_hashed_base(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        status, pv = world.preview(target, "high")
        self.assertEqual(status, 200)
        trail = json.dumps({"before": pv["before"]["entries"], "after": pv["after"]["entries"]}, sort_keys=True)
        self.assertEqual(pv["base_file"], api_edit._hmac(world.ctx, world.read("project")))
        self.assertEqual(pv["base_trail"], api_edit._hmac(world.ctx, trail.encode("utf-8")))
        self.assertEqual(set(pv["base_others"]), {"config/settings.json", "project/.claude/settings.local.json",
                                                  "managed/managed-settings.json"})
        # A save built from this preview is not stale, so nothing new fed a hash.
        status, body = world.save(pv, target, "high")
        self.assertEqual(status, 200, body)

    def test_before_and_after_are_settings_payloads(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        _status, pv = world.preview(target, "high")
        listing = projects.load(world.ctx)
        plain = api_settings.answer(world.ctx, listing, listing.find(world.key))
        self.assertEqual(pv["before"], plain)
        self.assertEqual(set(pv["after"]), set(plain))
        self.assertEqual(main_effort(pv["after"])["value"], "high")
        # The other layers did not move: the after answer is the plain answer with one value changed.
        world.write("project", world.read("project").replace(b'"low"', b'"high"'))
        listing = projects.load(world.ctx)
        self.assertEqual(pv["after"], api_settings.answer(world.ctx, listing, listing.find(world.key)))

    def test_the_preview_touches_no_file(self):
        world = self.world(managed={"maxEffortLevel": "high"}, local={"effortLevel": "medium"})
        body = world.targets()
        before = world.snapshot()
        answers = []
        for row in body["targets"]:
            for value in LEVELS:
                status, _pv = world.preview(row["target"], value)
                self.assertIn(status, (200, 400), (row["target"], value))  # 400: a row the list marks not pickable
                answers.append(status)
        self.assertIn(200, answers)
        self.assertEqual(world.snapshot(), before)
        self.assertFalse(os.path.exists(os.path.join(world.cfg, edit_store.STORE_DIR)))

    def test_the_same_inputs_give_the_same_bytes(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        first = json.dumps(world.preview(target, "high")[1])
        self.assertEqual(first, json.dumps(world.preview(target, "high")[1]))

    def test_a_value_the_file_already_holds_is_no_change(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        status, pv = world.preview(target, "low")
        self.assertEqual(status, 200)
        self.assertIs(pv["no_change"], True)
        self.assertEqual(pv["before"], pv["after"])
        self.assertEqual(pv["changes"], [])
        self.assertEqual(pv["diff"]["hunks"], [])

    def test_bad_values_answer_bad_value(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        for value in ("max", "", "HIGH", "turbo", None, 5, ["high"], {"a": 1}, True):
            self.assertEqual(world.preview(target, value), (400, {"error": "bad_value"}), repr(value))
        status, body = api_edit.preview(world.ctx, {"project": world.key, "target": target})
        self.assertEqual((status, body), (400, {"error": "bad_value"}))

    def test_a_target_that_is_not_a_string_answers_bad_request(self):
        world = self.world()
        for target in (None, 5, ["t-1"], {"a": 1}):
            self.assertEqual(world.preview(target, "high"), (400, {"error": "bad_request"}), repr(target))
        self.assertEqual(api_edit.preview(world.ctx, {"project": world.key, "value": "high"}),
                         (400, {"error": "bad_request"}))

    def test_an_unknown_target_is_not_editable(self):
        world = self.world()
        for target in ("", "t-0", "../../etc/passwd", "t-" + "0" * 16):
            self.assertEqual(world.preview(target, "high"), (400, {"error": "not_editable"}), target)

    def test_the_project_value_rules_apply_to_the_body(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        for project, status, error in ((["a"], 400, "bad_request"), (5, 400, "bad_request"), (None, 400, "bad_request"),
                                       ("all", 400, "bad_request"), ("nope", 404, "unknown_project")):
            got = api_edit.preview(world.ctx, {"project": project, "target": target, "value": "high"})
            self.assertEqual(got, (status, {"error": error}), repr(project))
        status, _pv = api_edit.preview(world.ctx, {"target": target, "value": "high"})
        self.assertEqual(status, 200)

    def test_path_file_and_dot_dot_fields_change_nothing(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        plain = world.preview(target, "high")
        evil = {"path": "/etc/passwd", "file": os.path.join(world.root, "elsewhere.json"),
                "../x": "..", "key_path": ["model"], "layer": "user", "target_path": "../config/settings.json",
                "key": "model", "store": "x"}
        self.assertEqual(world.preview(target, "high", **evil), plain)
        pv = plain[1]
        before = world.snapshot()
        status, body = world.save(pv, target, "high", **evil)
        self.assertEqual(status, 200)
        after = world.snapshot()
        changed = sorted(k for k in after if before.get(k) != after[k] and not k.startswith("config/routing-dashboard"))
        self.assertEqual(changed, ["project/.claude/settings.json"])
        self.assertEqual(world.read("project"), dumps({"effortLevel": "high"}).encode())
        self.assertEqual(world.read("user"), dumps({"model": SONNET}).encode())

    def test_a_target_naming_a_path_is_not_editable(self):
        world = self.world()
        for target in (world.path("project"), "../project/.claude/settings.json", "modelSettings.x.effortLevel"):
            self.assertEqual(world.preview(target, "high"), (400, {"error": "not_editable"}), target)

    def test_the_diff_changes_one_line_and_is_plain_text(self):
        world = self.world(project={"effortLevel": "low", "note": "<b>hi</b>"})
        target = target_of(world.targets(), "project")["target"]
        _status, pv = world.preview(target, "xhigh")
        self.assertEqual(pv["diff"]["file_display"], "project/.claude/settings.json")
        lines = [line for hunk in pv["diff"]["hunks"] for line in hunk["lines"]]
        self.assertEqual([(l["kind"], l["text"]) for l in lines if l["kind"] != "context"],
                         [("del", '  "effortLevel": "low",'), ("add", '  "effortLevel": "xhigh",')])
        self.assertTrue(any("<b>hi</b>" in l["text"] for l in lines))

    def test_a_secret_shaped_value_shows_hidden_everywhere(self):
        world = self.world(project={"effortLevel": SECRET, "other": {"apiToken": SECRET}})
        body = world.targets()
        self.assertEqual(target_of(body, "project")["current_value"], "hidden")
        self.assertNotIn("sk-planted", json.dumps(body))
        target = target_of(body, "project")["target"]
        status, pv = world.preview(target, "high")
        self.assertEqual(status, 200)
        self.assertEqual(pv["old_value"], "hidden")
        self.assertNotIn("sk-planted", json.dumps(pv))
        status, saved = world.save(pv, target, "high")
        self.assertEqual(status, 200)
        self.assertEqual((saved["edit"]["old_value"], saved["edit"]["new_value"]), ("hidden", "high"))
        self.assertNotIn("sk-planted", json.dumps(saved))
        self.assertNotIn("sk-planted", json.dumps(world.history()))

    def test_changes_list_the_main_row_with_both_sides(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        _status, pv = world.preview(target, "high")
        self.assertEqual(len(pv["changes"]), 1)
        change = pv["changes"][0]
        self.assertEqual((change["agent"], change["setting"]), ("@main", "effortLevel"))
        self.assertEqual(change["before"], {"value": "low", "status": "in_effect", "layer": "project",
                                            "file": "project/.claude/settings.json", "line": 2, "runs_as": "low"})
        self.assertEqual(change["after"], dict(change["before"], value="high", runs_as="high"))

    def test_changes_reach_agent_rows(self):
        agent = "---\nname: probe\ndescription: Made-up agent for a test.\nmodel: claude-haiku-5-5\n---\nYou are a probe.\n"
        world = self.world(agents={"probe": agent})
        target = target_of(world.targets(), "project")["target"]
        _status, pv = world.preview(target, "high")
        agents = [c for c in pv["changes"] if c["agent"] == "probe"]
        self.assertEqual(len(agents), 1)
        self.assertEqual((agents[0]["setting"], agents[0]["before"]["runs_as"], agents[0]["after"]["runs_as"]),
                         ("effort", "low", "high"))
        self.assertEqual(pv["changes"][0]["agent"], "@main")

    def test_a_row_that_only_moves_run_as_is_listed(self):
        # No model, project high under a user cap of low: the resolver says in_effect before and after,
        # the file value moves, and the run-as value stays at the cap.
        world = World(self, user={"maxEffortLevel": "low"}, project={"effortLevel": "medium"})
        target = target_of(world.targets(), "project")["target"]
        pv = inner_preview(world, target, "high")  # the row leaves what runs alone, so the route refuses it
        change = pv["changes"][0]
        self.assertEqual((change["before"]["value"], change["after"]["value"]), ("medium", "high"))
        self.assertEqual((change["before"]["runs_as"], change["after"]["runs_as"]), ("low", "low"))

    def test_hash_bases_name_every_other_file_including_managed_ones(self):
        world = self.world(managed={"maxEffortLevel": "high"}, local={"effortLevel": "medium"})
        os.makedirs(os.path.join(world.managed, "managed-settings.d"))
        world.put(os.path.join(world.managed, "managed-settings.d", "10-extra.json"), {"a": 1})
        target = target_of(world.targets(), "project")["target"]
        pv = inner_preview(world, target, "high")  # the local line wins, so the route refuses this row
        self.assertEqual(sorted(pv["base_others"]), [
            "config/settings.json", "managed/managed-settings.d/10-extra.json", "managed/managed-settings.json",
            "project/.claude/settings.local.json"])
        self.assertNotIn("project/.claude/settings.json", pv["base_others"])
        for value in pv["base_others"].values():
            self.assertRegex(value, r"^[0-9a-f]{64}$")
        os.chmod(world.path("local"), 0)
        try:
            again = inner_preview(world, target, "high")
            if os.access(world.path("local"), os.R_OK):  # running as root reads it anyway
                self.skipTest("the file stays readable")
            self.assertEqual(again["base_others"]["project/.claude/settings.local.json"], "unreadable")
        finally:
            os.chmod(world.path("local"), 0o600)


class Warnings(Base):
    def preview(self, world, layer, value, ends=None):
        """Return the preview payload of a target's edit, built by _preview.

        The route refuses a row the file list marks not pickable, and several warnings (overridden,
        ignored, a level the winner already holds) only appear on such a row. So this helper skips the route.
        """
        target = target_of(world.targets(), layer, ends)["target"]
        listing = projects.load(world.ctx)
        view = api_edit._view(world.ctx, listing, listing.find(world.key))
        return api_edit._preview(world.ctx, view, view.find(target), value).payload

    def test_in_effect_with_no_limit_is_null(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        self.assertIsNone(self.preview(world, "project", "high")["warning"])

    def test_in_effect_with_a_limit_carries_the_limits_in_the_no_model_case(self):
        world = World(self, user={"maxEffortLevel": "low"}, project={"effortLevel": "low"})
        warning = self.preview(world, "project", "high")["warning"]
        self.assertEqual(set(warning), {"status", "reason", "rule_ids", "in_effect_changes", "model_known", "limits"})
        self.assertEqual(warning["status"], "in_effect")
        self.assertEqual(kinds(warning), ["cap"])
        self.assertEqual(warning["limits"][0]["value"], "low")
        self.assertIs(warning["in_effect_changes"], False)
        self.assertIsInstance(warning["reason"], str)
        self.assertIsInstance(warning["rule_ids"], list)

    def test_lowered_by_a_cap_lists_the_blocking_caps(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "medium"},
                      project={"effortLevel": "low", "maxEffortLevel": "high"})
        warning = self.preview(world, "project", "xhigh")["warning"]
        self.assertEqual(warning["status"], "lowered")
        self.assertEqual([(l["kind"], l["layer"], l["value"]) for l in warning["limits"]],
                         [("cap", "user", "medium"), ("cap", "project", "high")])
        self.assertIs(warning["in_effect_changes"], True)  # low before, medium after
        self.assert_limits(warning["limits"])

    def test_a_per_model_line_under_a_cap_is_lowered_and_the_model_is_known(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"maxEffortLevel": "high"})
        body = world.targets()
        self.assertEqual(body["runs_as"], "low")
        row = level_of(body, "xhigh")
        user = file_of(row, "user")
        self.assertEqual((user["effect"], user["runs_as"], user["pickable"]), ("lowered", "high", True))
        pv = self.preview(world, "user", "xhigh")
        self.assertEqual((pv["runs_before"], pv["runs_after"]), ("low", "high"))
        warning = pv["warning"]
        self.assertIs(warning["model_known"], True)
        self.assertEqual([(l["kind"], l["value"]) for l in warning["limits"]], [("cap", "high")])
        self.assertIs(warning["in_effect_changes"], True)  # low before, high after

    def test_a_per_model_line_at_the_cap_today_reads_wont_apply(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "high"}}},
                      project={"maxEffortLevel": "high"})
        body = world.targets()
        self.assertEqual(body["runs_as"], "high")
        user = file_of(level_of(body, "xhigh"), "user")
        self.assertEqual((user["effect"], user["runs_as"], user["pickable"]), ("wont_apply", "high", False))

    def test_the_warning_says_the_model_is_unknown_when_there_is_none(self):
        world = World(self, user={"maxEffortLevel": "low"}, project={"effortLevel": "low"})
        self.assertIs(self.preview(world, "project", "high")["warning"]["model_known"], False)

    def test_lowered_by_the_model_gives_the_model_limit(self):
        world = World(self, user={"model": "claude-opus-4-6"}, project={"effortLevel": "low"})
        warning = self.preview(world, "project", "xhigh")["warning"]
        self.assertEqual(warning["status"], "lowered")
        self.assertEqual(kinds(warning), ["model"])
        self.assertEqual(warning["limits"][0]["value"], "high")
        self.assertIs(warning["in_effect_changes"], True)

    def test_overridden_names_the_winner_and_a_winner_on_the_table_is_editable(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"effortLevel": "high"})
        body = world.targets()
        project = target_of(body, "project")["target"]
        warning = self.preview(world, "user", "medium")["warning"]
        self.assertEqual(warning["status"], "overridden")
        self.assertEqual(len(warning["limits"]), 1)
        limit = warning["limits"][0]
        self.assertEqual((limit["kind"], limit["layer"], limit["value"], limit["target"], limit["editable"]),
                         ("winner", "project", "high", project, True))
        self.assertIsNone(limit["lock_reason"])
        self.assertIs(warning["in_effect_changes"], False)

    def test_overridden_by_a_winner_that_cannot_be_edited_stays_locked(self):
        world = World(self, user={"model": SONNET, "effortLevel": "low"}, project={"effortLevel": "low"},
                      shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "high"})
        warning = self.preview(world, "project", "medium")["warning"]
        self.assertEqual(warning["status"], "overridden")
        limit = warning["limits"][0]
        self.assertEqual((limit["kind"], limit["layer"], limit["lock_reason"], limit["editable"], limit["target"]),
                         ("winner", "env", "env_shell", False, None))

    def test_ignored_names_the_default_winner(self):
        world = World(self, user={"model": OPUS, "effortLevel": "xhigh"})
        warning = self.preview(world, "user", "low")["warning"]
        self.assertEqual(warning["status"], "ignored")
        limit = warning["limits"][0]
        self.assertEqual((limit["kind"], limit["layer"], limit["lock_reason"], limit["editable"]),
                         ("winner", "default", "no_key_in_file", False))

    def test_unknown_with_no_model_names_the_model(self):
        world = World(self, user={"effortLevel": "high"})
        warning = self.preview(world, "user", "low")["warning"]
        self.assertEqual(warning["status"], "unknown")
        self.assertEqual(warning["limits"], [{"kind": "model_unknown", "value": None, "layer": None,
                                              "file_display": None, "line": None, "editable": False,
                                              "target": None, "lock_reason": "model_unknown"}])

    def test_a_warning_does_not_block_a_save(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "medium"}, project={"effortLevel": "low"})
        target = target_of(world.targets(), "project")["target"]
        status, pv = world.preview(target, "xhigh")
        self.assertEqual(status, 200, pv)
        self.assertEqual(pv["warning"]["status"], "lowered")
        status, saved = world.save(pv, target, "xhigh")
        self.assertEqual(status, 200, saved)
        self.assertIn(b'"xhigh"', world.read("project"))

    def test_a_target_gone_from_the_after_answer_is_not_editable(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        listing = projects.load(world.ctx)
        view = api_edit._view(world.ctx, listing, listing.find(world.key))
        after = {"entries": [e for e in view.entries if e["layer"] != "project"]}
        with self.assertRaises(api_edit._Answer) as caught:
            api_edit._warning(view, view.targets[0], "high", after, after)
        self.assertEqual((caught.exception.status, caught.exception.body), (400, {"error": "not_editable"}))


# --------------------------------------------------------------------------
# Save

class Save(Base):
    def world(self, **kwargs):
        defaults = {"user": {"model": SONNET}, "project": {"effortLevel": "low"}}
        defaults.update(kwargs)
        return World(self, **defaults)

    def ready(self, world, layer="project", value="high", ends=None):
        target = target_of(world.targets(), layer, ends)["target"]
        status, pv = world.preview(target, value)
        self.assertEqual(status, 200, pv)
        return target, pv

    def backups(self, world):
        found = []
        for dirpath, _dirs, files in os.walk(os.path.join(world.cfg, edit_store.STORE_DIR)):
            found += [os.path.join(dirpath, f) for f in files if f.endswith(".bak") or f == "ledger.json"]
        return found

    def test_a_save_returns_the_edit_and_the_settings(self):
        world = self.world()
        old = world.read("project")
        target, pv = self.ready(world)
        status, body = world.save(pv, target, "high")
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"edit", "settings"})
        self.assertEqual(world.read("project"), old.replace(b'"low"', b'"high"'))
        edit = body["edit"]
        self.assertEqual(set(edit), {"id", "kind", "time", "layer", "file_display", "op", "key_path", "old_value",
                                     "new_value", "backup_display", "undoable", "not_undoable_reason"})
        self.assertEqual((edit["kind"], edit["layer"], edit["file_display"], edit["key_path"], edit["old_value"],
                          edit["new_value"], edit["time"]),
                         ("edit", "project", "project/.claude/settings.json", ["effortLevel"], "low", "high",
                          FIXED.isoformat()))
        self.assertEqual((edit["undoable"], edit["not_undoable_reason"]), (True, None))
        with open(world.real(edit["backup_display"]), "rb") as fh:
            self.assertEqual(fh.read(), old)
        listing = projects.load(world.ctx)
        self.assertEqual(body["settings"], api_settings.answer(world.ctx, listing, listing.find(world.key)))
        self.assertEqual(main_effort(body["settings"])["value"], "high")

    def test_a_save_in_every_layer_and_a_model_path_changes_only_that_value(self):
        raw = ('{"model": "%s", "modelSettings": {"%s": {"effortLevel": "low"}}, "effortLevel": "low"}\n'
               % (OPUS, OPUS))
        # Only the layer that wins takes a pick, so each world drops the layers above the one it edits.
        worlds = (("local", None, dict(user=raw, project={"effortLevel": "low"}, local={"effortLevel": "low"})),
                  ("project", None, dict(user=raw, project={"effortLevel": "low"})),
                  ("user", "modelSettings.claude-opus-5-5.effortLevel", dict(user=raw)))
        for layer, ends, files in worlds:
            world = World(self, **files)
            before = {name: world.read(name) for name in files}
            target = target_of(world.targets(), layer, ends)["target"]
            world.edit(target, "medium")
            for name, data in before.items():
                if name == layer:
                    self.assertEqual(world.read(name), data.replace(b'"low"', b'"medium"', 1), name)
                else:
                    self.assertEqual(world.read(name), data, name)

    def test_missing_bases_answer_bad_request_and_write_nothing(self):
        world = self.world()
        target, pv = self.ready(world)
        before = world.snapshot()
        good = world.save_body(pv, target, "high")
        for name in ("base_file", "base_trail", "base_others"):
            missing = dict(good)
            del missing[name]
            self.assertEqual(api_edit.save(world.ctx, missing), (400, {"error": "bad_request"}), name)
        for name, value in (("base_file", 5), ("base_trail", None), ("base_others", "x"), ("base_others", [])):
            self.assertEqual(api_edit.save(world.ctx, dict(good, **{name: value})), (400, {"error": "bad_request"}))
        self.assertEqual(world.snapshot(), before)

    def test_save_checks_value_and_target_like_preview(self):
        world = self.world()
        target, pv = self.ready(world)
        self.assertEqual(world.save(pv, target, "max"), (400, {"error": "bad_value"}))
        self.assertEqual(world.save(pv, 5, "high"), (400, {"error": "bad_request"}))
        self.assertEqual(world.save(pv, "t-0000000000000000", "high"), (400, {"error": "not_editable"}))
        self.assertEqual(api_edit.save(world.ctx, dict(world.save_body(pv, target, "high"), project="nope")),
                         (404, {"error": "unknown_project"}))
        self.assertEqual(world.read("project"), dumps({"effortLevel": "low"}).encode())

    def test_no_effort_support_cannot_be_saved(self):
        world = self.world(user={"model": "claude-haiku-4-5"})
        target = target_of(world.targets(), "project")["target"]
        body = world.save_body({"base_file": "a", "base_trail": "b", "base_others": {}}, target, "high")
        self.assertEqual(api_edit.save(world.ctx, body), (400, {"error": "not_editable"}))
        self.assertEqual(world.read("project"), dumps({"effortLevel": "low"}).encode())

    def test_a_changed_target_file_is_stale_and_names_that_file(self):
        world = self.world()
        target, pv = self.ready(world)
        world.write("project", {"effortLevel": "low", "added": 1})
        changed = world.read("project")
        status, body = world.save(pv, target, "high")
        self.assertEqual(status, 409)
        self.assertEqual(set(body), {"error", "changed", "changed_files", "preview"})
        self.assertEqual((body["error"], body["changed"]), ("stale", "file"))
        self.assertEqual(body["changed_files"], [{"layer": "project", "file_display": "project/.claude/settings.json"}])
        self.assertEqual(world.read("project"), changed)
        self.assertEqual(self.backups(world), [])
        self.assertEqual(body["preview"]["base_file"], api_edit._hmac(world.ctx, changed))
        self.assertEqual(body["preview"]["old_value"], "low")
        # The fresh preview is a valid way forward: its bases save.
        status, again = world.save(body["preview"], target, "high")
        self.assertEqual(status, 200, again)

    def test_a_changed_other_layer_is_stale_with_changed_trail(self):
        world = self.world(user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                           project={"effortLevel": "high"})
        target, pv = self.ready(world, "project", "medium")
        world.write("user", {"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}, "unrelated": True})
        project_bytes = world.read("project")
        status, body = world.save(pv, target, "medium")
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "trail"))
        self.assertEqual(body["changed_files"], [{"layer": "user", "file_display": "config/settings.json"}])
        self.assertEqual(world.read("project"), project_bytes)
        self.assertEqual(self.backups(world), [])
        status, again = world.save(body["preview"], target, "medium")
        self.assertEqual(status, 200, again)

    def test_a_changed_trail_with_the_same_files_has_an_empty_file_list(self):
        world = self.world()
        target, pv = self.ready(world)
        stale = dict(pv, base_trail="0" * 64)
        status, body = world.save(stale, target, "high")
        self.assertEqual((status, body["changed"], body["changed_files"]), (409, "trail", []))

    def test_each_other_file_is_named_with_its_layer(self):
        world = self.world(local={"effortLevel": "medium"}, managed={"maxEffortLevel": "xhigh"})
        target, pv = self.ready(world, "local")  # the local line wins, so it is the row that takes a pick
        for layer, display in (("project", "project/.claude/settings.json"), ("user", "config/settings.json"),
                               ("managed", "managed/managed-settings.json")):
            original = world.read(layer)
            world.write(layer, original + b"\n")
            status, body = world.save(pv, target, "high")
            self.assertEqual((status, body["changed"]), (409, "trail"), layer)
            self.assertEqual(body["changed_files"], [{"layer": layer, "file_display": display}], layer)
            world.write(layer, original)
        self.assertEqual(world.save(pv, target, "high")[0], 200)

    def test_a_file_that_appears_or_goes_is_stale(self):
        world = self.world()
        target, pv = self.ready(world)
        world.write("local", {"note": 1})
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["changed_files"]),
                         (409, [{"layer": "local", "file_display": "project/.claude/settings.local.json"}]))
        os.remove(world.path("local"))
        os.remove(world.path("user"))
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["changed_files"]),
                         (409, [{"layer": "user", "file_display": "config/settings.json"}]))

    def test_a_stale_save_leaves_the_store_with_no_backup_or_ledger(self):
        world = self.world()
        target, pv = self.ready(world)
        world.write("user", {"model": OPUS})
        world.save(pv, target, "high")
        self.assertEqual(self.backups(world), [])

    def test_no_change_answers_after_the_stale_check(self):
        world = self.world()
        target, pv = self.ready(world, value="low")
        self.assertIs(pv["no_change"], True)
        self.assertEqual(world.save(pv, target, "low"), (400, {"error": "no_change"}))
        world.write("user", {"model": OPUS})
        status, body = world.save(pv, target, "low")
        self.assertEqual((status, body["error"]), (409, "stale"))
        self.assertEqual(self.backups(world), [])

    def test_a_target_whose_line_went_is_stale_and_its_id_now_names_an_add(self):
        world = self.world()
        target, pv = self.ready(world)
        world.write("project", {"model": "x"})  # the key is gone
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"]), (409, "stale"))
        self.assertEqual((body["preview"]["target"], body["preview"]["op"]), (target, "insert"))

    def test_a_target_in_a_file_that_stopped_parsing_is_not_editable(self):
        world = self.world()
        target, pv = self.ready(world)
        world.write("project", "{not json")
        status, body = world.save(pv, target, "high")
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "not_editable"})

    def test_a_save_fills_the_ledger_and_the_history_of_the_project(self):
        world = self.world()
        target, pv = self.ready(world)
        world.save(pv, target, "high")
        rows = world.history()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["new_value"], "high")


class StoreFailures(Base):
    """The answers for each store exception, reached through a seam in a real save."""

    def setUp(self):
        self.world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        self.target = target_of(self.world.targets(), "project")["target"]
        self.original = self.world.read("project")

    def attempt(self, seam_name, action):
        status, pv = self.world.preview(self.target, "high")
        self.assertEqual(status, 200)

        def seam(seen):
            if seen == seam_name:
                action()
        self.world.store.seam = seam
        return self.world.save(pv, self.target, "high")

    def test_write_failed_leaves_the_file_unchanged(self):
        def fail():
            raise OSError(28, "no space")
        status, body = self.attempt("after_backup", fail)
        self.assertEqual((status, body), (500, {"error": "write_failed", "file_unchanged": True}))
        self.assertEqual(self.world.read("project"), self.original)

    def test_a_missing_config_folder_has_its_own_answer_on_save(self):
        self.world.edit(self.target, "medium")
        before = self.world.read("project")
        status, pv = self.world.preview(self.target, "high")
        gone = os.path.join(self.world.cfg, "gone")
        self.world.store.config_dir = gone
        status, body = self.world.save(pv, self.target, "high")
        self.assertEqual((status, body["error"], body["file_unchanged"]), (500, "config_dir_missing", True))
        self.assertEqual(body["config_dir_display"], "config/gone")
        self.assertEqual(self.world.read("project"), before)
        self.assertFalse(os.path.exists(gone))

    def damage_ledger(self):
        saved = self.world.edit(self.target, "medium")
        ledger = [os.path.join(d, f) for d, _x, files in os.walk(self.world.cfg) for f in files
                  if f == "ledger.json"][0]
        with open(ledger, "w") as fh:
            fh.write("{not json")
        return saved, ledger

    def test_a_damaged_ledger_has_its_own_answer_on_save(self):
        _saved, ledger = self.damage_ledger()
        before = self.world.read("project")
        status, pv = self.world.preview(self.target, "high")
        status, body = self.world.save(pv, self.target, "high")
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "ledger_damaged")
        self.assertIs(body["file_unchanged"], True)
        self.assertTrue(body["ledger_display"].endswith("ledger.json"))
        self.assertEqual(self.world.read("project"), before)
        with open(ledger) as fh:
            self.assertEqual(fh.read(), "{not json")

    def test_a_damaged_ledger_has_its_own_answer_on_undo(self):
        saved, _ledger = self.damage_ledger()
        before = self.world.read("project")
        status, body = self.world.undo(saved["edit"]["id"])
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "ledger_damaged")
        self.assertEqual(self.world.read("project"), before)

    def test_history_names_a_damaged_ledger_and_shows_no_rows(self):
        self.damage_ledger()
        history = self.world.history()
        self.assertEqual(history["rows"], [])
        self.assertEqual([item["layer"] for item in history["damaged_ledgers"]], ["project"])
        self.assertTrue(history["damaged_ledgers"][0]["ledger_display"].endswith("ledger.json"))

    def test_history_lists_no_damaged_ledger_when_all_are_sound(self):
        self.world.edit(self.target, "medium")
        self.assertEqual(self.world.history()["damaged_ledgers"], [])

    def test_a_file_that_moved_before_the_rename_is_stale_with_a_fresh_preview(self):
        moved = dumps({"effortLevel": "low", "added": True}).encode()

        def move():
            with open(self.world.path("project"), "wb") as fh:
                fh.write(moved)
        status, body = self.attempt("before_recheck", move)
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "file"))
        self.assertEqual(body["changed_files"], [{"layer": "project", "file_display": "project/.claude/settings.json"}])
        self.assertEqual(body["preview"]["base_file"], api_edit._hmac(self.world.ctx, moved))
        self.assertEqual(self.world.read("project"), moved)

    def test_a_fresh_preview_that_fails_falls_back_to_null(self):
        def vanish():
            with open(self.world.path("project"), "wb") as fh:
                fh.write(b"{not json")
        status, body = self.attempt("before_recheck", vanish)
        self.assertEqual((status, body["error"], body["preview"]), (409, "stale", None))

    def test_a_write_after_the_rename_is_raced(self):
        other = dumps({"effortLevel": "xhigh"}).encode()

        def race():
            with open(self.world.path("project"), "wb") as fh:
                fh.write(other)
        status, body = self.attempt("after_rename", race)
        self.assertEqual(status, 409)
        self.assertEqual(set(body), {"error", "edit", "backup_display", "settings"})
        self.assertEqual(body["error"], "raced")
        self.assertEqual(body["edit"]["kind"], "edit")
        self.assertFalse(body["edit"]["undoable"])
        self.assertRegex(body["backup_display"], r"^config/routing-dashboard/backups/[0-9a-f]{16}/\d{6}-[0-9a-f]{16}\.bak$")
        self.assertEqual(main_effort(body["settings"])["value"], "xhigh")

    def test_a_failed_read_back_is_unverified(self):
        def fail():
            raise OSError(5, "io error")
        status, body = self.attempt("reread", fail)
        self.assertEqual(status, 500)
        self.assertEqual(set(body), {"error", "stage", "file_unchanged", "edit", "backup_display"})
        self.assertEqual((body["error"], body["stage"], body["file_unchanged"]), ("unverified", "reread", False))
        self.assertEqual((body["edit"]["op"], body["edit"]["kind"]), ("replace", "edit"))
        self.assertRegex(body["backup_display"], r"\.bak$")
        self.assertEqual(self.world.read("project"), self.original.replace(b'"low"', b'"high"'))

    def test_every_exception_has_one_answer(self):
        ctx = self.world.ctx
        req = api_edit._Request(ctx, None, None)
        cases = (
            (edit_store.Refused("not_editable"), 400, {"error": "not_editable"}),
            (edit_store.Refused("unknown_project"), 404, {"error": "unknown_project"}),
            (edit_store.Refused("no_change"), 400, {"error": "no_change"}),
            (edit_store.Refused("file_missing"), 422, {"error": "file_missing"}),
            (edit_store.Refused("symlink"), 422, {"error": "symlink"}),
            (edit_store.Refused("too_large"), 422, {"error": "too_large"}),
            (edit_store.WriteFailed("x"), 500, {"error": "write_failed", "file_unchanged": True}),
            (edit_store.ConfigDirMissing(None), 500, {"error": "config_dir_missing", "file_unchanged": True,
                                                      "config_dir_display": None}),
            (edit_store.ChangedSinceSave(None), 409, {"error": "changed_since_save", "backup_display": None}),
            (edit_store.BackupDamaged(None), 409, {"error": "backup_damaged", "backup_display": None}),
            (edit_store.NotUndoable("not_newest"), 409, {"error": "not_undoable", "reason": "not_newest"}),
            (edit_store.UnknownEdit("x"), 404, {"error": "unknown_edit"}),
            (json_edit.Refused("key_missing"), 422, {"error": "key_missing"}),
            (json_edit.Refused("unparsed"), 422, {"error": "unparsed"}),
            (json_edit.Refused("oracle_failed"), 500, {"error": "write_failed", "file_unchanged": True}),
        )
        for exc, status, body in cases:
            self.assertEqual(api_edit._store_answer(req, exc), (status, body), repr(exc))
        # Unverified carries the edit row, so its answer needs a real target and a real ledger row.
        saved = self.world.edit(self.target, "medium")["edit"]
        store_target = edit_store.target_for(ctx, self.world.key, "project")
        row = self.world.store.find(store_target, saved["id"])
        status, body = api_edit._store_answer(api_edit._Request(ctx, None, None, store_target, undo=True),
                                              edit_store.Unverified("fsync", row, None))
        self.assertEqual((status, set(body)), (500, {"error", "stage", "file_unchanged", "edit", "backup_display"}))
        self.assertEqual((body["error"], body["stage"], body["file_unchanged"], body["backup_display"], body["edit"]["id"]),
                         ("unverified", "fsync", False, None, saved["id"]))
        path = os.path.join(self.world.cfg, "x.bak")
        status, body = api_edit._store_answer(req, edit_store.ChangedSinceSave(path))
        self.assertEqual(body["backup_display"], "config/x.bak")


# --------------------------------------------------------------------------
# Undo and history

class Undo(Base):
    def setUp(self):
        self.world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        self.target = target_of(self.world.targets(), "project")["target"]
        self.original = self.world.read("project")

    def test_an_undo_puts_the_backup_back_and_proves_it(self):
        saved = self.world.edit(self.target, "high")
        status, body = self.world.undo(saved["edit"]["id"])
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"edit", "settings", "matches_backup", "restored_from_display",
                                     "removed_file", "removed_dir"})
        self.assertEqual((body["removed_file"], body["removed_dir"]), (False, False))
        self.assertIs(body["matches_backup"], True)
        self.assertEqual(body["restored_from_display"], saved["edit"]["backup_display"])
        self.assertEqual(self.world.read("project"), self.original)
        with open(self.world.real(body["restored_from_display"]), "rb") as fh:
            self.assertEqual(fh.read(), self.world.read("project"))
        edit = body["edit"]
        self.assertEqual((edit["kind"], edit["undoable"], edit["not_undoable_reason"]), ("undo", False, "undo_row"))
        self.assertEqual(edit["restored_from_display"], saved["edit"]["backup_display"])
        self.assertNotEqual(edit["backup_display"], edit["restored_from_display"])
        self.assertEqual((edit["old_value"], edit["new_value"]), ("high", "low"))
        self.assertEqual(main_effort(body["settings"])["value"], "low")

    def test_edit_edit_undo_leaves_no_undoable_row_whatever_the_hashes_say(self):
        first = self.world.edit(self.target, "medium")["edit"]
        second = self.world.edit(self.target, "high")["edit"]
        status, undone = self.world.undo(second["id"])
        self.assertEqual(status, 200)
        # The file holds the first edit's result again, so the first row's hash matches. It still is
        # not the newest row, and the undo row is not an edit.
        self.assertEqual(self.world.read("project"), dumps({"effortLevel": "medium"}).encode())
        rows = self.world.history()["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["undoable"] for r in rows], [False, False, False])
        reasons = {r["id"]: r["not_undoable_reason"] for r in rows}
        self.assertEqual(reasons[undone["edit"]["id"]], "undo_row")
        self.assertEqual(reasons[first["id"]], "not_newest")
        self.assertEqual(reasons[second["id"]], "not_newest")
        for edit_id, reason in ((first["id"], "not_newest"), (second["id"], "not_newest"),
                                (undone["edit"]["id"], "undo_row")):
            self.assertEqual(self.world.undo(edit_id), (409, {"error": "not_undoable", "reason": reason}))
        self.assertEqual(self.world.read("project"), dumps({"effortLevel": "medium"}).encode())

    def test_an_older_row_and_an_undo_row_are_not_undoable(self):
        first = self.world.edit(self.target, "medium")["edit"]
        self.world.edit(self.target, "high")
        before = self.world.read("project")
        self.assertEqual(self.world.undo(first["id"]), (409, {"error": "not_undoable", "reason": "not_newest"}))
        self.assertEqual(self.world.read("project"), before)

    def test_a_changed_file_answers_changed_since_save_with_the_backup_path(self):
        saved = self.world.edit(self.target, "high")["edit"]
        self.world.write("project", {"effortLevel": "high", "by_hand": True})
        status, body = self.world.undo(saved["id"])
        self.assertEqual((status, body), (409, {"error": "changed_since_save",
                                                "backup_display": saved["backup_display"]}))
        rows = self.world.history()["rows"]
        self.assertEqual((rows[0]["undoable"], rows[0]["not_undoable_reason"]), (False, "changed_since_save"))

    def test_a_damaged_backup_answers_backup_damaged(self):
        saved = self.world.edit(self.target, "high")["edit"]
        with open(self.world.real(saved["backup_display"]), "wb") as fh:
            fh.write(b"{")
        status, body = self.world.undo(saved["id"])
        self.assertEqual((status, body), (409, {"error": "backup_damaged", "backup_display": saved["backup_display"]}))
        self.assertEqual(self.world.read("project"), dumps({"effortLevel": "high"}).encode())
        self.assertEqual(self.world.history()["rows"][0]["not_undoable_reason"], "backup_damaged")

    def test_an_unknown_or_malformed_edit(self):
        self.world.edit(self.target, "high")
        self.assertEqual(self.world.undo("0" * 16), (404, {"error": "unknown_edit"}))
        self.assertEqual(self.world.undo("../../x"), (404, {"error": "unknown_edit"}))
        for edit_id in (None, 5, ["a"]):
            self.assertEqual(self.world.undo(edit_id), (400, {"error": "bad_request"}), repr(edit_id))
        self.assertEqual(api_edit.undo(self.world.ctx, {"project": self.world.key}), (400, {"error": "bad_request"}))
        self.assertEqual(api_edit.undo(self.world.ctx, {"project": "nope", "edit": "x"}),
                         (404, {"error": "unknown_project"}))

    def test_path_file_and_dot_dot_fields_change_nothing_on_undo(self):
        saved = self.world.edit(self.target, "high")["edit"]
        status, body = self.world.undo(saved["id"], path="/etc/passwd", file="../x", layer="user")
        self.assertEqual(status, 200)
        self.assertEqual(self.world.read("project"), self.original)
        self.assertEqual(self.world.read("user"), dumps({"model": SONNET}).encode())

    def test_a_write_after_an_undo_rename_is_raced_with_matches_backup_false(self):
        saved = self.world.edit(self.target, "high")["edit"]
        other = dumps({"effortLevel": "xhigh"}).encode()

        def race(seen):
            if seen == "after_rename":
                with open(self.world.path("project"), "wb") as fh:
                    fh.write(other)
        self.world.store.seam = race
        status, body = self.world.undo(saved["id"])
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "raced")
        self.assertIs(body["matches_backup"], False)
        self.assertEqual(body["restored_from_display"], saved["backup_display"])
        self.assertEqual(body["edit"]["kind"], "undo")
        self.assertEqual(set(body), {"error", "edit", "backup_display", "settings", "matches_backup",
                                     "restored_from_display"})


class RepoLock(Base):
    """A project that is a repo subfolder, a worktree or a submodule locks every write (T23)."""

    def make(self):
        return World(self, user={"model": SONNET, "effortLevel": "high"}, project={"effortLevel": "low"},
                     local={"effortLevel": "medium"})

    def lock(self, world, place):
        world.place.stop()
        world.place = mock.patch.object(git_check, "repo_place", return_value=place)
        world.place.start()
        self.addCleanup(world.place.stop)

    def test_subfolder_and_linked_lock_every_row(self):
        for place in ("subfolder", "linked"):
            with self.subTest(place=place):
                world = self.make()
                before = world.targets()
                ids = [t["target"] for t in before["targets"]]
                self.assertTrue(ids)
                self.assertIsNone(before["project_lock"])
                self.lock(world, place)
                after = world.targets()
                self.assertEqual(after["project_lock"], "not_repo_root")
                self.assertEqual(after["targets"], [])
                self.assertEqual(len(after["blocked"]), len(before["targets"]))
                self.assertEqual({b["reason"] for b in after["blocked"]}, {"not_repo_root"})
                self.assertIs(after["saveable"], False)
                self.assertEqual({f["layer"] for f in after["files"]}, {"user", "project", "local"})
                for row in after["files"]:
                    self.assertEqual(row["lock_reason"], "not_repo_root")
                    self.assertIsNone(row["target"])
                self.assertEqual(file_of(after["files"], "user")["state"], "locked")
                for level in after["levels"]:
                    self.assertIs(level["saveable"], False)
                    self.assertIsNone(level["preselect"])
                    for row in level["files"]:
                        self.assertEqual(row["lock_reason"], "not_repo_root")
                        self.assertIs(row["pickable"], False)
                for target in ids:
                    status, body = world.preview(target, "xhigh")
                    self.assertEqual((status, body), (422, {"error": "not_repo_root"}))

    def test_a_missing_file_keeps_its_state_but_locks(self):
        world = World(self, user={"model": SONNET})
        self.lock(world, "subfolder")
        rows = world.targets()["files"]
        self.assertEqual(file_of(rows, "local")["state"], "absent")
        self.assertEqual(file_of(rows, "local")["lock_reason"], "not_repo_root")
        self.assertEqual(file_of(rows, "project")["lock_reason"], "not_repo_root")

    def test_a_forced_save_is_refused_and_the_file_is_untouched(self):
        for place in ("subfolder", "linked"):
            with self.subTest(place=place):
                world = self.make()
                target = target_of(world.targets(), "local")["target"]
                status, pv = world.preview(target, "low")
                self.assertEqual(status, 200)
                before = world.snapshot()
                self.lock(world, place)
                status, body = world.save(pv, target, "low")
                self.assertEqual((status, body), (422, {"error": "not_repo_root"}))
                self.assertEqual(world.snapshot(), before)

    def test_a_repo_lock_that_appears_between_the_check_and_the_write_is_refused(self):
        world = self.make()
        target = target_of(world.targets(), "local")["target"]
        status, pv = world.preview(target, "low")
        self.assertEqual(status, 200)
        # The store makes its own folder before it plans, so only the settings files are compared.
        before = {k: v for k, v in world.snapshot().items() if "routing-dashboard" not in k}
        world.place.stop()
        # The view before the lock sees no repo, the view the write plan reads again sees a subfolder.
        world.place = mock.patch.object(git_check, "repo_place", side_effect=["no_repo", "subfolder"])
        world.place.start()
        self.addCleanup(world.place.stop)
        status, body = world.save(pv, target, "low")
        self.assertEqual((status, body), (422, {"error": "not_repo_root"}))
        after = {k: v for k, v in world.snapshot().items() if "routing-dashboard" not in k}
        self.assertEqual(after, before)

    def test_undo_stays_open_while_locked(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        original = world.read("project")
        target = target_of(world.targets(), "project")["target"]
        saved = world.edit(target, "high")
        self.lock(world, "subfolder")
        status, body = world.undo(saved["edit"]["id"])
        self.assertEqual(status, 200)
        self.assertIs(body["matches_backup"], True)
        self.assertEqual(world.read("project"), original)

    def test_root_and_no_repo_lock_nothing(self):
        for place in ("root", "no_repo"):
            with self.subTest(place=place):
                world = self.make()
                self.lock(world, place)
                body = world.targets()
                self.assertIsNone(body["project_lock"])
                self.assertEqual(body["blocked"], [])
                self.assertEqual(len(body["targets"]), 3)
                self.assertNotIn("not_repo_root", {f["lock_reason"] for f in body["files"]})
                target = target_of(body, "local")["target"]  # the local line wins, so it takes a pick
                self.assertEqual(world.preview(target, "low")[0], 200)

    def test_an_unexpanded_project_is_not_walked(self):
        project = projects.Project("x", "~/nowhere", unexpanded=True) if hasattr(projects, "Project") else None
        if project is None:
            self.skipTest("no Project class")
        with mock.patch.object(git_check, "repo_place", side_effect=AssertionError("walked")):
            self.assertIs(api_edit._repo_locked(project), False)


class History(Base):
    def test_rows_join_the_three_ledgers_newest_first(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"effortLevel": "low"}, local={"effortLevel": "low"})
        ids = {}
        # Only the layer that wins takes a pick, so each step first leaves the layers above it empty.
        arrange = ({"project": {}, "local": {}}, {"local": {"effortLevel": "low"}},
                   {"project": {"effortLevel": "low"}, "local": {}}, {"project": {}})
        for step, (layer, ends) in enumerate((("user", "claude-opus-5-5.effortLevel"), ("local", None),
                                              ("project", None), ("user", "claude-opus-5-5.effortLevel"))):
            for name, content in arrange[step].items():
                world.write(name, content)
            world.store.fixed_now = FIXED + datetime.timedelta(minutes=step)
            value = "medium" if step < 3 else "high"
            target = target_of(world.targets(), layer, ends)["target"]
            ids[step] = world.edit(target, value)["edit"]["id"]
        rows = world.history()
        self.assertEqual(set(rows), {"enabled", "project", "rows", "damaged_ledgers"})
        self.assertEqual((rows["enabled"], rows["project"]), (True, world.key))
        self.assertEqual([r["id"] for r in rows["rows"]], [ids[3], ids[2], ids[1], ids[0]])
        self.assertEqual([r["layer"] for r in rows["rows"]], ["user", "project", "local", "user"])
        times = [r["time"] for r in rows["rows"]]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_equal_times_fall_back_to_the_backup_number(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        target = target_of(world.targets(), "project")["target"]
        a = world.edit(target, "medium")["edit"]["id"]
        b = world.edit(target, "high")["edit"]["id"]
        self.assertEqual([r["id"] for r in world.history()["rows"]], [b, a])

    def test_a_row_has_every_field(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        target = target_of(world.targets(), "project")["target"]
        saved = world.edit(target, "high")["edit"]
        undone = world.undo(saved["id"])[1]["edit"]
        rows = world.history()["rows"]
        self.assertEqual(rows[0], undone)
        self.assertEqual(set(rows[0]), {"id", "kind", "time", "layer", "file_display", "op", "key_path", "old_value",
                                        "new_value", "backup_display", "restored_from_display", "undoable",
                                        "not_undoable_reason"})
        self.assertNotIn("restored_from_display", rows[1])
        self.assertEqual(set(rows[1]), set(rows[0]) - {"restored_from_display"})

    def test_a_user_file_edit_appears_under_every_project(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      listed=[{"name": "Main", "path": "{proj}"}, {"name": "Second", "path": "{root}/second"}])
        os.makedirs(os.path.join(world.root, "second", ".claude"))
        self.assertEqual(world.key, "main")
        target = target_of(world.targets(), "user")["target"]
        status, pv = world.preview(target, "medium")
        self.assertEqual(status, 200, pv)
        status, saved = world.save(pv, target, "medium")
        self.assertEqual(status, 200, saved)
        self.assertEqual([r["id"] for r in world.history("main")["rows"]], [saved["edit"]["id"]])
        rows = world.history("second")["rows"]
        self.assertEqual([r["id"] for r in rows], [saved["edit"]["id"]])
        # An undo from the other project works too.
        status, undone = api_edit.undo(world.ctx, {"project": "second", "edit": saved["edit"]["id"]})
        self.assertEqual(status, 200, undone)
        self.assertEqual(world.read("user"), dumps({"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}}).encode())

    def test_a_target_that_cannot_be_made_is_skipped(self):
        # A project path with an unexpanded ~ has no project or local file, but the user ledger still reads.
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      listed=[{"name": "Main", "path": "{proj}"}, {"name": "Tilde", "path": "~/no-home-here"}])
        target = target_of(world.targets("main"), "user")["target"]
        status, pv = api_edit.preview(world.ctx, {"project": "main", "target": target, "value": "medium"})
        status, saved = api_edit.save(world.ctx, dict(world.save_body(pv, target, "medium"), project="main"))
        self.assertEqual(status, 200, saved)
        with self.assertRaises(edit_store.Refused):
            edit_store.target_for(world.ctx, "tilde", "project")
        rows = world.history("tilde")["rows"]
        self.assertEqual([(r["id"], r["layer"]) for r in rows], [(saved["edit"]["id"], "user")])

    def test_a_store_folder_that_is_a_link_gives_no_rows_for_that_target(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        target = target_of(world.targets(), "project")["target"]
        saved = world.edit(target, "high")["edit"]
        backups = os.path.dirname(world.real(saved["backup_display"]))
        moved = backups + "-moved"
        os.rename(backups, moved)
        os.symlink(moved, backups)
        self.assertEqual(world.history()["rows"], [])
        self.assertEqual(world.undo(saved["id"]), (404, {"error": "unknown_edit"}))

    def test_values_in_rows_are_masked_again(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        target = target_of(world.targets(), "project")["target"]
        saved = world.edit(target, "high")["edit"]
        ledger = [os.path.join(d, f) for d, _x, files in os.walk(world.cfg) for f in files if f == "ledger.json"][0]
        with open(ledger, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["rows"][0]["old_value"] = SECRET
        with open(ledger, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        row = world.history()["rows"][0]
        self.assertEqual(row["old_value"], "hidden")
        self.assertNotIn("sk-planted", json.dumps(world.history()))
        self.assertEqual(saved["id"], row["id"])

    def test_the_project_rules_apply(self):
        world = World(self, user={"model": SONNET})
        self.assertEqual(api_edit.history(world.ctx, {"project": ["a", "b"]}), (400, {"error": "bad_request"}))
        self.assertEqual(api_edit.history(world.ctx, {"project": ["all"]}), (400, {"error": "bad_request"}))
        self.assertEqual(api_edit.history(world.ctx, {"project": ["nope"]}), (404, {"error": "unknown_project"}))
        self.assertEqual(api_edit.history(world.ctx, {}), (200, {"enabled": True, "project": world.key, "rows": [], "damaged_ledgers": []}))


# --------------------------------------------------------------------------
# Adds: a new effort line in a file that exists (T11b)

def add_of(body, layer, ends=None):
    """Return the one add row of a layer, optionally the one whose ref ends with `ends`."""
    found = [a for a in body["adds"] if a["layer"] == layer and (ends is None or a["ref"].endswith(ends))]
    assert len(found) == 1, (layer, ends, body["adds"])
    return found[0]


MODEL_REF = 'modelSettings.%s.effortLevel"]'  # the end of a ref through modelSettings
TOP = '"effortLevel"]'  # the end of a ref for the top-level line


class Adds(Base):
    def test_a_project_file_with_no_line_takes_an_insert_and_local_is_the_preselect(self):
        world = World(self, user={"model": OPUS}, project={"language": "en"}, local={"language": "en"})
        body = world.targets()
        local = add_of(body, "local", TOP)
        project = add_of(body, "project", TOP)
        self.assertEqual((local["op"], project["op"], project["shared"], local["shared"]),
                         ("insert", "insert", True, False))
        self.assertEqual(set(local), {"target", "ref", "layer", "file_display", "op", "shared"})
        todays = body["runs_as"]
        for row in body["levels"]:
            if row["level"] == todays:
                continue
            rows = file_of(row, "project")
            self.assertEqual((rows["op"], rows["effect"], rows["target"], rows["pickable"]),
                             ("insert", "applies", project["target"], True), row["level"])
            self.assertEqual(row["preselect"], local["target"], row["level"])
            self.assertEqual(file_of(row, "local")["effect"], "applies")

    def test_a_level_with_only_a_shared_row_reachable_has_no_preselect(self):
        world = World(self, user={"model": OPUS}, project={"language": "en"}, local="{ not json")  # local locked
        body = world.targets()
        self.assertEqual(file_of(body["files"], "local")["state"], "locked")
        for row in body["levels"]:
            if row["result"] == "now":
                continue
            self.assertEqual(file_of(row, "project")["effect"], "applies")
            self.assertIsNone(row["preselect"], row["level"])
            self.assertIs(row["saveable"], True)

    def test_every_preselect_in_these_worlds_is_a_local_target_or_null(self):
        worlds = [
            World(self, user={"model": OPUS}, project={"language": "en"}, local={"language": "en"}),
            World(self, user={"model": OPUS}, project={"language": "en"}),
            World(self, user={"model": OPUS, "effortLevel": "high"}, project={"effortLevel": "low"}),
            World(self, user={"model": SONNET}, project={"effortLevel": "high"}, local={"language": "en"}),
            World(self, user={"x": 1}, project={"x": 1}, local={"x": 1}),
            World(self, user={"model": SONNET, "maxEffortLevel": "medium"}, local={"x": 1}),
        ]
        seen = 0
        for index, world in enumerate(worlds):
            body = world.targets()
            local_ids = {t["target"] for t in body["targets"] + body["adds"] if t["layer"] == "local"}
            for row in body["levels"]:
                if row["preselect"] is not None:
                    seen += 1
                    self.assertIn(row["preselect"], local_ids, index)
        self.assertGreater(seen, 0)

    def test_an_ignored_top_line_stays_and_the_new_line_goes_beside_it(self):
        world = World(self, user={"model": OPUS, "effortLevel": "high"})
        body = world.targets()
        top = file_of(body["files"], "user")
        self.assertEqual((top["state"], top["status"], top["value"]), ("has_line", "ignored", "high"))
        add = add_of(body, "user", MODEL_REF % OPUS)
        self.assertEqual(add["op"], "insert")
        self.assertEqual(body["runs_as"], "medium")
        row = file_of(level_of(body, "low"), "user")
        self.assertEqual((row["target"], row["op"], row["effect"], row["pickable"]),
                         (add["target"], "insert", "applies", True))
        self.assertIsInstance(row["line"], int)
        before = world.read("user")
        saved = world.edit(add["target"], "low")
        data = json.loads(world.read("user"))
        self.assertEqual(data["effortLevel"], "high")
        self.assertEqual(data["modelSettings"], {OPUS: {"effortLevel": "low"}})
        self.assertTrue(world.read("user").startswith(before.rstrip()[:-1].rstrip()))  # one added span
        self.assertEqual(saved["edit"]["op"], "insert")
        self.assertEqual(saved["edit"]["key_path"], ["modelSettings", OPUS, "effortLevel"])
        self.assertEqual(world.targets()["runs_as"], "low")

    def test_an_existing_alias_entry_gets_the_line_and_no_entry_is_added(self):
        world = World(self, user={"model": OPUS, "modelSettings": {"opus": {"thinking": 1}}})
        body = world.targets()
        add = add_of(body, "user", MODEL_REF % "opus")
        world.edit(add["target"], "low")
        data = json.loads(world.read("user"))
        self.assertEqual(data["modelSettings"], {"opus": {"thinking": 1, "effortLevel": "low"}})

    def test_with_two_matching_names_the_best_form_takes_the_line(self):
        for names, expected in ((["opus", OPUS], OPUS), (["opus[1m]", "opus"], "opus"),
                                ([OPUS + "[1m]", OPUS + "-20260101"], OPUS + "-20260101")):
            with self.subTest(names=names):
                world = World(self, user={"model": OPUS, "modelSettings": {n: {"thinking": 1} for n in names}})
                view = view_of(world)
                keys = [a.key_path for a in view.adds if a.layer == "user" and len(a.key_path) == 3]
                self.assertEqual(keys, [("modelSettings", expected, "effortLevel")])

    def test_with_no_entry_for_the_model_the_catalog_id_is_used(self):
        world = World(self, user={"model": OPUS, "modelSettings": {"sonnet": {"thinking": 1}}})
        view = view_of(world)
        keys = [a.key_path for a in view.adds if a.layer == "user" and len(a.key_path) == 3]
        self.assertEqual(keys, [("modelSettings", OPUS, "effortLevel")])
        add = add_of(world.targets(), "user", MODEL_REF % OPUS)
        world.edit(add["target"], "low")
        self.assertEqual(json.loads(world.read("user"))["modelSettings"],
                         {"sonnet": {"thinking": 1}, OPUS: {"effortLevel": "low"}})

    def test_an_unknown_model_offers_only_a_top_level_add_with_an_unknown_effect(self):
        world = World(self, user={"x": 1}, project={"x": 1}, local={"x": 1})
        body = world.targets()
        self.assertIsNone(body["model"])
        self.assertEqual(sorted(a["layer"] for a in body["adds"]), ["local", "project", "user"])
        for add in body["adds"]:
            self.assertTrue(add["ref"].endswith(TOP), add["ref"])
        user_only = World(self, user={"x": 1}, local="{ not json")  # local locked, so the user file is alone
        for row in user_only.targets()["levels"]:
            f = file_of(row, "user")
            self.assertEqual((f["op"], f["effect"], f["runs_as"], f["pickable"]),
                             ("insert", "unknown", None, True), row["level"])
            self.assertIsNone(row["preselect"])
            self.assertIs(row["saveable"], True)

    def test_a_null_key_is_a_replace_and_the_save_has_a_real_value(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": None})
        body = world.targets()
        self.assertEqual(file_of(body["files"], "project")["state"], "no_line")
        add = add_of(body, "project", '"effortLevel"]')
        self.assertEqual(add["op"], "replace")
        saved = world.edit(add["target"], "high")["edit"]
        self.assertEqual((saved["op"], saved["new_value"]), ("replace", "high"))
        self.assertNotIn("old_value", saved)
        self.assertEqual(json.loads(world.read("project")), {"effortLevel": "high"})

    def test_a_model_settings_that_is_not_an_object_keeps_the_wont_apply_label_on_a_row_with_a_line(self):
        for table, label in (("x", "table"), ({OPUS: "x"}, "entry")):
            with self.subTest(label):
                world = World(self, user={"model": OPUS, "effortLevel": "high", "modelSettings": table})
                body = world.targets()
                self.assertEqual(file_of(body["files"], "user")["state"], "has_line")
                for row in body["levels"]:
                    if row["result"] == "now":
                        continue
                    f = file_of(row, "user")
                    self.assertEqual((f["effect"], f["lock_reason"], f["pickable"]),
                                     ("wont_apply", None, False), label)

    def test_a_model_settings_that_is_not_an_object_locks_a_row_with_no_line(self):
        for table, label in (("x", "table"), ({OPUS: "x"}, "entry")):
            with self.subTest(label):
                world = World(self, user={"model": OPUS, "modelSettings": table})
                body = world.targets()
                self.assertEqual(file_of(body["files"], "user")["state"], "locked")
                for row in body["levels"]:
                    if row["result"] == "now":
                        continue
                    f = file_of(row, "user")
                    self.assertEqual((f["lock_reason"], f["pickable"]), ("parent_not_object", False), label)

    def test_a_name_the_trail_hides_is_not_on_the_trail_and_refuses_with_422(self):
        name = "auth.anthropic.claude-opus-5-5-v1:0"  # normalizes to Opus 5.5, but AUTH hides the name
        self.assertEqual(resolve.normalize_model(name, RULES["models"]), (OPUS, "provider"))
        world = World(self, user={"model": OPUS, "modelSettings": {name: {}}})
        body = world.targets()
        add = add_of(body, "user", "modelSettings.%s.effortLevel\"]" % name)
        view = view_of(world)
        hidden = [a for a in view.adds if a.id == add["target"]][0]
        self.assertEqual(api_edit._effect(view, hidden, "low")[:3], (None, None, "not_on_trail"))
        for row in body["levels"]:
            if row["result"] == "now":
                continue
            f = file_of(row, "user")
            self.assertEqual((f["lock_reason"], f["pickable"]), ("not_on_trail", False), row["level"])
        # a preview of the top add gives hashes a forced request can borrow
        top = add_of(body, "user", '"effortLevel"]')
        pv = inner_preview(world, top["target"], "low")  # a payload whose hashes a forced save can borrow
        before = world.read("user")
        self.assertEqual(world.preview(add["target"], "low"), (422, {"error": "not_on_trail"}))
        self.assertEqual(world.save(pv, add["target"], "low"), (422, {"error": "not_on_trail"}))
        self.assertEqual(world.read("user"), before)
        self.assertEqual(world.history()["rows"], [])

    def test_a_repo_lock_builds_no_adds_and_refuses_a_forced_request(self):
        world = World(self, user={"model": SONNET}, project={"language": "en"})
        add = add_of(world.targets(), "project", TOP)
        status, pv = world.preview(add["target"], "high")
        self.assertEqual(status, 200)
        lock_repo(self, world)
        body = world.targets()
        self.assertEqual(body["adds"], [])
        for f in body["files"]:
            self.assertEqual(f["lock_reason"], "not_repo_root")
        for row in body["levels"]:
            for f in row["files"]:
                self.assertEqual((f["lock_reason"], f["pickable"]), ("not_repo_root", False))
        before = world.snapshot()
        status, _body = world.preview(add["target"], "high")
        self.assertNotEqual(status, 200)
        status, _body = world.save(pv, add["target"], "high")
        self.assertNotEqual(status, 200)
        self.assertEqual(world.snapshot(), before)

    def test_the_preview_of_an_insert_then_a_save_and_an_undo_restore_the_bytes(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "high"}, project={"language": "en"})
        original = world.read("project")
        add = add_of(world.targets(), "project", TOP)
        status, pv = world.preview(add["target"], "xhigh")
        self.assertEqual(status, 200, pv)
        self.assertEqual((pv["op"], pv["layer"], pv["shared"], pv["no_change"], pv["new_file"], pv["creates_dir"]),
                         ("insert", "project", True, False, False, False))
        self.assertIsNone(pv["old_value"])
        self.assertIsInstance(pv["line"], int)
        self.assertEqual(pv["ref"], add["ref"])
        self.assertEqual(pv["base_file"], api_edit._hmac(world.ctx, original))
        self.assertEqual(pv["warning"]["status"], "lowered")
        self.assertEqual(pv["runs_after"], "high")
        self.assertTrue(pv["diff"])
        self.assertEqual(world.read("project"), original)
        status, saved = world.save(pv, add["target"], "xhigh")
        self.assertEqual(status, 200, saved)
        self.assertEqual(json.loads(world.read("project")), {"language": "en", "effortLevel": "xhigh"})
        edit = saved["edit"]
        self.assertEqual((edit["op"], edit["new_value"], edit["undoable"]), ("insert", "xhigh", True))
        self.assertNotIn("old_value", edit)
        status, undone = world.undo(edit["id"])
        self.assertEqual(status, 200, undone)
        self.assertEqual(world.read("project"), original)
        self.assertEqual((undone["edit"]["op"], undone["edit"]["old_value"]), ("insert", "xhigh"))
        self.assertNotIn("new_value", undone["edit"])
        for row in world.history()["rows"]:
            self.assertNotIn(None, [row.get("old_value", 0), row.get("new_value", 0)])
            self.assertEqual(row["op"], "insert")

    def test_a_line_keeps_its_target_id_after_an_add_is_saved_over_its_place(self):
        world = World(self, user={"model": SONNET}, project={"language": "en"})
        body = world.targets()
        add = add_of(body, "project", TOP)
        self.assertEqual(add["target"], api_edit._target_id("project", ("effortLevel",)))
        world.edit(add["target"], "high")
        after = world.targets()
        self.assertNotIn(add["target"], [a["target"] for a in after["adds"]])
        self.assertEqual(target_of(after, "project")["target"], add["target"])
        self.assertEqual(target_of(after, "project")["ref"], add["ref"])
        self.assertEqual(world.edit(add["target"], "low")["edit"]["op"], "replace")

    def test_a_file_edited_between_preview_and_save_is_stale_with_a_fresh_insert_preview(self):
        world = World(self, user={"model": SONNET}, project={"language": "en"})
        add = add_of(world.targets(), "project", TOP)
        status, pv = world.preview(add["target"], "high")
        self.assertEqual(status, 200)
        world.write("project", {"language": "fr"})
        status, body = world.save(pv, add["target"], "high")
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "file"))
        self.assertEqual((body["preview"]["op"], body["preview"]["target"]), ("insert", add["target"]))
        self.assertEqual(json.loads(world.read("project")), {"language": "fr"})

    def test_a_planted_secret_stays_out_of_every_answer_for_an_insert(self):
        shapes = {
            "lines": '{\n  "model": "%s",\n  "apiToken": "%s"\n}\n' % (SONNET, SECRET),
            "one line": '{"model": "%s","apiToken": "%s"}' % (SONNET, SECRET),
        }
        for label, text in shapes.items():
            with self.subTest(label):
                world = World(self, user=text)
                body = world.targets()
                add = add_of(body, "user", 'claude-sonnet-5-5.effortLevel"]')  # the user top line is not read
                status, pv = world.preview(add["target"], "high")
                self.assertEqual(status, 200, pv)
                status, saved = world.save(pv, add["target"], "high")
                self.assertEqual(status, 200, saved)
                self.assertIn(SECRET.encode(), world.read("user"))
                answers = [body, pv, saved, world.targets(), world.history()]
                status, undone = world.undo(saved["edit"]["id"])
                answers += [undone, world.history()]
                for answer in answers:
                    self.assertNotIn("sk-planted-", json.dumps(answer))


class Crash(BaseException):
    """Raised by a seam to stop the process at a step. No cleanup handler catches it."""


class Creates(Base):
    """A settings file that is not there: its row is a create, and a save makes the file."""

    def at(self, world, name, fn):
        """Run fn when the store reaches the seam called name."""
        def seam(seen):
            if seen == name:
                fn()
        world.store.seam = seam

    def local_create(self, world, level="high"):
        """Return (target id, preview payload) of the local create at a level."""
        target = add_of(world.targets(), "local", TOP)["target"]
        status, pv = world.preview(target, level)
        self.assertEqual(status, 200, pv)
        return target, pv

    def test_absent_rows_are_creates_and_only_local_is_preselected(self):
        world = World(self)  # no settings file at all
        body = world.targets()
        self.assertEqual([(f["layer"], f["state"], f["lock_reason"], f["target"]) for f in body["files"]],
                         [("local", "absent", None, None), ("project", "absent", None, None),
                          ("user", "absent", None, None)])
        self.assertEqual(sorted((a["layer"], a["op"]) for a in body["adds"]),
                         [("local", "create"), ("project", "create"), ("user", "create")])
        local = add_of(body, "local", TOP)["target"]
        for row in body["levels"]:
            files = {f["layer"]: f for f in row["files"]}
            self.assertEqual({k: (f["op"], f["target"] is not None) for k, f in files.items()},
                             {"local": ("create", True), "project": ("create", True), "user": ("create", True)})
            self.assertEqual(files["local"]["target"], local)
            self.assertEqual((files["local"]["effect"], files["local"]["pickable"]), ("applies", True))
            self.assertEqual((files["project"]["effect"], files["user"]["effect"]), ("applies", "unknown"))
            self.assertEqual((files["project"]["pickable"], files["user"]["pickable"]), (True, True))
            self.assertEqual(row["preselect"], local)
        self.assertIs(body["saveable"], True)

    def test_a_shared_create_is_never_preselected_and_greys_out_when_it_loses(self):
        world = World(self, user={"model": SONNET}, local={"effortLevel": "low"})
        body = world.targets()
        project = add_of(body, "project", TOP)
        self.assertEqual((project["op"], project["shared"]), ("create", True))
        row = level_of(body, "high")
        grey = file_of(row, "project")
        self.assertEqual((grey["op"], grey["effect"], grey["pickable"]), ("create", "wont_apply", False))
        self.assertEqual(row["preselect"], target_of(body, "local")["target"])
        # With the line out of local, the project create applies and can be picked, still never preselected.
        quiet = World(self, user={"model": SONNET}, local="{ not json")
        quiet_row = level_of(quiet.targets(), "high")
        shared = file_of(quiet_row, "project")
        self.assertEqual((shared["op"], shared["effect"], shared["pickable"]), ("create", "applies", True))
        self.assertIsNone(quiet_row["preselect"])

    def test_a_preview_of_a_create_in_a_project_with_no_claude_folder(self):
        world = World(self, user={"model": SONNET})
        shutil.rmtree(os.path.join(world.proj, ".claude"))
        target, pv = self.local_create(world)
        self.assertEqual((pv["op"], pv["new_file"], pv["creates_dir"], pv["no_change"]), ("create", True, True, False))
        self.assertEqual((pv["layer"], pv["shared"], pv["line"], pv["old_value"], pv["new_value"]),
                         ("local", False, 2, None, "high"))
        self.assertEqual(pv["base_file"], api_edit._base_file(world.ctx, None))
        self.assertNotEqual(pv["base_file"], api_edit._hmac(world.ctx, b""))
        lines = [line for hunk in pv["diff"]["hunks"] for line in hunk["lines"]]
        self.assertEqual([(l["kind"], l["old_line"], l["new_line"], l["text"]) for l in lines],
                         [("add", None, 1, "{"), ("add", None, 2, '  "effortLevel": "high"'),
                          ("add", None, 3, "}")])
        self.assertEqual(pv["diff"]["file_display"], "project/.claude/settings.local.json")
        self.assertIs(pv["ledger_damaged"], False)
        self.assertFalse(os.path.exists(os.path.join(world.proj, ".claude")), "a preview writes nothing")

    def test_a_preview_with_the_folder_there_does_not_create_it(self):
        world = World(self, user={"model": SONNET})
        _target, pv = self.local_create(world)
        self.assertEqual((pv["new_file"], pv["creates_dir"]), (True, False))

    def test_a_save_makes_the_file_and_the_folder(self):
        world = World(self, user={"model": SONNET})
        shutil.rmtree(os.path.join(world.proj, ".claude"))
        target, pv = self.local_create(world)
        status, body = world.save(pv, target, "high")
        self.assertEqual(status, 200, body)
        self.assertEqual(world.read("local"), json_edit.new_file(("effortLevel",), "high"))
        self.assertEqual(os.stat(world.path("local")).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(os.path.join(world.proj, ".claude")).st_mode & 0o777, 0o700)
        edit = body["edit"]
        self.assertEqual((edit["kind"], edit["op"], edit["layer"], edit["new_value"], edit["backup_display"]),
                         ("edit", "create", "local", "high", None))
        self.assertNotIn("old_value", edit)
        self.assertEqual(main_effort(body["settings"])["value"], "high")
        row = world.history()["rows"][0]
        self.assertEqual({k: row[k] for k in ("id", "kind", "op", "layer", "new_value", "backup_display")},
                         {k: edit[k] for k in ("id", "kind", "op", "layer", "new_value", "backup_display")})
        self.assertNotIn("old_value", row)
        self.assertIs(row["undoable"], True)

    def test_a_save_into_an_existing_folder_leaves_the_folder_mode_alone(self):
        world = World(self, user={"model": SONNET})
        mode = os.stat(os.path.join(world.proj, ".claude")).st_mode & 0o777
        target, pv = self.local_create(world)
        status, body = world.save(pv, target, "high")
        self.assertEqual(status, 200, body)
        self.assertEqual(os.stat(os.path.join(world.proj, ".claude")).st_mode & 0o777, mode)
        self.assertEqual(os.stat(world.path("local")).st_mode & 0o777, 0o600)

    def test_undo_removes_the_file_and_the_folder_this_save_made(self):
        world = World(self, user={"model": SONNET})
        shutil.rmtree(os.path.join(world.proj, ".claude"))
        before = helpers.tree_snapshot(world.proj)
        target, pv = self.local_create(world)
        status, saved = world.save(pv, target, "high")
        self.assertEqual(status, 200, saved)
        status, body = world.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, body)
        self.assertEqual((body["removed_file"], body["removed_dir"]), (True, True))
        self.assertEqual(helpers.tree_snapshot(world.proj), before)
        self.assertEqual(body["edit"]["kind"], "undo")
        self.assertEqual(main_effort(body["settings"])["layer"], "default")

    def test_undo_keeps_a_folder_that_was_already_there(self):
        world = World(self, user={"model": SONNET})
        before = helpers.tree_snapshot(world.proj)
        target, pv = self.local_create(world)
        status, saved = world.save(pv, target, "high")
        self.assertEqual(status, 200, saved)
        status, body = world.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, body)
        self.assertEqual((body["removed_file"], body["removed_dir"]), (True, False))
        self.assertEqual(helpers.tree_snapshot(world.proj), before)
        self.assertTrue(os.path.isdir(os.path.join(world.proj, ".claude")))

    def test_undo_keeps_a_made_folder_that_holds_another_file(self):
        world = World(self, user={"model": SONNET})
        shutil.rmtree(os.path.join(world.proj, ".claude"))
        target, pv = self.local_create(world)
        status, saved = world.save(pv, target, "high")
        self.assertEqual(status, 200, saved)
        stray = os.path.join(world.proj, ".claude", "notes.txt")
        world.put(stray, "keep me")
        status, body = world.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, body)
        self.assertEqual((body["removed_file"], body["removed_dir"]), (True, False))
        self.assertFalse(os.path.exists(world.path("local")))
        with open(stray) as fh:
            self.assertEqual(fh.read(), "keep me")

    def test_a_nested_create_on_a_user_file_for_opus(self):
        world = World(self, project={"model": OPUS})  # no user file, no local file
        body = world.targets()
        self.assertEqual(body["model"], OPUS)
        nested = add_of(body, "user", MODEL_REF % OPUS)
        self.assertEqual(nested["op"], "create")
        today = body["runs_as"]
        level = [l for l in LEVELS if l != today][0]
        row = level_of(body, level)
        user = file_of(row, "user")
        self.assertEqual((user["op"], user["target"], user["effect"], user["pickable"]),
                         ("create", nested["target"], "applies", True))
        status, pv = world.preview(nested["target"], level)
        self.assertEqual(status, 200, pv)
        self.assertEqual((pv["op"], pv["new_file"], pv["creates_dir"]), ("create", True, False))
        status, saved = world.save(pv, nested["target"], level)
        self.assertEqual(status, 200, saved)
        self.assertEqual(world.read("user"), json_edit.new_file(("modelSettings", OPUS, "effortLevel"), level))
        self.assertEqual(saved["edit"]["key_path"], ["modelSettings", OPUS, "effortLevel"])
        self.assertEqual(world.targets()["runs_as"], level)
        status, undone = world.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, undone)
        self.assertEqual((undone["removed_file"], undone["removed_dir"]), (True, False))
        self.assertFalse(os.path.exists(world.path("user")))
        self.assertTrue(os.path.isdir(world.cfg))
        self.assertEqual(world.targets()["runs_as"], today)

    def test_undo_is_refused_when_the_created_file_was_edited_by_hand(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)
        status, saved = world.save(pv, target, "high")
        self.assertEqual(status, 200, saved)
        world.write("local", {"effortLevel": "high", "by_hand": True})
        kept = world.read("local")
        self.assertEqual(world.undo(saved["edit"]["id"]),
                         (409, {"error": "changed_since_save", "backup_display": None}))
        self.assertEqual(world.read("local"), kept)
        row = world.history()["rows"][0]
        self.assertEqual((row["undoable"], row["not_undoable_reason"]), (False, "changed_since_save"))

    # stale

    def test_a_file_that_appears_after_a_create_preview_is_stale_file_appeared(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)
        world.write("local", {"language": "en"})
        other = world.read("local")
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "file_appeared"))
        self.assertEqual(body["changed_files"], [{"layer": "local", "file_display": "project/.claude/settings.local.json"}])
        self.assertEqual((body["preview"]["target"], body["preview"]["op"], body["preview"]["new_file"]),
                         (target, "insert", False))
        self.assertEqual(world.read("local"), other)
        self.assertEqual(world.history()["rows"], [])

    def test_a_file_that_goes_after_an_insert_preview_is_stale_file_removed(self):
        world = World(self, user={"model": SONNET}, local={"language": "en"})
        target = add_of(world.targets(), "local", TOP)["target"]
        status, pv = world.preview(target, "high")
        self.assertEqual((status, pv["op"]), (200, "insert"))
        os.remove(world.path("local"))
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "file_removed"))
        self.assertEqual((body["preview"]["target"], body["preview"]["op"]), (target, "create"))
        self.assertFalse(os.path.exists(world.path("local")))

    def test_a_file_that_goes_after_a_replace_preview_is_stale_file_removed(self):
        world = World(self, user={"model": SONNET}, local={"effortLevel": "low"})
        target = target_of(world.targets(), "local")["target"]
        status, pv = world.preview(target, "high")
        self.assertEqual((status, pv["op"]), (200, "replace"))
        os.remove(world.path("local"))
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "file_removed"))
        self.assertEqual((body["preview"]["target"], body["preview"]["op"]), (target, "create"))
        self.assertFalse(os.path.exists(world.path("local")))
        # The fresh preview saves.
        status, saved = world.save(body["preview"], target, "high")
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved["edit"]["op"], "create")

    def test_a_file_that_changes_after_a_replace_preview_stays_stale_file(self):
        world = World(self, user={"model": SONNET}, local={"effortLevel": "low"})
        target = target_of(world.targets(), "local")["target"]
        status, pv = world.preview(target, "high")
        world.write("local", {"effortLevel": "medium"})
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["changed"]), (409, "file"))

    def test_the_store_reports_a_file_that_appears_just_before_the_rename(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)
        self.at(world, "before_recheck", lambda: world.write("local", {"language": "en"}))
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "file_appeared"))
        self.assertEqual(body["changed_files"], [{"layer": "local", "file_display": "project/.claude/settings.local.json"}])
        self.assertEqual((body["preview"]["target"], body["preview"]["op"]), (target, "insert"))
        self.assertEqual(json.loads(world.read("local")), {"language": "en"})
        self.assertEqual(world.history()["rows"], [])

    def test_another_file_that_changed_is_still_a_trail_change_on_a_create(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)
        world.write("user", {"model": SONNET, "alwaysThinkingEnabled": True})
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "trail"))
        self.assertEqual(body["changed_files"], [{"layer": "user", "file_display": "config/settings.json"}])
        self.assertEqual((body["preview"]["op"], body["preview"]["new_file"]), ("create", True))
        self.assertFalse(os.path.exists(world.path("local")))

    # folders that went

    def test_a_project_folder_that_goes_between_preview_and_save_is_file_missing(self):
        world = World(self, user={"model": SONNET}, listed=[{"name": "Elsewhere", "path": "{root}/elsewhere"}])
        folder = os.path.join(world.root, "elsewhere")
        os.makedirs(os.path.join(folder, ".claude"))
        world.key = "elsewhere"
        target, pv = self.local_create(world)
        shutil.rmtree(folder)
        before = world.snapshot()
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body), (422, {"error": "file_missing"}))
        self.assertEqual(world.preview(target, "high"), (422, {"error": "file_missing"}))
        self.assertFalse(os.path.exists(folder))
        self.assertEqual(world.snapshot(), before)

    def test_a_config_folder_that_goes_is_file_missing_and_is_not_made_again(self):
        world = World(self, project={"model": SONNET})
        target = add_of(world.targets(), "user", 'claude-sonnet-5-5.effortLevel"]')["target"]
        status, pv = world.preview(target, "high")
        self.assertEqual((status, pv["op"]), (200, "create"))
        shutil.rmtree(world.cfg)
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body), (422, {"error": "file_missing"}))
        self.assertFalse(os.path.exists(world.cfg))
        self.assertEqual(world.preview(target, "high"), (422, {"error": "file_missing"}))

    # links and locks

    def test_a_dangling_link_at_the_file_is_locked_symlink(self):
        world = World(self, user={"model": SONNET})
        os.symlink(os.path.join(world.root, "nowhere.json"), world.path("local"))
        body = world.targets()
        row = file_of(body["files"], "local")
        self.assertEqual((row["state"], row["lock_reason"], row["target"]), ("locked", "symlink", None))
        self.assertEqual([a["layer"] for a in body["adds"] if a["layer"] == "local"], [])
        forced = api_edit._target_id("local", ("effortLevel",))
        status, answer = world.preview(forced, "high")
        self.assertIn(status, (400, 422))
        self.assertIn("error", answer)
        status, answer = world.save({"base_file": "x", "base_trail": "x", "base_others": {}}, forced, "high")
        self.assertIn(status, (400, 422))
        self.assertTrue(os.path.islink(world.path("local")))
        self.assertFalse(os.path.exists(world.path("local")))

    def test_a_dangling_link_at_the_claude_folder_is_locked_symlink(self):
        world = World(self, user={"model": SONNET})
        shutil.rmtree(os.path.join(world.proj, ".claude"))
        os.symlink(os.path.join(world.root, "nowhere"), os.path.join(world.proj, ".claude"))
        body = world.targets()
        for layer in ("local", "project"):
            row = file_of(body["files"], layer)
            self.assertEqual((row["state"], row["lock_reason"], row["target"]), ("locked", "symlink", None), layer)
        self.assertEqual({a["layer"] for a in body["adds"]}, {"user"})
        forced = api_edit._target_id("local", ("effortLevel",))
        status, answer = world.preview(forced, "high")
        self.assertIn(status, (400, 422))
        self.assertTrue(os.path.islink(os.path.join(world.proj, ".claude")))
        self.assertFalse(os.path.exists(os.path.join(world.proj, ".claude")))

    def test_a_repo_lock_locks_the_absent_rows_and_offers_no_adds(self):
        world = World(self, user={"model": SONNET})
        lock_repo(self, world)
        body = world.targets()
        self.assertEqual(body["adds"], [])
        self.assertEqual([(f["layer"], f["state"], f["lock_reason"], f["target"]) for f in body["files"]],
                         [("local", "absent", "not_repo_root", None), ("project", "absent", "not_repo_root", None),
                          ("user", "no_line", "not_repo_root", None)])
        self.assertIs(body["saveable"], False)

    # failures

    def test_a_failed_read_back_of_a_create_carries_the_edit_with_its_op(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)

        def fail():
            raise OSError(5, "io error")
        self.at(world, "reread", fail)
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"], body["stage"]), (500, "unverified", "reread"))
        self.assertEqual((body["edit"]["op"], body["edit"]["kind"], body["edit"]["backup_display"]),
                         ("create", "edit", None))
        self.assertIsNone(body["backup_display"])
        self.assertTrue(os.path.exists(world.path("local")))

    def test_a_writer_after_the_rename_of_a_create_is_raced_with_the_op(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)
        self.at(world, "after_rename", lambda: world.write("local", {"effortLevel": "xhigh"}))
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"], body["edit"]["op"]), (409, "raced", "create"))
        self.assertIsNone(body["backup_display"])
        self.assertIs(body["edit"]["undoable"], False)

    def test_the_undo_of_a_create_is_raced_when_a_file_is_put_back(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)
        status, saved = world.save(pv, target, "high")
        self.assertEqual(status, 200, saved)
        self.at(world, "after_unlink", lambda: world.write("local", {"language": "en"}))
        status, body = world.undo(saved["edit"]["id"])
        self.assertEqual((status, body["error"], body["matches_backup"]), (409, "raced", False))
        self.assertEqual(body["edit"]["kind"], "undo")
        self.assertEqual(json.loads(world.read("local")), {"language": "en"})

    def test_the_undo_of_a_create_is_unverified_when_the_read_back_fails(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)
        status, saved = world.save(pv, target, "high")
        self.assertEqual(status, 200, saved)

        def fail():
            raise OSError(5, "io error")
        self.at(world, "reread", fail)
        status, body = world.undo(saved["edit"]["id"])
        self.assertEqual((status, body["error"], body["stage"]), (500, "unverified", "reread"))
        self.assertEqual(body["edit"]["kind"], "undo")
        self.assertFalse(os.path.exists(world.path("local")))

    def test_write_failed_says_dir_left_when_the_made_folder_could_not_go(self):
        world = World(self, user={"model": SONNET})
        shutil.rmtree(os.path.join(world.proj, ".claude"))
        target, pv = self.local_create(world)

        def fail():
            world.put(os.path.join(world.proj, ".claude", "other.txt"), "x")
            raise edit_store.WriteFailed("no space")
        self.at(world, "after_mkdir", fail)
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body), (500, {"error": "write_failed", "file_unchanged": True, "dir_left": True}))
        self.assertTrue(os.path.isdir(os.path.join(world.proj, ".claude")))
        self.assertFalse(os.path.exists(world.path("local")))

    def test_write_failed_has_no_dir_left_key_when_the_made_folder_went(self):
        world = World(self, user={"model": SONNET})
        shutil.rmtree(os.path.join(world.proj, ".claude"))
        before = helpers.tree_snapshot(world.proj)
        target, pv = self.local_create(world)

        def fail():
            raise edit_store.WriteFailed("no space")
        self.at(world, "after_mkdir", fail)
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body), (500, {"error": "write_failed", "file_unchanged": True}))
        self.assertEqual(helpers.tree_snapshot(world.proj), before)

    def test_a_crash_after_the_ledger_leaves_the_row_absent_and_the_history_empty(self):
        world = World(self, user={"model": SONNET})
        target, pv = self.local_create(world)

        def crash():
            raise Crash("after_ledger")
        self.at(world, "after_ledger", crash)
        with self.assertRaises(Crash):
            world.save(pv, target, "high")
        world.store.seam = None
        body = world.targets()
        self.assertEqual(file_of(body["files"], "local")["state"], "absent")
        self.assertEqual(add_of(body, "local", TOP)["op"], "create")
        self.assertEqual(world.history()["rows"], [])
        self.assertFalse(os.path.exists(world.path("local")))
        # Saving again from a fresh preview works.
        status, fresh = world.preview(target, "high")
        self.assertEqual(status, 200, fresh)
        status, saved = world.save(fresh, target, "high")
        self.assertEqual(status, 200, saved)


# --------------------------------------------------------------------------
# Every fixture

class EveryFixture(Base):
    @classmethod
    def setUpClass(cls):
        cls.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-api-edit-fixtures-", dir=helpers._tmp_base()))
        cls.cases = {}
        for name in sorted(os.listdir(FIXTURE_DIR)):
            if not os.path.isdir(os.path.join(FIXTURE_DIR, name)):
                continue
            dest = os.path.join(cls.root, name)
            shutil.copytree(os.path.join(FIXTURE_DIR, name), dest)
            ctx = server.fixture_context(dest, None, None, RULES, FIELDS)
            store = edit_store.Store(ctx.config_dir, fixed_now=FIXED)
            cls.cases[name] = dataclasses.replace(ctx, edit=api_edit.EditState(TOKEN, "launch-test", store))
        cls.before = helpers.tree_snapshot(cls.root)

    @classmethod
    def tearDownClass(cls):
        helpers.rmtree_force(cls.root)

    def answer(self, ctx):
        status, body = api_edit.targets(ctx, {})
        self.assertEqual(status, 200, body)
        return body

    def plain_entries(self, ctx):
        listing = projects.load(ctx)
        return api_settings.answer(ctx, listing, listing.find(listing.current))["entries"]

    def test_the_copy_matches_the_fixtures_and_there_are_many(self):
        self.assertGreater(len(self.cases), 60)
        self.assertFalse(self.root.startswith(helpers.REPO))

    def test_each_effort_entry_matches_exactly_one_target_or_blocked_row(self):
        for name, ctx in self.cases.items():
            body = self.answer(ctx)
            entries = api_edit._effort_row(self.plain_entries(ctx))
            refs = [api_edit.ref_of(e) for e in entries]
            self.assertEqual(len(refs), len(set(refs)), name)
            rows = collections.Counter([t["ref"] for t in body["targets"]] + [b["ref"] for b in body["blocked"]])
            for ref in refs:
                self.assertEqual(rows[ref], 1, "%s %s" % (name, ref))
            self.assertEqual(sum(rows.values()), len(refs), name)

    def test_no_level_row_has_a_target_and_a_preselect_is_always_a_local_row(self):
        picked = project_only = 0
        for name, ctx in self.cases.items():
            body = self.answer(ctx)
            layers = {t["target"]: t["layer"] for t in body["targets"] + body["adds"]}
            self.assertEqual([f["layer"] for f in body["files"]],
                             ["local", "project", "user"] if body["files"] else [], name)
            for row in body["levels"]:
                self.assertNotIn("target", row, name)
                self.assertEqual(set(row), {"level", "result", "runs_as", "certain", "limits", "files",
                                            "preselect", "saveable"}, name)
                self.assertEqual(row["saveable"], any(f["pickable"] for f in row["files"]), name)
                if row["result"] == "now":
                    self.assertEqual((row["files"], row["preselect"], row["saveable"]), ([], None, False), name)
                    continue
                self.assertEqual([f["layer"] for f in row["files"]], [f["layer"] for f in body["files"]], name)
                for f in row["files"]:
                    if f["target"] is not None:
                        self.assertEqual(layers[f["target"]], f["layer"], name)
                    self.assertEqual(f["pickable"], f["lock_reason"] is None
                                     and f["effect"] in ("applies", "lowered", "unknown"), name)
                if row["preselect"] is None:
                    if any(f["layer"] != "local" and f["pickable"] for f in row["files"]):
                        project_only += 1
                else:
                    picked += 1
                    self.assertEqual(layers[row["preselect"]], "local", name)
                    local = file_of(row, "local")
                    self.assertEqual((local["target"], local["effect"], local["pickable"]),
                                     (row["preselect"], "applies", True), name)
                    for f in row["files"]:
                        if f["layer"] != "local":
                            self.assertNotEqual(f["target"], row["preselect"], name)
            self.assertEqual(body["saveable"], any(r["saveable"] for r in body["levels"]), name)
        self.assertGreater(picked, 0)
        self.assertGreater(project_only, 0)

    def test_reachable_levels_preview_to_that_result_and_stopped_levels_list_every_cap(self):
        reached = stopped = 0
        for name, ctx in self.cases.items():
            body = self.answer(ctx)
            entries = self.plain_entries(ctx)
            ids = {t["target"]: t for t in body["targets"] + body["adds"]}
            if body["levels_state"] == "no_effort_support":
                self.assertEqual(body["levels"], [], name)
            else:
                self.assertEqual([r["level"] for r in body["levels"]], list(LEVELS), name)
            for row in body["levels"]:
                self.assert_limits(row["limits"])
                level = row["level"]
                if row["result"] == "now":
                    self.assertEqual((row["runs_as"], body["runs_as"]), (level, level), name)
                elif row["result"] == "reachable":
                    reached += 1
                    applies = [f for f in row["files"] if f["effect"] == "applies"]
                    self.assertTrue(applies, name)
                    for item in applies:
                        self.assertIn(item["target"], ids, name)
                        status, pv = api_edit.preview(ctx, {"target": item["target"], "value": level})
                        self.assertEqual(status, 200, name)
                        winner = api_edit._winner(api_edit._effort_row(pv["after"]["entries"]))
                        self.assertEqual(api_edit.ref_of(winner), ids[item["target"]]["ref"], name)
                        self.assertEqual((winner["status"], winner["value"]), ("in_effect", level), name)
                        self.assertIsNone(pv["warning"], "%s %s" % (name, level))
                        self.assertEqual(item["runs_as"], level)
                    self.assertEqual(row["runs_as"], level)
                else:
                    stopped += 1
                    self.assertEqual(row["result"], "stopped", name)
                    expected = sorted(
                        (e.get("file"), e["value"]) for e in entries
                        if e["key"] == "maxEffortLevel" and e.get("scope") == "main" and not e.get("agent")
                        and isinstance(e["value"], str) and e["value"] in api_edit.RANKS and e["value"] != "max"
                        and api_edit.RANKS.index(e["value"]) < api_edit.RANKS.index(level)
                        and e["status"] != "invalid"
                        and "max-effort-level-replaced-in-file" not in (e.get("rule_ids") or []))
                    got = sorted((l["file_display"], l["value"]) for l in row["limits"] if l["kind"] == "cap")
                    self.assertEqual(got, expected, "%s %s" % (name, level))
                    self.assertNotIn("max", [l["value"] for l in row["limits"] if l["kind"] == "cap"], name)
            if body["levels_state"] == "no_effort_support":
                for target in ids:
                    self.assertEqual(api_edit.preview(ctx, {"target": target, "value": "low"}),
                                     (400, {"error": "not_editable"}), name)
        self.assertGreater(reached, 10)
        self.assertGreater(stopped, 5)

    def test_every_preview_and_every_answer_wrote_nothing(self):
        for ctx in self.cases.values():
            self.answer(ctx)
        self.assertEqual(helpers.tree_snapshot(self.root), self.before)


# --------------------------------------------------------------------------
# Remove: action "remove" on preview and save (T13)

def remove_body(world, target, **extra):
    out = {"project": world.key, "target": target, "action": "remove"}
    out.update(extra)
    return out


def remove_preview(world, target, **extra):
    return api_edit.preview(world.ctx, remove_body(world, target, **extra))


def remove_save(world, pv, target, **extra):
    return api_edit.save(world.ctx, remove_body(
        world, target, base_file=pv["base_file"], base_trail=pv["base_trail"], base_others=pv["base_others"],
        **extra))


def plain_dumps(obj):
    return json.dumps(obj, indent=2) + "\n"


class ForgedRows(Base):
    """A preview or save for a row the file list marks not pickable is refused, and nothing is written."""

    def refused(self, world, layer, value, ends=None):
        """Assert the row is listed not pickable, then force a preview and a save for it. Returns the target."""
        body = world.targets()
        if ends is None:
            self.assertIs(file_of(level_of(body, value), layer)["pickable"], False)
        # An add can sit beside a pickable one in its file: the file's row takes the other, and this one is forced.
        target = (add_of(body, layer, ends) if ends else target_of(body, layer))["target"]
        before = self.files(world)
        self.assertEqual(world.preview(target, value), (400, {"error": "not_editable"}))
        # a save with the hashes of a real payload, so only the pickable check stands in the way
        pv = inner_preview(world, target, value)
        self.assertEqual(world.save(pv, target, value), (400, {"error": "not_editable"}))
        self.assertEqual(self.files(world), before)
        self.assertEqual(world.history()["rows"], [])
        return target

    @staticmethod
    def files(world):
        return {k: v for k, v in world.snapshot().items() if not k.startswith("config/routing-dashboard")}

    def test_a_line_that_a_higher_layer_overrides_is_refused_in_preview_and_save(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"}, local={"effortLevel": "medium"})
        self.refused(world, "project", "high")

    def test_an_add_that_would_not_apply_is_refused_in_preview_and_save(self):
        # Sonnet reads no top-level line in the user file, so that add changes nothing.
        world = World(self, user={"model": SONNET})
        self.refused(world, "user", "high", ends=TOP)

    def test_a_save_is_refused_inside_the_plan_when_the_row_stops_being_pickable(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        target = target_of(world.targets(), "project")["target"]
        status, pv = world.preview(target, "high")
        self.assertEqual(status, 200, pv)
        world.write("local", {"effortLevel": "medium"})  # a higher layer now wins, so the row can't take it
        before = self.files(world)
        status, body = world.save(pv, target, "high")
        self.assertEqual((status, body), (400, {"error": "not_editable"}))
        self.assertEqual(self.files(world), before)

    def test_a_pickable_row_still_previews_and_saves(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"}, local={"effortLevel": "medium"})
        body = world.targets()
        self.assertIs(file_of(level_of(body, "high"), "local")["pickable"], True)
        saved = world.edit(target_of(body, "local")["target"], "high")["edit"]
        self.assertEqual(saved["new_value"], "high")

    def test_a_remove_of_a_line_that_would_not_apply_still_goes_through(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"}, local={"effortLevel": "medium"})
        target = target_of(world.targets(), "project")["target"]
        status, pv = remove_preview(world, target)
        self.assertEqual(status, 200, pv)
        status, saved = remove_save(world, pv, target)
        self.assertEqual(status, 200, saved)
        self.assertEqual(json.loads(world.read("project")), {})


class Removes(Base):
    def test_a_remove_with_no_level_known_is_never_called_no_effect(self):
        world = World(self, user={"effortLevel": "high"}, project="{ not json", local="{ not json")
        body = world.targets()
        self.assertEqual((body["levels_state"], body["runs_as"]), ("model_unknown", None))
        entry = target_of(body, "user")
        self.assertIsNone(entry["remove"]["runs_as"])
        self.assertFalse(entry["remove"]["no_effect"])
        status, pv = remove_preview(world, entry["target"])
        self.assertEqual(200, status, pv)
        self.assertEqual((pv["runs_before"], pv["runs_after"], pv["no_effect"]), (None, None, False))

    def world(self, **kwargs):
        defaults = {"user": {"model": SONNET}, "project": {"effortLevel": "low"},
                    "local": {"effortLevel": "high", "language": "en"}}
        defaults.update(kwargs)
        return World(self, **defaults)

    def line(self, world, layer="local", ends=None):
        return target_of(world.targets(), layer, ends)["target"]

    def copy_of(self, world, layer):
        copy = os.path.join(world.root, "copy-of-" + layer)
        shutil.copyfile(world.path(layer), copy)
        return copy

    def ledger_files(self, world):
        """Backups and ledgers in the store. A save opens the store folder under its lock, so a .lock is no write."""
        return [f for _d, _s, files in os.walk(os.path.join(world.cfg, edit_store.STORE_DIR)) for f in files
                if f.endswith((".bak", ".json"))]

    def settings(self, world):
        """The bytes of every settings file in the world, to show a refused request wrote nothing."""
        return {layer: world.read(layer) for layer in ("user", "project", "local") if os.path.lexists(world.path(layer))}

    def raced(self, change):
        """Run change after a save's first view and before its locked recheck, as a second writer would."""
        real = api_edit._editable_view

        def late(ctx, listing, project, target_id):
            found = real(ctx, listing, project, target_id)
            change()
            return found
        return mock.patch.object(api_edit, "_editable_view", late)

    # the winning line

    def test_targets_say_what_runs_after_a_removal(self):
        world = self.world()
        body = world.targets()
        local = target_of(body, "local")
        project = target_of(body, "project")
        self.assertEqual(body["runs_as"], "high")
        self.assertEqual(local["remove"], {"runs_as": "low", "no_effect": False, "lock_reason": None})
        self.assertEqual(project["remove"], {"runs_as": "high", "no_effect": True, "lock_reason": None})

    def test_removing_the_winning_line_previews_saves_and_undoes(self):
        world = self.world()
        target = self.line(world)
        original = world.read("local")
        copy = self.copy_of(world, "local")
        status, pv = remove_preview(world, target)
        self.assertEqual(status, 200, pv)
        self.assertEqual((pv["op"], pv["new_value"], pv["old_value"], pv["warning"], pv["no_effect"],
                          pv["last_line"], pv["no_change"]), ("remove", None, "high", None, False, False, False))
        self.assertEqual((pv["runs_before"], pv["runs_after"], pv["line"]), ("high", "low", 2))
        lines = [(l["kind"], l["text"]) for h in pv["diff"]["hunks"] for l in h["lines"] if l["kind"] != "context"]
        self.assertEqual(lines, [("del", '  "effortLevel": "high",')])
        self.assertEqual(world.read("local"), original)  # a preview writes nothing
        status, saved = remove_save(world, pv, target)
        self.assertEqual(status, 200, saved)
        self.assertEqual(world.read("local"), json_edit.remove_key(original, ("effortLevel",)))
        edit = saved["edit"]
        self.assertEqual((edit["op"], edit["old_value"], edit["key_path"]), ("remove", "high", ["effortLevel"]))
        self.assertNotIn("new_value", edit)
        self.assertEqual(world.history()["rows"][0]["op"], "remove")
        self.assertNotIn("new_value", world.history()["rows"][0])
        status, undone = world.undo(edit["id"])
        self.assertEqual(status, 200, undone)
        self.assertTrue(filecmp.cmp(world.path("local"), copy, shallow=False))
        self.assertEqual(undone["edit"]["op"], "remove")
        self.assertEqual(undone["edit"]["kind"], "undo")
        self.assertIs(undone["matches_backup"], True)

    def test_a_line_that_does_not_win_is_no_effect(self):
        world = self.world()
        project = self.line(world, "project")
        status, pv = remove_preview(world, project)
        self.assertEqual((status, pv["no_effect"], pv["runs_before"], pv["runs_after"]), (200, True, "high", "high"))

    def test_a_set_preview_says_no_effect_and_last_line_false(self):
        world = self.world()
        status, pv = world.preview(self.line(world), "xhigh")
        self.assertEqual((status, pv["no_effect"], pv["last_line"]), (200, False, False))

    def test_an_explicit_set_action_is_a_set(self):
        world = self.world()
        status, pv = world.preview(self.line(world), "xhigh", action="set")
        self.assertEqual((status, pv["op"], pv["new_value"]), (200, "replace", "xhigh"))

    def test_the_files_last_line_leaves_the_file_with_its_braces(self):
        world = self.world(local=None)
        target = self.line(world, "project")
        status, pv = remove_preview(world, target)
        self.assertEqual((status, pv["last_line"], pv["no_effect"]), (200, True, False))
        status, saved = remove_save(world, pv, target)
        self.assertEqual(status, 200, saved)
        self.assertEqual(world.read("project"), b"{\n}\n")
        self.assertEqual(json.loads(world.read("project")), {})
        bare = World(self, user={"model": SONNET})
        self.assertEqual(pv["runs_after"], bare.targets()["runs_as"])
        self.assertNotEqual(pv["runs_after"], "low")
        self.assertEqual(world.targets()["runs_as"], bare.targets()["runs_as"])

    def test_a_nested_line_leaves_an_empty_object_and_is_not_the_last_line(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}})
        target = self.line(world, "user", "claude-opus-5-5.effortLevel")
        status, pv = remove_preview(world, target)
        self.assertEqual((status, pv["op"], pv["last_line"]), (200, "remove", False))
        status, saved = remove_save(world, pv, target)
        self.assertEqual(status, 200, saved)
        self.assertEqual(json.loads(world.read("user")), {"model": OPUS, "modelSettings": {OPUS: {}}})
        self.assertEqual(saved["edit"]["key_path"], ["modelSettings", OPUS, "effortLevel"])

    # repeated keys

    def test_a_repeated_key_cannot_be_removed(self):
        repeated = b'{\n  "effortLevel": "low",\n  "effortLevel": "high"\n}\n'
        world = self.world(local=repeated)
        body = world.targets()
        local = target_of(body, "local")
        self.assertEqual(local["remove"], {"runs_as": None, "no_effect": False, "lock_reason": "repeated_key"})
        target = local["target"]
        status, other = world.preview(target, "medium")
        self.assertEqual(status, 200, other)
        before = self.settings(world)
        self.assertEqual(remove_preview(world, target), (422, {"error": "repeated_key"}))
        self.assertEqual(remove_save(world, other, target), (422, {"error": "repeated_key"}))
        self.assertEqual(self.settings(world), before)
        self.assertEqual(world.read("local"), repeated)
        self.assertEqual(self.ledger_files(world), [])

    # bad requests

    def test_an_add_cannot_be_removed(self):
        world = self.world(project={"language": "en"}, local=None)
        add = add_of(world.targets(), "project", TOP)["target"]
        status, pv = world.preview(add, "low")
        self.assertEqual(status, 200, pv)
        before = self.settings(world)
        self.assertEqual(remove_preview(world, add), (400, {"error": "not_editable"}))
        self.assertEqual(remove_save(world, pv, add), (400, {"error": "not_editable"}))
        self.assertEqual(self.settings(world), before)
        self.assertEqual(self.ledger_files(world), [])

    def test_a_bad_action_is_a_bad_request(self):
        world = self.world()
        target = self.line(world)
        status, pv = world.preview(target, "xhigh")
        for bad in ("delete", "", "REMOVE", None, 5, ["remove"], {"a": 1}):
            with self.subTest(action=bad):
                self.assertEqual(api_edit.preview(world.ctx, world.body(target, "xhigh", action=bad)),
                                 (400, {"error": "bad_request"}))
                self.assertEqual(world.save(pv, target, "xhigh", action=bad), (400, {"error": "bad_request"}))
        self.assertEqual(world.read("local"), plain_dumps({"effortLevel": "high", "language": "en"}).encode())

    def test_a_remove_with_a_value_is_a_bad_request(self):
        world = self.world()
        target = self.line(world)
        status, pv = remove_preview(world, target)
        for value in ("low", None, "", 3):
            with self.subTest(value=value):
                self.assertEqual(remove_preview(world, target, value=value), (400, {"error": "bad_request"}))
                self.assertEqual(remove_save(world, pv, target, value=value), (400, {"error": "bad_request"}))
        self.assertEqual(self.ledger_files(world), [])

    def test_a_set_without_a_value_is_still_bad_value(self):
        world = self.world()
        target = self.line(world)
        body = {"project": world.key, "target": target}
        self.assertEqual(api_edit.preview(world.ctx, body), (400, {"error": "bad_value"}))
        self.assertEqual(api_edit.preview(world.ctx, dict(body, action="set")), (400, {"error": "bad_value"}))
        self.assertEqual(api_edit.preview(world.ctx, dict(body, value="max")), (400, {"error": "bad_value"}))

    def test_no_path_or_key_field_changes_what_a_remove_touches(self):
        world = self.world()
        target = self.line(world)
        status, pv = remove_preview(world, target, key_path=["language"], path="x", key="language")
        self.assertEqual((status, pv["target"], pv["old_value"]), (200, target, "high"))

    # blocked

    def test_a_file_that_became_a_symlink_answers_with_its_reason(self):
        world = self.world()
        target = self.line(world)
        status, pv = remove_preview(world, target)
        real = os.path.join(world.root, "elsewhere.json")
        os.replace(world.path("local"), real)
        os.symlink(real, world.path("local"))
        before = self.settings(world)
        self.assertEqual(remove_preview(world, target), (422, {"error": "symlink"}))
        self.assertEqual(remove_save(world, pv, target), (422, {"error": "symlink"}))
        self.assertEqual(self.settings(world), before)
        self.assertEqual(self.ledger_files(world), [])

    def test_a_repo_locked_project_answers_not_repo_root(self):
        world = self.world()
        target = self.line(world)
        status, pv = remove_preview(world, target)
        lock_repo(self, world)
        before = self.settings(world)
        self.assertEqual(remove_preview(world, target), (422, {"error": "not_repo_root"}))
        self.assertEqual(remove_save(world, pv, target), (422, {"error": "not_repo_root"}))
        self.assertEqual(self.settings(world), before)
        self.assertEqual(self.ledger_files(world), [])

    # stale

    def test_a_file_edited_with_the_line_kept_is_stale_with_a_fresh_remove_preview(self):
        world = self.world()
        target = self.line(world)
        status, pv = remove_preview(world, target)
        moved = plain_dumps({"effortLevel": "high", "language": "en", "added": True}).encode()
        world.write("local", moved)
        status, body = remove_save(world, pv, target)
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "file"))
        self.assertEqual(body["changed_files"], [{"layer": "local", "file_display": "project/.claude/settings.local.json"}])
        fresh = body["preview"]
        self.assertEqual((fresh["target"], fresh["op"], fresh["new_value"], fresh["old_value"]),
                         (target, "remove", None, "high"))
        self.assertEqual(fresh["base_file"], api_edit._hmac(world.ctx, moved))
        self.assertEqual(world.read("local"), moved)
        self.assertEqual(self.ledger_files(world), [])
        # The fresh preview saves.
        status, saved = remove_save(world, fresh, target)
        self.assertEqual(status, 200, saved)
        self.assertEqual(json.loads(world.read("local")), {"language": "en", "added": True})

    def test_a_line_deleted_before_the_request_is_not_editable(self):
        world = self.world()
        target = self.line(world)
        status, pv = remove_preview(world, target)
        gone = plain_dumps({"language": "en"}).encode()
        world.write("local", gone)
        self.assertEqual(remove_preview(world, target), (400, {"error": "not_editable"}))
        self.assertEqual(remove_save(world, pv, target), (400, {"error": "not_editable"}))
        self.assertEqual(world.read("local"), gone)

    def test_a_line_deleted_by_hand_during_the_save_is_stale_with_no_preview(self):
        world = self.world()
        target = self.line(world)
        status, pv = remove_preview(world, target)
        gone = plain_dumps({"language": "en"}).encode()
        with self.raced(lambda: world.write("local", gone)):
            status, body = remove_save(world, pv, target)
        self.assertEqual((status, body["error"], body["changed"], body["preview"]), (409, "stale", "file", None))
        self.assertEqual(body["changed_files"], [{"layer": "local", "file_display": "project/.claude/settings.local.json"}])
        self.assertEqual(world.read("local"), gone)
        self.assertEqual(self.ledger_files(world), [])

    def test_a_file_deleted_during_the_save_is_stale_file_removed(self):
        world = self.world()
        target = self.line(world)
        status, pv = remove_preview(world, target)
        with self.raced(lambda: os.remove(world.path("local"))):
            status, body = remove_save(world, pv, target)
        self.assertEqual((status, body["error"], body["changed"], body["preview"]), (409, "stale", "file_removed", None))
        self.assertEqual(body["changed_files"], [{"layer": "local", "file_display": "project/.claude/settings.local.json"}])
        self.assertFalse(os.path.exists(world.path("local")))
        self.assertEqual(self.ledger_files(world), [])

    def alias_world(self):
        return World(self, user={"model": OPUS, "modelSettings": {"opus": {"effortLevel": "low"}}})

    def test_a_file_that_goes_with_its_alias_target_is_file_removed_for_a_set(self):
        # The alias name is not offered for a create, so the fresh view cannot find the target at all.
        world = self.alias_world()
        target = self.line(world, "user", ".opus.effortLevel")
        status, pv = world.preview(target, "high")
        self.assertEqual(status, 200, pv)
        with self.raced(lambda: os.remove(world.path("user"))):
            status, body = world.save(pv, target, "high")
        self.assertEqual((status, body["error"], body["changed"], body["preview"]), (409, "stale", "file_removed", None))
        self.assertEqual(body["changed_files"], [{"layer": "user", "file_display": "config/settings.json"}])
        self.assertFalse(os.path.exists(world.path("user")))

    def test_a_file_that_goes_with_its_alias_target_is_file_removed_for_a_remove(self):
        world = self.alias_world()
        target = self.line(world, "user", ".opus.effortLevel")
        status, pv = remove_preview(world, target)
        self.assertEqual(status, 200, pv)
        with self.raced(lambda: os.remove(world.path("user"))):
            status, body = remove_save(world, pv, target)
        self.assertEqual((status, body["error"], body["changed"], body["preview"]), (409, "stale", "file_removed", None))
        self.assertEqual(body["changed_files"], [{"layer": "user", "file_display": "config/settings.json"}])
        self.assertFalse(os.path.exists(world.path("user")))

    def seam_remove(self, world, target, change):
        status, pv = remove_preview(world, target)
        self.assertEqual(status, 200, pv)

        def seam(seen):
            if seen == "before_recheck":
                change()
        world.store.seam = seam
        return remove_save(world, pv, target)

    def test_the_store_going_stale_hands_back_a_fresh_remove_preview(self):
        world = self.world()
        target = self.line(world)
        moved = plain_dumps({"effortLevel": "high", "language": "fr"}).encode()
        status, body = self.seam_remove(world, target, lambda: world.write("local", moved))
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "file"))
        fresh = body["preview"]
        self.assertEqual((fresh["op"], fresh["new_value"], fresh["target"]), ("remove", None, target))
        self.assertEqual(fresh["base_file"], api_edit._hmac(world.ctx, moved))
        self.assertEqual(world.read("local"), moved)

    def test_the_store_going_stale_after_the_line_went_hands_back_no_preview(self):
        world = self.world()
        target = self.line(world)
        status, body = self.seam_remove(world, target, lambda: world.write("local", {"language": "fr"}))
        self.assertEqual((status, body["error"], body["preview"]), (409, "stale", None))

    # read-only

    def test_the_read_only_answer_holds_no_remove_field(self):
        world = World(self, edit=False, user={"model": SONNET}, project={"effortLevel": "high"})
        self.assertNotIn("remove", json.dumps(world.targets()))

    def test_remove_with_edits_off_is_refused(self):
        world = World(self, edit=False, user={"model": SONNET}, project={"effortLevel": "high"})
        self.assertEqual(api_edit.preview(world.ctx, {"target": "t", "action": "remove"}),
                         (400, {"error": "not_editable"}))
        self.assertEqual(api_edit.save(world.ctx, {"target": "t", "action": "remove"}),
                         (400, {"error": "not_editable"}))

    # masking

    LAYOUTS = {
        "one line, secret before": b'{"apiKey": "%s", "effortLevel": "high"}\n',
        "one line, secret after": b'{"effortLevel": "high", "apiKey": "%s"}\n',
        "lines, secret before": b'{\n  "apiKey": "%s",\n  "effortLevel": "high"\n}\n',
        "lines, secret after": b'{\n  "effortLevel": "high",\n  "apiKey": "%s"\n}\n',
        "repeated secret key": b'{\n  "token": "%s",\n  "effortLevel": "high",\n  "token": "%s"\n}\n',
    }

    def test_a_removal_beside_a_secret_leaks_no_secret_byte(self):
        for label, template in sorted(self.LAYOUTS.items()):
            with self.subTest(label):
                secret = SECRET.encode()
                raw = template.replace(b"%s", secret)
                world = self.world(project=raw, local=None)
                target = self.line(world, "project")
                seen = [json.dumps(world.targets())]
                status, pv = remove_preview(world, target)
                self.assertEqual(status, 200, pv)
                seen.append(json.dumps(pv))
                status, saved = remove_save(world, pv, target)
                self.assertEqual(status, 200, saved)
                seen.append(json.dumps(saved))
                seen.append(json.dumps(world.history()))
                status, undone = world.undo(saved["edit"]["id"])
                self.assertEqual(status, 200, undone)
                seen.append(json.dumps(undone))
                seen.append(json.dumps(world.history()))
                self.assertEqual(world.read("project"), raw)
                for text in seen:
                    self.assertNotIn("sk-planted-", text)

    def test_the_old_value_of_a_secret_looking_effort_value_is_hidden(self):
        world = self.world(project=plain_dumps({"effortLevel": SECRET}), local=None)
        target = self.line(world, "project")
        seen = [json.dumps(world.targets())]
        status, pv = remove_preview(world, target)
        self.assertEqual(status, 200, pv)
        self.assertNotEqual(pv["old_value"], SECRET)
        seen.append(json.dumps(pv))
        status, saved = remove_save(world, pv, target)
        self.assertEqual(status, 200, saved)
        seen.append(json.dumps(saved))
        seen.append(json.dumps(world.history()))
        for text in seen:
            self.assertNotIn("sk-planted-", text)
        self.assertEqual(world.read("project"), b"{\n}\n")


# --------------------------------------------------------------------------
# One more look at the project value rules for the write routes with the edit flag off

class FlagOff(Base):
    def test_write_routes_answer_not_editable_without_the_flag(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"}, edit=False)
        for route, body in ((api_edit.preview, {"target": "t", "value": "low"}),
                            (api_edit.save, {"target": "t", "value": "low"}),
                            (api_edit.undo, {"edit": "x"})):
            self.assertEqual(route(world.ctx, body), (400, {"error": "not_editable"}))


class ReadOnlyTargets(Base):
    """With edits off, targets answers the read-only form: today's level, the level names and the file rows."""

    KEYS = {"enabled", "project", "state", "agent", "setting", "runs_as", "model", "levels_state",
            "project_lock", "files", "levels"}

    def world(self, **kwargs):
        return World(self, edit=False, **kwargs)

    def test_the_answer_holds_the_level_picker_and_the_file_rows_only(self):
        world = self.world(user={"model": SONNET}, project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual(set(body), self.KEYS)
        self.assertEqual((body["enabled"], body["project"], body["state"], body["agent"], body["setting"]),
                         (False, "project", "ok", "@main", "effortLevel"))
        self.assertEqual((body["runs_as"], body["model"], body["levels_state"], body["project_lock"]),
                         ("high", SONNET, "ok", None))
        self.assertEqual(body["levels"], [{"level": "low", "result": "offered"},
                                          {"level": "medium", "result": "offered"},
                                          {"level": "high", "result": "now"},
                                          {"level": "xhigh", "result": "offered"}])
        self.assertEqual([row["layer"] for row in body["files"]], ["local", "project", "user"])
        project = file_of(body["files"], "project")
        self.assertEqual((project["state"], project["line"], project["value"], project["shared"]),
                         ("has_line", 2, "high", True))
        self.assertEqual(project["file_display"], "project/.claude/settings.json")

    def test_it_holds_no_target_and_nothing_to_save(self):
        world = self.world(user={"model": SONNET, "effortLevel": "low"}, project={"effortLevel": "high"},
                           local={"effortLevel": "medium"})
        body = world.targets()
        text = json.dumps(body)
        self.assertNotRegex(text, r"\bt-[0-9a-f]{16}\b")
        for key in ("targets", "blocked", "preselect", "saveable", "target"):
            self.assertNotIn('"%s"' % key, text, key)
        for row in body["files"]:
            self.assertNotIn("target", row)
        for row in body["levels"]:
            self.assertEqual(set(row), {"level", "result"})
        self.assertEqual({row["state"] for row in body["files"]}, {"has_line"})

    def test_the_full_answer_still_has_its_target_ids(self):
        full = World(self, user={"model": SONNET}, project={"effortLevel": "high"}).targets()
        self.assertRegex(json.dumps(full), r"t-[0-9a-f]{16}")
        self.assertTrue(full["enabled"])
        self.assertTrue(all("target" in row for row in full["files"]))

    def test_the_resolver_runs_once(self):
        world = self.world(user={"model": SONNET}, project={"effortLevel": "high"})
        with mock.patch.object(api_settings, "resolved", wraps=api_settings.resolved) as resolved:
            status, _body = api_edit.targets(world.ctx, {"project": [world.key]})
        self.assertEqual(status, 200)
        self.assertEqual(resolved.call_count, 1)

    def test_a_planted_secret_never_reaches_the_answer(self):
        world = self.world(user={"model": SONNET, "env": {"ANTHROPIC_API_KEY": SECRET}},
                           project={"effortLevel": SECRET},
                           local={"apiKeyHelper": SECRET, "modelSettings": {"x": {"token": SECRET}}})
        body = world.targets()
        self.assertNotIn(SECRET, json.dumps(body))
        self.assertEqual(file_of(body["files"], "project")["value"], "hidden")

    def test_a_bad_project_answers_404_and_all_answers_400(self):
        world = self.world(user={"model": SONNET})
        self.assertEqual(api_edit.targets(world.ctx, {"project": ["no-such-project"]}),
                         (404, {"error": "unknown_project"}))
        self.assertEqual(api_edit.targets(world.ctx, {"project": ["all"]}), (400, {"error": "bad_request"}))
        self.assertEqual(api_edit.targets(world.ctx, {"project": ["a", "b"]}), (400, {"error": "bad_request"}))

    def test_a_model_without_effort_support_gives_no_levels(self):
        world = self.world(user={"model": "claude-haiku-4-5"}, project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual((body["levels_state"], body["levels"]), ("no_effort_support", []))
        self.assertEqual(file_of(body["files"], "project")["state"], "has_line")

    def test_a_missing_folder_gives_no_levels_and_no_files(self):
        world = self.world(user={"model": SONNET}, listed=[{"name": "Gone", "path": "{root}/no-such-folder"}])
        body = world.targets()
        self.assertEqual((body["state"], body["levels_state"], body["files"], body["levels"]),
                         ("missing_folder", "model_unknown", [], []))
        self.assertEqual((body["runs_as"], body["model"]), (None, None))

    def test_an_unknown_model_still_lists_the_levels(self):
        world = self.world(project={"effortLevel": "low"})
        body = world.targets()
        self.assertEqual(body["levels_state"], "model_unknown")
        self.assertEqual([row["level"] for row in body["levels"]], list(LEVELS))

    def test_a_repo_subfolder_sets_the_project_lock_and_locks_the_file_rows(self):
        for place in ("subfolder", "linked"):
            with self.subTest(place=place):
                world = self.world(user={"model": SONNET}, project={"effortLevel": "low"})
                world.place.stop()
                world.place = mock.patch.object(git_check, "repo_place", return_value=place)
                world.place.start()
                self.addCleanup(world.place.stop)
                body = world.targets()
                self.assertEqual(body["project_lock"], "not_repo_root")
                for row in body["files"]:
                    self.assertEqual(row["lock_reason"], "not_repo_root")
                    self.assertNotIn("target", row)

    def test_the_project_lock_matches_the_full_answer(self):
        for place in ("no_repo", "subfolder"):
            with self.subTest(place=place):
                on = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
                off = self.world(user={"model": SONNET}, project={"effortLevel": "low"})
                for world in (on, off):
                    world.place.stop()
                    world.place = mock.patch.object(git_check, "repo_place", return_value=place)
                    world.place.start()
                    self.addCleanup(world.place.stop)
                on_body, off_body = on.targets(), off.targets()
                self.assertEqual(on_body["project_lock"], off_body["project_lock"])
                self.assertEqual([{k: v for k, v in row.items() if k != "target"} for row in on_body["files"]],
                                 off_body["files"])

    def test_history_still_answers_enabled_false(self):
        world = self.world(user={"model": SONNET}, project={"effortLevel": "low"})
        self.assertEqual(api_edit.history(world.ctx, {}), (200, {"enabled": False}))
        self.assertEqual(api_edit.history(world.ctx, {"project": ["no-such-project"]}), (200, {"enabled": False}))

    def test_the_read_only_path_never_touches_the_edit_state(self):
        world = self.world(user={"model": SONNET}, project={"effortLevel": "low"})
        self.assertIsNone(world.ctx.edit)
        with mock.patch.object(api_edit, "_hmac", side_effect=AssertionError("hmac")):
            self.assertEqual(api_edit.targets(world.ctx, {})[0], 200)


class GitIgnore(unittest.TestCase):
    """Every local preview says whether git ignores the file. The call runs in the route, never under the lock."""

    def world(self, **files):
        world = World(self, **files)
        patcher = mock.patch.object(git_check, "ignore_state", return_value="not_ignored")
        self.state = patcher.start()
        self.addCleanup(patcher.stop)
        return world

    @staticmethod
    def level_row(world, layer, value):
        level = next(row for row in world.targets()["levels"] if row["level"] == value)
        return next(row for row in level["files"] if row["layer"] == layer)

    def test_a_local_preview_of_any_op_carries_the_result(self):
        world = self.world(local={"effortLevel": "low"})
        status, body = api_edit.preview(world.ctx, world.body(self.level_row(world, "local", "high")["target"], "high"))
        self.assertEqual(200, status)
        self.assertEqual("replace", body["op"])
        self.assertEqual("not_ignored", body["git_ignore"])
        self.state.assert_called_once_with(world.proj, world.ctx.path_env, world.ctx.home,
                                           world.ctx.shell_env.get("XDG_CONFIG_HOME"))

    def test_a_preview_of_a_file_that_does_not_exist_carries_it_too(self):
        world = self.world()
        row = self.level_row(world, "local", "high")
        self.assertEqual("create", row["op"])
        _status, body = api_edit.preview(world.ctx, world.body(row["target"], "high"))
        self.assertEqual("not_ignored", body["git_ignore"])

    def test_a_shared_file_never_runs_git(self):
        world = self.world(project={"effortLevel": "low"})
        row = self.level_row(world, "project", "high")
        _status, body = api_edit.preview(world.ctx, world.body(row["target"], "high"))
        self.assertIsNone(body["git_ignore"])
        self.state.assert_not_called()

    def test_a_save_never_runs_git_under_the_lock(self):
        world = self.world(local={"effortLevel": "low"})
        row = self.level_row(world, "local", "high")
        _status, preview = api_edit.preview(world.ctx, world.body(row["target"], "high"))
        self.state.reset_mock()
        status, _body = api_edit.save(world.ctx, world.save_body(preview, row["target"], "high"))
        self.assertEqual(200, status)
        self.state.assert_not_called()

    def test_a_stale_save_carries_the_result_on_the_fresh_preview_outside_the_lock(self):
        world = self.world(local={"effortLevel": "low"})
        row = self.level_row(world, "local", "high")
        _status, preview = api_edit.preview(world.ctx, world.body(row["target"], "high"))
        world.write("local", '{ "effortLevel": "medium" }\n')
        self.state.reset_mock()
        held = []
        self.state.side_effect = lambda *args: held.append(world.store._lock.locked()) or "ignored"
        status, body = api_edit.save(world.ctx, world.save_body(preview, row["target"], "high"))
        self.assertEqual(409, status)
        self.assertEqual("ignored", body["preview"]["git_ignore"])
        self.assertEqual([False], held)

    def test_the_result_stays_out_of_the_base_hashes(self):
        world = self.world(local={"effortLevel": "low"})
        row = self.level_row(world, "local", "high")
        _status, one = api_edit.preview(world.ctx, world.body(row["target"], "high"))
        self.state.return_value = "ignored"
        _status, two = api_edit.preview(world.ctx, world.body(row["target"], "high"))
        for key in ("base_file", "base_trail", "base_others"):
            self.assertEqual(one[key], two[key])


if __name__ == "__main__":
    unittest.main()

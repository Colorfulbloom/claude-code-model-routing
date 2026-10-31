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


def target_of(body, layer, ends=None):
    """Return the one target row of a layer, optionally the one whose ref ends with `ends`."""
    found = [t for t in body["targets"] if t["layer"] == layer and (ends is None or ends in t["ref"])]
    assert len(found) == 1, (layer, ends, body["targets"])
    return found[0]


def level_of(body, level):
    return [row for row in body["levels"] if row["level"] == level][0]


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
        self.assertEqual(api_edit.targets(off.ctx, {}), (200, {"enabled": False}))
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
                                     "levels_state", "targets", "blocked", "levels"})
        self.assertEqual((body["enabled"], body["project"], body["state"], body["agent"], body["setting"]),
                         (True, "project", "ok", "@main", "effortLevel"))
        self.assertEqual((body["runs_as"], body["model"], body["levels_state"]), ("high", SONNET, "ok"))
        row = target_of(body, "project")
        self.assertEqual(set(row), {"target", "ref", "layer", "file_display", "line", "current_value",
                                    "status", "shared", "in_effect"})
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
        status, pv = world.preview(by_name[dotted].id, "high")
        self.assertEqual(status, 200)
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
        self.assertEqual((status, pv), (400, {"error": "not_editable"}))


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
            self.assertEqual(set(row), {"level", "result", "target", "runs_as", "certain", "limits"})
            self.assertIs(row["certain"], True)
            self.assertEqual(row["limits"], [])
        self.assertEqual(level_of(body, "high"), {"level": "high", "result": "now", "target": None,
                                                  "runs_as": "high", "certain": True, "limits": []})
        for name in ("low", "medium", "xhigh"):
            self.assertEqual(level_of(body, name), {"level": name, "result": "reachable", "target": project,
                                                    "runs_as": name, "certain": True, "limits": []})

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
            self.assertEqual((row["result"], row["target"], row["certain"]), ("reachable", project, False))

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
            self.assertEqual((row["result"], row["target"], row["runs_as"]), ("stopped", None, "low"))
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
        self.assertEqual((row["result"], row["target"], row["runs_as"]), ("stopped", None, "high"))
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
        self.assertEqual((row["result"], row["target"], row["runs_as"]), ("stopped", None, "high"))
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
        self.assertEqual((row["result"], row["target"]), ("stopped", None))
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
            self.assertEqual((row["result"], row["target"], row["runs_as"], row["certain"]),
                             ("stopped", None, "low", False), name)
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
        self.assertEqual(level_of(body, "low")["target"], project)

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
        world = World(self, user={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual((body["levels_state"], body["runs_as"]), ("model_unknown", None))
        self.assertEqual(target_of(body, "user")["status"], "unknown")
        for row in body["levels"]:
            self.assertEqual((row["result"], row["target"], row["runs_as"], row["certain"]),
                             ("stopped", None, None, False))
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
        world = World(self, user={"maxEffortLevel": "high"})
        body = world.targets()
        self.assertEqual(body["levels_state"], "model_unknown")
        for name in ("low", "medium", "high"):
            self.assertEqual(kinds(level_of(body, name)), ["model_unknown"], name)
        # The cap is below xhigh, so the cap is what stops that one.
        self.assertEqual(kinds(level_of(body, "xhigh")), ["cap"])


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
        self.assertEqual(set(pv), {"target", "old_value", "new_value", "no_change", "before", "after",
                                   "changes", "warning", "diff", "base_file", "base_trail", "base_others"})
        self.assertEqual((pv["target"], pv["old_value"], pv["new_value"], pv["no_change"]),
                         (target, "low", "high", False))
        self.assertNotIn("new_raw", pv)
        for name in ("base_file", "base_trail"):
            self.assertRegex(pv[name], r"^[0-9a-f]{64}$")
        self.assertEqual(pv["base_others"], {"config/settings.json": api_edit._hmac(world.ctx, world.read("user")),
                                             "project/.claude/settings.local.json": "missing",
                                             "managed/managed-settings.json": "missing"})
        self.assertEqual(pv["base_file"], api_edit._hmac(world.ctx, world.read("project")))

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
        for row in body["targets"]:
            for value in LEVELS:
                status, _pv = world.preview(row["target"], value)
                self.assertEqual(status, 200)
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
        _status, pv = world.preview(target, "high")
        change = pv["changes"][0]
        self.assertEqual((change["before"]["value"], change["after"]["value"]), ("medium", "high"))
        self.assertEqual((change["before"]["runs_as"], change["after"]["runs_as"]), ("low", "low"))

    def test_hash_bases_name_every_other_file_including_managed_ones(self):
        world = self.world(managed={"maxEffortLevel": "high"}, local={"effortLevel": "medium"})
        os.makedirs(os.path.join(world.managed, "managed-settings.d"))
        world.put(os.path.join(world.managed, "managed-settings.d", "10-extra.json"), {"a": 1})
        target = target_of(world.targets(), "project")["target"]
        _status, pv = world.preview(target, "high")
        self.assertEqual(sorted(pv["base_others"]), [
            "config/settings.json", "managed/managed-settings.d/10-extra.json", "managed/managed-settings.json",
            "project/.claude/settings.local.json"])
        self.assertNotIn("project/.claude/settings.json", pv["base_others"])
        for value in pv["base_others"].values():
            self.assertRegex(value, r"^[0-9a-f]{64}$")
        os.chmod(world.path("local"), 0)
        try:
            _status, again = world.preview(target, "high")
            if os.access(world.path("local"), os.R_OK):  # running as root reads it anyway
                self.skipTest("the file stays readable")
            self.assertEqual(again["base_others"]["project/.claude/settings.local.json"], "unreadable")
        finally:
            os.chmod(world.path("local"), 0o600)


class Warnings(Base):
    def preview(self, world, layer, value, ends=None):
        target = target_of(world.targets(), layer, ends)["target"]
        status, pv = world.preview(target, value)
        self.assertEqual(status, 200, pv)
        return pv

    def test_in_effect_with_no_limit_is_null(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        self.assertIsNone(self.preview(world, "project", "high")["warning"])

    def test_in_effect_with_a_limit_carries_the_limits_in_the_no_model_case(self):
        world = World(self, user={"maxEffortLevel": "low"}, project={"effortLevel": "low"})
        warning = self.preview(world, "project", "high")["warning"]
        self.assertEqual(set(warning), {"status", "reason", "rule_ids", "in_effect_changes", "limits"})
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
        world = World(self, user={"model": OPUS, "effortLevel": "xhigh"})
        target = target_of(world.targets(), "user")["target"]
        status, pv = world.preview(target, "low")
        self.assertIsNotNone(pv["warning"])
        status, saved = world.save(pv, target, "low")
        self.assertEqual(status, 200, saved)
        self.assertIn(b'"low"', world.read("user"))

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
        self.assertEqual(set(edit), {"id", "kind", "time", "layer", "file_display", "key_path", "old_value",
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
        world = World(self, user=raw, project={"effortLevel": "low"}, local={"effortLevel": "low"})
        body = world.targets()
        for layer, ends in (("local", None), ("project", None), ("user", "modelSettings.claude-opus-5-5.effortLevel")):
            before = {name: world.read(name) for name in ("user", "project", "local")}
            target = target_of(body, layer, ends)["target"]
            world.edit(target, "medium")
            for name, data in before.items():
                if name == layer:
                    self.assertEqual(world.read(name), data.replace(b'"low"', b'"medium"', 1), name)
                else:
                    self.assertEqual(world.read(name), data, name)
            body = world.targets()

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
        target, pv = self.ready(world, "user", "medium")
        world.write("project", {"effortLevel": "high", "unrelated": True})
        user_bytes = world.read("user")
        status, body = world.save(pv, target, "medium")
        self.assertEqual((status, body["error"], body["changed"]), (409, "stale", "trail"))
        self.assertEqual(body["changed_files"], [{"layer": "project", "file_display": "project/.claude/settings.json"}])
        self.assertEqual(world.read("user"), user_bytes)
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
        target, pv = self.ready(world)
        for layer, display in (("local", "project/.claude/settings.local.json"), ("user", "config/settings.json"),
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

    def test_a_target_that_stopped_being_valid_is_not_editable(self):
        world = self.world()
        target, pv = self.ready(world)
        world.write("project", {"model": "x"})  # the key is gone
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
                fh.write(dumps({"model": "x"}).encode())
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
        self.assertEqual(set(body), {"error", "stage", "file_unchanged", "backup_display"})
        self.assertEqual((body["error"], body["stage"], body["file_unchanged"]), ("unverified", "reread", False))
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
            (edit_store.Unverified("fsync", {}, None), 500, {"error": "unverified", "stage": "fsync",
                                                             "file_unchanged": False, "backup_display": None}),
            (json_edit.Refused("key_missing"), 422, {"error": "key_missing"}),
            (json_edit.Refused("unparsed"), 422, {"error": "unparsed"}),
            (json_edit.Refused("oracle_failed"), 500, {"error": "write_failed", "file_unchanged": True}),
        )
        for exc, status, body in cases:
            self.assertEqual(api_edit._store_answer(req, exc), (status, body), repr(exc))
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
        self.assertEqual(set(body), {"edit", "settings", "matches_backup", "restored_from_display"})
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


class History(Base):
    def test_rows_join_the_three_ledgers_newest_first(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"effortLevel": "low"}, local={"effortLevel": "low"})
        body = world.targets()
        ids = {}
        for step, (layer, ends) in enumerate((("user", "claude-opus-5-5.effortLevel"), ("local", None),
                                              ("project", None), ("user", "claude-opus-5-5.effortLevel"))):
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
        self.assertEqual(set(rows[0]), {"id", "kind", "time", "layer", "file_display", "key_path", "old_value",
                                        "new_value", "backup_display", "restored_from_display", "undoable",
                                        "not_undoable_reason"})
        self.assertNotIn("restored_from_display", rows[1])
        self.assertEqual(set(rows[1]), set(rows[0]) - {"restored_from_display"})

    def test_a_user_file_edit_appears_under_every_project(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "low"}}},
                      project={"effortLevel": "low"},
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

    def test_reachable_levels_preview_to_that_result_and_stopped_levels_list_every_cap(self):
        reached = stopped = 0
        for name, ctx in self.cases.items():
            body = self.answer(ctx)
            entries = self.plain_entries(ctx)
            ids = {t["target"]: t for t in body["targets"]}
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
                    self.assertIn(row["target"], ids, name)
                    status, pv = api_edit.preview(ctx, {"target": row["target"], "value": level})
                    self.assertEqual(status, 200, name)
                    winner = api_edit._winner(api_edit._effort_row(pv["after"]["entries"]))
                    self.assertEqual(api_edit.ref_of(winner), ids[row["target"]]["ref"], name)
                    self.assertEqual((winner["status"], winner["value"]), ("in_effect", level), name)
                    self.assertIsNone(pv["warning"], "%s %s" % (name, level))
                    self.assertEqual(row["runs_as"], level)
                else:
                    stopped += 1
                    self.assertEqual((row["result"], row["target"]), ("stopped", None), name)
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
# One more look at the project value rules for the write routes with the edit flag off

class FlagOff(Base):
    def test_write_routes_answer_not_editable_without_the_flag(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"}, edit=False)
        for route, body in ((api_edit.preview, {"target": "t", "value": "low"}),
                            (api_edit.save, {"target": "t", "value": "low"}),
                            (api_edit.undo, {"edit": "x"})):
            self.assertEqual(route(world.ctx, body), (400, {"error": "not_editable"}))


if __name__ == "__main__":
    unittest.main()

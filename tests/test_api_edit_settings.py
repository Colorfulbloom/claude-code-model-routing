"""Tests for the settings table of dashboard/api_edit.py (#118, #119, #121).

One table runs the edit routes for effortLevel, maxEffortLevel (the effort cap), model and autoCompactWindow.
The worlds come from tests/test_api_edit.py (throwaway config, project and managed folders in a temp root,
a fixed test token). Nothing reads the real Claude config folder. Secrets are made-up strings that start with
"sk-planted-".
"""
import json
import os
import time
import unittest

import helpers

import test_api_edit as tae

api_edit = tae.api_edit
projects = tae.projects
RULES = tae.RULES
SONNET = tae.SONNET
OPUS = tae.OPUS
SECRET = tae.SECRET
World = tae.World
level_of = tae.level_of
file_of = tae.file_of
target_of = tae.target_of

EFFORT = "effortLevel"
CAP = "maxEffortLevel"
MODEL = "model"
WINDOW = "autoCompactWindow"
FOUR = (EFFORT, CAP, MODEL, WINDOW)
RANKS = ("low", "medium", "high", "xhigh", "max")


def targets_of(world, setting, project=None):
    return world.targets(project, setting)


def preview_of(world, setting, target, value, **extra):
    return api_edit.preview(world.ctx, world.body(target, value, setting=setting, **extra))


def save_of(world, setting, target, value):
    status, pv = preview_of(world, setting, target, value)
    assert status == 200, (status, pv)
    return api_edit.save(world.ctx, world.save_body(pv, target, value, setting=setting))


def view_of(world, setting):
    listing = projects.load(world.ctx)
    return api_edit._view(world.ctx, listing, listing.find(world.key), setting=setting)


def pickable(row):
    return [f for f in row["files"] if f["pickable"]]


# --------------------------------------------------------------------------
# T14a: the table

class TheTable(unittest.TestCase):
    def test_the_table_holds_exactly_the_four_settings(self):
        self.assertEqual(list(api_edit.SETTINGS), list(FOUR))
        for name in ("env", "hooks", "permissions", "apiKeyHelper", "availableModels", "agent", "agents"):
            self.assertNotIn(name, api_edit.SETTINGS)

    def test_the_cap_values_are_the_values_of_the_rule(self):
        rule = [r for r in RULES["rules"] if r["rule_id"] == "max-effort-level-values"][0]
        found = [c["values"] for c in rule["conditions"] if "values" in c]
        self.assertTrue(found)
        for values in found:
            self.assertEqual(tuple(values), api_edit.RANKS)
        self.assertEqual(api_edit.RANKS, RANKS)
        self.assertEqual(tuple(api_edit.SETTINGS[CAP].levels(None)), RANKS)

    def test_the_key_paths_of_each_setting(self):
        yes = {
            EFFORT: [("effortLevel",), ("modelSettings", OPUS, "effortLevel")],
            CAP: [("maxEffortLevel",), ("modelSettings", OPUS, "maxEffortLevel"),
                  ("modelSettings", "us.anthropic.claude-opus-5-5-v1:0", "maxEffortLevel")],
            MODEL: [("model",)],
            WINDOW: [("autoCompactWindow",), ("modelSettings", OPUS, "autoCompactWindow")],
        }
        for setting in FOUR:
            for key_path in yes[setting]:
                self.assertTrue(api_edit._key_allowed(key_path, setting), (setting, key_path))
            # a path of one setting is never a path of another
            for other in FOUR:
                if other != setting:
                    for key_path in yes[other]:
                        self.assertFalse(api_edit._key_allowed(key_path, setting), (setting, key_path))
            for key_path in [(), ("env", "CLAUDE_CODE_AUTO_COMPACT_WINDOW"), ("env", "ANTHROPIC_MODEL"),
                             ("hooks",), ("hooks", setting), ("permissions", "allow"), ("apiKeyHelper",),
                             ("availableModels",), ("modelSettings", OPUS, setting, "x"),
                             ("modelSettings", setting), ("modelSettings", 0, setting), (setting, "x")]:
                self.assertFalse(api_edit._key_allowed(key_path, setting), (setting, key_path))
        self.assertFalse(api_edit._key_allowed(("model",), "env"))
        self.assertFalse(api_edit._key_allowed(("hooks",), "hooks"))
        self.assertFalse(api_edit._key_allowed(("modelSettings", OPUS, "model"), MODEL))

    def test_a_model_is_a_top_level_key_only(self):
        self.assertFalse(api_edit.SETTINGS[MODEL].model_path)
        for setting in (EFFORT, CAP, WINDOW):
            self.assertTrue(api_edit.SETTINGS[setting].model_path, setting)

    def test_the_model_values_are_the_catalog_in_order_each_id_before_its_aliases(self):
        world = World(self, user={})
        values = api_edit._model_values(world.ctx)
        expected = []
        for model in RULES["models"]:
            expected.append(model["id"])
            expected.extend(model.get("aliases") or [])
        self.assertEqual(values, expected)
        self.assertLess(values.index("claude-opus-5-5"), values.index("opus"))
        self.assertEqual(values.index("opus"), values.index("claude-opus-5-5") + 1)

    def test_value_checks(self):
        ctx = World(self, user={}).ctx
        accepts = lambda setting, value, nested=None: api_edit.SETTINGS[setting].accepts(ctx, value, nested)
        for value in ("low", "xhigh"):
            self.assertTrue(accepts(EFFORT, value), value)
        for value in ("max", "", "LOW", None, 1, True, ["low"]):
            self.assertFalse(accepts(EFFORT, value), value)
        for value in RANKS:
            self.assertTrue(accepts(CAP, value), value)
        for value in ("turbo", "", None, 1, True):
            self.assertFalse(accepts(CAP, value), value)
        for value in ("opus", "claude-opus-5-5", "claude-haiku-4-5", "sonnet"):
            self.assertTrue(accepts(MODEL, value), value)
        for value in ("claude-opus-5-5-20260101", "default", "Opus", "", None, 5, True, "claude-opus-5-5[1m]"):
            self.assertFalse(accepts(MODEL, value), value)
        for value in (100000, 100001, 200000, 1000000):
            self.assertTrue(accepts(WINDOW, value), value)
            self.assertTrue(accepts(WINDOW, value, True), value)
            self.assertTrue(accepts(WINDOW, value, False), value)
        for value in (True, False, "100000", "200k", 99999, 1000001, 0, -5, 200000.0, 150000.5, None, [],
                      "Auto", "number"):
            self.assertFalse(accepts(WINDOW, value), value)
        self.assertTrue(accepts(WINDOW, "auto"))
        self.assertTrue(accepts(WINDOW, "auto", True))
        self.assertFalse(accepts(WINDOW, "auto", False))  # the top-level key takes a number only

    def test_the_main_row_helper_finds_one_row_per_setting(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "high", "effortLevel": "low",
                                  "autoCompactWindow": 200000})
        view = view_of(world, MODEL)
        for key in FOUR:
            row = api_edit._main_row(view.entries, key)
            self.assertTrue(row, key)
            self.assertEqual({e["key"] for e in row}, {key})
            self.assertEqual({e["scope"] for e in row}, {"main"})
        self.assertEqual(api_edit._effort_row(view.entries), api_edit._main_row(view.entries, EFFORT))


class RunsAs(unittest.TestCase):
    def runs(self, setting, **kwargs):
        view = view_of(World(self, **kwargs), setting)
        return view.runs_as

    def test_effort_is_unchanged(self):
        self.assertEqual(self.runs(EFFORT, user={"model": SONNET, "maxEffortLevel": "low"},
                                   project={"effortLevel": "high"}), "low")

    def test_the_cap_is_the_winner_or_max_with_no_cap_or_none_when_unknown(self):
        self.assertEqual(self.runs(CAP, user={"model": SONNET}), "max")
        self.assertEqual(self.runs(CAP, user={"model": SONNET, "maxEffortLevel": "high"}), "high")
        self.assertEqual(self.runs(CAP, user={"model": SONNET, "maxEffortLevel": "high"},
                                   project={"maxEffortLevel": "medium"}), "medium")
        self.assertEqual(self.runs(CAP, user={"model": SONNET, "maxEffortLevel": "turbo"}), "max")
        self.assertEqual(self.runs(CAP, user={"model": SONNET}, managed={"maxEffortLevel": "low"}), "low")
        self.assertEqual(self.runs(CAP, user={"model": OPUS, "maxEffortLevel": "low",
                                              "modelSettings": {OPUS: {"maxEffortLevel": "max"}}}), "max")

    def test_the_cap_is_none_when_the_winner_is_unknown(self):
        self.assertIsNone(api_edit._cap_runs_as(None, [
            {"key": CAP, "scope": "main", "layer": "user", "value": "low", "status": "unknown"}]))
        self.assertIsNone(api_edit._cap_runs_as(None, []))

    def test_the_model_is_the_raw_winner_or_none(self):
        self.assertEqual(self.runs(MODEL, user={"model": "opus"}), "opus")
        self.assertEqual(self.runs(MODEL, user={"model": "opus"}, project={"model": "claude-sonnet-5-5"}),
                         "claude-sonnet-5-5")
        self.assertIsNone(self.runs(MODEL, user={}))

    def test_the_window_is_becomes_or_the_value_or_none(self):
        self.assertEqual(self.runs(WINDOW, user={"autoCompactWindow": 300000}), 300000)
        self.assertEqual(self.runs(WINDOW, user={"autoCompactWindow": "auto"}), "auto")
        self.assertIsNone(self.runs(WINDOW, user={}))
        self.assertEqual(self.runs(WINDOW, user={"autoCompactWindow": 99999}), None)
        self.assertEqual(api_edit._compact_runs_as(None, [
            {"key": WINDOW, "scope": "main", "layer": "user", "value": 5, "status": "in_effect", "becomes": 100000}]),
            100000)


# --------------------------------------------------------------------------
# The setting parameter on every route

class TheSettingParameter(unittest.TestCase):
    def world(self, **kwargs):
        return World(self, **dict({"user": {"model": SONNET}, "project": {"effortLevel": "low"}}, **kwargs))

    def test_a_missing_setting_means_effort_and_the_answer_names_the_key(self):
        world = self.world()
        status, body = api_edit.targets(world.ctx, {"project": [world.key]})
        self.assertEqual((status, body["setting"]), (200, EFFORT))
        for setting in FOUR:
            self.assertEqual(targets_of(world, setting)["setting"], setting)

    def test_a_setting_that_is_not_in_the_table_is_bad_setting(self):
        world = self.world()
        for name in ("unknown", "env", "hooks", "permissions", "apiKeyHelper", "availableModels", "", "EffortLevel",
                     "effortLevel ", "modelSettings", "agent"):
            self.assertEqual(api_edit.targets(world.ctx, {"project": [world.key], "setting": [name]}),
                             (400, {"error": "bad_setting"}), name)

    def test_two_values_and_an_empty_list_are_bad_setting(self):
        world = self.world()
        for asked in ([EFFORT, CAP], [EFFORT, EFFORT], [], [5], [None]):
            self.assertEqual(api_edit.targets(world.ctx, {"project": [world.key], "setting": asked}),
                             (400, {"error": "bad_setting"}), asked)

    def test_a_bad_setting_in_a_body_is_bad_setting_for_preview_and_save(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        for setting in ("unknown", "env", "hooks", "permissions", "apiKeyHelper", "", None, 5, ["effortLevel"],
                        {"x": 1}):
            body = world.body(target, "high", setting=setting)
            self.assertEqual(api_edit.preview(world.ctx, body), (400, {"error": "bad_setting"}), setting)
            save = dict(body, base_file="x", base_trail="y", base_others={})
            self.assertEqual(api_edit.save(world.ctx, save), (400, {"error": "bad_setting"}), setting)

    def test_a_body_without_a_setting_is_effort(self):
        world = self.world()
        target = target_of(world.targets(), "project")["target"]
        status, pv = api_edit.preview(world.ctx, world.body(target, "high"))
        self.assertEqual((status, pv["setting"]), (200, EFFORT))
        status, pv = preview_of(world, EFFORT, target, "high")
        self.assertEqual((status, pv["setting"]), (200, EFFORT))

    def test_the_target_must_be_found_in_the_view_of_that_setting(self):
        world = self.world(project={"effortLevel": "low", "maxEffortLevel": "high", "model": SONNET})
        effort = target_of(world.targets(), "project")["target"]
        cap = target_of(targets_of(world, CAP), "project")["target"]
        self.assertNotEqual(effort, cap)
        self.assertEqual(preview_of(world, CAP, effort, "low"), (400, {"error": "not_editable"}))
        self.assertEqual(preview_of(world, EFFORT, cap, "low"), (400, {"error": "not_editable"}))
        self.assertEqual(preview_of(world, MODEL, cap, "opus"), (400, {"error": "not_editable"}))
        self.assertEqual(preview_of(world, CAP, cap, "low")[0], 200)

    def test_a_bad_value_is_bad_value_for_each_setting(self):
        world = self.world(project={"effortLevel": "low", "maxEffortLevel": "high", "model": SONNET,
                                    "autoCompactWindow": 200000})
        bad = {EFFORT: ["max", "turbo", None, 1, True, ""],
               CAP: ["turbo", None, 3, False, "Max"],
               MODEL: ["claude-opus-5-5-20260101", "default", None, 4, True, ["opus"]],
               WINDOW: [True, False, "100000", "200k", 99999, 1000001, 150000.5, 200000.0, None, "number", [], {}]}
        for setting, values in bad.items():
            target = target_of(targets_of(world, setting), "project")["target"]
            for value in values:
                self.assertEqual(preview_of(world, setting, target, value), (400, {"error": "bad_value"}),
                                 (setting, value))
                body = dict(world.body(target, value, setting=setting), base_file="x", base_trail="y",
                            base_others={})
                self.assertEqual(api_edit.save(world.ctx, body), (400, {"error": "bad_value"}), (setting, value))

    def test_a_remove_carries_a_setting_too(self):
        world = self.world(project={"effortLevel": "low", "maxEffortLevel": "high", "model": SONNET})
        target = target_of(targets_of(world, CAP), "project")["target"]
        body = {"project": world.key, "setting": CAP, "target": target, "action": "remove"}
        status, pv = api_edit.preview(world.ctx, body)
        self.assertEqual((status, pv["setting"], pv["op"]), (200, CAP, "remove"))
        self.assertEqual(api_edit.preview(world.ctx, dict(body, setting="hooks")),
                         (400, {"error": "bad_setting"}))
        status, saved = api_edit.save(world.ctx, dict(body, base_file=pv["base_file"], base_trail=pv["base_trail"],
                                                      base_others=pv["base_others"]))
        self.assertEqual(status, 200, saved)
        self.assertNotIn(b"maxEffortLevel", world.read("project"))
        self.assertEqual(saved["edit"]["key_path"], [CAP])


# --------------------------------------------------------------------------
# Writing each setting

class Writes(unittest.TestCase):
    def read(self, world, layer):
        return json.loads(world.read(layer).decode("utf-8"))

    def test_a_top_level_line_is_replaced_for_every_setting(self):
        cases = ((EFFORT, "high", "medium"), (CAP, "high", "medium"), (MODEL, "opus", "sonnet"),
                 (WINDOW, 200000, 300000))
        for setting, old, new in cases:
            world = World(self, user={"model": SONNET}, project={setting: old})
            target = target_of(targets_of(world, setting), "project")["target"]
            status, saved = save_of(world, setting, target, new)
            self.assertEqual(status, 200, (setting, saved))
            self.assertEqual(self.read(world, "project")[setting], new, setting)
            self.assertEqual(saved["edit"]["key_path"], [setting])
            self.assertEqual(saved["edit"]["new_value"], new)

    def test_a_new_line_is_added_for_every_setting(self):
        for setting, value in ((EFFORT, "high"), (CAP, "low"), (MODEL, "opus"), (WINDOW, 250000)):
            world = World(self, user={"model": SONNET}, project={"note": 1})
            body = targets_of(world, setting)
            add = [a for a in body["adds"] if a["layer"] == "project" and a["op"] == "insert"]
            self.assertTrue(add, setting)
            status, saved = save_of(world, setting, add[0]["target"], value)
            self.assertEqual(status, 200, (setting, saved))
            written = self.read(world, "project")
            self.assertEqual((written[setting], written["note"]), (value, 1), setting)

    def test_a_missing_file_is_created_for_every_setting(self):
        for setting, value in ((EFFORT, "high"), (CAP, "low"), (MODEL, "opus"), (WINDOW, 250000)):
            world = World(self, user={"model": SONNET})
            body = targets_of(world, setting)
            add = [a for a in body["adds"] if a["layer"] == "local" and a["op"] == "create"]
            self.assertTrue(add, setting)
            status, saved = save_of(world, setting, add[0]["target"], value)
            self.assertEqual(status, 200, (setting, saved))
            self.assertEqual(self.read(world, "local"), {setting: value}, setting)

    def test_a_model_has_a_top_level_add_only(self):
        world = World(self, user={"model": SONNET}, project={})
        body = targets_of(world, MODEL)
        self.assertTrue(body["adds"])
        self.assertEqual({a["layer"] for a in body["adds"]}, {"local", "project"})  # the user file holds a line
        view = view_of(world, MODEL)
        self.assertEqual({len(a.key_path) for a in view.adds}, {1})
        with_model = World(self, user={"model": SONNET, "modelSettings": {SONNET: {"effortLevel": "low"}}})
        self.assertEqual({len(a.key_path) for a in view_of(with_model, MODEL).adds}, {1})

    def test_a_model_name_under_model_settings_is_never_a_model_target(self):
        world = World(self, user={"model": SONNET, "modelSettings": {SONNET: {"model": "opus"}}})
        body = targets_of(world, MODEL)
        self.assertEqual([t["layer"] for t in body["targets"]], ["user"])
        self.assertEqual(len(body["targets"]), 1)
        self.assertEqual(world.targets()["targets"], [])

    def test_the_cap_and_the_window_are_written_under_model_settings(self):
        for setting, value in ((CAP, "low"), (WINDOW, 250000), (WINDOW, "auto")):
            world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"effortLevel": "high"}}},
                          project={"model": OPUS})
            body = targets_of(world, setting)
            adds = [a for a in body["adds"] if a["layer"] == "user"]
            nested = [a for a in adds if api_edit_path(world, body, a)]
            self.assertEqual(len(nested), 1, (setting, adds))
            status, saved = save_of(world, setting, nested[0]["target"], value)
            self.assertEqual(status, 200, (setting, value, saved))
            table = self.read(world, "user")["modelSettings"][OPUS]
            self.assertEqual((table[setting], table["effortLevel"]), (value, "high"), (setting, value))
            self.assertEqual(saved["edit"]["key_path"], ["modelSettings", OPUS, setting])

    def test_an_existing_model_settings_line_is_replaced_for_the_cap_and_the_window(self):
        for setting, old, new in ((CAP, "low", "xhigh"), (WINDOW, "auto", 300000), (WINDOW, 200000, "auto"),
                                  (WINDOW, 200000, 400000)):
            world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {setting: old}}})
            body = targets_of(world, setting)
            nested = [t for t in body["targets"] if "modelSettings" in t["ref"]]
            self.assertEqual(len(nested), 1, setting)
            status, saved = save_of(world, setting, nested[0]["target"], new)
            self.assertEqual(status, 200, (setting, new, saved))
            self.assertEqual(self.read(world, "user")["modelSettings"][OPUS][setting], new)

    def test_auto_is_written_under_model_settings_and_a_number_at_both_paths(self):
        world = World(self, user={"model": OPUS}, project={WINDOW: 300000})
        body = targets_of(world, WINDOW)
        top = target_of(body, "project")["target"]
        # "auto" on the top-level key is refused, whichever route asks
        self.assertEqual(preview_of(world, WINDOW, top, "auto"), (400, {"error": "bad_value"}))
        save = dict(world.body(top, "auto", setting=WINDOW), base_file="x", base_trail="y", base_others={})
        before = world.snapshot()
        self.assertEqual(api_edit.save(world.ctx, save), (400, {"error": "bad_value"}))
        self.assertEqual(world.snapshot(), before)
        self.assertEqual(self.read(world, "project")[WINDOW], 300000)
        # a number goes to the top-level key
        self.assertEqual(save_of(world, WINDOW, top, 150000)[0], 200)
        self.assertEqual(self.read(world, "project")[WINDOW], 150000)
        # "auto" and a number go to the model table
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {WINDOW: 200000}}})
        nested = [t for t in targets_of(world, WINDOW)["targets"] if "modelSettings" in t["ref"]][0]["target"]
        self.assertEqual(save_of(world, WINDOW, nested, "auto")[0], 200)
        self.assertEqual(self.read(world, "user")["modelSettings"][OPUS][WINDOW], "auto")
        self.assertEqual(save_of(world, WINDOW, nested, 400000)[0], 200)
        self.assertEqual(self.read(world, "user")["modelSettings"][OPUS][WINDOW], 400000)

    def test_the_bytes_written_for_an_int_are_a_json_number(self):
        world = World(self, user={"model": SONNET}, project='{\n  "autoCompactWindow": 200000\n}\n')
        target = target_of(targets_of(world, WINDOW), "project")["target"]
        self.assertEqual(save_of(world, WINDOW, target, 250000)[0], 200)
        self.assertEqual(world.read("project"), b'{\n  "autoCompactWindow": 250000\n}\n')

    def test_max_is_a_cap_value_and_leaves_no_cap_below_any_level(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "xhigh"})
        target = target_of(targets_of(world, CAP), "user")["target"]
        status, saved = save_of(world, CAP, target, "max")
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.read(world, "user")["maxEffortLevel"], "max")
        self.assertIn(b'"maxEffortLevel": "max"', world.read("user"))
        entries = saved["settings"]["entries"]
        for level in api_edit.RANKS:
            self.assertEqual(api_edit._caps_below(entries, level), [], level)
        self.assertEqual(api_edit._cap_runs_as(None, entries), "max")
        self.assertEqual(api_edit._runs_as(None, entries), "xhigh")
        self.assertEqual(targets_of(world, CAP)["runs_as"], "max")


def api_edit_path(world, body, add):
    """True when the add is a modelSettings add (its ref names the path)."""
    return "modelSettings" in add["ref"]


# --------------------------------------------------------------------------
# Secrets

class Masking(unittest.TestCase):
    def planted(self, setting):
        """A world with a secret-looking value in the setting in every file, a secret-named parent and secret keys."""
        value = {EFFORT: SECRET, CAP: SECRET, MODEL: SECRET, WINDOW: SECRET}[setting]
        hidden = {"modelSettings": {"api_token": {setting: SECRET}, OPUS: {setting: SECRET}},
                  "env": {"API_TOKEN": SECRET}, "apiKeyHelper": SECRET,
                  "hooks": {"PreToolUse": [{"command": SECRET}]}, "permissions": {"allow": [SECRET]}}
        files = {}
        for layer in ("user", "project", "local"):
            files[layer] = dict(hidden, **{setting: value, "model": OPUS if setting != MODEL else SECRET})
        return files

    def test_a_planted_secret_never_reaches_an_answer_for_any_setting(self):
        for setting in FOUR:
            world = World(self, **self.planted(setting))
            body = targets_of(world, setting)
            text = json.dumps(body)
            self.assertNotIn(SECRET, text, setting)
            self.assertIn("hidden", text, setting)
            for part in ("files", "targets", "blocked", "levels", "adds"):
                self.assertNotIn(SECRET, json.dumps(body[part]), (setting, part))
            self.assertNotIn(SECRET, json.dumps(body["runs_as"]), setting)
            # a preview of every target never shows the secret either
            for target in body["targets"]:
                value = {EFFORT: "high", CAP: "high", MODEL: "opus", WINDOW: 300000}[setting]
                status, pv = preview_of(world, setting, target["target"], value)
                if status == 200:
                    self.assertNotIn(SECRET, json.dumps(pv), setting)
                    self.assertEqual(pv["old_value"], "hidden", setting)
                else:
                    self.assertNotIn(SECRET, json.dumps(pv), setting)

    def test_the_read_only_answer_hides_the_secret_too(self):
        for setting in FOUR:
            world = World(self, edit=False, **self.planted(setting))
            body = targets_of(world, setting)
            self.assertNotIn(SECRET, json.dumps(body), setting)

    def test_a_secret_model_is_masked_in_runs_as_and_in_the_file_rows(self):
        world = World(self, user={"model": SECRET})
        body = targets_of(world, MODEL)
        self.assertNotIn(SECRET, json.dumps(body))
        self.assertEqual(body["runs_as"], "hidden")
        self.assertEqual(file_of(body["files"], "user")["value"], "hidden")
        for row in body["levels"]:
            self.assertNotIn(SECRET, json.dumps(row))

    def test_a_secret_parent_in_a_blocked_file_is_masked(self):
        world = World(self, user={"model": OPUS}, project='{"modelSettings": {"x": {"maxEffortLevel": "%s"}} ' % SECRET)
        for setting in FOUR:
            self.assertNotIn(SECRET, json.dumps(targets_of(world, setting)), setting)


# --------------------------------------------------------------------------
# Edits off

class EditsOff(unittest.TestCase):
    def test_the_read_only_answer_holds_no_target_ids_and_the_level_list_of_the_setting(self):
        expect = {EFFORT: list(api_edit.LEVELS), CAP: list(RANKS), WINDOW: ["auto", "number"],
                  MODEL: api_edit._model_values(World(self, user={}).ctx)}
        for setting in FOUR:
            world = World(self, edit=False, user={"model": SONNET}, project={"effortLevel": "low", "maxEffortLevel": "high",
                                                                           "autoCompactWindow": 200000, "model": "opus"})
            body = targets_of(world, setting)
            self.assertEqual(body["enabled"], False)
            self.assertEqual(body["setting"], setting)
            text = json.dumps(body)
            self.assertNotRegex(text, r"\bt-[0-9a-f]{16}\b", setting)
            for key in ("targets", "adds", "blocked", "preselect", "saveable", "target", "via", "cap_first", "allow"):
                self.assertNotIn('"%s"' % key, text, (setting, key))
            self.assertEqual([row["level"] for row in body["levels"]], expect[setting], setting)
            for row in body["levels"]:
                self.assertEqual(set(row), {"level", "result"}, setting)
            self.assertEqual(len([r for r in body["levels"] if r["result"] == "now"]),
                             0 if body["runs_as"] not in expect[setting] else 1, setting)

    def test_a_preview_and_a_save_answer_not_editable_for_each_setting(self):
        world = World(self, edit=False, user={"model": SONNET}, project={"effortLevel": "low"})
        for setting in FOUR:
            body = {"project": world.key, "setting": setting, "target": "t-0000000000000000", "value": "low"}
            self.assertEqual(api_edit.preview(world.ctx, body), (400, {"error": "not_editable"}), setting)
            self.assertEqual(api_edit.save(world.ctx, dict(body, base_file="a", base_trail="b", base_others={})),
                             (400, {"error": "not_editable"}), setting)

    def test_a_bad_setting_is_refused_with_edits_off_for_the_read_route(self):
        world = World(self, edit=False, user={})
        self.assertEqual(api_edit.targets(world.ctx, {"setting": ["hooks"]}), (400, {"error": "bad_setting"}))

    def test_the_read_only_path_never_touches_the_edit_state(self):
        world = World(self, edit=False, user={"model": SONNET, "maxEffortLevel": "low"},
                      project={"effortLevel": "high"})
        for setting in FOUR:
            self.assertIs(world.ctx.edit, None)
            self.assertEqual(targets_of(world, setting)["enabled"], False)


# --------------------------------------------------------------------------
# preselect

class Preselect(unittest.TestCase):
    """Only the local file is ever preselected. Where just the shared project file can apply, it is null."""

    def test_a_project_only_row_gives_null_for_each_setting(self):
        worlds = {
            EFFORT: dict(project={"model": SONNET, "effortLevel": "low"}),
            CAP: dict(project={"model": SONNET, "maxEffortLevel": "low"}),
            MODEL: dict(project={"model": "opus"}),
            WINDOW: dict(project={"model": SONNET, "autoCompactWindow": 150000}),
        }
        for setting, files in worlds.items():
            world = World(self, user="{ not json", local="{ not json", **files)
            body = targets_of(world, setting)
            seen = 0
            for row in body["levels"]:
                if row["result"] == "now":
                    continue
                self.assertIsNone(row["preselect"], (setting, row["level"]))
                if [f for f in pickable(row) if f["layer"] == "project"]:
                    seen += 1
                    self.assertTrue(row["saveable"], (setting, row["level"]))
            self.assertGreater(seen, 0, setting)

    def test_the_local_file_is_preselected_when_it_applies_for_each_setting(self):
        for setting in FOUR:
            world = World(self, user={"model": SONNET}, project={"effortLevel": "low", "maxEffortLevel": "high",
                                                                "autoCompactWindow": 200000, "model": "opus"})
            body = targets_of(world, setting)
            picked = [r for r in body["levels"] if r["preselect"] is not None]
            self.assertTrue(picked, setting)
            for row in picked:
                self.assertEqual(file_of(row, "local")["target"], row["preselect"], setting)
                self.assertEqual(file_of(row, "local")["effect"], "applies", setting)


# --------------------------------------------------------------------------
# T14b: caps

class CapLevels(unittest.TestCase):
    def test_a_cap_in_a_file_is_an_editable_limit_with_via_cap(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "low"})
        cap_target = target_of(targets_of(world, CAP), "user")["target"]
        row = level_of(world.targets(), "high")
        limit = row["limits"][0]
        self.assertEqual((limit["kind"], limit["editable"], limit["target"], limit["lock_reason"], limit["via"]),
                         ("cap", True, cap_target, None, "cap"))
        self.assertEqual((limit["value"], limit["layer"], limit["file_display"], limit["line"]),
                         ("low", "user", "config/settings.json", 3))

    def test_cap_later_is_gone_from_the_server(self):
        self.assertNotIn("cap_later", tae.SOURCE.read_text(encoding="utf-8"))

    def test_one_change_via_the_cap_when_the_effort_line_already_holds_the_level(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "high"})
        body = world.targets()
        self.assertEqual(body["runs_as"], "low")
        row = level_of(body, "high")
        self.assertEqual((row["result"], row["via"], row["cap_first"], row["runs_as"]), ("reachable", "cap", False, "high"))
        cap_body = targets_of(world, CAP)
        user_cap = target_of(cap_body, "user")["target"]
        by_layer = {f["layer"]: f for f in row["files"]}
        self.assertEqual([f["layer"] for f in row["files"]], ["local", "project", "user"])
        user = by_layer["user"]
        self.assertEqual((user["target"], user["op"], user["line"], user["effect"], user["runs_as"], user["pickable"],
                          user["lock_reason"]), (user_cap, "replace", 3, "applies", "high", True, None))
        # the other files take a cap line too, but raising nothing else changes what runs
        for layer in ("local", "project"):
            self.assertEqual((by_layer[layer]["effect"], by_layer[layer]["pickable"]), ("wont_apply", False), layer)
            self.assertIn(by_layer[layer]["target"], {a["target"] for a in cap_body["adds"]})
            self.assertEqual(by_layer[layer]["op"], "create" if layer == "local" else "insert")
        self.assertIsNone(row["preselect"])  # the local file holds no cap
        self.assertTrue(row["saveable"])
        self.assertEqual(len(row["limits"]), 1)
        self.assertEqual((row["limits"][0]["target"], row["limits"][0]["editable"]), (user_cap, True))
        self.assertIs(body["saveable"], True)
        # a level above the effort line is not a one change level
        self.assertEqual(level_of(body, "xhigh")["via"], None)
        self.assertEqual(level_of(body, "xhigh")["cap_first"], True)

    def test_the_local_preselect_comes_only_when_local_holds_the_cap(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"}, local={"maxEffortLevel": "low"})
        row = level_of(world.targets(), "high")
        self.assertEqual((row["result"], row["via"]), ("reachable", "cap"))
        local_cap = target_of(targets_of(world, CAP), "local")["target"]
        self.assertEqual(row["preselect"], local_cap)
        self.assertEqual(file_of(row, "local")["target"], local_cap)
        self.assertEqual(file_of(row, "local")["effect"], "applies")

    def test_a_via_cap_level_saves_through_the_cap_setting(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"}, local={"maxEffortLevel": "low"})
        body = world.targets()
        row = level_of(body, "high")
        status, pv = preview_of(world, CAP, row["preselect"], "high")
        self.assertEqual(status, 200, pv)
        self.assertEqual((pv["setting"], pv["runs_before"], pv["runs_after"]), (CAP, "low", "high"))
        self.assertIsNone(pv["warning"])
        status, saved = world.save(pv, row["preselect"], "high", setting=CAP)
        self.assertEqual(status, 200, saved)
        self.assertEqual(json.loads(world.read("local")), {"maxEffortLevel": "high"})
        after = world.targets()
        self.assertEqual(after["runs_as"], "high")
        self.assertEqual(level_of(after, "high")["result"], "now")

    def test_the_via_cap_file_rows_follow_the_cap_views_lock_reasons(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "high"},
                      local="{ not json")
        row = level_of(world.targets(), "high")
        self.assertEqual(row["via"], "cap")
        local = file_of(row, "local")
        self.assertEqual((local["lock_reason"], local["pickable"], local["target"]), ("unparsed", False, None))

    def test_two_changes_when_the_effort_line_is_below_the_level(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "low"})
        body = world.targets()
        user_cap = target_of(targets_of(world, CAP), "user")["target"]
        for name in ("medium", "high", "xhigh"):
            row = level_of(body, name)
            self.assertEqual((row["result"], row["via"], row["cap_first"], row["saveable"], row["preselect"]),
                             ("stopped", None, True, True, None), name)
            self.assertEqual(pickable(row), [], name)
            self.assertEqual([(l["target"], l["editable"], l["via"]) for l in row["limits"]],
                             [(user_cap, True, "cap")], name)
        self.assertIs(body["saveable"], True)
        self.assertEqual(level_of(body, "low")["result"], "now")

    def test_several_caps_below_the_level_are_all_editable_and_the_level_goes_cap_first(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "medium"},
                      project={"effortLevel": "low", "maxEffortLevel": "low"})
        body = world.targets()
        row = level_of(body, "xhigh")
        self.assertEqual((row["result"], row["via"], row["cap_first"], row["saveable"]), ("stopped", None, True, True))
        cap_body = targets_of(world, CAP)
        ids = {layer: target_of(cap_body, layer)["target"] for layer in ("project", "user")}
        self.assertEqual([(l["layer"], l["target"], l["editable"]) for l in row["limits"]],
                         [("project", ids["project"], True), ("user", ids["user"], True)])
        # two caps: never a one change level, even when the effort line holds the level
        world = World(self, user={"model": SONNET, "maxEffortLevel": "medium"},
                      project={"effortLevel": "xhigh", "maxEffortLevel": "low"})
        row = level_of(world.targets(), "xhigh")
        self.assertEqual((row["result"], row["via"], row["cap_first"]), ("stopped", None, True))

    def test_a_managed_cap_keeps_the_stage_one_behaviour(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "high"}, managed={"maxEffortLevel": "low"})
        body = world.targets()
        self.assertEqual(body["runs_as"], "low")
        for name in ("medium", "high", "xhigh"):
            row = level_of(body, name)
            self.assertEqual((row["result"], row["via"], row["cap_first"], row["saveable"], row["preselect"]),
                             ("stopped", None, False, False, None), name)
            limit = row["limits"][0]
            self.assertEqual((limit["kind"], limit["layer"], limit["lock_reason"], limit["editable"], limit["target"]),
                             ("cap", "managed", "managed", False, None), name)
            self.assertNotIn("via", limit)
        self.assertIs(body["saveable"], False)

    def test_a_managed_cap_beside_an_editable_one_keeps_the_level_out_of_reach(self):
        # The lowest cap applies (lowest_value), so raising the user cap can't lift a level the managed cap holds.
        world = World(self, user={"model": SONNET, "maxEffortLevel": "medium"}, project={"effortLevel": "high"},
                      managed={"maxEffortLevel": "low"})
        row = level_of(world.targets(), "high")
        self.assertEqual((row["result"], row["via"], row["cap_first"], row["saveable"]), ("stopped", None, False, False))
        by_layer = {l["layer"]: l for l in row["limits"]}
        self.assertEqual((by_layer["managed"]["editable"], by_layer["user"]["editable"]), (False, True))

    def test_a_cap_in_a_locked_file_carries_the_cap_views_reason(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "high"})
        tae.lock_repo(self, world)
        row = level_of(world.targets(), "high")
        self.assertEqual((row["result"], row["via"], row["cap_first"], row["saveable"]), ("stopped", None, False, False))
        limit = row["limits"][0]
        self.assertEqual((limit["editable"], limit["lock_reason"], limit["target"]), (False, "not_repo_root", None))

    def test_a_model_that_lacks_the_level_does_not_wait_for_the_cap(self):
        world = World(self, user={"model": "claude-opus-4-6", "maxEffortLevel": "low"}, project={"effortLevel": "low"})
        row = level_of(world.targets(), "xhigh")
        self.assertEqual((row["via"], row["cap_first"], row["saveable"]), (None, False, False))
        self.assertEqual([l["kind"] for l in row["limits"]], ["cap", "model"])

    def test_the_cap_panel_reads_lowered_when_a_higher_cap_below_the_value_remains(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "medium"}, project={"effortLevel": "xhigh"},
                      local={"maxEffortLevel": "low"})
        body = targets_of(world, CAP)
        self.assertEqual(body["runs_as"], "low")
        row = level_of(body, "high")
        local = file_of(row, "local")
        self.assertEqual((local["effect"], local["runs_as"], local["pickable"], local["lock_reason"]),
                         ("lowered", "medium", True, None))
        self.assertEqual(row["result"], "stopped")
        self.assertTrue(row["saveable"])
        self.assertIsNone(row["preselect"])  # a lowered row is not "applies"
        self.assertEqual([(l["kind"], l["layer"], l["value"]) for l in row["limits"]], [("winner", "user", "medium")])
        status, pv = preview_of(world, CAP, local["target"], "high")
        self.assertEqual(status, 200, pv)
        self.assertEqual((pv["runs_before"], pv["runs_after"]), ("low", "medium"))
        self.assertEqual(pv["warning"]["status"], "overridden")  # the user cap of medium is the lower one
        self.assertTrue(pv["warning"]["in_effect_changes"])
        self.assertEqual([(l["layer"], l["editable"]) for l in pv["warning"]["limits"]], [("user", True)])

    def test_the_cap_panel_levels_for_no_cap_and_a_cap(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        body = targets_of(world, CAP)
        self.assertEqual((body["runs_as"], body["levels_state"]), ("max", "ok"))
        self.assertEqual([r["level"] for r in body["levels"]], list(RANKS))
        self.assertEqual(level_of(body, "max")["result"], "now")
        for name in ("low", "medium", "high", "xhigh"):
            row = level_of(body, name)
            self.assertEqual((row["result"], row["runs_as"], row["limits"]), ("reachable", name, []), name)
            self.assertEqual(row["preselect"], file_of(row, "local")["target"], name)
        self.assertEqual(set(level_of(body, "low")), {"level", "result", "runs_as", "certain", "limits", "files",
                                                      "preselect", "saveable"})

    def test_a_cap_on_a_model_without_effort_has_no_levels_and_is_not_editable(self):
        world = World(self, user={"model": "claude-haiku-4-5"}, project={"maxEffortLevel": "low", "effortLevel": "low"})
        body = targets_of(world, CAP)
        self.assertEqual((body["levels_state"], body["levels"]), ("no_effort_support", []))
        target = target_of(body, "project")["target"]
        self.assertEqual(preview_of(world, CAP, target, "high"), (400, {"error": "not_editable"}))
        effort = target_of(world.targets(), "project")["target"]
        self.assertEqual(preview_of(world, EFFORT, effort, "high"), (400, {"error": "not_editable"}))

    def test_a_per_model_cap_is_a_target_of_the_cap_setting(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"maxEffortLevel": "low"}}},
                      project={"effortLevel": "low"})
        cap_body = targets_of(world, CAP)
        nested = [t for t in cap_body["targets"] if "modelSettings" in t["ref"]]
        self.assertEqual(len(nested), 1)
        row = level_of(world.targets(), "high")
        self.assertEqual(row["limits"][0]["target"], nested[0]["target"])
        self.assertEqual((row["cap_first"], row["saveable"]), (True, True))


# --------------------------------------------------------------------------
# T14d: the model

class ModelLevels(unittest.TestCase):
    def levels(self, **kwargs):
        world = World(self, **kwargs)
        return world, targets_of(world, MODEL)

    def blocked(self, body):
        return sorted(r["level"] for r in body["levels"] if r["allow"] == "blocked")

    def test_the_levels_are_the_catalog_with_a_verdict_on_each(self):
        world, body = self.levels(user={"model": "opus"}, project={"model": "sonnet"})
        self.assertEqual([r["level"] for r in body["levels"]], api_edit._model_values(world.ctx))
        self.assertEqual((body["levels_state"], body["runs_as"], body["setting"]), ("ok", "sonnet", MODEL))
        for row in body["levels"]:
            self.assertEqual(row["allow"], "ok")
            self.assertEqual(set(row), {"level", "result", "runs_as", "certain", "limits", "files", "preselect",
                                        "saveable", "allow"})
        self.assertEqual(level_of(body, "sonnet")["result"], "now")
        self.assertEqual(level_of(body, "opus")["result"], "reachable")
        row = level_of(body, "opus")
        self.assertEqual([f["layer"] for f in row["files"]], ["local", "project", "user"])
        self.assertEqual(row["preselect"], file_of(row, "local")["target"])
        self.assertEqual(file_of(row, "project")["effect"], "applies")
        self.assertEqual(file_of(row, "user")["effect"], "wont_apply")

    def test_timing_of_the_model_answer_with_lines_in_all_three_files(self):
        world = World(self, user={"model": "sonnet", "availableModels": ["opus", "sonnet"]},
                      project={"model": "opus"}, local={"model": "claude-opus-4-7"})
        start = time.perf_counter()
        body = targets_of(world, MODEL)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(body["levels"]), 16)
        self.assertLess(elapsed, 1.5)

    def test_haiku_4_5_is_not_a_reason_to_refuse_the_model(self):
        world = World(self, user={"model": "claude-haiku-4-5"}, project={"model": "claude-haiku-4-5"})
        view = view_of(world, EFFORT)
        self.assertEqual(view.levels_state, "no_effort_support")
        body = targets_of(world, MODEL)
        self.assertEqual(body["levels_state"], "ok")
        self.assertEqual(len(body["levels"]), 16)
        target = target_of(body, "project")["target"]
        status, pv = preview_of(world, MODEL, target, "opus")
        self.assertEqual((status, pv["old_value"], pv["new_value"], pv["runs_after"]),
                         (200, "claude-haiku-4-5", "opus", "opus"))
        status, saved = world.save(pv, target, "opus", setting=MODEL)
        self.assertEqual(status, 200, saved)
        self.assertEqual(json.loads(world.read("project")), {"model": "opus"})

    def test_the_default_model_has_no_runs_as_and_every_level_can_be_added(self):
        world, body = self.levels(user={})
        self.assertIsNone(body["runs_as"])
        self.assertEqual([r["result"] for r in body["levels"]].count("now"), 0)
        self.assertTrue(all(r["result"] == "reachable" for r in body["levels"]))

    def test_managed_sonnet_blocks_every_opus_id_and_the_alias(self):
        _world, body = self.levels(user={"model": "sonnet"}, managed={"availableModels": ["sonnet"]})
        blocked = self.blocked(body)
        for name in ("opus", "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
                     "claude-opus-4-6"):
            self.assertIn(name, blocked)
        for name in ("sonnet", "claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6"):
            self.assertEqual(level_of(body, name)["allow"], "ok", name)
        row = level_of(body, "claude-opus-5-5")
        self.assertEqual((row["result"], row["saveable"], row["preselect"], row["runs_as"]),
                         ("stopped", False, None, "sonnet"))
        self.assertEqual([f["lock_reason"] for f in row["files"]], ["model_blocked"] * 3)
        self.assertEqual([f["pickable"] for f in row["files"]], [False] * 3)
        self.assertEqual([f["target"] for f in row["files"]], [None] * 3)
        self.assertEqual(row["limits"], [{"kind": "allowlist", "value": None, "layer": None, "file_display": None,
                                          "line": None, "editable": False, "target": None,
                                          "lock_reason": "model_blocked"}])

    def test_a_specific_managed_entry_disables_the_family_wildcard(self):
        _world, body = self.levels(user={"model": "opus"}, managed={"availableModels": ["opus", "claude-opus-4-7"]})
        self.assertEqual(level_of(body, "claude-opus-5-5")["allow"], "blocked")
        self.assertEqual(level_of(body, "claude-opus-4-7")["allow"], "ok")
        self.assertEqual(level_of(body, "opus")["allow"], "ok")

    def test_a_version_prefix_allows_the_ids_it_starts(self):
        _world, body = self.levels(user={"model": "opus"}, managed={"availableModels": ["claude-opus-4"]})
        self.assertEqual(level_of(body, "claude-opus-4-7")["allow"], "ok")
        self.assertEqual(level_of(body, "claude-opus-4-8")["allow"], "ok")
        self.assertEqual(level_of(body, "claude-opus-5-5")["allow"], "blocked")

    def test_a_managed_match_or_denied_list_makes_every_verdict_unclear_and_blocks_nothing(self):
        for managed in ({"availableModelsMatch": ["claude-opus-*"]}, {"deniedModels": ["haiku"]},
                        {"availableModels": ["sonnet"], "availableModelsMatch": ["claude-opus-*"]}):
            world, body = self.levels(user={"model": "sonnet"}, managed=managed)
            self.assertEqual({r["allow"] for r in body["levels"]}, {"unclear"}, managed)
            self.assertTrue(any(r["saveable"] for r in body["levels"]), managed)
            row = level_of(body, "claude-opus-5-5")
            target = file_of(row, "local")["target"]
            status, pv = preview_of(world, MODEL, target, "claude-opus-5-5")
            self.assertEqual((status, pv["allow"]), (200, "unclear"), managed)

    def test_a_non_managed_list_blocks_too_because_the_merged_list_is_what_runs(self):
        world, body = self.levels(user={"model": "sonnet", "availableModels": ["sonnet"]}, project={"model": "sonnet"})
        self.assertEqual(level_of(body, "opus")["allow"], "blocked")
        self.assertEqual(level_of(body, "sonnet")["allow"], "ok")
        # the lists of the files merge, so a project list adds to the user list
        _world, body = self.levels(user={"model": "sonnet", "availableModels": ["sonnet"]},
                                   project={"availableModels": ["opus"]})
        self.assertEqual(level_of(body, "opus")["allow"], "ok")
        self.assertEqual(level_of(body, "claude-haiku-5-5")["allow"], "blocked")

    def test_no_list_means_ok_everywhere(self):
        _world, body = self.levels(user={"model": "sonnet"})
        self.assertEqual({r["allow"] for r in body["levels"]}, {"ok"})

    def test_a_list_that_is_unknown_is_unclear(self):
        _world, body = self.levels(user={"model": "sonnet", "availableModels": "not a list"})
        self.assertEqual({r["allow"] for r in body["levels"]}, {"unclear"})

    def test_preview_and_save_of_a_blocked_model_answer_422_model_blocked(self):
        world = World(self, user={"model": "sonnet"}, project={"model": "sonnet"},
                      managed={"availableModels": ["sonnet"]})
        body = targets_of(world, MODEL)
        target = target_of(body, "project")["target"]
        before = world.snapshot()
        for value in ("opus", "claude-opus-5-5", "claude-haiku-5-5"):
            self.assertEqual(preview_of(world, MODEL, target, value), (422, {"error": "model_blocked"}), value)
            save = dict(world.body(target, value, setting=MODEL), base_file="x", base_trail="y", base_others={})
            self.assertEqual(api_edit.save(world.ctx, save), (422, {"error": "model_blocked"}), value)
        self.assertEqual(world.snapshot(), before)
        status, pv = preview_of(world, MODEL, target, "claude-sonnet-5")
        self.assertEqual((status, pv["allow"]), (200, "ok"))

    def test_a_blocked_level_is_not_a_reachable_one_even_with_a_local_create(self):
        _world, body = self.levels(user={"model": "sonnet"}, managed={"availableModels": ["sonnet"]})
        for row in body["levels"]:
            if row["allow"] == "blocked":
                self.assertEqual((row["result"], row["saveable"], row["preselect"]), ("stopped", False, None))

    def test_a_shell_model_stops_every_level_with_the_env_lock(self):
        world, body = self.levels(user={"model": "sonnet"}, project={"model": "sonnet"},
                                  shell_env={"ANTHROPIC_MODEL": "opus"})
        self.assertEqual(body["runs_as"], "opus")
        row = level_of(body, "claude-sonnet-5-5")
        self.assertEqual(row["result"], "stopped")
        self.assertEqual([(l["kind"], l["layer"], l["lock_reason"]) for l in row["limits"]],
                         [("winner", "env", "env_shell")])
        self.assertFalse(row["saveable"])
        self.assertEqual(level_of(body, "opus")["result"], "now")

    def test_a_line_that_leaves_the_model_alone_wont_apply(self):
        world = World(self, user={"model": "sonnet"}, project={"model": "opus"})
        body = targets_of(world, MODEL)
        row = level_of(body, "claude-sonnet-5-5")
        self.assertEqual(file_of(row, "user")["effect"], "wont_apply")  # the project line wins over it
        self.assertEqual(file_of(row, "project")["effect"], "applies")
        self.assertEqual(file_of(row, "local")["effect"], "applies")


# --------------------------------------------------------------------------
# T14d: the window

class WindowLevels(unittest.TestCase):
    def test_two_rows_auto_and_number_with_a_probe(self):
        world = World(self, user={"model": OPUS}, project={"autoCompactWindow": 300000})
        body = targets_of(world, WINDOW)
        self.assertEqual([r["level"] for r in body["levels"]], ["auto", "number"])
        self.assertEqual((body["runs_as"], body["levels_state"]), (300000, "ok"))
        auto, number = body["levels"]
        self.assertNotIn("probe", auto)
        self.assertEqual(number["probe"], 200000)
        self.assertEqual((number["result"], number["runs_as"]), ("reachable", 200000))
        self.assertEqual((auto["result"], auto["runs_as"]), ("reachable", "auto"))
        self.assertEqual(set(number), {"level", "result", "runs_as", "certain", "limits", "files", "preselect",
                                       "saveable", "probe"})
        self.assertEqual(file_of(number, "local")["effect"], "applies")
        self.assertEqual(file_of(number, "project")["effect"], "applies")
        self.assertEqual(file_of(number, "user")["effect"], "wont_apply")  # the project number wins over it

    def test_the_probe_moves_off_a_window_that_runs_now(self):
        world = World(self, user={"model": OPUS}, project={"autoCompactWindow": 200000})
        number = level_of(targets_of(world, WINDOW), "number")
        self.assertEqual(number["probe"], 300000)
        self.assertEqual(number["result"], "reachable")
        world = World(self, user={"model": OPUS})
        self.assertEqual(level_of(targets_of(world, WINDOW), "number")["probe"], 200000)

    def test_the_number_row_is_never_now_and_the_auto_row_is_now_when_it_runs(self):
        world = World(self, user={"model": OPUS, "modelSettings": {OPUS: {"autoCompactWindow": "auto"}}})
        body = targets_of(world, WINDOW)
        self.assertEqual(body["runs_as"], "auto")
        auto, number = body["levels"]
        self.assertEqual((auto["result"], auto["files"], auto["saveable"], auto["preselect"]), ("now", [], False, None))
        self.assertNotEqual(number["result"], "now")
        self.assertEqual(number["probe"], 200000)
        world = World(self, user={"model": OPUS, "autoCompactWindow": 200000})
        for row in targets_of(world, WINDOW)["levels"]:
            self.assertNotEqual(row["result"], "now")

    def test_the_auto_row_counts_model_settings_candidates_only(self):
        world = World(self, user={"model": OPUS, "autoCompactWindow": 300000}, project={"autoCompactWindow": 200000})
        body = targets_of(world, WINDOW)
        auto = level_of(body, "auto")
        ids = {t["target"]: t for t in body["targets"] + body["adds"]}
        for row in auto["files"]:
            if row["target"] is not None:
                self.assertIn("modelSettings", ids[row["target"]]["ref"], row["layer"])
        self.assertEqual(auto["result"], "reachable")
        self.assertEqual(auto["preselect"], file_of(auto, "local")["target"])
        view = view_of(world, WINDOW)
        self.assertEqual(file_of(auto, "project")["op"], "insert")
        self.assertTrue(all(len(a.key_path) == 3 for a in view.adds if a.id in {r["target"] for r in auto["files"]}))
        # the number row may use the top-level lines
        number = level_of(body, "number")
        top = [ids[r["target"]] for r in number["files"] if r["target"] is not None]
        self.assertTrue(any("modelSettings" not in t["ref"] for t in top))

    def test_with_no_model_the_auto_row_has_no_pickable_row(self):
        world = World(self, user={"autoCompactWindow": 300000}, project={"autoCompactWindow": 200000})
        body = targets_of(world, WINDOW)
        self.assertIsNone(body["model"])
        auto = level_of(body, "auto")
        self.assertEqual((auto["result"], auto["saveable"], auto["preselect"]), ("stopped", False, None))
        self.assertEqual(pickable(auto), [])
        self.assertEqual([f["lock_reason"] for f in auto["files"]], ["not_editable"] * 3)
        number = level_of(body, "number")
        self.assertTrue(number["saveable"])
        self.assertIs(body["saveable"], True)

    def test_a_window_below_the_floor_is_ignored_and_runs_as_nothing(self):
        world = World(self, user={"model": OPUS, "autoCompactWindow": 99999})
        body = targets_of(world, WINDOW)
        self.assertNotEqual(body["runs_as"], 99999)  # the model's own window runs
        self.assertEqual(target_of(body, "user")["status"], "ignored")

    def test_a_shell_window_wins_over_every_file(self):
        world = World(self, user={"model": OPUS}, shell_env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000"})
        body = targets_of(world, WINDOW)
        self.assertEqual(body["runs_as"], 150000)
        number = level_of(body, "number")
        self.assertEqual((number["result"], number["saveable"]), ("stopped", False))
        self.assertEqual([(l["kind"], l["layer"], l["lock_reason"]) for l in number["limits"]],
                         [("winner", "env", "env_shell")])

    def test_preview_and_save_run_the_real_value_not_the_probe(self):
        world = World(self, user={"model": OPUS}, project={"autoCompactWindow": 300000})
        body = targets_of(world, WINDOW)
        number = level_of(body, "number")
        target = number["preselect"]
        status, pv = preview_of(world, WINDOW, target, 123456)
        self.assertEqual((status, pv["new_value"], pv["runs_after"], pv["setting"]), (200, 123456, 123456, WINDOW))
        self.assertNotIn("allow", pv)
        status, saved = world.save(pv, target, 123456, setting=WINDOW)
        self.assertEqual(status, 200, saved)
        self.assertEqual(json.loads(world.read("local")), {"autoCompactWindow": 123456})
        self.assertEqual(targets_of(world, WINDOW)["runs_as"], 123456)

    def test_auto_saved_for_a_model_settings_target_runs_as_auto(self):
        world = World(self, user={"model": OPUS})
        body = targets_of(world, WINDOW)
        target = level_of(body, "auto")["preselect"]
        status, pv = preview_of(world, WINDOW, target, "auto")
        self.assertEqual((status, pv["runs_after"], pv["warning"]), (200, "auto", None))
        self.assertEqual(world.save(pv, target, "auto", setting=WINDOW)[0], 200)
        self.assertEqual(json.loads(world.read("local")), {"modelSettings": {OPUS: {"autoCompactWindow": "auto"}}})
        self.assertEqual(targets_of(world, WINDOW)["runs_as"], "auto")

    def test_auto_on_a_top_level_target_is_bad_value_and_writes_nothing(self):
        world = World(self, user={"model": OPUS}, project={"autoCompactWindow": 300000})
        body = targets_of(world, WINDOW)
        top = [t for t in body["adds"] + body["targets"] if "modelSettings" not in t["ref"]]
        self.assertTrue(top)
        before = world.snapshot()
        for target in top:
            self.assertEqual(preview_of(world, WINDOW, target["target"], "auto"), (400, {"error": "bad_value"}))
        self.assertEqual(world.snapshot(), before)


# --------------------------------------------------------------------------
# The effect of the new settings

class Effects(unittest.TestCase):
    def test_a_file_that_leaves_the_setting_where_it_is_wont_apply(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, local={"maxEffortLevel": "low"})
        view = view_of(world, CAP)
        user = [t for t in view.targets if t.layer == "user"][0]
        self.assertEqual(api_edit._effect(view, user, "high")[:2], ("wont_apply", "low"))

    def test_a_higher_cap_in_another_file_moves_the_cap_partway_and_reads_lowered(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "medium"}, local={"maxEffortLevel": "low"})
        view = view_of(world, CAP)
        local = [t for t in view.targets if t.layer == "local"][0]
        self.assertEqual(api_edit._effect(view, local, "xhigh")[:2], ("lowered", "medium"))
        self.assertEqual(api_edit._effect(view, local, "medium")[:2], ("applies", "medium"))

    def test_a_value_the_entry_loses_to_a_lower_winner_wont_apply(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"})
        view = view_of(world, CAP)
        local_add = [t for t in view.adds if t.layer == "local"][0]
        self.assertEqual(api_edit._effect(view, local_add, "high")[0], "wont_apply")

    def test_an_unknown_entry_reads_unknown(self):
        world = World(self, user={"model": SONNET}, project={"autoCompactWindow": 300000})
        view = view_of(world, WINDOW)
        # a file value the resolver cannot judge (the model's window unknown) is drawn by the same rule
        entries = view.entries
        mine = [e for e in api_edit._main_row(entries, WINDOW) if e["layer"] == "project"][0]
        fake = [dict(e, status="unknown") if e is mine else e for e in entries]
        with_unknown = api_edit._Target("project", (WINDOW,), view.targets[0].store_target, view.targets[0].raw,
                                        mine)
        view.sims[(with_unknown.id, 250000)] = fake
        self.assertEqual(api_edit._effect(view, with_unknown, 250000)[0], "unknown")

    def test_a_model_settings_that_is_no_object_locks_the_window_but_not_the_model(self):
        world = World(self, user={"model": OPUS}, project={"modelSettings": "x"})
        for setting in (EFFORT, CAP, WINDOW):
            self.assertEqual(file_of(targets_of(world, setting)["files"], "project")["lock_reason"],
                             "parent_not_object", setting)
        project = file_of(targets_of(world, MODEL)["files"], "project")
        self.assertEqual((project["state"], project["lock_reason"]), ("no_line", None))

    def test_a_refused_simulation_answers_not_editable_with_no_effect(self):
        world = World(self, user={"model": OPUS}, project={"model": OPUS})
        view = view_of(world, MODEL)
        target = [t for t in view.targets if t.layer == "project"][0]
        view.sims[(target.id, "sonnet")] = None
        view.refused[(target.id, "sonnet")] = "repeated_key"
        self.assertEqual(api_edit._effect(view, target, "sonnet"), (None, None, "not_editable", None))
        view.refused[(target.id, "sonnet")] = "parent_not_object"
        self.assertEqual(api_edit._effect(view, target, "sonnet"), (None, None, "parent_not_object", None))

    def test_the_warning_is_none_when_the_entry_runs_as_the_value(self):
        world = World(self, user={"model": "sonnet"}, project={"model": "sonnet"})
        target = target_of(targets_of(world, MODEL), "project")["target"]
        status, pv = preview_of(world, MODEL, target, "opus")
        self.assertEqual((status, pv["warning"]), (200, None))

    def test_the_warning_names_the_winner_when_it_is_not_this_entry(self):
        world = World(self, user={"model": "sonnet"}, project={"model": "sonnet"}, local={"model": "opus"})
        body = targets_of(world, MODEL)
        user = target_of(body, "user")["target"]
        status, pv = api_edit.preview(world.ctx, world.body(user, "claude-opus-5", setting=MODEL))
        # the user line loses to the local one, so the preview is refused as a file that would not apply
        self.assertEqual((status, pv), (400, {"error": "not_editable"}))
        inner = api_edit._preview(world.ctx, view_of(world, MODEL), view_of(world, MODEL).find(user), "claude-opus-5")
        warning = inner.payload["warning"]
        self.assertEqual(warning["status"], "overridden")
        self.assertEqual(set(warning), {"status", "reason", "rule_ids", "in_effect_changes", "model_known", "limits"})
        self.assertEqual([(l["kind"], l["layer"], l["editable"]) for l in warning["limits"]], [("winner", "local", True)])
        self.assertIsNotNone(warning["limits"][0]["target"])
        self.assertIsNone(warning["limits"][0]["lock_reason"])

    def test_the_warning_limit_of_a_managed_winner_is_locked(self):
        world = World(self, user={"model": "sonnet"}, project={"model": "sonnet"}, managed={"model": "opus"})
        view = view_of(world, MODEL)
        target = [t for t in view.targets if t.layer == "project"][0]
        warning = api_edit._preview(world.ctx, view, target, "claude-opus-5").payload["warning"]
        self.assertEqual([(l["layer"], l["editable"], l["lock_reason"]) for l in warning["limits"]],
                         [("managed", False, "managed")])

    def test_the_preview_payload_names_the_setting_and_only_the_model_gains_allow(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low", "maxEffortLevel": "high",
                                                           "model": "sonnet", "autoCompactWindow": 200000})
        for setting, value in ((EFFORT, "high"), (CAP, "low"), (MODEL, "opus"), (WINDOW, 300000)):
            target = target_of(targets_of(world, setting), "project")["target"]
            status, pv = preview_of(world, setting, target, value)
            self.assertEqual(status, 200, (setting, pv))
            self.assertEqual(pv["setting"], setting)
            self.assertEqual("allow" in pv, setting == MODEL, setting)
        self.assertEqual(preview_of(world, MODEL, target_of(targets_of(world, MODEL), "project")["target"], "opus")[1]["allow"], "ok")

    def test_a_remove_of_a_cap_line_says_what_runs_after(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "high"})
        body = targets_of(world, CAP)
        user = target_of(body, "user")
        self.assertEqual(user["remove"], {"runs_as": "max", "no_effect": False, "lock_reason": None})
        self.assertTrue(user["in_effect"])


# --------------------------------------------------------------------------
# Saving the new settings

class Saves(unittest.TestCase):
    def test_a_stale_cap_save_answers_with_a_fresh_preview_of_the_same_setting(self):
        world = World(self, user={"model": SONNET}, project={"maxEffortLevel": "low", "effortLevel": "low"})
        target = target_of(targets_of(world, CAP), "project")["target"]
        status, pv = preview_of(world, CAP, target, "high")
        self.assertEqual(status, 200)
        world.write("project", {"maxEffortLevel": "medium", "effortLevel": "low"})
        status, body = world.save(pv, target, "high", setting=CAP)
        self.assertEqual((status, body["error"]), (409, "stale"))
        self.assertEqual((body["preview"]["setting"], body["preview"]["old_value"]), (CAP, "medium"))

    def test_a_stale_model_save_answers_with_a_fresh_preview_of_the_model(self):
        world = World(self, user={"model": SONNET}, project={"model": "sonnet"})
        target = target_of(targets_of(world, MODEL), "project")["target"]
        status, pv = preview_of(world, MODEL, target, "opus")
        world.write("project", {"model": "claude-opus-4-7"})
        status, body = world.save(pv, target, "opus", setting=MODEL)
        self.assertEqual((status, body["error"], body["preview"]["setting"]), (409, "stale", MODEL))
        self.assertEqual(body["preview"]["allow"], "ok")

    def test_a_save_that_would_not_apply_is_not_editable_for_each_new_setting(self):
        cases = (
            (CAP, dict(user={"model": SONNET, "maxEffortLevel": "low"}), "local", "high"),
            (MODEL, dict(user={"model": SONNET}, managed={"model": "opus"}), "local", "haiku"),
            (WINDOW, dict(user={"model": OPUS}, shell_env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000"}), "local", 250000),
        )
        for setting, kwargs, layer, value in cases:
            world = World(self, **kwargs)
            body = targets_of(world, setting)
            add = [a for a in body["adds"] if a["layer"] == layer and "modelSettings" not in a["ref"]][0]
            before = world.snapshot()
            self.assertEqual(preview_of(world, setting, add["target"], value), (400, {"error": "not_editable"}), setting)
            self.assertEqual(world.snapshot(), before)

    def test_an_undo_of_a_cap_edit_restores_the_file(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "high"})
        original = world.read("user")
        target = target_of(targets_of(world, CAP), "user")["target"]
        status, saved = save_of(world, CAP, target, "high")
        self.assertEqual(status, 200, saved)
        self.assertNotEqual(world.read("user"), original)
        status, undone = world.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, undone)
        self.assertEqual(world.read("user"), original)


# --------------------------------------------------------------------------
# Shapes

class Shapes(unittest.TestCase):
    def test_every_setting_answers_the_same_top_level_fields(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        keys = set(world.targets())
        for setting in FOUR:
            self.assertEqual(set(targets_of(world, setting)), keys, setting)

    def test_only_effort_rows_carry_via_and_cap_first(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "low"})
        for setting in FOUR:
            for row in targets_of(world, setting)["levels"]:
                self.assertEqual("via" in row, setting == EFFORT, (setting, row["level"]))
                self.assertEqual("cap_first" in row, setting == EFFORT, (setting, row["level"]))
                self.assertEqual("allow" in row, setting == MODEL, (setting, row["level"]))
                self.assertEqual("probe" in row, setting == WINDOW and row["level"] == "number", (setting, row["level"]))

    def test_the_file_row_keys_are_the_same_for_every_setting(self):
        world = World(self, user={"model": SONNET}, project={"effortLevel": "low"})
        for setting in FOUR:
            for row in targets_of(world, setting)["levels"]:
                for item in row["files"]:
                    self.assertEqual(set(item), {"layer", "target", "op", "line", "runs_as", "effect", "lock_reason",
                                                 "pickable"}, setting)


# --------------------------------------------------------------------------
# What the page needs to word a cap change: the setting of a backup preview, and the editable winner of a stopped level

class CapPageNeeds(unittest.TestCase):
    def test_a_backup_preview_of_a_cap_row_names_the_cap_and_its_runs(self):
        world = World(self, user={"model": SONNET, "maxEffortLevel": "low"}, project={"effortLevel": "high"})
        target = target_of(targets_of(world, CAP), "user")["target"]
        status, saved = save_of(world, CAP, target, "high")
        self.assertEqual(status, 200, saved)
        self.assertEqual(world.targets()["runs_as"], "high")
        for kind in ("undo", "restore"):
            status, body = api_edit.backup_preview(world.ctx, {"project": world.key, "edit": saved["edit"]["id"], "kind": kind})
            self.assertEqual(status, 200, body)
            self.assertEqual((body["kind"], body["setting"]), (kind, CAP), kind)
            self.assertEqual((body["runs_before"], body["runs_after"]), ("high", "low"), kind)
            self.assertEqual((body["old_value"], body["new_value"]), ("high", "low"), kind)

    def test_a_stopped_cap_level_held_by_a_line_of_the_view_lists_that_winner_as_editable(self):
        world = World(self, user={"model": SONNET}, local={"maxEffortLevel": "low"}, project={"maxEffortLevel": "high"})
        body = targets_of(world, CAP)
        project = target_of(body, "project")["target"]
        stopped = [row for row in body["levels"] if row["result"] == "stopped"]
        self.assertTrue(stopped)
        for row in stopped:
            self.assertEqual([(l["kind"], l["layer"], l["editable"], l["target"], l["lock_reason"]) for l in row["limits"]],
                             [("winner", "project", True, project, None)], row["level"])

    def test_a_stopped_window_level_held_by_a_line_of_the_view_lists_that_winner_as_editable(self):
        world = World(self, local={"autoCompactWindow": 300000})
        body = targets_of(world, WINDOW)
        row = level_of(body, "auto")
        local = target_of(body, "local")["target"]
        self.assertEqual((row["result"], row["saveable"]), ("stopped", False))
        self.assertEqual([(l["kind"], l["layer"], l["editable"], l["target"], l["lock_reason"]) for l in row["limits"]],
                         [("winner", "local", True, local, None)])


if __name__ == "__main__":
    unittest.main()

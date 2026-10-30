"""Tests for the dashboard collectors (dashboard/collect.py).

Every run reads only the repo and its own throwaway folders, and all content is
made up. A guard test fails if a collector touches the real home or the real
managed folder, or calls os.path.expanduser, Path.home or reads os.environ.
"""
import json
import os
import pwd
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import collect  # noqa: E402

RULES_PATH = os.path.join(helpers.REPO, "dashboard", "rules.json")
REAL_MANAGED = "/Library/Application Support/ClaudeCode"


def load_rules():
    with open(RULES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def jsonable(value):
    """Make collector output printable: a tuple key becomes its repr."""
    if isinstance(value, dict):
        return {(repr(k) if isinstance(k, tuple) else k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def dump(value):
    return json.dumps(jsonable(value), sort_keys=True)


def agent_text(extra="", name="probe"):
    return "---\nname: %s\ndescription: Made-up agent.\n%s---\nBody.\n" % (name, extra)


class Tree(unittest.TestCase):
    """A throwaway tree with a config dir, a project dir and a managed dir."""

    def setUp(self):
        raw = tempfile.mkdtemp(prefix="collect-", dir=helpers._tmp_base())
        self.addCleanup(helpers.rmtree_force, raw)
        self.root = raw
        self.config = os.path.join(raw, "config")
        self.project = os.path.join(raw, "project")
        self.managed = os.path.join(raw, "managed")
        for folder in (self.config, self.project, self.managed):
            os.makedirs(folder)

    def write(self, path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = content if isinstance(content, bytes) else (
            content if isinstance(content, str) else json.dumps(content, indent=2)).encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def user(self, content):
        return self.write(os.path.join(self.config, "settings.json"), content)

    def proj(self, content):
        return self.write(os.path.join(self.project, ".claude", "settings.json"), content)

    def local(self, content):
        return self.write(os.path.join(self.project, ".claude", "settings.local.json"), content)

    def managed_file(self, content, name="managed-settings.json"):
        return self.write(os.path.join(self.managed, name), content)

    def managed_d(self, name, content):
        return self.write(os.path.join(self.managed, "managed-settings.d", name), content)

    def settings(self):
        return collect.collect_settings(self.config, self.project, self.managed)

    def collect(self, shell=None, rules=None):
        return collect.collect(self.config, self.project, self.managed, shell or {},
                               rules if rules is not None else load_rules())

    def layers(self, result):
        return [s["layer"] for s in result["sources"]]

    def source(self, result, layer):
        return next(s for s in result["sources"] if s["layer"] == layer)

    def deny_access(self, path, mode=0o000):
        original = os.stat(path).st_mode & 0o777
        os.chmod(path, mode)
        self.addCleanup(os.chmod, path, original)


class MaskTests(unittest.TestCase):
    def test_secret_names_in_any_case(self):
        for name in ("ANTHROPIC_API_KEY", "anthropic_auth_token", "MyToken", "client_SECRET",
                     "db_Password", "credentials", "AuthHeader", "apiKeyHelper"):
            with self.subTest(name=name):
                self.assertTrue(collect.is_secret_name(name))

    def test_harmless_names(self):
        for name in ("ANTHROPIC_MODEL", "model", "effortLevel", "CLAUDE_CODE_EFFORT_LEVEL", ""):
            with self.subTest(name=name):
                self.assertFalse(collect.is_secret_name(name))
        self.assertFalse(collect.is_secret_name(None))

    def test_secret_value_prefixes(self):
        for value in ("sk-planted-bravo", "SK-planted-bravo", "Bearer planted-charlie",
                      "bearer planted-charlie", "  sk-planted-bravo"):
            with self.subTest(value=value):
                self.assertTrue(collect.is_secret_value(value))
        for value in ("disk-1", "Bearer", "a sk- b", "", 5, None, ["sk-x"]):
            with self.subTest(value=value):
                self.assertFalse(collect.is_secret_value(value))

    def test_value_patterns_hide_under_harmless_names(self):
        self.assertEqual(collect.mask("sk-planted-bravo", "NOTE"), collect.HIDDEN)
        self.assertEqual(collect.mask("Bearer planted-charlie", "NOTE"), collect.HIDDEN)
        self.assertEqual(collect.mask("sk-planted-bravo"), collect.HIDDEN)
        self.assertEqual(collect.mask("plain", "NOTE"), "plain")

    def test_a_secret_name_hides_any_value(self):
        for value in ("plain", 7, True, None, {"a": 1}, ["a", "b"]):
            with self.subTest(value=value):
                self.assertEqual(collect.mask(value, "MADE_UP_TOKEN"), collect.HIDDEN)

    def test_dicts_and_lists_mask_item_by_item(self):
        value = {"ok": "fine", "madeUpKey": "x", "nest": {"a": "sk-q", "b": [1, "Bearer z", "y"]},
                 "authors": ["a"]}
        self.assertEqual(collect.mask(value), {
            "ok": "fine", "madeUpKey": "hidden",
            "nest": {"a": "hidden", "b": [1, "hidden", "y"]}, "authors": "hidden"})

    def test_a_list_takes_the_name_of_its_key(self):
        self.assertEqual(collect.mask({"hooks": ["Bearer z", "ok"]}), {"hooks": ["hidden", "ok"]})

    def test_mask_does_not_change_its_input(self):
        value = {"madeUpKey": "x", "n": ["sk-q"]}
        collect.mask(value)
        self.assertEqual(value, {"madeUpKey": "x", "n": ["sk-q"]})

    def test_scalars_pass_through(self):
        for value in (1, 2.5, True, None, "text"):
            self.assertEqual(collect.mask(value, "NOTE"), value)

    def test_no_variable_rules_json_names_matches_a_secret_pattern(self):
        self.assertEqual(self.secret_variables(load_rules()), [])

    def test_the_variable_check_fails_on_a_matching_name(self):
        rules = {"variables": [{"name": "ANTHROPIC_MODEL"}, {"name": "MADE_UP_AUTH_TOKEN"},
                               {"name": "my_secret_mode"}]}
        self.assertEqual(self.secret_variables(rules), ["MADE_UP_AUTH_TOKEN", "my_secret_mode"])

    @staticmethod
    def secret_variables(rules):
        return [v["name"] for v in rules.get("variables", []) if collect.is_secret_name(v["name"])]


class JsonKeyLinesTests(unittest.TestCase):
    def test_every_key_at_any_depth(self):
        text = '{\n  "a": 1,\n  "b": {\n    "c": [1, {"hidden": 2}],\n    "d": {\n      "e": null\n    }\n  }\n}\n'
        self.assertEqual(collect.json_key_lines(text), {
            ("a",): 2, ("b",): 3, ("b", "c"): 4, ("b", "d"): 5, ("b", "d", "e"): 6})

    def test_one_line_documents(self):
        text = '{"a":{"b":"}\\"{","c":[1,2,{"x":1}]},"d":true}'
        self.assertEqual(collect.json_key_lines(text), {
            ("a",): 1, ("a", "b"): 1, ("a", "c"): 1, ("d",): 1})

    def test_keys_with_dots_stay_whole(self):
        text = '{"modelSettings": {\n"us.anthropic.x-v1:0": {\n"effortLevel": "high"}}}'
        lines = collect.json_key_lines(text)
        self.assertEqual(lines[("modelSettings", "us.anthropic.x-v1:0", "effortLevel")], 3)

    def test_last_duplicate_wins(self):
        text = '{\n"a": {"x": 1},\n"b": 1,\n"a": 2\n}'
        self.assertEqual(collect.json_key_lines(text), {("a",): 4, ("b",): 3})
        text = '{\n"a": 1,\n"a": {"x": 1}\n}'
        self.assertEqual(collect.json_key_lines(text), {("a",): 3, ("a", "x"): 3})

    def test_line_endings(self):
        body = '{\n  "a": 1,\n  "b": {\n    "c": 2\n  }\n}\n'
        for ending in ("\r\n", "\r"):
            with self.subTest(ending=repr(ending)):
                lines = collect.json_key_lines(body.replace("\n", ending))
                self.assertEqual(lines, {("a",): 2, ("b",): 3, ("b", "c"): 4})

    def test_top_level_array_and_scalars_have_no_keys(self):
        for text in ('[{"a": 1}]', "5", '"x"', "null", "{}"):
            self.assertEqual(collect.json_key_lines(text), {})

    def test_escaped_and_unicode_keys(self):
        text = '{"a\\"b": 1,\n"\\u00e9": {"\\n": 2}}'
        self.assertEqual(collect.json_key_lines(text), {
            ('a"b',): 1, ("é",): 2, ("é", "\n"): 2})


class SettingsFileTests(Tree):
    def test_the_three_files_and_the_managed_file_are_read(self):
        user = self.user({"model": "u"})
        proj = self.proj({"model": "p"})
        loc = self.local({"model": "l"})
        man = self.managed_file({"model": "m"})
        result = self.settings()
        self.assertEqual(self.layers(result), ["managed", "local", "project", "user"])
        self.assertEqual([s["data"]["model"] for s in result["sources"]], ["m", "l", "p", "u"])
        self.assertEqual(
            [(f["layer"], f["path"], f["status"], f["line"]) for f in result["files"]],
            [("managed", man, "ok", None), ("local", loc, "ok", None),
             ("project", proj, "ok", None), ("user", user, "ok", None)])
        for source, path in zip(result["sources"], (man, loc, proj, user)):
            self.assertEqual(source["where"][("model",)]["path"], path)

    def test_a_missing_file_leaves_no_record(self):
        user = self.user({"model": "u"})
        result = self.settings()
        self.assertEqual(self.layers(result), ["user"])
        self.assertEqual([f["path"] for f in result["files"]], [user])

    def test_no_files_at_all(self):
        self.assertEqual(self.settings(), {"sources": [], "files": []})

    def test_a_none_managed_dir_reads_no_managed_file(self):
        self.managed_file({"model": "m"})
        self.user({"model": "u"})
        result = collect.collect_settings(self.config, self.project, None)
        self.assertEqual(self.layers(result), ["user"])

    def test_managed_order_and_skipped_names(self):
        base = self.managed_file({"model": "base"})
        late = self.managed_d("30-late.json", {"model": "late"})
        early = self.managed_d("10-early.json", {"model": "early"})
        self.managed_d(".hidden.json", {"model": "hidden"})
        self.managed_d("notes.txt", {"model": "text"})
        self.managed_d("config.json.bak", {"model": "bak"})
        os.makedirs(os.path.join(self.managed, "managed-settings.d", "dir.json"))
        result = self.settings()
        self.assertEqual([f["path"] for f in result["files"]], [base, early, late])
        managed = self.source(result, "managed")
        self.assertEqual(managed["data"]["model"], "late")
        self.assertEqual(managed["where"][("model",)]["path"], late)

    def test_a_managed_folder_without_a_base_file(self):
        only = self.managed_d("a.json", {"model": "a"})
        result = self.settings()
        self.assertEqual([f["path"] for f in result["files"]], [only])

    def test_later_managed_file_wins_a_single_value(self):
        self.managed_file({"model": "m1", "other": 1})
        late = self.managed_d("10-team.json", {"model": "m2"})
        managed = self.source(self.settings(), "managed")
        self.assertEqual(managed["data"], {"model": "m2", "other": 1})
        self.assertEqual(managed["where"][("model",)]["path"], late)
        self.assertEqual(managed["where"][("model",)]["line"], 2)

    def test_managed_merge(self):
        first = self.managed_file({
            "model": "m1",
            "x": {"a": 1},
            "env": {"A": "1", "C": "old"},
            "permissions": {"deny": ["x", "y"], "other": True},
            "fallbackModel": {"name": "f1", "extra": 1},
            "extraKnownMarketplaces": {"one": {"src": "a"}, "two": {"src": "b"}},
            "modelSettings": {"m": {"effortLevel": "low"}},
        })
        second = self.managed_d("10-team.json", {
            "model": "m2",
            "x": 5,
            "env": {"B": "2", "C": "new"},
            "permissions": {"deny": ["y", "z"]},
            "fallbackModel": {"name": "f2"},
            "extraKnownMarketplaces": {"two": {"src": "b2"}, "three": {"src": "c"}},
            "modelSettings": {"m": {"effortLevel": "high"}},
        })
        managed = self.source(self.settings(), "managed")
        data, where = managed["data"], managed["where"]
        self.assertEqual(data["model"], "m2")
        self.assertEqual(data["x"], 5)
        self.assertEqual(data["env"], {"A": "1", "C": "new", "B": "2"})
        self.assertEqual(data["permissions"], {"deny": ["x", "y", "z"], "other": True})
        self.assertEqual(data["fallbackModel"], {"name": "f2"})
        self.assertEqual(data["extraKnownMarketplaces"],
                         {"one": {"src": "a"}, "two": {"src": "b2"}, "three": {"src": "c"}})
        self.assertEqual(data["modelSettings"], {"m": {"effortLevel": "high"}})
        owner = {
            ("model",): second, ("x",): second, ("env", "A"): first, ("env", "B"): second,
            ("env", "C"): second, ("permissions", "deny"): second,
            ("permissions", "other"): first, ("fallbackModel", "name"): second,
            ("extraKnownMarketplaces", "one"): first,
            ("extraKnownMarketplaces", "one", "src"): first,
            ("extraKnownMarketplaces", "two"): second,
            ("extraKnownMarketplaces", "two", "src"): second,
            ("extraKnownMarketplaces", "three"): second,
            ("modelSettings", "m", "effortLevel"): second,
        }
        for key, path in owner.items():
            with self.subTest(key=key):
                self.assertEqual(where[key]["path"], path)
        # A replaced value drops the earlier file's entries under it.
        self.assertNotIn(("x", "a"), where)
        self.assertNotIn(("fallbackModel", "extra"), where)
        # Every key of the merged data has a spot, and lines belong to their own file.
        self.assertTrue(all(isinstance(v["line"], int) for v in where.values()))
        self.assertEqual(where[("env", "A")]["line"], 7)

    def test_managed_data_is_masked_before_it_merges(self):
        self.managed_file({"env": {"MADE_UP_TOKEN": "planted-secret-one"}})
        self.managed_d("10.json", {"env": {"OTHER": "Bearer planted-secret-two"}})
        managed = self.source(self.settings(), "managed")
        self.assertEqual(managed["data"]["env"], {"MADE_UP_TOKEN": "hidden", "OTHER": "hidden"})
        self.assertIn(("env", "MADE_UP_TOKEN"), managed["where"])

    def test_empty_managed_file_is_ok(self):
        base = self.managed_file("")
        empty = self.managed_d("10.json", "")
        result = self.settings()
        self.assertEqual([(f["path"], f["status"], f["line"]) for f in result["files"]],
                         [(base, "ok", None), (empty, "ok", None)])
        self.assertEqual(self.source(result, "managed")["data"], {})

    def test_a_whitespace_only_managed_file_is_unparsed(self):
        path = self.managed_file(" \n\t\n")
        result = self.settings()
        self.assertEqual(result["files"], [
            {"layer": "managed", "path": path, "status": "unparsed", "line": 3}])
        self.assertEqual(result["sources"], [])

    def test_an_empty_ordinary_file_is_unparsed(self):
        path = self.user("")
        result = self.settings()
        self.assertEqual(result["files"], [
            {"layer": "user", "path": path, "status": "unparsed", "line": 1}])
        self.assertEqual(result["sources"], [])

    def test_lines_of_env_and_model_settings(self):
        text = ('{\n'
                '  "model": "x",\n'
                '  "env": {\n'
                '    "FOO": "1",\n'
                '    "BAR": 2\n'
                '  },\n'
                '  "modelSettings": {\n'
                '    "us.anthropic.x-v1:0": {\n'
                '      "effortLevel": "high"\n'
                '    }\n'
                '  }\n'
                '}\n')
        for label, content in (("lf", text), ("crlf", text.replace("\n", "\r\n"))):
            with self.subTest(newlines=label):
                path = self.user(content.encode("utf-8"))
                where = self.source(self.settings(), "user")["where"]
                expected = {("model",): 2, ("env",): 3, ("env", "FOO"): 4, ("env", "BAR"): 5,
                            ("modelSettings",): 7, ("modelSettings", "us.anthropic.x-v1:0"): 8,
                            ("modelSettings", "us.anthropic.x-v1:0", "effortLevel"): 9}
                self.assertEqual({k: v["line"] for k, v in where.items()}, expected)
                self.assertTrue(all(v["path"] == path for v in where.values()))

    def test_invalid_json_is_unparsed_with_its_line(self):
        path = self.user('{\n  "model": "x",\n  "env": oops\n}\n')
        result = self.settings()
        self.assertEqual(result["files"], [
            {"layer": "user", "path": path, "status": "unparsed", "line": 3}])
        self.assertEqual(result["sources"], [])

    def test_a_top_level_list_is_unparsed(self):
        path = self.proj('[\n  {"model": "x"}\n]\n')
        self.assertEqual(self.settings()["files"], [
            {"layer": "project", "path": path, "status": "unparsed", "line": 1}])

    def test_a_scalar_and_non_utf8_are_unparsed(self):
        local = self.local("5")
        user = self.user(b'{"a": "ok"}\n{"b": "\xff"}\n')
        files = self.settings()["files"]
        self.assertEqual([(f["path"], f["status"]) for f in files],
                         [(local, "unparsed"), (user, "unparsed")])
        self.assertEqual(files[0]["line"], 1)
        self.assertIsInstance(files[1]["line"], int)

    def test_unparsed_files_in_every_layer_are_all_reported(self):
        man = self.managed_file("{")
        late = self.managed_d("10.json", "[]")
        loc = self.local("nope")
        result = self.settings()
        self.assertEqual([(f["layer"], f["path"], f["status"]) for f in result["files"]], [
            ("managed", man, "unparsed"), ("managed", late, "unparsed"),
            ("local", loc, "unparsed")])
        self.assertEqual(result["sources"], [])

    def test_one_bad_managed_file_does_not_stop_the_others(self):
        self.managed_file({"model": "base"})
        bad = self.managed_d("10.json", "{")
        self.managed_d("20.json", {"other": 1})
        result = self.settings()
        self.assertEqual(self.source(result, "managed")["data"], {"model": "base", "other": 1})
        self.assertIn((bad, "unparsed"), [(f["path"], f["status"]) for f in result["files"]])

    def test_a_folder_in_place_of_a_file_is_unreadable(self):
        path = os.path.join(self.config, "settings.json")
        os.makedirs(path)
        self.assertEqual(self.settings()["files"], [
            {"layer": "user", "path": path, "status": "unreadable", "line": None}])

    @unittest.skipIf(os.geteuid() == 0, "root reads every file")
    def test_an_unreadable_managed_file(self):
        path = self.managed_file({"model": "m"})
        late = self.managed_d("10.json", {"other": 1})
        self.deny_access(path)
        result = self.settings()
        self.assertEqual(result["files"][0],
                         {"layer": "managed", "path": path, "status": "unreadable", "line": None})
        self.assertEqual(result["files"][1]["path"], late)
        self.assertEqual(self.source(result, "managed")["data"], {"other": 1})

    @unittest.skipIf(os.geteuid() == 0, "root lists every folder")
    def test_an_unlistable_managed_folder(self):
        base = self.managed_file({"model": "m"})
        folder = os.path.join(self.managed, "managed-settings.d")
        os.makedirs(folder)
        self.deny_access(folder)
        result = self.settings()
        self.assertEqual(result["files"], [
            {"layer": "managed", "path": base, "status": "ok", "line": None},
            {"layer": "managed", "path": folder, "status": "unreadable", "line": None}])
        self.assertEqual(self.source(result, "managed")["data"], {"model": "m"})

    def test_paths_are_built_from_the_arguments(self):
        self.user({"model": "u"})
        result = self.settings()
        self.assertEqual(result["files"][0]["path"], os.path.join(self.config, "settings.json"))


class EnvTests(Tree):
    NAMES = ["ANTHROPIC_MODEL", "CLAUDE_CODE_EFFORT_LEVEL"]

    def test_settings_origin_has_path_and_line(self):
        path = self.user('{\n  "env": {\n    "ANTHROPIC_MODEL": "x",\n    "FOO": 7\n  }\n}\n')
        env = collect.collect_env(self.settings()["sources"], {}, self.NAMES)
        self.assertEqual(env, {
            "ANTHROPIC_MODEL": [{"value": "x", "origin": "settings", "layer": "user",
                                 "path": path, "line": 3}],
            "FOO": [{"value": "7", "origin": "settings", "layer": "user",
                     "path": path, "line": 4}]})

    def test_shell_origin_after_the_settings_records(self):
        loc = self.local({"env": {"ANTHROPIC_MODEL": "from-local"}})
        proj = self.proj({"env": {"ANTHROPIC_MODEL": "from-project"}})
        shell = {"ANTHROPIC_MODEL": "from-shell", "CLAUDE_CODE_EFFORT_LEVEL": "high"}
        env = collect.collect_env(self.settings()["sources"], shell, self.NAMES)
        self.assertEqual(env["ANTHROPIC_MODEL"], [
            {"value": "from-local", "origin": "settings", "layer": "local", "path": loc, "line": 3},
            {"value": "from-project", "origin": "settings", "layer": "project", "path": proj,
             "line": 3},
            {"value": "from-shell", "origin": "shell"}])
        self.assertEqual(env["CLAUDE_CODE_EFFORT_LEVEL"], [{"value": "high", "origin": "shell"}])

    def test_a_shell_variable_set_by_a_block_is_kept(self):
        self.user({"env": {"SOMETHING_ELSE": "block"}})
        env = collect.collect_env(self.settings()["sources"], {"SOMETHING_ELSE": "shell"}, [])
        self.assertEqual([r["origin"] for r in env["SOMETHING_ELSE"]], ["settings", "shell"])

    def test_a_managed_env_record_names_the_later_file(self):
        self.managed_file({"env": {"ANTHROPIC_MODEL": "one"}})
        late = self.managed_d("10.json", {"env": {"ANTHROPIC_MODEL": "two"}})
        env = collect.collect_env(self.settings()["sources"], {}, self.NAMES)
        self.assertEqual(env["ANTHROPIC_MODEL"], [
            {"value": "two", "origin": "settings", "layer": "managed", "path": late, "line": 3}])

    def test_env_value_types(self):
        self.user({"env": {"S": "x", "I": 3, "F": 1.5, "B": True, "N": None, "L": [1],
                           "D": {"a": 1}}})
        env = collect.collect_env(self.settings()["sources"], {}, [])
        self.assertEqual({k: v[0]["value"] for k, v in env.items()},
                         {"S": "x", "I": "3", "F": "1.5"})

    def test_a_non_object_env_is_ignored(self):
        self.user({"env": ["A"]})
        self.assertEqual(collect.collect_env(self.settings()["sources"], {}, []), {})

    def test_shell_values_must_be_text(self):
        env = collect.collect_env([], {"ANTHROPIC_MODEL": 5, "CLAUDE_CODE_EFFORT_LEVEL": "low"},
                                  self.NAMES)
        self.assertEqual(env, {"CLAUDE_CODE_EFFORT_LEVEL": [{"value": "low", "origin": "shell"}]})

    def test_an_unnamed_shell_variable_never_leaves_the_collector(self):
        self.user({"env": {"ANTHROPIC_MODEL": "x"}})
        self.write(os.path.join(self.project, ".claude", "agents", "probe.md"), agent_text())
        shell = {"MADE_UP_UNLISTED_NAME": "planted-shell-value-9", "ANTHROPIC_MODEL": "shell"}
        out = self.collect(shell=shell)
        text = dump(out)
        self.assertNotIn("MADE_UP_UNLISTED_NAME", text)
        self.assertNotIn("planted-shell-value-9", text)
        self.assertIn("ANTHROPIC_MODEL", out["env"])

    def test_shell_secrets_under_named_variables_are_masked(self):
        env = collect.collect_env([], {"ANTHROPIC_MODEL": "sk-planted-bravo"}, self.NAMES)
        self.assertEqual(env["ANTHROPIC_MODEL"], [{"value": "hidden", "origin": "shell"}])


class AgentTests(Tree):
    def test_both_folders_and_a_subfolder(self):
        proj_dir = os.path.join(self.project, ".claude", "agents")
        user_dir = os.path.join(self.config, "agents")
        a = self.write(os.path.join(proj_dir, "a.md"),
                       "---\nname: a\ndescription: d\nmodel: opus\neffort: high\n"
                       "experimental:\n  cacheTtl: 1h\n---\nBody\n")
        b = self.write(os.path.join(proj_dir, "team", "b.md"), agent_text(name="b"))
        note = self.write(os.path.join(proj_dir, "notes.txt"), "not an agent\n")
        u = self.write(os.path.join(user_dir, "u.md"), agent_text(name="u"))
        self.write(os.path.join(user_dir, ".hidden.md"), agent_text(name="h"))
        out = collect.collect_agents(self.config, self.project)
        self.assertEqual([(r["layer"], r["path"]) for r in out],
                         [("project", a), ("project", note), ("project", b), ("user", u)])
        first = out[0]
        self.assertEqual(first["errors"], [])
        self.assertEqual(first["fields"]["model"], "opus")
        self.assertEqual(first["lines"]["model"], 4)
        self.assertEqual(first["lines"]["effort"], 5)
        self.assertEqual(first["lines"]["experimental.cacheTtl"], 7)
        self.assertEqual(first["fields"]["experimental"], {"cacheTtl": "1h"})
        self.assertEqual(set(first), {"layer", "path", "fields", "errors", "lines"})

    def test_a_rejected_file_keeps_its_error_kinds(self):
        bad = self.write(os.path.join(self.project, ".claude", "agents", "bad.md"),
                         "---\nname: bad\nmodel: [a\n---\nBody\n")
        nofence = self.write(os.path.join(self.config, "agents", "nofence.md"),
                             "---\nname: x\n")
        plain = self.write(os.path.join(self.config, "agents", "plain.txt"), "just text\n")
        out = {r["path"]: r for r in collect.collect_agents(self.config, self.project)}
        self.assertEqual(len(out), 3)
        self.assertTrue(out[bad]["errors"])
        self.assertEqual(out[nofence]["errors"], ["line 1: missing closing fence"])
        self.assertEqual(out[plain]["errors"], ["line 1: missing opening fence"])
        self.assertEqual(out[plain]["fields"], {})

    def test_an_unreadable_agent_file_is_still_listed(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every file")
        path = self.write(os.path.join(self.config, "agents", "locked.md"), agent_text())
        self.deny_access(path)
        out = collect.collect_agents(self.config, self.project)
        self.assertEqual([r["path"] for r in out], [path])
        self.assertTrue(out[0]["errors"])

    def test_no_file_text_in_the_output(self):
        self.write(os.path.join(self.config, "agents", "a.md"),
                   agent_text() + "BODY-TEXT-THAT-STAYS-OUT\n")
        self.assertNotIn("BODY-TEXT-THAT-STAYS-OUT", dump(collect.collect_agents(
            self.config, self.project)))

    def test_missing_folders_give_nothing(self):
        self.assertEqual(collect.collect_agents(self.config, self.project), [])


class RulesFilesTests(Tree):
    def test_files_are_listed_with_their_scope(self):
        proj_dir = os.path.join(self.project, ".claude", "rules")
        user_dir = os.path.join(self.config, "rules")
        a = self.write(os.path.join(proj_dir, "a.md"), "A\n")
        b = self.write(os.path.join(proj_dir, "sub", "b.md"), "B\n")
        c = self.write(os.path.join(proj_dir, "c.txt"), "C\n")
        self.write(os.path.join(proj_dir, ".hidden.md"), "H\n")
        u = self.write(os.path.join(user_dir, "u.md"), "U\n")
        self.assertEqual(collect.collect_rules_files(self.config, self.project), [
            {"layer": "project", "path": a}, {"layer": "project", "path": c},
            {"layer": "project", "path": b}, {"layer": "user", "path": u}])

    def test_missing_folders_give_nothing(self):
        self.assertEqual(collect.collect_rules_files(self.config, self.project), [])


class CollectTests(Tree):
    def test_exactly_the_five_keys(self):
        out = self.collect()
        self.assertEqual(list(out), ["settings", "settings_files", "env", "agents", "rules_files"])

    def test_a_tiny_tree(self):
        user = self.user({"env": {"ANTHROPIC_MODEL": "x"}, "model": "opus"})
        agent = self.write(os.path.join(self.project, ".claude", "agents", "a.md"), agent_text())
        rule = self.write(os.path.join(self.config, "rules", "r.md"), "R\n")
        out = self.collect(shell={"ANTHROPIC_MODEL": "s"})
        self.assertEqual(out["settings"], [{
            "layer": "user",
            "data": {"env": {"ANTHROPIC_MODEL": "x"}, "model": "opus"},
            "where": {("env",): {"path": user, "line": 2},
                      ("env", "ANTHROPIC_MODEL"): {"path": user, "line": 3},
                      ("model",): {"path": user, "line": 5}}}])
        self.assertEqual(out["settings_files"],
                         [{"layer": "user", "path": user, "status": "ok", "line": None}])
        self.assertEqual(out["env"]["ANTHROPIC_MODEL"][1], {"value": "s", "origin": "shell"})
        self.assertEqual(out["agents"][0]["path"], agent)
        self.assertEqual(out["rules_files"], [{"layer": "user", "path": rule}])

    def test_the_rules_document_names_the_variables(self):
        shell = {"ANTHROPIC_MODEL": "a", "NOT_NAMED": "b"}
        self.assertEqual(list(self.collect(shell=shell)["env"]), ["ANTHROPIC_MODEL"])
        self.assertEqual(self.collect(shell=shell, rules={})["env"], {})
        self.assertEqual(
            list(self.collect(shell=shell, rules={"variables": [{"name": "NOT_NAMED"}]})["env"]),
            ["NOT_NAMED"])

    def test_no_flags_or_other_unseen_sources(self):
        out = self.collect()
        text = dump(out)
        for word in ("--settings", "mdm", "server-managed", "flags"):
            self.assertNotIn(word, text.lower())


class GuardTests(Tree):
    def real_places(self):
        return [pwd.getpwuid(os.getuid()).pw_dir, REAL_MANAGED]

    def populate(self):
        self.user({"env": {"ANTHROPIC_MODEL": "x"}})
        self.proj({"model": "p"})
        self.local({"model": "l"})
        self.managed_file({"model": "m"})
        self.managed_d("10.json", {"other": 1})
        self.write(os.path.join(self.config, "agents", "a.md"), agent_text())
        self.write(os.path.join(self.project, ".claude", "agents", "b", "b.md"), agent_text())
        self.write(os.path.join(self.config, "rules", "r.md"), "R\n")
        self.write(os.path.join(self.project, ".claude", "rules", "r.md"), "R\n")

    def test_the_collectors_stay_out_of_the_real_home_and_managed_folder(self):
        self.populate()
        shell = {"ANTHROPIC_MODEL": "s", "CLAUDE_CODE_EFFORT_LEVEL": "high"}
        with helpers.home_guard(self.real_places(), allowed=[self.root, helpers.REPO]) as seen:
            out = self.collect(shell=shell)
        self.assertEqual(seen, [])
        self.assertEqual(self.layers({"sources": out["settings"]}),
                         ["managed", "local", "project", "user"])

    def test_the_guard_would_see_a_collector_pointed_at_a_home(self):
        fake_home = os.path.join(self.root, "fakehome")
        os.makedirs(os.path.join(fake_home, ".claude"))
        self.write(os.path.join(fake_home, ".claude", "settings.json"), {"model": "x"})
        with helpers.home_guard([fake_home], allowed=[helpers.REPO]) as seen:
            collect.collect(os.path.join(fake_home, ".claude"), self.project, None, {}, {})
        self.assertTrue(seen)

    def test_no_expanduser_no_path_home_no_environ(self):
        self.populate()

        class NoEnviron(dict):
            def _refuse(self, *_args, **_kwargs):
                raise AssertionError("collect read os.environ")
            __getitem__ = get = __contains__ = __iter__ = items = keys = values = _refuse

        with helpers.home_guard(self.real_places(), allowed=[self.root, helpers.REPO]):
            with mock.patch.object(os, "environ", NoEnviron()):
                self.collect(shell={"ANTHROPIC_MODEL": "s"})

    def test_a_variable_in_the_test_process_is_not_read_from_the_environment(self):
        # The shell comes in as an argument. Setting a named variable in this
        # process changes nothing.
        self.populate()
        with mock.patch.dict(os.environ, {"ANTHROPIC_MODEL": "from-os-environ"}):
            out = self.collect(shell={})
        self.assertNotIn("from-os-environ", dump(out))
        self.assertEqual(out["env"].get("ANTHROPIC_MODEL", [{}])[0].get("origin"), "settings")


class WriteTests(Tree):
    def snapshot(self):
        found = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            for name in dirnames + filenames:
                full = os.path.join(dirpath, name)
                info = os.lstat(full)
                found[os.path.relpath(full, self.root)] = (
                    info.st_size, info.st_mtime_ns, info.st_mode)
        info = os.lstat(self.root)
        found["."] = (info.st_size, info.st_mtime_ns, info.st_mode)
        return found

    def test_collect_writes_nothing(self):
        self.user({"env": {"ANTHROPIC_MODEL": "x"}})
        self.proj("{ not json")
        self.managed_file({"model": "m"})
        self.managed_d("10.json", {"other": 1})
        self.write(os.path.join(self.config, "agents", "a.md"), agent_text())
        self.write(os.path.join(self.config, "rules", "r.md"), "R\n")
        before = self.snapshot()
        self.collect(shell={"ANTHROPIC_MODEL": "s"})
        self.assertEqual(self.snapshot(), before)


class MaskingTests(Tree):
    """Made-up secrets planted in four places never leave the collectors."""
    PLANTED = ("planted-secret-alpha", "planted-secret-bravo", "planted-secret-charlie",
               "planted-secret-delta", "planted-secret-echo")

    def setUp(self):
        super().setUp()
        self.user_path = self.user(
            '{\n  "env": {\n    "MADE_UP_TOKEN": "planted-secret-alpha",\n'
            '    "ANTHROPIC_MODEL": "visible"\n  }\n}\n')
        self.managed_path = self.managed_file(
            '{\n  "env": {\n    "MADE_UP_PASSWORD": "planted-secret-charlie"\n  },\n'
            '  "madeUpApiKey": "planted-secret-delta"\n}\n')
        self.agent_path = self.write(
            os.path.join(self.config, "agents", "probe.md"),
            "---\nname: probe\ndescription: Made-up agent.\nmadeUpSecret: planted-secret-echo\n"
            "hooks:\n  PreToolUse: Bearer planted-secret-bravo\n---\nBody.\n")
        self.out = self.collect(shell={"MADE_UP_TOKEN": "planted-secret-bravo",
                                       "ANTHROPIC_MODEL": "shell-visible"})

    def test_no_planted_value_is_in_the_output(self):
        text = dump(self.out)
        for planted in self.PLANTED:
            with self.subTest(planted=planted):
                self.assertNotIn(planted, text)

    def test_settings_env_value_is_hidden_with_its_place(self):
        records = self.out["env"]["MADE_UP_TOKEN"]
        self.assertEqual(records, [
            {"value": "hidden", "origin": "settings", "layer": "user",
             "path": self.user_path, "line": 3},
            {"value": "hidden", "origin": "shell"}])
        self.assertEqual(self.out["env"]["ANTHROPIC_MODEL"][0]["value"], "visible")

    def test_managed_values_are_hidden_with_their_place(self):
        managed = self.source({"sources": self.out["settings"]}, "managed")
        self.assertEqual(managed["data"], {"env": {"MADE_UP_PASSWORD": "hidden"},
                                           "madeUpApiKey": "hidden"})
        self.assertEqual(managed["where"][("env", "MADE_UP_PASSWORD")],
                         {"path": self.managed_path, "line": 3})
        self.assertEqual(managed["where"][("madeUpApiKey",)],
                         {"path": self.managed_path, "line": 5})
        records = self.out["env"]["MADE_UP_PASSWORD"]
        self.assertEqual(records, [
            {"value": "hidden", "origin": "settings", "layer": "managed",
             "path": self.managed_path, "line": 3}])

    def test_agent_fields_are_hidden_with_their_lines(self):
        agent = self.out["agents"][0]
        self.assertEqual(agent["path"], self.agent_path)
        self.assertEqual(agent["errors"], [])
        self.assertEqual(agent["fields"]["madeUpSecret"], "hidden")
        self.assertEqual(agent["fields"]["hooks"], {"PreToolUse": "hidden"})
        self.assertEqual(agent["fields"]["name"], "probe")
        self.assertEqual(agent["lines"]["madeUpSecret"], 4)
        self.assertEqual(agent["lines"]["hooks.PreToolUse"], 6)

    def test_value_patterns_hide_under_harmless_names(self):
        self.write(os.path.join(self.config, "agents", "q.md"),
                   agent_text("note: sk-planted-foxtrot\n", name="q"))
        self.user({"env": {"NOTE": "sk-planted-golf", "OTHER": "Bearer planted-hotel"},
                   "model": "Bearer planted-india"})
        out = self.collect()
        text = dump(out)
        for planted in ("planted-foxtrot", "planted-golf", "planted-hotel", "planted-india"):
            self.assertNotIn(planted, text)
        self.assertEqual(out["env"]["NOTE"][0]["value"], "hidden")
        self.assertEqual(out["env"]["OTHER"][0]["value"], "hidden")
        user = self.source({"sources": out["settings"]}, "user")
        self.assertEqual(user["data"]["model"], "hidden")
        self.assertEqual(user["where"][("model",)]["line"], 6)


if __name__ == "__main__":
    unittest.main()

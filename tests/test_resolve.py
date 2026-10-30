"""Tests for the settings resolver (dashboard/resolve.py).

One test per fixture folder in tests/fixtures/resolution, then unit tests for
the parts of the resolver. Every run reads only the repo and its own temp
folders. A guard test fails if the resolver touches a path under the real home
or calls os.path.expanduser.
"""
import builtins
import contextlib
import copy
import dataclasses
import io
import json
import os
import pwd
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import helpers
from helpers import home_guard

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import collect  # noqa: E402
import resolve  # noqa: E402
import rules_schema  # noqa: E402

FIXTURE_DIR = os.path.join(helpers.REPO, "tests", "fixtures", "resolution")
REAL_MANAGED = "/Library/Application Support/ClaudeCode"
RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()


def _fixture_names():
    return sorted(
        name for name in os.listdir(FIXTURE_DIR)
        if os.path.isfile(os.path.join(FIXTURE_DIR, name, "expected.json")))


class FixtureTests(unittest.TestCase):
    """One method per fixture folder, added below."""


def _make_fixture_test(name):
    def test(self):
        inputs, expected = resolve.load_fixture(os.path.join(FIXTURE_DIR, name))
        messages = resolve.compare(resolve.resolve(inputs, RULES, FIELDS), expected)
        self.assertEqual(messages, [])
    test.__name__ = "test_" + name.replace("-", "_")
    return test


for _name in _fixture_names():
    _test = _make_fixture_test(_name)
    setattr(FixtureTests, _test.__name__, _test)


class GuardTests(unittest.TestCase):
    def test_resolver_stays_out_of_the_real_home(self):
        home = pwd.getpwuid(os.getuid()).pw_dir
        with home_guard([home], allowed=[helpers.REPO]) as seen:
            for name in _fixture_names():
                inputs, _expected = resolve.load_fixture(os.path.join(FIXTURE_DIR, name))
                resolve.resolve(inputs, RULES, FIELDS)
        self.assertEqual(seen, [])

    def test_the_guard_sees_every_way_to_read_a_home(self):
        # A throwaway folder stands in for the home, so the real one is never read.
        import pathlib
        tmp = tempfile.mkdtemp(prefix="guard-", dir=helpers._tmp_base())
        self.addCleanup(shutil.rmtree, tmp, True)
        fake = os.path.join(tmp, "home")
        os.makedirs(os.path.join(fake, ".claude"))
        note = os.path.join(fake, "notes.txt")
        _write(note, "x")
        link = os.path.join(tmp, "link")
        os.symlink(fake, link)
        probes = {
            "open": lambda: open(note).close(),
            "io.open": lambda: io.open(note).close(),
            "os.open": lambda: os.close(os.open(note, os.O_RDONLY)),
            "os.stat": lambda: os.stat(fake),
            "os.lstat": lambda: os.lstat(fake),
            "os.access": lambda: os.access(fake, os.R_OK),
            "os.listdir": lambda: os.listdir(fake),
            "os.scandir": lambda: list(os.scandir(fake)),
            "os.walk": lambda: list(os.walk(fake)),
            "os.path.exists": lambda: os.path.exists(os.path.join(fake, ".claude")),
            "os.path.isdir": lambda: os.path.isdir(fake),
            "Path.exists": lambda: pathlib.Path(fake, ".claude").exists(),
            "Path.read_text": lambda: pathlib.Path(note).read_text(),
            "Path.read_bytes": lambda: pathlib.Path(note).read_bytes(),
            "Path.iterdir": lambda: list(pathlib.Path(fake).iterdir()),
            "Path.open": lambda: pathlib.Path(note).open().close(),
            "Path.is_dir": lambda: pathlib.Path(fake).is_dir(),
            "Path.resolve": lambda: pathlib.Path(fake).resolve(),
            "a symlink into the home": lambda: os.listdir(link),
            "a symlink to a file in the home": lambda: open(os.path.join(link, "notes.txt")).close(),
        }
        for label, probe in probes.items():
            with self.subTest(probe=label):
                with home_guard([fake]) as seen:
                    probe()
                self.assertTrue(seen, label + " was not caught")
        with self.subTest(probe="a path outside the home"):
            with home_guard([fake]) as seen:
                os.listdir(tmp)
            self.assertEqual(seen, [])
        with self.subTest(probe="the repo, when allowed"):
            with home_guard([helpers.REPO], allowed=[helpers.REPO]) as seen:
                os.listdir(helpers.REPO)
            self.assertEqual(seen, [])
        for label, call in (("Path.home", lambda: pathlib.Path.home()),
                            ("os.path.expanduser", lambda: os.path.expanduser("~"))):
            with self.subTest(probe=label):
                with home_guard([fake]):
                    with self.assertRaises(AssertionError):
                        call()

    def test_resolve_does_not_change_the_rules(self):
        before = copy.deepcopy(RULES)
        for name in _fixture_names():
            inputs, _expected = resolve.load_fixture(os.path.join(FIXTURE_DIR, name))
            resolve.resolve(inputs, RULES, FIELDS)
        self.assertEqual(RULES, before)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content if isinstance(content, str) else json.dumps(content))


def pretty(obj):
    """JSON text with one key per line, so a key's line number is not 1."""
    return json.dumps(obj, indent=2) + "\n"


def agent_text(name="probe", description="Made-up agent.", model=None, extra=""):
    lines = ["---"]
    if name is not None:
        lines.append("name: %s" % name)
    if description is not None:
        lines.append("description: %s" % description)
    if model is not None:
        lines.append("model: %s" % model)
    if extra:
        lines.append(extra)
    lines.append("---")
    lines.append("You are a probe.")
    return "\n".join(lines) + "\n"


class ResolveCase(unittest.TestCase):
    """Builds throwaway config and project folders, then resolves them."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="resolve-", dir=helpers._tmp_base())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make_inputs(self, user=None, project=None, local=None, user_agents=None,
                    project_agents=None, user_rules=None, project_rules=None,
                    shell_env=None, flags=None, cli=None, plan=None, managed=None,
                    rules=RULES, home=None, root=True, managed_mode=None,
                    shell_label=resolve.LABEL_SHELL):
        """Write the files, run the collectors and return the resolver's Inputs.

        `managed` is written to managed/managed-settings.json in the throwaway
        tree, then given the file mode `managed_mode` when that is set. The
        shell label is the fixtures' one, so shell entries read
        session.json:shell_env. `root` False leaves the paths absolute.
        """
        config = os.path.join(self.tmp, "config")
        proj = os.path.join(self.tmp, "project")
        os.makedirs(config, exist_ok=True)
        os.makedirs(proj, exist_ok=True)
        if user is not None:
            _write(os.path.join(config, "settings.json"), user)
        if project is not None:
            _write(os.path.join(proj, ".claude", "settings.json"), project)
        if local is not None:
            _write(os.path.join(proj, ".claude", "settings.local.json"), local)
        if managed is not None:
            path = os.path.join(self.tmp, "managed", "managed-settings.json")
            _write(path, managed)
            if managed_mode is not None:
                os.chmod(path, managed_mode)
                self.addCleanup(os.chmod, path, 0o600)
        for rel, text in (user_agents or {}).items():
            _write(os.path.join(config, "agents", rel), text)
        for rel, text in (project_agents or {}).items():
            _write(os.path.join(proj, ".claude", "agents", rel), text)
        for rel, text in (user_rules or {}).items():
            _write(os.path.join(config, "rules", rel), text)
        for rel, text in (project_rules or {}).items():
            _write(os.path.join(proj, ".claude", "rules", rel), text)
        collected = collect.collect(
            config_dir=config, project_dir=proj,
            managed_dir=os.path.join(self.tmp, "managed"),
            shell_env=shell_env or {}, rules=rules)
        return resolve.Inputs(
            collected=collected, flags=flags or [], cli_settings=cli, plan=plan,
            home=home, root=self.tmp if root else None, shell_label=shell_label)

    def run_resolve(self, rules=RULES, **kw):
        return resolve.resolve(self.make_inputs(rules=rules, **kw), rules, FIELDS)

    @staticmethod
    def rows(entries, key, scope="main", agent=None):
        return [e for e in entries
                if e["key"] == key and e["scope"] == scope and e.get("agent") == agent]

    def only(self, entries, key, scope="main", agent=None):
        found = self.rows(entries, key, scope, agent)
        self.assertEqual(len(found), 1, found)
        return found[0]

    @staticmethod
    def brief(entries):
        return [(e["layer"], e["value"], e["status"]) for e in entries]


class EnvBlockTests(ResolveCase):
    def test_shell_alone_is_in_effect(self):
        entries = self.run_resolve(shell_env={"ANTHROPIC_MODEL": "a"})
        entry = self.only(entries, "env.ANTHROPIC_MODEL")
        self.assertEqual((entry["layer"], entry["file"], entry["status"], entry["value"]),
                         ("env", "session.json:shell_env", "in_effect", "a"))

    def test_settings_block_overwrites_the_shell(self):
        entries = self.run_resolve(user={"env": {"FOO": "block"}}, shell_env={"FOO": "shell"})
        got = self.rows(entries, "env.FOO")
        self.assertEqual(self.brief(got), [("user", "block", "in_effect"),
                                           ("env", "shell", "overridden")])
        self.assertEqual(got[0]["file"], "config/settings.json")

    def test_higher_file_wins_between_blocks(self):
        entries = self.run_resolve(
            user={"env": {"FOO": "user"}}, project={"env": {"FOO": "project"}},
            local={"env": {"FOO": "local"}}, cli={"env": {"FOO": "cli"}},
            managed={"env": {"FOO": "managed"}}, shell_env={"FOO": "shell"})
        got = self.rows(entries, "env.FOO")
        self.assertEqual([e["layer"] for e in got],
                         ["managed", "cli", "local", "project", "user", "env"])
        self.assertEqual([e["status"] for e in got], ["in_effect"] + ["overridden"] * 5)

    def test_block_value_feeds_the_variable_row(self):
        entries = self.run_resolve(user={"env": {"ANTHROPIC_MODEL": "claude-opus-5-5"}})
        model = self.only(entries, "model")
        self.assertEqual((model["layer"], model["file"], model["via"], model["value"]),
                         ("env", "config/settings.json", "ANTHROPIC_MODEL", "claude-opus-5-5"))

    def test_a_number_in_a_block_reads_as_text(self):
        entries = self.run_resolve(user={"env": {"FOO": 5}})
        self.assertEqual(self.only(entries, "env.FOO")["value"], "5")

    def test_a_settings_file_that_is_not_json_is_left_out(self):
        config = os.path.join(self.tmp, "config")
        _write(os.path.join(config, "settings.json"), "{not json")
        entries = self.run_resolve()
        self.assertEqual(self.rows(entries, "model")[0]["status"], "unknown")


class ModelNameTests(unittest.TestCase):
    CATALOG = RULES["models"]

    def test_every_name_form(self):
        cases = [
            ("claude-opus-5-5", ("claude-opus-5-5", "canonical")),
            ("claude-opus-5", ("claude-opus-5", "canonical")),
            ("opus", ("claude-opus-5-5", "alias")),
            ("sonnet", ("claude-sonnet-5-5", "alias")),
            ("claude-opus-5-5[1m]", ("claude-opus-5-5", "context_1m")),
            ("claude-opus-5-5-20261001", ("claude-opus-5-5", "dated")),
            ("us.anthropic.claude-opus-5-5-v1:0", ("claude-opus-5-5", "provider")),
            ("claude-opus-5-5@20261001", ("claude-opus-5-5", "provider")),
            ("claude-opus-9", (None, None)),
            ("claude-opus-5-5-2026", (None, None)),
            ("opus[1m]", (None, None)),
            ("", (None, None)),
            (None, (None, None)),
            (5, (None, None)),
        ]
        for name, want in cases:
            with self.subTest(name=name):
                self.assertEqual(resolve.normalize_model(name, self.CATALOG), want)

    def test_forms_match_the_schema_list(self):
        found = {resolve.normalize_model(n, self.CATALOG)[1] for n in (
            "claude-opus-5-5", "opus", "claude-opus-5-5-20261001", "claude-opus-5-5[1m]",
            "claude-opus-5-5@20261001")}
        self.assertEqual(found, set(rules_schema.NAME_FORMS))

    def test_read_number(self):
        cases = [(200000, 200000), ("200000", 200000), ("200k", 200), ("200", 200),
                 ("abc", None), ("", None), (True, None), (None, None), (1.5, None),
                 ("-5", None), (" 5", None)]
        for value, want in cases:
            with self.subTest(value=value):
                self.assertEqual(resolve.read_number(value), want)

    def test_flags(self):
        flags = ["--effort", "low", "--model=opus", "--effort", "high", "--other", "x",
                 "--autocompact"]
        self.assertEqual(resolve.parse_flags(flags), {"--effort": "high", "--model": "opus"})


class TieTests(ResolveCase):
    def test_per_model_entry_beats_the_top_level_key_in_one_file(self):
        entries = self.run_resolve(user={
            "model": "claude-opus-5-5", "autoCompactWindow": 200000,
            "modelSettings": {"claude-opus-5-5": {"autoCompactWindow": 300000}}})
        got = self.rows(entries, "autoCompactWindow")
        self.assertEqual([(e["value"], e["status"]) for e in got],
                         [(300000, "in_effect"), (200000, "overridden")])
        self.assertEqual(got[0]["path"], "modelSettings.claude-opus-5-5.autoCompactWindow")

    def test_canonical_beats_alias_in_either_key_order(self):
        for order in (("opus", "claude-opus-5-5"), ("claude-opus-5-5", "opus")):
            settings = {"model": "claude-opus-5-5", "modelSettings": {
                order[0]: {"effortLevel": "low" if order[0] == "opus" else "high"},
                order[1]: {"effortLevel": "high" if order[1] == "claude-opus-5-5" else "low"}}}
            with self.subTest(order=order):
                entries = self.run_resolve(user=settings)
                got = self.rows(entries, "effortLevel")
                self.assertEqual([(e["value"], e["status"]) for e in got],
                                 [("high", "in_effect"), ("low", "overridden")])

    def test_other_forms_rank_by_the_schema_order(self):
        settings = {"model": "claude-opus-5-5", "modelSettings": {
            "claude-opus-5-5-20261001": {"effortLevel": "low"}, "opus": {"effortLevel": "high"}}}
        got = self.rows(self.run_resolve(user=settings), "effortLevel")
        self.assertEqual([e["path"] for e in got],
                         ["modelSettings.opus.effortLevel",
                          "modelSettings.claude-opus-5-5-20261001.effortLevel"])

    def test_a_model_setting_for_another_model_is_not_a_candidate(self):
        settings = {"model": "claude-opus-5-5", "modelSettings": {
            "sonnet": {"effortLevel": "low"}, "claude-opus-9": {"effortLevel": "low"}}}
        got = self.rows(self.run_resolve(user=settings), "effortLevel")
        self.assertEqual(self.brief(got), [("default", "medium", "default")])

    def test_two_variables_in_one_layer_rank_by_their_order(self):
        env = {"CLAUDE_CODE_PROMPT_CACHE_TTL": "1h", "FORCE_PROMPT_CACHING_5M": "1"}
        got = self.rows(self.run_resolve(shell_env=env, user={"model": "claude-sonnet-5-5"}),
                        "promptCacheTtl")
        self.assertEqual([(e["via"], e["status"]) for e in got],
                         [("FORCE_PROMPT_CACHING_5M", "in_effect"),
                          ("CLAUDE_CODE_PROMPT_CACHE_TTL", "overridden")])

    def test_two_agent_files_in_one_layer_stay_tied(self):
        agents = {"a/probe.md": agent_text(model="claude-haiku-5-5"),
                  "z/probe.md": agent_text(model="claude-sonnet-5-5")}
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"}, user_agents=agents)
        self.assertEqual([e["status"] for e in self.rows(entries, "agentFile", "agent", "probe")],
                         ["unknown", "unknown"])
        self.assertEqual([e["status"] for e in self.rows(entries, "model", "agent", "probe")],
                         ["unknown", "unknown"])

    def test_project_file_beats_user_file_and_names_the_other(self):
        entries = self.run_resolve(
            user_agents={"probe.md": agent_text()}, project_agents={"probe.md": agent_text()})
        got = self.rows(entries, "agentFile", "agent", "probe")
        self.assertEqual([(e["layer"], e["status"]) for e in got],
                         [("project", "in_effect"), ("user", "overridden")])
        self.assertEqual(got[0]["other_file"], "config/agents/probe.md")
        self.assertEqual(got[1]["other_file"], "project/.claude/agents/probe.md")


class CeilingTests(ResolveCase):
    def agent_row(self, frontmatter, user=None, env=None):
        agents = {"probe.md": agent_text(model="claude-haiku-5-5",
                                         extra="autoCompactWindow: %s" % frontmatter
                                         if frontmatter is not None else "")}
        settings = {"model": "claude-sonnet-5-5"}
        if user is not None:
            settings["autoCompactWindow"] = user
        entries = self.run_resolve(user=settings, user_agents=agents, shell_env=env)
        return self.rows(entries, "autoCompactWindow", "agent", "probe")

    def test_frontmatter_below_the_settings_value_wins(self):
        got = self.agent_row(200000, user=500000)
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in got],
                         [("agent", 200000, "in_effect"), ("user", 500000, "overridden")])

    def test_frontmatter_above_the_settings_value_loses(self):
        got = self.agent_row(600000, user=500000)
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in got],
                         [("user", 500000, "in_effect"), ("agent", 600000, "overridden")])

    def test_frontmatter_equal_to_the_settings_value_loses(self):
        got = self.agent_row(500000, user=500000)
        self.assertEqual([(e["layer"], e["status"]) for e in got],
                         [("user", "in_effect"), ("agent", "overridden")])

    def test_the_env_variable_beats_the_frontmatter(self):
        got = self.agent_row(200000, user=500000,
                             env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "400000"})
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in got],
                         [("env", 400000, "in_effect"), ("agent", 200000, "overridden"),
                          ("user", 500000, "overridden")])

    def test_frontmatter_alone_is_unknown_when_the_session_window_is_unknown(self):
        got = self.agent_row(200000)
        self.assertEqual([(e["layer"], e["status"]) for e in got], [("agent", "unknown")])

    def test_settings_alone_win(self):
        got = self.agent_row(None, user=500000)
        self.assertEqual([(e["layer"], e["status"]) for e in got], [("user", "in_effect")])


class RangeTests(ResolveCase):
    def window(self, value, where="env"):
        if where == "env":
            entries = self.run_resolve(user={"model": "claude-opus-5-5"},
                                       shell_env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": value})
        else:
            entries = self.run_resolve(user={"model": "claude-opus-5-5",
                                             "autoCompactWindow": value})
        return next(e for e in self.rows(entries, "autoCompactWindow")
                    if e["layer"] != "default")

    def test_env_values(self):
        cases = [
            ("100000", 100000, "in_effect", None),
            ("1000000", 1000000, "in_effect", None),
            ("99999", 99999, "in_effect", 100000),
            ("50000", 50000, "in_effect", 100000),
            ("200k", "200k", "in_effect", 100000),
            ("200", 200, "in_effect", 100000),
            ("1000001", 1000001, "lowered", 1000000),
            ("2000000", 2000000, "lowered", 1000000),
            ("abc", "abc", "ignored", None),
            ("", "", "ignored", None),
        ]
        for text, value, status, becomes in cases:
            with self.subTest(text=text):
                entry = self.window(text)
                self.assertEqual((entry["value"], entry["status"], entry.get("becomes")),
                                 (value, status, becomes))

    def test_digits_show_as_an_integer(self):
        self.assertIsInstance(self.window("300000")["value"], int)

    def test_settings_values(self):
        low = self.window(50000, "user")
        self.assertEqual((low["status"], "becomes" in low), ("ignored", False))
        self.assertEqual(self.window(100000, "user")["status"], "in_effect")
        self.assertEqual(self.window(99999, "user")["status"], "ignored")

    def test_a_clamped_value_still_wins(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5", "autoCompactWindow": 300000},
                                   shell_env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "50000"})
        got = self.rows(entries, "autoCompactWindow")
        self.assertEqual([(e["layer"], e["status"]) for e in got],
                         [("env", "in_effect"), ("user", "overridden")])

    def test_a_clamped_entry_shows_the_values_rule_reason(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5"},
                                   shell_env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "50000"})
        entry = next(e for e in self.rows(entries, "autoCompactWindow")
                     if e["layer"] == "env")
        self.assertEqual(entry["becomes"], 100000)
        self.assertEqual(entry["rule_id"], "auto-compact-window-values")
        self.assertIn("It raises a value below 100000 to 100000, so that value still shows In effect.", entry["reason"])

    def test_a_forced_agent_model_shows_the_force_rule_reason(self):
        entries = self.run_resolve(
            user={"model": "claude-sonnet-5-5"},
            user_agents={"probe.md": agent_text(model="claude-haiku-5-5")},
            shell_env={"CLAUDE_CODE_SUBAGENT_MODEL": "claude-fable-5-1",
                       "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"})
        winner = next(e for e in self.rows(entries, "model", "agent", "probe")
                      if e["status"] == "in_effect")
        self.assertEqual(winner["rule_id"], "subagent-model-force")
        self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL_FORCE is on", winner["reason"])
        self.assertEqual(winner["rule_ids"][0], "subagent-model-force")

    def test_without_the_force_variable_the_order_rule_explains_the_agent_model(self):
        entries = self.run_resolve(
            user={"model": "claude-sonnet-5-5"},
            user_agents={"probe.md": agent_text()},
            shell_env={"CLAUDE_CODE_SUBAGENT_MODEL": "claude-fable-5-1"})
        winner = next(e for e in self.rows(entries, "model", "agent", "probe")
                      if e["status"] == "in_effect")
        self.assertEqual(winner["rule_id"], "subagent-model-order")


class DefaultEntryTests(ResolveCase):
    def test_effort_default_comes_from_the_catalog(self):
        entry = self.only(self.run_resolve(user={"model": "claude-opus-5-5"}), "effortLevel")
        self.assertEqual((entry["value"], entry["status"], entry["layer"], entry["file"],
                          entry["rule_id"]),
                         ("medium", "default", "default", None, "effort-default-by-model"))

    def test_a_model_without_effort_levels_has_no_default(self):
        entry = self.only(self.run_resolve(user={"model": "claude-haiku-4-5"}), "effortLevel")
        self.assertEqual((entry["value"], entry["status"]), (None, "default"))

    def test_a_default_above_the_cap_is_lowered(self):
        entries = self.run_resolve(user={"model": "claude-opus-4-7", "maxEffortLevel": "high"})
        entry = self.only(entries, "effortLevel")
        self.assertEqual((entry["value"], entry["status"], entry["becomes"]),
                         ("xhigh", "lowered", "high"))

    def test_a_main_model_nothing_sets_is_unknown_with_a_rule(self):
        entry = self.only(self.run_resolve(), "model")
        self.assertEqual((entry["value"], entry["status"], entry["rule_id"], entry["rule_ids"]),
                         (None, "unknown", "model-main-default",
                          ["model-main-default", "model-main-session-order"]))
        self.assertNotEqual(entry["reason"], "")

    def test_cache_default_follows_the_plan(self):
        for plan, value, status in (("api_key", "5m", "default"), ("cloud_provider", "5m", "default"),
                                    ("subscription", None, "unknown"), (None, None, "unknown")):
            with self.subTest(plan=plan):
                entry = self.only(self.run_resolve(plan=plan), "promptCacheTtl")
                self.assertEqual((entry["value"], entry["status"]), (value, status))

    def test_auto_compact_window_default_is_unknown_off_opus_5_5(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"})
        entry = self.only(entries, "autoCompactWindow")
        self.assertEqual((entry["value"], entry["status"], entry["layer"]),
                         (None, "unknown", "default"))

    def test_subagent_cache_default_is_five_minutes(self):
        entries = self.run_resolve(user_agents={"probe.md": agent_text()})
        entry = self.only(entries, "subagentPromptCacheTtl", "agent", "probe")
        self.assertEqual((entry["value"], entry["status"]), ("5m", "default"))

    def test_an_agent_with_no_model_runs_on_the_main_model(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"},
                                   user_agents={"probe.md": agent_text()})
        entry = self.only(entries, "model", "agent", "probe")
        self.assertEqual((entry["value"], entry["status"], entry["layer"]),
                         ("claude-sonnet-5-5", "default", "default"))

    def test_enable_1h_alone_is_in_effect(self):
        entries = self.run_resolve(shell_env={"ENABLE_PROMPT_CACHING_1H": "1"})
        entry = self.only(entries, "promptCacheTtl")
        self.assertEqual((entry["value"], entry["status"], entry["layer"], entry["via"]),
                         ("1h", "in_effect", "default", "ENABLE_PROMPT_CACHING_1H"))

    def test_enable_1h_loses_to_a_settings_value(self):
        entries = self.run_resolve(project={"promptCacheTtl": "5m"},
                                   shell_env={"ENABLE_PROMPT_CACHING_1H": "1"})
        self.assertEqual([(e["layer"], e["status"]) for e in self.rows(entries, "promptCacheTtl")],
                         [("project", "in_effect"), ("default", "overridden")])

    def test_force_5m_needs_a_non_empty_value(self):
        entries = self.run_resolve(project={"promptCacheTtl": "1h"},
                                   shell_env={"FORCE_PROMPT_CACHING_5M": ""})
        self.assertEqual([(e["layer"], e["status"]) for e in self.rows(entries, "promptCacheTtl")],
                         [("project", "in_effect")])


class ExplanationTests(ResolveCase):
    """Which rule explains an entry: the order rule for a loser, the most specific voter for a winner."""

    def test_an_overridden_effort_entry_is_explained_by_the_row_order(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"},
                                   project={"effortLevel": "low"},
                                   shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "high"})
        got = self.rows(entries, "effortLevel")
        self.assertEqual([(e["layer"], e["status"]) for e in got],
                         [("env", "in_effect"), ("project", "overridden")])
        loser = got[1]
        self.assertEqual((loser["rule_id"], loser["rule_ids"]),
                         ("effort-level-layer-order", ["effort-level-layer-order"]))
        self.assertTrue(loser["reason"].startswith("CLAUDE_CODE_EFFORT_LEVEL decides the effort."))

    def test_the_order_rule_is_the_widest_rule_of_the_row_not_a_narrow_one(self):
        # effort-level-user-settings-opus-5-5 comes first in rules.json but names one layer.
        ctx = resolve._Context(self.make_inputs(), RULES, FIELDS)
        for scope, key, wanted in (
                ("main", "effortLevel", "effort-level-layer-order"),
                ("main", "autoCompactWindow", "auto-compact-window-order"),
                ("main", "promptCacheTtl", "prompt-cache-ttl-order"),
                ("main", "maxEffortLevel", "max-effort-level-lowest-cap"),
                ("agent", "effort", "agent-effort-order"),
                ("agent", "model", "subagent-model-order"),
                ("agent", "autoCompactWindow", "agent-auto-compact-window"),
                ("agent", "agentFile", "agent-file-location-order")):
            with self.subTest(row=(scope, key)):
                row = {"key": key, "scope": scope, "agent": None, "model": None}
                self.assertEqual(resolve._row_plan(ctx, row, [])[1]["rule_id"], wanted)

    def test_an_overridden_agent_entry_is_explained_by_the_agent_order(self):
        entries = self.run_resolve(
            user={"model": "claude-sonnet-5-5"},
            user_agents={"probe.md": agent_text(model="claude-haiku-5-5", extra="effort: high")},
            shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "low"})
        loser = next(e for e in self.rows(entries, "effort", "agent", "probe")
                     if e["status"] == "overridden")
        self.assertEqual((loser["layer"], loser["rule_id"]), ("agent", "agent-effort-order"))

    def test_a_winner_prefers_the_voter_with_a_range(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5"},
                                   shell_env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "300000"})
        winner = self.only(entries, "autoCompactWindow")
        self.assertEqual(winner["rule_ids"], ["auto-compact-window-values", "auto-compact-window-order"])
        self.assertEqual(winner["rule_id"], "auto-compact-window-values")

    def test_a_winner_prefers_the_voter_with_a_name_form(self):
        entries = self.run_resolve(user={
            "model": "claude-opus-5-5",
            "modelSettings": {"claude-opus-5-5": {"effortLevel": "low"}}})
        winner = next(e for e in self.rows(entries, "effortLevel") if e["status"] == "in_effect")
        self.assertEqual(winner["rule_id"], "model-settings-name-matching")
        # an alias entry matches no name_form condition, so the plain voter comes first
        entries = self.run_resolve(user={
            "model": "claude-opus-5-5", "modelSettings": {"opus": {"effortLevel": "low"}}})
        winner = next(e for e in self.rows(entries, "effortLevel") if e["status"] == "in_effect")
        self.assertEqual(winner["rule_id"], "model-settings-effort-per-model")

    def test_a_plain_voter_still_wins_on_rules_json_order(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5", "autoCompactWindow": "abc"})
        winner = self.only(entries, "autoCompactWindow")
        self.assertEqual(winner["rule_id"], "auto-compact-window-order")

    def test_a_winner_lists_its_voters_then_the_order_rule_only(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"},
                                   flags=["--effort", "high"])
        winner = next(e for e in self.rows(entries, "effortLevel") if e["status"] == "in_effect")
        self.assertEqual(winner["rule_ids"], ["effort-level-layer-order", "effort-flag-values"])

    def test_force_and_the_model_variable_leave_force_alone_out_of_the_ignored_entry(self):
        entries = self.run_resolve(
            user={"model": "claude-opus-5-5"},
            user_agents={"probe.md": agent_text(model="claude-haiku-5-5")},
            shell_env={"CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
                       "CLAUDE_CODE_SUBAGENT_MODEL": "claude-fable-5-1"})
        ignored = next(e for e in self.rows(entries, "model", "agent", "probe")
                       if e["status"] == "ignored")
        self.assertEqual(ignored["rule_ids"], ["subagent-model-force"])
        self.assertNotIn("subagent-model-force-alone", ignored["rule_ids"])

    def test_force_alone_explains_the_default_and_the_ignored_entry(self):
        entries = self.run_resolve(
            user={"model": "claude-opus-5-5"},
            user_agents={"probe.md": agent_text(model="claude-haiku-5-5")},
            shell_env={"CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"})
        for entry in self.rows(entries, "model", "agent", "probe"):
            with self.subTest(status=entry["status"]):
                self.assertEqual(entry["rule_id"], "subagent-model-force-alone")
        winner = next(e for e in self.rows(entries, "model", "agent", "probe")
                      if e["status"] == "default")
        self.assertEqual((winner["value"], winner["rule_ids"]),
                         ("claude-opus-5-5", ["subagent-model-force-alone", "subagent-model-order"]))


class AgentEffortTests(ResolveCase):
    """The user's top-level effortLevel counts for an agent by the agent's own model."""

    def agent_effort(self, main, agent_model, **kw):
        entries = self.run_resolve(user=dict({"model": main}, **kw.pop("user", {})),
                                   user_agents={"probe.md": agent_text(model=agent_model)}, **kw)
        return self.rows(entries, "effort", "agent", "probe")

    def test_a_haiku_5_5_agent_ignores_the_user_key_under_a_fable_5_1_main(self):
        got = self.agent_effort("claude-fable-5-1", "claude-haiku-5-5",
                                user={"effortLevel": "low"})
        by_status = {e["status"]: e for e in got}
        self.assertEqual((by_status["default"]["value"], by_status["default"]["layer"]),
                         ("medium", "default"))
        self.assertEqual((by_status["ignored"]["value"], by_status["ignored"]["rule_id"]),
                         ("low", "agent-effort-user-settings-opus-5-5"))
        self.assertEqual(len(got), 2)

    def test_an_opus_5_5_agent_runs_at_its_default_not_the_user_key(self):
        got = self.agent_effort("claude-opus-5-5", "claude-opus-5-5", user={"effortLevel": "xhigh"})
        self.assertEqual(sorted((e["status"], e["value"]) for e in got),
                         [("default", "medium"), ("ignored", "xhigh")])

    def test_an_agent_on_an_older_model_takes_the_user_key(self):
        got = self.agent_effort("claude-sonnet-5-5", "claude-fable-5-1", user={"effortLevel": "low"})
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in got],
                         [("user", "low", "in_effect")])

    def test_the_project_key_counts_for_a_5_5_agent(self):
        entries = self.run_resolve(
            user={"model": "claude-sonnet-5-5"}, project={"effortLevel": "low"},
            user_agents={"probe.md": agent_text(model="claude-haiku-5-5")})
        got = self.rows(entries, "effort", "agent", "probe")
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in got],
                         [("project", "low", "in_effect")])

    def test_a_model_settings_level_for_the_main_model_does_not_reach_the_agent(self):
        entries = self.run_resolve(
            user={"model": "claude-sonnet-5-5",
                  "modelSettings": {"claude-sonnet-5-5": {"effortLevel": "low"}}},
            user_agents={"probe.md": agent_text(model="claude-haiku-5-5")})
        got = self.rows(entries, "effort", "agent", "probe")
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in got],
                         [("default", "medium", "default")])


class MainEffortModelUnknownTests(ResolveCase):
    """The user's top-level effortLevel depends on a model, so it is unknown without one."""

    def user_entries(self, user):
        entries = self.rows(self.run_resolve(user=user), "effortLevel")
        return [e for e in entries if e["layer"] == "user"]

    def test_no_model_leaves_the_user_key_unknown(self):
        got = self.user_entries({"effortLevel": "high"})
        self.assertEqual([(e["value"], e["status"], e["rule_id"]) for e in got],
                         [("high", "unknown", "effort-level-user-settings-model-unknown")])

    def test_a_model_that_reads_the_key_keeps_it_in_effect(self):
        got = self.user_entries({"model": "claude-opus-4-6", "effortLevel": "high"})
        self.assertEqual([(e["value"], e["status"]) for e in got], [("high", "in_effect")])


class EmptyEffortEnvTests(ResolveCase):
    """An empty CLAUDE_CODE_EFFORT_LEVEL is not set, and only the word unset sends none."""

    ENV = "CLAUDE_CODE_EFFORT_LEVEL"

    def test_empty_matches_the_empty_rule_not_the_unset_rule(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5"},
                                   project={"effortLevel": "high"}, shell_env={self.ENV: ""})
        env = [e for e in self.rows(entries, "effortLevel") if e["layer"] == "env"]
        self.assertEqual([(e["status"], e["rule_id"]) for e in env],
                         [("ignored", "effort-env-empty-ignored")])

    def test_the_word_unset_still_sends_no_level(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5"},
                                   project={"effortLevel": "high"}, shell_env={self.ENV: "unset"})
        env = [e for e in self.rows(entries, "effortLevel") if e["layer"] == "env"]
        self.assertEqual([(e["status"], e["rule_id"]) for e in env],
                         [("default", "effort-env-auto-sends-none")])

    def test_empty_does_not_win_for_an_agent(self):
        entries = self.run_resolve(
            user={"model": "claude-sonnet-5-5"}, shell_env={self.ENV: ""},
            user_agents={"probe.md": agent_text(model="claude-haiku-5-5", extra="effort: high\n")})
        got = self.rows(entries, "effort", "agent", "probe")
        self.assertIn(("env", "ignored", "agent-effort-env-empty-ignored"),
                      [(e["layer"], e["status"], e.get("rule_id")) for e in got])
        self.assertIn(("agent", "high", "in_effect"),
                      [(e["layer"], e["value"], e["status"]) for e in got])


class AgentAutoCompactTests(ResolveCase):
    """The agent's window follows sub-agents#subagent-auto-compact-window."""

    OPUS = {"model": "claude-opus-5-5"}

    def window(self, frontmatter=None, user=None, env=None, model="claude-opus-5-5", rules=RULES):
        settings = {"model": model}
        if user is not None:
            settings["autoCompactWindow"] = user
        extra = "autoCompactWindow: %s" % frontmatter if frontmatter is not None else ""
        entries = self.run_resolve(user=settings, shell_env=env, rules=rules,
                                   user_agents={"probe.md": agent_text(extra=extra)})
        return self.rows(entries, "autoCompactWindow", "agent", "probe")

    @staticmethod
    def brief(got):
        return [(e["layer"], e["value"], e["status"]) for e in got]

    def test_a_variable_that_is_not_a_number_is_ignored_and_the_frontmatter_applies(self):
        got = self.window(300000, env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "abc"})
        self.assertEqual(self.brief(got), [("agent", 300000, "in_effect"),
                                           ("default", 1000000, "overridden"),
                                           ("env", "abc", "ignored")])

    def test_a_variable_below_the_floor_clamps_and_beats_the_frontmatter(self):
        got = self.window(300000, env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "50000"})
        self.assertEqual(self.brief(got), [("env", 50000, "in_effect"), ("agent", 300000, "overridden")])
        self.assertEqual(got[0]["becomes"], 100000)

    def test_a_variable_above_the_ceiling_clamps_and_shows_lowered(self):
        got = self.window(None, env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1500000"})
        self.assertEqual((got[0]["status"], got[0]["becomes"]), ("lowered", 1000000))

    def test_a_variable_in_range_beats_the_frontmatter_whatever_its_size(self):
        got = self.window(200000, env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "900000"})
        self.assertEqual(self.brief(got), [("env", 900000, "in_effect"), ("agent", 200000, "overridden")])

    def test_a_settings_value_below_the_floor_is_ignored_and_cannot_set_the_window(self):
        got = self.window(400000, user=50000)
        self.assertEqual(self.brief(got), [("agent", 400000, "in_effect"),
                                           ("default", 1000000, "overridden"),
                                           ("user", 50000, "ignored")])

    def test_frontmatter_above_the_session_window_cannot_raise_it(self):
        got = self.window(500000, user=300000)
        self.assertEqual(self.brief(got), [("user", 300000, "in_effect"), ("agent", 500000, "overridden")])

    def test_frontmatter_equal_to_the_default_window_loses_to_the_default(self):
        got = self.window(1000000)
        self.assertEqual(self.brief(got), [("default", 1000000, "default"), ("agent", 1000000, "overridden")])

    def test_frontmatter_below_the_default_window_wins(self):
        got = self.window(250000)
        self.assertEqual(self.brief(got), [("agent", 250000, "in_effect"), ("default", 1000000, "overridden")])

    def test_frontmatter_outside_100000_to_1000000_is_ignored(self):
        for value in (99999, 1000001, 2000000, "200k", "abc"):
            with self.subTest(value=value):
                got = self.window(value)
                self.assertEqual([(e["layer"], e["status"]) for e in got],
                                 [("default", "default"), ("agent", "ignored")])

    def test_frontmatter_at_the_edges_counts(self):
        self.assertEqual(self.window(100000)[0]["status"], "in_effect")
        self.assertEqual(self.brief(self.window(1000000, user=None))[0], ("default", 1000000, "default"))

    def test_no_frontmatter_and_nothing_set_inherits_the_session_default(self):
        got = self.window()
        self.assertEqual((got[0]["layer"], got[0]["value"], got[0]["status"], got[0]["rule_id"]),
                         ("default", 1000000, "default", "agent-auto-compact-window-default"))

    def test_an_unknown_session_window_makes_the_frontmatter_unknown(self):
        got = self.window(200000, model="claude-sonnet-5-5")
        self.assertEqual(self.brief(got), [("agent", 200000, "unknown")])
        self.assertEqual(got[0]["rule_id"], "agent-auto-compact-window-default")
        self.assertNotEqual(got[0]["reason"], "")

    def test_a_known_session_window_from_settings_decides_even_off_opus_5_5(self):
        got = self.window(200000, user=500000, model="claude-sonnet-5-5")
        self.assertEqual(self.brief(got), [("agent", 200000, "in_effect"), ("user", 500000, "overridden")])

    def test_no_frontmatter_and_an_unknown_default_is_unknown(self):
        got = self.window(model="claude-sonnet-5-5")
        self.assertEqual(self.brief(got), [("default", None, "unknown")])

    def test_the_default_follows_the_main_model_not_the_agent_model(self):
        entries = self.run_resolve(
            user=self.OPUS,
            user_agents={"probe.md": agent_text(model="claude-haiku-5-5",
                                                extra="autoCompactWindow: 300000")})
        got = self.rows(entries, "autoCompactWindow", "agent", "probe")
        self.assertEqual(self.brief(got), [("agent", 300000, "in_effect"), ("default", 1000000, "overridden")])
        self.assertEqual(got[0]["model"], "claude-haiku-5-5")

    def test_the_comparison_uses_the_clamped_value(self):
        rules = copy.deepcopy(RULES)
        values = next(r for r in rules["rules"] if r["rule_id"] == "agent-auto-compact-window-values")
        values["conditions"].insert(0, {"layer": "user", "models": ["*"], "range": {"min": 1000001},
                                        "becomes": 150000, "status": "lowered"})
        # 1500000 runs as 150000, so the frontmatter at 200000 is not lower and loses.
        got = self.window(200000, user=1500000, rules=rules)
        self.assertEqual([(e["layer"], e["status"]) for e in got],
                         [("user", "lowered"), ("agent", "overridden")])
        self.assertEqual(got[0]["becomes"], 150000)
        # Compared raw, 200000 would have counted as lower than 1500000.
        got = self.window(120000, user=1500000, rules=rules)
        self.assertEqual([(e["layer"], e["status"]) for e in got],
                         [("agent", "in_effect"), ("user", "overridden")])


class UnreadableFrontmatterTests(ResolveCase):
    """An agent whose frontmatter the reader rejected has no readable model, effort or window."""

    UNTESTED = "---\nname: probe\ndescription: {text: x}\n---\nbody\n"
    LOADS = "---\nname: probe\ndescription: [x\n---\nbody\n"
    ROWS = ("model", "effort", "autoCompactWindow", "subagentPromptCacheTtl")

    def entries(self, text, **kw):
        user = dict({"model": "claude-sonnet-5-5"}, **kw.pop("user", {}))
        return self.run_resolve(user=user, user_agents={"probe.md": text}, **kw)

    def agent_file(self, entries):
        return self.only(entries, "agentFile", "agent", "probe")

    def test_default_rows_become_unknown_with_the_file_rule(self):
        for label, text, rule in (("untested", self.UNTESTED, "agent-file-reader-rejected-untested"),
                                  ("loads", self.LOADS, "agent-file-reader-rejected")):
            entries = self.entries(text)
            file_entry = self.agent_file(entries)
            self.assertEqual((file_entry["status"], file_entry["rule_id"]), ("unknown", rule))
            for key in self.ROWS:
                with self.subTest(case=label, row=key):
                    entry = self.only(entries, key, "agent", "probe")
                    self.assertEqual(entry["status"], "unknown")
                    self.assertEqual(entry["rule_id"], rule)
                    self.assertEqual(entry["rule_ids"], file_entry["rule_ids"])
                    self.assertEqual(entry["reason"], file_entry["reason"])

    def test_a_settings_value_the_agent_layer_outranks_becomes_unknown(self):
        entries = self.entries(self.LOADS, project={"effortLevel": "low"})
        got = self.rows(entries, "effort", "agent", "probe")
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in got],
                         [("project", "low", "unknown")])

    def test_a_value_that_outranks_the_agent_layer_stays_known(self):
        entries = self.entries(self.LOADS, shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "low"})
        self.assertEqual(self.only(entries, "effort", "agent", "probe")["status"], "in_effect")
        entries = self.entries(self.LOADS, shell_env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "300000"})
        self.assertEqual(self.only(entries, "autoCompactWindow", "agent", "probe")["status"], "in_effect")
        entries = self.entries(self.LOADS, user={"subagentPromptCacheTtl": "1h"})
        self.assertEqual(self.only(entries, "subagentPromptCacheTtl", "agent", "probe")["status"],
                         "in_effect")

    def test_force_puts_the_model_variable_above_the_frontmatter(self):
        entries = self.entries(self.LOADS, shell_env={
            "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1", "CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-5-5"})
        self.assertEqual(self.only(entries, "model", "agent", "probe")["status"], "in_effect")
        entries = self.entries(self.LOADS, shell_env={"CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-5-5"})
        self.assertEqual(self.only(entries, "model", "agent", "probe")["status"], "unknown")

    def test_a_readable_agent_keeps_its_defaults(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"},
                                   user_agents={"probe.md": agent_text()})
        self.assertEqual(self.only(entries, "effort", "agent", "probe")["status"], "default")

    def test_other_agents_are_not_touched(self):
        entries = self.run_resolve(
            user={"model": "claude-sonnet-5-5"},
            user_agents={"probe.md": self.LOADS, "other.md": agent_text(name="other")})
        self.assertEqual(self.only(entries, "effort", "agent", "other")["status"], "default")


class DefaultReasonTests(ResolveCase):
    """Every default has a rule and a reason."""

    def entry(self, entries, key, scope="main", agent=None):
        return self.only(entries, key, scope, agent)

    def test_agent_model_default_is_the_main_model(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"},
                                   user_agents={"probe.md": agent_text()})
        entry = self.entry(entries, "model", "agent", "probe")
        self.assertEqual((entry["value"], entry["status"], entry["rule_id"]),
                         ("claude-sonnet-5-5", "default", "subagent-model-default"))
        self.assertNotEqual(entry["reason"], "")

    def test_agent_effort_default_uses_the_model_of_the_agent(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"},
                                   user_agents={"probe.md": agent_text(model="claude-fable-5-1")})
        entry = self.entry(entries, "effort", "agent", "probe")
        self.assertEqual((entry["value"], entry["status"], entry["rule_id"], entry["model"]),
                         ("high", "default", "agent-effort-default-by-model", "claude-fable-5-1"))
        self.assertIn("Fable 5.1", entry["reason"])
        self.assertIn("high", entry["reason"])

    def test_a_model_without_effort_gets_a_default_with_no_value_in_its_reason(self):
        entries = self.run_resolve(user={"model": "claude-haiku-4-5"},
                                   user_agents={"probe.md": agent_text()})
        main = self.entry(entries, "effortLevel")
        agent = self.entry(entries, "effort", "agent", "probe")
        self.assertEqual((main["value"], main["status"], main["rule_id"]),
                         (None, "default", "effort-default-no-effort-support"))
        self.assertEqual((agent["value"], agent["status"], agent["rule_id"]),
                         (None, "default", "agent-effort-default-no-effort-support"))
        for entry in (main, agent):
            self.assertNotIn("default, .", entry["reason"])
            self.assertIn("Haiku 4.5", entry["reason"])
        # the by-model rule leaves such a model alone, so one rule explains the default
        self.assertNotIn("effort-default-by-model", main["rule_ids"])

    def test_the_no_effort_rules_come_before_the_by_model_defaults(self):
        order = [r["rule_id"] for r in RULES["rules"]]
        self.assertLess(order.index("effort-default-no-effort-support"),
                        order.index("effort-default-by-model"))
        self.assertLess(order.index("agent-effort-default-no-effort-support"),
                        order.index("agent-effort-default-by-model"))
        self.assertLess(order.index("effort-default-model-unknown"),
                        order.index("effort-default-by-model"))
        self.assertLess(order.index("agent-effort-default-model-unknown"),
                        order.index("agent-effort-default-by-model"))

    def test_no_model_set_is_unknown_all_the_way_down(self):
        entries = self.run_resolve(user_agents={"probe.md": agent_text()})
        expected = (("model", "main", None, "model-main-default"),
                    ("effortLevel", "main", None, "effort-default-model-unknown"),
                    ("model", "agent", "probe", "subagent-model-default"),
                    ("effort", "agent", "probe", "agent-effort-default-model-unknown"))
        for key, scope, agent, rule in expected:
            with self.subTest(row=(key, scope)):
                entry = self.entry(entries, key, scope, agent)
                self.assertEqual((entry["value"], entry["status"], entry["rule_id"]),
                                 (None, "unknown", rule))
                self.assertNotEqual(entry["reason"], "")

    def test_a_model_name_outside_the_catalog_has_no_known_default_effort(self):
        entries = self.run_resolve(user={"model": "claude-future-9"},
                                   user_agents={"probe.md": agent_text(model="claude-future-10")})
        main = self.entry(entries, "effortLevel")
        agent = self.entry(entries, "effort", "agent", "probe")
        self.assertEqual((main["status"], main["rule_id"]), ("unknown", "effort-default-model-unknown"))
        self.assertEqual((agent["status"], agent["rule_id"]),
                         ("unknown", "agent-effort-default-model-unknown"))

    def test_force_alone_explains_the_agent_default(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"},
                                   user_agents={"probe.md": agent_text()},
                                   shell_env={"CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"})
        entry = self.entry(entries, "model", "agent", "probe")
        self.assertEqual((entry["value"], entry["status"], entry["rule_id"]),
                         ("claude-sonnet-5-5", "default", "subagent-model-force-alone"))
        self.assertNotIn("  ", entry["reason"])

    def test_max_effort_level_default_has_a_rule(self):
        entry = self.entry(self.run_resolve(user={"model": "claude-opus-5-5"}), "maxEffortLevel")
        self.assertEqual((entry["value"], entry["status"], entry["rule_id"]),
                         (None, "default", "max-effort-level-default"))

    def test_the_cap_still_picks_the_lowest_with_a_default_rule_in_the_row(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5", "maxEffortLevel": "high"},
                                   project={"maxEffortLevel": "low"})
        got = self.rows(entries, "maxEffortLevel")
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in got],
                         [("project", "low", "in_effect"), ("user", "high", "overridden")])

    def test_agent_window_default_has_a_rule(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5"},
                                   user_agents={"probe.md": agent_text()})
        entry = self.entry(entries, "autoCompactWindow", "agent", "probe")
        self.assertEqual((entry["value"], entry["status"], entry["rule_id"]),
                         (1000000, "default", "agent-auto-compact-window-default"))


class RenderedReasonTests(unittest.TestCase):
    """Every entry of every fixture explains itself in whole words."""

    EMPTY_SLOTS = (
        ("two spaces", re.compile(r"  ")),
        ("a space before a full stop", re.compile(r"\s\.(\s|$)")),  # not ".md"
        ("a space before a comma", re.compile(r"\s,")),
        ("empty brackets", re.compile(r"\( \)")),
        ("a comma before a full stop", re.compile(r", \.")),
        ("a trailing space", re.compile(r"\s$")),
        ("a slot left open", re.compile(r"[{}]")),
    )

    def test_every_entry_of_every_fixture_has_a_rule_and_a_whole_reason(self):
        problems = []
        count = 0
        for name in _fixture_names():
            inputs, _expected = resolve.load_fixture(os.path.join(FIXTURE_DIR, name))
            for entry in resolve.resolve(inputs, RULES, FIELDS):
                count += 1
                where = "%s: %s/%s%s %s" % (
                    name, entry["key"], entry["scope"],
                    "/" + entry["agent"] if entry.get("agent") else "", entry["status"])
                if entry["rule_id"] is None:
                    problems.append(where + ": rule_id is None")
                reason = entry["reason"]
                if not reason.strip():
                    problems.append(where + ": the reason is empty")
                for label, pattern in self.EMPTY_SLOTS:
                    if pattern.search(reason):
                        problems.append("%s: the reason has %s: %r" % (where, label, reason))
        self.assertGreater(count, 100)
        self.assertEqual(problems, [])

    def test_the_check_catches_each_kind_of_gap(self):
        for reason in ("runs at  medium", "its default, .", "a ( ) b", "x , y", "ends ", "{value}"):
            with self.subTest(reason=reason):
                self.assertTrue(any(p.search(reason) for _l, p in self.EMPTY_SLOTS))
        for reason in ("Claude Code reads only .md files.", "Fine, and whole."):
            with self.subTest(reason=reason):
                self.assertFalse(any(p.search(reason) for _l, p in self.EMPTY_SLOTS))


class FileCaseTests(ResolveCase):
    def statuses(self, entries):
        return {e["file"].rsplit("/", 1)[-1]: (e["status"], e.get("field"))
                for e in entries if e["key"] == "agentFile"}

    def test_each_case(self):
        agents = {
            "good.md": agent_text("good"),
            "notes.txt": agent_text("notes"),
            "noname.md": agent_text(None),
            "nodesc.md": agent_text("nodesc", None),
            "tab.md": "---\nname: tab\n\tdescription: x\n---\n",
            "quote.md": '---\nname: quote\ndescription: "open\n---\n',
            "nofence.md": "---\nname: nofence\ndescription: x\n",
            "bracket.md": agent_text("bracket", "[open"),
            "colons.md": agent_text("colons", "one: two"),
            "dupkey.md": "---\nname: dupkey\nname: other\ndescription: x\n---\n",
            "flow.md": agent_text("flow", "{a: b}"),
            "plain.md": "no frontmatter here\n",
            "sub/deep.md": agent_text("deep"),
            ".hidden.md": agent_text("hidden"),
        }
        got = self.statuses(self.run_resolve(user_agents=agents))
        self.assertEqual(got, {
            "good.md": ("in_effect", None),
            "notes.txt": ("ignored", None),
            "noname.md": ("ignored", None),
            "nodesc.md": ("invalid", None),
            "tab.md": ("invalid", None),
            "quote.md": ("invalid", None),
            "nofence.md": ("invalid", None),
            "bracket.md": ("unknown", None),
            "colons.md": ("unknown", None),
            "dupkey.md": ("unknown", None),
            "flow.md": ("unknown", None),
            "plain.md": ("unknown", None),
            "deep.md": ("in_effect", None),
        })

    def test_untested_rejection_uses_its_own_rule(self):
        entries = self.run_resolve(user_agents={"flow.md": agent_text("flow", "{a: b}"),
                                                "open.md": agent_text("open", "[x")})
        by_agent = {e["agent"]: e["rule_id"] for e in entries if e["key"] == "agentFile"}
        self.assertEqual(by_agent["flow"], "agent-file-reader-rejected-untested")
        self.assertEqual(by_agent["open"], "agent-file-reader-rejected")

    def test_agent_name_falls_back_to_the_file_name(self):
        entries = self.run_resolve(user_agents={"my.agent.md": agent_text("x", "[open")})
        self.assertEqual([e["agent"] for e in entries if e["key"] == "agentFile"], ["my"])

    def test_unknown_fields_get_their_own_entries(self):
        entries = self.run_resolve(user_agents={
            "probe.md": agent_text(extra="zeta: 1\nalpha: 2\ntools: Read")})
        got = self.rows(entries, "agentFile", "agent", "probe")
        self.assertEqual([(e["status"], e.get("field")) for e in got],
                         [("in_effect", None), ("ignored", "alpha"), ("ignored", "zeta")])

    def test_files_that_do_not_load_have_no_agent_rows(self):
        entries = self.run_resolve(user_agents={"probe.md.bak": agent_text()})
        self.assertEqual(self.rows(entries, "model", "agent", "probe"), [])
        self.assertEqual(len(self.rows(entries, "agentFile", "agent", "probe")), 1)

    def test_rules_files(self):
        entries = self.run_resolve(user_rules={"a.md": "x", "sub/b.md": "x", "c.txt": "x"},
                                   project_rules={"d.md": "x"})
        got = [(e["layer"], e["file"].rsplit("/", 1)[-1], e["status"])
               for e in self.rows(entries, "rulesFile")]
        self.assertEqual(sorted(got), [("project", "d.md", "in_effect"),
                                       ("user", "a.md", "in_effect"),
                                       ("user", "b.md", "in_effect"),
                                       ("user", "c.txt", "ignored")])

    def test_no_rules_folder_means_no_rules_row(self):
        self.assertEqual(self.rows(self.run_resolve(), "rulesFile"), [])


class ReasonTests(ResolveCase):
    def test_reason_fills_the_slots_and_blanks_the_rest(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5", "effortLevel": "low"})
        entry = next(e for e in self.rows(entries, "effortLevel") if e["status"] == "ignored")
        self.assertEqual(entry["reason"], (
            "Opus 5.5 ignores the top-level effortLevel in config/settings.json. Opus 5.5 "
            "and later models take a user settings level only from modelSettings."))
        self.assertNotIn("{", self.only(entries, "promptCacheTtl")["reason"])

    def test_a_shell_source_reads_the_shell_in_a_reason_and_keeps_its_label(self):
        for label in (resolve.LABEL_SHELL, resolve.LIVE_SHELL_LABEL):
            with self.subTest(label=label):
                entries = self.run_resolve(
                    shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "max"},
                    user={"model": "claude-opus-5-5", "maxEffortLevel": "high"},
                    shell_label=label)
                lowered = next(e for e in self.rows(entries, "effortLevel")
                               if e["status"] == "lowered")
                self.assertEqual(lowered["rule_id"], "effort-lowered-by-cap")
                self.assertEqual(lowered["file"], label)
                self.assertEqual(lowered["reason"], (
                    "max from the shell runs as high, because maxEffortLevel caps "
                    "Opus 5.5 at high."))
                block = self.only(entries, "env.CLAUDE_CODE_EFFORT_LEVEL")
                self.assertTrue(block["reason"].startswith(
                    "env.CLAUDE_CODE_EFFORT_LEVEL comes from the shell."))

    def test_a_file_source_keeps_its_name_in_a_reason(self):
        entries = self.run_resolve(
            user={"model": "claude-opus-5-5", "maxEffortLevel": "high",
                  "env": {"CLAUDE_CODE_EFFORT_LEVEL": "max"}})
        lowered = next(e for e in self.rows(entries, "effortLevel") if e["status"] == "lowered")
        self.assertIn("max from config/settings.json runs as high", lowered["reason"])
        self.assertNotIn("the shell", lowered["reason"])

    def test_every_entry_has_a_reason_unless_no_rule_decided(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5"},
                                   user_agents={"probe.md": agent_text()})
        for entry in entries:
            with self.subTest(row=(entry["key"], entry["scope"])):
                self.assertEqual(entry["reason"] == "", entry["rule_id"] is None)


class PerModelCapReplacesTopLevelTests(ResolveCase):
    """A file's modelSettings maxEffortLevel replaces that file's top-level cap."""
    PROJECT = "project/.claude/settings.json"

    def resolve_caps(self, user=None, project=None, effort="xhigh"):
        user = dict({"model": "claude-sonnet-5-5"}, **(user or {}))
        entries = self.run_resolve(user=user, project=project, flags=["--effort", effort])
        caps = [e for e in self.rows(entries, "maxEffortLevel")]
        return entries, caps, self.only(entries, "effortLevel")

    @staticmethod
    def by_value(caps, value, layer="project"):
        found = [e for e in caps if e["value"] == value and e["layer"] == layer]
        assert len(found) == 1, found
        return found[0]

    def test_the_replaced_top_level_entry_is_overridden_by_the_new_rule(self):
        _entries, caps, effort = self.resolve_caps(project={
            "maxEffortLevel": "low",
            "modelSettings": {"claude-sonnet-5-5": {"maxEffortLevel": "xhigh"}}})
        winner = self.by_value(caps, "xhigh")
        top = self.by_value(caps, "low")
        self.assertEqual(winner["status"], "in_effect")
        self.assertEqual(winner["rule_id"], "model-settings-max-effort-per-model")
        self.assertEqual(top["status"], "overridden")
        self.assertEqual(top["rule_id"], "max-effort-level-replaced-in-file")
        self.assertIn("max-effort-level-replaced-in-file", top["rule_ids"])
        rule = next(r for r in RULES["rules"] if r["rule_id"] == "max-effort-level-replaced-in-file")
        self.assertEqual(top["reason"], rule["reason"].format(
            value="low", file=self.PROJECT, model="Sonnet 5.5"))
        self.assertEqual((effort["status"], effort["value"]), ("in_effect", "xhigh"))

    def test_a_cap_in_a_second_file_still_wins_as_the_lowest(self):
        _entries, caps, effort = self.resolve_caps(
            user={"maxEffortLevel": "low"},
            project={"maxEffortLevel": "medium",
                     "modelSettings": {"claude-sonnet-5-5": {"maxEffortLevel": "xhigh"}}})
        self.assertEqual(self.by_value(caps, "low", "user")["status"], "in_effect")
        self.assertEqual(self.by_value(caps, "xhigh")["status"], "overridden")
        replaced = self.by_value(caps, "medium")
        self.assertEqual(replaced["status"], "overridden")
        self.assertEqual(replaced["rule_id"], "max-effort-level-replaced-in-file")
        self.assertEqual((effort["status"], effort["becomes"]), ("lowered", "low"))

    def test_an_entry_for_another_model_replaces_nothing(self):
        _entries, caps, effort = self.resolve_caps(project={
            "maxEffortLevel": "low",
            "modelSettings": {"claude-opus-5-5": {"maxEffortLevel": "xhigh"}}})
        self.assertEqual([(e["value"], e["status"]) for e in caps], [("low", "in_effect")])
        self.assertEqual((effort["status"], effort["becomes"]), ("lowered", "low"))

    def test_a_lower_per_model_cap_replaces_a_higher_top_level_cap(self):
        _entries, caps, effort = self.resolve_caps(effort="high", project={
            "maxEffortLevel": "xhigh",
            "modelSettings": {"claude-sonnet-5-5": {"maxEffortLevel": "low"}}})
        self.assertEqual(self.by_value(caps, "low")["status"], "in_effect")
        top = self.by_value(caps, "xhigh")
        self.assertEqual((top["status"], top["rule_id"]),
                         ("overridden", "max-effort-level-replaced-in-file"))
        self.assertEqual((effort["status"], effort["becomes"]), ("lowered", "low"))

    def test_a_per_model_max_lowers_nothing(self):
        _entries, caps, effort = self.resolve_caps(project={
            "maxEffortLevel": "low",
            "modelSettings": {"claude-sonnet-5-5": {"maxEffortLevel": "max"}}})
        self.assertEqual(self.by_value(caps, "max")["status"], "in_effect")
        self.assertEqual(self.by_value(caps, "low")["status"], "overridden")
        self.assertEqual(effort["status"], "in_effect")
        self.assertNotIn("becomes", effort)

    def test_a_per_model_value_that_is_not_a_level_replaces_nothing(self):
        _entries, caps, effort = self.resolve_caps(project={
            "maxEffortLevel": "low",
            "modelSettings": {"claude-sonnet-5-5": {"maxEffortLevel": "turbo"}}})
        top = self.by_value(caps, "low")
        self.assertEqual((top["status"], top["rule_id"]),
                         ("in_effect", "max-effort-level-lowest-cap"))
        self.assertEqual(self.by_value(caps, "turbo")["status"], "overridden")
        self.assertEqual((effort["status"], effort["becomes"]), ("lowered", "low"))

    def test_the_lowest_name_form_decides_which_entry_counts(self):
        for first, second, replaced in (("turbo", "xhigh", False), ("xhigh", "turbo", True)):
            with self.subTest(canonical=first, alias=second):
                self.setUp()
                _entries, caps, _effort = self.resolve_caps(project={
                    "maxEffortLevel": "low",
                    "modelSettings": {"sonnet": {"maxEffortLevel": second},
                                      "claude-sonnet-5-5": {"maxEffortLevel": first}}})
                top = self.by_value(caps, "low")
                self.assertEqual(top["status"], "overridden" if replaced else "in_effect")

    def test_only_the_new_rule_votes_overridden_with_a_file_case(self):
        found = [(r["rule_id"], c["when"]) for r in RULES["rules"] for c in r["conditions"]
                 if c["status"] == "overridden" and "when" in c]
        self.assertEqual({rule_id for rule_id, _when in found},
                         {"max-effort-level-replaced-in-file"})


class RuleErrorTests(ResolveCase):
    ENV_RULE = {
        "rule_id": "env-block-order", "key": "env", "scope": "main",
        "layer_order": ["managed", "cli", "local", "project", "user", "env"],
        "combine": "highest_layer",
        "conditions": [{"layer": layer, "models": ["*"], "status": "in_effect"}
                       for layer in ("managed", "cli", "local", "project", "user", "env")],
        "reason": "{key}",
    }

    @classmethod
    def mini(cls, *rules):
        return {"schema_version": 3, "models": RULES["models"], "rules": [cls.ENV_RULE] + list(rules)}

    @staticmethod
    def model_rule(rule_id, order, combine="highest_layer", **extra):
        rule = {"rule_id": rule_id, "key": "model", "scope": "main", "layer_order": order,
                "combine": combine, "reason": "{value}",
                "conditions": [{"layer": layer, "models": ["*"], "status": "in_effect"}
                               for layer in order]}
        rule.update(extra)
        return rule

    SETTINGS = {"model": "claude-opus-5-5"}

    def test_orders_that_disagree_raise(self):
        rules = self.mini(self.model_rule("a", ["user", "project"]),
                          self.model_rule("b", ["project", "user"]))
        with self.assertRaisesRegex(ValueError, "order the layers"):
            self.run_resolve(user=self.SETTINGS, project=self.SETTINGS, rules=rules)

    def test_a_shorter_order_inside_a_longer_one_is_fine(self):
        rules = self.mini(self.model_rule("a", ["local", "project", "user"]),
                          self.model_rule("b", ["project", "user"]))
        entries = self.run_resolve(user=self.SETTINGS, project=self.SETTINGS, rules=rules)
        self.assertEqual([e["layer"] for e in self.rows(entries, "model")], ["project", "user"])

    def test_combines_that_disagree_raise(self):
        rules = self.mini(self.model_rule("a", ["user", "project"]),
                          self.model_rule("b", ["user", "project"], "lowest_value",
                                          value_order=["claude-opus-5-5"]))
        with self.assertRaisesRegex(ValueError, "combine"):
            self.run_resolve(user=self.SETTINGS, project=self.SETTINGS, rules=rules)

    def test_lowest_value_picks_the_lowest_wherever_it_is_set(self):
        rules = self.mini(self.model_rule("a", ["project", "user"], "lowest_value",
                                          value_order=["claude-haiku-5-5", "claude-opus-5-5"]))
        entries = self.run_resolve(user={"model": "claude-haiku-5-5"},
                                   project={"model": "claude-opus-5-5"}, rules=rules)
        self.assertEqual([(e["layer"], e["status"]) for e in self.rows(entries, "model")],
                         [("user", "in_effect"), ("project", "overridden")])

    def test_all_keeps_every_candidate(self):
        rules = self.mini(self.model_rule("a", ["project", "user"], "all"))
        entries = self.run_resolve(user={"model": "claude-haiku-5-5"},
                                   project={"model": "claude-opus-5-5"}, rules=rules)
        self.assertEqual([e["status"] for e in self.rows(entries, "model")],
                         ["in_effect", "in_effect"])

    def test_a_missing_env_rule_raises(self):
        rules = {"schema_version": 3, "models": RULES["models"], "rules": []}
        with self.assertRaisesRegex(ValueError, "env"):
            self.run_resolve(rules=rules)

    def test_a_candidate_no_condition_matches_is_unknown(self):
        rule = self.model_rule("a", ["user"])
        rule["conditions"] = [{"layer": "user", "models": ["*"], "values": ["x"],
                               "status": "in_effect"}]
        entries = self.run_resolve(user=self.SETTINGS, rules=self.mini(rule))
        entry = self.only(entries, "model")
        self.assertEqual((entry["status"], entry["rule_id"]), ("unknown", None))


def _blocked(label):
    def fail(*_args, **_kwargs):
        raise AssertionError("resolve called " + label)
    return fail


@contextlib.contextmanager
def no_file_access():
    """Make every call that opens, lists or stats a file raise."""
    with contextlib.ExitStack() as stack:
        for owner, name in ((builtins, "open"), (io, "open"), (os, "open"), (os, "listdir"),
                            (os, "scandir"), (os, "walk"), (os, "stat"), (os, "lstat"),
                            (os, "access"), (os.path, "exists"), (os.path, "isdir"),
                            (os.path, "isfile")):
            stack.enter_context(mock.patch.object(owner, name, _blocked(
                "%s.%s" % (owner.__name__, name))))
        for name in ("read_text", "read_bytes", "open", "stat", "iterdir", "exists", "is_dir",
                     "is_file", "resolve"):
            stack.enter_context(mock.patch.object(pathlib.Path, name, _blocked("Path." + name)))
        yield


class NoFileAccessTests(unittest.TestCase):
    def test_resolve_opens_nothing_for_any_fixture(self):
        loaded = [(name, resolve.load_fixture(os.path.join(FIXTURE_DIR, name), RULES)[0])
                  for name in _fixture_names()]
        self.assertGreater(len(loaded), 60)
        with no_file_access():
            for name, inputs in loaded:
                with self.subTest(fixture=name):
                    self.assertTrue(resolve.resolve(inputs, RULES, FIELDS))

    def test_the_patch_stops_each_kind_of_access(self):
        probes = (lambda: open(__file__), lambda: io.open(__file__), lambda: os.listdir("."),
                  lambda: os.stat("."), lambda: os.path.isdir("."),
                  lambda: pathlib.Path(".").exists(), lambda: pathlib.Path(__file__).read_text())
        for probe in probes:
            with no_file_access():
                with self.assertRaises(AssertionError):
                    probe()

    def test_resolve_needs_the_field_list(self):
        inputs = resolve.load_fixture(os.path.join(FIXTURE_DIR, "env-block-over-shell"), RULES)[0]
        with self.assertRaises(TypeError):
            resolve.resolve(inputs, RULES)


class LineTests(ResolveCase):
    """Every entry whose value came from a real file carries its line."""

    USER = {
        "model": "claude-sonnet-5-5",
        "effortLevel": "low",
        "modelSettings": {"sonnet": {"effortLevel": "high"}},
        "env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000", "MADE_UP_NOTE": "x"},
    }

    def test_a_file_entry_has_an_integer_line_and_the_others_have_none(self):
        entries = self.run_resolve(
            user=pretty(self.USER), project=pretty({"promptCacheTtl": "1h"}),
            cli={"effortLevel": "low"}, flags=["--effort", "high"],
            shell_env={"ANTHROPIC_MODEL": "claude-haiku-5-5"},
            user_agents={"probe.md": agent_text(extra="zeta: 1\n")},
            project_rules={"a.md": "x", "b.txt": "x"})
        labels = {resolve.LABEL_SHELL, resolve.LABEL_FLAGS, resolve.LABEL_CLI}
        seen = set()
        for entry in entries:
            with self.subTest(row=(entry["key"], entry["scope"], entry["layer"], entry["file"])):
                if entry["file"] is None or entry["file"] in labels:
                    self.assertNotIn("line", entry)
                else:
                    self.assertIsInstance(entry["line"], int)
                    self.assertNotIsInstance(entry["line"], bool)
                seen.add(entry["file"] in labels)
        self.assertEqual(seen, {True, False})

    def test_settings_lines(self):
        entries = self.run_resolve(user=pretty(self.USER))
        model = self.only(entries, "model")
        self.assertEqual((model["file"], model["line"]), ("config/settings.json", 2))
        nested = [e for e in self.rows(entries, "effortLevel") if e.get("path")]
        self.assertEqual([(e["path"], e["line"]) for e in nested],
                         [("modelSettings.sonnet.effortLevel", 6)])
        top = [e for e in self.rows(entries, "effortLevel") if e["layer"] == "user"
               and not e.get("path")]
        self.assertEqual([e["line"] for e in top], [3])

    def test_env_block_lines_reach_the_variable_rows(self):
        entries = self.run_resolve(user=pretty(self.USER))
        note = self.only(entries, "env.MADE_UP_NOTE")
        self.assertEqual((note["file"], note["line"]), ("config/settings.json", 11))
        window = self.only(entries, "env.CLAUDE_CODE_AUTO_COMPACT_WINDOW")
        self.assertEqual(window["line"], 10)
        fed = self.only(entries, "autoCompactWindow")
        self.assertEqual((fed["via"], fed["file"], fed["line"]),
                         ("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "config/settings.json", 10))

    def test_managed_lines_name_the_file_the_key_came_from(self):
        entries = self.run_resolve(managed=pretty({"model": "claude-haiku-5-5"}),
                                   user=pretty({"model": "claude-sonnet-5-5"}))
        got = self.rows(entries, "model")
        self.assertEqual([(e["layer"], e["file"], e["line"]) for e in got],
                         [("managed", "managed/managed-settings.json", 2),
                          ("user", "config/settings.json", 2)])

    def test_agent_lines(self):
        text = agent_text(model="claude-haiku-5-5",
                          extra="experimental:\n  cacheTtl: 1h\nzeta: 1")
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"},
                                   user_agents={"probe.md": text})
        agent = lambda key: self.only(entries, key, "agent", "probe")  # noqa: E731
        self.assertEqual(agent("model")["line"], 4)
        self.assertEqual(agent("subagentPromptCacheTtl")["line"], 6)
        self.assertEqual(agent("subagentPromptCacheTtl")["layer"], "agent")
        files = self.rows(entries, "agentFile", "agent", "probe")
        self.assertEqual([(e["status"], e.get("field"), e["line"]) for e in files],
                         [("in_effect", None, 2), ("ignored", "zeta", 7)])

    def test_a_rejected_agent_file_names_the_line_of_its_first_error(self):
        entries = self.run_resolve(user_agents={
            "tab.md": "---\nname: tab\n\tdescription: x\n---\n",
            "flow.md": "---\nname: flow\ndescription: [x\n---\n",
            "nodesc.md": agent_text("nodesc", None),
            "notes.txt": agent_text("notes")})
        lines = {e["agent"]: e["line"] for e in entries if e["key"] == "agentFile"}
        self.assertEqual(lines, {"tab": 3, "flow": 3, "nodesc": 1, "notes": 1})

    def test_rules_files_and_unparsed_settings_files(self):
        entries = self.run_resolve(user_rules={"a.md": "x"}, project="{\n  \"model\": 1,\n}\n")
        self.assertEqual([e["line"] for e in self.rows(entries, "rulesFile")], [1])
        broken = self.only(entries, "settingsFile")
        self.assertEqual((broken["layer"], broken["line"]), ("project", 3))

    def test_a_shell_value_and_a_default_carry_no_line(self):
        entries = self.run_resolve(shell_env={"ANTHROPIC_MODEL": "claude-haiku-5-5"},
                                   shell_label=resolve.LIVE_SHELL_LABEL)
        shell = self.only(entries, "env.ANTHROPIC_MODEL")
        self.assertEqual((shell["file"], "line" in shell), ("Shell", False))
        default = self.only(entries, "promptCacheTtl")
        self.assertEqual((default["file"], "line" in default), (None, False))


class HomeDisplayTests(ResolveCase):
    def test_display_path_is_a_pure_string_function(self):
        show = resolve.display_path
        self.assertEqual(show("/x/a/f.json", home="/x/a"), "~/f.json")
        self.assertEqual(show("/x/a/f.json", home="/x/a/"), "~/f.json")
        self.assertEqual(show("/x/a", home="/x/a"), "~")
        self.assertEqual(show("/x/ab/f.json", home="/x/a"), "/x/ab/f.json")
        self.assertEqual(show("/x/a/f.json", home="/x/a", root="/x/a"), "f.json")
        self.assertEqual(show("/x/a/b/f.json", home="/x/a", root="/x/a/b"), "f.json")
        self.assertEqual(show("/x/a/f.json"), "/x/a/f.json")
        self.assertEqual(show("/x/a/f.json", home="/"), "/x/a/f.json")

    def test_entries_and_reasons_show_a_tilde_for_the_home_folder(self):
        inputs = self.make_inputs(
            user={"model": "claude-opus-5-5", "effortLevel": "low"},
            user_agents={"probe.md": agent_text(extra="zeta: 1")},
            user_rules={"a.md": "x"}, project="{broken", home=self.tmp, root=False)
        with home_guard([self.tmp]) as seen:
            entries = resolve.resolve(inputs, RULES, FIELDS)
        self.assertEqual(seen, [])
        files = [e["file"] for e in entries if e["file"]]
        self.assertTrue(files)
        for file in files:
            self.assertTrue(file.startswith("~/"), file)
        for entry in entries:
            self.assertNotIn(self.tmp, entry["reason"])
        ignored = next(e for e in self.rows(entries, "effortLevel") if e["status"] == "ignored")
        self.assertEqual(ignored["file"], "~/config/settings.json")
        self.assertIn("~/config/settings.json", ignored["reason"])
        broken = self.only(entries, "settingsFile")
        self.assertIn("~/project/.claude/settings.json", broken["reason"])

    def test_a_sibling_folder_that_starts_with_the_home_name_is_not_shortened(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5"},
                                   home=os.path.join(self.tmp, "conf"), root=False)
        model = self.only(entries, "model")
        self.assertEqual(model["file"], os.path.join(self.tmp, "config", "settings.json"))

    def test_a_root_beats_the_home_folder(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5"}, home=self.tmp)
        self.assertEqual(self.only(entries, "model")["file"], "config/settings.json")


class DisplayNameTests(ResolveCase):
    def test_a_reason_shows_the_display_name_and_the_entry_keeps_the_id(self):
        entries = self.run_resolve(user={"model": "claude-opus-5-5", "effortLevel": "low"})
        ignored = next(e for e in self.rows(entries, "effortLevel") if e["status"] == "ignored")
        self.assertEqual(ignored["model"], "claude-opus-5-5")
        self.assertIn("Opus 5.5", ignored["reason"])
        self.assertNotIn("claude-opus-5-5", ignored["reason"])
        default = next(e for e in self.rows(entries, "effortLevel") if e["status"] == "default")
        self.assertEqual(default["model"], "claude-opus-5-5")
        self.assertNotIn("claude-opus-5-5", default["reason"])

    def test_every_catalog_model_has_its_display_name_in_reasons(self):
        for model in RULES["models"]:
            with self.subTest(model=model["id"]):
                entries = self.run_resolve(user={"model": model["id"]})
                got = [e for e in self.rows(entries, "effortLevel") if e.get("model") == model["id"]]
                self.assertTrue(got)
                for entry in got:
                    self.assertNotIn(model["id"], entry["reason"])


class UnreadableSettingsFileTests(ResolveCase):
    """A settings file the dashboard cannot read hides the values it could set."""

    MAIN = ("model", "maxEffortLevel", "effortLevel", "autoCompactWindow", "promptCacheTtl")
    AGENT = ("model", "effort", "autoCompactWindow", "subagentPromptCacheTtl")

    def setUp(self):
        super().setUp()
        if os.geteuid() == 0:
            self.skipTest("root reads a file with mode 000")

    def unreadable(self, **kw):
        kw.setdefault("user", {"model": "claude-sonnet-5-5"})
        kw.setdefault("user_agents", {"probe.md": agent_text()})
        return self.run_resolve(managed="{}", managed_mode=0, **kw)

    def assert_unknown(self, entry, source):
        self.assertEqual(entry["status"], "unknown", entry)
        self.assertEqual(entry["rule_id"], source["rule_id"])
        self.assertEqual(entry["rule_ids"], source["rule_ids"])
        self.assertEqual(entry["reason"], source["reason"])
        self.assertNotIn("becomes", entry)

    def test_the_rows_a_managed_file_could_set_show_unknown_with_the_rule(self):
        entries = self.unreadable(shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "low"})
        source = self.only(entries, "settingsFile")
        self.assertEqual((source["layer"], source["status"], source["rule_id"], source["line"],
                          source["file"]),
                         ("managed", "unknown", "settings-file-unreadable", 1,
                          "managed/managed-settings.json"))
        self.assertIn("managed/managed-settings.json", source["reason"])
        for key in self.MAIN:
            with self.subTest(row=key):
                self.assert_unknown(self.only(entries, key), source)
        for key in self.AGENT:
            with self.subTest(row=("probe", key)):
                self.assert_unknown(self.only(entries, key, "agent", "probe"), source)
        self.assert_unknown(self.only(entries, "env.CLAUDE_CODE_EFFORT_LEVEL"), source)

    def test_an_unknown_winner_keeps_its_value_layer_file_and_line(self):
        entries = self.unreadable(user=pretty({"model": "claude-sonnet-5-5"}))
        model = self.only(entries, "model")
        self.assertEqual((model["value"], model["layer"], model["file"], model["line"]),
                         ("claude-sonnet-5-5", "user", "config/settings.json", 2))

    def test_a_model_flag_still_wins_and_stays_in_effect(self):
        entries = self.unreadable(flags=["--model", "claude-haiku-5-5"])
        model = self.rows(entries, "model")
        self.assertEqual((model[0]["layer"], model[0]["value"], model[0]["status"]),
                         ("flag", "claude-haiku-5-5", "in_effect"))
        self.assertEqual(model[0]["rule_id"], "model-main-session-order")
        self.assertEqual(self.only(entries, "maxEffortLevel")["status"], "unknown")

    def test_the_unknown_model_leaves_the_rows_that_depend_on_it_unknown(self):
        entries = self.unreadable()
        self.assertEqual(self.only(entries, "model")["status"], "unknown")
        self.assertIsNone(self.only(entries, "effortLevel").get("model"))
        self.assertIsNone(self.only(entries, "model", "agent", "probe")["value"])

    def test_a_managed_file_that_is_not_json_follows_its_own_rule(self):
        entries = self.run_resolve(managed="{not json", user={"model": "claude-sonnet-5-5"},
                                   user_agents={"probe.md": agent_text()})
        source = self.only(entries, "settingsFile")
        self.assertEqual((source["status"], source["rule_id"]),
                         ("unknown", "settings-file-managed-unparsed"))
        for key in self.MAIN:
            with self.subTest(row=key):
                self.assert_unknown(self.only(entries, key), source)
        for key in self.AGENT:
            with self.subTest(row=("probe", key)):
                self.assert_unknown(self.only(entries, key, "agent", "probe"), source)

    def lock_user_file(self):
        """Write an empty user settings.json with mode 000, and restore it on cleanup."""
        config = os.path.join(self.tmp, "config", "settings.json")
        os.makedirs(os.path.dirname(config), exist_ok=True)
        _write(config, "{}")
        os.chmod(config, 0)
        self.addCleanup(os.chmod, config, 0o600)

    def test_an_unreadable_user_file_hides_what_ranks_below_its_env_block(self):
        self.lock_user_file()
        entries = self.run_resolve(project={"model": "claude-sonnet-5-5"},
                                   flags=["--model", "claude-haiku-5-5"])
        source = self.only(entries, "settingsFile")
        self.assertEqual((source["layer"], source["rule_id"]),
                         ("user", "settings-file-unreadable-untested"))
        self.assertEqual([e["status"] for e in self.rows(entries, "model")],
                         ["in_effect", "overridden"])
        self.assert_unknown(self.only(entries, "promptCacheTtl"), source)

    def test_a_managed_env_block_keeps_the_model_in_effect_over_an_unreadable_user_file(self):
        self.lock_user_file()
        entries = self.run_resolve(managed={"env": {"ANTHROPIC_MODEL": "claude-haiku-5-5"}})
        env = self.only(entries, "env.ANTHROPIC_MODEL")
        self.assertEqual((env["layer"], env["status"]), ("managed", "in_effect"))
        model = self.only(entries, "model")
        self.assertEqual((model["layer"], model["via"], model["value"], model["status"]),
                         ("env", "ANTHROPIC_MODEL", "claude-haiku-5-5", "in_effect"))
        # The model is known, so the effort row sees it. It stays unknown for its
        # own reason: a default ranks below the user file, which could set it.
        effort = self.only(entries, "effortLevel")
        self.assertEqual(effort["model"], "claude-haiku-5-5")
        self.assertEqual((effort["layer"], effort["status"], effort["rule_id"]),
                         ("default", "unknown", "settings-file-unreadable-untested"))

    def test_a_project_env_block_keeps_the_model_in_effect_over_an_unreadable_user_file(self):
        self.lock_user_file()
        entries = self.run_resolve(project={"env": {"ANTHROPIC_MODEL": "claude-haiku-5-5"}})
        env = self.only(entries, "env.ANTHROPIC_MODEL")
        self.assertEqual((env["layer"], env["status"]), ("project", "in_effect"))
        model = self.only(entries, "model")
        self.assertEqual((model["value"], model["status"]), ("claude-haiku-5-5", "in_effect"))

    def test_a_shell_only_variable_is_unknown_over_an_unreadable_user_file(self):
        self.lock_user_file()
        entries = self.run_resolve(shell_env={"ANTHROPIC_MODEL": "claude-haiku-5-5"})
        env = self.only(entries, "env.ANTHROPIC_MODEL")
        self.assertEqual((env["layer"], env["status"], env["rule_id"]),
                         ("env", "unknown", "settings-file-unreadable-untested"))
        model = self.only(entries, "model")
        self.assertEqual((model["via"], model["status"], model["rule_id"]),
                         ("ANTHROPIC_MODEL", "unknown", "settings-file-unreadable-untested"))

    def test_a_managed_file_is_unreadable_under_the_tested_rule(self):
        entries = self.unreadable()
        self.assertEqual(self.only(entries, "settingsFile")["rule_id"], "settings-file-unreadable")

    def test_local_and_project_files_are_unreadable_under_the_untested_rule(self):
        for layer, rel in (("local", os.path.join("project", ".claude", "settings.local.json")),
                           ("project", os.path.join("project", ".claude", "settings.json"))):
            with self.subTest(layer=layer):
                path = os.path.join(self.tmp, rel)
                _write(path, "{}")
                os.chmod(path, 0)
                try:
                    source = self.only(self.run_resolve(), "settingsFile")
                finally:
                    os.chmod(path, 0o600)
                    os.remove(path)
                self.assertEqual((source["layer"], source["status"], source["rule_id"]),
                                 (layer, "unknown", "settings-file-unreadable-untested"))


class ParsedFileTests(ResolveCase):
    def test_an_unparsed_user_file_is_skipped_and_the_others_resolve_as_normal(self):
        entries = self.run_resolve(user="{\"model\": \"claude-haiku-4-5\"",
                                   project={"model": "claude-sonnet-5-5"})
        source = self.only(entries, "settingsFile")
        self.assertEqual((source["layer"], source["status"], source["rule_id"], source["line"]),
                         ("user", "ignored", "settings-file-unparsed-skipped", 1))
        self.assertIn("config/settings.json", source["reason"])
        model = self.only(entries, "model")
        self.assertEqual((model["layer"], model["value"], model["status"]),
                         ("project", "claude-sonnet-5-5", "in_effect"))
        self.assertEqual(model["rule_id"], "model-main-session-order")
        for entry in entries:
            if entry["key"] != "settingsFile":
                self.assertNotEqual(entry["rule_id"], "settings-file-unparsed-skipped")

    def test_no_unparsed_file_means_no_settings_file_row(self):
        entries = self.run_resolve(user={"model": "claude-sonnet-5-5"})
        self.assertEqual(self.rows(entries, "settingsFile"), [])


class LiveInputsTests(ResolveCase):
    def test_live_inputs_carry_no_flags_and_no_settings_content(self):
        collected = self.make_inputs(user={"model": "claude-sonnet-5-5"},
                                     project={"effortLevel": "low"},
                                     shell_env={"ANTHROPIC_MODEL": "claude-haiku-5-5"}).collected
        live = resolve.Inputs(collected)
        self.assertEqual((live.flags, live.cli_settings, live.plan, live.home, live.root,
                          live.shell_label), ([], None, None, None, None, "Shell"))
        entries = resolve.resolve(live, RULES, FIELDS)
        self.assertTrue(entries)
        self.assertEqual({e["layer"] for e in entries} & {"flag", "cli"}, set())
        self.assertFalse(any(e["file"] in (resolve.LABEL_FLAGS, resolve.LABEL_CLI)
                             for e in entries))
        shell = self.only(entries, "env.ANTHROPIC_MODEL")
        self.assertEqual(shell["file"], "Shell")

    def test_inputs_are_frozen_and_flags_are_not_shared(self):
        one, two = resolve.Inputs({}), resolve.Inputs({})
        self.assertIsNot(one.flags, two.flags)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            one.home = "/x"


class FixtureRunGuardTests(unittest.TestCase):
    def test_a_fixture_run_never_reads_the_real_shell_or_the_real_folders(self):
        home = pwd.getpwuid(os.getuid()).pw_dir
        made_up = "made-up-effort-zz9"
        texts = []
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": made_up}):
            with home_guard([home, REAL_MANAGED], allowed=[helpers.REPO]) as seen:
                for name in _fixture_names():
                    inputs, _expected = resolve.load_fixture(os.path.join(FIXTURE_DIR, name), RULES)
                    texts.append(json.dumps(resolve.resolve(inputs, RULES, FIELDS)))
        self.assertEqual(seen, [])
        self.assertGreater(len(texts), 60)
        self.assertNotIn(made_up, "".join(texts))


class MaskingEndToEndTests(ResolveCase):
    """Made-up secrets planted in four places reach no entry, but their rows keep place and status."""
    PLANTED = ("planted-secret-alpha", "planted-secret-bravo", "planted-secret-charlie",
               "planted-secret-delta", "planted-secret-echo")

    def setUp(self):
        super().setUp()
        self.entries = self.run_resolve(
            user='{\n  "env": {\n    "MADE_UP_TOKEN": "planted-secret-alpha",\n'
                 '    "ANTHROPIC_MODEL": "claude-haiku-5-5"\n  }\n}\n',
            managed='{\n  "env": {\n    "MADE_UP_PASSWORD": "planted-secret-charlie"\n  },\n'
                    '  "madeUpApiKey": "planted-secret-delta"\n}\n',
            user_agents={"probe.md": "---\nname: probe\ndescription: Made-up agent.\n"
                                     "madeUpSecret: planted-secret-echo\n"
                                     "hooks:\n  PreToolUse: Bearer planted-secret-bravo\n---\nBody.\n"},
            shell_env={"MADE_UP_TOKEN": "planted-secret-bravo", "ANTHROPIC_MODEL": "shell"})

    def test_no_planted_value_is_in_any_entry(self):
        text = json.dumps(self.entries)
        for planted in self.PLANTED:
            with self.subTest(planted=planted):
                self.assertNotIn(planted, text)

    def test_masked_rows_keep_their_file_line_and_status(self):
        got = self.rows(self.entries, "env.MADE_UP_TOKEN")
        self.assertEqual(
            [(e["layer"], e["value"], e["file"], e.get("line"), e["status"]) for e in got],
            [("user", "hidden", "config/settings.json", 3, "in_effect"),
             ("env", "hidden", "session.json:shell_env", None, "overridden")])
        password = self.only(self.entries, "env.MADE_UP_PASSWORD")
        self.assertEqual((password["value"], password["file"], password["line"], password["status"]),
                         ("hidden", "managed/managed-settings.json", 3, "in_effect"))
        files = self.rows(self.entries, "agentFile", "agent", "probe")
        self.assertEqual([(e["status"], e.get("field"), e["line"]) for e in files],
                         [("in_effect", None, 2), ("ignored", "madeUpSecret", 4)])
        model = self.only(self.entries, "model")
        self.assertEqual((model["value"], model["via"], model["line"]),
                         ("claude-haiku-5-5", "ANTHROPIC_MODEL", 4))


class FixtureMaskingTests(unittest.TestCase):
    """A fixture's --settings content is masked before it reaches an entry."""

    def test_cli_settings_env_secret_shows_hidden(self):
        folder = tempfile.mkdtemp(prefix="resolve-fixture-", dir=helpers._tmp_base())
        self.addCleanup(shutil.rmtree, folder, True)
        _write(os.path.join(folder, "session.json"), {
            "cli_settings": {"env": {"MADE_UP_TOKEN": "planted-secret-foxtrot",
                                     "MADE_UP_PLAIN": "plain"}}})
        _write(os.path.join(folder, "expected.json"), [])
        inputs, _expected = resolve.load_fixture(folder)
        self.assertEqual(inputs.cli_settings["env"]["MADE_UP_TOKEN"], "hidden")
        entries = resolve.resolve(inputs, RULES, FIELDS)
        token = [e for e in entries if e["key"] == "env.MADE_UP_TOKEN"]
        self.assertEqual([(e["layer"], e["value"], e["status"]) for e in token],
                         [("cli", "hidden", "in_effect")])
        plain = [e for e in entries if e["key"] == "env.MADE_UP_PLAIN"]
        self.assertEqual(plain[0]["value"], "plain")
        self.assertNotIn("planted-secret-foxtrot", json.dumps(entries))


class CompareTests(unittest.TestCase):
    def entry(self, **fields):
        base = {"key": "effortLevel", "value": "low", "status": "in_effect", "layer": "user",
                "file": "config/settings.json", "scope": "main", "rule_id": "r", "rule_ids": ["r"],
                "reason": "x"}
        base.update(fields)
        return base

    def expected(self, *items, **extra):
        doc = {"fixture": "demo", "rule_ids": [], "expect": list(items)}
        doc.update(extra)
        return doc

    def test_extra_runner_fields_are_fine(self):
        want = self.expected({"key": "effortLevel", "value": "low", "scope": "main"})
        self.assertEqual(resolve.compare([self.entry()], want), [])

    def test_a_field_that_differs_is_named(self):
        want = self.expected({"key": "effortLevel", "value": "high", "scope": "main"})
        self.assertEqual(resolve.compare([self.entry()], want), [
            'demo: row effortLevel/main: value expected "high", got "low"'])

    def test_a_field_the_runner_lacks_is_named(self):
        want = self.expected({"key": "effortLevel", "scope": "main", "via": "X"})
        self.assertEqual(resolve.compare([self.entry()], want), [
            'demo: row effortLevel/main: via expected "X", got nothing'])

    def test_null_must_match_null(self):
        want = self.expected({"key": "effortLevel", "scope": "main", "file": None})
        self.assertEqual(len(resolve.compare([self.entry()], want)), 1)
        self.assertEqual(resolve.compare([self.entry(file=None)], want), [])

    def test_counts_must_match_row_by_row(self):
        want = self.expected({"key": "effortLevel", "scope": "main", "value": "low"})
        got = resolve.compare([self.entry(), self.entry(value="high", status="overridden")], want)
        self.assertEqual(got, ["demo: row effortLevel/main: expected 1 entries, got 2"])

    def test_a_missing_row_is_reported(self):
        want = self.expected({"key": "model", "scope": "main", "value": "x"})
        got = resolve.compare([self.entry()], want)
        self.assertEqual(got[0], "demo: row model/main: expected 1 entries, got 0")
        self.assertIn("no entry for", got[1])

    def test_rows_the_file_does_not_name_are_not_checked(self):
        want = self.expected({"key": "effortLevel", "scope": "main", "value": "low"})
        other = self.entry(key="model", value="x")
        self.assertEqual(resolve.compare([self.entry(), other, other], want), [])

    def test_agents_are_separate_rows(self):
        want = self.expected({"key": "effort", "scope": "agent", "agent": "a", "value": "low"},
                             {"key": "effort", "scope": "agent", "agent": "b", "value": "high"})
        got = [self.entry(key="effort", scope="agent", agent="a"),
               self.entry(key="effort", scope="agent", agent="b", value="high")]
        self.assertEqual(resolve.compare(got, want), [])
        self.assertEqual(len(resolve.compare(got[:1], want)), 2)

    def test_pairing_does_not_depend_on_order(self):
        low = {"key": "effortLevel", "scope": "main", "value": "low"}
        high = {"key": "effortLevel", "scope": "main", "value": "high", "status": "overridden"}
        got = [self.entry(value="high", status="overridden"), self.entry()]
        self.assertEqual(resolve.compare(got, self.expected(low, high)), [])
        self.assertEqual(resolve.compare(got, self.expected(high, low)), [])

    def test_pairing_finds_a_match_when_the_first_choice_is_taken(self):
        loose = {"key": "effortLevel", "scope": "main", "layer": "user"}
        tight = {"key": "effortLevel", "scope": "main", "layer": "user", "value": "low"}
        got = [self.entry(), self.entry(value="high")]
        self.assertEqual(resolve.compare(got, self.expected(loose, tight)), [])

    def test_two_expected_entries_cannot_share_one_runner_entry(self):
        item = {"key": "effortLevel", "scope": "main", "value": "low"}
        got = [self.entry(), self.entry(value="high")]
        self.assertEqual(len(resolve.compare(got, self.expected(item, item))), 1)

    def test_every_expected_rule_id_must_appear_somewhere(self):
        want = self.expected({"key": "effortLevel", "scope": "main"}, rule_ids=["r", "missing"])
        self.assertEqual(resolve.compare([self.entry()], want), [
            "demo: rule_ids: missing is in no rule_ids of the rows the file names"])

    def test_rule_ids_may_come_from_any_entry_of_a_named_row(self):
        want = self.expected({"key": "effortLevel", "scope": "main", "value": "low"},
                             {"key": "effortLevel", "scope": "main", "value": "high"},
                             rule_ids=["other"])
        got = [self.entry(), self.entry(rule_ids=["other"], value="high", status="overridden")]
        self.assertEqual(resolve.compare(got, want), [])

    def test_rule_ids_of_a_row_the_file_does_not_name_do_not_count(self):
        want = self.expected({"key": "effortLevel", "scope": "main"}, rule_ids=["other"])
        got = [self.entry(), self.entry(key="model", rule_ids=["other"])]
        self.assertEqual(resolve.compare(got, want), [
            "demo: rule_ids: other is in no rule_ids of the rows the file names"])

    def test_rule_id_and_reason_are_checked_when_the_expected_entry_has_them(self):
        want = self.expected({"key": "effortLevel", "scope": "main", "rule_id": "r", "reason": "x"})
        self.assertEqual(resolve.compare([self.entry()], want), [])
        self.assertEqual(resolve.compare([self.entry(rule_id="q")], want), [
            'demo: row effortLevel/main: rule_id expected "r", got "q"'])
        self.assertEqual(resolve.compare([self.entry(reason="y")], want), [
            'demo: row effortLevel/main: reason expected "x", got "y"'])
        loose = self.expected({"key": "effortLevel", "scope": "main"})
        self.assertEqual(resolve.compare([self.entry(rule_id="q", reason="y")], loose), [])


class CommandLineTests(ResolveCase):
    def copy_fixture(self, name, target):
        shutil.copytree(os.path.join(FIXTURE_DIR, name), os.path.join(target, name))

    def test_load_fixture_reads_the_plan_and_tolerates_missing_folders(self):
        inputs, expected = resolve.load_fixture(
            os.path.join(FIXTURE_DIR, "prompt-cache-plan-api-key-five-minutes"))
        self.assertEqual((inputs.plan, inputs.flags, inputs.cli_settings, inputs.home),
                         ("api_key", [], None, None))
        self.assertEqual(inputs.shell_label, resolve.LABEL_SHELL)
        self.assertEqual((inputs.collected["settings"], inputs.collected["settings_files"]), ([], []))
        self.assertEqual(expected["fixture"], "prompt-cache-plan-api-key-five-minutes")
        self.assertEqual(resolve.compare(resolve.resolve(inputs, RULES, FIELDS), expected), [])

    def test_run_fixtures_prints_ok_and_mismatches(self):
        folder = os.path.join(self.tmp, "fixtures")
        os.makedirs(folder)
        self.copy_fixture("env-block-over-shell", folder)
        self.copy_fixture("auto-compact-top-level", folder)
        path = os.path.join(folder, "auto-compact-top-level", "expected.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["expect"][0]["value"] = 1
        _write(path, doc)
        out = io.StringIO()
        failed = resolve.run_fixtures(folder, out)
        lines = out.getvalue().splitlines()
        self.assertEqual(failed, 1)
        self.assertEqual(lines[0], "auto-compact-top-level: FAIL")
        self.assertIn("row autoCompactWindow/main: value expected 1, got 200000", lines[1])
        self.assertEqual(lines[-1], "env-block-over-shell: ok")

    def test_main_exit_codes(self):
        folder = os.path.join(self.tmp, "fixtures")
        os.makedirs(folder)
        self.copy_fixture("env-block-over-shell", folder)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(resolve.main(["resolve.py", folder]), 0)
        self.assertEqual(out.getvalue(), "env-block-over-shell: ok\n")
        with open(os.path.join(folder, "env-block-over-shell", "expected.json"), "w") as fh:
            fh.write("{broken")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(resolve.main(["resolve.py", folder]), 1)
        self.assertIn("env-block-over-shell: FAIL", out.getvalue())


if __name__ == "__main__":
    unittest.main()

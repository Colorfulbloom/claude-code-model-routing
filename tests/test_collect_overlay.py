"""Tests for the in-memory overlay of the collectors (ticket #80).

collect.collect takes overlay={path: bytes} and reuse=<an earlier collect result>, and
api_settings.resolved / answer run collect then resolve over them. Every run reads only the repo's
fixtures and its own temp folders.
"""
import json
import os
import sys
import unittest
from unittest import mock

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import api_settings  # noqa: E402
import api_usage  # noqa: E402
import collect  # noqa: E402
import projects  # noqa: E402
import resolve  # noqa: E402
import test_api_settings as tas  # noqa: E402

RULES = resolve.load_rules()
SAMPLE_FIXTURES = tas.fixture_names()[:6]
ONE = tas.fixture_names()[0]


def old_entries(ctx, listing, project):
    """The code api_settings.settings and api_usage._entries held before #80."""
    collected = collect.collect(
        config_dir=ctx.config_dir, project_dir=project.path, managed_dir=ctx.managed_dir,
        shell_env=ctx.shell_env, rules=ctx.rules)
    extra = {} if ctx.shell_label is None else {"shell_label": ctx.shell_label}
    inputs = resolve.Inputs(
        collected=collected, flags=list(ctx.flags), cli_settings=ctx.cli_settings, plan=listing.plan,
        home=ctx.home, root=ctx.root, **extra)
    return resolve.resolve(inputs, ctx.rules, ctx.agent_fields), collected


def fixture_ctx(name):
    return tas.context(os.path.join(tas.FIXTURE_DIR, name))


def current(ctx):
    listing = projects.load(ctx)
    return listing, listing.find(listing.current)


class Sandbox(unittest.TestCase):
    """A throwaway config folder and project folder."""

    def setUp(self):
        self.root = tas.new_dir(self, "overlay-")
        self.config = os.path.join(self.root, "config")
        self.project = os.path.join(self.root, "work")
        os.makedirs(self.config)
        os.makedirs(os.path.join(self.project, ".claude"))
        self.user_file = os.path.join(self.config, "settings.json")
        self.project_file = os.path.join(self.project, ".claude", "settings.json")

    def collect(self, **kwargs):
        return collect.collect(self.config, self.project, None, {}, RULES, **kwargs)


class NoOverlay(unittest.TestCase):
    def test_settings_payload_matches_old_path(self):
        for name in SAMPLE_FIXTURES:
            with self.subTest(name):
                ctx = fixture_ctx(name)
                listing, project = current(ctx)
                entries, collected = old_entries(ctx, listing, project)
                got_entries, got_collected = api_settings.resolved(ctx, project)
                self.assertEqual(entries, got_entries)
                self.assertEqual(collected, got_collected)
                self.assertEqual(entries, api_usage._entries(ctx, listing, project))
                status, payload = tas.call(ctx)
                self.assertEqual(200, status)
                self.assertEqual(payload, api_settings.answer(ctx, listing, project))
                self.assertEqual(entries, payload["entries"])

    def test_collect_default_matches_explicit_none(self):
        ctx = fixture_ctx(ONE)
        args = dict(config_dir=ctx.config_dir, project_dir=ctx.project_dir, managed_dir=ctx.managed_dir,
                    shell_env=ctx.shell_env, rules=RULES)
        self.assertEqual(collect.collect(**args), collect.collect(overlay=None, reuse=None, **args))

    def test_missing_folder_answer(self):
        ctx = fixture_ctx(ONE)
        listing, _project = current(ctx)
        gone = projects.Project("gone", "/work/does-not-exist")
        gone.key = "gone"
        self.assertEqual(projects.STATE_MISSING, gone.state)
        answer = api_settings.answer(ctx, listing, gone)
        self.assertEqual([], answer["entries"])
        self.assertEqual([], answer["attention"])
        self.assertEqual(0, answer["attention_equal"])
        self.assertEqual([], api_usage._entries(ctx, listing, gone))


class Overlay(Sandbox):
    def test_overlay_changes_the_answer(self):
        with open(self.user_file, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus"}, fh)
        before = self.collect()
        self.assertEqual("opus", before["settings"][0]["data"]["model"])
        after = self.collect(overlay={self.user_file: b'{"model": "sonnet"}'})
        self.assertEqual("sonnet", after["settings"][0]["data"]["model"])
        self.assertEqual("ok", after["settings_files"][0]["status"])

    def test_overlay_key_not_on_disk_counts_as_present(self):
        self.assertEqual([], self.collect()["settings_files"])
        got = self.collect(overlay={self.project_file: b'{"model": "haiku"}'})
        self.assertEqual([self.project_file], [r["path"] for r in got["settings_files"]])
        self.assertEqual("haiku", got["settings"][0]["data"]["model"])
        self.assertEqual({"path": self.project_file, "line": 1}, got["settings"][0]["where"][("model",)])

    def test_overlay_bytes_that_do_not_parse(self):
        got = self.collect(overlay={self.user_file: b'{"model": '})
        self.assertEqual("unparsed", got["settings_files"][0]["status"])
        self.assertEqual([], got["settings"])

    def test_overlay_does_not_touch_other_paths(self):
        with open(self.project_file, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus"}, fh)
        got = self.collect(overlay={self.user_file: b'{"model": "haiku"}'})
        layers = {s["layer"]: s["data"]["model"] for s in got["settings"]}
        self.assertEqual({"project": "opus", "user": "haiku"}, layers)

    def test_overlay_changes_resolved_entries(self):
        ctx = fixture_ctx(ONE)
        listing, project = current(ctx)
        plain, _ = api_settings.resolved(ctx, project)
        user = os.path.join(ctx.config_dir, "settings.json")
        overlay = {user: b'{"model": "sonnet"}'}
        changed, _ = api_settings.resolved(ctx, project, overlay=overlay, listing=listing)
        self.assertNotEqual(plain, changed)
        self.assertTrue(any(e["key"] == "model" and e["value"] == "sonnet" for e in changed))
        status, payload = tas.call(ctx)
        self.assertEqual(plain, payload["entries"])
        answered = api_settings.answer(ctx, listing, project, overlay=overlay)
        self.assertEqual(changed, answered["entries"])

    def test_overlay_run_reads_no_settings_file_from_disk(self):
        with open(self.user_file, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus"}, fh)
        real = collect._read_bytes
        seen = []

        def spy(path):
            seen.append(path)
            return real(path)

        with mock.patch.object(collect, "_read_bytes", spy):
            got = self.collect(overlay={self.user_file: b'{"model": "sonnet"}'})
        self.assertNotIn(self.user_file, seen)
        self.assertIn(self.project_file, seen)
        self.assertEqual("sonnet", got["settings"][0]["data"]["model"])
        with mock.patch.object(collect, "_read_bytes", spy):
            self.collect()
        self.assertIn(self.user_file, seen)


class Masking(Sandbox):
    def test_overlaid_values_are_masked(self):
        text = json.dumps({"apiKeyHelper": "sk-live-1234567890",
                           "env": {"MY_SECRET_TOKEN": "plain-value", "FINE": "ok"}}).encode()
        got = self.collect(overlay={self.user_file: text})
        data = got["settings"][0]["data"]
        self.assertEqual(collect.HIDDEN, data["apiKeyHelper"])
        self.assertEqual(collect.HIDDEN, data["env"]["MY_SECRET_TOKEN"])
        self.assertEqual("ok", data["env"]["FINE"])
        blob = repr(got)
        self.assertNotIn("sk-live-1234567890", blob)
        self.assertNotIn("plain-value", blob)

    def test_overlaid_secret_stays_hidden_in_the_answer(self):
        ctx = fixture_ctx(ONE)
        listing, project = current(ctx)
        user = os.path.join(ctx.config_dir, "settings.json")
        text = json.dumps({"effortLevel": "sk-abcdef123456", "env": {"X_SECRET": "marker-9f3"}}).encode()
        answered = api_settings.answer(ctx, listing, project, overlay={user: text})
        blob = json.dumps(answered)
        self.assertNotIn("sk-abcdef123456", blob)
        self.assertNotIn("marker-9f3", blob)


class Reuse(Sandbox):
    def test_reuse_skips_the_agent_and_rules_collectors(self):
        first = self.collect()
        with mock.patch.object(collect, "collect_agents", side_effect=AssertionError("agents ran")), \
                mock.patch.object(collect, "collect_rules_files", side_effect=AssertionError("rules ran")):
            second = self.collect(reuse=first, overlay={self.user_file: b'{"model": "haiku"}'})
        self.assertIs(first["agents"], second["agents"])
        self.assertIs(first["rules_files"], second["rules_files"])
        self.assertEqual("haiku", second["settings"][0]["data"]["model"])

    def test_reuse_still_runs_settings_and_env(self):
        first = self.collect()
        with mock.patch.object(collect, "collect_settings", wraps=collect.collect_settings) as settings, \
                mock.patch.object(collect, "collect_env", wraps=collect.collect_env) as env:
            self.collect(reuse=first)
        self.assertEqual(1, settings.call_count)
        self.assertEqual(1, env.call_count)

    def test_without_reuse_both_collectors_run(self):
        with mock.patch.object(collect, "collect_agents", wraps=collect.collect_agents) as agents, \
                mock.patch.object(collect, "collect_rules_files", wraps=collect.collect_rules_files) as rules:
            self.collect()
        self.assertEqual(1, agents.call_count)
        self.assertEqual(1, rules.call_count)

    def test_resolved_passes_reuse_through(self):
        ctx = fixture_ctx(ONE)
        listing, project = current(ctx)
        entries, collected = api_settings.resolved(ctx, project, listing=listing)
        with mock.patch.object(collect, "collect_agents", side_effect=AssertionError("agents ran")), \
                mock.patch.object(collect, "collect_rules_files", side_effect=AssertionError("rules ran")):
            again, _ = api_settings.resolved(ctx, project, listing=listing, reuse=collected)
        self.assertEqual(entries, again)


class Structure(unittest.TestCase):
    def test_api_settings_does_not_import_api_usage(self):
        path = os.path.join(helpers.REPO, "dashboard", "api_settings.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("import api_usage", text)

    def test_resolved_loads_the_listing_when_none(self):
        ctx = fixture_ctx(ONE)
        listing, project = current(ctx)
        with mock.patch.object(projects, "load", wraps=projects.load) as load:
            api_settings.resolved(ctx, project)
        self.assertEqual(1, load.call_count)
        with mock.patch.object(projects, "load", wraps=projects.load) as load:
            api_settings.resolved(ctx, project, listing=listing)
        self.assertEqual(0, load.call_count)


if __name__ == "__main__":
    unittest.main()

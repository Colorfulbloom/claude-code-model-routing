"""Tests for the in-memory overlay of the collectors: app/server/collect.py.

Ported from tests/test_collect_overlay.py (ticket #80).

``collect.collect`` takes ``overlay={path: bytes}`` and ``reuse=<an earlier collect
result>``. The old file also drove ``api_settings.resolved``, ``api_settings.answer``
and ``api_usage._entries`` over the overlay. Those are old server modules that stay
in the old app, so six tests of them did not come over. Two came over rewritten to
call ``collect`` and ``resolve.resolve`` directly. Every run reads only its own
throwaway folders.
"""

# ruff: noqa: PT009, PTH103, PTH118, PTH120, PTH123
#
# Ported unchanged so the old suite stays easy to compare: unittest assertions,
# os.path and open() string handling, % messages and long comment lines.

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import port_helpers as helpers

import collect
import resolve

RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()


class Sandbox(unittest.TestCase):
    """A throwaway config folder and project folder."""

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="overlay-", dir=helpers.tmp_base())
        self.addCleanup(helpers.rmtree_force, self.root)
        self.config = os.path.join(self.root, "config")
        self.project = os.path.join(self.root, "work")
        os.makedirs(self.config)
        os.makedirs(os.path.join(self.project, ".claude"))
        self.user_file = os.path.join(self.config, "settings.json")
        self.project_file = os.path.join(self.project, ".claude", "settings.json")

    def collect(self, **kwargs: Any) -> dict[str, Any]:
        return collect.collect(self.config, self.project, None, {}, RULES, **kwargs)


class NoOverlay(Sandbox):
    def test_collect_default_matches_explicit_none(self) -> None:
        with open(self.user_file, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus", "env": {"FINE": "ok"}}, fh)
        self.assertEqual(self.collect(), self.collect(overlay=None, reuse=None))


class Overlay(Sandbox):
    def test_overlay_changes_the_answer(self) -> None:
        with open(self.user_file, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus"}, fh)
        before = self.collect()
        self.assertEqual("opus", before["settings"][0]["data"]["model"])
        after = self.collect(overlay={self.user_file: b'{"model": "sonnet"}'})
        self.assertEqual("sonnet", after["settings"][0]["data"]["model"])
        self.assertEqual("ok", after["settings_files"][0]["status"])

    def test_overlay_key_not_on_disk_counts_as_present(self) -> None:
        self.assertEqual([], self.collect()["settings_files"])
        got = self.collect(overlay={self.project_file: b'{"model": "haiku"}'})
        self.assertEqual(
            [self.project_file], [r["path"] for r in got["settings_files"]]
        )
        self.assertEqual("haiku", got["settings"][0]["data"]["model"])
        self.assertEqual(
            {"path": self.project_file, "line": 1},
            got["settings"][0]["where"][("model",)],
        )

    def test_overlay_bytes_that_do_not_parse(self) -> None:
        got = self.collect(overlay={self.user_file: b'{"model": '})
        self.assertEqual("unparsed", got["settings_files"][0]["status"])
        self.assertEqual([], got["settings"])

    def test_overlay_does_not_touch_other_paths(self) -> None:
        with open(self.project_file, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus"}, fh)
        got = self.collect(overlay={self.user_file: b'{"model": "haiku"}'})
        layers = {s["layer"]: s["data"]["model"] for s in got["settings"]}
        self.assertEqual({"project": "opus", "user": "haiku"}, layers)

    def test_overlay_run_reads_no_settings_file_from_disk(self) -> None:
        with open(self.user_file, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus"}, fh)
        real = collect._read_bytes  # pyright: ignore[reportPrivateUsage]
        seen: list[str] = []

        def spy(path: str) -> tuple[bytes | None, str]:
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
    def test_overlaid_values_are_masked(self) -> None:
        text = json.dumps(
            {
                "apiKeyHelper": "sk-live-1234567890",
                "env": {"MY_SECRET_TOKEN": "plain-value", "FINE": "ok"},
            }
        ).encode()
        got = self.collect(overlay={self.user_file: text})
        data = got["settings"][0]["data"]
        self.assertEqual(collect.HIDDEN, data["apiKeyHelper"])
        self.assertEqual(collect.HIDDEN, data["env"]["MY_SECRET_TOKEN"])
        self.assertEqual("ok", data["env"]["FINE"])
        blob = repr(got)
        self.assertNotIn("sk-live-1234567890", blob)
        self.assertNotIn("plain-value", blob)


class TwoLocalOverlay(Sandbox):
    def setUp(self) -> None:
        super().setUp()
        self.root_file = os.path.join(
            self.root, "repo", ".claude", "settings.local.json"
        )
        self.start_file = os.path.join(self.project, ".claude", "settings.local.json")
        os.makedirs(os.path.dirname(self.root_file))
        for path, data in (
            (self.start_file, {"model": "leftover"}),
            (self.root_file, {"model": "root"}),
        ):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh)

    def local_source(self, got: Any) -> Any:
        return next(s for s in got["settings"] if s["layer"] == "local")

    def test_an_overlay_keyed_on_the_root_path_replaces_the_root_file(self) -> None:
        got = self.collect(
            local_path=self.root_file, overlay={self.root_file: b'{"model": "edited"}'}
        )
        local = self.local_source(got)
        self.assertEqual("edited", local["data"]["model"])
        self.assertEqual(self.root_file, local["where"][("model",)]["path"])

    def test_an_overlay_keyed_on_the_leftover_path_replaces_the_leftover(self) -> None:
        with open(self.root_file, "w", encoding="utf-8") as fh:
            json.dump({"theme": "dark"}, fh)
        got = self.collect(
            local_path=self.root_file, overlay={self.start_file: b'{"model": "edited"}'}
        )
        local = self.local_source(got)
        self.assertEqual({"model": "edited", "theme": "dark"}, local["data"])
        self.assertEqual(self.start_file, local["where"][("model",)]["path"])


class Reuse(Sandbox):
    def test_reuse_skips_the_agent_and_rules_collectors(self) -> None:
        first = self.collect()
        with (
            mock.patch.object(
                collect, "collect_agents", side_effect=AssertionError("agents ran")
            ),
            mock.patch.object(
                collect, "collect_rules_files", side_effect=AssertionError("rules ran")
            ),
        ):
            second = self.collect(
                reuse=first, overlay={self.user_file: b'{"model": "haiku"}'}
            )
        self.assertIs(first["agents"], second["agents"])
        self.assertIs(first["rules_files"], second["rules_files"])
        self.assertEqual("haiku", second["settings"][0]["data"]["model"])

    def test_reuse_still_runs_settings_and_env(self) -> None:
        first = self.collect()
        with (
            mock.patch.object(
                collect, "collect_settings", wraps=collect.collect_settings
            ) as settings,
            mock.patch.object(collect, "collect_env", wraps=collect.collect_env) as env,
        ):
            self.collect(reuse=first)
        self.assertEqual(1, settings.call_count)
        self.assertEqual(1, env.call_count)

    def test_without_reuse_both_collectors_run(self) -> None:
        with (
            mock.patch.object(
                collect, "collect_agents", wraps=collect.collect_agents
            ) as agents,
            mock.patch.object(
                collect, "collect_rules_files", wraps=collect.collect_rules_files
            ) as rules,
        ):
            self.collect()
        self.assertEqual(1, agents.call_count)
        self.assertEqual(1, rules.call_count)


class ResolveOverlay(Sandbox):
    def inputs(self, collected: dict[str, Any]) -> resolve.Inputs:
        return resolve.Inputs(collected=collected, home=self.root, root=self.project)

    def test_overlay_changes_resolved_entries(self) -> None:
        with open(self.user_file, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus"}, fh)
        plain = resolve.resolve(self.inputs(self.collect()), RULES, FIELDS)
        changed = resolve.resolve(
            self.inputs(self.collect(overlay={self.user_file: b'{"model": "sonnet"}'})),
            RULES,
            FIELDS,
        )
        self.assertNotEqual(plain, changed)
        self.assertTrue(
            any(e["key"] == "model" and e["value"] == "sonnet" for e in changed)
        )

    def test_overlaid_secret_stays_hidden_in_the_entries(self) -> None:
        text = json.dumps(
            {"effortLevel": "sk-abcdef123456", "env": {"X_SECRET": "marker-9f3"}}
        ).encode()
        entries = resolve.resolve(
            self.inputs(self.collect(overlay={self.user_file: text})), RULES, FIELDS
        )
        blob = json.dumps(entries)
        self.assertNotIn("sk-abcdef123456", blob)
        self.assertNotIn("marker-9f3", blob)

    def test_reuse_passes_through_to_resolve(self) -> None:
        first = self.collect()
        entries = resolve.resolve(self.inputs(first), RULES, FIELDS)
        with (
            mock.patch.object(
                collect, "collect_agents", side_effect=AssertionError("agents ran")
            ),
            mock.patch.object(
                collect, "collect_rules_files", side_effect=AssertionError("rules ran")
            ),
        ):
            again = resolve.resolve(
                self.inputs(self.collect(reuse=first)), RULES, FIELDS
            )
        self.assertEqual(entries, again)

"""Tests for the project list: app/server/projects.py.

Ported from tests/test_projects.py. The old tests also drove /api/projects and
/api/settings through a running server. Those routes stay in the old app, so only
the tests of ``projects.load`` came over, and they read the list through a
``ProjectsContext`` instead of the old server context. Every name and path here is
made up. Secrets are strings that start with "sk-planted-" and no other value in
these tests contains "planted".
"""

# ruff: noqa: PT009, PT027, PTH103, PTH118, PTH120, PTH123

# old tests so the two suites stay easy to compare.
import contextlib
import dataclasses
import io
import json
import os
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import port_helpers as helpers

import projects

CONFIG_FILE = "routing-dashboard.json"
T = TypeVar("T")


def write(path: str, text: str) -> str:
    """Write a text file, making its folder first, and return the path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def write_json(path: str, data: object) -> str:
    """Write a JSON file, making its folder first, and return the path."""
    return write(path, json.dumps(data))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.root = os.path.realpath(
            tempfile.mkdtemp(prefix="projects-", dir=helpers.tmp_base())
        )
        self.addCleanup(helpers.rmtree_force, self.root)
        self.fx = os.path.join(self.root, "fx")
        self.cfg = os.path.join(self.root, "cfg")
        os.makedirs(self.fx)
        os.makedirs(self.cfg)

    def make_project(
        self, name: str, claude: bool = True, settings: dict[str, Any] | None = None
    ) -> str:
        path = os.path.join(self.root, "work", name)
        os.makedirs(path, exist_ok=True)
        if claude:
            write_json(os.path.join(path, ".claude", "settings.json"), settings or {})
        return path

    def write_list(self, items: list[Any], **extra: Any) -> None:
        data = {"projects": items}
        data.update(extra)
        write_json(os.path.join(self.cfg, CONFIG_FILE), data)

    def ctx(
        self,
        home: str | None = None,
        project: str | None = None,
        root: str | None = None,
    ) -> projects.ProjectsContext:
        return projects.ProjectsContext(
            config_dir=self.cfg,
            project_dir=project or os.path.join(self.fx, "project"),
            project_explicit=project is not None,
            root=root,
            home=home,
        )

    def stderr_of(self, fn: Callable[[], T]) -> tuple[T, str]:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = fn()
        return result, buf.getvalue()

    def names(self, listing: projects.ProjectList) -> list[str]:
        return [p.name for p in listing.projects]


class Format(Base):
    def test_absolute_path(self) -> None:
        a = self.make_project("alpha")
        self.write_list([{"name": "Alpha", "path": a}])
        listing = projects.load(self.ctx())
        self.assertEqual(
            [(p.key, p.name, p.path, p.state) for p in listing.projects],
            [("alpha", "Alpha", a, "ok")],
        )
        self.assertEqual(listing.current, "alpha")

    def test_relative_path_resolves_against_the_config_folder(self) -> None:
        os.makedirs(os.path.join(self.cfg, "sub", "proj", ".claude"))
        os.makedirs(os.path.join(self.root, "rel-proj", ".claude"))
        self.write_list(
            [
                {"name": "One", "path": "sub/proj"},
                {"name": "Two", "path": "../rel-proj"},
            ]
        )
        listing = projects.load(self.ctx())
        self.assertEqual([p.state for p in listing.projects], ["ok", "ok"])
        self.assertEqual(
            listing.projects[0].path, os.path.join(self.cfg, "sub", "proj")
        )
        self.assertEqual(listing.projects[1].path, os.path.join(self.root, "rel-proj"))

    def test_tilde_expands_with_home(self) -> None:
        home = os.path.join(self.root, "fakehome")
        os.makedirs(os.path.join(home, "work", "shop", ".claude"))
        self.write_list(
            [
                {"name": "Shop", "path": "~/work/shop"},
                {"name": "Home", "path": "~"},
                {"name": "Gone", "path": "~/work/gone"},
            ]
        )
        rows = {p.key: p for p in projects.load(self.ctx(home=home)).projects}
        self.assertEqual(rows["shop"].path, os.path.join(home, "work", "shop"))
        self.assertEqual(rows["shop"].state, "ok")
        self.assertEqual(rows["home"].path, home)
        self.assertEqual(rows["home"].state, "no_claude_folder")
        self.assertEqual(rows["gone"].path, os.path.join(home, "work", "gone"))
        self.assertEqual(rows["gone"].state, "folder_not_found")

    def test_tilde_without_a_home_stays_unexpanded_and_not_found(self) -> None:
        self.write_list([{"name": "Shop", "path": "~/work/shop"}])
        row = projects.load(self.ctx(home=None)).projects[0]
        self.assertEqual(row.state, "folder_not_found")
        self.assertEqual(row.path, "~/work/shop")
        self.assertTrue(row.unexpanded)

    def test_the_old_state_name_is_gone(self) -> None:
        self.write_list([{"name": "Gone", "path": os.path.join(self.root, "gone")}])
        state = projects.load(self.ctx()).projects[0].state
        self.assertEqual(state, "folder_not_found")
        self.assertEqual(projects.STATE_FOLDER_NOT_FOUND, "folder_not_found")
        self.assertFalse(hasattr(projects, "STATE_MISSING"))

    def test_no_file_lists_the_current_project_only(self) -> None:
        listing = projects.load(self.ctx())
        self.assertEqual(len(listing.projects), 1)
        self.assertEqual(listing.projects[0].name, "project")
        self.assertTrue(listing.projects[0].implicit)
        self.assertEqual(listing.current, "project")

    def test_broken_json_falls_back_with_one_fixed_stderr_line(self) -> None:
        write(os.path.join(self.cfg, CONFIG_FILE), "{not json sk-planted-broken-0001")
        listing, err = self.stderr_of(lambda: projects.load(self.ctx()))
        self.assertEqual(self.names(listing), ["project"])
        self.assertEqual(len(err.splitlines()), 1)
        self.assertNotIn("sk-planted", err)

    def test_non_object_falls_back_with_one_fixed_stderr_line(self) -> None:
        write(os.path.join(self.cfg, CONFIG_FILE), '["sk-planted-array-0002"]')
        listing, err = self.stderr_of(lambda: projects.load(self.ctx()))
        self.assertEqual(self.names(listing), ["project"])
        self.assertEqual(len(err.splitlines()), 1)
        self.assertNotIn("sk-planted", err)

    def test_unreadable_file_falls_back(self) -> None:
        # A folder cannot be read as a file.
        os.makedirs(os.path.join(self.cfg, CONFIG_FILE))
        listing, err = self.stderr_of(lambda: projects.load(self.ctx()))
        self.assertEqual(self.names(listing), ["project"])
        self.assertEqual(len(err.splitlines()), 1)

    def test_no_valid_entry_falls_back(self) -> None:
        self.write_list(
            [
                {"name": "", "path": "/x"},
                {"name": "n"},
                "text",
                5,
                {"name": 3, "path": "/y"},
                {"name": "n", "path": ""},
            ]
        )
        listing, err = self.stderr_of(lambda: projects.load(self.ctx()))
        self.assertEqual(self.names(listing), ["project"])
        self.assertEqual(len(err.splitlines()), 1)

    def test_bad_entries_are_skipped_and_good_ones_kept(self) -> None:
        a = self.make_project("alpha")
        self.write_list(
            ["text", {"name": "x"}, {"name": "Alpha", "path": a}, {"path": a}, None]
        )
        self.assertEqual(self.names(projects.load(self.ctx())), ["Alpha"])

    def test_same_normalized_path_keeps_the_first(self) -> None:
        a = self.make_project("alpha")
        self.write_list(
            [
                {"name": "First", "path": a},
                {"name": "Second", "path": a + "/"},
                {"name": "Third", "path": os.path.join(a, "..", "alpha")},
            ]
        )
        self.assertEqual(self.names(projects.load(self.ctx())), ["First"])

    def test_a_file_with_only_a_plan_lists_the_current_project_quietly(self) -> None:
        write_json(os.path.join(self.cfg, CONFIG_FILE), {"plan": "api_key"})
        listing, err = self.stderr_of(lambda: projects.load(self.ctx()))
        self.assertEqual(self.names(listing), ["project"])
        self.assertEqual(err, "")


class Keys(Base):
    def keys_for(self, names: list[str]) -> list[str | None]:
        self.write_list(
            [{"name": n, "path": f"/nowhere/{i}"} for i, n in enumerate(names)]
        )
        return [p.key for p in projects.load(self.ctx()).projects]

    def test_slug(self) -> None:
        self.assertEqual(
            self.keys_for(["  My Big_App!! v2  ", "--x--"]), ["my-big-app-v2", "x"]
        )

    def test_slug_function(self) -> None:
        self.assertEqual(projects.slug("  My Big_App!! v2  "), "my-big-app-v2")
        self.assertEqual(projects.slug("!!!"), "project")

    def test_all_is_reserved(self) -> None:
        self.assertEqual(self.keys_for(["All", "ALL"]), ["all-2", "all-3"])

    def test_duplicates_count_up_in_list_order(self) -> None:
        self.assertEqual(
            self.keys_for(["Shop", "shop", "SHOP!", "Shop 2"]),
            ["shop", "shop-2", "shop-3", "shop-2-2"],
        )

    def test_non_ascii_names(self) -> None:
        self.assertEqual(
            self.keys_for(["Café ☕", "日本", "日本語", "!!!"]),
            ["caf", "project", "project-2", "project-3"],
        )


class States(Base):
    def test_all_three_states(self) -> None:
        ok = self.make_project("withclaude")
        bare = self.make_project("bare", claude=False)
        gone = os.path.join(self.root, "work", "gone")
        file_path = write(os.path.join(self.root, "work", "afile"), "x")
        self.write_list(
            [
                {"name": "Ok", "path": ok},
                {"name": "Bare", "path": bare},
                {"name": "Gone", "path": gone},
                {"name": "File", "path": file_path},
            ]
        )
        self.assertEqual(
            [p.state for p in projects.load(self.ctx()).projects],
            ["ok", "no_claude_folder", "folder_not_found", "folder_not_found"],
        )


class Current(Base):
    def test_explicit_project_is_added_first(self) -> None:
        a = self.make_project("alpha")
        extra = self.make_project("extra")
        self.write_list([{"name": "Alpha", "path": a}])
        listing = projects.load(self.ctx(project=extra))
        self.assertEqual(self.names(listing), ["extra", "Alpha"])
        self.assertEqual(listing.current, "extra")

    def test_explicit_project_that_is_listed_is_not_added(self) -> None:
        a = self.make_project("alpha")
        b = self.make_project("beta")
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        listing = projects.load(self.ctx(project=b))
        self.assertEqual(self.names(listing), ["Alpha", "Beta"])
        self.assertEqual(listing.current, "beta")

    def test_without_project_the_list_is_the_files_and_current_is_first(self) -> None:
        a = self.make_project("alpha")
        b = self.make_project("beta")
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        listing = projects.load(self.ctx())
        self.assertEqual(self.names(listing), ["Alpha", "Beta"])
        self.assertEqual(listing.current, "alpha")

    def test_a_hand_edit_of_the_list_shows_in_the_next_load(self) -> None:
        a = self.make_project("alpha")
        b = self.make_project("beta")
        self.write_list([{"name": "Alpha", "path": a}])
        first = projects.load(self.ctx())
        self.write_list([{"name": "Alpha", "path": a}, {"name": "Beta", "path": b}])
        second = projects.load(self.ctx())
        self.assertEqual([p.key for p in first.projects], ["alpha"])
        self.assertEqual([p.key for p in second.projects], ["alpha", "beta"])
        found = second.find("beta")
        self.assertIsNotNone(found)
        self.assertIsNone(second.find("nope"))

    def test_the_context_is_frozen(self) -> None:
        ctx = self.ctx()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ctx.home = "/work/x"  # pyright: ignore[reportAttributeAccessIssue] - the frozen field is the test


class Plan(Base):
    def plan_file(self, value: object) -> None:
        write_json(os.path.join(self.cfg, CONFIG_FILE), {"plan": value})

    def test_each_plan_word_is_read(self) -> None:
        for word in ("subscription", "api_key", "cloud_provider"):
            with self.subTest(plan=word):
                self.plan_file(word)
                self.assertEqual(projects.load(self.ctx()).plan, word)

    def test_missing_plan_is_none(self) -> None:
        write_json(os.path.join(self.cfg, CONFIG_FILE), {"projects": []})
        listing, err = self.stderr_of(lambda: projects.load(self.ctx()))
        self.assertIsNone(listing.plan)
        self.assertIn("no valid project entry", err)

    def test_unknown_plan_behaves_as_unset_and_is_never_logged(self) -> None:
        for value in ("planted-plan-value-0001", 7, ["api_key"], "API_KEY"):
            with self.subTest(plan=value):
                self.plan_file(value)
                listing, err = self.stderr_of(lambda: projects.load(self.ctx()))
                self.assertIsNone(listing.plan)
                self.assertNotIn("planted-plan", err)
                self.assertIn("unknown plan", err)

    def test_the_fixture_dashboard_json_gives_the_plan_when_the_file_gives_none(
        self,
    ) -> None:
        write_json(os.path.join(self.fx, "dashboard.json"), {"plan": "api_key"})
        self.assertEqual(projects.load(self.ctx(root=self.fx)).plan, "api_key")
        write_json(os.path.join(self.fx, "dashboard.json"), {"plan": "bogus"})
        listing, err = self.stderr_of(lambda: projects.load(self.ctx(root=self.fx)))
        self.assertIsNone(listing.plan)
        self.assertIn("dashboard.json has an unknown plan", err)

    def test_the_file_wins_over_the_fixture_dashboard_json(self) -> None:
        write_json(os.path.join(self.fx, "dashboard.json"), {"plan": "api_key"})
        self.plan_file("subscription")
        self.assertEqual(projects.load(self.ctx(root=self.fx)).plan, "subscription")


if __name__ == "__main__":
    unittest.main()

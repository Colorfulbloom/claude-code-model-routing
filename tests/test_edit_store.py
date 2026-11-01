"""Tests for dashboard/edit_store.py, the only module that writes.

Every test runs on temp folders: a throwaway config folder, a project folder and
a made-up managed folder. Nothing reads the real Claude config folder. Secrets
are made-up strings that start with "sk-planted-". A crash is simulated by a
seam that raises a BaseException subclass, so no cleanup handler runs.
"""
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import helpers

DASHBOARD = os.path.join(helpers.REPO, "dashboard")
sys.path.insert(0, DASHBOARD)
import edit_store as es  # noqa: E402

SETTINGS = b'{\n  "effortLevel": "low",\n  "env": {"NOTE": "a"}\n}\n'
BAK_RE = re.compile(r"^\d{6}-[0-9a-f]{16}\.bak$")
EFFORT_RE = re.compile(rb'"effortLevel": "[a-z0-9]+"')


class Crash(BaseException):
    """Raised by a seam to stop the process at a step. No cleanup handler catches it."""


class Ctx:
    def __init__(self, config_dir, project_dir, managed_dir, home=None):
        self.config_dir = config_dir
        self.project_dir = project_dir
        self.managed_dir = managed_dir
        self.home = home
        self.root = None
        self.project_explicit = False


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def effort_plan(value):
    """A plan_fn that sets effortLevel to value with a byte splice."""
    def plan(raw):
        old = json.loads(raw.decode("utf-8")).get("effortLevel")
        new_raw = EFFORT_RE.sub(b'"effortLevel": "' + value.encode("ascii") + b'"', raw, count=1)
        return es.Plan(new_raw, ["effortLevel"], old, value)
    return plan


def fd_count():
    return len(os.listdir("/dev/fd"))


class Base(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-edit-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, self.root)
        self.cfg = os.path.join(self.root, "cfg")
        self.proj = os.path.join(self.root, "work", "demo")
        self.managed = os.path.join(self.root, "managed")
        for folder in (self.cfg, self.managed, os.path.join(self.proj, ".claude")):
            os.makedirs(folder)
        write(os.path.join(self.cfg, "routing-dashboard.json"),
              json.dumps({"projects": [{"name": "Demo", "path": self.proj}]}).encode())
        self.user_file = write(os.path.join(self.cfg, "settings.json"), SETTINGS)
        self.project_file = write(os.path.join(self.proj, ".claude", "settings.json"), SETTINGS)
        self.local_file = write(os.path.join(self.proj, ".claude", "settings.local.json"), SETTINGS)
        self.ctx = Ctx(self.cfg, self.proj, self.managed, home=os.path.join(self.root, "home"))
        self.store = es.Store(self.cfg)

    def target(self, layer="project"):
        return es.target_for(self.ctx, "demo", layer)

    def store_dir(self, target=None):
        target = target or self.target()
        return os.path.join(self.cfg, "routing-dashboard", "backups", self.store.target_id(target))

    def baks(self, target=None):
        folder = self.store_dir(target)
        if not os.path.isdir(folder):
            return []
        return sorted(n for n in os.listdir(folder) if BAK_RE.match(n))

    def leftovers(self):
        return sorted(n for n in os.listdir(os.path.join(self.proj, ".claude"))
                      if n.startswith(".routing-dashboard-"))

    def at(self, name, fn):
        """Run fn when the store reaches the seam called name."""
        def seam(seen):
            if seen == name:
                fn()
        self.store.seam = seam

    def crash_at(self, name):
        def boom():
            raise Crash(name)
        self.at(name, boom)

    def tree(self):
        found = []
        for dirpath, dirnames, filenames in os.walk(self.cfg):
            found.extend(os.path.join(dirpath, n) for n in dirnames + filenames)
        return sorted(found)


class TargetTests(Base):
    def test_three_layers_give_the_collect_paths(self):
        self.assertEqual(os.path.join(self.cfg, "settings.json"), self.target("user").path)
        self.assertEqual(os.path.join(self.proj, ".claude", "settings.json"),
                         self.target("project").path)
        self.assertEqual(os.path.join(self.proj, ".claude", "settings.local.json"),
                         self.target("local").path)
        self.assertEqual((), self.target("user").rel)
        self.assertEqual((".claude",), self.target("local").rel)

    def test_a_layer_outside_the_three_is_not_editable(self):
        for layer in ("managed", "flag", "env", "default", "cli", "", None, "../x", "User"):
            with self.assertRaises(es.Refused) as ctx:
                es.target_for(self.ctx, "demo", layer)
            self.assertEqual("not_editable", ctx.exception.code, layer)

    def test_an_unlisted_project_key_is_refused(self):
        for key in ("nope", "all", "", "../demo", "Demo", None):
            with self.assertRaises(es.Refused) as ctx:
                es.target_for(self.ctx, key, "project")
            self.assertEqual("unknown_project", ctx.exception.code, key)

    def test_the_implicit_current_project_is_listed(self):
        bare = os.path.join(self.root, "bare")
        os.makedirs(os.path.join(bare, ".claude"))
        other = Ctx(os.path.join(self.root, "cfg2"), bare, None)
        os.makedirs(other.config_dir)
        target = es.target_for(other, "bare", "local")
        self.assertEqual(os.path.join(bare, ".claude", "settings.local.json"), target.path)

    def test_a_project_path_that_did_not_expand_is_refused(self):
        write(os.path.join(self.cfg, "routing-dashboard.json"),
              json.dumps({"projects": [{"name": "Tilde", "path": "~/x"}]}).encode())
        self.ctx.home = None
        with self.assertRaises(es.Refused) as ctx:
            es.target_for(self.ctx, "tilde", "project")
        self.assertEqual("file_missing", ctx.exception.code)

    def test_config_dir_at_the_managed_folder_is_managed(self):
        write(os.path.join(self.managed, "settings.json"), SETTINGS)
        self.ctx.config_dir = self.managed
        with self.assertRaises(es.Refused) as ctx:
            es.target_for(self.ctx, "demo", "user")
        self.assertEqual("managed", ctx.exception.code)

    def test_config_dir_under_the_managed_folder_is_managed(self):
        inner = os.path.join(self.managed, "inner")
        os.makedirs(inner)
        self.ctx.config_dir = inner
        with self.assertRaises(es.Refused) as ctx:
            es.target_for(self.ctx, "demo", "user")
        self.assertEqual("managed", ctx.exception.code)

    def test_a_link_to_the_managed_folder_is_managed(self):
        link = os.path.join(self.root, "alias")
        os.symlink(self.managed, link)
        self.ctx.config_dir = link
        with self.assertRaises(es.Refused) as ctx:
            es.target_for(self.ctx, "demo", "user")
        self.assertEqual("managed", ctx.exception.code)

    def test_a_project_inside_the_managed_folder_is_managed(self):
        inside = os.path.join(self.managed, "proj")
        os.makedirs(os.path.join(inside, ".claude"))
        write(os.path.join(self.cfg, "routing-dashboard.json"),
              json.dumps({"projects": [{"name": "In", "path": inside}]}).encode())
        with self.assertRaises(es.Refused) as ctx:
            es.target_for(self.ctx, "in", "project")
        self.assertEqual("managed", ctx.exception.code)

    def test_no_managed_dir_still_builds_targets(self):
        self.ctx.managed_dir = None
        self.assertEqual(self.project_file, self.target("project").path)

    def test_a_managed_settings_basename_is_managed(self):
        target = es.Target("user", self.cfg, (), "managed-settings.json")
        with self.assertRaises(es.Refused) as ctx:
            es.read_target(target)
        self.assertEqual("managed", ctx.exception.code)

    def test_the_walk_checks_managed_again(self):
        target = self.target("project")
        claude = os.path.join(self.proj, ".claude")
        for name in os.listdir(claude):
            os.unlink(os.path.join(claude, name))
        os.rmdir(claude)
        write(os.path.join(self.managed, "settings.json"), SETTINGS)
        os.symlink(self.managed, claude)
        with self.assertRaises(es.Refused) as ctx:
            es.read_target(target)
        self.assertEqual("managed", ctx.exception.code)

    def test_target_id_is_sixteen_hex_and_ignores_links_on_the_way(self):
        target = self.target("project")
        self.assertRegex(self.store.target_id(target), r"^[0-9a-f]{16}$")
        expected = hashlib.sha256(os.fsencode(self.project_file)).hexdigest()[:16]
        self.assertEqual(expected, self.store.target_id(target))
        alias = os.path.join(self.root, "alias-proj")
        os.symlink(self.proj, alias)
        write(os.path.join(self.cfg, "routing-dashboard.json"),
              json.dumps({"projects": [{"name": "Demo", "path": self.proj},
                                       {"name": "Alias", "path": alias}]}).encode())
        via_alias = es.target_for(self.ctx, "alias", "project")
        self.assertEqual(self.store.target_id(target), self.store.target_id(via_alias))
        self.assertNotEqual(self.store.target_id(target), self.store.target_id(self.target("local")))
        self.assertNotEqual(self.store.target_id(target), self.store.target_id(self.target("user")))


class WalkTests(Base):
    def refused(self, target):
        with self.assertRaises(es.Refused) as ctx:
            es.read_target(target)
        return ctx.exception.code

    def test_a_plain_file_reads(self):
        self.assertEqual(SETTINGS, es.read_target(self.target("project")))
        self.assertEqual(SETTINGS, es.read_target(self.target("user")))

    def test_claude_folder_as_a_symlink(self):
        target = self.target("project")
        real = os.path.join(self.root, "elsewhere")
        os.makedirs(real)
        write(os.path.join(real, "settings.json"), SETTINGS)
        claude = os.path.join(self.proj, ".claude")
        for name in os.listdir(claude):
            os.unlink(os.path.join(claude, name))
        os.rmdir(claude)
        os.symlink(real, claude)
        self.assertEqual("symlink", self.refused(target))

    def test_claude_folder_as_a_plain_file(self):
        target = self.target("project")
        claude = os.path.join(self.proj, ".claude")
        for name in os.listdir(claude):
            os.unlink(os.path.join(claude, name))
        os.rmdir(claude)
        write(claude, b"x")
        self.assertEqual("not_regular", self.refused(target))

    def test_missing_claude_folder_and_missing_file(self):
        target = self.target("project")
        os.unlink(self.project_file)
        self.assertEqual("file_missing", self.refused(target))
        os.unlink(self.local_file)
        os.rmdir(os.path.join(self.proj, ".claude"))
        self.assertEqual("file_missing", self.refused(target))

    def test_missing_base_folder(self):
        target = self.target("project")
        os.unlink(self.project_file)
        os.unlink(self.local_file)
        os.rmdir(os.path.join(self.proj, ".claude"))
        os.rmdir(self.proj)
        self.assertEqual("file_missing", self.refused(target))

    def test_leaf_symlink_project_and_user(self):
        outside = write(os.path.join(self.root, "outside.json"), SETTINGS)
        for layer, path in (("project", self.project_file), ("user", self.user_file)):
            target = self.target(layer)
            os.unlink(path)
            os.symlink(outside, path)
            self.assertEqual("symlink", self.refused(target), layer)
        self.assertEqual(SETTINGS, read(outside))

    def test_dangling_leaf_symlink(self):
        target = self.target("project")
        os.unlink(self.project_file)
        os.symlink(os.path.join(self.root, "nowhere.json"), self.project_file)
        self.assertEqual("symlink", self.refused(target))

    def test_leaf_hard_link(self):
        target = self.target("project")
        os.link(self.project_file, os.path.join(self.root, "twin.json"))
        self.assertEqual("hard_link", self.refused(target))

    def test_leaf_directory(self):
        target = self.target("project")
        os.unlink(self.project_file)
        os.mkdir(self.project_file)
        self.assertEqual("not_regular", self.refused(target))

    def test_leaf_fifo_returns_without_hanging(self):
        target = self.target("project")
        os.unlink(self.project_file)
        os.mkfifo(self.project_file)
        outcome = {}

        def run():
            try:
                es.read_target(target)
                outcome["code"] = "read"
            except es.Refused as exc:
                outcome["code"] = exc.code

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(10)
        self.assertFalse(worker.is_alive(), "the walk hung on a FIFO")
        self.assertEqual("not_regular", outcome.get("code"))

    def test_leaf_fifo_in_a_save_creates_no_store_folder(self):
        target = self.target("project")
        os.unlink(self.project_file)
        os.mkfifo(self.project_file)
        outcome = {}

        def run():
            try:
                self.store.save(target, effort_plan("high"))
            except es.Refused as exc:
                outcome["code"] = exc.code

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(10)
        self.assertFalse(worker.is_alive(), "the save hung on a FIFO")
        self.assertEqual("not_regular", outcome.get("code"))
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "routing-dashboard")))

    def test_a_file_that_is_not_ours(self):
        target = self.target("project")
        with mock.patch.object(os, "geteuid", return_value=os.geteuid() + 1):
            self.assertEqual("not_owner", self.refused(target))

    @unittest.skipIf(os.geteuid() == 0, "root can open any file")
    def test_an_unreadable_file_is_not_owner(self):
        target = self.target("project")
        os.chmod(self.project_file, 0)
        self.addCleanup(os.chmod, self.project_file, 0o600)
        self.assertEqual("not_owner", self.refused(target))

    def test_size_limit(self):
        target = self.target("project")
        write(self.project_file, b" " * es.MAX_FILE)
        self.assertEqual(es.MAX_FILE, len(es.read_target(target)))
        write(self.project_file, b" " * (es.MAX_FILE + 1))
        self.assertEqual("too_large", self.refused(target))

    def test_a_save_that_grows_the_file_past_the_cap_is_too_large(self):
        target = self.target("project")
        raw = b" " * es.MAX_FILE
        write(self.project_file, raw)
        with self.assertRaises(es.Refused) as ctx:
            self.store.save(target, lambda r: es.Plan(r + b" " * 25, ["effortLevel"], None, "high"))
        self.assertEqual("too_large", ctx.exception.code)
        self.assertEqual(raw, read(self.project_file))
        self.assertEqual([], self.baks(target))
        self.assertEqual([], self.store.rows(target))

    def test_a_file_that_grows_during_the_read_is_too_large(self):
        target = self.target("project")
        write(self.project_file, b" " * 10)
        real_fstat = os.fstat

        def small_fstat(fd):
            info = real_fstat(fd)
            if stat.S_ISREG(info.st_mode):
                write(self.project_file, b" " * (es.MAX_FILE + 5))
            return os.stat_result((info.st_mode, info.st_ino, info.st_dev, info.st_nlink,
                                   info.st_uid, info.st_gid, 10, int(info.st_atime),
                                   int(info.st_mtime), int(info.st_ctime)))

        with mock.patch.object(os, "fstat", side_effect=small_fstat):
            self.assertEqual("too_large", self.refused(target))

    def test_every_walk_closes_its_descriptors(self):
        target = self.target("project")
        before = fd_count()
        for _ in range(20):
            es.read_target(target)
            with self.assertRaises(es.Refused):
                es.read_target(es.Target("project", self.proj, (".claude",), "missing.json"))
        self.assertEqual(before, fd_count())


class SaveTests(Base):
    def test_save_splices_and_keeps_every_other_byte(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(self.project_file))
        self.assertEqual("edit", row["kind"])
        self.assertEqual(["effortLevel"], row["key_path"])
        self.assertEqual("project", row["layer"])
        self.assertEqual("low", row["old_value"])
        self.assertEqual("high", row["new_value"])
        self.assertEqual(sha(SETTINGS), row["before_sha256"])
        self.assertEqual(sha(read(self.project_file)), row["after_sha256"])
        self.assertIsNone(row["restored_from"])
        self.assertIsNone(row["restored_from_backup"])
        self.assertRegex(row["backup"], r"^000001-[0-9a-f]{16}\.bak$")
        self.assertEqual(SETTINGS, read(os.path.join(self.store_dir(), row["backup"])))
        self.assertEqual([row], self.store.rows(target))
        self.assertEqual(row, self.store.find(target, row["id"]))
        self.assertIsNone(self.store.find(target, "nope"))

    def test_all_three_layers_save_into_the_config_folder(self):
        ids = set()
        for layer in es.LAYERS:
            target = self.target(layer)
            row = self.store.save(target, effort_plan("high"))
            ids.add(self.store.target_id(target))
            self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(target.path), layer)
            self.assertEqual([row["backup"]], self.baks(target), layer)
        self.assertEqual(3, len(ids))
        self.assertEqual(["routing-dashboard"],
                         sorted(n for n in os.listdir(self.cfg) if n == "routing-dashboard"))
        self.assertEqual([".claude"], os.listdir(self.proj))

    def test_nothing_lands_in_the_project_folder_but_the_file(self):
        before = sorted(os.listdir(os.path.join(self.proj, ".claude")))
        self.store.save(self.target("local"), effort_plan("high"))
        self.assertEqual(before, sorted(os.listdir(os.path.join(self.proj, ".claude"))))

    def test_modes_are_kept_and_the_store_is_private(self):
        os.chmod(self.project_file, 0o640)
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        self.assertEqual(0o640, stat.S_IMODE(os.stat(self.project_file).st_mode))
        folder = self.store_dir(target)
        for part in (os.path.join(self.cfg, "routing-dashboard"),
                     os.path.join(self.cfg, "routing-dashboard", "backups"), folder):
            self.assertEqual(0o700, stat.S_IMODE(os.stat(part).st_mode), part)
        for name in (row["backup"], "ledger.json", ".lock"):
            self.assertEqual(0o600, stat.S_IMODE(os.stat(os.path.join(folder, name)).st_mode), name)

    def test_a_wide_store_folder_is_narrowed(self):
        target = self.target("project")
        folder = self.store_dir(target)
        os.makedirs(folder)
        os.chmod(folder, 0o755)
        self.store.save(target, effort_plan("high"))
        self.assertEqual(0o700, stat.S_IMODE(os.stat(folder).st_mode))

    def test_the_ledger_stores_values_masked(self):
        write(self.project_file, b'{"env": {"API_TOKEN": "sk-planted-one"}, "effortLevel": "low"}\n')
        target = self.target("project")

        def plan(raw):
            return es.Plan(raw.replace(b"sk-planted-one", b"sk-planted-two"),
                           ["env", "API_TOKEN"], "sk-planted-one", "sk-planted-two")
        row = self.store.save(target, plan)
        self.assertEqual("hidden", row["old_value"])
        self.assertEqual("hidden", row["new_value"])

        def plan2(raw):
            return es.Plan(raw.replace(b'"low"', b'"sk-planted-x"'), ["effortLevel"], "low",
                           "sk-planted-x")
        row2 = self.store.save(target, plan2)
        self.assertEqual("low", row2["old_value"])
        self.assertEqual("hidden", row2["new_value"])
        self.assertNotIn(b"planted", read(os.path.join(self.store_dir(target), "ledger.json")))

    def test_time_comes_from_fixed_now(self):
        import datetime
        stamp = datetime.datetime(2026, 10, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)
        store = es.Store(self.cfg, fixed_now=stamp)
        row = store.save(self.target("project"), effort_plan("high"))
        self.assertEqual("2026-10-31T12:00:00+00:00", row["time"])
        live = self.store.save(self.target("project"), effort_plan("low"))
        self.assertRegex(live["time"], r"^\d{4}-\d\d-\d\dT.*\+00:00$")

    def test_the_ledger_file_shape(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        doc = json.loads(read(os.path.join(self.store_dir(target), "ledger.json")))
        self.assertEqual({"version": 1, "rows": [row]}, doc)
        self.assertEqual({"id", "time", "kind", "op", "key_path", "layer", "old_value", "new_value",
                          "before_sha256", "after_sha256", "backup", "restored_from",
                          "restored_from_backup"}, set(row))

    def test_backup_numbers_count_up_past_every_name_in_the_folder(self):
        target = self.target("project")
        self.store.save(target, effort_plan("high"))
        folder = self.store_dir(target)
        write(os.path.join(folder, "000007-" + "a" * 16 + ".bak"), b"orphan")
        row = self.store.save(target, effort_plan("low"))
        self.assertTrue(row["backup"].startswith("000008-"), row["backup"])

    def test_no_change_is_refused_and_writes_no_backup(self):
        target = self.target("project")
        with self.assertRaises(es.Refused) as ctx:
            self.store.save(target, lambda raw: es.Plan(raw, ["effortLevel"], "low", "low"))
        self.assertEqual("no_change", ctx.exception.code)
        self.assertEqual([], self.baks(target))
        self.assertEqual(SETTINGS, read(self.project_file))
        self.assertEqual([], self.store.rows(target))

    def test_a_plan_exception_passes_through_with_nothing_written(self):
        target = self.target("project")

        def plan(raw):
            raise KeyError("bad plan")
        with self.assertRaises(KeyError):
            self.store.save(target, plan)
        self.assertEqual([], self.baks(target))
        self.assertEqual(SETTINGS, read(self.project_file))
        self.assertEqual([], self.store.rows(target))

    def test_a_plan_gets_the_bytes_read_under_the_lock(self):
        target = self.target("project")
        seen = []

        def plan(raw):
            seen.append(raw)
            return effort_plan("high")(raw)
        self.store.save(target, plan)
        self.assertEqual([SETTINGS], seen)

    def test_a_refused_target_creates_no_store_folder(self):
        target = self.target("project")
        os.unlink(self.project_file)
        with self.assertRaises(es.Refused) as ctx:
            self.store.save(target, effort_plan("high"))
        self.assertEqual("file_missing", ctx.exception.code)
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "routing-dashboard")))

    def test_save_refuses_a_hard_linked_file_without_touching_it(self):
        target = self.target("project")
        twin = os.path.join(self.root, "twin.json")
        os.link(self.project_file, twin)
        with self.assertRaises(es.Refused) as ctx:
            self.store.save(target, effort_plan("high"))
        self.assertEqual("hard_link", ctx.exception.code)
        self.assertEqual(SETTINGS, read(twin))
        self.assertEqual(SETTINGS, read(self.project_file))

    def test_leftover_temp_files_go_on_the_next_save(self):
        claude = os.path.join(self.proj, ".claude")
        write(os.path.join(claude, ".routing-dashboard-" + "0" * 16 + ".tmp"), b"junk")
        write(os.path.join(claude, ".routing-dashboard-short.tmp"), b"keep")
        write(os.path.join(claude, "notes.tmp"), b"keep")
        self.store.save(self.target("project"), effort_plan("high"))
        self.assertEqual([".routing-dashboard-short.tmp"], self.leftovers())
        self.assertTrue(os.path.exists(os.path.join(claude, "notes.tmp")))

    def test_the_temp_file_is_gone_after_a_save(self):
        self.store.save(self.target("project"), effort_plan("high"))
        self.assertEqual([], self.leftovers())

    def test_fullfsync_falls_back_to_fsync(self):
        target = self.target("project")
        with mock.patch.object(es.fcntl, "fcntl", side_effect=OSError(25, "no")):
            self.store.save(target, effort_plan("high"))
        self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(self.project_file))

    def test_descriptors_do_not_grow_over_thirty_saves(self):
        target = self.target("project")
        self.store.save(target, effort_plan("v0"))
        before = fd_count()
        for n in range(1, 31):
            self.store.save(target, effort_plan("v%d" % n))
            self.store.rows(target)
        self.assertEqual(before, fd_count())

    def test_descriptors_do_not_grow_over_refusals_and_failures(self):
        target = self.target("project")
        self.store.save(target, effort_plan("v0"))
        before = fd_count()
        for _ in range(5):
            with self.assertRaises(es.Refused):
                self.store.save(target, lambda raw: es.Plan(raw, [], None, None))

            def boom(raw):
                raise ValueError("x")
            with self.assertRaises(ValueError):
                self.store.save(target, boom)
            self.at("after_temp", lambda: (_ for _ in ()).throw(OSError(5, "io")))
            with self.assertRaises(es.WriteFailed):
                self.store.save(target, effort_plan("v9"))
            self.store.seam = None
        self.assertEqual(before, fd_count())

    def test_a_missing_config_folder_is_its_own_error_and_creates_nothing(self):
        target = self.target("project")
        gone = os.path.join(self.root, "gone")
        store = es.Store(gone)
        with self.assertRaises(es.ConfigDirMissing) as ctx:
            store.save(target, effort_plan("high"))
        self.assertEqual(gone, ctx.exception.path)
        self.assertIsInstance(ctx.exception, es.WriteFailed)
        self.assertFalse(os.path.exists(gone))
        self.assertEqual(SETTINGS, read(self.project_file))

    def test_concurrent_saves_run_one_after_another(self):
        target = self.target("project")
        errors = []

        def plan(raw):
            return es.Plan(raw + b" ", ["x"], None, None)

        def run():
            try:
                self.store.save(target, plan)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        workers = [threading.Thread(target=run) for _ in range(6)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(30)
        self.assertEqual([], errors)
        self.assertEqual(len(SETTINGS) + 6, len(read(self.project_file)))
        self.assertEqual(6, len(self.store.rows(target)))

    def test_two_stores_share_the_flock(self):
        target = self.target("project")
        self.store.save(target, effort_plan("high"))
        other = es.Store(self.cfg)
        results = []

        def inner():
            try:
                other.save(target, effort_plan("low"))
                results.append("ok")
            except es.StoreError as exc:
                results.append(exc)

        def hold():
            worker = threading.Thread(target=inner)
            worker.start()
            worker.join(30)

        self.at("after_read", hold)
        with mock.patch.object(es, "LOCK_WAIT", 0.3):
            self.store.save(target, effort_plan("v1"))
        self.assertEqual(1, len(results))
        self.assertIsInstance(results[0], es.WriteFailed)
        self.assertEqual(2, len(self.store.rows(target)))
        self.assertEqual(SETTINGS.replace(b'"low"', b'"v1"'), read(self.project_file))

    def test_a_source_lint_keeps_writes_on_descriptors(self):
        with open(es.__file__.replace(".pyc", ".py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertIsNone(re.search(r"(?<![\w.])open\(", source))
        for banned in (r"\bshutil\b", r"\bpathlib\b", r"\bio\.open\b", r"\bsubprocess\b",
                       r"\bos\.(replace|remove|makedirs|truncate)\(",
                       r"\.writelines?\("):
            self.assertIsNone(re.search(banned, source), banned)
        for call in re.findall(r"\bos\.(?:unlink|rename|mkdir|rmdir)\([^)]*\)", source):
            self.assertIn("dir_fd", call)


class HostileTests(Base):
    def test_leaf_swapped_for_a_symlink_before_recheck(self):
        target = self.target("project")
        outside = write(os.path.join(self.root, "outside.json"), b'{"outside": true}\n')

        def swap():
            os.unlink(self.project_file)
            os.symlink(outside, self.project_file)
        self.at("before_recheck", swap)
        with self.assertRaises(es.Refused) as ctx:
            self.store.save(target, effort_plan("high"))
        self.assertEqual("symlink", ctx.exception.code)
        self.assertEqual(b'{"outside": true}\n', read(outside))
        self.assertTrue(os.path.islink(self.project_file))
        self.assertEqual([], self.leftovers())
        self.assertEqual([], self.baks(target))
        self.assertEqual([], self.store.rows(target))

    def test_leaf_swapped_for_a_symlink_before_rename_is_replaced(self):
        target = self.target("project")
        outside = write(os.path.join(self.root, "outside.json"), b'{"outside": true}\n')

        def swap():
            os.unlink(self.project_file)
            os.symlink(outside, self.project_file)
        self.at("before_rename", swap)
        self.store.save(target, effort_plan("high"))
        self.assertFalse(os.path.islink(self.project_file))
        self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(self.project_file))
        self.assertEqual(b'{"outside": true}\n', read(outside))

    def test_claude_folder_swapped_for_a_link_before_recheck(self):
        target = self.target("project")
        claude = os.path.join(self.proj, ".claude")
        hold = os.path.join(self.root, "held")
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        write(os.path.join(elsewhere, "settings.json"), b'{"outside": true}\n')

        def swap():
            os.rename(claude, hold)
            os.symlink(elsewhere, claude)
        self.at("before_recheck", swap)
        with self.assertRaises(es.Refused) as ctx:
            self.store.save(target, effort_plan("high"))
        self.assertEqual("symlink", ctx.exception.code)
        self.assertEqual(b'{"outside": true}\n', read(os.path.join(elsewhere, "settings.json")))
        self.assertEqual(sorted(os.listdir(elsewhere)), ["settings.json"])
        self.assertEqual(SETTINGS, read(os.path.join(hold, "settings.json")))
        self.assertEqual([], sorted(n for n in os.listdir(hold) if n.startswith(".routing")))

    def test_claude_folder_replaced_by_another_folder_is_stale(self):
        target = self.target("project")
        claude = os.path.join(self.proj, ".claude")
        hold = os.path.join(self.root, "held")

        def swap():
            os.rename(claude, hold)
            os.makedirs(claude)
            write(os.path.join(claude, "settings.json"), SETTINGS)
        self.at("before_recheck", swap)
        with self.assertRaises(es.Stale) as ctx:
            self.store.save(target, effort_plan("high"))
        self.assertEqual("file", ctx.exception.changed)
        self.assertEqual(SETTINGS, read(os.path.join(claude, "settings.json")))
        self.assertEqual(SETTINGS, read(os.path.join(hold, "settings.json")))
        self.assertEqual([], sorted(n for n in os.listdir(hold) if n.startswith(".routing")))

    def test_in_place_race_is_stale_and_the_writers_bytes_survive(self):
        target = self.target("project")
        theirs = b'{"effortLevel": "max", "extra": 1}\n'

        def rewrite():
            before = os.stat(self.project_file).st_ino
            with open(self.project_file, "r+b") as fh:
                fh.truncate(0)
                fh.write(theirs)
            self.assertEqual(before, os.stat(self.project_file).st_ino)
        self.at("before_recheck", rewrite)
        with self.assertRaises(es.Stale) as ctx:
            self.store.save(target, effort_plan("high"))
        self.assertEqual("file", ctx.exception.changed)
        self.assertEqual(theirs, read(self.project_file))
        self.assertEqual([], self.leftovers())
        self.assertEqual([], self.baks(target))
        self.assertEqual([], self.store.rows(target))
        self.assertEqual("[]", json.dumps(json.loads(
            read(os.path.join(self.store_dir(target), "ledger.json")))["rows"]))

    def test_a_rename_race_before_recheck_is_stale_too(self):
        target = self.target("project")
        theirs = b'{"effortLevel": "max"}\n'

        def swap():
            write(self.project_file + ".new", theirs)
            os.rename(self.project_file + ".new", self.project_file)
        self.at("before_recheck", swap)
        with self.assertRaises(es.Stale):
            self.store.save(target, effort_plan("high"))
        self.assertEqual(theirs, read(self.project_file))

    def test_an_io_failure_at_each_step_leaves_the_file_and_cleans_up(self):
        for seam_name in ("before_backup", "after_backup", "after_ledger", "after_temp",
                          "before_recheck", "before_rename"):
            target = self.target("project")
            write(self.project_file, SETTINGS)
            self.setUp_clean_store(target)

            def fail():
                raise OSError(5, "simulated")
            self.at(seam_name, fail)
            with self.assertRaises(es.WriteFailed, msg=seam_name):
                self.store.save(target, effort_plan("high"))
            self.assertEqual(SETTINGS, read(self.project_file), seam_name)
            self.assertEqual([], self.leftovers(), seam_name)
            self.assertEqual([], self.baks(target), seam_name)
            self.assertEqual([], self.store.rows(target), seam_name)
            self.store.seam = None

    def setUp_clean_store(self, target):
        folder = os.path.join(self.cfg, "routing-dashboard")
        if os.path.isdir(folder):
            helpers.rmtree_force(folder)

    def test_a_short_backup_read_back_fails_the_save(self):
        target = self.target("project")
        real = es._read_file

        def short(name, dir_fd, cap):
            data = real(name, dir_fd, cap)
            return data[:-1] if name.endswith(".bak") else data
        with mock.patch.object(es, "_read_file", side_effect=short):
            with self.assertRaises(es.WriteFailed):
                self.store.save(target, effort_plan("high"))
        self.assertEqual(SETTINGS, read(self.project_file))
        self.assertEqual([], self.baks(target))

    def test_store_folder_as_a_link_fails_the_save(self):
        target = self.target("project")
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        os.symlink(elsewhere, os.path.join(self.cfg, "routing-dashboard"))
        with self.assertRaises(es.WriteFailed):
            self.store.save(target, effort_plan("high"))
        self.assertEqual([], os.listdir(elsewhere))
        self.assertEqual(SETTINGS, read(self.project_file))

    def test_target_folder_as_a_plain_file_fails_the_save(self):
        target = self.target("project")
        write(os.path.join(self.cfg, "routing-dashboard", "backups", self.store.target_id(target)),
              b"x")
        with self.assertRaises(es.WriteFailed):
            self.store.save(target, effort_plan("high"))
        self.assertEqual(SETTINGS, read(self.project_file))

    def test_ledger_as_a_link_fails_the_save(self):
        target = self.target("project")
        self.store.save(target, effort_plan("high"))
        ledger = os.path.join(self.store_dir(target), "ledger.json")
        outside = write(os.path.join(self.root, "outside.json"), b"{}")
        os.unlink(ledger)
        os.symlink(outside, ledger)
        with self.assertRaises(es.WriteFailed):
            self.store.save(target, effort_plan("low"))
        self.assertEqual(b"{}", read(outside))
        self.assertEqual([], self.store.rows(target))

    def test_a_damaged_ledger_reads_as_no_rows_and_refuses_a_save(self):
        target = self.target("project")
        self.store.save(target, effort_plan("high"))
        ledger = os.path.join(self.store_dir(target), "ledger.json")
        for junk in (b"not json", b"[]", b'{"version": 2, "rows": []}', b'{"version": 1, "rows": 5}',
                     b'{"version": 1, "rows": [1]}', b"\xff\xfe"):
            write(ledger, junk)
            self.assertEqual([], self.store.rows(target), junk)
            before = read(self.project_file)
            self.assertTrue(self.store.ledger_damaged(target), junk)
            with self.assertRaises(es.LedgerDamaged) as caught:
                self.store.save(target, effort_plan("low"))
            self.assertEqual(ledger, caught.exception.path)
            self.assertEqual(before, read(self.project_file))
            self.assertEqual(junk, read(ledger))
        self.assertEqual(1, len(self.baks(target)))

    def test_a_sound_or_absent_ledger_is_not_damaged(self):
        target = self.target("project")
        self.assertFalse(self.store.ledger_damaged(target))
        self.store.save(target, effort_plan("high"))
        self.assertFalse(self.store.ledger_damaged(target))

    def test_bad_backup_names_in_the_ledger_are_treated_as_absent(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        ledger = os.path.join(self.store_dir(target), "ledger.json")
        for bad in ("../../escape.bak", "000001-xyz.bak", None, 5, "000001-" + "a" * 16 + ".BAK"):
            doc = {"version": 1, "rows": [dict(row, backup=bad)]}
            write(ledger, json.dumps(doc).encode())
            current = self.store.rows(target)[0]
            self.assertEqual("backup_pruned", self.store.undo_state(target, current), bad)
            self.assertIsNone(self.store.backup_path(target, bad))
            with self.assertRaises(es.NotUndoable) as ctx:
                self.store.restore(target, row["id"])
            self.assertEqual("backup_pruned", ctx.exception.reason)


class CrashTests(Base):
    def crash_then_restart(self, seam_name, target):
        self.crash_at(seam_name)
        with self.assertRaises(Crash):
            self.store.save(target, effort_plan("high"))
        self.store = es.Store(self.cfg)

    def test_crash_before_anything_is_written(self):
        target = self.target("project")
        self.crash_then_restart("before_backup", target)
        self.assertEqual(SETTINGS, read(self.project_file))
        self.assertEqual([], self.baks(target))
        self.assertEqual([], self.store.rows(target))

    def test_crash_after_the_backup_leaves_an_orphan_the_next_save_removes(self):
        target = self.target("project")
        first = self.store.save(target, effort_plan("first"))
        first_raw = read(self.project_file)
        self.crash_then_restart("after_backup", target)
        self.assertEqual(first_raw, read(self.project_file))
        orphan = [name for name in self.baks(target) if name != first["backup"]]
        self.assertEqual(1, len(orphan))
        self.assertEqual([first], self.store.rows(target))
        row = self.store.save(target, effort_plan("low2"))
        self.assertEqual(sorted([first["backup"], row["backup"]]), self.baks(target))
        self.assertNotIn(orphan[0], self.baks(target))
        self.assertEqual([first, row], self.store.rows(target))

    def test_a_crash_with_a_never_applied_row_is_not_the_newest_row(self):
        for seam_name in ("after_ledger", "after_temp", "before_rename"):
            self.tearDown_store()
            target = self.target("project")
            applied = self.store.save(target, effort_plan("mid"))
            applied_raw = read(self.project_file)
            self.crash_then_restart(seam_name, target)
            self.assertEqual(applied_raw, read(self.project_file), seam_name)
            ledger = json.loads(read(os.path.join(self.store_dir(target), "ledger.json")))
            self.assertEqual(2, len(ledger["rows"]), seam_name)
            # the row on disk is the orphan, and a read hides it
            self.assertEqual([applied], self.store.rows(target), seam_name)
            self.assertEqual(applied, self.store.find(target, applied["id"]))
            self.assertIsNone(self.store.find(target, ledger["rows"][1]["id"]))
            self.assertIsNone(self.store.undo_state(target, applied), seam_name)
            self.assertEqual(2, len(self.baks(target)), seam_name)
            # the next save removes the orphan row and its backup, and the leftover temp file
            row = self.store.save(target, effort_plan("end"))
            self.assertEqual([applied, row], self.store.rows(target), seam_name)
            self.assertEqual(sorted([applied["backup"], row["backup"]]), self.baks(target), seam_name)
            self.assertEqual([], self.leftovers(), seam_name)

    def tearDown_store(self):
        write(self.project_file, SETTINGS)
        folder = os.path.join(self.cfg, "routing-dashboard")
        if os.path.isdir(folder):
            helpers.rmtree_force(folder)
        for name in self.leftovers():
            os.unlink(os.path.join(self.proj, ".claude", name))
        self.store = es.Store(self.cfg)

    def test_an_applied_edit_survives_a_crash_after_the_rename_and_is_undoable(self):
        for seam_name in ("after_rename", "dir_fsync", "reread"):
            self.tearDown_store()
            target = self.target("project")
            self.crash_then_restart(seam_name, target)
            self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(self.project_file), seam_name)
            rows = self.store.rows(target)
            self.assertEqual(1, len(rows), seam_name)
            self.assertIsNone(self.store.undo_state(target, rows[0]), seam_name)
            result = self.store.restore(target, rows[0]["id"])
            self.assertTrue(result.matches_backup)
            self.assertEqual(SETTINGS, read(self.project_file), seam_name)

    def test_the_file_is_whole_at_every_crash_point(self):
        for seam_name in ("before_backup", "after_backup", "after_ledger", "after_temp",
                          "before_recheck", "before_rename", "after_rename", "dir_fsync", "reread"):
            self.tearDown_store()
            target = self.target("project")
            self.crash_then_restart(seam_name, target)
            raw = read(self.project_file)
            self.assertIn(raw, (SETTINGS, SETTINGS.replace(b'"low"', b'"high"')), seam_name)
            json.loads(raw.decode("utf-8"))


class RestoreTests(Base):
    def edited(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        return target, row

    def test_restore_puts_the_bytes_back_with_its_own_backup_and_row(self):
        target, row = self.edited()
        edited = read(self.project_file)
        result = self.store.restore(target, row["id"])
        self.assertEqual(SETTINGS, read(self.project_file))
        undo = result.row
        self.assertEqual("undo", undo["kind"])
        self.assertEqual(row["id"], undo["restored_from"])
        self.assertEqual(row["backup"], undo["restored_from_backup"])
        self.assertEqual(["effortLevel"], undo["key_path"])
        self.assertEqual("project", undo["layer"])
        self.assertEqual("high", undo["old_value"])
        self.assertEqual("low", undo["new_value"])
        self.assertEqual(sha(edited), undo["before_sha256"])
        self.assertEqual(sha(SETTINGS), undo["after_sha256"])
        self.assertNotEqual(row["backup"], undo["backup"])
        self.assertEqual(edited, read(os.path.join(self.store_dir(target), undo["backup"])))
        self.assertTrue(result.matches_backup)
        self.assertEqual(os.path.join(self.store_dir(target), row["backup"]), result.restored_from_path)
        self.assertEqual(os.path.join(self.store_dir(target), undo["backup"]), result.backup_path)
        self.assertEqual(SETTINGS, read(result.restored_from_path))
        self.assertEqual([row, undo], self.store.rows(target))

    def test_restore_masks_the_swapped_values(self):
        write(self.project_file, b'{"effortLevel": "sk-planted-a"}\n')
        target = self.target("project")

        def plan(raw):
            return es.Plan(raw.replace(b"sk-planted-a", b"low"), ["effortLevel"], "sk-planted-a", "low")
        row = self.store.save(target, plan)
        self.assertEqual("hidden", row["old_value"])
        result = self.store.restore(target, row["id"])
        self.assertEqual("low", result.row["old_value"])
        self.assertEqual("hidden", result.row["new_value"])

    def test_unknown_edit(self):
        target, row = self.edited()
        for edit_id in ("nope", "", None):
            with self.assertRaises(es.UnknownEdit):
                self.store.restore(target, edit_id)
        self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(self.project_file))

    def test_the_check_hook_runs_under_the_lock_and_can_veto(self):
        target, row = self.edited()
        seen = []

        def check(rows, found):
            seen.append((list(rows), found))
            raise es.NotUndoable("not_newest")
        with self.assertRaises(es.NotUndoable) as ctx:
            self.store.restore(target, row["id"], check=check)
        self.assertEqual("not_newest", ctx.exception.reason)
        self.assertEqual([([row], row)], seen)
        self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(self.project_file))
        self.assertEqual([row], self.store.rows(target))

    def test_changed_since_save(self):
        target, row = self.edited()
        write(self.project_file, b'{"effortLevel": "max"}\n')
        self.assertEqual("changed_since_save", self.store.undo_state(target, row))
        with self.assertRaises(es.ChangedSinceSave) as ctx:
            self.store.restore(target, row["id"])
        self.assertEqual(os.path.join(self.store_dir(target), row["backup"]), ctx.exception.backup_path)
        self.assertEqual(b'{"effortLevel": "max"}\n', read(self.project_file))
        self.assertEqual([row], self.store.rows(target))

    def test_an_unreadable_file_is_changed_since_save(self):
        target, row = self.edited()
        os.unlink(self.project_file)
        self.assertEqual("changed_since_save", self.store.undo_state(target, row))
        self.assertEqual([row], self.store.rows(target))

    def test_truncated_backup_is_damaged_and_nothing_is_written(self):
        target, row = self.edited()
        bak = os.path.join(self.store_dir(target), row["backup"])
        with open(bak, "r+b") as fh:
            fh.truncate(5)
        self.assertEqual("backup_damaged", self.store.undo_state(target, row))
        edited = read(self.project_file)
        with self.assertRaises(es.BackupDamaged) as ctx:
            self.store.restore(target, row["id"])
        self.assertEqual(bak, ctx.exception.backup_path)
        self.assertEqual(edited, read(self.project_file))
        self.assertEqual([row], self.store.rows(target))
        self.assertEqual([row["backup"]], self.baks(target))

    def test_an_empty_or_swapped_backup_is_damaged(self):
        target, row = self.edited()
        bak = os.path.join(self.store_dir(target), row["backup"])
        for data in (b"", b'{"effortLevel": "other"}\n'):
            write(bak, data)
            self.assertEqual("backup_damaged", self.store.undo_state(target, row))
            with self.assertRaises(es.BackupDamaged):
                self.store.restore(target, row["id"])

    def test_a_backup_replaced_by_a_link_is_damaged(self):
        target, row = self.edited()
        bak = os.path.join(self.store_dir(target), row["backup"])
        outside = write(os.path.join(self.root, "outside.bak"), SETTINGS)
        os.unlink(bak)
        os.symlink(outside, bak)
        self.assertEqual("backup_damaged", self.store.undo_state(target, row))
        with self.assertRaises(es.BackupDamaged):
            self.store.restore(target, row["id"])

    def test_a_missing_backup_is_pruned(self):
        target, row = self.edited()
        os.unlink(os.path.join(self.store_dir(target), row["backup"]))
        self.assertEqual("backup_pruned", self.store.undo_state(target, row))
        with self.assertRaises(es.NotUndoable) as ctx:
            self.store.restore(target, row["id"])
        self.assertEqual("backup_pruned", ctx.exception.reason)

    def test_undo_state_is_none_for_a_healthy_row(self):
        target, row = self.edited()
        self.assertIsNone(self.store.undo_state(target, row))

    def test_after_an_undo_the_older_row_matches_again_and_the_store_has_the_general_mechanism(self):
        target, row = self.edited()
        self.store.restore(target, row["id"])
        # the file is back at the pre-edit bytes, so the edit's after hash no longer matches
        self.assertEqual("changed_since_save", self.store.undo_state(target, row))
        second = self.store.save(target, effort_plan("mid"))
        third = self.store.save(target, effort_plan("end"))
        self.assertIsNone(self.store.undo_state(target, third))
        self.assertEqual("changed_since_save", self.store.undo_state(target, second))
        result = self.store.restore(target, third["id"])
        self.assertEqual(read(self.project_file), SETTINGS.replace(b'"low"', b'"mid"'))
        self.assertEqual("undo", result.row["kind"])


class RacedTests(Base):
    def test_a_write_between_rename_and_reread_is_raced_for_a_save(self):
        target = self.target("project")
        theirs = b'{"effortLevel": "theirs"}\n'
        self.at("reread", lambda: write(self.project_file, theirs))
        with self.assertRaises(es.Raced) as ctx:
            self.store.save(target, effort_plan("high"))
        exc = ctx.exception
        self.assertIsNone(exc.matches_backup)
        self.assertIsNone(exc.restored_from_path)
        self.assertEqual(theirs, read(self.project_file))
        self.assertEqual(os.path.join(self.store_dir(target), exc.row["backup"]), exc.backup_path)
        self.assertEqual(SETTINGS, read(exc.backup_path))
        # the row and its backup stay, and the row is not undoable
        self.store.seam = None
        self.assertEqual([exc.row], self.store.rows(target))
        self.assertEqual([exc.row["backup"]], self.baks(target))
        self.assertEqual("changed_since_save", self.store.undo_state(target, exc.row))

    def test_a_write_between_rename_and_reread_is_raced_for_an_undo(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        theirs = b'{"effortLevel": "theirs"}\n'
        self.at("reread", lambda: write(self.project_file, theirs))
        with self.assertRaises(es.Raced) as ctx:
            self.store.restore(target, row["id"])
        exc = ctx.exception
        self.assertIs(False, exc.matches_backup)
        self.assertEqual(os.path.join(self.store_dir(target), row["backup"]), exc.restored_from_path)
        self.assertEqual(theirs, read(self.project_file))
        self.assertEqual("undo", exc.row["kind"])
        self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(exc.backup_path))

    def test_a_backup_that_changes_before_the_undo_reread_is_raced(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        bak = os.path.join(self.store_dir(target), row["backup"])
        self.at("reread", lambda: write(bak, b"changed"))
        with self.assertRaises(es.Raced) as ctx:
            self.store.restore(target, row["id"])
        self.assertIs(False, ctx.exception.matches_backup)
        self.assertEqual(SETTINGS, read(self.project_file))

    def test_a_backup_that_goes_missing_before_the_undo_reread_is_raced(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        bak = os.path.join(self.store_dir(target), row["backup"])
        self.at("reread", lambda: os.unlink(bak))
        with self.assertRaises(es.Raced) as ctx:
            self.store.restore(target, row["id"])
        self.assertIs(False, ctx.exception.matches_backup)

    def test_a_raced_save_skips_the_prune(self):
        target = self.target("project")
        for n in range(es.RETENTION):
            self.store.save(target, effort_plan("v%d" % n))
        self.at("reread", lambda: write(self.project_file, b'{"effortLevel": "theirs"}\n'))
        with self.assertRaises(es.Raced):
            self.store.save(target, effort_plan("late"))
        ledger = json.loads(read(os.path.join(self.store_dir(target), "ledger.json")))
        self.assertEqual(es.RETENTION + 1, len(ledger["rows"]))
        self.assertEqual(es.RETENTION + 1, len(self.baks(target)))


class UnverifiedTests(Base):
    def test_a_failed_reread(self):
        target = self.target("project")

        def fail():
            raise OSError(5, "simulated")
        self.at("reread", fail)
        with self.assertRaises(es.Unverified) as ctx:
            self.store.save(target, effort_plan("high"))
        exc = ctx.exception
        self.assertEqual("reread", exc.stage)
        self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(self.project_file))
        self.assertEqual(os.path.join(self.store_dir(target), exc.row["backup"]), exc.backup_path)
        self.store.seam = None
        self.assertEqual([exc.row], self.store.rows(target))
        self.assertIsNone(self.store.undo_state(target, exc.row))

    def test_a_reread_that_is_refused(self):
        target = self.target("project")
        outside = write(os.path.join(self.root, "outside.json"), SETTINGS)

        def swap():
            os.unlink(self.project_file)
            os.symlink(outside, self.project_file)
        self.at("reread", swap)
        with self.assertRaises(es.Unverified) as ctx:
            self.store.save(target, effort_plan("high"))
        self.assertEqual("reread", ctx.exception.stage)

    def test_a_failed_directory_fsync(self):
        target = self.target("project")

        def fail():
            raise OSError(5, "simulated")
        self.at("dir_fsync", fail)
        with self.assertRaises(es.Unverified) as ctx:
            self.store.save(target, effort_plan("high"))
        exc = ctx.exception
        self.assertEqual("fsync", exc.stage)
        self.assertEqual(SETTINGS.replace(b'"low"', b'"high"'), read(self.project_file))
        self.assertEqual(os.path.join(self.store_dir(target), exc.row["backup"]), exc.backup_path)
        self.store.seam = None
        self.assertEqual([exc.row], self.store.rows(target))

    def test_raced_wins_over_a_failed_directory_fsync(self):
        target = self.target("project")

        def fail():
            raise OSError(5, "simulated")

        def seam(name):
            if name == "dir_fsync":
                fail()
            if name == "reread":
                write(self.project_file, b'{"effortLevel": "theirs"}\n')
        self.store.seam = seam
        with self.assertRaises(es.Raced):
            self.store.save(target, effort_plan("high"))


class RetentionTests(Base):
    def test_the_twenty_first_write_prunes_the_oldest_and_nothing_else(self):
        target = self.target("project")
        folder = self.store_dir(target)
        rows = []
        for n in range(es.RETENTION):
            rows.append(self.store.save(target, effort_plan("v%d" % n)))
        # files the prune must leave alone
        keepers = {".lock", "ledger.json"}
        for name, data in (("notes.txt", b"mine"), ("000001-short.bak", b"no match"),
                           (".ledger-0123456789abcdef.tmp", b"x"), ("sub", None)):
            if data is None:
                os.mkdir(os.path.join(folder, name))
            else:
                write(os.path.join(folder, name), data)
            keepers.add(name)
        other_folder = os.path.join(self.cfg, "routing-dashboard", "backups", "f" * 16)
        write(os.path.join(other_folder, "000001-" + "a" * 16 + ".bak"), b"another target")
        self.assertEqual(es.RETENTION, len(self.store.rows(target)))
        self.assertEqual([r["backup"] for r in rows], self.baks(target)[:es.RETENTION])
        newest = self.store.save(target, effort_plan("v20"))
        kept = rows[1:] + [newest]
        self.assertEqual(kept, self.store.rows(target))
        self.assertEqual(sorted(r["backup"] for r in kept), [n for n in self.baks(target)
                                                             if n != "000001-short.bak"])
        self.assertNotIn(rows[0]["backup"], os.listdir(folder))
        self.assertEqual(keepers, set(os.listdir(folder)) - {r["backup"] for r in kept})
        self.assertTrue(os.path.exists(os.path.join(other_folder, "000001-" + "a" * 16 + ".bak")))

    def test_the_newest_is_never_pruned_and_numbers_keep_counting(self):
        target = self.target("project")
        last = None
        for n in range(es.RETENTION + 5):
            last = self.store.save(target, effort_plan("v%d" % n))
        rows = self.store.rows(target)
        self.assertEqual(es.RETENTION, len(rows))
        self.assertEqual(last, rows[-1])
        self.assertTrue(last["backup"].startswith("%06d-" % (es.RETENTION + 5)))
        self.assertEqual(es.RETENTION, len(self.baks(target)))

    def test_a_backup_no_row_names_goes_on_the_next_prune(self):
        target = self.target("project")
        self.store.save(target, effort_plan("v1"))
        orphan = "000042-" + "b" * 16 + ".bak"
        write(os.path.join(self.store_dir(target), orphan), b"orphan")
        row = self.store.save(target, effort_plan("v2"))
        self.assertNotIn(orphan, self.baks(target))
        self.assertEqual(2, len(self.baks(target)))
        self.assertTrue(row["backup"].startswith("000043-"))

    def test_backups_from_before_a_moved_ledger_stay_through_every_save(self):
        target = self.target("project")
        folder = self.store_dir(target)
        for n in range(5):
            self.store.save(target, effort_plan("v%d" % n))
        old = self.baks(target)
        self.assertEqual(5, len(old))
        for name in old:
            hour_ago = time.time() - 3600
            os.utime(os.path.join(folder, name), (hour_ago, hour_ago))
        os.rename(os.path.join(folder, "ledger.json"), os.path.join(folder, "ledger.json.aside"))
        for n in range(3):
            self.store.save(target, effort_plan("w%d" % n))
            self.assertEqual(old, [name for name in self.baks(target) if name in old])
        self.assertEqual(8, len(self.baks(target)))
        self.assertEqual(3, len(self.store.rows(target)))

    def test_a_prune_failure_never_fails_the_save(self):
        target = self.target("project")
        for n in range(es.RETENTION):
            self.store.save(target, effort_plan("v%d" % n))
        real = os.listdir
        calls = []

        def flaky(path):
            calls.append(path)
            if len(calls) == 3:  # next number, temp files, then the prune
                raise OSError(5, "simulated")
            return real(path)
        with mock.patch.object(os, "listdir", side_effect=flaky):
            row = self.store.save(target, effort_plan("late"))
        self.assertEqual(3, len(calls))
        self.assertEqual(row, self.store.rows(target)[-1])
        self.assertEqual(SETTINGS.replace(b'"low"', b'"late"'), read(self.project_file))

    def test_a_ledger_rewrite_failure_during_prune_keeps_every_backup(self):
        target = self.target("project")
        for n in range(es.RETENTION):
            self.store.save(target, effort_plan("v%d" % n))
        real = es.Store._write_ledger
        calls = []

        def flaky(store, store_fd, rows):
            calls.append(len(rows))
            if len(calls) == 2:
                raise OSError(5, "simulated")
            return real(store, store_fd, rows)
        with mock.patch.object(es.Store, "_write_ledger", autospec=True, side_effect=flaky):
            self.store.save(target, effort_plan("late"))
        self.assertEqual(es.RETENTION + 1, len(self.baks(target)))
        self.assertEqual(es.RETENTION + 1, len(json.loads(
            read(os.path.join(self.store_dir(target), "ledger.json")))["rows"]))


class ReadOnlyTests(Base):
    def test_reads_create_nothing_on_a_fresh_config_folder(self):
        target = self.target("project")
        row = {"id": "x" * 16, "backup": "000001-" + "a" * 16 + ".bak", "before_sha256": "0",
               "after_sha256": "1"}
        before = self.tree()
        self.assertEqual([], self.store.rows(target))
        self.assertIsNone(self.store.find(target, "x"))
        self.assertEqual("changed_since_save", self.store.undo_state(target, row))
        row["after_sha256"] = sha(SETTINGS)
        self.assertEqual("backup_pruned", self.store.undo_state(target, row))
        self.assertIsNotNone(self.store.backup_path(target, row["backup"]))
        self.assertEqual(before, self.tree())
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "routing-dashboard")))

    def test_reads_create_nothing_when_the_target_is_missing(self):
        target = self.target("project")
        os.unlink(self.project_file)
        before = self.tree()
        self.assertEqual([], self.store.rows(target))
        self.assertEqual(before, self.tree())

    def test_reads_do_not_write_a_trailing_row_away(self):
        target = self.target("project")
        self.crash_at("after_ledger")
        with self.assertRaises(Crash):
            self.store.save(target, effort_plan("high"))
        self.store = es.Store(self.cfg)
        ledger = os.path.join(self.store_dir(target), "ledger.json")
        before = read(ledger)
        self.assertEqual([], self.store.rows(target))
        self.assertIsNone(self.store.find(target, json.loads(before)["rows"][0]["id"]))
        self.assertEqual(before, read(ledger))
        self.assertEqual(1, len(self.baks(target)))

    def test_reads_with_a_file_that_cannot_be_read_keep_every_row(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        os.unlink(self.project_file)
        self.assertEqual([row], self.store.rows(target))

    def test_a_wide_folder_is_not_narrowed_by_a_read(self):
        target = self.target("project")
        self.store.save(target, effort_plan("high"))
        folder = self.store_dir(target)
        os.chmod(folder, 0o755)
        self.store.rows(target)
        self.assertEqual(0o755, stat.S_IMODE(os.stat(folder).st_mode))

    def test_backup_path_is_the_full_path(self):
        target = self.target("project")
        name = "000003-" + "c" * 16 + ".bak"
        self.assertEqual(os.path.join(self.store_dir(target), name),
                         self.store.backup_path(target, name))


NEW = b'{\n  "effortLevel": "high"\n}\n'
HEX16 = "0123456789abcdef"


def create_plan(raw):
    """A plan_fn for a file that must not be there yet."""
    if raw is not None:
        raise AssertionError("the file should be absent")
    return es.Plan(NEW, ["effortLevel"], None, "high", "create")


def tree_hash(folder):
    """Names, modes and bytes of everything under folder."""
    found = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        rel = os.path.relpath(dirpath, folder)
        found.append((rel, stat.S_IMODE(os.stat(dirpath).st_mode)))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            found.append((os.path.join(rel, name), stat.S_IMODE(os.stat(path).st_mode), read(path)))
    return found


def fail():
    raise es.WriteFailed("simulated")


class CreateBase(Base):
    def setUp(self):
        super().setUp()
        self.claude = os.path.join(self.proj, ".claude")

    def bare(self):
        """No .claude folder at all."""
        helpers.rmtree_force(self.claude)

    def no_file(self):
        """A .claude folder that has no settings.json."""
        os.unlink(self.project_file)

    def create(self, target=None):
        return self.store.save(target or self.target("project"), create_plan, allow_absent=True)

    def made(self):
        """Create the project file in a project with no .claude. Returns (target, row)."""
        self.bare()
        target = self.target("project")
        return target, self.create(target)

    def markers(self, target=None):
        folder = self.store_dir(target)
        if not os.path.isdir(folder):
            return []
        return sorted(n for n in os.listdir(folder) if n.endswith(".absent"))

    def ledger_rows(self, target=None):
        return json.loads(read(os.path.join(self.store_dir(target), "ledger.json")))["rows"]

    def rewrite_ledger(self, target, fn):
        path = os.path.join(self.store_dir(target), "ledger.json")
        doc = json.loads(read(path))
        fn(doc["rows"])
        write(path, json.dumps(doc).encode())

    def crash_create(self, seam_name):
        self.crash_at(seam_name)
        with self.assertRaises(Crash):
            self.create()
        self.store = es.Store(self.cfg)


class ReadOrNoneTests(CreateBase):
    def test_reads_the_bytes_or_none(self):
        target = self.target("project")
        self.assertEqual(SETTINGS, es.read_or_none(target))
        self.no_file()
        self.assertIsNone(es.read_or_none(target))
        self.assertEqual(es.ABSENT, es._file_hash(target))
        helpers.rmtree_force(self.claude)
        self.assertIsNone(es.read_or_none(target))
        self.assertEqual(es.ABSENT, es._file_hash(target))

    def test_read_target_stays_strict(self):
        target = self.target("project")
        self.bare()
        with self.assertRaises(es.Refused) as ctx:
            es.read_target(target)
        self.assertEqual("file_missing", ctx.exception.code)

    def test_a_missing_base_is_refused_and_hashes_to_none(self):
        target = self.target("project")
        helpers.rmtree_force(self.proj)
        with self.assertRaises(es.Refused) as ctx:
            es.read_or_none(target)
        self.assertEqual("file_missing", ctx.exception.code)
        self.assertIsNone(es._file_hash(target))

    def test_a_dangling_link_or_a_plain_file_is_still_refused(self):
        target = self.target("project")
        nowhere = os.path.join(self.root, "nowhere")
        self.bare()
        os.symlink(nowhere, self.claude)
        with self.assertRaises(es.Refused) as ctx:
            es.read_or_none(target)
        self.assertEqual("symlink", ctx.exception.code)
        self.assertIsNone(es._file_hash(target))
        os.unlink(self.claude)
        write(self.claude, b"x")
        with self.assertRaises(es.Refused) as ctx:
            es.read_or_none(target)
        self.assertEqual("not_regular", ctx.exception.code)
        os.unlink(self.claude)
        os.makedirs(self.claude)
        os.symlink(nowhere, self.project_file)
        with self.assertRaises(es.Refused) as ctx:
            es.read_or_none(target)
        self.assertEqual("symlink", ctx.exception.code)

    def test_every_absent_walk_closes_its_descriptors(self):
        target = self.target("project")
        before = fd_count()
        for _ in range(10):
            es.read_or_none(target)
            os.unlink(self.project_file)
            es.read_or_none(target)
            write(self.project_file, SETTINGS)
        self.assertEqual(before, fd_count())


class CreateTests(CreateBase):
    def check_created(self, target, row, mode_dir=None):
        self.assertEqual(NEW, read(target.path))
        self.assertEqual(0o600, stat.S_IMODE(os.stat(target.path).st_mode))
        self.assertEqual("absent", row["before_sha256"])
        self.assertEqual(sha(NEW), row["after_sha256"])
        self.assertEqual("create", row["op"])
        self.assertEqual("edit", row["kind"])
        self.assertTrue(row["backup"].endswith(".absent"))
        marker = os.path.join(self.store_dir(target), row["backup"])
        self.assertEqual(b"", read(marker))
        self.assertIsNone(self.store.backup_path(target, row["backup"]))
        self.assertNotIn("old_value", row)
        self.assertEqual("high", row["new_value"])
        self.assertEqual([row], self.store.rows(target))
        self.assertEqual([], self.baks(target))
        self.assertIsNone(self.store.undo_state(target, row))

    def test_a_file_in_an_existing_claude_folder(self):
        self.no_file()
        target = self.target("project")
        row = self.create(target)
        self.check_created(target, row)
        self.assertNotIn("made_dir", row)
        self.assertEqual(["settings.json", "settings.local.json"], sorted(os.listdir(self.claude)))
        self.assertEqual([], self.leftovers())

    def test_a_file_with_no_claude_folder_makes_it_private(self):
        self.bare()
        target = self.target("project")
        row = self.create(target)
        self.check_created(target, row)
        self.assertTrue(row["made_dir"])
        self.assertEqual(0o700, stat.S_IMODE(os.stat(self.claude).st_mode))
        self.assertEqual(["settings.json"], os.listdir(self.claude))

    def test_the_user_layer_creates_in_the_config_folder(self):
        os.unlink(self.user_file)
        target = self.target("user")
        row = self.create(target)
        self.check_created(target, row)
        self.assertNotIn("made_dir", row)
        self.assertEqual(self.user_file, target.path)

    def test_a_default_save_on_an_absent_file_is_still_refused_and_makes_no_store(self):
        self.no_file()
        with self.assertRaises(es.Refused) as ctx:
            self.store.save(self.target("project"), effort_plan("high"))
        self.assertEqual("file_missing", ctx.exception.code)
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "routing-dashboard")))
        self.bare()
        with self.assertRaises(es.Refused) as ctx:
            self.store.save(self.target("project"), effort_plan("high"))
        self.assertEqual("file_missing", ctx.exception.code)
        self.assertFalse(os.path.exists(self.claude))

    def test_a_missing_base_folder_is_refused_and_nothing_is_made(self):
        target = self.target("project")
        helpers.rmtree_force(self.proj)
        with mock.patch.object(es.os, "mkdir", side_effect=AssertionError("mkdir")) as mk:
            with self.assertRaises(es.Refused) as ctx:
                self.store.save(target, create_plan, allow_absent=True)
        self.assertEqual("file_missing", ctx.exception.code)
        mk.assert_not_called()
        self.assertFalse(os.path.exists(self.proj))
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "routing-dashboard")))

    def test_a_dangling_link_at_claude_is_a_symlink_refusal(self):
        self.bare()
        os.symlink(os.path.join(self.root, "nowhere"), self.claude)
        with self.assertRaises(es.Refused) as ctx:
            self.create()
        self.assertEqual("symlink", ctx.exception.code)
        self.assertTrue(os.path.islink(self.claude))
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "routing-dashboard")))

    def test_a_dangling_link_at_the_file_is_a_symlink_refusal(self):
        self.no_file()
        os.symlink(os.path.join(self.root, "nowhere.json"), self.project_file)
        with self.assertRaises(es.Refused) as ctx:
            self.create()
        self.assertEqual("symlink", ctx.exception.code)
        self.assertTrue(os.path.islink(self.project_file))
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "routing-dashboard")))

    def test_claude_as_a_regular_file_is_not_regular(self):
        self.bare()
        write(self.claude, b"x")
        with self.assertRaises(es.Refused) as ctx:
            self.create()
        self.assertEqual("not_regular", ctx.exception.code)
        self.assertEqual(b"x", read(self.claude))

    def test_a_plan_may_not_delete_the_file(self):
        target = self.target("project")
        with self.assertRaises(ValueError):
            self.store.save(target, lambda raw: es.Plan(None, ["x"], None, None))
        self.assertEqual(SETTINGS, read(self.project_file))

    def test_a_create_that_finds_the_file_present_gets_its_bytes(self):
        seen = []

        def plan(raw):
            seen.append(raw)
            return effort_plan("high")(raw)
        self.store.save(self.target("project"), plan, allow_absent=True)
        self.assertEqual([SETTINGS], seen)

    def test_a_plan_of_none_for_an_absent_file_is_refused(self):
        self.no_file()
        with self.assertRaises(ValueError):
            self.store.save(self.target("project"), lambda raw: es.Plan(None, [], None, None),
                            allow_absent=True)
        self.assertFalse(os.path.exists(self.project_file))


class CreateCrashTests(CreateBase):
    def test_crash_after_the_backup_leaves_an_orphan_marker_the_next_save_removes(self):
        self.bare()
        target = self.target("project")
        self.crash_create("after_backup")
        self.assertFalse(os.path.exists(self.claude))
        self.assertEqual(1, len(self.markers(target)))
        self.assertEqual([], self.store.rows(target))
        orphan = self.markers(target)[0]
        row = self.create(target)
        self.assertEqual([row["backup"]], self.markers(target))
        self.assertNotEqual(orphan, row["backup"])
        self.assertEqual([row], self.store.rows(target))

    def test_crash_after_the_ledger_leaves_a_row_that_is_not_shown(self):
        self.bare()
        target = self.target("project")
        self.crash_create("after_ledger")
        self.assertFalse(os.path.exists(self.claude))
        self.assertEqual(1, len(self.ledger_rows(target)))
        self.assertEqual([], self.store.rows(target))
        row = self.create(target)
        self.assertEqual([row["backup"]], self.markers(target))
        self.assertEqual([row], self.store.rows(target))
        self.assertEqual([row["id"]], [r["id"] for r in self.ledger_rows(target)])

    def test_crash_after_the_mkdir_leaves_an_empty_folder_and_the_next_create_finds_it(self):
        self.bare()
        target = self.target("project")
        self.crash_create("after_mkdir")
        self.assertEqual([], os.listdir(self.claude))
        self.assertEqual(1, len(self.ledger_rows(target)))
        self.assertEqual([], self.store.rows(target))
        row = self.create(target)
        self.assertEqual(NEW, read(self.project_file))
        self.assertNotIn("made_dir", row)
        self.assertEqual([row], self.store.rows(target))
        self.assertEqual([row["backup"]], self.markers(target))

    def test_crash_after_the_temp_leaves_a_temp_the_next_save_sweeps(self):
        self.bare()
        target = self.target("project")
        self.crash_create("after_temp")
        self.assertEqual(1, len(self.leftovers()))
        self.assertFalse(os.path.exists(self.project_file))
        self.assertEqual([], self.store.rows(target))
        row = self.create(target)
        self.assertEqual([], self.leftovers())
        self.assertEqual(["settings.json"], os.listdir(self.claude))
        self.assertEqual([row], self.store.rows(target))

    def test_crash_after_the_rename_leaves_a_row_that_is_newest_and_undoable(self):
        self.bare()
        target = self.target("project")
        self.crash_create("after_rename")
        self.assertEqual(NEW, read(self.project_file))
        rows = self.store.rows(target)
        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0]["made_dir"])
        self.assertIsNone(self.store.undo_state(target, rows[0]))
        result = self.store.restore(target, rows[0]["id"])
        self.assertTrue(result.removed_file)
        self.assertTrue(result.removed_dir)
        self.assertFalse(os.path.exists(self.claude))

    def test_the_file_is_whole_or_absent_at_every_create_crash_point(self):
        for seam_name in ("before_backup", "after_backup", "after_ledger", "after_mkdir",
                          "after_temp", "before_recheck", "before_rename", "after_rename",
                          "dir_fsync", "reread"):
            self.store = es.Store(self.cfg)
            helpers.rmtree_force(os.path.join(self.cfg, "routing-dashboard"))
            helpers.rmtree_force(self.claude)
            self.crash_create(seam_name)
            if os.path.exists(self.project_file):
                self.assertEqual(NEW, read(self.project_file), seam_name)


class PruneMarkerTests(CreateBase):
    def orphan(self, name="000007-" + HEX16 + ".absent", age=0):
        target = self.target("project")
        write(os.path.join(self.store_dir(target), name), b"")
        if age:
            stamp = time.time() - age
            os.utime(os.path.join(self.store_dir(target), name), (stamp, stamp))
        return name

    def test_an_orphan_marker_with_no_rows_at_all_goes(self):
        target = self.target("project")
        name = self.orphan()
        row = self.store.save(target, effort_plan("high"))
        self.assertNotIn(name, os.listdir(self.store_dir(target)))
        self.assertTrue(row["backup"].startswith("000008-"))

    def test_an_orphan_marker_older_than_the_floor_goes(self):
        target = self.target("project")
        self.store.save(target, effort_plan("v1"))
        name = self.orphan(age=3600)
        self.store.save(target, effort_plan("v2"))
        self.assertNotIn(name, os.listdir(self.store_dir(target)))

    def test_a_marker_only_ledger_has_no_floor_so_a_real_orphan_stays_and_a_marker_goes(self):
        self.no_file()
        target = self.target("project")
        name = self.orphan()
        real = "000042-" + HEX16 + ".bak"
        write(os.path.join(self.store_dir(target), real), b"older ledger")
        row = self.create(target)
        listing = os.listdir(self.store_dir(target))
        self.assertNotIn(name, listing)
        self.assertIn(real, listing)
        self.assertIn(row["backup"], listing)

    def test_a_real_orphan_older_than_the_floor_stays(self):
        target = self.target("project")
        self.store.save(target, effort_plan("v1"))
        self.store.save(target, effort_plan("v2"))
        real = "000042-" + HEX16 + ".bak"
        path = write(os.path.join(self.store_dir(target), real), b"old")
        stamp = time.time() - 3600
        os.utime(path, (stamp, stamp))
        self.store.save(target, effort_plan("v3"))
        self.assertIn(real, os.listdir(self.store_dir(target)))

    def test_numbers_count_past_a_marker(self):
        target = self.target("project")
        self.orphan("000042-" + HEX16 + ".absent")
        row = self.store.save(target, effort_plan("high"))
        self.assertTrue(row["backup"].startswith("000043-"))

    def test_a_marker_a_row_names_is_kept_whatever_its_age(self):
        self.no_file()
        target = self.target("project")
        row = self.create(target)
        stamp = time.time() - 7200
        os.utime(os.path.join(self.store_dir(target), row["backup"]), (stamp, stamp))
        self.store.save(target, effort_plan("v2"))
        self.assertEqual([row["backup"]], self.markers(target))

    def test_a_marker_never_sets_the_floor(self):
        target = self.target("project")
        folder = self.store_dir(target)
        self.no_file()
        first = self.create(target)
        stamp = time.time() - 7200
        os.utime(os.path.join(folder, first["backup"]), (stamp, stamp))
        self.assertIsNone(self.store._oldest_mtime(self.open_store(target), [first]))

    def open_store(self, target):
        fd = self.store._open_store(target, create=False)
        self.addCleanup(os.close, fd)
        return fd


class UndoCreateCrashTests(CreateBase):
    def crash_restore(self, seam_name, target, row):
        self.crash_at(seam_name)
        with self.assertRaises(Crash):
            self.store.restore(target, row["id"])
        self.store = es.Store(self.cfg)

    def test_crash_before_the_unlink_keeps_the_file_and_the_create_undoable(self):
        target, row = self.made()
        self.crash_restore("before_unlink", target, row)
        self.assertEqual(NEW, read(self.project_file))
        self.assertEqual([row], self.store.rows(target))
        self.assertEqual(2, len(self.ledger_rows(target)))
        self.assertIsNone(self.store.undo_state(target, row))
        result = self.store.restore(target, row["id"])
        self.assertTrue(result.removed_file)
        self.assertFalse(os.path.exists(self.project_file))

    def test_crash_after_the_unlink_keeps_the_undo_row(self):
        target, row = self.made()
        self.crash_restore("after_unlink", target, row)
        self.assertFalse(os.path.exists(self.project_file))
        rows = self.store.rows(target)
        self.assertEqual(2, len(rows))
        self.assertEqual(row, rows[0])
        undo = rows[1]
        self.assertEqual("undo", undo["kind"])
        self.assertEqual("absent", undo["after_sha256"])
        self.assertEqual(sha(NEW), undo["before_sha256"])
        self.assertTrue(os.path.isdir(self.claude))

    def test_crash_before_the_rmdir_leaves_a_harmless_empty_folder(self):
        target, row = self.made()
        self.crash_restore("before_rmdir", target, row)
        self.assertFalse(os.path.exists(self.project_file))
        self.assertEqual([], os.listdir(self.claude))
        self.assertEqual(2, len(self.store.rows(target)))
        again = self.create(target)
        self.assertEqual(NEW, read(self.project_file))
        self.assertNotIn("made_dir", again)


class UndoCreateTests(CreateBase):
    def test_the_whole_project_folder_is_back_as_it_was(self):
        self.bare()
        before = tree_hash(self.proj)
        target = self.target("project")
        row = self.create(target)
        self.assertNotEqual(before, tree_hash(self.proj))
        result = self.store.restore(target, row["id"])
        self.assertTrue(result.removed_file)
        self.assertTrue(result.removed_dir)
        self.assertTrue(result.matches_backup)
        self.assertEqual(before, tree_hash(self.proj))
        self.assertIsNone(result.restored_from_path)

    def test_the_undo_row_backs_up_the_created_bytes(self):
        target, row = self.made()
        result = self.store.restore(target, row["id"])
        undo = result.row
        self.assertEqual("undo", undo["kind"])
        self.assertEqual("create", undo["op"])
        self.assertEqual(sha(NEW), undo["before_sha256"])
        self.assertEqual("absent", undo["after_sha256"])
        self.assertTrue(undo["backup"].endswith(".bak"))
        self.assertIsNotNone(result.backup_path)
        self.assertEqual(NEW, read(result.backup_path))
        self.assertEqual(row["id"], undo["restored_from"])
        self.assertEqual(row["backup"], undo["restored_from_backup"])
        self.assertEqual("high", undo["old_value"])
        self.assertNotIn("new_value", undo)
        self.assertNotIn("made_dir", undo)
        self.assertEqual([row, undo], self.store.rows(target))

    def test_a_stray_file_in_claude_keeps_the_folder(self):
        target, row = self.made()
        stray = write(os.path.join(self.claude, ".DS_Store"), b"junk")
        result = self.store.restore(target, row["id"])
        self.assertTrue(result.removed_file)
        self.assertFalse(result.removed_dir)
        self.assertTrue(result.matches_backup)
        self.assertEqual([".DS_Store"], os.listdir(self.claude))
        self.assertEqual(b"junk", read(stray))
        self.assertFalse(os.path.exists(self.project_file))

    def test_a_leftover_temp_does_not_block_the_folder_removal(self):
        target, row = self.made()
        write(os.path.join(self.claude, ".routing-dashboard-" + HEX16 + ".tmp"), b"x")
        result = self.store.restore(target, row["id"])
        self.assertTrue(result.removed_dir)
        self.assertFalse(os.path.exists(self.claude))

    def test_a_folder_that_was_already_there_stays(self):
        self.no_file()
        target = self.target("project")
        row = self.create(target)
        result = self.store.restore(target, row["id"])
        self.assertTrue(result.removed_file)
        self.assertFalse(result.removed_dir)
        self.assertEqual(["settings.local.json"], os.listdir(self.claude))

    def test_the_user_layer_has_no_folder_to_remove(self):
        os.unlink(self.user_file)
        target = self.target("user")
        row = self.create(target)
        result = self.store.restore(target, row["id"])
        self.assertTrue(result.removed_file)
        self.assertFalse(result.removed_dir)
        self.assertTrue(os.path.isdir(self.cfg))
        self.assertFalse(os.path.exists(self.user_file))

    def test_a_folder_swapped_for_another_before_the_rmdir_stays(self):
        target, row = self.made()
        held = os.path.join(self.root, "held")

        def swap():
            os.rename(self.claude, held)
            os.makedirs(self.claude)
        self.at("before_rmdir", swap)
        result = self.store.restore(target, row["id"])
        self.assertTrue(result.removed_file)
        self.assertFalse(result.removed_dir)
        self.assertTrue(os.path.isdir(self.claude))
        self.assertTrue(os.path.isdir(held))

    def test_restoring_the_undo_makes_the_file_again(self):
        target, row = self.made()
        undo = self.store.restore(target, row["id"]).row
        again = self.store.restore(target, undo["id"])
        self.assertEqual(NEW, read(self.project_file))
        self.assertFalse(again.removed_file)
        self.assertEqual("absent", again.row["before_sha256"])
        self.assertTrue(again.row["backup"].endswith(".absent"))
        self.assertTrue(again.row["made_dir"])
        self.assertEqual(0o600, stat.S_IMODE(os.stat(self.project_file).st_mode))

    def test_a_default_undo_works_on_a_hand_deleted_edit(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        os.unlink(self.project_file)
        self.assertEqual("changed_since_save", self.store.undo_state(target, row))
        with self.assertRaises(es.ChangedSinceSave):
            self.store.restore(target, row["id"])
        self.assertFalse(os.path.exists(self.project_file))
        self.assertEqual([row], self.store.rows(target))


class UndoCreateStateTests(CreateBase):
    def marker(self, target, row):
        return os.path.join(self.store_dir(target), row["backup"])

    def assert_blocked(self, target, row, state, error):
        self.assertEqual(state, self.store.undo_state(target, row))
        with self.assertRaises(error) as ctx:
            self.store.restore(target, row["id"])
        self.assertEqual(NEW, read(self.project_file))
        self.assertEqual([row], self.store.rows(target))
        self.assertEqual(1, len(self.ledger_rows(target)))
        return ctx.exception

    def test_a_good_marker_row_can_be_undone(self):
        target, row = self.made()
        self.assertIsNone(self.store.undo_state(target, row))

    def test_a_missing_marker_is_pruned(self):
        target, row = self.made()
        os.unlink(self.marker(target, row))
        exc = self.assert_blocked(target, row, "backup_pruned", es.NotUndoable)
        self.assertEqual("backup_pruned", exc.reason)

    def test_a_marker_with_bytes_is_damaged(self):
        target, row = self.made()
        write(self.marker(target, row), b"x")
        exc = self.assert_blocked(target, row, "backup_damaged", es.BackupDamaged)
        self.assertIsNone(exc.backup_path)

    def test_a_marker_replaced_by_a_link_is_damaged(self):
        target, row = self.made()
        outside = write(os.path.join(self.root, "empty"), b"")
        os.unlink(self.marker(target, row))
        os.symlink(outside, self.marker(target, row))
        self.assert_blocked(target, row, "backup_damaged", es.BackupDamaged)

    def test_a_marker_replaced_by_a_folder_is_damaged(self):
        target, row = self.made()
        os.unlink(self.marker(target, row))
        os.mkdir(self.marker(target, row))
        self.assert_blocked(target, row, "backup_damaged", es.BackupDamaged)

    def test_an_absent_name_with_a_real_before_hash_is_damaged(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        name = "000009-" + HEX16 + ".absent"
        write(os.path.join(self.store_dir(target), name), b"")
        self.rewrite_ledger(target, lambda rows: rows[0].update(backup=name))
        row = self.store.rows(target)[0]
        edited = read(self.project_file)
        self.assertEqual("backup_damaged", self.store.undo_state(target, row))
        with self.assertRaises(es.BackupDamaged) as ctx:
            self.store.restore(target, row["id"])
        self.assertIsNone(ctx.exception.backup_path)
        self.assertEqual(edited, read(self.project_file))

    def test_a_real_name_with_an_absent_before_hash_is_damaged(self):
        target, row = self.made()
        name = "000009-" + HEX16 + ".bak"
        write(os.path.join(self.store_dir(target), name), b"")
        self.rewrite_ledger(target, lambda rows: rows[0].update(backup=name))
        row = self.store.rows(target)[0]
        self.assertEqual("backup_damaged", self.store.undo_state(target, row))
        with self.assertRaises(es.BackupDamaged):
            self.store.restore(target, row["id"])
        self.assertEqual(NEW, read(self.project_file))

    def test_a_half_pair_reads_damaged_even_with_no_store_folder(self):
        target, row = self.made()
        half = dict(row, backup="000009-" + HEX16 + ".bak")
        whole = dict(row)
        helpers.rmtree_force(os.path.join(self.cfg, "routing-dashboard"))
        self.assertEqual("backup_damaged", self.store.undo_state(target, half))
        self.assertEqual("backup_pruned", self.store.undo_state(target, whole))
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "routing-dashboard")))

    def test_a_file_edited_by_hand_is_changed_since_save_and_is_not_deleted(self):
        target, row = self.made()
        theirs = b'{"effortLevel": "max"}\n'
        write(self.project_file, theirs)
        self.assertEqual("changed_since_save", self.store.undo_state(target, row))
        with self.assertRaises(es.ChangedSinceSave) as ctx:
            self.store.restore(target, row["id"])
        self.assertIsNone(ctx.exception.backup_path)
        self.assertEqual(theirs, read(self.project_file))
        self.assertTrue(os.path.isdir(self.claude))
        self.assertEqual(1, len(self.ledger_rows(target)))

    def test_a_file_deleted_by_hand_trims_the_row(self):
        target, row = self.made()
        os.unlink(self.project_file)
        self.assertEqual([], self.store.rows(target))
        self.assertIsNone(self.store.find(target, row["id"]))
        with self.assertRaises(es.UnknownEdit):
            self.store.restore(target, row["id"])
        self.assertTrue(os.path.isdir(self.claude))


class CreateStaleTests(CreateBase):
    def clean(self, target):
        self.assertEqual([], self.markers(target))
        self.assertEqual([], self.ledger_rows(target))
        self.assertEqual([], self.store.rows(target))

    def test_claude_swapped_for_another_folder_between_mkdir_and_rename_is_stale(self):
        self.bare()
        target = self.target("project")
        held = os.path.join(self.root, "held")

        def swap():
            os.rename(self.claude, held)
            os.makedirs(self.claude)
        self.at("before_recheck", swap)
        with self.assertRaises(es.Stale) as ctx:
            self.create(target)
        self.assertEqual("file", ctx.exception.changed)
        self.assertEqual([], os.listdir(self.claude))
        self.assertEqual([], os.listdir(held))
        # the folder this save made sits under another name, so it could not be taken away
        self.assertTrue(ctx.exception.dir_left)
        self.clean(target)

    def test_claude_removed_between_mkdir_and_rename_is_stale(self):
        self.bare()
        target = self.target("project")

        def remove():
            for name in os.listdir(self.claude):
                os.unlink(os.path.join(self.claude, name))
            os.rmdir(self.claude)
        self.at("before_recheck", remove)
        with self.assertRaises(es.Stale) as ctx:
            self.create(target)
        self.assertEqual("file", ctx.exception.changed)
        self.assertFalse(os.path.exists(self.claude))
        self.clean(target)

    def test_a_file_that_appears_before_the_recheck_is_stale_and_survives(self):
        self.bare()
        target = self.target("project")
        theirs = b'{"effortLevel": "max"}\n'
        self.at("before_recheck", lambda: write(self.project_file, theirs))
        with self.assertRaises(es.Stale) as ctx:
            self.create(target)
        self.assertEqual("file_appeared", ctx.exception.changed)
        self.assertEqual(theirs, read(self.project_file))
        self.assertEqual(["settings.json"], os.listdir(self.claude))
        self.assertTrue(ctx.exception.dir_left)
        self.clean(target)

    def test_a_file_that_appears_in_an_existing_claude_is_stale_without_dir_left(self):
        self.no_file()
        target = self.target("project")
        theirs = b'{"effortLevel": "max"}\n'
        self.at("before_recheck", lambda: write(self.project_file, theirs))
        with self.assertRaises(es.Stale) as ctx:
            self.create(target)
        self.assertEqual("file_appeared", ctx.exception.changed)
        self.assertFalse(ctx.exception.dir_left)
        self.assertEqual(theirs, read(self.project_file))
        self.assertEqual([], self.leftovers())
        self.clean(target)

    def test_a_claude_made_by_someone_else_after_the_read_is_stale(self):
        self.bare()
        target = self.target("project")
        real = es.os.mkdir

        def racing(name, mode=0o777, dir_fd=None):
            real(name, mode, dir_fd=dir_fd)  # their folder lands first
            return real(name, mode, dir_fd=dir_fd)  # ours then finds it there
        with mock.patch.object(es.os, "mkdir", side_effect=racing):
            with self.assertRaises(es.Stale) as ctx:
                self.create(target)
        self.assertEqual("file_appeared", ctx.exception.changed)
        self.assertTrue(os.path.isdir(self.claude))
        self.assertFalse(ctx.exception.dir_left)
        self.clean(target)

    def test_a_replace_whose_file_vanishes_before_the_recheck_is_stale_file_removed(self):
        target = self.target("project")
        self.at("before_recheck", lambda: os.unlink(self.project_file))
        with self.assertRaises(es.Stale) as ctx:
            self.store.save(target, effort_plan("high"))
        self.assertEqual("file_removed", ctx.exception.changed)
        self.assertEqual([], self.leftovers())
        self.assertEqual([], self.store.rows(target))

    def test_a_delete_whose_file_changes_before_the_recheck_is_stale_and_keeps_their_bytes(self):
        target, row = self.made()
        theirs = b'{"effortLevel": "max"}\n'
        self.at("before_recheck", lambda: write(self.project_file, theirs))
        with self.assertRaises(es.Stale) as ctx:
            self.store.restore(target, row["id"])
        self.assertEqual("file", ctx.exception.changed)
        self.assertEqual(theirs, read(self.project_file))
        self.assertEqual([row["id"]], [r["id"] for r in self.ledger_rows(target)])
        self.assertEqual([], self.baks(target))

    def test_a_delete_whose_file_vanishes_before_the_recheck_is_file_removed(self):
        target, row = self.made()
        self.at("before_recheck", lambda: os.unlink(self.project_file))
        with self.assertRaises(es.Stale) as ctx:
            self.store.restore(target, row["id"])
        self.assertEqual("file_removed", ctx.exception.changed)


class CreateFailureTests(CreateBase):
    def test_a_failure_after_the_mkdir_or_the_temp_takes_the_made_folder_away(self):
        for seam_name in ("after_mkdir", "after_temp", "before_recheck", "before_rename"):
            self.store = es.Store(self.cfg)
            helpers.rmtree_force(os.path.join(self.cfg, "routing-dashboard"))
            helpers.rmtree_force(self.claude)
            target = self.target("project")
            self.at(seam_name, fail)
            with self.assertRaises(es.WriteFailed) as ctx:
                self.create(target)
            self.assertFalse(ctx.exception.dir_left, seam_name)
            self.assertFalse(os.path.exists(self.claude), seam_name)
            self.assertEqual([], self.markers(target), seam_name)
            self.assertEqual([], self.ledger_rows(target), seam_name)
            self.assertEqual([], self.store.rows(target), seam_name)

    def test_a_file_dropped_in_the_made_folder_keeps_it_and_says_so(self):
        for seam_name in ("after_mkdir", "after_temp"):
            self.store = es.Store(self.cfg)
            helpers.rmtree_force(os.path.join(self.cfg, "routing-dashboard"))
            helpers.rmtree_force(self.claude)
            target = self.target("project")

            def drop():
                write(os.path.join(self.claude, "keep.txt"), b"theirs")
                fail()
            self.at(seam_name, drop)
            with self.assertRaises(es.WriteFailed) as ctx:
                self.create(target)
            self.assertTrue(ctx.exception.dir_left, seam_name)
            self.assertEqual(["keep.txt"], os.listdir(self.claude), seam_name)
            self.assertEqual([], self.markers(target), seam_name)
            self.assertEqual([], self.ledger_rows(target), seam_name)

    def test_a_folder_made_but_never_opened_is_still_taken_away_when_empty(self):
        self.bare()
        target = self.target("project")
        real_open, real_mkdir = os.open, os.mkdir
        made = []

        def mkdir(*args, **kwargs):
            real_mkdir(*args, **kwargs)
            if args[0] != ".claude":
                return
            made.append(args[0])

        def opener(path, flags, *args, **kwargs):
            if made and path == made[0] and flags == es._SUBDIR_FLAGS:
                raise OSError(5, "simulated")
            return real_open(path, flags, *args, **kwargs)
        with mock.patch.object(os, "mkdir", side_effect=mkdir), mock.patch.object(os, "open", side_effect=opener):
            with self.assertRaises(es.WriteFailed) as ctx:
                self.create(target)
        self.assertEqual([".claude"], made)
        self.assertFalse(ctx.exception.dir_left)
        self.assertFalse(os.path.exists(self.claude))
        self.assertEqual([], self.markers(target))
        self.assertEqual([], self.ledger_rows(target))

    def test_a_folder_made_but_never_opened_and_not_empty_is_reported_left(self):
        self.bare()
        target = self.target("project")
        real_open, real_mkdir = os.open, os.mkdir
        made = []

        def mkdir(*args, **kwargs):
            real_mkdir(*args, **kwargs)
            if args[0] != ".claude":
                return
            made.append(args[0])
            write(os.path.join(self.claude, "keep.txt"), b"theirs")

        def opener(path, flags, *args, **kwargs):
            if made and path == made[0] and flags == es._SUBDIR_FLAGS:
                raise OSError(5, "simulated")
            return real_open(path, flags, *args, **kwargs)
        with mock.patch.object(os, "mkdir", side_effect=mkdir), mock.patch.object(os, "open", side_effect=opener):
            with self.assertRaises(es.WriteFailed) as ctx:
                self.create(target)
        self.assertTrue(ctx.exception.dir_left)
        self.assertEqual(["keep.txt"], os.listdir(self.claude))

    def test_an_os_error_is_wrapped_and_carries_dir_left(self):
        self.bare()
        target = self.target("project")

        def drop():
            write(os.path.join(self.claude, "keep.txt"), b"theirs")
            raise OSError(5, "simulated")
        self.at("after_temp", drop)
        with self.assertRaises(es.WriteFailed) as ctx:
            self.create(target)
        self.assertTrue(ctx.exception.dir_left)

    def test_a_failure_in_an_existing_claude_leaves_the_folder_and_no_dir_left(self):
        self.no_file()
        target = self.target("project")
        self.at("after_temp", fail)
        with self.assertRaises(es.WriteFailed) as ctx:
            self.create(target)
        self.assertFalse(ctx.exception.dir_left)
        self.assertTrue(os.path.isdir(self.claude))
        self.assertEqual([], self.leftovers())
        self.assertEqual([], self.markers(target))

    def test_a_failed_marker_read_back_rolls_the_create_back(self):
        self.bare()
        target = self.target("project")
        real = es._read_file

        def wrong(name, dir_fd, cap):
            data = real(name, dir_fd, cap)
            return b"x" if name.endswith(".absent") else data
        with mock.patch.object(es, "_read_file", side_effect=wrong):
            with self.assertRaises(es.WriteFailed):
                self.create(target)
        self.assertEqual([], self.markers(target))
        self.assertFalse(os.path.exists(self.claude))

    def test_a_failure_before_the_unlink_keeps_the_file_and_rolls_back(self):
        target, row = self.made()
        self.at("before_unlink", fail)
        with self.assertRaises(es.WriteFailed):
            self.store.restore(target, row["id"])
        self.assertEqual(NEW, read(self.project_file))
        self.assertEqual([row["id"]], [r["id"] for r in self.ledger_rows(target)])
        self.assertEqual([], self.baks(target))


class VerifyDeleteTests(CreateBase):
    def test_a_file_that_comes_back_after_the_unlink_is_raced(self):
        target, row = self.made()
        theirs = b'{"effortLevel": "max"}\n'
        self.at("reread", lambda: write(self.project_file, theirs))
        with self.assertRaises(es.Raced) as ctx:
            self.store.restore(target, row["id"])
        self.assertFalse(ctx.exception.matches_backup)
        self.assertIsNone(ctx.exception.restored_from_path)
        self.assertEqual(theirs, read(self.project_file))
        self.assertTrue(os.path.isdir(self.claude))

    def test_a_refused_reread_is_unverified(self):
        target, row = self.made()
        outside = write(os.path.join(self.root, "outside.json"), SETTINGS)
        self.at("reread", lambda: os.symlink(outside, self.project_file))
        with self.assertRaises(es.Unverified) as ctx:
            self.store.restore(target, row["id"])
        self.assertEqual("reread", ctx.exception.stage)
        self.assertTrue(os.path.isdir(self.claude))

    def test_a_failed_directory_fsync_is_unverified(self):
        target, row = self.made()
        self.at("dir_fsync", lambda: (_ for _ in ()).throw(OSError(5, "simulated")))
        with self.assertRaises(es.Unverified) as ctx:
            self.store.restore(target, row["id"])
        self.assertEqual("fsync", ctx.exception.stage)
        self.assertFalse(os.path.exists(self.project_file))
        self.assertTrue(os.path.isdir(self.claude))

    def test_a_create_whose_reread_finds_other_bytes_is_raced(self):
        self.no_file()
        target = self.target("project")
        theirs = b'{"effortLevel": "max"}\n'

        def swap():
            write(self.project_file + ".new", theirs)
            os.rename(self.project_file + ".new", self.project_file)
        self.at("reread", swap)
        with self.assertRaises(es.Raced) as ctx:
            self.create(target)
        self.assertIsNone(ctx.exception.backup_path)
        self.assertIsNone(ctx.exception.matches_backup)

    def test_a_create_syncs_the_base_folder_too(self):
        self.bare()
        synced = []
        real = es._fullfsync

        def spy(fd):
            synced.append(os.fstat(fd).st_ino)
            return real(fd)
        with mock.patch.object(es, "_fullfsync", side_effect=spy):
            self.create()
        self.assertIn(os.stat(self.proj).st_ino, synced)
        self.assertIn(os.stat(self.claude).st_ino, synced)


class RowShapeTests(CreateBase):
    def test_an_edit_records_replace_by_default_and_the_plans_op(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        self.assertEqual("replace", row["op"])
        self.assertNotIn("made_dir", row)

        def plan(raw):
            return es.Plan(raw.replace(b"low", b"mid"), ["effortLevel"], "low", "mid", "insert")
        write(self.project_file, SETTINGS)
        second = self.store.save(target, plan)
        self.assertEqual("insert", second["op"])

    def test_an_old_row_with_no_op_reads_as_replace(self):
        target = self.target("project")
        row = self.store.save(target, effort_plan("high"))
        self.rewrite_ledger(target, lambda rows: rows[0].pop("op"))
        result = self.store.restore(target, row["id"])
        self.assertEqual("replace", result.row["op"])
        self.assertFalse(result.removed_file)
        self.assertFalse(result.removed_dir)
        self.assertEqual(SETTINGS, read(self.project_file))

    def test_a_null_value_leaves_its_key_out(self):
        target = self.target("project")
        row = self.store.save(target, lambda raw: es.Plan(raw + b" ", ["effortLevel"], None, None))
        self.assertNotIn("old_value", row)
        self.assertNotIn("new_value", row)
        self.assertEqual(row, self.store.rows(target)[0])
        row2 = self.store.save(target, lambda raw: es.Plan(raw + b" ", ["effortLevel"], "a", None))
        self.assertEqual("a", row2["old_value"])
        self.assertNotIn("new_value", row2)

    def test_a_secret_value_is_still_masked(self):
        target = self.target("project")
        row = self.store.save(target, lambda raw: es.Plan(raw + b" ", ["env"], "sk-planted-a", "x"))
        self.assertEqual("hidden", row["old_value"])

    def test_the_ledger_stays_version_one(self):
        self.no_file()
        self.create()
        doc = json.loads(read(os.path.join(self.store_dir(), "ledger.json")))
        self.assertEqual(1, doc["version"])


class CreateDescriptorTests(CreateBase):
    def test_no_descriptor_leaks_over_a_create_and_an_undo(self):
        self.bare()
        target = self.target("project")
        row = self.create(target)
        self.store.restore(target, row["id"])
        before = fd_count()
        for _ in range(5):
            row = self.create(target)
            self.store.restore(target, row["id"])
            self.store.rows(target)
        self.assertEqual(before, fd_count())

    def test_no_descriptor_leaks_over_failed_creates(self):
        self.bare()
        target = self.target("project")
        before = fd_count()
        for seam_name in ("after_mkdir", "after_temp", "before_recheck"):
            self.at(seam_name, fail)
            with self.assertRaises(es.WriteFailed):
                self.create(target)
        self.store.seam = None
        with self.assertRaises(es.Refused):
            self.store.save(target, create_plan)
        self.assertEqual(before, fd_count())

    def test_no_descriptor_leaks_over_a_stale_create_and_a_blocked_undo(self):
        self.bare()
        target = self.target("project")
        before = fd_count()
        self.at("before_recheck", lambda: write(self.project_file, b"{}\n"))
        with self.assertRaises(es.Stale):
            self.create(target)
        self.store.seam = None
        self.assertEqual(before, fd_count())


if __name__ == "__main__":
    unittest.main()

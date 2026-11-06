"""Checks of the plugin packages: the generated payloads, the manifests, the hook and the skills.

tools/build_plugins.py copies the dashboard and installer files into plugins/routing-dashboard/payload/ and the HiveMind
library into plugins/hivemind/payload/. These tests prove each copy matches its sources (and that the drift check
notices when it does not), that the dashboard payload holds everything the installer and the server import, and that
each plugin root has the shape the design calls for. Nothing here runs
`claude`, installs a plugin or reads the real ~/.claude. The copy tests work in a temp folder outside every git tree.
"""
import ast
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest

import helpers

sys.dont_write_bytecode = True

REPO = helpers.REPO
BUILD = os.path.join(REPO, "tools", "build_plugins.py")
PLUGIN = os.path.join(REPO, "plugins", "routing-dashboard")
PAYLOAD = os.path.join(PLUGIN, "payload")
MARKETPLACE = os.path.join(REPO, ".claude-plugin", "marketplace.json")
PLUGIN_JSON = os.path.join(PLUGIN, ".claude-plugin", "plugin.json")
HOOKS_JSON = os.path.join(PLUGIN, "hooks", "hooks.json")
SKILL = os.path.join(PLUGIN, "skills", "dashboard", "SKILL.md")
LAUNCHER = os.path.join(PLUGIN, "bin", "routing-dashboard")
HM_PLUGIN = os.path.join(REPO, "plugins", "hivemind")
HM_PAYLOAD = os.path.join(HM_PLUGIN, "payload")
HM_PLUGIN_JSON = os.path.join(HM_PLUGIN, ".claude-plugin", "plugin.json")
HM_WRAPPER = os.path.join(HM_PLUGIN, "bin", "hivemind")
HM_SKILLS = os.path.join(HM_PLUGIN, "skills")
HM_WRAPPER_TEXT = 'python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind"'
HM_HOOKS_JSON = os.path.join(HM_PLUGIN, "hooks", "hooks.json")
HM_GUARD_RULE = "Bash(python3 *bin/hivemind*)"
HM_ACTIONS = ["status", "check", "link", "related", "inbox", "init", "consolidate"]
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
ONE_MB = 1024 * 1024
LAUNCHER_PATH_TEXT = 'python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard"'
# The `if` rule of the PreToolUse guard hook. The hook denies the launcher to the model, its
# subagents and background agents, and a skill's own ! line never reaches it (probed on Claude
# Code 2.1.302). A disallowed-tools deny on the skill outlived the command, so the skill has none.
GUARD_RULE = "Bash(python3 *bin/routing-dashboard*)"
GUARD_ENTRY = {"type": "command", "command": "python3",
               "args": ["${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard", "guard"],
               "if": GUARD_RULE, "onFailure": "block"}
HM_GUARD_ENTRY = {"type": "command", "command": "python3",
                  "args": ["${CLAUDE_PLUGIN_ROOT}/bin/hivemind", "guard"],
                  "if": HM_GUARD_RULE, "onFailure": "block"}


def bash_rule_regex(rule):
    """A Bash(...) permission rule as a regex: * matches any run of characters, the rest is literal."""
    assert rule.startswith("Bash(") and rule.endswith(")"), rule
    return re.compile(".*".join(re.escape(part) for part in rule[len("Bash("):-1].split("*")), re.S)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_script(name, path):
    """Import a script that has no .py suffix."""
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def payload_files(payload=PAYLOAD):
    """Relative paths (forward slashes) of every file under a payload."""
    found = []
    for dirpath, _dirs, files in os.walk(payload):
        for name in files:
            found.append(os.path.relpath(os.path.join(dirpath, name), payload).replace(os.sep, "/"))
    return sorted(found)


def source_files(payload=PAYLOAD):
    """payload_files() without BUILD.json, which the build writes and no source holds."""
    return [rel for rel in payload_files(payload) if rel != "BUILD.json"]


def run_build(script, *args, env=None):
    env = dict(os.environ if env is None else env)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, "-B", script] + list(args), cwd=os.path.dirname(os.path.dirname(script)),
                          env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)


class DriftTest(unittest.TestCase):
    def test_committed_payload_matches_its_sources(self):
        proc = run_build(BUILD, "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_check_names_a_changed_file_and_the_build_fixes_it(self):
        with CopiedTree() as tree:
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)
            version = os.path.join(tree.root, "dashboard", "version.py")
            with open(version, "a", encoding="utf-8") as fh:
                fh.write("\n# changed for the drift test\n")
            tree.bump_version("9.9.9")
            proc = run_build(tree.build, "--check")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("plugins/routing-dashboard/payload/dashboard/version.py", proc.stdout)
            self.assertIn("changed bytes", proc.stdout)
            self.assertIn("python3 tools/build_plugins.py", proc.stdout.splitlines()[-1])
            self.assertEqual(run_build(tree.build).returncode, 0)
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)
            self.assertEqual(read_text(version), read_text(os.path.join(tree.payload, "dashboard", "version.py")))

    def test_a_source_change_without_a_version_bump_is_refused(self):
        with CopiedTree() as tree:
            version = os.path.join(tree.root, "dashboard", "version.py")
            with open(version, "a", encoding="utf-8") as fh:
                fh.write("\n# changed without a bump\n")
            before = tree.snapshot()
            proc = run_build(tree.build)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("the payload changed but plugins/routing-dashboard/.claude-plugin/plugin.json "
                          "still says version %s; bump it, then run the build again" % tree.version(), proc.stderr)
            self.assertEqual(tree.snapshot(), before, "a refused build writes nothing")
            tree.bump_version("9.9.9")
            self.assertEqual(run_build(tree.build).returncode, 0)
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)
            record = read_json(os.path.join(tree.payload, "BUILD.json"))
            self.assertEqual(record["plugin_version"], "9.9.9")
            self.assertEqual(read_text(version), read_text(os.path.join(tree.payload, "dashboard", "version.py")))

    def test_a_library_change_lands_in_both_payloads_and_needs_both_bumps(self):
        with CopiedTree() as tree:
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)
            library = os.path.join(tree.root, "hooks", "hivemind_lib.py")
            with open(library, "a", encoding="utf-8") as fh:
                fh.write("\n# changed for the two-payload test\n")
            proc = run_build(tree.build, "--check")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("changed bytes: plugins/routing-dashboard/payload/hooks/hivemind_lib.py", proc.stdout)
            self.assertIn("changed bytes: plugins/hivemind/payload/hooks/hivemind_lib.py", proc.stdout)
            before = tree.snapshot()
            refused = run_build(tree.build)
            self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
            self.assertIn("plugins/routing-dashboard/.claude-plugin/plugin.json still says version %s"
                          % tree.version(), refused.stderr)
            self.assertEqual(tree.snapshot(), before, "a refused build writes nothing")
            tree.bump_version("9.9.9", "hivemind")
            refused = run_build(tree.build)
            self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
            self.assertIn("plugins/routing-dashboard/.claude-plugin/plugin.json", refused.stderr)
            self.assertNotIn("plugins/hivemind/.claude-plugin/plugin.json still says", refused.stderr)
            tree.bump_version("9.9.9", "routing-dashboard")
            proc = run_build(tree.build)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)
            for payload in (tree.payload, tree.hm_payload):
                self.assertEqual(read_text(library), read_text(os.path.join(payload, "hooks", "hivemind_lib.py")))
                self.assertEqual(read_json(os.path.join(payload, "BUILD.json"))["plugin_version"], "9.9.9")

    def test_a_hivemind_only_bump_leaves_the_dashboard_payload_alone(self):
        with CopiedTree() as tree:
            before = tree.snapshot()
            tree.bump_version("9.9.9", "hivemind")
            proc = run_build(tree.build)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            after = tree.snapshot()
            changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
            self.assertEqual(changed, [os.path.join("plugins", "hivemind", ".claude-plugin", "plugin.json"),
                                       os.path.join("plugins", "hivemind", "payload", "BUILD.json")])

    def test_check_flags_a_stale_or_missing_build_record(self):
        with CopiedTree() as tree:
            path = os.path.join(tree.payload, "BUILD.json")
            good = read_text(path)
            record = json.loads(good)
            for change, reason in (({"payload_sha256": "0" * 64}, "payload_sha256 does not match"),
                                   ({"plugin_version": "0.0.1"}, "plugin_version 0.0.1 differs from plugin.json")):
                bad = dict(record)
                bad.update(change)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(bad, indent=2, sort_keys=True) + "\n")
                proc = run_build(tree.build, "--check")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn(reason, proc.stdout)
                self.assertIn("payload/BUILD.json", proc.stdout)
            os.remove(path)
            proc = run_build(tree.build, "--check")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("missing: plugins/routing-dashboard/payload/BUILD.json", proc.stdout)
            self.assertEqual(run_build(tree.build).returncode, 0, "no record to compare, so the build writes it")
            self.assertEqual(read_text(path), good)
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)

    def test_the_committed_build_record_is_sorted_and_pretty(self):
        text = read_text(os.path.join(PAYLOAD, "BUILD.json"))
        record = json.loads(text)
        self.assertEqual(sorted(record), ["payload_sha256", "plugin_version"])
        self.assertEqual(record["plugin_version"], read_json(PLUGIN_JSON)["version"])
        self.assertRegex(record["payload_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(text, json.dumps(record, indent=2, sort_keys=True) + "\n")

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_the_git_path_drops_an_untracked_file(self):
        with CopiedTree() as tree:
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tree.base,
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
            for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "sources"]):
                proc = subprocess.run(["git"] + args, cwd=tree.root, env=env, stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            stray = os.path.join(tree.root, "dashboard", "zz_untracked.py")
            with open(stray, "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            self.assertEqual(run_build(tree.build, env=env).returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(tree.payload, "dashboard", "zz_untracked.py")))
            self.assertEqual(run_build(tree.build, "--check", env=env).returncode, 0)
            # Without a repo at this folder the build walks the folders, so the same file is picked up.
            shutil.rmtree(os.path.join(tree.root, ".git"))
            tree.bump_version("9.9.9")
            self.assertEqual(run_build(tree.build, env=env).returncode, 0)
            self.assertTrue(os.path.exists(os.path.join(tree.payload, "dashboard", "zz_untracked.py")))

    def test_check_writes_nothing(self):
        with CopiedTree() as tree:
            version = os.path.join(tree.root, "dashboard", "version.py")
            with open(version, "a", encoding="utf-8") as fh:
                fh.write("\n# changed for the drift test\n")
            before = tree.snapshot()
            self.assertEqual(run_build(tree.build, "--check").returncode, 1)
            self.assertEqual(tree.snapshot(), before)

    def test_build_removes_stale_files_and_empty_folders(self):
        with CopiedTree() as tree:
            stale_file = os.path.join(tree.payload, "dashboard", "stale.py")
            stale_dir = os.path.join(tree.payload, "old", "deeper")
            os.makedirs(stale_dir)
            with open(stale_file, "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            with open(os.path.join(stale_dir, "note.txt"), "w", encoding="utf-8") as fh:
                fh.write("x\n")
            proc = run_build(tree.build, "--check")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("payload/dashboard/stale.py", proc.stdout)
            self.assertIn("payload/old/deeper/note.txt", proc.stdout)
            self.assertEqual(run_build(tree.build).returncode, 0)
            self.assertFalse(os.path.exists(stale_file))
            self.assertFalse(os.path.exists(os.path.join(tree.payload, "old")))
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)

    def test_check_reports_a_missing_file_and_an_exec_bit_change(self):
        with CopiedTree() as tree:
            os.remove(os.path.join(tree.payload, "agent_md.py"))
            os.chmod(os.path.join(tree.payload, "install.py"), 0o644)
            proc = run_build(tree.build, "--check")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("missing: plugins/routing-dashboard/payload/agent_md.py", proc.stdout)
            self.assertIn("changed exec bit: plugins/routing-dashboard/payload/install.py", proc.stdout)
            self.assertEqual(run_build(tree.build).returncode, 0)
            self.assertTrue(os.access(os.path.join(tree.payload, "install.py"), os.X_OK))
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)

    def test_files_outside_the_source_lists_do_not_count(self):
        with CopiedTree() as tree:
            for rel in ("dashboard/experiments/note.py", "dashboard/__pycache__/x.pyc", "dashboard/static/.hidden"):
                path = os.path.join(tree.root, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(b"x")
            self.assertEqual(run_build(tree.build, "--check").returncode, 0)

    def test_hook_names_come_from_the_text_of_install(self):
        build = load_module("build_plugins_under_test", BUILD)
        install = load_module("install_for_hook_names", os.path.join(REPO, "install.py"))
        self.assertEqual(build.hook_names(REPO), install.HOOK_NAMES)
        self.assertEqual([p["name"] for p in build.PLUGINS], ["routing-dashboard", "hivemind"])
        self.assertEqual(build.hivemind_files(REPO), ["hooks/hivemind_lib.py"])


class CopiedTree:
    """The sources a payload build reads, copied into a temp folder outside every git tree.

    The sources are found from the committed payload (every payload file has a source at the same relative path),
    so a stray untracked file in the checkout cannot leak into the copy."""

    def __enter__(self):
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="mr-plugin-build-", dir=helpers._tmp_base()))
        self.root = os.path.join(self.base, "repo")
        os.makedirs(os.path.join(self.root, "tools"))
        self.build = os.path.join(self.root, "tools", "build_plugins.py")
        shutil.copy2(BUILD, self.build)
        shutil.copy2(os.path.join(REPO, "LICENSE"), os.path.join(self.root, "LICENSE"))
        # Each plugin is copied by its own payload's file list: every payload file has a source at the same
        # relative path, then come its payload copy, its LICENSE and its manifest.
        for name, folder, payload in (("routing-dashboard", PLUGIN, PAYLOAD), ("hivemind", HM_PLUGIN, HM_PAYLOAD)):
            for rel in source_files(payload):
                self.copy(rel, rel)
            for rel in payload_files(payload):
                self.copy(rel, "plugins/%s/payload/%s" % (name, rel), from_payload=payload)
            shutil.copy2(os.path.join(folder, "LICENSE"), os.path.join(self.root, "plugins", name, "LICENSE"))
            manifest = os.path.join(self.root, "plugins", name, ".claude-plugin", "plugin.json")
            os.makedirs(os.path.dirname(manifest))
            shutil.copy2(os.path.join(folder, ".claude-plugin", "plugin.json"), manifest)
        self.payload = os.path.join(self.root, "plugins", "routing-dashboard", "payload")
        self.hm_payload = os.path.join(self.root, "plugins", "hivemind", "payload")
        self.manifest = os.path.join(self.root, "plugins", "routing-dashboard", ".claude-plugin", "plugin.json")
        self.hm_manifest = os.path.join(self.root, "plugins", "hivemind", ".claude-plugin", "plugin.json")
        return self

    def manifest_of(self, plugin):
        return self.manifest if plugin == "routing-dashboard" else self.hm_manifest

    def version(self, plugin="routing-dashboard"):
        return read_json(self.manifest_of(plugin))["version"]

    def bump_version(self, new, plugin="routing-dashboard"):
        path = self.manifest_of(plugin)
        manifest = read_json(path)
        manifest["version"] = new
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, indent=2) + "\n")

    def copy(self, rel, dest_rel, from_payload=None):
        src = os.path.join(from_payload or REPO, *rel.split("/"))
        dest = os.path.join(self.root, *dest_rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)

    def snapshot(self):
        state = {}
        for dirpath, _dirs, files in os.walk(self.root):
            for name in files:
                full = os.path.join(dirpath, name)
                with open(full, "rb") as fh:
                    state[os.path.relpath(full, self.root)] = (fh.read(), os.stat(full).st_mode)
        return state

    def __exit__(self, *exc):
        helpers.rmtree_force(self.base)
        return False


class CoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = load_module("install_for_coverage", os.path.join(REPO, "install.py"))

    def plan(self, folder, defaults):
        return {e.rel: (e.mode, e.data) for e in self.install.build_plan(folder, defaults)}

    def test_payload_holds_every_file_the_installer_reads(self):
        defaults = self.install.load_agent_defaults(REPO, self.install.list_agents(REPO))
        from_repo = self.plan(REPO, defaults)
        from_payload = self.plan(PAYLOAD, defaults)
        self.assertEqual(sorted(from_payload), sorted(from_repo))
        for rel in from_repo:
            self.assertEqual(from_payload[rel], from_repo[rel], rel)

    def test_every_server_import_resolves_inside_the_payload(self):
        stdlib = os.path.realpath(sysconfig.get_paths()["stdlib"])
        modules = []
        for folder in ("dashboard", ""):
            base = os.path.join(PAYLOAD, folder)
            modules += [os.path.join(base, f) for f in sorted(os.listdir(base)) if f.endswith(".py")]
        self.assertTrue(modules)
        missing = []
        for path in modules:
            tree = ast.parse(read_text(path), path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                else:
                    continue
                for dotted in names:
                    top = dotted.split(".")[0]
                    if not self.resolves(top, stdlib):
                        missing.append("%s imports %s" % (os.path.relpath(path, PAYLOAD), top))
        self.assertEqual(missing, [])

    @staticmethod
    def resolves(top, stdlib):
        if os.path.isfile(os.path.join(PAYLOAD, "dashboard", top + ".py")) \
                or os.path.isfile(os.path.join(PAYLOAD, top + ".py")):
            return True
        if top in sys.builtin_module_names:
            return True
        names = getattr(sys, "stdlib_module_names", None)
        if names is not None:
            return top in names
        spec = importlib.util.find_spec(top)
        origin = getattr(spec, "origin", None)
        if spec is None or origin is None:
            return False
        if origin in ("built-in", "frozen"):
            return True
        return os.path.realpath(origin).startswith(stdlib + os.sep) and "site-packages" not in origin


class ShapeTest(unittest.TestCase):
    def test_plugin_root_holds_only_what_the_design_lists(self):
        found = set(os.listdir(PLUGIN))
        required = {".claude-plugin", "bin", "hooks", "skills", "payload", "LICENSE"}
        allowed = required | {"README.md"}
        self.assertEqual(sorted(required - found), [])
        self.assertEqual(sorted(found - allowed), [])

    def test_no_component_folders_or_files_at_the_plugin_root(self):
        for name in ("agents", "commands", ".mcp.json", "monitors", "settings.json", "output-styles"):
            self.assertFalse(os.path.lexists(os.path.join(PLUGIN, name)), name)

    def test_plugin_json_declares_no_components(self):
        manifest = read_json(PLUGIN_JSON)
        for key in ("hooks", "agents", "skills", "commands", "mcpServers"):
            self.assertNotIn(key, manifest)

    def test_hooks_json_runs_the_launcher_at_session_end_and_guards_it_before_bash(self):
        hooks = read_json(HOOKS_JSON)
        self.assertEqual(list(hooks), ["hooks"])
        self.assertEqual(sorted(hooks["hooks"]), ["PreToolUse", "SessionEnd"])
        groups = hooks["hooks"]["SessionEnd"]
        self.assertEqual(len(groups), 1)
        self.assertNotIn("matcher", groups[0])
        self.assertEqual(len(groups[0]["hooks"]), 1)
        entry = groups[0]["hooks"][0]
        self.assertEqual(entry["type"], "command")
        self.assertEqual(entry["command"], "python3")
        self.assertEqual(entry["args"], ["${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard", "session-end"])
        self.assertEqual(sorted(entry), ["args", "command", "type"])
        groups = hooks["hooks"]["PreToolUse"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(groups[0]), ["hooks", "matcher"])
        self.assertEqual(groups[0]["matcher"], "Bash")
        self.assertEqual(groups[0]["hooks"], [GUARD_ENTRY])

    def test_the_guard_if_rule_is_the_launchers_guard_rule(self):
        launcher = load_script("launcher_for_build_test", LAUNCHER)
        self.assertEqual(read_json(HOOKS_JSON)["hooks"]["PreToolUse"][0]["hooks"][0]["if"], launcher.GUARD_RULE)
        self.assertEqual(launcher.GUARD_RULE, GUARD_RULE)

    def test_payload_has_no_clutter_and_stays_small(self):
        total = 0
        for rel in payload_files():
            parts = rel.split("/")
            self.assertNotIn("__pycache__", parts, rel)
            self.assertNotIn("experiments", parts, rel)
            self.assertNotEqual(parts[-1], ".DS_Store", rel)
            size = os.path.getsize(os.path.join(PAYLOAD, *parts))
            self.assertLessEqual(size, ONE_MB, rel)
            total += size
        self.assertLess(total, 3 * ONE_MB)

    def test_plugin_license_is_the_root_license(self):
        with open(os.path.join(REPO, "LICENSE"), "rb") as a, open(os.path.join(PLUGIN, "LICENSE"), "rb") as b:
            self.assertEqual(a.read(), b.read())


class NamesTest(unittest.TestCase):
    def test_names_and_source(self):
        market = read_json(MARKETPLACE)
        manifest = read_json(PLUGIN_JSON)
        self.assertEqual(market["name"], "model-routing")
        self.assertEqual(manifest["name"], "routing-dashboard")
        for name in (market["name"], manifest["name"]):
            self.assertRegex(name, NAME_RE)
            self.assertFalse(name.startswith(RESERVED_PREFIXES), name)
        hivemind = read_json(HM_PLUGIN_JSON)
        self.assertEqual(hivemind["name"], "hivemind")
        self.assertRegex(hivemind["name"], NAME_RE)
        self.assertFalse(hivemind["name"].startswith(RESERVED_PREFIXES))
        self.assertEqual(len(market["plugins"]), 2)
        entry, hm_entry = market["plugins"]
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["source"], "./plugins/routing-dashboard")
        self.assertEqual(hm_entry["name"], hivemind["name"])
        self.assertEqual(hm_entry["source"], "./plugins/hivemind")
        self.assertEqual(hm_entry["description"], hivemind["description"])
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(hivemind["version"], r"^\d+\.\d+\.\d+$")


def split_frontmatter(text):
    lines = text.split("\n")
    assert lines[0] == "---", "the skill must open with front matter"
    end = lines.index("---", 1)
    fields = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, "\n".join(lines[end + 1:])


class SkillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fields, cls.body = split_frontmatter(read_text(SKILL))

    def test_frontmatter_locks_the_skill_down(self):
        self.assertEqual(self.fields["name"], "dashboard")
        self.assertEqual(self.fields["disable-model-invocation"], "true")
        self.assertEqual(self.fields["model"], "haiku")
        # A disallowed-tools deny outlives the command into the next slash command and denies that
        # command's own ! line, so the PreToolUse guard hook does the denying instead.
        self.assertNotIn("disallowed-tools", self.fields)

    def test_the_guard_if_rule_is_a_bash_pattern_without_a_dollar(self):
        rule = self.guard_rule()
        self.assertEqual(rule, GUARD_RULE)
        self.assertIsNone(deny_rule_problem(rule))
        for bad in ("Bash", "Bash()", "Read", "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard*)"):
            self.assertIsNotNone(deny_rule_problem(bad), bad)

    @staticmethod
    def guard_rule():
        return read_json(HOOKS_JSON)["hooks"]["PreToolUse"][0]["hooks"][0]["if"]

    def rendered_line(self, arguments):
        command = self.bang_lines()[0][2:-1]
        for name, value in (("${CLAUDE_PLUGIN_ROOT}", "/work/cache/routing-dashboard/0.1.2"),
                            ("${CLAUDE_PLUGIN_DATA}", "/work/data/routing-dashboard"),
                            ("${CLAUDE_PROJECT_DIR}", "/work/proj"), ("${CLAUDE_SESSION_ID}", "abc-123"),
                            ("$ARGUMENTS", arguments)):
            command = command.replace(name, value)
        return command.strip()

    def test_guard_rule_covers_every_launcher_command_the_grant_allows(self):
        allow = bash_rule_regex(self.fields["allowed-tools"].replace(
            "${CLAUDE_PLUGIN_ROOT}", "/work/cache/routing-dashboard/0.1.2"))
        deny = bash_rule_regex(self.guard_rule())
        hint = self.fields["argument-hint"].strip('"')
        actions = [part.split()[0] for part in re.match(r"\[([^\]]+)\]", hint).group(1).split("|")]
        for arguments in [""] + actions + ["edits --key-file", "stop --all", 'project "/work/other dir"']:
            command = self.rendered_line(arguments)
            self.assertTrue(allow.fullmatch(command), command)
            self.assertTrue(deny.fullmatch(command), command)

    def test_guard_rule_leaves_other_commands_alone(self):
        deny = bash_rule_regex(self.guard_rule())
        for command in ("ls", "git status", "python3 -m unittest discover -s tests",
                        "python3 tools/build_plugins.py", "/usr/bin/python3 -B tests/test_plugin_launcher.py",
                        "cat /work/repo/plugins/routing-dashboard/bin/routing-dashboard",
                        "sed -n 1,80p plugins/routing-dashboard/bin/routing-dashboard"):
            self.assertIsNone(deny.fullmatch(command), command)

    def bang_lines(self):
        return [line for line in self.body.split("\n") if "!`" in line]

    def test_body_has_one_injection_line_with_every_placeholder(self):
        lines = self.bang_lines()
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertTrue(line.startswith("!`"))
        command = line[2:]
        self.assertTrue(command.endswith("`"))
        command = command[:-1]
        self.assertTrue(command.startswith(LAUNCHER_PATH_TEXT + " "), command)
        for piece in ('--data "${CLAUDE_PLUGIN_DATA}"', '--default-project "${CLAUDE_PROJECT_DIR}"',
                      '--session "${CLAUDE_SESSION_ID}"', "$ARGUMENTS"):
            self.assertIn(piece, command)

    def test_allowed_tools_is_exactly_the_launcher_rule_and_covers_the_line(self):
        rule = self.fields["allowed-tools"]
        self.assertEqual(rule, "Bash(%s *)" % LAUNCHER_PATH_TEXT)
        command = self.bang_lines()[0][2:-1]
        prefix = rule[len("Bash("):-len("*)")]
        self.assertTrue(command.startswith(prefix))

    def test_argument_hint_actions_appear_in_the_launcher(self):
        if not os.path.isfile(LAUNCHER):
            self.skipTest("plugins/routing-dashboard/bin/routing-dashboard does not exist yet")
        hint = self.fields["argument-hint"].strip('"')
        group = re.match(r"\[([^\]]+)\]", hint).group(1)
        actions = [part.split()[0] for part in group.split("|")]
        self.assertGreaterEqual(len(actions), 8)
        text = read_text(LAUNCHER)
        for action in actions:
            self.assertRegex(text, r"\b%s\b" % re.escape(action), action)


class HiveMindShapeTest(unittest.TestCase):
    def test_plugin_root_holds_exactly_what_the_design_lists(self):
        self.assertEqual(sorted(os.listdir(HM_PLUGIN)),
                         sorted([".claude-plugin", "bin", "hooks", "skills", "payload", "LICENSE", "README.md"]))

    def test_hooks_folder_holds_only_hooks_json(self):
        self.assertEqual(os.listdir(os.path.join(HM_PLUGIN, "hooks")), ["hooks.json"])

    def test_hooks_json_guards_the_wrapper_before_bash_and_nothing_else(self):
        hooks = read_json(HM_HOOKS_JSON)
        self.assertEqual(list(hooks), ["hooks"])
        self.assertEqual(list(hooks["hooks"]), ["PreToolUse"])
        groups = hooks["hooks"]["PreToolUse"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(groups[0]), ["hooks", "matcher"])
        self.assertEqual(groups[0]["matcher"], "Bash")
        self.assertEqual(groups[0]["hooks"], [HM_GUARD_ENTRY])

    def test_the_guard_if_rule_is_the_wrappers_guard_rule(self):
        wrapper = load_script("hivemind_wrapper_for_build_test", HM_WRAPPER)
        self.assertEqual(read_json(HM_HOOKS_JSON)["hooks"]["PreToolUse"][0]["hooks"][0]["if"], wrapper.GUARD_RULE)
        self.assertEqual(wrapper.GUARD_RULE, HM_GUARD_RULE)

    def test_no_component_folders_or_files_at_the_plugin_root(self):
        for name in ("agents", "commands", ".mcp.json", "monitors", "settings.json", "output-styles"):
            self.assertFalse(os.path.lexists(os.path.join(HM_PLUGIN, name)), name)

    def test_plugin_json_declares_no_components(self):
        manifest = read_json(HM_PLUGIN_JSON)
        for key in ("hooks", "agents", "skills", "commands", "mcpServers"):
            self.assertNotIn(key, manifest)
        for key in ("name", "version", "description", "author", "homepage", "repository", "license"):
            self.assertIn(key, manifest)
        dashboard = read_json(PLUGIN_JSON)
        for key in ("author", "homepage", "repository", "license"):
            self.assertEqual(manifest[key], dashboard[key], key)

    def test_payload_is_the_library_and_its_build_record(self):
        self.assertEqual(payload_files(HM_PAYLOAD), ["BUILD.json", "hooks/hivemind_lib.py"])
        record = read_json(os.path.join(HM_PAYLOAD, "BUILD.json"))
        self.assertEqual(record["plugin_version"], read_json(HM_PLUGIN_JSON)["version"])
        self.assertRegex(record["payload_sha256"], r"^[0-9a-f]{64}$")

    def test_both_payloads_carry_the_same_library_bytes(self):
        paths = [os.path.join(REPO, "hooks", "hivemind_lib.py"),
                 os.path.join(HM_PAYLOAD, "hooks", "hivemind_lib.py"),
                 os.path.join(PAYLOAD, "hooks", "hivemind_lib.py")]
        data = []
        for path in paths:
            with open(path, "rb") as fh:
                data.append(fh.read())
        self.assertEqual(data[0], data[1])
        self.assertEqual(data[0], data[2])

    def test_plugin_license_is_the_root_license(self):
        with open(os.path.join(REPO, "LICENSE"), "rb") as a, open(os.path.join(HM_PLUGIN, "LICENSE"), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_the_wrapper_is_executable_and_hand_written(self):
        self.assertTrue(os.access(HM_WRAPPER, os.X_OK))
        self.assertEqual(os.stat(HM_WRAPPER).st_mode & 0o777, 0o755)
        self.assertEqual(read_text(HM_WRAPPER).split("\n")[0], "#!/usr/bin/env python3")

    def test_readme_names_every_command(self):
        text = read_text(os.path.join(HM_PLUGIN, "README.md"))
        for action in HM_ACTIONS:
            self.assertIn("/hivemind:" + action, text)


def deny_rule_problem(rule):
    """Why a guard hook's `if` rule is unsafe, or None. It must be a Bash(...) pattern, never a bare tool name.
    ${CLAUDE_PLUGIN_ROOT} is not expanded in a disallowed-tools rule, and whether `if` expands it is unverified,
    so the rule keeps a wildcard and holds no $."""
    if not re.fullmatch(r"Bash\(.+\)", rule):
        return "not a Bash(...) pattern"
    if "$" in rule:
        return "holds a $ that is not expanded"
    return None


class HiveMindSkillTest(unittest.TestCase):
    SAMPLE_ARGS = {
        "status": [""], "check": [""], "inbox": [""], "init": [""], "consolidate": [""],
        "link": ["", "F-0001 abcdef1", "F-0001 abcdef1..1234567"],
        "related": ["src/a.py", "src/a.py docs/b.md", '"docs/my notes.md"'],
    }
    KEY_ORDER = ["name", "description", "argument-hint", "disable-model-invocation", "model", "allowed-tools"]

    @classmethod
    def setUpClass(cls):
        cls.skills = {}
        for name in sorted(os.listdir(HM_SKILLS)):
            text = read_text(os.path.join(HM_SKILLS, name, "SKILL.md"))
            fields, body = split_frontmatter(text)
            order = [line.partition(":")[0] for line in text.split("\n")[1:text.split("\n").index("---", 1)]]
            cls.skills[name] = {"fields": fields, "body": body, "order": order}

    @staticmethod
    def bang_lines(body):
        return [line for line in body.split("\n") if "!`" in line]

    def test_there_are_exactly_the_seven_skill_folders(self):
        self.assertEqual(sorted(os.listdir(HM_SKILLS)), sorted(HM_ACTIONS))
        for name in HM_ACTIONS:
            self.assertEqual(sorted(os.listdir(os.path.join(HM_SKILLS, name))), ["SKILL.md"])

    def test_every_wrapper_action_has_a_skill_and_the_reverse(self):
        loader = importlib.machinery.SourceFileLoader("hivemind_wrapper_for_skill_test", HM_WRAPPER)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        wrapper = importlib.util.module_from_spec(spec)
        loader.exec_module(wrapper)
        self.assertEqual(sorted(wrapper.USAGE), sorted(self.skills))
        self.assertEqual(sorted(wrapper.ORDER), sorted(self.skills))
        for name, skill in self.skills.items():
            self.assertTrue(wrapper.grammar_ok(name, ["x"] if name == "related" else []), name)
            self.assertEqual(skill["fields"]["name"], name)

    def test_front_matter_locks_each_skill_down(self):
        for name, skill in self.skills.items():
            with self.subTest(skill=name):
                fields = skill["fields"]
                self.assertEqual(fields["name"], name)
                self.assertTrue(fields["description"])
                self.assertEqual(fields["disable-model-invocation"], "true")
                # A disallowed-tools deny outlives the command into the next slash command, so no
                # skill carries one. The PreToolUse guard hook denies the wrapper instead.
                self.assertNotIn("disallowed-tools", fields)
                self.assertEqual(fields["allowed-tools"], "Bash(%s *)" % HM_WRAPPER_TEXT)
                if name == "consolidate":
                    self.assertNotIn("model", fields)
                else:
                    self.assertEqual(fields["model"], "haiku")
                expected = [key for key in self.KEY_ORDER if key in fields]
                self.assertEqual(skill["order"], expected)
                self.assertEqual("argument-hint" in fields, name in ("link", "related"))
        self.assertEqual(self.skills["link"]["fields"]["argument-hint"], '"[<id> <sha or base..head>]"')
        self.assertEqual(self.skills["related"]["fields"]["argument-hint"], '"<path>..."')

    @staticmethod
    def guard_rule():
        return read_json(HM_HOOKS_JSON)["hooks"]["PreToolUse"][0]["hooks"][0]["if"]

    def test_guard_rule_is_never_a_bare_tool_name_or_holds_a_dollar(self):
        rule = self.guard_rule()
        self.assertEqual(rule, HM_GUARD_RULE)
        self.assertIsNone(deny_rule_problem(rule))
        for bad in ("Bash", "Bash()", "Read", 'Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind"*)', "Bash(python3 $X*)"):
            self.assertIsNotNone(deny_rule_problem(bad), bad)

    def test_each_body_has_one_injection_line_with_every_placeholder(self):
        for name, skill in self.skills.items():
            with self.subTest(skill=name):
                lines = self.bang_lines(skill["body"])
                self.assertEqual(len(lines), 1)
                line = lines[0]
                self.assertTrue(line.startswith("!`") and line.endswith("`"), line)
                command = line[2:-1]
                self.assertTrue(command.startswith(HM_WRAPPER_TEXT + " "), command)
                self.assertEqual(command, '%s --project "${CLAUDE_PROJECT_DIR}" %s $ARGUMENTS' % (HM_WRAPPER_TEXT, name))

    def render(self, name, arguments):
        command = self.bang_lines(self.skills[name]["body"])[0][2:-1]
        for placeholder, value in (("${CLAUDE_PLUGIN_ROOT}", "/work/cache/hivemind/0.1.0"),
                                   ("${CLAUDE_PROJECT_DIR}", "/work/proj"), ("$ARGUMENTS", arguments)):
            command = command.replace(placeholder, value)
        return command.strip()

    def test_guard_rule_covers_every_wrapper_line_the_grant_allows(self):
        deny = bash_rule_regex(self.guard_rule())
        for name, skill in self.skills.items():
            allow = bash_rule_regex(skill["fields"]["allowed-tools"].replace(
                "${CLAUDE_PLUGIN_ROOT}", "/work/cache/hivemind/0.1.0"))
            for arguments in self.SAMPLE_ARGS[name]:
                command = self.render(name, arguments)
                self.assertTrue(allow.fullmatch(command), command)
                self.assertTrue(deny.fullmatch(command), command)

    def test_guard_rule_leaves_other_commands_alone(self):
        deny = bash_rule_regex(self.guard_rule())
        for command in ("ls", "git status", "python3 -m unittest discover -s tests",
                        "python3 tools/build_plugins.py",
                        'python3 "/work/cfg/hooks/hivemind_lib.py" prep /work/proj/.claude/hivemind',
                        "python3 /work/cfg/hooks/hivemind_lib.py check /work/proj/.claude/hivemind"):
            self.assertIsNone(deny.fullmatch(command), command)

    def test_the_guard_rule_does_not_touch_the_dashboard_launcher(self):
        self.assertIsNone(bash_rule_regex(self.guard_rule()).fullmatch(
            'python3 "/work/cache/routing-dashboard/0.1.3/bin/routing-dashboard" --data /work/d status'))
        self.assertIsNone(bash_rule_regex(read_json(HOOKS_JSON)["hooks"]["PreToolUse"][0]["hooks"][0]["if"]).fullmatch(
            'python3 "/work/cache/hivemind/0.1.0/bin/hivemind" --project /work/proj status'))

    def test_consolidate_hands_the_work_to_deep_reasoner_and_never_runs_apply(self):
        body = self.skills["consolidate"]["body"]
        self.assertIn("deep-reasoner", body)
        self.assertIn("history none", body)
        self.assertIn("Kind: hivemind-consolidation", body)
        self.assertIn("(2 hours)", body)
        self.assertIn("./install.sh", body)
        for line in body.split("\n"):
            if "apply" in line:
                # Only the brief for deep-reasoner and the closing guard rule may name apply.
                self.assertTrue(line.strip().startswith("Run CONSOLIDATION only") or line.startswith("Never run "),
                                line)
        self.assertTrue(body.rstrip().split("\n")[-1].startswith("Never run prep, apply, check or any HiveMind "
                                                                  "command yourself"))
        self.assertNotIn("python3", body.replace(self.bang_lines(body)[0], ""))

    def test_relay_bodies_forbid_running_commands(self):
        for name in ("status", "check", "link", "related", "init", "inbox"):
            body = self.skills[name]["body"]
            self.assertIn("Don't run any command.", body, name)
            self.assertIn("error:, warning: or note:", body, name)
        self.assertIn("This was a preview, and nothing was written.", self.skills["inbox"]["body"])
        for name in ("status", "check", "link", "related", "init"):
            self.assertIn("consolidate: exactly as written", self.skills[name]["body"])


if __name__ == "__main__":
    unittest.main()

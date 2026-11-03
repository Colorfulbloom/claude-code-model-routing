"""Checks of the routing-dashboard plugin package: the generated payload, the manifests, the hook and the skill.

tools/build_plugins.py copies the dashboard and installer files into plugins/routing-dashboard/payload/. These tests
prove the copy matches its sources (and that the drift check notices when it does not), that it holds everything the
installer and the server import, and that the plugin root has the shape the design calls for. Nothing here runs
`claude`, installs a plugin or reads the real ~/.claude. The copy tests work in a temp folder outside every git tree.
"""
import ast
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
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
ONE_MB = 1024 * 1024
LAUNCHER_PATH_TEXT = 'python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard"'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def payload_files():
    """Relative paths (forward slashes) of every file under the payload."""
    found = []
    for dirpath, _dirs, files in os.walk(PAYLOAD):
        for name in files:
            found.append(os.path.relpath(os.path.join(dirpath, name), PAYLOAD).replace(os.sep, "/"))
    return sorted(found)


def source_files():
    """payload_files() without BUILD.json, which the build writes and no source holds."""
    return [rel for rel in payload_files() if rel != "BUILD.json"]


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
        self.assertEqual([p["name"] for p in build.PLUGINS], ["routing-dashboard"])


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
        for rel in source_files():
            self.copy(rel, rel)
        self.payload = os.path.join(self.root, "plugins", "routing-dashboard", "payload")
        for rel in payload_files():
            self.copy(rel, "plugins/routing-dashboard/payload/" + rel, from_payload=True)
        shutil.copy2(os.path.join(PLUGIN, "LICENSE"), os.path.join(self.root, "plugins", "routing-dashboard", "LICENSE"))
        self.manifest = os.path.join(self.root, "plugins", "routing-dashboard", ".claude-plugin", "plugin.json")
        os.makedirs(os.path.dirname(self.manifest))
        shutil.copy2(PLUGIN_JSON, self.manifest)
        return self

    def version(self):
        return read_json(self.manifest)["version"]

    def bump_version(self, new):
        manifest = read_json(self.manifest)
        manifest["version"] = new
        with open(self.manifest, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, indent=2) + "\n")

    def copy(self, rel, dest_rel, from_payload=False):
        src = os.path.join(PAYLOAD if from_payload else REPO, *rel.split("/"))
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

    def test_hooks_json_runs_the_launcher_at_session_end_only(self):
        hooks = read_json(HOOKS_JSON)
        self.assertEqual(list(hooks), ["hooks"])
        self.assertEqual(list(hooks["hooks"]), ["SessionEnd"])
        groups = hooks["hooks"]["SessionEnd"]
        self.assertEqual(len(groups), 1)
        self.assertNotIn("matcher", groups[0])
        self.assertEqual(len(groups[0]["hooks"]), 1)
        entry = groups[0]["hooks"][0]
        self.assertEqual(entry["type"], "command")
        self.assertEqual(entry["command"], "python3")
        self.assertEqual(entry["args"], ["${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard", "session-end"])

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
        self.assertEqual(len(market["plugins"]), 1)
        entry = market["plugins"][0]
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["source"], "./plugins/routing-dashboard")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")


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
        self.assertEqual(self.fields["disallowed-tools"], "Bash")

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


if __name__ == "__main__":
    unittest.main()

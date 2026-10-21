"""Old installer (tests/fixtures/install_old.sh) vs the new one, scenario by scenario.

Each scenario function runs against one sandbox, so the test runs it twice (old
and new) in separate fresh sandboxes with identical setup, then compares exit
codes, normalized output and tree snapshots within the spec's allowances.
Set PARITY_NEW=old to run old against old (harness self-test).
"""
import json
import os
import unittest

from helpers import CFG, SELF_TEST, Sandbox, apply_allowances, master_src

REAL_NEW = not SELF_TEST


def agent_names():
    return sorted(f[:-3] for f in os.listdir(os.path.join(master_src(), "agents")) if f.endswith(".md"))


class ParityBase(unittest.TestCase):
    maxDiff = 2000

    def sandbox(self, kind):
        sb = Sandbox(kind)
        self.addCleanup(sb.cleanup)
        return sb

    def parity(self, scenario):
        old = scenario(self.sandbox("old"))
        new = scenario(self.sandbox("new"))
        self.assertEqual(len(old), len(new), "scenario produced different step counts")
        problems = []
        for i, (o, n) in enumerate(zip(old, new)):
            for p in apply_allowances(o, n):
                problems.append("step %d: %s" % (i, p))
        if problems:
            self.fail("\n" + "\n".join(problems))
        return old, new

    def assertSame(self, before, step, what="tree"):
        self.assertEqual(before, step.tree, "%s changed" % what)


def settings_path(sb):
    return os.path.join(sb.cfg, "settings.json")


class ParityTests(ParityBase):
    # 1
    def test_01_fresh_install(self):
        def scn(sb):
            st = sb.run([])
            self.assertEqual(st.code, 0, st.err)
            if sb.kind == "new" and REAL_NEW:
                self.assertIn("cfg/model-routing-choices.json", st.tree)
                self.assertEqual(st.tree["cfg/model-routing-choices.json"][2], 0o644)
            return [st]
        self.parity(scn)

    # 2
    def test_02_rerun_all_unchanged(self):
        def scn(sb):
            first = sb.run([])
            second = sb.run([])
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertIn(" 0 added, 0 replaced,", second.out)
            self.assertNotIn("backups", " ".join(k for k in second.tree if "backups/" in k))
            return [first, second]
        self.parity(scn)

    # 3
    def test_03_existing_settings_merge(self):
        other = {
            "model": "opus",
            "env": {"A": "1"},
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Agent", "hooks": [{"type": "command", "command": "echo other"}]},
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo bash"}]},
                ],
                "SessionStart": [{"matcher": "resume", "hooks": [{"type": "command", "command": "echo resume"}]}],
                "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "echo post"}]}],
            },
        }

        def scn(sb):
            sb.write(settings_path(sb), json.dumps(other, indent=2) + "\n")
            steps = [sb.run([]), sb.run([]), sb.run(["--uninstall"])]
            self.assertEqual([s.code for s in steps], [0, 0, 0])
            with open(settings_path(sb)) as fh:
                data = json.load(fh)
            self.assertEqual(data["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "echo other")
            return steps
        self.parity(scn)

    # 4a
    def test_04a_settings_symlink(self):
        def scn(sb):
            sb.write(sb.p("dotfiles", "settings.json"), '{"theme": "dark"}\n', 0o640)
            os.makedirs(sb.cfg)
            os.symlink(sb.p("dotfiles", "settings.json"), settings_path(sb))
            steps = [sb.run([]), sb.run(["--uninstall"])]
            self.assertEqual([s.code for s in steps], [0, 0])
            self.assertTrue(os.path.islink(settings_path(sb)))
            return steps
        self.parity(scn)

    # 4b
    def test_04b_settings_dangling_symlink(self):
        def scn(sb):
            os.makedirs(sb.cfg)
            os.symlink(sb.p("nowhere.json"), settings_path(sb))
            before = sb.tree()
            st = sb.run([])
            self.assertEqual(st.code, 1)
            self.assertSame(before, st)
            return [st]
        self.parity(scn)

    def _bad_settings(self, content):
        def scn(sb):
            sb.write(settings_path(sb), content)
            before = sb.tree()
            st = sb.run([])
            self.assertEqual(st.code, 1)
            self.assertSame(before, st)
            return [st]
        self.parity(scn)

    # 5a-d
    def test_05a_invalid_json(self):
        self._bad_settings("{not json")

    def test_05b_json_array(self):
        self._bad_settings("[1, 2]\n")

    def test_05c_hooks_not_object(self):
        self._bad_settings('{"hooks": []}\n')

    def test_05d_pretooluse_not_list(self):
        self._bad_settings('{"hooks": {"PreToolUse": {"a": 1}}}\n')

    # 6
    def test_06_installed_file_edited_then_rerun(self):
        def scn(sb):
            first = sb.run([])
            target = os.path.join(sb.cfg, "agents", agent_names()[0] + ".md")
            with open(target, "a") as fh:
                fh.write("local edit\n")
            second = sb.run([])
            third = sb.run([])
            self.assertEqual((first.code, second.code, third.code), (0, 0, 0))
            self.assertIn("replace", second.out)
            return [first, second, third]
        self.parity(scn)

    # 7
    def test_07_same_name_agents(self):
        names = agent_names()
        self.assertTrue({"scout", "judge", "verifier"} <= set(names))

        def scn(sb):
            ag = os.path.join(sb.cfg, "agents")
            sb.write(os.path.join(ag, "mine.md"), "---\nname: scout\ndescription: x\n---\nbody\n")
            sb.write(os.path.join(ag, "sub", "x.md"), '---\nname: "judge"\n---\nbody\n')
            sb.write(sb.p("elsewhere", "real.md"), "---\nname: 'verifier'\n---\nbody\n")
            os.symlink(sb.p("elsewhere", "real.md"), os.path.join(ag, "link.md"))
            sb.write(os.path.join(ag, "bodyonly.md"), "---\nname: other\n---\nname: scout\nmentions name: judge\n")
            sb.write(os.path.join(ag, "nofm.md"), "name: scout\n")
            first = sb.run([])
            second = sb.run([])
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertEqual(first.out.count("also declares name:"), 3)
            self.assertNotIn("bodyonly.md", first.out)
            self.assertNotIn("nofm.md", first.out)
            return [first, second]
        self.parity(scn)

    # 8a
    def test_08a_dry_run_fresh(self):
        def scn(sb):
            before = sb.tree()
            st = sb.run(["--dry-run"])
            self.assertEqual(st.code, 0)
            self.assertSame(before, st)
            return [st]
        self.parity(scn)

    # 8b
    def test_08b_dry_run_after_edit(self):
        def scn(sb):
            first = sb.run([])
            with open(os.path.join(sb.cfg, "rules", "model-routing.md"), "a") as fh:
                fh.write("edit\n")
            before = sb.tree()
            st = sb.run(["--dry-run"])
            self.assertEqual((first.code, st.code), (0, 0))
            self.assertIn("replace", st.out)
            self.assertSame(before, st)
            return [first, st]
        self.parity(scn)

    # 9a
    def test_09a_uninstall_after_install(self):
        def scn(sb):
            first = sb.run([])
            second = sb.run(["--uninstall"])
            self.assertEqual((first.code, second.code), (0, 0))
            if sb.kind == "new" and REAL_NEW:
                self.assertNotIn("cfg/model-routing-choices.json", second.tree)
                self.assertIn("model-routing-choices.json", second.out)
            return [first, second]
        self.parity(scn)

    # 9b
    def test_09b_uninstall_with_edited_file(self):
        def scn(sb):
            first = sb.run([])
            with open(os.path.join(sb.cfg, "agents", agent_names()[0] + ".md"), "a") as fh:
                fh.write("local edit\n")
            second = sb.run(["--uninstall"])
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertIn("edited", second.out)
            return [first, second]
        self.parity(scn)

    # 9c
    def test_09c_uninstall_with_deleted_file(self):
        def scn(sb):
            first = sb.run([])
            os.unlink(os.path.join(sb.cfg, "rules", "claude-in-chrome.md"))
            second = sb.run(["--uninstall"])
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertIn("already gone", second.out)
            return [first, second]
        self.parity(scn)

    # 9d
    def test_09d_uninstall_without_manifest(self):
        def scn(sb):
            first = sb.run([])
            os.unlink(os.path.join(sb.cfg, "model-routing-manifest.txt"))
            second = sb.run(["--uninstall"])
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertIn("No manifest at", second.out)
            return [first, second]
        self.parity(scn)

    # 9e
    def _unsafe_manifest(self, line_for):
        def scn(sb):
            first = sb.run([])
            sb.write(sb.p("evil"), "keep me\n")
            with open(os.path.join(sb.cfg, "model-routing-manifest.txt"), "a") as fh:
                fh.write(line_for(sb) + "\n")
            before = sb.tree()
            second = sb.run(["--uninstall"])
            self.assertEqual((first.code, second.code), (0, 1))
            self.assertSame(before, second)
            return [first, second]
        self.parity(scn)

    def test_09e_uninstall_unsafe_manifest(self):
        self._unsafe_manifest(lambda sb: "../evil")

    def test_09e2_uninstall_absolute_manifest_path(self):
        self._unsafe_manifest(lambda sb: sb.p("evil"))

    def test_09e3_uninstall_dotdot_in_middle(self):
        self._unsafe_manifest(lambda sb: "a/../../evil")

    # 9f
    def test_09f_manifest_line_with_trailing_space_is_missing(self):
        def scn(sb):
            first = sb.run([])
            mpath = os.path.join(sb.cfg, "model-routing-manifest.txt")
            with open(mpath) as fh:
                lines = fh.read().split("\n")
            self.assertIn("agents/scout.md", lines)
            lines[lines.index("agents/scout.md")] = "agents/scout.md "
            with open(mpath, "w") as fh:
                fh.write("\n".join(lines))
            second = sb.run(["--uninstall"])
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertIn("already gone", second.out)
            self.assertTrue(os.path.exists(os.path.join(sb.cfg, "agents", "scout.md")))
            return [first, second]
        self.parity(scn)

    # 9g
    def test_09g_uninstall_dry_run_changes_nothing(self):
        def scn(sb):
            first = sb.run([])
            before = sb.tree()
            second = sb.run(["--uninstall", "--dry-run"])
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertSame(before, second)
            self.assertFalse(os.path.exists(os.path.join(sb.cfg, "backups")))
            return [first, second]
        self.parity(scn)

    # 9h
    def _duplicate_hook(self, event):
        def scn(sb):
            first = sb.run([])
            with open(settings_path(sb)) as fh:
                data = json.load(fh)
            ours = [g for g in data["hooks"][event] if g.get("matcher") in ("Agent", "startup")]
            self.assertEqual(len(ours), 1)
            data["hooks"][event].append(json.loads(json.dumps(ours[0])))
            sb.write(settings_path(sb), json.dumps(data, indent=2) + "\n")
            second = sb.run([])
            third = sb.run(["--uninstall"])
            self.assertEqual((first.code, second.code, third.code), (0, 0, 0))
            self.assertIn("skip", second.out)
            with open(settings_path(sb)) as fh:
                self.assertNotIn(event, json.load(fh).get("hooks", {}))
            return [first, second, third]
        self.parity(scn)

    def test_09h_duplicate_pretooluse_hook(self):
        self._duplicate_hook("PreToolUse")

    def test_09i_duplicate_sessionstart_hook(self):
        self._duplicate_hook("SessionStart")

    # 10a
    def test_10a_config_dir_with_dollar(self):
        def scn(sb):
            cfg = sb.p("cfg$x")
            st = sb.run([], config_dir=cfg)
            self.assertEqual(st.code, 1)
            self.assertFalse(os.path.exists(cfg))
            return [st]
        self.parity(scn)

    # 10b
    def test_10b_target_is_regular_file(self):
        def scn(sb):
            sb.write(sb.cfg, "i am a file\n")
            before = sb.tree()
            st = sb.run([])
            self.assertEqual(st.code, 1)
            self.assertSame(before, st)
            return [st]
        self.parity(scn)

    # 10c
    def test_10c_target_read_only(self):
        def scn(sb):
            os.makedirs(sb.cfg)
            os.chmod(sb.cfg, 0o555)
            self.addCleanup(os.chmod, sb.cfg, 0o755)
            before = sb.tree()
            st = sb.run([])
            self.assertEqual(st.code, 1)
            self.assertSame(before, st)
            return [st]
        self.parity(scn)

    # 11a
    def test_11a_relative_config_dir(self):
        def scn(sb):
            work = sb.p("work")
            os.makedirs(work)
            first = sb.run([], config_dir="rel/cfg", cwd=work)
            second = sb.run([], config_dir="rel/cfg", cwd=work)
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertTrue(os.path.isdir(sb.p("work", "rel", "cfg", "agents")))
            return [first, second]
        self.parity(scn)

    # 11b
    def test_11b_trailing_slashes(self):
        def scn(sb):
            st = sb.run([], config_dir=sb.cfg + "///")
            self.assertEqual(st.code, 0)
            self.assertIn("Target: <ROOT>/cfg\n", st.out)
            return [st]
        self.parity(scn)

    # 11c
    def test_11c_config_dir_unset(self):
        def scn(sb):
            first = sb.run([], config_dir=None)
            second = sb.run(["--uninstall"], config_dir=None)
            self.assertEqual((first.code, second.code), (0, 0))
            return [first, second]
        self.parity(scn)

    def test_11c_unset_uses_literal_home_prefix(self):
        for kind in ("old", "new"):
            sb = self.sandbox(kind)
            st = sb.run([], config_dir=None)
            self.assertEqual(st.code, 0, st.err)
            with open(os.path.join(sb.home, ".claude", "settings.json")) as fh:
                text = fh.read()
            self.assertIn('python3 \\"$HOME/.claude/hooks/require-agent-model.py\\"', text)
            self.assertIn('bash \\"$HOME/.claude/hooks/check-agent-models.sh\\"', text)
            if kind == "new" and REAL_NEW:
                for tail in ('hooks/hivemind-inject.py', 'hooks/hivemind-capture.py', 'hooks/hivemind-guard.py'):
                    self.assertIn('python3 \\"$HOME/.claude/%s\\"' % tail, text)
                self.assertIn('python3 \\"$HOME/.claude/hooks/hivemind_lib.py\\" status', text)
            self.assertNotIn(sb.home, text)

    # 12a
    def test_12a_unknown_flag(self):
        def scn(sb):
            before = sb.tree()
            st = sb.run(["--bogus"])
            self.assertEqual(st.code, 2)
            self.assertIn("Unknown option: --bogus", st.err)
            self.assertSame(before, st)
            return [st]
        self.parity(scn)

    # 12b
    def test_12b_help(self):
        def scn(sb):
            st = sb.run(["--help"])
            self.assertEqual(st.code, 0)
            self.assertTrue(st.out.startswith("Usage: install.sh"))
            st2 = sb.run(["-h"])
            self.assertEqual(st2.code, 0)
            return [st, st2]
        self.parity(scn)

    # 12c
    def test_12c_flag_order(self):
        def scn(sb):
            a = sb.run(["--bogus", "--help"])
            b = sb.run(["--help", "--bogus"])
            self.assertEqual((a.code, b.code), (2, 0))
            return [a, b]
        self.parity(scn)

    # 12d
    def test_12d_claude_missing(self):
        def scn(sb):
            before = sb.tree()
            missing = sb.run([], claude=False)
            self.assertEqual(missing.code, 1)
            self.assertIn("claude is not on PATH", missing.err)
            self.assertSame(before, missing)
            installed = sb.run([])
            uninstall = sb.run(["--uninstall"], claude=False)
            self.assertEqual((installed.code, uninstall.code), (0, 0))
            self.assertNotIn("claude 2.1", uninstall.out)
            return [missing, installed, uninstall]
        self.parity(scn)

    # 13
    def test_13_non_ascii_settings_mode_600(self):
        raw = '{\n  "note": "caf\u00e9 \u00f1 \u65e5\u672c",\n  "x": 1\n}\n'

        def scn(sb):
            sb.write(settings_path(sb), raw, 0o600)
            first = sb.run([])
            second = sb.run(["--uninstall"])
            self.assertEqual((first.code, second.code), (0, 0))
            self.assertEqual(os.stat(settings_path(sb)).st_mode & 0o7777, 0o600)
            with open(settings_path(sb), encoding="utf-8") as fh:
                self.assertIn("caf\u00e9 \u00f1 \u65e5\u672c", fh.read())
            return [first, second]
        self.parity(scn)


class HarnessSelfTests(ParityBase):
    """The harness must still fail on anything the allowances do not name: Allowance 4 drops
    the four HiveMind hook files and entries and nothing else."""

    def baseline(self):
        old = self.sandbox("old").run([])
        new = self.sandbox("new").run([])
        self.assertEqual((old.code, new.code), (0, 0), old.err + new.err)
        self.assertEqual(apply_allowances(old, new), [], "baseline is not clean")
        return old, new

    def new_settings(self, new):
        key = "cfg/settings.json"
        return key, json.loads(new.tree[key][3].decode("utf-8"))

    def with_settings(self, new, data):
        key = "cfg/settings.json"
        tree = dict(new.tree)
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        tree[key] = tree[key][:3] + (text.encode("utf-8"),)
        return new._replace(tree=tree)

    def assertFails(self, old, new, needle):
        problems = apply_allowances(old, new)
        self.assertTrue(problems, "harness accepted a difference it should reject: " + needle)
        self.assertIn(needle, "\n".join(problems))

    def test_self_01_extra_unrelated_hook_file(self):
        old, new = self.baseline()
        tree = dict(new.tree)
        tree["cfg/hooks/extra-hook.py"] = ("file", None, 0o755, b"print(1)\n")
        self.assertFails(old, new._replace(tree=tree), "extra-hook.py")

    def test_self_02_hivemind_name_outside_hooks_dir(self):
        old, new = self.baseline()
        tree = dict(new.tree)
        tree["cfg/hivemind-guard.py"] = ("file", None, 0o755, b"x\n")
        tree["cfg/hooks/hivemind-other.py"] = ("file", None, 0o755, b"x\n")
        problems = apply_allowances(old, new._replace(tree=tree))
        self.assertTrue(any("cfg/hivemind-guard.py" in p for p in problems), problems)
        self.assertTrue(any("hivemind-other.py" in p for p in problems), problems)

    def test_self_03_extra_unrelated_settings_entry(self):
        old, new = self.baseline()
        for event in ("SubagentStart", "PreToolUse", "SessionStart", "Stop"):
            with self.subTest(event=event):
                _, data = self.new_settings(new)
                data["hooks"].setdefault(event, []).append(
                    {"matcher": "x", "hooks": [{"type": "command", "command": "echo foreign"}]})
                self.assertFails(old, self.with_settings(new, data), "settings.json")

    @unittest.skipIf(SELF_TEST, "old installer writes no HiveMind entries")
    def test_self_04_new_entry_with_wrong_command_or_matcher(self):
        old, new = self.baseline()
        _, data = self.new_settings(new)
        data["hooks"]["SubagentStart"][0]["hooks"][0]["command"] = 'python3 "/elsewhere/other.py"'
        self.assertFails(old, self.with_settings(new, data), "settings.json")
        _, data = self.new_settings(new)
        for g in data["hooks"]["SessionStart"]:
            if g["matcher"] == "":
                g["matcher"] = "startup"
        self.assertFails(old, self.with_settings(new, data), "settings.json")

    def test_self_05_extra_stdout_and_manifest_lines(self):
        old, new = self.baseline()
        self.assertFails(old, new._replace(out=new.out + "  add        SubagentStart hook, matcher Other\n"),
                         "stdout")
        self.assertFails(old, new._replace(out=new.out + "  add        hooks/extra-hook.py\n"), "stdout")
        twice = "  skip       SubagentStop hook, matcher * (already there)\n"
        self.assertFails(old, new._replace(out=new.out + twice + twice), "stdout")
        key = "cfg/model-routing-manifest.txt"
        tree = dict(new.tree)
        tree[key] = tree[key][:3] + (tree[key][3] + b"hooks/extra-hook.py\n",)
        self.assertFails(old, new._replace(tree=tree), "manifest")

    def test_self_06_invalid_new_settings_is_a_problem(self):
        old, new = self.baseline()
        tree = dict(new.tree)
        key = "cfg/settings.json"
        tree[key] = tree[key][:3] + (b"{not json",)
        self.assertFails(old, new._replace(tree=tree), "not valid JSON")


if __name__ == "__main__":
    unittest.main()

"""The startup hook keeps its old output and then prints one roster line."""
import os
import re
import unittest

from helpers import Sandbox

ROSTER_PREFIX = "Model routing agents (model/effort): "


def agent(name, model=None, effort=None, model_raw=None, effort_raw=None):
    lines = ["---", "name: %s" % name, "description: test agent"]
    if model_raw is not None:
        lines.append("model: %s" % model_raw)
    elif model is not None:
        lines.append("model: %s" % model)
    if effort_raw is not None:
        lines.append("effort: %s" % effort_raw)
    elif effort is not None:
        lines.append("effort: %s" % effort)
    lines += ["---", "body", ""]
    return "\n".join(lines)


def field(path, key):
    """Mirror of the hook's field(): frontmatter value, trimmed, one quote pair removed."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    for line in lines[1:]:
        if line == "---":
            break
        m = re.match(r"^%s:\s*(.*?)\s*$" % key, line)
        if m:
            v = m.group(1)
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            return v
    return ""


def entries(dirpath):
    out = []
    for f in sorted(os.listdir(dirpath)):
        if f.endswith(".md"):
            p = os.path.join(dirpath, f)
            out.append("%s=%s/%s" % (f[:-3], field(p, "model") or "none", field(p, "effort") or "none"))
    return out


def expected_roster(user_dir, proj_dir):
    parts, seen = [], set()
    for label, d in (("user:", user_dir), ("project:", proj_dir)):
        if d in seen or not os.path.isdir(d):
            continue
        seen.add(d)
        e = entries(d)
        if e:
            parts.append(label)
            parts.extend(e)
    return (ROSTER_PREFIX + " ".join(parts) + "\n") if parts else ""


class HookRosterTests(unittest.TestCase):
    def sandbox(self):
        sb = Sandbox("new")
        self.addCleanup(sb.cleanup)
        return sb

    def populate_user(self, d):
        files = {
            "deep-reasoner.md": agent("deep-reasoner", "opus", "high"),
            "fast-worker.md": agent("fast-worker", "sonnet"),
            "quoted.md": agent("quoted", model_raw='"sonnet"', effort_raw="'medium'"),
            "inheriting.md": agent("inheriting", "inherit", "low"),
            "bare.md": agent("bare"),
            "notes.txt": "not an agent\n",
        }
        for n, c in files.items():
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, n), "w") as fh:
                fh.write(c)

    def populate_project(self, d):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "tech-writer.md"), "w") as fh:
            fh.write(agent("tech-writer", "sonnet", "medium"))
        with open(os.path.join(d, "unpinned.md"), "w") as fh:
            fh.write(agent("unpinned", "haiku"))

    def check(self, sb, user_dir, proj_dir):
        proj_agents = os.path.join(proj_dir, ".claude", "agents")
        user_agents = os.path.join(user_dir, "agents")
        oc, oo, oe = sb.run_hook("old", user_dir, proj_dir)
        nc, no, ne = sb.run_hook("new", user_dir, proj_dir)
        self.assertEqual((oc, nc), (0, 0))
        self.assertEqual(oe, ne)
        want = expected_roster(user_agents, proj_agents)
        self.assertEqual(no, oo + want)
        return oo, no

    def test_both_dirs(self):
        sb = self.sandbox()
        self.populate_user(os.path.join(sb.cfg, "agents"))
        self.populate_project(os.path.join(sb.p("proj"), ".claude", "agents"))
        old, new = self.check(sb, sb.cfg, sb.p("proj"))
        self.assertIn("user: bare=none/none deep-reasoner=opus/high fast-worker=sonnet/none "
                      "inheriting=inherit/low quoted=sonnet/medium project: "
                      "tech-writer=sonnet/medium unpinned=haiku/none\n", new)

    def test_only_user(self):
        sb = self.sandbox()
        self.populate_user(os.path.join(sb.cfg, "agents"))
        os.makedirs(sb.p("proj"))
        old, new = self.check(sb, sb.cfg, sb.p("proj"))
        self.assertIn(ROSTER_PREFIX + "user: bare=none/none", new)
        self.assertNotIn("project:", new)

    def test_only_project(self):
        sb = self.sandbox()
        self.populate_project(os.path.join(sb.p("proj"), ".claude", "agents"))
        os.makedirs(sb.cfg)
        old, new = self.check(sb, sb.cfg, sb.p("proj"))
        self.assertIn(ROSTER_PREFIX + "project: tech-writer=sonnet/medium unpinned=haiku/none\n", new)

    def test_project_dir_same_as_user_dir(self):
        sb = self.sandbox()
        proj = sb.p("proj")
        user_dir = os.path.join(proj, ".claude")
        self.populate_user(os.path.join(user_dir, "agents"))
        old, new = self.check(sb, user_dir, proj)
        roster = [l for l in new.splitlines() if l.startswith(ROSTER_PREFIX)]
        self.assertEqual(len(roster), 1)
        self.assertEqual(roster[0].count("deep-reasoner="), 1)

    def test_no_agents_prints_no_roster_line(self):
        sb = self.sandbox()
        os.makedirs(sb.cfg)
        os.makedirs(sb.p("proj"))
        old, new = self.check(sb, sb.cfg, sb.p("proj"))
        self.assertNotIn("Model routing agents", new)
        self.assertEqual(old, new)

    def test_empty_agent_dirs_print_no_roster_line(self):
        sb = self.sandbox()
        os.makedirs(os.path.join(sb.cfg, "agents"))
        os.makedirs(os.path.join(sb.p("proj"), ".claude", "agents"))
        old, new = self.check(sb, sb.cfg, sb.p("proj"))
        self.assertNotIn("Model routing agents", new)


if __name__ == "__main__":
    unittest.main()

"""Shared sandbox code for the installer and hook tests.

Every run uses throwaway HOME and CLAUDE_CONFIG_DIR directories inside a temp
root. The code refuses to run when a path it builds is outside that root or is
the invoking user's real Claude config directory.
"""
import atexit
import collections
import difflib
import os
import pwd
import re
import shutil
import stat
import subprocess
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "tests", "fixtures")

STAMP_RE = re.compile(r"model-routing(-uninstall)?-\d{8}-\d{6}(-\d+)?")
SELF_TEST = os.environ.get("PARITY_NEW") == "old"
CFG = object()  # sentinel: use the sandbox's default throwaway config dir
# Relative paths. home/Library is where the macOS python3 shim caches under a sandboxed HOME.
EXCLUDE_FROM_TREE = ("src", "bin", "bin_noclaude", "tmp", "home/Library")
CHOICES = "model-routing-choices.json"
MANIFEST = "model-routing-manifest.txt"

Step = collections.namedtuple("Step", "code out err tree")


class SandboxError(Exception):
    pass


def _tmp_base():
    base = os.environ.get("MR_TEST_TMP") or None
    if base:
        os.makedirs(base, exist_ok=True)
    return base


def rmtree_force(path):
    for dirpath, dirnames, _ in os.walk(path):
        for d in dirnames:
            full = os.path.join(dirpath, d)
            try:
                if not os.path.islink(full):
                    os.chmod(full, 0o755)
            except OSError:
                pass
    try:
        os.chmod(path, 0o755)
    except OSError:
        pass
    shutil.rmtree(path, ignore_errors=True)


def _real_claude_dirs():
    dirs = set()
    homes = [pwd.getpwuid(os.getuid()).pw_dir, os.path.expanduser("~")]
    for h in homes:
        dirs.add(os.path.realpath(os.path.join(h, ".claude")))
    return dirs


def _inside(path, parent):
    path = os.path.realpath(path)
    parent = os.path.realpath(parent)
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def check_safe(path, root):
    """Raise unless path is inside root and is not (or inside) the real ~/.claude."""
    if not _inside(path, root):
        raise SandboxError("refusing to run: %s is outside the temp root %s" % (path, root))
    for real in _real_claude_dirs():
        if _inside(path, real) or _inside(root, real):
            raise SandboxError("refusing to run: %s is inside the real Claude config dir %s" % (path, real))


def snapshot_source(root, repo=REPO):
    """Copy the repo content the installers read into <root>/src."""
    src = os.path.join(root, "src")
    os.makedirs(src)
    ignore = shutil.ignore_patterns("__pycache__")
    for d in ("agents", "rules", "hooks", "skills", "docs"):
        s = os.path.join(repo, d)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(src, d), symlinks=True, ignore=ignore)
    for f in ("install.py", "install.sh"):
        s = os.path.join(repo, f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(src, f))
    shutil.copy2(os.path.join(FIXTURES, "install_old.sh"), os.path.join(src, "install_old.sh"))
    shutil.copy2(os.path.join(FIXTURES, "check-agent-models_old.sh"),
                 os.path.join(src, "check-agent-models_old.sh"))
    return src


_master = {}


def master_src():
    """One snapshot per test process, so old and new always see the same content."""
    if "src" not in _master:
        root = os.path.realpath(tempfile.mkdtemp(prefix="mr-master-", dir=_tmp_base()))
        atexit.register(rmtree_force, root)
        _master["src"] = snapshot_source(root)
    return _master["src"]


def normalize_stamps(text):
    return STAMP_RE.sub(lambda m: "model-routing%s-STAMP" % (m.group(1) or ""), text)


def normalize_output(text, root, aliases=()):
    for a in sorted(set((root,) + tuple(aliases)), key=len, reverse=True):
        text = text.replace(a, "<ROOT>")
    return normalize_stamps(text)


def tree_snapshot(directory, root=None, aliases=(), exclude=()):
    """Map normalized relative path -> (kind, link target, mode, bytes)."""
    names_to_replace = sorted(set(((root,) if root else ()) + tuple(aliases)), key=len, reverse=True)
    snap = {}

    def add(key, entry):
        key = normalize_stamps(key)
        base, n = key, 1
        while key in snap:
            n += 1
            key = "%s#%d" % (base, n)
        snap[key] = entry

    for dirpath, dirnames, filenames in os.walk(directory):
        rel_dir = os.path.relpath(dirpath, directory)
        keep = lambda n: os.path.normpath(os.path.join(rel_dir, n)) not in exclude  # noqa: E731
        dirnames[:] = [d for d in dirnames if keep(d)]
        filenames = [f for f in filenames if keep(f)]
        dirnames.sort()
        for name in sorted(dirnames + list(filenames)):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, directory)
            st = os.lstat(full)
            mode = st.st_mode & 0o7777
            if stat.S_ISLNK(st.st_mode):
                target = os.readlink(full)
                for a in names_to_replace:
                    target = target.replace(a, "<ROOT>")
                add(rel, ("symlink", target, mode, None))
            elif stat.S_ISDIR(st.st_mode):
                add(rel, ("dir", None, mode, None))
            else:
                with open(full, "rb") as fh:
                    data = fh.read()
                for a in names_to_replace:
                    data = data.replace(a.encode(), b"<ROOT>")
                add(rel, ("file", None, mode, data))
    return snap


class Sandbox:
    def __init__(self, kind):
        if kind not in ("old", "new"):
            raise ValueError(kind)
        self.kind = kind
        raw = tempfile.mkdtemp(prefix="mr-test-", dir=_tmp_base())
        self.root = os.path.realpath(raw)
        self.aliases = (raw,) if raw != self.root else ()
        self.home = os.path.join(self.root, "home")
        self.cfg = os.path.join(self.root, "cfg")
        self.bin = os.path.join(self.root, "bin")
        self.bin_noclaude = os.path.join(self.root, "bin_noclaude")
        self.src = os.path.join(self.root, "src")
        for d in (self.home, self.bin, self.bin_noclaude, os.path.join(self.root, "tmp")):
            os.makedirs(d)
        stub = os.path.join(self.bin, "claude")
        with open(stub, "w") as fh:
            fh.write("#!/bin/sh\necho '2.1.302 (Claude Code)'\n")
        os.chmod(stub, 0o755)
        shutil.copytree(master_src(), self.src, symlinks=True)
        self.check_safe(self.home)

    def cleanup(self):
        rmtree_force(self.root)

    # -- paths and files
    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def write(self, path, data, mode=None):
        if not os.path.isabs(path):
            path = self.p(path)
        self.check_safe(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if isinstance(data, str):
            data = data.encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(data)
        if mode is not None:
            os.chmod(path, mode)
        return path

    def check_safe(self, path):
        check_safe(path, self.root)

    def tree(self):
        return tree_snapshot(self.root, self.root, self.aliases, EXCLUDE_FROM_TREE)

    def normalize(self, text):
        return normalize_output(text, self.root, self.aliases)

    # -- running
    def script_for(self, cmd_kind):
        if cmd_kind == "old" or (cmd_kind == "new" and SELF_TEST):
            return os.path.join(self.src, "install_old.sh")
        return os.path.join(self.src, "install.sh")

    def run(self, args=(), config_dir=CFG, env_extra=None, cwd=None, stdin=subprocess.DEVNULL, claude=True):
        if config_dir is CFG:
            config_dir = self.cfg
        proc = run(self.kind, list(args), self.home, config_dir, env_extra, stdin,
                   sandbox=self, cwd=cwd, claude=claude)
        return Step(proc.returncode,
                    self.normalize(proc.stdout.decode("utf-8", "replace")),
                    self.normalize(proc.stderr.decode("utf-8", "replace")),
                    self.tree())

    def run_hook(self, cmd_kind, config_dir, project_dir):
        """Run the old or new check-agent-models.sh; returns normalized stdout, code."""
        script = (os.path.join(self.src, "check-agent-models_old.sh") if cmd_kind == "old"
                  else os.path.join(self.src, "hooks", "check-agent-models.sh"))
        env = self.base_env(True)
        env["CLAUDE_CONFIG_DIR"] = config_dir
        env["CLAUDE_PROJECT_DIR"] = project_dir
        cwd = self.p("hookcwd")
        os.makedirs(cwd, exist_ok=True)
        self.check_env(env, cwd)
        proc = subprocess.run(["bash", script], env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        return proc.returncode, self.normalize(proc.stdout.decode("utf-8", "replace")), \
            self.normalize(proc.stderr.decode("utf-8", "replace"))

    def base_env(self, claude):
        return {
            "HOME": self.home,
            "PATH": "%s:/usr/bin:/bin" % (self.bin if claude else self.bin_noclaude),
            "LANG": "C",
            "LC_ALL": "C",
            "TMPDIR": os.path.join(self.root, "tmp"),
        }

    def check_env(self, env, cwd):
        self.check_safe(cwd)
        self.check_safe(env["HOME"])
        for var in ("CLAUDE_CONFIG_DIR", "CLAUDE_PROJECT_DIR"):
            if var in env:
                val = env[var]
                full = val if os.path.isabs(val) else os.path.join(cwd, val)
                self.check_safe(full)
        if "CLAUDE_CONFIG_DIR" not in env:
            self.check_safe(os.path.join(env["HOME"], ".claude"))


def run(cmd_kind, args, home, config_dir, env_extra=None, stdin=subprocess.DEVNULL,
        sandbox=None, cwd=None, claude=True):
    """Run the old or new installer. The env is built from scratch."""
    if sandbox is None:
        raise SandboxError("run() needs a sandbox")
    env = sandbox.base_env(claude)
    env["HOME"] = home
    if config_dir is not None:
        env["CLAUDE_CONFIG_DIR"] = config_dir
    env.update(env_extra or {})
    if not (env_extra and "CI" in env_extra):
        env.pop("CI", None)
    cwd = cwd or sandbox.root
    sandbox.check_env(env, cwd)
    script = sandbox.script_for(cmd_kind)
    return subprocess.run(["bash", script] + list(args), env=env, cwd=cwd, stdin=stdin,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)


# ---------------------------------------------------------------------------
# Parity allowances (the only differences permitted between old and new)
# ---------------------------------------------------------------------------
VERSION_OLD = re.compile(r"^bash \S+$")
VERSION_NEW = re.compile(r"^python \S+$")
AGENT_MODELS = re.compile(r"^Agent models: .+$")
CHOICES_WARN = re.compile(r"(?i)^\s*warning\b.*\bchoices\b")
CHOICES_FILES_LINE = re.compile(r"^  (add|unchanged|replace|remove|edited|missing)\s+model-routing-choices\.json(\s.*)?$")
CHOICES_MANIFEST_LINE = "    model-routing-choices.json"
MANIFEST_LISTING = re.compile(r"^    (agents|rules|hooks|skills)/")
SUM_INSTALL = re.compile(r"^Summary: (\d+) added, (\d+) replaced, (\d+) unchanged\.(.*)$")
SUM_UNINSTALL = re.compile(r"^Summary: (\d+) removed, (\d+) kept in backup, (\d+) already gone\.(.*)$")
INSTALL_GROUP = {"add": 1, "replace": 2, "unchanged": 3}
UNINSTALL_GROUP = {"remove": 1, "edited": 2, "missing": 3}


def _usage_strip(o, n, problems, label):
    """Usage text may gain lines for the new flags; old lines must all survive in order."""
    ol, nl = o.split("\n"), n.split("\n")
    oi = next((i for i, l in enumerate(ol) if l.startswith("Usage: install.sh")), None)
    ni = next((i for i, l in enumerate(nl) if l.startswith("Usage: install.sh")), None)
    if oi is None and ni is None:
        return o, n
    if oi is None or ni is None:
        problems.append("%s: usage text present on one side only" % label)
        return o, n
    old_rest, new_rest = ol[oi + 1:], nl[ni + 1:]
    pos = 0
    for line in old_rest:
        if line == "":
            continue
        try:
            pos = new_rest.index(line, pos) + 1
        except ValueError:
            problems.append("%s: usage line missing or out of order in new: %r" % (label, line))
            break
    return "\n".join(ol[:oi] + ["<USAGE>"]), "\n".join(nl[:ni] + ["<USAGE>"])


def _text_diff(a, b, label):
    return "%s differs:\n%s" % (label, "".join(difflib.unified_diff(
        a.splitlines(True), b.splitlines(True), "old", "new", n=2)))


def _entry_diff(key, o, n):
    if o is None:
        return "only in new: %s (%s mode %o)" % (key, n[0], n[2])
    if n is None:
        return "only in old: %s (%s mode %o)" % (key, o[0], o[2])
    parts = []
    if o[0] != n[0]:
        parts.append("kind %s vs %s" % (o[0], n[0]))
    if o[1] != n[1]:
        parts.append("link target %r vs %r" % (o[1], n[1]))
    if o[2] != n[2]:
        parts.append("mode %o vs %o" % (o[2], n[2]))
    if o[3] != n[3]:
        try:
            parts.append("content differs:\n" + "".join(difflib.unified_diff(
                o[3].decode("utf-8").splitlines(True), n[3].decode("utf-8").splitlines(True),
                "old", "new", n=1)))
        except Exception:
            parts.append("binary content differs (%d vs %d bytes)" % (len(o[3] or b""), len(n[3] or b"")))
    return "tree entry %s: %s" % (key, "; ".join(parts))


def apply_allowances(old, new):
    """Return a list of readable problems; empty means parity within the allowances."""
    problems = []
    if old.code != new.code:
        problems.append("exit code %s (old) vs %s (new)" % (old.code, new.code))

    o_out, n_out, o_err, n_err = old.out, new.out, old.err, new.err
    o_out, n_out = _usage_strip(o_out, n_out, problems, "stdout")
    o_err, n_err = _usage_strip(o_err, n_err, problems, "stderr")

    # Allowance 1: version line, bash (old) vs python (new).
    ol, nl = o_out.split("\n"), n_out.split("\n")
    if VERSION_OLD.match(ol[0]):
        new_ok = VERSION_NEW.match(nl[0]) or (SELF_TEST and VERSION_OLD.match(nl[0]))
        if new_ok:
            ol[0] = nl[0] = "<VERSION>"
        else:
            problems.append("new first stdout line is not a python version line: %r" % nl[0])
    elif VERSION_NEW.match(nl[0]):
        problems.append("new prints a version line where old printed none: %r" % nl[0])
    o_out, n_out = "\n".join(ol), "\n".join(nl)

    # Allowance 2: Agent models line and choices warning lines.
    n_lines = n_out.split("\n")
    models_lines = [l for l in n_lines if AGENT_MODELS.match(l)]
    n_lines = [l for l in n_lines if not AGENT_MODELS.match(l) and not CHOICES_WARN.match(l)]
    n_err = "\n".join(l for l in n_err.split("\n") if not CHOICES_WARN.match(l))
    old_install_sum = any(SUM_INSTALL.match(l) for l in o_out.split("\n"))
    if len(models_lines) > 1:
        problems.append("new printed %d 'Agent models:' lines" % len(models_lines))
    if not SELF_TEST and old_install_sum and len(models_lines) != 1:
        problems.append("new did not print exactly one 'Agent models:' line on a successful install")

    # Allowance 3: the choices file (Files line, manifest line, summary count).
    files_lines = [l for l in n_lines if CHOICES_FILES_LINE.match(l)]
    if len(files_lines) > 1:
        problems.append("new printed %d Files lines for the choices file" % len(files_lines))
    old_summary = any(SUM_INSTALL.match(l) or SUM_UNINSTALL.match(l) for l in o_out.split("\n"))
    if not SELF_TEST and old_install_sum and len(files_lines) != 1:
        problems.append("new did not print exactly one Files line for the choices file on install")
    action = CHOICES_FILES_LINE.match(files_lines[0]).group(1) if files_lines else None
    if files_lines:
        n_lines.remove(files_lines[0])
    manifest_lines = [l for l in n_lines if l == CHOICES_MANIFEST_LINE]
    old_lists_manifest = any(MANIFEST_LISTING.match(l) for l in o_out.split("\n"))
    if len(manifest_lines) > 1:
        problems.append("new listed the choices file %d times in the manifest output" % len(manifest_lines))
    if not SELF_TEST and old_lists_manifest and len(manifest_lines) != 1:
        problems.append("new did not list the choices file exactly once in the dry-run manifest lines")
    if manifest_lines:
        n_lines.remove(CHOICES_MANIFEST_LINE)
    if action:
        adjusted, done = [], False
        for l in n_lines:
            m_i, m_u = SUM_INSTALL.match(l), SUM_UNINSTALL.match(l)
            m, group = (m_i, INSTALL_GROUP.get(action)) if m_i else ((m_u, UNINSTALL_GROUP.get(action)) if m_u else (None, None))
            if m and not done:
                if group is None:
                    problems.append("choices Files line action %r does not fit this summary" % action)
                else:
                    vals = list(m.groups())
                    if int(vals[group - 1]) < 1:
                        problems.append("summary count for %r is 0 but the choices file was listed" % action)
                    else:
                        vals[group - 1] = str(int(vals[group - 1]) - 1)
                        l = _rebuild(m, vals)
                done = True
            adjusted.append(l)
        if not done:
            problems.append("choices Files line printed but no summary line found")
        n_lines = adjusted
    n_out = "\n".join(n_lines)

    # Same-name warnings must appear in the same order: install.py walks the
    # agents dir in the same readdir, preorder order as the old `find`.

    if o_out != n_out:
        problems.append(_text_diff(o_out, n_out, "stdout"))
    if o_err != n_err:
        problems.append(_text_diff(o_err, n_err, "stderr"))

    # Tree: the choices file and its manifest line.
    o_tree, n_tree = dict(old.tree), dict(new.tree)
    for key in sorted(n_tree):
        if os.path.basename(key) != MANIFEST or key not in o_tree:
            continue
        ob, nb = o_tree[key][3], n_tree[key][3]
        if ob is not None and ob.startswith(b"# model-routing manifest") and nb is not None:
            lines = nb.split(b"\n")
            cnt = lines.count(CHOICES.encode())
            if cnt > 1 or (cnt != 1 and not SELF_TEST):
                problems.append("manifest %s lists the choices file %d times (want 1)" % (key, cnt))
            if cnt:
                lines.remove(CHOICES.encode())
            n_tree[key] = n_tree[key][:3] + (b"\n".join(lines),)
            want = os.path.join(os.path.dirname(key), CHOICES)
            entry = new.tree.get(want)
            if not SELF_TEST and (entry is None or entry[0] != "file" or entry[2] != 0o644):
                problems.append("choices file %s missing, not a file, or mode is not 644: %r"
                                % (want, entry and entry[:3]))
    for key in list(n_tree):
        if os.path.basename(key) == CHOICES:
            del n_tree[key]
    for key in sorted(set(o_tree) | set(n_tree)):
        if o_tree.get(key) != n_tree.get(key):
            problems.append(_entry_diff(key, o_tree.get(key), n_tree.get(key)))
    return problems


def _rebuild(m, vals):
    """Rebuild a summary line with vals as the three counts, keeping the tail."""
    line = m.string
    spans = [m.span(i) for i in (1, 2, 3)]
    out, last = [], 0
    for (s, e), v in zip(spans, vals[:3]):
        out.append(line[last:s])
        out.append(v)
        last = e
    out.append(line[last:])
    return "".join(out)

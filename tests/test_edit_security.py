"""Security tests for the edit routes (#84): the write-call scan and real server processes.

Two kinds of test live here. The first scans every dashboard/*.py with the ast
module and allows write calls only in edit_store.py, plus one named line in
reference_page.py. The second starts a real server process with --allow-edits
on a temp fixture, from a copy of the server tree, and drives it over HTTP the
way the page does: targets, preview, save, undo. The tree hash covers the
config, project and managed folders and the server copy, so a write anywhere
else shows up. No browser, and nothing reads the real ~/.claude: every test
uses a temp root and a throwaway HOME.

Secrets are made-up strings that start with "sk-ant-planted" or "marker". Tests
pin stable error codes and status numbers, never wording.
"""
import ast
import collections
import filecmp
import json
import os
import urllib.parse
import unittest

import helpers
import test_edit_server as es
import test_server as ts

DASHBOARD = os.path.join(helpers.REPO, "dashboard")
STORE_DIR = "routing-dashboard"
MODEL = b'{"model": "claude-sonnet-5-5"}\n'  # Sonnet 5.5 takes a project or local effortLevel
EXCEPTION_FILE = "reference_page.py"
STORE_FILE = "edit_store.py"


# --------------------------------------------------------------------------
# The write-call scanner

OS_WRITES = frozenset("""rename renames replace unlink remove mkdir makedirs rmdir removedirs link symlink
truncate ftruncate write chmod fchmod utime mkfifo lchmod chown fchown lchown mknod pwrite writev
sendfile copy_file_range posix_fallocate chflags lchflags setxattr removexattr""".split())
SHUTIL_WRITES = frozenset("""copy copy2 copyfile copytree move rmtree copymode copystat make_archive
unpack_archive chown""".split())
TEMPFILE_WRITES = frozenset("""NamedTemporaryFile TemporaryFile SpooledTemporaryFile TemporaryDirectory
mkstemp mkdtemp mktemp""".split())
PATH_WRITES = frozenset("""write_text write_bytes touch mkdir rmdir unlink rename chmod lchmod symlink_to
hardlink_to link_to""".split())
READ_ONLY_FLAGS = frozenset("O_RDONLY O_NOFOLLOW O_DIRECTORY O_NONBLOCK O_CLOEXEC O_NOCTTY".split())
WATCHED_MODULES = frozenset(["os", "io", "shutil", "tempfile", "builtins", "codecs"])
Finding = collections.namedtuple("Finding", "file line call detail first")


def _mode_writes(node):
    """A missing mode reads. A constant mode writes when it holds w, a, x or +. Anything else writes."""
    if node is None:
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return any(ch in node.value for ch in "wax+")
    return True


def _arg(call, index, name):
    if len(call.args) > index:
        return call.args[index]
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _flags_read_only(node, consts, seen=()):
    """True when the os.open flags are built only from read-only names, a literal 0, or | of those.

    A bare name counts when a module-level assignment in the same file builds it from the same parts.
    A variable, a call, a parameter or an unknown name is not read-only.
    """
    if isinstance(node, ast.Constant):
        return node.value == 0
    if isinstance(node, ast.Attribute):
        return isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr in READ_ONLY_FLAGS
    if isinstance(node, ast.Name):
        if node.id in READ_ONLY_FLAGS:
            return True
        if node.id in consts and node.id not in seen:
            return _flags_read_only(consts[node.id], consts, seen + (node.id,))
        return False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _flags_read_only(node.left, consts, seen) and _flags_read_only(node.right, consts, seen)
    return False


def _is_getattr(call):
    return (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "getattr"
            and len(call.args) >= 2)


def _bound_to(node, modules, names):
    """What an expression names in a watched module, for the scan to follow.

    Returns (module, None) for a watched module, (module, attr) for one of its functions, or None. The forms are
    the module name, "os.replace", an alias already followed, and getattr(os, "replace") with a constant name.
    """
    if isinstance(node, ast.Name):
        if node.id in modules and modules[node.id] != "pathlib":
            return (modules[node.id], None)
        return names.get(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in modules:
        return (modules[node.value.id], node.attr)
    if _is_getattr(node) and isinstance(node.args[0], ast.Name) and node.args[0].id in modules:
        name = node.args[1]
        if isinstance(name, ast.Constant) and isinstance(name.value, str):
            return (modules[node.args[0].id], name.value)
    return None


def scan_source(source, name):
    """Return the Findings for every call in source that can write, create, move, delete or change a file.

    Strict on purpose: an unknown open mode or os.open flags counts as a write. Calls are found by name,
    so an alias (import os as o, from os import replace) is followed. A reference that is not a call is not
    a finding.
    """
    tree = ast.parse(source, filename=name)
    modules = {}  # local name -> module, for "import os" and "import os as o"
    names = {}  # local name -> (module, attr), for "from os import replace as r"
    consts = {}  # module-level NAME = expression
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            consts[node.targets[0].id] = node.value
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in WATCHED_MODULES or alias.name == "pathlib":
                    modules[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in WATCHED_MODULES:
            for alias in node.names:
                names[alias.asname or alias.name] = (node.module, alias.name)
    # A name bound to a watched module, or to one of its functions, is followed too: "o = os", "f = os.replace",
    # "f = getattr(os, 'replace')" and "g = f". The pass repeats until nothing new is bound.
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and len(n.targets) == 1
               and isinstance(n.targets[0], ast.Name)]
    grew = True
    while grew:
        grew = False
        for node in assigns:
            target, value = node.targets[0].id, node.value
            bound = _bound_to(value, modules, names)
            if bound is None:
                continue
            if bound[1] is None and target not in modules:
                modules[target] = bound[0]
                grew = True
            elif bound[1] is not None and names.get(target) != bound:
                names[target] = bound
                grew = True
    found = []

    def add(call, kind, detail=""):
        first = ast.unparse(call.args[0]) if call.args else ""
        found.append(Finding(name, call.lineno, kind, detail, first))

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        module = attr = None
        if _is_getattr(call) and isinstance(call.args[0], ast.Name) and call.args[0].id in modules:
            # getattr(os, name) with a name the scan can't read could be any function of the module.
            if _bound_to(call, modules, names) is None:
                add(call, "getattr", modules[call.args[0].id] + "." + "?")
            continue
        if isinstance(func, ast.Call) and _bound_to(func, modules, names) is not None:
            module, attr = _bound_to(func, modules, names)  # getattr(os, "replace")(a, b)
        elif isinstance(func, ast.Name):
            if func.id in names:
                module, attr = names[func.id]
            elif func.id == "open":
                module, attr = "builtins", "open"
        elif isinstance(func, ast.Attribute):
            attr = func.attr
            if isinstance(func.value, ast.Name) and func.value.id in modules:
                module = modules[func.value.id]
        if attr is None:
            continue
        if module is None:
            # A method on an unknown object, so it may be a pathlib.Path.
            if attr in PATH_WRITES:
                add(call, "pathlib." + attr)
            elif attr == "replace" and len(call.args) == 1 and not call.keywords:
                add(call, "pathlib.replace")  # str.replace takes two arguments
            elif attr == "open" and _mode_writes(_arg(call, 0, "mode")):
                mode = _arg(call, 0, "mode")
                add(call, "pathlib.open", repr(mode.value) if isinstance(mode, ast.Constant) else "?")
            continue
        if module in ("builtins", "io", "codecs") and attr == "open" or module == "os" and attr == "fdopen":
            mode = _arg(call, 1, "mode")
            if _mode_writes(mode):
                add(call, "open", repr(mode.value) if isinstance(mode, ast.Constant) else "?")
        elif module == "os" and attr == "open":
            flags = _arg(call, 1, "flags")
            if flags is None or not _flags_read_only(flags, consts):
                add(call, "os.open", "?" if flags is None else ast.unparse(flags))
        elif module == "os" and attr in OS_WRITES:
            add(call, "os." + attr)
        elif module == "shutil" and attr in SHUTIL_WRITES:
            add(call, "shutil." + attr)
        elif module == "tempfile" and attr in TEMPFILE_WRITES:
            add(call, "tempfile." + attr)
    return sorted(found, key=lambda f: f.line)


def scan_dashboard():
    out = {}
    for name in sorted(os.listdir(DASHBOARD)):
        if name.endswith(".py"):
            with open(os.path.join(DASHBOARD, name), "rb") as fh:
                out[name] = scan_source(fh.read(), name)
    return out


# One sample per call the ticket lists, so a scanner that goes blind fails here first.
POSITIVE_SAMPLES = {
    "open w": "open('f', 'w')",
    "open a": "open('f', mode='a')",
    "open x": "open('f', 'x')",
    "open r+": "open('f', 'r+b')",
    "open variable mode": "open('f', mode)",
    "io.open w": "import io\nio.open('f', 'wb')",
    "codecs.open w": "import codecs\ncodecs.open('f', 'w')",
    "os.fdopen w": "import os\nos.fdopen(3, 'w')",
    "os.open O_WRONLY": "import os\nos.open('f', os.O_WRONLY)",
    "os.open O_RDWR": "import os\nos.open('f', os.O_RDWR)",
    "os.open O_CREAT": "import os\nos.open('f', os.O_RDONLY | os.O_CREAT)",
    "os.open O_TRUNC": "import os\nos.open('f', flags=os.O_TRUNC)",
    "os.open O_APPEND": "import os\nos.open('f', os.O_APPEND)",
    "os.open variable flags": "import os\ndef f(flags):\n    os.open('f', flags)",
    "os.open unknown constant": "import os\nos.open('f', SOME_FLAGS)",
    "os.open constant with a write flag": "import os\nF = os.O_RDONLY | os.O_CREAT\nos.open('f', F)",
    "os.open no flags": "import os\nos.open('f')",
    "os.open nonzero literal": "import os\nos.open('f', 1)",
    "from os import open": "from os import open as o\no('f', os.O_WRONLY)",
    "alias": "import os as o\no.unlink('f')",
    "from os import": "from os import replace as r\nr('a', 'b')",
    "pathlib write_text": "p.write_text('x')",
    "pathlib write_bytes": "p.write_bytes(b'x')",
    "pathlib open w": "p.open('w')",
    "pathlib open variable": "p.open(mode)",
    "pathlib touch": "p.touch()",
    "pathlib mkdir": "p.mkdir()",
    "pathlib unlink": "p.unlink()",
    "pathlib rmdir": "p.rmdir()",
    "pathlib rename": "p.rename('x')",
    "pathlib replace": "p.replace('x')",
    "pathlib symlink_to": "p.symlink_to('x')",
    "pathlib chmod": "p.chmod(0o600)",
    "tempfile NamedTemporaryFile": "import tempfile\ntempfile.NamedTemporaryFile()",
    "tempfile TemporaryFile": "import tempfile\ntempfile.TemporaryFile()",
    "tempfile mkstemp": "import tempfile\ntempfile.mkstemp()",
    "tempfile mkdtemp": "import tempfile\ntempfile.mkdtemp()",
    "tempfile TemporaryDirectory": "import tempfile\ntempfile.TemporaryDirectory()",
    "alias of os.replace": "import os\nf = os.replace\nf('a', 'b')",
    "alias of an alias": "import os\nf = os.replace\ng = f\ng('a', 'b')",
    "alias of a module": "import os\no = os\no.unlink('f')",
    "alias of from os import": "from os import replace\nf = replace\nf('a', 'b')",
    "alias of shutil.rmtree": "import shutil\nf = shutil.rmtree\nf('x')",
    "alias of os.open with write flags": "import os\nf = os.open\nf('f', os.O_WRONLY)",
    "getattr called at once": "import os\ngetattr(os, 'replace')('a', 'b')",
    "getattr bound to a name": "import os\nf = getattr(os, 'unlink')\nf('a')",
    "getattr bound to a name, with a default": "import os\nf = getattr(os, 'unlink', None)\nf('a')",
    "getattr os.open with write flags": "import os\nf = getattr(os, 'open')\nf('f', os.O_WRONLY)",
    "getattr with a name the scan can't read": "import os\ngetattr(os, name)('a')",
    "getattr with a name held in a variable": "import os\nf = getattr(os, name)\nf('a')",
    "getattr on an aliased module": "import os as o\ngetattr(o, 'remove')('a')",
}
for _name in ("rename", "renames", "replace", "unlink", "remove", "mkdir", "makedirs", "rmdir", "removedirs",
              "link", "symlink", "truncate", "ftruncate", "write", "chmod", "fchmod", "utime", "mkfifo"):
    POSITIVE_SAMPLES["os." + _name] = "import os\nos.%s('a', 'b')" % _name
for _name in ("copy", "copy2", "copyfile", "copytree", "move", "rmtree"):
    POSITIVE_SAMPLES["shutil." + _name] = "import shutil\nshutil.%s('a', 'b')" % _name

NEGATIVE_SAMPLES = {
    "open default": "open('f')",
    "open r": "open('f', 'r')",
    "open rb": "open('f', mode='rb')",
    "io.open rb": "import io\nio.open('f', 'rb')",
    "os.open read-only flags": "import os\nos.open('f', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)",
    "os.open read-only constant": ("import os\nFLAGS = os.O_RDONLY | os.O_DIRECTORY\n"
                                   "SUB = FLAGS | os.O_NOFOLLOW\nos.open('f', SUB)"),
    "os.open zero": "import os\nos.open('f', 0)",
    "str.replace": "'abc'.replace('a', 'b')",
    "os.path.join": "import os\nos.path.join('a', 'b')",
    "os.stat and listdir": "import os\nos.stat('f')\nos.listdir('.')\nos.fstat(3)\nos.read(3, 5)",
    "pathlib reads": "p.read_text()\np.read_bytes()\np.exists()\np.open('rb')\np.open()",
    "a reference that is not a call": "import os\nneeds = (os.open, os.rename, os.unlink)",
    "json.dump": "import json\njson.dumps({})",
    "an alias of a read": "import os\nf = os.stat\nf('x')\ng = getattr(os, 'listdir')\ng('.')",
    "an alias of a module used to read": "import os\no = os\no.listdir('.')\no.path.join('a', 'b')",
    "getattr on something else": "getattr(obj, name)('a')\ngetattr(obj, 'replace')('a', 'b')",
}


class ScannerWorks(unittest.TestCase):
    """The scan is only worth trusting if it fails on a known write. Each sample runs through scan_source."""

    def test_every_listed_call_is_found(self):
        for label, source in sorted(POSITIVE_SAMPLES.items()):
            found = scan_source(source, "sample.py")
            self.assertTrue(found, label)

    def test_the_sample_set_names_every_call_the_ticket_lists(self):
        for call in ("os.rename", "os.renames", "os.replace", "os.unlink", "os.remove", "os.mkdir",
                     "os.makedirs", "os.rmdir", "os.removedirs", "os.link", "os.symlink", "os.truncate",
                     "os.ftruncate", "os.write", "os.chmod", "os.fchmod", "os.utime", "os.mkfifo",
                     "shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree", "shutil.move",
                     "shutil.rmtree", "io.open w", "open w"):
            self.assertIn(call, POSITIVE_SAMPLES, call)
        flags = " ".join(POSITIVE_SAMPLES[k] for k in POSITIVE_SAMPLES if k.startswith("os.open O_"))
        for flag in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND"):
            self.assertIn(flag, flags)
        names = " ".join(POSITIVE_SAMPLES)
        for word in ("tempfile", "pathlib"):
            self.assertIn(word, names)

    def test_the_kind_and_line_of_a_finding_are_right(self):
        found = scan_source("import os\n\nx = 1\nos.replace('a', 'b')\nopen('f', 'w')\n", "sample.py")
        self.assertEqual([(f.line, f.call, f.detail, f.first) for f in found],
                         [(4, "os.replace", "", "'a'"), (5, "open", "'w'", "'f'")])

    def test_a_followed_alias_is_reported_at_its_call(self):
        found = scan_source("import os\nf = os.replace\n\nf('a', 'b')\ngetattr(os, 'rename')('c', 'd')\n"
                            "getattr(os, name)('e')\n", "sample.py")
        self.assertEqual([(f.line, f.call) for f in found],
                         [(4, "os.replace"), (5, "os.rename"), (6, "getattr")])

    def test_reads_are_not_findings(self):
        for label, source in sorted(NEGATIVE_SAMPLES.items()):
            self.assertEqual(scan_source(source, "sample.py"), [], label)


# --------------------------------------------------------------------------
# What the real modules do

class WriteCalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scan = scan_dashboard()

    def test_the_scan_covers_the_whole_dashboard_folder(self):
        self.assertEqual(sorted(self.scan), sorted(n for n in os.listdir(DASHBOARD) if n.endswith(".py")))
        for name in ("server.py", "api_edit.py", "edit_store.py", "json_edit.py", "reference_page.py",
                     "collect.py", "api_settings.py", "api_usage.py"):
            self.assertIn(name, self.scan)

    def test_write_calls_live_in_edit_store_and_one_line_of_reference_page(self):
        stray = []
        for name, findings in self.scan.items():
            if name == STORE_FILE:
                continue
            for finding in findings:
                if (name == EXCEPTION_FILE and finding.call == "open" and finding.detail == "'w'"
                        and finding.first == "PAGE_PATH"):
                    continue
                stray.append("%s:%d %s %s" % (name, finding.line, finding.call, finding.detail))
        self.assertEqual(stray, [])

    def test_the_named_exception_is_there_exactly_once(self):
        hits = [f for f in self.scan[EXCEPTION_FILE] if f.call == "open" and f.first == "PAGE_PATH"]
        self.assertEqual([(f.detail) for f in hits], ["'w'"])
        self.assertEqual(len(self.scan[EXCEPTION_FILE]), 1)

    def test_edit_store_is_the_one_module_the_scan_finds_writing(self):
        kinds = {f.call for f in self.scan[STORE_FILE]}
        self.assertTrue({"os.open", "os.rename", "os.unlink", "os.mkdir", "os.write"} <= kinds, kinds)

    def test_the_server_never_calls_the_docs_generator(self):
        for name in sorted(self.scan):
            if name in (EXCEPTION_FILE, "__init__.py"):
                continue
            with open(os.path.join(DASHBOARD, name), encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotIn("import reference_page", text, name)
            self.assertNotIn("from reference_page", text, name)


# --------------------------------------------------------------------------
# A real server process on a temp fixture

class Run:
    """A server process with --allow-edits on a temp fixture, started from a copy of the server tree."""

    def __init__(self, case, project=None, local=None, user=MODEL, managed=None):
        self.root = ts.make_root("mr-edit-sec-")
        case.addCleanup(helpers.rmtree_force, self.root)
        self.fx = os.path.join(self.root, "fixture")
        self.cfg = os.path.join(self.fx, "config")
        self.proj = os.path.join(self.fx, "project")
        self.managed = os.path.join(self.fx, "managed")
        os.makedirs(self.managed)
        self.put(os.path.join(self.fx, "session.json"), b"{}\n")
        for layer, raw in (("user", user), ("project", project), ("local", local)):
            if raw is not None:
                self.put(self.path(layer), raw)
        if managed is not None:
            self.put(os.path.join(self.managed, "managed-settings.json"), managed)
        os.makedirs(os.path.join(self.proj, ".claude"), exist_ok=True)
        self.tree = os.path.join(self.root, "copy")
        script = ts.copy_tree(self.tree)
        env = ts.base_env(self.root)
        self.home = env["HOME"]
        # -X pycache_prefix= turns off the cache folder Apple's python3 adds, which would hide a
        # __pycache__ write from the tree hash (W-f6ed). No -B: the server's own setting keeps bytecode off.
        self.proc = ts.start(self.root, ["--fixture", self.fx, "--allow-edits"], env=env, script=script,
                             python_args=["-X", "pycache_prefix="])
        case.addCleanup(self.proc.stop)
        self.port = self.proc.port
        self.token = self.proc.token
        self.bodies = []

    # files

    @staticmethod
    def put(path, raw):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(raw)

    def path(self, layer):
        return {"user": os.path.join(self.cfg, "settings.json"),
                "project": os.path.join(self.proj, ".claude", "settings.json"),
                "local": os.path.join(self.proj, ".claude", "settings.local.json")}[layer]

    def read(self, layer):
        with open(self.path(layer), "rb") as fh:
            return fh.read()

    def real(self, display):
        """A fixture run shows paths relative to the fixture folder."""
        return os.path.join(self.fx, *display.split("/"))

    def store_folder(self):
        return os.path.join(self.cfg, STORE_DIR)

    # the tree

    def watched(self):
        return (self.cfg, self.proj, self.managed, self.tree)

    def snap(self):
        return ts.hash_tree(*self.watched())

    @staticmethod
    def changed(before, after):
        return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))

    def assert_only(self, case, before, layers=()):
        """The only differences are the named target files and paths under config/routing-dashboard."""
        allowed = {self.path(layer) for layer in layers}
        store = self.store_folder()
        stray = [p for p in self.changed(before, self.snap())
                 if p not in allowed and p != store and not p.startswith(store + os.sep)]
        case.assertEqual(stray, [])
        case.assertEqual([d for d, _, _ in os.walk(self.tree) if "__pycache__" in d], [])

    # requests

    def get(self, path):
        status, _heads, data = es.send(self.port, "GET", path)
        self.bodies.append(data)
        return status, json.loads(data)

    def raw_post(self, path, body, headers=None, **kwargs):
        if headers is None:
            headers = es.good_headers(self.port, self.token)
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        result = es.send(self.port, "POST", path, headers, body, **kwargs)
        self.bodies.append(result[2])
        return result

    def post(self, path, body):
        status, _heads, data = self.raw_post(path, body)
        return status, json.loads(data)

    def targets(self):
        status, body = self.get("/api/edit/targets")
        assert status == 200, (status, body)
        return body

    def target(self, layer="project"):
        listing = self.targets()
        found = [t for t in listing["targets"] if t["layer"] == layer]
        assert len(found) == 1, listing
        return listing["project"], found[0]["target"]

    def preview(self, layer, value):
        key, target = self.target(layer)
        status, body = self.post("/api/edit/preview", {"project": key, "target": target, "value": value})
        assert status == 200, (status, body)
        return key, target, body

    def save_body(self, layer, value):
        key, target, pv = self.preview(layer, value)
        return {"project": key, "target": target, "value": value, "base_file": pv["base_file"],
                "base_trail": pv["base_trail"], "base_others": pv["base_others"]}

    def save(self, layer, value):
        return self.post("/api/edit/save", self.save_body(layer, value))

    def undo_body(self, edit_id, key="project"):
        return {"project": key, "edit": edit_id}

    def undo(self, edit_id, key="project"):
        return self.post("/api/edit/undo", self.undo_body(edit_id, key))

    def everything(self):
        """Every response body this run saw, plus the server's log, as one string."""
        return b"\n".join(self.bodies).decode("utf-8", "replace") + "\n" + self.proc.stderr()

    def ledgers(self):
        out = []
        for dirpath, _dirs, files in os.walk(self.store_folder()):
            out += [os.path.join(dirpath, f) for f in files if f.endswith(".json")]
        return out


class RunCase(es.GateAssertions, ts.TempCase):
    """TempCase stops every server it started; Run adds its own cleanups and uses its own root."""


SIMPLE = b'{\n  "effortLevel": "high",\n  "env": {\n    "A": "1"\n  }\n}\n'


# --------------------------------------------------------------------------
# The tree hash

class TreeHash(RunCase):
    def test_the_routes_that_only_read_write_nothing(self):
        run = Run(self, project=SIMPLE)
        before = run.snap()
        run.get("/api/edit")
        run.get("/api/edit/history")
        run.get("/api/settings")
        run.get("/api/usage")
        run.preview("project", "low")
        run.preview("project", "xhigh")
        self.assertEqual(run.snap(), before)
        self.assertFalse(os.path.exists(run.store_folder()))

    def test_a_save_and_an_undo_change_only_the_target_and_the_backup_store(self):
        run = Run(self, project=SIMPLE, local=b'{"effortLevel": "medium"}\n')
        before = run.snap()
        status, saved = run.save("project", "low")
        self.assertEqual(status, 200, saved)
        mid = run.snap()
        self.assertIn(run.path("project"), run.changed(before, mid))
        self.assertTrue(os.path.isdir(run.store_folder()))
        run.assert_only(self, before, ["project"])
        status, undone = run.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, undone)
        run.assert_only(self, before, ["project"])
        # The other settings files, the managed folder and the whole server copy, install.py included.
        after = run.snap()
        for path in (run.path("user"), run.path("local"), os.path.join(run.tree, "install.py"),
                     os.path.join(run.tree, "dashboard", "server.py")):
            self.assertEqual(after[path], before[path], path)
        self.assertEqual([p for p in after if p.startswith(run.managed + os.sep)],
                         [p for p in before if p.startswith(run.managed + os.sep)])

    def test_a_user_layer_save_changes_only_the_user_file_and_the_store(self):
        run = Run(self, user=b'{"model": "claude-sonnet-5-5", "effortLevel": "high"}\n')
        listing = run.targets()
        layers = [t["layer"] for t in listing["targets"]]
        self.assertIn("user", layers)
        before = run.snap()
        status, saved = run.save("user", "low")
        self.assertEqual(status, 200, saved)
        run.assert_only(self, before, ["user"])

    def test_a_refused_save_writes_neither_the_target_nor_a_backup(self):
        run = Run(self, project=SIMPLE)
        body = run.save_body("project", "low")
        before = run.snap()
        for bad in (dict(body, value="max"), dict(body, value="sk-planted"), dict(body, target="t-0000"),
                    dict(body, base_file="0" * 64), dict(body, project="nope")):
            status, _heads, _data = run.raw_post("/api/edit/save", bad)
            self.assertGreaterEqual(status, 400)
            self.assertLess(status, 500)
        # A stale save may open the store folder under its lock, so the store may gain empty folders.
        run.assert_only(self, before)
        self.assertEqual(run.read("project"), SIMPLE)
        found = [f for _d, _s, files in os.walk(run.store_folder()) for f in files]
        self.assertEqual([f for f in found if f.endswith((".bak", ".json", ".tmp"))], [])


# --------------------------------------------------------------------------
# The header matrix

class HeaderMatrix(RunCase):
    def cases(self, run):
        port, token = run.port, run.token
        good = es.good_headers
        return [
            ("bad Host", dict(host="evil.example"), None, 403, "forbidden"),
            ("missing Origin", {}, good(port, token, drop=("Origin",)), 403, "forbidden"),
            ("foreign Origin", {}, good(port, token, {"Origin": "http://evil.example"}), 403, "forbidden"),
            ("null Origin", {}, good(port, token, {"Origin": "null"}), 403, "forbidden"),
            ("Sec-Fetch-Site cross-site", {}, good(port, token, extra=[("Sec-Fetch-Site", "cross-site")]),
             403, "forbidden"),
            ("Sec-Fetch-Site none", {}, good(port, token, extra=[("Sec-Fetch-Site", "none")]),
             403, "forbidden"),
            ("text/plain", {}, good(port, token, {"Content-Type": "text/plain"}), 415, "bad_content_type"),
            ("form content", {"form": True}, good(port, token, {
                "Content-Type": "application/x-www-form-urlencoded"}), 415, "bad_content_type"),
            ("missing token", {}, good(port, token, drop=("X-Dashboard-Token",)), 403, "bad_token"),
            ("wrong token", {}, good(port, token, {"X-Dashboard-Token": "wrong"}), 403, "bad_token"),
            ("token in query", {"query": True}, good(port, token, drop=("X-Dashboard-Token",)),
             403, "bad_token"),
        ]

    def run_matrix(self, run, path, body, label):
        before = run.snap()
        for name, opts, headers, status, error in self.cases(run):
            payload = body
            target = path
            if opts.get("form"):
                payload = urllib.parse.urlencode({k: v for k, v in body.items()
                                                  if isinstance(v, str)}).encode("ascii")
            if opts.get("query"):
                target = path + "?token=" + run.token
            kwargs = {"host": opts["host"]} if "host" in opts else {}
            result = run.raw_post(target, payload, headers, **kwargs)
            self.assert_refused(result, status, error, "%s %s" % (label, name))
            self.assertEqual(run.snap(), before, "%s %s" % (label, name))
            self.assertFalse(os.path.exists(run.store_folder()) and label != "undo", name)

    def test_every_case_is_refused_on_each_write_route_and_nothing_changes(self):
        run = Run(self, project=SIMPLE)
        original = run.read("project")
        pristine = run.snap()
        body = run.save_body("project", "low")
        self.run_matrix(run, "/api/edit/preview", {k: body[k] for k in ("project", "target", "value")},
                        "preview")
        self.run_matrix(run, "/api/edit/save", body, "save")
        self.assertEqual(run.snap(), pristine)
        self.assertFalse(os.path.exists(run.store_folder()))
        self.assertEqual(run.read("project"), original)
        # The same request with a good gate writes, so the refusals above held something back.
        status, saved = run.post("/api/edit/save", body)
        self.assertEqual(status, 200, saved)
        self.assertNotEqual(run.read("project"), original)
        after_save = run.snap()
        self.run_matrix(run, "/api/edit/undo", run.undo_body(saved["edit"]["id"]), "undo")
        self.assertEqual(run.snap(), after_save)
        status, undone = run.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, undone)
        self.assertEqual(run.read("project"), original)

    def test_a_refused_request_is_not_logged_with_its_token_or_body(self):
        run = Run(self, project=SIMPLE)
        body = run.save_body("project", "low")
        run.raw_post("/api/edit/save?token=" + run.token, body,
                     es.good_headers(run.port, run.token, {"X-Dashboard-Token": "planted-wrong"}))
        err = run.proc.stderr()
        self.assertNotIn(run.token, err)
        self.assertNotIn("planted-wrong", err)
        self.assertNotIn(body["base_file"], err)


# --------------------------------------------------------------------------
# Secret preservation

SECRET_FILE = (b'{\n'
               b'  "effortLevel": "high",\n'
               b'  "env": {\n'
               b'    "ANTHROPIC_API_KEY": "sk-ant-planted-AAAA1111bbbb2222cccc",\n'
               b'    "PLAIN": "ok"\n'
               b'  },\n'
               b'  "credentials": {\n'
               b'    "client": "acme",\n'
               b'    "password": "planted-password-9999",\n'
               b'    "nested": {\n'
               b'      "token": "sk-ant-planted-multi-ZZZZ8888"\n'
               b'    }\n'
               b'  }\n'
               b'}\n')
SECRETS = (b"sk-ant-planted-AAAA1111bbbb2222cccc", b"planted-password-9999", b"sk-ant-planted-multi-ZZZZ8888")


class SecretPreservation(RunCase):
    def test_a_save_keeps_every_secret_byte_and_no_response_or_log_holds_one(self):
        run = Run(self, project=SECRET_FILE)
        status, saved = run.save("project", "low")
        self.assertEqual(status, 200, saved)
        after = run.read("project")
        self.assertEqual(after, SECRET_FILE.replace(b'"high"', b'"low"', 1))
        for secret in SECRETS:
            self.assertIn(secret, after)
        run.get("/api/edit/history")
        run.get("/api/edit/targets")
        run.get("/api/settings")
        run.get("/api/usage")
        status, undone = run.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, undone)
        self.assertEqual(run.read("project"), SECRET_FILE)
        text = run.everything()
        for secret in SECRETS:
            self.assertNotIn(secret.decode(), text)
            self.assertNotIn(secret.decode()[:12] + secret.decode()[12:], text)
        for ledger in run.ledgers():
            with open(ledger, "rb") as fh:
                data = fh.read()
            for secret in SECRETS:
                self.assertNotIn(secret, data, ledger)

    def test_the_preview_diff_shows_hidden_where_a_secret_sits_in_the_context(self):
        run = Run(self, project=SECRET_FILE)
        _key, _target, pv = run.preview("project", "low")
        text = json.dumps(pv)
        self.assertIn("hidden", text)
        for secret in SECRETS:
            self.assertNotIn(secret.decode(), text)


# --------------------------------------------------------------------------
# Byte identity through the routes

CASES = {
    "CRLF": b'{\r\n  "effortLevel": "high",\r\n  "env": {\r\n    "A": "1"\r\n  }\r\n}\r\n',
    "tabs": b'{\n\t"effortLevel": "high",\n\t"env": {\n\t\t"A": "1"\n\t}\n}\n',
    "no trailing newline": b'{\n  "effortLevel": "high"\n}',
    "minified": b'{"effortLevel":"high","env":{"A":"1"},"list":[1,2,3]}',
    "duplicate keys": (b'{\n  "env": {"A": "1", "A": "2"},\n  "effortLevel": "xhigh",\n'
                       b'  "effortLevel": "high",\n  "note": "x", "note": "y"\n}\n'),
    "unicode escapes": (b'{\n  "note": "caf\\u00e9 \\ud83d\\ude00 \\u2028 \\"q\\" \\\\",\n'
                        b'  "effortLevel": "high",\n  "name\\u00e9": "x"\n}\n'),
    "raw utf-8": '{\n  "note": "café \U0001f600",\n  "effortLevel": "high"\n}\n'.encode("utf-8"),
}


def expected_after_save(raw, value):
    """The bytes with only the last effortLevel value swapped. Every other byte stays."""
    start = raw.index(b'"', raw.index(b":", raw.rindex(b'"effortLevel"')))
    end = raw.index(b'"', start + 1) + 1
    return raw[:start] + json.dumps(value).encode("ascii") + raw[end:]


class ByteIdentity(RunCase):
    def test_save_then_undo_gives_back_the_original_bytes_on_every_layout(self):
        for label, original in sorted(CASES.items()):
            with self.subTest(label):
                run = Run(self, project=original)
                before = run.snap()
                status, saved = run.save("project", "low")
                self.assertEqual(status, 200, (label, saved))
                self.assertEqual(run.read("project"), expected_after_save(original, "low"), label)
                self.assertNotEqual(run.read("project"), original)
                backup = run.real(saved["edit"]["backup_display"])
                with open(backup, "rb") as fh:
                    self.assertEqual(fh.read(), original, label)
                status, undone = run.undo(saved["edit"]["id"])
                self.assertEqual(status, 200, (label, undone))
                self.assertEqual(run.read("project"), original, label)
                self.assertTrue(filecmp.cmp(run.path("project"), backup, shallow=False), label)
                self.assertIs(undone["matches_backup"], True, label)
                run.assert_only(self, before, ["project"])

    def test_the_first_value_of_a_repeated_key_is_left_alone(self):
        original = CASES["duplicate keys"]
        run = Run(self, project=original)
        status, saved = run.save("project", "low")
        self.assertEqual(status, 200, saved)
        after = run.read("project")
        self.assertIn(b'"effortLevel": "xhigh"', after)
        self.assertIn(b'"A": "1", "A": "2"', after)
        self.assertIn(b'"note": "x", "note": "y"', after)


# --------------------------------------------------------------------------
# The undo proof

class UndoProof(RunCase):
    def one_cycle(self):
        run = Run(self, project=SIMPLE)
        status, saved = run.save("project", "medium")
        self.assertEqual(status, 200, saved)
        status, undone = run.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, undone)
        return run, saved, undone

    def test_the_file_and_restored_from_display_are_byte_equal(self):
        run, saved, undone = self.one_cycle()
        restored = run.real(undone["restored_from_display"])
        self.assertTrue(os.path.isfile(restored))
        self.assertTrue(filecmp.cmp(run.path("project"), restored, shallow=False))
        with open(restored, "rb") as fh:
            self.assertEqual(fh.read(), SIMPLE)
        self.assertEqual(undone["restored_from_display"], saved["edit"]["backup_display"])
        self.assertEqual(undone["edit"]["restored_from_display"], undone["restored_from_display"])

    def test_the_file_and_the_undo_rows_own_backup_differ(self):
        run, saved, undone = self.one_cycle()
        own = run.real(undone["edit"]["backup_display"])
        self.assertTrue(os.path.isfile(own))
        self.assertNotEqual(undone["edit"]["backup_display"], undone["restored_from_display"])
        self.assertFalse(filecmp.cmp(run.path("project"), own, shallow=False))
        with open(own, "rb") as fh:
            self.assertEqual(fh.read(), expected_after_save(SIMPLE, "medium"))

    def test_the_history_row_of_the_undo_carries_the_same_two_paths(self):
        run, _saved, undone = self.one_cycle()
        status, history = run.get("/api/edit/history")
        self.assertEqual(status, 200)
        row = history["rows"][0]
        self.assertEqual(row["kind"], "undo")
        self.assertEqual(row["restored_from_display"], undone["restored_from_display"])
        self.assertEqual(row["backup_display"], undone["edit"]["backup_display"])


# --------------------------------------------------------------------------
# Masking across the routes

MARKERS = ("marker-token-first", "marker-token-second", "marker-helper-value", "sk-marker-list-item",
           "marker-auth-nested", "sk-marker-bearer", "Bearer marker-bearer-header", "sk-marker-effort-local",
           "marker-credential-value")
MASK_PROJECT = (b'{\n'
                b'  "env": {\n'
                b'    "MY_TOKEN": "marker-token-first",\n'
                b'    "MY_TOKEN": "marker-token-second",\n'
                b'    "NOTE": "sk-marker-bearer"\n'
                b'  },\n'
                b'  "apiKeyHelper": "marker-helper-value",\n'
                b'  "effortLevel": "high",\n'
                b'  "headers": ["sk-marker-list-item", "Bearer marker-bearer-header"],\n'
                b'  "authBlock": {"inner": "marker-auth-nested"},\n'
                b'  "credentialStore": "marker-credential-value"\n'
                b'}\n')
MASK_LOCAL = b'{\n  "effortLevel": "sk-marker-effort-local"\n}\n'


class Masking(RunCase):
    def sweep(self, run):
        run.get("/api/edit")
        run.get("/api/edit/targets")
        run.get("/api/edit/history")
        run.get("/api/settings")
        run.get("/api/usage")

    def assert_no_marker(self, run, label):
        text = run.everything()
        for marker in MARKERS:
            self.assertNotIn(marker, text, "%s: %s" % (label, marker))
        for ledger in run.ledgers():
            with open(ledger, "rb") as fh:
                data = fh.read().decode("utf-8", "replace")
            for marker in MARKERS:
                self.assertNotIn(marker, data, "%s: %s" % (ledger, marker))

    def test_planted_markers_never_show_in_preview_targets_history_or_the_log(self):
        run = Run(self, project=MASK_PROJECT, local=MASK_LOCAL)
        self.sweep(run)
        _key, _target, pv = run.preview("project", "low")
        self.assertIn("hidden", json.dumps(pv["diff"] if "diff" in pv else pv))
        run.preview("project", "xhigh")
        self.sweep(run)
        self.assert_no_marker(run, "before the save")
        status, saved = run.save("project", "low")
        self.assertEqual(status, 200, saved)
        self.sweep(run)
        status, undone = run.undo(saved["edit"]["id"])
        self.assertEqual(status, 200, undone)
        self.sweep(run)
        self.assert_no_marker(run, "after save and undo")
        self.assertEqual(run.read("project"), MASK_PROJECT)
        self.assertEqual(run.read("local"), MASK_LOCAL)

    def test_an_effort_level_that_starts_with_sk_shows_as_hidden_everywhere(self):
        run = Run(self, project=MASK_PROJECT, local=MASK_LOCAL)
        listing = run.targets()
        text = json.dumps(listing)
        self.assertNotIn("sk-marker-effort-local", text)
        self.assertIn("hidden", text)
        status, settings = run.get("/api/settings")
        self.assertEqual(status, 200)
        self.assertNotIn("sk-marker-effort-local", json.dumps(settings))
        status, saved = run.save("project", "low")
        self.assertEqual(status, 200, saved)
        history = run.get("/api/edit/history")[1]
        self.assertNotIn("sk-marker-effort-local", json.dumps(history))
        self.assert_no_marker(run, "sk- effortLevel")

    def test_an_edit_of_a_value_that_starts_with_sk_hides_the_old_value(self):
        run = Run(self, project=b'{\n  "effortLevel": "sk-marker-effort-local"\n}\n')
        listing = run.targets()
        self.assertNotIn("sk-marker-effort-local", json.dumps(listing))
        found = [t for t in listing["targets"] if t["layer"] == "project"]
        self.assertEqual(len(found), 1, listing)
        status, saved = run.save("project", "low")
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved["edit"]["old_value"], "hidden")
        self.assertNotIn("sk-marker-effort-local", run.everything())
        for ledger in run.ledgers():
            with open(ledger, "rb") as fh:
                self.assertNotIn(b"sk-marker-effort-local", fh.read())


if __name__ == "__main__":
    unittest.main()

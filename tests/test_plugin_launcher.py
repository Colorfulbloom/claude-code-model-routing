"""Tests for the routing-dashboard plugin's launcher (plugins/routing-dashboard/bin/routing-dashboard).

Each class builds a throwaway plugin tree once, in a temp folder under the helpers' temp
base: bin/routing-dashboard (a copy of the launcher), .claude-plugin/plugin.json with
version 9.9.9, and payload/ filled by test_server.copy_tree. Every test gets its own data
folder and project folder, and runs the launcher with a throwaway HOME and
CLAUDE_CONFIG_DIR, --fixture, --port 0 and env BROWSER set to a stub script that appends
its argument to a file. A test never reads the real ~/.claude and never opens a browser.

Acting as a Claude Code session. The launcher counts env CLAUDE_PID only when it names an
ancestor of the launcher, and it drops an owner whose process has gone. So a "session" is
a long-lived fake process (Session below). It sets CLAUDE_PID to its own pid, reads one
JSON request per stdin line, runs the launcher as its child, and writes one JSON line
back with the exit code, stdout, stderr and elapsed time. The session outlives each
launcher run. Ending a session means killing that process (the launcher then prunes its
owner) or running session-end through it with the matching stdin. A run with no --session
is "by hand": the launcher is a plain child of the test, with no CLAUDE_PID.

Cleanup. Each test runs stop --all by hand, then kills any pid still named in a record
whose command holds the server path, then kills its sessions.
"""
import contextlib
import hashlib
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import select
import signal
import socket
import stat
import subprocess
import sys
import time
import unittest

import helpers
import test_server as ts

LAUNCHER_SRC = os.path.join(helpers.REPO, "plugins", "routing-dashboard", "bin", "routing-dashboard")
SESSION_SCRIPT = r'''
import json, os, subprocess, sys, time
os.environ["CLAUDE_PID"] = str(os.getpid())
launcher = sys.argv[1]
for line in sys.stdin:
    req = json.loads(line)
    env = dict(os.environ)
    env.update(req.get("env", {}))
    for name in req.get("unset", []):
        env.pop(name, None)
    start = time.time()
    proc = subprocess.run([sys.executable, launcher] + req["argv"], env=env, input=req.get("stdin"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    sys.stdout.write(json.dumps({"code": proc.returncode, "out": proc.stdout, "err": proc.stderr,
                                 "elapsed": time.time() - start}) + "\n")
    sys.stdout.flush()
'''
STUB = '#!/bin/sh\nprintf \'%s\\n\' "$1" >> "$STUB_OUT"\n'
STUB_FAIL = '#!/bin/sh\nprintf \'%s\\n\' "$1" >> "$STUB_OUT"\nexit 1\n'
KEY_RE = re.compile(r"#/settings\?edit=([A-Za-z0-9_-]+)")
URL_RE = re.compile(r"Routing Dashboard: http://127\.0\.0\.1:(\d+)/ \((.*)\)")
WAIT = 8


class Result:
    def __init__(self, code, out, err, elapsed=0.0):
        self.code = code
        self.out = out
        self.err = err
        self.elapsed = elapsed

    @property
    def port(self):
        return int(URL_RE.search(self.out).group(1))

    def __repr__(self):
        return "Result(code=%r, out=%r, err=%r)" % (self.code, self.out, self.err)


class Session:
    """A fake Claude Code process. Its pid is the CLAUDE_PID of every launcher it runs."""

    def __init__(self, case, name):
        self.sid = "sess-" + name
        self.case = case
        self.proc = subprocess.Popen([sys.executable, "-c", SESSION_SCRIPT, case.launcher],
                                     env=case.env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, universal_newlines=True)

    @property
    def pid(self):
        return self.proc.pid

    def run(self, argv, env=None, unset=(), stdin=None, timeout=90):
        req = {"argv": argv, "env": env or {}, "unset": list(unset), "stdin": stdin}
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            raise AssertionError("the fake session did not answer: %r" % (argv,))
        reply = json.loads(self.proc.stdout.readline())
        return Result(reply["code"], reply["out"], reply["err"], reply["elapsed"])

    def die(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(10)
        for fh in (self.proc.stdin, self.proc.stdout):
            try:
                fh.close()
            except OSError:
                pass


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def hold_port():
    """A listening socket on a free port. Returns (socket, port)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


def port_open(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for(check, timeout=WAIT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return check()


def get_root(port):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/")
        resp = conn.getresponse()
        resp.read()
        return resp.status, resp.getheader("Server")
    finally:
        conn.close()


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def project_id(path):
    return hashlib.sha1(os.path.realpath(path).encode()).hexdigest()[:12]


class LauncherCase(unittest.TestCase):
    """Base class: the plugin tree, the stubs and the run helpers."""

    @classmethod
    def setUpClass(cls):
        cls.base = ts.make_root("mr-plugin-launcher-")
        cls.plugin = os.path.join(cls.base, "plugin")
        os.makedirs(os.path.join(cls.plugin, "bin"))
        cls.launcher = os.path.join(cls.plugin, "bin", "routing-dashboard")
        with open(LAUNCHER_SRC, "rb") as src, open(cls.launcher, "wb") as dst:
            dst.write(src.read())
        os.chmod(cls.launcher, 0o755)
        ts.write_json(os.path.join(cls.plugin, ".claude-plugin", "plugin.json"),
                      {"name": "routing-dashboard", "version": "9.9.9"})
        cls.server = ts.copy_tree(os.path.join(cls.plugin, "payload"))
        cls.fixture = ts.fixture_copy(cls.base)
        cls.stub = ts.write(os.path.join(cls.base, "stub.sh"), STUB)
        cls.stub_fail = ts.write(os.path.join(cls.base, "stub-fail.sh"), STUB_FAIL)
        os.chmod(cls.stub, 0o755)
        os.chmod(cls.stub_fail, 0o755)
        cls.first_port = free_port()
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        helpers.rmtree_force(cls.base)

    def setUp(self):
        type(self).counter += 1
        self.dir = os.path.join(self.base, "t%d" % self.counter)
        self.data = os.path.join(self.dir, "data")
        self.proj = os.path.join(self.dir, "proj")
        os.makedirs(self.proj)
        self.stub_out = os.path.join(self.dir, "browser.txt")
        self.sessions = {}
        self.extra_procs = []
        self.addCleanup(self._cleanup)

    # ---- cleanup

    def _cleanup(self):
        try:
            if os.path.isdir(os.path.join(self.data, "servers")):
                subprocess.run([sys.executable, self.launcher, "--data", self.data, "--default-project",
                                self.proj, "stop", "--all"], env=self.env(), capture_output=True, timeout=60)
                for rec in self.records().values():
                    if pid_alive(rec["pid"]) and rec["server"] in self.command_of(rec["pid"]):
                        os.kill(rec["pid"], signal.SIGKILL)
        finally:
            for session in self.sessions.values():
                session.die()
            for proc in self.extra_procs:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(10)

    @staticmethod
    def command_of(pid):
        proc = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True,
                              universal_newlines=True)
        return proc.stdout

    # ---- running the launcher

    def env(self, **extra):
        env = ts.base_env(self.base, ROUTING_DASHBOARD_TEST_FIXTURES="1", BROWSER=self.stub,
                          STUB_OUT=self.stub_out, ROUTING_DASHBOARD_FIRST_PORT=str(self.first_port),
                          DISPLAY=":0")
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def globals(self, session=None, data=None, project=None, fixture=True):
        argv = ["--data", data or self.data, "--default-project", project or self.proj]
        if fixture:
            argv += ["--fixture", self.fixture]
        if session is not None:
            argv += ["--session", session]
        return argv

    def sess(self, name="a"):
        if name not in self.sessions:
            self.sessions[name] = Session(self, name)
        return self.sessions[name]

    def skill(self, argv, name="a", env=None, unset=(), data=None, project=None, sid=None):
        """Run the launcher as the skill does, inside the fake session called name."""
        session = self.sess(name)
        full = self.globals(session.sid if sid is None else sid, data, project) + list(argv)
        return session.run(full, env=env, unset=unset)

    def hand(self, argv, env=None, data=None, project=None, fixture=True, timeout=90):
        """Run the launcher by hand: a plain child of the test, with no --session."""
        full = [sys.executable, self.launcher] + self.globals(None, data, project, fixture) + list(argv)
        proc = subprocess.run(full, env=env if env is not None else self.env(), capture_output=True,
                              universal_newlines=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return Result(proc.returncode, proc.stdout, proc.stderr)

    def hook(self, stdin, name="a", env=None, use_env_data=True, data=None):
        """Run session-end the way the hook does, as a child of the fake session."""
        session = self.sess(name)
        argv = ["session-end"] if use_env_data else ["--data", data or self.data, "session-end"]
        env = dict(env or {})
        if use_env_data:
            env["CLAUDE_PLUGIN_DATA"] = data or self.data
        return session.run(argv, env=env, stdin=stdin)

    # ---- reading state

    def records(self, data=None):
        folder = os.path.join(data or self.data, "servers")
        out = {}
        if not os.path.isdir(folder):
            return out
        for name in sorted(os.listdir(folder)):
            if name.endswith(".json"):
                with open(os.path.join(folder, name), encoding="utf-8") as fh:
                    out[name[:-5]] = json.load(fh)
        return out

    def record(self, project=None):
        return self.records().get(project_id(project or self.proj))

    def stub_lines(self):
        if not os.path.exists(self.stub_out):
            return []
        with open(self.stub_out, encoding="utf-8") as fh:
            return fh.read().splitlines()

    def start(self, name="a", extra=(), **kw):
        res = self.skill(["start", "--port", "0"] + list(extra), name=name, **kw)
        self.assertEqual(res.code, 0, res)
        self.assertNotIn("error:", res.out)
        return res

    def log_text(self):
        folder = os.path.join(self.data, "logs")
        text = ""
        for name in os.listdir(folder):
            with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as fh:
                text += fh.read()
        return text

    def data_files(self, skip=("links",)):
        """Yield (path, bytes) for every file under the data folder, except the skipped top folders."""
        for dirpath, dirnames, filenames in os.walk(self.data):
            rel = os.path.relpath(dirpath, self.data)
            if rel.split(os.sep)[0] in skip:
                continue
            for name in filenames:
                path = os.path.join(dirpath, name)
                with open(path, "rb") as fh:
                    yield path, fh.read()


class StartTests(LauncherCase):
    def test_start_writes_the_record_and_opens_the_read_only_url(self):
        session = self.sess()
        res = self.start()
        port = res.port
        proj = os.path.realpath(self.proj)
        self.assertIn("Routing Dashboard: http://127.0.0.1:%d/ (%s)" % (port, proj), res.out)
        self.assertNotIn("edits on", res.out)
        self.assertEqual(res.err, "")
        rec = self.record()
        self.assertEqual(rec["port"], port)
        self.assertEqual(rec["project"], proj)
        self.assertIs(rec["edits"], False)
        self.assertRegex(rec["started"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        self.assertEqual(rec["plugin_root"], self.plugin)
        self.assertEqual(rec["plugin_version"], "9.9.9")
        self.assertEqual(rec["server"], self.server)
        self.assertEqual(rec["log"], os.path.join(self.data, "logs", project_id(self.proj) + ".log"))
        self.assertTrue(os.path.isfile(rec["log"]))
        self.assertEqual(len(rec["owners"]), 1)
        owner = rec["owners"][0]
        self.assertEqual(owner["claude_pid"], session.pid)
        self.assertTrue(owner["claude_started"])
        self.assertEqual(owner["session"], session.sid)
        self.assertIs(rec["manual"], False)
        self.assertIsNone(rec["link_file"])
        self.assertEqual(rec["fixture"], self.fixture)
        self.assertTrue(pid_alive(rec["pid"]))
        self.assertIn(self.server, self.command_of(rec["pid"]))
        status, header = get_root(port)
        self.assertEqual(status, 200)
        self.assertTrue(header.startswith("RoutingDashboard"))
        self.assertEqual(self.stub_lines(), ["http://127.0.0.1:%d/" % port])
        self.assertIn("Opened in your browser.", res.out)
        # modes: folders 0700, files 0600
        for sub in ("", "servers", "logs", "links"):
            self.assertEqual(mode(os.path.join(self.data, sub)), 0o700, sub)
        for path, _ in self.data_files(skip=()):
            self.assertEqual(mode(path), 0o600, path)

    def test_no_open_leaves_the_browser_alone(self):
        res = self.start(extra=["--no-open"])
        self.assertIn("Routing Dashboard: http://127.0.0.1:", res.out)
        self.assertFalse(os.path.exists(self.stub_out))
        self.assertNotIn("browser", res.out)

    def test_ssh_skips_the_browser_and_says_so(self):
        res = self.start(env={"SSH_CONNECTION": "10.0.0.1 22 10.0.0.2 22"})
        self.assertIn("Not opening a browser over SSH.", res.out)
        self.assertFalse(os.path.exists(self.stub_out))
        res = self.skill(["open"], env={"SSH_TTY": "/dev/ttys001"})
        self.assertIn("Not opening a browser over SSH.", res.out)
        self.assertFalse(os.path.exists(self.stub_out))

    def test_a_failing_browser_is_reported(self):
        res = self.start(env={"BROWSER": self.stub_fail})
        self.assertIn("Couldn't open a browser.", res.out)
        self.assertEqual(len(self.stub_lines()), 1)

    def test_default_start_word_and_open_action(self):
        res = self.skill(["--port", "0", "--no-open"])
        self.assertEqual(res.code, 0, res)
        port = res.port
        res = self.skill(["open"])
        self.assertIn("Routing Dashboard: http://127.0.0.1:%d/" % port, res.out)
        self.assertEqual(self.stub_lines(), ["http://127.0.0.1:%d/" % port])
        self.skill(["stop"])
        res = self.skill(["open"])
        self.assertEqual(res.code, 0)
        self.assertRegex(res.out, r"^error: no Routing Dashboard is running for .*run start")

    def test_a_second_start_reuses_the_server_and_adds_an_owner(self):
        first = self.start("a")
        pid = self.record()["pid"]
        second = self.start("b")
        self.assertEqual(second.port, first.port)
        rec = self.record()
        self.assertEqual(rec["pid"], pid)
        self.assertEqual([o["claude_pid"] for o in rec["owners"]],
                         [self.sess("a").pid, self.sess("b").pid])
        self.start("a")
        self.assertEqual(len(self.record()["owners"]), 2, "the same session is not added twice")
        self.assertEqual(len([n for n in os.listdir(os.path.join(self.data, "servers")) if n.endswith(".json")]), 1)

    def test_a_hand_run_sets_manual_and_adds_no_owner(self):
        res = self.hand(["start", "--port", "0", "--no-open"])
        self.assertEqual(res.code, 0, res)
        rec = self.record()
        self.assertIs(rec["manual"], True)
        self.assertEqual(rec["owners"], [])
        self.start("a")
        rec = self.record()
        self.assertIs(rec["manual"], True)
        self.assertEqual(len(rec["owners"]), 1)
        res = self.hand(["status"])
        self.assertIn("sessions manual", res.out)

    def test_a_busy_first_port_falls_back_and_says_so(self):
        holder, port = hold_port()
        self.addCleanup(holder.close)
        res = self.skill(["start", "--no-open"], env={"ROUTING_DASHBOARD_FIRST_PORT": str(port)})
        self.assertEqual(res.code, 0, res)
        self.assertIn("port %d is busy, using %d" % (port, res.port), res.out)
        self.assertNotEqual(res.port, port)
        self.assertEqual(self.record()["port"], res.port)
        self.assertEqual(get_root(res.port)[0], 200)

    def test_a_different_port_for_a_running_server_is_not_applied_silently(self):
        first = self.start()
        other = free_port()
        for argv in (["start", "--no-open", "--port", str(other)],
                     ["project", self.proj, "--no-open", "--port", str(other)]):
            res = self.skill(argv)
            self.assertEqual(res.code, 0, res)
            self.assertEqual(res.port, first.port)
            self.assertIn("already running on port %d; run stop first to change the port" % first.port, res.out)
            self.assertEqual(self.record()["port"], first.port)
        res = self.skill(["start", "--no-open", "--port", str(first.port)])
        self.assertNotIn("already running", res.out)

    def test_an_explicit_busy_port_is_an_error(self):
        holder, port = hold_port()
        self.addCleanup(holder.close)
        res = self.skill(["start", "--no-open", "--port", str(port)])
        self.assertEqual(res.code, 0, res)
        self.assertRegex(res.out, r"^error: port %d is in use" % port)
        self.assertIsNone(self.record())
        res = self.hand(["start", "--no-open", "--port", str(port)])
        self.assertEqual(res.code, 1)
        self.assertRegex(res.err, r"^error: port %d is in use" % port)
        self.assertEqual(res.out, "")

    def test_two_concurrent_starts_give_one_server(self):
        full = [sys.executable, self.launcher] + self.globals() + ["start", "--port", "0", "--no-open"]
        procs = [subprocess.Popen(full, env=self.env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, universal_newlines=True) for _ in range(2)]
        self.extra_procs.extend(procs)
        outs = [p.communicate(timeout=90) for p in procs]
        self.assertEqual([p.returncode for p in procs], [0, 0], outs)
        ports = {int(URL_RE.search(out).group(1)) for out, _ in outs}
        self.assertEqual(len(ports), 1, outs)
        names = [n for n in os.listdir(os.path.join(self.data, "servers")) if n.endswith(".json")]
        self.assertEqual(len(names), 1)
        self.assertEqual(get_root(ports.pop())[0], 200)

    def test_project_starts_a_second_server(self):
        first = self.start()
        other = os.path.join(self.dir, "other")
        os.makedirs(other)
        res = self.skill(["project", other, "--port", "0", "--no-open"])
        self.assertEqual(res.code, 0, res)
        self.assertIn("(%s)" % os.path.realpath(other), res.out)
        self.assertNotEqual(res.port, first.port)
        recs = self.records()
        self.assertEqual(len(recs), 2)
        self.assertEqual(self.record(other)["port"], res.port)
        self.assertEqual(self.record(other)["owners"][0]["claude_pid"], self.sess().pid)

    def test_project_resolves_a_relative_folder_against_the_default_project(self):
        os.makedirs(os.path.join(self.proj, "sub"))
        res = self.skill(["project", "sub", "--port", "0", "--no-open"])
        self.assertEqual(res.code, 0, res)
        self.assertIn("(%s)" % os.path.realpath(os.path.join(self.proj, "sub")), res.out)
        self.assertIsNotNone(self.record(os.path.join(self.proj, "sub")))
        self.assertIsNone(self.record())

    def test_project_refuses_a_missing_folder(self):
        res = self.skill(["project", "nope", "--port", "0"])
        self.assertEqual(res.code, 0)
        self.assertRegex(res.out, r"^error: not a folder: nope")
        res = self.hand(["project", "nope", "--port", "0"])
        self.assertEqual(res.code, 1)
        self.assertRegex(res.err, r"^error: not a folder: nope")
        self.assertEqual(self.records(), {})

    def test_a_log_over_one_megabyte_is_cut_when_the_server_starts(self):
        self.start()
        self.hand(["stop"])
        log = os.path.join(self.data, "logs", project_id(self.proj) + ".log")
        with open(log, "wb") as fh:
            fh.write(b"x" * 1100000 + b"\nlast old line\n")
        self.start()
        size = os.path.getsize(log)
        self.assertLess(size, 300 * 1024)
        self.assertIn("last old line", self.log_text())
        self.assertEqual(mode(log), 0o600)


class StopTests(LauncherCase):
    def test_stop_ends_the_server_and_removes_the_record(self):
        res = self.start()
        pid = self.record()["pid"]
        out = self.skill(["stop"])
        self.assertEqual(out.code, 0, out)
        self.assertIn("Stopped Routing Dashboard for %s (port %d)." % (os.path.realpath(self.proj), res.port), out.out)
        self.assertTrue(wait_for(lambda: not pid_alive(pid)))
        self.assertFalse(port_open(res.port))
        self.assertIsNone(self.record())
        out = self.skill(["stop"])
        self.assertIn("No Routing Dashboard is running for %s." % os.path.realpath(self.proj), out.out)

    def test_stop_all_stops_two_servers(self):
        first = self.start()
        other = os.path.join(self.dir, "other")
        os.makedirs(other)
        second = self.skill(["project", other, "--port", "0", "--no-open"])
        pids = [r["pid"] for r in self.records().values()]
        self.assertEqual(len(pids), 2)
        out = self.skill(["stop"])
        self.assertEqual(len(self.records()), 1, "plain stop ends only this project's server")
        out = self.skill(["stop", "--all"])
        self.assertEqual(self.records(), {})
        for pid in pids:
            self.assertTrue(wait_for(lambda pid=pid: not pid_alive(pid)))
        self.assertFalse(port_open(first.port))
        self.assertFalse(port_open(second.port))

    def test_stop_all_ends_a_manual_server_too(self):
        self.hand(["start", "--port", "0", "--no-open"])
        port = self.record()["port"]
        res = self.hand(["stop", "--all"])
        self.assertEqual(res.code, 0)
        self.assertTrue(wait_for(lambda: not port_open(port)))
        self.assertEqual(self.records(), {})

    def test_reload_keeps_the_port_and_the_owners(self):
        first = self.start("a")
        self.start("b")
        before = self.record()
        res = self.skill(["reload", "--no-open"])
        self.assertEqual(res.code, 0, res)
        after = self.record()
        self.assertEqual(after["port"], before["port"])
        self.assertEqual(res.port, before["port"])
        self.assertNotEqual(after["pid"], before["pid"])
        self.assertEqual(after["owners"], before["owners"])
        self.assertIs(after["manual"], before["manual"])
        self.assertTrue(wait_for(lambda: not pid_alive(before["pid"])))
        self.assertEqual(get_root(first.port)[0], 200)

    def test_reload_with_no_server_starts_one(self):
        res = self.skill(["reload", "--no-open"])
        self.assertEqual(res.code, 0, res)
        self.assertIn("Routing Dashboard: http://127.0.0.1:", res.out)
        self.assertEqual(len(self.records()), 1)


class StatusTests(LauncherCase):
    def test_status_all_lists_two_servers_and_flags_an_older_plugin(self):
        self.start()
        other = os.path.join(self.dir, "other")
        os.makedirs(other)
        self.skill(["project", other, "--port", "0", "--no-open"])
        rec = self.record(other)
        rec["plugin_root"] = "/work/old-plugin"
        ts.write_json(os.path.join(self.data, "servers", project_id(other) + ".json"), rec)
        res = self.skill(["status", "--all"])
        self.assertEqual(res.code, 0, res)
        lines = res.out.splitlines()
        mine = [l for l in lines if l.startswith(os.path.realpath(self.proj) + "  ")]
        theirs = [l for l in lines if l.startswith(os.path.realpath(other) + "  ")]
        self.assertEqual(len(mine), 1, res.out)
        self.assertEqual(len(theirs), 1, res.out)
        self.assertRegex(mine[0], r"  http://127\.0\.0\.1:\d+/  read-only  started \S+  plugin 9\.9\.9  sessions 1$")
        self.assertEqual(res.out.count("running code from an older plugin version, run reload"), 1)
        self.assertEqual(lines[lines.index(theirs[0]) + 1].strip(),
                         "running code from an older plugin version, run reload")
        plain = self.skill(["status"])
        self.assertEqual(len(plain.out.splitlines()), 1, plain.out)

    def test_status_with_nothing_running(self):
        res = self.skill(["status"])
        self.assertEqual(res.out.strip(), "No Routing Dashboard is running for %s." % os.path.realpath(self.proj))
        res = self.skill(["status", "--all"])
        self.assertEqual(res.out.strip(), "No Routing Dashboard is running.")

    def test_status_notes_a_first_port_held_by_something_else(self):
        holder = socket.socket()
        holder.bind(("127.0.0.1", self.first_port))
        holder.listen(1)
        self.addCleanup(holder.close)
        res = self.skill(["status"])
        self.assertIn("port %d is in use by a server this plugin didn't start" % self.first_port, res.out)
        holder.close()
        res = self.skill(["status"])
        self.assertNotIn("is in use", res.out)

    def test_a_dead_pid_is_removed_by_status(self):
        dead = subprocess.Popen(["true"])
        dead.wait()
        self.hand(["status"])
        self.write_record(dead.pid, 1, self.server)
        res = self.skill(["status"])
        self.assertIn("cleaned up a stopped server for %s" % os.path.realpath(self.proj), res.out)
        self.assertIn("No Routing Dashboard is running", res.out)
        self.assertIsNone(self.record())

    def write_record(self, pid, port, server, link=False):
        rec = {"pid": pid, "port": port, "project": os.path.realpath(self.proj), "edits": False,
               "started": "2026-01-01T00:00:00+00:00", "plugin_root": self.plugin,
               "plugin_version": "9.9.9", "server": server, "log": None, "owners": [], "manual": True,
               "link_file": None, "fixture": self.fixture}
        ts.write_json(os.path.join(self.data, "servers", project_id(self.proj) + ".json"), rec)
        if link:
            path = os.path.join(self.data, "links", project_id(self.proj) + ".url")
            ts.write(path, "http://127.0.0.1:1/#/settings?edit=abc\n")
            os.chmod(path, 0o600)
            return path

    def test_a_live_pid_that_is_not_a_server_is_removed_and_not_signalled(self):
        sleeper = subprocess.Popen(["sleep", "100"])
        self.extra_procs.append(sleeper)
        self.hand(["status"])
        link = self.write_record(sleeper.pid, 1, self.server, link=True)
        res = self.skill(["status"])
        self.assertIn("cleaned up a stopped server", res.out)
        self.assertIsNone(self.record())
        self.assertFalse(os.path.exists(link), "the link file goes with the record")
        time.sleep(0.3)
        self.assertIsNone(sleeper.poll(), "the process was not signalled")
        res = self.hand(["stop", "--all"])
        self.assertIsNone(sleeper.poll())

    def test_a_server_that_does_not_answer_is_stopped_and_forgotten(self):
        hung = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(100)", self.server])
        self.extra_procs.append(hung)
        self.hand(["status"])
        self.write_record(hung.pid, free_port(), self.server)
        res = self.skill(["status"])
        self.assertIn("stopped a server for %s that stopped answering" % os.path.realpath(self.proj), res.out)
        self.assertNotIn("cleaned up a stopped server", res.out)
        self.assertIsNone(self.record())
        self.assertTrue(wait_for(lambda: hung.poll() is not None), "ps matched the server path, so it is stopped")

    def test_a_corrupt_record_is_cleaned_up_without_a_crash(self):
        self.hand(["status"])
        bad = os.path.join(self.data, "servers", "abc123abc123.json")
        ts.write(bad, "this is not json {")
        res = self.skill(["status", "--all"])
        self.assertEqual(res.code, 0, res)
        self.assertIn("cleaned up an unreadable server record", res.out)
        self.assertNotIn("unexpected", res.out)
        self.assertFalse(os.path.exists(bad))

    def test_log_prints_the_last_lines(self):
        self.start()
        log = self.record()["log"]
        with open(log, "a", encoding="utf-8") as fh:
            for i in range(1, 51):
                fh.write("server line %d\n" % i)
            fh.write("secret http://127.0.0.1:1/#/settings?edit=planted-key\n")
        res = self.skill(["log"])
        self.assertEqual(res.code, 0)
        lines = res.out.splitlines()
        self.assertLessEqual(len(lines), 40)
        self.assertIn("server line 50", lines)
        self.assertIn("server line 12", lines)
        self.assertNotIn("server line 5", lines)
        self.assertNotIn("planted-key", res.out)
        self.assertEqual(lines[-1], "[line hidden]")

    def test_log_without_a_log(self):
        res = self.skill(["log"])
        self.assertEqual(res.out.strip(), "No log for %s." % os.path.realpath(self.proj))


class ArgumentTests(LauncherCase):
    BAD = [
        ["frobnicate"],
        ["start", "--port", "70000"],
        ["start", "--port", "x"],
        ["start", "--port", "-1"],
        ["start", "--all"],
        ["start", "now"],
        ["start", "--data", "x"],
        ["start", "--fixture", "x"],
        ["--port", "0", "--data", "x"],
        ["stop", "--port", "0"],
        ["stop", "--all", "--all"],
        ["start", "--port", "0", "--port", "1"],
        ["start", "--port"],
        ["project"],
        ["project", "a", "b"],
        ["status", "--no-open"],
        ["open", "--no-open"],
        ["log", "--all"],
        ["reload", "--port", "0"],
    ]

    def test_bad_arguments_by_hand_exit_2(self):
        for argv in self.BAD:
            res = self.hand(argv)
            self.assertEqual(res.code, 2, (argv, res))
            self.assertTrue(res.err.startswith("error: "), (argv, res))
            self.assertEqual(res.out, "", argv)
        self.assertFalse(os.path.exists(self.data), "a refused command creates nothing")

    def test_bad_arguments_in_skill_mode_exit_0_with_an_error_line(self):
        for argv in self.BAD:
            res = self.skill(argv, sid="")
            self.assertEqual(res.code, 0, (argv, res))
            self.assertTrue(res.out.startswith("error: "), (argv, res))
            self.assertEqual(len(res.out.splitlines()), 1, (argv, res))
            self.assertIn("usage: routing-dashboard", res.out)
            self.assertEqual(res.err, "", argv)

    def test_a_bad_session_id_is_refused(self):
        for sid in ("a b", "a;b", "x" * 129, "a\nb"):
            res = self.skill(["status"], sid=sid)
            self.assertEqual(res.code, 0, sid)
            self.assertTrue(res.out.startswith("error: --session takes"), (sid, res))
        res = self.skill(["status"], sid="x" * 128)
        self.assertTrue(res.out.startswith("No Routing Dashboard"), res)

    def test_fixture_needs_the_test_knob(self):
        res = self.hand(["status"], env=self.env(ROUTING_DASHBOARD_TEST_FIXTURES=None))
        self.assertEqual(res.code, 2)
        self.assertIn("--fixture is for tests only", res.err)
        res = self.hand(["status"], env=self.env(ROUTING_DASHBOARD_TEST_FIXTURES="0"))
        self.assertEqual(res.code, 2)
        res = self.hand(["status"], fixture=False, env=self.env(ROUTING_DASHBOARD_TEST_FIXTURES=None))
        self.assertEqual(res.code, 0, res)

    def test_fixture_must_be_a_folder(self):
        res = subprocess.run([sys.executable, self.launcher, "--data", self.data, "--fixture",
                              os.path.join(self.dir, "missing"), "status"], env=self.env(),
                             capture_output=True, universal_newlines=True)
        self.assertEqual(res.returncode, 2)

    def test_data_is_required(self):
        res = subprocess.run([sys.executable, self.launcher, "status"], env=self.env(),
                             capture_output=True, universal_newlines=True, cwd=self.proj)
        self.assertEqual(res.returncode, 1)
        self.assertIn("no data folder", res.stderr)
        res = subprocess.run([sys.executable, self.launcher, "--session", "s1", "status"], env=self.env(),
                             capture_output=True, universal_newlines=True, cwd=self.proj)
        self.assertEqual(res.returncode, 0)
        self.assertTrue(res.stdout.startswith("error: no data folder"))

    def test_data_and_project_fall_back_to_env_and_cwd(self):
        env = self.env(CLAUDE_PLUGIN_DATA=self.data)
        res = subprocess.run([sys.executable, self.launcher, "--default-project", "", "--fixture", self.fixture,
                              "start", "--port", "0", "--no-open"], env=env, capture_output=True,
                             universal_newlines=True, cwd=self.proj)
        self.assertEqual(res.returncode, 0, res)
        self.assertIsNotNone(self.record(), "an empty --default-project means the working folder")

    def test_the_sandbox_message(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores folder modes")
        parent = os.path.join(self.dir, "locked")
        os.makedirs(parent)
        os.chmod(parent, 0o500)
        self.addCleanup(os.chmod, parent, 0o755)
        data = os.path.join(parent, "data")
        res = self.skill(["start", "--port", "0"], data=data)
        self.assertEqual(res.code, 0, res)
        self.assertEqual(res.out, "error: Claude Code's sandbox blocked the dashboard launcher. "
                                  "See \"Sandbox\" in the routing-dashboard plugin README.\n")
        res = self.hand(["status"], data=data)
        self.assertEqual(res.code, 1)
        self.assertTrue(res.err.startswith("error: Claude Code's sandbox blocked"))
        self.assertFalse(os.path.exists(data))


class UnexpectedErrorTests(unittest.TestCase):
    """The wrapper prints the exception class and never its text."""

    @classmethod
    def setUpClass(cls):
        cls.base = ts.make_root("mr-plugin-launcher-unit-")
        path = os.path.join(cls.base, "routing-dashboard")
        with open(LAUNCHER_SRC, "rb") as src, open(path, "wb") as dst:
            dst.write(src.read())
        old = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            loader = importlib.machinery.SourceFileLoader("routing_dashboard_under_test", path)
            spec = importlib.util.spec_from_loader(loader.name, loader)
            cls.mod = importlib.util.module_from_spec(spec)
            loader.exec_module(cls.mod)
        finally:
            sys.dont_write_bytecode = old

    @classmethod
    def tearDownClass(cls):
        helpers.rmtree_force(cls.base)

    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        original = self.mod.run_action

        def boom(*args):
            raise RuntimeError("planted http://127.0.0.1:1/#/settings?edit=planted-key")

        self.mod.run_action = boom
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = self.mod.main(["--data", os.path.join(self.base, "data")] + argv)
        finally:
            self.mod.run_action = original
        return code, out.getvalue(), err.getvalue()

    def test_skill_mode_prints_one_line_and_exits_0(self):
        code, out, err = self.call(["--session", "s1", "status"])
        self.assertEqual((code, out, err), (0, "error: unexpected RuntimeError\n", ""))

    def test_by_hand_it_goes_to_stderr_and_exits_1(self):
        code, out, err = self.call(["status"])
        self.assertEqual((code, out, err), (1, "", "error: unexpected RuntimeError\n"))


class EditTests(LauncherCase):
    def assert_key_nowhere(self, key, *texts):
        for text in texts:
            self.assertNotIn(key, text)
            self.assertNotIn("edit=", text)
        for path, data in self.data_files():
            self.assertNotIn(key.encode(), data, path)
            self.assertNotIn(b"edit=", data, path)
        self.assertNotIn(key, self.log_text())

    def test_edits_open_the_link_and_keep_the_key_out_of_everything_else(self):
        res = self.skill(["edits", "--port", "0"])
        self.assertEqual(res.code, 0, res)
        lines = self.stub_lines()
        self.assertEqual(len(lines), 1, "the browser got the edit link and nothing else")
        match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/#/settings\?edit=([A-Za-z0-9_-]+)", lines[0])
        self.assertIsNotNone(match, lines)
        self.assertEqual(int(match.group(1)), res.port)
        self.assertIn("edits on", res.out)
        self.assertIn("Opened the edit link in your browser.", res.out)
        self.assertNotIn("#/settings", res.out)
        self.assert_key_nowhere(match.group(2), res.out, res.err)
        rec = self.record()
        self.assertIs(rec["edits"], True)
        self.assertIsNone(rec["link_file"])
        self.assertEqual(os.listdir(os.path.join(self.data, "links")), [])
        # the link works: the key is the server's own
        self.assertEqual(get_root(res.port)[0], 200)

    def test_key_file_saves_the_link_and_opens_no_browser(self):
        res = self.skill(["edits", "--port", "0", "--key-file"])
        self.assertEqual(res.code, 0, res)
        self.assertFalse(os.path.exists(self.stub_out))
        path = os.path.join(self.data, "links", project_id(self.proj) + ".url")
        self.assertIn("Edit link saved to %s. It holds a key, so delete it when you're done." % path, res.out)
        self.assertEqual(mode(path), 0o600)
        self.assertEqual(mode(os.path.join(self.data, "links")), 0o700)
        with open(path, encoding="utf-8") as fh:
            link = fh.read()
        match = re.fullmatch(r"http://127\.0\.0\.1:%d/#/settings\?edit=([A-Za-z0-9_-]+)\n" % res.port, link)
        self.assertIsNotNone(match, link)
        self.assertEqual(self.record()["link_file"], path)
        self.assert_key_nowhere(match.group(1), res.out, res.err)
        self.assertNotIn(match.group(1), json.dumps(self.record()))
        self.skill(["stop"])
        self.assertFalse(os.path.exists(path), "stop deletes the link file")

    def test_a_failing_browser_still_leaks_no_key(self):
        res = self.skill(["edits", "--port", "0"], env={"BROWSER": self.stub_fail})
        self.assertEqual(res.code, 0, res)
        key = KEY_RE.search("\n".join(self.stub_lines())).group(1)
        self.assertIn("Couldn't open a browser.", res.out)
        self.assertIn("Run edits --key-file to save the link to a file instead.", res.out)
        self.assert_key_nowhere(key, res.out, res.err)

    def test_ssh_skips_the_edit_link_and_leaks_no_key(self):
        res = self.skill(["edits", "--port", "0"], env={"SSH_TTY": "/dev/ttys001"})
        self.assertEqual(res.code, 0, res)
        self.assertIn("Not opening a browser over SSH.", res.out)
        self.assertIn("Run edits --key-file to save the link to a file instead.", res.out)
        self.assertFalse(os.path.exists(self.stub_out))
        self.assertNotIn("edit=", res.out + res.err + self.log_text())
        for path, data in self.data_files():
            self.assertNotIn(b"edit=", data, path)

    def test_no_open_skips_the_edit_link_too(self):
        res = self.skill(["edits", "--port", "0", "--no-open"])
        self.assertIn("--no-open", res.out)
        self.assertIn("Run edits --key-file", res.out)
        self.assertFalse(os.path.exists(self.stub_out))
        self.assertNotIn("edit=", res.out + res.err)

    def test_edits_on_a_running_server_restarts_it_with_a_new_key(self):
        first = self.start("a")
        self.start("b")
        before = self.record()
        res = self.skill(["edits", "--no-open", "--key-file"], name="a")
        self.assertEqual(res.code, 0, res)
        after = self.record()
        self.assertIs(after["edits"], True)
        self.assertNotEqual(after["pid"], before["pid"])
        self.assertEqual(after["port"], before["port"])
        self.assertEqual(after["owners"], before["owners"])
        self.assertTrue(wait_for(lambda: not pid_alive(before["pid"])))
        self.assertIn("edits on", res.out)
        self.assertEqual(res.port, first.port)

    def test_reload_keeps_edits_and_makes_a_new_link(self):
        self.skill(["edits", "--port", "0", "--key-file"])
        path = os.path.join(self.data, "links", project_id(self.proj) + ".url")
        with open(path, encoding="utf-8") as fh:
            old = fh.read()
        before = self.record()["pid"]
        res = self.skill(["reload", "--key-file"])
        self.assertEqual(res.code, 0, res)
        self.assertIs(self.record()["edits"], True)
        self.assertNotEqual(self.record()["pid"], before)
        with open(path, encoding="utf-8") as fh:
            self.assertNotEqual(fh.read(), old)
        self.assertNotIn("edit=", res.out)


class SessionEndTests(LauncherCase):
    def end(self, name="a", reason="other", sid=None, **kw):
        body = json.dumps({"session_id": sid or self.sess(name).sid, "reason": reason})
        return self.hook(body, name=name, **kw)

    def test_the_hook_returns_fast_and_prints_nothing(self):
        self.start()
        res = self.end()
        self.assertEqual((res.code, res.out, res.err), (0, "", ""))
        self.assertLess(res.elapsed, 1.0)

    def test_ending_the_first_owner_keeps_the_server_and_the_last_stops_it(self):
        started = self.start("a")
        self.start("b")
        pid = self.record()["pid"]
        self.end("a")
        self.assertTrue(wait_for(lambda: len(self.record()["owners"]) == 1))
        self.assertEqual(self.record()["owners"][0]["claude_pid"], self.sess("b").pid)
        self.assertTrue(pid_alive(pid))
        self.assertTrue(port_open(started.port))
        self.end("b")
        self.assertTrue(wait_for(lambda: not port_open(started.port)), "the server stops")
        self.assertTrue(wait_for(lambda: not pid_alive(pid)))
        self.assertTrue(wait_for(lambda: self.record() is None))

    def test_a_session_id_does_not_remove_an_owner_that_has_a_pid(self):
        self.start("a", sid="sess-shared")
        self.start("b", sid="sess-shared")
        self.assertEqual(len(self.record()["owners"]), 2)
        self.end("a", sid="sess-shared")
        self.assertTrue(wait_for(lambda: len(self.record()["owners"]) == 1))
        time.sleep(0.5)
        self.assertEqual([o["claude_pid"] for o in self.record()["owners"]], [self.sess("b").pid])

    def test_the_hidden_actions_are_refused_in_skill_mode(self):
        for argv in (["session-end"], ["_end", "--session", "sess-a"]):
            res = self.skill(argv)
            self.assertEqual(res.code, 0, res)
            self.assertTrue(res.out.startswith("error: "), res)
            self.assertIn("is not an action the skill can run", res.out)
            self.assertIn("usage:", res.out)

    def test_the_hook_takes_data_from_a_global_option_too(self):
        started = self.start("a")
        res = self.end("a", use_env_data=False)
        self.assertEqual((res.code, res.out), (0, ""))
        self.assertTrue(wait_for(lambda: not port_open(started.port)))

    def test_clear_and_resume_change_nothing(self):
        started = self.start("a")
        for reason in ("clear", "resume"):
            res = self.end("a", reason=reason)
            self.assertEqual((res.code, res.out, res.err), (0, "", ""))
        time.sleep(1.5)
        self.assertEqual(len(self.record()["owners"]), 1)
        self.assertTrue(port_open(started.port))

    def test_a_manual_server_survives_its_owners(self):
        self.hand(["start", "--port", "0", "--no-open"])
        started = self.start("a")
        self.end("a")
        self.assertTrue(wait_for(lambda: self.record()["owners"] == []))
        self.assertTrue(port_open(started.port))
        self.assertIs(self.record()["manual"], True)

    def test_the_session_id_alone_removes_an_owner_with_no_pid(self):
        self.start("a", unset=())
        rec = self.record()
        rec["owners"] = [{"claude_pid": None, "claude_started": None, "session": "sess-ghost"}]
        ts.write_json(os.path.join(self.data, "servers", project_id(self.proj) + ".json"), rec)
        self.end("a", sid="sess-ghost")
        self.assertTrue(wait_for(lambda: self.record() is None))

    def test_bad_input_exits_0_quietly(self):
        started = self.start("a")
        for body in ("", "not json", "[]", "{}", '{"session_id": "a b"}', '{"session_id": ""}',
                     '{"session_id": 5}', json.dumps({"session_id": "x" * 129})):
            res = self.hook(body)
            self.assertEqual((res.code, res.out, res.err), (0, "", ""), body)
        time.sleep(1.0)
        self.assertEqual(len(self.record()["owners"]), 1)
        self.assertTrue(port_open(started.port))

    def test_a_missing_data_folder_is_not_created(self):
        missing = os.path.join(self.dir, "never-made")
        res = self.hook(json.dumps({"session_id": "sess-a", "reason": "other"}), data=missing)
        self.assertEqual((res.code, res.out, res.err), (0, "", ""))
        res = self.hook(json.dumps({"session_id": "sess-a", "reason": "other"}), data=missing, use_env_data=False)
        self.assertEqual((res.code, res.out, res.err), (0, "", ""))
        time.sleep(1.0)
        self.assertFalse(os.path.exists(missing))

    def test_an_empty_servers_folder_is_fine(self):
        os.makedirs(os.path.join(self.data, "servers"))
        res = self.hook(json.dumps({"session_id": "sess-a", "reason": "other"}))
        self.assertEqual((res.code, res.out, res.err), (0, "", ""))
        time.sleep(1.0)
        self.assertLessEqual(set(os.listdir(os.path.join(self.data, "servers"))), {".lock"})
        self.assertFalse(os.path.exists(os.path.join(self.data, "logs")), "the hook creates no folders")


class PruningTests(LauncherCase):
    def test_a_dead_session_is_pruned_and_its_server_stopped(self):
        started = self.start("a")
        pid = self.record()["pid"]
        self.sess("a").die()
        res = self.skill(["status", "--all"], name="b")
        self.assertEqual(res.code, 0, res)
        self.assertIn("stopped the server for %s: every session that used it has ended"
                      % os.path.realpath(self.proj), res.out)
        self.assertIn("No Routing Dashboard is running.", res.out)
        self.assertTrue(wait_for(lambda: not pid_alive(pid)))
        self.assertFalse(port_open(started.port))
        self.assertIsNone(self.record())

    def test_a_dead_owner_is_dropped_while_a_live_one_keeps_the_server(self):
        started = self.start("a")
        self.start("b")
        self.sess("a").die()
        res = self.skill(["status"], name="b")
        self.assertIn("sessions 1", res.out)
        self.assertNotIn("stopped the server", res.out)
        self.assertEqual([o["claude_pid"] for o in self.record()["owners"]], [self.sess("b").pid])
        self.assertTrue(port_open(started.port))

    def test_a_manual_server_is_never_pruned(self):
        self.hand(["start", "--port", "0", "--no-open"])
        started = self.start("a")
        self.sess("a").die()
        res = self.skill(["status"], name="b")
        self.assertIn("sessions manual", res.out)
        self.assertEqual(self.record()["owners"], [])
        self.assertTrue(port_open(started.port))


if __name__ == "__main__":
    unittest.main()

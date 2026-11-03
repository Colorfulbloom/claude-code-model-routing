"""End-to-end checks of the routing-dashboard plugin with the real `claude` program. Opt in with MR_E2E=1.

The class installs the plugin from this repo into a throwaway HOME and CLAUDE_CONFIG_DIR, then runs the dashboard skill
through `claude -p` against a fake API on 127.0.0.1. Nothing reads or writes the real ~/.claude, no real API request
leaves the machine, and the browser is a stub (BROWSER=/usr/bin/true, plus --no-open on the start call).

Steps, in order, because each one builds on the last:
1. `claude plugin validate` passes on the repo root and on plugins/routing-dashboard. The docs say a marketplace
   validate does not open plugin files in other folders, so both run.
2. `claude plugin marketplace add <source>`, then `claude plugin install routing-dashboard@model-routing`, then
   `claude plugin list` names routing-dashboard. The source is MR_PLUGIN_SOURCE when set, else the local repo path.
3. `/routing-dashboard:dashboard status` reaches the fake API with the launcher's status text in the request body.
4. `/routing-dashboard:dashboard start --no-open` reaches the fake API with the dashboard URL. Once that `claude -p`
   process has exited, the plugin's SessionEnd hook must stop the server: its port closes within 10 seconds and no
   record is left under <config>/plugins/data/*/servers/.

The owner runs it with

    MR_E2E=1 /usr/bin/python3 -m unittest discover -s tests -p "test_plugin_e2e.py"

To test the copied install a colleague gets, point it at a pushed branch first:

    MR_E2E=1 MR_PLUGIN_SOURCE="Colorfulbloom/claude-code-model-routing#feature/routing-dashboard-plugin" \\
        /usr/bin/python3 -m unittest discover -s tests -p "test_plugin_e2e.py"

Importing this module starts nothing. The class skips unless MR_E2E=1, and again when `claude` is not on PATH.
"""
import glob
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import helpers

REPO = helpers.REPO
PLUGIN_DIR = os.path.join(REPO, "plugins", "routing-dashboard")
FAKE_KEY = "sk-ant-fake-000"
HOST = "127.0.0.1"
CLAUDE_TIMEOUT = 180
STATUS_TEXT = "No Routing Dashboard is running"


def text_sse(model):
    """A streamed reply that says "done" (modeled on dashboard/experiments/harness/fakeapi.py)."""
    ev = [("message_start", {"type": "message_start", "message": {
              "id": "msg_fake2", "type": "message", "role": "assistant", "model": model, "content": [],
              "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}}),
          ("content_block_start", {"type": "content_block_start", "index": 0,
                                   "content_block": {"type": "text", "text": ""}}),
          ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                   "delta": {"type": "text_delta", "text": "done"}}),
          ("content_block_stop", {"type": "content_block_stop", "index": 0}),
          ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                             "usage": {"output_tokens": 1}}),
          ("message_stop", {"type": "message_stop"})]
    return "".join("event: %s\ndata: %s\n\n" % (n, json.dumps(d)) for n, d in ev).encode()


class FakeApi:
    """A loopback HTTP server that saves every request body and answers "done"."""

    def __init__(self):
        self.bodies = []
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                size = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(size) if size else b""
                with outer.lock:
                    outer.bodies.append(raw.decode("utf-8", "replace"))
                try:
                    model = json.loads(raw or b"{}").get("model")
                except ValueError:
                    model = None
                out = text_sse(model)
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("content-length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            do_GET = do_POST

        self.server = ThreadingHTTPServer((HOST, 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def clear(self):
        with self.lock:
            self.bodies = []

    def text(self):
        with self.lock:
            return "\n".join(self.bodies)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


def port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((HOST, port)) == 0


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the plugin checks with the real claude")
class PluginE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.claude = shutil.which("claude")
        if not cls.claude:
            raise unittest.SkipTest("the claude program is not on PATH")
        cls.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-plugin-e2e-", dir=helpers._tmp_base()))
        cls.home = os.path.join(cls.root, "home")
        cls.cfg = os.path.join(cls.root, "home-cfg")
        cls.tmp = os.path.join(cls.root, "tmp")
        cls.project = os.path.join(cls.root, "project")
        for d in (cls.home, cls.cfg, cls.tmp, cls.project):
            os.makedirs(d, exist_ok=True)
        cls.api = FakeApi()

    @classmethod
    def tearDownClass(cls):
        cls.stop_leftover_servers()
        if getattr(cls, "api", None):
            cls.api.close()
        if getattr(cls, "root", None):
            helpers.rmtree_force(cls.root)

    @classmethod
    def records(cls):
        return sorted(glob.glob(os.path.join(cls.cfg, "plugins", "data", "*", "servers", "*.json")))

    @classmethod
    def stop_leftover_servers(cls):
        for path in cls.records():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    pid = json.load(fh).get("pid")
                if isinstance(pid, int) and pid > 1:
                    command = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)],
                                             capture_output=True, universal_newlines=True).stdout
                    if "dashboard/server.py" in command:
                        os.kill(pid, signal.SIGTERM)
            except (OSError, ValueError, AttributeError):
                pass

    def env(self):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": self.home,
               "CLAUDE_CONFIG_DIR": self.cfg, "TMPDIR": self.tmp, "LANG": "C", "LC_ALL": "C",
               "ANTHROPIC_API_KEY": FAKE_KEY, "ANTHROPIC_BASE_URL": "http://%s:%d" % (HOST, self.api.port),
               "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
               "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1",
               "DISABLE_AUTOUPDATER": "1", "BROWSER": "/usr/bin/true",
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        return env

    def claude_run(self, args, cwd=None):
        return subprocess.run([self.claude] + args, cwd=cwd or self.root, env=self.env(), capture_output=True,
                              text=True, timeout=CLAUDE_TIMEOUT, stdin=subprocess.DEVNULL)

    def assert_ok(self, proc, what):
        self.assertEqual(proc.returncode, 0, "%s failed\nstdout: %s\nstderr: %s" % (what, proc.stdout, proc.stderr))

    def test_1_validate_repo_and_plugin(self):
        for folder in (REPO, PLUGIN_DIR):
            self.assert_ok(self.claude_run(["plugin", "validate", folder]), "claude plugin validate " + folder)

    def test_2_install_from_the_marketplace(self):
        source = os.environ.get("MR_PLUGIN_SOURCE") or REPO
        self.assert_ok(self.claude_run(["plugin", "marketplace", "add", source]),
                       "claude plugin marketplace add " + source)
        self.assert_ok(self.claude_run(["plugin", "install", "routing-dashboard@model-routing"]),
                       "claude plugin install")
        listed = self.claude_run(["plugin", "list"])
        self.assert_ok(listed, "claude plugin list")
        self.assertIn("routing-dashboard", listed.stdout + listed.stderr)

    def test_3_status_text_reaches_the_request(self):
        self.api.clear()
        proc = self.claude_run(["-p", "/routing-dashboard:dashboard status"], cwd=self.project)
        self.assert_ok(proc, "claude -p status")
        self.assertIn(STATUS_TEXT, self.api.text())

    def test_4_start_then_session_end_stops_the_server(self):
        self.api.clear()
        proc = self.claude_run(["-p", "/routing-dashboard:dashboard start --no-open"], cwd=self.project)
        self.assert_ok(proc, "claude -p start")
        ports = [int(p) for p in re.findall(r"http://127\.0\.0\.1:(\d+)/", self.api.text())
                 if int(p) != self.api.port]
        self.assertTrue(ports, "no dashboard URL in the request body:\n" + self.api.text()[:2000])
        port = ports[0]
        # The claude -p process has exited, so its SessionEnd hook has run. The server must be gone.
        deadline = time.time() + 10
        while port_open(port) and time.time() < deadline:
            time.sleep(0.25)
        self.assertFalse(port_open(port), "port %d still open 10 seconds after the session ended" % port)
        self.assertEqual(self.records(), [], "a server record is left behind")


if __name__ == "__main__":
    unittest.main()

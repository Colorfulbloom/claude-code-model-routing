"""End-to-end checks of the dashboard shell in headless Chrome. Opt in with MR_E2E=1.

The server runs with --fixture on a temp folder with its own routing-dashboard.json, so nothing reads
the real ~/.claude. Chrome runs headless with a throwaway --user-data-dir under the helpers' temp base,
never the real profile. The test drives it over the DevTools protocol with a small WebSocket client,
because the page's Content-Security-Policy leaves no room for a script that the test injects.

The agent-name and branch half of the ticket's script-injection check waits for the Agents and
Sessions pages (U-12 and U-14). The project name and the route parameters are covered here.
"""
import base64
import http.client
import json
import os
import select
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import urllib.parse

import helpers
from test_server import make_root, start, write_json

INJECTED = "<script>window.__x=1</script>"
AGENT_INJECTED = "<script>window.__y=1</script>"
CHROME_CANDIDATES = (
    os.environ.get("MR_CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
)
CHROME = next((c for c in CHROME_CANDIDATES if c and os.path.exists(c)), None)

ROUTES = (
    ("#/overview", "overview"), ("", "overview"), ("#/nope", "overview"),
    ("#/agents", "agents"), ("#/agents/@main", "agent-detail"), ("#/agents/builder", "agent-detail"),
    ("#/models", "models"), ("#/sessions", "sessions"), ("#/sessions/abc-123", "session-detail"),
    ("#/settings", "settings"), ("#/settings/builder/effort", "trail"), ("#/settings/@main/effortLevel", "trail"),
    ("#/attention", "attention"), ("#/files", "files"), ("#/rules", "rules"),
)
VISIBLE = "[...document.querySelectorAll('main [data-page]')].filter(s => !s.hidden).map(s => s.dataset.page)"


class WebSocket:
    """Just enough RFC 6455 for the DevTools protocol: text messages, masked on the way out."""

    def __init__(self, host, port, path):
        self.sock = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, host, port, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise AssertionError("DevTools closed the handshake")
            buf += chunk
        head, _, self.buf = buf.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise AssertionError("DevTools refused the WebSocket: %r" % head[:80])

    def _read(self, count):
        while len(self.buf) < count:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("DevTools closed the socket")
            self.buf += chunk
        out, self.buf = self.buf[:count], self.buf[count:]
        return out

    def _send_frame(self, opcode, data):
        header = bytearray([0x80 | opcode])
        size = len(data)
        if size < 126:
            header.append(0x80 | size)
        elif size < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", size)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", size)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def send(self, text):
        self._send_frame(0x1, text.encode("utf-8"))

    def pending(self, wait):
        return bool(self.buf) or bool(select.select([self.sock], [], [], wait)[0])

    def recv(self):
        message = b""
        while True:
            b1, b2 = self._read(2)
            opcode, size = b1 & 0x0F, b2 & 0x7F
            if size == 126:
                size = struct.unpack(">H", self._read(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(size)
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0x8:
                raise EOFError("DevTools closed the socket")
            message += payload
            if b1 & 0x80:
                return message.decode("utf-8")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Page:
    """One browser tab over the DevTools protocol."""

    def __init__(self, ws):
        self.ws = ws
        self.next_id = 0
        self.events = []

    def call(self, method, **params):
        self.next_id += 1
        want = self.next_id
        self.ws.send(json.dumps({"id": want, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == want:
                if "error" in msg:
                    raise AssertionError("%s failed: %s" % (method, msg["error"]))
                return msg.get("result", {})
            self.events.append(msg)

    def drain(self, wait=0.3):
        while self.ws.pending(wait):
            self.events.append(json.loads(self.ws.recv()))
            wait = 0.05

    def eval(self, expression):
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise AssertionError("page script failed: %s" % json.dumps(result["exceptionDetails"])[:400])
        return result["result"].get("value")

    def wait_for(self, expression, timeout=20):
        deadline = time.time() + timeout
        value = None
        while time.time() < deadline:
            value = self.eval(expression)
            if value:
                return value
            time.sleep(0.1)
        raise AssertionError("timed out waiting for %s (last value %r)" % (expression, value))

    def key(self, name):
        for kind in ("keyDown", "keyUp"):
            self.call("Input.dispatchKeyEvent", type=kind, key=name, code=name, windowsVirtualKeyCode=27 if name == "Escape" else 0)

    def open(self, url, width, height=900):
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
        self.call("Page.navigate", url="about:blank")
        time.sleep(0.2)
        self.call("Page.navigate", url=url)
        self.wait_for("document.documentElement.getAttribute('data-rendered') !== null")

    def go(self, hash_, expect_section):
        self.eval("location.hash = %s" % json.dumps(hash_ or "#/overview"))
        self.wait_for("JSON.stringify(%s) === %s" % (VISIBLE, json.dumps(json.dumps([expect_section]))))

    def messages(self):
        out = []
        for event in self.events:
            params = event.get("params", {})
            if event.get("method") == "Log.entryAdded":
                out.append(params["entry"].get("text", ""))
            elif event.get("method") == "Runtime.consoleAPICalled":
                out.append(" ".join(str(a.get("value", a.get("description", ""))) for a in params.get("args", [])))
            elif event.get("method") == "Runtime.exceptionThrown":
                out.append("EXCEPTION " + json.dumps(params.get("exceptionDetails", {}))[:400])
        return out


class Chrome:
    """A headless Chrome with a throwaway profile under parent_dir, and one tab driven over the DevTools protocol.

    Attributes: proc, ws, page, err_path (Chrome's stderr) and profile. close() undoes all of it.
    """

    def __init__(self, parent_dir, extra_args=()):
        self.ws = None
        self.proc = None
        self.err_fh = None
        self.profile = tempfile.mkdtemp(prefix="mr-chrome-", dir=parent_dir)
        self.err_path = os.path.join(self.profile, "chrome.err")
        self.err_fh = open(self.err_path, "wb")
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", "--remote-debugging-port=0", "--user-data-dir=" + os.path.join(self.profile, "data"),
             "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--disable-extensions",
             "--enable-logging=stderr", "--v=0"] + list(extra_args) + ["about:blank"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self.err_fh)
        try:
            port = self._debug_port()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
            conn.request("GET", "/json/list")
            targets = [t for t in json.loads(conn.getresponse().read()) if t.get("type") == "page"]
            conn.close()
            if not targets:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
                conn.request("PUT", "/json/new?about:blank")
                targets = [json.loads(conn.getresponse().read())]
                conn.close()
            path = urllib.parse.urlparse(targets[0]["webSocketDebuggerUrl"]).path
            self.ws = WebSocket("127.0.0.1", port, path)
            self.page = Page(self.ws)
            for method in ("Page.enable", "Runtime.enable", "Log.enable"):
                self.page.call(method)
        except BaseException:
            self.close()
            raise

    def _debug_port(self):
        active = os.path.join(self.profile, "data", "DevToolsActivePort")
        deadline = time.time() + 30
        while time.time() < deadline:
            if os.path.exists(active):
                with open(active, encoding="utf-8") as fh:
                    first = fh.readline().strip()
                if first.isdigit():
                    return int(first)
            if self.proc.poll() is not None:
                raise AssertionError("Chrome exited early: %s" % open(self.err_path, errors="replace").read()[-400:])
            time.sleep(0.1)
        raise AssertionError("Chrome did not open a debugging port")

    def close(self):
        if self.ws:
            self.ws.close()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)
        if self.err_fh:
            self.err_fh.close()
        helpers.rmtree_force(self.profile)


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class ShellE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_root("mr-e2e-")
        work = os.path.join(cls.root, "work")
        os.makedirs(os.path.join(work, "injected", ".claude"))
        folder = os.path.join(cls.root, "fixture")
        os.makedirs(os.path.join(folder, "project"))
        write_json(os.path.join(folder, "config", "routing-dashboard.json"), {"projects": [
            {"name": INJECTED, "path": os.path.join(work, "injected")},
            {"name": "Gone", "path": os.path.join(work, "does-not-exist")},
        ]})
        cls.srv = start(cls.root, ["--fixture", folder])
        cls.base = "http://127.0.0.1:%d/" % cls.srv.port
        try:
            cls.chrome = Chrome(helpers._tmp_base())
        except BaseException:
            cls.tearDownClass()
            raise
        cls.page = cls.chrome.page
        cls.err_path = cls.chrome.err_path

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "chrome", None):
            cls.chrome.close()
        if getattr(cls, "srv", None):
            cls.srv.stop()
        if getattr(cls, "root", None):
            helpers.rmtree_force(cls.root)

    def open(self, hash_="#/overview", width=1440):
        self.page.open(self.base + hash_, width)

    # ------------------------------------------------------------ boot

    def test_boot_sets_the_flags_at_both_widths(self):
        for width in (1440, 375):
            self.open("#/overview", width)
            self.page.wait_for("document.documentElement.getAttribute('data-rendered') === '1'")
            self.assertEqual(self.page.eval("document.documentElement.getAttribute('data-ox')"), "0", width)
            self.assertEqual(self.page.eval("innerWidth"), width)

    def test_project_name_is_text_and_nothing_is_injected(self):
        self.open()
        options = self.page.eval("[...document.querySelectorAll('#project option')].map(o => o.textContent)")
        self.assertIn(INJECTED, options)
        self.assertEqual(options[-1], "All projects")
        self.assertEqual(self.page.eval("document.querySelectorAll('script:not([src])').length"), 0)
        self.assertEqual(self.page.eval("typeof window.__x"), "undefined")
        self.assertEqual(self.page.eval("document.querySelectorAll('#project option script, .topbar script').length"), 0)

    def test_agent_route_parameter_is_text(self):
        self.open("#/agents/" + urllib.parse.quote(AGENT_INJECTED, safe=""))
        self.page.wait_for("JSON.stringify(%s) === '[\"agent-detail\"]'" % VISIBLE)
        self.assertEqual(self.page.eval("document.querySelector('[data-page=agent-detail] h1').textContent"), AGENT_INJECTED)
        self.assertEqual(self.page.eval("document.querySelectorAll('script:not([src])').length"), 0)
        self.assertEqual(self.page.eval("typeof window.__y"), "undefined")

    def test_missing_folder_wording(self):
        self.open()
        options = self.page.eval("[...document.querySelectorAll('#project option')].map(o => o.textContent)")
        self.assertIn("Gone, folder not found", options)
        self.assertEqual(self.page.eval("document.querySelector('#project').value"), self.page.eval(
            "[...document.querySelectorAll('#project option')][0].value"))

    def test_version_chip_reads_unknown(self):
        self.open("#/overview", 1440)
        self.assertEqual(self.page.eval("(() => { const c = document.querySelector('.vchip .vc-long'); return getComputedStyle(c).display !== 'none' ? c.textContent : null })()"),
                         "Claude Code version unknown")
        self.open("#/overview", 375)
        self.assertEqual(self.page.eval("(() => { const c = document.querySelector('.vchip .vc-short'); return getComputedStyle(c).display !== 'none' ? c.textContent : null })()"),
                         "Version unknown")

    # ------------------------------------------------------------ routes

    def test_every_route_shows_its_section(self):
        for width in (1440, 375):
            self.open("#/overview", width)
            for hash_, section in ROUTES:
                self.page.go(hash_, section)
                self.assertEqual(self.page.eval("document.querySelectorAll('main [data-page]').length"), 12)
                self.assertTrue(self.page.eval("document.querySelector('[data-page=%s] h1').textContent.length > 0" % section), hash_)
        self.page.go("#/overview?project=all", "all-projects")
        self.assertEqual(self.page.eval("document.querySelector('.sb-g').textContent"), "All projects")
        self.assertEqual(self.page.eval("document.querySelector('.nv.is-active').textContent"), "Overview")

    def test_unknown_route_goes_to_overview_and_theme_flag_sets_the_theme(self):
        self.open("#/nope?theme=dark")
        self.page.wait_for("JSON.stringify(%s) === '[\"overview\"]'" % VISIBLE)
        self.assertEqual(self.page.eval("location.hash"), "#/overview?theme=dark")
        self.assertEqual(self.page.eval("document.documentElement.getAttribute('data-theme')"), "dark")

    # ------------------------------------------------------------ data

    def api_requests(self, needle=""):
        return self.page.eval("performance.getEntriesByType('resource').map(e => new URL(e.name).pathname + new URL(e.name).search)"
                              ".filter(u => u.startsWith('/api/') && u.includes(%s))" % json.dumps(needle))

    def test_range_fetches_nothing_and_project_fetches_once(self):
        self.open()
        self.page.wait_for("document.documentElement.getAttribute('data-rendered') === '1'")
        before = self.api_requests()
        for label in ("Today", "7 days", "30 days"):
            self.page.eval("[...document.querySelectorAll('[data-page=overview] .seg')].find(b => b.textContent === %s).click()" % json.dumps(label))
            self.page.wait_for("document.querySelector('[data-page=overview] .seg.is-active').textContent === %s" % json.dumps(label))
        self.assertEqual(self.api_requests(), before)
        gone = self.page.eval("[...document.querySelectorAll('#project option')].find(o => o.textContent.startsWith('Gone')).value")
        for key in (gone, "all", gone):
            self.page.eval("(() => { const s = document.querySelector('#project'); s.value = %s; s.dispatchEvent(new Event('change')) })()" % json.dumps(key))
            self.page.wait_for("document.querySelector('#project').value === %s" % json.dumps(key))
            time.sleep(0.3)
        self.assertEqual(len(self.api_requests("project=" + gone)), 2)
        self.assertEqual(len(self.api_requests("project=all")), 2)
        self.assertEqual(len(self.api_requests("/api/projects")), 1)

    # ------------------------------------------------------------ the menu at 375

    def test_menu_button_and_aria_expanded(self):
        self.open("#/overview", 375)
        self.page.wait_for("document.documentElement.getAttribute('data-rendered') === '1'")
        state = "document.querySelector('.btn.menu').getAttribute('aria-expanded')"
        shown = "document.querySelector('#sidebar').getBoundingClientRect().width > 0"
        # What is inert: each child of .main and of the top bar, by class, and whether .main or the button is.
        inert = ("[...document.querySelectorAll('.main > *, .topbar > *')]"
                 ".filter(e => e.hasAttribute('inert')).map(e => e.className).sort()")
        button_free = ("!document.querySelector('.main').hasAttribute('inert') && "
                       "!document.querySelector('.topbar').hasAttribute('inert') && "
                       "!document.querySelector('.btn.menu').hasAttribute('inert')")
        on_button = "document.activeElement === document.querySelector('.btn.menu')"
        behind = ["content", "tb-right", "tb-title"]
        menu = "document.querySelector('.btn.menu')"
        self.assertEqual(self.page.eval(state), "false")
        self.assertFalse(self.page.eval(shown))
        self.assertEqual(self.page.eval(inert), [])

        # Open: the panel sits below the top bar, the page behind it is inert, the button is not.
        self.page.eval(menu + ".click()")
        self.assertEqual(self.page.eval(state), "true")
        self.assertTrue(self.page.eval(shown))
        self.assertEqual(self.page.eval(inert), behind)
        self.assertTrue(self.page.eval(button_free))
        self.assertAlmostEqual(
            self.page.eval("document.querySelector('#sidebar').getBoundingClientRect().top"),
            self.page.eval("document.querySelector('#topbar').getBoundingClientRect().bottom"), delta=1)

        # The button closes the menu and keeps focus.
        self.page.eval(menu + ".click()")
        self.assertEqual(self.page.eval(state), "false")
        self.assertFalse(self.page.eval(shown))
        self.assertEqual(self.page.eval(inert), [])
        self.assertTrue(self.page.eval(on_button))

        # Escape.
        self.page.eval(menu + ".click()")
        self.assertEqual(self.page.eval(inert), behind)
        self.page.key("Escape")
        self.assertEqual(self.page.eval(state), "false")
        self.assertFalse(self.page.eval(shown))
        self.assertEqual(self.page.eval(inert), [])
        self.assertTrue(self.page.eval(on_button))

        # A click outside the panel and the button.
        self.page.eval(menu + ".click()")
        self.page.eval("document.querySelector('.app').click()")
        self.assertEqual(self.page.eval(state), "false")
        self.assertEqual(self.page.eval(inert), [])
        self.assertTrue(self.page.eval(on_button))

        # A hash change from outside the panel.
        self.page.eval(menu + ".click()")
        self.page.eval("location.hash = '#/models'")
        self.page.wait_for("JSON.stringify(%s) === '[\"models\"]'" % VISIBLE)
        self.assertEqual(self.page.eval(state), "false")
        self.assertEqual(self.page.eval(inert), [])
        self.assertTrue(self.page.eval(on_button))

        # A nav link.
        self.page.eval(menu + ".click()")
        self.page.eval("document.querySelectorAll('#sidebar .nv')[1].click()")
        self.assertEqual(self.page.eval(state), "false")
        self.assertEqual(self.page.eval(inert), [])
        self.assertTrue(self.page.eval(on_button))
        self.page.wait_for("JSON.stringify(%s) === '[\"agents\"]'" % VISIBLE)

    def test_menu_button_is_hidden_on_a_wide_screen(self):
        self.open("#/overview", 1440)
        self.assertEqual(self.page.eval("getComputedStyle(document.querySelector('.btn.menu')).display"), "none")
        self.assertTrue(self.page.eval("document.querySelector('#sidebar').getBoundingClientRect().width > 0"))

    # ------------------------------------------------------------ Content-Security-Policy

    def test_zz_no_csp_violation_or_script_error(self):
        for width in (1440, 375):
            self.open("#/overview", width)
            for hash_, section in ROUTES[3:]:
                self.page.go(hash_, section)
        self.page.drain()
        bad = [m for m in self.page.messages() if "Content Security Policy" in m or "Refused to" in m or m.startswith("EXCEPTION")]
        self.assertEqual(bad, [])
        with open(self.err_path, encoding="utf-8", errors="replace") as fh:
            stderr = fh.read()
        self.assertNotIn("Content Security Policy", stderr)
        self.assertNotIn("Refused to", stderr)


if __name__ == "__main__":
    unittest.main()

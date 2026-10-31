"""Tests for the read-only local server (dashboard/server.py).

Every server runs in a temp folder under the helpers' temp base, in its own
process, with an explicit environment: a throwaway HOME and CLAUDE_CONFIG_DIR
and --port 0. A test never reads the real ~/.claude. Secrets in these tests are
made-up strings that start with "planted-" or "sk-planted-".
"""
import contextlib
import hashlib
import http.client
import inspect
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import helpers

DASHBOARD = os.path.join(helpers.REPO, "dashboard")
sys.path.insert(0, DASHBOARD)
sys.path.insert(0, helpers.REPO)
import api_settings  # noqa: E402
import collect  # noqa: E402
import install  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402

FIXTURE_DIR = os.path.join(helpers.REPO, "tests", "fixtures", "resolution")
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'")
REAL_MANAGED = ("/Library/Application Support/ClaudeCode", "/etc/claude-code")
RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
START_TIMEOUT = 25


def make_root(prefix="mr-server-"):
    root = os.path.realpath(tempfile.mkdtemp(prefix=prefix, dir=helpers._tmp_base()))
    return root


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def write_json(path, data):
    return write(path, json.dumps(data, indent=2))


def copy_tree(dest):
    """Copy the modules the server loads into dest, with no __pycache__.

    dest/agent_md.py, dest/install.py (api_settings.files plans with it) and
    dest/dashboard/*.py, *.json and static/. Returns the path of the copied
    server.py.
    """
    os.makedirs(os.path.join(dest, "dashboard"))
    shutil.copy2(os.path.join(helpers.REPO, "agent_md.py"), dest)
    shutil.copy2(os.path.join(helpers.REPO, "install.py"), dest)
    for name in os.listdir(DASHBOARD):
        full = os.path.join(DASHBOARD, name)
        if os.path.isfile(full) and name.endswith((".py", ".json")):
            shutil.copy2(full, os.path.join(dest, "dashboard", name))
    shutil.copytree(os.path.join(DASHBOARD, "static"), os.path.join(dest, "dashboard", "static"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    return os.path.join(dest, "dashboard", "server.py")


def base_env(root, **extra):
    home = os.path.join(root, "home")
    cfg = os.path.join(root, "home-cfg")
    tmp = os.path.join(root, "tmp")
    for d in (home, cfg, tmp):
        os.makedirs(d, exist_ok=True)
    env = {"HOME": home, "CLAUDE_CONFIG_DIR": cfg, "PATH": "/usr/bin:/bin", "LANG": "C",
           "LC_ALL": "C", "TMPDIR": tmp}
    env.update(extra)
    return env


class Proc:
    """A server process. Output goes to files outside every folder a test watches."""

    def __init__(self, root, argv, env, cwd=None, name="srv"):
        logs = os.path.join(root, "logs")
        os.makedirs(logs, exist_ok=True)
        self.out_path = os.path.join(logs, name + ".out")
        self.err_path = os.path.join(logs, name + ".err")
        self.out_fh = open(self.out_path, "wb")
        self.err_fh = open(self.err_path, "wb")
        self.proc = subprocess.Popen(argv, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                                     stdout=self.out_fh, stderr=self.err_fh)
        self.url = None
        self.port = None

    def wait_for_url(self):
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            text = self.stdout()
            if "\n" in text:
                self.url = text.splitlines()[0]
                m = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/", self.url)
                if not m:
                    raise AssertionError("unexpected first stdout line: %r" % self.url)
                self.port = int(m.group(1))
                return self
            if self.proc.poll() is not None:
                raise AssertionError("server exited early (%s): %s" % (
                    self.proc.returncode, self.stderr()))
            time.sleep(0.05)
        raise AssertionError("server did not print its URL")

    def stdout(self):
        with open(self.out_path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")

    def stderr(self):
        with open(self.err_path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)
        self.out_fh.close()
        self.err_fh.close()

    def request(self, method, path, headers=None, body=None, host="default"):
        """Send one request. host="default" lets http.client add Host; None sends none."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            skip = host != "default"
            conn.putrequest(method, path, skip_host=skip, skip_accept_encoding=True)
            if host not in ("default", None):
                conn.putheader("Host", host)
            for name, value in (headers or {}).items():
                conn.putheader(name, value)
            if body is not None:
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            resp = conn.getresponse()
            data = resp.read()
            heads = {k.lower(): v for k, v in resp.getheaders()}
            return resp.status, heads, data
        finally:
            conn.close()

    def raw(self, payload):
        """Send raw bytes and return everything the server answers."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=15) as sock:
            sock.sendall(payload)
            chunks = []
            while True:
                try:
                    chunk = sock.recv(65536)
                except OSError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
        return b"".join(chunks)


def start(root, extra_args=(), env=None, cwd=None, script=None, python_args=(), name="srv"):
    # A server started without --fixture would read the real managed folder.
    if "--fixture" not in extra_args:
        raise AssertionError("tests start the server with --fixture only")
    argv = [sys.executable] + list(python_args) + [script or os.path.join(DASHBOARD, "server.py"),
                                                  "--port", "0"] + list(extra_args)
    proc = Proc(root, argv, env if env is not None else base_env(root), cwd=cwd, name=name)
    try:
        return proc.wait_for_url()
    except Exception:
        proc.stop()
        raise


def all_text(obj):
    """Every string in obj, keys included. Tuple keys are walked part by part."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from all_text(key)
            yield from all_text(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from all_text(item)


def hash_tree(*roots):
    """Map every path under roots to its kind, content hash, mode and mtime."""
    out = {}
    for root in roots:
        out[root] = ("root", os.path.isdir(root))
        for dirpath, dirnames, filenames in os.walk(root):
            for name in dirnames + filenames:
                full = os.path.join(dirpath, name)
                st = os.lstat(full)
                if os.path.islink(full):
                    out[full] = ("link", os.readlink(full))
                elif os.path.isdir(full):
                    out[full] = ("dir", st.st_mode)
                else:
                    with open(full, "rb") as fh:
                        digest = hashlib.sha256(fh.read()).hexdigest()
                    out[full] = ("file", digest, st.st_mode, st.st_mtime_ns)
    return out


def local_non_loopback_addresses():
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # a UDP connect sends nothing
            found.add(sock.getsockname()[0])
    except OSError:
        pass
    return sorted(a for a in found if not a.startswith("127.") and a != "0.0.0.0")


class TempCase(unittest.TestCase):
    """Gives each test a temp root and stops every server it started."""

    def setUp(self):
        self.root = make_root()
        self._procs = []
        self.addCleanup(helpers.rmtree_force, self.root)
        self.addCleanup(self._stop_all)

    def _stop_all(self):
        for proc in self._procs:
            proc.stop()

    def start(self, *args, **kwargs):
        proc = start(self.root, *args, **kwargs)
        self._procs.append(proc)
        return proc


def fixture_copy(root, case="env-block-over-shell", name="fixture"):
    dest = os.path.join(root, name)
    shutil.copytree(os.path.join(FIXTURE_DIR, case), dest)
    os.remove(os.path.join(dest, "expected.json"))
    return dest


# --------------------------------------------------------------------------
# Requests: Host, Origin, methods, headers, HEAD

class RequestRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_root()
        cls.fixture = fixture_copy(cls.root)
        cls.srv = start(cls.root, ["--fixture", cls.fixture])
        cls.port = cls.srv.port

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
        helpers.rmtree_force(cls.root)

    def assert_refusal(self, status, heads, body):
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body), {"error": "forbidden"})
        self.assertNotIn(b"entries", body)
        self.assertNotIn("access-control-allow-origin", heads)

    def test_startup_url_is_loopback(self):
        self.assertEqual(self.srv.url, "http://127.0.0.1:%d/" % self.port)

    def test_good_hosts_are_served(self):
        for host in ("127.0.0.1:%d" % self.port, "localhost:%d" % self.port,
                     "LOCALHOST:%d" % self.port):
            status, _, body = self.srv.request("GET", "/api/settings", host=host)
            self.assertEqual(status, 200, host)
            self.assertIn("entries", json.loads(body))

    def test_bad_hosts_are_refused_on_every_path(self):
        hosts = ["127.0.0.1:%d" % (self.port + 1), "evil.example", "evil.example:%d" % self.port,
                 "127.0.0.1", "localhost", "planted-host.example:%d" % self.port, "", None]
        for host in hosts:
            for path in ("/", "/api/settings", "/api/usage", "/static/tokens.css", "/nope", "/api/nope"):
                status, heads, body = self.srv.request("GET", path, host=host)
                self.assert_refusal(status, heads, body)
                self.assertNotIn(b"planted-host", body)
                self.assertNotIn(b"evil.example", body)

    def test_duplicate_host_is_refused(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.putrequest("GET", "/api/settings", skip_host=True)
        conn.putheader("Host", "127.0.0.1:%d" % self.port)
        conn.putheader("Host", "127.0.0.1:%d" % self.port)
        conn.endheaders()
        resp = conn.getresponse()
        self.assertEqual(resp.status, 403)
        conn.close()

    def test_host_is_checked_before_method(self):
        for method in ("POST", "PROPFIND", "GET", "HEAD"):
            status, _, _ = self.srv.request(method, "/api/settings", host="evil.example")
            self.assertEqual(status, 403, method)

    def test_origin_rules(self):
        good = ("http://127.0.0.1:%d" % self.port, "http://localhost:%d" % self.port)
        for origin in good:
            status, heads, _ = self.srv.request("GET", "/api/settings", {"Origin": origin})
            self.assertEqual(status, 200, origin)
            self.assertNotIn("access-control-allow-origin", heads)
        bad = ("http://evil.example", "null", "http://127.0.0.1", "https://127.0.0.1:%d" % self.port,
               "http://127.0.0.1:%d" % (self.port + 1), "http://planted-origin.example", "")
        for origin in bad:
            status, heads, body = self.srv.request("GET", "/api/settings", {"Origin": origin})
            self.assert_refusal(status, heads, body)
            self.assertNotIn(b"planted-origin", body)
            self.assertNotIn(b"evil.example", body)

    def test_sec_fetch_site_rules(self):
        for value, status in (("same-origin", 200), ("none", 200), ("SAME-ORIGIN", 200),
                              ("cross-site", 403), ("same-site", 403), ("", 403),
                              ("planted-site", 403)):
            for path in ("/api/settings", "/api/usage", "/", "/static/tokens.css"):
                got, heads, body = self.srv.request("GET", path, {"Sec-Fetch-Site": value})
                self.assertEqual(got, status, (value, path))
                self.assertNotIn("access-control-allow-origin", heads)
                if got == 403:
                    self.assertEqual(json.loads(body), {"error": "forbidden"})
                    self.assertNotIn(b"planted", body)
                    self.assertEqual(heads["cross-origin-resource-policy"], "same-origin")
        self.assertEqual(self.srv.request("GET", "/api/settings")[0], 200)  # header absent
        self.assertEqual(self.srv.request("HEAD", "/api/settings", {"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.srv.request("POST", "/", {"Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_cross_site_link_opens_the_page_and_nothing_else(self):
        load = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        self.assertEqual(self.srv.request("GET", "/", load)[0], 200)
        self.assertEqual(self.srv.request("GET", "/?x=1", load)[0], 200)
        self.assertEqual(self.srv.request("HEAD", "/", load)[0], 403)
        self.assertEqual(self.srv.request("POST", "/", load)[0], 403)
        for path in ("/api/settings", "/api/projects", "/api/usage", "/static/tokens.css", "/static/index.html"):
            self.assertEqual(self.srv.request("GET", path, load)[0], 403, path)
        for change in ({"Sec-Fetch-Mode": "no-cors"}, {"Sec-Fetch-Mode": "cors"},
                       {"Sec-Fetch-Dest": "iframe"}, {"Sec-Fetch-Dest": "script"}, {"Sec-Fetch-Dest": "empty"}):
            self.assertEqual(self.srv.request("GET", "/", dict(load, **change))[0], 403, change)
        missing = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"}
        self.assertEqual(self.srv.request("GET", "/", missing)[0], 403)

    def test_no_cors_header_on_any_response(self):
        probes = [("GET", "/", {}), ("GET", "/api/settings", {"Origin": "http://localhost:%d" % self.port}),
                  ("GET", "/api/usage", {}), ("GET", "/nope", {}), ("POST", "/api/settings", {}),
                  ("GET", "/api/settings", {"Origin": "http://evil.example"}),
                  ("OPTIONS", "/api/settings", {"Origin": "http://evil.example",
                                                "Access-Control-Request-Method": "GET"})]
        for method, path, heads in probes:
            _, resp_heads, _ = self.srv.request(method, path, heads)
            self.assertFalse([h for h in resp_heads if h.startswith("access-control-")],
                             (method, path))

    def test_other_methods_get_405(self):
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "PROPFIND", "PATCH", "TRACE", "CONNECT"):
            for path in ("/api/settings", "/api/usage", "/", "/nope"):
                body = b"x=1" if method in ("POST", "PUT", "PATCH") else None
                status, heads, data = self.srv.request(method, path, body=body)
                self.assertEqual(status, 405, (method, path))
                self.assertEqual(heads.get("allow"), "GET, HEAD")
                self.assertEqual(json.loads(data), {"error": "method_not_allowed"})

    def test_every_response_carries_the_security_headers(self):
        probes = [("GET", "/"), ("GET", "/api/settings"), ("GET", "/nope"), ("POST", "/"),
                  ("HEAD", "/api/settings"), ("GET", "/api/usage"), ("GET", "/static/tokens.css")]
        for method, path in probes:
            _, heads, _ = self.srv.request(method, path)
            self.assertEqual(heads["content-security-policy"], CSP, (method, path))
            self.assertEqual(heads["x-content-type-options"], "nosniff")
            self.assertEqual(heads["cache-control"], "no-store")
            self.assertEqual(heads["referrer-policy"], "no-referrer")
            self.assertEqual(heads["cross-origin-resource-policy"], "same-origin")
        _, heads, _ = self.srv.request("GET", "/", host="evil.example")
        self.assertEqual(heads["content-security-policy"], CSP)

    def test_head_matches_get_without_a_body(self):
        for path in ("/", "/api/settings", "/api/usage", "/static/tokens.css", "/nope"):
            g_status, g_heads, g_body = self.srv.request("GET", path)
            h_status, h_heads, h_body = self.srv.request("HEAD", path)
            self.assertEqual(h_status, g_status, path)
            self.assertEqual(h_body, b"", path)
            self.assertEqual(int(h_heads["content-length"]), len(g_body), path)
            for name in ("content-type", "content-length", "content-security-policy",
                         "x-content-type-options", "cache-control", "referrer-policy"):
                self.assertEqual(h_heads.get(name), g_heads.get(name), (path, name))

    def test_unknown_api_path_is_json_404(self):
        for path in ("/api/other", "/api/", "/api", "/api/settings/x"):
            status, heads, body = self.srv.request("GET", path)
            self.assertEqual(status, 404, path)
            self.assertEqual(json.loads(body), {"error": "not_found"})
            self.assertEqual(heads["content-type"], "application/json; charset=utf-8")

    def test_settings_route_returns_entries(self):
        status, heads, body = self.srv.request("GET", "/api/settings?x=1")
        self.assertEqual(status, 200)
        self.assertEqual(heads["content-type"], "application/json; charset=utf-8")
        entries = json.loads(body)["entries"]
        self.assertTrue(entries)
        self.assertTrue(all("key" in e and "value" in e for e in entries))

    def test_malformed_requests_get_a_fixed_body(self):
        for payload in (b"GET /x planted-garbage\r\n\r\n", b"GET\r\n\r\n",
                        b"GET /x HTTP/9.9\r\nHost: planted-host.example\r\n\r\n",
                        b"GET /" + b"a" * 70000 + b" HTTP/1.0\r\n\r\n"):
            answer = self.srv.raw(payload)
            self.assertNotIn(b"planted", answer)
            self.assertNotIn(b"<html", answer.lower())
            if answer.startswith(b"HTTP/"):
                self.assertIn(b"content-security-policy", answer.lower())
        answer = self.srv.raw(b"GET /x HTTP/1.0\r\nX-Planted: " + b"p" * 70000 + b"\r\n\r\n")
        self.assertIn(b" 431 ", answer.split(b"\r\n", 1)[0])
        self.assertIn(b'{"error": "headers_too_large"}', answer)
        self.assertNotIn(b"planted", answer.lower())

    def test_log_lines(self):
        planted = "sk-planted-query-0099"
        self.srv.request("GET", "/api/settings?token=%s" % planted)
        self.srv.request("GET", "/static/" + "a" * 3000)
        self.srv.raw(b"GET /static/\xff\x01x HTTP/1.0\r\nHost: 127.0.0.1:%d\r\n\r\n" % self.port)
        deadline = time.time() + 5
        while time.time() < deadline and "xff" not in self.srv.stderr():
            time.sleep(0.05)
        err = self.srv.stderr()
        self.assertNotIn(planted, err)
        self.assertNotIn("token=", err)
        self.assertIn("\\xff\\x01x", err)
        for line in err.splitlines():
            self.assertRegex(line, r"^[A-Za-z0-9_-]+ '[^']*' \d{3}$")
            self.assertLessEqual(len(line), 260)
            self.assertTrue(line.isprintable(), repr(line))


# --------------------------------------------------------------------------
# Static files and path escapes, on a copy of the dashboard folder

class StaticFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_root()
        cls.tree = os.path.join(cls.root, "tree")
        os.makedirs(cls.tree)
        script = copy_tree(cls.tree)
        static = os.path.join(cls.tree, "dashboard", "static")
        write(os.path.join(static, "app.js"), "console.log(1);\n")
        write(os.path.join(static, "data.json"), '{"a": 1}\n')
        write(os.path.join(static, "pic.svg"), "<svg xmlns='http://www.w3.org/2000/svg'/>\n")
        write(os.path.join(static, "notes.txt"), "text\n")
        write(os.path.join(static, ".hidden.css"), "a{}\n")
        write(os.path.join(static, "sub", "inner.css"), "b{}\n")
        write(os.path.join(static, "UPPER.JS"), "1\n")
        cls.outside = write(os.path.join(cls.root, "outside", "secret.html"),
                            "<p>planted-outside-file-0001</p>\n")
        os.symlink(cls.outside, os.path.join(static, "leak.html"))
        os.symlink(os.path.join(cls.root, "outside"), os.path.join(static, "linkdir"))
        os.symlink(os.path.join(static, "index.html"), os.path.join(static, "inner.html"))
        os.symlink(os.path.join(static, ".hidden.css"), os.path.join(static, "visible.css"))
        cls.srv = start(cls.root, ["--fixture", fixture_copy(cls.root)], script=script)

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
        helpers.rmtree_force(cls.root)

    def get(self, path):
        return self.srv.request("GET", path)

    def test_types(self):
        cases = (("/", "text/html"), ("/static/index.html", "text/html"),
                 ("/static/tokens.css", "text/css"), ("/static/app.js", "text/javascript"),
                 ("/static/data.json", "application/json"), ("/static/pic.svg", "image/svg+xml"),
                 ("/static/UPPER.JS", "text/javascript"), ("/static/sub/inner.css", "text/css"),
                 ("/static/inner.html", "text/html"))
        for path, ctype in cases:
            status, heads, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(heads["content-type"].startswith(ctype), (path, heads["content-type"]))
            self.assertEqual(heads["content-security-policy"], CSP)
            self.assertEqual(int(heads["content-length"]), len(body))
        self.assertTrue(self.get("/static/app.js")[1]["content-type"].startswith("text/javascript"))

    def test_served_bytes_match_the_file(self):
        with open(os.path.join(DASHBOARD, "static", "tokens.css"), "rb") as fh:
            expected = fh.read()
        self.assertEqual(self.get("/static/tokens.css")[2], expected)

    def test_index_has_no_inline_script_or_style(self):
        html = self.get("/")[2].decode("utf-8")
        self.assertNotRegex(html, r"(?i)<script(?![^>]*\bsrc=)")
        self.assertNotRegex(html, r"(?i)<style|\sstyle=|\sonclick=|\sonload=")

    def test_not_served(self):
        paths = ("/static/notes.txt", "/static/.hidden.css", "/static/visible.css",
                 "/static/sub", "/static/sub/", "/static/", "/static", "/index.html",
                 "/static/index.html%00", "/static/index.html%00.css", "/static/nope.css",
                 "/static//index.html", "/static/sub//inner.css", "/static/sub/./inner.css",
                 "/static/%2e/index.html", "/static/index.html/", "/static/index.html?x=/../",
                 "/static/..%5Cserver.py", "/static/server.py", "/dashboard/static/index.html")
        for path in paths:
            status, _, body = self.get(path)
            if path == "/static/index.html?x=/../":
                self.assertEqual(status, 200, path)
                continue
            self.assertEqual(status, 404, path)
            self.assertEqual(json.loads(body), {"error": "not_found"}, path)

    def test_path_escapes_are_refused(self):
        paths = ("/static/../server.py", "/static/%2e%2e/server.py", "/static/%252e%252e/server.py",
                 "/static/..%2fserver.py", "/static/%2e%2e%2fserver.py", "/static/..%252fserver.py",
                 "/static/sub/../../server.py", "/static/sub/%2e%2e/%2e%2e/server.py",
                 "/static/%2fetc%2fhosts", "/static//etc/hosts", "/static/%2Fetc/hosts",
                 "/etc/hosts", "/../server.py", "/..%2fdashboard/server.py",
                 "/static/../../agent_md.py", "/static/../static/index.html",
                 "/static/....//server.py", "/static/..;/server.py")
        for path in paths:
            status, _, body = self.get(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"def ", body)
            self.assertNotIn(b"root:", body)

    def test_symlink_out_of_the_folder_is_refused(self):
        for path in ("/static/leak.html", "/static/linkdir/secret.html"):
            status, _, body = self.get(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"planted-outside", body)

    def test_absolute_form_request_target(self):
        answer = self.srv.raw(("GET http://127.0.0.1:%d/static/index.html HTTP/1.0\r\n"
                               "Host: 127.0.0.1:%d\r\n\r\n" % (self.srv.port, self.srv.port)).encode())
        self.assertIn(b" 404 ", answer.split(b"\r\n", 1)[0])


# --------------------------------------------------------------------------
# Secrets

PLANTED = {
    "env_block_value": "sk-planted-env-0001",
    "token_name_value": "planted-token-value-0002",
    "key_name_value": "planted-key-name-0003",
    "unknown_key_value": "sk-planted-unknown-0004",
    "nested_secret": "planted-nested-0005",
    "managed_value": "Bearer planted-managed-0006",
    "managed_env": "planted-managed-env-0007",
    "shell_model": "sk-planted-shell-0008",
    "shell_other": "planted-shell-other-0009",
    "shell_secret_name": "planted-shell-secret-0010",
    "env_shadow": "planted-env-shadow-0011",
    "cli_value": "Bearer planted-cli-0012",
    "cli_key": "planted-cli-key-0013",
    "agent_model": "sk-planted-agent-0014",
    "agent_key": "planted-agent-key-0015",
    "malformed": "planted-malformed-0016",
    "exception": "sk-planted-exception-0017",
    "project_local": "planted-local-token-0018",
    "flag_word": "sk-planted-flag-0019",
    "flag_inline": "sk-planted-flag-inline-0020",
}


def build_secret_fixture(folder):
    p = PLANTED
    write_json(os.path.join(folder, "config", "settings.json"), {
        "model": "claude-opus-5-5",
        "env": {"MY_API_TOKEN": p["token_name_value"], "ANTHROPIC_MODEL": p["env_block_value"],
                "MY_SERVICE_PASSWORD": p["env_shadow"]},
        "apiKey": p["key_name_value"],
        "unknownThing": p["unknown_key_value"],
        "mcpServers": {"x": {"command": "run", "env": {"SERVICE_SECRET": p["nested_secret"]}}},
    })
    write_json(os.path.join(folder, "project", ".claude", "settings.local.json"), {
        "env": {"LOCAL_AUTH_TOKEN": p["project_local"]}})
    write(os.path.join(folder, "project", ".claude", "settings.json"),
          '{\n  "env": {\n    "BROKEN_KEY": "%s",\n' % p["malformed"])
    write_json(os.path.join(folder, "managed", "managed-settings.json"), {
        "someManagedThing": p["managed_value"], "env": {"MANAGED_SECRET": p["managed_env"]}})
    write(os.path.join(folder, "config", "agents", "spy.md"),
          "---\nname: spy\ndescription: a spy\nmodel: %s\napiToken: %s\n---\nBody text.\n"
          % (p["agent_model"], p["agent_key"]))
    write_json(os.path.join(folder, "session.json"), {
        "shell_env": {"ANTHROPIC_MODEL": p["shell_model"], "PLANTED_OTHER": p["shell_other"],
                      "MY_SERVICE_PASSWORD": p["shell_secret_name"]},
        "flags": ["--model", p["flag_word"], "--effort=" + p["flag_inline"]],
        "cli_settings": {"model": p["cli_value"], "apiKeyHelper": p["cli_key"]},
    })


BOOM_DRIVER = """\
import sys
sys.path.insert(0, %(dashboard)r)
import server


def boom(ctx, query):
    raise RuntimeError("route failed with " + %(secret)r)


server.ROUTES["/api/boom"] = boom
sys.exit(server.main(sys.argv[1:]))
"""


class Secrets(TempCase):
    def run_requests(self, proc):
        """Hit every route and error path. Returns all text the server produced."""
        port = proc.port
        seen = []

        def go(method, path, **kw):
            status, heads, body = proc.request(method, path, **kw)
            seen.append(json.dumps(heads) + body.decode("utf-8", "replace"))
            return status, body

        statuses = {
            "settings": go("GET", "/api/settings")[0],
            "settings_query": go("GET", "/api/settings?token=%s" % PLANTED["env_block_value"])[0],
            "index": go("GET", "/")[0],
            "static": go("GET", "/static/tokens.css")[0],
            "head": go("HEAD", "/api/settings")[0],
            "not_found": go("GET", "/nope")[0],
            "api_not_found": go("GET", "/api/nope")[0],
            "escape": go("GET", "/static/../server.py")[0],
            "forbidden_host": go("GET", "/api/settings", host="evil.example")[0],
            "forbidden_origin": go("GET", "/api/settings", headers={"Origin": "http://evil.example"})[0],
            "post": go("POST", "/api/settings", body=b"a=b")[0],
            "boom": go("GET", "/api/boom")[0],
            "boom_head": go("HEAD", "/api/boom")[0],
        }
        seen.append(proc.raw(b"GET /x bad-request\r\n\r\n").decode("utf-8", "replace"))
        seen.append(proc.raw(b"GET /api/settings HTTP/1.0\r\nHost: 127.0.0.1:%d\r\n\r\n" % port)
                    .decode("utf-8", "replace"))
        return statuses, seen

    def test_no_hidden_value_leaves_the_server(self):
        folder = os.path.join(self.root, "secrets")
        build_secret_fixture(folder)
        driver = write(os.path.join(self.root, "drivers", "boom.py"),
                       BOOM_DRIVER % {"dashboard": DASHBOARD, "secret": PLANTED["exception"]})
        proc = self.start(["--fixture", folder], script=driver, python_args=["-B"], name="secrets")
        statuses, seen = self.run_requests(proc)
        self.assertEqual(statuses["settings"], 200)
        self.assertEqual(statuses["boom"], 500)
        self.assertEqual(statuses["boom_head"], 500)
        self.assertEqual(statuses["not_found"], 404)
        self.assertEqual(statuses["forbidden_host"], 403)
        self.assertEqual(statuses["forbidden_origin"], 403)
        self.assertEqual(statuses["post"], 405)
        self.assertEqual(statuses["escape"], 404)
        settings_text = proc.request("GET", "/api/settings")[2].decode("utf-8")
        proc.stop()
        everything = "\n".join(seen + [proc.stdout(), proc.stderr()])
        for name, value in PLANTED.items():
            self.assertNotIn(value, everything, name)
        self.assertNotIn("planted-", everything)
        self.assertNotIn("planted-", settings_text)
        # Not vacuous: the names are in the output and their values show as hidden.
        entries = json.loads(settings_text)["entries"]
        by_key = {e["key"]: e for e in entries}
        self.assertIn("hidden", settings_text)
        self.assertEqual(by_key["env.MY_API_TOKEN"]["value"], "hidden")
        self.assertEqual(by_key["env.ANTHROPIC_MODEL"]["value"], "hidden")
        self.assertEqual(by_key["env.MANAGED_SECRET"]["value"], "hidden")
        # The failing route logged its class name and nothing else.
        self.assertIn("route error 'RuntimeError'", proc.stderr())
        self.assertNotIn("route failed", everything)
        self.assertNotIn("Traceback", everything)

    def test_a_secret_in_a_launch_flag_is_hidden_in_both_forms(self):
        """A flag value is masked in the separate-word form and in the --flag=value form."""
        forms = {
            "word": ["--model", "sk-planted-flag-word-0101"],
            "inline": ["--model=sk-planted-flag-inline-0102"],
        }
        for name, flags in forms.items():
            folder = os.path.join(self.root, "flags-" + name)
            write_json(os.path.join(folder, "session.json"), {"flags": flags})
            proc = self.start(["--fixture", folder], name="flags-" + name)
            seen = []
            for path in ("/api/settings", "/api/settings?project=all", "/api/projects",
                         "/api/usage", "/api/usage?project=all"):
                status, heads, body = proc.request("GET", path)
                seen.append(json.dumps(heads) + body.decode("utf-8", "replace"))
            settings = json.loads(proc.request("GET", "/api/settings")[2].decode("utf-8"))
            proc.stop()
            everything = "\n".join(seen + [proc.stdout(), proc.stderr()])
            self.assertNotIn("planted-flag", everything, name)
            self.assertNotIn("sk-planted", everything, name)
            # Not vacuous: the flag still reaches the resolver, which reports the masked value.
            self.assertIn("hidden", json.dumps(settings), name)

    def test_planted_values_are_hidden_by_collect(self):
        """The fixture really plants values collect hides, so the test above means something."""
        folder = os.path.join(self.root, "secrets")
        build_secret_fixture(folder)
        collected = collect.collect(os.path.join(folder, "config"), os.path.join(folder, "project"),
                                    os.path.join(folder, "managed"), {}, RULES)
        text = "\n".join(all_text(collected))  # collector "where" maps have tuple keys
        self.assertNotIn("planted-", text)
        self.assertIn("hidden", text)
        self.assertTrue(collect.is_secret_name("MY_API_TOKEN"))
        self.assertTrue(collect.is_secret_value(PLANTED["env_block_value"]))
        self.assertTrue(collect.is_secret_value(PLANTED["managed_value"]))


# --------------------------------------------------------------------------
# Entries and JSON

class Entries(TempCase):
    def case_names(self):
        names = []
        for name in sorted(os.listdir(FIXTURE_DIR)):
            path = os.path.join(FIXTURE_DIR, name)
            if os.path.isfile(os.path.join(path, "expected.json")):
                names.append(name)
        return names

    def test_every_case_matches_resolve_and_is_json_safe(self):
        names = self.case_names()
        self.assertGreater(len(names), 50)
        for name in names:
            folder = os.path.join(FIXTURE_DIR, name)
            inputs, _ = resolve.load_fixture(folder, RULES)
            expected = json.loads(json.dumps(resolve.resolve(inputs, RULES, FIELDS)))
            ctx = server.fixture_context(folder, None, None, RULES, FIELDS)
            status, payload = api_settings.settings(ctx, {})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(json.dumps(payload))["entries"], expected, name)
            self.assertEqual(payload["project"], "project")

    def test_http_entries_equal_resolve_for_a_committed_case(self):
        for name in ("env-block-over-shell", "agent-project-over-user"):
            folder = os.path.join(FIXTURE_DIR, name)
            inputs, _ = resolve.load_fixture(folder, RULES)
            expected = json.loads(json.dumps(resolve.resolve(inputs, RULES, FIELDS)))
            proc = self.start(["--fixture", folder], name=name)
            status, _, body = proc.request("GET", "/api/settings")
            self.assertEqual(status, 200)
            answer = json.loads(body)
            self.assertEqual(answer["entries"], expected, name)
            self.assertEqual(set(answer), {
                "project", "state", "entries", "no_user_settings", "shell_label", "path_display",
                "config_dir_display", "config_file_display", "models", "rows", "rules", "files", "installed", "attention"})

    def test_a_fixture_folder_may_be_empty(self):
        folder = os.path.join(self.root, "empty")
        os.makedirs(folder)
        proc = self.start(["--fixture", folder])
        status, _, body = proc.request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertIsInstance(json.loads(body)["entries"], list)

    def test_a_malformed_session_file_is_treated_as_empty(self):
        folder = os.path.join(self.root, "badsession")
        write(os.path.join(folder, "session.json"), "{not json")
        proc = self.start(["--fixture", folder])
        self.assertEqual(proc.request("GET", "/api/settings")[0], 200)

    def test_config_dir_and_project_override_a_fixture(self):
        folder = fixture_copy(self.root)
        cfg = os.path.join(self.root, "other-cfg")
        project = os.path.join(self.root, "other-project")
        write_json(os.path.join(cfg, "settings.json"), {"env": {"ANTHROPIC_MODEL": "claude-opus-5-5"}})
        write_json(os.path.join(project, ".claude", "settings.json"),
                   {"env": {"CLAUDE_CODE_EFFORT_LEVEL": "high"}})
        proc = self.start(["--fixture", folder, "--config-dir", cfg, "--project", project])
        entries = json.loads(proc.request("GET", "/api/settings")[2])["entries"]
        files = {e.get("file") for e in entries}
        self.assertIn(os.path.join(cfg, "settings.json"), files)
        self.assertIn(os.path.join(project, ".claude", "settings.json"), files)
        self.assertNotIn("config/settings.json", files)

    def test_files_are_read_again_on_every_request(self):
        folder = fixture_copy(self.root)
        proc = self.start(["--fixture", folder])
        first = json.loads(proc.request("GET", "/api/settings")[2])["entries"]
        write_json(os.path.join(folder, "config", "settings.json"),
                   {"env": {"ANTHROPIC_MODEL": "claude-opus-5-5"}})
        second = json.loads(proc.request("GET", "/api/settings")[2])["entries"]
        self.assertNotEqual(first, second)

    def test_live_run_uses_the_config_dir_rule(self):
        """In process, on a platform with no managed folder, so no real folder is read."""
        env_cfg = os.path.join(self.root, "cfg-from-env")
        write_json(os.path.join(env_cfg, "settings.json"), {"env": {"ANTHROPIC_MODEL": "claude-opus-5-5"}})
        project = os.path.join(self.root, "project")
        os.makedirs(project)
        home = os.path.join(self.root, "home")
        write_json(os.path.join(home, ".claude", "settings.json"),
                   {"env": {"ANTHROPIC_MODEL": "claude-haiku-5-5"}})

        def files_for(env, config_dir=None):
            ctx = server.live_context(config_dir or server.default_config_dir(env, project),
                                      project, env, "test-platform", RULES, FIELDS)
            self.assertIsNone(ctx.managed_dir)
            status, payload = api_settings.settings(ctx, {})
            self.assertEqual(status, 200)
            return {e.get("file") for e in payload["entries"]}

        env = {"HOME": home, "CLAUDE_CONFIG_DIR": env_cfg}
        self.assertIn(os.path.join(env_cfg, "settings.json"), files_for(env))
        del env["CLAUDE_CONFIG_DIR"]
        self.assertIn("~/.claude/settings.json", files_for(env))
        # --config-dir wins over both.
        files = files_for(env, config_dir=env_cfg)
        self.assertIn(os.path.join(env_cfg, "settings.json"), files)
        self.assertNotIn("~/.claude/settings.json", files)


# --------------------------------------------------------------------------
# Start-up, address and options

class StartUp(TempCase):
    def test_in_process_server_binds_loopback_only(self):
        ctx = server.fixture_context(self.root, None, None, RULES, FIELDS)
        srv = server.Server(ctx, 0)
        try:
            self.assertEqual(srv.server_address[0], "127.0.0.1")
            self.assertEqual(srv.socket.family, socket.AF_INET)
            self.assertEqual(srv.socket.getsockname()[0], "127.0.0.1")
        finally:
            srv.server_close()

    def test_there_is_no_way_to_pick_another_address(self):
        self.assertEqual(list(inspect.signature(server.Server.__init__).parameters),
                         ["self", "ctx", "port"])
        options = {a.dest for a in server.build_parser()._actions}
        self.assertEqual(options, {"help", "config_dir", "project", "port", "fixture"})
        for flag in ("--host", "--bind", "--address"):
            with open(os.devnull, "w") as null, contextlib.redirect_stderr(null):
                with self.assertRaises(SystemExit):
                    server.build_parser().parse_args([flag, "0.0.0.0"])
        proc = subprocess.run([sys.executable, "-B", os.path.join(DASHBOARD, "server.py"),
                               "--host", "0.0.0.0", "--port", "0", "--fixture", fixture_copy(self.root)],
                              env=base_env(self.root),
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b"")

    def test_the_listening_socket_is_loopback_only(self):
        if shutil.which("lsof") is None:
            self.skipTest("lsof is not installed")
        proc = self.start(["--fixture", fixture_copy(self.root)])
        self.assertEqual(proc.request("GET", "/")[0], 200)
        out = subprocess.run(["lsof", "-nP", "-a", "-p", str(proc.proc.pid), "-iTCP",
                              "-sTCP:LISTEN", "-Fn"], capture_output=True, timeout=30,
                             stdin=subprocess.DEVNULL).stdout.decode()
        names = [line[1:] for line in out.splitlines() if line.startswith("n")]
        self.assertEqual(names, ["127.0.0.1:%d" % proc.port])

    def test_not_reachable_through_another_local_address(self):
        addresses = local_non_loopback_addresses()
        if not addresses:
            self.skipTest("this machine has no non-loopback IPv4 address")
        proc = self.start(["--fixture", fixture_copy(self.root)])
        for addr in addresses:
            with self.assertRaises(OSError, msg=addr):
                socket.create_connection((addr, proc.port), timeout=3).close()

    def test_busy_port_prints_one_line_and_exits_1(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        try:
            port = holder.getsockname()[1]
            proc = subprocess.run([sys.executable, "-B", os.path.join(DASHBOARD, "server.py"),
                                   "--port", str(port), "--fixture", fixture_copy(self.root)],
                                  env=base_env(self.root), stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=30)
        finally:
            holder.close()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, b"")
        self.assertEqual(len(proc.stderr.decode().splitlines()), 1)
        self.assertNotIn(b"Traceback", proc.stderr)

    def test_bad_options_exit_2(self):
        self.fixture = fixture_copy(self.root, name="opt-fixture")
        for args in (["--port", "70000"], ["--port", "x"], ["--fixture", os.path.join(self.root, "nope")]):
            proc = subprocess.run([sys.executable, "-B", os.path.join(DASHBOARD, "server.py")] + args
                                  + ([] if "--fixture" in args else ["--fixture", self.fixture]),
                                  env=base_env(self.root), stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=30)
            self.assertEqual(proc.returncode, 2, args)
            self.assertEqual(proc.stdout, b"")

    def test_default_port_is_8377(self):
        self.assertEqual(server.build_parser().parse_args([]).port, 8377)

    def test_bytecode_line_comes_before_every_repo_import(self):
        with open(os.path.join(DASHBOARD, "server.py"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        flag = next(i for i, line in enumerate(lines) if line.startswith("sys.dont_write_bytecode = True"))
        repo_imports = [i for i, line in enumerate(lines)
                        if re.match(r"import (api_settings|collect|resolve|agent_md|rules_schema)\b", line)]
        self.assertTrue(repo_imports)
        self.assertLess(flag, min(repo_imports))

    def test_only_main_reads_the_environment(self):
        import ast
        for name in ("server.py", "api_settings.py"):
            with open(os.path.join(DASHBOARD, name), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            main_lines = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "main":
                    main_lines = set(range(node.lineno, node.end_lineno + 1))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
                    self.assertIn(node.lineno, main_lines, "%s:%d" % (name, node.lineno))


class ConfigDirRule(unittest.TestCase):
    def test_rule(self):
        cwd = make_root()
        self.addCleanup(helpers.rmtree_force, cwd)
        cases = (
            ({"CLAUDE_CONFIG_DIR": "/x/y", "HOME": "/h"}, "/x/y"),
            ({"CLAUDE_CONFIG_DIR": "/x/y///", "HOME": "/h"}, "/x/y"),
            ({"CLAUDE_CONFIG_DIR": "", "HOME": "/h"}, "/h/.claude"),
            ({"HOME": "/h"}, "/h/.claude"),
            ({"HOME": "/h/"}, "/h//.claude"),
            ({"CLAUDE_CONFIG_DIR": "rel/cfg", "HOME": "/h"}, os.path.join(cwd, "rel/cfg")),
            ({"CLAUDE_CONFIG_DIR": "/", "HOME": "/h"}, "/"),
            ({}, "/.claude"),
        )
        for env, expected in cases:
            self.assertEqual(server.default_config_dir(env, cwd), expected, env)

    def test_matches_install_py(self):
        cwd = make_root()
        self.addCleanup(helpers.rmtree_force, cwd)
        for env in ({"CLAUDE_CONFIG_DIR": "/x/y/", "HOME": "/h"}, {"HOME": "/h"},
                    {"CLAUDE_CONFIG_DIR": "rel", "HOME": "/h"}, {"CLAUDE_CONFIG_DIR": "", "HOME": "/h"}):
            self.assertEqual(server.default_config_dir(env, cwd), install.resolve_target(env, cwd), env)

    def test_does_not_read_the_process_environment(self):
        saved = dict(os.environ)
        os.environ["CLAUDE_CONFIG_DIR"] = "/planted/env/dir"
        try:
            self.assertEqual(server.default_config_dir({"HOME": "/h"}, "/"), "/h/.claude")
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_managed_dir_by_platform(self):
        self.assertEqual(server.managed_dir_for("darwin"), "/Library/Application Support/ClaudeCode")
        self.assertEqual(server.managed_dir_for("linux"), "/etc/claude-code")
        self.assertEqual(server.managed_dir_for("win32"), r"C:\Program Files\ClaudeCode")
        self.assertIsNone(server.managed_dir_for("test-platform"))


# --------------------------------------------------------------------------
# Writes and reads

class NoWrites(TempCase):
    def test_no_file_is_added_changed_or_removed(self):
        tree = os.path.join(self.root, "tree")
        os.makedirs(tree)
        script = copy_tree(tree)
        cfg = os.path.join(self.root, "cfg")
        project = os.path.join(self.root, "project")
        write_json(os.path.join(cfg, "settings.json"), {"env": {"ANTHROPIC_MODEL": "claude-opus-5-5"}})
        write(os.path.join(cfg, "agents", "a.md"), "---\nname: a\ndescription: d\nmodel: opus\n---\nBody\n")
        write_json(os.path.join(project, ".claude", "settings.json"), {"effortLevel": "high"})
        write(os.path.join(project, ".claude", "settings.local.json"), "{broken")
        for folder in (tree, cfg, project):
            self.assertEqual([d for d, _, _ in os.walk(folder) if d.endswith("__pycache__")], [])
        fixture = fixture_copy(self.root)
        watched = (tree, cfg, project, fixture)
        before = hash_tree(*watched)
        env = base_env(self.root)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        # No -B, so only the server's own setting keeps bytecode off. The -X option turns off
        # the cache folder Apple's python3 adds, which would hide writes from this test.
        proc = self.start(["--fixture", fixture, "--config-dir", cfg, "--project", project], env=env,
                          script=script, python_args=["-X", "pycache_prefix="])
        for method, path in (("GET", "/"), ("GET", "/static/tokens.css"), ("GET", "/api/settings"),
                             ("GET", "/api/usage"), ("GET", "/api/projects"),
                             ("HEAD", "/api/settings"), ("GET", "/nope"), ("POST", "/"),
                             ("PROPFIND", "/"), ("GET", "/static/%2e%2e/server.py")):
            proc.request(method, path)
        proc.request("GET", "/api/settings", host="evil.example")
        proc.raw(b"GET /x bad\r\n\r\n")
        proc.raw(b"\xff\xfe\r\n\r\n")
        self.assertEqual(proc.request("GET", "/api/settings")[0], 200)
        proc.stop()
        self.assertEqual(hash_tree(*watched), before)
        for folder in watched:
            self.assertEqual([d for d, _, _ in os.walk(folder) if "__pycache__" in d], [])

    def test_the_repo_copy_is_not_dirty_after_a_run_from_the_repo(self):
        repo_pycache = [d for d, _, _ in os.walk(DASHBOARD) if d.endswith("__pycache__")]
        proc = self.start(["--fixture", fixture_copy(self.root)],
                          python_args=["-X", "pycache_prefix="])
        proc.request("GET", "/api/settings")
        proc.stop()
        after =[d for d, _, _ in os.walk(DASHBOARD) if d.endswith("__pycache__")]
        self.assertEqual(after, repo_pycache)


AUDIT_DRIVER = """\
import os
import runpy
import sys

LOG = %(log)r
fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND)


def hook(event, args):
    if event not in ("open", "os.listdir", "os.scandir"):
        return
    try:
        path = args[0]
        if isinstance(path, int) or path is None:
            return
        path = os.path.abspath(os.fsdecode(path))
        os.write(fd, (event + "\\t" + path + "\\n").encode("utf-8", "replace"))
    except Exception:
        pass


sys.addaudithook(hook)
sys.argv = [%(server)r] + sys.argv[1:]
runpy.run_path(%(server)r, run_name="__main__")
"""


class Isolation(TempCase):
    def test_a_fixture_run_reads_no_real_managed_folder_shell_or_home(self):
        fake_home = os.path.join(self.root, "home")
        canary_cfg = os.path.join(self.root, "canary-cfg")
        write_json(os.path.join(fake_home, ".claude", "settings.json"),
                   {"env": {"ANTHROPIC_MODEL": "canary-home-model"}, "effortLevel": "canary-home-effort"})
        write_json(os.path.join(canary_cfg, "settings.json"),
                   {"env": {"ANTHROPIC_MODEL": "canary-cfg-model"}})
        write(os.path.join(canary_cfg, "agents", "canary.md"),
              "---\nname: canary\ndescription: canary-cfg-agent\n---\n")
        folder = fixture_copy(self.root, "env-block-over-shell")
        log = os.path.join(self.root, "logs", "audit.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        driver = write(os.path.join(self.root, "drivers", "audit.py"),
                       AUDIT_DRIVER % {"log": log, "server": os.path.join(DASHBOARD, "server.py")})
        env = base_env(self.root, HOME=fake_home, CLAUDE_CONFIG_DIR=canary_cfg,
                       ANTHROPIC_MODEL="canary-shell-model", CLAUDE_CODE_EFFORT_LEVEL="canary-shell-effort")
        proc = self.start(["--fixture", folder], env=env, script=driver, python_args=["-B"], name="audit")
        bodies = []
        for path in ("/api/settings", "/api/usage", "/api/projects", "/", "/static/tokens.css", "/nope"):
            bodies.append(proc.request("GET", path)[2].decode("utf-8", "replace"))
        proc.stop()
        everything = "\n".join(bodies + [proc.stdout(), proc.stderr()])
        self.assertNotIn("canary", everything)
        with open(log, encoding="utf-8") as fh:
            recorded = [line.rstrip("\n").split("\t", 1) for line in fh if "\t" in line]
        paths = [os.path.realpath(p) for _, p in recorded]
        # The hook worked: it saw the fixture's own files.
        self.assertTrue(any(p.startswith(os.path.realpath(folder)) for p in paths), paths[:5])
        forbidden = [os.path.join(fake_home, ".claude"), canary_cfg] + list(REAL_MANAGED) \
            + sorted(helpers._real_claude_dirs())
        for p in paths:
            for bad in forbidden:
                bad = os.path.realpath(bad)
                self.assertFalse(p == bad or p.startswith(bad + os.sep), "%s read %s" % (p, bad))
        self.assertTrue(any(p.startswith(os.path.join(os.path.realpath(folder), "config")) for p in paths))


if __name__ == "__main__":
    unittest.main()

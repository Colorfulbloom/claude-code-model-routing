"""Tests for the --allow-edits flag, the launch token and the POST gate (dashboard/server.py).

Two kinds of server run here. An in-process Server on a copy of a fixture takes the
bulk of the gate checks, with a fake echo route beside the real write routes, so a
request that passes every check can be seen reaching a route. Server processes,
started with --fixture on a temp copy, prove the command line, the printed link,
the logs and the default launch. A test never starts a server with --allow-edits
on anything but a temp folder, and never reads the real ~/.claude.

Test tokens are made by the server or by secrets here. Nothing is pinned to
argparse help or to the wording of an error message, only to exit codes and to
the stable error codes in the JSON bodies.
"""
import contextlib
import dataclasses
import io
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import unittest
from unittest import mock

import helpers
import test_server as ts

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import api_edit  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402

RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
SERVER_PY = os.path.join(helpers.REPO, "dashboard", "server.py")
STATIC = os.path.join(helpers.REPO, "dashboard", "static")
ECHO = "/api/edit/echo"
WRITE_PATHS = ("/api/edit/preview", "/api/edit/save", "/api/edit/undo")
READ_EDIT_PATHS = ("/api/edit", "/api/edit/targets", "/api/edit/history")
LINK = re.compile(r"http://127\.0\.0\.1:\d+/#/settings\?edit=([A-Za-z0-9_-]{43})")
LOG_LINE = re.compile(r"^[A-Za-z0-9_-]+ '[^']*' \d{3}$")
JSON_BODY = b'{"a": 1, "b": ["x", "y"]}'


# --------------------------------------------------------------------------
# Raw requests, so a test can repeat a header or send bytes http.client would refuse

def send(port, method, path, headers=(), body=None, length="auto", host="auto", half_close=False):
    """Send one request on a new socket. Returns (status, lowercase headers, body bytes).

    headers is a list of (name, value) pairs, value a str (Latin-1) or bytes.
    length "auto" adds the true Content-Length when there is a body, None sends
    none, and any other value is sent as written. half_close ends the sending
    side after the body, so a short body is seen as short at once.
    """
    lines = [("%s %s HTTP/1.1" % (method, path)).encode("ascii")]
    if host == "auto":
        lines.append(b"Host: 127.0.0.1:%d" % port)
    elif host is not None:
        lines.append(b"Host: " + host.encode("latin-1"))
    for name, value in headers:
        lines.append(name.encode("ascii") + b": " + (value if isinstance(value, bytes)
                                                   else value.encode("latin-1")))
    if length == "auto":
        if body is not None:
            lines.append(b"Content-Length: %d" % len(body))
    elif length is not None:
        lines.append(b"Content-Length: " + (length if isinstance(length, bytes)
                                            else length.encode("latin-1")))
    payload = b"\r\n".join(lines) + b"\r\n\r\n" + (body or b"")
    with socket.create_connection(("127.0.0.1", port), timeout=15) as sock:
        sock.sendall(payload)
        if half_close:
            sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            try:
                chunk = sock.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
    data = b"".join(chunks)
    head, _, rest = data.partition(b"\r\n\r\n")
    head_lines = head.split(b"\r\n")
    status = int(head_lines[0].split(b" ", 2)[1])
    heads = {}
    for line in head_lines[1:]:
        name, _, value = line.partition(b":")
        heads[name.decode("latin-1").lower()] = value.strip().decode("latin-1")
    return status, heads, rest


def good_headers(port, token, replace=None, drop=(), extra=()):
    """The headers of a request that passes the gate, changed by replace, drop and extra."""
    base = [("Origin", "http://127.0.0.1:%d" % port), ("Content-Type", "application/json"),
            ("X-Dashboard-Token", token)]
    replace = replace or {}
    out = [(n, replace.get(n, v)) for n, v in base if n not in drop]
    return out + list(extra)


def error_of(data):
    return json.loads(data).get("error")


class GateAssertions:
    def assert_refused(self, result, status, name, label=None):
        got, heads, data = result
        self.assertEqual(got, status, label)
        self.assertEqual(error_of(data), name, label)
        self.assertFalse([h for h in heads if h.startswith("access-control-")], label)
        self.assertEqual(heads["content-security-policy"], ts.CSP, label)


# --------------------------------------------------------------------------
# The gate, on an in-process server with an echo route

class GateCase(GateAssertions, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ts.make_root("mr-edit-")
        cls.fixture = ts.fixture_copy(cls.root)
        cls.token = secrets.token_urlsafe(32)
        cls.calls = []
        cls.logs = []

        def echo(ctx, body):
            cls.calls.append((ctx, body))
            return 200, {"echo": body}

        ctx = server.fixture_context(cls.fixture, None, None, RULES, FIELDS)
        cls.ctx = dataclasses.replace(ctx, edit=api_edit.EditState(cls.token, "launch-one", None))
        routes = dict(server.write_routes_for(True))
        routes[ECHO] = echo
        cls.patch = mock.patch.object(server.Handler, "log_message",
                                      lambda self, fmt, *args: cls.logs.append(fmt % args))
        cls.patch.start()
        cls.srv = server.Server(cls.ctx, 0, routes)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(10)
        cls.patch.stop()
        helpers.rmtree_force(cls.root)

    def setUp(self):
        del self.calls[:]

    def post(self, path=ECHO, body=JSON_BODY, **kwargs):
        headers = kwargs.pop("headers", None)
        if headers is None:
            headers = good_headers(self.port, self.token)
        return send(self.port, "POST", path, headers, body, **kwargs)

    # -- a request that passes every check

    def test_a_good_request_reaches_the_route_with_the_parsed_body(self):
        status, heads, data = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data), {"echo": {"a": 1, "b": ["x", "y"]}})
        self.assertEqual(len(self.calls), 1)
        ctx, body = self.calls[0]
        self.assertIs(ctx, self.ctx)
        self.assertEqual(body, {"a": 1, "b": ["x", "y"]})
        self.assertFalse([h for h in heads if h.startswith("access-control-")])
        self.assertEqual(heads["cache-control"], "no-store")

    def test_good_variants_pass(self):
        port, token = self.port, self.token
        variants = {
            "localhost origin": good_headers(port, token, {"Origin": "http://localhost:%d" % port}),
            "origin case and space": good_headers(port, token, {"Origin": " HTTP://LOCALHOST:%d " % port}),
            "same-origin": good_headers(port, token, extra=[("Sec-Fetch-Site", "same-origin")]),
            "same-origin case": good_headers(port, token, extra=[("Sec-Fetch-Site", " Same-Origin ")]),
            "content type case": good_headers(port, token, {"Content-Type": "Application/JSON"}),
            "lowercase header names": [("origin", "http://127.0.0.1:%d" % port),
                                       ("content-type", "application/json"),
                                       ("x-dashboard-token", token)],
        }
        for label, headers in variants.items():
            self.assertEqual(self.post(headers=headers)[0], 200, label)
        self.assertEqual(len(self.calls), len(variants))

    def test_a_body_at_the_cap_passes_and_the_empty_object_passes(self):
        filler = b'{"k": "' + b"x" * (server.DRAIN_CAP - len(b'{"k": ""}')) + b'"}'
        self.assertEqual(len(filler), server.DRAIN_CAP)
        self.assertEqual(self.post(body=filler)[0], 200)
        self.assertEqual(self.post(body=b"{}")[0], 200)
        self.assertEqual(self.post(body=b' \n{"a": "caf\xc3\xa9"}\n')[0], 200)
        self.assertEqual(self.calls[-1][1], {"a": "caf\u00e9"})

    # -- each check refuses

    def test_host(self):
        for host in ("evil.example", "evil.example:%d" % self.port, "127.0.0.1", "127.0.0.1:%d" % (self.port + 1),
                     "", None):
            self.assert_refused(self.post(host=host), 403, "forbidden", host)
        two = send(self.port, "POST", ECHO, [("Host", "127.0.0.1:%d" % self.port)] + good_headers(
            self.port, self.token), JSON_BODY)
        self.assert_refused(two, 403, "forbidden", "two Host headers")
        self.assertFalse(self.calls)

    def test_origin(self):
        port, token = self.port, self.token
        bad = ("null", "http://evil.example", "http://127.0.0.1", "https://127.0.0.1:%d" % port,
               "http://127.0.0.1:%d" % (port + 1), "http://planted-origin.example", "")
        for origin in bad:
            result = self.post(headers=good_headers(port, token, {"Origin": origin}))
            self.assert_refused(result, 403, "forbidden", origin)
            self.assertNotIn(b"planted", result[2])
        self.assert_refused(self.post(headers=good_headers(port, token, drop=("Origin",))),
                            403, "forbidden", "no Origin")
        twice = good_headers(port, token, extra=[("Origin", "http://127.0.0.1:%d" % port)])
        self.assert_refused(self.post(headers=twice), 403, "forbidden", "two Origin headers")
        self.assertFalse(self.calls)

    def test_sec_fetch_site(self):
        port, token = self.port, self.token
        for value in ("none", "cross-site", "same-site", "", "planted-site", "same-origin, same-origin"):
            headers = good_headers(port, token, extra=[("Sec-Fetch-Site", value)])
            self.assert_refused(self.post(headers=headers), 403, "forbidden", value)
        twice = good_headers(port, token, extra=[("Sec-Fetch-Site", "same-origin"),
                                                 ("Sec-Fetch-Site", "same-origin")])
        self.assert_refused(self.post(headers=twice), 403, "forbidden", "two values")
        navigate = good_headers(port, token, extra=[("Sec-Fetch-Site", "cross-site"),
                                                    ("Sec-Fetch-Mode", "navigate"),
                                                    ("Sec-Fetch-Dest", "document")])
        self.assert_refused(self.post(headers=navigate), 403, "forbidden", "cross-site navigation")
        self.assertFalse(self.calls)

    def test_content_type(self):
        port, token = self.port, self.token
        for value in ("text/plain", "application/json; charset=utf-8", "application/json;charset=utf-8",
                      "application/jsonx", "application/x-www-form-urlencoded",
                      "multipart/form-data; boundary=x", "application/json,text/plain", "json", ""):
            headers = good_headers(port, token, {"Content-Type": value})
            self.assert_refused(self.post(headers=headers), 415, "bad_content_type", value)
        self.assert_refused(self.post(headers=good_headers(port, token, drop=("Content-Type",))),
                            415, "bad_content_type", "no Content-Type")
        twice = good_headers(port, token, extra=[("Content-Type", "application/json")])
        self.assert_refused(self.post(headers=twice), 415, "bad_content_type", "two Content-Type headers")
        self.assertFalse(self.calls)

    def test_transfer_encoding(self):
        port, token = self.port, self.token
        for value in ("chunked", "identity", "gzip, chunked"):
            headers = good_headers(port, token, extra=[("Transfer-Encoding", value)])
            self.assert_refused(self.post(headers=headers), 400, "bad_request", value)
        headers = good_headers(port, token, extra=[("Transfer-Encoding", "chunked")])
        self.assert_refused(self.post(headers=headers, body=b"", length=None), 400, "bad_request",
                            "chunked, no length")
        self.assertFalse(self.calls)

    def test_content_length(self):
        big = str(server.DRAIN_CAP + 1)
        for length, label in ((None, "missing"), (big, "over the cap"), ("99999999999999999999", "huge"),
                              ("1" * 5000, "thousands of digits"), ("abc", "letters"), ("+5", "plus sign"),
                              ("-1", "negative"), ("1e3", "exponent"), ("0x10", "hex"), ("", "empty"),
                              (b"\xb2", "superscript two"), ("5 5", "inner space")):
            # half_close: a lenient length such as +5 makes the server wait for bytes that never come
            result = self.post(body=b"", length=length, half_close=True)
            self.assert_refused(result, 413, "too_large", label)
        twice = send(self.port, "POST", ECHO, good_headers(self.port, self.token) + [
            ("Content-Length", str(len(JSON_BODY)))], JSON_BODY)
        self.assert_refused(twice, 413, "too_large", "two Content-Length headers")
        self.assertFalse(self.calls)

    def test_a_short_body_is_refused(self):
        result = self.post(body=b'{"a"', length="40", half_close=True)
        self.assert_refused(result, 400, "bad_request", "short body")
        self.assertFalse(self.calls)

    def test_token(self):
        port, token = self.port, self.token
        wrong = ("", "wrong", token[:-1], token + "x", token.upper(), "caf\u00e9", "\u00ff" * 43)
        for value in wrong:
            result = self.post(headers=good_headers(port, token, {"X-Dashboard-Token": value}))
            self.assert_refused(result, 403, "bad_token", repr(value))
        for raw in (b"\xc3\xa9", b"\xe9", b"\xff\xfe", token.encode() + b"\xc3\xa9"):
            result = self.post(headers=good_headers(port, token, {"X-Dashboard-Token": raw}))
            self.assert_refused(result, 403, "bad_token", repr(raw))
        self.assert_refused(self.post(headers=good_headers(port, token, drop=("X-Dashboard-Token",))),
                            403, "bad_token", "no token header")
        twice = good_headers(port, token, extra=[("X-Dashboard-Token", token)])
        self.assert_refused(self.post(headers=twice), 403, "bad_token", "two token headers")
        mixed = good_headers(port, token, extra=[("X-Dashboard-Token", "wrong")])
        self.assert_refused(self.post(headers=mixed), 403, "bad_token", "good and wrong token")
        self.assertFalse(self.calls)

    def test_the_token_is_accepted_in_the_header_only(self):
        port, token = self.port, self.token
        no_header = good_headers(port, token, drop=("X-Dashboard-Token",))
        body = json.dumps({"token": token, "x_dashboard_token": token}).encode("utf-8")
        for path in (ECHO + "?token=" + token, ECHO + "?x-dashboard-token=" + token):
            self.assert_refused(self.post(path=path, body=body, headers=no_header), 403, "bad_token", path)
        wrong_header = good_headers(port, token, {"X-Dashboard-Token": "wrong"})
        self.assert_refused(self.post(path=ECHO + "?token=" + token, body=body, headers=wrong_header),
                            403, "bad_token", "good token in the query, wrong in the header")
        cookie = no_header + [("Cookie", "token=" + token), ("Authorization", "Bearer " + token)]
        self.assert_refused(self.post(headers=cookie), 403, "bad_token", "cookie and Authorization")
        self.assertFalse(self.calls)

    def test_a_query_string_on_a_good_request_is_ignored(self):
        self.assertEqual(self.post(path=ECHO + "?x=1&token=zzz")[0], 200)
        self.assertEqual(self.post(path=ECHO + "#frag")[0], 200)

    def test_json(self):
        cases = (("empty body", b""), ("not json", b"{nope"), ("array", b"[]"), ("null", b"null"),
                 ("number", b"1"), ("string", b'"x"'), ("true", b"true"),
                 ("invalid utf-8", b'{"a": "\xff"}'), ("bom", b"\xef\xbb\xbf{}"),
                 ("utf-16", '{"a": 1}'.encode("utf-16")), ("utf-32", '{"a": 1}'.encode("utf-32-le")),
                 ("trailing text", b"{} x"), ("deep nesting", b"[" * 60000),
                 ("deep object nesting", b'{"a":' * 9000 + b"1" + b"}" * 9000))
        for label, body in cases:
            self.assert_refused(self.post(body=body), 400, "bad_request", label)
        self.assertFalse(self.calls)

    # -- order

    def test_each_check_refuses_in_order_when_two_fail_at_once(self):
        port, token = self.port, self.token

        def host(spec):
            spec["host"] = "evil.example"

        def origin(spec):
            spec["headers"] = [(n, v) for n, v in spec["headers"] if n != "Origin"] + [("Origin", "null")]

        def fetch(spec):
            spec["headers"].append(("Sec-Fetch-Site", "none"))

        def ctype(spec):
            spec["headers"] = [(n, "text/plain" if n == "Content-Type" else v) for n, v in spec["headers"]]

        def transfer(spec):
            spec["headers"].append(("Transfer-Encoding", "chunked"))

        def length(spec):
            spec["body"] = b""
            spec["length"] = str(server.DRAIN_CAP + 1)

        def short(spec):
            spec["body"] = b"{"
            spec["length"] = "40"
            spec["half_close"] = True

        def wrong_token(spec):
            spec["headers"] = [(n, "wrong" if n == "X-Dashboard-Token" else v) for n, v in spec["headers"]]

        def bad_json(spec):
            spec["body"] = b"[]"

        steps = [("host", host, 403, "forbidden"), ("origin", origin, 403, "forbidden"),
                 ("fetch", fetch, 403, "forbidden"), ("ctype", ctype, 415, "bad_content_type"),
                 ("transfer", transfer, 400, "bad_request"), ("length", length, 413, "too_large"),
                 ("short", short, 400, "bad_request"), ("token", wrong_token, 403, "bad_token"),
                 ("json", bad_json, 400, "bad_request")]
        checked = 0
        for i, (name_a, break_a, status_a, error_a) in enumerate(steps):
            for name_b, break_b, _, _ in steps[i + 1:]:
                if {name_a, name_b} == {"length", "short"}:
                    continue  # both set Content-Length
                spec = {"host": "auto", "headers": good_headers(port, token), "body": JSON_BODY,
                        "length": "auto", "half_close": False}
                break_b(spec)
                break_a(spec)  # applied last, so a clash on one header keeps the earlier check's change
                result = send(port, "POST", ECHO, spec["headers"], spec["body"], length=spec["length"],
                              host=spec["host"], half_close=spec["half_close"])
                self.assert_refused(result, status_a, error_a, (name_a, name_b))
                checked += 1
        self.assertEqual(checked, 35)
        self.assertFalse(self.calls)

    def test_a_refused_request_never_runs_a_route(self):
        self.post(headers=good_headers(self.port, "wrong"))
        self.post(body=b"[]")
        self.assertFalse(self.calls)

    # -- methods on a write route

    def test_other_methods_on_a_write_route_get_405_allow_post(self):
        for path in WRITE_PATHS + (ECHO,):
            for method in ("GET", "HEAD", "PUT", "DELETE", "OPTIONS", "PROPFIND", "PATCH", "TRACE"):
                body = JSON_BODY if method in ("PUT", "PATCH") else None
                result = send(self.port, method, path, [("Origin", "http://127.0.0.1:%d" % self.port)], body)
                status, heads, data = result
                self.assertEqual(status, 405, (method, path))
                self.assertEqual(heads["allow"], "POST", (method, path))
                self.assertFalse([h for h in heads if h.startswith("access-control-")], (method, path))
                if method != "HEAD":
                    self.assertEqual(error_of(data), "method_not_allowed")
        self.assertFalse(self.calls)

    def test_a_preflight_gets_no_cors_headers(self):
        probe = [("Origin", "http://evil.example"), ("Access-Control-Request-Method", "POST"),
                 ("Access-Control-Request-Headers", "content-type, x-dashboard-token")]
        status, heads, _ = send(self.port, "OPTIONS", ECHO, probe)
        self.assertEqual(status, 403)
        self.assertFalse([h for h in heads if h.startswith("access-control-")])
        probe = [("Origin", "http://127.0.0.1:%d" % self.port)] + probe[1:]
        status, heads, _ = send(self.port, "OPTIONS", ECHO, probe)
        self.assertEqual(status, 405)
        self.assertEqual(heads["allow"], "POST")
        self.assertFalse([h for h in heads if h.startswith("access-control-")])

    def test_a_get_on_a_write_route_checks_the_host_and_origin_first(self):
        self.assertEqual(send(self.port, "GET", ECHO, host="evil.example")[0], 403)
        self.assertEqual(send(self.port, "GET", ECHO, [("Origin", "http://evil.example")])[0], 403)

    def test_the_other_routes_keep_todays_405_with_the_flag_on(self):
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "PROPFIND", "PATCH", "TRACE", "CONNECT"):
            for path in ("/api/settings", "/api/usage", "/", "/nope", "/api/edit", "/api/edit/targets",
                         "/api/edit/history"):
                body = b"x=1" if method in ("POST", "PUT", "PATCH") else None
                status, heads, data = send(self.port, method, path, (), body)
                self.assertEqual(status, 405, (method, path))
                self.assertEqual(heads.get("allow"), "GET, HEAD", (method, path))
                self.assertEqual(error_of(data), "method_not_allowed")

    def test_a_good_post_to_a_read_route_still_gets_405_get_head(self):
        for path in ("/api/settings", "/api/edit", "/"):
            status, heads, _ = self.post(path=path)
            self.assertEqual(status, 405, path)
            self.assertEqual(heads["allow"], "GET, HEAD")
        self.assertFalse(self.calls)

    # -- the read routes and the token

    def test_get_api_edit_reports_the_launch_without_the_token(self):
        status, heads, data = send(self.port, "GET", "/api/edit")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data), {"enabled": True, "launch_id": "launch-one"})
        self.assertEqual(heads["content-type"], server.JSON_TYPE)

    def test_the_token_is_in_no_response(self):
        paths = ["/", "/nope", "/api/nope", "/static/%2e%2e/server.py"] + sorted(server.ROUTES)
        paths += ["/static/" + name for name in sorted(os.listdir(STATIC))
                  if os.path.splitext(name)[1] in server.CONTENT_TYPES]
        self.assertGreater(len(paths), 15)
        for path in paths:
            for method in ("GET", "HEAD"):
                status, heads, data = send(self.port, method, path)
                self.assertNotIn(self.token.encode(), data, (method, path))
                self.assertNotIn(self.token, "".join(heads.values()), (method, path))
                self.assertNotIn("x-dashboard-token", heads)
        for result in (self.post(headers=good_headers(self.port, "wrong")), self.post(),
                       self.post(headers=good_headers(self.port, self.token, {"Origin": "null"}))):
            self.assertNotIn(self.token.encode(), result[2])
            self.assertNotIn(self.token, "".join(result[1].values()))

    def test_the_log_lines_hold_method_path_and_status_only(self):
        del self.logs[:]
        wrong = good_headers(self.port, "planted-wrong-token")
        self.post(path=ECHO + "?token=" + self.token, body=b'{"token": "%s"}' % self.token.encode(),
                  headers=wrong)
        self.post(path=ECHO + "?token=" + self.token)
        self.post(headers=good_headers(self.port, self.token, {"Origin": "http://planted-origin.example"}))
        self.post(body=b'{"planted": "planted-body"}')
        self.assertEqual(len(self.logs), 4)
        for line in self.logs:
            self.assertRegex(line, LOG_LINE)
            self.assertNotIn(self.token, line)
            self.assertNotIn("planted", line)
            self.assertNotIn("token=", line)
        self.assertEqual([line.split()[-1] for line in self.logs], ["403", "200", "403", "200"])

    def test_a_route_that_raises_gets_a_fixed_500(self):
        def boom(ctx, body):
            raise RuntimeError("planted-secret-value")

        ctx = self.ctx
        srv = server.Server(ctx, 0, {ECHO: boom})
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            port = srv.server_address[1]
            del self.logs[:]
            status, _, data = send(port, "POST", ECHO, good_headers(port, self.token), JSON_BODY)
            self.assertEqual(status, 500)
            self.assertEqual(json.loads(data), {"error": "internal"})
            self.assertNotIn(b"planted", data)
            self.assertNotIn("planted", "\n".join(self.logs))
            self.assertIn("route error 'RuntimeError'", self.logs)
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(10)


class ServerClass(unittest.TestCase):
    def test_write_routes_default_to_empty(self):
        self.assertEqual(server.write_routes_for(False), {})
        self.assertEqual(server.write_routes_for(None), {})
        self.assertEqual(sorted(server.write_routes_for(True)), list(WRITE_PATHS))
        ctx = server.fixture_context(ts.fixture_copy(self._root(), name="f"), None, None, RULES, FIELDS)
        srv = server.Server(ctx, 0)
        try:
            self.assertEqual(srv.write_routes, {})
        finally:
            srv.server_close()

    def _root(self):
        root = ts.make_root("mr-edit-")
        self.addCleanup(helpers.rmtree_force, root)
        return root

    def test_the_read_routes_are_in_the_table_and_no_write_route_is(self):
        for path in READ_EDIT_PATHS:
            self.assertIn(path, server.ROUTES)
        for path in WRITE_PATHS:
            self.assertNotIn(path, server.ROUTES)

    def test_the_edit_state_does_not_show_its_token(self):
        state = api_edit.EditState("planted-token-value", "launch-x", object())
        self.assertNotIn("planted-token-value", repr(state))
        self.assertNotIn("planted-token-value", str(state))
        ctx = dataclasses.replace(server.fixture_context(ts.fixture_copy(self._root()), None, None,
                                                         RULES, FIELDS), edit=state)
        self.assertNotIn("planted-token-value", repr(ctx))
        self.assertEqual(ctx, dataclasses.replace(ctx, edit=None))  # edit is left out of comparisons

    def test_api_edit_reports_off_without_state(self):
        ctx = server.fixture_context(ts.fixture_copy(self._root()), None, None, RULES, FIELDS)
        self.assertEqual(api_edit.edit_info(ctx, {}), (200, {"enabled": False, "launch_id": None}))
        status, body = api_edit.targets(ctx, {})
        self.assertEqual((status, body["enabled"]), (200, False))
        self.assertNotIn("targets", body)
        self.assertEqual(api_edit.history(ctx, {}), (200, {"enabled": False}))

    def test_edits_supported_here_and_not_without_the_pieces(self):
        self.assertTrue(server.edits_supported())
        with mock.patch.object(server.sys, "platform", "win32"):
            self.assertFalse(server.edits_supported())
        with mock.patch.object(os, "supports_dir_fd", set()):
            self.assertFalse(server.edits_supported())
        for missing in (os.open, os.rename, os.stat, os.mkdir, os.unlink):
            kept = set(os.supports_dir_fd) - {missing}
            with mock.patch.object(os, "supports_dir_fd", kept):
                self.assertFalse(server.edits_supported(), missing)
        with mock.patch.object(os, "supports_follow_symlinks", set()):
            self.assertFalse(server.edits_supported())
        with mock.patch.object(os, "supports_fd", set()):
            self.assertFalse(server.edits_supported())
        for name in ("O_NOFOLLOW", "O_DIRECTORY"):
            saved = getattr(os, name)
            delattr(os, name)
            try:
                self.assertFalse(server.edits_supported(), name)
            finally:
                setattr(os, name, saved)
        self.assertTrue(server.edits_supported())

    def test_the_flag_checks_run_in_order_and_start_nothing(self):
        fixture = ts.fixture_copy(self._root())
        argv = ["--fixture", fixture, "--allow-edits", "--port", "0"]
        with mock.patch.object(server, "edits_supported", return_value=False), \
                mock.patch.object(server, "_under") as under, \
                mock.patch.object(server, "Server") as made, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                server.main(argv, env={})
        self.assertNotEqual(caught.exception.code, 0)
        under.assert_not_called()
        made.assert_not_called()
        inside = os.path.join(helpers.REPO, "tests", "fixtures", "resolution", "env-block-over-shell")
        with mock.patch.object(server, "Server") as made, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                server.main(["--fixture", inside, "--allow-edits", "--port", "0"], env={})
        self.assertNotEqual(caught.exception.code, 0)
        made.assert_not_called()

    def test_under(self):
        self.assertTrue(server._under("/work/repo", "/work/repo"))
        self.assertTrue(server._under("/work/repo/a/b", "/work/repo"))
        self.assertFalse(server._under("/work/repo2", "/work/repo"))
        self.assertFalse(server._under("/work", "/work/repo"))
        self.assertTrue(server._under("/work/x", "/"))


# --------------------------------------------------------------------------
# Server processes

class DefaultLaunch(GateAssertions, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ts.make_root("mr-edit-")
        cls.fixture = ts.fixture_copy(cls.root)
        cls.srv = ts.start(cls.root, ["--fixture", cls.fixture])
        cls.port = cls.srv.port

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
        helpers.rmtree_force(cls.root)

    def test_the_first_line_is_the_bare_url_and_there_is_no_token(self):
        self.assertEqual(self.srv.url, "http://127.0.0.1:%d/" % self.port)
        self.assertIsNone(self.srv.token)
        self.assertEqual(self.srv.stdout().count("\n"), 1)

    def test_api_edit_says_edits_are_off(self):
        status, _, data = send(self.port, "GET", "/api/edit")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data), {"enabled": False, "launch_id": None})
        status, _, data = send(self.port, "GET", "/api/edit/history")
        self.assertEqual((status, json.loads(data)), (200, {"enabled": False}))
        status, _, data = send(self.port, "GET", "/api/edit/targets")
        body = json.loads(data)
        self.assertEqual(status, 200)
        self.assertIs(body["enabled"], False)
        for key in ("project", "runs_as", "levels_state", "project_lock", "files", "levels"):
            self.assertIn(key, body)
        for key in ("targets", "blocked", "saveable", "preselect"):
            self.assertNotIn(key, body)
        status, _, data = send(self.port, "GET", "/api/edit/targets?project=no-such-project")
        self.assertEqual((status, json.loads(data)), (404, {"error": "unknown_project"}))

    def test_a_post_to_each_write_path_gets_405_and_the_tree_is_unchanged(self):
        before = ts.hash_tree(self.fixture)
        token = secrets.token_urlsafe(32)
        for path in WRITE_PATHS + ("/api/edit/other",):
            for headers in ((), good_headers(self.port, token),
                            good_headers(self.port, token, extra=[("Sec-Fetch-Site", "same-origin")])):
                status, heads, data = send(self.port, "POST", path, headers, JSON_BODY)
                self.assertEqual(status, 405, path)
                self.assertEqual(heads["allow"], "GET, HEAD")
                self.assertEqual(error_of(data), "method_not_allowed")
        self.assertEqual(ts.hash_tree(self.fixture), before)

    def test_a_get_on_a_write_path_is_a_plain_404(self):
        for path in WRITE_PATHS:
            for method in ("GET", "HEAD"):
                status, heads, data = send(self.port, method, path)
                self.assertEqual(status, 404, (method, path))
                self.assertNotIn("allow", heads)
                if method == "GET":
                    self.assertEqual(error_of(data), "not_found")

    def test_the_405_matrix_is_the_same(self):
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "PROPFIND", "PATCH", "TRACE", "CONNECT"):
            for path in ("/api/settings", "/api/usage", "/", "/nope"):
                body = b"x=1" if method in ("POST", "PUT", "PATCH") else None
                status, heads, data = send(self.port, method, path, (), body)
                self.assertEqual(status, 405, (method, path))
                self.assertEqual(heads.get("allow"), "GET, HEAD")
                self.assertEqual(error_of(data), "method_not_allowed")


class FlagOn(GateAssertions, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ts.make_root("mr-edit-")
        cls.fixture = ts.fixture_copy(cls.root)
        cls.srvs = []
        try:
            for name in ("one", "two"):
                cls.srvs.append(ts.start(cls.root, ["--fixture", cls.fixture, "--allow-edits"], name=name))
        except Exception:
            cls.tearDownClass()
            raise
        cls.srv = cls.srvs[0]
        cls.port = cls.srv.port
        cls.token = cls.srv.token

    @classmethod
    def tearDownClass(cls):
        for proc in cls.srvs:
            proc.stop()
        helpers.rmtree_force(cls.root)

    def test_the_first_line_is_the_link_with_the_token(self):
        match = LINK.fullmatch(self.srv.url)
        self.assertTrue(match, self.srv.url)
        self.assertEqual(self.token, match.group(1))
        self.assertEqual(self.srv.url, "http://127.0.0.1:%d/#/settings?edit=%s" % (self.port, self.token))
        self.assertEqual(self.srv.stdout().count("\n"), 1)
        self.assertEqual(self.srv.stdout().count(self.token), 1)

    def test_every_launch_has_its_own_token_and_launch_id(self):
        first, second = self.srvs
        self.assertNotEqual(first.token, second.token)
        ids = []
        for proc in self.srvs:
            status, _, data = send(proc.port, "GET", "/api/edit")
            self.assertEqual(status, 200)
            info = json.loads(data)
            self.assertEqual(set(info), {"enabled", "launch_id"})
            self.assertIs(info["enabled"], True)
            self.assertIsInstance(info["launch_id"], str)
            self.assertGreaterEqual(len(info["launch_id"]), 16)
            self.assertNotEqual(info["launch_id"], proc.token)
            self.assertEqual(json.loads(send(proc.port, "GET", "/api/edit")[2]), info)
            ids.append(info["launch_id"])
        self.assertNotEqual(*ids)

    def test_the_targets_answer_has_file_rows_and_no_level_target(self):
        status, _, data = send(self.port, "GET", "/api/edit/targets")
        self.assertEqual(status, 200)
        body = json.loads(data)
        self.assertIs(body["enabled"], True)
        self.assertIsInstance(body["saveable"], bool)
        self.assertEqual([row["layer"] for row in body["files"]], ["local", "project", "user"])
        for row in body["files"]:
            self.assertEqual(set(row), {"layer", "file_display", "state", "line", "value", "status", "target",
                                        "shared", "lock_reason"})
            self.assertIn(row["state"], ("has_line", "no_line", "absent", "locked"))
        for level in body["levels"]:
            self.assertNotIn("target", level)
            self.assertEqual(set(level), {"level", "result", "runs_as", "certain", "limits", "files",
                                          "preselect", "saveable"})
            self.assertTrue(level["preselect"] is None or isinstance(level["preselect"], str))
        self.assertNotIn(self.token.encode(), data)

    def test_no_route_or_static_file_returns_the_token(self):
        paths = ["/", "/nope", "/api/nope"] + sorted(server.ROUTES)
        paths += ["/static/" + name for name in sorted(os.listdir(STATIC))
                  if os.path.splitext(name)[1] in server.CONTENT_TYPES]
        for path in paths:
            for proc in self.srvs:
                status, heads, data = send(proc.port, "GET", path)
                self.assertNotIn(proc.token.encode(), data, path)
                self.assertNotIn(proc.token, "".join(heads.values()), path)
        for path in WRITE_PATHS:
            status, heads, data = send(self.port, "GET", path)
            self.assertEqual(status, 405, path)
            self.assertNotIn(self.token.encode(), data)

    def test_the_405_matrix_is_the_same_with_the_flag_on(self):
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "PROPFIND", "PATCH", "TRACE", "CONNECT"):
            for path in ("/api/settings", "/api/usage", "/", "/nope"):
                body = b"x=1" if method in ("POST", "PUT", "PATCH") else None
                status, heads, data = send(self.port, method, path, (), body)
                self.assertEqual(status, 405, (method, path))
                self.assertEqual(heads.get("allow"), "GET, HEAD")
                self.assertEqual(error_of(data), "method_not_allowed")

    def test_the_gate_guards_each_write_path_in_a_real_process(self):
        for path in WRITE_PATHS:
            self.assert_refused(send(self.port, "POST", path, (), JSON_BODY), 403, "forbidden", path)
            origin_only = [("Origin", "http://127.0.0.1:%d" % self.port)]
            self.assert_refused(send(self.port, "POST", path, origin_only, JSON_BODY), 415,
                                "bad_content_type", path)
            self.assert_refused(send(self.port, "POST", path, good_headers(self.port, "wrong"), JSON_BODY),
                                403, "bad_token", path)
            self.assert_refused(send(self.port, "POST", path, good_headers(self.port, self.token), b"[]"),
                                400, "bad_request", path)
            self.assertEqual(send(self.port, "GET", path)[1]["allow"], "POST")

    def test_the_token_is_not_logged_and_the_tree_is_unchanged(self):
        before = ts.hash_tree(self.fixture)
        token = self.token
        self.assert_refused(
            send(self.port, "POST", "/api/edit/save?token=" + token,
                 good_headers(self.port, "planted-wrong"), json.dumps({"token": token}).encode()),
            403, "bad_token")
        send(self.port, "POST", "/api/edit/save", good_headers(self.port, token, drop=("Origin",)), JSON_BODY)
        status = send(self.port, "POST", "/api/edit/save", good_headers(self.port, token), JSON_BODY)[0]
        self.assertNotIn(status, (403, 413, 415))  # past the gate; the route may refuse the body
        send(self.port, "POST", "/api/edit/preview", good_headers(self.port, token), b"{}")
        send(self.port, "POST", "/api/edit/undo", good_headers(self.port, token), b"{}")
        err = self.srv.stderr()
        self.assertNotIn(token, err)
        self.assertNotIn("planted", err)
        lines = err.splitlines()
        self.assertGreaterEqual(len(lines), 5)
        for line in lines:
            self.assertRegex(line, LOG_LINE)
        self.assertIn("POST '/api/edit/save' 403", lines)
        self.assertEqual(ts.hash_tree(self.fixture), before)

    def test_a_default_launch_checks_hold_with_the_flag_on(self):
        for host in ("evil.example", None):
            self.assert_refused(send(self.port, "POST", "/api/edit/save", good_headers(self.port, self.token),
                                     JSON_BODY, host=host), 403, "forbidden")
        status, heads, _ = send(self.port, "GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertFalse([h for h in heads if h.startswith("access-control-")])


class FixtureUnderTheRepo(ts.TempCase):
    def run_main(self, folder, *extra):
        argv = [sys.executable, "-B", SERVER_PY, "--fixture", folder, "--allow-edits", "--port", "0"] + list(extra)
        env = ts.base_env(self.root)
        try:
            done = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=30)
        except subprocess.TimeoutExpired:
            self.fail("the server started for %s" % folder)
        return done

    def assert_refused_start(self, folder):
        done = self.run_main(folder)
        self.assertNotEqual(done.returncode, 0, folder)
        self.assertEqual(done.stdout, b"", folder)
        self.assertTrue(os.path.isdir(folder), folder)  # refused for the flag, not for a missing folder

    def test_a_fixture_in_the_repo_exits_non_zero(self):
        inside = os.path.join(helpers.REPO, "tests", "fixtures", "resolution", "env-block-over-shell")
        self.assertTrue(os.path.isdir(inside))
        self.assert_refused_start(inside)
        self.assert_refused_start(os.path.join(helpers.REPO, "docs"))
        self.assert_refused_start(helpers.REPO)
        self.assert_refused_start(helpers.REPO + "/dashboard/../tests")

    def test_a_link_into_the_repo_exits_non_zero(self):
        link = os.path.join(self.root, "linked")
        os.symlink(os.path.join(helpers.REPO, "tests", "fixtures", "resolution", "env-block-over-shell"), link)
        self.assert_refused_start(link)

    def test_a_default_launch_may_still_read_a_fixture_in_the_repo(self):
        inside = os.path.join(helpers.REPO, "tests", "fixtures", "resolution", "env-block-over-shell")
        proc = self.start(["--fixture", inside])
        self.assertEqual(proc.request("GET", "/api/settings")[0], 200)

    def test_help_lists_the_flag(self):
        done = subprocess.run([sys.executable, "-B", SERVER_PY, "--help"], env=ts.base_env(self.root),
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30)
        self.assertEqual(done.returncode, 0)
        self.assertIn(b"--allow-edits", done.stdout)


if __name__ == "__main__":
    unittest.main()

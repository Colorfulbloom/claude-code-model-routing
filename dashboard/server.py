#!/usr/bin/env python3
"""A read-only local server for the Routing Dashboard.

    python3 dashboard/server.py [--config-dir DIR] [--project DIR]
                                [--port N] [--fixture FOLDER]

It prints its URL, http://127.0.0.1:<port>/, and serves the files in
dashboard/static/ plus the resolved settings as JSON. It binds 127.0.0.1 and
nothing else, and there is no option to change that. It answers GET and HEAD
only, and it writes no file of any kind, __pycache__ included.

Config dir. --config-dir, else CLAUDE_CONFIG_DIR, else $HOME/.claude, the rule
install.py uses (see default_config_dir). The project is --project, else the
folder the server started in.

Fixture run. --fixture FOLDER reads a folder laid out like
tests/fixtures/resolution/<case>: config/, project/, managed/ and session.json.
Every one of those may be missing. The shell is session.json's shell_env, never
the real environment, and the managed folder is FOLDER/managed, never the real
one. CLAUDE_CONFIG_DIR and HOME are not consulted.

Safety rules the handler keeps:
  * The Host header must be 127.0.0.1:<port> or localhost:<port>, and an Origin
    header, when present, must be http:// plus one of those, and a
    Sec-Fetch-Site header, when present, must be same-origin or none. The one
    exception is a top-level load of "/", which holds no settings. Anything
    else gets a 403 with no settings data. No response carries a CORS header.
  * Only "/", "/static/<file>" and the routes in ROUTES map to anything.
  * A response, a log line or an error message never holds a value
    collect.py hides. Logs name the method, the path without its query and the
    status. A failed route logs its exception class and nothing else.

Standard library only, Python 3.9.
"""
import sys

sys.dont_write_bytecode = True  # before any repo module is imported

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import http.server  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
import socketserver  # noqa: E402
import urllib.parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import api_settings  # noqa: E402
import collect  # noqa: E402
import projects  # noqa: E402
import resolve  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8377
STATIC_DIR = os.path.join(HERE, "static")
STATIC_PREFIX = "/static/"
INDEX = "index.html"

# Where Claude Code keeps file-based managed settings, from
# https://code.claude.com/docs/en/managed-settings.md (macOS; Linux and WSL; Windows).
MANAGED_DIRS = {
    "darwin": "/Library/Application Support/ClaudeCode",
    "linux": "/etc/claude-code",
    "win32": r"C:\Program Files\ClaudeCode",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}
JSON_TYPE = "application/json; charset=utf-8"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = (
    ("Content-Security-Policy", CSP),
    ("X-Content-Type-Options", "nosniff"),
    ("Cache-Control", "no-store"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
)
ERROR_NAMES = {
    400: "bad_request",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    408: "timeout",
    414: "uri_too_long",
    431: "headers_too_large",
    500: "internal",
}
LOG_PATH_CAP = 200
DRAIN_CAP = 65536

# One line per route. Each is a function (ctx, query) -> (status, payload).
ROUTES = {
    "/api/projects": projects.api_projects,
    "/api/settings": api_settings.settings,
}


# --------------------------------------------------------------------------
# Context and start-up rules

@dataclasses.dataclass(frozen=True)
class Context:
    """Everything a route may read. Built once at start-up.

    shell_label None means resolve's default label for a live shell.
    """

    config_dir: str
    project_dir: str
    managed_dir: object
    shell_env: dict
    home: object
    root: object
    flags: tuple
    cli_settings: object
    shell_label: object
    rules: dict
    agent_fields: list
    static_dir: str = STATIC_DIR
    project_explicit: bool = False  # --project was given


def default_config_dir(env, cwd):
    """The config dir: CLAUDE_CONFIG_DIR else $HOME/.claude, as install.py does.

    A relative value is taken from cwd, and trailing slashes are dropped.
    """
    target = env.get("CLAUDE_CONFIG_DIR") or (env.get("HOME", "") + "/.claude")
    while len(target) > 1 and target.endswith("/"):
        target = target[:-1]
    if not target.startswith("/"):
        target = os.path.realpath(cwd) + "/" + target
    return target


def managed_dir_for(platform):
    """The real managed settings folder for a platform, or None when unknown."""
    for prefix, folder in MANAGED_DIRS.items():
        if platform.startswith(prefix):
            return folder
    return None


def _read_object(path):
    """Return the JSON object in a file, or {} when it is missing or not an object."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def live_context(config_dir, project_dir, env, platform, rules, agent_fields,
                 project_explicit=False):
    """Context for a run on the real machine."""
    return Context(
        config_dir=config_dir,
        project_dir=project_dir,
        managed_dir=managed_dir_for(platform),
        shell_env=dict(env),
        home=env.get("HOME") or None,
        root=None,
        flags=(),
        cli_settings=None,
        shell_label=None,
        rules=rules,
        agent_fields=agent_fields,
        project_explicit=project_explicit)


def fixture_context(folder, config_dir, project_dir, rules, agent_fields,
                    project_explicit=False):
    """Context for a fixture run. Reads nothing from the real machine."""
    folder = os.path.abspath(folder)
    session = _read_object(os.path.join(folder, "session.json"))
    shell_env = session.get("shell_env")
    flags = session.get("flags")
    return Context(
        config_dir=config_dir or os.path.join(folder, "config"),
        project_dir=project_dir or os.path.join(folder, "project"),
        managed_dir=os.path.join(folder, "managed"),
        shell_env=dict(shell_env) if isinstance(shell_env, dict) else {},
        home=None,
        root=folder,
        flags=tuple(flags) if isinstance(flags, list) else (),
        cli_settings=collect.mask(session.get("cli_settings")),
        shell_label=resolve.LABEL_SHELL,
        rules=rules,
        agent_fields=agent_fields,
        project_explicit=project_explicit)


# --------------------------------------------------------------------------
# The HTTP handler

def _clean(text, cap):
    """Escape text for a log line and cut it to cap characters, closing quote kept."""
    out = ascii(text)
    return out if len(out) <= cap else out[:cap - 1] + out[0]


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "RoutingDashboard"
    protocol_version = "HTTP/1.0"
    timeout = 15

    def version_string(self):
        return self.server_version

    # -- logging: one line per request, never a message built from request text

    def log_request(self, code="-", size="-"):
        method = _clean(getattr(self, "command", None) or "-", 32)[1:-1]
        path = (getattr(self, "path", None) or "-").partition("#")[0].partition("?")[0]
        self.log_message("%s %s %s", method, _clean(path, LOG_PATH_CAP), code)

    def log_message(self, format, *args):
        sys.stderr.write((format % args) + "\n")
        sys.stderr.flush()

    def log_error(self, format, *args):
        """Say nothing. The text these messages carry can hold request data."""

    # -- sending

    def _send(self, status, content_type, body, extra=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        if getattr(self, "command", None) != "HEAD":
            self.wfile.write(body)

    def _send_error_json(self, status, extra=()):
        body = json.dumps({"error": ERROR_NAMES.get(status, "error")}).encode("utf-8")
        self._send(status, JSON_TYPE, body, extra)

    def send_error(self, code, message=None, explain=None):
        """Send a fixed JSON body. The default page echoes request text."""
        self.close_connection = True
        self._send_error_json(code)

    # -- checks

    def _allowed(self, prefix):
        port = self.server.server_address[1]
        return {"%s127.0.0.1:%d" % (prefix, port), "%slocalhost:%d" % (prefix, port)}

    def _host_ok(self):
        hosts = self.headers.get_all("Host") or []
        return len(hosts) == 1 and hosts[0].strip().lower() in self._allowed("")

    def _origin_ok(self):
        origins = self.headers.get_all("Origin") or []
        if not origins:
            return True
        return len(origins) == 1 and origins[0].strip().lower() in self._allowed("http://")

    def _fetch_site_ok(self):
        """A browser's no-cors GET from another page sends no Origin but does send this.

        One cross-site request is allowed: a top-level load of "/", such as a link
        on another site. That page holds no settings, and frame-ancestors stops it
        being framed, so the other site can open it but cannot read anything.
        """
        sites = self.headers.get_all("Sec-Fetch-Site") or []
        if not sites:
            return True
        if len(sites) == 1 and sites[0].strip().lower() in ("same-origin", "none"):
            return True
        return len(sites) == 1 and self._top_level_page_load()

    def _top_level_page_load(self):
        modes = self.headers.get_all("Sec-Fetch-Mode") or []
        dests = self.headers.get_all("Sec-Fetch-Dest") or []
        path = self.path.partition("#")[0].partition("?")[0]
        return (self.command == "GET" and path == "/"
                and [v.strip().lower() for v in modes] == ["navigate"]
                and [v.strip().lower() for v in dests] == ["document"])

    def _drain_body(self):
        """Read a small request body so closing the socket does not reset the reply."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if 0 < length <= DRAIN_CAP:
            try:
                self.rfile.read(length)
            except OSError:
                pass

    # -- methods

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def __getattr__(self, name):
        # Any other verb, PROPFIND included, lands here and gets a 405.
        if name.startswith("do_"):
            return self._handle
        raise AttributeError(name)

    def _handle(self):
        self._drain_body()
        if not (self._host_ok() and self._origin_ok() and self._fetch_site_ok()):
            self._send_error_json(403)
            return
        if self.command not in ("GET", "HEAD"):
            self._send_error_json(405, (("Allow", "GET, HEAD"),))
            return
        raw_path = self.path.partition("#")[0]
        path, _, query = raw_path.partition("?")
        route = ROUTES.get(path)
        if route is not None:
            self._run_route(route, query)
        elif path == "/":
            self._send_static(INDEX)
        elif path.startswith(STATIC_PREFIX):
            self._send_static(urllib.parse.unquote(path[len(STATIC_PREFIX):]))
        else:
            self._send_error_json(404)

    def _run_route(self, route, query):
        try:
            parsed = urllib.parse.parse_qs(query, max_num_fields=50)
        except ValueError:
            self._send_error_json(400)
            return
        try:
            status, payload = route(self.server.ctx, parsed)
            body = json.dumps(payload).encode("utf-8")
        except Exception as exc:  # no traceback and no str(exc): either could hold a value
            self.log_message("route error %s", _clean(type(exc).__name__, 60))
            self._send_error_json(500)
            return
        self._send(status, JSON_TYPE, body)

    def _send_static(self, rel):
        """Send a file below the static folder, or a bare 404."""
        found = self._find_static(rel)
        if found is None:
            self._send_error_json(404)
            return
        full, content_type = found
        try:
            with open(full, "rb") as fh:
                body = fh.read()
        except OSError:
            self._send_error_json(404)
            return
        self._send(200, content_type, body)

    def _find_static(self, rel):
        """Return (real path, content type) for a servable file, else None."""
        if rel == "" or "\x00" in rel or "\\" in rel or rel.startswith("/"):
            return None
        parts = rel.split("/")
        if any(part == "" or part.startswith(".") for part in parts):
            return None
        content_type = CONTENT_TYPES.get(os.path.splitext(parts[-1])[1].lower())
        if content_type is None:
            return None
        base = os.path.realpath(self.server.ctx.static_dir)
        full = os.path.realpath(os.path.join(base, *parts))
        if not full.startswith(base + os.sep) or os.path.basename(full).startswith("."):
            return None
        if not os.path.isfile(full):
            return None
        return full, content_type


class Server(http.server.ThreadingHTTPServer):
    """Binds 127.0.0.1 on the given port. The address is not a parameter."""

    daemon_threads = True
    address_family = socket.AF_INET

    def __init__(self, ctx, port=DEFAULT_PORT):
        self.ctx = ctx
        super().__init__((HOST, port), Handler)

    def server_bind(self):
        # HTTPServer.server_bind looks the host name up. Loopback needs none.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def handle_error(self, request, client_address):
        # The default prints a traceback, which could carry a value.
        name = sys.exc_info()[0].__name__ if sys.exc_info()[0] else "Error"
        sys.stderr.write("connection error %s\n" % _clean(name, 60))
        sys.stderr.flush()


# --------------------------------------------------------------------------
# Command line

def _port(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not a port number")
    if not 0 <= value <= 65535:
        raise argparse.ArgumentTypeError("not a port number")
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog="server.py",
        description="Read-only local server for the Routing Dashboard. Binds 127.0.0.1 only.")
    parser.add_argument("--config-dir", help="Claude config folder (default: "
                        "CLAUDE_CONFIG_DIR, else $HOME/.claude)")
    parser.add_argument("--project", help="project folder (default: the folder the server "
                        "started in)")
    parser.add_argument("--port", type=_port, default=DEFAULT_PORT,
                        help="port to listen on; 0 asks the system for a free one "
                        "(default: %d)" % DEFAULT_PORT)
    parser.add_argument("--fixture", metavar="FOLDER",
                        help="read a fixture folder instead of the real machine")
    return parser


def main(argv=None, env=None):
    """Start the server. This is the only place that reads os.environ."""
    parser = build_parser()
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    cwd = os.getcwd()
    if args.fixture is not None and not os.path.isdir(args.fixture):
        parser.error("--fixture needs an existing folder")
    rules = resolve.load_rules()
    agent_fields = resolve.load_agent_fields()
    config_dir = os.path.abspath(args.config_dir) if args.config_dir else None
    project_dir = os.path.abspath(args.project) if args.project else None
    if args.fixture is not None:
        ctx = fixture_context(args.fixture, config_dir, project_dir, rules, agent_fields,
                              project_explicit=args.project is not None)
    else:
        ctx = live_context(config_dir or default_config_dir(env, cwd), project_dir or cwd,
                           env, sys.platform, rules, agent_fields,
                           project_explicit=args.project is not None)
    try:
        server = Server(ctx, args.port)
    except OSError:
        sys.stderr.write("server: cannot listen on 127.0.0.1:%d, the port may be in use\n"
                         % args.port)
        return 1
    sys.stdout.write("http://%s:%d/\n" % (HOST, server.server_address[1]))
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

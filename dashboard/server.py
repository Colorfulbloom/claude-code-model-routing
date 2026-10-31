#!/usr/bin/env python3
"""A local server for the Routing Dashboard, read-only unless --allow-edits is on.

    python3 dashboard/server.py [--config-dir DIR] [--project DIR]
                                [--port N] [--fixture FOLDER] [--allow-edits]

It prints its URL, http://127.0.0.1:<port>/, and serves the files in
dashboard/static/ plus the resolved settings as JSON. It binds 127.0.0.1 and
nothing else, and there is no option to change that. A default launch answers
GET and HEAD only and writes no file of any kind, __pycache__ included.

Edits. --allow-edits adds POST on the routes in write_routes_for, and the URL
it prints ends in #/settings?edit=<token>. The token is new on each launch, and
a fragment never reaches a server or a log. edit_store.py does every write, to
one settings file and to <config dir>/routing-dashboard/backups/. A save changes
an effort value on a line that already exists in a user, project or local file.
It adds no line and creates no file. The flag refuses to start on win32 or with
a fixture inside the repo.

Config dir. --config-dir, else CLAUDE_CONFIG_DIR, else $HOME/.claude, the rule
install.py uses (see default_config_dir). The project is --project, else the
folder the server started in.

Fixture run. --fixture FOLDER reads a folder laid out like
tests/fixtures/resolution/<case>: config/, project/, managed/ and session.json,
and a repo/ folder that stands in for the repo /api/files compares config/
with (without it, the real repo). Every one of those may be missing. The shell is session.json's shell_env, never
the real environment, and the managed folder is FOLDER/managed, never the real
one. CLAUDE_CONFIG_DIR and HOME are not consulted. The zone is session.json's
"tz", else shell_env's TZ, and the clock is its "now" (an ISO time with an
offset) when it has one, else the real clock. The usage routes read the
transcripts in config/projects/, and a thread warms that read at start-up.

Safety rules the handler keeps:
  * The Host header must be 127.0.0.1:<port> or localhost:<port>, and an Origin
    header, when present, must be http:// plus one of those, and a
    Sec-Fetch-Site header, when present, must be same-origin or none. The one
    exception is a top-level load of "/", which holds no settings. Anything
    else gets a 403 with no settings data. No response carries a CORS header.
  * Only "/", "/static/<file>", the routes in ROUTES and, with --allow-edits,
    the routes from write_routes_for map to anything.
  * A POST reaches a write route only through Handler._handle_write, and every
    check there runs before any file is touched. The Host rule above holds. The
    Origin header is required and must be one of the two above, and a
    Sec-Fetch-Site header, when present, must be same-origin, so the top-level
    exception never applies. The Content-Type must be exactly application/json
    and the body at most DRAIN_CAP bytes. The request needs exactly one
    X-Dashboard-Token header, and it must match this launch's token.
  * The token comes only from the URL main prints. No route returns it, and the
    server never takes it from a query string or a body and never logs it.
  * Without --allow-edits the write routes are empty, so a POST to one gets the
    same 405 as any other POST.
  * A response, a log line or an error message never holds a value
    collect.py hides. Logs name the method, the path without its query and the
    status. A failed route logs its exception class and nothing else.

Standard library only, Python 3.9.
"""
import sys

sys.dont_write_bytecode = True  # before any repo module is imported

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import datetime  # noqa: E402
import hmac  # noqa: E402
import http.server  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import secrets  # noqa: E402
import socket  # noqa: E402
import socketserver  # noqa: E402
import urllib.parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import api_edit  # noqa: E402
import api_settings  # noqa: E402
import api_usage  # noqa: E402
import collect  # noqa: E402
import edit_store  # noqa: E402
import resolve  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8377
STATIC_DIR = os.path.join(HERE, "static")
REPO_DIR = os.path.dirname(HERE)  # the repo /api/files compares the config folder with
STATIC_PREFIX = "/static/"
INDEX = "index.html"
LOCALTIME_LINK = "/etc/localtime"

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
    413: "too_large",
    414: "uri_too_long",
    415: "bad_content_type",
    431: "headers_too_large",
    500: "internal",
}
LOG_PATH_CAP = 200
DRAIN_CAP = 65536

# One line per route. Each is a function (ctx, query) -> (status, payload).
ROUTES = {
    "/api/edit": api_edit.edit_info,
    "/api/edit/history": api_edit.history,
    "/api/edit/targets": api_edit.targets,
    "/api/files": api_settings.files,
    "/api/projects": api_usage.api_projects,
    "/api/rules": api_settings.rules,
    "/api/settings": api_settings.settings,
    "/api/usage": api_usage.usage,
}


def write_routes_for(allow):
    """The write routes of a launch: empty unless --allow-edits is on.

    Each is a function (ctx, body) -> (status, payload), where body is the parsed
    JSON object. Only a POST that passes Handler._handle_write reaches one.
    """
    if not allow:
        return {}
    return {
        "/api/edit/preview": api_edit.preview,
        "/api/edit/save": api_edit.save,
        "/api/edit/undo": api_edit.undo,
    }


def edits_supported():
    """True where the edit store can work by descriptor: no win32, and the dir_fd calls exist."""
    if sys.platform.startswith("win32"):
        return False
    if not (hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")):
        return False
    needs_dir_fd = (os.open, os.rename, os.stat, os.mkdir, os.unlink)
    if not all(fn in os.supports_dir_fd for fn in needs_dir_fd):
        return False
    return os.stat in os.supports_follow_symlinks and os.listdir in os.supports_fd


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
    repo_dir: str = REPO_DIR  # the repo whose files /api/files expects in the config folder
    project_explicit: bool = False  # --project was given
    tz_name: object = None  # the TZ value, or None
    localtime_link: object = None  # the /etc/localtime link to read, or None
    fixed_now: object = None  # an aware datetime that replaces the clock, or None
    claude_version: object = None  # a fixture's fixed installed version, or None
    path_env: object = None  # the PATH text to search for claude, or None (read nothing)
    usage_cache: object = dataclasses.field(default_factory=api_usage.Cache, compare=False,
                                            repr=False)
    edit: object = dataclasses.field(default=None, compare=False, repr=False)  # api_edit.EditState, or None


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
        project_explicit=project_explicit,
        tz_name=env.get("TZ") or None,
        localtime_link=LOCALTIME_LINK,
        path_env=env.get("PATH"))


def mask_flags(flags):
    """Mask each launch flag word. A word of the form --name=value keeps its name and masks the value."""
    out = []
    for word in flags:
        if isinstance(word, str) and "=" in word:
            name, _sep, value = word.partition("=")
            out.append(name + "=" + collect.mask(value))
        else:
            out.append(collect.mask(word))
    return tuple(out)


def fixture_context(folder, config_dir, project_dir, rules, agent_fields,
                    project_explicit=False):
    """Context for a fixture run. Reads nothing from the real machine."""
    folder = os.path.abspath(folder)
    session = _read_object(os.path.join(folder, "session.json"))
    shell_env = session.get("shell_env")
    flags = session.get("flags")
    shell_zone = shell_env.get("TZ") if isinstance(shell_env, dict) else None
    tz_name = session.get("tz") if isinstance(session.get("tz"), str) else (
        shell_zone if isinstance(shell_zone, str) else None)
    repo = os.path.join(folder, "repo")
    return Context(
        config_dir=config_dir or os.path.join(folder, "config"),
        project_dir=project_dir or os.path.join(folder, "project"),
        managed_dir=os.path.join(folder, "managed"),
        repo_dir=repo if os.path.isdir(repo) else REPO_DIR,
        shell_env=dict(shell_env) if isinstance(shell_env, dict) else {},
        home=None,
        root=folder,
        flags=mask_flags(flags) if isinstance(flags, list) else (),
        cli_settings=collect.mask(session.get("cli_settings")),
        shell_label=resolve.LABEL_SHELL,
        rules=rules,
        agent_fields=agent_fields,
        project_explicit=project_explicit,
        tz_name=tz_name,
        fixed_now=_fixture_now(session.get("now")),
        claude_version=session.get("claude_version") if isinstance(session.get("claude_version"), str) else None)


def _fixture_now(value):
    """The fixture's clock: an ISO time with an offset, else None (the real clock)."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.utcoffset() is not None else None


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

    def _send_error_json(self, status, extra=(), name=None):
        body = json.dumps({"error": name or ERROR_NAMES.get(status, "error")}).encode("utf-8")
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
        """Read a small request body so closing the socket does not reset the reply.

        Returns the bytes read, or b"" when it read none.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return b""
        if 0 < length <= DRAIN_CAP:
            try:
                return self.rfile.read(length)
            except OSError:
                pass
        return b""

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
        raw_path = self.path.partition("#")[0]
        path, _, query = raw_path.partition("?")
        write_routes = self.server.write_routes
        if self.command == "POST" and path in write_routes:
            self._handle_write(path)
            return
        self._drain_body()
        if not (self._host_ok() and self._origin_ok() and self._fetch_site_ok()):
            self._send_error_json(403)
            return
        if path in write_routes:
            self._send_error_json(405, (("Allow", "POST"),))
            return
        if self.command not in ("GET", "HEAD"):
            self._send_error_json(405, (("Allow", "GET, HEAD"),))
            return
        route = ROUTES.get(path)
        if route is not None:
            self._run_route(route, query)
        elif path == "/":
            self._send_static(INDEX)
        elif path.startswith(STATIC_PREFIX):
            self._send_static(urllib.parse.unquote(path[len(STATIC_PREFIX):]))
        else:
            self._send_error_json(404)

    def _handle_write(self, path):
        """The gate for a POST to a write route. Every check runs before any file is touched."""
        body = self._drain_body()
        if not self._host_ok():
            self._send_error_json(403)
            return
        origins = self.headers.get_all("Origin") or []
        if not (len(origins) == 1 and origins[0].strip().lower() in self._allowed("http://")):
            self._send_error_json(403)
            return
        sites = self.headers.get_all("Sec-Fetch-Site") or []
        if sites and not (len(sites) == 1 and sites[0].strip().lower() == "same-origin"):
            self._send_error_json(403)
            return
        types = self.headers.get_all("Content-Type") or []
        if not (len(types) == 1 and types[0].strip().lower() == "application/json"):
            self._send_error_json(415)
            return
        if self.headers.get_all("Transfer-Encoding"):
            self._send_error_json(400)
            return
        lengths = self.headers.get_all("Content-Length") or []
        text = lengths[0].strip() if len(lengths) == 1 else ""
        if not (text.isascii() and text.isdigit() and len(text) <= 10 and int(text) <= DRAIN_CAP):
            self._send_error_json(413)
            return
        if len(body) < int(text):
            self._send_error_json(400)
            return
        if not self._token_ok():
            self._send_error_json(403, name="bad_token")
            return
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
            parsed = None
        if not isinstance(parsed, dict):
            self._send_error_json(400)
            return
        self._call_route(self.server.write_routes[path], parsed)

    def _token_ok(self):
        """True when there is exactly one X-Dashboard-Token header and it is this launch's token."""
        state = self.server.ctx.edit
        values = self.headers.get_all("X-Dashboard-Token") or []
        if state is None or len(values) != 1:
            return False
        try:
            given = values[0].encode("utf-8", "surrogateescape")
            expected = state.token.encode("utf-8")
        except (AttributeError, UnicodeError):
            return False
        return hmac.compare_digest(given, expected)

    def _run_route(self, route, query):
        try:
            parsed = urllib.parse.parse_qs(query, max_num_fields=50)
        except ValueError:
            self._send_error_json(400)
            return
        self._call_route(route, parsed)

    def _call_route(self, route, arg):
        try:
            status, payload = route(self.server.ctx, arg)
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
    # The default of 5 resets a burst of connections. Every file opens its own connection here (HTTP/1.0),
    # and one reset module stops the whole page before any script runs.
    request_queue_size = 128

    def __init__(self, ctx, port=DEFAULT_PORT, write_routes=None):
        self.ctx = ctx
        self.write_routes = write_routes or {}
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
        description="Local server for the Routing Dashboard. Binds 127.0.0.1 only. "
        "Read-only unless --allow-edits is on.")
    parser.add_argument("--config-dir", help="Claude config folder (default: "
                        "CLAUDE_CONFIG_DIR, else $HOME/.claude)")
    parser.add_argument("--project", help="project folder (default: the folder the server "
                        "started in)")
    parser.add_argument("--port", type=_port, default=DEFAULT_PORT,
                        help="port to listen on; 0 asks the system for a free one "
                        "(default: %d)" % DEFAULT_PORT)
    parser.add_argument("--fixture", metavar="FOLDER",
                        help="read a fixture folder instead of the real machine")
    parser.add_argument("--allow-edits", action="store_true",
                        help="turn on the edit routes and print a link with a key "
                        "for this launch; only that link unlocks editing "
                        "(default: off, and the server writes no file)")
    return parser


def _under(path, folder):
    """True when path is folder or lies below it. Both are real paths."""
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def main(argv=None, env=None):
    """Start the server. This is the only place that reads os.environ."""
    parser = build_parser()
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    cwd = os.getcwd()
    if args.fixture is not None and not os.path.isdir(args.fixture):
        parser.error("--fixture needs an existing folder")
    if args.allow_edits:
        if not edits_supported():
            parser.error("--allow-edits needs file calls this system lacks, "
                         "so it can't run here (Windows is one such system)")
        if args.fixture is not None and _under(os.path.realpath(args.fixture),
                                                os.path.realpath(REPO_DIR)):
            parser.error("--allow-edits refuses a fixture inside the repo, so a save "
                         "can't change it; copy the fixture outside the repo first")
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
    token = None
    if args.allow_edits:
        token = secrets.token_urlsafe(32)
        state = api_edit.EditState(token, secrets.token_urlsafe(16),
                                   edit_store.Store(ctx.config_dir, fixed_now=ctx.fixed_now))
        ctx = dataclasses.replace(ctx, edit=state)
    try:
        server = Server(ctx, args.port, write_routes_for(args.allow_edits))
    except OSError:
        sys.stderr.write("server: cannot listen on 127.0.0.1:%d, the port may be in use\n"
                         % args.port)
        return 1
    api_usage.start_warm(ctx)
    if token is None:
        sys.stdout.write("http://%s:%d/\n" % (HOST, server.server_address[1]))
    else:
        sys.stdout.write("http://%s:%d/#/settings?edit=%s\n" % (HOST, server.server_address[1], token))
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

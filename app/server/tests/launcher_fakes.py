"""Source text for the fake uv and the fake server that test_launcher.py runs.

The launcher starts them as real processes, so they are scripts, not objects.
Both use the standard library only. Nothing here binds port 8377.
"""

# The fake server stands in for serve.py. It follows the launch contract in
# docs/rebuild/planning/m0-build.md section 10 and writes its start-up to
# <data>/serve-runs.log and its mint calls to <data>/mints.log.
# FAKE_SERVE_MODE picks a failure: busy (cannot bind the port), silent (exits at once),
# badline (a launch line that isn't JSON).
FAKE_SERVE = r"""
import http.server
import json
import os
import secrets
import signal
import sys
import time

argv = sys.argv[1:]
args = {}
_i = 0
while _i < len(argv):
    if argv[_i] == "--demo":  # the one flag with no value
        args["--demo"] = "1"
        _i += 1
    else:
        args[argv[_i]] = argv[_i + 1]
        _i += 2
data = args["--data"]
mode = os.environ.get("FAKE_SERVE_MODE", "")
with open(os.path.join(data, "serve-runs.log"), "a") as fh:
    fh.write(json.dumps({"pid": os.getpid(), "argv": argv, "cwd": os.getcwd()}) + "\n")
if mode == "busy":
    port_text = args["--port"]
    sys.stderr.write("ERROR bartab.serve: could not bind 127.0.0.1:%s\n" % port_text)
    sys.exit(1)
if mode == "silent":
    sys.stderr.write("boom\n")
    sys.exit(1)

instance = secrets.token_hex(4)
secret = secrets.token_urlsafe(16)
port = int(args["--port"])


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *rest):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html>ok</html>")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        good = (
            self.path == "/api/access/mint"
            and self.headers.get("X-Bartab-Mint") == secret
            and self.headers.get("Host") == "127.0.0.1:%d" % port
            and self.headers.get("Content-Type") == "application/json"
        )
        if not good:
            self.send_response(403)
            self.end_headers()
            return
        if body.decode() == "" or "project" not in json.loads(body):
            self.send_response(422)
            self.end_headers()
            return
        with open(os.path.join(data, "mints.log"), "a") as fh:
            fh.write(body.decode() + "\n")
        out = json.dumps({"code": instance + "." + secrets.token_urlsafe(8)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)


server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)


def on_term(signum, frame):
    try:
        os.unlink(os.path.join(data, "server.json"))
    finally:
        os._exit(0)


signal.signal(signal.SIGTERM, on_term)
record = {
    "port": port,
    "pid": os.getpid(),
    "instance": instance,
    "mint_secret": secret,
    "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "owners": [],
}
path = os.path.join(data, "server.json")
fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as fh:
    fh.write(json.dumps(record))
os.replace(path + ".tmp", path)
if mode == "badline":
    line = "not json\n"
else:
    line = json.dumps(
        {
            "port": port,
            "pid": os.getpid(),
            "instance": instance,
            "code": instance + "." + secrets.token_urlsafe(8),
            "project": os.path.basename(args["--project-dir"]),
        }
    ) + "\n"
launch_fd = int(args["--launch-fd"])
os.write(launch_fd, line.encode())
os.close(launch_fd)
server.serve_forever()
"""

# The fake uv answers `sync` and nothing else. It logs each call's argv and UV_*
# variables to $FAKE_UV_LOG, and on success makes <UV_PROJECT_ENVIRONMENT>/bin/python
# a script that runs the test's own Python. FAKE_UV_MODE picks a failure:
# download_fail (the Python download fails), pkg_fail (a package download fails).
FAKE_UV = r"""#!@PYTHON@
import json
import os
import sys

argv = sys.argv[1:]
log = os.environ.get("FAKE_UV_LOG")
if log:
    uv_env = {k: v for k, v in os.environ.items() if k.startswith("UV_")}
    with open(log, "a") as fh:
        fh.write(json.dumps({"argv": argv, "env": uv_env}) + "\n")
mode = os.environ.get("FAKE_UV_MODE", "ok")
if argv[:1] != ["sync"]:
    sys.exit(3)
if mode == "download_fail":
    print("error: Failed to install cpython-3.13.1-macos-aarch64-none")
    print("  Caused by: Failed to download https://example.invalid/cpython.tar.gz")
    sys.exit(2)
if mode == "pkg_fail":
    print("error: Failed to download `fastapi==0.162.0`")
    sys.exit(2)
env_dir = os.environ["UV_PROJECT_ENVIRONMENT"]
os.makedirs(os.path.join(env_dir, "bin"), exist_ok=True)
py = os.path.join(env_dir, "bin", "python")
with open(py, "w") as fh:
    fh.write('#!/bin/sh\nexec "@PYTHON@" "$@"\n')
os.chmod(py, 0o755)
"""

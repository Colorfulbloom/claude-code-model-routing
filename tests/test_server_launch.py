"""Tests for the server's launcher hooks: --launch-fd and a clean stop on SIGTERM.

The routing-dashboard plugin's launcher points the server's stdout at a log file
and reads the URL from a pipe, so an edit key never reaches the log. These tests
start dashboard/server.py with --fixture in a temp folder and a throwaway HOME.
"""
import os
import select
import signal
import socket
import subprocess
import sys
import time
import unittest

import helpers
import test_server as ts

URL_WAIT = 25


def read_line(fd, timeout=URL_WAIT):
    """Read from fd until a newline or EOF. Returns the bytes read."""
    out = b""
    deadline = time.time() + timeout
    while b"\n" not in out:
        left = deadline - time.time()
        if left <= 0:
            raise AssertionError("no line on the launch descriptor")
        ready, _, _ = select.select([fd], [], [], left)
        if not ready:
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        out += chunk
    return out


class LaunchFd(unittest.TestCase):
    def setUp(self):
        self.root = ts.make_root("mr-launch-")
        self.addCleanup(helpers.rmtree_force, self.root)
        self.procs = []
        self.addCleanup(self._stop_all)

    def _stop_all(self):
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait(10)

    def launch(self, extra=()):
        r, w = os.pipe()
        self.addCleanup(os.close, r)
        out = open(os.path.join(self.root, "out.log"), "wb")
        err = open(os.path.join(self.root, "err.log"), "wb")
        self.addCleanup(out.close)
        self.addCleanup(err.close)
        argv = [sys.executable, os.path.join(ts.DASHBOARD, "server.py"), "--port", "0",
                "--fixture", ts.fixture_copy(self.root), "--launch-fd", str(w)] + list(extra)
        proc = subprocess.Popen(argv, env=ts.base_env(self.root), stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, pass_fds=(w,))
        os.close(w)
        self.procs.append(proc)
        return proc, r

    def read_file(self, name):
        with open(os.path.join(self.root, name), "rb") as fh:
            return fh.read()

    def test_url_goes_to_the_descriptor_and_nothing_to_stdout(self):
        proc, r = self.launch()
        line = read_line(r).decode("ascii")
        self.assertRegex(line, r"^http://127\.0\.0\.1:\d+/\n$")
        self.assertEqual(os.read(r, 10), b"", "the server closes the descriptor after the line")
        port = int(line.split(":")[2].split("/")[0])
        socket.create_connection(("127.0.0.1", port), timeout=5).close()
        self.assertEqual(self.read_file("out.log"), b"")

    def test_edit_key_goes_only_to_the_descriptor(self):
        proc, r = self.launch(["--allow-edits"])
        line = read_line(r).decode("ascii")
        self.assertRegex(line, r"^http://127\.0\.0\.1:\d+/#/settings\?edit=[A-Za-z0-9_-]+\n$")
        key = line.strip().rsplit("=", 1)[1].encode("ascii")
        proc.send_signal(signal.SIGTERM)
        proc.wait(15)
        self.assertNotIn(key, self.read_file("out.log"))
        self.assertNotIn(key, self.read_file("err.log"))
        self.assertEqual(self.read_file("out.log"), b"")

    def test_sigterm_closes_the_socket_and_exits_0(self):
        proc, r = self.launch()
        line = read_line(r).decode("ascii")
        port = int(line.split(":")[2].split("/")[0])
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(15), 0)
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=3).close()
        self.assertNotIn(b"Traceback", self.read_file("err.log"))

    def test_a_taken_port_sends_an_error_line_and_exits_1(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        self.addCleanup(holder.close)
        port = holder.getsockname()[1]
        r, w = os.pipe()
        self.addCleanup(os.close, r)
        proc = subprocess.Popen([sys.executable, "-B", os.path.join(ts.DASHBOARD, "server.py"),
                                 "--port", str(port), "--fixture", ts.fixture_copy(self.root),
                                 "--launch-fd", str(w)],
                                env=ts.base_env(self.root), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(w,))
        os.close(w)
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out, b"")
        self.assertIn(b"may be in use", err)
        self.assertEqual(read_line(r), b"error: port-in-use\n")
        self.assertEqual(os.read(r, 10), b"")

    def test_bad_descriptor_values_exit_2(self):
        for value in ("x", "2", "-1", "70000"):
            proc = subprocess.run([sys.executable, "-B", os.path.join(ts.DASHBOARD, "server.py"),
                                   "--port", "0", "--fixture", ts.fixture_copy(self.root, name="f" + value),
                                   "--launch-fd", value],
                                  env=ts.base_env(self.root), stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=30)
            self.assertEqual(proc.returncode, 2, value)
            self.assertEqual(proc.stdout, b"", value)

    def test_a_closed_descriptor_exits_2(self):
        proc = subprocess.run([sys.executable, "-B", os.path.join(ts.DASHBOARD, "server.py"),
                               "--port", "0", "--fixture", ts.fixture_copy(self.root),
                               "--launch-fd", "250"],
                              env=ts.base_env(self.root), stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b"")


if __name__ == "__main__":
    unittest.main()

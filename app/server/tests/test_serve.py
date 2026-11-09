"""Tests for the serve entry point, in process and as a subprocess."""

import asyncio
import json
import os
import select
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx2
import pytest

import main
import serve

SERVER_DIR = Path(__file__).resolve().parents[1]
PORT = 47123  # the conftest settings fixture's port
AsgiCaller = Any
INDEX = "<!doctype html><html><head></head><body></body></html>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    folder = tmp_path / "dist"
    folder.mkdir()
    (folder / "index.html").write_text(INDEX, encoding="utf-8")
    return folder


def _read_line(fd: int, timeout: float = 15.0) -> dict[str, Any]:
    """Read one JSON line from a pipe fd, failing when none arrives in time."""
    buffer = b""
    deadline = time.monotonic() + timeout
    while b"\n" not in buffer:
        left = deadline - time.monotonic()
        assert left > 0, "no launch line"
        ready, _, _ = select.select([fd], [], [], left)
        assert ready, "no launch line"
        chunk = os.read(fd, 4096)
        assert chunk, "launch fd closed without a line"
        buffer += chunk
    return json.loads(buffer.split(b"\n", 1)[0])


def _swap(port: int, code: str) -> dict[str, Any]:
    response = httpx2.post(
        f"http://127.0.0.1:{port}/api/access/swap", json={"code": code}, timeout=5
    )
    assert response.status_code == 200
    return response.json()


def test_parse_args_defaults_and_options(tmp_path: Path) -> None:
    args = serve.parse_args(["--data", str(tmp_path)])
    assert args.port == 0
    assert args.launch_fd is None
    assert args.fixture == "demo"
    assert args.idle_exit_minutes == 30
    assert args.project_dir is None
    chosen = serve.parse_args(
        [
            "--port",
            "47001",
            "--data",
            str(tmp_path),
            "--launch-fd",
            "3",
            "--project-dir",
            "/work/saltmarsh",
            "--fixture",
            "firstrun",
            "--idle-exit-minutes",
            "0",
            "--dist",
            str(tmp_path / "d"),
        ]
    )
    assert (chosen.port, chosen.launch_fd, chosen.fixture) == (47001, 3, "firstrun")
    assert chosen.idle_exit_minutes == 0
    assert chosen.project_dir == Path("/work/saltmarsh")


def test_parse_args_refuses_an_unknown_fixture(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        serve.parse_args(["--data", str(tmp_path), "--fixture", "nope"])


def test_parse_args_refuses_the_reserved_port(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as err:
        serve.parse_args(["--port", "8377", "--data", str(tmp_path)])
    assert err.value.code == 2
    assert "8377" in capsys.readouterr().err
    assert serve.parse_args(["--port", "8378", "--data", str(tmp_path)]).port == 8378


def _info(pid: int = 4242) -> serve.ServerInfo:
    sample = "s3cr3t-sample"
    return serve.ServerInfo(
        port=47000, pid=pid, instance="abcd1234", mint_secret=sample, started="t"
    )


def test_server_json_is_private_and_complete(tmp_path: Path) -> None:
    path = serve.write_server_json(tmp_path, _info())
    assert path == tmp_path / "server.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == {
        "port": 47000,
        "pid": 4242,
        "instance": "abcd1234",
        "mint_secret": "s3cr3t-sample",
        "started": "t",
        "owners": [],
    }
    assert [p.name for p in tmp_path.iterdir()] == ["server.json"]


def test_server_json_write_replaces_and_leaves_no_temp_file(tmp_path: Path) -> None:
    serve.write_server_json(tmp_path, _info(1))
    serve.write_server_json(tmp_path, _info(2))
    assert json.loads((tmp_path / "server.json").read_text())["pid"] == 2
    assert [p.name for p in tmp_path.iterdir()] == ["server.json"]


def test_failed_write_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_fd: int) -> None:
        raise OSError

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):  # noqa: PT011
        serve.write_server_json(tmp_path, _info())
    assert list(tmp_path.iterdir()) == []


def test_remove_server_json_only_for_the_owner(tmp_path: Path) -> None:
    serve.write_server_json(tmp_path, _info(10))
    serve.remove_server_json(tmp_path, 11)
    assert (tmp_path / "server.json").exists()
    serve.remove_server_json(tmp_path, 10)
    assert not (tmp_path / "server.json").exists()
    serve.remove_server_json(tmp_path, 10)


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_remove_server_json_ignores_odd_files(tmp_path: Path, content: str) -> None:
    (tmp_path / "server.json").write_text(content)
    serve.remove_server_json(tmp_path, 1)
    assert (tmp_path / "server.json").exists()


def test_launch_line_is_one_json_line_and_closes_the_fd() -> None:
    read_fd, write_fd = os.pipe()
    serve.emit_launch_line(write_fd, {"port": 1, "code": "c"})
    assert os.read(read_fd, 100) == b'{"port": 1, "code": "c"}\n'
    assert os.read(read_fd, 100) == b""
    os.close(read_fd)
    with pytest.raises(OSError, match="Bad file descriptor"):
        os.fstat(write_fd)


def test_launch_line_survives_a_closed_fd() -> None:
    read_fd, write_fd = os.pipe()
    os.close(read_fd)
    serve.emit_launch_line(write_fd, {"port": 1})


def test_bind_socket_gives_a_free_loopback_port() -> None:
    sock = serve.bind_socket(0)
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1"
        assert port not in (0, 8377)
    finally:
        sock.close()


def test_bind_failure_exits_with_one(tmp_path: Path, dist: Path) -> None:
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    try:
        port = busy.getsockname()[1]
        args = serve.parse_args(
            ["--port", str(port), "--data", str(tmp_path / "d"), "--dist", str(dist)]
        )
        assert asyncio.run(serve.run(args)) == 1
    finally:
        busy.close()


def test_activity_middleware_records_http_requests_only() -> None:
    now = [10.0]
    seen: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    tracker = serve.ActivityMiddleware(inner, clock=lambda: now[0])
    assert tracker.last == 10.0
    now[0] = 20.0
    asyncio.run(tracker({"type": "lifespan"}, None, None))  # type: ignore[arg-type]
    assert tracker.last == 10.0
    asyncio.run(tracker({"type": "http"}, None, None))  # type: ignore[arg-type]
    assert tracker.last == 20.0
    assert seen == ["lifespan", "http"]


def test_a_request_the_gate_refuses_does_not_reset_the_idle_clock(
    settings: main.Settings, asgi_call: AsgiCaller
) -> None:
    now = [10.0]
    app, tracker = serve.create_tracked_app(settings, clock=lambda: now[0])
    assert tracker.last == 10.0
    good = [("host", f"127.0.0.1:{PORT}")]

    async def scenario() -> None:
        now[0] = 20.0
        refused = await asgi_call(app, path="/", headers=[("host", "evil.example")])
        assert refused.status == 400
        assert tracker.last == 10.0
        now[0] = 30.0
        refused = await asgi_call(app, path="/api/projects", headers=good)
        assert refused.status == 401
        assert tracker.last == 10.0
        now[0] = 40.0
        accepted = await asgi_call(app, path="/", headers=good)
        assert accepted.status == 200
        assert tracker.last == 40.0

    asyncio.run(scenario())


def test_watch_idle_stops_the_server_after_the_limit() -> None:
    now = [0.0]

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        return None

    tracker = serve.ActivityMiddleware(inner, clock=lambda: now[0])

    class FakeServer:
        should_exit = False

    server = FakeServer()

    async def scenario() -> None:
        task = asyncio.create_task(
            serve.watch_idle(server, tracker, 60, poll_seconds=0.01)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)
        assert not server.should_exit
        now[0] = 30.0
        await tracker({"type": "http"}, None, None)  # type: ignore[arg-type]
        now[0] = 89.0
        await asyncio.sleep(0.05)
        assert not server.should_exit
        now[0] = 90.0
        await asyncio.wait_for(task, 2)

    asyncio.run(scenario())
    assert server.should_exit


def test_run_in_process_serves_then_exits_when_idle(tmp_path: Path, dist: Path) -> None:
    data = tmp_path / "data"
    read_fd, write_fd = os.pipe()
    result: list[int] = []
    thread = threading.Thread(
        target=lambda: result.append(
            serve.main(
                [
                    "--port",
                    "0",
                    "--data",
                    str(data),
                    "--launch-fd",
                    str(write_fd),
                    "--dist",
                    str(dist),
                    "--project-dir",
                    "/work/Saltmarsh",
                    "--idle-exit-minutes",
                    "0.03",
                ]
            )
        )
    )
    thread.start()
    try:
        line = _read_line(read_fd)
        assert set(line) == {"port", "pid", "instance", "code", "project"}
        assert line["pid"] == os.getpid()
        assert line["project"] == "saltmarsh"
        assert line["port"] not in (0, 8377)
        info = json.loads((data / "server.json").read_text())
        assert info["port"] == line["port"]
        assert info["instance"] == line["instance"]
        keys = _swap(line["port"], line["code"])
        response = httpx2.get(
            f"http://127.0.0.1:{line['port']}/api/projects",
            headers={"X-Bartab-Key": keys["read_key"]},
            timeout=5,
        )
        assert response.status_code == 200
    finally:
        thread.join(timeout=20)
        os.close(read_fd)
    assert not thread.is_alive()
    assert result == [0]
    assert not (data / "server.json").exists()


def test_subprocess_serves_and_stops_cleanly_on_sigterm(
    tmp_path: Path, dist: Path
) -> None:
    data = tmp_path / "data"
    read_fd, write_fd = os.pipe()
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            str(SERVER_DIR / "serve.py"),
            "--port",
            "0",
            "--data",
            str(data),
            "--launch-fd",
            str(write_fd),
            "--dist",
            str(dist),
            "--idle-exit-minutes",
            "0",
        ],
        pass_fds=(write_fd,),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=SERVER_DIR,
    )
    os.close(write_fd)
    try:
        line = _read_line(read_fd)
        port = line["port"]
        assert port != 8377
        assert line["pid"] == process.pid
        assert line["project"] is None
        assert stat.S_IMODE((data / "server.json").stat().st_mode) == 0o600
        keys = _swap(port, line["code"])
        headers = {"X-Bartab-Key": keys["read_key"]}
        answer = httpx2.get(
            f"http://127.0.0.1:{port}/api/app", headers=headers, timeout=5
        )
        assert answer.status_code == 200
        assert answer.json()["instance"] == line["instance"]
        page = httpx2.get(f"http://127.0.0.1:{port}/", timeout=5)
        assert "content-security-policy" in page.headers
        spoofed = httpx2.get(
            f"http://127.0.0.1:{port}/api/app",
            headers={**headers, "X-Forwarded-For": "9.9.9.9", "Host": "evil.example"},
            timeout=5,
        )
        assert 400 <= spoofed.status_code < 500
        process.send_signal(signal.SIGTERM)
        _, stderr = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        os.close(read_fd)
    assert process.returncode == 0
    assert "shutdown complete" in stderr.decode()
    assert not (data / "server.json").exists()

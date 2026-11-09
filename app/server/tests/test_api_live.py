"""Tests for the Live routes, over each ``live_flow`` scenario in flow mode.

One server runs per scenario, on a store ingested from the built folder and a fixed
data clock at the scenario's time. The fixture provider's answers and the read key use
the plain app fixtures.
"""

import json
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import test_flow_mode as flow_mode
from conftest import INDEX_HTML, _open  # pyright: ignore[reportPrivateUsage]
from timeline_helpers import OTHER_FOLDER, S1, S2, World

import main
import serve
import store_provider
from data_clock import DataClock
from provider import UnknownProjectError, UnknownSessionError

SCENARIOS = ("busy", "many", "unlinked", "empty")
PROJECT = "tidewater-reporting"
OTHER_PROJECT = "driftwood"
JSON_HEADERS = {"Accept-Encoding": "identity"}


@dataclass
class Served:
    """A running flow server and what its build says about it."""

    client: Any
    flow: flow_mode.Flow
    built: Path
    clock: DataClock
    now: datetime
    runs: int
    cwd: str

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.client.get(
            path, headers={**self.flow.headers, **JSON_HEADERS}, **kwargs
        )

    def timeline(self, session: str | None = None, project: str = PROJECT) -> Any:
        return self.get(
            f"/api/sessions/{session or self.flow.session}/timeline?project={project}"
        )

    def listing(self, project: str = PROJECT) -> Any:
        return self.get(f"/api/live/sessions?project={project}")


def _cwd_of(built: Path, session: str) -> str:
    for path in (built / "config" / "projects").rglob(f"{session}.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            cwd = json.loads(line).get("cwd")
            if isinstance(cwd, str):
                return cwd
    pytest.fail("no cwd in the flow session's transcript")


@pytest.fixture(scope="module", params=SCENARIOS)
def served(
    request: pytest.FixtureRequest,
    flow_build: Callable[[str], Path],
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Served]:
    scenario: str = request.param
    built = flow_build(scenario)
    base = tmp_path_factory.mktemp(f"live-{scenario}")
    dist = base / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    now = serve.scenario_now(built)
    clock = DataClock.test(now)
    flow = flow_mode.make_flow(base, dist, built, clock)
    runs = len(json.loads((built / "flow.json").read_text(encoding="utf-8"))["runs"])
    with _open(main.create_app(flow.settings)) as client:
        flow_mode.wait_done(client, flow)
        flow_mode.wait_running(client, flow)
        yield Served(
            client, flow, built, clock, now, runs, _cwd_of(built, flow.session)
        )


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in cast("dict[object, object]", value).items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            yield from _strings(item)


def assert_no_paths(served: Served, reply: Any) -> None:
    text = reply.text
    assert str(served.built) not in text
    assert served.cwd not in text
    assert "cwd" not in text
    for value in _strings(reply.json()):
        assert not value.startswith(("/", "\\")), value


# ------------------------------------------------------------------ timeline


def test_the_timeline_answers_for_the_flow_session(served: Served) -> None:
    reply = served.timeline()
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["unchanged"] is False
    assert body["project"] == PROJECT
    assert body["session"]["id"] == served.flow.session
    assert body["session"]["project"] == PROJECT
    assert datetime.fromisoformat(body["server_time"]) == served.now
    assert body["totals"]["runs"] == served.runs
    assert len(body["runs"]) == served.runs
    assert body["prices"]["source"] in {"bundled", "last_good", "litellm"}
    assert body["etag"]
    assert "model_check" in body


def test_the_timeline_etag_round_trip_gives_unchanged(served: Served) -> None:
    first = served.timeline().json()
    again = served.get(
        f"/api/sessions/{served.flow.session}/timeline"
        f"?project={PROJECT}&etag={first['etag']}"
    )
    assert again.status_code == 200
    assert again.json() == {
        "project": PROJECT,
        "server_time": first["server_time"],
        "etag": first["etag"],
        "unchanged": True,
    }
    stale = served.get(
        f"/api/sessions/{served.flow.session}/timeline?project={PROJECT}&etag=0000"
    )
    assert stale.json()["unchanged"] is False
    assert stale.json()["etag"] == first["etag"]


def test_the_timeline_etag_changes_when_the_clock_moves_the_data(
    served: Served,
) -> None:
    first = served.timeline().json()
    served.clock.set(served.now + timedelta(hours=2))
    try:
        later = served.timeline().json()
    finally:
        served.clock.set(served.now)
    assert later["session"]["state"] == "ended"
    assert later["etag"] != first["etag"]


def test_the_timeline_lists_the_session_in_its_own_project_only(
    served: Served,
) -> None:
    reply = served.timeline(project=OTHER_PROJECT)
    assert reply.status_code == 404
    assert reply.json() == {"code": "unknown_session", "path": None}


def test_the_timeline_error_codes(served: Served) -> None:
    session = served.flow.session
    cases = [
        (f"/api/sessions/{session}/timeline", 400, "bad_request"),
        (f"/api/sessions/{session}/timeline?project=a&project=b", 400, "bad_request"),
        (
            f"/api/sessions/{session}/timeline?project={PROJECT}&etag=a&etag=b",
            400,
            "bad_request",
        ),
        (f"/api/sessions/{session}/timeline?project=no-such", 404, "unknown_project"),
        (
            f"/api/sessions/no-such-session/timeline?project={PROJECT}",
            404,
            "unknown_session",
        ),
        (f"/api/sessions/{session}/timeline?project=BAD!", 422, "invalid_request"),
        (f"/api/sessions/bad%20id/timeline?project={PROJECT}", 422, "invalid_request"),
    ]
    for path, status, code in cases:
        reply = served.get(path)
        assert reply.status_code == status, path
        assert reply.json()["code"] == code, path
        assert set(reply.json()) == {"code", "path"}, path


def test_no_cwd_or_absolute_path_appears_in_any_answer(served: Served) -> None:
    timeline = served.timeline()
    assert timeline.status_code == 200
    assert_no_paths(served, timeline)
    assert_no_paths(served, served.listing())
    for path in (
        f"/api/sessions/{served.flow.session}/timeline?project=no-such",
        f"/api/sessions/{served.flow.session}/timeline",
    ):
        assert_no_paths(served, served.get(path))


def test_a_timeline_in_flow_mode_reads_the_build_shell_env_and_managed_folder(
    served: Served,
) -> None:
    rows = served.timeline().json()["model_check"]["rows"]
    for row in rows:
        for pair in (row["set"]["model"], row["set"]["effort"]):
            if pair is not None and pair["file"] is not None:
                assert not pair["file"].startswith("/")
                assert str(served.built) not in pair["file"]


# --------------------------------------------------------------- live sessions


def test_the_session_list_has_the_running_flow_session(served: Served) -> None:
    reply = served.listing()
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["unchanged"] is False
    assert datetime.fromisoformat(body["server_time"]) == served.now
    ours = [s for s in body["sessions"] if s["id"] == served.flow.session]
    assert len(ours) == 1
    session = ours[0]
    assert session["project"] == PROJECT
    assert session["project_name"]
    assert session["state"] in {"working", "idle"}
    assert session["requests"] > 0
    last = [datetime.fromisoformat(s["last_request"]) for s in body["sessions"]]
    assert last == sorted(last, reverse=True)
    assert set(body["sessions"][0]) == {
        "id",
        "project",
        "project_name",
        "branch",
        "started",
        "last_request",
        "active",
        "state",
        "runs_working",
        "requests",
    }


def test_the_latest_ended_session_is_the_newest_one_not_running(
    served: Served,
) -> None:
    body = served.listing().json()
    ended = body["latest_ended"]
    assert ended is not None
    assert ended["id"] != served.flow.session
    assert set(ended) == {"id", "branch", "started", "last_request", "requests"}
    running = {s["id"] for s in body["sessions"]}
    assert ended["id"] not in running
    assert datetime.fromisoformat(ended["last_request"]) <= served.now - timedelta(
        minutes=30
    )
    other = served.listing(OTHER_PROJECT).json()
    assert other["latest_ended"] is not None
    assert other["latest_ended"]["id"] != ended["id"]
    # the asked project narrows only latest_ended, never the running list
    assert [s["id"] for s in other["sessions"]] == [s["id"] for s in body["sessions"]]


def test_the_session_list_spans_projects_when_the_clock_moves(served: Served) -> None:
    other = served.listing(OTHER_PROJECT).json()["latest_ended"]
    assert other is not None
    at = datetime.fromisoformat(other["last_request"]) + timedelta(seconds=30)
    served.clock.set(at)
    try:
        body = served.listing(PROJECT).json()
    finally:
        served.clock.set(served.now)
    found = [s for s in body["sessions"] if s["id"] == other["id"]]
    assert len(found) == 1
    assert found[0]["project"] == OTHER_PROJECT
    assert found[0]["state"] in {"working", "idle"}
    assert served.flow.session not in [s["id"] for s in body["sessions"]]


def test_the_session_list_etag_round_trip(served: Served) -> None:
    first = served.listing().json()
    again = served.get(f"/api/live/sessions?project={PROJECT}&etag={first['etag']}")
    assert again.status_code == 200
    assert again.json() == {
        "server_time": first["server_time"],
        "etag": first["etag"],
        "unchanged": True,
    }
    stale = served.get(f"/api/live/sessions?project={PROJECT}&etag=0000")
    assert stale.json()["unchanged"] is False


def test_the_session_list_error_codes(served: Served) -> None:
    cases = [
        ("/api/live/sessions", 400, "bad_request"),
        ("/api/live/sessions?project=a&project=b", 400, "bad_request"),
        (f"/api/live/sessions?project={PROJECT}&etag=a&etag=b", 400, "bad_request"),
        ("/api/live/sessions?project=no-such", 404, "unknown_project"),
        ("/api/live/sessions?project=BAD!", 422, "invalid_request"),
    ]
    for path, status, code in cases:
        reply = served.get(path)
        assert reply.status_code == status, path
        assert reply.json() == {"code": code, "path": reply.json()["path"]}, path


# ------------------------------------------------------------------------ gzip


def test_a_large_answer_is_gzipped_and_a_small_one_is_not(served: Served) -> None:
    path = f"/api/sessions/{served.flow.session}/timeline?project={PROJECT}"
    plain = served.get(path)
    packed = served.client.get(
        path, headers={**served.flow.headers, "Accept-Encoding": "gzip"}
    )
    assert packed.status_code == 200
    assert len(plain.content) > 1024
    assert packed.headers["content-encoding"] == "gzip"
    assert "content-encoding" not in plain.headers
    assert packed.json() == plain.json()
    etag = plain.json()["etag"]
    short = served.client.get(
        f"{path}&etag={etag}",
        headers={**served.flow.headers, "Accept-Encoding": "gzip"},
    )
    assert short.json()["unchanged"] is True
    assert "content-encoding" not in short.headers


def test_gzip_keeps_the_security_headers(served: Served) -> None:
    packed = served.client.get(
        f"/api/live/sessions?project={PROJECT}",
        headers={**served.flow.headers, "Accept-Encoding": "gzip"},
    )
    assert packed.status_code == 200
    assert "content-security-policy" in packed.headers or (
        "x-content-type-options" in packed.headers
    )


# ----------------------------------------------------------- the fixture provider


def test_the_fixture_provider_has_no_sessions(
    client: Any, key_headers: dict[str, str]
) -> None:
    keys = [
        p["key"]
        for p in client.get("/api/projects", headers=key_headers).json()["projects"]
    ]
    assert keys
    timeline = client.get(
        f"/api/sessions/abc/timeline?project={keys[0]}", headers=key_headers
    )
    assert timeline.status_code == 404
    assert timeline.json() == {"code": "unknown_project", "path": None}
    listing = client.get(f"/api/live/sessions?project={keys[0]}", headers=key_headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["sessions"] == []
    assert body["latest_ended"] is None
    assert body["unchanged"] is False
    again = client.get(
        f"/api/live/sessions?project={keys[0]}&etag={body['etag']}",
        headers=key_headers,
    )
    assert again.json()["unchanged"] is True
    assert set(again.json()) == {"server_time", "etag", "unchanged"}
    missing = client.get("/api/live/sessions?project=no-such", headers=key_headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "unknown_project"


# --------------------------------------------------------------------- the key


def test_the_live_routes_need_the_read_key(served: Served) -> None:
    for path in (
        f"/api/sessions/{served.flow.session}/timeline?project={PROJECT}",
        f"/api/live/sessions?project={PROJECT}",
    ):
        assert served.client.get(path).status_code == 401
        wrong = served.client.get(path, headers={"X-Bartab-Key": "wrong"})
        assert wrong.status_code == 401
        assert served.get(path).status_code == 200


# --------------------------------------------------------- a session ingested late


def test_a_miss_refreshes_the_project_mapping_once(tmp_path: Path) -> None:
    """A folder the 5 s mapping cache has not seen is found on the first miss."""
    w = World(tmp_path)
    try:
        w.add(100, "a", 1, 1, sid=S1)
        w.store.run()
        wall = 1_000_000.0

        def make() -> store_provider.StoreProvider:
            return store_provider.create(
                claude_dir=w.config.dir,
                store_dir=w.store.layout.root,
                demo=False,
                pace_ms=0,
                price_fetch=False,
                clock=lambda: wall,
                data_clock=DataClock.fixed(w.moment()),
            )

        provider = make()
        first = provider.projects().projects
        old_key = next(p.key for p in first if p.running)
        answer = provider.timeline(old_key, S1, None)
        assert answer.unchanged is False
        # a second folder arrives while the cached mapping is still fresh
        w.add(50, "b", 1, 1, sid=S2, folder=OTHER_FOLDER)
        w.store.run()
        keys = {p.key for p in make().projects().projects}
        new_key = next(iter(keys - {p.key for p in first}))
        found = provider.timeline(new_key, S2, None)
        assert found.unchanged is False
        assert found.session.id == S2
        assert found.project == new_key
        # a second miss still ends in the right error
        with pytest.raises(UnknownSessionError):
            provider.timeline(new_key, S1, None)
        with pytest.raises(UnknownProjectError):
            provider.timeline("no-such", S1, None)
        with pytest.raises(UnknownProjectError):
            provider.live_sessions("no-such", None)
    finally:
        w.close()

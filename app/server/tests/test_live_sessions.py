"""Tests for the running-session list, over stores built from crafted transcripts.

The old route had no list across projects (allowed difference 7 in the oracle), so
these tests are the whole check. The 30-minute window, the active window and the
run rules are the ones the timeline tests pin.
"""

import hashlib
import json
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import timeline_helpers as t
from timeline_helpers import OTHER, OTHER_FOLDER, PROJECT, S1, S2, S3, World

import live_sessions
from models import LiveSessions

NAMES = {PROJECT: "Demo app", OTHER: "Other app"}
S4 = "44444444-4444-4444-8444-444444444444"


@pytest.fixture
def w(tmp_path: Path) -> Iterator[World]:
    world = World(tmp_path)
    yield world
    world.close()


def listing(w: World, *, project: str = PROJECT, ago: float = 0.0) -> LiveSessions:
    return live_sessions.build_live_sessions(
        w.conn(),
        project_key=project,
        now=w.moment(ago),
        project_names=NAMES,
        folder_keys=w.projects,
    )


def ids(answer: LiveSessions) -> list[str]:
    return [s.id for s in answer.sessions]


def test_the_thirty_minute_window_edges(w: World) -> None:
    w.add(29 * 60 + 59, "in", 1, 1, sid=S1)
    w.add(30 * 60, "edge", 1, 1, sid=S2)
    w.add(30 * 60 + 1, "out", 1, 1, sid=S3)
    assert ids(listing(w)) == [S1]


def test_running_sessions_of_every_project_newest_first(w: World) -> None:
    w.add(500, "a", 1, 1, sid=S1)
    w.add(100, "b", 1, 1, sid=S2, folder=OTHER_FOLDER)
    w.add(900, "c", 1, 1, sid=S3)
    answer = listing(w)
    assert ids(answer) == [S2, S1, S3]
    assert [(s.project, s.project_name) for s in answer.sessions] == [
        (OTHER, "Other app"),
        (PROJECT, "Demo app"),
        (PROJECT, "Demo app"),
    ]
    # the asked project does not narrow the running list
    assert ids(listing(w, project=OTHER)) == [S2, S1, S3]


def test_a_tie_on_the_last_request_goes_to_the_larger_id_first(w: World) -> None:
    for sid, mid in ((S1, "a"), (S3, "c"), (S2, "b")):
        w.add(100, mid, 1, 1, sid=sid)
    assert ids(listing(w)) == [S3, S2, S1]


def test_a_project_with_no_name_shows_its_key(w: World) -> None:
    w.add(100, "a", 1, 1)
    answer = live_sessions.build_live_sessions(
        w.conn(),
        project_key=PROJECT,
        now=w.moment(),
        project_names={},
        folder_keys=w.projects,
    )
    assert answer.sessions[0].project_name == PROJECT


def test_each_session_has_its_start_branch_count_and_state(w: World) -> None:
    w.add(500, "a1", 1, 1, branch="feature/one")
    w.add(300, "a2", 1, 1, branch="feature/two")
    w.add(59, "b1", 1, 1, sid=S2)
    w.add(60, "c1", 1, 1, sid=S3)
    by_id = {s.id: s for s in listing(w).sessions}
    first = by_id[S1]
    assert first.branch == "feature/one"
    assert first.started == w.moment(500)
    assert first.last_request == w.moment(300)
    assert first.requests == 2
    assert (first.active, first.state) == (False, "idle")
    assert (by_id[S2].active, by_id[S2].state) == (True, "working")
    assert (by_id[S3].active, by_id[S3].state) == (False, "idle")


def test_records_after_the_clock_are_ignored(w: World) -> None:
    w.add(10, "now", 1, 1, sid=S1)
    w.add(-10, "future", 1, 1, sid=S1)
    w.add(-5, "only-future", 1, 1, sid=S2)
    answer = listing(w)
    assert ids(answer) == [S1]
    assert answer.sessions[0].requests == 1
    assert answer.sessions[0].last_request == w.moment(10)


def test_runs_working_counts_the_runs_the_timeline_calls_working(w: World) -> None:
    t.build_dispatch(w)
    session = listing(w).sessions[0]
    assert session.runs_working == w.live().totals.runs_working == 2


def test_nothing_running(w: World) -> None:
    w.add(3600, "old", 1, 1)
    answer = listing(w)
    assert answer.sessions == []
    assert answer.latest_ended is not None


def test_a_store_with_no_sessions(w: World) -> None:
    answer = listing(w)
    assert answer.sessions == []
    assert answer.latest_ended is None


def test_the_latest_ended_session_is_the_newest_one_of_the_project(w: World) -> None:
    w.add(7000, "a", 1, 1, sid=S1, branch="old-branch")
    w.add(4000, "b1", 1, 1, sid=S2, branch="newer")
    w.add(3900, "b2", 1, 1, sid=S2, branch="newer")
    w.add(2500, "c", 1, 1, sid=S3, folder=OTHER_FOLDER)  # another project's
    w.add(100, "d", 1, 1, sid=S4)  # running
    answer = listing(w)
    assert ids(answer) == [S4]
    ended = answer.latest_ended
    assert ended is not None
    assert ended.id == S2
    assert ended.branch == "newer"
    assert ended.started == w.moment(4000)
    assert ended.last_request == w.moment(3900)
    assert ended.requests == 2
    other = listing(w, project=OTHER).latest_ended
    assert other is not None
    assert other.id == S3


def test_latest_ended_is_none_when_the_project_has_only_running_sessions(
    w: World,
) -> None:
    w.add(100, "a", 1, 1)
    assert listing(w).latest_ended is None


def test_latest_ended_skips_a_session_that_has_no_request_yet(w: World) -> None:
    w.add(4000, "a", 1, 1, sid=S1)
    w.add(-100, "future", 1, 1, sid=S2)
    ended = listing(w).latest_ended
    assert ended is not None
    assert ended.id == S1


def test_an_earlier_clock_lists_what_ran_then(w: World) -> None:
    w.add(3000, "a", 1, 1, sid=S1)
    w.add(100, "b", 1, 1, sid=S2)
    assert ids(listing(w, ago=2990)) == [S1]
    assert ids(listing(w)) == [S2]


def test_a_session_in_a_folder_the_map_lacks_is_left_out(w: World) -> None:
    w.add(100, "a", 1, 1)
    answer = live_sessions.build_live_sessions(
        w.conn(),
        project_key=PROJECT,
        now=w.moment(),
        project_names=NAMES,
        folder_keys={},
    )
    assert answer.sessions == []
    assert answer.latest_ended is None


def test_the_etag_covers_everything_but_server_time_and_itself(w: World) -> None:
    w.add(100, "a", 1, 1)
    answer = listing(w)
    body = answer.model_dump(mode="json", exclude={"server_time", "etag"})
    want = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    assert answer.etag == want
    assert answer.server_time == w.moment()
    assert answer.unchanged is False
    assert listing(w).etag == answer.etag


def test_the_etag_changes_with_a_new_request_and_with_a_state_change(w: World) -> None:
    w.add(100, "a", 1, 1)
    first = listing(w).etag
    w.add(50, "b", 1, 1)
    second = listing(w)
    assert second.etag != first
    later = listing(w, ago=-100)
    assert later.sessions[0].state == "idle"
    assert second.sessions[0].state == "working"
    assert later.etag != second.etag


def test_as_of_is_the_last_pass_held_back_to_the_clock(w: World) -> None:
    w.add(100, "a", 1, 1)
    assert listing(w).as_of is None
    conn = w.conn()
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('last_pass', '2026-11-01T12:30:00Z')"
    )
    assert listing(w).as_of == datetime.fromisoformat("2026-11-01T12:30:00+00:00")


def test_no_cwd_or_text_is_in_the_answer(w: World) -> None:
    t.build_dispatch(w)
    body = listing(w).model_dump_json()
    for planted in (
        t.PLANTED_TEXT,
        t.PLANTED_TOOL,
        t.PLANTED_CWD,
        "cwd",
        str(w.config.dir),
    ):
        assert planted not in body

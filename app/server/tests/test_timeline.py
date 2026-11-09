"""Behaviour tests for the session timeline, ported from the old live route's tests.

Every world is built by the test in a temp folder: transcript rows are written the way
Claude Code writes them, a real ingest pass reads them into a migrated store, and the
timeline is built at a clock the test picks. The old classes this follows are
``Running``, ``SessionChoice``, ``Dedupe``, ``Numbers`` and ``Dispatch`` in
``tests/test_api_live.py``, plus the new rules (stored labels, parent state, state
history, whole-session buckets).
"""

import hashlib
import json
import sys
from collections.abc import Iterator
from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
import timeline_helpers as t
from timeline_helpers import MYSTERY, OPUS, S1, S2, S3, SONNET, World, cost_of, rid

import timeline
import usage
from models import Timeline, TimelineRun


@pytest.fixture
def w(tmp_path: Path) -> Iterator[World]:
    world = World(tmp_path)
    yield world
    world.close()


def run_of(answer: Timeline, raw: str) -> TimelineRun:
    return next(r for r in answer.runs if r.run_id == rid(raw))


def by_id(answer: Timeline) -> dict[str, TimelineRun]:
    return {r.run_id: r for r in answer.runs}


# --------------------------------------------------------------------- contract


def test_an_unknown_session_is_none(w: World) -> None:
    w.add(10, "a", 1, 1)
    assert w.timeline("44444444-4444-4444-8444-444444444444") is None


def test_a_session_with_only_future_requests_is_none(w: World) -> None:
    w.add(-5, "only-future", 1, 1)
    assert w.timeline(S1) is None


def test_a_session_of_another_project_is_unknown(w: World) -> None:
    w.add(10, "a", 1, 1)
    assert w.timeline(S1, project=t.OTHER) is None
    assert w.timeline(S1) is not None


def test_a_session_in_a_folder_the_map_lacks_is_unknown(w: World) -> None:
    w.add(10, "a", 1, 1)
    w.projects.clear()
    assert w.timeline(S1) is None


def test_the_shape_and_the_clock(w: World) -> None:
    w.add(10, "a", 100, 10)
    answer = w.live()
    assert answer.server_time == w.moment()
    assert answer.unchanged is False
    assert len(answer.etag) == 16
    int(answer.etag, 16)
    assert answer.project == t.PROJECT
    assert answer.session.last_request == w.moment(10)
    assert answer.session.branch == "main"
    assert answer.prices.source == "bundled"


def test_as_of_is_the_last_pass_held_back_to_the_clock(w: World) -> None:
    w.add(10, "a", 1, 1)
    assert w.live().as_of is None
    conn = w.conn()
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('last_pass', '2026-11-01T11:00:00Z')"
    )
    assert w.live().as_of == h.T0 - timedelta(hours=1)
    conn.execute(
        "UPDATE meta SET value = '2026-12-01T00:00:00Z' WHERE key = 'last_pass'"
    )
    assert w.live().as_of == w.moment()


def test_model_check_and_prices_come_from_the_callables(w: World) -> None:
    w.add(10, "a", 1, 1)
    answer = w.timeline(check=t.check_with(5))
    assert answer is not None
    assert answer.model_check.in_effect_count == 5


# ---------------------------------------------------------------------- running


def test_the_thirty_minute_window_edges(w: World) -> None:
    w.add(29 * 60 + 59, "in", 1, 1, sid=S1)
    w.add(30 * 60, "edge", 1, 1, sid=S2)
    w.add(30 * 60 + 1, "out", 1, 1, sid=S3)
    assert w.live(S1).session.running is True
    assert w.live(S1).session.state == "idle"
    for sid in (S2, S3):
        ended = w.live(sid)
        assert ended.session.running is False
        assert ended.session.state == "ended"
        assert ended.session.ended_at == ended.session.last_request
        assert ended.last_minute is None


def test_a_session_runs_while_any_of_its_files_has_a_recent_request(w: World) -> None:
    w.add(3000, "old", 1, 1)
    w.add(100, "sub", 1, 1, run="r1", agent="explorer")
    answer = w.live()
    assert answer.session.running is True
    assert answer.session.requests == 2


def test_records_after_the_clock_are_ignored(w: World) -> None:
    w.add(10, "now", 100, 10)
    w.add(-10, "future", 5000, 5000)
    answer = w.live()
    assert answer.session.requests == 1
    assert answer.totals.tokens == 110
    assert answer.session.last_request == w.moment(10)
    assert len(answer.requests) == 1
    assert answer.buckets[-1].requests == 1


def test_an_earlier_clock_shows_the_session_as_it_was(w: World) -> None:
    w.add(600, "a", 10, 1)
    w.add(300, "b", 20, 2)
    w.add(10, "c", 40, 4)
    earlier = w.live(ago=250)
    assert earlier.session.requests == 2
    assert earlier.totals.input == 30
    assert earlier.server_time == w.moment(250)


def test_active_flips_at_sixty_seconds(w: World) -> None:
    w.add(59, "a", 1, 1, sid=S1)
    w.add(60, "b", 1, 1, sid=S2)
    w.add(61, "c", 1, 1, sid=S3)
    assert (w.live(S1).session.active, w.live(S1).session.state) == (True, "working")
    assert (w.live(S2).session.active, w.live(S2).session.state) == (False, "idle")
    assert (w.live(S3).session.active, w.live(S3).session.state) == (False, "idle")


def test_a_gap_over_thirty_minutes_makes_an_ended_span(w: World) -> None:
    w.add(4000, "a", 1, 1)
    w.add(3990, "b", 1, 1)
    w.add(100, "c", 1, 1)
    states = [(s.at, s.state) for s in w.live().session.states]
    assert states == [
        (w.moment(4000), "working"),
        (w.moment(3930), "idle"),
        (w.moment(3990 - 1800), "ended"),
        (w.moment(100), "working"),
        (w.moment(40), "idle"),
    ]


def test_session_states_do_not_repeat(w: World) -> None:
    for i in range(6):
        w.add(60 - i * 10, f"m{i}", 1, 1)
    states = [s.state for s in w.live().session.states]
    assert states == ["working"]


# ----------------------------------------------------------------------- dedupe


def test_the_larger_row_of_one_message_wins(w: World) -> None:
    w.add(30, "m", 100, 50)
    w.add(29, "m", 100, 300)
    w.add(28, "m", 100, 200)  # a smaller output later: the larger row stays
    answer = w.live()
    assert answer.totals.requests == 1
    assert answer.totals.output == 300
    assert answer.totals.tokens == 400
    assert len(answer.requests) == 1


def test_totals_never_step_back_as_a_row_grows(w: World) -> None:
    w.add(30, "other", 10, 10)
    seen: list[int] = []
    for output in (5, 40, 40, 90):
        w.add(20, "grows", 100, output)
        seen.append(w.live().totals.tokens)
    assert seen == sorted(seen)
    assert seen[-1] == 20 + 190


def test_a_row_with_only_a_request_id_dedupes_on_it(w: World) -> None:
    w.add(10, "same", 1, 10, message_id=False)
    w.add(10, "same", 1, 30, message_id=False)
    answer = w.live()
    assert answer.totals.requests == 1
    assert answer.totals.output == 30
    expected = hashlib.sha256(json.dumps([1, "req_same"]).encode()).hexdigest()[:12]
    assert answer.requests[0].id == expected


def test_a_message_copied_into_another_session_counts_once(w: World) -> None:
    w.add(40, "shared", 10, 5, sid=S1)
    w.add(20, "shared", 10, 50, sid=S2)  # the larger copy wins, in the later session
    w.add(30, "own", 1, 1, sid=S1)
    first, second = w.live(S1), w.live(S2)
    assert first.totals.requests == 1
    assert second.totals.requests == 1
    assert second.totals.output == 50


# ---------------------------------------------------------------------- numbers

MAIN = [
    (3000, "m1", 100, 50, 1000, 0, OPUS, "high"),
    (1500, "m2", 10, 20, 0, 200, SONNET, "high"),
    (90, "m3", 40, 10, 500, 0, OPUS, "high"),
    (60, "m4", 5, 5, 0, 0, OPUS, "high"),  # exactly 60 s old: outside the minute
    (59, "m5", 7, 3, 0, 0, OPUS, "high"),
    (0, "m6", 1, 2, 3, 4, MYSTERY, "high"),  # at T, unpriced
]
EXPLORER = [  # agent type explorer: opus/low twice, sonnet/medium once
    (200, "e1", 3, 3, 0, 0, SONNET, "medium"),
    (100, "e2", 4, 4, 0, 0, OPUS, "low"),
    (60, "e3", 5, 5, 0, 0, OPUS, "low"),
]
UNNAMED = [  # no meta file. A tie between two pairs goes to the first seen
    (80, "u1", 2, 2, 0, 0, SONNET, "high"),
    (59, "u2", 2, 2, 0, 0, OPUS, "high"),
]
Row = tuple[float, str, int, int, int, int, str, str]


def build_numbers(w: World) -> list[Row]:
    for ago, mid, i, o, cr, cw, model, effort in MAIN:
        w.add(ago, mid, i, o, cr, cw, model=model, effort=effort)
    for ago, mid, i, o, cr, cw, model, effort in EXPLORER:
        w.add(
            ago,
            mid,
            i,
            o,
            cr,
            cw,
            model=model,
            effort=effort,
            run="r1",
            agent="explorer",
        )
    for ago, mid, i, o, cr, cw, model, effort in UNNAMED:
        w.add(ago, mid, i, o, cr, cw, model=model, effort=effort, run="r2")
    w.add(-10, "future", 9999, 9999)  # after the clock, in the open minute: ignored
    return [*MAIN, *EXPLORER, *UNNAMED]


def tokens_of(row: Row) -> int:
    return row[2] + row[3] + row[4] + row[5]


def new_of(row: Row) -> int:
    return row[2] + row[3] + row[5]


@pytest.fixture
def numbers(w: World) -> tuple[World, list[Row], Timeline]:
    rows = build_numbers(w)
    return w, rows, w.live()


def bucket_index(w: World, answer: Timeline, row: Row) -> int:
    seconds = answer.axis.bucket_seconds
    start = (answer.axis.start - h.T0).total_seconds()
    return int((w.now - row[0] - start) // seconds)


def test_totals(numbers: tuple[World, list[Row], Timeline]) -> None:
    _w, rows, answer = numbers
    totals = answer.totals
    assert totals.requests == len(rows)
    assert totals.input == sum(r[2] for r in rows)
    assert totals.output == sum(r[3] for r in rows)
    assert totals.cache_read == sum(r[4] for r in rows)
    assert totals.cache_write == sum(r[5] for r in rows)
    assert totals.tokens == sum(new_of(r) for r in rows)
    assert totals.unpriced.requests == 1
    assert totals.unpriced.models == [MYSTERY]
    priced = sum(cost_of(r[6], r[2], r[3], r[4], r[5]) or 0 for r in rows)
    assert totals.cost == pytest.approx(priced, abs=1e-9)
    denom = totals.cache_read + totals.cache_write + totals.input
    assert totals.hit_rate == pytest.approx(totals.cache_read / denom)
    assert answer.session.requests == len(rows)
    assert answer.session.unpriced.requests == 1


def test_the_last_minute_excludes_exactly_sixty_seconds(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    _w, rows, answer = numbers
    last = answer.last_minute
    assert last is not None
    inside = [r for r in rows if r[0] < 60]
    assert last.requests == len(inside)
    assert last.tokens == sum(new_of(r) for r in inside)
    assert last.cache_read == sum(r[4] for r in inside)
    assert last.unpriced.requests == 1
    want = sum(cost_of(r[6], r[2], r[3], r[4], r[5]) or 0 for r in inside)
    assert last.cost == pytest.approx(want, abs=1e-9)
    reads = sum(r[4] for r in inside)
    denom = reads + sum(r[5] for r in inside) + sum(r[2] for r in inside)
    assert last.hit_rate == pytest.approx(reads / denom)


def test_hit_rate_is_none_when_nothing_could_hit(w: World) -> None:
    w.add(10, "z", 0, 0)
    answer = w.live()
    assert answer.totals.hit_rate is None
    assert answer.last_minute is not None
    assert answer.last_minute.hit_rate is None


def test_buckets_cover_the_whole_session_in_minutes(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    w, rows, answer = numbers
    assert answer.axis.bucket_seconds == 60
    assert answer.axis.start == w.moment(3000).replace(second=0, microsecond=0)
    assert answer.axis.end == w.moment()
    starts = [b.start for b in answer.buckets]
    assert all(b - a == timedelta(minutes=1) for a, b in pairwise(starts))
    assert starts[-1] <= w.moment() < starts[-1] + timedelta(minutes=1)
    want: dict[int, dict[str, int]] = {}
    for row in rows:
        if new_of(row) > 0:
            slot = want.setdefault(bucket_index(w, answer, row), {})
            slot[row[6]] = slot.get(row[6], 0) + new_of(row)
    for i, bucket in enumerate(answer.buckets):
        assert bucket.by_model == want.get(i, {}), i


def test_cache_read_per_bucket_matches_the_rows(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    w, rows, answer = numbers
    want: dict[int, int] = {}
    for row in rows:
        i = bucket_index(w, answer, row)
        want[i] = want.get(i, 0) + row[4]
    for i, bucket in enumerate(answer.buckets):
        assert bucket.cache_read == want.get(i, 0), i
        old = sum(tokens_of(r) for r in rows if bucket_index(w, answer, r) == i)
        assert sum(bucket.by_model.values()) + bucket.cache_read == old, i


def test_the_open_minute_leaves_out_requests_after_the_clock(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    # the future row sits in the same minute as T, so its minute_usage cell holds it
    w, _rows, answer = numbers
    conn = w.conn()
    cell = conn.execute(
        "SELECT SUM(input) FROM minute_usage WHERE minute = ?",
        (w.moment().strftime("%Y-%m-%dT%H:%M"),),
    ).fetchone()
    assert cell[0] >= 9999
    assert answer.buckets[-1].requests == 1
    assert sum(answer.buckets[-1].by_model.values()) == 7


def test_a_bucket_with_only_cache_reads_has_no_new_tokens(w: World) -> None:
    w.add(10, "reads", 0, 0, 700)
    answer = w.live()
    assert answer.buckets[-1].cache_read == 700
    assert answer.buckets[-1].by_model == {}
    assert answer.models == []
    assert answer.axis.token_ticks == usage.token_ticks(0)[1]


def test_a_model_with_only_cache_reads_is_not_in_the_legend(w: World) -> None:
    w.add(10, "new", 10, 5, model=OPUS)
    w.add(8, "reads", 0, 0, 900, model=SONNET)
    answer = w.live()
    assert answer.buckets[-1].by_model == {OPUS: 15}
    assert [m.model for m in answer.models] == [OPUS]


def test_token_ticks_follow_the_tallest_bucket_without_cache_reads(w: World) -> None:
    w.add(100, "big-reads", 1, 1, 5000000)
    w.add(10, "small", 20, 10)
    assert w.live().axis.token_ticks == usage.token_ticks(30)[1]


def test_the_legend_is_in_catalog_order_then_others(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    _w, rows, answer = numbers
    assert [m.model for m in answer.models] == [OPUS, SONNET, MYSTERY]
    want: dict[str, int] = {}
    for row in rows:
        want[row[6]] = want.get(row[6], 0) + new_of(row)
    assert {m.model: m.tokens for m in answer.models} == want


def test_per_bucket_unpriced_detail(numbers: tuple[World, list[Row], Timeline]) -> None:
    _w, _rows, answer = numbers
    last = answer.buckets[-1]
    assert last.unpriced.requests == 1
    assert last.unpriced.models == [MYSTERY]
    assert last.cost is None  # every request in that bucket is unpriced
    assert answer.buckets[0].cost is not None


def test_runs_carry_their_model_effort_and_numbers(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    _w, _rows, answer = numbers
    main = answer.runs[0]
    explorer, unnamed = run_of(answer, "r1"), run_of(answer, "r2")
    assert (main.agent, main.run_id, main.label_n) == (None, "main", 1)
    assert (main.model, main.effort) == (OPUS, "high")
    assert (explorer.agent, explorer.model, explorer.effort) == (
        "explorer",
        OPUS,
        "low",
    )
    assert (unnamed.agent, unnamed.model, unnamed.effort) == ("unnamed", SONNET, "high")
    assert explorer.tokens == sum(new_of(r) for r in EXPLORER)
    want = sum(cost_of(r[6], r[2], r[3], r[4], r[5]) or 0 for r in EXPLORER)
    assert explorer.cost == pytest.approx(want, abs=1e-9)
    assert explorer.cum[-1].tokens == explorer.tokens
    assert explorer.cum[-1].cache_read == 0
    assert main.cum[-1].cache_read == sum(r[4] for r in MAIN)
    assert main.unpriced.requests == 1


def test_a_tie_between_pairs_goes_to_the_first_seen(w: World) -> None:
    w.add(30, "t1", 1, 1, model=SONNET, effort="low")
    w.add(20, "t2", 1, 1, model=OPUS, effort="high")
    run = w.live().runs[0]
    assert (run.model, run.effort) == (SONNET, "low")


def test_the_latest_eight_come_newest_first_with_stable_ids(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    w, _rows, answer = numbers
    latest = answer.requests
    assert len(latest) == timeline.LATEST
    times = [r.at for r in latest]
    assert times == sorted(times, reverse=True)
    assert latest[0].at == w.moment()
    assert latest[0].model == MYSTERY
    assert latest[0].cost is None
    assert latest[0].tokens == 10  # every kind, cache reads included
    assert latest[0].new_tokens == 7
    assert latest[0].cache_read == 3
    assert latest[0].output == 2
    assert latest[0].run_id == "main"
    assert len({r.id for r in latest}) == timeline.LATEST
    assert (
        latest[0].id
        == hashlib.sha256(json.dumps([0, "msg_m6"]).encode()).hexdigest()[:12]
    )
    assert [r.id for r in w.live().requests] == [r.id for r in latest]
    w.add(0.5, "newer", 1, 1)  # lands between the two newest rows
    newer = w.live().requests
    assert newer[0].id == latest[0].id
    assert newer[1].tokens == 2
    assert [r.id for r in newer[2:]] == [r.id for r in latest[1:-1]]


def test_a_priced_request_has_its_list_price_cost(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    _w, rows, answer = numbers
    row = next(r for r in answer.requests if r.model == OPUS)
    src = next(
        r
        for r in rows
        if r[6] == OPUS and tokens_of(r) == row.tokens and r[3] == row.output
    )
    assert row.cost == pytest.approx(
        cost_of(OPUS, src[2], src[3], src[4], src[5]), abs=1e-9
    )
    assert row.effort == "high"


def test_a_request_without_ids_hashes_its_time_session_and_run(w: World) -> None:
    w.add(10, "x", 1, 1, message_id=False, request_id=False)
    request = w.live().requests[0]
    at = w.moment(10)
    want = hashlib.sha256(
        json.dumps([2, at.isoformat(), S1, None]).encode()
    ).hexdigest()
    assert request.id == want[:12]


def test_cost_is_zero_with_no_requests_in_a_bucket_and_none_when_all_unpriced(
    w: World,
) -> None:
    w.add(3000, "u", 5, 5, model=MYSTERY)
    w.add(10, "p", 5, 5)
    answer = w.live()
    assert answer.buckets[0].cost is None
    assert answer.buckets[1].cost == 0.0
    assert answer.buckets[-1].cost is not None
    assert answer.totals.cost == pytest.approx(cost_of(OPUS, 5, 5, 0, 0) or 0)


def test_cells_and_requests_price_the_same(w: World) -> None:
    # one request now, then the clock moves a minute on so it comes from a cell
    w.add(10, "a", 1234, 567, 8900, 321, model=SONNET)
    open_minute = w.live()
    later = w.live(ago=-120)
    assert later.totals.cost == pytest.approx(open_minute.totals.cost or 0, abs=1e-12)
    assert later.totals.tokens == open_minute.totals.tokens


def test_a_long_session_picks_a_wider_bucket(w: World) -> None:
    w.add(4900, "a", 1, 1)
    w.add(10, "b", 1, 1)
    answer = w.live()
    assert answer.axis.bucket_seconds == 120
    assert len(answer.buckets) <= timeline.MAX_BUCKETS
    assert answer.buckets[1].start - answer.buckets[0].start == timedelta(seconds=120)
    assert answer.buckets[0].requests == 1
    assert answer.buckets[-1].requests == 1
    assert answer.axis.ticks
    assert all(tick >= answer.axis.start for tick in answer.axis.ticks)


@pytest.mark.parametrize(
    ("minutes", "size"),
    [(0, 60), (59, 60), (60, 120), (119, 120), (120, 300), (299, 300), (300, 600)],
)
def test_the_bucket_size_keeps_at_most_sixty_buckets(minutes: int, size: int) -> None:
    assert timeline.choose_bucket_seconds(timedelta(minutes=minutes)) == size


def test_the_bucket_size_stops_at_an_hour() -> None:
    assert timeline.choose_bucket_seconds(timedelta(days=30)) == 3600


def test_an_ended_session_has_its_axis_end_at_the_last_bucket(w: World) -> None:
    w.add(4000, "a", 1, 1)
    w.add(3500, "b", 1, 1)
    answer = w.live()
    assert answer.session.state == "ended"
    assert answer.axis.bucket_seconds == 60
    last_bucket = answer.buckets[-1]
    assert answer.axis.end == last_bucket.start + timedelta(seconds=60)
    assert last_bucket.start <= w.moment(3500) < answer.axis.end
    assert answer.last_minute is None


def test_started_and_branch_come_from_the_session(
    numbers: tuple[World, list[Row], Timeline],
) -> None:
    w, rows, answer = numbers
    assert answer.session.started == w.moment(3000)
    assert answer.session.branch == "main"
    assert answer.session.requests == len(rows)


# ------------------------------------------------------------------------- etag


def test_the_etag_covers_everything_but_the_clock_driven_fields(w: World) -> None:
    w.add(10, "a", 100, 10)
    answer = w.live()
    assert answer.runs[0].state == "working"
    body = answer.model_dump(mode="json", exclude={"server_time", "etag", "as_of"})
    del body["axis"]["end"]
    for run in body["runs"]:
        if run["state"] == "working":
            del run["segments"][-1]["end"]
    want = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    assert answer.etag == want == timeline.etag_of(answer)


def test_the_etag_ignores_a_moving_clock_inside_one_bucket(w: World) -> None:
    w.add(10, "a", 100, 10)
    a, b = w.live(), w.live(ago=-5)
    assert b.axis.end > a.axis.end
    assert b.server_time > a.server_time
    assert a.runs[0].segments[-1].end < b.runs[0].segments[-1].end
    assert a.etag == b.etag


def test_the_etag_is_stable_between_two_calls(w: World) -> None:
    w.add(10, "a", 100, 10)
    assert w.live().etag == w.live().etag


def test_the_etag_changes_when_a_request_arrives(w: World) -> None:
    w.add(10, "a", 100, 10)
    first = w.live().etag
    w.add(5, "b", 1, 1)
    assert w.live().etag != first


def test_the_etag_changes_when_a_run_changes_state_with_the_clock(w: World) -> None:
    w.add(59, "a", 1, 1)
    w.add(59, "k", 1, 1, run="kid", agent="scout")
    w.link(59, "kid")
    a, b = w.live(), w.live(ago=-2)
    assert run_of(a, "kid").state == "working"
    assert run_of(b, "kid").state == "idle"
    assert a.etag != b.etag


# ---------------------------------------------------------------------- privacy


def test_no_cwd_text_or_tool_data_is_in_any_answer(w: World) -> None:
    t.build_dispatch(w)
    body = w.live().model_dump_json()
    for raw in t.RAW_IDS:
        assert raw not in body
    for planted in (
        t.PLANTED_TEXT,
        t.PLANTED_TOOL,
        t.PLANTED_CWD,
        "cwd",
        "origin",
        "toolUseResult",
        "agentId",
        str(w.config.dir),
        "stranger",
    ):
        assert planted not in body

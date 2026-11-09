"""Run rules of the timeline: parents, order, rounds, states, done, labels.

Ported from the old ``Dispatch`` class in ``tests/test_api_live.py`` and extended for
the rules the new answer adds (``parent_at``, ``parent_state``, state history,
segments, stored ``label_n``).
"""

import sys
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import timeline_helpers as t
from timeline_helpers import AGENT_RUNS, MYSTERY, OPUS, SONNET, World, rid

from models import Timeline, TimelineRun


@pytest.fixture
def w(tmp_path: Path) -> Iterator[World]:
    world = World(tmp_path)
    yield world
    world.close()


@pytest.fixture
def dispatch(w: World) -> tuple[World, Timeline]:
    t.build_dispatch(w)
    return w, w.live()


def run_of(answer: Timeline, raw: str) -> TimelineRun:
    return next(r for r in answer.runs if r.run_id == rid(raw))


def kid(answer: Timeline) -> TimelineRun:
    return answer.runs[1]


# ----------------------------------------------------------------------- order


def test_runs_come_in_dispatch_order_main_first(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    assert [r.run_id for r in answer.runs] == ["main"] + [rid(x) for x in AGENT_RUNS]
    assert [r.dispatch_order for r in answer.runs] == list(range(10))


def test_run_ids_are_the_first_twelve_hex_of_a_sha256(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    for run in answer.runs[1:]:
        assert len(run.run_id) == 12
        int(run.run_id, 16)
    assert rid("lead1") == answer.runs[1].run_id


def test_main_is_the_root(dispatch: tuple[World, Timeline]) -> None:
    w, answer = dispatch
    main = answer.runs[0]
    assert (main.agent, main.label_n, main.parent, main.parent_known) == (
        None,
        1,
        None,
        True,
    )
    assert (main.parent_state, main.parent_at, main.together, main.depth) == (
        "known",
        None,
        None,
        0,
    )
    assert main.state == "working"
    assert [(r.n, r.by, r.by_kind) for r in main.rounds] == [(1, None, None)]
    assert main.first_request == w.moment(900)
    assert main.last_request == w.moment(5)


def test_a_session_with_only_agent_requests_has_no_main_run(w: World) -> None:
    w.add(70, "k1", 1, 1, run="kid", agent="scout")
    runs = w.live().runs
    assert [r.dispatch_order for r in runs] == [1]
    assert (runs[0].parent, runs[0].parent_known) == ("main", False)


def test_the_future_request_and_link_make_no_run(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    assert len(answer.runs) == 10
    assert rid("fut1") not in {r.run_id for r in answer.runs}


# --------------------------------------------------------------------- parents


def test_a_linked_run_hangs_under_the_run_that_launched_it(
    dispatch: tuple[World, Timeline],
) -> None:
    w, answer = dispatch
    lead = run_of(answer, "lead1")
    assert (lead.parent, lead.parent_known, lead.parent_state) == (
        "main",
        True,
        "known",
    )
    assert lead.parent_at == w.moment(880)
    for raw, ago in (("wkr_a", 860), ("wkr_b", 859)):
        run = run_of(answer, raw)
        assert (run.parent, run.parent_known) == (lead.run_id, True), raw
        assert run.parent_at == w.moment(ago), raw
        assert run.depth == 2
    assert lead.depth == 1


def test_a_run_nothing_links_is_under_main_with_parent_known_false(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    fg = run_of(answer, "fg1")
    assert (fg.parent, fg.parent_known, fg.parent_at) == ("main", False, None)
    assert fg.rounds[0].by == "main"


def test_the_earliest_link_names_the_parent(w: World) -> None:
    w.add(100, "m", 1, 1)
    w.add(90, "l", 1, 1, run="lead1", agent="lead")
    w.add(70, "k1", 1, 1, run="kid", agent="scout")
    w.link(75, "kid", run="lead1")
    w.link(80, "kid")  # the main session names it first
    run = next(r for r in w.live().runs if r.agent == "scout")
    assert (run.parent, run.parent_known) == ("main", True)
    assert run.parent_at == w.moment(80)


def test_a_link_from_a_run_with_no_request_leaves_the_run_unknown(w: World) -> None:
    w.add(100, "m", 1, 1)
    w.add(70, "k1", 1, 1, run="kid", agent="scout")
    w.link(80, "kid", run="ghost")
    run = kid(w.live())
    assert (run.parent, run.parent_known) == ("main", False)


def test_a_cycle_link_and_a_link_to_itself_are_dropped(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    a, b = run_of(answer, "cyc_a"), run_of(answer, "cyc_b")
    assert (a.parent, a.parent_known) == ("main", False)
    assert (b.parent, b.parent_known) == (a.run_id, True)


def test_a_new_link_row_updates_the_parent(w: World) -> None:
    w.add(100, "m", 1, 1)
    w.add(70, "k1", 1, 1, run="kid", agent="scout")
    assert not kid(w.live()).parent_known
    w.link(60, "kid")
    answer = w.live()
    assert kid(answer).parent_known
    assert kid(answer).parent_at == w.moment(60)


def test_a_link_after_the_clock_is_not_a_parent(w: World) -> None:
    w.add(100, "m", 1, 1)
    w.add(70, "k1", 1, 1, run="kid", agent="scout")
    w.link(-5, "kid")
    assert not kid(w.live()).parent_known
    assert kid(w.live(ago=-10)).parent_known


# ---------------------------------------------------------------- parent state


def test_a_running_unlinked_run_is_waiting(w: World) -> None:
    w.add(100, "m", 1, 1)
    w.add(30, "k1", 1, 1, run="kid", agent="scout")
    assert kid(w.live()).parent_state == "waiting"


def test_an_unlinked_run_finished_under_five_minutes_ago_is_still_waiting(
    w: World,
) -> None:
    w.add(900, "m", 1, 1)
    w.add(299, "k1", 1, 1, run="kid", agent="scout", stop="handback")
    run = kid(w.live())
    assert run.state == "finished"
    assert run.parent_state == "waiting"


def test_an_unlinked_run_finished_over_five_minutes_ago_is_unknown_for_good(
    w: World,
) -> None:
    w.add(900, "m", 1, 1)
    w.add(300, "k1", 1, 1, run="kid", agent="scout", stop="handback")
    assert kid(w.live()).parent_state == "unknown"
    assert kid(w.live(ago=-1000)).parent_state == "unknown"
    assert kid(w.live(ago=10)).parent_state == "waiting"


def test_a_linked_run_is_known(w: World) -> None:
    w.add(900, "m", 1, 1)
    w.link(700, "kid")
    w.add(300, "k1", 1, 1, run="kid", agent="scout", stop="handback")
    assert kid(w.live()).parent_state == "known"


# -------------------------------------------------------------------- together


def test_parallel_launches_within_five_seconds_run_together(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    a, b = run_of(answer, "wkr_a"), run_of(answer, "wkr_b")
    assert a.together is not None
    assert (a.together.key, a.together.n) == (a.run_id, 2)
    assert b.together == a.together
    unnamed, mystery = run_of(answer, "unn1"), run_of(answer, "mys1")
    assert unnamed.together is not None
    assert (unnamed.together.key, unnamed.together.n) == (unnamed.run_id, 2)
    assert mystery.together == unnamed.together


def test_a_single_launch_is_not_together(dispatch: tuple[World, Timeline]) -> None:
    _w, answer = dispatch
    for raw in ("lead1", "res1", "fg1", "cyc_a", "cyc_b"):
        assert run_of(answer, raw).together is None, raw


# ---------------------------------------------------------------------- labels


def test_the_label_is_the_number_among_runs_of_one_agent(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    labels = {raw: run_of(answer, raw).label_n for raw in AGENT_RUNS}
    assert labels == {
        "lead1": 1,
        "wkr_a": 1,
        "wkr_b": 2,
        "res1": 1,
        "unn1": 1,
        "mys1": 1,
        "fg1": 2,
        "cyc_a": 1,
        "cyc_b": 2,
    }


def test_a_label_never_renames_when_a_second_scout_arrives_later(w: World) -> None:
    w.add(900, "m", 1, 1)
    w.add(500, "s1", 1, 1, run="scout-b", agent="scout")
    first = w.live()
    assert run_of(first, "scout-b").label_n == 1
    # a scout that began earlier but whose file lands later takes the next number
    w.add(700, "s0", 1, 1, run="scout-a", agent="scout")
    second = w.live()
    assert run_of(second, "scout-b").label_n == 1
    assert run_of(second, "scout-a").label_n == 2
    w.add(300, "s2", 1, 1, run="scout-c", agent="scout")
    third = w.live()
    assert [run_of(third, x).label_n for x in ("scout-b", "scout-a", "scout-c")] == [
        1,
        2,
        3,
    ]


def test_runs_first_seen_in_one_pass_are_numbered_by_first_request_then_id(
    w: World,
) -> None:
    w.add(900, "m", 1, 1)
    w.add(300, "late", 1, 1, run="aaa", agent="scout")
    w.add(500, "early", 1, 1, run="zzz", agent="scout")
    w.add(500, "tie", 1, 1, run="mmm", agent="scout")
    answer = w.live()
    labels = {raw: run_of(answer, raw).label_n for raw in ("mmm", "zzz", "aaa")}
    assert labels == {"mmm": 1, "zzz": 2, "aaa": 3}


def test_a_type_that_arrives_late_takes_the_next_number(w: World) -> None:
    w.add(900, "m", 1, 1)
    w.add(500, "s1", 1, 1, run="one", agent="scout")
    w.add(400, "s2", 1, 1, run="two")  # no meta file yet
    first = w.live()
    assert (run_of(first, "two").agent, run_of(first, "two").label_n) == ("unnamed", 1)
    w.config.meta("two", "scout")
    second = w.live()
    assert run_of(second, "two").agent == "scout"
    assert run_of(second, "two").label_n == 2
    assert run_of(second, "one").label_n == 1


def test_an_unnamed_run_has_the_unnamed_agent_and_label_one(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    run = run_of(answer, "unn1")
    assert (run.agent, run.label_n) == ("unnamed", 1)
    assert run_of(answer, "lead1").agent == "lead"


# --------------------------------------------------------------------- numbers


def test_an_unpriced_model_has_cost_none_and_still_counts_tokens(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    run = run_of(answer, "mys1")
    assert run.cost is None
    assert run.tokens == 22
    assert run.model == MYSTERY
    assert run.unpriced.requests == 2
    assert run.unpriced.models == [MYSTERY]
    assert run_of(answer, "lead1").cost is not None


def test_model_and_effort_are_the_most_used_pair(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    run = run_of(answer, "wkr_a")
    assert (run.model, run.effort) == (SONNET, "medium")


def test_tokens_and_cost_are_the_run_totals(dispatch: tuple[World, Timeline]) -> None:
    _w, answer = dispatch
    lead = run_of(answer, "lead1")
    assert lead.tokens == 3 * 55
    assert lead.cost == pytest.approx(3 * (t.cost_of(OPUS, 50, 5, 0, 0) or 0), abs=1e-9)


def test_cum_is_cumulative_per_bucket_and_ends_at_the_run_total(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    for run in answer.runs:
        assert len(run.cum) == len(answer.buckets)
        tokens = [c.tokens for c in run.cum]
        assert tokens == sorted(tokens)
        assert run.cum[-1].tokens == run.tokens
    assert run_of(answer, "cyc_a").cum[0].tokens == 0
    assert sum(r.tokens for r in answer.runs) == answer.totals.tokens


# ---------------------------------------------------------------------- rounds


def test_rounds_of_a_run_resumed_by_a_peer(dispatch: tuple[World, Timeline]) -> None:
    w, answer = dispatch
    lead = run_of(answer, "lead1")
    assert [
        (r.n, r.at, r.last_request, r.by, r.by_kind)
        for r in run_of(answer, "wkr_b").rounds
    ] == [
        (1, w.moment(857), w.moment(600), lead.run_id, None),
        (2, w.moment(500), w.moment(300), lead.run_id, "peer"),
    ]


def test_rounds_of_a_run_resumed_by_the_coordinator_mid_round_two(
    dispatch: tuple[World, Timeline],
) -> None:
    w, answer = dispatch
    run = run_of(answer, "res1")
    assert [(r.n, r.at, r.last_request, r.by, r.by_kind) for r in run.rounds] == [
        (1, w.moment(695), w.moment(680), "main", None),
        (2, w.moment(120), w.moment(30), "main", "coordinator"),
    ]
    assert run.last_request == w.moment(30)


def test_a_run_with_one_round_has_one(dispatch: tuple[World, Timeline]) -> None:
    _w, answer = dispatch
    assert [r.n for r in run_of(answer, "wkr_a").rounds] == [1]


def test_segments_are_one_per_round_and_a_working_run_ends_at_the_clock(
    dispatch: tuple[World, Timeline],
) -> None:
    w, answer = dispatch
    res = run_of(answer, "res1")
    assert res.state == "working"
    assert [(s.start, s.end) for s in res.segments] == [
        (w.moment(695), w.moment(680)),
        (w.moment(120), w.moment()),
    ]
    wkr = run_of(answer, "wkr_b")
    assert [(s.start, s.end) for s in wkr.segments] == [
        (w.moment(857), w.moment(600)),
        (w.moment(500), w.moment(300)),
    ]
    assert answer.runs[0].segments[-1].end == w.moment()


def test_a_round_that_started_after_the_last_request_makes_the_run_working(
    w: World,
) -> None:
    one_kid = t.one_kid(w, stop="end_turn")
    one_kid.brief(20, "kid", "coordinator")  # resumed, with no request yet
    run = kid(one_kid.live())
    assert run.rounds[1].at == run.rounds[1].last_request == w.moment(20)
    assert run.last_request == w.moment(80)
    assert run.state == "working"
    assert run.segments[-1].end == w.moment()


def test_a_brief_after_the_clock_is_not_a_round(w: World) -> None:
    t.one_kid(w, stop="end_turn")
    w.brief(-10, "kid", "coordinator")
    run = kid(w.live())
    assert len(run.rounds) == 1
    assert run.state == "finished"


def test_a_peer_that_is_not_a_run_of_the_session_has_by_none(w: World) -> None:
    t.one_kid(w, stop="end_turn")
    w.brief(70, "kid", "peer", sender="stranger")
    w.add(60, "k2", 1, 1, run="kid", agent="scout")
    rnd = kid(w.live()).rounds[1]
    assert (rnd.by, rnd.by_kind) == (None, "peer")


def test_a_human_brief_has_by_none(w: World) -> None:
    t.one_kid(w, stop="end_turn")
    w.brief(70, "kid", "human")
    w.add(60, "k2", 1, 1, run="kid", agent="scout")
    rnd = kid(w.live()).rounds[1]
    assert (rnd.by, rnd.by_kind) == (None, "human")


# ----------------------------------------------------------------------- states


def test_states(dispatch: tuple[World, Timeline]) -> None:
    _w, answer = dispatch
    states = {raw: run_of(answer, raw).state for raw in AGENT_RUNS}
    assert states == {
        "lead1": "finished",
        "wkr_a": "finished",
        "wkr_b": "finished",
        "res1": "working",
        "unn1": "idle",
        "mys1": "idle",
        "fg1": "idle",
        "cyc_a": "idle",
        "cyc_b": "idle",
    }
    assert answer.totals.runs == 10
    assert answer.totals.runs_working == 2  # main and res1
    assert answer.totals.runs_finished == 3


def test_a_lead_is_not_finished_while_a_child_is_not(w: World) -> None:
    t.build_dispatch(w)
    w.brief(50, "wkr_a", "coordinator")  # wkr_a wakes, so lead1 is no longer done
    w.add(40, "a4", 20, 2, run="wkr_a", agent="worker", model=SONNET, effort="medium")
    answer = w.live()
    assert run_of(answer, "wkr_a").state == "working"
    assert run_of(answer, "lead1").state == "idle"
    assert run_of(answer, "wkr_b").state == "finished"


def test_a_nudge_after_a_hand_back_reads_working_then_finished(w: World) -> None:
    t.one_kid(w, stop="handback")
    w.nudge(70, "kid")
    w.add(55, "k2", 1, 1, run="kid", agent="scout")
    assert kid(w.live()).state == "working"
    w.add(50, "k3", 1, 1, run="kid", agent="scout", stop="handback")
    run = kid(w.live())
    assert run.state == "finished"
    assert [r.n for r in run.rounds] == [1]


def test_a_stop_after_the_clock_does_not_count(w: World) -> None:
    t.one_kid(w)
    w.add(-10, "k2", 1, 1, run="kid", agent="scout", stop="handback")
    assert kid(w.live()).state == "idle"


def test_a_run_is_working_for_sixty_seconds_after_its_last_request(w: World) -> None:
    w.add(100, "m", 1, 1)
    w.add(59, "a", 1, 1, run="a", agent="scout")
    w.add(60, "b", 1, 1, run="b", agent="scout")
    answer = w.live()
    assert run_of(answer, "a").state == "working"
    assert run_of(answer, "b").state == "idle"


def test_the_state_history_of_a_run_ends_in_its_state(
    dispatch: tuple[World, Timeline],
) -> None:
    _w, answer = dispatch
    for run in answer.runs:
        assert run.states[0].state == "working", run.run_id
        assert run.states[-1].state == run.state, run.run_id
        moments = [s.at for s in run.states]
        assert moments == sorted(moments)
        words = [s.state for s in run.states]
        assert all(a != b for a, b in pairwise(words))


def test_the_state_history_of_a_worker_that_hands_back_and_is_resumed(
    dispatch: tuple[World, Timeline],
) -> None:
    w, answer = dispatch
    run = run_of(answer, "wkr_b")
    tail = [(s.at, s.state) for s in run.states if s.at >= w.moment(600)]
    assert tail == [
        (w.moment(600), "finished"),  # the hand-back
        (w.moment(500), "working"),  # the peer brief wakes it
        (w.moment(430), "idle"),
        (w.moment(300), "finished"),
    ]


def test_a_run_that_pauses_reads_idle_between_requests(w: World) -> None:
    w.add(900, "m", 1, 1)
    w.add(500, "a", 1, 1, run="a", agent="scout")
    w.add(400, "b", 1, 1, run="a", agent="scout")
    run = run_of(w.live(), "a")
    assert [(s.at, s.state) for s in run.states] == [
        (w.moment(500), "working"),
        (w.moment(440), "idle"),
        (w.moment(400), "working"),
        (w.moment(340), "idle"),
    ]


def test_a_child_counts_for_its_parent_only_from_its_link(w: World) -> None:
    w.add(900, "m", 1, 1)
    w.link(800, "lead")
    w.add(790, "l1", 1, 1, run="lead", agent="lead", stop="end_turn")
    w.add(700, "c1", 1, 1, run="child", agent="scout", stop="handback")
    w.link(300, "child", run="lead")  # a foreground child is linked when it ends
    late = w.live()
    assert run_of(late, "child").parent_known
    # before the link the child hangs under main, so the lead is finished
    assert run_of(w.live(ago=400), "lead").state == "finished"
    # from the link on the child is the lead's, and it is finished too
    assert run_of(late, "lead").state == "finished"
    states = [s.state for s in run_of(late, "lead").states]
    assert states[-1] == "finished"


def test_a_lead_waits_for_a_linked_child_that_is_not_done(w: World) -> None:
    w.add(900, "m", 1, 1)
    w.link(800, "lead")
    w.link(780, "child", run="lead")
    w.add(790, "l1", 1, 1, run="lead", agent="lead", stop="end_turn")
    w.add(100, "c1", 1, 1, run="child", agent="scout")
    answer = w.live()
    assert run_of(answer, "lead").state == "idle"
    earlier = w.live(ago=400)  # the child had no request yet
    assert run_of(earlier, "lead").state == "finished"


def test_the_depth_of_nested_runs(dispatch: tuple[World, Timeline]) -> None:
    _w, answer = dispatch
    depths = {raw: run_of(answer, raw).depth for raw in AGENT_RUNS}
    assert depths["lead1"] == 1
    assert depths["wkr_a"] == depths["wkr_b"] == 2
    assert depths["fg1"] == 1
    assert depths["cyc_b"] == 2  # cyc_a launched it


def test_the_migration_numbers_existing_runs_by_first_request_then_id(
    tmp_path: Path,
) -> None:
    import store
    from store_paths import StoreLayout

    conn = store.open_writer(StoreLayout(tmp_path / "bartab"))
    store.migrate(conn, target=5)
    stamp = "2026-01-01T00:00:00Z"
    for file_id, path in enumerate(("/work/a", "/work/b", "/work/c", "/work/d"), 1):
        conn.execute(
            "INSERT INTO files (id, path, kind, folder, first_seen, last_seen)"
            " VALUES (?, ?, 'agent', 'f', ?, ?)",
            (file_id, path, stamp, stamp),
        )
    for file_id, run, kind, ts in (
        (1, "r-a", "scout", "2026-01-01T00:00:05Z"),
        (2, "r-b", "scout", "2026-01-01T00:00:01Z"),
        (3, "r-c", "scout", "2026-01-01T00:00:05Z"),
        (4, "r-d", None, "2026-01-01T00:00:00Z"),
    ):
        conn.execute(
            "INSERT INTO runs (session_id, run_id, file_id, agent_type)"
            " VALUES ('s', ?, ?, ?)",
            (run, file_id, kind),
        )
        conn.execute(
            "INSERT INTO requests (file_id, key, ts, model) VALUES (?, ?, ?, 'm')",
            (file_id, run, ts),
        )
    assert store.migrate(conn) == store.latest_version()
    labels = dict(conn.execute("SELECT run_id, label_n FROM runs"))
    assert labels == {"r-b": 1, "r-a": 2, "r-c": 3, "r-d": None}
    conn.close()

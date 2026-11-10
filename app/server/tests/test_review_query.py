"""Behaviour tests for review_query on small crafted stores.

Every world is built by the test in a temp folder: transcript rows are written the way
Claude Code writes them, a real ingest pass reads them into a migrated store, and
``review_query.scan`` reads the store. Expected numbers come from the price table or
from counting by hand. The old-app rules these follow are in the module docstring of
``review_query``, and ``test_differential_review.py`` checks them against recordings.
"""

import copy
import sys
from collections.abc import Iterator
from datetime import UTC, date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
import timeline_helpers as t
from timeline_helpers import MYSTERY, OPUS, S1, S2, S3, SONNET, World
from timeline_helpers import cost_of as price_of

import prices
import review_query as rq
import review_windows as rw
import usage_query

S4 = "44444444-4444-4444-8444-444444444444"
S5 = "55555555-5555-4555-8555-555555555555"
S6 = "66666666-6666-4666-8666-666666666666"
NY = "America/New_York"
HOUR = 3600


def cost_of(
    model: str, input_tokens: int, output: int, cache_read: int, cache_write: int
) -> float:
    """USD for one request, from the price table. The model must have a price."""
    found = price_of(model, input_tokens, output, cache_read, cache_write)
    assert found is not None
    return found


@pytest.fixture
def w(tmp_path: Path) -> Iterator[World]:
    world = World(tmp_path, now=2 * HOUR)  # 14:00:00 UTC on November 1, 2026
    yield world
    world.close()


def scan(w: World, *, window: float = HOUR, **kwargs: object) -> rq.Scan:
    """Scan the last ``window`` seconds of a world, in UTC."""
    args: dict[str, object] = {
        "folders": None,
        "start": w.moment(window),
        "end": w.moment(0),
        "tz": "UTC",
    }
    args.update(kwargs)
    return rq.scan(w.conn(), t.PRICES, **args)  # type: ignore[arg-type]


# ---------------------------------------------------------------- totals


def test_totals_sum_the_cells_and_price_them(w: World) -> None:
    w.add(600, "a", 100, 20, 300, 50)
    w.add(540, "b", 10, 5, 0, 0)
    w.add(60, "c", 1, 1, 1, 1, model=SONNET, sid=S2)
    got = scan(w).total
    assert (got.input, got.output, got.cache_read) == (111, 26, 301)
    assert (got.cache_write_5m, got.cache_write_1h, got.thinking) == (51, 0, 0)
    assert (got.requests, got.sessions, got.runs) == (3, 2, 0)
    assert got.tokens == 111 + 26 + 301 + 51
    assert got.hit_rate == pytest.approx(301 / (301 + 51 + 111))
    expected = (
        cost_of(OPUS, 100, 20, 300, 50)
        + cost_of(OPUS, 10, 5, 0, 0)
        + cost_of(SONNET, 1, 1, 1, 1)
    )
    assert got.cost == pytest.approx(expected)
    kinds = got.cost_by_kind
    assert kinds.input + kinds.output + kinds.cache_read + kinds.cache_write == (
        pytest.approx(expected)
    )
    assert got.unpriced == rq.Unpriced(0, ())


def test_hit_rate_is_none_without_input_or_cache(w: World) -> None:
    w.add(60, "a", 0, 7, 0, 0)
    assert scan(w).total.hit_rate is None


def test_an_empty_window_has_zero_sums(w: World) -> None:
    w.add(60, "a", 1, 1, 1, 1)
    got = scan(w, start=w.moment(7 * HOUR), end=w.moment(6 * HOUR))
    assert got.total == rq.Sums()
    assert got.total.cost == 0.0
    assert got.by_agent == {}
    assert got.sessions == ()


def test_an_empty_folder_set_is_empty(w: World) -> None:
    w.add(60, "a", 1, 1, 1, 1)
    got = scan(w, folders=frozenset[str](), bars=[_bar(w, 0, 1)])
    assert got.total == rq.Sums()
    assert got.by_model == {}
    assert got.bars == (rq.BarSums({}, rq.Unpriced()),)


def test_folders_pick_the_sessions_they_hold(w: World) -> None:
    w.add(60, "a", 10, 1, 0, 0)
    w.add(60, "b", 20, 2, 0, 0, sid=S2, folder=t.OTHER_FOLDER)
    assert scan(w).total.requests == 2
    assert scan(w, folders=frozenset({h.FOLDER})).total.input == 10
    assert scan(w, folders=frozenset({t.OTHER_FOLDER})).total.input == 20
    both = frozenset({h.FOLDER, t.OTHER_FOLDER})
    assert scan(w, folders=both).total.input == 30


def test_a_changed_price_changes_the_cost_only(w: World) -> None:
    w.add(60, "a", 1000, 100, 0, 0)
    base = scan(w)
    doubled = copy.deepcopy(t.PRICES)
    for field in prices.PRICE_FIELDS:
        doubled["models"][OPUS][field] *= 2
    after = rq.scan(
        w.conn(),
        doubled,
        folders=None,
        start=w.moment(HOUR),
        end=w.moment(0),
        tz="UTC",
    )
    assert after.total.requests == base.total.requests
    assert base.total.cost is not None
    assert after.total.cost == pytest.approx(2 * base.total.cost)


def test_the_sums_equal_the_totals_of_usage_query(tmp_path: Path) -> None:
    w = World(tmp_path, now=t.NOW)
    try:
        t.build_dispatch(w)
        conn = w.conn()
        start, end = w.moment(3 * HOUR), w.moment(0)
        got = rq.scan(
            conn, t.PRICES, folders=None, start=start, end=end, tz="UTC", days=True
        )
        old = usage_query.totals(
            conn, t.PRICES, folders=None, start=start, end=end, tz="UTC"
        )
    finally:
        w.close()
    assert got.total.cost == pytest.approx(old.total.cost)
    assert got.total.tokens == old.total.tokens
    assert got.total.requests == old.total.requests
    assert got.total.unpriced.requests == old.total.unpriced_requests
    assert set(got.by_agent) == set(old.by_agent)
    assert set(got.by_model) == set(old.by_model)
    for key, agent in got.by_agent.items():
        assert agent.sums.cost == pytest.approx(old.by_agent[key].cost)
        assert agent.sums.tokens == old.by_agent[key].tokens
    for key, model in got.by_model.items():
        assert model.sums.requests == old.by_model[key].requests
    assert {d.isoformat() for d in got.by_day} == set(old.by_day)


# ---------------------------------------------------------------- window edges


def test_a_whole_minute_end_leaves_that_minute_out(w: World) -> None:
    w.add(30, "a", 5, 1, 0, 0)  # 13:59:30
    assert scan(w, end=w.moment(60)).total.requests == 0  # end is 13:59:00
    assert scan(w, end=w.moment(30)).total.requests == 1  # end has seconds
    assert scan(w, end=w.moment(0)).total.requests == 1


def test_a_start_inside_a_minute_keeps_the_whole_minute(w: World) -> None:
    w.add(30, "a", 5, 1, 0, 0)  # 13:59:30
    assert scan(w, start=w.moment(10)).total.requests == 1  # starts 13:59:50
    assert scan(w, start=w.moment(0)).total.requests == 0


# ---------------------------------------------------------------- agents and runs


def _dispatch(w: World) -> None:
    """Main, a lead, workers, a tied pair, an unnamed run and an unpriced scout."""
    w.add(3500, "m1", 10, 1, 0, 0)
    w.add(3400, "m2", 10, 1, 0, 0)
    w.add(3300, "l1", 5, 1, 0, 0, run="lead1", agent="lead")
    w.add(3290, "l2", 5, 1, 0, 0, run="lead1", agent="lead")
    w.add(
        3000, "w1", 2, 1, 0, 0, run="wk1", agent="worker", model=SONNET, effort="medium"
    )
    w.add(
        2990, "w2", 2, 1, 0, 0, run="wk1", agent="worker", model=SONNET, effort="medium"
    )
    w.add(2000, "w3", 2, 1, 0, 0, run="wk2", agent="worker", model=SONNET, effort="low")
    w.add(
        1000, "w4", 2, 1, 0, 0, run="wk3", agent="worker", model=SONNET, effort="medium"
    )
    # tied: both runs have one pair. The sonnet run began first, but opus sorts first.
    w.add(3100, "t1", 3, 1, 0, 0, run="tie1", agent="tied", model=SONNET, effort="high")
    w.add(2100, "t2", 3, 1, 0, 0, run="tie2", agent="tied", model=OPUS, effort="high")
    # one run that tied between two pairs, one request each. The first seen wins.
    w.add(900, "x1", 4, 1, 0, 0, run="xrun", agent="split", model=SONNET, effort="high")
    w.add(800, "x2", 4, 1, 0, 0, run="xrun", agent="split", model=OPUS, effort="high")
    w.add(700, "u1", 1, 1, 0, 0, run="unn1")
    w.add(600, "y1", 1, 1, 0, 0, run="mys1", agent="scout", model=MYSTERY)


def test_agents_count_runs_and_sessions(w: World) -> None:
    _dispatch(w)
    got = scan(w).by_agent
    assert set(got) == {"@main", "lead", "worker", "tied", "split", "@unnamed", "scout"}
    assert got["@main"].sums.runs == 0
    assert got["@main"].sums.sessions == 1
    assert got["lead"].sums.runs == 1
    assert got["worker"].sums.runs == 3
    assert got["worker"].sums.requests == 4
    assert got["tied"].sums.runs == 2
    assert got["@unnamed"].sums.runs == 1
    assert scan(w).total.runs == 1 + 3 + 2 + 1 + 1 + 1


def test_agents_come_biggest_cost_first_then_tokens_then_key(w: World) -> None:
    _dispatch(w)
    got = scan(w)
    costs = [a.sums.cost or 0.0 for a in got.by_agent.values()]
    assert costs == sorted(costs, reverse=True)
    # scout has no price, so it sorts by tokens after every priced agent.
    assert list(got.by_agent)[-1] == "scout"


def test_ran_pairs_count_each_run_under_its_most_used_pair(w: World) -> None:
    _dispatch(w)
    worker = scan(w).by_agent["worker"]
    assert worker.ran_pairs == (
        rq.PairRuns(SONNET, "medium", 2),
        rq.PairRuns(SONNET, "low", 1),
    )
    assert worker.ran == rq.PairRuns(SONNET, "medium", 2)
    assert worker.mixed is True
    lead = scan(w).by_agent["lead"]
    assert lead.ran_pairs == (rq.PairRuns(OPUS, "high", 1),)
    assert lead.mixed is False


def test_ran_pair_ties_go_to_the_first_seen_not_the_first_by_name(w: World) -> None:
    _dispatch(w)
    tied = scan(w).by_agent["tied"]
    assert [p.model for p in tied.ran_pairs] == [SONNET, OPUS]
    assert tied.ran is not None
    assert tied.ran.model == SONNET


def test_a_run_that_ties_between_pairs_takes_the_pair_first_seen(w: World) -> None:
    _dispatch(w)
    split = scan(w).by_agent["split"]
    assert split.ran_pairs == (rq.PairRuns(SONNET, "high", 1),)


def test_main_counts_sessions_as_its_runs(w: World) -> None:
    w.add(600, "a", 1, 1, 0, 0, sid=S1)
    w.add(500, "b", 1, 1, 0, 0, sid=S2, model=SONNET, effort="medium")
    w.add(400, "c", 1, 1, 0, 0, sid=S3)
    main = scan(w).by_agent["@main"]
    assert main.sums.runs == 0
    assert main.sums.sessions == 3
    assert main.ran_pairs == (
        rq.PairRuns(OPUS, "high", 2),
        rq.PairRuns(SONNET, "medium", 1),
    )
    assert main.mixed is True


def test_a_request_with_no_effort_has_an_effort_of_none(w: World) -> None:
    w.add(60, "a", 1, 1, 0, 0, effort=None)
    assert scan(w).by_agent["@main"].ran == rq.PairRuns(OPUS, None, 1)


def test_agent_shares_add_up_to_one(w: World) -> None:
    _dispatch(w)
    got = scan(w)
    shares = [a.share for a in got.by_agent.values()]
    assert shares[-1] is None  # scout, which has no price
    assert sum(s for s in shares if s is not None) == pytest.approx(1.0)
    total = got.total.cost
    assert total is not None
    for agent in got.by_agent.values():
        if agent.sums.cost is not None:
            assert agent.share == pytest.approx(agent.sums.cost / total)


# ---------------------------------------------------------------- unpriced


def test_unpriced_requests_stay_out_of_the_cost_and_say_which_model(
    w: World,
) -> None:
    w.add(600, "a", 100, 10, 0, 0)
    w.add(500, "b", 7, 1, 0, 0, model=MYSTERY)
    w.add(400, "c", 7, 1, 0, 0, model="another-model")
    w.add(300, "d", 7, 1, 0, 0, model=MYSTERY)
    got = scan(w)
    assert got.total.cost == pytest.approx(cost_of(OPUS, 100, 10, 0, 0))
    assert got.total.unpriced == rq.Unpriced(3, ("another-model", MYSTERY))
    assert got.total.requests == 4
    assert got.by_model[MYSTERY].sums.cost is None
    assert got.by_model[MYSTERY].share is None
    assert got.by_model[MYSTERY].sums.unpriced == rq.Unpriced(2, (MYSTERY,))
    assert got.by_model[OPUS].share == pytest.approx(1.0)
    assert got.by_model[OPUS].sums.unpriced == rq.Unpriced()


def test_an_agent_with_nothing_priced_has_no_cost_and_no_share(w: World) -> None:
    w.add(600, "a", 100, 10, 0, 0)
    w.add(500, "b", 7, 1, 0, 0, run="r1", agent="scout", model=MYSTERY)
    scout = scan(w).by_agent["scout"]
    assert scout.sums.cost is None
    assert scout.share is None
    assert scout.sums.requests == 1


def test_a_window_with_nothing_priced_has_no_cost(w: World) -> None:
    w.add(500, "b", 7, 1, 0, 0, model=MYSTERY)
    got = scan(w).total
    assert got.cost is None
    assert got.requests == 1
    assert scan(w).by_model[MYSTERY].share is None


# ---------------------------------------------------------------- models


def test_a_model_lists_its_agents_biggest_cost_first(w: World) -> None:
    w.add(600, "a", 10, 1, 0, 0, model=SONNET)
    w.add(500, "b", 5000, 1, 0, 0, model=SONNET, run="r1", agent="big")
    w.add(400, "c", 100, 1, 0, 0, model=SONNET, run="r2", agent="mid")
    w.add(300, "d", 1, 1, 0, 0, model=OPUS, run="r3", agent="opus-only")
    models = scan(w).by_model
    assert models[SONNET].agents == ("big", "mid", "@main")
    assert models[OPUS].agents == ("opus-only",)
    assert sum(m.share or 0.0 for m in models.values()) == pytest.approx(1.0)
    assert list(models) == sorted(models, key=lambda m: -(models[m].sums.cost or 0.0))


# ---------------------------------------------------------------- days and bars


def _bar(w: World, start_ago: float, end_ago: float) -> rw.Bar:
    return rw.Bar(w.moment(start_ago), w.moment(end_ago), False, False, False)


def test_days_split_at_the_local_midnight(tmp_path: Path) -> None:
    w = World(tmp_path, now=3 * 24 * HOUR)  # November 4, 12:00 UTC
    try:
        # 03:30 UTC on November 2 is 22:30 on November 1 in New York (EST).
        w.add(w.now - (15.5 * HOUR), "a", 10, 1, 0, 0)
        # 05:30 UTC is 00:30 on November 2.
        w.add(w.now - (17.5 * HOUR), "b", 20, 1, 0, 0)
        got = rq.scan(
            w.conn(),
            t.PRICES,
            folders=None,
            start=w.moment(3 * 24 * HOUR),
            end=w.moment(0),
            tz=NY,
            days=True,
        )
    finally:
        w.close()
    assert list(got.by_day) == [date(2026, 11, 1), date(2026, 11, 2)]
    assert got.by_day[date(2026, 11, 1)].input == 10
    assert got.by_day[date(2026, 11, 2)].input == 20


def test_days_are_empty_unless_asked_for(w: World) -> None:
    w.add(60, "a", 1, 1, 0, 0)
    assert scan(w).by_day == {}


def test_bars_hold_the_models_of_their_slot(w: World) -> None:
    w.add(3000, "a", 100, 10, 50, 5)  # 13:10
    w.add(2900, "b", 100, 10, 0, 0, model=SONNET)  # 13:11
    w.add(1500, "c", 7, 1, 0, 0, model=MYSTERY)  # 13:35
    w.add(30, "d", 1, 1, 0, 0)  # 13:59
    bars = [
        _bar(w, 4 * HOUR, 3 * HOUR),  # 10:00 to 11:00
        _bar(w, HOUR, 0.5 * HOUR),  # 13:00 to 13:30
        _bar(w, 0.5 * HOUR, 0),  # 13:30 to 14:00
    ]
    first, second, third = scan(w, window=4 * HOUR, bars=bars).bars
    assert first.models == {}
    assert first.unpriced == rq.Unpriced()
    assert set(second.models) == {OPUS, SONNET}
    opus = second.models[OPUS]
    assert opus.cost == pytest.approx(cost_of(OPUS, 100, 10, 50, 5))
    assert (opus.tokens, opus.requests) == (165, 1)
    assert opus.kinds.input > 0
    assert opus.kinds.cache_write > 0
    assert opus.unpriced == rq.Unpriced()
    assert second.unpriced == rq.Unpriced()
    assert list(third.models) == [OPUS, MYSTERY]  # catalog order, then the rest
    mystery = third.models[MYSTERY]
    assert mystery.cost is None
    assert mystery.requests == 1
    assert mystery.unpriced == rq.Unpriced(1, (MYSTERY,))
    assert third.unpriced == rq.Unpriced(1, (MYSTERY,))


def test_bar_costs_add_up_to_the_total(w: World) -> None:
    _dispatch(w)
    start = w.moment(HOUR)
    bars = [
        rw.Bar(
            start + timedelta(minutes=20 * i),
            start + timedelta(minutes=20 * (i + 1)),
            False,
            False,
            False,
        )
        for i in range(3)
    ]
    got = scan(w, bars=bars)
    total = sum(m.cost or 0.0 for bar in got.bars for m in bar.models.values())
    assert got.total.cost is not None
    assert total == pytest.approx(got.total.cost)
    assert sum(m.requests for b in got.bars for m in b.models.values()) == (
        got.total.requests
    )


# ---------------------------------------------------------------- sessions


def _sessions_world(w: World) -> None:
    """Three sessions over one day. The first began before the window."""
    w.add(26 * HOUR, "a0", 100, 10, 0, 0, sid=S1, branch="old-branch")
    w.add(1.5 * HOUR, "a1", 10, 1, 0, 0, sid=S1)
    w.add(1.4 * HOUR, "a2", 10, 1, 0, 0, sid=S1, run="r1", agent="lead")
    w.add(1.0 * HOUR, "b1", 20, 2, 0, 0, sid=S2, model=SONNET, branch="feature/x")
    w.add(600, "b2", 20, 2, 0, 0, sid=S2)
    w.add(30, "c1", 5, 1, 0, 0, sid=S3)


def test_sessions_come_newest_first(tmp_path: Path) -> None:
    w = World(tmp_path, now=30 * HOUR)
    try:
        _sessions_world(w)
        got = scan(w, window=3 * HOUR, sessions=True).sessions
    finally:
        w.close()
    assert [s.id for s in got] == [S3, S2, S1]
    assert [s.sort_key for s in got] == sorted((s.sort_key for s in got), reverse=True)


def test_a_session_counts_the_window_and_carries_its_whole_numbers(
    tmp_path: Path,
) -> None:
    w = World(tmp_path, now=30 * HOUR)
    try:
        _sessions_world(w)
        got = {s.id: s for s in scan(w, window=3 * HOUR, sessions=True).sessions}
    finally:
        w.close()
    first = got[S1]
    assert first.started_before_range is True
    assert first.tokens == 11 + 11  # the window only
    assert first.runs == 1
    assert first.whole is not None
    assert first.whole.tokens == 110 + 11 + 11
    assert first.whole.cost == pytest.approx(
        cost_of(OPUS, 100, 10, 0, 0) + cost_of(OPUS, 10, 1, 0, 0) * 2
    )
    assert first.whole.unpriced == rq.Unpriced()
    assert first.started < first.first_in_window
    assert first.branch == "old-branch"
    assert got[S2].started_before_range is False
    assert got[S2].whole is None
    assert got[S2].branch == "feature/x"
    assert got[S2].started.replace(second=0, microsecond=0) == got[S2].first_in_window


def test_a_session_row_lists_its_agents_by_cost(tmp_path: Path) -> None:
    w = World(tmp_path, now=30 * HOUR)
    try:
        w.add(600, "a", 10, 1, 0, 0)
        w.add(500, "b", 900, 1, 0, 0, run="r1", agent="big")
        w.add(400, "c", 90, 1, 0, 0, run="r2", agent="mid")
        row = scan(w, window=HOUR, sessions=True).sessions[0]
    finally:
        w.close()
    assert row.agents == ("big", "mid", "@main")
    assert row.runs == 2


def test_a_session_row_carries_its_unpriced_requests(w: World) -> None:
    w.add(500, "b", 7, 1, 0, 0, model=MYSTERY)
    w.add(400, "c", 1, 1, 0, 0)
    row = scan(w, sessions=True).sessions[0]
    assert row.unpriced == rq.Unpriced(1, (MYSTERY,))
    assert row.cost == pytest.approx(cost_of(OPUS, 1, 1, 0, 0))
    only = scan(w, sessions=True, start=w.moment(450)).sessions[0]
    assert only.cost == pytest.approx(cost_of(OPUS, 1, 1, 0, 0))
    none = scan(w, sessions=True, end=w.moment(450)).sessions[0]
    assert none.cost is None


def test_session_state_follows_the_last_request(w: World) -> None:
    w.add(10, "a", 1, 1, 0, 0, sid=S1)  # working: inside 60 seconds
    w.add(600, "b", 1, 1, 0, 0, sid=S2)  # idle: inside 30 minutes
    w.add(3000, "c", 1, 1, 0, 0, sid=S3)  # ended
    got = {s.id: s.state for s in scan(w, sessions=True).sessions}
    assert got == {S1: "working", S2: "idle", S3: "ended"}


def test_session_state_reads_the_whole_sessions_last_request(w: World) -> None:
    w.add(3000, "a", 1, 1, 0, 0, sid=S1)
    w.add(10, "b", 1, 1, 0, 0, sid=S1)
    row = scan(w, sessions=True, end=w.moment(1000)).sessions[0]
    assert row.state == "working"  # at the answer's clock, not the window's end
    assert row.last_request == w.moment(10).replace(microsecond=0)


def test_sessions_group_by_the_local_day_of_the_first_request_in_the_window(
    tmp_path: Path,
) -> None:
    w = World(tmp_path, now=3 * 24 * HOUR)
    try:
        w.add(w.now - (15.5 * HOUR), "a", 10, 1, 0, 0, sid=S1)  # Nov 1, 22:30 EST
        w.add(w.now - (17.5 * HOUR), "b", 10, 1, 0, 0, sid=S2)  # Nov 2, 00:30 EST
        w.add(w.now - (19.5 * HOUR), "c", 10, 1, 0, 0, sid=S3)  # Nov 2, 02:30 EST
        rows = scan(w, window=3 * 24 * HOUR, sessions=True, tz=NY).sessions
    finally:
        w.close()
    days = rq.sessions_by_day(rows, NY)
    assert [(d, [r.id for r in group]) for d, group in days] == [
        (date(2026, 11, 2), [S3, S2]),
        (date(2026, 11, 1), [S1]),
    ]


def test_a_straddling_session_sits_under_its_first_day_in_the_window(
    tmp_path: Path,
) -> None:
    w = World(tmp_path, now=3 * 24 * HOUR)
    try:
        w.add(w.now - 1 * HOUR, "a", 10, 1, 0, 0, sid=S1)  # Nov 1, 13:00 UTC
        w.add(w.now - 40 * HOUR, "z", 10, 1, 0, 0, sid=S1)  # before the window
        rows = scan(w, window=2 * 24 * HOUR, sessions=True, tz="UTC").sessions
    finally:
        w.close()
    (row,) = rows
    assert row.started_before_range is True
    assert rq.sessions_by_day(rows, "UTC")[0][0] == row.first_in_window.date()


# ---------------------------------------------------------------- paging


def _five(w: World) -> None:
    for i, sid in enumerate((S1, S2, S3, S4, S5)):
        w.add(3000 - 400 * i, f"p{i}", 1, 1, 0, 0, sid=sid)


def test_the_cursor_pages_a_session_list(w: World) -> None:
    _five(w)
    rows = scan(w, sessions=True).sessions
    assert [r.id for r in rows] == [S5, S4, S3, S2, S1]
    first, cursor = rq.page_sessions(rows, None, 2)
    assert [r.id for r in first] == [S5, S4]
    assert cursor is not None
    second, cursor = rq.page_sessions(rows, cursor, 2)
    assert [r.id for r in second] == [S3, S2]
    assert cursor is not None
    last, cursor = rq.page_sessions(rows, cursor, 2)
    assert [r.id for r in last] == [S1]
    assert cursor is None


def test_a_page_that_fills_the_list_exactly_has_no_next(w: World) -> None:
    _five(w)
    rows = scan(w, sessions=True).sessions
    page, cursor = rq.page_sessions(rows, None, 5)
    assert len(page) == 5
    assert cursor is None
    assert rq.page_sessions(rows, None)[0] == page  # the default size is 50
    assert rq.SESSION_PAGE == 50


def test_a_new_session_at_the_top_moves_no_loaded_row(w: World) -> None:
    _five(w)
    rows = scan(w, sessions=True).sessions
    _first, cursor = rq.page_sessions(rows, None, 2)
    assert cursor is not None
    w.add(10, "new", 1, 1, 0, 0, sid=S6)
    again = scan(w, sessions=True).sessions
    assert again[0].id == S6
    second, _ = rq.page_sessions(again, cursor, 2)
    assert [r.id for r in second] == [S3, S2]
    assert S6 not in {r.id for r in second}


def test_a_session_whose_numbers_change_stays_in_its_place(w: World) -> None:
    _five(w)
    rows = scan(w, sessions=True).sessions
    _, cursor = rq.page_sessions(rows, None, 2)
    assert cursor is not None
    w.add(5, "more", 9, 9, 0, 0, sid=S3)  # S3 gets busier but its first minute stays
    again = scan(w, sessions=True).sessions
    second, _ = rq.page_sessions(again, cursor, 2)
    assert [r.id for r in second] == [S3, S2]


def test_the_cursor_is_opaque_text_that_round_trips() -> None:
    key = ("2026-11-01T13:10", S1)
    cursor = rq.encode_cursor(key)
    assert cursor.replace("-", "").replace("_", "").isalnum()
    assert rq.decode_cursor(cursor) == key


@pytest.mark.parametrize(
    "bad",
    [
        "not a cursor",
        "",
        "e30",  # {}
        "WzFd",  # [1]
        "WzEsIDJd",  # [1, 2]
        "WyJhIl0",  # ["a"]
        "WyJhIiwgImIiLCAiYyJd",  # three parts
        "/w",  # not base64 text for JSON
    ],
)
def test_a_cursor_that_was_not_made_here_is_refused(bad: str, w: World) -> None:
    with pytest.raises(ValueError, match="bad cursor"):
        rq.decode_cursor(bad)
    with pytest.raises(ValueError, match="bad cursor"):
        rq.page_sessions([], bad)


def test_top_sessions_are_the_most_expensive(w: World) -> None:
    for i, sid in enumerate((S1, S2, S3, S4, S5)):
        w.add(3000 - 400 * i, f"p{i}", 100 * (i + 1), 1, 0, 0, sid=sid)
    w.add(100, "mystery", 9, 9, 0, 0, sid=S6, model=MYSTERY)
    rows = scan(w, sessions=True).sessions
    top = rq.top_sessions(rows)
    assert [r.id for r in top] == [S5, S4, S3, S2]
    assert [r.id for r in rq.top_sessions(rows, 6)][-1] == S6  # no cost sorts last


# ---------------------------------------------------------------- oldest, no usage


def test_the_oldest_request_is_the_first_one_ever_seen(w: World) -> None:
    assert rq.oldest_request(w.conn(), None) is None
    w.add(9000, "a", 1, 1, 0, 0, sid=S1)
    w.add(5000, "b", 1, 1, 0, 0, sid=S2, folder=t.OTHER_FOLDER)
    conn = w.conn()
    assert rq.oldest_request(conn, None) == w.moment(9000)
    assert rq.oldest_request(conn, frozenset({t.OTHER_FOLDER})) == w.moment(5000)
    assert rq.oldest_request(conn, frozenset({h.FOLDER, t.OTHER_FOLDER})) == (
        w.moment(9000)
    )
    assert rq.oldest_request(conn, frozenset()) is None
    assert rq.oldest_request(conn, frozenset({"-work-nothing"})) is None


def test_no_usage_sessions_spans_the_window_with_no_cell_in_it(w: World) -> None:
    w.add(6000, "a", 1, 1, 0, 0, sid=S1)  # a session with a gap
    w.add(100, "b", 1, 1, 0, 0, sid=S1)
    w.add(1000, "c", 1, 1, 0, 0, sid=S2)  # active inside the gap
    conn = w.conn()
    gap = (w.moment(3000), w.moment(2000))
    assert rq.no_usage_sessions(conn, None, *gap) == 1
    assert rq.no_usage_sessions(conn, frozenset({h.FOLDER}), *gap) == 1
    assert rq.no_usage_sessions(conn, frozenset({t.OTHER_FOLDER}), *gap) == 0
    assert rq.no_usage_sessions(conn, frozenset(), *gap) == 0
    busy = (w.moment(1200), w.moment(900))
    assert rq.no_usage_sessions(conn, None, *busy) == 1  # S1 has a gap, S2 does not
    assert rq.no_usage_sessions(conn, None, w.moment(7200), w.moment(0)) == 0


def test_the_window_end_is_a_datetime_in_utc(w: World) -> None:
    w.add(60, "a", 1, 1, 0, 0)
    row = scan(w, sessions=True).sessions[0]
    assert row.started.tzinfo == UTC
    assert row.last_request.tzinfo == UTC
    assert row.first_in_window.tzinfo == UTC

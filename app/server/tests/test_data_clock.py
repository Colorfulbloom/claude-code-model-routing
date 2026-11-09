"""Tests for the data clock kinds, apart from the wall clock."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

import data_clock
from data_clock import DataClock

START = datetime(2026, 10, 30, 22, 10, tzinfo=UTC)
END = datetime(2026, 10, 30, 22, 40, tzinfo=UTC)


class Wall:
    """Epoch seconds the test moves by hand."""

    def __init__(self, at: float = 1_000.0) -> None:
        self.at = at

    def __call__(self) -> float:
        return self.at


def test_a_real_clock_follows_the_wall_clock() -> None:
    wall = Wall(START.timestamp())
    clock = DataClock.real(wall)
    assert clock.kind == "real"
    assert clock.now() == START
    wall.at += 90
    assert clock.now() == START + timedelta(seconds=90)
    assert clock.info().kind == "real"
    assert clock.info().rate_n is None


def test_a_fixed_clock_holds_one_time() -> None:
    clock = DataClock.fixed(END)
    assert clock.kind == "fixed"
    assert clock.now() == END
    assert clock.now() == END
    assert clock.info().rate_n is None


def test_a_fixed_clock_answers_in_utc_from_any_offset() -> None:
    zone = timezone(timedelta(hours=-4))
    clock = DataClock.fixed(datetime(2026, 10, 30, 18, 40, tzinfo=zone))
    assert clock.now() == END
    assert clock.now().utcoffset() == timedelta(0)


def test_a_rate_clock_runs_n_times_real_time_and_holds_at_the_end() -> None:
    wall = Wall()
    clock = DataClock.rate(START, 60, END, wall)
    assert clock.kind == "rate"
    assert clock.now() == START
    wall.at += 10
    assert clock.now() == START + timedelta(minutes=10)
    wall.at += 10
    assert clock.now() == START + timedelta(minutes=20)
    wall.at += 20
    assert clock.now() == END
    wall.at += 3600
    assert clock.now() == END
    info = clock.info()
    assert (info.kind, info.rate_n) == ("rate", 60)


def test_a_rate_clock_without_an_end_keeps_running() -> None:
    wall = Wall()
    clock = DataClock.rate(START, 2, None, wall)
    wall.at += 3600
    assert clock.now() == START + timedelta(hours=2)


def test_a_test_clock_holds_until_it_is_set() -> None:
    clock = DataClock.test(START)
    assert clock.kind == "test"
    assert clock.now() == START
    moved = clock.set(
        datetime(2026, 10, 30, 18, 20, tzinfo=timezone(timedelta(hours=-4)))
    )
    assert moved == datetime(2026, 10, 30, 22, 20, tzinfo=UTC)
    assert clock.now() == moved


def test_only_a_test_clock_can_be_set() -> None:
    for clock in (DataClock.real(), DataClock.fixed(START)):
        with pytest.raises(ValueError, match="only a test clock"):
            clock.set(END)


def test_a_time_without_an_offset_is_refused() -> None:
    naive = datetime(2026, 10, 30, 22, 10)
    with pytest.raises(ValueError, match="offset"):
        DataClock.fixed(naive)
    with pytest.raises(ValueError, match="offset"):
        DataClock.test(START).set(naive)


def test_a_rate_clock_needs_a_positive_rate() -> None:
    with pytest.raises(ValueError, match="rate"):
        DataClock("rate", start=START, rate_n=0)
    with pytest.raises(ValueError, match="rate"):
        DataClock("rate", start=START, rate_n=None)
    with pytest.raises(ValueError, match="start"):
        DataClock("fixed")


def test_the_module_reads_a_real_wall_clock_by_default() -> None:
    before = datetime.now(UTC)
    reading = data_clock.DataClock.real().now()
    assert before <= reading <= datetime.now(UTC)

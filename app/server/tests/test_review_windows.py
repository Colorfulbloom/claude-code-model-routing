"""Tests for review_windows: ranges, prior rules, clock changes and chart pages."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import review_windows as rw
from models import REVIEW_RANGES, ReviewRange

TZ = "America/New_York"
NY = ZoneInfo(TZ)
# The demo clock, October 30, 2026 at 18:00 New York time.
NOW = datetime(2026, 10, 30, 22, 0, tzinfo=UTC)
OLDEST = datetime(2026, 8, 29, 15, 48, 44, tzinfo=UTC)


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def window(
    review_range: ReviewRange,
    now: datetime = NOW,
    oldest: datetime | None = OLDEST,
    rule: rw.PriorRule = "same_time",
) -> rw.Window:
    return rw.review_window(review_range, now, TZ, oldest, rule)


# ---------------------------------------------------------------- windows


@pytest.mark.parametrize(
    ("name", "start", "prior_start", "prior_end"),
    [
        (
            "today",
            utc(2026, 10, 30, 4),
            utc(2026, 10, 29, 4),
            utc(2026, 10, 29, 22),
        ),
        ("7d", utc(2026, 10, 24, 4), utc(2026, 10, 17, 4), utc(2026, 10, 23, 22)),
        ("30d", utc(2026, 10, 1, 4), utc(2026, 9, 1, 4), utc(2026, 9, 30, 22)),
        ("90d", utc(2026, 8, 2, 4), utc(2026, 5, 4, 4), utc(2026, 8, 1, 22)),
        ("12m", utc(2025, 10, 31, 4), utc(2024, 10, 31, 4), utc(2025, 10, 30, 22)),
    ],
)
def test_same_time_windows_end_the_prior_at_the_same_wall_time(
    name: ReviewRange,
    start: datetime,
    prior_start: datetime,
    prior_end: datetime,
) -> None:
    got = window(name, oldest=None)
    assert got.start == start
    assert got.end == NOW
    assert got.prior_start == prior_start
    assert got.prior_end == prior_end
    assert got.start.tzinfo == UTC


def test_old_app_windows_for_the_demo_clock() -> None:
    """The recorded old payloads, ``usage-30d-all.json``, hold these edges."""
    got = window("30d")
    assert got.start.astimezone(NY).isoformat() == "2026-10-01T00:00:00-04:00"
    assert got.prior_start is not None
    assert got.prior_start.astimezone(NY).isoformat() == "2026-09-01T00:00:00-04:00"
    assert got.prior_end is not None
    assert got.prior_end.astimezone(NY).isoformat() == "2026-09-30T18:00:00-04:00"


@pytest.mark.parametrize("name", ["today", "7d", "30d", "90d", "12m"])
def test_whole_days_ends_the_prior_at_the_current_start(name: ReviewRange) -> None:
    got = window(name, rule="whole_days")
    same = window(name, rule="same_time")
    assert got.prior_end == got.start
    assert got.prior_start == same.prior_start
    assert got.start == same.start


def test_same_time_is_the_default_rule() -> None:
    assert rw.PRIOR_RULE == "same_time"
    assert rw.review_window("30d", NOW, TZ, OLDEST) == window("30d")


def test_the_module_switch_is_read_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rw, "PRIOR_RULE", "whole_days")
    got = rw.review_window("30d", NOW, TZ, OLDEST)
    assert got.prior_end == got.start
    assert got == window("30d", rule="whole_days")
    # An explicit rule still wins.
    assert rw.review_window("30d", NOW, TZ, OLDEST, "same_time") == window("30d")


def test_whole_days_today_compares_all_of_yesterday() -> None:
    got = window("today", rule="whole_days")
    assert got.prior_start == utc(2026, 10, 29, 4)
    assert got.prior_end == utc(2026, 10, 30, 4)


def test_all_starts_at_the_oldest_with_no_prior() -> None:
    got = window("all")
    assert got.start == OLDEST
    assert got.end == NOW
    assert got.prior_start is None
    assert got.prior_end is None
    assert got.partial is False
    assert got.prior_partial is False


def test_all_with_nothing_stored_starts_now() -> None:
    got = window("all", oldest=None)
    assert got.start == NOW
    assert got.end == NOW
    assert got.prior_start is None


@pytest.mark.parametrize("rule", ["same_time", "whole_days"])
def test_partial_flags_follow_the_oldest_request(rule: rw.PriorRule) -> None:
    # Oldest inside the current window: both windows are short of history.
    inside = window("7d", oldest=utc(2026, 10, 26, 12), rule=rule)
    assert inside.partial is True
    assert inside.prior_partial is True
    # Oldest inside the prior window only.
    prior = window("7d", oldest=utc(2026, 10, 20, 12), rule=rule)
    assert prior.partial is False
    assert prior.prior_partial is True
    # Oldest before the prior window starts.
    full = window("7d", oldest=utc(2026, 10, 1), rule=rule)
    assert full.partial is False
    assert full.prior_partial is False


def test_oldest_at_a_window_start_is_not_partial() -> None:
    got = window("7d", oldest=utc(2026, 10, 17, 4))
    assert got.prior_partial is False
    assert got.partial is False


def test_nothing_stored_is_not_partial() -> None:
    got = window("30d", oldest=None)
    assert got.partial is False
    assert got.prior_partial is False


def test_oldest_in_another_zone_compares_as_an_instant() -> None:
    oldest = datetime(2026, 10, 1, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    # October 1 in Tokyo is September 30 at 11:00 in New York.
    assert window("30d", oldest=oldest).partial is False
    assert window("30d", oldest=oldest).prior_partial is True


# ---------------------------------------------------------------- clock changes


def test_spring_forward_day_window() -> None:
    # March 8, 2026 is the 23-hour day. Midnight is still EST.
    now = datetime(2026, 3, 8, 15, 0, tzinfo=NY)
    got = rw.review_window("today", now, TZ, None)
    assert got.start == utc(2026, 3, 8, 5)
    assert got.prior_start == utc(2026, 3, 7, 5)
    assert got.prior_end == utc(2026, 3, 7, 20)  # 15:00 EST
    assert got.end - got.start == timedelta(hours=14)  # 15 wall hours, one is lost


def test_the_day_after_spring_forward_compares_nine_real_hours() -> None:
    now = datetime(2026, 3, 9, 10, 0, tzinfo=NY)
    got = rw.review_window("today", now, TZ, None)
    assert got.start == utc(2026, 3, 9, 4)  # EDT now
    assert got.prior_start == utc(2026, 3, 8, 5)  # EST midnight
    assert got.prior_end == utc(2026, 3, 8, 14)  # 10:00 EDT
    assert got.prior_start is not None
    assert got.prior_end is not None
    assert got.prior_end - got.prior_start == timedelta(hours=9)


def test_a_wall_time_in_the_spring_gap_lands_after_the_gap() -> None:
    now = datetime(2026, 3, 9, 2, 30, tzinfo=NY)
    got = rw.review_window("today", now, TZ, None)
    # 02:30 on March 8 does not exist. It lands at 03:30 EDT.
    assert got.prior_end == utc(2026, 3, 8, 7, 30)
    assert got.prior_end is not None
    assert got.prior_end.astimezone(NY).hour == 3


def test_spring_forward_inside_a_seven_day_window() -> None:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=NY)
    got = rw.review_window("7d", now, TZ, None)
    assert got.start == utc(2026, 3, 4, 5)  # EST midnight, March 4
    assert got.prior_start == utc(2026, 2, 25, 5)
    assert got.prior_end == utc(2026, 3, 3, 17)  # 12:00 EST
    whole = rw.review_window("7d", now, TZ, None, "whole_days")
    assert whole.prior_end == got.start


def test_fall_back_day_window() -> None:
    # November 1, 2026 is the 25-hour day. Midnight is still EDT.
    now = datetime(2026, 11, 1, 15, 0, tzinfo=NY)
    got = rw.review_window("today", now, TZ, None)
    assert got.start == utc(2026, 11, 1, 4)
    assert got.prior_start == utc(2026, 10, 31, 4)
    assert got.prior_end == utc(2026, 10, 31, 19)  # 15:00 EDT
    assert got.end - got.start == timedelta(hours=16)  # 15 wall hours plus one


def test_the_day_after_fall_back_compares_eleven_real_hours() -> None:
    now = datetime(2026, 11, 2, 10, 0, tzinfo=NY)
    got = rw.review_window("today", now, TZ, None)
    assert got.start == utc(2026, 11, 2, 5)  # EST now
    assert got.prior_start == utc(2026, 11, 1, 4)  # EDT midnight
    assert got.prior_end == utc(2026, 11, 1, 15)  # 10:00 EST
    assert got.prior_start is not None
    assert got.prior_end is not None
    assert got.prior_end - got.prior_start == timedelta(hours=11)


def test_fall_back_inside_a_thirty_day_window() -> None:
    now = datetime(2026, 11, 8, 9, 0, tzinfo=NY)
    got = rw.review_window("30d", now, TZ, None)
    assert got.start == utc(2026, 10, 10, 4)  # EDT midnight
    assert got.prior_start == utc(2026, 9, 10, 4)
    assert got.prior_end == utc(2026, 10, 9, 13)  # 09:00 EDT


def test_a_zone_with_no_clock_change() -> None:
    now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    got = rw.review_window("7d", now, "UTC", None)
    assert got.start == utc(2026, 10, 24)
    assert got.prior_start == utc(2026, 10, 17)
    assert got.prior_end == utc(2026, 10, 23, 12)


# ---------------------------------------------------------------- chart bars


def chart(
    name: ReviewRange,
    page: int = 0,
    now: datetime = NOW,
    oldest: datetime | None = OLDEST,
) -> rw.ChartWindow:
    return rw.chart_window(name, now, TZ, oldest, page)


def assert_contiguous(got: rw.ChartWindow) -> None:
    assert got.bars, "no bars"
    assert got.bars[0].start == got.start
    assert got.bars[-1].end == got.end
    for left, right in zip(got.bars, got.bars[1:], strict=False):
        assert left.end == right.start
    assert all(b.start < b.end for b in got.bars)


def test_units_per_range() -> None:
    # The test oldest is 62 days before T, so All counts weeks.
    assert [chart(r).unit for r in REVIEW_RANGES] == [
        "hour",
        "day",
        "day",
        "week",
        "month",
        "week",
    ]


def test_today_has_one_bar_per_hour_up_to_now() -> None:
    got = chart("today")
    assert_contiguous(got)
    assert len(got.bars) == 18  # 00:00 to 18:00, T is on the hour
    assert got.start == utc(2026, 10, 30, 4)
    assert got.end == NOW
    assert [b.open for b in got.bars] == [False] * 17 + [True]
    assert got.bars[-1].start == utc(2026, 10, 30, 21)


def test_today_clips_the_last_hour_to_now() -> None:
    got = chart("today", now=datetime(2026, 10, 30, 18, 30, tzinfo=NY))
    assert_contiguous(got)
    assert len(got.bars) == 19
    last = got.bars[-1]
    assert last.start == utc(2026, 10, 30, 22)
    assert last.end == utc(2026, 10, 30, 22, 30)
    assert last.open is True


def test_a_whole_earlier_day_has_24_hour_bars() -> None:
    got = chart("today", page=1)
    assert_contiguous(got)
    assert len(got.bars) == 24
    assert got.start == utc(2026, 10, 29, 4)
    assert got.end == utc(2026, 10, 30, 4)
    assert not any(b.open for b in got.bars)


def test_the_spring_forward_day_has_23_hour_bars() -> None:
    now = datetime(2026, 3, 9, 10, 0, tzinfo=NY)
    got = chart("today", page=1, now=now, oldest=None)
    assert_contiguous(got)
    assert len(got.bars) == 23
    assert all(b.end - b.start == timedelta(hours=1) for b in got.bars)
    assert got.start == utc(2026, 3, 8, 5)
    assert got.end == utc(2026, 3, 9, 4)


def test_the_fall_back_day_has_25_hour_bars() -> None:
    now = datetime(2026, 11, 2, 10, 0, tzinfo=NY)
    got = chart("today", page=1, now=now, oldest=None)
    assert_contiguous(got)
    assert len(got.bars) == 25
    assert got.end == utc(2026, 11, 2, 5)
    # Local hour 1 happens twice, once in EDT and once in EST.
    starts = [b.start.astimezone(NY) for b in got.bars]
    assert [s.hour for s in starts].count(1) == 2


def test_today_on_the_spring_forward_day_has_real_hours_only() -> None:
    now = datetime(2026, 3, 8, 15, 0, tzinfo=NY)
    got = chart("today", now=now, oldest=None)
    assert_contiguous(got)
    assert len(got.bars) == 14  # 15 wall hours minus the lost one


@pytest.mark.parametrize(("name", "count"), [("7d", 7), ("30d", 30)])
def test_day_ranges_have_one_bar_per_local_day(name: ReviewRange, count: int) -> None:
    got = chart(name)
    assert_contiguous(got)
    assert len(got.bars) == count
    assert got.bars[0].start.astimezone(NY).hour == 0
    assert got.bars[-1].open is True
    assert got.bars[-1].end == NOW
    assert got.bars[-1].start == utc(2026, 10, 30, 4)


def test_a_day_bar_on_a_clock_change_is_23_or_25_hours() -> None:
    spring = chart("7d", now=datetime(2026, 3, 10, 12, 0, tzinfo=NY), oldest=None)
    lengths = [b.end - b.start for b in spring.bars[:-1]]
    assert timedelta(hours=23) in lengths
    fall = chart("7d", now=datetime(2026, 11, 3, 12, 0, tzinfo=NY), oldest=None)
    assert timedelta(hours=25) in [b.end - b.start for b in fall.bars[:-1]]


def test_90_days_is_weeks_that_start_on_monday() -> None:
    got = chart("90d")
    assert_contiguous(got)
    assert got.unit == "week"
    first = got.bars[0]
    # August 2, 2026 is a Sunday, so the first week is one day.
    assert first.start == utc(2026, 8, 2, 4)
    assert first.end == utc(2026, 8, 3, 4)
    for bar in got.bars[1:]:
        assert bar.start.astimezone(NY).weekday() == 0
    assert len(got.bars) == 14
    assert got.bars[-1].open is True
    # The last week runs Monday October 26 to now, which is Friday.
    assert got.bars[-1].start == utc(2026, 10, 26, 4)
    assert got.bars[-2].end - got.bars[-2].start == timedelta(days=7)


def test_12_months_is_calendar_months() -> None:
    got = chart("12m")
    assert_contiguous(got)
    assert got.unit == "month"
    assert len(got.bars) == 13
    assert got.bars[0].start == utc(2025, 10, 31, 4)
    assert got.bars[0].end == utc(2025, 11, 1, 4)  # midnight EDT
    assert got.bars[1].start.astimezone(NY).date() == date(2025, 11, 1)
    assert got.bars[-1].start.astimezone(NY).date() == date(2026, 10, 1)
    for bar in got.bars[1:]:
        assert bar.start.astimezone(NY).day == 1
    # December rolls the year.
    assert got.bars[2].start.astimezone(NY).date() == date(2025, 12, 1)
    assert got.bars[3].start.astimezone(NY).date() == date(2026, 1, 1)


def test_older_pages_are_whole_windows_of_the_same_length() -> None:
    newest = chart("30d")
    one = chart("30d", page=1)
    two = chart("30d", page=2)
    assert one.end == newest.start
    assert two.end == one.start
    assert len(one.bars) == 30
    assert len(two.bars) == 30
    assert one.start == utc(2026, 9, 1, 4)
    assert not any(b.open for b in one.bars)
    assert_contiguous(one)


def test_older_week_and_month_pages_clip_both_edges() -> None:
    weeks = chart("90d", page=1)
    assert_contiguous(weeks)
    assert weeks.end == chart("90d").start
    assert weeks.bars[0].start == weeks.start
    assert weeks.bars[-1].end == weeks.end
    months = chart("12m", page=1)
    assert_contiguous(months)
    assert months.end == chart("12m").start
    assert months.start == utc(2024, 10, 31, 4)
    assert len(months.bars) == 13


def assert_one_page_with_both_ends_reached(got: rw.ChartWindow) -> None:
    assert_contiguous(got)
    assert got.start == got.bars[0].start
    assert got.end == NOW
    assert got.bars[0].holds_oldest is True
    assert got.bars[-1].open is True
    assert got.has_earlier is False
    assert got.earlier_reason == "no_earlier_data"
    assert got.has_later is False
    assert got.later_reason == "newest"
    assert got.newest is True


def test_all_counts_weeks_when_the_span_is_two_months() -> None:
    got = chart("all")  # the oldest is 62 days before T
    assert got.unit == "week"
    assert got.start == OLDEST
    assert_one_page_with_both_ends_reached(got)
    assert len(got.bars) == 10  # a short week from Saturday August 29, then nine more
    assert got.bars[1].start == utc(2026, 8, 31, 4)  # a Monday, local midnight
    assert got.bars[-1].start == utc(2026, 10, 26, 4)


def test_all_counts_months_when_the_span_is_over_13_weeks() -> None:
    oldest = datetime(2026, 8, 29, 15, 48, 44, tzinfo=UTC) - timedelta(days=40)
    got = chart("all", oldest=oldest)  # 102 days
    assert got.unit == "month"
    assert got.start == oldest
    assert_one_page_with_both_ends_reached(got)
    assert len(got.bars) == 4  # July (short, from the 20th), August, September, October
    assert got.bars[0].holds_oldest is True


def test_all_counts_days_when_the_span_is_a_month_or_less() -> None:
    oldest = NOW - timedelta(days=20, hours=3, minutes=7)
    got = chart("all", oldest=oldest)
    assert got.unit == "day"
    assert got.start == oldest
    assert_one_page_with_both_ends_reached(got)
    assert len(got.bars) == 21
    assert got.bars[1].start == utc(2026, 10, 11, 4)


@pytest.mark.parametrize(
    ("span", "unit"),
    [
        (timedelta(0), "day"),
        (timedelta(days=31), "day"),
        (timedelta(days=31, seconds=1), "week"),
        (timedelta(weeks=13), "week"),
        (timedelta(weeks=13, seconds=1), "month"),
        (timedelta(days=800), "month"),
    ],
)
def test_all_unit_changes_just_after_31_days_and_13_weeks(
    span: timedelta, unit: str
) -> None:
    assert rw.all_unit(NOW, NOW - span) == unit
    assert chart("all", oldest=NOW - span).unit == unit


def test_all_with_nothing_stored_counts_days() -> None:
    assert rw.all_unit(NOW, None) == "day"


def test_the_other_ranges_keep_their_unit_whatever_the_span() -> None:
    old = NOW - timedelta(days=900)
    assert [chart(r, oldest=old).unit for r in REVIEW_RANGES[:-1]] == [
        "hour",
        "day",
        "day",
        "week",
        "month",
    ]


def test_all_has_no_second_page() -> None:
    with pytest.raises(ValueError, match="no chart page 1"):
        chart("all", page=1)


def test_a_negative_page_is_refused() -> None:
    with pytest.raises(ValueError, match="no chart page -1"):
        chart("30d", page=-1)


def test_all_with_nothing_stored_has_no_bars() -> None:
    got = chart("all", oldest=None)
    assert got.bars == ()
    assert got.start == got.end == NOW
    assert got.has_earlier is False
    assert got.earlier_reason == "no_earlier_data"


# ---------------------------------------------------------------- bar flags


def test_bars_before_the_oldest_have_no_records() -> None:
    oldest = datetime(2026, 10, 30, 5, 30, tzinfo=NY)
    got = chart("today", oldest=oldest)
    flags = [(b.no_records, b.holds_oldest) for b in got.bars]
    assert flags[:5] == [(True, False)] * 5  # 00:00 to 05:00
    assert flags[5] == (False, True)  # 05:00 to 06:00 holds 05:30
    assert flags[6:] == [(False, False)] * 12


def test_a_bar_that_ends_at_the_oldest_has_no_records() -> None:
    oldest = datetime(2026, 10, 30, 5, 0, tzinfo=NY)
    got = chart("today", oldest=oldest)
    assert got.bars[4].no_records is True
    assert got.bars[4].holds_oldest is False
    assert got.bars[5].holds_oldest is True
    assert got.bars[5].no_records is False


def test_with_nothing_stored_every_bar_has_no_records() -> None:
    got = chart("7d", oldest=None)
    assert all(b.no_records and not b.holds_oldest for b in got.bars)


def test_the_oldest_in_a_later_bar_leaves_earlier_pages_empty() -> None:
    got = chart("7d", page=1)
    assert all(b.no_records for b in got.bars) is False  # OLDEST is Aug 29
    far = chart("7d", page=20)
    assert all(b.no_records for b in far.bars)
    assert far.has_earlier is False


# ---------------------------------------------------------------- pager


def test_the_newest_page_has_no_later_page() -> None:
    got = chart("30d")
    assert got.newest is True
    assert got.has_later is False
    assert got.later_reason == "newest"


def test_pages_go_earlier_until_the_oldest_is_reached() -> None:
    states = [
        (p, chart("30d", p).has_earlier, chart("30d", p).earlier_reason)
        for p in range(4)
    ]
    # Page 2 starts August 2, before the oldest request on August 29.
    assert states == [
        (0, True, None),
        (1, True, None),
        (2, False, "no_earlier_data"),
        (3, False, "no_earlier_data"),
    ]
    for page in (1, 2, 3):
        got = chart("30d", page)
        assert got.has_later is True
        assert got.later_reason is None
        assert got.newest is False


def test_a_page_starting_exactly_at_the_oldest_is_the_last() -> None:
    oldest = utc(2026, 9, 1, 4)
    assert chart("30d", 1, oldest=oldest).has_earlier is False
    assert chart("30d", 0, oldest=oldest).has_earlier is True


def test_with_nothing_stored_there_is_no_earlier_data() -> None:
    got = chart("30d", oldest=None)
    assert got.has_earlier is False
    assert got.earlier_reason == "no_earlier_data"


# ---------------------------------------------------------------- end date


@pytest.mark.parametrize("name", ["today", "7d", "30d", "90d", "12m"])
def test_page_for_end_round_trips_every_chart_end(name: ReviewRange) -> None:
    for page in range(4):
        got = chart(name, page)
        assert rw.page_for_end(name, NOW, TZ, got.last_date) == page


def test_page_for_end_takes_the_page_that_holds_the_date() -> None:
    today = date(2026, 10, 30)
    assert rw.page_for_end("30d", NOW, TZ, today) == 0
    assert rw.page_for_end("30d", NOW, TZ, today - timedelta(days=29)) == 0
    assert rw.page_for_end("30d", NOW, TZ, today - timedelta(days=30)) == 1
    assert rw.page_for_end("30d", NOW, TZ, today - timedelta(days=59)) == 1
    assert rw.page_for_end("30d", NOW, TZ, today - timedelta(days=60)) == 2


def test_page_for_end_after_today_is_the_newest_page() -> None:
    assert rw.page_for_end("30d", NOW, TZ, date(2027, 1, 1)) == 0


def test_page_for_end_of_all_is_the_only_page() -> None:
    assert rw.page_for_end("all", NOW, TZ, date(2020, 1, 1)) == 0


def test_the_last_date_of_the_newest_page_is_today() -> None:
    assert chart("30d").last_date == date(2026, 10, 30)
    assert chart("30d", 1).last_date == date(2026, 9, 30)
    assert chart("today", 1).last_date == date(2026, 10, 29)

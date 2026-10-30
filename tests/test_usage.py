"""Tests for the usage views (dashboard/usage.py) and transcripts.project_folders.

Every record is built here from made-up values and every expected number is
worked out by hand in the comments. Prices come from the committed prices.json
(opus-5-5 is $4 input, $5 5-minute write, $8 1-hour write, $0.20 cache read and
$20 output per million tokens). The zone is America/New_York, whose clocks fall
back on November 1, 2026 and spring forward on March 8, 2026. Nothing here
reads the real ~/.claude.

The Tidewater demo check at the end builds the demo set and compares the 30 day
totals with the README figures and with the demo builder's own truth.
"""
import datetime
import itertools
import json
import os
import shutil
import sys
import tempfile
import unittest
import zoneinfo
from unittest import mock

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import build_demo  # noqa: E402
import prices as prices_mod  # noqa: E402
import resolve  # noqa: E402
import transcripts  # noqa: E402
import usage  # noqa: E402

UTC = datetime.timezone.utc
NY = zoneinfo.ZoneInfo("America/New_York")
PRICES = prices_mod.load_prices()
CATALOG = resolve.load_rules()["models"]

OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-4-5"


def utc(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


# Friday, October 30, 2026, 14:00 in New York (EDT, UTC-4).
NOW = utc("2026-10-30T18:00:00Z")
PROJECT_A = {"key": "a", "name": "Project A", "folder": "-work-a"}
PROJECT_B = {"key": "b", "name": "Project B", "folder": "-work-b"}

_ids = itertools.count(1)


def rec(ts, mid=None, **kw):
    """One Record. Tokens default to 0. ts is an ISO string in UTC."""
    fields = dict(
        message_id=mid if mid is not None else "m%d" % next(_ids),
        request_id=None, ts_utc=utc(ts), folder="-work-a", session_id="s1",
        run_id=None, agent_type=None, model_raw=OPUS, effort="high", cwd="/work/a",
        git_branch="main", is_sidechain=False, input=0, output=0, cache_read=0,
        cache_write_5m=0, cache_write_1h=0, thinking=None, speed=None,
        service_tier=None, inference_geo=None)
    fields.update(kw)
    return transcripts.Record(**fields)


def sub(ts, agent, run, **kw):
    """A request made by a subagent run."""
    kw.setdefault("is_sidechain", True)
    return rec(ts, run_id=run, agent_type=agent, **kw)


def oldest_by_folder(records, projects, skipped=None):
    """What the reader would hand over: {folder: oldest record ts}, per folder.

    skipped is a datetime held by an old skipped file in every folder of the
    records and the projects, or None for no skipped file.
    """
    out = {}
    for r in records:
        if r.folder not in out or r.ts_utc < out[r.folder]:
            out[r.folder] = r.ts_utc
    if skipped is not None:
        folders = set(out) | set(p["folder"] for p in projects if p.get("folder"))
        for folder in folders:
            out[folder] = min(out.get(folder, skipped), skipped)
    return out


def views(records, scope="all", now=NOW, tz=NY, oldest_seen=None, projects=(PROJECT_A,), **kw):
    """oldest_seen is None, a datetime held by a skipped file in every folder, or a dict."""
    if not isinstance(oldest_seen, dict):
        oldest_seen = oldest_by_folder(records, projects, oldest_seen)
    return usage.build_views(records, scope, now, tz, PRICES, CATALOG, oldest_seen,
                             projects=projects, **kw)


EARLY = utc("2026-08-01T00:00:00Z")  # older than any record: previous windows exist


def by_key(rows, key, field="route_key"):
    return [r for r in rows if r[field] == key][0]


# ---------------------------------------------------------------- dedupe

class DedupeTests(unittest.TestCase):
    def test_largest_output_wins_in_either_order(self):
        first = rec("2026-10-30T15:00:00Z", "x", output=5)
        second = rec("2026-10-30T15:00:01Z", "x", output=9)
        for rows in ([first, second], [second, first]):
            kept, no_id = usage.dedupe(rows)
            self.assertEqual([9], [r.output for r in kept])
            self.assertEqual(0, no_id)

    def test_tie_goes_to_the_later_timestamp_wherever_it_sits(self):
        early = rec("2026-10-30T15:00:00Z", "x", output=5, input=1)
        late = rec("2026-10-30T15:00:05Z", "x", output=5, input=2)
        for rows in ([early, late], [late, early]):
            kept, _ = usage.dedupe(rows)
            self.assertEqual([2], [r.input for r in kept])

    def test_tie_on_output_and_time_goes_to_the_later_file(self):
        a = rec("2026-10-30T15:00:00Z", "x", output=5, input=1)
        b = rec("2026-10-30T15:00:00Z", "x", output=5, input=2)
        self.assertEqual([2], [r.input for r in usage.dedupe([a, b])[0]])
        self.assertEqual([1], [r.input for r in usage.dedupe([b, a])[0]])

    def test_runs_across_every_file(self):
        main = rec("2026-10-30T15:00:00Z", "x", output=5, folder="-work-a")
        agent = sub("2026-10-30T15:00:01Z", "builder", "r1", mid="x", output=9, folder="-work-b",
                    session_id="s2")
        kept, _ = usage.dedupe([main, agent])
        self.assertEqual(1, len(kept))
        self.assertEqual(("-work-b", "r1"), (kept[0].folder, kept[0].run_id))

    def test_request_id_stands_in_for_a_missing_message_id(self):
        one = rec("2026-10-30T15:00:00Z", "ignored", output=5)._replace(message_id=None, request_id="q1")
        two = rec("2026-10-30T15:00:01Z", "ignored", output=8)._replace(message_id=None, request_id="q1")
        kept, no_id = usage.dedupe([one, two])
        self.assertEqual([8], [r.output for r in kept])
        self.assertEqual(0, no_id)

    def test_a_record_with_no_id_is_kept_and_counted(self):
        bare = [rec("2026-10-30T15:00:0%dZ" % i, "ignored", output=5)._replace(message_id=None) for i in range(3)]
        kept, no_id = usage.dedupe(bare)
        self.assertEqual(3, len(kept))
        self.assertEqual(3, no_id)

    def test_other_rows_keep_their_order(self):
        a1 = rec("2026-10-30T15:00:00Z", "a", output=1)
        b1 = rec("2026-10-30T15:00:01Z", "b", output=1)
        a2 = rec("2026-10-30T15:00:02Z", "a", output=2)
        c1 = rec("2026-10-30T15:00:03Z", "c", output=1)
        kept, _ = usage.dedupe([a1, b1, a2, c1])
        self.assertEqual([("a", 2), ("b", 1), ("c", 1)], [(r.message_id, r.output) for r in kept])

    def test_views_count_a_repeated_response_once_at_its_largest_output(self):
        rows = [rec("2026-10-30T15:00:00Z", "x", output=5), rec("2026-10-30T15:00:01Z", "x", output=9),
                rec("2026-10-30T15:00:02Z", "y", output=3)]
        totals = views(rows)["today"]["totals"]
        self.assertEqual(2, totals["requests"])
        self.assertEqual(12, totals["tokens"])  # 9 + 3

    def test_dedupe_is_global_so_scope_cannot_bring_back_a_losing_row(self):
        loser = rec("2026-10-30T15:00:00Z", "x", output=5, folder="-work-b")
        winner = rec("2026-10-30T15:00:01Z", "x", output=10, folder="-work-a")
        out = views([loser, winner], projects=(PROJECT_A, PROJECT_B))
        self.assertEqual(10, out["today"]["totals"]["tokens"])
        out_b = views([loser, winner], scope="b", projects=(PROJECT_A, PROJECT_B))
        self.assertEqual(0, out_b["today"]["totals"]["tokens"])
        out_a = views([loser, winner], scope="a", projects=(PROJECT_A, PROJECT_B))
        self.assertEqual(10, out_a["today"]["totals"]["tokens"])

    def test_no_id_rows_note_adds_the_dedupe_count_to_the_readers(self):
        bare = rec("2026-10-30T15:00:00Z", "ignored", output=5)._replace(message_id=None)
        out = views([bare, rec("2026-10-30T15:00:01Z", "y", output=1)], reader_notes={"no_id_rows": 4})
        self.assertEqual(5, out["today"]["notes"]["no_id_rows"])
        self.assertEqual(2, out["today"]["totals"]["requests"])


# ---------------------------------------------------------------- windows

class WindowTests(unittest.TestCase):
    def test_ranges_start_at_local_midnight_and_end_at_now(self):
        out = views([])
        self.assertEqual("2026-10-30T00:00:00-04:00", out["today"]["start"])
        self.assertEqual("2026-10-24T00:00:00-04:00", out["7d"]["start"])
        self.assertEqual("2026-10-01T00:00:00-04:00", out["30d"]["start"])
        for name in ("today", "7d", "30d"):
            self.assertEqual("2026-10-30T14:00:00-04:00", out[name]["end"])
            self.assertEqual(name, out[name]["range"])

    def test_requests_land_in_the_range_by_local_time_at_both_edges(self):
        rows = [
            rec("2026-10-01T03:59:59Z", output=1),    # Sep 30, 23:59:59 local: in no range
            rec("2026-10-01T04:00:00Z", output=2),    # 30 days start, inclusive
            rec("2026-10-24T03:59:59Z", output=4),    # Oct 23, 23:59:59 local: 30 days only
            rec("2026-10-24T04:00:00Z", output=8),    # 7 days start, inclusive
            rec("2026-10-30T03:59:59Z", output=16),   # Oct 29, 23:59:59 local
            rec("2026-10-30T04:00:00Z", output=32),   # today start, inclusive
            rec("2026-10-30T18:00:00Z", output=64),   # now, inclusive
            rec("2026-10-30T18:00:01Z", output=128),  # after now: in no range
        ]
        out = views(rows)
        self.assertEqual(32 + 64, out["today"]["totals"]["tokens"])
        self.assertEqual(8 + 16 + 32 + 64, out["7d"]["totals"]["tokens"])
        self.assertEqual(2 + 4 + 8 + 16 + 32 + 64, out["30d"]["totals"]["tokens"])

    def test_previous_window_is_the_current_one_shifted_back_with_the_same_clock(self):
        out = views([], oldest_seen=EARLY)
        want = {
            "today": ("2026-10-29T00:00:00-04:00", "2026-10-29T14:00:00-04:00"),
            "7d": ("2026-10-17T00:00:00-04:00", "2026-10-23T14:00:00-04:00"),
            "30d": ("2026-09-01T00:00:00-04:00", "2026-09-30T14:00:00-04:00"),
        }
        for name, (start, end) in want.items():
            self.assertEqual(start, out[name]["previous_start"])
            self.assertEqual(end, out[name]["previous_end"])

    def test_previous_totals_cover_only_the_shifted_window(self):
        rows = [
            rec("2026-10-29T03:59:59Z", output=1),    # before yesterday's start
            rec("2026-10-29T04:00:00Z", output=2),    # yesterday start, inclusive
            rec("2026-10-29T18:00:00Z", output=4),    # yesterday at 14:00, inclusive
            rec("2026-10-29T18:00:01Z", output=8),    # after yesterday's 14:00
            rec("2026-10-17T03:59:59Z", output=16),
            rec("2026-10-17T04:00:00Z", output=32),
            rec("2026-10-23T18:00:00Z", output=64),
            rec("2026-10-23T18:00:01Z", output=128),
            rec("2026-09-01T03:59:59Z", output=256),
            rec("2026-09-01T04:00:00Z", output=512),
            rec("2026-09-30T18:00:00Z", output=1024),
            rec("2026-09-30T18:00:01Z", output=2048),
        ]
        out = views(rows, oldest_seen=EARLY)
        self.assertEqual(2 + 4, out["today"]["previous"]["tokens"])
        self.assertEqual(32 + 64, out["7d"]["previous"]["tokens"])
        self.assertEqual(512 + 1024, out["30d"]["previous"]["tokens"])

    def test_a_clock_change_does_not_move_the_hours_of_the_previous_window(self):
        now = utc("2026-11-01T20:00:00Z")  # 15:00 EST, after the clocks fell back
        rows = [
            rec("2026-10-31T19:00:00Z", output=1),   # 15:00 EDT yesterday: the shifted end, inclusive
            rec("2026-10-31T19:00:01Z", output=2),   # a day back minus 24 hours would include this
            rec("2026-10-31T03:59:59Z", output=4),   # before yesterday's midnight
        ]
        out = views(rows, now=now, oldest_seen=EARLY)
        today = out["today"]
        self.assertEqual("2026-11-01T00:00:00-04:00", today["start"])
        self.assertEqual("2026-11-01T15:00:00-05:00", today["end"])
        self.assertEqual("2026-10-31T00:00:00-04:00", today["previous_start"])
        self.assertEqual("2026-10-31T15:00:00-04:00", today["previous_end"])
        self.assertEqual(1, today["previous"]["tokens"])
        self.assertEqual("2026-10-19T00:00:00-04:00", out["7d"]["previous_start"])
        self.assertEqual("2026-10-25T15:00:00-04:00", out["7d"]["previous_end"])
        self.assertEqual("2026-10-03T00:00:00-04:00", out["30d"]["start"])
        self.assertEqual("2026-09-03T00:00:00-04:00", out["30d"]["previous_start"])
        self.assertEqual("2026-10-02T15:00:00-04:00", out["30d"]["previous_end"])

    def test_the_previous_of_a_25_hour_day_keeps_its_wall_clock_hours(self):
        now = utc("2026-11-02T15:00:00Z")  # 10:00 EST on the day after the long day
        today = views([], now=now, oldest_seen=EARLY)["today"]
        self.assertEqual("2026-11-02T00:00:00-05:00", today["start"])
        self.assertEqual("2026-11-01T00:00:00-04:00", today["previous_start"])
        self.assertEqual("2026-11-01T10:00:00-05:00", today["previous_end"])


class NoEarlierDataTests(unittest.TestCase):
    def previous_is_none(self, out):
        return {name: out[name]["previous"] is None for name in ("today", "7d", "30d")}

    def test_previous_is_none_when_it_starts_before_the_oldest_record(self):
        # Today's previous starts Oct 29 00:00 local. 7 days: Oct 17. 30 days: Sep 1.
        out = views([rec("2026-10-28T12:00:00Z", output=1)])
        self.assertEqual({"today": False, "7d": True, "30d": True}, self.previous_is_none(out))
        out = views([rec("2026-10-29T12:00:00Z", output=1)])
        self.assertEqual({"today": True, "7d": True, "30d": True}, self.previous_is_none(out))
        out = views([rec("2026-10-30T12:00:00Z", output=1)])
        self.assertEqual({"today": True, "7d": True, "30d": True}, self.previous_is_none(out))
        out = views([rec("2026-10-10T12:00:00Z", output=1)])
        self.assertEqual({"today": False, "7d": False, "30d": True}, self.previous_is_none(out))

    def test_previous_exists_when_it_starts_exactly_at_the_oldest_record(self):
        out = views([rec("2026-10-29T04:00:00Z", output=1)])
        self.assertIsNotNone(out["today"]["previous"])
        out = views([rec("2026-10-29T04:00:01Z", output=1)])
        self.assertIsNone(out["today"]["previous"])

    def test_an_older_skipped_file_moves_the_oldest_data_back(self):
        rows = [rec("2026-10-30T12:00:00Z", output=1)]
        out = views(rows, oldest_seen={"-work-a": utc("2026-09-01T04:00:00Z")})
        self.assertEqual({"today": False, "7d": False, "30d": False}, self.previous_is_none(out))
        out = views(rows, oldest_seen={"-work-a": utc("2026-09-01T04:00:01Z")})
        self.assertEqual({"today": False, "7d": False, "30d": True}, self.previous_is_none(out))

    def test_oldest_seen_later_than_the_oldest_record_changes_nothing(self):
        rows = [rec("2026-10-10T12:00:00Z", output=1)]
        out = views(rows, oldest_seen={"-work-a": utc("2026-10-10T12:00:00Z")})
        self.assertEqual({"today": False, "7d": False, "30d": True}, self.previous_is_none(out))
        out = views(rows, oldest_seen=utc("2026-10-30T00:00:00Z"))   # the helper keeps the earlier
        self.assertEqual({"today": False, "7d": False, "30d": True}, self.previous_is_none(out))

    def test_no_data_at_all_gives_no_previous(self):
        out = views([])
        self.assertEqual({"today": True, "7d": True, "30d": True}, self.previous_is_none(out))
        self.assertEqual(0, out["30d"]["totals"]["requests"])

    def test_the_oldest_record_is_the_oldest_in_scope(self):
        rows = [rec("2026-10-02T12:00:00Z", output=1, folder="-work-a"),
                rec("2026-10-30T12:00:00Z", output=1, folder="-work-b")]
        both = (PROJECT_A, PROJECT_B)
        self.assertIsNone(views(rows, scope="b", projects=both)["today"]["previous"])
        self.assertIsNotNone(views(rows, scope="all", projects=both)["today"]["previous"])
        self.assertIsNotNone(views(rows, scope="all", projects=both)["7d"]["previous"])
        self.assertIsNone(views(rows, scope="all", projects=both)["30d"]["previous"])
        # A skipped older file in b's own folder gives b a previous.
        seen = views(rows, scope="b", projects=both,
                     oldest_seen={"-work-a": utc("2026-10-02T12:00:00Z"), "-work-b": utc("2026-08-01T00:00:00Z")})
        self.assertIsNotNone(seen["30d"]["previous"])

    def test_a_project_with_no_folder_or_no_key_has_no_previous(self):
        rows = [rec("2026-10-30T12:00:00Z", output=1)]
        nowhere = {"key": "n", "name": "Nowhere", "folder": None}
        out = views(rows, scope="n", projects=(PROJECT_A, nowhere), oldest_seen={"-work-a": EARLY})
        self.assertEqual({"today": True, "7d": True, "30d": True}, self.previous_is_none(out))
        out = views(rows, scope="a", oldest_seen={})
        self.assertEqual({"today": True, "7d": True, "30d": True}, self.previous_is_none(out))

    def test_a_repeated_oldest_row_gives_a_new_project_no_previous(self):
        # Project a's oldest row (Oct 2) is written twice and dedupe keeps the later copy.
        # Project b is new: its only row is from yesterday and no file was skipped.
        # The oldest moment of b is its own row, so no range of b has a previous.
        b_row = rec("2026-10-29T15:00:00Z", "mb", output=1, folder="-work-b")
        unique = [rec("2026-10-02T12:00:00Z", "ma", output=5), b_row]
        repeated = [rec("2026-10-02T12:00:00Z", "ma", output=5),
                    rec("2026-10-02T12:00:05Z", "ma", output=5), b_row]
        both = (PROJECT_A, PROJECT_B)
        seen = {}
        for name, rows in (("unique", unique), ("repeated", repeated)):
            out = views(rows, scope="b", projects=both)
            seen[name] = self.previous_is_none(out)
            self.assertEqual({"today": True, "7d": True, "30d": True}, seen[name], name)
            self.assertEqual(0, out["today"]["totals"]["tokens"], name)
            self.assertEqual(1, out["7d"]["totals"]["tokens"], name)
        self.assertEqual(seen["unique"], seen["repeated"])

    def test_a_skipped_file_in_one_folder_gives_a_previous_only_there(self):
        rows = [rec("2026-10-30T12:00:00Z", "ma", output=1),
                rec("2026-10-30T12:00:00Z", "mb", output=1, folder="-work-b")]
        both = (PROJECT_A, PROJECT_B)
        seen = {"-work-a": utc("2026-08-01T00:00:00Z"), "-work-b": utc("2026-10-30T12:00:00Z")}
        out_a = views(rows, scope="a", projects=both, oldest_seen=seen)
        out_b = views(rows, scope="b", projects=both, oldest_seen=seen)
        self.assertEqual({"today": False, "7d": False, "30d": False}, self.previous_is_none(out_a))
        self.assertEqual({"today": True, "7d": True, "30d": True}, self.previous_is_none(out_b))


# ---------------------------------------------------------------- time zone and buckets

class BucketTests(unittest.TestCase):
    def test_today_has_every_local_hour_and_later_hours_are_empty(self):
        rows = [rec("2026-10-30T14:00:00Z", output=5),               # 10:00 local
                rec("2026-10-30T15:30:00Z", output=7)]               # 11:30 local
        today = views(rows)["today"]
        self.assertEqual("hour", today["bucket_unit"])
        buckets = today["buckets"]
        self.assertEqual(list(range(24)), [b["hour"] for b in buckets])
        self.assertEqual("2026-10-30T00:00:00-04:00", buckets[0]["start"])
        self.assertEqual("2026-10-30T10:00:00-04:00", buckets[10]["start"])
        self.assertEqual({"2026-10-30"}, {b["date"] for b in buckets})
        self.assertEqual(5, buckets[10]["tokens"])
        self.assertEqual({OPUS: 5}, buckets[10]["by_model"])
        self.assertEqual(7, buckets[11]["tokens"])
        for b in buckets[:10] + buckets[12:]:
            self.assertEqual((0, {}, {}), (b["tokens"], b["by_model"], b["runs_by_agent"]))

    def test_seven_and_thirty_days_use_one_bucket_per_local_day(self):
        out = views([rec("2026-10-30T03:59:59Z", output=3)])    # Oct 29, 23:59:59 local
        week = out["7d"]
        self.assertEqual("day", week["bucket_unit"])
        self.assertEqual(["2026-10-%d" % d for d in range(24, 31)], [b["date"] for b in week["buckets"]])
        self.assertEqual([None] * 7, [b["hour"] for b in week["buckets"]])
        self.assertEqual("2026-10-24T00:00:00-04:00", week["buckets"][0]["start"])
        self.assertEqual([0, 0, 0, 0, 0, 3, 0], [b["tokens"] for b in week["buckets"]])
        month = out["30d"]
        self.assertEqual("day", month["bucket_unit"])
        self.assertEqual(30, len(month["buckets"]))
        self.assertEqual("2026-10-01", month["buckets"][0]["date"])
        self.assertEqual("2026-10-30", month["buckets"][-1]["date"])

    def test_the_day_the_clocks_fall_back_has_25_hourly_buckets(self):
        now = utc("2026-11-01T20:00:00Z")  # 15:00 EST
        rows = [
            rec("2026-11-01T04:00:00Z", output=1),   # 00:00 EDT
            rec("2026-11-01T05:30:00Z", output=2),   # 01:30 EDT, the first 01:00 hour
            rec("2026-11-01T06:30:00Z", output=4),   # 01:30 EST, the second 01:00 hour
            rec("2026-11-01T07:00:00Z", output=8),   # 02:00 EST
            rec("2026-11-01T20:00:00Z", output=16),  # 15:00 EST, now
            rec("2026-11-01T03:59:59Z", output=32),  # 23:59:59 EDT the day before
        ]
        today = views(rows, now=now, oldest_seen=EARLY)["today"]
        buckets = today["buckets"]
        self.assertEqual(25, len(buckets))
        self.assertEqual([0, 1, 1] + list(range(2, 24)), [b["hour"] for b in buckets])
        self.assertEqual("2026-11-01T01:00:00-04:00", buckets[1]["start"])
        self.assertEqual("2026-11-01T01:00:00-05:00", buckets[2]["start"])
        self.assertEqual("2026-11-01T02:00:00-05:00", buckets[3]["start"])
        want = [0] * 25
        want[0], want[1], want[2], want[3], want[16] = 1, 2, 4, 8, 16
        self.assertEqual(want, [b["tokens"] for b in buckets])
        self.assertEqual(1 + 2 + 4 + 8 + 16, today["totals"]["tokens"])

    def test_days_on_both_sides_of_the_clock_change_use_local_dates(self):
        now = utc("2026-11-01T20:00:00Z")
        rows = [
            rec("2026-10-30T03:59:59Z", output=256),   # Oct 29, 23:59:59 EDT
            rec("2026-10-31T03:59:59Z", output=1),     # Oct 30, 23:59:59 EDT
            rec("2026-10-31T19:00:00Z", output=2),     # Oct 31, 15:00 EDT
            rec("2026-11-01T03:59:59Z", output=4),     # Oct 31, 23:59:59 EDT (a UTC date says Nov 1)
            rec("2026-11-01T04:00:00Z", output=8),     # Nov 1, 00:00 EDT
            rec("2026-11-01T06:30:00Z", output=16),    # Nov 1, 01:30 EST
            rec("2026-11-01T20:00:00Z", output=32),    # Nov 1, 15:00 EST
        ]
        week = views(rows, now=now, oldest_seen=EARLY)["7d"]
        self.assertEqual(["2026-10-%d" % d for d in range(26, 32)] + ["2026-11-01"],
                         [b["date"] for b in week["buckets"]])
        tokens = {b["date"]: b["tokens"] for b in week["buckets"]}
        self.assertEqual(256, tokens["2026-10-29"])
        self.assertEqual(1, tokens["2026-10-30"])
        self.assertEqual(2 + 4, tokens["2026-10-31"])
        self.assertEqual(8 + 16 + 32, tokens["2026-11-01"])
        self.assertEqual(sum(tokens.values()), week["totals"]["tokens"])
        self.assertEqual("2026-11-01T00:00:00-04:00", week["buckets"][-1]["start"])

    def test_the_day_the_clocks_spring_forward_has_23_hourly_buckets(self):
        now = utc("2026-03-08T16:00:00Z")  # 12:00 EDT
        today = views([rec("2026-03-08T07:30:00Z", output=5)], now=now)["today"]  # 03:30 EDT
        self.assertEqual("2026-03-08T00:00:00-05:00", today["start"])
        self.assertEqual("2026-03-08T12:00:00-04:00", today["end"])
        self.assertEqual("2026-03-07T12:00:00-05:00", today["previous_end"])
        hours = [b["hour"] for b in today["buckets"]]
        self.assertEqual(23, len(hours))
        self.assertEqual([0, 1] + list(range(3, 24)), hours)
        self.assertEqual(5, today["buckets"][2]["tokens"])

    def test_a_normal_day_after_the_change_has_24_buckets(self):
        today = views([], now=utc("2026-11-02T15:00:00Z"))["today"]
        self.assertEqual(24, len(today["buckets"]))
        self.assertEqual(list(range(24)), [b["hour"] for b in today["buckets"]])

    def test_a_fixed_offset_zone_works_too(self):
        zone = datetime.timezone(datetime.timedelta(hours=-4))
        out = views([rec("2026-10-30T14:00:00Z", output=5)], tz=zone)
        self.assertEqual("2026-10-30T00:00:00-04:00", out["today"]["start"])
        self.assertEqual(5, out["today"]["buckets"][10]["tokens"])

    def test_bucket_runs_count_each_run_once_per_bucket(self):
        rows = [
            sub("2026-10-30T14:00:00Z", "builder", "r1", output=1),   # 10:00
            sub("2026-10-30T14:10:00Z", "builder", "r1", output=1),   # 10:10, same run
            sub("2026-10-30T14:20:00Z", "builder", "r2", output=1),   # 10:20
            sub("2026-10-30T15:00:00Z", "builder", "r1", output=1),   # 11:00, r1 again
            sub("2026-10-30T14:30:00Z", "scribe", "r3", output=1),    # 10:30
            rec("2026-10-30T14:40:00Z", output=1),                    # Main session, 10:40
        ]
        today = views(rows)["today"]
        self.assertEqual({"builder": 2, "scribe": 1, "@main": 1}, today["buckets"][10]["runs_by_agent"])
        self.assertEqual({"builder": 1}, today["buckets"][11]["runs_by_agent"])
        builder = by_key(today["by_agent"], "builder")
        self.assertEqual(24, len(builder["runs_per_day"]))
        self.assertEqual(2, builder["runs_per_day"][10])
        self.assertEqual(1, builder["runs_per_day"][11])
        self.assertEqual(3, sum(by_key(today["by_agent"], "builder")["runs_per_day"]))
        week = views(rows)["7d"]
        self.assertEqual(7, len(by_key(week["by_agent"], "builder")["runs_per_day"]))
        self.assertEqual(2, by_key(week["by_agent"], "builder")["runs_per_day"][-1])


# ---------------------------------------------------------------- effort, agents, models

class EffortTests(unittest.TestCase):
    def efforts(self, rows):
        return [r["effort"] for r in views(rows)["today"]["by_effort"]]

    def test_the_four_levels_always_appear_in_order_with_zero_rows(self):
        today = views([rec("2026-10-30T15:00:00Z", output=3, effort="high")])["today"]
        rows = today["by_effort"]
        self.assertEqual(["low", "medium", "high", "xhigh"], [r["effort"] for r in rows])
        self.assertEqual([0, 0, 3, 0], [r["tokens"] for r in rows])
        low = rows[0]
        self.assertEqual((0, 0.0, None, 0), (low["requests"], low["cost"], low["hit_rate"], low["runs"]))
        empty = views([])["today"]["by_effort"]
        self.assertEqual(["low", "medium", "high", "xhigh"], [r["effort"] for r in empty])

    def test_max_and_not_recorded_rows_appear_only_when_they_exist(self):
        base = rec("2026-10-30T15:00:00Z", output=1)
        self.assertEqual(["low", "medium", "high", "xhigh", "max"],
                         self.efforts([base, rec("2026-10-30T15:00:01Z", effort="max", output=1)]))
        self.assertEqual(["low", "medium", "high", "xhigh", None],
                         self.efforts([base, rec("2026-10-30T15:00:01Z", effort=None, output=1)]))

    def test_an_unknown_effort_string_sits_after_max_and_before_not_recorded(self):
        rows = [rec("2026-10-30T15:00:0%dZ" % i, effort=e, output=1)
                for i, e in enumerate(["turbo", None, "max", "high"])]
        self.assertEqual(["low", "medium", "high", "xhigh", "max", "turbo", None], self.efforts(rows))
        rows = [rec("2026-10-30T15:00:00Z", effort="turbo", output=1)]
        self.assertEqual(["low", "medium", "high", "xhigh", "turbo"], self.efforts(rows))

    def test_each_row_carries_the_same_sums_as_any_group(self):
        rows = [rec("2026-10-30T15:00:00Z", effort="low", output=100_000),        # $2.00
                rec("2026-10-30T15:00:01Z", effort="low", output=50_000),         # $1.00
                rec("2026-10-30T15:00:02Z", effort="xhigh", input=1_000_000)]     # $4.00
        by = {r["effort"]: r for r in views(rows)["today"]["by_effort"]}
        self.assertEqual((150_000, 2), (by["low"]["tokens"], by["low"]["requests"]))
        self.assertAlmostEqual(3.0, by["low"]["cost"], places=9)
        self.assertAlmostEqual(4.0, by["xhigh"]["cost"], places=9)


class AgentTests(unittest.TestCase):
    def test_agents_sort_by_cost_then_tokens_with_unpriced_ones_last_by_tokens(self):
        rows = [
            rec("2026-10-30T15:00:00Z", output=100_000),                                  # Main: $2.00, 100,000 tokens
            sub("2026-10-30T15:00:01Z", "builder", "b1", input=1_000_000),                # $4.00
            sub("2026-10-30T15:00:02Z", "reviewer", "r1", model_raw=SONNET, input=1_000_000),  # $2.00, 1,000,000 tokens
            sub("2026-10-30T15:00:03Z", None, "u1", output=10),                           # $0.0002
            sub("2026-10-30T15:00:04Z", "scribe", "s1", model_raw="acme-9", input=5_000_000),  # unpriced
            sub("2026-10-30T15:00:05Z", "ghost", "g1", model_raw="acme-9", input=1_000_000),   # unpriced
        ]
        agents = views(rows)["today"]["by_agent"]
        self.assertEqual(["builder", "reviewer", "@main", "@unnamed", "scribe", "ghost"],
                         [a["route_key"] for a in agents])

    def test_main_and_unnamed_keys_and_display(self):
        rows = [rec("2026-10-30T15:00:00Z", output=1, session_id="s1"),
                rec("2026-10-30T15:00:01Z", output=1, session_id="s2"),
                sub("2026-10-30T15:00:02Z", None, "u1", output=1),
                sub("2026-10-30T15:00:03Z", "", "u2", output=1, session_id="s2"),
                sub("2026-10-30T15:00:04Z", "builder", "b1", output=1)]
        agents = views(rows)["today"]["by_agent"]
        main = by_key(agents, "@main")
        self.assertEqual((None, "Main session"), (main["agent"], main["display"]))
        self.assertEqual((0, 2, 2), (main["runs"], main["sessions"], main["requests"]))
        unnamed = by_key(agents, "@unnamed")
        self.assertEqual(("@unnamed", "Unnamed agent", 2), (unnamed["agent"], unnamed["display"], unnamed["runs"]))
        builder = by_key(agents, "builder")
        self.assertEqual(("builder", "builder", 1), (builder["agent"], builder["display"], builder["runs"]))

    def test_a_run_is_a_session_and_run_id_pair(self):
        rows = [sub("2026-10-30T15:00:00Z", "builder", "r1", session_id="s1", output=1),
                sub("2026-10-30T15:00:01Z", "builder", "r1", session_id="s2", output=1),
                sub("2026-10-30T15:00:02Z", "builder", "r1", session_id="s1", output=1)]
        today = views(rows)["today"]
        self.assertEqual(2, by_key(today["by_agent"], "builder")["runs"])
        self.assertEqual(2, today["totals"]["runs"])

    def test_a_run_counts_if_any_request_is_in_range_and_only_those_tokens_count(self):
        rows = [sub("2026-10-30T03:00:00Z", "builder", "r1", output=3),   # Oct 29, 23:00 local
                sub("2026-10-30T14:00:00Z", "builder", "r1", output=7),   # Oct 30, 10:00 local
                sub("2026-10-30T03:30:00Z", "builder", "r2", output=100)]  # only yesterday
        out = views(rows)
        today = out["today"]
        self.assertEqual(1, today["totals"]["runs"])
        self.assertEqual(7, by_key(today["by_agent"], "builder")["tokens"])
        week = out["7d"]
        self.assertEqual(2, week["totals"]["runs"])
        self.assertEqual(110, by_key(week["by_agent"], "builder")["tokens"])

    def test_ran_with_and_recent_runs_use_each_runs_most_used_pair(self):
        rows = [
            sub("2026-10-30T14:00:00Z", "builder", "r1", model_raw="claude-opus-5-5-20260301", effort="high", output=1),
            sub("2026-10-30T14:01:00Z", "builder", "r1", model_raw=OPUS, effort="high", output=1),
            sub("2026-10-30T14:02:00Z", "builder", "r1", model_raw=OPUS, effort="high", output=1),
            sub("2026-10-30T14:03:00Z", "builder", "r1", model_raw=SONNET, effort="low", output=1),
            sub("2026-10-30T15:00:00Z", "builder", "r2", model_raw=SONNET + "[1m]", effort="low", output=1),
            sub("2026-10-30T16:00:00Z", "builder", "r3", model_raw=HAIKU, effort="low", output=1),
            sub("2026-10-30T16:01:00Z", "builder", "r3", model_raw=OPUS, effort="high", output=1),
        ]
        builder = by_key(views(rows)["today"]["by_agent"], "builder")
        self.assertEqual([
            {"model": OPUS, "effort": "high", "requests": 4, "runs": 1},
            {"model": SONNET, "effort": "low", "requests": 2, "runs": 1},
            {"model": HAIKU, "effort": "low", "requests": 1, "runs": 1},
        ], builder["ran_with"])
        self.assertEqual(["r3", "r2", "r1"], [r["run_id"] for r in builder["recent_runs"]])
        self.assertEqual([(HAIKU, "low"), (SONNET, "low"), (OPUS, "high")],
                         [(r["model"], r["effort"]) for r in builder["recent_runs"]])

    def test_a_model_name_that_is_not_in_the_catalog_stays_as_written(self):
        rows = [sub("2026-10-30T14:00:00Z", "builder", "r1", model_raw="acme-9", output=1)]
        builder = by_key(views(rows)["today"]["by_agent"], "builder")
        self.assertEqual("acme-9", builder["ran_with"][0]["model"])
        self.assertEqual("acme-9", builder["recent_runs"][0]["model"])

    def test_recent_runs_hold_eight_newest_first_with_the_run_fields(self):
        rows = [sub("2026-10-30T%02d:00:00Z" % (4 + i), "builder", "r%d" % i, output=i + 1,
                    session_id="s1", git_branch="dev") for i in range(10)]
        rows.append(rec("2026-10-28T12:00:00Z", output=1))   # the session's first main row
        builder = by_key(views(rows)["today"]["by_agent"], "builder")
        self.assertEqual(10, builder["runs"])
        runs = builder["recent_runs"]
        self.assertEqual(8, len(runs))
        self.assertEqual(["r9", "r8", "r7", "r6", "r5", "r4", "r3", "r2"], [r["run_id"] for r in runs])
        first = runs[0]
        self.assertEqual("2026-10-30T09:00:00-04:00", first["started"])   # 13:00Z
        self.assertEqual("2026-10-28T08:00:00-04:00", first["session_started"])
        self.assertEqual(("s1", "Project A", 10, 1), (first["session_id"], first["project"], first["tokens"], first["requests"]))
        self.assertAlmostEqual(10 * 20 / 1e6, first["cost"], places=12)
        self.assertEqual(set(["run_id", "started", "session_id", "session_started", "project", "model",
                              "effort", "tokens", "cost", "hit_rate", "requests"]), set(first))

    def test_for_main_a_run_is_a_session(self):
        rows = [rec("2026-10-30T14:00:00Z", output=1, session_id="s1"),
                rec("2026-10-30T14:05:00Z", output=1, session_id="s1"),
                rec("2026-10-30T15:00:00Z", output=1, session_id="s2", effort="low")]
        main = by_key(views(rows)["today"]["by_agent"], "@main")
        self.assertEqual((0, 2), (main["runs"], main["sessions"]))
        self.assertEqual([{"model": OPUS, "effort": "high", "requests": 2, "runs": 1},
                          {"model": OPUS, "effort": "low", "requests": 1, "runs": 1}], main["ran_with"])
        self.assertEqual(["s2", "s1"], [r["session_id"] for r in main["recent_runs"]])

    def test_pin_fn_gets_every_in_range_run_for_a_single_project_only(self):
        rows = [sub("2026-10-30T14:00:00Z", "builder", "r1", output=1),
                sub("2026-10-30T14:01:00Z", "builder", "r1", output=1),
                sub("2026-10-30T15:00:00Z", "builder", "r2", model_raw=SONNET, effort="low", output=1),
                rec("2026-10-30T16:00:00Z", output=1, session_id="s9")]
        calls = []

        def pin_fn(agent_key, ran_with, runs):
            calls.append((agent_key, ran_with, runs))
            return {"state": "matches"} if agent_key == "builder" else None

        out = views(rows, scope="a", pin_fn=pin_fn)
        today = out["today"]
        self.assertEqual({"state": "matches"}, by_key(today["by_agent"], "builder")["pin"])
        self.assertIsNone(by_key(today["by_agent"], "@main")["pin"])
        got = {c[0]: c for c in calls if c[1] == by_key(today["by_agent"], c[0])["ran_with"]}
        self.assertEqual(set(["builder", "@main"]), set(got))
        self.assertEqual([
            {"run_id": "r1", "model": OPUS, "effort": "high", "requests": 2},
            {"run_id": "r2", "model": SONNET, "effort": "low", "requests": 1},
        ], got["builder"][2])
        self.assertEqual([{"run_id": "s9", "model": OPUS, "effort": "high", "requests": 1}], got["@main"][2])

        calls[:] = []
        everything = views(rows, scope="all", pin_fn=pin_fn)
        self.assertEqual([], calls)
        self.assertIsNone(by_key(everything["today"]["by_agent"], "builder")["pin"])
        self.assertIsNone(by_key(views(rows)["today"]["by_agent"], "builder")["pin"])

    def test_pin_stays_none_without_a_pin_fn(self):
        rows = [sub("2026-10-30T14:00:00Z", "builder", "r1", output=1)]
        self.assertIsNone(by_key(views(rows, scope="a")["today"]["by_agent"], "builder")["pin"])


class ModelTests(unittest.TestCase):
    def test_models_follow_catalog_order_then_unknown_models(self):
        rows = [
            rec("2026-10-30T15:00:00Z", model_raw="claude-opus-5-5-20260301", input=10, session_id="s1"),
            rec("2026-10-30T15:00:01Z", model_raw=HAIKU, input=20, session_id="s1"),
            sub("2026-10-30T15:00:02Z", "builder", "r1", model_raw=SONNET + "[1m]", input=30),
            sub("2026-10-30T15:00:03Z", "scribe", "r2", model_raw="acme-9", input=40),
            sub("2026-10-30T15:00:04Z", "builder", "r3", model_raw="zeta-1", input=50),
            sub("2026-10-30T15:00:05Z", "scribe", "r4", model_raw="claude-fable-5-1", input=60),
            sub("2026-10-30T15:00:06Z", "scribe", "r5", model_raw="claude-haiku-5-5", input=70),
        ]
        models = views(rows)["today"]["by_model"]
        self.assertEqual(
            ["claude-haiku-4-5", "claude-fable-5-1", OPUS, SONNET, "claude-haiku-5-5", "zeta-1", "acme-9"],
            [m["model"] for m in models])
        by = {m["model"]: m for m in models}
        self.assertEqual("Haiku 4.5", by["claude-haiku-4-5"]["display_name"])
        self.assertEqual("Opus 5.5", by[OPUS]["display_name"])
        self.assertEqual(
            {"claude-haiku-4-5": "other", OPUS: 1, SONNET: 2, "claude-haiku-5-5": 3, "claude-fable-5-1": 4,
             "zeta-1": "other", "acme-9": "other"},
            {m["model"]: m["cat"] for m in models})
        self.assertEqual(["Main session"], by[OPUS]["agents"])
        self.assertEqual(["builder"], by[SONNET]["agents"])
        self.assertEqual(["Main session"], by["claude-haiku-4-5"]["agents"])
        self.assertEqual(["scribe"], by["acme-9"]["agents"])

    def test_an_unknown_model_shows_its_raw_name_and_has_no_cost(self):
        rows = [rec("2026-10-30T15:00:00Z", model_raw="acme-9", input=40)]
        row = views(rows)["today"]["by_model"][0]
        self.assertEqual(("acme-9", "acme-9", "other", None, 40), (
            row["model"], row["display_name"], row["cat"], row["cost"], row["tokens"]))
        self.assertEqual((1, 40), (row["unpriced_requests"], row["unpriced_tokens"]))

    def test_a_model_with_the_same_agent_twice_lists_it_once_sorted(self):
        rows = [sub("2026-10-30T15:00:00Z", "zed", "r1", input=1), sub("2026-10-30T15:00:01Z", "zed", "r2", input=1),
                sub("2026-10-30T15:00:02Z", "abe", "r3", input=1)]
        self.assertEqual(["abe", "zed"], views(rows)["today"]["by_model"][0]["agents"])

    def test_equal_costs_split_100_by_largest_remainder(self):
        rows = [rec("2026-10-30T15:00:00Z", model_raw=HAIKU, input=4_000_000),    # $1 per million: $4.00
                rec("2026-10-30T15:00:01Z", model_raw=OPUS, input=1_000_000),     # $4.00
                rec("2026-10-30T15:00:02Z", model_raw=SONNET, input=2_000_000)]   # $2 per million: $4.00
        models = views(rows)["today"]["by_model"]
        self.assertEqual([HAIKU, OPUS, SONNET], [m["model"] for m in models])
        # Each is 33.33 percent, so one extra point goes to the first in order.
        self.assertEqual([34, 33, 33], [m["share_pct"] for m in models])
        self.assertEqual(100, sum(m["share_pct"] for m in models))
        self.assertEqual([False] * 3, [m["share_lt1"] for m in models])

    def test_a_nonzero_share_under_half_a_percent_sets_share_lt1(self):
        rows = [rec("2026-10-30T15:00:00Z", model_raw=OPUS, input=1_000_000),      # $4.00
                rec("2026-10-30T15:00:01Z", model_raw=SONNET, input=1_000)]        # $0.002, 0.05 percent
        models = views(rows)["today"]["by_model"]
        self.assertEqual([OPUS, SONNET], [m["model"] for m in models])
        self.assertEqual([100, 0], [m["share_pct"] for m in models])
        self.assertEqual([False, True], [m["share_lt1"] for m in models])

    def test_a_share_of_exactly_half_a_percent_is_not_flagged(self):
        rows = [rec("2026-10-30T15:00:00Z", model_raw=OPUS, output=9_950_000),     # $199.00
                rec("2026-10-30T15:00:01Z", model_raw=SONNET, output=100_000)]     # $1.00, 0.5 percent
        models = views(rows)["today"]["by_model"]
        self.assertEqual([False, False], [m["share_lt1"] for m in models])
        self.assertEqual(100, sum(m["share_pct"] for m in models))

    def test_shares_are_zero_when_nothing_is_priced(self):
        rows = [rec("2026-10-30T15:00:00Z", model_raw="acme-9", input=5)]
        row = views(rows)["today"]["by_model"][0]
        self.assertEqual((0, False), (row["share_pct"], row["share_lt1"]))


# ---------------------------------------------------------------- sums

class SumTests(unittest.TestCase):
    def test_one_request_with_every_token_kind(self):
        rows = [rec("2026-10-30T15:00:00Z", input=1_000_000, output=100_000, cache_read=1_000_000,
                    cache_write_5m=500_000, cache_write_1h=250_000, thinking=40_000)]
        t = views(rows)["today"]["totals"]
        self.assertEqual(2_850_000, t["tokens"])        # 1,000,000 + 100,000 + 1,000,000 + 750,000
        self.assertEqual((1_000_000, 100_000, 1_000_000), (t["input"], t["output"], t["cache_read"]))
        self.assertEqual((750_000, 500_000, 250_000), (t["cache_write"], t["cache_write_5m"], t["cache_write_1h"]))
        self.assertEqual(40_000, t["thinking"])
        kinds = t["cost_by_kind"]
        self.assertAlmostEqual(4.0, kinds["input"], places=9)
        self.assertAlmostEqual(2.0, kinds["output"], places=9)
        self.assertAlmostEqual(0.2, kinds["cache_read"], places=9)
        self.assertAlmostEqual(4.5, kinds["cache_write"], places=9)     # 2.50 + 2.00
        self.assertAlmostEqual(10.7, t["cost"], places=9)
        self.assertAlmostEqual(1_000_000 / 2_750_000, t["hit_rate"], places=12)
        self.assertEqual((0, 0, 1, 1, 0), (t["unpriced_requests"], t["unpriced_tokens"], t["requests"], t["sessions"], t["runs"]))
        self.assertEqual(set(["tokens", "input", "output", "cache_read", "cache_write", "cache_write_5m",
                              "cache_write_1h", "thinking", "cost", "cost_by_kind", "unpriced_requests",
                              "unpriced_tokens", "hit_rate", "requests", "runs", "sessions"]), set(t))

    def test_thinking_sums_the_rows_that_have_a_value_and_is_none_when_none_do(self):
        rows = [rec("2026-10-30T15:00:00Z", output=5, thinking=3), rec("2026-10-30T15:00:01Z", output=5),
                rec("2026-10-30T15:00:02Z", output=5, thinking=4)]
        self.assertEqual(7, views(rows)["today"]["totals"]["thinking"])
        self.assertIsNone(views([rec("2026-10-30T15:00:00Z", output=5)])["today"]["totals"]["thinking"])
        self.assertIsNone(views([])["today"]["totals"]["thinking"])
        thinking = by_key(views(rows + [sub("2026-10-30T15:00:03Z", "b", "r1", output=1)])["today"]["by_agent"], "b")
        self.assertIsNone(thinking["thinking"])

    def test_hit_rate_is_cache_read_over_read_plus_write_plus_input(self):
        rows = [rec("2026-10-30T15:00:00Z", input=100, cache_read=300, cache_write_5m=50, cache_write_1h=50, output=999)]
        self.assertAlmostEqual(0.6, views(rows)["today"]["totals"]["hit_rate"], places=12)   # 300 / (300 + 100 + 100)

    def test_hit_rate_is_none_when_there_are_no_prompt_tokens(self):
        today = views([rec("2026-10-30T15:00:00Z", output=5)])["today"]
        self.assertIsNone(today["totals"]["hit_rate"])
        self.assertIsNone(views([])["today"]["totals"]["hit_rate"])

    def test_costs_are_not_rounded_and_every_group_adds_up_to_the_total(self):
        rows = [
            rec("2026-10-30T15:00:00Z", model_raw=OPUS, input=123_457, session_id="s1", effort="low"),            # 0.493828
            sub("2026-10-30T15:00:01Z", "builder", "r1", model_raw=SONNET, output=33_333, session_id="s2"),      # 0.33333
            sub("2026-10-30T15:00:02Z", "scribe", "r2", model_raw=HAIKU, cache_read=77_777, session_id="s2",
                effort="medium", folder="-work-z"),                                                              # 0.0077777
        ]
        today = views(rows)["today"]
        want = 0.493828 + 0.33333 + 0.0077777    # 0.8349357, not 0.83
        self.assertAlmostEqual(want, today["totals"]["cost"], places=12)
        self.assertNotEqual(round(want, 2), today["totals"]["cost"])
        for field in ("by_model", "by_effort", "by_agent", "sessions", "by_project"):
            with self.subTest(field=field):
                self.assertAlmostEqual(want, sum(r["cost"] or 0 for r in today[field]), places=12)
        kinds = today["totals"]["cost_by_kind"]
        self.assertAlmostEqual(want, sum(kinds.values()), places=12)
        for row in today["sessions"]:
            self.assertAlmostEqual(row["cost"], sum(a["cost"] for a in row["by_agent"]), places=12)

    def test_an_unpriced_request_counts_in_tokens_everywhere_but_not_in_cost(self):
        rows = [
            rec("2026-10-30T15:00:00Z", model_raw=OPUS, output=100_000),                          # $2.00
            sub("2026-10-30T15:00:01Z", "builder", "r1", model_raw="acme-9", input=1_000, output=500),   # 1,500 tokens
            sub("2026-10-30T15:00:02Z", "builder", "r2", model_raw=OPUS, speed="turbo", input=2_000),    # 2,000, modifier not listed
        ]
        today = views(rows)["today"]
        t = today["totals"]
        self.assertEqual(103_500, t["tokens"])
        self.assertAlmostEqual(2.0, t["cost"], places=9)
        self.assertEqual((2, 3_500), (t["unpriced_requests"], t["unpriced_tokens"]))
        builder = by_key(today["by_agent"], "builder")
        self.assertEqual((3_500, 3_500, 2), (builder["tokens"], builder["unpriced_tokens"], builder["unpriced_requests"]))
        self.assertEqual(0.0, builder["cost"])
        self.assertEqual([{"model": OPUS, "requests": 1, "tokens": 2_000},
                          {"model": "acme-9", "requests": 1, "tokens": 1_500}], today["notes"]["unpriced"])
        self.assertEqual(103_500, sum(m["tokens"] for m in today["by_model"]))
        self.assertEqual(103_500, sum(b["tokens"] for b in today["buckets"]))
        self.assertEqual(103_500, sum(s["tokens"] for s in today["sessions"]))

    def test_a_clean_view_lists_nothing_unpriced(self):
        today = views([rec("2026-10-30T15:00:00Z", output=1)])["today"]
        self.assertEqual([], today["notes"]["unpriced"])


class DeltaTests(unittest.TestCase):
    def test_token_cost_and_run_deltas_are_relative_percent(self):
        rows = [rec("2026-10-29T15:00:00Z", output=100_000),        # yesterday: $2.00
                rec("2026-10-30T15:00:00Z", output=150_000)]        # today: $3.00
        d = views(rows, oldest_seen=EARLY)["today"]["deltas"]
        self.assertAlmostEqual(50.0, d["tokens_pct"], places=9)
        self.assertAlmostEqual(50.0, d["cost_pct"], places=9)
        self.assertIsNone(d["runs_pct"])    # yesterday had no subagent runs
        self.assertIsNone(d["hit_rate_pts"])

    def test_a_drop_is_negative_and_no_change_is_zero(self):
        rows = [rec("2026-10-29T15:00:00Z", output=100_000), rec("2026-10-30T15:00:00Z", output=50_000)]
        d = views(rows, oldest_seen=EARLY)["today"]["deltas"]
        self.assertAlmostEqual(-50.0, d["tokens_pct"], places=9)
        self.assertAlmostEqual(-50.0, d["cost_pct"], places=9)
        rows = [rec("2026-10-29T15:00:00Z", output=100_000), rec("2026-10-30T15:00:00Z", output=100_000)]
        d = views(rows, oldest_seen=EARLY)["today"]["deltas"]
        self.assertEqual((0, 0), (d["tokens_pct"], d["cost_pct"]))

    def test_run_delta_compares_subagent_runs(self):
        rows = [sub("2026-10-29T15:00:0%dZ" % i, "b", "p%d" % i, output=1) for i in range(2)]
        rows += [sub("2026-10-30T15:00:0%dZ" % i, "b", "c%d" % i, output=1) for i in range(3)]
        d = views(rows, oldest_seen=EARLY)["today"]["deltas"]
        self.assertAlmostEqual(50.0, d["runs_pct"], places=9)    # 2 runs to 3

    def test_hit_rate_delta_is_in_percentage_points(self):
        rows = [rec("2026-10-29T15:00:00Z", input=50, cache_read=50),     # 0.50
                rec("2026-10-30T15:00:00Z", input=25, cache_read=75)]     # 0.75
        d = views(rows, oldest_seen=EARLY)["today"]["deltas"]
        self.assertAlmostEqual(25.0, d["hit_rate_pts"], places=9)
        same = [rec("2026-10-29T15:00:00Z", input=50, cache_read=50), rec("2026-10-30T15:00:00Z", input=10, cache_read=10)]
        self.assertEqual(0, views(same, oldest_seen=EARLY)["today"]["deltas"]["hit_rate_pts"])

    def test_a_baseline_of_zero_gives_none(self):
        rows = [rec("2026-10-30T15:00:00Z", output=100_000)]
        out = views(rows, oldest_seen=EARLY)["today"]
        self.assertIsNotNone(out["previous"])
        self.assertEqual(0, out["previous"]["tokens"])
        self.assertEqual({"tokens_pct": None, "cost_pct": None, "runs_pct": None, "hit_rate_pts": None}, out["deltas"])

    def test_every_delta_is_none_when_there_is_no_previous(self):
        out = views([rec("2026-10-30T15:00:00Z", output=100_000)])["today"]
        self.assertIsNone(out["previous"])
        self.assertEqual({"tokens_pct": None, "cost_pct": None, "runs_pct": None, "hit_rate_pts": None}, out["deltas"])

    def test_a_current_window_with_no_prompt_tokens_has_no_rate_delta(self):
        rows = [rec("2026-10-29T15:00:00Z", input=50, cache_read=50), rec("2026-10-30T15:00:00Z", output=5)]
        d = views(rows, oldest_seen=EARLY)["today"]["deltas"]
        self.assertIsNone(d["hit_rate_pts"])

    def test_a_previous_rate_of_zero_gives_a_number(self):
        rows = [rec("2026-10-29T15:00:00Z", input=100, cache_read=0),    # 0.0
                rec("2026-10-30T15:00:00Z", input=50, cache_read=50)]    # 0.5
        d = views(rows, oldest_seen=EARLY)["today"]["deltas"]
        self.assertAlmostEqual(50.0, d["hit_rate_pts"], places=9)


# ---------------------------------------------------------------- axis

class AxisTests(unittest.TestCase):
    def test_nice_max_rounds_up_to_1_2_2_5_or_5_times_a_power_of_ten(self):
        want = {0: 1, 1: 1, 2: 2, 3: 5, 5: 5, 6: 10, 11: 20, 21: 25, 26: 50, 51: 100, 999: 1000,
                1000: 1000, 1001: 2000, 2001: 2500, 2500: 2500, 2501: 5000, 5001: 10000,
                1_200_000: 2_000_000, 104_300_000: 200_000_000}
        for value, nice in want.items():
            with self.subTest(value=value):
                self.assertEqual(nice, usage.nice_max(value))

    def test_token_ticks_are_four_equal_steps_from_zero(self):
        self.assertEqual((10_000_000, [0, 2_500_000, 5_000_000, 7_500_000, 10_000_000]), usage.token_ticks(7_120_000))
        self.assertEqual((1000, [0, 250, 500, 750, 1000]), usage.token_ticks(1000))
        self.assertEqual((2, [0, 0.5, 1, 1.5, 2]), usage.token_ticks(2))

    def test_run_ticks_are_integers(self):
        self.assertEqual([0, 1, 2, 3], usage.run_ticks(0))
        self.assertEqual([0, 1, 2, 3], usage.run_ticks(3))
        self.assertEqual([0, 2, 4, 6, 8], usage.run_ticks(7))
        self.assertEqual([0, 25, 50, 75, 100], usage.run_ticks(100))
        for top in range(0, 300):
            with self.subTest(top=top):
                ticks = usage.run_ticks(top)
                self.assertTrue(all(isinstance(t, int) for t in ticks))
                self.assertGreaterEqual(ticks[-1], top)

    def test_the_axis_follows_the_tallest_bucket(self):
        rows = [rec("2026-10-30T14:00:00Z", input=7_120_000),     # 10:00 local
                rec("2026-10-30T15:00:00Z", input=1_000)]
        axis = views(rows)["today"]["axis"]
        self.assertEqual(10_000_000, axis["tokens_max_nice"])
        self.assertEqual([0, 2_500_000, 5_000_000, 7_500_000, 10_000_000], axis["tokens_ticks"])
        self.assertEqual([0, 1, 2, 3], axis["runs_ticks"])

    def test_run_ticks_follow_the_most_runs_in_one_bucket(self):
        rows = [sub("2026-10-30T14:00:0%dZ" % i, "b", "r%d" % i, output=1) for i in range(7)]
        self.assertEqual([0, 2, 4, 6, 8], views(rows)["today"]["axis"]["runs_ticks"])

    def test_an_empty_view_still_has_an_axis(self):
        axis = views([])["today"]["axis"]
        self.assertEqual(1, axis["tokens_max_nice"])
        self.assertEqual([0, 0.25, 0.5, 0.75, 1], axis["tokens_ticks"])
        self.assertEqual([0, 1, 2, 3], axis["runs_ticks"])


# ---------------------------------------------------------------- sessions, projects

class SessionTests(unittest.TestCase):
    def test_a_session_starts_at_its_first_main_row_even_when_that_row_is_out_of_range(self):
        rows = [
            rec("2026-10-28T12:00:00Z", session_id="s1", output=1),                 # main, Oct 28 08:00 local
            sub("2026-10-27T12:00:00Z", "builder", "r0", session_id="s1", output=1),  # earlier, but not main
            sub("2026-10-30T14:00:00Z", "builder", "r1", session_id="s1", output=5),
        ]
        today = views(rows)["today"]
        self.assertEqual(1, len(today["sessions"]))
        s = today["sessions"][0]
        self.assertEqual("2026-10-28T08:00:00-04:00", s["started"])
        self.assertEqual(5, s["tokens"])    # only the in-range request
        run = by_key(today["by_agent"], "builder")["recent_runs"][0]
        self.assertEqual("2026-10-28T08:00:00-04:00", run["session_started"])
        self.assertEqual("2026-10-30T10:00:00-04:00", run["started"])

    def test_a_session_with_no_main_row_starts_at_its_earliest_row(self):
        rows = [sub("2026-10-29T12:00:00Z", "builder", "r0", session_id="s2", output=1),
                sub("2026-10-30T14:00:00Z", "builder", "r1", session_id="s2", output=5)]
        s = views(rows)["today"]["sessions"][0]
        self.assertEqual("2026-10-29T08:00:00-04:00", s["started"])

    def test_sessions_list_newest_first_and_only_those_with_in_range_requests(self):
        rows = [rec("2026-10-30T13:00:00Z", session_id="old", output=1),
                rec("2026-10-30T15:00:00Z", session_id="new", output=1),
                rec("2026-10-28T12:00:00Z", session_id="gone", output=1),
                rec("2026-10-29T12:00:00Z", session_id="mid", output=1),
                rec("2026-10-30T15:30:00Z", session_id="mid", output=1)]
        out = views(rows)
        self.assertEqual(["new", "old", "mid"], [s["session_id"] for s in out["today"]["sessions"]])
        self.assertEqual(["new", "old", "mid", "gone"], [s["session_id"] for s in out["7d"]["sessions"]])

    def test_a_session_belongs_to_its_folder_not_to_later_cwd_values(self):
        rows = [rec("2026-10-30T13:00:00Z", output=1, cwd="/work/a"),
                rec("2026-10-30T13:05:00Z", output=1, cwd="/work/somewhere-else/sub"),
                sub("2026-10-30T13:10:00Z", "builder", "r1", output=1, cwd="/work/other-again")]
        out = views(rows)
        self.assertEqual(["Project A"], [s["project"] for s in out["today"]["sessions"]])
        self.assertEqual("Project A", by_key(out["today"]["by_agent"], "builder")["recent_runs"][0]["project"])

    def test_session_row_carries_branch_agents_and_the_per_agent_breakdown(self):
        rows = [rec("2026-10-30T13:00:00Z", output=100_000, git_branch="feature/x"),        # Main $2.00
                sub("2026-10-30T13:01:00Z", "builder", "r1", input=1_000_000),              # $4.00
                sub("2026-10-30T13:02:00Z", "builder", "r2", input=1_000_000),              # $4.00
                sub("2026-10-30T13:03:00Z", None, "u1", output=10)]
        s = views(rows)["today"]["sessions"][0]
        self.assertEqual("feature/x", s["branch"])
        self.assertEqual(["Unnamed agent", "builder"], s["agents"])
        self.assertEqual(3, s["runs"])           # r1, r2 and u1
        self.assertEqual(1, s["sessions"])
        # builder $8.00, Main $2.00, the unnamed agent $0.0002
        self.assertEqual(["builder", None, "@unnamed"], [a["agent"] for a in s["by_agent"]])
        self.assertEqual([2, 0, 1], [a["runs"] for a in s["by_agent"]])


class ProjectTests(unittest.TestCase):
    def two_folders(self):
        return [
            rec("2026-10-30T13:00:00Z", output=100_000, folder="-work-a", cwd="/work/a"),                # $2.00
            rec("2026-10-30T13:01:00Z", output=50_000, folder="-work-zz", cwd="/work/zz/app", session_id="u1"),   # $1.00
            rec("2026-10-30T13:02:00Z", output=50_000, folder="-work-zz", cwd="/work/zz/app", session_id="u1"),
            rec("2026-10-30T13:03:00Z", output=50_000, folder="-work-zz", cwd="/work/zz/lib", session_id="u1"),
            rec("2026-10-30T13:04:00Z", output=1, folder="-work-yy", cwd=None, session_id="u2"),
        ]

    def test_unlisted_folders_show_only_in_all_projects_named_from_the_common_cwd(self):
        today = views(self.two_folders())["today"]
        by = {p["folder"]: p for p in today["by_project"]}
        self.assertEqual(["-work-zz", "-work-a", "-work-yy"], [p["folder"] for p in today["by_project"]])
        self.assertEqual(("Project A", True, "a"), (by["-work-a"]["name"], by["-work-a"]["listed"], by["-work-a"]["key"]))
        zz = by["-work-zz"]
        self.assertEqual(("app", False, None), (zz["name"], zz["listed"], zz["key"]))   # app twice, lib once
        yy = by["-work-yy"]
        self.assertEqual(("-work-yy", False, None), (yy["name"], yy["listed"], yy["key"]))
        self.assertEqual(150_000, zz["tokens"])
        self.assertEqual(["-work-yy", "app", "Project A"], [s["project"] for s in today["sessions"]])

    def test_a_listed_project_view_leaves_unlisted_folders_out_and_has_no_project_rows(self):
        today = views(self.two_folders(), scope="a")["today"]
        self.assertIsNone(today["by_project"])
        self.assertEqual(100_000, today["totals"]["tokens"])
        self.assertEqual(["Project A"], [s["project"] for s in today["sessions"]])

    def test_projects_sort_like_agents_by_cost_then_tokens(self):
        rows = [rec("2026-10-30T13:00:00Z", output=10, folder="-work-a"),
                rec("2026-10-30T13:01:00Z", output=20, folder="-work-b", session_id="s2"),
                rec("2026-10-30T13:02:00Z", model_raw="acme-9", output=900, folder="-work-c", cwd=None, session_id="s3")]
        both = (PROJECT_A, PROJECT_B)
        names = [p["name"] for p in views(rows, projects=both)["today"]["by_project"]]
        self.assertEqual(["Project B", "Project A", "-work-c"], names)

    def test_all_projects_scope_can_be_limited_to_listed_folders(self):
        self.assertEqual("every_folder", usage.ALL_PROJECTS_SCOPE)
        with mock.patch.object(usage, "ALL_PROJECTS_SCOPE", "listed"):
            today = views(self.two_folders())["today"]
        self.assertEqual(["-work-a"], [p["folder"] for p in today["by_project"]])
        self.assertEqual(100_000, today["totals"]["tokens"])

    def test_an_unknown_project_or_one_without_a_folder_is_empty(self):
        rows = self.two_folders()
        self.assertEqual(0, views(rows, scope="nope")["today"]["totals"]["requests"])
        nofolder = {"key": "n", "name": "N", "folder": None}
        self.assertEqual(0, views(rows, scope="n", projects=(nofolder,))["today"]["totals"]["requests"])
        self.assertIsNone(views(rows, scope="n", projects=(nofolder,))["today"]["by_project"])

    def test_a_session_started_in_one_folder_stays_there(self):
        rows = [rec("2026-10-28T12:00:00Z", output=1, folder="-work-a", session_id="s1"),
                rec("2026-10-30T13:00:00Z", output=5, folder="-work-a", session_id="s1")]
        self.assertEqual("-work-a", views(rows)["7d"]["by_project"][0]["folder"])


# ---------------------------------------------------------------- shape, notes, purity

class ShapeTests(unittest.TestCase):
    def test_view_keys_are_the_ticket_shape_plus_deltas(self):
        out = views([rec("2026-10-30T15:00:00Z", output=1)], oldest_seen=EARLY)
        self.assertEqual(["today", "7d", "30d"], list(out))
        want = set(["range", "start", "end", "previous_start", "previous_end", "totals", "previous", "by_model",
                    "by_effort", "by_agent", "bucket_unit", "buckets", "axis", "sessions", "by_project",
                    "notes", "deltas"])
        for name, view in out.items():
            self.assertEqual(want, set(view))
            self.assertEqual(set(["tokens_max_nice", "tokens_ticks", "runs_ticks"]), set(view["axis"]))
            self.assertEqual(set(["start", "date", "hour", "tokens", "by_model", "runs_by_agent"]),
                             set(view["buckets"][0]))
            self.assertEqual(set(view["totals"]), set(view["previous"]))

    def test_agent_model_and_project_rows_extend_agg(self):
        rows = [sub("2026-10-30T15:00:00Z", "builder", "r1", output=1)]
        today = views(rows)["today"]
        agg = set(today["totals"])
        self.assertEqual(agg | set(["agent", "route_key", "display", "ran_with", "pin", "recent_runs", "runs_per_day"]),
                         set(today["by_agent"][0]))
        self.assertEqual(agg | set(["model", "display_name", "cat", "share_pct", "share_lt1", "agents"]),
                         set(today["by_model"][0]))
        self.assertEqual(agg | set(["effort"]), set(today["by_effort"][0]))
        self.assertEqual(agg | set(["key", "name", "listed", "folder"]), set(today["by_project"][0]))
        self.assertEqual(agg | set(["session_id", "project", "branch", "started", "agents", "by_agent"]),
                         set(today["sessions"][0]))
        self.assertEqual(agg | set(["agent"]), set(today["sessions"][0]["by_agent"][0]))

    def test_notes_carry_the_readers_counts_and_the_zone_flag(self):
        reader = {"malformed_lines": 2, "synthetic_rows": 3, "no_id_rows": 1, "skipped_old_files": 4,
                  "ignored_files": 9}
        notes = views([], reader_notes=reader, tz_fixed=True)["30d"]["notes"]
        self.assertEqual(set(["unpriced", "malformed_lines", "synthetic_rows", "no_id_rows",
                              "skipped_old_files", "tz_fixed"]), set(notes))
        self.assertEqual((2, 3, 1, 4, True), (notes["malformed_lines"], notes["synthetic_rows"],
                                              notes["no_id_rows"], notes["skipped_old_files"], notes["tz_fixed"]))
        plain = views([])["today"]["notes"]
        self.assertEqual((0, 0, 0, 0, False), (plain["malformed_lines"], plain["synthetic_rows"],
                                               plain["no_id_rows"], plain["skipped_old_files"], plain["tz_fixed"]))

    def test_constants(self):
        self.assertEqual("every_folder", usage.ALL_PROJECTS_SCOPE)
        self.assertTrue(hasattr(usage, "THINKING_IN_OUTPUT"))

    def test_it_reads_no_file_clock_or_real_path(self):
        rows = [rec("2026-10-30T15:00:00Z", output=1), sub("2026-10-30T15:01:00Z", "builder", "r1", output=2)]

        def refuse(*args, **kwargs):
            raise AssertionError("usage.build_views touched the outside world")

        with mock.patch("builtins.open", refuse), mock.patch("os.path.realpath", refuse), \
                mock.patch("time.time", refuse), mock.patch("os.listdir", refuse), mock.patch("os.stat", refuse):
            out = views(rows, scope="a", pin_fn=lambda *a: None)
        self.assertEqual(3, out["today"]["totals"]["tokens"])

    def test_it_does_not_change_its_input(self):
        rows = [rec("2026-10-30T15:00:00Z", "x", output=1), rec("2026-10-30T15:00:01Z", "x", output=2)]
        copy = list(rows)
        views(rows)
        self.assertEqual(copy, rows)

    def test_a_naive_now_is_taken_as_utc(self):
        out = views([], now=NOW.replace(tzinfo=None))
        self.assertEqual("2026-10-30T14:00:00-04:00", out["today"]["end"])


# ---------------------------------------------------------------- project_folders

class ProjectFolderTests(unittest.TestCase):
    def tmpdir(self):
        path = os.path.realpath(tempfile.mkdtemp(prefix="usage-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, path)
        return path

    def test_a_listed_project_maps_to_the_sanitized_real_path(self):
        root = self.tmpdir()
        real = os.path.join(root, "my project")
        os.makedirs(real)
        link = os.path.join(root, "link")
        os.symlink(real, link)
        folder = transcripts.sanitize(real)
        other = rec("2026-10-30T15:00:00Z", folder="-work-someone-else", cwd="/work/someone/else")
        mine = rec("2026-10-30T15:00:01Z", folder=folder, cwd=real)
        projects = [{"key": "k1", "name": "One", "path": real},
                    {"key": "k2", "name": "Two", "path": link},
                    {"key": "k3", "name": "Three", "path": os.path.join(root, "no such project")},
                    {"key": "k4", "name": "Four", "path": ""}]
        got = transcripts.project_folders(projects, [other, mine])
        self.assertEqual({"k1": folder, "k2": folder, "k3": None, "k4": None}, got)

    def test_a_project_with_no_records_has_no_folder(self):
        root = self.tmpdir()
        self.assertEqual({"k": None}, transcripts.project_folders([{"key": "k", "name": "K", "path": root}], []))

    def test_above_200_characters_the_prefix_and_the_first_cwd_decide(self):
        long_path = "/work/demo/" + "x" * 250
        prefix = transcripts.sanitize(long_path)
        self.assertEqual(200, len(prefix))
        right = rec("2026-10-30T15:00:00Z", folder=prefix + "-k3j9x2", cwd=long_path)
        wrong_cwd = rec("2026-10-30T15:00:01Z", folder=prefix + "-q1w2e3", cwd=long_path + "/sub")
        no_dash = rec("2026-10-30T15:00:02Z", folder=prefix + "z", cwd=long_path)
        project = [{"key": "k", "name": "K", "path": "/p"}]
        with mock.patch.object(transcripts.os.path, "realpath", return_value=long_path):
            self.assertEqual({"k": prefix + "-k3j9x2"}, transcripts.project_folders(project, [wrong_cwd, no_dash, right]))
            self.assertEqual({"k": None}, transcripts.project_folders(project, [wrong_cwd, no_dash]))
            # Only the first cwd seen in a folder counts.
            later = rec("2026-10-30T15:00:03Z", folder=prefix + "-q1w2e3", cwd=long_path)
            self.assertEqual({"k": None}, transcripts.project_folders(project, [wrong_cwd, later]))

    def test_the_result_feeds_build_views(self):
        root = self.tmpdir()
        real = os.path.join(root, "app")
        os.makedirs(real)
        folder = transcripts.sanitize(real)
        rows = [rec("2026-10-30T15:00:00Z", output=7, folder=folder, cwd=real),
                rec("2026-10-30T15:00:01Z", output=3, folder="-work-elsewhere", cwd="/work/elsewhere", session_id="s2")]
        found = transcripts.project_folders([{"key": "k", "name": "App", "path": real}], rows)
        projects = [{"key": "k", "name": "App", "folder": found["k"]}]
        out = views(rows, scope="k", projects=projects)
        self.assertEqual(7, out["today"]["totals"]["tokens"])
        everything = views(rows, scope="all", projects=projects)["today"]["by_project"]
        self.assertEqual([("App", True), ("elsewhere", False)], [(p["name"], p["listed"]) for p in everything])


# ---------------------------------------------------------------- Tidewater demo check

class TestDemoSet(unittest.TestCase):
    """The usage views on the built demo set, against the README and the truth file."""

    # Figures from tests/fixtures/demo/README.md, Tidewater reporting, default arguments.
    README = {"input": 5987439, "output": 3317776, "cache_read": 89076369,
              "cache_write_5m": 17040156, "cache_write_1h": 1827034, "thinking": 999663,
              "requests": 3259, "runs": 190, "sessions": 53}
    README_COST = 319.61503237
    NAMES = ("Tidewater reporting", "Driftwood", "Harbor Light")
    EMPTY = ("Saltmarsh", "Lantern")

    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix="d-", dir=helpers._tmp_base()))
        out = os.path.join(cls.tmp, "set")
        cls.truth = build_demo.build(out)
        now = datetime.datetime.strptime(cls.truth["window"]["end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        tz = zoneinfo.ZoneInfo(cls.truth["window"]["tz"])
        result = transcripts.Reader(os.path.join(out, "config")).read(now)
        with open(os.path.join(out, "config", "routing-dashboard.json"), encoding="utf-8") as fh:
            listed = json.load(fh)["projects"]
        projects = [{"key": p["name"], "name": p["name"], "path": p["path"]} for p in listed]
        folders = transcripts.project_folders(projects, result.records)
        shown = [{"key": p["key"], "name": p["name"], "folder": folders[p["key"]]} for p in projects]
        cls.totals = {}
        for name in cls.NAMES:
            built = usage.build_views(result.records, name, now, tz, PRICES, CATALOG, result.oldest_by_folder,
                                      projects=shown)
            cls.totals[name] = built["30d"]["totals"]
        cls.previous = {}
        for name in cls.EMPTY:
            built = usage.build_views(result.records, name, now, tz, PRICES, CATALOG, result.oldest_by_folder,
                                      projects=shown)
            cls.previous[name] = dict((r, built[r]["previous"]) for r in ("today", "7d", "30d"))

    @classmethod
    def tearDownClass(cls):
        helpers.rmtree_force(cls.tmp)

    def test_tidewater_matches_the_readme(self):
        got = self.totals["Tidewater reporting"]
        for field, want in self.README.items():
            self.assertEqual(want, got[field], field)
        self.assertAlmostEqual(self.README_COST, got["cost"], places=6)
        self.assertEqual(0, got["unpriced_requests"])

    def test_saltmarsh_and_lantern_have_no_previous_on_any_range(self):
        for name in self.EMPTY:
            self.assertEqual({"today": None, "7d": None, "30d": None}, self.previous[name], name)

    def test_every_listed_project_matches_the_truth(self):
        for name in self.NAMES:
            got = self.totals[name]
            want = self.truth["projects"][name]
            for field in ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h",
                          "thinking", "requests", "runs", "sessions", "unpriced_requests"):
                self.assertEqual(want[field], got[field], (name, field))
            self.assertAlmostEqual(want["cost"], got["cost"], places=6, msg=name)
        self.assertGreater(self.totals["Driftwood"]["unpriced_requests"], 0)
        self.assertEqual(0, self.totals["Harbor Light"]["unpriced_requests"])


if __name__ == "__main__":
    unittest.main()

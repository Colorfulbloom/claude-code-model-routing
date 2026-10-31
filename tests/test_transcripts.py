"""Tests for the transcript reader (dashboard/transcripts.py).

Every run reads only its own throwaway folders and the hand-written fixtures in
tests/fixtures/transcripts. All content is made up. Nothing here reads the real
~/.claude. Fixture cases are copied to a temp dir first, because git keeps no
modified times and the reader looks at them.
"""
import builtins
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import prices as prices_mod  # noqa: E402
import resolve  # noqa: E402
import transcripts  # noqa: E402

CASES = os.path.join(helpers.FIXTURES, "transcripts")
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)
DAY = 86400
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
FOLDER = "-work-demo-app"
MARKER = "PLANTED-MARKER-7f3a"

CASE_NAMES = [
    "cache-split-missing", "cache-split-smaller", "dated-and-1m-model-names",
    "dst-change-new-york", "duplicate-ids-growing-output", "file-older-than-horizon",
    "haiku-over-100k", "id-across-main-and-subagent", "ignored-files",
    "long-folder-name", "malformed-line", "non-assistant-rows", "partial-last-line",
    "set-aside-repeat-and-add", "set-aside-row-without-id", "speed-tier-thinking",
    "subagent-meta-marker", "subagent-missing-meta", "synthetic-row",
    "timestamp-forms", "unknown-model",
]
RECORD_FIELDS = (
    "message_id request_id ts_utc folder session_id run_id agent_type model_raw effort "
    "cwd git_branch is_sidechain input output cache_read cache_write_5m cache_write_1h "
    "thinking speed service_tier inference_geo"
).split()


def row_line(mid, rid, ts, out=50, model="claude-opus-5-5", sid=S1, content=None, usage=None, side=False):
    row = {
        "type": "assistant", "timestamp": ts, "cwd": "/work/demo/app", "sessionId": sid,
        "gitBranch": "main", "isSidechain": side, "effort": "high", "requestId": rid,
        "message": {
            "id": mid, "model": model, "role": "assistant",
            "usage": usage or {"input_tokens": 10, "output_tokens": out, "cache_read_input_tokens": 0},
            "content": content or [{"type": "text", "text": "hello"}],
        },
    }
    if sid is None:
        del row["sessionId"]
    if side is None:
        del row["isSidechain"]
    return json.dumps(row)


def write_lines(path, lines, end="\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(lines) + end)


def age(path, days_old):
    ts = (NOW - datetime.timedelta(days=days_old)).timestamp()
    os.utime(path, (ts, ts))


def snapshot(root):
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            state[os.path.relpath(full, root)] = (st.st_size, st.st_mtime_ns, st.st_ino)
    return state


class OpenSpy:
    """Records every builtins.open call made inside the with block."""

    def __init__(self):
        self.calls = []
        self._real = builtins.open

    def __enter__(self):
        spy = self

        def fake(file, mode="r", *args, **kwargs):
            spy.calls.append((os.fspath(file), mode))
            return spy._real(file, mode, *args, **kwargs)

        self._patch = mock.patch("builtins.open", fake)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()


class TmpCase(unittest.TestCase):
    def tmpdir(self):
        path = os.path.realpath(tempfile.mkdtemp(prefix="transcripts-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, path)
        return path

    def config(self):
        cfg = self.tmpdir()
        os.makedirs(os.path.join(cfg, "projects"))
        return cfg

    def main_path(self, cfg, sid=S1, folder=FOLDER):
        return os.path.join(cfg, "projects", folder, sid + ".jsonl")


class FixtureCases(TmpCase):
    def copy_case(self, name):
        cfg = self.tmpdir()
        shutil.copytree(os.path.join(CASES, name, "projects"), os.path.join(cfg, "projects"), symlinks=True)
        with open(os.path.join(CASES, name, "expected.json"), encoding="utf-8") as fh:
            expected = json.load(fh)
        default = (NOW - datetime.timedelta(days=1)).timestamp()
        for dirpath, _, filenames in os.walk(cfg):
            for fname in filenames:
                os.utime(os.path.join(dirpath, fname), (default, default))
        for rel, days in expected.get("mtimes", {}).items():
            age(os.path.join(cfg, "projects", rel), days)
        return cfg, expected

    def test_every_case_is_present(self):
        self.assertEqual(sorted(CASE_NAMES), sorted(os.listdir(CASES)))

    def test_cases_match_expected_json(self):
        for name in CASE_NAMES:
            with self.subTest(case=name):
                cfg, expected = self.copy_case(name)
                with OpenSpy() as spy:
                    result = transcripts.Reader(cfg).read(NOW)
                self.assertEqual(expected["notes"], result.notes)
                self.assertEqual(len(expected["records"]), len(result.records))
                for want, got in zip(expected["records"], result.records):
                    for key, value in want.items():
                        have = got.ts_utc.isoformat() if key == "ts_utc" else getattr(got, key)
                        self.assertEqual(value, have, "%s of %s" % (key, want["message_id"]))
                oldest = result.oldest_seen.isoformat() if result.oldest_seen else None
                self.assertEqual(expected["oldest_seen"], oldest)
                # reads use open(path, "rb") and stay under the projects folder
                root = os.path.join(cfg, "projects") + os.sep
                for path, mode in spy.calls:
                    self.assertEqual("rb", mode)
                    self.assertTrue(path.startswith(root), path)

    def test_records_hold_only_the_listed_fields(self):
        self.assertEqual(tuple(RECORD_FIELDS), transcripts.Record._fields)
        cfg, _ = self.copy_case("speed-tier-thinking")
        for rec in transcripts.Reader(cfg).read(NOW).records:
            self.assertIsInstance(rec, transcripts.Record)
            self.assertEqual(UTC.utcoffset(None), rec.ts_utc.utcoffset())
            for key in ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h"):
                self.assertIs(int, type(getattr(rec, key)))
            self.assertTrue(rec.thinking is None or type(rec.thinking) is int)

    def test_speed_comes_from_usage_speed_only(self):
        cfg, _ = self.copy_case("speed-tier-thinking")
        recs = transcripts.Reader(cfg).read(NOW).records
        self.assertEqual(["fast", "turbo", None, None], [r.speed for r in recs])
        self.assertEqual(["standard", "priority", None, "standard"], [r.service_tier for r in recs])
        self.assertEqual([120, None, None, 0], [r.thinking for r in recs])

    def test_meta_gives_agent_type_only(self):
        cfg, _ = self.copy_case("subagent-meta-marker")
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual([None, "reviewer"], [r.agent_type for r in result.records])
        self.assertNotIn("find", repr(result))


class MarkerTests(TmpCase):
    def test_marker_appears_in_no_record(self):
        cfg = self.config()
        text_row = row_line("msg_1", "req_1", "2026-11-02T10:00:00.000Z",
                            content=[{"type": "text", "text": "reply " + MARKER}])
        tool_row = row_line("msg_2", "req_2", "2026-11-02T10:00:01.000Z", content=[
            {"type": "tool_use", "id": "t1", "name": "Task",
             "input": {"command": "echo " + MARKER, "description": MARKER, "prompt": MARKER}}])
        think_row = row_line("msg_3", "req_3", "2026-11-02T10:00:02.000Z", content=[
            {"type": "thinking", "thinking": MARKER, "signature": MARKER}])
        user_row = json.dumps({"type": "user", "timestamp": "2026-11-02T10:00:03.000Z",
                               "message": {"role": "user", "content": 'the "assistant" said ' + MARKER}})
        write_lines(self.main_path(cfg), [text_row, tool_row, think_row, user_row])
        agent = os.path.join(cfg, "projects", FOLDER, S1, "subagents", "agent-zz9.jsonl")
        write_lines(agent, [row_line("msg_4", "req_4", "2026-11-02T10:00:04.000Z",
                                     content=[{"type": "text", "text": MARKER}])])
        with open(agent[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump({"agentType": "explorer", "description": "find " + MARKER}, fh)
        with open(self.main_path(cfg), "rb") as fh:
            self.assertIn(MARKER.encode(), fh.read())
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(4, len(result.records))
        self.assertNotIn(MARKER, repr(result))
        for rec in result.records:
            self.assertNotIn("PLANTED", repr(rec))
        self.assertEqual("explorer", result.records[-1].agent_type)

    def test_the_cache_keeps_only_the_allowed_fields(self):
        cfg = self.config()
        text_row = row_line("msg_1", "req_1", "2026-11-02T10:00:00.000Z",
                            content=[{"type": "text", "text": "reply " + MARKER}])
        tool_row = row_line("msg_2", "req_2", "2026-11-02T10:00:01.000Z", content=[
            {"type": "tool_use", "id": "t1", "name": "Task",
             "input": {"command": "echo " + MARKER, "description": MARKER, "prompt": MARKER}}])
        think_row = row_line("msg_3", "req_3", "2026-11-02T10:00:02.000Z", content=[
            {"type": "thinking", "thinking": MARKER, "signature": MARKER}])
        result_row = json.dumps({"type": "user", "timestamp": "2026-11-02T10:00:03.000Z", "message": {
            "role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": MARKER}]}})
        write_lines(self.main_path(cfg), [text_row, tool_row, think_row, result_row])
        agent = os.path.join(cfg, "projects", FOLDER, S1, "subagents", "agent-zz9.jsonl")
        write_lines(agent, [row_line("msg_4", "req_4", "2026-11-02T10:00:04.000Z",
                                     content=[{"type": "text", "text": MARKER}])])
        with open(agent[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump({"agentType": "explorer", "description": "find " + MARKER}, fh)
        reader = transcripts.Reader(cfg)
        self.assertEqual(4, len(reader.read(NOW).records))
        self.assertEqual({self.main_path(cfg), agent}, set(reader._cache))
        for path, entry in reader._cache.items():
            with self.subTest(path=os.path.basename(path)):
                # The entry's own bookkeeping, and nothing else.
                self.assertEqual(
                    ("dev", "ino", "size", "mtime_ns", "offset", "records", "stats", "meta_sig", "agent_type"),
                    entry._fields)
                for name in ("dev", "ino", "size", "mtime_ns", "offset"):
                    self.assertIsInstance(getattr(entry, name), int, name)
                self.assertEqual({"malformed", "synthetic", "no_id"}, set(entry.stats))
                self.assertTrue(all(isinstance(v, int) for v in entry.stats.values()))
                self.assertTrue(entry.meta_sig is None or all(isinstance(v, int) for v in entry.meta_sig))
                self.assertTrue(entry.agent_type is None or entry.agent_type == "explorer")
                # Records carry Record's fields and no more.
                self.assertTrue(entry.records)
                for rec in entry.records:
                    self.assertIsInstance(rec, transcripts.Record)
                    self.assertEqual(tuple(RECORD_FIELDS), rec._fields)
        # The planted strings sit in message text, a tool_use input, a thinking block, a tool_result and a meta
        # description. None of it reached the cache, keys and values alike.
        self.assertNotIn(MARKER, repr(reader._cache))
        self.assertNotIn("PLANTED", repr(reader._cache))

    def test_marker_cases_in_fixtures(self):
        for name in ("subagent-meta-marker", "non-assistant-rows"):
            with self.subTest(case=name):
                cfg = self.tmpdir()
                shutil.copytree(os.path.join(CASES, name, "projects"), os.path.join(cfg, "projects"))
                raw = b""
                for dirpath, _, filenames in os.walk(cfg):
                    for fname in filenames:
                        with open(os.path.join(dirpath, fname), "rb") as fh:
                            raw += fh.read()
                self.assertIn(b"PLANTED-MARKER", raw)
                self.assertNotIn("PLANTED", repr(transcripts.Reader(cfg).read(NOW)))


class MetaTests(TmpCase):
    def agent_file(self, cfg):
        path = os.path.join(cfg, "projects", FOLDER, S1, "subagents", "agent-q1.jsonl")
        write_lines(path, [row_line("msg_1", "req_1", "2026-11-02T10:00:00.000Z")])
        return path

    def test_unreadable_or_odd_meta_gives_none(self):
        for content in ('{"agentType": "ex', "[]", '{"agentType": 7}', '{"other": "x"}', "\xff\xfe"):
            with self.subTest(content=content):
                cfg = self.config()
                path = self.agent_file(cfg)
                with open(path[:-len(".jsonl")] + ".meta.json", "w", encoding="latin-1") as fh:
                    fh.write(content)
                self.assertIsNone(transcripts.Reader(cfg).read(NOW).records[0].agent_type)

    def test_meta_that_arrives_later_is_picked_up(self):
        cfg = self.config()
        path = self.agent_file(cfg)
        reader = transcripts.Reader(cfg)
        self.assertIsNone(reader.read(NOW).records[0].agent_type)
        with open(path[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump({"agentType": "scribe"}, fh)
        self.assertEqual("scribe", reader.read(NOW).records[0].agent_type)

    def test_main_file_rows_have_no_agent_type_or_run_id(self):
        cfg = self.config()
        write_lines(self.main_path(cfg), [row_line("msg_1", "req_1", "2026-11-02T10:00:00.000Z")])
        rec = transcripts.Reader(cfg).read(NOW).records[0]
        self.assertIsNone(rec.agent_type)
        self.assertIsNone(rec.run_id)
        self.assertEqual(S1, rec.session_id)

    def test_session_id_falls_back_to_folder_name_for_subagent(self):
        cfg = self.config()
        path = os.path.join(cfg, "projects", FOLDER, S2, "subagents", "agent-q2.jsonl")
        write_lines(path, [row_line("msg_1", "req_1", "2026-11-02T10:00:00.000Z", sid=None, side=None)])
        rec = transcripts.Reader(cfg).read(NOW).records[0]
        self.assertEqual(S2, rec.session_id)
        self.assertEqual("q2", rec.run_id)
        self.assertTrue(rec.is_sidechain)  # no isSidechain on the row: a subagent file is a side chain


class ScanTests(TmpCase):
    def test_missing_projects_dir_gives_empty_result(self):
        result = transcripts.Reader(self.tmpdir()).read(NOW)
        self.assertEqual([], result.records)
        self.assertIsNone(result.oldest_seen)
        self.assertEqual(
            {"malformed_lines": 0, "synthetic_rows": 0, "no_id_rows": 0, "ignored_files": 0, "skipped_old_files": 0},
            result.notes)

    def test_records_come_in_sorted_path_order_with_file_order_inside(self):
        cfg = self.config()
        write_lines(self.main_path(cfg, folder="-b-proj"), [
            row_line("m_b1", "r_b1", "2026-11-02T10:00:09.000Z"),
            row_line("m_b2", "r_b2", "2026-11-02T10:00:01.000Z")])
        write_lines(self.main_path(cfg, folder="-a-proj", sid=S2), [
            row_line("m_a1", "r_a1", "2026-11-02T10:00:05.000Z", sid=S2)])
        write_lines(self.main_path(cfg, folder="-a-proj"), [
            row_line("m_a2", "r_a2", "2026-11-02T10:00:07.000Z")])
        reader = transcripts.Reader(cfg)
        first = [r.message_id for r in reader.read(NOW).records]
        self.assertEqual(["m_a2", "m_a1", "m_b1", "m_b2"], first)
        self.assertEqual(first, [r.message_id for r in reader.read(NOW).records])

    def test_horizon_edges(self):
        cfg = self.config()
        keep = self.main_path(cfg, S1)
        drop = self.main_path(cfg, S2)
        write_lines(keep, [row_line("m1", "r1", "2026-11-02T10:00:00.000Z")])
        write_lines(drop, [row_line("m2", "r2", "2026-09-01T10:00:00.000Z", sid=S2)])
        age(keep, 61)
        ts = (NOW - datetime.timedelta(days=61, seconds=1)).timestamp()
        os.utime(drop, (ts, ts))
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(["m1"], [r.message_id for r in result.records])
        self.assertEqual(1, result.notes["skipped_old_files"])
        self.assertEqual(datetime.datetime.fromtimestamp(ts, UTC), result.oldest_seen)
        # a shorter horizon drops the other file too
        short = transcripts.Reader(cfg, horizon_days=10).read(NOW)
        self.assertEqual([], short.records)
        self.assertEqual(2, short.notes["skipped_old_files"])
        self.assertEqual(datetime.datetime.fromtimestamp(ts, UTC), short.oldest_seen)

    def test_oldest_seen_is_the_earlier_of_record_and_skipped_file(self):
        cfg = self.config()
        keep = self.main_path(cfg, S1)
        drop = self.main_path(cfg, S2)
        write_lines(keep, [row_line("m1", "r1", "2026-06-01T10:00:00.000Z")])
        write_lines(drop, [row_line("m2", "r2", "2026-07-01T10:00:00.000Z", sid=S2)])
        age(keep, 1)
        age(drop, 70)
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(datetime.datetime(2026, 6, 1, 10, 0, tzinfo=UTC), result.oldest_seen)

    def test_oldest_by_folder_has_one_value_per_folder_with_data(self):
        cfg = self.config()
        write_lines(self.main_path(cfg, S1, folder="-a-proj"), [
            row_line("m1", "r1", "2026-10-01T10:00:00.000Z"),
            row_line("m2", "r2", "2026-10-05T10:00:00.000Z")])
        write_lines(self.main_path(cfg, S2, folder="-b-proj"), [
            row_line("m3", "r3", "2026-10-03T10:00:00.000Z", sid=S2)])
        for folder, sid in (("-a-proj", S1), ("-b-proj", S2)):
            age(self.main_path(cfg, sid, folder=folder), 1)
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual({"-a-proj": datetime.datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
                          "-b-proj": datetime.datetime(2026, 10, 3, 10, 0, tzinfo=UTC)},
                         result.oldest_by_folder)
        self.assertEqual(datetime.datetime(2026, 10, 1, 10, 0, tzinfo=UTC), result.oldest_seen)

    def test_oldest_by_folder_counts_a_skipped_file_only_in_its_own_folder(self):
        cfg = self.config()
        keep_a = self.main_path(cfg, S1, folder="-a-proj")
        drop_a = self.main_path(cfg, S2, folder="-a-proj")
        keep_b = self.main_path(cfg, S1, folder="-b-proj")
        write_lines(keep_a, [row_line("m1", "r1", "2026-10-10T10:00:00.000Z")])
        write_lines(drop_a, [row_line("m2", "r2", "2026-06-01T10:00:00.000Z", sid=S2)])
        write_lines(keep_b, [row_line("m3", "r3", "2026-10-20T10:00:00.000Z")])
        age(keep_a, 1)
        age(keep_b, 1)
        ts = (NOW - datetime.timedelta(days=70)).timestamp()
        os.utime(drop_a, (ts, ts))
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(1, result.notes["skipped_old_files"])
        self.assertEqual({"-a-proj": datetime.datetime.fromtimestamp(ts, UTC),
                          "-b-proj": datetime.datetime(2026, 10, 20, 10, 0, tzinfo=UTC)},
                         result.oldest_by_folder)
        self.assertEqual(datetime.datetime.fromtimestamp(ts, UTC), result.oldest_seen)

    def test_oldest_by_folder_has_a_key_for_a_folder_with_only_a_skipped_file(self):
        cfg = self.config()
        drop = self.main_path(cfg, S1, folder="-old-proj")
        write_lines(drop, [row_line("m1", "r1", "2026-06-01T10:00:00.000Z")])
        ts = (NOW - datetime.timedelta(days=70)).timestamp()
        os.utime(drop, (ts, ts))
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual([], result.records)
        self.assertEqual({"-old-proj": datetime.datetime.fromtimestamp(ts, UTC)}, result.oldest_by_folder)

    def test_oldest_by_folder_is_empty_with_nothing_to_read(self):
        result = transcripts.Reader(self.config()).read(NOW)
        self.assertEqual({}, result.oldest_by_folder)

    def test_a_modifier_that_is_not_a_string_is_kept_as_text_and_has_no_price(self):
        cfg = self.config()
        usage = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0, "speed": 7}
        write_lines(self.main_path(cfg), [
            row_line("m1", "r1", "2026-11-02T10:00:00.000Z", usage=usage),
            row_line("m2", "r2", "2026-11-02T10:00:01.000Z")])
        age(self.main_path(cfg), 1)
        first, second = transcripts.Reader(cfg).read(NOW).records
        self.assertEqual("7", first.speed)
        self.assertIsNone(second.speed)    # a missing value stays None and prices as standard
        prices = prices_mod.load_prices()
        catalog = resolve.load_rules()["models"]
        self.assertIsNone(prices_mod.price(first, prices, catalog))
        self.assertIsNotNone(prices_mod.price(second, prices, catalog))

    def test_naive_now_is_taken_as_utc(self):
        cfg = self.config()
        write_lines(self.main_path(cfg), [row_line("m1", "r1", "2026-11-02T10:00:00.000Z")])
        age(self.main_path(cfg), 1)
        self.assertEqual(1, len(transcripts.Reader(cfg).read(NOW.replace(tzinfo=None)).records))

    def test_symlinks_are_skipped_and_never_read(self):
        cfg = self.config()
        outside = self.tmpdir()
        line = row_line("m_out", "r_out", "2026-11-02T10:00:00.000Z")
        write_lines(os.path.join(outside, "secret.jsonl"), [line])
        write_lines(os.path.join(outside, "dir", S2 + ".jsonl"), [line])
        write_lines(os.path.join(outside, "subagents", "agent-s1.jsonl"), [line])
        with open(os.path.join(outside, "agent-m1.meta.json"), "w", encoding="utf-8") as fh:
            json.dump({"agentType": "evil"}, fh)
        real = self.main_path(cfg)
        write_lines(real, [row_line("m_in", "r_in", "2026-11-02T10:00:01.000Z")])
        os.symlink(os.path.join(outside, "secret.jsonl"), self.main_path(cfg, S2))       # file link
        os.symlink(os.path.join(outside, "dir"), os.path.join(cfg, "projects", "-linked"))  # folder link
        os.makedirs(os.path.join(cfg, "projects", FOLDER, S2))
        os.symlink(os.path.join(outside, "subagents"), os.path.join(cfg, "projects", FOLDER, S2, "subagents"))
        agent = os.path.join(cfg, "projects", FOLDER, S1, "subagents", "agent-m1.jsonl")
        write_lines(agent, [row_line("m_ag", "r_ag", "2026-11-02T10:00:02.000Z")])
        os.symlink(os.path.join(outside, "agent-m1.meta.json"), agent[:-len(".jsonl")] + ".meta.json")
        for dirpath, _, filenames in os.walk(cfg):
            for fname in filenames:
                if not os.path.islink(os.path.join(dirpath, fname)):
                    age(os.path.join(dirpath, fname), 1)
        with OpenSpy() as spy:
            result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(["m_in", "m_ag"], [r.message_id for r in result.records])
        self.assertIsNone(result.records[1].agent_type)
        # file link, folder link, subagents link, meta link
        self.assertEqual(4, result.notes["ignored_files"])
        for path, _ in spy.calls:
            self.assertTrue(path.startswith(os.path.join(cfg, "projects") + os.sep), path)

    def test_cache_drops_files_that_vanished(self):
        cfg = self.config()
        one, two = self.main_path(cfg, S1), self.main_path(cfg, S2)
        write_lines(one, [row_line("m1", "r1", "2026-11-02T10:00:00.000Z")])
        write_lines(two, [row_line("m2", "r2", "2026-11-02T10:00:01.000Z", sid=S2)])
        reader = transcripts.Reader(cfg)
        self.assertEqual(2, len(reader.read(NOW).records))
        self.assertEqual({one, two}, set(reader._cache))
        os.remove(two)
        result = reader.read(NOW)
        self.assertEqual(["m1"], [r.message_id for r in result.records])
        self.assertEqual({one}, set(reader._cache))


class UnreadableTests(TmpCase):
    def failing_listing(self, bad):
        real = transcripts._listdir_checked
        return mock.patch.object(transcripts, "_listdir_checked", lambda path: None if path in bad else real(path))

    def test_a_folder_that_cannot_be_listed_is_unreadable_and_the_others_still_read(self):
        cfg = self.config()
        write_lines(self.main_path(cfg), [row_line("m1", "r1", "2026-11-02T10:00:00.000Z")])
        write_lines(self.main_path(cfg, S2, "-work-other"), [row_line("m2", "r2", "2026-11-02T10:00:01.000Z", sid=S2)])
        with self.failing_listing({os.path.join(cfg, "projects", "-work-other")}):
            result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(frozenset({"-work-other"}), result.unreadable)
        self.assertIs(False, result.top_unreadable)
        self.assertEqual(["m1"], [r.message_id for r in result.records])

    def test_a_top_folder_that_cannot_be_listed_is_flagged(self):
        cfg = self.config()
        write_lines(self.main_path(cfg), [row_line("m1", "r1", "2026-11-02T10:00:00.000Z")])
        with self.failing_listing({os.path.join(cfg, "projects")}):
            result = transcripts.Reader(cfg).read(NOW)
        self.assertIs(True, result.top_unreadable)
        self.assertEqual([], result.records)

    def test_a_folder_whose_files_all_fail_to_open_is_unreadable(self):
        cfg = self.config()
        write_lines(self.main_path(cfg), [row_line("m1", "r1", "2026-11-02T10:00:00.000Z")])
        write_lines(self.main_path(cfg, S2), [row_line("m2", "r2", "2026-11-02T10:00:01.000Z", sid=S2)])
        write_lines(self.main_path(cfg, S1, "-work-ok"), [row_line("m3", "r3", "2026-11-02T10:00:02.000Z")])
        real = open

        def fake(file, mode="r", *args, **kwargs):
            if os.fspath(file).startswith(os.path.join(cfg, "projects", FOLDER) + os.sep):
                raise PermissionError(13, "denied")
            return real(file, mode, *args, **kwargs)

        with mock.patch("builtins.open", fake):
            result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(frozenset({FOLDER}), result.unreadable)
        self.assertEqual(["m3"], [r.message_id for r in result.records])

    def test_a_folder_with_one_good_file_is_not_unreadable(self):
        cfg = self.config()
        bad = self.main_path(cfg, S2)
        write_lines(self.main_path(cfg), [row_line("m1", "r1", "2026-11-02T10:00:00.000Z")])
        write_lines(bad, [row_line("m2", "r2", "2026-11-02T10:00:01.000Z", sid=S2)])
        real = open

        def fake(file, mode="r", *args, **kwargs):
            if os.fspath(file) == bad:
                raise PermissionError(13, "denied")
            return real(file, mode, *args, **kwargs)

        with mock.patch("builtins.open", fake):
            result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(frozenset(), result.unreadable)
        self.assertEqual(["m1"], [r.message_id for r in result.records])

    def test_a_folder_with_no_files_and_a_missing_projects_folder_stay_readable(self):
        cfg = self.config()
        os.makedirs(os.path.join(cfg, "projects", "-empty"))
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(frozenset(), result.unreadable)
        self.assertIs(False, result.top_unreadable)

    def test_a_folder_of_old_files_is_not_unreadable(self):
        cfg = self.config()
        path = self.main_path(cfg)
        write_lines(path, [row_line("m1", "r1", "2026-01-02T10:00:00.000Z")])
        age(path, 200)
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(frozenset(), result.unreadable)

    def test_unreadable_folder_matches_a_short_path_exactly_and_a_long_one_by_prefix(self):
        self.assertEqual("-work-demo-app", transcripts.unreadable_folder("/work/demo/app", {"-work-demo-app", "-x"}))
        self.assertIsNone(transcripts.unreadable_folder("/work/demo/app", {"-work-demo-app-2"}))
        long_path = "/" + "a" * 250
        full = transcripts.sanitize(long_path)
        self.assertEqual(full + "-hash", transcripts.unreadable_folder(long_path, {"-b", full + "-hash"}))
        self.assertIsNone(transcripts.unreadable_folder(long_path, {full}))


class CacheTests(TmpCase):
    def setUp(self):
        self.cfg = self.config()
        self.path = self.main_path(self.cfg)
        write_lines(self.path, [row_line("m1", "r1", "2026-11-02T10:00:00.000Z", out=10),
                                row_line("m2", "r2", "2026-11-02T10:00:01.000Z", out=20)])
        age(self.path, 1)
        self.reader = transcripts.Reader(self.cfg)

    def counted_read(self):
        real = json.loads
        calls = []

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        with mock.patch.object(transcripts.json, "loads", counting), OpenSpy() as spy:
            result = self.reader.read(NOW)
        return result, len(calls), spy.calls

    def test_same_key_reuses_records_without_opening_the_file(self):
        first, parsed, _ = self.counted_read()
        self.assertEqual(2, parsed)
        again, parsed, opens = self.counted_read()
        self.assertEqual(0, parsed)
        self.assertEqual([], opens)
        self.assertEqual(first.records, again.records)

    def test_grown_file_parses_from_the_stored_offset_only(self):
        self.counted_read()
        inode = os.stat(self.path).st_ino
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(row_line("m3", "r3", "2026-11-02T10:00:02.000Z", out=30) + "\n")
        result, parsed, _ = self.counted_read()
        self.assertEqual(inode, os.stat(self.path).st_ino)
        self.assertEqual(1, parsed)
        self.assertEqual(["m1", "m2", "m3"], [r.message_id for r in result.records])
        self.assertEqual([10, 20, 30], [r.output for r in result.records])

    def test_new_inode_parses_again(self):
        self.counted_read()
        tmp = self.path + ".new"
        write_lines(tmp, [row_line("n1", "q1", "2026-11-02T11:00:00.000Z"),
                          row_line("n2", "q2", "2026-11-02T11:00:01.000Z"),
                          row_line("n3", "q3", "2026-11-02T11:00:02.000Z")])
        os.replace(tmp, self.path)
        result, parsed, _ = self.counted_read()
        self.assertEqual(3, parsed)
        self.assertEqual(["n1", "n2", "n3"], [r.message_id for r in result.records])

    def test_shorter_file_with_the_same_inode_parses_again(self):
        self.counted_read()
        inode = os.stat(self.path).st_ino
        write_lines(self.path, [row_line("s1", "t1", "2026-11-02T12:00:00.000Z")])
        self.assertEqual(inode, os.stat(self.path).st_ino)
        result, parsed, _ = self.counted_read()
        self.assertEqual(1, parsed)
        self.assertEqual(["s1"], [r.message_id for r in result.records])

    def test_same_size_with_new_mtime_parses_again(self):
        self.counted_read()
        with open(self.path, "rb") as fh:
            data = fh.read()
        with open(self.path, "wb") as fh:
            fh.write(data.replace(b"m1", b"x1"))
        os.utime(self.path, (NOW.timestamp(), NOW.timestamp() - 5))
        result, parsed, _ = self.counted_read()
        self.assertEqual(2, parsed)
        self.assertEqual(["x1", "m2"], [r.message_id for r in result.records])

    def test_partial_last_line_then_completion(self):
        full = row_line("m3", "r3", "2026-11-02T10:00:02.000Z", out=30)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(full[:70])
        with open(self.path, "rb") as fh:
            before = len(fh.read()) - 70
        result = self.reader.read(NOW)
        self.assertEqual(["m1", "m2"], [r.message_id for r in result.records])
        self.assertEqual(0, result.notes["malformed_lines"])
        self.assertEqual(before, self.reader._cache[self.path].offset)
        # more of the line arrives, still no newline
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(full[70:-5])
        result = self.reader.read(NOW)
        self.assertEqual(2, len(result.records))
        self.assertEqual(0, result.notes["malformed_lines"])
        self.assertEqual(before, self.reader._cache[self.path].offset)
        # the line completes
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(full[-5:] + "\n")
        result = self.reader.read(NOW)
        self.assertEqual(["m1", "m2", "m3"], [r.message_id for r in result.records])
        self.assertEqual(0, result.notes["malformed_lines"])
        self.assertEqual(os.path.getsize(self.path), self.reader._cache[self.path].offset)

    def test_counts_survive_an_incremental_read(self):
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("not json but \"assistant\"\n")
        self.assertEqual(1, self.reader.read(NOW).notes["malformed_lines"])
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(row_line("m3", "r3", "2026-11-02T10:00:02.000Z", model="<synthetic>") + "\n")
        result = self.reader.read(NOW)
        self.assertEqual(1, result.notes["malformed_lines"])
        self.assertEqual(1, result.notes["synthetic_rows"])
        self.assertEqual(2, len(result.records))

    def test_a_second_read_waits_for_the_first(self):
        started, release, calls = threading.Event(), threading.Event(), []
        real = json.loads

        def slow(*args, **kwargs):
            calls.append(1)
            started.set()
            release.wait(5)
            return real(*args, **kwargs)

        results = {}
        first = threading.Thread(target=lambda: results.update(a=self.reader.read(NOW)))
        second = threading.Thread(target=lambda: results.update(b=self.reader.read(NOW)))
        with mock.patch.object(transcripts.json, "loads", slow):
            first.start()
            self.assertTrue(started.wait(5))
            second.start()
            second.join(0.3)
            self.assertTrue(second.is_alive(), "the second read should wait on the lock")
            release.set()
            first.join(5)
            second.join(5)
        self.assertEqual(2, len(calls))  # two lines, parsed once
        self.assertEqual(results["a"].records, results["b"].records)


class NoWriteTests(TmpCase):
    def test_a_read_adds_or_changes_nothing_under_the_config_dir(self):
        cfg = self.config()
        write_lines(self.main_path(cfg), [row_line("m1", "r1", "2026-11-02T10:00:00.000Z")])
        agent = os.path.join(cfg, "projects", FOLDER, S1, "subagents", "agent-w1.jsonl")
        write_lines(agent, [row_line("m2", "r2", "2026-11-02T10:00:01.000Z")])
        with open(agent[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump({"agentType": "scribe"}, fh)
        before = snapshot(cfg)
        reader = transcripts.Reader(cfg)
        with OpenSpy() as spy:
            reader.read(NOW)
            reader.read(NOW)
        self.assertEqual(before, snapshot(cfg))
        self.assertTrue(spy.calls)
        self.assertEqual({"rb"}, {mode for _, mode in spy.calls})

    def test_module_source_has_no_write_calls(self):
        with open(transcripts.__file__.replace(".pyc", ".py"), encoding="utf-8") as fh:
            source = fh.read()
        opens = re.findall(r"\bopen\([^)]*\)", source)
        self.assertTrue(opens)
        for call in opens:
            self.assertIn('"rb"', call)
        for banned in (r"\.write\(", r"\.writelines\(", r"os\.(remove|unlink|rename|replace|mkdir|makedirs|rmdir|utime|chmod|symlink|link|truncate)\b",
                       r"\bshutil\b", r"\btempfile\b", r"\bpathlib\b", r"\bio\.open\b", r"\bsubprocess\b"):
            self.assertIsNone(re.search(banned, source), banned)

    def test_module_imports_the_standard_library_only(self):
        with open(transcripts.__file__.replace(".pyc", ".py"), encoding="utf-8") as fh:
            names = re.findall(r"^(?:import|from)\s+(\w+)", fh.read(), re.M)
        self.assertEqual({"collections", "datetime", "json", "os", "re", "stat", "threading"}, set(names))


SANITIZE_SAMPLES = [
    ("/work/demo/project", "-work-demo-project"),
    ("/work/demo/my project", "-work-demo-my-project"),
    ("/work/jane.doe/app", "-work-jane-doe-app"),
    ("/Volumes/Warehouse/Projects/claude-code-model-routing", "-Volumes-Warehouse-Projects-claude-code-model-routing"),
    ("/work/demo/.claude/worktrees/agent-a1", "-work-demo--claude-worktrees-agent-a1"),
    ("/work/demo/caf\u00e9", "-work-demo-caf-"),
    ("/work/demo/\u65e5\u672c\u8a9e", "-work-demo----"),
    ("/work/demo/emoji\U0001F600", "-work-demo-emoji--"),
    ("", ""),
    ("/", "-"),
    ("C:\\Users\\demo", "C--Users-demo"),
    ("/tmp/a_b", "-tmp-a-b"),
    ("/work/demo/proj (copy)", "-work-demo-proj--copy-"),
    ("/work/Demo/CamelCase123", "-work-Demo-CamelCase123"),
    ("/a//b", "-a--b"),
    ("/work/demo/\u00fcn\u00ef", "-work-demo--n-"),
    ("~/x", "--x"),
    ("/work/demo/a+b=c", "-work-demo-a-b-c"),
    ("/" + "a" * 250, "-" + "a" * 199),
    ("/" + "\U0001F600" * 60, "-" * 121),
    ("a" * 199 + "\U0001F600", "a" * 199 + "-"),
    ("a" * 200, "a" * 200),
    ("a" * 201, "a" * 200),
]


class SanitizeTests(TmpCase):
    def test_samples_follow_the_rule(self):
        self.assertGreaterEqual(len(SANITIZE_SAMPLES), 20)
        for path, want in SANITIZE_SAMPLES:
            with self.subTest(path=path[:40]):
                self.assertEqual(want, transcripts.sanitize(path))

    def test_never_longer_than_200_units(self):
        for path in ("a" * 500, "\U0001F600" * 300, "/x" * 400):
            utf16 = transcripts.sanitize(path).encode("utf-16-le")
            self.assertLessEqual(len(utf16) // 2, 200)

    def test_folder_matches_the_real_path(self):
        root = self.tmpdir()
        real = os.path.join(root, "my project")
        os.makedirs(real)
        link = os.path.join(root, "link")
        os.symlink(real, link)
        folder = re.sub(r"[^a-zA-Z0-9]", "-", real)
        self.assertTrue(transcripts.folder_matches(real, folder))
        self.assertTrue(transcripts.folder_matches(link, folder))  # realpath happens here
        self.assertFalse(transcripts.folder_matches(link, re.sub(r"[^a-zA-Z0-9]", "-", link)))
        self.assertFalse(transcripts.folder_matches(real, folder + "-extra"))
        self.assertFalse(transcripts.folder_matches(real, "-work-someone-else"))

    def test_folder_over_200_units_needs_prefix_dash_and_first_cwd(self):
        long_path = "/work/demo/" + "x" * 250
        prefix = re.sub(r"[^a-zA-Z0-9]", "-", long_path)[:200]
        with mock.patch.object(transcripts.os.path, "realpath", return_value=long_path):
            self.assertTrue(transcripts.folder_matches("/p", prefix + "-k3j9x2", long_path))
            self.assertFalse(transcripts.folder_matches("/p", prefix + "-k3j9x2"))
            self.assertFalse(transcripts.folder_matches("/p", prefix + "-k3j9x2", long_path + "/sub"))
            self.assertFalse(transcripts.folder_matches("/p", prefix, long_path))
            self.assertFalse(transcripts.folder_matches("/p", prefix + "x", long_path))
            self.assertFalse(transcripts.folder_matches("/p", "-work-demo-other-k3j9x2", long_path))

    def test_exactly_200_units_must_match_exactly(self):
        path = "/" + "y" * 199
        with mock.patch.object(transcripts.os.path, "realpath", return_value=path):
            self.assertTrue(transcripts.folder_matches("/p", "-" + "y" * 199))
            self.assertFalse(transcripts.folder_matches("/p", "-" + "y" * 199 + "-k3j9x2", path))


if __name__ == "__main__":
    unittest.main()

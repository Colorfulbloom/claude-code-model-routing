"""Tests for the transcript ingest: rules, resume, safety and progress."""

import json
import os
import shutil
import sqlite3
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
import port_helpers
from ingest_helpers import Config, Store

import history
import ingest
import transcripts


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(tmp_path)


@pytest.fixture
def st(tmp_path: Path, config: Config) -> Iterator[Store]:
    s = Store(tmp_path, config)
    yield s
    s.close()


def _keys(st: Store, path: Path) -> set[str]:
    rows = st.rows(
        "SELECT key FROM requests JOIN files ON files.id = file_id WHERE path = ?",
        str(path),
    )
    return {str(r[0]) for r in rows}


def test_cold_pass_matches_the_old_reader(config: Config, st: Store) -> None:
    config.write(
        config.main(h.S1),
        [h.assistant(i, f"m{i}", out=10 + i) for i in range(5)]
        + [h.assistant(2, "m2", out=99)],
    )
    config.write(config.main(h.S2), [h.assistant(9, "x1", sid=h.S2, model="other")])
    result = st.run("full")
    assert result.files_read == 2
    assert result.changed
    assert h.store_totals(st.conn) == h.oracle_totals(config.dir)
    assert st.one("SELECT COUNT(*) FROM sessions") == 2
    assert st.one("SELECT first_ts FROM sessions WHERE session_id = ?", h.S1) == (
        "2026-11-01T12:00:00.000000Z"
    )
    assert (
        st.one("SELECT cwd FROM sessions WHERE session_id = ?", h.S1)
        == "/work/demo/app"
    )
    assert st.one("SELECT folder FROM sessions WHERE session_id = ?", h.S1) == h.FOLDER


def test_a_pass_with_no_change_reads_nothing(config: Config, st: Store) -> None:
    config.write(config.main(), [h.assistant(0, "m0")])
    st.run("full")
    again = st.run()
    assert again.files_read == 0
    assert not again.changed


class TestDedupeRules:
    def test_larger_output_wins_then_later_ts(self, config: Config, st: Store) -> None:
        config.write(
            config.main(),
            [
                h.assistant(5, "m", out=50),
                h.assistant(6, "m", out=20),  # smaller: loses
                h.assistant(7, "n", out=5),
                h.assistant(8, "n", out=5, inp=99),  # equal output, later ts: wins
            ],
        )
        st.run()
        assert st.one("SELECT output FROM requests WHERE key = 'm'") == 50
        assert st.one("SELECT input FROM requests WHERE key = 'n'") == 99

    def test_later_path_wins_a_tie_across_files(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(h.S1), [h.assistant(5, "m", out=9, inp=1)])
        config.write(config.main(h.S2), [h.assistant(5, "m", out=9, inp=2, sid=h.S2)])
        st.run()
        assert st.one("SELECT session_id FROM best_winners WHERE key = 'm'") == h.S2
        assert h.store_totals(st.conn) == h.oracle_totals(config.dir)

    def test_key_is_message_id_then_request_id_then_file_and_offset(
        self, config: Config, st: Store
    ) -> None:
        first = h.assistant(1, None, req="req-1")
        second = h.assistant(2, None)
        third = h.assistant(3, None)
        config.write(
            config.main(), [h.assistant(0, "msg-1", req="req-0"), first, second, third]
        )
        st.run()
        offset = len(h.assistant(0, "msg-1", req="req-0")) + 1 + len(first) + 1
        file_id = st.one("SELECT id FROM files WHERE path = ?", str(config.main()))
        assert _keys(st, config.main()) == {
            "msg-1",
            "r|req-1",
            f"n|{file_id}|{offset}",
            f"n|{file_id}|{offset + len(second) + 1}",
        }
        assert h.store_totals(st.conn) == h.oracle_totals(config.dir)

    def test_records_with_no_id_at_the_same_offset_in_two_files_both_count(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(h.S1), [h.assistant(1, None, out=11)])
        config.write(config.main(h.S2), [h.assistant(1, None, out=22, sid=h.S2)])
        st.run()
        assert st.one("SELECT COUNT(*) FROM best_winners") == 2
        assert st.one("SELECT SUM(output) FROM best_winners") == 33
        assert h.store_totals(st.conn) == h.oracle_totals(config.dir)

    def test_a_rescan_of_a_file_with_no_id_records_adds_no_rows(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(), [h.assistant(1, None), h.assistant(2, None)])
        st.run()
        before = st.one("SELECT COUNT(*) FROM requests")
        config.append(config.main(), [h.assistant(3, None)])
        st.run()
        assert before == 2
        assert st.one("SELECT COUNT(*) FROM requests") == 3

    def test_synthetic_and_bad_timestamp_rows_are_dropped_and_counted(
        self, config: Config, st: Store
    ) -> None:
        bad = json.loads(h.assistant(1, "bad"))
        bad["timestamp"] = "yesterday"
        config.write(
            config.main(),
            [
                h.assistant(0, "ok"),
                h.assistant(1, "syn", model="<synthetic>"),
                json.dumps(bad).encode(),
            ],
        )
        st.run()
        row = st.file_row(config.main())
        assert row["synthetic"] == 1
        assert row["malformed"] == 1
        assert _keys(st, config.main()) == {"ok"}

    def test_orphaned_file_rows_with_no_id_are_dropped_and_counted(
        self, config: Config, st: Store
    ) -> None:
        orphan = (
            config.projects / h.FOLDER / f"{h.S1}.orphaned-20261101T120000Z-ab.jsonl"
        )
        config.write(orphan, [h.assistant(0, None), h.assistant(1, "kept-id")])
        st.run()
        assert st.file_row(orphan)["no_id"] == 1
        assert st.file_row(orphan)["kind"] == "orphaned"
        assert _keys(st, orphan) == {"kept-id"}

    def test_superseded_file_is_read_like_a_main_file(
        self, config: Config, st: Store
    ) -> None:
        old = config.projects / h.FOLDER / f"{h.S1}.jsonl.superseded-20261101T120000Z"
        config.write(old, [h.assistant(0, "shared", out=4)])
        config.write(config.main(), [h.assistant(1, "shared", out=8)])
        st.run()
        assert st.rows("SELECT kind FROM files ORDER BY kind") == [
            ("main",),
            ("superseded",),
        ]
        assert st.one("SELECT output FROM best_winners WHERE key = 'shared'") == 8
        assert h.store_totals(st.conn) == h.oracle_totals(config.dir)


def test_no_usage_rows_are_counted_per_file(config: Config, st: Store) -> None:
    config.write(
        config.main(),
        [
            h.assistant(0, "a"),
            h.assistant(1, "b", usage_obj=False),
            h.assistant(2, "c", usage_obj=False),
        ],
    )
    st.run()
    assert st.file_row(config.main())["no_usage"] == 2
    assert _keys(st, config.main()) == {"a"}
    config.append(config.main(), [h.assistant(3, "d", usage_obj=False)])
    st.run()
    assert st.file_row(config.main())["no_usage"] == 3
    assert history.read_history(st.conn).no_usage_rows == 3


def test_partial_last_line_waits_for_its_newline(config: Config, st: Store) -> None:
    whole = h.assistant(0, "a")
    second = h.assistant(1, "b")
    config.write(config.main(), [whole], end=b"\n")
    config.append(config.main(), [second[:40]], end=b"")
    st.run()
    row = st.file_row(config.main())
    assert row["offset"] == len(whole) + 1
    assert isinstance(row["size"], int)
    assert isinstance(row["offset"], int)
    assert row["size"] > row["offset"]
    assert _keys(st, config.main()) == {"a"}
    assert st.run().files_read == 0  # unchanged: the half line is not read again
    with config.main().open("ab") as fh:
        fh.write(second[40:] + b"\n")
    st.run()
    assert _keys(st, config.main()) == {"a", "b"}
    assert st.file_row(config.main())["offset"] == st.file_row(config.main())["size"]
    assert h.store_totals(st.conn) == h.oracle_totals(config.dir)


class TestLateLinks:
    def test_link_row_before_the_agent_file(self, config: Config, st: Store) -> None:
        config.write(config.main(), [h.assistant(0, "a"), h.link_row(1, "agent-1")])
        st.run()
        assert st.rows("SELECT child_id, session_id, resolved FROM links") == [
            ("agent-1", h.S1, 0)
        ]
        config.write(config.agent("agent-1"), [h.assistant(2, "w1")])
        st.run()
        assert st.rows("SELECT child_id, resolved FROM links") == [("agent-1", 1)]
        assert st.rows("SELECT run_id FROM runs") == [("agent-1",)]

    def test_agent_file_before_the_link_row(self, config: Config, st: Store) -> None:
        config.write(config.main(), [h.assistant(0, "a")])
        config.write(config.agent("agent-1"), [h.assistant(2, "w1")])
        st.run()
        assert st.rows("SELECT * FROM links") == []
        config.append(config.main(), [h.link_row(3, "agent-1")])
        st.run()
        assert st.rows("SELECT child_id, resolved FROM links") == [("agent-1", 1)]

    def test_a_link_for_another_session_stays_unresolved(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(h.S1), [h.link_row(1, "agent-1")])
        config.write(
            config.agent("agent-1", sid=h.S2), [h.assistant(2, "w1", sid=h.S2)]
        )
        st.run()
        assert st.rows("SELECT resolved FROM links") == [(0,)]

    def test_agent_type_comes_from_the_meta_file_even_when_it_is_late(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.agent("a1"), [h.assistant(0, "w1")])
        config.meta("a1", "scribe")
        config.write(config.agent("a2"), [h.assistant(1, "w2")])
        st.run()
        assert st.rows("SELECT run_id, agent_type FROM runs ORDER BY run_id") == [
            ("a1", "scribe"),
            ("a2", None),
        ]
        config.meta("a2", "reviewer")
        st.run()
        assert st.one("SELECT agent_type FROM runs WHERE run_id = 'a2'") == "reviewer"


class TestRescanSafety:
    def test_never_delete_rows_on_rescan(self, config: Config, st: Store) -> None:
        config.write(config.main(), [h.assistant(i, f"m{i}", out=10) for i in range(4)])
        st.run()
        before = st.one("SELECT COUNT(*) FROM requests")
        # a new inode with fewer rows, one of them improved
        tmp = config.main().with_name("replacement")
        config.write(tmp, [h.assistant(0, "m0", out=70)])
        tmp.replace(config.main())
        st.run()
        assert st.one("SELECT COUNT(*) FROM requests") == before
        assert st.one("SELECT output FROM requests WHERE key = 'm0'") == 70
        assert _keys(st, config.main()) == {"m0", "m1", "m2", "m3"}
        assert st.file_row(config.main())["scans"] == 2

    def test_rows_never_lose_a_better_snapshot(self, config: Config, st: Store) -> None:
        config.write(config.main(), [h.assistant(0, "m", out=90)])
        st.run()
        tmp = config.main().with_name("replacement")
        config.write(tmp, [h.assistant(0, "m", out=5)])
        tmp.replace(config.main())
        st.run()
        assert st.one("SELECT output FROM requests WHERE key = 'm'") == 90

    def test_missing_file_keeps_its_rows(self, config: Config, st: Store) -> None:
        config.write(config.main(), [h.assistant(0, "a"), h.assistant(1, "b")])
        config.write(config.main(h.S2), [h.assistant(2, "c", sid=h.S2)])
        st.run()
        totals = h.store_totals(st.conn)
        config.main().unlink()
        st.run()
        assert st.file_row(config.main())["missing"] == 1
        assert h.store_totals(st.conn) == totals
        assert history.read_history(st.conn).kept_files == 1
        # it comes back as a new file: the flag clears and rows stay
        config.write(config.main(), [h.assistant(0, "a"), h.assistant(1, "b")])
        st.run()
        assert st.file_row(config.main())["missing"] == 0
        assert h.store_totals(st.conn) == totals

    def test_a_removed_project_folder_marks_its_files_missing(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(), [h.assistant(0, "a")])
        st.run()
        shutil.rmtree(config.projects / h.FOLDER)
        st.run()
        assert st.file_row(config.main())["missing"] == 1
        assert st.one("SELECT COUNT(*) FROM requests") == 1

    def test_shrink_keeps_rows_counts_shrinks_and_keeps_events(
        self, config: Config, st: Store
    ) -> None:
        lines = [
            h.assistant(0, "a", tools=["Read"]),
            h.assistant(1, "b", stop="end_turn"),  # a stop
            h.brief_row(2, "coordinator"),  # wakes it
            h.assistant(3, "c", stop="end_turn"),  # a second stop
            h.assistant(4, "d"),
        ]
        config.write(config.agent("a1"), lines)
        st.run()
        events_before = st.rows(
            "SELECT kind, at, finished FROM run_events ORDER BY seq"
        )
        assert events_before  # stops and a wake
        total = st.one("SELECT COUNT(*) FROM requests")
        with config.agent("a1").open("r+b") as fh:
            fh.truncate(len(lines[0]) + len(lines[1]) + 2)
        st.run()
        row = st.file_row(config.agent("a1"))
        assert row["shrinks"] == 1
        assert row["scans"] == 2
        assert st.one("SELECT COUNT(*) FROM requests") == total
        events_after = st.rows("SELECT kind, at, finished FROM run_events ORDER BY seq")
        assert events_after[: len(events_before)] == events_before
        assert len(events_after) == len(events_before)  # nothing new, nothing doubled
        # growing again past the old size is caught by the hashes
        config.append(
            config.agent("a1"), [h.assistant(9, "e", out=3) for _ in range(8)]
        )
        st.run()
        assert h.store_totals(st.conn)

    def test_a_new_inode_with_the_same_content_is_read_again_and_changes_nothing(
        self, config: Config, st: Store
    ) -> None:
        lines = [h.assistant(0, "a"), h.link_row(1, "c1"), h.assistant(2, "b")]
        config.write(config.main(), lines)
        st.run()
        totals = h.store_totals(st.conn)
        links = st.rows("SELECT * FROM links")
        tmp = config.main().with_name("replacement")
        config.write(tmp, lines)
        tmp.replace(config.main())
        result = st.run()
        assert result.rescans == 1
        assert h.store_totals(st.conn) == totals
        assert st.rows("SELECT * FROM links") == links
        assert st.one("SELECT COUNT(*) FROM run_events") == 1  # the launch, once

    def test_a_hash_mismatch_triggers_a_rescan(self, config: Config, st: Store) -> None:
        config.write(config.main(), [h.assistant(i, f"m{i}") for i in range(4)])
        st.run()
        data = config.main().read_bytes()
        # same inode, rewritten bytes in place that keep the length, then more rows
        head, tail = data.rsplit(b"main", 1)
        config.main().write_bytes(head + b"maiz" + tail)  # inside the last 64 bytes
        config.append(config.main(), [h.assistant(9, "m9")])
        result = st.run()
        assert result.rescans == 1
        assert _keys(st, config.main()) == {"m0", "m1", "m2", "m3", "m9"}


class TestUnreadableFiles:
    @pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
    def test_unreadable_file_is_counted_then_read_on_a_later_cold_pass(
        self, config: Config, st: Store
    ) -> None:
        path = config.write(config.main(), [h.assistant(0, "a")])
        path.chmod(0)
        try:
            first = st.run("full")
            assert first.files_seen == 1
            assert st.file_row(path)["read_errors"] == 1
            assert history.read_history(st.conn).unreadable_files == 1
            assert st.one("SELECT COUNT(*) FROM requests") == 0
            st.run()  # still unreadable on the next cold pass
            assert st.file_row(path)["read_errors"] == 2
            st.ingestor.run_pass(ingest.PassScope("hot", frozenset({h.FOLDER})))
            assert st.file_row(path)["read_errors"] == 2  # hot passes leave it
        finally:
            path.chmod(0o600)
        result = st.run()
        assert result.files_read == 1
        assert st.file_row(path)["read_errors"] == 0
        assert _keys(st, path) == {"a"}
        assert history.read_history(st.conn).unreadable_files == 0
        assert h.store_totals(st.conn) == h.oracle_totals(config.dir)

    def test_one_unreadable_file_does_not_fail_the_pass(
        self, config: Config, st: Store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        good = config.write(config.main(h.S2), [h.assistant(0, "g", sid=h.S2)])
        bad = config.write(config.main(h.S1), [h.assistant(0, "b")])
        real = transcripts.parse_file

        def flaky(path: str, *args: object, **kw: object) -> transcripts.FileParse:
            if path == str(bad):
                return transcripts.FileParse([], None, {}, transcripts.LinkState(), [])
            return real(path, *args, **kw)  # pyright: ignore[reportArgumentType]

        monkeypatch.setattr(transcripts, "parse_file", flaky)
        st.run()
        assert st.file_row(bad)["read_errors"] == 1
        assert _keys(st, good) == {"g"}


def test_the_projects_folder_errors(tmp_path: Path) -> None:
    missing = Config(tmp_path / "a")
    shutil.rmtree(missing.projects)
    s1 = Store(tmp_path / "s1", missing)
    try:
        with pytest.raises(ingest.IngestError) as gone:
            s1.run("full")
        assert gone.value.code == "config_dir_missing"
        assert gone.value.file == str(missing.projects)
    finally:
        s1.close()
    if os.geteuid() == 0:
        return
    locked = Config(tmp_path / "b")
    s2 = Store(tmp_path / "s2", locked)
    locked.projects.chmod(0)
    try:
        with pytest.raises(ingest.IngestError) as denied:
            s2.run("full")
        assert denied.value.code == "config_dir_unreadable"
        assert denied.value.file == str(locked.projects)
    finally:
        locked.projects.chmod(0o700)
        s2.close()


def test_an_empty_projects_folder_is_a_clean_pass(config: Config, st: Store) -> None:
    result = st.run("full")
    assert result.files_seen == 0
    assert not result.changed
    assert st.one("SELECT COUNT(*) FROM files") == 0


class TestStatePrivacy:
    def test_file_state_holds_ids_flags_and_counters_only(
        self, config: Config, st: Store
    ) -> None:
        body_text = "SECRET-BODY-TEXT"
        row = json.loads(h.brief_row(1, "coordinator"))
        row["message"]["content"] = body_text
        config.write(
            config.agent("a1"),
            [
                h.assistant(0, "a", stop="end_turn"),
                json.dumps(row).encode(),
                h.link_row(2, "kid"),
            ],
        )
        st.run()
        states = [
            json.loads(str(r[0])) for r in st.rows("SELECT state FROM file_state")
        ]
        assert states
        for state in states:
            assert set(state) <= {"seen", "stopped", "finished"}
        assert body_text not in json.dumps(states)
        dump = "\n".join(st.conn.iterdump())
        assert body_text not in dump

    def test_link_state_round_trips_through_a_dict(self) -> None:
        state = transcripts.LinkState()
        state.seen = {"a1", "b-2"}
        state.stopped = True
        state.finished = True
        data = state.export_state()
        assert json.loads(json.dumps(data)) == data
        back = transcripts.LinkState.from_state(data)
        assert (back.seen, back.stopped, back.finished) == ({"a1", "b-2"}, True, True)
        assert (back.launched, back.rounds, back.stops) == ([], [], [])

    def test_bad_state_dicts_give_defaults(self) -> None:
        back = transcripts.LinkState.from_state(
            {"seen": ["ok", 5, "bad id!", "x" * 90], "stopped": "yes", "finished": 1}
        )
        assert (back.seen, back.stopped, back.finished) == ({"ok"}, False, False)
        assert transcripts.LinkState.from_state({}).seen == set()


class TestMinuteUsage:
    def test_cells_equal_a_rebuild_and_cross_sessions(
        self, config: Config, st: Store
    ) -> None:
        # the same message id in two sessions: the better copy decides the cell
        config.write(
            config.main(h.S1),
            [h.assistant(5, "dup", out=10), h.assistant(70, "solo", out=4)],
        )
        st.run()
        before = h.actual_minutes(st.conn)
        assert before == h.expected_minutes(st.conn, st.ingestor.tier)
        config.write(config.main(h.S2), [h.assistant(130, "dup", out=40, sid=h.S2)])
        st.run()
        after = h.actual_minutes(st.conn)
        assert after == h.expected_minutes(st.conn, st.ingestor.tier)
        # the first session's minute lost its winner: that cell is gone
        sessions = {k[0] for k in after}
        assert sessions == {h.S1, h.S2}
        assert not any(k[0] == h.S1 and str(k[2]).endswith("12:00") for k in after)

    def test_run_key_is_main_or_the_agent_id(self, config: Config, st: Store) -> None:
        config.write(config.main(), [h.assistant(0, "m")])
        config.write(config.agent("a7"), [h.assistant(1, "w")])
        st.run()
        assert st.rows("SELECT run_key FROM minute_usage ORDER BY run_key") == [
            ("a7",),
            ("main",),
        ]

    def test_key_columns_and_tier_text(self, config: Config, st: Store) -> None:
        rows = [h.assistant(0, "h1", model="claude-haiku-5-5", inp=100_001, out=3)]
        rows += [h.assistant(1, "h2", model="claude-haiku-5-5", inp=10, out=3)]
        config.write(config.main(), rows)
        st.run()
        tiers = st.rows("SELECT tier, requests FROM minute_usage ORDER BY tier")
        assert tiers == [("0", 1), ("1", 1)]

    def test_a_tier_threshold_change_rebuilds_the_whole_table(
        self, tmp_path: Path, config: Config
    ) -> None:
        config.write(
            config.main(), [h.assistant(0, "h1", model="claude-sonnet-5-5", inp=60_000)]
        )
        base = ingest.default_tier_policy()
        s = Store(tmp_path, config, tier=base)
        try:
            s.run("full")
            assert s.one("SELECT tier FROM minute_usage") == "0"
            assert s.one("SELECT value FROM meta WHERE key = 'tier_hash'") == base.hash
            moved = ingest.TierPolicy(
                lambda _m, prompt: 1 if prompt > 50_000 else 0, "changed-hash"
            )
            s.ingestor.tier = moved
            result = s.run()
            assert result.changed
            assert s.one("SELECT tier FROM minute_usage") == "1"
            assert (
                s.one("SELECT value FROM meta WHERE key = 'tier_hash'")
                == "changed-hash"
            )
            assert h.actual_minutes(s.conn) == h.expected_minutes(s.conn, moved)
        finally:
            s.close()

    def test_default_policy_reads_the_old_price_tiers(self) -> None:
        policy = ingest.default_tier_policy()
        assert policy.tier_for("claude-haiku-5-5", 100_000) == 0
        assert policy.tier_for("claude-haiku-5-5", 100_001) == 1
        assert policy.tier_for("claude-haiku-5-5-20260101", 200_000) == 1
        assert policy.tier_for("claude-sonnet-5-5", 900_000) == 0
        assert policy.tier_for("not-a-model", 900_000) == 0
        assert policy.tier_for("", 5) == 0
        assert len(policy.hash) == 64


class TestProgress:
    def test_listing_then_fixed_totals_then_done_counts(
        self, config: Config, st: Store
    ) -> None:
        for i, sid in enumerate((h.S1, h.S2, h.S3)):
            config.write(config.main(sid), [h.assistant(i, f"m{i}", sid=sid)])
        calls: list[tuple[object, ...]] = []

        class Sink(ingest.ProgressSink):
            def listing(self) -> None:
                calls.append(("listing",))

            def totals(self, files: int, bytes_: int) -> None:
                calls.append(("totals", files, bytes_))

            def done(self, files: int, bytes_: int) -> None:
                calls.append(("done", files, bytes_))

            def has_work(self) -> None:
                calls.append(("work",))

        st.ingestor.progress = Sink()
        st.run("full")
        size = sum(p.stat().st_size for p in config.projects.rglob("*.jsonl"))
        assert calls[0] == ("listing",)
        assert calls[1] == ("totals", 3, size)
        assert calls[2] == ("work",)
        assert [c[1:] for c in calls[3:]] == [
            (1, calls[3][2]),
            (2, calls[4][2]),
            (3, size),
        ]
        # a pass with nothing to read still reports totals of zero
        calls.clear()
        st.run()
        assert calls == [("listing",), ("totals", 0, 0)]

    def test_totals_count_only_the_bytes_still_to_read(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(), [h.assistant(0, "a")])
        st.run()
        before = config.main().stat().st_size
        config.append(config.main(), [h.assistant(1, "b")])
        seen: list[tuple[int, int]] = []

        class Sink(ingest.ProgressSink):
            def totals(self, files: int, bytes_: int) -> None:
                seen.append((files, bytes_))

        st.ingestor.progress = Sink()
        st.run()
        assert seen == [(1, config.main().stat().st_size - before)]

    def test_pace_runs_after_each_file_and_cancel_ends_the_pass(
        self, config: Config, st: Store
    ) -> None:
        for i, sid in enumerate((h.S1, h.S2, h.S3)):
            config.write(config.main(sid), [h.assistant(i, f"m{i}", sid=sid)])
        paced: list[int] = []
        st.ingestor.pace = lambda: paced.append(1)
        st.ingestor.cancel = lambda: len(paced) >= 2
        result = st.run("full")
        assert paced == [1, 1]
        assert result.cancelled
        assert result.files_read == 2
        assert st.one("SELECT COUNT(*) FROM files") == 2  # what was read is committed
        assert not st.conn.in_transaction


class TestBatches:
    def test_small_batches_give_the_same_store(
        self, tmp_path: Path, config: Config
    ) -> None:
        for i, sid in enumerate((h.S1, h.S2, h.S3)):
            config.write(
                config.main(sid),
                [h.assistant(j, f"m{i}-{j % 3}", sid=sid, out=j) for j in range(6)],
            )
        config.write(config.main(h.S1).with_name("x"), [])
        one = Store(tmp_path / "one", config)
        many = Store(tmp_path / "many", config, batch_rows=1)
        try:
            one.run("full")
            many.run("full")
            assert h.store_totals(one.conn) == h.store_totals(many.conn)
            assert h.actual_minutes(one.conn) == h.actual_minutes(many.conn)
            assert h.actual_minutes(many.conn) == h.expected_minutes(
                many.conn, many.ingestor.tier
            )
        finally:
            one.close()
            many.close()

    def test_a_failed_batch_rolls_back_whole(
        self, config: Config, st: Store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config.write(config.main(h.S1), [h.assistant(0, "a")])
        config.write(config.main(h.S2), [h.assistant(1, "b", sid=h.S2)])

        def boom(self: ingest.Ingestor, keys: object, batch: object) -> None:
            del self, keys, batch
            msg = "disk full"
            raise sqlite3.OperationalError(msg)

        calls = {"n": 0}
        real = ingest.Ingestor._remember_old_winners  # pyright: ignore[reportPrivateUsage]

        def second_file_fails(
            self: ingest.Ingestor, keys: object, batch: object
        ) -> None:
            calls["n"] += 1
            if calls["n"] == 2:
                boom(self, keys, batch)
            real(self, keys, batch)  # pyright: ignore[reportArgumentType]

        monkeypatch.setattr(ingest.Ingestor, "_remember_old_winners", second_file_fails)
        with pytest.raises(sqlite3.OperationalError):
            st.run("full")
        assert not st.conn.in_transaction
        assert st.one("SELECT COUNT(*) FROM files") == 0  # offsets and rows go together
        assert st.one("SELECT COUNT(*) FROM requests") == 0
        monkeypatch.undo()
        st.run("full")
        assert st.one("SELECT COUNT(*) FROM files") == 2


class TestScopes:
    def test_hot_pass_reads_only_the_named_folders(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(h.S1, "-work-one"), [h.assistant(0, "a")])
        config.write(config.main(h.S2, "-work-two"), [h.assistant(0, "b", sid=h.S2)])
        st.ingestor.run_pass(ingest.PassScope("hot", frozenset({"-work-two"})))
        assert st.rows("SELECT folder FROM files") == [("-work-two",)]
        st.run()
        assert st.one("SELECT COUNT(*) FROM files") == 2

    def test_a_hot_pass_does_not_mark_other_folders_missing(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(h.S1, "-work-one"), [h.assistant(0, "a")])
        config.write(config.main(h.S2, "-work-two"), [h.assistant(0, "b", sid=h.S2)])
        st.run()
        st.ingestor.run_pass(ingest.PassScope("hot", frozenset({"-work-two"})))
        assert st.one("SELECT COUNT(*) FROM files WHERE missing = 1") == 0

    def test_running_folders_are_those_with_a_request_in_the_last_30_minutes(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(h.S1, "-work-one"), [h.assistant(0, "a")])
        config.write(
            config.main(h.S2, "-work-two"), [h.assistant(25 * 60, "b", sid=h.S2)]
        )
        st.run()
        at = h.T0 + timedelta(minutes=29)
        assert st.ingestor.running_folders(at) == {"-work-one", "-work-two"}
        assert st.ingestor.running_folders(h.T0 + timedelta(minutes=31)) == {
            "-work-two"
        }
        assert st.ingestor.running_folders(h.T0 + timedelta(hours=2)) == frozenset()

    def test_symlinked_and_foreign_entries_are_ignored(
        self, config: Config, st: Store
    ) -> None:
        config.write(config.main(), [h.assistant(0, "a")])
        outside = config.dir / "elsewhere"
        outside.mkdir()
        config.write(outside / f"{h.S2}.jsonl", [h.assistant(0, "z", sid=h.S2)])
        (config.projects / "-linked").symlink_to(outside)
        (config.projects / "stray.txt").write_text("x", encoding="utf-8")
        (config.projects / h.FOLDER / "notes.md").write_text("x", encoding="utf-8")
        st.run()
        assert st.one("SELECT COUNT(*) FROM files") == 1


class TestRounds:
    ROUNDS = port_helpers.FIXTURES / "rounds"
    NAMES = sorted(p.name for p in ROUNDS.glob("*.jsonl"))

    @staticmethod
    def _old_links(config: Config) -> dict[tuple[str, str | None], transcripts.Links]:
        reader = transcripts.Reader(str(config.dir), horizon_days=100000)
        out = reader.read_folder(h.FOLDER, h.FAR).links
        assert out is not None
        return out

    @staticmethod
    def _stored(st: Store, run_key: str) -> dict[str, list[tuple[object, ...]]]:
        rows = st.rows(
            "SELECT kind, at, finished, by_kind, by_run FROM run_events"
            " WHERE run_key = ? ORDER BY file_id, seq",
            run_key,
        )
        return {
            "launched": [(r[4], r[1]) for r in rows if r[0] == "launch"],
            "rounds": [(r[1], r[3], r[4]) for r in rows if r[0] == "brief"],
            "stops": [(r[1], bool(r[2])) for r in rows if r[0] == "stop"],
        }

    @staticmethod
    def _expect(links: transcripts.Links) -> dict[str, list[tuple[object, ...]]]:
        return {
            "launched": [(c, ingest.ts_text(t)) for c, t in links.launched],
            "rounds": [(ingest.ts_text(t), k, b) for t, k, b in links.rounds],
            "stops": [(ingest.ts_text(t), f) for t, f in links.stops],
        }

    @pytest.mark.parametrize("name", NAMES)
    def test_rounds_and_stops_equal_the_old_links(
        self, name: str, tmp_path: Path, config: Config, st: Store
    ) -> None:
        shutil.copy(self.ROUNDS / name, tmp_path / "fx.jsonl")
        data = (self.ROUNDS / name).read_bytes()
        config.agent("lead-1").parent.mkdir(parents=True)
        config.agent("lead-1").write_bytes(data)
        st.run()
        old = self._old_links(config)[(h.S1, "lead-1")]
        assert self._stored(st, "lead-1") == self._expect(old)
        assert old.stops or old.rounds or old.launched

    @pytest.mark.parametrize("name", NAMES)
    def test_every_split_point_gives_the_same_events(
        self, name: str, config: Config, tmp_path: Path
    ) -> None:
        data = (self.ROUNDS / name).read_bytes()
        lines = [x for x in data.split(b"\n") if x]
        whole = Config(tmp_path / "whole")
        whole.agent("lead-1").parent.mkdir(parents=True)
        whole.agent("lead-1").write_bytes(data)
        old = self._old_links(whole)[(h.S1, "lead-1")]
        for cut in range(1, len(lines)):
            sub = Config(tmp_path / f"cut{cut}")
            s = Store(tmp_path / f"cut{cut}", sub)
            try:
                head = b"\n".join(lines[:cut]) + b"\n"
                half = lines[cut][: len(lines[cut]) // 2]
                sub.agent("lead-1").parent.mkdir(parents=True)
                sub.agent("lead-1").write_bytes(head + half)  # a partial line too
                s.run()
                sub.agent("lead-1").write_bytes(data)
                s.run()
                assert self._stored(s, "lead-1") == self._expect(old), cut
            finally:
                s.close()

    def test_a_peer_round_and_the_launches_equal_the_old_links_on_the_lead_file(
        self, config: Config, st: Store
    ) -> None:
        data = (self.ROUNDS / "worker-handback-wakes-lead.jsonl").read_bytes()
        config.agent("lead-1").parent.mkdir(parents=True)
        config.agent("lead-1").write_bytes(data)
        st.run()
        old = self._old_links(config)[(h.S1, "lead-1")]
        assert old.launched
        assert st.rows("SELECT child_id, resolved FROM links ORDER BY child_id") == [
            (c, 0) for c, _t in sorted(old.launched)
        ]


def test_the_old_reader_is_unchanged_by_the_public_additions(config: Config) -> None:
    config.write(
        config.main(), [h.assistant(0, "a", usage_obj=False), h.assistant(1, "b")]
    )
    reader = transcripts.Reader(str(config.dir), horizon_days=100000)
    reader.read(h.FAR)
    entry = next(iter(reader._cache.values()))  # pyright: ignore[reportPrivateUsage]
    assert set(entry.stats) == {"malformed", "synthetic", "no_id"}


def test_parse_file_resumes_from_an_offset_with_a_link_state(config: Config) -> None:
    lines = [h.assistant(0, "a", stop="end_turn"), h.brief_row(1), h.assistant(2, "b")]
    path = config.write(config.agent("a1"), lines)
    first = transcripts.parse_file(
        str(path), "agent", 0, None, None, session_id=h.S1, run_id="a1", folder=h.FOLDER
    )
    assert first.end_offset == path.stat().st_size
    cut = len(lines[0]) + 1
    head = transcripts.parse_file(
        str(path), "agent", 0, None, None, session_id=h.S1, run_id="a1"
    )
    del head
    part = transcripts.parse_file(
        str(path),
        "agent",
        cut,
        transcripts.LinkState.from_state(
            {"seen": [], "stopped": True, "finished": True}
        ),
        None,
        session_id=h.S1,
        run_id="a1",
    )
    assert [r.message_id for r in part.records] == ["b"]
    assert part.line_offsets == [len(lines[0]) + len(lines[1]) + 2]
    assert len(part.link_state.rounds) == 1
    assert part.stats["no_usage"] == 0
    missing = transcripts.parse_file(str(path) + "x", "agent", 0, None, None)
    assert missing.end_offset is None


def test_the_store_clock_only_writes_utc_text(config: Config, st: Store) -> None:
    config.write(config.main(), [h.assistant(0, "a")])
    st.now = datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    st.run()
    assert st.one("SELECT first_seen FROM files") == "2026-11-01T07:00:00Z"

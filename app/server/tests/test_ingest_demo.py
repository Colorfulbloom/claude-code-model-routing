"""Ingest of the demo build: equal to the old reader, and how long a cold read takes."""

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
from ingest_helpers import Config, Store

import ingest
import transcripts
import usage


@pytest.fixture(scope="module")
def ingested(demo_build: Path, tmp_path_factory: pytest.TempPathFactory) -> Store:
    base = tmp_path_factory.mktemp("demo-store")
    config = Config.__new__(Config)
    config.dir = demo_build / "config"
    config.projects = config.dir / "projects"
    s = Store(base, config)
    s.run("full")
    return s


def test_demo_totals_equal_the_old_reader_and_minute_usage_equals_a_rebuild(
    ingested: Store, demo_build: Path
) -> None:
    assert h.store_totals(ingested.conn) == h.oracle_totals(demo_build / "config")
    assert h.actual_minutes(ingested.conn) == h.expected_minutes(
        ingested.conn, ingested.ingestor.tier
    )


def test_demo_winners_equal_usage_dedupe(ingested: Store, demo_build: Path) -> None:
    result = transcripts.Reader(str(demo_build / "config"), horizon_days=100000).read(
        datetime(2026, 11, 1, tzinfo=UTC)
    )
    kept, no_id = usage.dedupe(result.records)
    assert no_id == 0
    assert ingested.one("SELECT COUNT(*) FROM best_winners") == len(kept)
    assert ingested.one("SELECT SUM(output) FROM best_winners") == sum(
        r.output for r in kept
    )


def test_demo_run_events_equal_the_old_links(ingested: Store, demo_build: Path) -> None:
    reader = transcripts.Reader(str(demo_build / "config"), horizon_days=100000)
    projects = demo_build / "config" / "projects"
    checked = 0
    for folder in sorted(p.name for p in projects.iterdir()):
        links = reader.read_folder(folder, h.FAR).links or {}
        for (sid, run), old in links.items():
            rows = ingested.rows(
                "SELECT kind, at, finished, by_kind, by_run FROM run_events"
                " WHERE session_id = ? AND run_key = ? ORDER BY file_id, seq",
                sid,
                run or "main",
            )
            assert [(r[4], r[1]) for r in rows if r[0] == "launch"] == [
                (c, ingest.ts_text(t)) for c, t in old.launched
            ]
            assert [(r[1], r[3], r[4]) for r in rows if r[0] == "brief"] == [
                (ingest.ts_text(t), k, b) for t, k, b in old.rounds
            ]
            assert [(r[1], bool(r[2])) for r in rows if r[0] == "stop"] == [
                (ingest.ts_text(t), f) for t, f in old.stops
            ]
            checked += len(old.launched) + len(old.rounds) + len(old.stops)
    # The demo rows carry no launches, rounds or stops, so this holds for none. The
    # rounds fixtures in test_ingest.py are where the events are compared for real.
    assert checked == 0


def test_demo_agent_types_and_sessions(ingested: Store) -> None:
    assert ingested.one("SELECT COUNT(*) FROM runs WHERE agent_type IS NOT NULL") == 405
    assert ingested.one("SELECT COUNT(*) FROM sessions") == 133
    assert ingested.one("SELECT COUNT(*) FROM sessions WHERE cwd IS NULL") == 0


@pytest.mark.slow
def test_cold_ingest_of_the_demo_build_with_pace_off(
    demo_build: Path, tmp_path: Path
) -> None:
    config = Config.__new__(Config)
    config.dir = demo_build / "config"
    config.projects = config.dir / "projects"
    s = Store(tmp_path, config)
    try:
        start = time.perf_counter()
        result = s.run("full")
        seconds = time.perf_counter() - start
        rows = s.one("SELECT COUNT(*) FROM requests")
        print(  # noqa: T201 - the number the build report quotes
            f"cold ingest: {result.files_read} files, {result.bytes_read} bytes,"
            f" {rows} rows, {seconds:.3f} s"
        )
        assert result.files_read == 538
        assert result.bytes_read == sum(
            p.stat().st_size for p in config.projects.rglob("*.jsonl")
        )
        start = time.perf_counter()
        again = s.run()
        print(f"no-change pass: {time.perf_counter() - start:.4f} s")  # noqa: T201
        assert again.files_read == 0
    finally:
        s.close()

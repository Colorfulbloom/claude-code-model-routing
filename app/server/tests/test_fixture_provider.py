"""Tests for the fixture provider and its ingest steps on an injected clock."""

import json
from pathlib import Path
from typing import Any

import pytest

import fixture_provider
from fixture_provider import SCENARIOS, FixtureProvider
from provider import Provider


def _provider(scenario: str, clock: Any) -> FixtureProvider:
    return FixtureProvider(scenario, clock)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_scenario_loads(scenario: str, clock: Any) -> None:
    provider = _provider(scenario, clock)
    info = provider.app_info("abcd1234", None)
    assert info.claude_version == "2.1.310"
    assert info.instance == "abcd1234"
    assert provider.scenario == scenario


def test_unknown_scenario_is_refused(clock: Any) -> None:
    with pytest.raises(ValueError, match="unknown fixture scenario"):
        FixtureProvider("../demo", clock)


def test_demo_projects_cover_the_three_states(clock: Any) -> None:
    projects = _provider("demo", clock).projects().projects
    assert [p.key for p in projects] == [
        "tidewater-reporting",
        "saltmarsh",
        "driftwood",
    ]
    assert {p.state for p in projects} == {"ok", "no_claude_folder", "folder_not_found"}
    assert [p.running for p in projects] == [True, False, False]


def test_demo_to_fix_counts(clock: Any) -> None:
    provider = _provider("demo", clock)
    counts = {
        key: provider.app_info("x", key).to_fix_count
        for key in ("tidewater-reporting", "saltmarsh", "driftwood")
    }
    assert counts == {"tidewater-reporting": 4, "saltmarsh": 0, "driftwood": 0}
    assert provider.app_info("x", None).to_fix_count is None
    assert provider.app_info("x", "other").to_fix_count is None


def test_empty_scenario_has_no_projects(clock: Any) -> None:
    provider = _provider("empty", clock)
    assert provider.projects().projects == []
    info = provider.app_info("x", "tidewater-reporting")
    assert info.running == []
    assert info.to_fix_count is None
    assert info.ingest.state == "done"
    assert info.ingest.files_total == 0


def test_demo_ingest_is_done_at_once(clock: Any) -> None:
    ingest = _provider("demo", clock).ingest()
    assert ingest.state == "done"
    assert ingest.files_done == ingest.files_total == 82
    assert ingest.error is None
    assert not ingest.retrying


def test_firstrun_steps_on_the_clock(clock: Any) -> None:
    provider = _provider("firstrun", clock)
    first = provider.ingest()
    assert (first.state, first.files_done, first.bytes_done) == ("waiting", 0, 0)
    assert first.files_total is None
    assert first.bytes_total is None
    clock.advance(1.9)
    assert provider.ingest().state == "waiting"
    clock.advance(0.1)
    seen = [provider.ingest()]
    for _ in range(4):
        clock.advance(1)
        seen.append(provider.ingest())
    assert [s.state for s in seen] == ["running"] * 5
    files = [s.files_done for s in seen]
    nbytes = [s.bytes_done for s in seen]
    assert files == sorted(files)
    assert len(set(files)) == 5
    assert nbytes == sorted(nbytes)
    assert len(set(nbytes)) == 5
    assert all(s.files_total == 82 and s.bytes_total == 82_000_000 for s in seen)
    assert all(s.files_done < 82 for s in seen)
    clock.advance(10)
    final = provider.ingest()
    assert final.state == "done"
    assert final.files_done == final.files_total
    assert final.bytes_done == final.bytes_total
    assert final.error is None


def test_clock_starts_at_the_first_ingest_read(clock: Any) -> None:
    provider = _provider("firstrun", clock)
    clock.advance(500)
    assert provider.ingest().state == "waiting"


def test_firstrun_failed_then_retrying(clock: Any) -> None:
    provider = _provider("firstrun_failed", clock)
    provider.ingest()
    clock.advance(4)
    assert provider.ingest().state == "running"
    clock.advance(1)
    failed = provider.ingest()
    assert failed.state == "failed"
    assert failed.error is not None
    assert failed.error.code == "store_unwritable"
    assert failed.error.file is not None
    assert failed.error.file.startswith("/work/")
    assert failed.retrying is False
    clock.advance(3)
    retrying = provider.ingest()
    assert retrying.state == "running"
    assert retrying.retrying is True
    assert retrying.error == failed.error
    assert failed.retry_at is not None
    assert retrying.retry_at is None
    assert retrying.files_done == 0
    clock.advance(1000)
    assert provider.ingest().retrying is True


def test_server_time_follows_the_clock(clock: Any) -> None:
    provider = _provider("demo", clock)
    before = provider.now()
    clock.advance(60)
    assert (provider.now() - before).total_seconds() == 60
    assert provider.now().tzinfo is not None


@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("/work/tidewater-reporting", "tidewater-reporting"),
        ("/work/Saltmarsh", "saltmarsh"),
        ("/work/Tidewater Reporting", "tidewater-reporting"),
        ("/work/unrelated", None),
        (None, None),
    ],
)
def test_resolve_project(clock: Any, folder: str | None, expected: str | None) -> None:
    provider = _provider("demo", clock)
    assert provider.resolve_project(Path(folder) if folder else None) == expected


def test_fixture_files_use_only_work_paths() -> None:
    for scenario in SCENARIOS:
        text = (fixture_provider.DEFAULT_FIXTURES_DIR / f"{scenario}.json").read_text()
        for value in json.loads(text)["projects"]:
            assert value["display_path"].startswith("/work/")


def test_counting_scenario_has_null_totals(clock: Any) -> None:
    info = _provider("firstrun_counting", clock).app_info("x", None)
    assert info.ingest.state == "running"
    assert info.ingest.files_total is None
    assert info.ingest.bytes_total is None
    assert info.pass_running_since is not None


def test_retry_scenario_keeps_the_error_and_names_the_next_try(clock: Any) -> None:
    provider = _provider("firstrun_retry", clock)
    ingest = provider.ingest()
    assert ingest.state == "failed"
    assert ingest.error is not None
    assert ingest.retry_at is not None
    assert (ingest.retry_at - provider.now()).total_seconds() == 600
    assert ingest.bytes_total == 2_000_000_000
    clock.advance(30)
    assert provider.ingest().retry_at == ingest.retry_at


def test_store_newer_scenario(clock: Any) -> None:
    ingest = _provider("store_newer", clock).ingest()
    assert ingest.state == "failed"
    assert ingest.error is not None
    assert ingest.error.code == "store_newer"
    assert ingest.error.file is None
    assert ingest.retry_at is None


def test_stopped_scenario_is_done_with_a_pass_error(clock: Any) -> None:
    info = _provider("stopped", clock).app_info("x", None)
    assert info.ingest.state == "done"
    error = info.history.pass_error
    assert error is not None
    assert error.code == "config_dir_unreadable"
    assert info.as_of is not None
    assert info.as_of < error.since


def test_history_problem_scenario(clock: Any) -> None:
    history = _provider("history_problem", clock).app_info("x", None).history
    assert history.unreadable_files == 3
    assert history.backup_failed is not None
    assert history.backup_failed.reason_code == "no_space"
    assert history.pass_error is None


def test_times_hold_still_while_the_clock_runs(clock: Any) -> None:
    provider = _provider("stopped", clock)
    before = provider.app_info("x", None)
    clock.advance(600)
    after = provider.app_info("x", None)
    assert after.as_of == before.as_of
    assert after.history == before.history
    assert after.server_time > before.server_time


def test_prices_follow_the_scenario(clock: Any) -> None:
    demo = _provider("demo", clock).prices()
    bundled = _provider("prices_bundled", clock).prices()
    assert (demo.source, bundled.source) == ("litellm", "bundled")
    assert bundled.cross_check.state == "not_checked"
    assert {m.source for m in bundled.models} == {"bundled"}


def test_fixture_provider_satisfies_the_protocol(clock: Any) -> None:
    provider: Provider = _provider("demo", clock)
    assert provider.prices().models

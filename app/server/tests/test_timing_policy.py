"""``timing_policy`` scales limits under CI, and every timing test follows it.

Wall-clock asserts keep tripping on shared runners one test at a time. This file is the
ratchet. A test module that measures a duration must use ``timing_policy`` or be listed
below with its reason. A test that asks ``timing_policy.limit`` for a limit must carry
the ``timing`` marker, because the python 3.11 job deselects that marker.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import timing_policy

TESTS = Path(__file__).resolve().parent
# A duration is a clock reading minus an earlier one: ``monotonic() - started`` or
# ``perf_counter() - began``. A deadline (``monotonic() + 30``) is not a duration.
DURATION = re.compile(r"(?:monotonic|perf_counter)\(\)\s*-")
# Modules that measure a duration and assert no upper limit on it.
NO_UPPER_LIMIT = {
    "test_launcher.py": "asserts a lower bound, that the idle server stayed up",
    "test_ingest_demo.py": "prints the time for the build report and asserts no limit",
}


def _test_modules() -> list[Path]:
    return sorted(p for p in TESTS.glob("test_*.py") if p.name != Path(__file__).name)


def test_the_scan_finds_the_timing_modules() -> None:
    names = {p.name for p in _test_modules()}
    assert {"test_review_size.py", "test_gate.py", "test_launcher.py"} <= names
    assert set(NO_UPPER_LIMIT) <= names


def test_a_local_run_keeps_the_strict_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    assert not timing_policy.in_ci()
    assert timing_policy.limit(250.0) == 250.0
    assert timing_policy.wait_limit(4.0) == 4.0


def test_ci_scales_cpu_limits_by_the_factor_and_waits_by_the_slack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "true")
    assert timing_policy.in_ci()
    assert timing_policy.limit(250.0) == 250.0 * timing_policy.CI_FACTOR
    assert timing_policy.wait_limit(4.0) == 4.0 + timing_policy.CI_WAIT_SLACK_S


def test_the_ci_limit_for_a_mebibyte_line_is_far_under_the_quadratic_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The old mask_url regex took about 480 s on 1 MiB. The CI limit must stay far
    # below that, or the denial-of-service guard stops guarding.
    monkeypatch.setenv("CI", "true")
    assert timing_policy.limit(1.0) <= 480.0 / 20


def test_every_module_that_measures_a_duration_uses_the_policy() -> None:
    stray = [
        p.name
        for p in _test_modules()
        if DURATION.search(p.read_text(encoding="utf-8"))
        and "timing_policy" not in p.read_text(encoding="utf-8")
        and p.name not in NO_UPPER_LIMIT
    ]
    assert stray == [], (
        "these modules measure a duration without timing_policy; use it, or list the "
        "module in NO_UPPER_LIMIT with its reason"
    )


def _is_marked_timing(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(ast.unparse(d) == "pytest.mark.timing" for d in node.decorator_list)


def _asks_for_a_cpu_limit(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Attribute)
        and child.attr == "limit"
        and isinstance(child.value, ast.Name)
        and child.value.id == "timing_policy"
        for child in ast.walk(node)
    )


def test_every_test_that_asks_for_a_cpu_limit_carries_the_timing_marker() -> None:
    unmarked: list[str] = []
    for path in _test_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        unmarked.extend(
            f"{path.name}::{node.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test_")
            and _asks_for_a_cpu_limit(node)
            and not _is_marked_timing(node)
        )
    assert unmarked == [], (
        "the python 3.11 job deselects the timing marker, so these tests would run "
        "there against a CPU limit"
    )

#!/usr/bin/env python3
"""Build the long demo set, for Review's wide ranges (90 days, 12 months, All).

    /usr/bin/python3 app/oracle/long_demo.py <out_dir>

It runs tests/fixtures/demo/build_demo.py in process with ``HISTORY_DAYS`` set to
LONG_HISTORY_DAYS, at the standard demo clock and zone. The builder has no flag for
its history length, and the old files are never edited, so the constant is set on
the imported module. The build's own truth.json still covers the standard 30-day
window, which gives a cross-check against the per-window sums the recorder makes.

``build_long`` also returns the generator's own request list, captured by wrapping
``build_demo._truth``. The recorder (app/oracle/record.py --only long) sums that list
per window, so the wide-range oracle never reads a transcript or the new store.

Same arguments give the same bytes, as for the standard demo build. Python 3.9
standard library only.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BUILDER_DIR = REPO / "tests" / "fixtures" / "demo"
NOW = "2026-10-30T18:00"
TZ = "America/New_York"
LONG_HISTORY_DAYS = 400


def _builder() -> Any:  # noqa: ANN401
    """Import build_demo from its folder."""
    path = str(BUILDER_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("build_demo")


def build_long(out_dir: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build the long set into out_dir. Return its truth.json and the request list."""
    mod = _builder()
    captured: list[list[dict[str, Any]]] = []
    original_truth = mod._truth
    original_days = mod.HISTORY_DAYS

    def keep(requests: list[dict[str, Any]], *args: Any) -> Any:  # noqa: ANN401
        captured.append(list(requests))
        return original_truth(requests, *args)

    mod._truth = keep
    mod.HISTORY_DAYS = LONG_HISTORY_DAYS
    try:
        truth = mod.build(out_dir, NOW, TZ)
    finally:
        mod._truth = original_truth
        mod.HISTORY_DAYS = original_days
    return truth, captured[0]


def main(argv: list[str] | None = None) -> int:
    """Build the long set into the folder named on the command line."""
    parser = argparse.ArgumentParser(description="Build the long demo set.")
    parser.add_argument("out_dir")
    args = parser.parse_args(argv)
    _truth, requests = build_long(args.out_dir)
    print(f"built {args.out_dir} ({len(requests)} requests)")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())

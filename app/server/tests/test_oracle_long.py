"""The wide-range oracle (demo-long) is complete and its groups add up."""

import json
from pathlib import Path
from typing import Any

LONG = Path(__file__).resolve().parents[2] / "fixtures" / "oracle" / "demo-long"
RANGES = ("30d", "90d", "12m", "all")
TOKEN_FIELDS = (
    "input",
    "output",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "thinking",
)
SUMMED = (*TOKEN_FIELDS, "requests")
BANNED = ("/private/", "/" + "Users/", "/" + "tmp/")


def _load(name: str) -> Any:
    return json.loads((LONG / name).read_text(encoding="utf-8"))


def test_manifest_lists_every_file_present() -> None:
    listed = _load("manifest.json")["files"]
    present = sorted(p.name for p in LONG.iterdir() if p.is_file())
    assert sorted(listed) == present


def test_no_payload_holds_a_machine_path() -> None:
    for path in LONG.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for banned in BANNED:
            assert banned not in text, f"{path.name} contains {banned}"


def test_every_project_and_range_is_present() -> None:
    truth = _load("truth-long.json")
    base = _load("truth-30d.json")
    assert set(truth["windows"]) == set(RANGES)
    assert truth["windows"]["all"]["start"] is None
    assert truth["windows"]["all"]["prior_start"] is None
    assert set(truth["projects"]) == set(base["projects"])
    for name, ranges in truth["projects"].items():
        assert set(ranges) == set(RANGES), name
        assert ranges["all"]["prior"] is None
        assert ranges["all"]["start"]
        for rng in ("30d", "90d", "12m"):
            assert ranges[rng]["prior"] is not None


def test_30d_current_equals_the_builds_own_truth() -> None:
    truth = _load("truth-long.json")
    base = _load("truth-30d.json")
    for name, row in base["projects"].items():
        assert truth["projects"][name]["30d"]["current"] == row, name


def test_ranges_nest() -> None:
    truth = _load("truth-long.json")
    for name, ranges in truth["projects"].items():
        counts = [
            ranges[r]["current"]["requests"] for r in ("30d", "90d", "12m", "all")
        ]
        assert counts == sorted(counts), name


def test_every_group_sums_to_current() -> None:
    truth = _load("truth-long.json")
    for name, ranges in truth["projects"].items():
        for rng, entry in ranges.items():
            for field in ("by_model", "by_agent", "by_day"):
                groups = entry[field]
                for key in SUMMED:
                    total = sum(g[key] for g in groups.values())
                    assert total == entry["current"][key], (name, rng, field, key)

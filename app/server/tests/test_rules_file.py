"""The new rules answer against ``rules.json`` itself, with no hard-coded count.

The file is read directly. Every rule appears once, ``checked_on`` is the oldest
version across ``rules.json`` and ``agent_fields.json``, and ``due`` follows
``claude_version.older(verified_on, installed)`` (m5-build.md section 3).
"""

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path

import agent_frontmatter
import claude_version
import rules_reference
from model_catalog import RULES_PATH

INSTALLED: list[str | None] = [None, "", "abc", "2.1.200", "2.1.302", "2.1.310", "3"]


def _file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _answer(installed: str | None) -> dict[str, Any]:
    answer = rules_reference.build_answer(installed, datetime.now(UTC))
    return answer.model_dump(mode="json")


def _numbers(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_every_rule_appears_exactly_once() -> None:
    rules = _file(RULES_PATH)["rules"]
    ids = [rule["rule_id"] for rule in rules]
    assert len(ids) == len(set(ids)), "rules.json repeats a rule_id"
    body = _answer(None)
    counts = Counter(row["rule_id"] for row in body["rules"])
    assert set(counts) == set(ids)
    assert set(counts.values()) == {1}
    assert len(body["rules"]) == len(ids)
    assert [row["rule_id"] for row in body["rules"]] == sorted(ids)


def test_each_row_carries_its_rule_as_the_file_has_it() -> None:
    by_id = {rule["rule_id"]: rule for rule in _file(RULES_PATH)["rules"]}
    for row in _answer("2.1.310")["rules"]:
        rule = by_id[row["rule_id"]]
        for field in ("key", "scope", "combine", "layer_order", "confidence"):
            assert row[field] == rule[field], (row["rule_id"], field)
        assert row["verified_on"] == {
            "claude_version": rule["verified_on"]["claude_version"],
            "date": rule["verified_on"]["date"],
        }
        quotes: list[dict[str, str]] = rule.get("quotes") or []
        assert row["quotes"] == [
            {"doc_url": q["doc_url"], "quote": q["quote"]} for q in quotes
        ]
        experiment = rule.get("experiment")
        expected = PurePosixPath(experiment).name if experiment else None
        assert row["experiment"] == expected, row["rule_id"]
        assert "reason" not in row


def test_outcomes_are_the_distinct_condition_statuses_in_file_order() -> None:
    by_id = {rule["rule_id"]: rule for rule in _file(RULES_PATH)["rules"]}
    for row in _answer(None)["rules"]:
        seen: list[str] = []
        for condition in by_id[row["rule_id"]]["conditions"]:
            if condition["status"] not in seen:
                seen.append(condition["status"])
        assert row["outcomes"] == seen, row["rule_id"]
        assert row["outcomes"], row["rule_id"]


def test_checked_on_is_the_oldest_version_of_both_files() -> None:
    rules = _file(RULES_PATH)["rules"]
    fields = _file(Path(agent_frontmatter.FIELDS_PATH))
    versions = [rule["verified_on"]["claude_version"] for rule in rules]
    versions.append(fields["verified_on"]["claude_version"])
    oldest = min(versions, key=_numbers)
    assert _answer(None)["checked_on"] == oldest
    assert _answer("2.1.310")["checked_on"] == oldest


@pytest.mark.parametrize("installed", INSTALLED)
def test_due_follows_older_of_verified_on_and_installed(installed: str | None) -> None:
    by_id = {rule["rule_id"]: rule for rule in _file(RULES_PATH)["rules"]}
    body = _answer(installed)
    assert body["installed"] == installed
    for row in body["rules"]:
        verified = by_id[row["rule_id"]]["verified_on"]["claude_version"]
        want = installed is not None and claude_version.older(verified, installed)
        assert row["due"] is want, (row["rule_id"], installed)

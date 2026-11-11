"""Tests for the Rules reference answer and the version gap."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import agent_frontmatter
import claude_version
import rules_reference
from model_catalog import RULES_PATH

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
FIELDS = Path(agent_frontmatter.FIELDS_PATH)


def _document() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _fields_version() -> str:
    return json.loads(FIELDS.read_text(encoding="utf-8"))["verified_on"][
        "claude_version"
    ]


def _write(path: Path, document: dict[str, Any]) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _expected_checked_on() -> str:
    found = [r["verified_on"]["claude_version"] for r in _document()["rules"]]
    found.append(_fields_version())
    best = claude_version.oldest(found)
    assert best is not None
    return best


def test_every_field_of_every_rule() -> None:
    answer = rules_reference.build_answer("2.1.302", NOW)
    source = {r["rule_id"]: r for r in _document()["rules"]}
    assert [r.rule_id for r in answer.rules] == sorted(source)
    assert len(answer.rules) == len(source)
    for row in answer.rules:
        rule = source[row.rule_id]
        assert row.key == rule["key"]
        assert row.scope == rule["scope"]
        assert row.combine == rule["combine"]
        assert row.layer_order == rule["layer_order"]
        assert row.confidence == rule["confidence"]
        assert row.verified_on.claude_version == rule["verified_on"]["claude_version"]
        assert row.verified_on.date == rule["verified_on"]["date"]
        assert [(q.doc_url, q.quote) for q in row.quotes] == [
            (q["doc_url"], q["quote"]) for q in rule["quotes"]
        ]
        record = rule.get("experiment")
        assert row.experiment == (None if record is None else record.rsplit("/", 1)[-1])
        assert row.experiment is None or "/" not in row.experiment
        assert row.due is False


def test_the_answer_is_shaped_and_carries_no_sentence() -> None:
    answer = rules_reference.build_answer("2.1.302", NOW)
    assert answer.unchanged is False
    assert answer.server_time == NOW
    assert answer.installed == "2.1.302"
    dumped = answer.model_dump(mode="json")
    assert set(dumped) == {
        "server_time",
        "etag",
        "unchanged",
        "installed",
        "checked_on",
        "rules",
    }
    assert "reason" not in dumped["rules"][0]
    text = json.dumps(dumped)
    for rule in _document()["rules"]:
        assert rule["reason"] not in text


def test_a_rule_without_an_experiment_gets_none() -> None:
    document = _document()
    assert any(r.get("experiment") is None for r in document["rules"])
    answer = rules_reference.build_answer("2.1.302", NOW)
    assert any(row.experiment is None for row in answer.rules)


def test_checked_on_is_the_oldest_version_of_the_rules_and_the_fields() -> None:
    assert rules_reference.build_answer(None, NOW).checked_on == _expected_checked_on()


def test_the_agent_fields_table_counts_toward_checked_on(tmp_path: Path) -> None:
    fields = json.loads(FIELDS.read_text(encoding="utf-8"))
    fields["verified_on"]["claude_version"] = "2.0.9"
    answer = rules_reference.build_answer(
        None, NOW, fields_path=_write(tmp_path / "fields.json", fields)
    )
    assert answer.checked_on == "2.0.9"


def test_one_old_rule_sets_checked_on(tmp_path: Path) -> None:
    document = _document()
    document["rules"][3]["verified_on"]["claude_version"] = "2.0.5"
    answer = rules_reference.build_answer(
        "2.1.302", NOW, rules_path=_write(tmp_path / "rules.json", document)
    )
    assert answer.checked_on == "2.0.5"
    by_id = {r.rule_id: r for r in answer.rules}
    assert by_id[document["rules"][3]["rule_id"]].due is True


@pytest.mark.parametrize(
    ("installed", "due"),
    [
        (None, False),  # no version
        ("abc", False),  # unparsable
        ("2.1.302", False),  # the same
        ("2.1.310", True),  # newer
        ("2.1.200", False),  # older
    ],
)
def test_due_for_each_installed_case(installed: str | None, due: bool) -> None:
    answer = rules_reference.build_answer(installed, NOW)
    assert {row.due for row in answer.rules} == {due}
    assert answer.installed == installed


@pytest.mark.parametrize(
    ("installed", "gap"),
    [
        ("", False),
        ("abc", False),
        ("2.1.302", False),
        ("2.1.310", True),
        ("2.1.200", False),
        ("2.1.310 (Claude Code)", True),
    ],
)
def test_version_gap_for_each_installed_case(installed: str, gap: bool) -> None:
    found = rules_reference.version_gap(installed)
    if not gap:
        assert found is None
        return
    assert found is not None
    assert found.installed == installed
    assert found.checked_on == _expected_checked_on()
    assert found.due == sum(
        claude_version.older(r["verified_on"]["claude_version"], installed)
        for r in _document()["rules"]
    )


def test_version_gap_counts_rules_only_and_ignores_the_fields_table(
    tmp_path: Path,
) -> None:
    fields = json.loads(FIELDS.read_text(encoding="utf-8"))
    fields["verified_on"]["claude_version"] = "2.0.1"
    document = _document()
    for index, rule in enumerate(document["rules"]):
        rule["verified_on"]["claude_version"] = "2.1.320" if index < 5 else "2.1.330"
    gap = rules_reference.version_gap(
        "2.1.325",
        rules_path=_write(tmp_path / "rules.json", document),
        fields_path=_write(tmp_path / "fields.json", fields),
    )
    assert gap is not None
    assert gap.checked_on == "2.0.1"
    assert gap.due == 5


def test_outcomes_keep_first_seen_order_and_drop_repeats(tmp_path: Path) -> None:
    document = _document()
    rule = document["rules"][0]
    rule["conditions"] = [
        {"layer": "user", "models": ["*"], "status": "in_effect"},
        {"layer": "project", "models": ["*"], "status": "unknown"},
        {"layer": "local", "models": ["*"], "status": "in_effect"},
        {"layer": "flag", "models": ["*"], "status": "ignored"},
        {"layer": "default", "models": ["*"], "status": "unknown"},
    ]
    answer = rules_reference.build_answer(
        None, NOW, rules_path=_write(tmp_path / "rules.json", document)
    )
    by_id = {r.rule_id: r for r in answer.rules}
    assert by_id[rule["rule_id"]].outcomes == ["in_effect", "unknown", "ignored"]


def test_version_gap_follows_the_oldest_file_version(tmp_path: Path) -> None:
    fields = json.loads(FIELDS.read_text(encoding="utf-8"))
    fields["verified_on"]["claude_version"] = "2.1.320"
    document = _document()
    for rule in document["rules"]:
        rule["verified_on"]["claude_version"] = "2.1.320"
    rules_path = _write(tmp_path / "rules.json", document)
    fields_path = _write(tmp_path / "fields.json", fields)
    assert (
        rules_reference.version_gap(
            "2.1.320", rules_path=rules_path, fields_path=fields_path
        )
        is None
    )
    gap = rules_reference.version_gap(
        "2.1.321", rules_path=rules_path, fields_path=fields_path
    )
    assert gap is not None
    assert gap.checked_on == "2.1.320"


def test_the_etag_follows_the_files_and_the_installed_version(tmp_path: Path) -> None:
    base = rules_reference.build_answer("2.1.302", NOW)
    assert base.etag == rules_reference.build_answer("2.1.302", NOW).etag
    assert base.etag != rules_reference.build_answer("2.1.310", NOW).etag
    assert base.etag != rules_reference.build_answer(None, NOW).etag
    assert len(base.etag) <= 64
    document = _document()
    document["rules"][0]["confidence"] = "assumed"
    changed = rules_reference.build_answer(
        "2.1.302", NOW, rules_path=_write(tmp_path / "rules.json", document)
    )
    assert changed.etag != base.etag
    fields = json.loads(FIELDS.read_text(encoding="utf-8"))
    fields["doc_url"] = "https://example.invalid/work"
    moved = rules_reference.build_answer(
        "2.1.302", NOW, fields_path=_write(tmp_path / "fields.json", fields)
    )
    assert moved.etag != base.etag

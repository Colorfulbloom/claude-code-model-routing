"""The Rules reference answer: every rule of ``rules.json`` as data, no sentences.

The page owns every word, so a rule's ``reason`` text never leaves this module. The
answer carries each rule's keys, order, confidence, version, quotes and the file name
of its experiment record.

``checked_on`` is the oldest Claude Code version any rule, or the agent fields table,
was checked on. The table counts because it decides Ignored for frontmatter and no rule
reports its age. A rule is ``due`` when the installed version is newer than the one it
was checked on.
"""

import functools
import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

import agent_frontmatter
import claude_version
from model_catalog import RULES_PATH
from models import (
    ModelCheckStatus,
    RuleQuote,
    RuleRow,
    RulesAnswer,
    RuleVerified,
    VersionGap,
)

# The etag is a short, URL-safe hash, inside the 64 characters the query allows.
ETAG_LENGTH = 32


def _object(raw: bytes) -> dict[str, Any]:
    """Return the JSON object in ``raw``."""
    return cast("dict[str, Any]", json.loads(raw.decode("utf-8")))


def _experiment(path: object) -> str | None:
    """Return the file name of an experiment record path, or None."""
    if not isinstance(path, str) or not path:
        return None
    return PurePosixPath(path).name or None


def _row(rule: dict[str, Any], installed: str | None) -> RuleRow:
    verified: dict[str, str] = rule["verified_on"]
    quotes: list[dict[str, str]] = rule.get("quotes") or []
    return RuleRow(
        rule_id=rule["rule_id"],
        key=rule["key"],
        scope=rule["scope"],
        combine=rule["combine"],
        layer_order=list(rule["layer_order"]),
        confidence=rule["confidence"],
        verified_on=RuleVerified(
            claude_version=verified["claude_version"], date=verified["date"]
        ),
        due=installed is not None
        and claude_version.older(verified["claude_version"], installed),
        quotes=[
            RuleQuote(doc_url=quote["doc_url"], quote=quote["quote"])
            for quote in quotes
        ],
        outcomes=_outcomes(rule),
        experiment=_experiment(rule.get("experiment")),
    )


def _outcomes(rule: dict[str, Any]) -> list[ModelCheckStatus]:
    """Return the distinct ``conditions[].status`` values, in first-seen order."""
    found: list[ModelCheckStatus] = []
    conditions: list[dict[str, Any]] = rule.get("conditions") or []
    for condition in conditions:
        status = cast("ModelCheckStatus | None", condition.get("status"))
        if status is not None and status not in found:
            found.append(status)
    return found


def _checked_on(rules: dict[str, Any], fields: dict[str, Any]) -> str:
    """Return the oldest version across the rules and the agent fields table."""
    found = [rule["verified_on"]["claude_version"] for rule in rules["rules"]]
    found.append(fields["verified_on"]["claude_version"])
    best = claude_version.oldest(found)
    return best if best is not None else ""


@functools.lru_cache(maxsize=8)
def _checked_on_cached(
    rules_path: Path, rules_mtime: int, fields_path: Path, fields_mtime: int
) -> tuple[str, tuple[str, ...]]:
    """Return ``checked_on`` and the rules' versions, parsed once per path and mtime.

    ``/api/app`` asks on every poll, and the files ship with the app, so the mtimes
    only take part to keep a test that rewrites a file honest. The versions cover
    rules only, so the caller can count the due rules per call.
    """
    del rules_mtime, fields_mtime
    rules = _object(rules_path.read_bytes())
    fields = _object(fields_path.read_bytes())
    versions = tuple(rule["verified_on"]["claude_version"] for rule in rules["rules"])
    return _checked_on(rules, fields), versions


def _etag(rules_bytes: bytes, fields_bytes: bytes, installed: str | None) -> str:
    digest = hashlib.sha256()
    for part in (rules_bytes, fields_bytes, (installed or "").encode("utf-8")):
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()[:ETAG_LENGTH]


def build_answer(
    installed: str | None,
    server_time: datetime,
    *,
    rules_path: Path = RULES_PATH,
    fields_path: Path = Path(agent_frontmatter.FIELDS_PATH),
) -> RulesAnswer:
    """Build the answer for ``GET /api/rules``.

    Args:
        installed: The Claude Code version the newest session ran, or None.
        server_time: The provider's clock.
        rules_path: The rules file. The default is ``data/rules.json``.
        fields_path: The agent fields file. The default is ``data/agent_fields.json``.

    Returns:
        The rules sorted by ``rule_id``, with the etag of the files and ``installed``.
    """
    rules_bytes = rules_path.read_bytes()
    fields_bytes = fields_path.read_bytes()
    rules = _object(rules_bytes)
    fields = _object(fields_bytes)
    ordered = sorted(rules["rules"], key=lambda rule: rule["rule_id"])
    return RulesAnswer(
        server_time=server_time,
        etag=_etag(rules_bytes, fields_bytes, installed),
        unchanged=False,
        installed=installed,
        checked_on=_checked_on(rules, fields),
        rules=[_row(rule, installed) for rule in ordered],
    )


def version_gap(
    installed: str,
    *,
    rules_path: Path = RULES_PATH,
    fields_path: Path = Path(agent_frontmatter.FIELDS_PATH),
) -> VersionGap | None:
    """Return the gap between ``installed`` and the version the rules were checked on.

    Args:
        installed: The Claude Code version, as ``/api/app`` reports it. May be empty.
        rules_path: The rules file. The default is ``data/rules.json``.
        fields_path: The agent fields file. The default is ``data/agent_fields.json``.

    Returns:
        A gap only when ``installed`` parses and ``checked_on`` is older. An empty or
        unparsable ``installed`` gives None.
    """
    if claude_version.parse(installed) is None:
        return None
    checked_on, versions = _checked_on_cached(
        rules_path,
        rules_path.stat().st_mtime_ns,
        fields_path,
        fields_path.stat().st_mtime_ns,
    )
    if not claude_version.older(checked_on, installed):
        return None
    due = sum(1 for version in versions if claude_version.older(version, installed))
    return VersionGap(installed=installed, checked_on=checked_on, due=due)

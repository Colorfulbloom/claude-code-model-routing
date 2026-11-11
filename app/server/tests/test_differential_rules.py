"""Differential test: the new ``GET /api/rules`` against the old ``/api/rules``.

The recorder (``app/oracle/record.py --only rules``) saved the old answer twice under
``app/fixtures/oracle/rules/``, once on the demo build (installed 2.1.310) and once with
no version. The new answer is asked through the route on a scenario that reports the
same version. Rule ids and their order, ``confidence``, ``verified_on``, ``due`` and
``quotes`` must match. The allowed differences each carry a pinned count, and a count
that changes fails the test (m5-build.md section 3).
"""

import json
import sys
from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import version_helpers as vh
from conftest import REPO_ROOT

import agent_frontmatter
import claude_version
import main

OpenClient = Callable[..., AbstractContextManager[Any]]

ORACLE = REPO_ROOT / "app" / "fixtures" / "oracle" / "rules"
# (recording, the version the new scenario reports). The demo build names 2.1.310.
RECORDINGS: list[tuple[str, str]] = [
    ("with-version.json", "2.1.310"),
    ("no-version.json", ""),
]

# The pinned counts, one set per recording. Each recording holds 84 rules, 53 of them
# with an experiment record.
ALLOWED: dict[str, int] = {
    # The old answer has "reason" and the new one sends no English.
    "reason-not-sent": 84,
    # The old answer has "reference_url" on every rule and "experiment_url" on those
    # with an experiment. The new one has the experiment file name only.
    "no-repo-links:reference_url": 84,
    "no-repo-links:experiment_url": 53,
    # The old "installed" can come from the binary on PATH and the new one from the
    # store. On fixtures both read the scenario's version, so no answer differs. The
    # entry stays to say why the count is 0.
    "installed-source": 0,
}
OLD_ONLY = {"reason", "reference_url", "experiment_url"}
NEW_ONLY = {"key", "scope", "combine", "layer_order", "outcomes"}
SAME = ("rule_id", "confidence", "verified_on", "due", "quotes")


def _load(name: str) -> dict[str, Any]:
    return json.loads((ORACLE / name).read_text(encoding="utf-8"))


def _new_answer(
    open_client: OpenClient, tmp_path: Path, dist_dir: Path, version: str
) -> dict[str, Any]:
    settings, state = vh.scenario_settings(tmp_path, dist_dir, version)
    with open_client(main.create_app(settings)) as client:
        reply = client.get("/api/rules", headers={"X-Bartab-Key": state.read_key})
    assert reply.status_code == 200
    return reply.json()


def _expected_checked_on(old_rows: list[dict[str, Any]]) -> str | None:
    """The old answer has no checked_on, so rebuild it from the old verified_on.

    The old route never sent it. The new one takes the oldest version across the rules
    and the agent fields table, so the same rule applies to the old rows plus the table.
    """
    fields = json.loads(Path(agent_frontmatter.FIELDS_PATH).read_text(encoding="utf-8"))
    found = [row["verified_on"]["claude_version"] for row in old_rows]
    found.append(fields["verified_on"]["claude_version"])
    return claude_version.oldest(found)


@pytest.mark.parametrize(("recording", "version"), RECORDINGS)
def test_the_new_answer_matches_the_old_one_rule_by_rule(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    recording: str,
    version: str,
) -> None:
    old = _load(recording)
    new = _new_answer(open_client, tmp_path, dist_dir, version)
    old_rows: list[dict[str, Any]] = old["rules"]
    new_rows: list[dict[str, Any]] = new["rules"]

    # Rule ids and their order.
    assert [r["rule_id"] for r in new_rows] == [r["rule_id"] for r in old_rows]

    seen: Counter[str] = Counter()
    for old_row, new_row in zip(old_rows, new_rows, strict=True):
        rule_id = old_row["rule_id"]
        for field in SAME:
            assert new_row[field] == old_row[field], (rule_id, field)
        # Field names: what the old row had and the new one has not, and the reverse.
        assert set(old_row) - set(new_row) == OLD_ONLY, rule_id
        assert set(new_row) - set(old_row) == NEW_ONLY, rule_id
        seen["reason-not-sent"] += int("reason" in old_row and "reason" not in new_row)
        seen["no-repo-links:reference_url"] += int(
            old_row["reference_url"] is not None and "reference_url" not in new_row
        )
        link = old_row["experiment_url"]
        if link is None:
            assert new_row["experiment"] is None, rule_id
        else:
            seen["no-repo-links:experiment_url"] += int("experiment_url" not in new_row)
            assert new_row["experiment"] == PurePosixPath(link).name, rule_id
            # The old experiment is the path under dashboard/, so its name agrees too.
            assert new_row["experiment"] == PurePosixPath(old_row["experiment"]).name

    # installed: both sides name the scenario's version (None when it has none).
    seen["installed-source"] += int(new["installed"] != old["installed"])
    # Every allowed difference, with its pinned count. A count that moves fails here.
    assert {key: seen.get(key, 0) for key in ALLOWED} == ALLOWED

    # checked_on: new field. The mapping is described in _expected_checked_on.
    assert new["checked_on"] == _expected_checked_on(old_rows)


def test_the_recordings_hold_the_pinned_totals() -> None:
    for recording, _version in RECORDINGS:
        rows = _load(recording)["rules"]
        assert len(rows) == ALLOWED["reason-not-sent"]
        linked = sum(1 for r in rows if r["experiment_url"])
        assert linked == ALLOWED["no-repo-links:experiment_url"]
        assert all(set(r) >= OLD_ONLY for r in rows)

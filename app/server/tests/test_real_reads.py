"""The real-mode read audit (m4-build.md section 7, "How the rule is enforced").

The server runs as a subprocess in a fake HOME, through ``read_audit_child.py``, which
logs every ``open``, ``os.listdir`` and ``os.scandir`` path. The tree has allowed files
and decoys (``read_audit_helpers.build_decoys``). After the pages are polled, every
logged path must be one the scope allows, or the app's own code, the Python install,
the store root or a named system file, and no decoy may appear.

Today only the M2 model check reads setup files, so the test drives what exists: start,
first run, the timeline, Agents and Summary. Tasks 4 to 9 add their setup routes to
``read_audit_helpers.poll_the_pages`` and nothing else here changes.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import read_audit_helpers as audit

import store_provider


@pytest.fixture
def decoys(tmp_path: Path) -> audit.Decoys:
    return audit.build_decoys(tmp_path)


def _run(decoys: audit.Decoys) -> list[tuple[str, str]]:
    with audit.audited_server(decoys) as served:
        audit.poll_the_pages(served)
        assert served.server.stop() == 0
        log = served.server.log.read_text(errors="replace")
        assert "Traceback" not in log
    return audit.read_log(served.log)


def test_the_server_reads_only_what_the_scope_allows(decoys: audit.Decoys) -> None:
    entries = _run(decoys)
    audit.assert_reads_allowed(
        entries,
        decoys,
        scope=decoys.scope(),
        extra_roots=[decoys.store, decoys.dist],
    )


def test_the_audit_sees_the_reads_it_should(decoys: audit.Decoys) -> None:
    opened = {path for event, path in _run(decoys) if event == "open"}
    # The model check reads user and project settings, and the repo-root local file
    # that sits above the project (owner answer 5), through the scope.
    for expected in (
        decoys.config / "settings.json",
        decoys.project / ".claude" / "settings.json",
        decoys.outer / ".claude" / "settings.local.json",
    ):
        assert str(expected) in opened, expected


def test_no_decoy_is_opened_or_listed(decoys: audit.Decoys) -> None:
    entries = _run(decoys)
    seen = [
        (event, path)
        for event, path in entries
        for decoy in decoys.decoys
        if path == str(decoy) or path.startswith(str(decoy) + os.sep)
    ]
    assert seen == []
    # The unlisted project is never read, though transcripts name it.
    assert not any(path.startswith(str(decoys.unlisted)) for _e, path in entries)


def test_the_assertion_fails_on_a_decoy_and_on_a_stray_path(
    decoys: audit.Decoys,
) -> None:
    scope = decoys.scope()
    fine = [("open", str(decoys.config / "settings.json"))]
    audit.assert_reads_allowed(fine, decoys, scope=scope)
    for bad in (
        ("open", str(decoys.outer / "secrets.txt")),
        ("os.scandir", str(decoys.listed_folder / "memory")),
        ("open", str(decoys.home / ".ssh" / "id_rsa")),
        ("open", str(decoys.unlisted / "CLAUDE.md")),
        ("open", str(decoys.outer / "other" / "file.txt")),
    ):
        with pytest.raises(pytest.fail.Exception):
            audit.assert_reads_allowed([bad], decoys, scope=scope)


def test_the_managed_folder_is_the_platforms_own(decoys: audit.Decoys) -> None:
    managed = store_provider.managed_dir_for(sys.platform)
    assert decoys.context().managed_dir == managed

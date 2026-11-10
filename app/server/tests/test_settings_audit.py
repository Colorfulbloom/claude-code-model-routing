"""The settings collector opens only what the read scope allows (m4-build.md section 7).

``settings_audit_child.py`` runs the collector under an audit hook that logs every
``open``, ``os.listdir`` and ``os.scandir``, on the decoy tree of
``read_audit_helpers`` plus a managed folder with settings and style files. Every
logged path must pass ``Scope.allows`` (or sit under the app's own code and Python),
and no decoy may appear. There is no setup route yet, so this runs the collector
directly. Task 9 adds the routes to ``poll_the_pages``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import read_audit_helpers as audit

import read_scope
import setup_contract

CHILD = audit.HERE / "settings_audit_child.py"


def _put(path: Path, text: str = audit.DECOY_TEXT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def decoys(tmp_path: Path) -> audit.Decoys:
    world = audit.build_decoys(tmp_path)
    managed = world.root / "managed"
    _put(managed / "managed-settings.json", '{"model": "claude-sonnet-5-5"}\n')
    _put(managed / "managed-settings.d" / "10.json", '{"outputStyle": "x"}\n')
    _put(managed / ".claude" / "output-styles" / "x.md", "---\nname: x\n---\n")
    # Decoys beside the files the collector reads.
    for stray in (
        world.config / "output-styles-notes.txt",
        world.project / ".claude" / "settings.local.json.bak",
        world.outside / "styles" / "evil.md",
    ):
        _put(stray)
    (world.config / "output-styles").mkdir()
    (world.config / "output-styles" / "linked").symlink_to(world.outside / "styles")
    _put(world.config / "output-styles" / "mine.md", "---\nname: mine\n---\n")
    _put(world.project / ".claude" / "output-styles" / "p.md", "---\nname: p\n---\n")
    (world.project / ".claude" / "output-styles" / "out.md").symlink_to(
        world.outside / "styles" / "evil.md"
    )
    return world


def _run(
    world: audit.Decoys, *, listed: bool = True
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    log = world.root / "settings-reads.log"
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-B",
            str(CHILD),
            str(world.config),
            str(world.home),
            str(world.root / "managed"),
            str(world.project) if listed else "-",
        ],
        cwd=audit.SERVER_DIR,
        env={**world.env(), audit.LOG_ENV: str(log)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return audit.read_log(log), json.loads(proc.stdout.splitlines()[-1])


def _scope(world: audit.Decoys, *, listed: bool = True) -> read_scope.Scope:
    return read_scope.Scope(
        setup_contract.SetupContext(
            project_key="proj",
            config_dir=world.config,
            home=world.home,
            project_dir=world.project if listed else None,
            managed_dir=world.root / "managed",
            real_mode=True,
        )
    )


def test_every_open_and_listing_passes_the_scope(decoys: audit.Decoys) -> None:
    entries, counts = _run(decoys)
    assert counts["settings"] >= 2
    scope = _scope(decoys)
    audit.assert_reads_allowed(
        entries,
        decoys,
        scope=scope,
        followed=[decoys.outside / "styles" / "evil.md"],
    )
    followed = str(decoys.outside / "styles" / "evil.md")
    # Everything under the test's own tree must pass the scope. The one exception is a
    # single-file symlink's real target, which is read through its link.
    own = [
        (event, path)
        for event, path in entries
        if path.startswith(str(decoys.root) + os.sep) and path != followed
    ]
    assert own, "the collector read nothing inside the scope"
    for event, path in own:
        assert scope.allows(path, folder=event != "open"), (event, path)


def test_the_audit_sees_the_files_it_should(decoys: audit.Decoys) -> None:
    entries, _counts = _run(decoys)
    opened = {path for event, path in entries if event == "open"}
    for wanted in (
        decoys.config / "settings.json",
        decoys.project / ".claude" / "settings.json",
        decoys.outer / ".claude" / "settings.local.json",
        decoys.root / "managed" / "managed-settings.json",
        decoys.root / "managed" / "managed-settings.d" / "10.json",
        decoys.root / "managed" / ".claude" / "output-styles" / "x.md",
        decoys.config / "output-styles" / "mine.md",
        decoys.project / ".claude" / "output-styles" / "p.md",
    ):
        assert str(wanted) in opened, wanted


def test_no_decoy_is_opened_or_listed(decoys: audit.Decoys) -> None:
    entries, _counts = _run(decoys)
    for decoy in decoys.decoys:
        hit = [
            p
            for _e, p in entries
            if p == str(decoy) or p.startswith(str(decoy) + os.sep)
        ]
        assert hit == [], decoy
    texts = [p for _e, p in entries]
    assert not any("evil.md" in p and "styles" in p and "linked" in p for p in texts)
    assert not any(p.endswith("output-styles-notes.txt") for p in texts)
    assert not any(p.endswith("settings.local.json.bak") for p in texts)


def test_an_unlisted_project_opens_nothing_under_it(decoys: audit.Decoys) -> None:
    entries, counts = _run(decoys, listed=False)
    assert counts["settings"] >= 1
    paths = [p for _e, p in entries]
    assert not any(p.startswith(str(decoys.project) + os.sep) for p in paths)
    assert not any(p.startswith(str(decoys.unlisted)) for p in paths)
    audit.assert_reads_allowed(
        entries,
        decoys,
        scope=_scope(decoys, listed=False),
        followed=[decoys.outside / "styles" / "evil.md"],
    )


def test_the_audit_fails_when_a_read_leaves_the_scope(decoys: audit.Decoys) -> None:
    scope = _scope(decoys)
    stray = [("open", str(decoys.outer / "secrets.txt"))]
    with pytest.raises(pytest.fail.Exception):
        audit.assert_reads_allowed(stray, decoys, scope=scope)

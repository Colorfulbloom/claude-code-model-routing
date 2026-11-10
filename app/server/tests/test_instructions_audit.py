"""The skills and instructions collectors open only what the read scope allows
(m4-build.md section 7).

``instructions_audit_child.py`` runs both collectors under an audit hook that logs every
``open``, ``os.listdir`` and ``os.scandir``, on the decoy tree of ``read_audit_helpers``
plus skills, commands, rules and imports of its own. Every logged path must pass
``Scope.allows`` (or sit under the app's own code and Python), and no decoy may appear.
The tree holds an auto memory file, a symlink to it inside the project, an import that
points out of the roots, a symlinked skills folder and an outside plugin path. There is
no setup route yet, so this runs the collectors directly. Task 9 adds the routes to
``poll_the_pages``.
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

CHILD = audit.HERE / "instructions_audit_child.py"
MEMORY_SENTINEL = "MEMORY-SENTINEL-DO-NOT-READ"


def _put(path: Path, text: str = audit.DECOY_TEXT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def decoys(tmp_path: Path) -> audit.Decoys:
    world = audit.build_decoys(tmp_path)
    managed = world.root / "managed"
    _put(managed / "CLAUDE.md", "# managed\n")
    _put(managed / ".claude" / "skills" / "org" / "SKILL.md", "---\nname: org\n---\n")
    skill = "---\nname: {}\ndescription: d\n---\nBody.\n"
    _put(world.config / "skills" / "mine" / "SKILL.md", skill.format("mine"))
    _put(world.config / "commands" / "go.md", "---\ndescription: d\n---\n")
    _put(world.project / ".claude" / "skills" / "p" / "SKILL.md", skill.format("p"))
    _put(
        world.project / "sub" / ".claude" / "skills" / "n" / "SKILL.md",
        skill.format("n"),
    )
    _put(world.project / ".claude" / "commands" / "pc.md", "---\ndescription: d\n---\n")
    _put(world.project / ".claude" / "rules" / "r.md", "---\npaths: a/**\n---\n")
    _put(world.config / "rules" / "ur.md", "# user rule\n")
    # Imports: one inside the roots, one out of them, one at the auto memory file.
    memory = world.listed_folder / "memory" / "MEMORY.md"
    memory.write_text(MEMORY_SENTINEL, encoding="utf-8")
    imports = [
        "@docs/in.md",
        "@../../../outside/dotfiles/CLAUDE.md",
        f"@{memory}",
        "@~/.claude/projects/x/memory/MEMORY.md",
    ]
    _put(world.project / "CLAUDE.md", "# project\n" + "\n".join(imports) + "\n")
    _put(world.project / "docs" / "in.md", "# in\n")
    # Stray files beside the ones the collectors read.
    for stray in (
        world.config / "skills" / "notes.txt",
        world.config / "rules" / "notes.txt",
        world.project / ".claude" / "skills" / "p" / "extra.txt",
        world.outside / "skills" / "evil" / "SKILL.md",
    ):
        _put(stray)
    (world.config / "skills" / "linked").symlink_to(world.outside / "skills")
    return world


def _run(
    world: audit.Decoys, *, listed: bool = True
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    log = world.root / "instruction-reads.log"
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-B",
            str(CHILD),
            str(world.config),
            str(world.home),
            str(world.root / "managed"),
            str(world.project) if listed else "-",
            str(world.outside / "skills"),
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
    assert counts["skills"] >= 4
    assert counts["instructions"] >= 5
    assert counts["rules"] == 3  # the decoy tree has one user rule of its own
    scope = _scope(decoys)
    audit.assert_reads_allowed(entries, decoys, scope=scope)
    own = [(e, p) for e, p in entries if p.startswith(str(decoys.root) + os.sep)]
    assert own, "the collectors read nothing inside the scope"
    for event, path in own:
        assert scope.allows(path, folder=event != "open"), (event, path)


def test_the_audit_sees_the_files_it_should(decoys: audit.Decoys) -> None:
    entries, _counts = _run(decoys)
    opened = {path for event, path in entries if event == "open"}
    for wanted in (
        decoys.config / "CLAUDE.md",
        decoys.config / "skills" / "mine" / "SKILL.md",
        decoys.config / "commands" / "go.md",
        decoys.config / "rules" / "ur.md",
        decoys.root / "managed" / "CLAUDE.md",
        decoys.root / "managed" / ".claude" / "skills" / "org" / "SKILL.md",
        decoys.outer / "CLAUDE.md",
        decoys.outer / "CLAUDE.local.md",
        decoys.root / "work" / "CLAUDE.md",
        decoys.project / "CLAUDE.md",
        decoys.project / "docs" / "in.md",
        decoys.project / "sub" / "CLAUDE.md",
        decoys.project / "sub" / ".claude" / "skills" / "n" / "SKILL.md",
        decoys.project / ".claude" / "rules" / "r.md",
    ):
        assert str(wanted) in opened, wanted


def test_no_decoy_and_no_auto_memory_is_opened_or_listed(decoys: audit.Decoys) -> None:
    entries, _counts = _run(decoys)
    for decoy in decoys.decoys:
        hit = [
            p
            for _e, p in entries
            if p == str(decoy) or p.startswith(str(decoy) + os.sep)
        ]
        assert hit == [], decoy
    paths = [p for _e, p in entries]
    assert not any("MEMORY.md" in p or "/memory" in p for p in paths)
    assert not any(p.endswith("notes.txt") or p.endswith("extra.txt") for p in paths)
    # The symlinked skills folder and the outside plugin path are never entered.
    assert not any(p.startswith(str(decoys.outside / "skills")) for p in paths)


def test_an_unlisted_project_opens_nothing_under_it(decoys: audit.Decoys) -> None:
    entries, counts = _run(decoys, listed=False)
    assert counts["skills"] >= 2
    paths = [p for _e, p in entries]
    assert not any(p.startswith(str(decoys.project) + os.sep) for p in paths)
    assert not any(p.startswith(str(decoys.unlisted)) for p in paths)
    assert not any(p.startswith(str(decoys.outer)) for p in paths)
    audit.assert_reads_allowed(entries, decoys, scope=_scope(decoys, listed=False))


def test_an_import_out_of_the_roots_is_never_opened(decoys: audit.Decoys) -> None:
    entries, _counts = _run(decoys)
    paths = [p for _e, p in entries]
    assert str(decoys.followed) not in paths
    assert not any(p.startswith(str(decoys.outside)) for p in paths)


def test_the_audit_fails_when_a_read_leaves_the_scope(decoys: audit.Decoys) -> None:
    stray = [("open", str(decoys.outer / "secrets.txt"))]
    with pytest.raises(pytest.fail.Exception):
        audit.assert_reads_allowed(stray, decoys, scope=_scope(decoys))

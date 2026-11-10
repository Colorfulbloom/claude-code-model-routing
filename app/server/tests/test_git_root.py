"""Tests for ``git_root``: the git root found by ``lstat`` of ``.git`` alone."""

import os
import subprocess
from pathlib import Path

import pytest

import git_root


def _tree(tmp_path: Path) -> tuple[Path, Path]:
    """A repo root with a project two levels down."""
    root = tmp_path.resolve() / "repo"
    project = root / "apps" / "web"
    project.mkdir(parents=True)
    return root, project


def test_a_git_folder_makes_its_parent_the_root(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)
    (root / ".git").mkdir()
    assert git_root.find_root(project) == root
    assert git_root.find_root(root) == root


def test_the_nearest_git_wins(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)
    (root / ".git").mkdir()
    (project.parent / ".git").mkdir()
    assert git_root.find_root(project) == project.parent


def test_a_git_file_makes_the_worktree_folder_the_root(tmp_path: Path) -> None:
    # A linked worktree. The gitdir chain is not followed, so the worktree folder is
    # the root and the main checkout is never touched.
    root, project = _tree(tmp_path)
    (root / ".git").write_text("gitdir: /work/main/.git/worktrees/x\n")
    assert git_root.find_root(project) == root


def test_no_repo_gives_none(tmp_path: Path) -> None:
    _root, project = _tree(tmp_path)
    assert git_root.find_root(project) is None
    assert git_root.local_settings_path(project) is None


def test_a_git_symlink_is_not_trusted(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)
    (root / ".git").symlink_to(tmp_path)
    assert git_root.find_root(project) is None


def test_a_git_fifo_is_not_trusted(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)
    os.mkfifo(root / ".git")
    assert git_root.find_root(project) is None


def test_a_project_path_through_a_symlink_starts_from_its_real_path(
    tmp_path: Path,
) -> None:
    root, project = _tree(tmp_path)
    (root / ".git").mkdir()
    link = tmp_path / "link"
    link.symlink_to(project)
    assert git_root.find_root(link) == root


def test_an_unusable_path_gives_none() -> None:
    assert git_root.find_root("bad\0path") is None


def test_the_local_file_is_the_root_one_when_the_root_differs(
    tmp_path: Path,
) -> None:
    root, project = _tree(tmp_path)
    (root / ".git").mkdir()
    assert git_root.local_settings_path(project) == (
        root / ".claude" / "settings.local.json"
    )


def test_a_project_at_its_root_keeps_its_own_file(tmp_path: Path) -> None:
    root, _project = _tree(tmp_path)
    (root / ".git").mkdir()
    assert git_root.local_settings_path(root) is None


def test_a_root_that_is_the_home_folder_keeps_the_project_file(
    tmp_path: Path,
) -> None:
    root, project = _tree(tmp_path)
    (root / ".git").mkdir()
    assert git_root.local_settings_path(project, home=root) is None
    assert git_root.local_settings_path(project, home=tmp_path / "other") is not None


def test_a_root_owned_by_another_user_is_not_trusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, project = _tree(tmp_path)
    (root / ".git").mkdir()
    monkeypatch.setattr(os, "geteuid", lambda: root.stat().st_uid + 1)
    assert git_root.local_settings_path(project) is None


def test_it_agrees_with_git_on_a_real_repo(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)
    subprocess.run(  # noqa: S603
        ["git", "init", "-q", str(root)],  # noqa: S607
        check=True,
        capture_output=True,
        timeout=60,
    )
    assert git_root.find_root(project) == root


def test_it_runs_no_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project = _tree(tmp_path)
    (root / ".git").mkdir()

    def refuse(*_args: object, **_kwargs: object) -> None:
        pytest.fail("a process was started")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert git_root.local_settings_path(project) is not None

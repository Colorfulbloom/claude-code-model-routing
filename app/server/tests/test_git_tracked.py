"""``git_tracked.is_tracked``: the answer, the cache and the hardening (m6-build.md 2).

A project's own ``.git/config`` is not trusted. A repo whose config sets
``core.fsmonitor`` to a program must not run it when Bar Tab asks whether a file is
tracked. The control runs ``git status`` over the same repo with a bare environment and
checks that the program does fire there, so the test can't pass because the hook was
never going to run.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_api_helpers import git_available, init_repo

import git_tracked

pytestmark = pytest.mark.skipif(not git_available(), reason="needs git")


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    git_tracked.clear_cache()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    (repo / ".claude" / "settings.local.json").write_text("{}\n", encoding="utf-8")
    init_repo(repo, [".claude/settings.json"])
    return repo


def test_a_staged_file_is_tracked_and_an_unstaged_one_is_not(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    assert git_tracked.is_tracked(repo / ".claude" / "settings.json") is True
    assert git_tracked.is_tracked(repo / ".claude" / "settings.local.json") is False


def test_a_file_that_is_not_there_is_not_tracked_and_starts_no_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def refuse(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", refuse)
    assert git_tracked.is_tracked(tmp_path / "nothing.json") is False
    assert git_tracked.is_tracked(tmp_path) is False  # a folder is not a file
    assert calls == []


def test_a_folder_outside_any_repo_is_not_tracked(tmp_path: Path) -> None:
    plain = tmp_path / "plain" / "settings.json"
    plain.parent.mkdir()
    plain.write_text("{}\n", encoding="utf-8")
    assert git_tracked.is_tracked(plain) is False


def test_a_link_into_a_repo_asks_that_repo(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    link = tmp_path / "link.json"
    link.symlink_to(repo / ".claude" / "settings.json")
    assert git_tracked.is_tracked(link) is True


def test_no_git_on_the_path_is_not_tracked(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    nothing = tmp_path / "empty-bin"
    nothing.mkdir()
    assert (
        git_tracked.is_tracked(
            repo / ".claude" / "settings.json", path_env=str(nothing)
        )
        is False
    )


def test_the_answer_is_cached_until_the_file_or_the_index_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    target = repo / ".claude" / "settings.local.json"
    real = subprocess.run
    calls: list[int] = []

    def counting(*args: object, **kwargs: object) -> object:
        command = args[0]
        if isinstance(command, list) and "ls-files" in command:
            calls.append(1)  # init_repo's own git calls are not the code under test
        return real(*args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", counting)
    assert git_tracked.is_tracked(target) is False
    assert git_tracked.is_tracked(target) is False
    assert len(calls) == 1
    init_repo(repo, [".claude/settings.local.json"])  # git add changes the index
    assert git_tracked.is_tracked(target) is True
    assert len(calls) == 2


def test_the_child_gets_a_fixed_argument_list_and_a_bare_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    seen: dict[str, object] = {}
    real = subprocess.run

    def spy(command: list[str], **kwargs: object) -> object:
        seen["command"] = command
        seen["env"] = kwargs["env"]
        seen["timeout"] = kwargs["timeout"]
        seen["stdin"] = kwargs["stdin"]
        return real(command, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", spy)
    monkeypatch.setenv("GIT_DIR", "/work/not-a-repo")  # must not reach the child
    monkeypatch.setenv("GIT_SSH_COMMAND", "false")
    assert git_tracked.is_tracked(repo / ".claude" / "settings.json") is True
    command = seen["command"]
    assert isinstance(command, list)
    assert command[1:] == [
        "--no-lazy-fetch",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-C",
        str(repo / ".claude"),
        "ls-files",
        "--error-unmatch",
        "--",
        "settings.json",
    ]
    env = seen["env"]
    assert isinstance(env, dict)
    env = cast("dict[str, str]", env)
    assert set(env) <= {"PATH", "HOME", "GIT_NO_LAZY_FETCH"}
    assert env["GIT_NO_LAZY_FETCH"] == "1"
    assert seen["timeout"] == git_tracked.TIMEOUT_SECONDS == 2.0
    assert seen["stdin"] == subprocess.DEVNULL


def test_a_repo_config_that_sets_fsmonitor_runs_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "hook.sh"
    hook.write_text(f'#!/bin/sh\necho ran >> "{marker}"\nexit 0\n', encoding="utf-8")
    hook.chmod(0o755)
    config = repo / ".git" / "config"
    config.write_text(
        config.read_text(encoding="utf-8") + f'[core]\n\tfsmonitor = "{hook}"\n',
        encoding="utf-8",
    )
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    # control: an unhardened git over the same repo does run the program
    subprocess.run(  # noqa: S603 - fixed arguments over a throwaway repo
        [shutil.which("git") or "git", "-C", str(repo), "status", "-s"],
        env=env,
        check=False,
        capture_output=True,
        timeout=20,
    )
    if not marker.exists():
        pytest.skip("this git does not run core.fsmonitor for status")
    marker.unlink()
    # the hardened call over the same repo runs nothing, and still answers
    assert (
        git_tracked.is_tracked(repo / ".claude" / "settings.json", home=str(tmp_path))
        is True
    )
    assert not marker.exists()
    assert (
        git_tracked.is_tracked(
            repo / ".claude" / "settings.local.json", home=str(tmp_path)
        )
        is False
    )
    assert not marker.exists()


def test_a_hook_the_repo_names_runs_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    marker = tmp_path / "hook-ran"
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    for name in (
        "post-index-change",
        "pre-commit",
        "post-checkout",
        "reference-transaction",
    ):
        hook = hooks / name
        hook.write_text(
            f'#!/bin/sh\necho {name} >> "{marker}"\nexit 0\n', encoding="utf-8"
        )
        hook.chmod(0o755)
    git_tracked.clear_cache()
    assert git_tracked.is_tracked(repo / ".claude" / "settings.json") is True
    assert not marker.exists()

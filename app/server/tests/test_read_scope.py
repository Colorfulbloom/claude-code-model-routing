"""Tests for ``read_scope`` on the decoy tree from ``read_audit_helpers``."""

import builtins
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import read_audit_helpers as audit

import read_scope
import setup_contract
from models import UnreadableFile

CAP = setup_contract.FILE_CAP_BYTES
NOT_ROOT = os.geteuid() != 0


@pytest.fixture
def decoys(tmp_path: Path) -> audit.Decoys:
    return audit.build_decoys(tmp_path)


@pytest.fixture
def scope(decoys: audit.Decoys) -> read_scope.Scope:
    return decoys.scope()


def reason(got: object) -> str:
    assert isinstance(got, UnreadableFile), got
    return got.reason


# ---------------------------------------------------------------- what is allowed


def test_the_allowed_files_are_allowed(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    for path in decoys.allowed_files:
        assert scope.allows(path), path


def test_no_decoy_is_allowed(decoys: audit.Decoys, scope: read_scope.Scope) -> None:
    for path in decoys.decoys:
        assert not scope.allows(path), path
        assert not scope.allows(path, folder=True), path


def test_the_roots_are_the_config_the_project_managed_and_plugins(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    roots = set(scope.roots)
    assert str(decoys.config) in roots
    assert str(decoys.project) in roots
    assert str(decoys.config / "plugins") in roots
    assert str(decoys.config / "projects") not in roots
    # Not a root: the git root, the home folder, and the unlisted project.
    for other in (decoys.outer, decoys.home, decoys.unlisted):
        assert str(other) not in roots


def test_an_unlisted_project_has_no_project_root(decoys: audit.Decoys) -> None:
    scope = decoys.scope(listed=False)
    assert str(decoys.project) not in scope.roots
    assert not scope.allows(decoys.project / ".claude" / "settings.json")
    assert not scope.allows(decoys.outer / "CLAUDE.md")
    assert not scope.allows(decoys.outer / ".claude" / "settings.local.json")
    assert scope.allows(decoys.config / "settings.json")
    assert reason(read_scope.read_bytes(scope, decoys.project / "CLAUDE.md", CAP)) == (
        "outside_scope"
    )


def test_memory_files_are_never_allowed(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    memory = decoys.listed_folder / "memory"
    assert not scope.allows(memory, folder=True)
    assert not scope.allows(memory / "MEMORY.md")
    assert scope.allows(decoys.listed_folder / f"{audit.SID_LISTED}.jsonl")
    assert reason(read_scope.read_bytes(scope, memory / "MEMORY.md", CAP)) == (
        "outside_scope"
    )
    assert reason(read_scope.list_dir(scope, memory)) == "outside_scope"


def test_a_link_to_a_memory_file_is_refused(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    link = decoys.project / "memory-link.md"
    assert link.is_symlink()
    assert reason(read_scope.read_bytes(scope, link, CAP)) == "outside_scope"


def test_every_ancestor_may_hold_only_the_two_claude_md_names(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    for ancestor in (decoys.outer, decoys.outer.parent, decoys.root, Path("/")):
        for name in ("CLAUDE.md", "CLAUDE.local.md"):
            assert scope.allows(ancestor / name), ancestor / name
        assert not scope.allows(ancestor / "CLAUDE.txt")
        assert not scope.allows(ancestor / "secrets.txt")
        assert not scope.allows(ancestor / ".claude" / "settings.json")


def test_only_the_git_root_local_file_is_allowed_above_the_project(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    assert scope.allows(decoys.outer / ".claude" / "settings.local.json")
    assert not scope.allows(decoys.outer.parent / ".claude" / "settings.local.json")
    assert not scope.allows(decoys.outer / ".claude" / "settings.json")


def test_without_a_git_root_there_is_no_local_file_above(
    decoys: audit.Decoys,
) -> None:
    (decoys.outer / ".git").rmdir()
    scope = decoys.scope()
    assert not scope.allows(decoys.outer / ".claude" / "settings.local.json")
    assert scope.allows(decoys.outer / "CLAUDE.md")


def test_the_home_settings_file_is_the_one_allowed_file_there(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    assert scope.claude_json_path() == decoys.home / ".claude.json"
    assert scope.allows(decoys.home / ".claude.json")
    for name in (".ssh/id_rsa", "id_ed25519", "notes.txt", ".claude.json.bak"):
        assert not scope.allows(decoys.home / name), name


def test_the_default_config_folder_never_reads_its_own_copy(
    decoys: audit.Decoys,
) -> None:
    inside = decoys.config / ".claude.json"
    inside.write_text("{}\n")
    scope = decoys.scope()
    # The copy sits inside the config root, which the scope allows like any file
    # there, but the reader never picks it.
    assert scope.claude_json_path() == decoys.home / ".claude.json"


def test_a_moved_config_folder_uses_its_own_file_only(
    decoys: audit.Decoys, tmp_path: Path
) -> None:
    moved = tmp_path / "moved-config"
    moved.mkdir()
    ctx = setup_contract.SetupContext(
        project_key="p",
        config_dir=moved,
        home=decoys.home,
        project_dir=None,
        managed_dir=None,
    )
    scope = read_scope.Scope(ctx)
    assert scope.claude_json_path() == moved / ".claude.json"
    assert scope.allows(moved / ".claude.json")
    assert not scope.allows(decoys.home / ".claude.json")


def test_with_no_home_the_config_folder_file_is_the_one(
    decoys: audit.Decoys,
) -> None:
    ctx = setup_contract.SetupContext(
        project_key="p",
        config_dir=decoys.config,
        home=None,
        project_dir=None,
        managed_dir=None,
    )
    assert read_scope.Scope(ctx).claude_json_path() == decoys.config / ".claude.json"


def test_dot_dot_tricks_are_caught(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    trick = decoys.project / ".claude" / ".." / ".." / ".." / "secrets.txt"
    assert not scope.allows(trick)
    assert reason(read_scope.read_bytes(scope, trick, CAP)) == "outside_scope"
    up = decoys.config / "agents" / ".." / ".." / "id_ed25519"
    assert not scope.allows(up)
    inside = decoys.project / "sub" / ".." / "CLAUDE.md"
    assert scope.allows(inside)
    assert read_scope.read_bytes(scope, inside, CAP) == b"# project\n"


def test_a_dot_dot_through_a_symlinked_folder_is_not_collapsed_into_scope(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    # linked-folder points outside, so linked-folder/../CLAUDE.md is a file next to
    # the target, not the project's. It is checked as the path that is opened.
    tricky = decoys.project / "linked-folder" / ".." / "CLAUDE.md"
    got = read_scope.read_bytes(scope, tricky, CAP)
    assert got == b"# project\n"  # abspath collapses it to the project's own file
    assert not scope.allows(decoys.outside / "linked-target" / "evil.md")


def test_a_path_that_cannot_be_checked_is_refused(scope: read_scope.Scope) -> None:
    assert not scope.allows("bad\0path")
    assert reason(read_scope.read_bytes(scope, "bad\0path", CAP)) == "outside_scope"


# ---------------------------------------------------------------- symlinks


def test_a_single_file_symlink_out_of_the_roots_is_followed(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    link = decoys.project / "linked-file.md"
    access = scope.access(link)
    assert access is not None
    assert access.followed_out is True
    assert access.path == str(decoys.followed)
    snapshot = read_scope.read_snapshot(scope, link, CAP)
    assert isinstance(snapshot, read_scope.Snapshot)
    assert snapshot.data == b"# from a dotfiles repo\n"
    assert snapshot.real_path == str(decoys.followed)
    assert read_scope.read_text(scope, link, CAP) == "# from a dotfiles repo\n"


def test_a_plain_file_has_no_real_path(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    snapshot = read_scope.read_snapshot(scope, decoys.project / "CLAUDE.md", CAP)
    assert isinstance(snapshot, read_scope.Snapshot)
    assert snapshot.real_path is None


def test_a_symlinked_folder_out_of_the_roots_is_not_entered(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    for link in (
        decoys.project / "linked-folder",
        decoys.project / ".claude" / "agents" / "linked",
    ):
        assert reason(read_scope.list_dir(scope, link)) == "outside_scope"
        assert reason(read_scope.read_bytes(scope, link / "evil.md", CAP)) == (
            "outside_scope"
        )
        walked = read_scope.walk(scope, link)
        assert [reason(row) for row in walked.unreadable] == ["outside_scope"]
        assert walked.hits == []


def test_a_symlink_to_a_folder_is_not_read_as_a_file(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    assert reason(
        read_scope.read_bytes(scope, decoys.project / "linked-folder", CAP)
    ) == ("outside_scope")


def test_a_symlink_inside_the_roots_to_another_root_is_plain(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    link = decoys.project / "to-settings.json"
    link.symlink_to(decoys.config / "settings.json")
    access = scope.access(link)
    assert access is not None
    assert access.followed_out is False
    assert (
        read_scope.read_bytes(scope, link, CAP)
        == (decoys.config / "settings.json").read_bytes()
    )


def test_symlink_target_gives_a_display_path(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    assert (
        read_scope.symlink_target(scope, decoys.project / "linked-file.md")
        == "~/outside/dotfiles/CLAUDE.md"
        or read_scope.symlink_target(scope, decoys.project / "linked-file.md")
        == "CLAUDE.md"
    )
    assert read_scope.symlink_target(scope, decoys.project / "CLAUDE.md") is None
    assert read_scope.symlink_target(scope, decoys.project / "missing") is None


# ---------------------------------------------------------------- reading


def test_read_bytes_and_read_text(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    path = decoys.config / "settings.json"
    assert read_scope.read_bytes(scope, path, CAP) == path.read_bytes()
    assert read_scope.read_text(scope, path, CAP) == path.read_text()


def test_a_file_over_the_cap_is_too_large(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    path = decoys.project / "CLAUDE.md"
    assert reason(read_scope.read_bytes(scope, path, 4)) == "too_large"
    assert read_scope.read_bytes(scope, path, len(path.read_bytes())) == (
        path.read_bytes()
    )


def test_a_file_that_grows_past_the_cap_while_read_is_too_large(
    decoys: audit.Decoys, scope: read_scope.Scope, monkeypatch: pytest.MonkeyPatch
) -> None:
    # fstat says the file fits, but it grows before the read ends.
    path = decoys.project / "CLAUDE.md"

    class Small:
        st_mode = stat.S_IFREG | 0o644
        st_size = 1

    def small(_fd: int) -> Small:
        return Small()

    monkeypatch.setattr(os, "fstat", small)
    assert reason(read_scope.read_bytes(scope, path, 4)) == "too_large"


def test_a_missing_file_has_vanished(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    assert reason(read_scope.read_bytes(scope, decoys.project / "nope.md", CAP)) == (
        "vanished"
    )
    assert reason(read_scope.read_text(scope, decoys.project / "nope.md", CAP)) == (
        "vanished"
    )


def test_a_folder_where_a_file_should_be_has_vanished(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    assert reason(read_scope.read_bytes(scope, decoys.project / "sub", CAP)) == (
        "vanished"
    )


def test_a_pipe_is_not_read_and_does_not_block(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    pipe = decoys.project / "pipe.md"
    os.mkfifo(pipe)
    assert reason(read_scope.read_bytes(scope, pipe, CAP)) == "vanished"


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_file_without_permission_is_a_permission_failure(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    path = decoys.project / "CLAUDE.md"
    path.chmod(0)
    try:
        assert reason(read_scope.read_bytes(scope, path, CAP)) == "permission"
        assert reason(read_scope.read_text(scope, path, CAP)) == "permission"
    finally:
        path.chmod(0o644)


def test_text_that_is_not_utf8_is_not_utf8(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    path = decoys.project / "bad.md"
    path.write_bytes(b"ok \xff\xfe broken")
    assert read_scope.read_bytes(scope, path, CAP) == b"ok \xff\xfe broken"
    assert reason(read_scope.read_text(scope, path, CAP)) == "not_utf8"


def test_a_refusal_says_where_and_why(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    got = read_scope.read_bytes(scope, decoys.outer / "secrets.txt", CAP)
    assert isinstance(got, UnreadableFile)
    assert got.reason == "outside_scope"
    assert got.full_path == str(decoys.outer / "secrets.txt")
    assert got.file == "secrets.txt"  # outside every known folder: the name only
    assert got.problem is None
    assert got.scope is None


def test_a_plugin_install_path_refusal_has_its_own_reason(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    path = decoys.outside / "plugin-elsewhere" / "plugin.json"
    assert reason(read_scope.read_bytes(scope, path, CAP, plugin=True)) == (
        "plugin_outside_plugins"
    )
    assert reason(read_scope.read_text(scope, path, CAP, plugin=True)) == (
        "plugin_outside_plugins"
    )
    assert reason(read_scope.list_dir(scope, path.parent, plugin=True)) == (
        "plugin_outside_plugins"
    )
    assert reason(read_scope.read_bytes(scope, path, CAP)) == "outside_scope"
    # An install folder inside <config>/plugins/ reads fine.
    inside = decoys.config / "plugins" / "cache" / "ok" / "plugin.json"
    assert read_scope.read_bytes(scope, inside, CAP, plugin=True) == inside.read_bytes()


def test_the_display_scope_and_full_path_of_a_failure(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    cases = {
        decoys.project / "gone.md": ("gone.md", "project"),
        decoys.project / ".claude" / "settings.local.json": (
            ".claude/settings.local.json",
            "project_local",
        ),
        decoys.outer / ".claude" / "settings.local.json": (
            "../.claude/settings.local.json",
            "project_local",
        ),
        decoys.config / "agents" / "gone.md": ("~/.claude/agents/gone.md", "user"),
        decoys.config / "plugins" / "cache" / "x.json": (
            "~/.claude/plugins/cache/x.json",
            "plugin",
        ),
        decoys.home / ".claude.json": ("~/.claude.json", None),
        decoys.outer / "CLAUDE.md": ("../CLAUDE.md", None),
        decoys.outer.parent / "CLAUDE.local.md": ("../../CLAUDE.local.md", None),
    }
    for path, (shown, where) in cases.items():
        row = scope.unreadable(path, "vanished")
        assert (row.file, row.scope, row.full_path) == (shown, where, str(path)), path


def test_the_managed_folder_shows_by_its_name_and_is_managed(
    decoys: audit.Decoys,
) -> None:
    managed = decoys.root / "managed" / "ClaudeCode"
    ctx = setup_contract.SetupContext(
        project_key="p",
        config_dir=decoys.config,
        home=decoys.home,
        project_dir=decoys.project,
        managed_dir=managed,
    )
    scope = read_scope.Scope(ctx)
    row = scope.unreadable(managed / "managed-settings.json", "permission")
    assert (row.file, row.scope) == ("ClaudeCode/managed-settings.json", "managed")
    assert scope.allows(managed / "managed-settings.d" / "a.json")


# ---------------------------------------------------------------- the parse retry


def test_read_text_retries_once_when_the_parse_fails(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    path = decoys.project / "mid-write.json"
    path.write_text("{ torn")
    calls: list[str] = []

    def parse(text: str) -> object:
        calls.append(text)
        if len(calls) == 1:
            path.write_text('{"fixed": true}')  # the writer finishes
            raise ValueError(text)
        return text

    # The first parse fails, the file is read again, and the new text comes back.
    assert read_scope.read_text(scope, path, CAP, parse=parse) == '{"fixed": true}'
    assert calls == ["{ torn"]


def test_read_text_returns_the_second_text_even_when_it_still_fails(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    path = decoys.project / "broken.json"
    path.write_text("{ nope")
    seen: list[str] = []

    def parse(text: str) -> object:
        seen.append(text)
        raise ValueError(text)

    assert read_scope.read_text(scope, path, CAP, parse=parse) == "{ nope"
    assert len(seen) == 1  # the second text is returned, not parsed again


def test_read_text_with_a_passing_parse_reads_once(
    decoys: audit.Decoys, scope: read_scope.Scope, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = decoys.config / "settings.json"
    opens: list[str] = []
    real_open = os.open

    def counting(file: str, *args: int, **kwargs: int) -> int:
        opens.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(os, "open", counting)
    assert read_scope.read_text(scope, path, CAP, parse=lambda t: t) == path.read_text()
    assert opens.count(str(path)) == 1


# ---------------------------------------------------------------- listing


def test_list_dir_gives_sorted_names(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    names = read_scope.list_dir(scope, decoys.config / "agents")
    assert names == ["user-agent.md"]
    top = read_scope.list_dir(scope, decoys.config)
    assert isinstance(top, list)
    assert top == sorted(top)
    assert "projects" in top  # names only; memory is under it, not listed here


def test_list_dir_of_a_missing_or_outside_folder(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    assert reason(read_scope.list_dir(scope, decoys.config / "nope")) == "vanished"
    assert reason(read_scope.list_dir(scope, decoys.config / "settings.json")) == (
        "vanished"
    )
    assert reason(read_scope.list_dir(scope, decoys.outer)) == "outside_scope"
    assert reason(read_scope.list_dir(scope, decoys.unlisted)) == "outside_scope"


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_folder_that_will_not_list_is_unlistable(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    folder = decoys.project / "sub"
    folder.chmod(0)
    try:
        assert reason(read_scope.list_dir(scope, folder)) == "folder_unlistable"
    finally:
        folder.chmod(0o755)


# ---------------------------------------------------------------- the walk


def _tree(base: Path, names: list[str]) -> None:
    for name in names:
        (base / name).mkdir(parents=True, exist_ok=True)


def test_the_walk_finds_nested_files_and_skills_and_nothing_else(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    project = decoys.project
    (project / "sub" / "CLAUDE.local.md").write_text("x")
    (project / "sub" / "notes.txt").write_text("decoy")
    skills = project / "pkg" / ".claude" / "skills" / "a"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("x")
    (project / ".claude" / "skills").mkdir()
    walked = read_scope.walk(scope, project)
    got = [(hit.kind, os.path.relpath(hit.path, project)) for hit in walked.hits]
    assert got == [
        ("skills", ".claude/skills"),
        ("claude_md", "CLAUDE.md"),
        ("skills", "pkg/.claude/skills"),
        ("claude_local_md", "sub/CLAUDE.local.md"),
        ("claude_md", "sub/CLAUDE.md"),
    ]
    assert walked.stopped is False
    assert walked.unreadable == []
    assert walked.folders == len(walked.touched)


def test_the_walk_skips_dot_folders_skip_names_and_symlinked_folders(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    project = decoys.project
    for name in (".git", ".venv", "node_modules", "vendor", "dist", "build"):
        (project / name).mkdir()
        (project / name / "CLAUDE.md").write_text("skipped")
    walked = read_scope.walk(scope, project)
    assert [os.path.relpath(h.path, project) for h in walked.hits] == [
        "CLAUDE.md",
        "sub/CLAUDE.md",
    ]
    listed = {os.path.relpath(p, project) for p in walked.touched}
    assert listed == {".", "sub"}  # linked-folder is a symlink and is never entered


def test_the_walk_does_not_list_inside_a_claude_folder(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    (decoys.project / ".claude" / "worktrees" / "big").mkdir(parents=True)
    walked = read_scope.walk(scope, decoys.project)
    assert all(".claude" not in p for p in walked.touched)


def test_the_walk_stops_at_the_depth_cap(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    deep = decoys.project
    for level in range(setup_contract.WALK_MAX_DEPTH):
        deep = deep / f"d{level}"
        deep.mkdir()
    (deep / "CLAUDE.md").write_text("at the cap")
    walked = read_scope.walk(scope, decoys.project)
    assert not walked.stopped
    assert str(deep / "CLAUDE.md") in [hit.path for hit in walked.hits]
    (deep / "one-more").mkdir()
    walked = read_scope.walk(scope, decoys.project)
    assert walked.stopped is True


def test_the_walk_stops_at_the_folder_cap(
    decoys: audit.Decoys, scope: read_scope.Scope, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(decoys.project, [f"f{n}" for n in range(10)])
    monkeypatch.setattr(read_scope, "WALK_MAX_FOLDERS", 4)
    walked = read_scope.walk(scope, decoys.project)
    assert walked.stopped is True
    assert walked.folders == 4


def test_the_walk_of_a_folder_outside_the_roots_reads_nothing(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    walked = read_scope.walk(scope, decoys.unlisted)
    assert walked.hits == []
    assert walked.folders == 0
    assert [reason(r) for r in walked.unreadable] == ["outside_scope"]
    walked = read_scope.walk(scope, decoys.outside / "plugin-elsewhere", plugin=True)
    assert [reason(r) for r in walked.unreadable] == ["plugin_outside_plugins"]


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_the_walk_reports_a_folder_it_cannot_list_and_goes_on(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    (decoys.project / "locked").mkdir()
    (decoys.project / "locked").chmod(0)
    try:
        walked = read_scope.walk(scope, decoys.project)
    finally:
        (decoys.project / "locked").chmod(0o755)
    assert [reason(r) for r in walked.unreadable] == ["folder_unlistable"]
    assert [os.path.relpath(h.path, decoys.project) for h in walked.hits] == [
        "CLAUDE.md",
        "sub/CLAUDE.md",
    ]


def test_the_walk_opens_no_file(
    decoys: audit.Decoys, scope: read_scope.Scope, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        pytest.fail("the walk opened a file")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(os, "open", refuse)
    assert read_scope.walk(scope, decoys.project).hits


# ---------------------------------------------------------------- the signature


def test_the_signature_is_stable_and_order_free(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    paths = [decoys.config / "settings.json", decoys.project / "CLAUDE.md"]
    first = read_scope.stat_signature(scope, paths)
    assert first == read_scope.stat_signature(scope, reversed(paths))
    assert first == read_scope.stat_signature(scope, set(paths))
    assert first != read_scope.stat_signature(scope, paths[:1])


def test_the_signature_changes_when_a_file_changes_appears_or_goes(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    path = decoys.project / "CLAUDE.md"
    new = decoys.project / "new.md"
    before = read_scope.stat_signature(scope, [path, new])
    new.write_text("x")
    appeared = read_scope.stat_signature(scope, [path, new])
    assert appeared != before
    new.write_text("xy")
    assert read_scope.stat_signature(scope, [path, new]) != appeared
    new.unlink()
    assert read_scope.stat_signature(scope, [path, new]) == before


def test_the_signature_follows_a_link_to_its_target(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    link = decoys.project / "linked-file.md"
    before = read_scope.stat_signature(scope, [link])
    decoys.followed.write_text("# changed in the dotfiles repo, longer\n")
    assert read_scope.stat_signature(scope, [link]) != before


def test_the_signature_never_opens_and_never_stats_outside(
    decoys: audit.Decoys, scope: read_scope.Scope, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        pytest.fail("the signature opened a file")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(os, "open", refuse)
    stat_calls: list[str] = []
    real_lstat = os.lstat

    def watching(path: str, **kwargs: int) -> os.stat_result:
        stat_calls.append(str(path))
        return real_lstat(path, **kwargs)

    monkeypatch.setattr(os, "lstat", watching)
    outside = decoys.outer / "secrets.txt"
    one = read_scope.stat_signature(scope, [outside, decoys.project / "CLAUDE.md"])
    assert str(outside) not in stat_calls
    outside.write_text("changed")
    assert (
        read_scope.stat_signature(scope, [outside, decoys.project / "CLAUDE.md"]) == one
    )


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_the_signature_of_a_path_it_cannot_stat_is_a_mark_not_an_error(
    decoys: audit.Decoys, scope: read_scope.Scope
) -> None:
    folder = decoys.project / "sub"
    folder.chmod(0)
    try:
        read_scope.stat_signature(scope, [folder / "CLAUDE.md"])
    finally:
        folder.chmod(0o755)

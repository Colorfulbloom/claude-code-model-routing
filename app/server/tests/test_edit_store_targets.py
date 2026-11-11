"""The write core's allowlist, link handling and file refusals (m6-build.md 3.3, 3.4).

Every test runs under ``edit_config`` and ``edit_project``, or a folder under
``tmp_path`` made the same way, and none sits in a git work tree. The write guard hook
is not installed in this process, so ``STATE.edits`` is set for the test and ``permit``
works. ``test_edit_store_guard.py`` runs a save under the real hook in a subprocess.
"""

# pyright: reportPrivateUsage=false
# These tests reach into the writer's helpers to set up a state or read one.

# ruff: noqa: PTH104, PTH105, PTH106, PTH116, PTH211
# The swap tests rename, replace and link files with the plain os calls the race needs.

import errno
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_helpers import PROJECT_KEY, World, make_world, write_json

import edit_store
import write_guard
from edit_store import EditContext, Refused


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


@pytest.fixture
def world(edit_config: Path, edit_project: Path) -> World:
    return make_world(edit_config, edit_project)


def refusal(world: World, *, scope: str = "project", value: str = "high") -> Refused:
    """Save a value that must be refused, and return the refusal."""
    target = world.target(scope)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(Refused) as caught:
        world.store.save(target, world.save_body(value, scope))  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    return caught.value


def settings(world: World, text: str) -> Path:
    """Write the project's settings file."""
    return write_json(world.path(), text)


def no_store_folder(world: World) -> bool:
    """True when nothing was made under the backups folder."""
    return not world.backups.exists() or not any(world.backups.iterdir())


# Registry


def test_a_project_has_three_settings_targets_in_scope_order(world: World) -> None:
    found = world.targets()
    assert [(t.scope, t.leftover) for t in found] == [
        ("user", False),
        ("project", False),
        ("local", False),
    ]
    assert found[0].display_path == str(world.config / "settings.json")
    assert found[1].display_path == str(world.project / ".claude" / "settings.json")
    assert found[2].display_path == str(
        world.project / ".claude" / "settings.local.json"
    )
    assert "project" in repr(found[1])


def test_no_project_means_the_user_file_alone(world: World) -> None:
    found = edit_store.settings_targets(world.ctx, None)
    assert [t.scope for t in found] == ["user"]
    with pytest.raises(Refused) as caught:
        edit_store.settings_target(world.ctx, None, "project")
    assert caught.value.code == "not_editable"


def test_a_target_can_not_be_built_outside_the_registry() -> None:
    with pytest.raises(TypeError):
        edit_store.Target(object(), "user", "/work/cfg", (), "settings.json")


def test_an_unknown_scope_is_not_editable(world: World) -> None:
    with pytest.raises(Refused) as caught:
        edit_store.settings_target(world.ctx, world.project, "managed")  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert caught.value.code == "not_editable"


def test_the_local_file_sits_at_the_git_root_and_the_start_folder_is_a_leftover(
    edit_config: Path, tmp_path: Path
) -> None:
    repo = (tmp_path / "repo").resolve()
    (repo / ".git").mkdir(parents=True)
    sub = repo / "sub"
    sub.mkdir()
    world = make_world(edit_config, sub)
    found = world.targets()
    assert [(t.scope, t.leftover) for t in found] == [
        ("user", False),
        ("project", False),
        ("local", False),
        ("local", True),
    ]
    assert found[2].display_path == str(repo / ".claude" / "settings.local.json")
    assert found[3].display_path == str(sub / ".claude" / "settings.local.json")
    assert (
        world.target("local") is found[2]
        or world.target("local").display_path == found[2].display_path
    )


def test_before_claude_code_2_1_211_the_local_file_stays_in_the_project(
    edit_config: Path, tmp_path: Path
) -> None:
    repo = (tmp_path / "repo").resolve()
    (repo / ".git").mkdir(parents=True)
    sub = repo / "sub"
    sub.mkdir()
    old = EditContext(
        config_dir=edit_config, home=edit_config.parent, claude_version="2.1.100"
    )
    found = edit_store.settings_targets(old, sub)
    assert [(t.scope, t.leftover) for t in found] == [
        ("user", False),
        ("project", False),
        ("local", False),
    ]
    assert found[2].display_path == str(sub / ".claude" / "settings.local.json")
    new = EditContext(
        config_dir=edit_config, home=edit_config.parent, claude_version="2.1.211"
    )
    assert len(edit_store.settings_targets(new, sub)) == 4


def test_a_leftover_local_file_is_never_written_by_a_save(
    edit_config: Path, tmp_path: Path
) -> None:
    repo = (tmp_path / "repo").resolve()
    (repo / ".git").mkdir(parents=True)
    sub = repo / "sub"
    sub.mkdir()
    world = make_world(edit_config, sub)
    leftover = world.targets()[3]
    body = world.save_body("high", "local", version="x")
    with pytest.raises(Refused) as caught:
        world.store.save(leftover, body)
    assert caught.value.code == "not_editable"


def test_a_save_to_the_wrong_scope_for_its_target_is_not_editable(world: World) -> None:
    body = world.save_body("high", "user", version="x")
    with pytest.raises(Refused) as caught:
        world.store.save(world.target("project"), body)
    assert caught.value.code == "not_editable"


# Resolving


def test_a_plain_file_resolves_to_itself(world: World) -> None:
    resolved = world.store.resolve(world.target("project"))
    assert resolved.real_path == str(world.project / ".claude" / "settings.json")
    assert resolved.target_id == edit_store.target_id_of(resolved.real_path)
    assert len(resolved.target_id) == 16
    assert resolved.trusted_base == str(world.project)
    assert resolved.parts == (".claude",)
    assert resolved.link is False
    assert resolved.may_make_dir is False


def test_the_user_file_walks_from_the_config_folder(world: World) -> None:
    resolved = world.store.resolve(world.target("user"))
    assert resolved.trusted_base == str(world.config)
    assert resolved.parts == ()
    assert resolved.name == "settings.json"


def test_a_config_folder_outside_home_is_its_own_trusted_base(
    edit_config: Path, edit_project: Path, tmp_path: Path
) -> None:
    ctx = EditContext(config_dir=edit_config, home=tmp_path / "somewhere-else")
    world = make_world(edit_config, edit_project, ctx=ctx)
    resolved = world.store.resolve(world.target("user"))
    assert resolved.trusted_base == str(edit_config)
    assert world.save("high", "user", field_name="model").row_id


def test_a_missing_claude_folder_may_be_made(edit_config: Path, tmp_path: Path) -> None:
    bare = (tmp_path / "bare").resolve()
    bare.mkdir()
    resolved = make_world(edit_config, bare).store.resolve(
        edit_store.settings_target(
            EditContext(config_dir=edit_config, home=edit_config.parent),
            bare,
            "project",
        )
    )
    assert resolved.may_make_dir is True
    assert resolved.folder_path == str(bare / ".claude")


def test_a_missing_project_folder_is_folder_not_found(
    edit_config: Path, tmp_path: Path
) -> None:
    gone = (tmp_path / "gone").resolve()
    world = make_world(edit_config, gone)
    assert refusal(world).code == "folder_not_found"


def test_a_missing_config_folder_is_folder_not_found(world: World) -> None:
    target = world.target("user")
    os.rename(world.config, world.config.with_name("moved"))
    with pytest.raises(Refused) as caught:
        world.store.resolve(target)
    assert caught.value.code == "folder_not_found"


def test_a_claude_entry_that_is_a_file_is_not_regular(world: World) -> None:
    os.rmdir(world.project / ".claude")
    (world.project / ".claude").write_text("x")
    with pytest.raises(Refused) as caught:
        world.store.inspect(world.target())
    assert caught.value.code == "not_regular"


# Links


def test_a_leaf_link_is_written_through_and_stays_a_link(world: World) -> None:
    real = write_json(
        world.home / "dotfiles" / "settings.json", '{"effortLevel": "low"}\n'
    )
    link = world.project / ".claude" / "settings.json"
    os.symlink(real, link)
    result = world.save("high")
    assert link.is_symlink()
    assert real.read_text() == '{"effortLevel": "high"}\n'
    assert result.row["real_path"] == str(real)
    assert result.row["display_path"] == str(link)
    assert (
        world.backups / edit_store.target_id_of(str(real)) / "ledger.json"
    ).is_file()
    assert world.store.resolve(world.target()).link is True


def test_a_folder_link_is_written_through(world: World) -> None:
    os.rmdir(world.project / ".claude")
    dotclaude = world.home / "dotclaude"
    dotclaude.mkdir()
    write_json(dotclaude / "settings.json", '{"effortLevel": "low"}\n')
    os.symlink(dotclaude, world.project / ".claude")
    world.save("high")
    assert (dotclaude / "settings.json").read_text() == '{"effortLevel": "high"}\n'
    assert (world.project / ".claude").is_symlink()


def test_a_link_inside_the_project_is_allowed(world: World) -> None:
    shared = write_json(world.project / "shared" / "s.json", '{"effortLevel": "low"}\n')
    os.symlink(shared, world.project / ".claude" / "settings.json")
    world.save("high")
    assert shared.read_text() == '{"effortLevel": "high"}\n'


def test_a_link_to_a_file_outside_home_and_project_is_link_outside(
    world: World, tmp_path: Path
) -> None:
    other = write_json(tmp_path / "elsewhere" / "s.json", '{"effortLevel": "low"}\n')
    os.symlink(other, world.project / ".claude" / "settings.json")
    assert refusal(world).code == "link_outside"
    assert other.read_text() == '{"effortLevel": "low"}\n'
    assert no_store_folder(world)


def git_subfolder_world(edit_config: Path, tmp_path: Path) -> tuple[World, Path]:
    """A project in a subfolder of a git repo, and the repo root."""
    repo = (tmp_path / "repo").resolve()
    (repo / ".git").mkdir(parents=True)
    sub = repo / "sub"
    (sub / ".claude").mkdir(parents=True)
    return make_world(edit_config, sub), repo


def test_a_git_root_local_link_to_a_file_under_the_git_root_is_written_through(
    edit_config: Path, tmp_path: Path
) -> None:
    world, repo = git_subfolder_world(edit_config, tmp_path)
    real = write_json(repo / "shared" / "local.json", '{"effortLevel": "low"}\n')
    link = repo / ".claude" / "settings.local.json"
    link.parent.mkdir(parents=True)
    os.symlink(real, link)
    assert world.target("local").display_path == str(link)
    world.save("high", "local")
    assert link.is_symlink()
    assert real.read_text() == '{"effortLevel": "high"}\n'


def test_a_git_root_local_link_outside_home_project_and_git_root_is_link_outside(
    edit_config: Path, tmp_path: Path
) -> None:
    world, repo = git_subfolder_world(edit_config, tmp_path)
    other = write_json(tmp_path / "elsewhere" / "s.json", '{"effortLevel": "low"}\n')
    link = repo / ".claude" / "settings.local.json"
    link.parent.mkdir(parents=True)
    os.symlink(other, link)
    assert refusal(world, scope="local").code == "link_outside"
    assert other.read_text() == '{"effortLevel": "low"}\n'
    assert no_store_folder(world)


def test_a_dangling_leaf_link_is_link_dangling(world: World) -> None:
    os.symlink(
        world.home / "nowhere" / "s.json", world.project / ".claude" / "settings.json"
    )
    assert refusal(world).code == "link_dangling"
    assert not (world.home / "nowhere").exists()


def test_a_dangling_folder_link_is_link_dangling(world: World) -> None:
    os.rmdir(world.project / ".claude")
    os.symlink(world.home / "nowhere", world.project / ".claude")
    assert refusal(world).code == "link_dangling"


def test_a_link_loop_is_link_dangling(world: World) -> None:
    os.symlink("settings.json", world.project / ".claude" / "settings.json")
    assert refusal(world).code == "link_dangling"


@pytest.mark.parametrize(
    ("relative", "code"),
    [
        ("config/plugins/p/settings.json", "forbidden_path"),
        ("config/plugins/cache/x/y/settings.json", "forbidden_path"),
        ("config/routing-dashboard/bartab/x.json", "forbidden_path"),
        ("config/routing-dashboard/backups/zz/settings.json", "forbidden_path"),
        ("config/routing-dashboard/anything.json", "forbidden_path"),
        ("home/.claude.json", "forbidden_path"),
        ("home/.claude.json.backup", "forbidden_path"),
        ("home/managed/managed-settings.json", "managed"),
        ("home/managed/managed-settings.d/50-team.json", "managed"),
        ("home/other/managed-settings.json", "managed"),
        ("home/other/managed-settings.d/50-team.json", "managed"),
    ],
)
def test_a_link_to_a_forbidden_path_is_refused_after_resolving(
    edit_config: Path, edit_project: Path, relative: str, code: str
) -> None:
    home = edit_config.parent
    ctx = EditContext(config_dir=edit_config, home=home, managed_dir=home / "managed")
    world = make_world(edit_config, edit_project, ctx=ctx)
    top, _, rest = relative.partition("/")
    base = edit_config if top == "config" else home
    victim = write_json(base / rest, '{"effortLevel": "low"}\n')
    os.symlink(victim, edit_project / ".claude" / "settings.json")
    assert refusal(world).code == code
    assert victim.read_text() == '{"effortLevel": "low"}\n'


def test_a_link_to_a_folder_is_not_regular(world: World) -> None:
    (world.home / "dir").mkdir()
    os.symlink(world.home / "dir", world.project / ".claude" / "settings.json")
    assert refusal(world).code == "not_regular"


def test_the_checkout_guard_refuses_a_target_inside_the_checkout(
    edit_config: Path, edit_project: Path
) -> None:
    ctx = EditContext(
        config_dir=edit_config,
        home=edit_config.parent,
        guard_checkout=True,
        checkout=edit_project,
    )
    world = make_world(edit_config, edit_project, ctx=ctx)
    err = refusal(world)
    assert err.code == "not_editable"
    assert err.params == {"reason": "checkout"}
    assert not (edit_project / ".claude" / "settings.json").exists()
    allowed = EditContext(
        config_dir=edit_config,
        home=edit_config.parent,
        guard_checkout=True,
        checkout=edit_config.parent / "elsewhere",
    )
    assert make_world(edit_config, edit_project, ctx=allowed).save("high").row_id


# A folder or file swapped for a link between the check and the write


def swap_at(world: World, point: str, action: object) -> list[str]:
    """Run ``action`` the first time the writer reaches ``point``."""
    assert callable(action)
    seen: list[str] = []

    def seam(name: str) -> None:
        seen.append(name)
        if name == point:
            action()

    world.store.seam = seam
    return seen


def folder_link_swap(world: World) -> None:
    folder = world.project / ".claude"
    aside = world.project / ".claude-aside"
    os.rename(folder, aside)
    os.symlink(aside, folder)


def assert_nothing_written(old: str, folder: Path, ledger_dir: Path) -> None:
    """The file holds ``old``, no temp file is left, and the ledger is as it was."""
    assert (folder / "settings.json").read_text() == old
    assert [
        p.name for p in folder.iterdir() if p.name.startswith(".routing-dashboard-")
    ] == []
    if (ledger_dir / "ledger.json").exists():
        rows = json.loads((ledger_dir / "ledger.json").read_bytes())["rows"]
        assert rows == []
    assert [
        p.name for p in ledger_dir.iterdir() if p.name.endswith((".bak", ".absent"))
    ] == []


def test_a_folder_swapped_for_a_link_before_the_rename_changes_nothing(
    world: World,
) -> None:
    old = '{"effortLevel": "low"}\n'
    settings(world, old)
    ledger_dir = world.ledger_dir()
    swap_at(world, "before_recheck", lambda: folder_link_swap(world))
    assert refusal(world).code == "changed"
    assert_nothing_written(old, world.project / ".claude-aside", ledger_dir)


def test_a_folder_replaced_by_another_folder_before_the_rename_changes_nothing(
    world: World,
) -> None:
    old = '{"effortLevel": "low"}\n'
    settings(world, old)

    def replace() -> None:
        folder = world.project / ".claude"
        os.rename(folder, world.project / ".claude-aside")
        write_json(folder / "settings.json", old)

    swap_at(world, "before_recheck", replace)
    assert refusal(world).code == "changed"
    assert (world.project / ".claude" / "settings.json").read_text() == old
    assert (world.project / ".claude-aside" / "settings.json").read_text() == old
    assert [p.name for p in (world.project / ".claude-aside").iterdir()] == [
        "settings.json"
    ]


def test_a_leaf_swapped_for_a_link_before_the_rename_changes_nothing(
    world: World,
) -> None:
    old = '{"effortLevel": "low"}\n'
    path = settings(world, old)
    other = write_json(world.home / "other.json", old)

    def swap() -> None:
        path.unlink()
        os.symlink(other, path)

    swap_at(world, "before_recheck", swap)
    assert refusal(world).code == "changed"
    assert other.read_text() == old


def test_a_leaf_replaced_by_a_new_file_with_the_same_bytes_is_changed(
    world: World,
) -> None:
    old = '{"effortLevel": "low"}\n'
    path = settings(world, old)

    def swap() -> None:
        replacement = path.with_name("x.json")
        write_json(replacement, old)
        os.replace(replacement, path)

    swap_at(world, "before_recheck", swap)
    assert refusal(world).code == "changed"
    assert path.read_text() == old


def test_a_folder_swapped_for_a_link_after_the_preview_is_bad_version(
    world: World,
) -> None:
    settings(world, '{"effortLevel": "low"}\n')
    body = world.save_body("high")
    folder_link_swap(world)
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), body)
    assert caught.value.code == "bad_version"


def test_a_folder_that_vanishes_before_the_walk_is_changed(world: World) -> None:
    settings(world, '{"effortLevel": "low"}\n')
    resolved = world.store.resolve(world.target())
    (world.project / ".claude" / "settings.json").unlink()
    os.rmdir(world.project / ".claude")
    with pytest.raises(Refused) as caught, edit_store._walk(resolved):
        pass
    assert caught.value.code == "changed"


def test_a_trusted_base_that_vanished_is_folder_not_found(world: World) -> None:
    settings(world, '{"effortLevel": "low"}\n')
    resolved = world.store.resolve(world.target())
    os.rename(world.project, world.project.with_name("moved"))
    with pytest.raises(Refused) as caught, edit_store._walk(resolved):
        pass
    assert caught.value.code == "folder_not_found"


# File refusals


def test_a_fifo_is_not_regular(world: World) -> None:
    os.mkfifo(world.path())
    assert refusal(world).code == "not_regular"
    assert no_store_folder(world)


def test_a_hard_linked_file_is_refused(world: World) -> None:
    path = settings(world, '{"effortLevel": "low"}\n')
    os.link(path, world.home / "twin.json")
    assert refusal(world).code == "hard_link"
    assert path.read_text() == '{"effortLevel": "low"}\n'
    assert no_store_folder(world)


def test_a_file_owned_by_someone_else_is_not_owner(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = settings(world, '{"effortLevel": "low"}\n')
    monkeypatch.setattr(os, "geteuid", lambda: os.stat(path).st_uid + 1)
    with pytest.raises(Refused) as caught:
        world.store.inspect(world.target())
    assert caught.value.code == "not_owner"


def test_a_file_over_one_mebibyte_is_too_large(world: World) -> None:
    path = write_json(
        world.path(), '{"effortLevel": "low"}' + " " * edit_store.MAX_FILE
    )
    assert refusal(world).code == "too_large"
    assert path.stat().st_size > edit_store.MAX_FILE


def test_a_save_that_grows_a_file_past_the_cap_is_too_large(world: World) -> None:
    path = write_json(world.path(), '{"model": "m"}' + " " * (edit_store.MAX_FILE - 14))
    assert path.stat().st_size == edit_store.MAX_FILE
    assert world.store.inspect(world.target()).raw is not None
    assert refusal(world).code == "too_large"
    assert path.stat().st_size == edit_store.MAX_FILE


def test_a_file_that_is_not_json_is_unparsed(world: World) -> None:
    path = settings(world, "{not json")
    assert refusal(world).code == "unparsed"
    assert path.read_text() == "{not json"


def test_an_unreadable_file_is_not_owner(world: World) -> None:
    path = settings(world, '{"effortLevel": "low"}\n')
    path.chmod(0)
    try:
        with pytest.raises(Refused) as caught:
            world.store.inspect(world.target())
        assert caught.value.code == "not_owner"
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize(
    ("value", "field_name"),
    [
        ("banana", "effortLevel"),
        ("max", "effortLevel"),
        (5, "effortLevel"),
        (50, "autoCompactWindow"),
        ("auto", "autoCompactWindow"),
        ("", "model"),
        ("sk-live-123", "model"),
    ],
)
def test_a_value_the_field_does_not_take_is_bad_value(
    world: World, value: str | int, field_name: str
) -> None:
    body = world.save_body(value, field_name=field_name, version="x")
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), body)
    assert caught.value.code == "bad_value"


def test_a_save_that_changes_nothing_is_no_change(world: World) -> None:
    path = settings(world, '{"effortLevel": "high"}\n')
    assert refusal(world).code == "no_change"
    assert path.read_text() == '{"effortLevel": "high"}\n'


def test_a_parent_that_is_not_an_object_refuses_an_env_insert(world: World) -> None:
    settings(world, '{"env": "text"}\n')
    body = world.save_body("high", version="x")
    with pytest.raises(Refused) as caught:
        world.store.save(
            world.target(), body, key_path=("env", "CLAUDE_CODE_EFFORT_LEVEL")
        )
    assert caught.value.code in {"bad_version", "parent_not_object"}
    version = world.version("high")
    body = world.save_body("high", version=version)
    with pytest.raises(Refused) as caught:
        world.store.save(
            world.target(), body, key_path=("env", "CLAUDE_CODE_EFFORT_LEVEL")
        )
    assert caught.value.code == "parent_not_object"


@pytest.mark.parametrize(
    "key_path",
    [
        ("env", "SOMETHING_ELSE"),
        ("modelSettings", "", "effortLevel"),
        ("modelSettings", "m", "model"),
        ("autoCompactWindow",),
        (),
    ],
)
def test_a_key_path_the_registry_does_not_allow_is_bad_value(
    world: World, key_path: tuple[str, ...]
) -> None:
    with pytest.raises(Refused) as caught:
        edit_store.plan_set(b"{}\n", "effortLevel", "high", key_path)
    assert caught.value.code == "bad_value"


def test_a_missing_edits_switch_refuses_before_any_write(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = settings(world, '{"effortLevel": "low"}\n')
    body = world.save_body("high")
    monkeypatch.setattr(write_guard.STATE, "edits", False)
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), body)
    assert caught.value.code == "edits_off"
    assert path.read_text() == '{"effortLevel": "low"}\n'


def test_a_lock_held_by_another_writer_is_lock_busy(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fcntl

    path = settings(world, '{"effortLevel": "low"}\n')
    body = world.save_body("high")
    store_dir = world.ledger_dir()
    store_dir.mkdir(parents=True, mode=0o700)
    held = os.open(store_dir / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(held, fcntl.LOCK_EX)
        monkeypatch.setattr(edit_store, "LOCK_WAIT", 0.1)
        with pytest.raises(Refused) as caught:
            world.store.save(world.target(), body)
        assert caught.value.code == "lock_busy"
    finally:
        os.close(held)
    assert path.read_text() == '{"effortLevel": "low"}\n'


def test_a_lock_file_that_is_a_link_is_lock_busy(world: World) -> None:
    settings(world, '{"effortLevel": "low"}\n')
    body = world.save_body("high")
    store_dir = world.ledger_dir()
    store_dir.mkdir(parents=True, mode=0o700)
    os.symlink(world.home / "lock", store_dir / ".lock")
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), body)
    assert caught.value.code == "lock_busy"


def test_errno_names_reach_the_params_of_an_unexpected_failure(world: World) -> None:
    resolved = world.store.resolve(world.target())
    err = edit_store._walk_error(OSError(errno.EIO, "boom"))
    assert err.code == "write_failed"
    assert err.params == {"errno": "EIO"}
    assert edit_store._scan_error(OSError(errno.EIO, "boom")).params == {"errno": "EIO"}
    assert resolved.name == "settings.json"
    assert PROJECT_KEY

"""Tests for platform_os."""

import contextlib
import stat
from pathlib import Path

import platform_os


def test_lock_is_exclusive_until_release(tmp_path: Path) -> None:
    lock = tmp_path / "writer.lock"
    first = platform_os.try_lock_exclusive(lock)
    assert first is not None
    assert first.held
    assert platform_os.try_lock_exclusive(lock) is None
    first.release()
    assert not first.held
    second = platform_os.try_lock_exclusive(lock)
    assert second is not None
    second.release()
    second.release()
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600


def test_lock_handle_works_as_context_manager(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    handle = platform_os.try_lock_exclusive(lock)
    assert handle is not None
    with handle:
        assert platform_os.try_lock_exclusive(lock) is None
    assert platform_os.try_lock_exclusive(lock) is not None


def test_file_identity_matches_stat(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"abc")
    st = path.stat()
    ident = platform_os.file_identity(path)
    assert ident == (st.st_dev, st.st_ino, 3, st.st_mtime_ns)
    assert ident.size == 3


def test_mkdir_private_sets_0700_for_new_folders_only(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b"
    platform_os.mkdir_private(deep, parents=True)
    assert stat.S_IMODE(deep.stat().st_mode) == 0o700
    assert stat.S_IMODE(deep.parent.stat().st_mode) == 0o700
    deep.chmod(0o755)
    platform_os.mkdir_private(deep)
    assert stat.S_IMODE(deep.stat().st_mode) == 0o755


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "last-good.json"
    platform_os.atomic_write(target, b"one")
    platform_os.atomic_write(target, b"two")
    assert target.read_bytes() == b"two"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["last-good.json"]


def test_atomic_write_failure_keeps_old_bytes(tmp_path: Path) -> None:
    target = tmp_path / "t.json"
    platform_os.atomic_write(target, b"old")
    with contextlib.suppress(TypeError):
        platform_os.atomic_write(target, "not bytes")  # type: ignore[arg-type]
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["t.json"]


def test_fsync_helpers_run(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"x")
    platform_os.fsync_file(path)
    platform_os.fsync_dir(tmp_path)


def test_create_private_file(tmp_path: Path) -> None:
    path = tmp_path / "db"
    platform_os.create_private_file(path)
    platform_os.create_private_file(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

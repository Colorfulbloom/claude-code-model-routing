"""Tests for store_paths."""

from pathlib import Path

import pytest

import store_paths
from store_paths import StoreLayout, StorePathError


def test_config_dir_default_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/work/cfg")
    assert store_paths.config_dir_default() == Path("/work/cfg")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setenv("HOME", "/work/userhome")
    assert store_paths.config_dir_default() == Path("/work/userhome/.claude")


def test_layout_names(tmp_path: Path) -> None:
    root = store_paths.shared_store_root(tmp_path / "cfg")
    assert root == tmp_path / "cfg" / "routing-dashboard" / "bartab"
    layout = StoreLayout(root)
    assert layout.db == root / "bartab.db"
    assert layout.writer_lock == root / "writer.lock"
    assert layout.db_backups == root / "db-backups"
    assert layout.prices_dir == root / "prices"
    assert layout.last_good_prices == root / "prices" / "last-good.json"


def test_layout_is_frozen(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path)
    with pytest.raises(AttributeError):
        layout.root = tmp_path / "x"  # type: ignore[misc]


def test_writable_accepts_paths_inside_root(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path / "bartab")
    layout.root.mkdir()
    for path in (
        layout.root,
        layout.db,
        layout.root / "bartab.db-wal",
        layout.db_backups / "bartab-20261108T120000Z.db",
        layout.prices_dir / ".incoming-abc.tmp",
        layout.last_good_prices,
    ):
        assert store_paths.writable(layout, path) == path.resolve()


def test_writable_refuses_outside_root(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path / "routing-dashboard" / "bartab")
    layout.root.mkdir(parents=True)
    for path in (
        tmp_path / "elsewhere.db",
        layout.root.parent / "other.db",
        layout.root / ".." / "ledger.json",
        tmp_path / "routing-dashboard.json",
    ):
        with pytest.raises(StorePathError) as info:
            store_paths.writable(layout, path)
        assert info.value.reason == "outside_root"


def test_writable_refuses_symlink_escape(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path / "bartab")
    layout.root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (layout.root / "link").symlink_to(outside)
    with pytest.raises(StorePathError):
        store_paths.writable(layout, layout.root / "link" / "x.db")


@pytest.mark.parametrize(
    "name",
    [
        "backups",
        "backups/x/ledger.json",
        "ledger.json",
        ".lock",
        "old.bak",
        ".ledger-abc.tmp",
        ".routing-dashboard-abc.tmp",
        "routing-dashboard.json",
    ],
)
def test_writable_refuses_old_app_names_inside_root(tmp_path: Path, name: str) -> None:
    layout = StoreLayout(tmp_path / "bartab")
    layout.root.mkdir()
    with pytest.raises(StorePathError) as info:
        store_paths.writable(layout, layout.root / name)
    assert info.value.reason == "old_app_name"

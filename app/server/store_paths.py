"""Where Bar Tab keeps its files, and the guard that keeps writes inside that folder.

Everything Bar Tab writes in the shared config folder sits under
``<config>/routing-dashboard/bartab/``. The old app owns the rest of
``routing-dashboard/`` and ``routing-dashboard.json``, and none of it is ever
written, locked or listed from here.
"""

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

# Names the old app owns. A write path that has one of these as a component is
# refused even inside the store root.
OLD_APP_NAMES = (
    "backups",
    "ledger.json",
    ".lock",
    "*.bak",
    ".ledger-*.tmp",
    ".routing-dashboard-*.tmp",
    "routing-dashboard.json",
)


class StorePathError(ValueError):
    """A write path is outside the store root or names an old-app file."""

    def __init__(self, path: Path, reason: str) -> None:
        """Keep the refused path and a short reason (outside_root, old_app_name)."""
        super().__init__(f"{reason}: {path}")
        self.path = path
        self.reason = reason


def config_dir_default() -> Path:
    """Return CLAUDE_CONFIG_DIR, else $HOME/.claude. ``serve.py --real`` calls this."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env)
    return Path(os.environ.get("HOME", "~")).expanduser() / ".claude"


def shared_store_root(config_dir: Path) -> Path:
    """Return the Bar Tab folder inside the shared config folder."""
    return config_dir / "routing-dashboard" / "bartab"


@dataclass(frozen=True)
class StoreLayout:
    """The fixed names inside one store root."""

    root: Path

    @property
    def db(self) -> Path:
        """The SQLite file."""
        return self.root / "bartab.db"

    @property
    def writer_lock(self) -> Path:
        """The single-writer lock file."""
        return self.root / "writer.lock"

    @property
    def db_backups(self) -> Path:
        """Folder for database copies. Not named backups, which the old app owns."""
        return self.root / "db-backups"

    @property
    def prices_dir(self) -> Path:
        """Folder for price copies."""
        return self.root / "prices"

    @property
    def last_good_prices(self) -> Path:
        """The last price copy that passed its checks."""
        return self.prices_dir / "last-good.json"


def _old_app_name(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in OLD_APP_NAMES)


def writable(layout: StoreLayout, path: Path) -> Path:
    """Return the resolved ``path`` when a write there is allowed.

    Symlinks resolve first. Raises ``StorePathError`` for a path outside the root or
    one that has an old-app name as a component below the root.
    """
    root = layout.root.resolve()
    target = Path(path).resolve()
    try:
        rel = target.relative_to(root)
    except ValueError:
        raise StorePathError(Path(path), "outside_root") from None
    if any(_old_app_name(part) for part in rel.parts):
        raise StorePathError(Path(path), "old_app_name")
    return target

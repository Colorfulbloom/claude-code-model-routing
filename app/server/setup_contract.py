"""The collector contract for the setup read side (M4).

Every setup collector is a module with one ``Collector`` object. ``read`` returns a
``Collected`` and never raises for a bad file: a file it cannot read lands in
``unreadable`` with a reason, a file Claude Code would skip lands in ``problems``,
and everything that did read still comes back (plan.md section 7, "Collector
contract"; m4-build.md sections 2 and 4). ``signature`` is a stat-only fingerprint
of the files and folders the last read touched, for the answer etag. It never opens
a file.

Collectors read through ``read_scope`` only, so the real-mode read rule in
m4-build.md section 7 has one place to hold. ``SetupContext`` carries everything a
collector may know about the project. Nothing here reads ``os.environ`` or looks a
home folder up; the caller decides what goes in.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from models import ProblemRow, SetupItem, SetupPart, UnreadableFile

# Caps from m4-build.md section 2. A file past its cap is unreadable with
# ``too_large``.
FILE_CAP_BYTES = 1024 * 1024
CLAUDE_JSON_CAP_BYTES = 32 * 1024 * 1024

# The capped walk for nested CLAUDE.md files and ``.claude/skills`` (section 7).
WALK_MAX_DEPTH = 6
WALK_MAX_FOLDERS = 5000
WALK_SKIP_NAMES = frozenset({"node_modules", "vendor", "dist", "build"})


@dataclass(frozen=True)
class SetupContext:
    """What a collector may know about one project.

    Attributes:
        project_key: The project's key in ``/api/projects``.
        config_dir: The Claude config folder (``CLAUDE_CONFIG_DIR`` or
            ``$HOME/.claude``), worked out by the caller.
        home: The home folder, for ``~`` in display paths and for the
            ``~/.claude.json`` fallback, or None.
        project_dir: The listed project's folder, or None for an unlisted project
            (then nothing under its ``cwd`` is read).
        managed_dir: The managed settings folder, or None.
        shell_env: The server's environment from start, already filtered by the
            caller. Owner answer 9: confidence ``assumed``.
        plan: ``subscription``, ``api_key``, ``cloud_provider`` or None, from
            ``routing-dashboard.json``.
        real_mode: True on the owner's real data. Fixture and demo modes read the
            same files from their own folders.
    """

    project_key: str
    config_dir: Path
    home: Path | None
    project_dir: Path | None
    managed_dir: Path | None
    shell_env: Mapping[str, str] = field(default_factory=dict[str, str])
    plan: str | None = None
    real_mode: bool = False


@dataclass
class Collected:
    """What one collector read for one project.

    Attributes:
        items: Items per part. A collector may feed several parts (settings feeds
            settings, permissions and output style).
        problems: Diagnostics as problem rows (Won't load, Not as set, Can't tell).
            Read failures are in ``unreadable`` and become rows in the feed.
        unreadable: Files that could not be read, or lay outside the allowed roots.
        touched: Every path the read opened or listed, for ``signature``.
        handoff: Data for a later collector, keyed by name (the plugin collector
            hands each plugin's agents, skills, hooks and MCP folders on).
    """

    items: dict[SetupPart, list[SetupItem]] = field(
        default_factory=dict[SetupPart, list[SetupItem]]
    )
    problems: list[ProblemRow] = field(default_factory=list[ProblemRow])
    unreadable: list[UnreadableFile] = field(default_factory=list[UnreadableFile])
    touched: list[Path] = field(default_factory=list[Path])
    handoff: dict[str, object] = field(default_factory=dict[str, object])


class Collector(Protocol):
    """One setup collector."""

    name: str
    parts: Sequence[SetupPart]

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the project's files for this collector's parts. Never raises."""
        ...

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Return a stat-only fingerprint of what ``read`` would see now."""
        ...


# Run order. A later collector receives the handoff of every earlier one, so this
# differs from the build order in m4-build.md section 4: settings gives
# ``enabledPlugins``, plugins hand their agents, skills, hooks and MCP folders on, and
# the masked ``~/.claude.json`` reader feeds MCP.
COLLECTOR_ORDER: tuple[str, ...] = (
    "settings",
    "plugins",
    "agents",
    "skills",
    "instructions",
    "hooks",
    "claude_json",
    "mcp",
)

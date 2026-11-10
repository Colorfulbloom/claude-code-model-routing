"""Read the settings layers for the setup read side (m4-build.md task 4).

``read_layers`` finds every settings file of one project (managed, local, project,
user), reads each through ``read_scope`` and hands the old ``collect`` and ``resolve``
modules what it read. ``collect`` opens nothing here: a ``FileAccess`` replays the
bytes this module already read, so the one read path holds (m4-build.md section 7).

The result, ``Layers``, serves the Settings, Permissions and Output style parts. It
keeps each file's parsed JSON for display. A value reaches a page only through
``display_value``, which masks it under the 26-07 rules (``masking``). ``collect.mask``
is never used for display, because it can't say whether it hid anything.

Top-wins order of files, as Claude Code applies them: every managed file (the last one
of ``managed-settings.d`` first), the repo-root local file when the project sits below
its git root, the project's own local file, the project file, the user file.
"""

# ruff: noqa: PTH100, PTH118 - paths are strings, joined as ``collect`` joins them, so
# the entries it makes name the paths this module read.

import functools
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import collect
import git_root
import masking
import read_scope
import resolve
import setup_contract
from models import MaskedText, SetupScope, UnreadableFile
from setup_contract import SetupContext
from usage import Row

# A project folder that cannot exist: /dev/null is a file, so nothing lies below it.
NO_PROJECT = os.devnull
# A made-up agent with no frontmatter. The resolver only makes agent rows for an agent
# it has, so a run with this one shows what the settings files, the shell and the
# flags say for an agent that sets nothing itself (``subagentPromptCacheTtl``).
PROBE_AGENT = "settings-only"

# The setup scope of each ``collect`` layer.
LAYER_SCOPE: dict[str, SetupScope] = {
    "managed": "managed",
    "local": "project_local",
    "project": "project",
    "user": "user",
}

FileState = Literal["ok", "json_invalid", "not_object", "unreadable"]


@functools.cache
def rules() -> dict[str, Any]:
    """Return the rules.json document, read once."""
    return resolve.load_rules()


@functools.cache
def agent_fields() -> tuple[str, ...]:
    """Return the agent front matter field names, read once."""
    return tuple(resolve.load_agent_fields())


@dataclass
class LayerFile:
    """One settings file that exists.

    Attributes:
        path: The path string handed to ``collect`` (and named by its entries).
        layer: ``managed``, ``local``, ``project`` or ``user``.
        scope: The setup scope of the layer.
        state: ``ok``, ``json_invalid`` (``error_line`` says where), ``not_object`` or
            ``unreadable`` (the file is also in ``Layers.unreadable``).
        display: The display path.
        full_path: The absolute path, for Copy path.
        data: The parsed object, unmasked. Never shown as it is: see ``display_value``.
        lines: Key path to 1-based line, from ``collect.json_key_lines``.
        text_lines: The file's lines, to find a list item's line.
        error_line: Where a ``json_invalid`` file stops parsing.
        real_path: The display path of a symlink's real target, or None.
    """

    path: str
    layer: str
    scope: SetupScope
    state: FileState
    display: str
    full_path: str
    data: dict[str, Any] = field(default_factory=dict[str, Any])
    lines: dict[tuple[str, ...], int] = field(
        default_factory=dict[tuple[str, ...], int]
    )
    text_lines: list[str] = field(default_factory=list[str])
    error_line: int | None = None
    real_path: str | None = None


@dataclass
class Layers:
    """Everything one read of a project's settings files found.

    Attributes:
        ctx: The project's context.
        scope: Its read scope.
        files: Every file that exists, in top-wins order.
        collected: The ``collect.collect`` result, with agents and rules files empty
            (the Agents collector reads those).
        unreadable: Files that could not be read, or were refused.
        touched: Every path and folder looked at, for the signature.
    """

    ctx: SetupContext
    scope: read_scope.Scope
    files: list[LayerFile]
    collected: dict[str, Any]
    unreadable: list[UnreadableFile]
    touched: list[Path]

    def readable(self) -> list[LayerFile]:
        """Return the files that parsed, in top-wins order."""
        return [f for f in self.files if f.state == "ok"]


class _Replay:
    """A ``collect.FileAccess`` that serves what was already read, and nothing else."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes | None, str]] = {}
        self.dirs: dict[str, list[str] | OSError] = {}

    def read(self, path: str) -> tuple[bytes | None, str]:
        return self.files.get(path, (None, "missing"))

    def listdir(self, folder: str) -> list[str]:
        got = self.dirs.get(folder, FileNotFoundError(folder))
        if isinstance(got, OSError):
            raise got
        return got

    def isfile(self, path: str) -> bool:
        return self.files.get(path, (None, "missing"))[1] != "missing"


def _classify(text: str, *, managed: bool) -> tuple[FileState, dict[str, Any], int]:
    """Return (state, parsed object, error line) the way ``collect`` would judge it."""
    if managed and text == "":
        return "ok", {}, 0
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        return "json_invalid", {}, exc.lineno
    except (ValueError, RecursionError):
        return "json_invalid", {}, 1
    if not isinstance(parsed, dict):
        return "not_object", {}, 0
    return "ok", cast("dict[str, Any]", parsed), 0


def _key_lines(text: str) -> dict[tuple[str, ...], int]:
    try:
        return collect.json_key_lines(text)
    except (ValueError, IndexError, RecursionError):
        return {}


class _Reader:
    """Reads the settings files of one project and fills the replay."""

    def __init__(self, ctx: SetupContext, scope: read_scope.Scope) -> None:
        self.ctx = ctx
        self.scope = scope
        self.replay = _Replay()
        self.unreadable: list[UnreadableFile] = []
        self.touched: list[Path] = []

    def file(self, path: str, layer: str) -> LayerFile | None:
        """Read one settings file. A missing file is None."""
        self.touched.append(Path(path))
        got = read_scope.read_text(
            self.scope, path, setup_contract.FILE_CAP_BYTES, parse=json.loads
        )
        if isinstance(got, UnreadableFile):
            if got.reason == "vanished":
                self.replay.files[path] = (None, "missing")
                return None
            # A refused path is dropped, as ``model_check`` drops it. The row stays so
            # the page can say "not read here".
            refused = got.reason in ("outside_scope", "plugin_outside_plugins")
            self.replay.files[path] = (None, "missing" if refused else "unreadable")
            self.unreadable.append(got)
            return self._make(path, layer, "unreadable", "", {})
        self.replay.files[path] = (got.encode("utf-8"), "ok")
        state, data, line = _classify(got, managed=layer == "managed")
        made = self._make(path, layer, state, got, data)
        made.error_line = line or None
        return made

    def _make(
        self, path: str, layer: str, state: FileState, text: str, data: dict[str, Any]
    ) -> LayerFile:
        return LayerFile(
            path=path,
            layer=layer,
            scope=LAYER_SCOPE[layer],
            state=state,
            display=self.scope.display(path),
            full_path=os.path.abspath(path),
            data=data,
            lines=_key_lines(text) if state == "ok" else {},
            text_lines=text.splitlines() if state == "ok" else [],
            real_path=read_scope.symlink_target(self.scope, path),
        )

    def managed(self, managed_dir: str) -> list[LayerFile]:
        """Read ``managed-settings.json`` and ``managed-settings.d/*.json``."""
        found = [self.file(os.path.join(managed_dir, collect.MANAGED_FILE), "managed")]
        folder = os.path.join(managed_dir, collect.MANAGED_FOLDER)
        self.touched.append(Path(folder))
        names = read_scope.list_dir(self.scope, folder)
        if isinstance(names, UnreadableFile):
            if names.reason == "vanished":
                self.replay.dirs[folder] = FileNotFoundError(folder)
            else:
                self.replay.dirs[folder] = OSError(folder)
                self.unreadable.append(names)
        else:
            self.replay.dirs[folder] = names
            for name in names:
                if name.endswith(".json") and not name.startswith("."):
                    found.append(self.file(os.path.join(folder, name), "managed"))
        return [f for f in found if f is not None]


def read_layers(ctx: SetupContext, scope: read_scope.Scope | None = None) -> Layers:
    """Read every settings file of the project through ``read_scope``.

    Args:
        ctx: The project's context. An unlisted project (``project_dir`` None) has
            managed and user files only.
        scope: The read scope, or None to build it from ``ctx``.

    Returns:
        The layers. A file that cannot be read is in ``unreadable``. Nothing raises
        for a bad file.
    """
    scope = scope if scope is not None else read_scope.Scope(ctx)
    reader = _Reader(ctx, scope)
    config = str(ctx.config_dir)
    project = str(ctx.project_dir) if ctx.project_dir is not None else None
    managed = reader.managed(str(ctx.managed_dir)) if ctx.managed_dir else []
    local_files: list[LayerFile | None] = []
    project_file: LayerFile | None = None
    local_path: str | None = None
    if project is not None:
        start_local = os.path.join(project, ".claude", "settings.local.json")
        root_local = git_root.local_settings_path(project, ctx.home)
        local_path = str(root_local) if root_local is not None else None
        local_files = [
            reader.file(local_path, "local") if local_path is not None else None,
            reader.file(start_local, "local"),
        ]
        project_file = reader.file(
            os.path.join(project, ".claude", "settings.json"), "project"
        )
    user_file = reader.file(os.path.join(config, "settings.json"), "user")
    collected = collect.collect(
        config_dir=config,
        project_dir=project if project is not None else NO_PROJECT,
        managed_dir=str(ctx.managed_dir) if ctx.managed_dir is not None else None,
        shell_env=ctx.shell_env,
        rules=rules(),
        reuse={"agents": [], "rules_files": []},
        local_path=local_path,
        access=reader.replay,
    )
    ordered = [
        *reversed(managed),
        *local_files,
        project_file,
        user_file,
    ]
    return Layers(
        ctx=ctx,
        scope=scope,
        files=[f for f in ordered if f is not None],
        collected=collected,
        unreadable=reader.unreadable,
        touched=reader.touched,
    )


def managed_settings(
    ctx: SetupContext, scope: read_scope.Scope | None = None
) -> tuple[dict[str, Any], list[Path]]:
    """Read the managed settings files only, through ``read_scope``.

    Args:
        ctx: The context. Only ``managed_dir`` and ``config_dir`` count.
        scope: The read scope, or None to build it from ``ctx``.

    Returns:
        The merged managed settings (``{}`` when there are none) and every path and
        folder looked at. ``collect`` merges the files, so ``managed-settings.d``
        rules apply as they do for the Settings part.
    """
    scope = scope if scope is not None else read_scope.Scope(ctx)
    reader = _Reader(ctx, scope)
    managed = str(ctx.managed_dir) if ctx.managed_dir is not None else None
    if managed is not None:
        reader.managed(managed)
    got = collect.collect_settings(
        str(ctx.config_dir), NO_PROJECT, managed, access=reader.replay
    )
    for source in got["sources"]:
        if source["layer"] == "managed":
            return dict(source["data"]), reader.touched
    return {}, reader.touched


def resolver_entries(  # noqa: PLR0913 - the ``resolve.Inputs`` fields
    collected: dict[str, Any],
    plan: str | None,
    *,
    flags: Sequence[str] = (),
    cli_settings: object = None,
    home: object = None,
    root: object = None,
    shell_label: str = resolve.LIVE_SHELL_LABEL,
    probe_agent: bool = False,
) -> list[Row]:
    """Run the resolver over a ``collect`` result and return its entries.

    Args:
        collected: A ``collect.collect`` result.
        plan: The plan from ``routing-dashboard.json``, or None.
        flags: Launch flags. The server never sees any. A fixture run passes them.
        cli_settings: The ``--settings`` content, already masked. Fixture runs only.
        home: The folder a ``~`` entry path shows from, or None.
        root: The folder an entry path shows relative to, or None.
        shell_label: What an entry names as the file of a shell value.
        probe_agent: Add the ``PROBE_AGENT`` agent, so the result also holds agent
            rows for it. Its other entries (``agentFile``, ``model``) are not for use.
    """
    if probe_agent:
        probe: dict[str, Any] = {
            "layer": "user",
            "path": f"/{PROBE_AGENT}/{PROBE_AGENT}.md",
            "fields": {"name": PROBE_AGENT, "description": PROBE_AGENT},
            "errors": [],
        }
        collected = {**collected, "agents": [*collected.get("agents", []), probe]}
    inputs = resolve.Inputs(
        collected=collected,
        flags=list(flags),
        cli_settings=cli_settings,
        plan=plan,
        home=home,
        root=root,
        shell_label=shell_label,
    )
    return resolve.resolve(inputs, rules(), agent_fields())


# ---------------------------------------------------------------- display


def json_text(value: object) -> str:
    """Return a value as text: a string as it is, anything else as compact JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def display_value(value: object, name: object = None) -> MaskedText:
    """Return a value as ``MaskedText`` under the 26-07 rules.

    Args:
        value: Any JSON value, as parsed from the file (not ``collect.mask``ed).
        name: The key it sits under, which can make the whole value secret.

    Returns:
        The masked text, with ``masked`` True when masking changed it.
    """
    original = json_text(value)
    text = json_text(masking.mask_value(value, name))
    return MaskedText(text=text, masked=text != original)


def raw_value(layers: Layers, path: str | None, keys: tuple[str, ...]) -> object:
    """Return the unmasked value at a key path of one file, or None when absent.

    Args:
        layers: The layers.
        path: The file's path string, as an entry names it.
        keys: The key path (``("env", "FOO")``).
    """
    for item in layers.files:
        if item.path == path and item.state == "ok":
            return _dig(item.data, keys)
    return None


def _dig(node: object, keys: tuple[str, ...]) -> object:
    for key in keys:
        if not isinstance(node, dict):
            return None
        table = cast("dict[str, object]", node)
        if key not in table:
            return None
        node = table[key]
    return node


def list_item_line(
    file: LayerFile, key: tuple[str, ...], item: object, occurrence: int = 0
) -> int | None:
    """Return the line of one item of a list in a file, or None when not found.

    ``json_key_lines`` skips arrays, so this looks for the item's JSON text on the
    lines from the list's key on.

    Args:
        file: The file.
        key: The list's key path.
        item: The item as parsed.
        occurrence: How many equal items come before it in the list, so a repeated
            item finds its own line.
    """
    start = file.lines.get(key)
    if start is None:
        return None
    needles = {json.dumps(item, ensure_ascii=False), json.dumps(item)}
    seen = 0
    for number in range(start, len(file.text_lines) + 1):
        line = file.text_lines[number - 1]
        if number == start and ":" in line:
            line = line.split(":", 1)[1]  # the key's own text is not an item
        if any(needle in line for needle in needles):
            if seen == occurrence:
                return number
            seen += 1
    return None

"""The Skills collector (m4-build.md task 7, part ``skills``).

One item per skill name. A skill is a folder with a ``SKILL.md``. A legacy command is a
``*.md`` file in a ``commands`` folder and counts as a skill with the file's name.
Places, from the docs facts in m4-build.md section 16.

- Managed ``<managed>/.claude/skills/``.
- User ``<config>/skills/`` and ``<config>/commands/``.
- Project ``<project>/.claude/skills/`` and ``<project>/.claude/commands/``, plus every
  nested ``.claude/skills`` the capped walk of ``read_scope`` finds below the project.
- Plugins, from ``handoff["plugins"]``. A plugin skill is its own item,
  ``skills:<plugin>:<name>``, invoked as ``/<plugin>:<name>``, so it never clashes with
  another name.

Items are ``skills:<name>``. Items come in name order, and the sources inside an item
in top-wins order. On a clash managed beats user beats project, and inside one scope a
skill beats a command file. The loser is ``overridden``, which is never a problem. Two
files with one name in one folder are different: the second is ``invalid`` with
``same_name_in_folder``.

Front matter is parsed with ``front_matter`` (``ruamel.yaml`` safe mode), never with
the strict agent reader, so ``allowed-tools`` and the docs' other hyphenated keys load.
The body is never read past the front matter and never kept. Only the description
shows, and it goes through ``masking``. That is why this part has no
``frontmatter_reader_gap`` row. The strict reader is never asked about a skill, so
there is no gap to report, and Claude Code reads skills with a real YAML parser, not
with that reader.

The plugin input is ``handoff["plugins"]``. It is either a list of
``PluginComponents`` from the plugins collector or a mapping
``{"skills": [{plugin, name, path}], "commands": [...]}`` whose ``plugin`` is
``<name>@<marketplace>``. A skills path is a skill folder (it holds a ``SKILL.md``) or
a folder of skill folders. A commands path is a folder of ``*.md`` files or one file.

Hand-off. ``Collected.handoff["skill_hooks"]`` holds the ``hooks`` front matter field of
each skill that loads, for the Hooks part.

The nested walk's own problems (a folder that would not list, a stopped walk) are
reported once, by the instructions collector, which runs the same walk.
"""

# ruff: noqa: PTH100, PTH112, PTH118, PTH119, PTH120 - paths are strings, as ``read_scope`` and
# ``agent_files`` handle them.

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import front_matter
import masking
import read_scope
import setup_items
from agent_files import AgentFile, front_matter_field
from collect_plugins import HANDOFF_PLUGINS, PluginComponents
from models import (
    ItemFacts,
    ItemReason,
    ModelCheckStatus,
    ProblemFix,
    ProblemRow,
    ReadOnly,
    SetupItem,
    SetupPart,
    SetupScope,
    SkillFacts,
    UnreadableFile,
)
from setup_contract import FILE_CAP_BYTES, Collected, SetupContext

PART: SetupPart = "skills"
SKILL_FILE = "SKILL.md"
# The handoff key of the front matter ``hooks`` of each loading skill: a list of
# ``AgentFile`` records (as ``collect_agents`` hands agents on), each with one masked
# ``hooks`` field. The Hooks part lists them after the agents' own.
HANDOFF_SKILL_HOOKS = "skill_hooks"
_RANK: dict[SetupScope, int] = {"managed": 0, "user": 1, "project": 2, "plugin": 3}
_SCOPES_VISIBLE: tuple[SetupScope, ...] = ("managed", "user", "project")


@dataclass(frozen=True)
class PluginPath:
    """A skills or commands path a plugin brings.

    Attributes:
        plugin: The plugin's name (``<name>`` of ``<name>@<marketplace>``).
        path: An absolute folder or file.
        command: True for a commands path, False for a skills path.
    """

    plugin: str
    path: str
    command: bool


@dataclass
class _Entry:
    """One skill or command file, read."""

    scope: SetupScope
    plugin: str | None
    name: str
    command: bool
    root: str
    order: int
    display: str
    full_path: str
    real_path: str | None
    fm: front_matter.FrontMatter
    key: str
    line: int | None
    description: object = None
    status: ModelCheckStatus = "in_effect"
    code: str | None = None
    code_line: int | None = None

    @property
    def group(self) -> tuple[str | None, str]:
        return (self.plugin, self.name)

    def rank(self) -> tuple[int, int, int]:
        """Return the rank: scope, then a skill before a command, then place."""
        return (_RANK[self.scope], int(self.command), self.order)


@dataclass
class _Run:
    """One read of the skills of a project."""

    ctx: SetupContext
    scope: read_scope.Scope
    handoff: Mapping[str, object]
    entries: list[_Entry] = field(default_factory=list[_Entry])
    problems: list[ProblemRow] = field(default_factory=list[ProblemRow])
    unreadable: list[UnreadableFile] = field(default_factory=list[UnreadableFile])
    touched: list[Path] = field(default_factory=list[Path])
    roots: int = 0
    files: set[str] = field(default_factory=set[str])
    hook_files: list[AgentFile] = field(default_factory=list[AgentFile])

    # ------------------------------------------------------------ reading

    def _note(self, bad: UnreadableFile) -> None:
        """Keep a failure. A vanished file or folder is no failure."""
        if bad.reason != "vanished":
            self.unreadable.append(bad.model_copy(update={"part": PART}))

    def _list(self, path: str, *, plugin: bool) -> list[str] | None:
        self.touched.append(Path(path))
        got = read_scope.list_dir(self.scope, path, plugin=plugin)
        if isinstance(got, UnreadableFile):
            self._note(got)
            return None
        return got

    def _text(self, path: str, *, plugin: bool) -> tuple[str, str | None] | None:
        """Return (text, real path) of a file, or None after noting why not."""
        self.touched.append(Path(path))
        got = read_scope.read_snapshot(self.scope, path, FILE_CAP_BYTES, plugin=plugin)
        if isinstance(got, UnreadableFile):
            self._note(got)
            return None
        try:
            text = got.data.decode("utf-8")
        except UnicodeDecodeError:
            self._note(self.scope.unreadable(path, "not_utf8"))
            return None
        # ``got.real_path`` is absolute (a followed link out of the roots). Show it as
        # a display path, never raw.
        real = (
            self.scope.display(got.real_path)
            if got.real_path
            else read_scope.symlink_target(self.scope, path)
        )
        return text, real

    # ------------------------------------------------------------ one file

    def _add(  # noqa: PLR0913 - one file and where it sits
        self,
        path: str,
        *,
        scope: SetupScope,
        plugin: str | None,
        command: bool,
        name: str,
        root: str,
    ) -> None:
        here = os.path.abspath(path)
        if here in self.files:  # handed twice, as a folder and inside a root
            return
        self.files.add(here)
        got = self._text(path, plugin=plugin is not None)
        if got is None:
            return
        text, real = got
        fm = front_matter.parse(text)
        key, line = _anchor(fm, command=command)
        if not command and fm.state == "ok":
            named = fm.data.get("name")
            if isinstance(named, str) and named.strip():
                name = named.strip()
        entry = _Entry(
            scope=scope,
            plugin=plugin,
            name=name,
            command=command,
            root=root,
            order=self.roots,
            display=self.scope.display(path),
            full_path=os.path.abspath(path),
            real_path=real,
            fm=fm,
            key=key,
            line=line,
            description=fm.data.get("description") if fm.state == "ok" else None,
        )
        if fm.state == "invalid":
            entry.status = "invalid"
            entry.code = "frontmatter_invalid"
            entry.code_line = fm.error_line
        self.entries.append(entry)

    def _skill_folder(self, folder: str, scope: SetupScope, plugin: str | None) -> None:
        """Read the ``SKILL.md`` of one skill folder, or report that it has none."""
        names = self._list(folder, plugin=plugin is not None)
        if names is None:
            return
        if SKILL_FILE not in names:
            self.problems.append(self._no_file(folder, scope, plugin))
            return
        self._add(
            os.path.join(folder, SKILL_FILE),
            scope=scope,
            plugin=plugin,
            command=False,
            name=os.path.basename(folder),
            root=os.path.dirname(folder),
        )

    def _no_file(
        self, folder: str, scope: SetupScope, plugin: str | None
    ) -> ProblemRow:
        shown = self.scope.display(folder)
        return setup_items.make_problem(
            code="skill_no_md",
            group="wont_load",
            kind="problem",
            part=PART,
            thing=os.path.basename(folder),
            item=None,
            file=shown,
            full_path=os.path.abspath(folder),
            line=None,
            params={"folder": shown},
            confidence=setup_items.DOCUMENTED,
            fix=_fix(None, os.path.abspath(folder), scope, plugin),
        )

    # ------------------------------------------------------------ roots

    def skills_root(self, root: str, scope: SetupScope, plugin: str | None) -> None:
        """Read a folder of skill folders."""
        self.roots += 1
        names = self._list(root, plugin=plugin is not None)
        if names is None:
            return
        for name in names:
            path = os.path.join(root, name)
            if not name.startswith(".") and os.path.isdir(path):
                self._skill_folder(path, scope, plugin)

    def plugin_skills(self, path: str, plugin: str) -> None:
        """Read a plugin's skills path: one skill folder, or a folder of them."""
        names = self._list(path, plugin=True)
        if names is None:
            return
        if SKILL_FILE in names:
            self.roots += 1
            self._skill_folder(path, "plugin", plugin)
            return
        self.skills_root(path, "plugin", plugin)

    def commands_root(self, root: str, scope: SetupScope, plugin: str | None) -> None:
        """Read a folder of ``*.md`` command files, or one such file."""
        self.roots += 1
        if root.endswith(".md"):
            self._command(root, scope, plugin, os.path.dirname(root))
            return
        names = self._list(root, plugin=plugin is not None)
        if names is None:
            return
        for name in names:
            if name.endswith(".md") and not name.startswith("."):
                self._command(os.path.join(root, name), scope, plugin, root)

    def _command(
        self, path: str, scope: SetupScope, plugin: str | None, root: str
    ) -> None:
        self._add(
            path,
            scope=scope,
            plugin=plugin,
            command=True,
            name=os.path.basename(path)[: -len(".md")],
            root=root,
        )

    # ------------------------------------------------------------ the run

    def run(self) -> Collected:
        """Read every place and build the items."""
        ctx = self.ctx
        if ctx.managed_dir is not None:
            self.skills_root(
                os.path.join(ctx.managed_dir, ".claude", "skills"), "managed", None
            )
        self.skills_root(os.path.join(ctx.config_dir, "skills"), "user", None)
        self.commands_root(os.path.join(ctx.config_dir, "commands"), "user", None)
        if ctx.project_dir is not None:
            self._project(str(ctx.project_dir))
        for found in plugin_paths(self.handoff):
            if found.command:
                self.commands_root(found.path, "plugin", found.plugin)
            else:
                self.plugin_skills(found.path, found.plugin)
        items = self._items()
        return Collected(
            items={PART: setup_items.number(items)},
            problems=setup_items.sort_problems(self.problems),
            unreadable=self.unreadable,
            touched=self.touched,
            handoff={HANDOFF_SKILL_HOOKS: self.hook_files},
        )

    def _project(self, project: str) -> None:
        claude = os.path.join(project, ".claude")
        own = os.path.join(claude, "skills")
        self.skills_root(own, "project", None)
        found = read_scope.walk(self.scope, project)
        self.touched.extend(Path(folder) for folder in found.touched)
        done = {os.path.realpath(own)}
        nested = sorted(
            hit.path
            for hit in found.hits
            if hit.kind == "skills" and os.path.realpath(hit.path) not in done
        )
        for folder in nested:
            self.skills_root(folder, "project", None)
        self.commands_root(os.path.join(claude, "commands"), "project", None)

    # ------------------------------------------------------------ the items

    def _items(self) -> list[SetupItem]:
        groups: dict[tuple[str | None, str], list[_Entry]] = {}
        for entry in self.entries:
            groups.setdefault(entry.group, []).append(entry)
        out: list[SetupItem] = []
        for key in sorted(groups, key=_group_key):
            out.append(self._item(key, groups[key]))
        return out

    def _item(self, key: tuple[str | None, str], found: list[_Entry]) -> SetupItem:
        plugin, name = key
        ordered = sorted(found, key=_Entry.rank)
        self._settle(ordered)
        won = next((e for e in ordered if e.status == "in_effect"), None)
        lead = won or ordered[0]
        if won is not None:
            self._hand_on_hooks(won)
        item_id = _item_id(plugin, name)
        sources = [
            setup_items.source_of(
                scope=e.scope,
                key=e.key,
                file=e.display,
                full_path=e.full_path,
                line=e.line,
                value=None,
                status=e.status,
            ).model_copy(update={"plugin": e.plugin})
            for e in ordered
        ]
        status: ModelCheckStatus = "in_effect" if won is not None else "invalid"
        other = next((e.display for e in ordered if e is not lead), None)
        params = {"file": lead.display} | ({"other_file": other} if other else {})
        item = setup_items.make_item(
            part=PART,
            key=name,
            name=name,
            item_id=item_id,
            label_known=True,
            scope=lead.scope,
            status=status,
            sources=sources,
            winner=ordered.index(won) if won is not None else None,
            reach_=setup_items.reach(["plugin"] if plugin else _SCOPES_VISIBLE),
            # The docs say managed beats user beats project and a skill beats a
            # command, but not which wins when the two disagree. Scope first is ours.
            confidence=(
                setup_items.ASSUMED
                if len({e.command for e in ordered}) > 1
                else setup_items.DOCUMENTED
            ),
            reason=ItemReason(code=status, params=params, rule_id=None, ref_item=None),
            facts=ItemFacts(skill=_facts(lead, plugin, name)),
            read_only=_read_only(lead.scope, plugin),
            real_path=lead.real_path,
            changeable=_may_change(self.unreadable, lead.scope),
        )
        for entry in ordered:
            if entry.code is not None:
                self.problems.append(self._problem(item, entry))
        return item

    def _hand_on_hooks(self, entry: _Entry) -> None:
        """Keep the ``hooks`` of a loading skill's front matter for the Hooks part.

        Docs (https://code.claude.com/docs/en/hooks.md, "Limits on skill hooks"): a
        plugin skill keeps its front matter hooks, unlike a plugin agent. So nothing is
        marked ignored here. Only the masked field leaves this module.
        """
        if entry.fm.state != "ok" or entry.fm.data.get("hooks") is None:
            return
        self.hook_files.append(
            AgentFile(
                layer=entry.scope,
                plugin=entry.plugin,
                path=entry.full_path,
                rel=os.path.basename(entry.full_path),
                display=entry.display,
                full_path=entry.full_path,
                real_path=entry.real_path,
                name=entry.name,
                fields=[
                    front_matter_field(
                        "hooks", entry.fm.data["hooks"], entry.fm.lines.get("hooks")
                    )
                ],
            )
        )

    @staticmethod
    def _settle(ordered: list[_Entry]) -> None:
        """Set each entry's status: the first valid one wins, the rest lose."""
        won = False
        seen: set[tuple[SetupScope, str, bool]] = set()
        for entry in ordered:
            here = (entry.scope, entry.root, entry.command)
            if entry.code == "frontmatter_invalid":
                continue
            if here in seen:
                entry.status = "invalid"
                entry.code = "same_name_in_folder"
                entry.code_line = entry.line
                continue
            seen.add(here)
            entry.status = "overridden" if won else "in_effect"
            won = True

    def _problem(self, item: SetupItem, entry: _Entry) -> ProblemRow:
        code = entry.code or ""
        return setup_items.make_problem(
            code=code,
            group="wont_load",
            kind="problem",
            part=PART,
            thing=item.name,
            item=item,
            file=entry.display,
            full_path=entry.full_path,
            line=entry.code_line,
            params={"file": entry.display},
            confidence=setup_items.DOCUMENTED,
            fix=_fix(item.id, entry.full_path, entry.scope, entry.plugin),
        )


# ---------------------------------------------------------------- helpers


def _anchor(fm: front_matter.FrontMatter, *, command: bool) -> tuple[str, int | None]:
    """Return the front matter key that names the item and its line."""
    for key in ("description",) if command else ("name", "description"):
        if key in fm.lines:
            return key, fm.lines[key]
    return "file", None


def _item_id(plugin: str | None, name: str) -> str:
    return f"{PART}:{plugin}:{name}" if plugin else f"{PART}:{name}"


def _group_key(key: tuple[str | None, str]) -> str:
    plugin, name = key
    return f"{plugin}:{name}" if plugin else name


def _facts(lead: _Entry, plugin: str | None, name: str) -> SkillFacts:
    shown = None
    text = lead.description
    if text is not None:
        raw = text if isinstance(text, str) else str(text)
        shown = masking.masked_text(raw.strip(), "description")
    return SkillFacts(
        description=shown,
        invoke=f"/{plugin}:{name}" if plugin else f"/{name}",
        namespace=plugin,
        legacy_command=lead.command,
    )


def _may_change(unreadable: Sequence[UnreadableFile], winner: SetupScope) -> bool:
    """True when a file that could not be read could change this item's answer.

    Skills rank managed, user, project, which is not the settings order, so a failed
    user file can change a project skill. A plugin skill has its own namespace, so only
    a failed plugin file can change it. A file the scope refused is no failure.
    """
    for file in unreadable:
        if file.reason in ("outside_scope", "plugin_outside_plugins"):
            continue
        if winner == "plugin":
            if file.scope == "plugin":
                return True
        elif file.scope is None or (
            file.scope in _RANK and _RANK[file.scope] <= _RANK[winner]
        ):
            return True
    return False


def _read_only(scope: SetupScope, plugin: str | None) -> ReadOnly | None:
    if scope == "plugin":
        return ReadOnly(code="plugin", params={"plugin": plugin or ""}, command=None)
    return setup_items.read_only_for(scope)


def _fix(
    item_id: str | None, full_path: str, scope: SetupScope, plugin: str | None
) -> ProblemFix:
    """Return the one action a row offers: managed and plugin files can't be changed."""
    if scope == "managed":
        return ProblemFix(kind="cant_fix_here", target=None, reason="managed")
    if scope == "plugin":
        return ProblemFix(kind="cant_fix_here", target=None, reason="plugin")
    if item_id is not None:
        return ProblemFix(kind="open_item", target=item_id, reason=None)
    return ProblemFix(kind="copy_path", target=full_path, reason=None)


def _from_mapping(raw: Mapping[object, object]) -> list[PluginPath]:
    found: list[PluginPath] = []
    for kind in ("skills", "commands"):
        listed = raw.get(kind)
        if not isinstance(listed, list):
            continue
        for one in cast("list[object]", listed):
            if not isinstance(one, Mapping):
                continue
            row = cast("Mapping[str, object]", one)
            plugin, path = row.get("plugin"), row.get("path")
            if isinstance(plugin, str) and isinstance(path, str):
                found.append(
                    PluginPath(plugin.split("@")[0], path, command=kind == "commands")
                )
    return found


def plugin_paths(handoff: Mapping[str, object]) -> list[PluginPath]:
    """Return every skills and commands path the plugins collector handed on.

    Accepts a list of ``PluginComponents`` (the plugins collector's own handoff) or the
    mapping shape in the module docstring. Anything else is no plugin input.
    """
    raw = handoff.get(HANDOFF_PLUGINS)
    if isinstance(raw, Mapping):
        return _from_mapping(cast("Mapping[object, object]", raw))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    found: list[PluginPath] = []
    for comp in cast("Sequence[object]", raw):
        if isinstance(comp, PluginComponents):
            found += [PluginPath(comp.name, p, command=False) for p in comp.skills]
            found += [PluginPath(comp.name, p, command=True) for p in comp.commands]
    return found


class SkillsCollector:
    """The collector of part ``skills``."""

    name = "skills"
    parts: Sequence[SetupPart] = (PART,)

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the skills and legacy commands of the project. Never raises."""
        return _Run(ctx, read_scope.Scope(ctx), handoff).run()

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Return a stat-only fingerprint of what the last read touched."""
        scope = read_scope.Scope(ctx)
        paths = last.touched if last is not None else _candidates(ctx)
        return read_scope.stat_signature(scope, paths)


def _candidates(ctx: SetupContext) -> list[Path]:
    """Return the skills and commands folders a first signature fingerprints."""
    found = [Path(ctx.config_dir) / "skills", Path(ctx.config_dir) / "commands"]
    if ctx.managed_dir is not None:
        found.append(ctx.managed_dir / ".claude" / "skills")
    if ctx.project_dir is not None:
        claude = ctx.project_dir / ".claude"
        found += [claude / "skills", claude / "commands"]
    return found


COLLECTOR = SkillsCollector()

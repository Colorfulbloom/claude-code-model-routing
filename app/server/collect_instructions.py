"""The CLAUDE.md and Rules files collector (m4-build.md task 7).

It feeds the parts ``instructions`` and ``rules``.

Part ``instructions`` has one item per file Claude Code loads, in load order.

1. Managed ``<managed>/CLAUDE.md``, then user ``<config>/CLAUDE.md``.
2. Every ancestor folder's ``CLAUDE.md`` and ``CLAUDE.local.md`` up to the filesystem
   root, root first (owner pick 6, November 9). They carry ``location: "parent"`` and
   show as "Parent folder" under Shared project. The ancestor reads are the exact two
   names only, which ``read_scope`` allows.
3. The project's ``CLAUDE.md``, ``.claude/CLAUDE.md`` and ``CLAUDE.local.md``.
4. ``AGENTS.md`` in the project, only when none of the files above (in the project or
   an ancestor) exists, with ``loads: when_no_claude_md`` (docs, v2.1.277 and later).
5. Nested ``CLAUDE.md`` and ``CLAUDE.local.md`` files from the capped walk of
   ``read_scope`` below the project, with ``loads: on_demand``.

An ``@path`` import is read right after its importer, depth first, so the order of the
items is the order Claude Code reads the files. The path is relative to the importing
file, and ``~/`` is the context home. Imports in code spans, fenced blocks and HTML
comments are skipped, and so is a token with no ``/`` and no ``.`` (a plain ``@name``
is a mention, not a path). The hop limit is four (docs). An import is one of

- ``read``: the target loaded (an item), or already loaded as an item before.
- ``missing``: no such file (Won't load, ``import_missing``).
- ``cycle``: the target is already open in this chain. It is reported once, at the
  import that closes the loop (Won't load, ``import_cycle``).
- ``too_deep``: past four hops, not opened (Won't load, ``import_too_deep``).
- ``not_read``: the target lies outside the allowed roots, so it is never opened. It
  gets an ``UnreadableFile`` with ``outside_scope`` and no problem id, and its importer
  gets a Can't tell row, ``import_out_of_scope``. A target that exists but could not be
  read (permission, not UTF-8, too large) is also ``not_read``, with its own reason.

Part ``rules`` has one item per ``*.md`` file in ``<config>/rules/`` and
``<project>/.claude/rules/`` (searched recursively, docs), user first. Only ``paths``
is read from the front matter, as a YAML list or a comma separated string. It becomes
``loads: on_demand`` with its globs. Without ``paths`` the rule loads at launch. Bad
front matter loads the rule with no paths, and is Not as set, ``ignored``.

A file's body is read in memory for imports, ``paths`` and line counts and never kept.
Only the line number of each import goes into an answer. Auto memory is never read, and
``read_scope`` refuses it anyway.

The nested walk reports a folder it could not list, and a walk a cap stopped
(``walk_stopped``, Can't tell). The skills collector runs the same walk and leaves both
to this one, so a row shows once.
"""

# ruff: noqa: PTH100, PTH112, PTH117, PTH118, PTH119, PTH120 - paths are strings, as
# ``read_scope`` and ``agent_files`` handle them.

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import cast

import agent_md
import front_matter
import read_scope
import setup_items
from models import (
    ImportRef,
    ImportState,
    InstructionFacts,
    ItemFacts,
    ItemReason,
    LoadsKind,
    ProblemFix,
    ProblemGroup,
    ProblemKind,
    ProblemRow,
    SetupItem,
    SetupLoads,
    SetupLocation,
    SetupPart,
    SetupScope,
    UnreadableFile,
)
from setup_contract import FILE_CAP_BYTES, Collected, SetupContext

MAX_HOPS = 4
RULES_DEPTH = 8
FILES = ("CLAUDE.md", "CLAUDE.local.md")
_IMPORT = re.compile(r"(?<![^\s(])@(\S+)")
_CODE_SPAN = re.compile(r"`[^`]*`")
_TRAILING = ".,;:!?)\"'"
_OUTSIDE = ("outside_scope", "plugin_outside_plugins")


# ---------------------------------------------------------------- import syntax


def _strip_comments(line: str, inside: bool) -> tuple[str, bool]:
    """Cut HTML comments out of a line. ``inside`` says a comment is open already."""
    while True:
        if inside:
            end = line.find("-->")
            if end == -1:
                return "", True
            line, inside = line[end + 3 :], False
            continue
        start = line.find("<!--")
        if start == -1:
            return line, False
        end = line.find("-->", start + 4)
        if end == -1:
            return line[:start], True
        line = line[:start] + " " + line[end + 3 :]


def import_refs(text: str) -> list[tuple[str, int]]:
    """Return the ``@path`` imports of a file's text as (target, 1-based line).

    Code spans, fenced blocks and HTML comments are skipped. A token needs a ``/`` or a
    ``.`` to count as a path, and a trailing sentence mark is not part of it.
    """
    found: list[tuple[str, int]] = []
    fence: str | None = None
    comment = False
    for number, raw in enumerate(agent_md.LINE_RE.findall(text), start=1):
        line = agent_md.split_line(raw)[0]
        stripped = line.lstrip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            continue
        line, comment = _strip_comments(line, comment)
        line = _CODE_SPAN.sub(" ", line)
        for match in _IMPORT.finditer(line):
            target = match.group(1).rstrip(_TRAILING)
            if target and ("/" in target or "." in target):
                found.append((target, number))
    return found


def _count_lines(text: str) -> int:
    if text == "":
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


# ---------------------------------------------------------------- the run


@dataclass
class _Opened:
    """A file's text, its size and where it really is."""

    text: str
    size: int
    real_path: str | None


@dataclass(frozen=True)
class _Outcome:
    """How one import went.

    Attributes:
        state: The ``ImportRef`` state.
        item: The target's item id when it is an item.
        code: The code of the To fix row the import makes, or None for none.
        failed: True when the target exists but could not be read, so the importer's
            answer may be incomplete.
    """

    state: ImportState
    item: str | None
    code: str | None
    failed: bool = False

    @property
    def row(self) -> tuple[ProblemGroup, ProblemKind]:
        """Return the group and kind of the row ``code`` makes."""
        if self.code == "import_out_of_scope":
            return "cant_tell", "cant_tell"
        return "wont_load", "problem"


@dataclass
class _Run:
    """One read of a project's instruction and rules files."""

    ctx: SetupContext
    scope: read_scope.Scope
    items: list[SetupItem] = field(default_factory=list[SetupItem])
    rules: list[SetupItem] = field(default_factory=list[SetupItem])
    problems: list[ProblemRow] = field(default_factory=list[ProblemRow])
    unreadable: list[UnreadableFile] = field(default_factory=list[UnreadableFile])
    touched: list[Path] = field(default_factory=list[Path])
    seen: dict[str, str] = field(default_factory=dict[str, str])
    excludes: list[tuple[str, re.Pattern[str]]] = field(
        default_factory=list[tuple[str, re.Pattern[str]]]
    )

    # ------------------------------------------------------------ reading

    def _excluded(self, path: str, scope_name: SetupScope) -> str | None:
        """Return the ``claudeMdExcludes`` pattern that skips a file, or None.

        A pattern is matched against the absolute path, and for a symlink against
        either the link or its target. A managed CLAUDE.md can't be excluded.
        """
        if scope_name == "managed" or not self.excludes:
            return None
        forms = {os.path.abspath(path), os.path.realpath(path)}
        for pattern, rx in self.excludes:
            if any(rx.match(form) for form in forms):
                return pattern
        return None

    def _note(self, bad: UnreadableFile, part: SetupPart) -> None:
        """Keep a failure. A vanished file is no failure."""
        if bad.reason != "vanished":
            self.unreadable.append(bad.model_copy(update={"part": part}))

    def _open(
        self, path: str, part: SetupPart, scope_name: SetupScope
    ) -> _Opened | UnreadableFile:
        """Read a file. A failure carries the part and the scope the file belongs to."""
        self.touched.append(Path(path))
        stamp = {"part": part, "scope": scope_name}
        got = read_scope.read_snapshot(self.scope, path, FILE_CAP_BYTES)
        if isinstance(got, UnreadableFile):
            return got.model_copy(update=stamp)
        try:
            text = got.data.decode("utf-8")
        except UnicodeDecodeError:
            bad = self.scope.unreadable(path, "not_utf8")
            return bad.model_copy(update=stamp)
        # ``got.real_path`` is absolute (a followed link out of the roots). Show it as
        # a display path, never raw.
        real = (
            self.scope.display(got.real_path)
            if got.real_path
            else read_scope.symlink_target(self.scope, path)
        )
        return _Opened(text, len(got.data), real)

    def _scope_of(self, path: str) -> SetupScope:
        found = self.scope.scope_of(path)
        if os.path.basename(path) == "CLAUDE.local.md" and found in (None, "project"):
            return "project_local"
        return found if found is not None else "project"

    # ------------------------------------------------------------ one file

    def _item(  # noqa: PLR0913, PLR0917 - one file and what is known about it
        self,
        path: str,
        opened: _Opened,
        scope_name: SetupScope,
        location: SetupLocation | None,
        loads: SetupLoads,
        imports: list[ImportRef],
        part: SetupPart = "instructions",
        *,
        failed: bool = False,
    ) -> SetupItem:
        display = self.scope.display(path)
        src = setup_items.source_of(
            scope=scope_name,
            key="file",
            file=display,
            full_path=os.path.abspath(path),
            line=None,
            value=None,
            status="in_effect",
        ).model_copy(update={"location": location})
        visible: list[SetupScope] = (
            ["user", "project"]
            if part == "rules"
            else ["managed", "user", "project_local", "project"]
        )
        item = setup_items.make_item(
            part=part,
            key=display,
            name=display,
            label_known=True,
            scope=scope_name,
            status="in_effect",
            sources=[src],
            winner=0,
            reach_=setup_items.reach(visible),
            confidence=setup_items.DOCUMENTED,
            reason=ItemReason(code="in_effect", params={}, rule_id=None, ref_item=None),
            facts=ItemFacts(
                instruction=InstructionFacts(
                    lines=_count_lines(opened.text),
                    bytes=opened.size,
                    imports=imports,
                )
            ),
            read_only=setup_items.read_only_for(scope_name),
            real_path=opened.real_path,
            changeable=failed,
        )
        return item.model_copy(update={"loads": loads, "location": location})

    def start(
        self,
        path: str,
        scope_name: SetupScope,
        *,
        location: SetupLocation | None = None,
        loads: LoadsKind = "always",
    ) -> bool:
        """Read one file Claude Code loads by itself. True when it was read."""
        got = self._open(path, "instructions", scope_name)
        if isinstance(got, UnreadableFile):
            if got.reason != "vanished":
                self.unreadable.append(got)
            return False
        if os.path.realpath(path) in self.seen:
            return True
        self._take(path, got, scope_name, location, loads, 0, ())
        return True

    def _take(  # noqa: PLR0913, PLR0917 - one file and where it sits in a chain
        self,
        path: str,
        opened: _Opened,
        scope_name: SetupScope,
        location: SetupLocation | None,
        loads: LoadsKind,
        depth: int,
        above: tuple[str, ...],
    ) -> str:
        """Add a file's item, then its imports depth first. Return the item id."""
        real = os.path.realpath(path)
        at = len(self.items)
        shown = SetupLoads(kind=loads, globs=[])
        first = self._item(path, opened, scope_name, location, shown, [])
        pattern = self._excluded(path, scope_name)
        if pattern is not None:
            # An excluded file is not loaded, so its imports are not followed.
            first = _ignored(first, pattern)
            self.items.append(first)
            self.seen[real] = first.id
            return first.id
        self.items.append(first)
        self.seen[real] = first.id
        refs: list[ImportRef] = []
        codes: list[tuple[_Outcome, int, str]] = []
        failed = False
        for target, line in import_refs(opened.text):
            out = self._follow(
                path, target, depth + 1, (*above, real), loads, scope_name
            )
            refs.append(
                ImportRef(
                    target=target,
                    target_item=out.item,
                    depth=depth + 1,
                    state=out.state,
                    line=line,
                )
            )
            failed = failed or out.failed
            if out.code is not None:
                codes.append((out, line, target))
        final = self._item(
            path, opened, scope_name, location, shown, refs, failed=failed
        )
        self.items[at] = final
        self.problems.extend(self._import_row(final, *one) for one in codes)
        return final.id

    # ------------------------------------------------------------ imports

    def _resolve(self, importer: str, target: str) -> str | None:
        if target.startswith("~/"):
            home = self.ctx.home
            return os.path.normpath(os.path.join(home, target[2:])) if home else None
        if os.path.isabs(target):
            return os.path.normpath(target)
        return os.path.normpath(os.path.join(os.path.dirname(importer), target))

    def _outside_display(self, path: str) -> str:
        project = self.ctx.project_dir
        if project is not None:
            return Path(os.path.relpath(path, str(project))).as_posix()
        home = self.ctx.home
        if home is not None:
            rel = Path(os.path.relpath(path, str(home))).as_posix()
            if not rel.startswith(".."):
                return f"~/{rel}"
        return os.path.basename(path)

    def _follow(  # noqa: PLR0913, PLR0917 - one import and its chain
        self,
        importer: str,
        target: str,
        hop: int,
        chain: tuple[str, ...],
        loads: LoadsKind,
        owner_scope: SetupScope,
    ) -> _Outcome:
        """Follow one import and say how it went."""
        dest = self._resolve(importer, target)
        if dest is None:
            return _Outcome("not_read", None, "import_out_of_scope")
        real = os.path.realpath(dest)
        if real in chain:
            return _Outcome("cycle", self.seen.get(real), "import_cycle")
        if hop > MAX_HOPS:
            return _Outcome("too_deep", None, "import_too_deep")
        if real in self.seen:
            return _Outcome("read", self.seen[real], None)
        got = self._open(dest, "instructions", self._scope_of(dest))
        if isinstance(got, UnreadableFile):
            return self._failed(got, dest, owner_scope)
        item_id = self._take(dest, got, self._scope_of(dest), None, loads, hop, chain)
        return _Outcome("read", item_id, None)

    def _failed(
        self, got: UnreadableFile, dest: str, owner_scope: SetupScope
    ) -> _Outcome:
        """Keep a target that could not be opened, and say how the import went."""
        if got.reason == "vanished":
            return _Outcome("missing", None, "import_missing")
        if got.reason in _OUTSIDE:
            shown = got.model_copy(
                update={
                    "file": self._outside_display(dest),
                    "scope": owner_scope,
                    "problem": None,
                }
            )
            self.unreadable.append(shown)
            return _Outcome("not_read", None, "import_out_of_scope")
        self.unreadable.append(got)
        return _Outcome("not_read", None, None, failed=True)

    def _import_row(
        self, owner: SetupItem, out: _Outcome, line: int, target: str
    ) -> ProblemRow:
        source = owner.sources[0]
        fix = (
            ProblemFix(kind="cant_fix_here", target=None, reason="managed")
            if source.scope == "managed"
            else ProblemFix(kind="open_item", target=owner.id, reason=None)
        )
        group, kind = out.row
        return setup_items.make_problem(
            code=out.code or "",
            group=group,
            kind=kind,
            part="instructions",
            thing=owner.name,
            item=owner,
            file=source.file,
            full_path=source.full_path,
            line=line,
            params={"target": target},
            confidence=setup_items.DOCUMENTED,
            fix=fix,
        )

    # ------------------------------------------------------------ rules

    def rules_folder(
        self,
        folder: str,
        scope_name: SetupScope,
        depth: int = 0,
        seen: set[str] | None = None,
    ) -> None:
        """Read the ``*.md`` rules files of a folder and the folders below it."""
        done = seen if seen is not None else set[str]()
        real = os.path.realpath(folder)
        if real in done or depth > RULES_DEPTH:
            return
        done.add(real)
        self.touched.append(Path(folder))
        names = read_scope.list_dir(self.scope, folder)
        if isinstance(names, UnreadableFile):
            self._note(names, "rules")
            return
        for name in names:
            if name.startswith("."):
                continue
            path = os.path.join(folder, name)
            if name.endswith(".md"):
                self._rule(path, scope_name)
            elif os.path.isdir(path):
                self.rules_folder(path, scope_name, depth + 1, done)

    def _rule(self, path: str, scope_name: SetupScope) -> None:
        got = self._open(path, "rules", scope_name)
        if isinstance(got, UnreadableFile):
            self._note(got, "rules")
            return
        fm = front_matter.parse(got.text)
        globs, bad = _globs(fm)
        key, line = (
            ("paths", fm.lines["paths"]) if "paths" in fm.lines else ("file", None)
        )
        loads = (
            SetupLoads(kind="on_demand", globs=globs)
            if globs
            else SetupLoads(kind="always", globs=[])
        )
        item = self._item(path, got, scope_name, None, loads, [], part="rules")
        src = item.sources[0].model_copy(update={"key": key, "line": line})
        item = item.model_copy(
            update={
                "sources": [src],
                "reason": ItemReason(
                    code="frontmatter_invalid" if bad else "in_effect",
                    params={},
                    rule_id=None,
                    ref_item=None,
                ),
            }
        )
        pattern = self._excluded(path, scope_name)
        if pattern is not None:
            self.rules.append(_ignored(item, pattern))
            return
        self.rules.append(item)
        if bad:
            self.problems.append(
                setup_items.make_problem(
                    code="ignored",
                    group="not_as_set",
                    kind="problem",
                    part="rules",
                    thing=item.name,
                    item=item,
                    file=src.file,
                    full_path=src.full_path,
                    line=line if line is not None else fm.error_line,
                    params={"key": "paths"},
                    confidence=setup_items.DOCUMENTED,
                    fix=ProblemFix(kind="open_item", target=item.id, reason=None),
                )
            )

    # ------------------------------------------------------------ the run

    def run(self) -> Collected:
        """Read every place and build the items."""
        ctx = self.ctx
        if ctx.managed_dir is not None:
            self.start(os.path.join(ctx.managed_dir, "CLAUDE.md"), "managed")
        self.start(os.path.join(ctx.config_dir, "CLAUDE.md"), "user")
        self.rules_folder(os.path.join(ctx.config_dir, "rules"), "user")
        if ctx.project_dir is not None:
            self._project(os.path.realpath(str(ctx.project_dir)))
        return Collected(
            items={
                "instructions": setup_items.number(self.items),
                "rules": setup_items.number(self.rules),
            },
            problems=setup_items.sort_problems(self.problems),
            unreadable=self.unreadable,
            touched=self.touched,
        )

    def _project(self, project: str) -> None:
        found = self._ancestors(project)
        found = self._own_files(project) or found
        if not found:
            self.start(
                os.path.join(project, "AGENTS.md"),
                "project",
                loads="when_no_claude_md",
            )
        self.rules_folder(os.path.join(project, ".claude", "rules"), "project")
        self._nested(project)

    def _ancestors(self, project: str) -> bool:
        """Read the CLAUDE files above the project, root first. True if any exists."""
        parents: list[str] = []
        here = project
        while (above := os.path.dirname(here)) != here:
            parents.append(above)
            here = above
        found = False
        for folder in reversed(parents):
            for name in FILES:
                path = os.path.join(folder, name)
                scope_name: SetupScope = (
                    "project_local" if name == "CLAUDE.local.md" else "project"
                )
                found = self.start(path, scope_name, location="parent") or found
        return found

    def _own_files(self, project: str) -> bool:
        found = False
        for rel, scope_name in (
            ("CLAUDE.md", "project"),
            (os.path.join(".claude", "CLAUDE.md"), "project"),
            ("CLAUDE.local.md", "project_local"),
        ):
            path = os.path.join(project, rel)
            found = self.start(path, cast("SetupScope", scope_name)) or found
        return found

    def _nested(self, project: str) -> None:
        """Read nested CLAUDE files from the capped walk, as on demand."""
        walked = read_scope.walk(self.scope, project)
        self.touched.extend(Path(folder) for folder in walked.touched)
        for bad in walked.unreadable:
            self._note(bad, "instructions")
        root = os.path.realpath(project)
        hits = sorted(
            (
                PurePosixPath(self.scope.display(hit.path)).parent.parts,
                hit.kind == "claude_local_md",
                hit.path,
            )
            for hit in walked.hits
            if hit.kind in ("claude_md", "claude_local_md")
            and os.path.dirname(hit.path) != root
        )
        for _parts, _local, path in hits:
            if os.path.realpath(path) in self.seen:
                continue
            self.start(path, self._scope_of(path), loads="on_demand")
        if walked.stopped:
            self.problems.append(self._stopped(project))

    def _stopped(self, project: str) -> ProblemRow:
        return setup_items.make_problem(
            code="walk_stopped",
            group="cant_tell",
            kind="cant_tell",
            part="instructions",
            thing="CLAUDE.md",
            item=None,
            file=self.scope.display(project),
            full_path=project,
            line=None,
            params={},
            confidence=setup_items.DOCUMENTED,
            fix=ProblemFix(kind="cant_fix_here", target=None, reason="walk_stopped"),
            subject="instructions",
        )


# ---------------------------------------------------------------- helpers


EXCLUDES_ITEM = "settings:claudeMdExcludes"


def excludes_from(handoff: Mapping[str, object]) -> list[str]:
    """Return the ``claudeMdExcludes`` patterns of every settings layer, concatenated.

    Source: https://code.claude.com/docs/en/memory#exclude-specific-claude-md-files
    ("Arrays merge across layers", at any settings layer: user, project, local or
    managed; "Patterns are matched against absolute file paths using glob syntax"; "You
    can't exclude a managed CLAUDE.md file"). The settings collector hands its
    ``Layers`` on in ``handoff["settings"]["layers"]``. Anything else is no patterns.
    """
    settings = handoff.get("settings")
    layers: object = (
        cast("Mapping[str, object]", settings).get("layers")
        if isinstance(settings, Mapping)
        else None
    )
    readable = getattr(layers, "readable", None)
    if not callable(readable):
        return []
    found: list[str] = []
    for file in cast("Sequence[object]", readable()):
        data: object = getattr(file, "data", None)
        listed = (
            cast("Mapping[str, object]", data).get("claudeMdExcludes")
            if isinstance(data, Mapping)
            else None
        )
        if isinstance(listed, list):
            found += [p for p in cast("list[object]", listed) if isinstance(p, str)]
    return list(dict.fromkeys(found))


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Turn a glob into a regex over an absolute path.

    ``**`` crosses folders (``**/`` may match none), ``*`` and ``?`` stay inside one
    folder name. Braces and brackets are plain text, which the docs don't promise.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _ignored(item: SetupItem, pattern: str) -> SetupItem:
    """Return the item as an excluded file: ignored, loads nothing, no problem row."""
    sources = [s.model_copy(update={"status": "ignored"}) for s in item.sources]
    facts = item.facts
    if facts.instruction is not None:
        facts = facts.model_copy(
            update={"instruction": facts.instruction.model_copy(update={"imports": []})}
        )
    return item.model_copy(
        update={
            "status": "ignored",
            "loads": None,
            "winner": None,
            "sources": sources,
            "facts": facts,
            "reason": ItemReason(
                code="ignored",
                params={"setting": "claudeMdExcludes", "pattern": pattern},
                rule_id=None,
                ref_item=EXCLUDES_ITEM,
            ),
        }
    )


def _globs(fm: front_matter.FrontMatter) -> tuple[list[str], bool]:
    """Return a rules file's ``paths`` globs and whether its front matter is bad."""
    if fm.state == "invalid":
        return [], True
    if "paths" not in fm.data or fm.data["paths"] is None:
        return [], False
    value = fm.data["paths"]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()], False
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [i.strip() for i in items if isinstance(i, str) and i.strip()], False
    return [], True


class InstructionsCollector:
    """The collector of parts ``instructions`` and ``rules``."""

    name = "instructions"
    parts: Sequence[SetupPart] = ("instructions", "rules")

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the project's CLAUDE.md and rules files. Never raises."""
        run = _Run(ctx, read_scope.Scope(ctx))
        run.excludes = [(p, _glob_regex(p)) for p in excludes_from(handoff)]
        return run.run()

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Return a stat-only fingerprint of what the last read touched."""
        scope = read_scope.Scope(ctx)
        paths = last.touched if last is not None else _candidates(ctx)
        return read_scope.stat_signature(scope, paths)


def _candidates(ctx: SetupContext) -> list[Path]:
    """Return the files and folders a first signature fingerprints."""
    config = Path(ctx.config_dir)
    found = [config / "CLAUDE.md", config / "rules"]
    if ctx.managed_dir is not None:
        found.append(ctx.managed_dir / "CLAUDE.md")
    if ctx.project_dir is not None:
        project = ctx.project_dir
        found += [
            project / "CLAUDE.md",
            project / ".claude" / "CLAUDE.md",
            project / "CLAUDE.local.md",
            project / ".claude" / "rules",
        ]
    return found


COLLECTOR = InstructionsCollector()

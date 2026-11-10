"""The Hooks collector (m4-build.md task 8, part ``hooks``).

One item per hook handler, keyed by event, matcher and handler. The id is
``hooks:<event>:<matcher or *>:<index>``, where the index counts the handlers of that
event and matcher in scope order (managed, local, project, user, plugin, then agent
front matter). Two more items hold the settings that switch hooks off,
``hooks:disableAllHooks`` and ``hooks:allowManagedHooksOnly``.

Where hooks come from (https://code.claude.com/docs/en/hooks.md, "Hook locations").

- The ``hooks`` key of every settings file, read from the settings collector's
  ``layers`` handoff, so no settings file is opened twice.
- A plugin's ``hooks/hooks.json`` and the ``hooks`` written inline in its manifest, from
  ``handoff["plugins"]`` (rows of ``{plugin, name, path}``, with ``inline`` for the
  manifest). A plugin hooks file may wrap its events in a ``hooks`` key, as the docs
  show.
- Agent front matter (``handoff["agent_files"]``). Claude Code turns ``Stop`` there into
  ``SubagentStop``, and a plugin agent's hooks are ignored, so they are skipped here.
- Skill front matter (``handoff["skill_hooks"]``, listed after the agents' own). A
  plugin skill keeps its hooks, unlike a plugin agent (hooks.md, "Limits on skill
  hooks"), and ``Stop`` stays ``Stop``.

Switches. ``disableAllHooks`` set in managed settings turns every hook off. Set anywhere
else it turns off every hook that is not managed. ``allowManagedHooksOnly`` (managed
settings only) blocks user, project, local and plugin hooks, except hooks of a plugin
force-enabled in managed ``enabledPlugins``. A blocked hook is ``ignored`` and its
reason names the switch's item in ``ref_item``. Each switch that blocks a hook also
makes one Not as set row, ``hooks_disabled``, on the switch's own item.

Problems are Won't load. An event that is not in the hooks page is ``hook_bad_event``. A
value that is not the event, matcher group, handler shape is ``hook_bad_handler``, and
a plugin hooks file that is not JSON is ``json_invalid``. Such a hook makes a row and no
item.

Order. Items come as the switches (by name), then the hooks in the page's lifecycle
order (``EVENTS``), and inside an event in scope order.
"""

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

import collect_settings
import command_mask
import json_lines
import masking
import plugin_inputs
import read_scope
import settings_layers
import setup_items
from agent_files import AgentFile
from models import (
    SETUP_SCOPES,
    Effective,
    HookFacts,
    ItemFacts,
    ItemReason,
    MaskedText,
    ModelCheckStatus,
    ProblemFix,
    ProblemRow,
    ReadOnly,
    SetupItem,
    SetupPart,
    SetupScope,
    SetupSource,
    UnreadableFile,
)
from setup_contract import FILE_CAP_BYTES, Collected, SetupContext

PART: SetupPart = "hooks"
HANDOFF_AGENT_FILES = "agent_files"
HANDOFF_SKILL_HOOKS = "skill_hooks"
HANDOFF_SETTINGS = "settings"
FLAG_ALL = "disableAllHooks"
FLAG_MANAGED = "allowManagedHooksOnly"
FLAGS = (FLAG_ALL, FLAG_MANAGED)

# The events of https://code.claude.com/docs/en/hooks.md, in the order its "Hook events"
# section lists them ("ordered to match the lifecycle: from session setup through the
# agentic loop to session end"). 33 events, read on November 9, 2026.
EVENTS: tuple[str, ...] = (
    "SessionStart",
    "Setup",
    "InstructionsLoaded",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "MessageDisplay",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "PermissionDenied",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "Stop",
    "StopFailure",
    "TeammateIdle",
    "ConfigChange",
    "CwdChanged",
    "DirectoryAdded",
    "FileChanged",
    "WorktreeCreate",
    "WorktreeRemove",
    "PreCompact",
    "PostCompact",
    "PreModelSwitch",
    "PostModelSwitch",
    "SessionEnd",
    "Elicitation",
    "ElicitationResult",
)
EVENT_RANK = {event: rank for rank, event in enumerate(EVENTS)}
HANDLER_TYPES = ("command", "http", "mcp_tool", "prompt", "agent")
_AGENT_EVENT = {"Stop": "SubagentStop"}
_SCOPE_RANK = {scope: rank for rank, scope in enumerate(SETUP_SCOPES)}
_AGENT_RANK = 10  # agent front matter sorts after every settings and plugin scope
_SKILL_RANK = 20  # and skill front matter after that
_VISIBLE: tuple[SetupScope, ...] = (
    "managed",
    "project_local",
    "project",
    "user",
    "plugin",
)
_PROJECT_SCOPES = ("project_local", "project")

Origin = Literal["settings", "plugin", "agent", "skill"]
Path_ = tuple[str | int, ...]


@dataclass
class _Src:
    """One place a ``hooks`` object was found."""

    scope: SetupScope
    origin: Origin
    file: str
    full_path: str
    data: object
    order: int
    plugin: str | None = None
    plugin_id: str | None = None
    base: Path_ = ()
    lines: dict[Path_, int] = field(default_factory=dict[Path_, int])
    flat_line: int | None = None
    real_path: str | None = None

    @property
    def rank(self) -> int:
        extra = {"agent": _AGENT_RANK, "skill": _SKILL_RANK}.get(self.origin, 0)
        return _SCOPE_RANK[self.scope] + extra

    def line(self, *path: str | int) -> int | None:
        if self.flat_line is not None:
            return self.flat_line
        return self.lines.get((*self.base, *path))


@dataclass
class _Hook:
    """One handler that parsed."""

    src: _Src
    written: str  # the event key as the file spells it
    event: str
    matcher: str | None
    handler: dict[str, object]
    line: int | None
    seq: tuple[int, int, int]
    item_id: str = ""


# ---------------------------------------------------------------- handlers


def _scalars(raw: object) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    out: list[str] = []
    for item in cast("list[object]", raw):
        if isinstance(item, (str, int, float)) and not isinstance(item, bool):
            out.append(str(item))
        else:
            return None
    return out


def _text(handler: Mapping[str, object], key: str) -> str | None:
    value = handler.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _typed_error(kind: str, handler: Mapping[str, object]) -> str | None:
    """Return what a handler of a known type lacks, or None."""
    if kind == "command":
        if _text(handler, "command") is None:
            return "no_command"
        bad_args = "args" in handler and _scalars(handler["args"]) is None
        return "bad_args" if bad_args else None
    if kind == "http":
        return None if _text(handler, "url") else "no_url"
    if kind == "mcp_tool":
        return (
            None if _text(handler, "server") and _text(handler, "tool") else "no_tool"
        )
    return None if _text(handler, "prompt") else "no_prompt"


def handler_error(raw: object) -> str | None:
    """Return why a handler can't load, or None when its shape is fine."""
    if not isinstance(raw, dict):
        return "not_object"
    handler = cast("dict[str, object]", raw)
    kind = handler.get("type")
    if not isinstance(kind, str):
        return "no_type"
    if kind not in HANDLER_TYPES:
        return "unknown_type"
    return _typed_error(kind, handler)


def _command_text(handler: Mapping[str, object]) -> MaskedText:
    """Return a command handler's command line, masked. Exec form adds its args."""
    command = str(handler["command"])
    args = _scalars(handler.get("args")) if "args" in handler else None
    original = command if not args else " ".join([command, *args])
    shown = command_mask.mask_command(command)
    if args:
        shown = " ".join([shown, *(str(a) for a in masking.mask_args(args))])
    return MaskedText(text=shown, masked=shown != original)


def _facts(event: str, matcher: str | None, handler: Mapping[str, object]) -> HookFacts:
    kind = str(handler["type"])
    command: MaskedText | None = None
    if kind == "command":
        command = _command_text(handler)
    elif kind == "http":
        command = masking.masked_text(handler["url"], "url")
    elif kind == "mcp_tool":
        command = command_mask.masked_command(f"{handler['server']} {handler['tool']}")
    timeout = handler.get("timeout")
    return HookFacts(
        event=event,
        matcher=matcher,
        handler_type=kind,
        command=command,
        timeout=int(timeout)
        if isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
        else None,
    )


# ---------------------------------------------------------------- the run


@dataclass
class _Flag:
    """A switch that turns hooks off: its item and what it does."""

    key: str
    item: SetupItem
    on: bool
    scope: SetupScope | None


def _fix_for(scope: SetupScope, full_path: str) -> ProblemFix:
    if scope == "managed":
        return ProblemFix(kind="cant_fix_here", target=None, reason="managed")
    if scope == "plugin":
        return ProblemFix(kind="cant_fix_here", target=None, reason="plugin")
    return ProblemFix(kind="copy_path", target=full_path, reason=None)


class _Run:
    """One read of the hooks of a project."""

    def __init__(
        self, ctx: SetupContext, handoff: Mapping[str, object], scope: read_scope.Scope
    ) -> None:
        self.ctx = ctx
        self.handoff = handoff
        self.scope = scope
        self.sources: list[_Src] = []
        self.hooks: list[_Hook] = []
        self.problems: dict[str, ProblemRow] = {}
        self.unreadable: list[UnreadableFile] = []
        self.touched: list[Path] = []
        self.settings = _settings_handoff(ctx, handoff)

    # ------------------------------------------------------------ problems

    def _problem(
        self,
        src: _Src,
        code: str,
        thing: str,
        line: int | None,
        params: dict[str, str],
    ) -> None:
        row = setup_items.make_problem(
            code=code,
            group="wont_load",
            kind="problem",
            part=PART,
            thing=thing,
            item=None,
            file=src.file,
            full_path=src.full_path,
            line=line,
            params=params,
            confidence=setup_items.DOCUMENTED,
            fix=_fix_for(src.scope, src.full_path),
        )
        self.problems.setdefault(row.id, row)

    # ------------------------------------------------------------ sources

    def _add(self, src: _Src) -> None:
        src.order = len(self.sources)
        self.sources.append(src)

    def read_settings(self) -> None:
        """Collect the ``hooks`` of every readable settings file."""
        layers = self.settings["layers"]
        if not isinstance(layers, settings_layers.Layers):
            return
        for file in layers.readable():
            if "hooks" not in file.data:
                continue
            text = "\n".join(file.text_lines)
            self._add(
                _Src(
                    scope=file.scope,
                    origin="settings",
                    file=file.display,
                    full_path=file.full_path,
                    data=file.data["hooks"],
                    order=0,
                    base=("hooks",),
                    lines=json_lines.index(text, ("hooks",)),
                    real_path=file.real_path,
                )
            )

    def read_plugins(self) -> None:
        """Collect the hooks of every enabled plugin."""
        for found in plugin_inputs.rows(self.handoff, "hooks"):
            plugin_id, name, path, inline = (
                found.plugin_id,
                found.name,
                found.path,
                found.inline,
            )
            self.touched.append(Path(path))
            got = read_scope.read_text(
                self.scope, path, FILE_CAP_BYTES, parse=json.loads, plugin=True
            )
            if isinstance(got, UnreadableFile):
                if got.reason != "vanished":
                    self.unreadable.append(got.model_copy(update={"part": PART}))
                continue
            shown, full = self.scope.display(path), os.path.abspath(path)  # noqa: PTH100
            src = _Src(
                scope="plugin",
                origin="plugin",
                file=shown,
                full_path=full,
                data=None,
                order=0,
                plugin=name,
                plugin_id=plugin_id,
            )
            if inline is not None:
                self._inline(src, got, inline)
            else:
                self._file(src, got)

    def _inline(self, src: _Src, text: str, inline: object) -> None:
        """Take the ``hooks`` written in a manifest. The text is the manifest's."""
        wrapped = isinstance(inline, dict) and isinstance(
            cast("dict[str, object]", inline).get("hooks"), dict
        )
        src.data = cast("dict[str, object]", inline)["hooks"] if wrapped else inline
        src.base = ("hooks", "hooks") if wrapped else ("hooks",)
        src.lines = json_lines.index(text, ("hooks",))
        self._add(src)

    def _file(self, src: _Src, text: str) -> None:
        """Take the events of a plugin ``hooks.json`` (wrapped in ``hooks`` or not)."""
        try:
            parsed = cast("object", json.loads(text))
        except json.JSONDecodeError as exc:
            self._problem(src, "json_invalid", src.file, exc.lineno, {})
            return
        except (ValueError, RecursionError):
            self._problem(src, "json_invalid", src.file, 1, {})
            return
        if not isinstance(parsed, dict):
            self._problem(src, "not_object", src.file, 1, {})
            return
        table = cast("dict[str, object]", parsed)
        if "hooks" in table:
            src.data, src.base = table["hooks"], ("hooks",)
        elif any(key in EVENT_RANK for key in table):
            src.data, src.base = table, ()
        else:
            return  # a file with no hooks (a description alone, say)
        src.lines = json_lines.index(text, src.base[:1])
        self._add(src)

    def read_agents(self) -> None:
        """Collect the hooks written in agent front matter."""
        self._front_matter(HANDOFF_AGENT_FILES, "agent")

    def read_skills(self) -> None:
        """Collect the hooks written in skill front matter.

        A plugin skill keeps its hooks, unlike a plugin agent
        (https://code.claude.com/docs/en/hooks.md, "Limits on skill hooks").
        """
        self._front_matter(HANDOFF_SKILL_HOOKS, "skill")

    def _front_matter(self, key: str, origin: Origin) -> None:
        raw = self.handoff.get(key)
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return
        for found in cast("Sequence[object]", raw):
            if not isinstance(found, AgentFile):
                continue
            if origin == "agent" and found.layer == "plugin":
                continue  # Claude Code ignores hooks on a plugin agent
            for one in found.fields:
                if one.name != "hooks" or one.ignored or one.value is None:
                    continue
                try:
                    data = cast("object", json.loads(one.value.text))
                except ValueError:
                    data = one.value.text  # not hooks: reported as a bad shape
                self._add(
                    _Src(
                        scope=found.layer,
                        origin=origin,
                        file=found.display,
                        full_path=found.full_path,
                        data=data,
                        order=0,
                        plugin=found.plugin,
                        flat_line=one.line,
                        real_path=found.real_path,
                    )
                )

    # ------------------------------------------------------------ walking

    def walk(self) -> None:
        """Turn every source into hooks and problem rows."""
        for src in self.sources:
            data = src.data
            if not isinstance(data, dict):
                self._problem(
                    src, "hook_bad_handler", src.file, src.line(), {"why": "not_object"}
                )
                continue
            table = cast("dict[str, object]", data)
            for written, groups in table.items():
                self._event(src, written, groups)

    def _event(self, src: _Src, written: str, groups: object) -> None:
        event = _AGENT_EVENT.get(written, written) if src.origin == "agent" else written
        line = src.line(written)
        if event not in EVENT_RANK:
            self._problem(src, "hook_bad_event", written, line, {"event": written})
            return
        if not isinstance(groups, list):
            self._bad(src, event, line, "not_list")
            return
        for gi, group in enumerate(cast("list[object]", groups)):
            self._group(src, written, event, gi, group)

    def _bad(self, src: _Src, event: str, line: int | None, why: str) -> None:
        self._problem(
            src, "hook_bad_handler", event, line, {"event": event, "why": why}
        )

    def _group(
        self, src: _Src, written: str, event: str, gi: int, group: object
    ) -> None:
        gline = src.line(written, gi)
        if not isinstance(group, dict):
            self._bad(src, event, gline, "not_object")
            return
        body = cast("dict[str, object]", group)
        matcher = body.get("matcher")
        if matcher is not None and not isinstance(matcher, str):
            self._bad(src, event, gline, "bad_matcher")
            return
        handlers = body.get("hooks")
        if not isinstance(handlers, list):
            self._bad(
                src, event, src.line(written, gi, "hooks") or gline, "no_handlers"
            )
            return
        for hi, handler in enumerate(cast("list[object]", handlers)):
            hline = src.line(written, gi, "hooks", hi)
            why = handler_error(handler)
            if why is not None:
                self._bad(src, event, hline, why)
                continue
            self.hooks.append(
                _Hook(
                    src=src,
                    written=written,
                    event=event,
                    matcher=matcher or None,
                    handler=cast("dict[str, object]", handler),
                    line=hline,
                    seq=(src.rank * 1000 + src.order, gi, hi),
                )
            )

    # ------------------------------------------------------------ switches

    def flags(self) -> dict[str, _Flag]:
        """Build the item of each switch that is set somewhere."""
        table = self.settings.get("hooks_flags")
        found: dict[str, _Flag] = {}
        if not isinstance(table, Mapping):
            return found
        by_key = cast("Mapping[str, object]", table)
        for key in sorted(FLAGS):
            places = by_key.get(key)
            if isinstance(places, list) and places:
                found[key] = self._flag(key, cast("list[Mapping[str, object]]", places))
        return found

    def _flag(self, key: str, places: list[Mapping[str, object]]) -> _Flag:
        sources: list[SetupSource] = []
        won: int | None = None
        for place in places:
            scope = cast("SetupScope", place["scope"])
            value = place["value"]
            status: ModelCheckStatus
            if not isinstance(value, bool):
                status = "invalid"
            elif key == FLAG_MANAGED and scope != "managed":
                status = "ignored"  # managed settings only
            elif won is None:
                status, won = "in_effect", len(sources)
            else:
                status = "overridden"
            file, full, line = (
                place.get("file"),
                place.get("full_path"),
                place.get("line"),
            )
            sources.append(
                setup_items.source_of(
                    scope=scope,
                    key=key,
                    file=file if isinstance(file, str) else None,
                    full_path=full if isinstance(full, str) else None,
                    line=line if isinstance(line, int) else None,
                    value=settings_layers.display_value(value, key),
                    status=status,
                )
            )
        lead = sources[won if won is not None else 0]
        status = lead.status
        on = won is not None and bool(places[won]["value"])
        visible = _VISIBLE[:1] if key == FLAG_MANAGED else _VISIBLE[:4]
        item = setup_items.make_item(
            part=PART,
            key=key,
            name=key,
            item_id=f"{PART}:{key}",
            label_known=True,
            scope=lead.scope,
            status=status,
            sources=sources,
            winner=won,
            reach_=setup_items.reach(visible),
            confidence=setup_items.ASSUMED
            if key == FLAG_MANAGED and won is None
            else setup_items.DOCUMENTED,
            reason=ItemReason(
                code="in_effect" if won is not None else _flag_reason(key, status),
                params={"file": lead.file or ""},
                rule_id=None,
                ref_item=None,
            ),
            effective=Effective(
                value=lead.value if won is not None else None,
                origin="set" if won is not None else "default",
                by_item=None,
            ),
            read_only=setup_items.read_only_for(lead.scope),
            changeable=setup_items.may_change(self.unreadable, lead.scope),
        )
        return _Flag(key, item, on, lead.scope if won is not None else None)

    # ------------------------------------------------------------ items

    def blocker(self, hook: _Hook, flags: Mapping[str, _Flag]) -> _Flag | None:
        """Return the first switch that blocks this hook, or None."""
        return next((f for f in self._blocking(hook, flags)), None)

    def _blocking(self, hook: _Hook, flags: Mapping[str, _Flag]) -> list[_Flag]:
        scope = hook.src.scope
        out: list[_Flag] = []
        all_off = flags.get(FLAG_ALL)
        if (
            all_off is not None
            and all_off.on
            and (all_off.scope == "managed" or scope != "managed")
        ):
            out.append(all_off)
        only = flags.get(FLAG_MANAGED)
        if (
            only is not None
            and only.on
            and scope != "managed"
            and not self._exempt(hook)
        ):
            out.append(only)
        return out

    def _exempt(self, hook: _Hook) -> bool:
        """True for a hook of a plugin that managed ``enabledPlugins`` force-enables."""
        src = hook.src
        if src.plugin_id is None and (src.origin != "skill" or src.plugin is None):
            return False
        for entry in cast("list[object]", self.settings.get("enabledPlugins") or []):
            if not isinstance(entry, Mapping):
                continue
            row = cast("Mapping[str, object]", entry)
            value = row.get("value")
            if row.get("scope") != "managed" or not isinstance(value, Mapping):
                continue
            for pid, on in cast("Mapping[str, object]", value).items():
                # A plugin skill is handed on with its name only, so match on that.
                same = pid == src.plugin_id or (
                    src.plugin_id is None and pid.split("@")[0] == src.plugin
                )
                if same and on is True:
                    return True
        return False

    def build(self, flags: Mapping[str, _Flag]) -> list[SetupItem]:
        """Number the hooks and build one item each."""
        ordered = sorted(self.hooks, key=lambda h: (EVENT_RANK[h.event], h.seq))
        counts: dict[tuple[str, str], int] = {}
        items: list[SetupItem] = []
        for hook in ordered:
            shown = hook.matcher or "*"
            at = counts.get((hook.event, shown), 0)
            counts[(hook.event, shown)] = at + 1
            hook.item_id = f"{PART}:{hook.event}:{shown}:{at}"
            items.append(self._item(hook, shown, self.blocker(hook, flags)))
        return items

    def _item(self, hook: _Hook, shown: str, blocked: _Flag | None) -> SetupItem:
        src = hook.src
        status: ModelCheckStatus = "ignored" if blocked is not None else "in_effect"
        source = setup_items.source_of(
            scope=src.scope,
            key=f"hooks.{hook.written}",
            file=src.file,
            full_path=src.full_path,
            line=hook.line,
            value=None,
            status=status,
        ).model_copy(update={"plugin": src.plugin})
        hidden = list(_PROJECT_SCOPES) if self.ctx.project_dir is None else []
        reason = (
            ItemReason(
                code="hooks_disabled",
                params={"flag": blocked.key},
                rule_id=None,
                ref_item=blocked.item.id,
            )
            if blocked is not None
            else ItemReason(
                code="in_effect", params={"file": src.file}, rule_id=None, ref_item=None
            )
        )
        return setup_items.make_item(
            part=PART,
            key=hook.event,
            name=f"{hook.event}:{shown}",
            item_id=hook.item_id,
            label_known=True,
            scope=src.scope,
            status=status,
            sources=[source],
            winner=0,
            reach_=setup_items.reach([s for s in _VISIBLE if s not in hidden], hidden),
            confidence=setup_items.DOCUMENTED,
            reason=reason,
            group=hook.event,
            facts=ItemFacts(hook=_facts(hook.event, hook.matcher, hook.handler)),
            read_only=_read_only(src),
            real_path=src.real_path,
            changeable=setup_items.may_change(self.unreadable, src.scope),
        )

    def switch_problems(self, flags: Mapping[str, _Flag]) -> list[ProblemRow]:
        """Return the rows of the switches: ``hooks_disabled`` and their bad values."""
        rows: list[ProblemRow] = []
        for flag in flags.values():
            for source in flag.item.sources:
                if source.status in ("invalid", "ignored"):
                    row = setup_items.status_problem(flag.item, source, source.status)
                    if row is not None:
                        rows.append(row)
            hit = sum(
                1
                for h in self.hooks
                if any(f is flag for f in self._blocking(h, flags))
            )
            if hit:
                rows.append(self._disabled_row(flag, hit))
        return rows

    @staticmethod
    def _disabled_row(flag: _Flag, count: int) -> ProblemRow:
        winner = flag.item.sources[flag.item.winner or 0]
        fix = (
            ProblemFix(kind="cant_fix_here", target=None, reason="managed")
            if winner.scope == "managed"
            else ProblemFix(kind="open_item", target=flag.item.id, reason=None)
        )
        return setup_items.make_problem(
            code="hooks_disabled",
            group="not_as_set",
            kind="problem",
            part=PART,
            thing=flag.key,
            item=flag.item,
            file=winner.file,
            full_path=winner.full_path,
            line=winner.line,
            params={"flag": flag.key, "count": str(count)},
            confidence=setup_items.DOCUMENTED,
            fix=fix,
        )

    def run(self) -> Collected:
        """Read every place and build the items."""
        self.read_settings()
        self.read_plugins()
        self.read_agents()
        self.read_skills()
        self.walk()
        flags = self.flags()
        items = [f.item for f in flags.values()] + self.build(flags)
        problems = [*self.problems.values(), *self.switch_problems(flags)]
        return Collected(
            items={PART: setup_items.number(items)},
            problems=setup_items.sort_problems(problems),
            unreadable=self.unreadable,
            touched=self.touched,
        )


def _flag_reason(key: str, status: ModelCheckStatus) -> str:
    if status == "ignored" and key == FLAG_MANAGED:
        return "managed_only"
    return status


def _read_only(src: _Src) -> ReadOnly | None:
    if src.scope == "plugin":
        return ReadOnly(
            code="plugin", params={"plugin": src.plugin or ""}, command=None
        )
    return setup_items.read_only_for(src.scope)


def _settings_handoff(
    ctx: SetupContext, handoff: Mapping[str, object]
) -> Mapping[str, object]:
    """Return the settings handoff, reading the settings if it is missing."""
    got = handoff.get(HANDOFF_SETTINGS)
    if isinstance(got, Mapping):
        table = cast("Mapping[str, object]", got)
        if (
            isinstance(table.get("layers"), settings_layers.Layers)
            and "hooks_flags" in table
        ):
            return table
    made = collect_settings.COLLECTOR.read(ctx, {}).handoff.get(HANDOFF_SETTINGS)
    return cast("Mapping[str, object]", made) if isinstance(made, Mapping) else {}


class HooksCollector:
    """The collector of part ``hooks``."""

    name = "hooks"
    parts: Sequence[SetupPart] = (PART,)

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the hooks of the project. Never raises."""
        return _Run(ctx, handoff, read_scope.Scope(ctx)).run()

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Return a stat-only fingerprint of the plugin hook files the read touched.

        Settings files and agent files are fingerprinted by their own collectors.
        """
        scope = read_scope.Scope(ctx)
        return read_scope.stat_signature(
            scope, last.touched if last is not None else []
        )


COLLECTOR = HooksCollector()

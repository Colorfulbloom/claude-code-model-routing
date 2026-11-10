"""The agents collector (m4-build.md task 6, part ``agents``).

Agents by name across managed, project, user and plugin. Files are found and read
through ``read_scope`` (``agent_files``), and every front matter field is parsed with
``ruamel.yaml`` in safe mode, so nested ``hooks`` and hyphenated keys parse.

Items. A file agent is ``agents:<name>``. A plugin agent is always its own item,
``agents:<plugin>:<name>``, even when a file agent has the same name (owner,
November 9). Items come sorted by id, so a refetch, or an agent moving from user to
project, never reorders them. The id holds no scope.

Where the answers come from.

- Does the file load, and which file wins. A name in several places goes to the highest
  place, managed then project then user (``agent-file-location-order``, documented).
  The strict resolver sees project and user files only, so its status is used for the
  one case this module cannot decide itself: a file the strict reader rejects but YAML
  parses. That item keeps the resolver's status and gets a Can't tell row,
  ``frontmatter_reader_gap``.
- Model and effort. Project and user agents take the resolver's entries, through
  ``model_check.resolve_entries`` as ``agent_setup`` does, so Live, Review and setup
  agree. The resolver has no managed or plugin layer (fact R-7c9c), so a managed or
  plugin agent shows what its front matter sets with status ``unknown``.
- Two files with one name in one folder. Claude Code picks one "by filesystem read
  order rather than a documented precedence". This module takes the first in sorted
  order, marks the item ``assumed``, and reports the other as ``same_name_in_folder``.

The item's ``status`` is the outcome of what runs, not the load status. A file that
loads is judged as the Model check judges it over no runs, so the item and the check
agree: lowered when a cap lowers it, overridden when a higher layer replaces its
file's value, invalid, ignored or unknown as the resolver says, in effect when it runs
as its file sets it. ``check`` carries the Model check's code and params. The load
status stays in ``reason`` (``agent_loads``, ``agent_overrides`` and the rest), and a
file that does not load keeps its load status.

``effective.value`` is the model and the effort that run, joined with `` / ``. The
per-key detail is in ``sources`` (keys ``model``, ``effort``, the settings key that sets
or caps them, an environment variable). ``usage`` and ``group`` stay None here: the
store's runs and the "No runs yet" group belong to the answer builder (task 9).

The strict resolver reads agent and settings files itself. Those reads are inside the
allowed roots, so the read rule holds, but they do not go through ``read_scope``.
"""

import functools
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import agent_files
import git_root
import masking
import model_catalog
import model_check
import read_scope
import resolve
from agent_files import AgentFile
from collect_plugins import HANDOFF_COMPONENTS, PluginComponents
from models import (
    AgentFacts,
    ConfidenceLevel,
    Effective,
    EffectiveOrigin,
    ItemCheck,
    ItemFacts,
    ItemReason,
    MaskedText,
    ModelCheckStatus,
    ProblemFix,
    ProblemGroup,
    ProblemRow,
    ReadOnly,
    ScopeReach,
    SetupItem,
    SetupPart,
    SetupScope,
    SetupSource,
)
from problem_rows import confidence, make_row
from setup_contract import Collected, SetupContext
from usage import Row

PART: SetupPart = "agents"
HANDOFF_AGENT_FILES = "agent_files"
_RANK: dict[str, int] = {"managed": 0, "project": 1, "user": 2, "plugin": 3}
_LAYER_SCOPE: dict[str, SetupScope] = {
    "project": "project",
    "local": "project_local",
    "user": "user",
    "managed": "managed",
    "flag": "command_line",
    "cli": "command_line",
}
_WON = ("in_effect", "lowered", "default")
_LEVELS: tuple[ConfidenceLevel, ...] = ("assumed", "documented", "tested")
_SETUP_ERRORS: tuple[type[Exception], ...] = (OSError, ValueError)
_SHELL_LABEL = resolve.LIVE_SHELL_LABEL
_CAP_ITEM = "settings:maxEffortLevel"
_SETTING_KEYS = ("model", "effort")
_LOCATION_RULE = "agent-file-location-order"
_CATALOG = model_catalog.load_catalog()
_SAME_NAME_RULE = "agent-file-same-name-one-tree"


@functools.cache
def _rule_table() -> dict[str, tuple[ConfidenceLevel, str | None]]:
    """Return {rule id: (confidence, Claude Code version a test ran on)}."""
    table: dict[str, tuple[ConfidenceLevel, str | None]] = {}
    rules: list[dict[str, Any]] = resolve.load_rules().get("rules", [])
    for rule in rules:
        level = rule.get("confidence")
        verified: dict[str, Any] = rule.get("verified_on") or {}
        if level in _LEVELS:
            table[str(rule["rule_id"])] = (level, verified.get("claude_version"))
    return table


def _weakest(rule_ids: Sequence[str]) -> tuple[ConfidenceLevel, str | None]:
    """Return the least certain level of some rules, and its version when tested."""
    table = _rule_table()
    found = [table[r] for r in rule_ids if r in table]
    if not found:
        return "assumed", None
    level, version = min(found, key=lambda pair: _LEVELS.index(pair[0]))
    return level, version if level == "tested" else None


@dataclass
class _Def:
    """One agent file that names an agent, and how it ended up."""

    file: AgentFile
    status: ModelCheckStatus = "unknown"
    code: str | None = None
    live: bool = False
    entry: Row | None = None
    other: str | None = None


@dataclass
class _Effect:
    sources: list[SetupSource] = field(default_factory=list[SetupSource])
    effective: Effective | None = None
    rule_ids: list[str] = field(default_factory=list[str])


class _Run:
    """One read of the agents part."""

    def __init__(
        self, ctx: SetupContext, handoff: Mapping[str, object], scope: read_scope.Scope
    ) -> None:
        self.ctx = ctx
        self.scope = scope
        self.handoff = handoff
        self.out = Collected()
        self.entries: list[Row] = []
        self.files: list[AgentFile] = []
        self.layer_of: dict[str, SetupScope] = {}

    # ------------------------------------------------------------ reading

    def roots(self) -> list[tuple[SetupScope, str]]:
        ctx = self.ctx
        found: list[tuple[SetupScope, str]] = []
        if ctx.managed_dir is not None:
            found.append(("managed", str(ctx.managed_dir / ".claude" / "agents")))
        if ctx.project_dir is not None:
            found.append(("project", str(ctx.project_dir / ".claude" / "agents")))
        found.append(("user", str(ctx.config_dir / "agents")))
        return found

    def read_files(self) -> None:
        for layer, root in self.roots():
            found = agent_files.find(self.scope, [root], layer)
            self.files.extend(found.files)
            self.out.unreadable.extend(found.unreadable)
            self.out.touched.extend(found.touched)
            self.out.touched.append(Path(root))
        for comp in self.plugins():
            found = agent_files.find(
                self.scope, comp.agents, "plugin", plugin=comp.name
            )
            self.files.extend(found.files)
            self.out.unreadable.extend(found.unreadable)
            self.out.touched.extend(found.touched)
            self.out.touched.extend(Path(r) for r in comp.agents)

    def plugins(self) -> list[PluginComponents]:
        raw = self.handoff.get(HANDOFF_COMPONENTS)
        if not isinstance(raw, list):
            return []
        return [c for c in cast("list[object]", raw) if isinstance(c, PluginComponents)]

    def read_entries(self) -> None:
        """Run the resolver as ``agent_setup`` does. A failed run leaves no entries."""
        ctx = self.ctx
        local = (
            git_root.local_settings_path(ctx.project_dir, ctx.home)
            if ctx.project_dir is not None
            else None
        )
        try:
            self.entries = model_check.resolve_entries(
                claude_dir=ctx.config_dir,
                project_dir=ctx.project_dir,
                managed_dir=ctx.managed_dir,
                shell_env=ctx.shell_env,
                local_path=local,
                plan=ctx.plan,
                scope=self.scope,
            )
        except _SETUP_ERRORS:
            self.entries = []

    def entry_of(self, f: AgentFile) -> Row | None:
        """Return the resolver's ``agentFile`` entry for a project or user file."""
        for entry in self.entries:
            if (
                entry.get("key") == "agentFile"
                and entry.get("scope") == "agent"
                and entry.get("file") == f.display
                and entry.get("layer") == f.layer
            ):
                return entry
        return None

    # ------------------------------------------------------------ problems

    def fix_for(self, layer: SetupScope, item_id: str | None, full: str) -> ProblemFix:
        if layer == "managed":
            return ProblemFix(kind="cant_fix_here", target=None, reason="managed")
        if item_id is not None:
            return ProblemFix(kind="open_item", target=item_id, reason=None)
        return ProblemFix(kind="copy_path", target=full, reason=None)

    def problem(  # noqa: PLR0913 - one keyword per row field
        self,
        code: str,
        f: AgentFile,
        *,
        group: ProblemGroup,
        item_id: str | None,
        thing: str,
        line: int | None,
        level: ConfidenceLevel,
        params: Mapping[str, str] | None = None,
        tested_on: str | None = None,
        fix: ProblemFix | None = None,
    ) -> None:
        row: ProblemRow = make_row(
            code=code,
            group=group,
            thing=thing,
            part=PART,
            item_id=item_id,
            file=f.display,
            full_path=f.full_path,
            line=line,
            level=level,
            tested_on=tested_on,
            params=params,
            fix=fix or self.fix_for(f.layer, item_id, f.full_path),
        )
        self.out.problems.append(row)

    def lowered_problems(self, f: AgentFile, item: SetupItem, rname: str) -> None:
        """Add a Not as set row for each setting of an agent that a cap lowers.

        One row per lowered setting, whatever the item's worst status is, so a lowered
        effort shows even when the model is ignored. A setting that a higher scope
        overrides makes none, because that is by design. A row says what the file
        sets, what runs and which setting lowers it. Its fix opens that cap, where the
        settings row of a lowered key opens the key.
        """
        for p in model_check.lowered_settings(self.entries, rname, _CATALOG):
            setting = p.get("setting", "effort")
            cap = p.get("cap_key", "")
            line = next((x.line for x in f.fields if x.name == setting), None)
            self.problem(
                "agent_lowered",
                f,
                group="not_as_set",
                item_id=item.id,
                thing=item.name,
                line=line if line is not None else f.name_line,
                level=item.confidence.level,
                tested_on=item.confidence.tested_on,
                params={
                    "setting": setting,
                    "value": p.get("value", ""),
                    "runs": p.get("expected", ""),
                    "cap": cap,
                },
                fix=ProblemFix(kind="open_item", target=f"settings:{cap}", reason=None)
                if cap
                else None,
            )

    # ------------------------------------------------------------ files to defs

    def classify(self) -> dict[tuple[str | None, str], list[_Def]]:
        """Sort the files into defs by (plugin, name), and report files with no name."""
        groups: dict[tuple[str | None, str], list[_Def]] = {}
        for f in self.files:
            base = os.path.basename(f.path)  # noqa: PTH119
            if f.code is not None:
                self.problem(
                    f.code,
                    f,
                    group="wont_load",
                    item_id=None,
                    thing=base,
                    line=f.line,
                    level="documented",
                )
                continue
            assert f.name is not None  # noqa: S101 - code is None only with a name
            groups.setdefault((f.plugin, f.name), []).append(_Def(file=f))
        return groups

    def decide(self, key: tuple[str | None, str], defs: list[_Def]) -> None:
        """Set each def's status, from the highest place down."""
        plugin, name = key
        item_id = agent_files.agent_item_id(name, plugin)
        for d in defs:
            d.entry = (
                self.entry_of(d.file) if d.file.layer in ("project", "user") else None
            )
            self.judge_one(d, item_id, name)
        loaded: dict[str, _Def] = {}
        for d in defs:
            if d.live and d.file.layer in loaded:
                d.live, d.status, d.code = False, "invalid", "same_name_in_folder"
                d.other = loaded[d.file.layer].file.display
                self.problem(
                    "same_name_in_folder",
                    d.file,
                    group="wont_load",
                    item_id=item_id,
                    thing=name,
                    line=d.file.name_line,
                    level="assumed",
                    params={"other_file": d.other},
                )
            elif d.live:
                loaded[d.file.layer] = d
        live = sorted((d for d in defs if d.live), key=lambda d: _RANK[d.file.layer])
        for index, d in enumerate(live):
            d.status = "in_effect" if index == 0 else "overridden"

    def judge_one(self, d: _Def, item_id: str, name: str) -> None:
        f = d.file
        # The reader gap comes first. A file the strict reader rejects has fields that
        # may parse as something else (a description written as a flow mapping), so
        # "no description" is not a safe verdict. The resolver says what it can.
        if f.gap and f.layer in ("project", "user"):
            status = d.entry.get("status") if d.entry is not None else None
            d.status = cast("ModelCheckStatus", status) if status else "unknown"
            d.code = "frontmatter_reader_gap"
            line = d.entry.get("line") if d.entry is not None else None
            self.problem(
                "frontmatter_reader_gap",
                f,
                group="cant_tell",
                item_id=item_id,
                thing=name,
                line=line if isinstance(line, int) else f.strict_line,
                level="assumed",
            )
        elif not f.has_description:
            d.status, d.code = "invalid", "agent_no_description"
            line = d.entry.get("line") if d.entry is not None else None
            self.problem(
                "agent_no_description",
                f,
                group="wont_load",
                item_id=item_id,
                thing=name,
                line=line if isinstance(line, int) else 1,
                level="documented",
            )
        else:
            d.live = True
            d.code = None

    # ------------------------------------------------------------ paths

    def full_path_of(self, display: str | None) -> str | None:
        """Turn a display path the resolver gave back into the absolute path."""
        if display is None or display == _SHELL_LABEL:
            return None
        ctx = self.ctx
        found: list[Path] = []
        prefix = f"~/{ctx.config_dir.name}/"
        if display.startswith(prefix):
            found.append(ctx.config_dir / display[len(prefix) :])
        if ctx.managed_dir is not None and display.startswith(
            ctx.managed_dir.name + "/"
        ):
            found.append(ctx.managed_dir / display[len(ctx.managed_dir.name) + 1 :])
        if ctx.project_dir is not None:
            found.append(Path(os.path.normpath(ctx.project_dir / display)))
        for candidate in found:
            if self.scope.display(candidate) == display:
                return str(candidate)
        return None

    # ------------------------------------------------------------ model and effort

    def source_of(self, row: Row, key: str) -> SetupSource:
        layer = str(row.get("layer"))
        display = row.get("file") if isinstance(row.get("file"), str) else None
        full = self.full_path_of(display)
        name = key
        if layer == "agent":
            scope: SetupScope = self.layer_of.get(str(display), "user")
        elif layer == "env":
            shell = display is None or display == _SHELL_LABEL
            scope = "shell" if shell else (self.scope.scope_of(full or "") or "user")
            name = str(row.get("via")) if shell else f"env.{row.get('via')}"
        else:
            scope = _LAYER_SCOPE.get(layer, "user")
            name = str(
                row.get("path") or resolve.SETTINGS_KEYS.get(("agent", key), key)
            )
        value = row.get("value")
        line = row.get("line")
        return SetupSource(
            scope=scope,
            key=name,
            file=None if display == _SHELL_LABEL else display,
            full_path=full,
            line=line if isinstance(line, int) else None,
            value=None if value is None else masking.masked_text(value),
            status=cast("ModelCheckStatus", row.get("status", "unknown")),
            plugin=None,
        )

    def cap_source(self, row: Row) -> SetupSource | None:
        """Return the ``maxEffortLevel`` source that lowers a lowered effort row."""
        caps = [
            entry
            for entry in self.entries
            if entry.get("key") == "maxEffortLevel"
            and entry.get("scope") == "main"
            and entry.get("status") == "in_effect"
        ]
        # A cap for this model first, then the one with no model.
        for wanted in (row.get("model"), None):
            for entry in caps:
                if entry.get("model") == wanted:
                    source = self.source_of(
                        {**entry, "value": row.get("becomes")}, "maxEffortLevel"
                    )
                    return source.model_copy(update={"key": "maxEffortLevel"})
        return None

    def settings_effect(self, rname: str) -> _Effect:
        """Sources and the value that runs, from the resolver's model and effort."""
        eff = _Effect()
        values: list[str] = []
        origins: list[EffectiveOrigin] = []
        by_item: str | None = None
        for key in _SETTING_KEYS:
            rows = [
                e
                for e in self.entries
                if e.get("scope") == "agent"
                and e.get("agent") == rname
                and e.get("key") == key
            ]
            for row in rows:
                if row.get("layer") != "default":
                    eff.sources.append(self.source_of(row, key))
            winner = next(
                (r for r in rows if r.get("status") in (*_WON, "unknown")), None
            )
            if winner is None:
                origins.append("unknown")
                continue
            eff.rule_ids.append(str(winner.get("rule_id")))
            if winner.get("status") == "unknown":
                origins.append("unknown")
                continue
            lowered = winner.get("status") == "lowered"
            raw = winner.get("becomes") if lowered else winner.get("value")
            if raw is not None:
                values.append(masking.masked_text(raw).text)
            if lowered:
                origins.append("cap")
                by_item = _CAP_ITEM
                cap = self.cap_source(winner)
                if cap is not None:
                    eff.sources.append(cap)
            else:
                origins.append("default" if winner.get("layer") == "default" else "set")
        eff.effective = self.make_effective(values, origins, by_item)
        return eff

    def make_effective(
        self,
        values: Sequence[str],
        origins: Sequence[EffectiveOrigin],
        by_item: str | None,
    ) -> Effective:
        text = " / ".join(values)
        if "cap" in origins:
            origin: EffectiveOrigin = "cap"
        elif "unknown" in origins or not origins:
            origin = "unknown"
        elif all(o == "default" for o in origins):
            origin = "default"
        else:
            origin = "set"
        return Effective(
            value=masking.masked_text(text) if text else None,
            origin=origin,
            by_item=by_item,
        )

    def front_matter_effect(self, f: AgentFile) -> _Effect:
        """Model and effort of a managed or plugin agent: front matter, unknown."""
        eff = _Effect()
        for key in _SETTING_KEYS:
            fm = next(
                (x for x in f.fields if x.name == key and x.value is not None), None
            )
            if fm is None:
                continue
            eff.sources.append(
                SetupSource(
                    scope=f.layer,
                    key=key,
                    file=f.display,
                    full_path=f.full_path,
                    line=fm.line,
                    value=fm.value,
                    status="unknown",
                    plugin=f.plugin,
                )
            )
        eff.effective = Effective(value=None, origin="unknown", by_item=None)
        return eff

    # ------------------------------------------------------------ items

    def name_source(self, d: _Def) -> SetupSource:
        f = d.file
        return SetupSource(
            scope=f.layer,
            key="name",
            file=f.display,
            full_path=f.full_path,
            line=f.name_line,
            value=MaskedText(text=f.name or "", masked=False),
            status=d.status,
            plugin=f.plugin,
        )

    def reach(self) -> list[ScopeReach]:
        return [
            ScopeReach(scope="managed", visible=self.ctx.managed_dir is not None),
            ScopeReach(scope="command_line", visible=False),
            ScopeReach(scope="project", visible=self.ctx.project_dir is not None),
            ScopeReach(scope="user", visible=True),
            ScopeReach(scope="plugin", visible=True),
        ]

    def read_only(self, layer: SetupScope, plugin: str | None) -> ReadOnly | None:
        if layer == "managed":
            return ReadOnly(code="managed", params={}, command=None)
        if layer == "plugin":
            return ReadOnly(
                code="plugin", params={"plugin": plugin or ""}, command=None
            )
        return None

    def build_item(self, key: tuple[str | None, str], defs: list[_Def]) -> SetupItem:
        plugin, name = key
        ordered = sorted(defs, key=lambda d: (_RANK[d.file.layer], d.file.rel))
        top = next((d for d in ordered if d.live and d.status == "in_effect"), None)
        lead = top or ordered[0]
        f = lead.file
        rname = None
        entry = lead.entry
        if entry is not None and top is not None and f.layer in ("project", "user"):
            rname = str(entry.get("agent"))
        eff = (
            self.settings_effect(rname)
            if rname is not None
            else self.front_matter_effect(f)
        )
        rule_ids = (
            [str(entry.get("rule_id"))] if entry is not None else [_LOCATION_RULE]
        )
        if lead.code == "same_name_in_folder" or self.shares_name(ordered, lead):
            rule_ids.append(_SAME_NAME_RULE)
        level, tested_on = _weakest([*rule_ids, *eff.rule_ids])
        if self.shares_name(ordered, lead) or lead.code == "frontmatter_reader_gap":
            level, tested_on = "assumed", None
        sources = [self.name_source(d) for d in ordered] + eff.sources
        status, check = self.outcome(lead, rname)
        other = next((d.file.display for d in ordered if d is not lead), None)
        params = {"file": f.display} | ({"other_file": other} if other else {})
        item_id = agent_files.agent_item_id(name, plugin)
        item = SetupItem(
            id=item_id,
            part=PART,
            key=name,
            name=name,
            label_known=True,
            order=0,
            group=None,
            scope=f.layer,
            effective=eff.effective,
            sources=sources,
            winner=ordered.index(top) if top is not None else None,
            reach=self.reach(),
            status=status,
            reason=ItemReason(
                code=self.reason_code(lead, ordered),
                params=params,
                rule_id=rule_ids[-1],
                ref_item=None,
            ),
            confidence=confidence(level, tested_on),
            loads=None,
            applies=None,
            writable=False,
            read_only_reason=self.read_only(f.layer, f.plugin),
            risk_tier=None,
            feature="core",
            facts=ItemFacts(agent=AgentFacts(plugin=f.plugin, fields=f.fields)),
            usage=None,
            real_path=f.real_path,
            not_read=None,
            may_change=bool(self.out.unreadable),
            check=check,
        )
        if rname is not None and check is not None:
            self.lowered_problems(f, item, rname)
        return item

    def outcome(
        self, lead: _Def, rname: str | None
    ) -> tuple[ModelCheckStatus, ItemCheck | None]:
        """Return the item's status and check: the outcome of what runs.

        A file that loads is judged as the Model check judges it over no runs
        (``model_check.judge_agent``), so the item and the check agree. Lowered
        when a cap lowers its model or effort, overridden when a higher layer
        replaces one, invalid, ignored or unknown as the resolver says, in effect
        when it runs as its file sets it. A file that sets neither keeps its load
        status. A file that does not load, and an agent the resolver does not judge
        (managed and plugin), keep the load status too.
        """
        if rname is None:
            return lead.status, None
        verdict = model_check.judge_agent(self.entries, rname, [], _CATALOG)
        if verdict.status is None:
            return lead.status, None
        return verdict.status, ItemCheck(
            code=verdict.reason_code, params=verdict.params
        )

    def shares_name(self, ordered: list[_Def], lead: _Def) -> bool:
        """True when another file of the lead's folder has the lead's name."""
        return any(
            d is not lead
            and d.file.layer == lead.file.layer
            and d.code == "same_name_in_folder"
            for d in ordered
        )

    def reason_code(self, lead: _Def, ordered: list[_Def]) -> str:
        if lead.code is not None:
            return lead.code
        if self.shares_name(ordered, lead):
            return "same_name_in_folder"
        return "agent_overrides" if len(ordered) > 1 else "agent_loads"

    def ignored_rows(self, key: tuple[str | None, str], defs: list[_Def]) -> None:
        plugin, name = key
        item_id = agent_files.agent_item_id(name, plugin)
        for d in defs:
            if not d.live or plugin is None:
                continue
            for fld in d.file.fields:
                if fld.ignored:
                    self.problem(
                        "plugin_field_ignored",
                        d.file,
                        group="not_as_set",
                        item_id=item_id,
                        thing=name,
                        line=fld.line,
                        level="documented",
                        params={"field": fld.name, "plugin": plugin},
                    )

    # ------------------------------------------------------------ the whole read

    def run(self) -> Collected:
        self.read_files()
        self.read_entries()
        for f in self.files:
            self.layer_of[f.display] = f.layer
        groups = self.classify()
        items: list[SetupItem] = []
        for key in sorted(groups, key=lambda k: agent_files.agent_item_id(k[1], k[0])):
            defs = groups[key]
            self.decide(key, defs)
            self.ignored_rows(key, defs)
            items.append(self.build_item(key, defs))
        items.sort(key=lambda i: i.id)
        for index, item in enumerate(items):
            item.order = index
        self.out.items[PART] = items
        self.out.unreadable = [
            u.model_copy(update={"part": PART}) for u in self.out.unreadable
        ]
        self.out.handoff[HANDOFF_AGENT_FILES] = [
            f for f in self.files if f.name is not None
        ]
        return self.out


class AgentsCollector:
    """The ``agents`` collector. ``COLLECTOR`` is the one instance."""

    name = "agents"
    parts: Sequence[SetupPart] = (PART,)

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the agents of one project. Never raises for a bad file."""
        return _Run(ctx, handoff, read_scope.Scope(ctx)).run()

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Fingerprint the files and folders the last read touched, with stat only."""
        scope = read_scope.Scope(ctx)
        if last is not None:
            return read_scope.stat_signature(scope, last.touched)
        run = _Run(ctx, {}, scope)
        return read_scope.stat_signature(scope, [root for _l, root in run.roots()])


COLLECTOR = AgentsCollector()

__all__ = [
    "COLLECTOR",
    "HANDOFF_AGENT_FILES",
    "AgentsCollector",
]

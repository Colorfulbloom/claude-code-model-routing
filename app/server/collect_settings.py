"""The Settings collector, which also feeds Permissions and Output style.

Part ``settings`` has one item per settings key set anywhere, plus ``model`` and
``effortLevel`` always (the setup map's Settings summary links to them), and one
``env.NAME`` item per environment variable a settings ``env`` block or the shell sets.
Keys other parts own (``permissions``, ``hooks``, ``enabledPlugins``, ``outputStyle``,
the hook switches and the MCP approval keys) are not items here. ``enabledPlugins``,
the approval keys and the hook switches go on to the later collectors in
``Collected.handoff["settings"]``.

What runs comes from the ported resolver (``resolve``), run over what ``read_scope``
read (``settings_layers``). A key with a resolver row (model, effort, the cache and
window keys, every ``env.NAME``) takes its statuses, ``effective`` and rule from the
resolver.
A key set only for an agent (``subagentPromptCacheTtl``) has no main row, so a probe
agent with no frontmatter stands in (``settings_layers.PROBE_AGENT``). Any other key
is top wins: the highest scope is in effect and the rest are overridden, except that a
list key combines across files and ``modelSettings`` is resolved one model at a time
(settings docs, "Lists merge instead of overriding"; see ``combine``). A To fix row
exists for every source that is invalid, ignored, lowered or unknown, the winner or not.
The resolver's own ``reason`` prose is never used, because it holds absolute paths.
``reason.code`` is the status word and ``reason.rule_id`` names the rule.

Shell values carry confidence ``assumed`` (owner answer 9, m4-build.md section 15):
the shell is what Bar Tab saw when it started.

``ManagedPricing`` feeds the managed layer's ``modelPricing`` to the price feed. Claude
Code reads that key from managed settings only (settings-reference), so the user,
project and local copies show as ignored.
"""

# ruff: noqa: PTH100 - display and full paths are strings, as ``collect`` builds them.

import functools
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import collect_output_style
import collect_permissions
import read_scope
import resolve
import settings_layers
import setup_items
from models import (
    Effective,
    EffectiveOrigin,
    ItemReason,
    MaskedText,
    ModelCheckStatus,
    ProblemRow,
    ScopeReach,
    SetupItem,
    SetupPart,
    SetupScope,
    SetupSource,
)
from settings_layers import LAYER_SCOPE, LayerFile, Layers
from setup_contract import Collected, SetupContext
from usage import Row

# Keys other parts own. They are not Settings items.
OTHER_PARTS = frozenset(
    {
        "permissions",
        "hooks",
        "enabledPlugins",
        "outputStyle",
        "enabledMcpjsonServers",
        "disabledMcpjsonServers",
        "enableAllProjectMcpServers",
        "disableAllHooks",
        "allowManagedHooksOnly",
    }
)
APPROVAL_KEYS = (
    "enabledMcpjsonServers",
    "disabledMcpjsonServers",
    "enableAllProjectMcpServers",
)
# Settings that switch hooks off or restrict them. The Hooks part shows them.
HOOK_FLAG_KEYS = ("disableAllHooks", "allowManagedHooksOnly")
ALWAYS = ("model", "effortLevel")
# Claude Code reads these only from managed settings (settings-reference).
MANAGED_ONLY = frozenset({"modelPricing"})
# Keys the page has a label for. Any other key shows as its raw name. An ``env.NAME``
# item is labelled when NAME is a variable in rules.json.
LABELLED = frozenset(
    {
        "model",
        "effortLevel",
        "maxEffortLevel",
        "autoCompactWindow",
        "promptCacheTtl",
        "alwaysThinkingEnabled",
        "fallbackModel",
        "availableModels",
        "modelSettings",
        "modelPricing",
    }
)
CAP_RULES = ("effort-lowered-by-cap", "effort-lowered-by-cap-model-unknown")
_NOT_ROWS = ("settingsFile", "agentFile", "rulesFile")
# Settings keys the resolver rows only for an agent (``subagentPromptCacheTtl``). The
# probe agent's rows stand in for the main row these keys do not have.
AGENT_ONLY = frozenset(
    name for (scope, _key), name in resolve.SETTINGS_KEYS.items() if scope == "agent"
) - frozenset(
    name for (scope, _key), name in resolve.SETTINGS_KEYS.items() if scope == "main"
)
_SHELL_LABELS = (resolve.LIVE_SHELL_LABEL, resolve.LABEL_SHELL)
_ENV = "env."
_SCOPES_FILES: tuple[SetupScope, ...] = ("managed", "project_local", "project", "user")


def _variable_keys() -> tuple[frozenset[str], frozenset[str]]:
    """Return (settings keys an environment variable can set, the variable names)."""
    keys: set[str] = set()
    names: set[str] = set()
    for variable in settings_layers.rules().get("variables", []):
        names.add(variable["name"])
        keys.update(r["key"] for r in variable["rows"] if r["scope"] == "main")
    return frozenset(keys), frozenset(names)


@functools.cache
def _file_rules() -> frozenset[str]:
    """Return the rule ids that say a settings file could not be read or parsed."""
    return frozenset(
        rule["rule_id"]
        for rule in settings_layers.rules()["rules"]
        if rule["key"] == "settingsFile"
    )


def _flag_keys() -> dict[str, str]:
    """Return {row key: flag} for the keys with a command line flag."""
    return {
        row: flag
        for flag, rows in resolve.FLAGS.items()
        for row, scope in rows
        if scope == "main"
    }


class _Builder:
    """Builds the Settings items and their problems from one read."""

    def __init__(self, layers: Layers, entries: list[Row]) -> None:
        self.layers = layers
        self.scope = layers.scope
        self.by_path = {f.path: f for f in layers.files}
        self.var_keys, self.var_names = _variable_keys()
        self.flag_of = _flag_keys()
        self.rows: dict[str, list[Row]] = {}
        for entry in entries:
            main = (
                entry.get("scope") == "main"
                and entry.get("agent") is None
                and entry["key"] not in _NOT_ROWS
            )
            probe = (
                entry.get("scope") == "agent"
                and entry.get("agent") == settings_layers.PROBE_AGENT
                and entry["key"] in AGENT_ONLY
            )
            if main or probe:
                self.rows.setdefault(entry["key"], []).append(entry)
        self.problems: list[ProblemRow] = []

    # ------------------------------------------------------------ which items

    def item_keys(self) -> list[str]:
        """Return the item keys: every key set anywhere, ``model``, ``effortLevel``."""
        found: dict[str, None] = dict.fromkeys(ALWAYS)
        for file in self.layers.readable():
            for key, value in file.data.items():
                if key != "env" and key not in OTHER_PARTS and value is not None:
                    found.setdefault(key)
            block = file.data.get("env")
            if isinstance(block, dict):
                for name, value in block.items():  # pyright: ignore[reportUnknownVariableType]
                    if isinstance(value, (str, int, float)) and not isinstance(
                        value, bool
                    ):
                        found.setdefault(_ENV + str(name))  # pyright: ignore[reportUnknownArgumentType]
        for key, entries in self.rows.items():
            if any(e["layer"] != "default" for e in entries):
                found.setdefault(key)
        return sorted(found)

    # ------------------------------------------------------------ one source

    def _file_parts(self, path: str | None) -> tuple[str | None, str | None]:
        if path is None or path in _SHELL_LABELS or path.startswith("session.json"):
            return None, None
        return self.scope.display(path), os.path.abspath(path)

    def _raw(self, key: str, entry: Row) -> object:
        """Return the unmasked value an entry reads, or None when it can't be found."""
        layer = entry["layer"]
        via = entry.get("via")
        if layer == "env" and via is not None:
            keys: tuple[str, ...] = ("env", via)
        elif key.startswith(_ENV):
            keys = ("env", key[len(_ENV) :])
        elif entry.get("path") is None and layer in LAYER_SCOPE:
            keys = (key,)
        else:
            return None
        return settings_layers.raw_value(self.layers, entry.get("file"), keys)

    def _source(self, key: str, entry: Row) -> SetupSource:
        layer = entry["layer"]
        file = entry.get("file")
        name: str = key
        scope: SetupScope
        if layer == "env":
            name = _ENV + str(entry.get("via") or key.removeprefix(_ENV))
            scope = "shell" if file in _SHELL_LABELS else self._scope_of(file)
        elif layer == "flag":
            name = str(entry.get("flag") or self.flag_of.get(key, "--flag"))
            scope = "command_line"
        elif layer == "cli":
            name = "--settings"
            scope = "command_line"
        else:
            scope = LAYER_SCOPE.get(layer) or self._scope_of(file)
            name = str(entry.get("path") or key)
        shown, full = self._file_parts(file)
        raw = self._raw(key, entry)
        value_name = name.removeprefix(_ENV) if name.startswith(_ENV) else name
        value = settings_layers.display_value(
            raw if raw is not None else entry["value"], value_name
        )
        return setup_items.source_of(
            scope=scope,
            key=name,
            file=shown,
            full_path=full,
            line=entry.get("line"),
            value=value,
            status=entry["status"],
        )

    def _scope_of(self, file: object) -> SetupScope:
        found = self.scope.scope_of(file) if isinstance(file, str) else None
        return found if found is not None else "user"

    # ------------------------------------------------------------ items

    def item(self, key: str) -> SetupItem:
        """Build one item."""
        entries = self.rows.get(key)
        return self._row_item(key, entries) if entries else self._plain_item(key)

    def _reach(
        self, key: str, *, files: Sequence[SetupScope] = _SCOPES_FILES
    ) -> list[ScopeReach]:
        hidden: list[SetupScope] = []
        if key.startswith(_ENV) or key in self.var_keys:
            hidden.append("shell")
        if key in self.flag_of:
            hidden.append("command_line")
        return setup_items.reach(files, hidden)

    def _label_known(self, key: str) -> bool:
        if key.startswith(_ENV):
            return key[len(_ENV) :] in self.var_names
        return key in LABELLED

    def _cap_item(self, winner: Row) -> str | None:
        """Return the item that caps a lowered effort level, when it exists."""
        if winner.get("rule_id") not in CAP_RULES:
            return None
        capped = any(
            e["layer"] != "default" for e in self.rows.get("maxEffortLevel", [])
        )
        if capped:
            return "settings:maxEffortLevel"
        present = any(
            f.data.get("modelSettings") is not None for f in self.layers.readable()
        )
        return "settings:modelSettings" if present else None

    def _row_item(self, key: str, entries: list[Row]) -> SetupItem:
        pairs = [(e, self._source(key, e)) for e in entries if e["layer"] != "default"]
        winner = next((e for e in entries if e["status"] in resolve.WINNING), None)
        pairs = self._demote(pairs, winner)
        sources = [src for _entry, src in pairs]
        excluded = [e for e in entries if e["status"] in resolve.EXCLUDING]
        on_set = winner is not None and winner["layer"] != "default"
        status: ModelCheckStatus
        driving: Row | None
        if on_set and winner is not None:
            status, driving = winner["status"], winner
        elif excluded:
            first_invalid = next(
                (e for e in excluded if e["status"] == "invalid"), None
            )
            driving = first_invalid or excluded[0]
            status = "invalid" if first_invalid is not None else "ignored"
        else:
            driving = winner
            status = winner["status"] if winner is not None else "unknown"
        win_at = next(
            (at for at, (e, _s) in enumerate(pairs) if e is winner and on_set), None
        )
        win_src = sources[win_at] if win_at is not None else None
        scope = win_src.scope if win_src is not None else None
        cap = (
            self._cap_item(winner)
            if winner is not None and winner["status"] == "lowered"
            else None
        )
        shell_win = scope == "shell"
        confidence = (
            setup_items.ASSUMED
            if shell_win
            else setup_items.rule_confidence(
                driving.get("rule_id") if driving else None
            )
        )
        item = setup_items.make_item(
            part="settings",
            key=key,
            name=key,
            label_known=self._label_known(key),
            scope=scope,
            status=status,
            sources=sources,
            winner=win_at,
            reach_=self._reach(key),
            confidence=confidence,
            reason=self._reason(status, driving, cap),
            effective=self._effective(winner, win_src, cap, key),
            read_only=setup_items.read_only_for(scope),
            real_path=self._real(win_src),
            changeable=setup_items.may_change(self.layers.unreadable, scope),
        )
        self._problems(item, pairs, winner)
        return item

    @staticmethod
    def _demote(
        pairs: list[tuple[Row, SetupSource]], winner: Row | None
    ) -> list[tuple[Row, SetupSource]]:
        """Show an ignored value that a higher scope beats as overridden.

        The resolver marks a value ignored when Claude Code skips it (a user
        ``effortLevel`` on Opus 5.5). When a set value in a higher file scope wins
        anyway, nothing needs fixing, so it reads as overridden and is no problem
        (Overridden is never a problem). Where nothing higher wins it stays ignored.
        """
        win = next((s for e, s in pairs if e is winner), None)
        if win is None or win.scope not in _SCOPES_FILES:
            return pairs
        out: list[tuple[Row, SetupSource]] = []
        for entry, src in pairs:
            beaten = (
                entry["status"] == "ignored"
                and src.scope in _SCOPES_FILES
                and _SCOPES_FILES.index(src.scope) > _SCOPES_FILES.index(win.scope)
            )
            out.append(
                (
                    entry,
                    src.model_copy(update={"status": "overridden"}) if beaten else src,
                )
            )
        return out

    def _effective(
        self, winner: Row | None, src: SetupSource | None, cap: str | None, key: str
    ) -> Effective:
        if winner is None:
            return Effective(value=None, origin="unknown", by_item=None)
        value = self._shown(winner, key)
        if winner["layer"] == "default":
            return Effective(value=value, origin="default", by_item=None)
        origin: EffectiveOrigin = "set"
        if winner["status"] == "lowered":
            return Effective(
                value=self._shown(winner, key, becomes=True), origin="cap", by_item=cap
            )
        if winner["status"] == "unknown":
            origin = "unknown"
        if src is not None and src.value is not None:
            value = src.value
        if winner.get("merged") is not None:
            # A list key merges across files, so what runs is the merged list and the
            # winner's own list is only its part.
            value = settings_layers.display_value(winner["merged"], key)
        return Effective(value=value, origin=origin, by_item=None)

    @staticmethod
    def _shown(entry: Row, key: str, *, becomes: bool = False) -> MaskedText | None:
        value = entry.get("becomes") if becomes else entry["value"]
        if value is None:
            return None
        return settings_layers.display_value(value, key)

    def _reason(
        self, status: ModelCheckStatus, driving: Row | None, cap: str | None
    ) -> ItemReason:
        params: dict[str, str] = {}
        if driving is not None:
            for name in ("model", "via", "layer"):
                if driving.get(name) is not None:
                    params[name] = str(driving[name])
            other = driving.get("other_file")
            if other:
                params["other_file"] = self.scope.display(other)
        return ItemReason(
            code=status,
            params=params,
            rule_id=driving.get("rule_id") if driving is not None else None,
            ref_item=cap,
        )

    def _real(self, src: SetupSource | None) -> str | None:
        if src is None or src.full_path is None:
            return None
        file = self.by_path.get(src.full_path)
        return file.real_path if file is not None else None

    def _problems(
        self, item: SetupItem, pairs: list[tuple[Row, SetupSource]], winner: Row | None
    ) -> None:
        for entry, src in pairs:
            status: ModelCheckStatus = src.status
            # Every source gets its row, the winner or not: a wrong-type list that
            # another file's list beats is still a thing to fix. Overridden never does.
            # An unknown that a file which did not load causes has that file's own row.
            counts = status in ("invalid", "ignored") or (
                status in ("lowered", "unknown")
                and entry.get("rule_id") not in _file_rules()
            )
            if status == "ignored" and _empty_variable(entry, src):
                # An empty variable is the same as an unset one (rule
                # effort-env-empty-ignored, tested), so there is nothing to fix. The
                # source still shows on the item as ignored. Any other source of the
                # key keeps its own row, because that is a different cause.
                counts = False
            row = setup_items.status_problem(item, src, status) if counts else None
            if row is not None:
                self.problems.append(row)

    # ------------------------------------------------------------ plain keys

    def _plain_item(self, key: str) -> SetupItem:
        managed_only = key in MANAGED_ONLY
        sources: list[SetupSource] = []
        values: list[object] = []
        for merged in self.layers.collected["settings"]:
            value = merged["data"].get(key)
            where = merged["where"].get((key,))
            if value is None or where is None:
                continue
            path = where["path"]
            raw = settings_layers.raw_value(self.layers, path, (key,))
            shown, full = self._file_parts(path)
            values.append(raw if raw is not None else value)
            sources.append(
                setup_items.source_of(
                    scope=LAYER_SCOPE[merged["layer"]],
                    key=key,
                    file=shown,
                    full_path=full,
                    line=where["line"],
                    value=settings_layers.display_value(
                        raw if raw is not None else value, key
                    ),
                    status="in_effect",
                )
            )
        for at, src in enumerate(sources):
            counts = src.scope == "managed" or not managed_only
            if not counts:
                sources[at] = src.model_copy(update={"status": "ignored"})
        live = [at for at, s in enumerate(sources) if s.status == "in_effect"]
        combined, gives = combine([values[at] for at in live]) if live else (None, [])
        for at, gave in zip(live, gives, strict=True):
            if not gave:
                sources[at] = sources[at].model_copy(update={"status": "overridden"})
        win_at = live[0] if live else None
        win = sources[win_at] if win_at is not None else None
        status: ModelCheckStatus = (
            "in_effect" if win is not None else ("ignored" if sources else "unknown")
        )
        scope = win.scope if win is not None else None
        item = setup_items.make_item(
            part="settings",
            key=key,
            name=key,
            label_known=self._label_known(key),
            scope=scope,
            status=status,
            sources=sources,
            winner=win_at,
            reach_=self._reach(
                key, files=("managed",) if managed_only else _SCOPES_FILES
            ),
            confidence=setup_items.DOCUMENTED,
            reason=ItemReason(code=status, params={}, rule_id=None, ref_item=None),
            effective=Effective(
                value=_what_runs(key, win, combined),
                origin="set" if win is not None else "default",
                by_item=None,
            ),
            read_only=setup_items.read_only_for(scope),
            real_path=self._real(win),
            changeable=setup_items.may_change(self.layers.unreadable, scope),
        )
        for src in sources:
            if src.status == "ignored":
                row = setup_items.status_problem(item, src, "ignored")
                if row is not None:
                    self.problems.append(row)
        return item


def _empty_variable(entry: Row, src: SetupSource) -> bool:
    """True when the source is an environment variable set to an empty string."""
    return (
        entry["layer"] == "env"
        and src.value is not None
        and src.value.text == ""
        and not src.value.masked
    )


def combine(values: list[object]) -> tuple[object, list[bool]]:
    """Return what a key runs with across the files that set it, and who gave a part.

    The settings docs ("Lists merge instead of overriding") combine a list key over
    its files, and resolve ``modelSettings`` one model at a time with the highest file
    deciding each model. Any other key, or a mix of types, is top wins: the first value
    runs and no other file gives a part.

    Args:
        values: The raw value of each file that sets the key, highest scope first.

    Returns:
        The value that runs, and for each file whether it gives a part of it.
    """
    if len(values) > 1 and all(isinstance(v, list) for v in values):
        merged: list[object] = []
        for value in values:
            merged.extend(v for v in cast("list[object]", value) if v not in merged)
        return merged, [True] * len(values)
    if len(values) > 1 and all(isinstance(v, dict) for v in values):
        return _by_model(values)
    return values[0], [at == 0 for at in range(len(values))]


def _by_model(values: list[object]) -> tuple[object, list[bool]]:
    """Return ``modelSettings`` merged by model name, the highest file's entry each.

    Unverified: the settings reference resolves ``effortLevel``, ``maxEffortLevel`` and
    ``autoCompactWindow`` per model, but whether the fields inside one model's entry
    merge across files is not checked against the docs. This takes the whole entry
    from the highest file.
    """
    out: dict[str, object] = {}
    gives: list[bool] = []
    for value in values:
        gave = False
        for model, entry in cast("dict[str, object]", value).items():
            if model not in out:
                out[model] = entry
                gave = True
        gives.append(gave)
    return out, gives


def _what_runs(
    key: str, win: SetupSource | None, combined: object
) -> MaskedText | None:
    """Return the effective value of a plain key: the combined value when it merges."""
    if win is None:
        return None
    return settings_layers.display_value(combined, key)


def _file_problems(layers: Layers) -> list[ProblemRow]:
    """Return a Won't load row for each settings file that did not parse."""
    rows: list[ProblemRow] = []
    for file in layers.files:
        if file.state == "json_invalid":
            code = "managed_invalid" if file.layer == "managed" else "json_invalid"
            line = file.error_line
        elif file.state == "not_object":
            code = "managed_invalid" if file.layer == "managed" else "not_object"
            line = 1 if file.layer == "managed" else None
        else:
            continue
        rows.append(
            setup_items.file_problem(
                code=code,
                part="settings",
                file=file.display,
                full_path=file.full_path,
                line=line,
                managed=file.layer == "managed",
            )
        )
    return rows


def _handoff(layers: Layers) -> dict[str, object]:
    """Return what the plugin and MCP collectors need from the settings files."""
    enabled: list[dict[str, object]] = []
    approvals: dict[str, list[dict[str, object]]] = {key: [] for key in APPROVAL_KEYS}
    hook_flags: dict[str, list[dict[str, object]]] = {key: [] for key in HOOK_FLAG_KEYS}
    for file in layers.readable():
        for key in HOOK_FLAG_KEYS:
            if file.data.get(key) is not None:
                hook_flags[key].append(_place(file, (key,), file.data[key]))
        plugins = file.data.get("enabledPlugins")
        if isinstance(plugins, dict):
            enabled.append(
                _place(
                    file,
                    ("enabledPlugins",),
                    {
                        str(k): v  # pyright: ignore[reportUnknownArgumentType]
                        for k, v in plugins.items()  # pyright: ignore[reportUnknownVariableType]
                        if isinstance(v, bool)
                    },
                )
            )
        for key in APPROVAL_KEYS:
            if file.data.get(key) is not None:
                approvals[key].append(_place(file, (key,), file.data[key]))
    return {
        "enabledPlugins": enabled,
        "approvals": approvals,
        "hooks_flags": hook_flags,
        "layers": layers,
    }


def _place(file: LayerFile, key: tuple[str, ...], value: object) -> dict[str, object]:
    return {
        "scope": file.scope,
        "file": file.display,
        "full_path": file.full_path,
        "line": file.lines.get(key),
        "value": value,
    }


class SettingsCollector:
    """The collector of parts ``settings``, ``permissions`` and ``output_style``."""

    name = "settings"
    parts: Sequence[SetupPart] = ("settings", "permissions", "output_style")

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the project's settings files and style files. Never raises."""
        layers = settings_layers.read_layers(ctx)
        entries = settings_layers.resolver_entries(
            layers.collected, ctx.plan, probe_agent=True
        )
        builder = _Builder(layers, entries)
        settings = [builder.item(key) for key in builder.item_keys()]
        perms = collect_permissions.build(layers)
        styles = collect_output_style.build(layers, handoff)
        problems = [
            *_file_problems(layers),
            *builder.problems,
            *perms.problems,
            *styles.problems,
        ]
        return Collected(
            items={
                "settings": setup_items.number(settings),
                "permissions": setup_items.number(perms.items),
                "output_style": setup_items.number(styles.items),
            },
            problems=setup_items.sort_problems(problems),
            unreadable=[*layers.unreadable, *styles.unreadable],
            touched=[*layers.touched, *styles.touched],
            handoff={"settings": _handoff(layers)},
        )

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Return a stat-only fingerprint of the files the read touched."""
        scope = read_scope.Scope(ctx)
        paths = last.touched if last is not None else _candidates(ctx)
        return read_scope.stat_signature(scope, paths)


def _candidates(ctx: SetupContext) -> list[Path]:
    """Return the settings paths and style folders a first signature fingerprints."""
    config = Path(ctx.config_dir)
    found = [config / "settings.json", *collect_output_style.folders(ctx)]
    if ctx.managed_dir is not None:
        found += [
            ctx.managed_dir / "managed-settings.json",
            ctx.managed_dir / "managed-settings.d",
        ]
    if ctx.project_dir is not None:
        claude = ctx.project_dir / ".claude"
        found += [claude / "settings.json", claude / "settings.local.json"]
    return found


COLLECTOR = SettingsCollector()


# ---------------------------------------------------------------- modelPricing


class ManagedPricing:
    """Gives the price feed the managed settings, read through ``read_scope``.

    Call it for the managed settings document (a dict) or None. Only the managed
    files are read. The answer is cached until a stat signature of the files and
    the folder changes, so the price feed can call it for every price table.
    """

    def __init__(self, config_dir: Path, managed_dir: Path | None) -> None:
        """Remember the folders. Nothing is read yet."""
        self._ctx = SetupContext(
            project_key="",
            config_dir=config_dir,
            home=None,
            project_dir=None,
            managed_dir=managed_dir,
        )
        self._scope = read_scope.Scope(self._ctx)
        self._touched: list[Path] = (
            [managed_dir / "managed-settings.json", managed_dir / "managed-settings.d"]
            if managed_dir is not None
            else []
        )
        self._signature: str | None = None
        self._cached: dict[str, Any] | None = None

    def __call__(self) -> dict[str, Any] | None:
        """Return the merged managed settings, or None when there are none."""
        if self._ctx.managed_dir is None:
            return None
        now = read_scope.stat_signature(self._scope, self._touched)
        if self._signature == now:
            return self._cached
        data, touched = settings_layers.managed_settings(self._ctx, self._scope)
        self._touched = touched
        self._cached = data
        self._signature = read_scope.stat_signature(self._scope, touched)
        return data

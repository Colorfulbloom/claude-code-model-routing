"""The preview of a settings edit: what it writes, runs at and beats (m6-build 4.2).

A preview reads the project's settings files once through ``settings_layers`` and runs
the resolver over them as they are (``now``). Then it runs the resolver again over a
copy of what it read with the candidate value put in the picked file (``after``). The
same what-if gives the outcome of each of the three scopes and, for an effort or
effort cap field, what each option would run at in the picked scope. A user-scope
preview runs one more pair for every other project, so the page can list the projects
a user-scope save reaches. The resolver is the one the Settings part uses. Nothing here
writes a file. ``edit_store`` plans the bytes and signs the token.

Where a value goes. The writer edits the key path the resolver reports for the file. A
``modelSettings`` entry for the main model that the file holds wins. Otherwise the
file's top-level key, else its ``env`` twin, else a new top-level key
(``choose_path``). The save calls ``save_key_path``, which runs the same choice, so the
bytes of the preview and the bytes of the save agree.

Outcome of a candidate. Its status is the resolver's status for the entry the new value
makes in that layer: ``in_effect``, ``overridden``, ``ignored``, ``lowered``,
``invalid`` or ``unknown``. ``beaten_by`` names the scope that wins when it is another
one of the three. An ``env`` twin has two steps. The ``env.NAME`` row says whether the
file's variable wins over the other layers' copies. If it does, the field's own row says
what the variable does there.

A preview never raises for a file it can't edit. The picked scope's ``refusal`` carries
the code, and the page holds Save. The only exception is an unknown project, which the
caller checks.
"""

# ruff: noqa: PLR0913, PLR0917 - one request's parts are many, and each reads
# better by name than bundled.

import dataclasses
import json
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

import edit_diff
import edit_fields
import edit_store
import git_tracked
import json_edit
import masking
import resolve
import settings_layers
from edit_history import as_scope
from edit_store import EditContext, EditStore, Inspected, Refused, Target
from models import (
    EditApplies,
    EditDiff,
    EditEffect,
    EditPreview,
    EditPreviewRequest,
    EditReach,
    EditReadOnlyCode,
    EditRefusal,
    EditRuns,
    EditScope,
    EditScopeRow,
    EditSetChange,
    EditSummary,
    EditTarget,
    EditWarning,
    ModelCheckStatus,
    OptionRunsAt,
    RunsAt,
    ScopeOutcome,
    SettingsEditField,
)
from settings_layers import Layers
from setup_contract import SetupContext
from usage import Row

SCOPES: tuple[EditScope, ...] = ("user", "project", "local")
MAX_REACHES = 20
APPLIES: EditApplies = "new_session"
_LAYER_RANK = {"managed": 0, "cli": 1, "local": 2, "project": 3, "user": 4}
_NOT_WRITABLE: frozenset[str] = frozenset(
    {
        "link_outside",
        "link_dangling",
        "not_regular",
        "hard_link",
        "not_owner",
        "too_large",
        "forbidden_path",
        "folder_not_found",
        "not_editable",
        "write_failed",
        "unparsed",
        "parent_not_object",
        "changed",
    }
)
Scalar = str | int


@dataclass(frozen=True)
class EditInputs:
    """What one project hands the edit routes.

    Attributes:
        setup: The project's setup context. ``project_dir`` is None for a project that
            is not listed, so only the user file can be edited.
        claude_version: The installed Claude Code version, or None when unknown. It
            picks the local file (``edit_store.settings_targets``).
        store_root: The Bar Tab store folder, where the seen marks live. None keeps
            them in memory.
    """

    setup: SetupContext
    claude_version: str | None
    store_root: Path | None = None


@runtime_checkable
class EditHost(Protocol):
    """A provider that knows each project's folders. ``StoreProvider`` is one."""

    def edit_inputs(self, project: str) -> EditInputs:
        """Return the project's inputs.

        Raises:
            provider.UnknownProjectError: When ``project`` is not a project key.
        """
        ...


def base_context(inputs: EditInputs) -> EditContext:
    """Return the writer context for a server, from any project's inputs.

    A run that is not real mode (a fixture or demo run) may not write inside the Bar
    Tab checkout, so ``guard_checkout`` is on for it.
    """
    setup = inputs.setup
    home = setup.home if setup.home is not None else _env_home(setup.config_dir)
    return EditContext(
        config_dir=Path(setup.config_dir),
        home=home,
        managed_dir=setup.managed_dir,
        claude_version=None,
        guard_checkout=not setup.real_mode,
    )


def _env_home(config_dir: Path) -> Path:
    value = os.environ.get("HOME")
    return Path(value) if value else Path(config_dir).parent


def request_context(store: EditStore, inputs: EditInputs) -> EditContext:
    """Return the store's context with this project's Claude Code version."""
    return dataclasses.replace(store.context, claude_version=inputs.claude_version)


def targets_of(
    store: EditStore, inputs: EditInputs, *, leftover: bool = True
) -> list[Target]:
    """Return the project's settings targets in scope order.

    Args:
        store: The writer.
        inputs: The project's inputs.
        leftover: Keep the leftover local file, which only undo reaches.
    """
    found = edit_store.settings_targets(
        request_context(store, inputs), inputs.setup.project_dir
    )
    return found if leftover else [t for t in found if not t.leftover]


# ---------------------------------------------------------------- reading and what-if


@dataclass
class Resolution:
    """One read of a project's layers and the resolver's entries over them."""

    layers: Layers
    entries: list[Row]


def read_resolution(setup: SetupContext) -> Resolution:
    """Read the project's settings layers and resolve them."""
    layers = settings_layers.read_layers(setup)
    return Resolution(
        layers, settings_layers.resolver_entries(layers.collected, setup.plan)
    )


def _row(entries: Iterable[Row], key: str) -> list[Row]:
    return [e for e in entries if e.get("key") == key and e.get("scope") == "main"]


def _winner(rows: Sequence[Row]) -> Row | None:
    return next((e for e in rows if e.get("status") in resolve.WINNING), None)


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def runs_at(entries: Sequence[Row], key: str) -> RunsAt:
    """Return what a row runs at: the winner's value, or what it lowers to."""
    winner = _winner(_row(entries, key))
    if winner is None:
        return RunsAt(value=None, status="unknown")
    shown = winner.get("becomes")
    if shown is None:
        shown = winner.get("value")
    return RunsAt(value=_text(shown), status=cast("ModelCheckStatus", winner["status"]))


def outcome_of(
    entries: Sequence[Row],
    field: SettingsEditField,
    layer: str,
    key_path: Sequence[str],
) -> ScopeOutcome:
    """Return what the value at ``key_path`` of ``layer`` does, from the entries."""
    rows = _row(entries, field)
    path = tuple(key_path)
    candidate: Row | None
    if path[0] == "env":
        name = path[1]
        env_rows = _row(entries, "env." + name)
        mine = next((e for e in env_rows if e.get("layer") == layer), None)
        if mine is None:
            return ScopeOutcome(status="unknown", beaten_by=None)
        if mine["status"] != "in_effect":
            return _outcome(entries, mine, _winner(env_rows), layer)
        candidate = next((e for e in rows if e.get("via") == name), None)
    elif path[0] == "modelSettings":
        want = ".".join(path)
        candidate = next(
            (e for e in rows if e.get("layer") == layer and e.get("path") == want),
            None,
        )
    else:
        candidate = next(
            (
                e
                for e in rows
                if e.get("layer") == layer and "path" not in e and "via" not in e
            ),
            None,
        )
    if candidate is None:
        return ScopeOutcome(status="unknown", beaten_by=None)
    return _outcome(entries, candidate, _winner(rows), layer)


def _outcome(
    entries: Sequence[Row], candidate: Row, winner: Row | None, layer: str
) -> ScopeOutcome:
    status = cast("ModelCheckStatus", candidate["status"])
    beaten: EditScope | None = None
    if status == "overridden" and winner is not None:
        won = _winning_layer(entries, winner)
        if won != layer:
            beaten = as_scope(won)
    return ScopeOutcome(status=status, beaten_by=beaten)


def _winning_layer(entries: Sequence[Row], winner: Row) -> object:
    """Return the layer a winning row comes from.

    A row that an env variable decides has the layer ``env``. The scope that wins is
    then the one holding the variable, which the variable's own row names.
    """
    via = winner.get("via")
    if isinstance(via, str):
        env_winner = _winner(_row(entries, "env." + via))
        if env_winner is not None:
            return env_winner.get("layer")
    return winner.get("layer")


def _put(data: dict[str, Any], key_path: Sequence[str], value: object) -> None:
    node = data
    for step in key_path[:-1]:
        child = node.get(step)
        if not isinstance(child, dict):
            child = {}
            node[step] = child
        node = cast("dict[str, Any]", child)
    node[key_path[-1]] = value


def _put_source(
    collected: dict[str, Any], layer: str, key_path: Sequence[str], value: object
) -> None:
    sources: list[Row] = collected["settings"]
    source: Row | None = next((s for s in sources if s["layer"] == layer), None)
    if source is None:
        source = {"layer": layer, "data": {}, "where": {}}
        rank = _LAYER_RANK[layer]
        at = next(
            (
                i
                for i, item in enumerate(sources)
                if _LAYER_RANK.get(item["layer"], 9) > rank
            ),
            len(sources),
        )
        sources.insert(at, source)
    _put(source["data"], key_path, value)


def _put_env(collected: dict[str, Any], layer: str, name: str, value: object) -> None:
    env: dict[str, list[Row]] = collected.setdefault("env", {})
    records = env.setdefault(name, [])
    record = {
        "value": str(value),
        "origin": "settings",
        "layer": layer,
        "path": None,
        "line": None,
    }
    for i, item in enumerate(records):
        if item["origin"] == "settings" and item["layer"] == layer:
            records[i] = record
            return
    rank = _LAYER_RANK[layer]
    at = next(
        (
            i
            for i, item in enumerate(records)
            if item["origin"] != "settings" or _LAYER_RANK.get(item["layer"], 9) > rank
        ),
        len(records),
    )
    records.insert(at, record)


def _branch(
    collected: dict[str, Any], layer: str, key_path: Sequence[str]
) -> dict[str, Any]:
    """Copy the layers for one what-if, sharing everything the edit does not touch.

    A whole-file deep copy cost more than the resolve on a file of several hundred KB,
    and a preview runs it once per option. The edit puts one value at ``key_path`` in
    one layer's data (and one record under ``env`` for an env twin), so only that
    spine of dicts, the layer's source, the ``settings`` list and that env record list
    are new. The resolver reads what it is given and never writes to it, which
    ``test_edit_api_preview.py`` checks.
    """
    out = dict(collected)
    sources: list[Row] = [
        {**item, "data": _spine(item["data"], key_path[:-1])}
        if item["layer"] == layer
        else item
        for item in collected["settings"]
    ]
    out["settings"] = sources
    if key_path[0] == "env":
        env: dict[str, list[Row]] = dict(collected.get("env", {}))
        env[key_path[1]] = list(env.get(key_path[1], []))
        out["env"] = env
    return out


def _spine(data: dict[str, Any], steps: Sequence[str]) -> dict[str, Any]:
    """Copy ``data`` and the dicts along ``steps``, so a write there spares ``data``."""
    root = dict(data)
    node = root
    for step in steps:
        child = node.get(step)
        if not isinstance(child, dict):
            break
        copied = dict(cast("dict[str, Any]", child))
        node[step] = copied
        node = copied
    return root


def what_if(
    res: Resolution,
    setup: SetupContext,
    layer: str,
    key_path: Sequence[str],
    value: Scalar,
) -> list[Row]:
    """Resolve again over a copy of the layers with ``value`` in ``layer``.

    Args:
        res: The read of the project, which is not changed.
        setup: The project's context, for the plan.
        layer: ``user``, ``project`` or ``local``.
        key_path: The key the writer would edit.
        value: The value as the file would hold it (text under ``env``).
    """
    collected = _branch(res.layers.collected, layer, key_path)
    _put_source(collected, layer, key_path, value)
    if key_path[0] == "env":
        _put_env(collected, layer, key_path[1], value)
    return settings_layers.resolver_entries(collected, setup.plan)


# ---------------------------------------------------------------- the key path


def _parsed(raw: bytes | None) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        return json_edit.parse_strict(raw)[1]
    except json_edit.Refused:
        return {}


def _dig(data: dict[str, Any], key_path: Sequence[str]) -> tuple[bool, object]:
    """Follow ``key_path`` through parsed JSON. Returns (found, the value there)."""
    node: object = data
    for step in key_path:
        if not isinstance(node, dict):
            return False, None
        table = cast("dict[str, object]", node)
        if step not in table:
            return False, None
        node = table[step]
    return True, node


def _has(data: dict[str, Any], key_path: Sequence[str]) -> bool:
    return _dig(data, key_path)[0]


def choose_path(
    field: SettingsEditField, raw: bytes | None, entries: Sequence[Row], layer: str
) -> tuple[str, ...]:
    """Pick the key a save to ``layer`` edits.

    A ``modelSettings`` entry for the main model that the resolver reports in this
    layer and the file holds. Otherwise ``edit_store.choose_key_path`` (the top-level
    key, an ``env`` twin, or a new top-level key).
    """
    data = _parsed(raw)
    prefix = "modelSettings."
    for entry in _row(entries, field):
        path = entry.get("path")
        if entry.get("layer") != layer or not isinstance(path, str):
            continue
        if not path.startswith(prefix):
            continue
        for inner in edit_fields.FIELDS[field].model_settings_fields:
            if path.endswith("." + inner):
                name = path[len(prefix) : -len(inner) - 1]
                found = ("modelSettings", name, inner)
                if name and _has(data, found):
                    return found
    return edit_store.choose_key_path(data, field)


def save_target(
    store: EditStore, inputs: EditInputs, body: EditPreviewRequest
) -> tuple[Target, tuple[str, ...]]:
    """Return the target a save of ``body`` writes and the key path it edits.

    The key path is the one the preview chose, so the bytes of the preview and the bytes
    of the save agree.

    Raises:
        Refused: Any refusal of ``settings_target`` and ``EditStore.inspect``.
    """
    target = edit_store.settings_target(
        request_context(store, inputs), inputs.setup.project_dir, body.scope
    )
    seen = store.inspect(target)
    res = read_resolution(inputs.setup)
    return target, choose_path(body.field, seen.raw, res.entries, body.scope)


# ---------------------------------------------------------------- small helpers


def _stored(path: Sequence[str], value: Scalar) -> Scalar:
    return str(value) if path[0] == "env" else value


def _scalar(value: object) -> Scalar | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    return value if isinstance(value, (str, int)) else str(value)


def _masked_scalar(value: object, name: str | None) -> Scalar | None:
    shown = masking.mask_value(value, name)
    return _scalar(shown)


def _value_at(raw: bytes | None, key_path: Sequence[str]) -> str | None:
    found, node = _dig(_parsed(raw), key_path)
    if not found or node is None or isinstance(node, (dict, list)):
        return None
    shown = masking.mask_value(node, key_path[-1])
    return None if shown is None else str(shown)


def read_only_reason(code: str) -> EditReadOnlyCode:
    """Map a refusal code to the reason line a non-writable scope shows."""
    if code == "managed":
        return "managed"
    if code == "link_outside":
        return "link_outside"
    if code == "link_dangling":
        return "link_dangling"
    return "not_writable"


def _refusal(exc: Refused) -> EditRefusal:
    return EditRefusal(code=exc.code, params=exc.params)


@dataclass
class _ScopeState:
    scope: EditScope
    target: Target
    inspected: Inspected | None
    refused: Refused | None
    display: str
    real: str
    link: bool
    tracked: bool

    @property
    def raw(self) -> bytes | None:
        return None if self.inspected is None else self.inspected.raw


def _scope_state(store: EditStore, res: Resolution, target: Target) -> _ScopeState:
    show = res.layers.scope.display
    inspected: Inspected | None = None
    refused: Refused | None = None
    real = target.display_path
    link = False
    try:
        inspected = store.inspect(target)
        real = inspected.resolved.real_path
        link = inspected.resolved.link
    except Refused as exc:
        refused = exc
        if exc.real_path is not None:
            # A link the writer won't follow still leads somewhere the row can name.
            real, link = exc.real_path, True
        else:
            try:
                resolved = store.resolve(target)
                real, link = resolved.real_path, resolved.link
            except Refused:
                pass
    tracked = git_tracked.is_tracked(real) if inspected is not None else False
    return _ScopeState(
        as_scope(target.scope) or "project",
        target,
        inspected,
        refused,
        show(target.display_path),
        show(real),
        link,
        tracked,
    )


def _hooks_may_block(res: Resolution) -> bool:
    """True when a settings file holds a ConfigChange hook and hooks are not off."""
    files = res.layers.readable()
    for item in files:
        if item.data.get("disableAllHooks") is True:
            return False
        if "disableAllHooks" in item.data:
            break
    for item in files:
        hooks = item.data.get("hooks")
        if isinstance(hooks, dict):
            found = cast("dict[str, Any]", hooks).get("ConfigChange")
            if isinstance(found, list) and found:
                return True
    return False


def _unwritable(state: _ScopeState) -> tuple[bool, EditReadOnlyCode | None]:
    if state.refused is None:
        return True, None
    return False, read_only_reason(state.refused.code)


# ---------------------------------------------------------------- the preview


def build_preview(
    store: EditStore,
    inputs: EditInputs,
    body: EditPreviewRequest,
    *,
    server_time: datetime,
    now_iso: str,
    reach_inputs: Callable[[], Iterable[tuple[str, str, EditInputs]]] | None = None,
) -> EditPreview:
    """Build the answer of ``POST /api/edit/preview`` for a settings edit.

    Args:
        store: The writer, for the token and the file reads.
        inputs: The project's inputs.
        body: The preview request.
        server_time: The provider's clock, for ``server_time``.
        now_iso: The writer's clock as text, for ``read_at`` when no file was read.
        reach_inputs: Yields (key, name, inputs) of the other projects, for a
            user-scope preview. None means no reaches.

    Returns:
        The preview. A file that can't be edited gives ``refusal``, not an exception.
    """
    setup = inputs.setup
    field = body.field
    res = read_resolution(setup)
    by_scope: dict[EditScope, Target] = {
        scope: t
        for t in targets_of(store, inputs, leftover=False)
        if (scope := as_scope(t.scope)) is not None
    }
    states: dict[EditScope, _ScopeState] = {
        scope: _scope_state(store, res, target) for scope, target in by_scope.items()
    }
    picked = states.get(body.scope)
    refusal: Refused | None = None
    plan: edit_store.Plan | None = None
    if picked is None:
        refusal = Refused("not_editable")
    elif picked.refused is not None:
        refusal = picked.refused
    key_paths: dict[EditScope, tuple[str, ...]] = {
        scope: choose_path(field, state.raw, res.entries, scope)
        for scope, state in states.items()
    }
    if picked is not None and refusal is None:
        try:
            plan = edit_store.plan_set(
                picked.raw, field, body.value, key_paths[body.scope]
            )
        except Refused as exc:
            refusal = exc
    now_runs = runs_at(res.entries, field)
    after_runs = now_runs
    outcomes: dict[EditScope, ScopeOutcome] = dict.fromkeys(
        states, ScopeOutcome(status="unknown", beaten_by=None)
    )
    options: list[OptionRunsAt] = []
    if refusal is None or refusal.code == "no_change":
        outcomes = _outcomes(res, setup, field, states, key_paths, body, plan)
        if plan is not None and picked is not None:
            after = what_if(
                res,
                setup,
                body.scope,
                plan.key_path,
                _stored(plan.key_path, body.value),
            )
            after_runs = runs_at(after, field)
    if picked is not None and (
        refusal is None or refusal.code in ("no_change", "bad_value")
    ):
        options = _options(res, setup, field, body.scope, key_paths[body.scope])
    scopes = [
        _scope_row(state, res, field, key_paths[scope], outcomes[scope])
        for scope, state in states.items()
    ]
    reaches = (
        _reaches(field, body, plan, reach_inputs)
        if body.scope == "user" and reach_inputs is not None and plan is not None
        else []
    )
    diff = (
        edit_diff.edit_diff(picked.raw, plan.new_raw)
        if picked is not None and plan is not None
        else EditDiff(lines=[], new_file=False)
    )
    picked_outcome = outcomes.get(body.scope)
    warnings = _warnings(res, picked, picked_outcome, body.scope, plan)
    exists = picked is not None and picked.raw is not None
    target = EditTarget(
        scope=body.scope,
        display_path=picked.display if picked else "",
        real_path=picked.real if picked else "",
        link=picked.link if picked else False,
        exists=exists,
        git_tracked=picked.tracked if picked else False,
        new_file=picked is not None and picked.inspected is not None and not exists,
    )
    old_value: Scalar | None = None
    if plan is not None:
        old_value = _masked_scalar(plan.old_value, plan.key_path[-1])
    elif picked is not None:
        text = _value_at(picked.raw, key_paths[body.scope])
        old_value = text
    version = ""
    read_at = now_iso
    if picked is not None and picked.inspected is not None:
        read_at = picked.inspected.read_at
        version = store.make_version(picked.inspected, body)
    return EditPreview(
        server_time=server_time,
        seq=body.seq,
        choice_key=edit_store.choice_key(body),
        target=target,
        effect=EditEffect(
            set=EditSetChange(from_=old_value, to=body.value),
            runs=EditRuns(now=now_runs, after=after_runs),
            applies=APPLIES,
        ),
        options=options,
        scopes=scopes,
        reaches=reaches,
        warnings=warnings,
        diff=diff,
        summary=EditSummary(
            verb="creates" if target.new_file else "changes",
            lines_changed=edit_diff.lines_changed(diff.lines),
            display_path=target.display_path,
        ),
        read_at=read_at,
        version=version,
        refusal=None if refusal is None else _refusal(refusal),
    )


def _outcomes(
    res: Resolution,
    setup: SetupContext,
    field: SettingsEditField,
    states: dict[EditScope, _ScopeState],
    key_paths: dict[EditScope, tuple[str, ...]],
    body: EditPreviewRequest,
    plan: edit_store.Plan | None,
) -> dict[EditScope, ScopeOutcome]:
    """Return what the value would do if saved in each scope."""
    out: dict[EditScope, ScopeOutcome] = {}
    for scope, state in states.items():
        path = key_paths[scope]
        if state.refused is not None:
            out[scope] = ScopeOutcome(status="unknown", beaten_by=None)
            continue
        if scope == body.scope and plan is not None:
            value = _stored(plan.key_path, body.value)
        else:
            try:
                value = _stored(path, edit_store.check_value(field, body.value, path))
            except Refused:
                out[scope] = ScopeOutcome(status="unknown", beaten_by=None)
                continue
        entries = what_if(res, setup, scope, path, value)
        out[scope] = outcome_of(entries, field, scope, path)
    return out


def _options(
    res: Resolution,
    setup: SetupContext,
    field: SettingsEditField,
    scope: EditScope,
    key_path: tuple[str, ...],
) -> list[OptionRunsAt]:
    """Return what each option of an effort or effort cap field would run at."""
    choices = edit_fields.options(field)
    if choices is None:
        return []
    subject = "effortLevel" if field in ("effortLevel", "maxEffortLevel") else field
    out: list[OptionRunsAt] = []
    for choice in choices:
        entries = what_if(res, setup, scope, key_path, _stored(key_path, choice))
        out.append(OptionRunsAt(value=choice, runs_at=runs_at(entries, subject)))
    return out


def _scope_row(
    state: _ScopeState,
    res: Resolution,
    field: SettingsEditField,
    key_path: tuple[str, ...],
    outcome: ScopeOutcome,
) -> EditScopeRow:
    del res, field
    writable, reason = _unwritable(state)
    return EditScopeRow(
        scope=state.scope,
        display_path=state.display,
        real_path=state.real,
        link=state.link,
        git_tracked=state.tracked,
        writable=writable,
        read_only_reason=reason,
        current_value=_value_at(state.raw, key_path),
        outcome=outcome,
    )


def _reaches(
    field: SettingsEditField,
    body: EditPreviewRequest,
    plan: edit_store.Plan | None,
    reach_inputs: Callable[[], Iterable[tuple[str, str, EditInputs]]] | None,
) -> list[EditReach]:
    """Return what a user-scope save does to every other project (owner decision O2)."""
    if plan is None or reach_inputs is None:
        return []
    out: list[EditReach] = []
    for key, name, other in reach_inputs():
        if len(out) >= MAX_REACHES:
            break
        try:
            res = read_resolution(other.setup)
            user_raw = _user_raw(res)
            path = choose_path(field, user_raw, res.entries, "user")
            value = _stored(path, edit_store.check_value(field, body.value, path))
            entries = what_if(res, other.setup, "user", path, value)
        except (Refused, OSError, ValueError, KeyError, RecursionError):
            continue
        out.append(
            EditReach(
                project=key, name=name, outcome=outcome_of(entries, field, "user", path)
            )
        )
    return out


def _user_raw(res: Resolution) -> bytes | None:
    for item in res.layers.files:
        if item.layer == "user" and item.state == "ok":
            return json.dumps(item.data).encode("utf-8")
    return None


def _warnings(
    res: Resolution,
    picked: _ScopeState | None,
    outcome: ScopeOutcome | None,
    scope: EditScope,
    plan: edit_store.Plan | None,
) -> list[EditWarning]:
    out: list[EditWarning] = []
    if (
        plan is not None
        and outcome is not None
        and outcome.status in ("overridden", "ignored", "invalid")
    ):
        out.append(
            EditWarning(
                code="wont_win",
                params={
                    "scope": scope,
                    "status": outcome.status,
                    "beaten_by": outcome.beaten_by or "",
                },
            )
        )
    if plan is not None and _hooks_may_block(res):
        out.append(EditWarning(code="config_change_hook", params={}))
    if picked is not None and picked.tracked:
        out.append(EditWarning(code="shared_repo", params={"path": picked.display}))
    return out

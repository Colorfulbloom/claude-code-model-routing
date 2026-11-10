"""The setup answers: the map, one part and the problems, from one cached read.

``SetupService`` runs the eight collectors in ``setup_contract.COLLECTOR_ORDER`` for a
project, hands each one the data of those before it, and builds the three answers from
what they returned (m4-build.md sections 5 and 16, task 9):

- ``SetupMap`` for ``GET /api/setup``: one row per part with its summary (Coded
  params), status counts, counted problems, an unreadable flag, why it is empty, and one
  cell per scope. The scope cells are always there, so the Switch flips with no fetch.
- ``SetupPartAnswer`` for ``GET /api/setup/{part}``: the items in their ``order``, the
  groups in order with counts, the files the part could not read (each with the id of
  its To fix row) and why the part is empty.
- ``ProblemList`` for ``GET /api/problems`` (built by ``problems.py``).

The read is cached per project. A cached read is valid while the combined stat-only
signature of every collector and the caller's data version (the store's pass marker and
the day) both still match, so a poll costs a few ``lstat`` calls and no file is opened.
The etag is a hash of that signature and version, and it is the same value for the
three answers of one read. A request whose ``etag`` matches gets the short ``Unchanged``
answer.

A collector never raises for a bad file. If one raises anyway (a bug), the failure is
logged by name and type only, the collector's parts come back empty, and ``failed`` on
the bundle turns the nav's To fix state to ``failed``.

Nothing here reads a file or the environment. The caller (a provider) hands in a
``SetupRequest`` with the project's ``SetupContext``, a data version, and two functions
that fetch the store's facts (``usage`` and ``transcripts``), which run only on a cold
read.
"""

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

import claude_json
import collect_agents
import collect_hooks
import collect_instructions
import collect_mcp
import collect_plugins
import collect_settings
import collect_skills
import model_catalog
import problems as problems_mod
import read_scope
import setup_codes
import setup_items
from model_check import STATUS_ORDER
from models import (
    SETUP_PARTS,
    SETUP_SCOPES,
    Coded,
    EmptyInfo,
    GroupCount,
    ModelCheckStatus,
    ProblemList,
    ProblemRow,
    SetupItem,
    SetupMap,
    SetupPart,
    SetupPartAnswer,
    SetupPartRow,
    SetupScope,
    SetupScopeCell,
    StatusCount,
    ToFix,
    Unchanged,
    UnreadableFile,
)
from setup_contract import COLLECTOR_ORDER, Collected, Collector, SetupContext

logger = logging.getLogger(__name__)

USAGE_DAYS = 30
CACHE_MAX = 16
ETAG_LENGTH = 32
DOCS_BASE = "https://code.claude.com/docs/en/"

# The docs page behind a part's "how to add one" link. The anchors are not checked
# against the rendered pages yet (fact D-1534), so the links name the page only.
EMPTY_DOCS: dict[SetupPart, str] = {
    "settings": "settings",
    "agents": "sub-agents",
    "instructions": "memory",
    "rules": "memory",
    "skills": "skills",
    "hooks": "hooks",
    "permissions": "permissions",
    "mcp": "mcp",
    "plugins": "plugins",
    "output_style": "output-styles",
}
# Parts whose empty state offers the folder to make. Value: the folder under the
# ``.claude`` folder (a file for ``instructions``).
EMPTY_FOLDERS: dict[SetupPart, str] = {
    "agents": "agents",
    "skills": "skills",
    "rules": "rules",
    "output_style": "output-styles",
    "instructions": "CLAUDE.md",
}
_MODEL_ID = "settings:model"
_EFFORT_ID = "settings:effortLevel"
_MODE_ID = "permissions:defaultMode"
_GLOB_SHOWN = 3

_BY_NAME: dict[str, Collector] = {
    c.name: c
    for c in (
        collect_settings.COLLECTOR,
        collect_plugins.COLLECTOR,
        collect_agents.COLLECTOR,
        collect_skills.COLLECTOR,
        collect_instructions.COLLECTOR,
        collect_hooks.COLLECTOR,
        claude_json.COLLECTOR,
        collect_mcp.COLLECTOR,
    )
}


@dataclass(frozen=True)
class SetupUsage:
    """What the store knows about the last ``days`` days of runs.

    Attributes:
        days: The window's length.
        agent_runs: Runs per agent type (``<plugin>:<name>`` for a plugin agent).
        main_pairs: Main-session runs per (model, effort) pair.
    """

    days: int
    agent_runs: Mapping[str, int]
    main_pairs: Mapping[tuple[str | None, str | None], int]


@dataclass(frozen=True)
class SetupRequest:
    """Everything one answer needs from the caller.

    Attributes:
        project: The project key.
        ctx: The collectors' context.
        listed: True when the project is on Bar Tab's list.
        version: The caller's data version. A new value drops the cached read.
        as_of: The end of the last good ingest pass, or None.
        usage: Fetches the store's run counts. Called by the map and part answers
            only, once per read (the Agents page and To fix never need it).
        transcripts: Fetches the unreadable transcripts. Called on a cold read only.
    """

    project: str
    ctx: SetupContext
    listed: bool
    version: str
    as_of: datetime | None
    usage: Callable[[], SetupUsage | None]
    transcripts: Callable[[], problems_mod.Transcripts]


@dataclass
class UsageView:
    """The parts of a read that change when the store's run counts are added.

    Attributes:
        items: The items by part, with usage and the agent groups.
        groups: The group counts by part.
        rows: The map's part rows.
    """

    items: dict[SetupPart, list[SetupItem]]
    groups: dict[SetupPart, list[GroupCount]]
    rows: list[SetupPartRow]


@dataclass
class Bundle:
    """One project's read and the answers built from it.

    ``items``, ``groups`` and ``rows`` are the read without the store's run counts.
    ``view`` holds the same three with them, filled the first time a map or part
    answer needs it. Problems and To fix never do.
    """

    etag: str
    signature: str
    key: tuple[object, ...]
    as_of: datetime | None
    listed: bool
    ran: list[tuple[str, Collected]]
    failed: tuple[str, ...]
    items: dict[SetupPart, list[SetupItem]]
    unreadable: dict[SetupPart, list[UnreadableFile]]
    groups: dict[SetupPart, list[GroupCount]]
    empty: dict[SetupPart, EmptyInfo | None]
    problems: list[ProblemRow]
    counted: int
    rows: list[SetupPartRow]
    notices: list[Coded]
    agent_items: list[SetupItem] = field(default_factory=list[SetupItem])
    view: UsageView | None = None

    def all_items(self) -> dict[str, SetupItem]:
        """Return every item of every part by id."""
        return {i.id: i for part in SETUP_PARTS for i in self.items[part]}


# ---------------------------------------------------------------- the read


def _context_key(req: SetupRequest) -> tuple[object, ...]:
    ctx = req.ctx
    return (
        req.listed,
        str(ctx.project_dir),
        str(ctx.config_dir),
        str(ctx.home),
        str(ctx.managed_dir),
        ctx.plan,
        ctx.real_mode,
        tuple(sorted(ctx.shell_env.items())),
        req.version,
    )


def _signature(ctx: SetupContext, ran: Sequence[tuple[str, Collected]]) -> str:
    """Join every collector's stat-only fingerprint.

    A collector whose fingerprint fails adds a token that is new every time, so the
    cached read never matches and the next request reads again.
    """
    last = dict(ran)
    pieces: list[str] = []
    for name in COLLECTOR_ORDER:
        try:
            pieces.append(f"{name}={_BY_NAME[name].signature(ctx, last.get(name))}")
        except Exception as exc:  # noqa: BLE001 - a signature bug forces a fresh read
            logger.error(  # noqa: TRY400 - the type only; a traceback could carry file text
                "setup signature %s failed (%s)", name, type(exc).__name__
            )
            pieces.append(f"{name}=error-{time.monotonic_ns()}")
    return "|".join(pieces)


def _etag(req: SetupRequest, signature: str) -> str:
    text = "\n".join([req.project, repr(_context_key(req)), signature])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:ETAG_LENGTH]


def _run_collectors(
    ctx: SetupContext,
) -> tuple[list[tuple[str, Collected]], tuple[str, ...]]:
    ran: list[tuple[str, Collected]] = []
    failed: list[str] = []
    handoff: dict[str, object] = {}
    for name in COLLECTOR_ORDER:
        try:
            got = _BY_NAME[name].read(ctx, handoff)
        except Exception as exc:  # noqa: BLE001 - one bad collector keeps the others
            logger.error(  # noqa: TRY400 - the type only; a traceback could carry file text
                "setup collector %s failed (%s)", name, type(exc).__name__
            )
            failed.append(name)
            got = Collected()
        handoff.update(got.handoff)
        ran.append((name, got))
    return ran, tuple(failed)


# ---------------------------------------------------------------- items


def _merged(ran: Sequence[tuple[str, Collected]]) -> dict[SetupPart, list[SetupItem]]:
    items: dict[SetupPart, list[SetupItem]] = {part: [] for part in SETUP_PARTS}
    for _name, got in ran:
        for part, found in got.items.items():
            items[part].extend(found)
    return {part: setup_items.number(found) for part, found in items.items()}


def _same_model(a: str | None, b: str | None, catalog: model_catalog.Catalog) -> bool:
    if a is None or b is None:
        return False
    one, two = (
        model_catalog.normalize_model(a, catalog)[0],
        model_catalog.normalize_model(b, catalog)[0],
    )
    return a == b if one is None or two is None else one == two


def _value_usage(
    item: SetupItem, usage: SetupUsage, catalog: model_catalog.Catalog
) -> SetupItem:
    """Return a model or effort setting with the main runs that used its value."""
    value = item.effective.value if item.effective is not None else None
    if value is None:
        return item
    total = sum(usage.main_pairs.values())
    at_value = sum(
        runs
        for (model, effort), runs in usage.main_pairs.items()
        if (
            _same_model(value.text, model, catalog)
            if item.id == _MODEL_ID
            else effort == value.text
        )
    )
    coded = Coded(
        code="runs_at_value",
        params={
            "value": value.text,
            "runs": str(at_value),
            "total": str(total),
            "days": str(usage.days),
        },
    )
    return item.model_copy(update={"usage": coded})


def _agent_usage(item: SetupItem, usage: SetupUsage) -> SetupItem:
    runs = usage.agent_runs.get(item.id.removeprefix("agents:"), 0)
    coded = Coded(
        code="agent_runs", params={"runs": str(runs), "days": str(usage.days)}
    )
    return item.model_copy(
        update={"usage": coded, "group": "ran" if runs > 0 else "no_runs"}
    )


def _with_usage(
    items: dict[SetupPart, list[SetupItem]], usage: SetupUsage | None
) -> None:
    """Add usage to agent items and the model and effort settings, and group agents."""
    if usage is None:
        return
    catalog = model_catalog.load_catalog()
    items["agents"] = [_agent_usage(i, usage) for i in items["agents"]]
    items["settings"] = [
        _value_usage(i, usage, catalog) if i.id in (_MODEL_ID, _EFFORT_ID) else i
        for i in items["settings"]
    ]


def _group_counts(part: SetupPart, found: Sequence[SetupItem]) -> list[GroupCount]:
    """Return the groups of a part, in the order the items first show them.

    Agents are grouped ``ran`` then ``no_runs`` (the store's 30 days), whatever the
    items' own order, so the page lists runs first. Rows keep their order.
    """
    counts: dict[str, int] = {}
    for item in found:
        if item.group is not None:
            counts[item.group] = counts.get(item.group, 0) + 1
    if part == "agents":
        keys = [k for k in setup_codes.AGENT_GROUPS if k in counts]
    else:
        keys = list(counts)
    return [GroupCount(key=key, count=counts[key]) for key in keys]


# ---------------------------------------------------------------- unreadable


def _unreadable_by_part(
    ran: Sequence[tuple[str, Collected]],
) -> dict[SetupPart, list[UnreadableFile]]:
    """Split every collector's unreadable files by part, each with its row id.

    A file with no part feeds every part of its collector (a settings file feeds
    Settings, Permissions and Output style). Duplicates of one file and reason in a
    part are dropped.
    """
    out: dict[SetupPart, list[UnreadableFile]] = {part: [] for part in SETUP_PARTS}
    seen: set[tuple[SetupPart, str, str]] = set()
    for name, got in ran:
        parts = tuple(_BY_NAME[name].parts)
        for file in got.unreadable:
            row_id = (
                problems_mod.read_failure_id(file.reason, file.file)
                if problems_mod.is_read_failure(file)
                else None
            )
            mine = (file.part,) if file.part is not None else parts
            for part in mine:
                key = (part, file.file, file.reason)
                if key in seen:
                    continue
                seen.add(key)
                out[part].append(
                    file.model_copy(update={"problem": row_id, "part": part})
                )
    return out


# ---------------------------------------------------------------- the map


def _count_summary(  # noqa: PLR0912 - one branch per part's summary words
    part: SetupPart, found: Sequence[SetupItem], known: bool
) -> Coded:
    """Return what a part says on the map, as a code and string parameters."""
    params: dict[str, str] = {}
    if part == "settings":
        for item_id, name in ((_MODEL_ID, "model"), (_EFFORT_ID, "effort")):
            item = next((i for i in found if i.id == item_id), None)
            value = item.effective.value if item and item.effective else None
            if value is not None:
                params[name] = value.text
    elif part == "agents":
        params["count"] = str(len(found))
        if known:
            params["no_runs"] = str(sum(1 for i in found if i.group == "no_runs"))
    elif part == "instructions":
        params["count"] = str(len(found))
        params["lines"] = str(
            sum(i.facts.instruction.lines for i in found if i.facts.instruction)
        )
    elif part == "rules":
        on_demand = [
            i for i in found if i.loads is not None and i.loads.kind == "on_demand"
        ]
        globs = list(
            dict.fromkeys(g for i in on_demand if i.loads for g in i.loads.globs)
        )
        params["count"] = str(len(found))
        params["on_demand"] = str(len(on_demand))
        if globs:
            params["globs"] = ", ".join(globs[:_GLOB_SHOWN])
    elif part == "hooks":
        params["count"] = str(len(found))
        params["events"] = str(len({i.group for i in found if i.group}))
    elif part == "permissions":
        kinds = [i.facts.permission.kind for i in found if i.facts.permission]
        for kind in ("allow", "ask", "deny"):
            params[kind] = str(kinds.count(kind))
        mode = next((i for i in found if i.id == _MODE_ID), None)
        if mode is not None and mode.effective and mode.effective.value:
            params["mode"] = mode.effective.value.text
    elif part == "mcp":
        params["count"] = str(len(found))
        params["not_approved"] = str(sum(1 for i in found if i.status == "ignored"))
    elif part == "plugins":
        params["count"] = str(len(found))
        params["enabled"] = str(
            sum(
                1
                for i in found
                if i.facts.plugin and any(s.enabled for s in i.facts.plugin.enabled)
            )
        )
    elif part == "output_style":
        active = next(
            (i.facts.output_style.active for i in found if i.facts.output_style), None
        )
        if active is not None:
            params["active"] = active
    else:
        params["count"] = str(len(found))
    return Coded(code=setup_codes.SUMMARY_CODES[part], params=params)


def _status_counts(found: Sequence[SetupItem]) -> list[StatusCount]:
    counts: dict[ModelCheckStatus, int] = {}
    for item in found:
        counts[item.status] = counts.get(item.status, 0) + 1
    return [StatusCount(status=s, count=counts[s]) for s in STATUS_ORDER if s in counts]


def _empty(part: SetupPart, ctx: SetupContext, *, listed: bool) -> EmptyInfo:
    """Return why a part has no items and the action its empty state offers."""
    folder = EMPTY_FOLDERS.get(part)
    if folder is None:
        return EmptyInfo(
            reason="none_found", action="docs", target=DOCS_BASE + EMPTY_DOCS[part]
        )
    if listed and ctx.project_dir is not None:
        base = (
            ctx.project_dir if part == "instructions" else ctx.project_dir / ".claude"
        )
    else:
        base = ctx.config_dir
    return EmptyInfo(reason="none_found", action="copy_path", target=str(base / folder))


def _scopes_of(item: SetupItem) -> set[str]:
    found = {s.scope for s in item.sources}
    if not found and item.scope is not None:
        found.add(item.scope)
    return found


def _scope_values(found: Sequence[SetupItem], scope: SetupScope) -> dict[str, str]:
    """Return the model and effort the settings sources of one scope set."""
    values: dict[str, str] = {}
    for item_id, name in ((_MODEL_ID, "model"), (_EFFORT_ID, "effort")):
        item = next((i for i in found if i.id == item_id), None)
        if item is None:
            continue
        for source in item.sources:
            if source.scope == scope and source.value is not None:
                values[name] = source.value.text
                break
    return values


def _cell(
    part: SetupPart,
    scope: SetupScope,
    found: Sequence[SetupItem],
    failed: set[str],
    *,
    listed: bool,
) -> SetupScopeCell:
    in_scope = [i for i in found if scope in _scopes_of(i)]
    if scope in ("project_local", "project") and not listed:
        return SetupScopeCell(scope=scope, state="not_visible", summary=None)
    if scope == "command_line":
        state = "set" if in_scope else "not_visible"
    elif scope == "shell":
        state = (
            ("set" if in_scope else "not_set") if part == "settings" else "not_visible"
        )
    elif scope in failed:
        state = "unreadable"
    else:
        state = "set" if in_scope else "not_set"
    if state != "set":
        return SetupScopeCell(scope=scope, state=state, summary=None)
    values = _scope_values(found, scope) if part == "settings" else {}
    summary = (
        Coded(code="model_effort", params=values)
        if values
        else Coded(code="count", params={"n": str(len(in_scope))})
    )
    return SetupScopeCell(scope=scope, state=state, summary=summary)


def _part_rows(  # noqa: PLR0913 - the pieces the map reads
    items: Mapping[SetupPart, Sequence[SetupItem]],
    unreadable: Mapping[SetupPart, Sequence[UnreadableFile]],
    empty: Mapping[SetupPart, EmptyInfo | None],
    rows: Sequence[ProblemRow],
    *,
    listed: bool,
    known: bool,
) -> list[SetupPartRow]:
    out: list[SetupPartRow] = []
    for part in SETUP_PARTS:
        found = items[part]
        failures = [u for u in unreadable[part] if problems_mod.is_read_failure(u)]
        failed_scopes = {u.scope for u in failures if u.scope is not None}
        mine = problems_mod.counted(r for r in rows if r.part == part)
        out.append(
            SetupPartRow(
                part=part,
                summary=_count_summary(part, found, known),
                statuses=_status_counts(found),
                counted_problems=mine,
                unreadable=bool(failures),
                empty=empty[part],
                scopes=[
                    _cell(part, scope, found, failed_scopes, listed=listed)
                    for scope in SETUP_SCOPES
                ],
            )
        )
    return out


def _notices(rows: Sequence[ProblemRow], *, listed: bool) -> list[Coded]:
    found: list[Coded] = []
    if not listed:
        found.append(Coded(code="project_not_listed", params={}))
    found.extend(
        Coded(code=r.code, params=r.params) for r in rows if r.group == "notice"
    )
    return found


# ---------------------------------------------------------------- the bundle


def build_bundle(req: SetupRequest) -> Bundle:
    """Run the collectors and build the read, without the store's run counts."""
    ran, failed = _run_collectors(req.ctx)
    items = _merged(ran)
    unreadable = _unreadable_by_part(ran)
    try:
        transcripts = req.transcripts()
    except Exception as exc:  # noqa: BLE001
        logger.error(  # noqa: TRY400 - the type only; a traceback could carry file text
            "setup transcripts failed (%s)", type(exc).__name__
        )
        transcripts = problems_mod.Transcripts()
    scope = read_scope.Scope(req.ctx)
    by_id = {i.id: i for part in SETUP_PARTS for i in items[part]}
    rows = problems_mod.build_rows(
        [(got, tuple(_BY_NAME[name].parts)) for name, got in ran],
        by_id,
        transcripts,
        scope_of=scope.scope_of,
        display=scope.display,
    )
    empty: dict[SetupPart, EmptyInfo | None] = {
        part: _empty(part, req.ctx, listed=req.listed) if not items[part] else None
        for part in SETUP_PARTS
    }
    signature = _signature(req.ctx, ran)
    return Bundle(
        etag=_etag(req, signature),
        signature=signature,
        key=_context_key(req),
        as_of=req.as_of,
        listed=req.listed,
        ran=ran,
        failed=failed,
        items=items,
        unreadable=unreadable,
        groups={part: _group_counts(part, items[part]) for part in SETUP_PARTS},
        empty=empty,
        problems=rows,
        counted=problems_mod.counted(rows),
        rows=_part_rows(
            items,
            unreadable,
            empty,
            rows,
            listed=req.listed,
            known=False,
        ),
        notices=_notices(rows, listed=req.listed),
        agent_items=list(items["agents"]),
    )


def _usage_view(req: SetupRequest, bundle: Bundle) -> UsageView:
    """Add the store's run counts to a read. A store problem leaves them out."""
    try:
        usage = req.usage()
    except Exception as exc:  # noqa: BLE001 - a store problem leaves usage out
        logger.error(  # noqa: TRY400 - the type only; a traceback could carry file text
            "setup usage failed (%s)", type(exc).__name__
        )
        usage = None
    if usage is None:
        return UsageView(items=bundle.items, groups=bundle.groups, rows=bundle.rows)
    items: dict[SetupPart, list[SetupItem]] = {
        part: list(bundle.items[part]) for part in SETUP_PARTS
    }
    _with_usage(items, usage)
    return UsageView(
        items=items,
        groups={part: _group_counts(part, items[part]) for part in SETUP_PARTS},
        rows=_part_rows(
            items,
            bundle.unreadable,
            bundle.empty,
            bundle.problems,
            listed=bundle.listed,
            known=True,
        ),
    )


class SetupService:
    """The per-project cache of setup reads, and the answers built from it."""

    def __init__(self, *, started_at: datetime) -> None:
        """Make an empty service.

        Args:
            started_at: When the server started, for the shell scope's line.
        """
        self._started_at = started_at
        self._cache: OrderedDict[str, Bundle] = OrderedDict()
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, project: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(project, threading.Lock())

    def bundle(self, req: SetupRequest) -> Bundle:
        """Return the project's read, from the cache while its signature holds."""
        with self._lock(req.project):
            with self._guard:
                cached = self._cache.get(req.project)
            if (
                cached is not None
                and cached.key == _context_key(req)
                and cached.signature == _signature(req.ctx, cached.ran)
            ):
                with self._guard:
                    self._cache.move_to_end(req.project)
                return cached
            built = build_bundle(req)
            with self._guard:
                self._cache[req.project] = built
                self._cache.move_to_end(req.project)
                while len(self._cache) > CACHE_MAX:
                    self._cache.popitem(last=False)
            return built

    def _view(self, req: SetupRequest, bundle: Bundle) -> UsageView:
        """Return the read with run counts, building it once per read."""
        with self._lock(req.project):
            if bundle.view is None:
                bundle.view = _usage_view(req, bundle)
            return bundle.view

    # ------------------------------------------------------------ the answers

    def setup_map(
        self, req: SetupRequest, etag: str | None, now: datetime
    ) -> SetupMap | Unchanged:
        """Return ``GET /api/setup``, or the short answer when ``etag`` matches."""
        found = self.bundle(req)
        if etag is not None and etag == found.etag:
            return _same(req.project, now, found.etag)
        return SetupMap(
            project=req.project,
            server_time=now,
            as_of=found.as_of,
            etag=found.etag,
            unchanged=False,
            parts=self._view(req, found).rows,
            notices=found.notices,
            server_started_at=self._started_at,
            listed=found.listed,
        )

    def setup_part(
        self, req: SetupRequest, part: SetupPart, etag: str | None, now: datetime
    ) -> SetupPartAnswer | Unchanged:
        """Return ``GET /api/setup/{part}``, or the short answer on a matching etag."""
        found = self.bundle(req)
        if etag is not None and etag == found.etag:
            return _same(req.project, now, found.etag)
        view = self._view(req, found)
        return SetupPartAnswer(
            project=req.project,
            server_time=now,
            as_of=found.as_of,
            etag=found.etag,
            unchanged=False,
            part=part,
            items=view.items[part],
            groups=view.groups[part],
            unreadable=found.unreadable[part],
            empty=found.empty[part],
        )

    def problems(
        self, req: SetupRequest, etag: str | None, now: datetime
    ) -> ProblemList | Unchanged:
        """Return ``GET /api/problems``, or the short answer when ``etag`` matches."""
        found = self.bundle(req)
        if etag is not None and etag == found.etag:
            return _same(req.project, now, found.etag)
        return ProblemList(
            project=req.project,
            server_time=now,
            as_of=found.as_of,
            etag=found.etag,
            unchanged=False,
            rows=found.problems,
            counted=found.counted,
        )

    def to_fix(self, req: SetupRequest) -> ToFix:
        """Return the nav's count from the same cached read as the problems answer."""
        try:
            found = self.bundle(req)
        except Exception as exc:  # noqa: BLE001 - the nav says "couldn't check"
            logger.error(  # noqa: TRY400 - the type only; a traceback could carry file text
                "setup problems pass failed (%s)", type(exc).__name__
            )
            return ToFix(state="failed", count=None, etag=None)
        if found.failed:
            return ToFix(state="failed", count=None, etag=None)
        return ToFix(state="ok", count=found.counted, etag=found.etag)

    def agent_items(self, req: SetupRequest) -> list[SetupItem]:
        """Return the agent items of the project's read, for the Agents page."""
        return list(self.bundle(req).agent_items)


def _same(project: str, now: datetime, etag: str) -> Unchanged:
    return Unchanged(project=project, server_time=now, etag=etag, unchanged=True)

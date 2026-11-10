"""The per-session Model check: what the setup asks for against what the runs used.

``resolve_entries`` builds the resolver entries for one project. It reads settings,
agent files, rules and managed settings through ``collect`` and nothing else. The
caller passes the folders and the shell environment, so this module never reads
``os.environ`` or looks a home folder up. ``build_model_check`` groups a session's
runs by agent type, asks ``pincheck.check_agent`` about each type, and maps the
answer into the response model's rows.

A row's status is one of the seven resolver words. Each setting (model, effort) gets
a status, and the row takes the worst one. The pin check state says how the runs
compare with the setup, the pin's own resolver status says what the setup does.

Mapping, as source -> status word, then why:

- pin status invalid -> invalid. The resolver rejects the value. Runs say nothing
  about it, so it wins over any run state.
- pin status ignored -> ignored. The setting has no effect, such as a user-level
  effort on a model that takes none. Same reason.
- state differs -> overridden. NO CLEAN MAPPING. Runs used another value than
  expected. Something the resolver cannot see beat the pin, so it lost in practice.
- state mixed -> overridden. NO CLEAN MAPPING. Same, with the runs split between
  values.
- state overridden -> overridden. The resolver's winner is not the pin.
- pin status overridden -> overridden. Same, when no run value exists to check.
- state cannot_check -> unknown. The expected value is unknown, so nothing can be
  compared.
- pin status unknown -> unknown. The resolver cannot say what wins.
- pin status lowered (state matches_lowered, or matches when runs used the pin) ->
  lowered. A cap lowers the pin.
- pin status default -> default. The pin is the built-in default.
- pin status in_effect -> in_effect. The pin wins and the runs match it.
- agent with no file, no pin, or unnamed -> None. Nothing is pinned, so nothing to
  judge. The row still lists the runs.
- any other pin status -> unknown. A resolver word this module does not know.

Worst first across the two settings: invalid, overridden, ignored, unknown, lowered,
default, in_effect.

Reason codes and their params (all values are strings, a missing value is left out).
Every code carries ``setting`` (the worst setting, ``model`` or ``effort``),
``settings`` (a comma list of the settings that share the row's status) and
``value`` (what the pin says), except the three codes with no status.

- ``in_effect``, ``default``
- ``lowered_by_cap``  adds ``expected``, ``cap_key``, ``cap_value``, ``cap_model``,
  ``cap_file``, ``cap_line``
- ``lowered_ran_at_pin``  same, for runs that used the pin despite the cap
- ``pin_overridden``  adds ``expected``, ``by_key``, ``by_file``, ``by_line``,
  ``by_layer``, ``by_via``
- ``pin_ignored``, ``pin_invalid``, ``expected_unknown``, ``unknown_status``
- ``ran_differs``, ``ran_mixed``  add ``expected``, ``ran`` (the distinct run values,
  most common first, joined by ", ")
- ``no_agent_file``, ``unnamed_agent``, ``no_pin``  (status None) carry no params

File names in a row are display paths, never absolute ones. A project file shows
relative to the project folder (``.claude/settings.json``). A file in the Claude
folder shows as ``~/<folder name>/<path>`` (``~/.claude/settings.json``), and a
managed file as ``<managed folder name>/<path>``.
"""

import collections
import functools
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

import collect
import model_catalog
import pincheck
import resolve
from models import (
    ModelCheck,
    ModelCheckRow,
    ModelCheckStatus,
    RanPair,
    SetPair,
    SetValue,
    TimelineRun,
)
from usage import Row

# A project folder that cannot exist: /dev/null is a file, so nothing lies below it.
NO_PROJECT = os.devnull

# Worst first.
STATUS_ORDER: tuple[ModelCheckStatus, ...] = (
    "invalid",
    "overridden",
    "ignored",
    "unknown",
    "lowered",
    "default",
    "in_effect",
)
_KINDS = ("model", "effort")
_MAIN_KEY = pincheck.MAIN
_UNNAMED_KEY = pincheck.UNNAMED
_TIMELINE_UNNAMED = "unnamed"

_Judged = tuple[ModelCheckStatus, str, dict[str, str]]


@functools.cache
def _rules() -> dict[str, Any]:
    return resolve.load_rules()


@functools.cache
def _agent_fields() -> tuple[str, ...]:
    return tuple(resolve.load_agent_fields())


# ---------------------------------------------------------------- entries


def _display(
    path: object,
    *,
    project_dir: Path | None,
    claude_dir: Path,
    managed_dir: Path | None,
) -> object:
    """Return a display path for a file an entry names. Never an absolute path."""
    if not isinstance(path, str):
        return path
    target = PurePath(path)
    if project_dir is not None and target.is_relative_to(project_dir):
        return target.relative_to(project_dir).as_posix()
    if target.is_relative_to(claude_dir):
        return f"~/{claude_dir.name}/{target.relative_to(claude_dir).as_posix()}"
    if managed_dir is not None and target.is_relative_to(managed_dir):
        return f"{managed_dir.name}/{target.relative_to(managed_dir).as_posix()}"
    return target.name


def resolve_entries(
    *,
    claude_dir: Path,
    project_dir: Path | None,
    managed_dir: Path | None,
    shell_env: Mapping[str, str],
) -> list[Row]:
    """Return the resolver entries for one project, as the old ``_entries`` does.

    Args:
        claude_dir: The Claude config folder (settings, agents and rules).
        project_dir: The project folder, or None for no project (user and managed
            files only).
        managed_dir: The managed settings folder, or None.
        shell_env: The shell environment the resolver may read. The caller decides
            what goes in. This function never reads ``os.environ``.

    Returns:
        ``resolve.resolve`` entries with every ``file`` and ``other_file`` turned
        into a display path.
    """
    rules = _rules()
    collected = collect.collect(
        config_dir=str(claude_dir),
        project_dir=str(project_dir) if project_dir is not None else NO_PROJECT,
        managed_dir=str(managed_dir) if managed_dir is not None else None,
        shell_env=shell_env,
        rules=rules,
    )
    entries = resolve.resolve(
        resolve.Inputs(collected=collected), rules, _agent_fields()
    )
    shown: list[Row] = []
    for entry in entries:
        copy = dict(entry)
        for field in ("file", "other_file"):
            if field in copy:
                copy[field] = _display(
                    copy[field],
                    project_dir=project_dir,
                    claude_dir=claude_dir,
                    managed_dir=managed_dir,
                )
        shown.append(copy)
    return shown


# ---------------------------------------------------------------- one setting


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _params(items: Mapping[str, object]) -> dict[str, str]:
    """Return the items whose value is set, as strings."""
    return {key: text for key, v in items.items() if (text := _text(v)) is not None}


def _expected(setting: Row) -> object:
    exp: Row = setting["expected"]
    return exp.get("becomes") if exp.get("status") == "lowered" else exp.get("value")


def _joined(values: Iterable[object]) -> str:
    return ", ".join(str(v) for v in values)


def _lowered(setting: Row, base: dict[str, str], *, ran_at_pin: bool) -> _Judged:
    cap: Row = setting["cap"] or {}
    params = base | _params(
        {
            "expected": _expected(setting),
            "cap_key": cap.get("key"),
            "cap_value": cap.get("value"),
            "cap_model": cap.get("model"),
            "cap_file": cap.get("file"),
            "cap_line": cap.get("line"),
        }
    )
    return "lowered", "lowered_ran_at_pin" if ran_at_pin else "lowered_by_cap", params


def _judge_setting(kind: str, setting: Row) -> _Judged:
    """Return (status, reason_code, params) for one pinned setting."""
    pinned: Row = setting["pinned"]
    exp: Row = setting["expected"]
    status = pinned.get("status")
    state = setting["state"]
    base = _params({"setting": kind, "value": pinned.get("value")})
    result: _Judged
    if status == "invalid":
        result = "invalid", "pin_invalid", base
    elif status == "ignored":
        result = (
            "ignored",
            "pin_ignored",
            base | _params({"expected": _expected(setting)}),
        )
    elif state in (pincheck.DIFFERS, pincheck.MIXED):
        code = "ran_differs" if state == pincheck.DIFFERS else "ran_mixed"
        ran = _params({"expected": _expected(setting), "ran": _joined(setting["ran"])})
        result = "overridden", code, base | ran
    elif state == pincheck.OVERRIDDEN or status == "overridden":
        by = _params(
            {
                "expected": _expected(setting),
                "by_key": exp.get("key"),
                "by_file": exp.get("file"),
                "by_line": exp.get("line"),
                "by_layer": exp.get("layer"),
                "by_via": exp.get("via"),
            }
        )
        result = "overridden", "pin_overridden", base | by
    elif state == pincheck.CANNOT_CHECK or status == "unknown":
        result = "unknown", "expected_unknown", base
    elif status == "lowered":
        result = _lowered(setting, base, ran_at_pin=state == pincheck.MATCHES)
    elif status in ("default", "in_effect"):
        result = status, status, base
    else:
        result = "unknown", "unknown_status", base
    return result


def _worst(judged: Mapping[str, _Judged]) -> _Judged:
    """Return the worst setting's result, the model first on a tie."""
    return min(judged.values(), key=lambda item: STATUS_ORDER.index(item[0]))


# ---------------------------------------------------------------- rows


def _ranked(values: Iterable[str | None]) -> list[str]:
    """Distinct values, most common first, ties in first-seen order."""
    seen = [v for v in values if v is not None]
    counts = collections.Counter(seen)
    return sorted(dict.fromkeys(seen), key=lambda v: -counts[v])


def _ran(runs: Sequence[Row]) -> RanPair:
    models = _ranked(r["model"] for r in runs)
    efforts = _ranked(r["effort"] for r in runs)
    return RanPair(
        model=models[0] if models else None,
        effort=efforts[0] if efforts else None,
        mixed=len(models) > 1 or len(efforts) > 1,
    )


def _set_value(setting: Row | None, source: str) -> SetValue | None:
    """Return what a pin sets.

    The scope is ``agent`` for an agent file, else the layer of the winning settings
    entry (the Main session's pin is the winner). A pin whose value is None sets
    nothing, so it returns None (the resolver's default with no value, when no
    settings file sets the model or the effort).
    """
    if setting is None:
        return None
    pinned: Row = setting["pinned"]
    if pinned["value"] is None:
        return None
    scope = "agent" if source == "agent_file" else setting["expected"].get("layer")
    return SetValue(
        value=str(pinned["value"]),
        file=pinned.get("file"),
        line=pinned.get("line"),
        scope=scope,
    )


@dataclass(frozen=True)
class Verdict:
    """The check of one agent key: what it sets, how the runs compare, the status.

    ``status`` is None when nothing is pinned (``reason_code`` then says why, one of
    ``no_agent_file``, ``no_pin`` and ``unnamed_agent``). ``runs`` counts the runs
    given. ``mismatched_runs`` counts the runs that differ from the pin on a
    setting whose runs differ or are mixed.
    """

    set: SetPair
    status: ModelCheckStatus | None
    reason_code: str
    params: dict[str, str]
    runs: int
    mismatched_runs: int


def agent_key(agent: str | None) -> str:
    """Return the pin check key for a timeline agent (None is the main session)."""
    if agent is None:
        return _MAIN_KEY
    return _UNNAMED_KEY if agent == _TIMELINE_UNNAMED else agent


def judge_agent(
    entries: Sequence[Row],
    key: str,
    runs: Sequence[Row],
    catalog: model_catalog.Catalog,
) -> Verdict:
    """Check one agent key against the resolver entries and map it to a status.

    This is the per-agent check the timeline's rows and the Agents page share, so
    both use the mapping in the module docstring.

    Args:
        entries: The ``resolve_entries`` result for the project.
        key: ``@main``, ``@unnamed`` or an agent type.
        runs: The agent's runs as ``{run_id, model, effort}`` (``requests`` may be
            there too). Empty for a check of the setup alone.
        catalog: The model catalog, so an alias and its dated name compare equal.

    Returns:
        The verdict. A key with no file, no pin, or ``@unnamed`` has status None.
    """
    check = pincheck.check_agent(list(entries), key, [], runs, catalog)
    if check is None or check["pinned"] == "none":
        code = (
            "unnamed_agent"
            if key == _UNNAMED_KEY
            else "no_pin"
            if check is not None
            else "no_agent_file"
        )
        return Verdict(
            set=SetPair(model=None, effort=None),
            status=None,
            reason_code=code,
            params={},
            runs=len(runs),
            mismatched_runs=0,
        )
    settings: dict[str, Row] = {k: check[k] for k in _KINDS if check[k] is not None}
    judged = {k: _judge_setting(k, s) for k, s in settings.items()}
    status, code, params = _worst(judged)
    same = [k for k, (s, _c, _p) in judged.items() if s == status]
    return Verdict(
        set=SetPair(
            model=_set_value(settings.get("model"), check["source"]),
            effort=_set_value(settings.get("effort"), check["source"]),
        ),
        status=status,
        reason_code=code,
        params=params | {"settings": ",".join(same)},
        runs=check["total_runs"],
        mismatched_runs=check["mismatched_runs"],
    )


def _row(
    agent: str | None,
    runs: Sequence[Row],
    entries: list[Row],
    catalog: model_catalog.Catalog,
) -> ModelCheckRow:
    verdict = judge_agent(entries, agent_key(agent), runs, catalog)
    return ModelCheckRow(
        agent=agent,
        set=verdict.set,
        ran=_ran(runs),
        status=verdict.status,
        reason_code=verdict.reason_code,
        params=verdict.params,
        runs=verdict.runs,
        mismatched_runs=verdict.mismatched_runs,
    )


def _sort_key(row: ModelCheckRow) -> tuple[bool, bool, str]:
    return (row.status == "in_effect", row.agent is not None, row.agent or "")


def build_model_check(
    *,
    entries: Sequence[Row],
    runs: Sequence[TimelineRun],
    catalog: model_catalog.Catalog,
) -> ModelCheck:
    """Build the Model check for one session.

    Args:
        entries: The ``resolve_entries`` result for the session's project.
        runs: The runs ``build_timeline`` passes (the main session has ``agent`` None).
        catalog: The model catalog, so an alias and its dated name compare equal.

    Returns:
        One row per agent type, the main session included, worst first, then by
        agent name with the main session ahead of the named agents. Rows whose status
        is in_effect come last. ``in_effect_count`` counts those rows.
    """
    by_agent: dict[str | None, list[Row]] = {}
    for run in runs:
        by_agent.setdefault(run.agent, []).append(
            {"run_id": run.run_id, "model": run.model, "effort": run.effort}
        )
    return build_model_check_from_runs(
        entries=entries, runs_by_agent=by_agent, catalog=catalog
    )


def build_model_check_from_runs(
    *,
    entries: Sequence[Row],
    runs_by_agent: Mapping[str | None, Sequence[Row]],
    catalog: model_catalog.Catalog,
) -> ModelCheck:
    """Build the Model check from runs that are already grouped by agent.

    This is ``build_model_check`` without the timeline's run objects, for a caller
    that holds many runs (Review's Summary). The result is the same.

    Args:
        entries: The ``resolve_entries`` result for the project.
        runs_by_agent: Each agent's runs as ``{run_id, model, effort}`` dicts. The key
            is the timeline's agent name: None for the main session, ``unnamed`` for an
            unnamed agent, else the agent type.
        catalog: The model catalog, so an alias and its dated name compare equal.

    Returns:
        The Model check, as ``build_model_check`` returns it.
    """
    listed = list(entries)
    rows = [
        _row(agent, group, listed, catalog) for agent, group in runs_by_agent.items()
    ]
    rows.sort(key=_sort_key)
    return ModelCheck(
        rows=rows,
        in_effect_count=sum(1 for row in rows if row.status == "in_effect"),
    )

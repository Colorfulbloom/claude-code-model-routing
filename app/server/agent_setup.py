"""The setup half of Review's Agents page: what each agent file sets, and the check.

``load_setup`` reads the user and project agent files and the main session's pins
through ``model_check.resolve_entries`` (so through ``collect`` and ``resolve``,
nothing else). ``check_agent`` judges one agent key over a range's runs with the
same per-agent check and status mapping as the timeline's Model check
(``model_check.judge_agent``, mapping in that module's docstring). ``never_ran``
lists the agent files with no run in the range.

An agent file that loads is one whose ``agentFile`` entry is in effect or unknown.
A project file wins over a user file of the same name, as Claude Code does, because
the resolver ranks the layers and marks the loser overridden. A name that ran with
no loading file in either scope (a plugin or built-in agent) has scope ``no_file``.

Why ``set`` holds no value, as ``set_reason``:

- ``sets_nothing``  the file (or the main session) sets neither model nor effort
- ``no_file``  the agent type ran with no user or project file, and ``@unnamed``
  agents have no file either
- ``read_failed``  the setup could not be read, see ``AgentSetup.failed``

When only one of model and effort is set, ``set`` holds a SetPair with the other
None. This module never reads ``os.environ`` or looks a home folder up.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import model_catalog
import model_check
import pincheck
from models import (
    AgentFileScope,
    AgentNoRuns,
    AgentScope,
    ModelCheckStatus,
    SetPair,
    SetReason,
)
from usage import Row

# What ``collect`` and ``resolve`` can raise for a setup they cannot read. ``collect``
# turns a missing or unreadable file into data, so these are the rest: an operating
# system error from a folder walk, and a ValueError, which covers a path with a null
# byte (``open``), a text that cannot decode, and the resolver's own ValueError when
# the rules disagree. Anything else is a bug and must show.
SETUP_ERRORS: tuple[type[Exception], ...] = (OSError, ValueError)

_LOADS = ("in_effect", "unknown")
_FILE_SCOPES: tuple[AgentFileScope, ...] = ("user", "project")
_MAIN_KEY = pincheck.MAIN
_UNNAMED_KEY = pincheck.UNNAMED
_CATALOG = model_catalog.load_catalog()


@dataclass(frozen=True)
class AgentFile:
    """One agent file that loads, in the scope that wins its name."""

    name: str
    scope: AgentFileScope
    set: SetPair | None
    set_reason: SetReason | None


@dataclass(frozen=True)
class AgentSetup:
    """What the user and project scopes set, read once.

    ``failed`` is True when reading raised one of ``SETUP_ERRORS``. Then ``files`` is
    empty, ``main`` is None and the API answers a ``CardError`` with card
    ``agent_setup`` (and one with ``model_check`` for the Summary).

    ``files`` maps an agent type to its file. ``main`` is the main session's pins,
    or None when it sets neither (``main_reason`` then says why).
    """

    failed: bool = False
    files: Mapping[str, AgentFile] = field(default_factory=dict[str, AgentFile])
    main: SetPair | None = None
    main_reason: SetReason | None = None
    entries: Sequence[Row] = ()
    catalog: model_catalog.Catalog = field(default_factory=lambda: _CATALOG)


@dataclass(frozen=True)
class AgentCheck:
    """The check of one agent key over a range.

    ``status`` is None when nothing is set or the setup could not be read. Then
    ``reason_code`` is the M2 code without a status (``no_agent_file``, ``no_pin``,
    ``unnamed_agent``), or None for a failed setup. ``runs_as_set`` and
    ``runs_not_as_set`` are None when ``status`` is None.
    """

    scope: AgentScope
    set: SetPair | None
    set_reason: SetReason | None
    status: ModelCheckStatus | None
    reason_code: str | None
    params: dict[str, str]
    runs_as_set: int | None
    runs_not_as_set: int | None


def _shown(pair: SetPair) -> tuple[SetPair | None, SetReason | None]:
    """Return the pair as ``set``, or None with ``sets_nothing`` when it is empty."""
    if pair.model is None and pair.effort is None:
        return None, "sets_nothing"
    return pair, None


def _loading_files(entries: Sequence[Row]) -> dict[str, AgentFileScope]:
    """Return {agent name: scope} for the agent files that load."""
    found: dict[str, AgentFileScope] = {}
    for entry in entries:
        if (
            entry.get("key") != "agentFile"
            or entry.get("scope") != "agent"
            or entry.get("status") not in _LOADS
        ):
            continue
        name, layer = entry.get("agent"), entry.get("layer")
        if isinstance(name, str) and layer in _FILE_SCOPES:
            found.setdefault(name, layer)
    return found


def from_entries(
    entries: Sequence[Row], catalog: model_catalog.Catalog | None = None
) -> AgentSetup:
    """Build the setup from resolver entries, for a caller that caches them.

    Args:
        entries: The ``model_check.resolve_entries`` result for the project.
        catalog: The model catalog. Loaded from the rules file when None.

    Returns:
        The setup, not failed.
    """
    used = _CATALOG if catalog is None else catalog
    files: dict[str, AgentFile] = {}
    for name, scope in _loading_files(entries).items():
        shown, reason = _shown(model_check.judge_agent(entries, name, [], used).set)
        files[name] = AgentFile(name, scope, shown, reason)
    main, main_reason = _shown(
        model_check.judge_agent(entries, _MAIN_KEY, [], used).set
    )
    return AgentSetup(
        files=files, main=main, main_reason=main_reason, entries=entries, catalog=used
    )


def load_setup(
    claude_dir: Path,
    project_dir: Path | None,
    managed_dir: Path | None,
    shell_env: Mapping[str, str],
) -> AgentSetup:
    """Read the agent files and the main session's pins for one project.

    Args:
        claude_dir: The Claude config folder (settings and user agents).
        project_dir: The project folder, or None for user and managed scope only.
        managed_dir: The managed settings folder, or None.
        shell_env: The shell environment the resolver may read.

    Returns:
        The setup. When reading raises one of ``SETUP_ERRORS`` the setup is failed
        (``failed`` True) and the API answers a ``CardError``.
    """
    try:
        entries = model_check.resolve_entries(
            claude_dir=claude_dir,
            project_dir=project_dir,
            managed_dir=managed_dir,
            shell_env=shell_env,
        )
    except SETUP_ERRORS:
        return AgentSetup(failed=True)
    return from_entries(entries)


def _scope_of(setup: AgentSetup, agent_key: str) -> AgentScope:
    if agent_key == _MAIN_KEY:
        return "main"
    if agent_key == _UNNAMED_KEY:
        return "unnamed"
    found = setup.files.get(agent_key)
    return "no_file" if found is None else found.scope


def check_agent(setup: AgentSetup, agent_key: str, runs: Sequence[Row]) -> AgentCheck:
    """Check one agent key over a range's runs.

    Args:
        setup: The ``load_setup`` result.
        agent_key: ``@main``, ``@unnamed`` or the agent type.
        runs: The agent's runs in the range as ``{run_id, model, effort, requests}``,
            the input the old ``pin_fn`` took. A main session run is one session.

    Returns:
        The scope, what is set (and why not), the status mapped as the timeline's
        Model check maps it, its reason and params, and the run split. A failed
        setup gives status None, ``set_reason`` ``read_failed`` and scope ``no_file``
        for a type (the file cannot be known), ``main`` or ``unnamed`` otherwise.
    """
    scope = _scope_of(setup, agent_key)
    if setup.failed:
        return AgentCheck(scope, None, "read_failed", None, None, {}, None, None)
    verdict = model_check.judge_agent(setup.entries, agent_key, runs, setup.catalog)
    shown: SetPair | None
    reason: SetReason | None
    if agent_key == _MAIN_KEY:
        shown, reason = setup.main, setup.main_reason
    elif agent_key == _UNNAMED_KEY or agent_key not in setup.files:
        shown, reason = None, "no_file"
    else:
        found = setup.files[agent_key]
        shown, reason = found.set, found.set_reason
    judged = verdict.status is not None
    return AgentCheck(
        scope=scope,
        set=shown,
        set_reason=reason,
        status=verdict.status,
        reason_code=verdict.reason_code,
        params=verdict.params,
        runs_as_set=verdict.runs - verdict.mismatched_runs if judged else None,
        runs_not_as_set=verdict.mismatched_runs if judged else None,
    )


def never_ran(setup: AgentSetup, ran_keys: Sequence[str]) -> list[AgentNoRuns]:
    """Return the agent files with no run in the range, sorted by name.

    Args:
        setup: The ``load_setup`` result.
        ran_keys: The agent keys that ran (``@main`` and ``@unnamed`` never match a
            file).

    Returns:
        One row per loading user or project agent file whose name is not in
        ``ran_keys``. A failed setup lists none, because it knows no files.
    """
    ran = set(ran_keys)
    return [
        AgentNoRuns(
            agent=found.name,
            scope=found.scope,
            set=found.set,
            set_reason=found.set_reason,
        )
        for name, found in sorted(setup.files.items())
        if name not in ran
    ]

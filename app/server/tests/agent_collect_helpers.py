"""Shared helpers for the agents and plugins collector tests (m4-build.md task 6).

``world`` copies one corpus case to a runnable folder and returns its context. ``run``
runs the plugins collector, then the agents collector with its handoff, as the answer
builder will. ``compare`` holds an expected.json spec to what the collectors made.
"""

import importlib.util
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import agent_files
import collect_agents
import collect_plugins
import read_scope
from models import ProblemRow, SetupItem, SetupScope, UnreadableFile
from setup_contract import Collected, SetupContext

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP_DIR = REPO_ROOT / "app" / "fixtures" / "setup"
CORPUS = SETUP_DIR / "corpus"


def _load_builder() -> Any:
    """Return the corpus builder module, the one ``test_setup_corpus`` loads too."""
    found = sys.modules.get("build_corpus")
    if found is not None:
        return found
    sys.path.insert(0, str(SETUP_DIR))
    spec = importlib.util.spec_from_file_location(
        "build_corpus", SETUP_DIR / "build_corpus.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus"] = module
    spec.loader.exec_module(module)
    return module


bc: Any = _load_builder()


class Mini:
    """A config folder, a project folder and a managed folder in a temp folder."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path.resolve()
        self.config = self.root / "home" / ".claude"
        self.project = self.root / "work" / "proj"
        self.managed = self.root / "managed"
        for folder in (self.config, self.project, self.managed):
            folder.mkdir(parents=True)
        self.ctx = SetupContext(
            project_key="proj",
            config_dir=self.config,
            home=self.root / "home",
            project_dir=self.project,
            managed_dir=self.managed,
        )

    def write(self, path: Path, text: str | bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def scope(self) -> read_scope.Scope:
        return read_scope.Scope(self.ctx)

    def find(
        self, root: Path, layer: SetupScope = "user", plugin: str | None = None
    ) -> agent_files.Found:
        return agent_files.find(self.scope(), [str(root)], layer, plugin=plugin)


def lines(*rows: str) -> str:
    """Join rows into a text with a final newline."""
    return "\n".join(rows) + "\n"


@dataclass
class World:
    """One materialized case."""

    root: Path
    lay: Any
    ctx: SetupContext


def expected(case: str) -> dict[str, Any]:
    """Return a case's expected.json."""
    return cast(
        "dict[str, Any]",
        json.loads((CORPUS / case / "expected.json").read_text("utf-8")),
    )


def context(root: Path, *, shell_env: dict[str, str] | None = None) -> SetupContext:
    """Return the ``SetupContext`` of a materialized case."""
    lay = bc.layout(root)
    meta = json.loads((root / "case.json").read_text("utf-8"))
    session = json.loads(lay.session.read_text("utf-8"))
    return SetupContext(
        project_key="proj",
        config_dir=lay.config,
        home=lay.home,
        project_dir=lay.project if meta["listed"] else None,
        managed_dir=lay.managed,
        shell_env=shell_env if shell_env is not None else session.get("shell_env", {}),
        plan=meta["plan"],
    )


def world(
    case: str,
    dest: Path,
    corpus: Path,
    *,
    shell_env: dict[str, str] | None = None,
) -> World:
    """Copy a case to ``dest`` and return it with its context."""
    root = bc.materialize(case, dest, corpus=corpus)
    return World(root=root, lay=bc.layout(root), ctx=context(root, shell_env=shell_env))


@dataclass
class Result:
    """What both collectors made for one context."""

    plugins: Collected
    agents: Collected

    def problems(self) -> list[ProblemRow]:
        return [*self.plugins.problems, *self.agents.problems]

    def unreadable(self) -> list[UnreadableFile]:
        return [*self.plugins.unreadable, *self.agents.unreadable]

    def everything(self) -> str:
        """Every answer the collectors made, as one JSON text (for masking sweeps)."""
        parts: list[object] = []
        for col in (self.plugins, self.agents):
            parts.extend(
                [
                    i.model_dump(mode="json")
                    for items in col.items.values()
                    for i in items
                ]
            )
            parts.extend(p.model_dump(mode="json") for p in col.problems)
            parts.extend(u.model_dump(mode="json") for u in col.unreadable)
        return json.dumps(parts, sort_keys=True)


def run(ctx: SetupContext, handoff: dict[str, object] | None = None) -> Result:
    """Run the plugins collector, then the agents collector with its handoff."""
    plugins = collect_plugins.COLLECTOR.read(ctx, handoff or {})
    agents = collect_agents.COLLECTOR.read(ctx, {**(handoff or {}), **plugins.handoff})
    return Result(plugins=plugins, agents=agents)


def components(col: Collected) -> list[collect_plugins.PluginComponents]:
    """Return the plugin components the plugins collector handed on."""
    return cast(
        "list[collect_plugins.PluginComponents]",
        col.handoff[collect_plugins.HANDOFF_COMPONENTS],
    )


def items_of(col: Collected, part: str) -> list[SetupItem]:
    return col.items.get(cast("Any", part), [])


# ---------------------------------------------------------------- the comparison


def _source_view(source: Any, keys: Iterable[str]) -> dict[str, Any]:
    dumped = source.model_dump(mode="json")
    return {k: dumped[k] for k in keys}


def item_errors(part: str, item: SetupItem, want: dict[str, Any]) -> list[str]:  # noqa: PLR0912
    """Return how one item differs from its expected spec."""
    errors: list[str] = []
    where = want["id"]
    for key in ("id", "key", "scope", "status"):
        if getattr(item, key) != want[key]:
            errors.append(f"{where}: {key} {getattr(item, key)!r} != {want[key]!r}")
    name_only = part == "agents"
    actual = [s for s in item.sources if s.key == "name"] if name_only else item.sources
    spec_keys = ("scope", "key", "file", "line", "status")
    got = [_source_view(s, spec_keys) for s in actual]
    wanted = [{k: s[k] for k in spec_keys} for s in want["sources"]]
    if got != wanted:
        errors.append(f"{where}: sources {got} != {wanted}")
    for a, w in zip(actual, want["sources"], strict=False):
        if "plugin" in w and a.plugin != w["plugin"]:
            errors.append(f"{where}: source plugin {a.plugin!r} != {w['plugin']!r}")
    if "effective" in want:
        eff = item.effective
        shown = (
            None
            if eff is None
            else {"value": eff.value.text if eff.value else None, "origin": eff.origin}
        )
        if shown != want["effective"]:
            errors.append(f"{where}: effective {shown} != {want['effective']}")
    if item.not_read != want.get("not_read"):
        errors.append(f"{where}: not_read {item.not_read!r}")
    facts = want.get("facts", {})
    if "ignored_fields" in facts:
        agent = item.facts.agent
        ignored = [] if agent is None else [f.name for f in agent.fields if f.ignored]
        if sorted(ignored) != sorted(facts["ignored_fields"]):
            errors.append(f"{where}: ignored fields {ignored}")
    plugin = item.facts.plugin
    for key in ("version", "orphaned_versions"):
        if key in facts and (plugin is None or getattr(plugin, key) != facts[key]):
            errors.append(f"{where}: plugin {key}")
    tail = want.get("real_path_endswith")
    if tail is not None and not (item.real_path or "").endswith(tail):
        errors.append(f"{where}: real_path {item.real_path!r}")
    return errors


def problem_view(row: ProblemRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "group": row.group,
        "code": row.code,
        "part": row.part,
        "item_id": row.item_id,
        "file": row.file,
        "line": row.line,
    }


def compare(
    part: str, col: Collected, want: dict[str, Any], problems: list[ProblemRow]
) -> list[str]:
    """Return every way a collector's answer for one part differs from expected.json."""
    errors: list[str] = []
    items = items_of(col, part)
    spec = want["parts"][part]
    wanted_ids = [i["id"] for i in spec["items"]]
    if [i.id for i in items] != wanted_ids:
        errors.append(f"item ids {[i.id for i in items]} != {wanted_ids}")
    else:
        for item, one in zip(items, spec["items"], strict=True):
            errors += item_errors(part, item, one)
    mine = {r.id: problem_view(r) for r in problems if r.part == part}
    theirs = {r["id"]: r for r in want["problems"] if r.get("part") == part}
    if mine != theirs:
        errors.append(f"problems {sorted(mine)} != {sorted(theirs)}")
        for key in mine.keys() & theirs.keys():
            if mine[key] != theirs[key]:
                errors.append(f"problem {key}: {mine[key]} != {theirs[key]}")
    got_unreadable = [
        {"file": u.file, "scope": u.scope, "reason": u.reason} for u in col.unreadable
    ]
    wanted_unreadable = spec.get("unreadable", [])
    if got_unreadable != wanted_unreadable:
        errors.append(f"unreadable {got_unreadable} != {wanted_unreadable}")
    return errors


def spy_on_reads(monkeypatch: Any, log: list[tuple[str, str]]) -> None:
    """Record every open, listdir and scandir path in ``log`` until the test ends."""
    import builtins
    import os

    real_open: Any = builtins.open
    real_os_open: Any = os.open
    real_listdir: Any = os.listdir
    real_scandir: Any = os.scandir

    def note(event: str, target: object) -> None:
        if isinstance(target, int) or target is None:
            return
        log.append((event, str(Path(os.fsdecode(cast("Any", target))).absolute())))

    def fake_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        note("open", file)
        return real_open(file, *args, **kwargs)

    def fake_os_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        note("open", path)
        return real_os_open(path, *args, **kwargs)

    def fake_listdir(path: Any = ".") -> Any:
        note("os.listdir", path)
        return real_listdir(path)

    def fake_scandir(path: Any = ".") -> Any:
        note("os.scandir", path)
        return real_scandir(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(os, "open", fake_os_open)
    monkeypatch.setattr(os, "listdir", fake_listdir)
    monkeypatch.setattr(os, "scandir", fake_scandir)

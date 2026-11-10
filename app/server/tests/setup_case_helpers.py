"""Helpers for the setup collector tests: a corpus case as a ``SetupContext``.

``bc`` is the corpus builder (``app/fixtures/setup/build_corpus.py``). ``world`` copies
a case into a folder, and ``context`` turns the copy into the ``SetupContext`` a
collector gets. ``expected`` reads a case's expected.json. ``compare`` checks a
collector's answer for the parts it owns against that file, field by field, so a
hand-written expected.json is the oracle and the collector is never its own.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from models import SetupItem, SetupPart
from setup_contract import Collected, SetupContext

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP_DIR = REPO_ROOT / "app" / "fixtures" / "setup"
CORPUS = SETUP_DIR / "corpus"


def _load_builder() -> ModuleType:
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


bc = _load_builder()

CASES = sorted(p.name for p in CORPUS.iterdir() if p.is_dir())
# The corpus keeps an unset model and effort out of expected.json for cases that have
# no settings part. The collector always makes both items (the setup map links to
# them), with origin ``default`` when nothing sets them.
ALWAYS = ("settings:model", "settings:effortLevel")


def world(case: str, dest: Path, corpus: Path) -> Path:
    """Copy a corpus case to ``dest`` and return the real path."""
    return bc.materialize(case, dest, corpus=corpus)


def context(root: Path, *, managed: bool = True) -> SetupContext:
    """Return the ``SetupContext`` of a materialized case."""
    lay = bc.layout(root)
    meta: dict[str, Any] = json.loads((root / "case.json").read_text("utf-8"))
    session: dict[str, Any] = json.loads(lay.session.read_text("utf-8"))
    return SetupContext(
        project_key="proj",
        config_dir=lay.config,
        home=lay.home,
        project_dir=lay.project if meta["listed"] else None,
        managed_dir=lay.managed if managed else None,
        shell_env=dict(session.get("shell_env") or {}),
        plan=meta["plan"],
    )


def scratch(tmp: Path, files: dict[str, str]) -> SetupContext:
    """Write files under ``tmp`` and return a context over them.

    Keys are relative paths. ``home/.claude/`` is the config folder, ``proj/`` the
    listed project and ``managed/`` the managed folder. ``tmp`` must lie outside every
    git repo.
    """
    for rel, text in files.items():
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for folder in ("home/.claude", "proj", "managed"):
        (tmp / folder).mkdir(parents=True, exist_ok=True)
    root = tmp.resolve()
    return SetupContext(
        project_key="proj",
        config_dir=root / "home" / ".claude",
        home=root / "home",
        project_dir=root / "proj",
        managed_dir=root / "managed",
    )


def expected(case: str) -> dict[str, Any]:
    """Return a case's expected.json."""
    data: dict[str, Any] = json.loads(
        (CORPUS / case / "expected.json").read_text("utf-8")
    )
    return data


def _source(src: Any) -> dict[str, Any]:
    return {
        "scope": src.scope,
        "key": src.key,
        "file": src.file,
        "line": src.line,
        "status": src.status,
    }


def item_view(item: SetupItem) -> dict[str, Any]:
    """Return the fields expected.json states for an item."""
    view: dict[str, Any] = {
        "id": item.id,
        "key": item.key,
        "scope": item.scope,
        "status": item.status,
        "sources": [_source(s) for s in item.sources],
    }
    if item.group is not None:
        view["group"] = item.group
    if item.effective is not None:
        value = item.effective.value
        view["effective"] = {
            "value": value.text if value is not None else None,
            "origin": item.effective.origin,
        }
    return view


def _wanted(item: dict[str, Any]) -> dict[str, Any]:
    """Return an expected item cut to the fields ``item_view`` makes."""
    keep = ("id", "key", "scope", "status", "group", "effective")
    view = {k: item[k] for k in keep if k in item}
    view["sources"] = [
        {k: s[k] for k in ("scope", "key", "file", "line", "status")}
        for s in item["sources"]
    ]
    return view


def compare_items(
    got: Collected, case: str, part: SetupPart
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (what the collector made, what expected.json says) for one part.

    The always-present ``settings:model`` and ``settings:effortLevel`` items that
    expected.json does not list are left out of the first list when nothing sets them.
    """
    body = expected(case)["parts"].get(part, {"items": []})
    wanted = [_wanted(i) for i in body["items"]]
    listed = {i["id"] for i in wanted}
    made = [
        item_view(i)
        for i in got.items.get(part, [])
        if not (i.id in ALWAYS and i.id not in listed and not i.sources)
    ]
    return made, wanted


def problem_view(row: Any) -> dict[str, Any]:
    """Return the fields expected.json states for a problem row."""
    return {
        "id": row.id,
        "group": row.group,
        "code": row.code,
        "part": row.part,
        "item_id": row.item_id,
        "file": row.file,
        "line": row.line,
    }


def compare_problems(
    got: Collected, case: str, parts: tuple[str, ...]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (what the collector made, what expected.json says) for these parts."""
    keep = ("id", "group", "code", "part", "item_id", "file", "line")
    wanted = [
        {k: row[k] for k in keep}
        for row in expected(case)["problems"]
        if row["part"] in parts
    ]
    return [problem_view(r) for r in got.problems if r.part in parts], wanted

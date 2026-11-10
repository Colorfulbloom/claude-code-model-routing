"""Helpers for the skills, instructions and rules collector tests (m4-build.md task 7).

``handoff`` runs the settings and plugins collectors first and hands their output on,
as the answer builder will, so a plugin skill reads the way it does in a real answer.
``instruction_view`` and ``wanted_instruction`` cut an item and an expected item to the
fields the corpus states for instruction and rules files, which the shared
``setup_case_helpers`` does not compare (``loads``, ``imports`` and ``location``).
``expected_part`` returns a case's expected items and unreadable files for one part.
"""

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import collect_instructions
import collect_plugins
import collect_settings
import collect_skills
from models import SetupItem
from setup_contract import Collected, SetupContext


def handoff(ctx: SetupContext) -> dict[str, object]:
    """Return what the settings and plugins collectors hand on for this context."""
    settings = collect_settings.COLLECTOR.read(ctx, {})
    plugins = collect_plugins.COLLECTOR.read(ctx, settings.handoff)
    return {**settings.handoff, **plugins.handoff}


def skills(ctx: SetupContext, plugins: Mapping[str, object] | None = None) -> Collected:
    """Run the skills collector. ``plugins`` replaces the real plugin handoff."""
    given = handoff(ctx) if plugins is None else {"plugins": plugins}
    return collect_skills.COLLECTOR.read(ctx, given)


def instructions(ctx: SetupContext) -> Collected:
    """Run the instructions and rules collector."""
    return collect_instructions.COLLECTOR.read(ctx, {})


def expected_part(case: str, part: str) -> tuple[list[dict[str, Any]], list[Any]]:
    """Return (expected items, expected unreadable files) of a case's part."""
    parts: dict[str, Any] = sc.expected(case)["parts"]
    body: dict[str, Any] = parts.get(part) or {}
    items: list[dict[str, Any]] = body.get("items", [])
    unreadable: list[Any] = body.get("unreadable", [])
    return items, unreadable


def instruction_view(item: SetupItem) -> dict[str, Any]:
    """Return the fields expected.json states for an instruction or rules item."""
    loads = item.loads
    imports = item.facts.instruction.imports if item.facts.instruction else []
    return {
        "id": item.id,
        "key": item.key,
        "scope": item.scope,
        "status": item.status,
        "location": item.location,
        "loads": {"kind": loads.kind, "globs": loads.globs} if loads else None,
        "imports": [
            {
                "target": i.target,
                "target_item": i.target_item,
                "depth": i.depth,
                "state": i.state,
                "line": i.line,
            }
            for i in imports
        ],
        "sources": [
            {
                "scope": s.scope,
                "key": s.key,
                "file": s.file,
                "line": s.line,
                "status": s.status,
                "location": s.location,
            }
            for s in item.sources
        ],
    }


def wanted_instruction(item: dict[str, Any]) -> dict[str, Any]:
    """Return an expected item cut to the fields ``instruction_view`` makes."""
    return {
        "id": item["id"],
        "key": item["key"],
        "scope": item["scope"],
        "status": item["status"],
        "location": item.get("location"),
        "loads": item.get("loads"),
        "imports": item.get("imports") or [],
        "sources": [
            {
                "scope": s["scope"],
                "key": s["key"],
                "file": s["file"],
                "line": s["line"],
                "status": s["status"],
                "location": s.get("location"),
            }
            for s in item["sources"]
        ],
    }


def dump(got: Collected) -> str:
    """Return everything a collector answered as one JSON text, for leak checks."""
    return json.dumps(
        {
            "items": {p: [i.model_dump() for i in v] for p, v in got.items.items()},
            "problems": [r.model_dump() for r in got.problems],
            "unreadable": [u.model_dump() for u in got.unreadable],
        }
    )

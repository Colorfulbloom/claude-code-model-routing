"""Helpers for the Hooks, MCP and masked-reader tests (m4-build.md task 8).

``chain`` runs the collectors the three parts need in ``COLLECTOR_ORDER``, handing each
one's output on, as the answer builder will. ``corpus_everything`` joins every answer
(items, problems, unreadable files, handed-on data) into one text, so a secret test
can search all of it at once. ``secrets`` and ``never`` read ``corpus/secrets.json``.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import claude_json
import collect_agents
import collect_hooks
import collect_mcp
import collect_plugins
import collect_settings
import collect_skills
import setup_items
from models import ProblemRow, SetupItem, SetupPart
from setup_contract import Collected, SetupContext

ORDER = (
    collect_settings.COLLECTOR,
    collect_plugins.COLLECTOR,
    collect_agents.COLLECTOR,
    collect_skills.COLLECTOR,
    claude_json.COLLECTOR,
    collect_hooks.COLLECTOR,
    collect_mcp.COLLECTOR,
)


def chain(ctx: SetupContext) -> dict[str, Collected]:
    """Run the collectors the hooks and MCP parts need. Returns each one's answer."""
    claude_json.clear_cache()
    answers: dict[str, Collected] = {}
    handoff: dict[str, object] = {}
    for collector in ORDER:
        got = collector.read(ctx, handoff)
        answers[collector.name] = got
        handoff.update(got.handoff)
    return answers


def items(got: dict[str, Collected], part: SetupPart) -> dict[str, SetupItem]:
    """Return a part's items by id."""
    return {i.id: i for i in got[part].items.get(part, [])}


def view(
    got: Collected, case: str, part: SetupPart
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (what the collector made, what expected.json says) for a part's items."""
    return sc.compare_items(got, case, part)


def problems(got: dict[str, Collected], parts: tuple[str, ...]) -> list[ProblemRow]:
    """Return the problem rows of the hooks, claude_json and mcp collectors, sorted."""
    rows = [
        row
        for name in ("claude_json", "hooks", "mcp")
        for row in got[name].problems
        if row.part in parts
    ]
    return setup_items.sort_problems(rows)  # sorted as the corpus lists them


def secrets() -> list[dict[str, str]]:
    """Return the corpus's planted secrets."""
    data: dict[str, Any] = json.loads((sc.CORPUS / "secrets.json").read_text("utf-8"))
    return list(data["secrets"])


def never() -> list[dict[str, str]]:
    """Return the values that must never reach any answer."""
    data: dict[str, Any] = json.loads((sc.CORPUS / "secrets.json").read_text("utf-8"))
    return list(data["never"])


def everything(got: dict[str, Collected]) -> str:
    """Return every answer of the chain as one JSON text, for a search."""
    parts: list[object] = []
    for answer in got.values():
        parts += [
            [
                i.model_dump(mode="json")
                for items_ in answer.items.values()
                for i in items_
            ],
            [p.model_dump(mode="json") for p in answer.problems],
            [u.model_dump(mode="json") for u in answer.unreadable],
            [str(t) for t in answer.touched],
        ]
    return json.dumps(parts, default=repr)

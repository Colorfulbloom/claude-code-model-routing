# ruff: noqa: E501, ANN401
"""The stress case, generated.

It has long names, 50 agents, 200 permission rules, 20 plugins and a 6-level CLAUDE.md
tree.

The expected JSON is generated with the files, so it only pins ids, order, scope,
status and line numbers. Task 10 uses the case for speed, and the corpus test checks
the counts against literals.
"""

from __future__ import annotations

from typing import Any

from corpus_types import Case, make_case
from plugin_blocks import MARKET, known_marketplaces

CFG = "home/.claude"
PRJ = "work/parent/proj"
AGENT_COUNT = 50
RULE_COUNTS = {"allow": 100, "ask": 50, "deny": 50}
# The Permissions part lists deny, ask, then allow (owner decision 5, evaluation order).
PERMISSION_ORDER = ("deny", "ask", "allow")
PLUGIN_COUNT = 20
SKILL_COUNT = 10
TREE_LEVELS = 6


def _agent(i: int) -> str:
    return f"stress-agent-with-a-deliberately-long-name-for-layout-checks-{i:02d}"


def _plugin(i: int) -> str:
    return f"stress-plugin-with-a-long-name-for-the-list-{i:02d}"


def _skill(i: int) -> str:
    return f"stress-skill-with-a-long-name-for-the-slash-menu-{i:02d}"


def _rule(kind: str, i: int) -> str:
    tool = {"allow": "Bash", "ask": "Edit", "deny": "Read"}[kind]
    return (
        f"{tool}(./a-long-directory-name-for-stress-testing/{kind}/segment-{i:03d}/**)"
    )


def _settings() -> tuple[str, dict[str, list[int]]]:
    """Return the user settings text and each rule's and plugin's line number."""
    lines = ["{", '  "model": "claude-opus-5-5",', '  "permissions": {']
    rule_lines: dict[str, list[int]] = {}
    kinds = list(RULE_COUNTS)
    for k, kind in enumerate(kinds):
        lines.append(f'    "{kind}": [')
        rule_lines[kind] = []
        for i in range(RULE_COUNTS[kind]):
            comma = "," if i < RULE_COUNTS[kind] - 1 else ""
            lines.append(f'      "{_rule(kind, i)}"{comma}')
            rule_lines[kind].append(len(lines))
        lines.append("    ]" + ("," if k < len(kinds) - 1 else ""))
    lines += ["  },", '  "enabledPlugins": {']
    rule_lines["plugins"] = []
    for i in range(PLUGIN_COUNT):
        comma = "," if i < PLUGIN_COUNT - 1 else ""
        lines.append(f'    "{_plugin(i)}@{MARKET}": true{comma}')
        rule_lines["plugins"].append(len(lines))
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n", rule_lines


def _blocks(settings: str) -> str:
    out = [f"=== {CFG}/settings.json\n", settings]
    out += [f"=== {CFG}/CLAUDE.md\n", "# User notes\nPrefer plain words.\n"]
    for i in range(AGENT_COUNT):
        out += [
            f"=== {CFG}/agents/{_agent(i)}.md\n",
            f"---\nname: {_agent(i)}\ndescription: Stress agent number {i}.\n---\nWork.\n",
        ]
    for i in range(SKILL_COUNT):
        out += [
            f"=== {CFG}/skills/{_skill(i)}/SKILL.md\n",
            f"---\nname: {_skill(i)}\ndescription: Stress skill number {i}.\n---\nWork.\n",
        ]
    out += [f"=== {PRJ}/CLAUDE.md\n", "# Proj\nTop of the tree.\n"]
    path = PRJ
    for level in range(1, TREE_LEVELS + 1):
        path += f"/level{level}"
        out += [f"=== {path}/CLAUDE.md\n", f"# Level {level}\nNested notes.\n"]
    entries = [
        f'    "{_plugin(i)}@{MARKET}": [\n'
        f'      {{"scope": "user", "installPath": "@@CONFIG@@/plugins/cache/{MARKET}/{_plugin(i)}/1.0.0", "version": "1.0.0"}}\n'
        "    ]"
        for i in range(PLUGIN_COUNT)
    ]
    installed = (
        '{\n  "version": 2,\n  "plugins": {\n' + ",\n".join(entries) + "\n  }\n}\n"
    )
    out += [f"=== {CFG}/plugins/installed_plugins.json\n", installed]
    out += [f"=== {CFG}/plugins/known_marketplaces.json\n", known_marketplaces()]
    for i in range(PLUGIN_COUNT):
        out += [
            f"=== {CFG}/plugins/cache/{MARKET}/{_plugin(i)}/1.0.0/.claude-plugin/plugin.json\n",
            f'{{\n  "name": "{_plugin(i)}",\n  "version": "1.0.0"\n}}\n',
        ]
    return "".join(out)


def _item(
    part: str, ident: str, key: str, scope: str, src: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    return {
        "id": f"{part}:{ident}",
        "key": key,
        "scope": scope,
        "status": "in_effect",
        "sources": [src],
        **extra,
    }


def _expected(rule_lines: dict[str, list[int]]) -> dict[str, Any]:
    user = "~/.claude/settings.json"
    parts: dict[str, list[dict[str, Any]]] = {}
    parts["settings"] = [
        _item(
            "settings",
            "model",
            "model",
            "user",
            {
                "scope": "user",
                "key": "model",
                "file": user,
                "line": 2,
                "status": "in_effect",
            },
            effective={"value": "claude-opus-5-5", "origin": "set"},
        )
    ]
    parts["agents"] = [
        _item(
            "agents",
            _agent(i),
            _agent(i),
            "user",
            {
                "scope": "user",
                "key": "name",
                "file": f"~/.claude/agents/{_agent(i)}.md",
                "line": 2,
                "status": "in_effect",
            },
        )
        for i in range(AGENT_COUNT)
    ]
    always = {"kind": "always", "globs": []}
    instr = [
        _item(
            "instructions",
            "~/.claude/CLAUDE.md",
            "~/.claude/CLAUDE.md",
            "user",
            {
                "scope": "user",
                "key": "file",
                "file": "~/.claude/CLAUDE.md",
                "line": None,
                "status": "in_effect",
            },
            loads=always,
        ),
        _item(
            "instructions",
            "CLAUDE.md",
            "CLAUDE.md",
            "project",
            {
                "scope": "project",
                "key": "file",
                "file": "CLAUDE.md",
                "line": None,
                "status": "in_effect",
            },
            loads=always,
        ),
    ]
    path = ""
    for level in range(1, TREE_LEVELS + 1):
        path += f"level{level}/"
        name = path + "CLAUDE.md"
        instr.append(
            _item(
                "instructions",
                name,
                name,
                "project",
                {
                    "scope": "project",
                    "key": "file",
                    "file": name,
                    "line": None,
                    "status": "in_effect",
                },
                loads={"kind": "on_demand", "globs": []},
            )
        )
    parts["instructions"] = instr
    parts["skills"] = [
        _item(
            "skills",
            _skill(i),
            _skill(i),
            "user",
            {
                "scope": "user",
                "key": "name",
                "file": f"~/.claude/skills/{_skill(i)}/SKILL.md",
                "line": 2,
                "status": "in_effect",
            },
        )
        for i in range(SKILL_COUNT)
    ]
    perms: list[dict[str, Any]] = []
    for kind in PERMISSION_ORDER:
        for i in range(RULE_COUNTS[kind]):
            rule = _rule(kind, i)
            perms.append(
                _item(
                    "permissions",
                    f"{kind}:{rule}",
                    rule,
                    "user",
                    {
                        "scope": "user",
                        "key": f"permissions.{kind}",
                        "file": user,
                        "line": rule_lines[kind][i],
                        "status": "in_effect",
                        "line_has": rule,
                    },
                    group=kind,
                )
            )
    parts["permissions"] = perms
    parts["plugins"] = [
        _item(
            "plugins",
            f"{_plugin(i)}@{MARKET}",
            f"{_plugin(i)}@{MARKET}",
            "user",
            {
                "scope": "user",
                "key": f"enabledPlugins.{_plugin(i)}@{MARKET}",
                "file": user,
                "line": rule_lines["plugins"][i],
                "status": "in_effect",
            },
            effective={"value": "enabled", "origin": "set"},
        )
        for i in range(PLUGIN_COUNT)
    ]
    return {
        "case": "stress",
        "generated": True,
        "project": {"name": "Proj", "dir": "work/parent/proj"},
        "parts": {
            name: {"items": items, "unreadable": []} for name, items in parts.items()
        },
        "problems": [],
    }


def case() -> Case:
    """Return the stress case, with generated expected JSON."""
    settings, rule_lines = _settings()
    return make_case("stress", _blocks(settings), expected=_expected(rule_lines))

# ruff: noqa: E501
"""File text of the demo setup overlay (m4-build.md section 2, "Demo setup").

The overlay sits over the demo build that ``tests/fixtures/demo/build_demo.py`` makes.
That build has ``config/`` (the Claude config folder), ``projects/<dir>/``, ``managed/``
and ``session.json``, and no separate HOME, so the masked user file lives at
``config/.claude.json`` (the config folder's own copy, the first place the reader looks).

A file named ``<name>.merge.json`` is merged into the demo's existing ``<name>.json``
(keys the demo already has win), because the demo already owns its settings files.
``@@DEMO@@`` becomes the absolute demo folder and ``@@CONFIG@@`` its config folder.
"""

from __future__ import annotations

from corpus_types import Link, dump_json, parse_blocks
from plugin_blocks import plugin_blocks

TIDE = "projects/tidewater-reporting"
EXTRA_PROJECTS = [
    {"name": "Setup empty", "dir": "projects/setup-empty"},
    {"name": "Setup broken", "dir": "projects/setup-broken"},
    {"name": "Setup large", "dir": "projects/setup-large"},
]
LARGE_AGENTS = 40
LARGE_RULES = 120
LARGE_SKILLS = 8

_RICH = f"""\
=== config/CLAUDE.md
# House notes
Prefer plain words.
=== config/skills/standup-notes/SKILL.md
---
name: standup-notes
description: Draft the standup notes from yesterday's commits.
---
Draft the notes.
=== config/settings.merge.json
{{
  "permissions": {{
    "allow": ["Bash(git status)", "Read(./docs/**)"],
    "deny": ["Read(./.env)"]
  }},
  "enabledPlugins": {{
    "routing-dashboard@bartab-demo": true,
    "hivemind@bartab-demo": true
  }},
  "hooks": {{
    "PreToolUse": [
      {{"matcher": "Bash", "hooks": [{{"type": "command", "command": "python3 ~/bin/check-bash.py --token sk-ant-api03-FAKEDEMOHOOK0000005"}}]}}
    ]
  }}
}}
=== config/.claude.json
{{
  "numStartups": 7,
  "mcpServers": {{
    "notes": {{
      "type": "sse",
      "url": "https://notes.example.test/sse",
      "headers": {{"X-Api-Key": "fake-xapikey-DEMO0123456789"}}
    }}
  }},
  "projects": {{
    "@@DEMO@@/{TIDE}": {{
      "mcpServers": {{
        "scratch": {{"command": "node", "args": ["scratch.js", "--password=hunter2demo"]}}
      }}
    }}
  }}
}}
=== {TIDE}/CLAUDE.md
# Tidewater reporting

Quarter-close rules live in @docs/close.md and nowhere else.
=== {TIDE}/docs/close.md
# Close
See @glossary.md for the terms.
=== {TIDE}/docs/glossary.md
# Glossary
Accrual means booked before it is paid.
=== {TIDE}/.mcp.json
{{
  "mcpServers": {{
    "ledger": {{
      "command": "npx",
      "args": ["-y", "ledger-mcp"],
      "env": {{"LEDGER_API_KEY": "sk-live-FAKEDEMOENV0000006"}}
    }},
    "files": {{
      "type": "http",
      "url": "https://files.example.test/mcp"
    }}
  }}
}}
=== {TIDE}/.claude/skills/quarter-close/SKILL.md
---
name: quarter-close
description: Walk through the quarter-close checklist.
---
Walk the checklist.
=== {TIDE}/.claude/settings.merge.json
{{
  "permissions": {{
    "allow": ["Bash(npm test)"]
  }},
  "enabledMcpjsonServers": ["ledger"],
  "hooks": {{
    "PostToolUse": [
      {{"matcher": "Edit|Write", "hooks": [{{"type": "command", "command": "bash ./scripts/format.sh"}}]}}
    ]
  }}
}}
"""

_EMPTY = """\
=== projects/setup-empty/notes.txt
A project with no Claude files at all.
"""

_BROKEN = """\
=== projects/setup-broken/.claude/settings.local.json
{
  "effortLevel": "high",
  "model" "claude-opus-5-5"
}
=== projects/setup-broken/.mcp.json
{
  "mcpServers": {
    "empty": {"env": {"A": "b"}}
  }
}
=== projects/setup-broken/CLAUDE.md
# Broken setup

Start with @notes/missing.md for the details.
=== projects/setup-broken/.claude/agents/nofront.md
Just text, no front matter.
"""


def _large() -> str:
    base = "projects/setup-large"
    out = []
    lines = ["{", '  "permissions": {', '    "allow": [']
    for i in range(LARGE_RULES):
        comma = "," if i < LARGE_RULES - 1 else ""
        lines.append(
            f'      "Bash(a-long-command-name-for-the-large-demo-{i:03d}:*)"{comma}'
        )
    lines += ["    ]", "  }", "}"]
    out += [f"=== {base}/.claude/settings.json\n", "\n".join(lines) + "\n"]
    for i in range(LARGE_AGENTS):
        name = f"large-demo-agent-{i:02d}"
        out += [
            f"=== {base}/.claude/agents/{name}.md\n",
            f"---\nname: {name}\ndescription: Demo agent number {i}.\nmodel: claude-sonnet-5-5\n---\nWork.\n",
        ]
    for i in range(LARGE_SKILLS):
        name = f"large-demo-skill-{i:02d}"
        out += [
            f"=== {base}/.claude/skills/{name}/SKILL.md\n",
            f"---\nname: {name}\ndescription: Demo skill number {i}.\n---\nWork.\n",
        ]
    out += [f"=== {base}/CLAUDE.md\n", "# Large demo\nTop of the tree.\n"]
    path = base
    for level in range(1, 5):
        path += f"/area{level}"
        out += [f"=== {path}/CLAUDE.md\n", f"# Area {level}\nNested notes.\n"]
    return "".join(out)


def overlay_files() -> dict[str, str | Link]:
    """Return the overlay as relative path to text, in write order.

    Includes ``extra-projects.json``, which ``apply_demo_overlay`` reads to append the
    three extra listed projects.
    """
    files = parse_blocks(_RICH + plugin_blocks("config") + _EMPTY + _BROKEN + _large())
    files["extra-projects.json"] = dump_json({"projects": EXTRA_PROJECTS})
    return files


OVERLAY_SECRETS: list[dict[str, object]] = [
    {
        "value": "sk-ant-api03-FAKEDEMOHOOK0000005",
        "kind": "sk_prefix_in_hook_command",
        "case": "demo-overlay",
        "file": "config/settings.merge.json",
    },
    {
        "value": "fake-xapikey-DEMO0123456789",
        "kind": "secret_named_header",
        "case": "demo-overlay",
        "file": "config/.claude.json",
    },
    {
        "value": "hunter2demo",
        "kind": "secret_named_flag_equals_in_args",
        "case": "demo-overlay",
        "file": "config/.claude.json",
    },
    {
        "value": "sk-live-FAKEDEMOENV0000006",
        "kind": "sk_prefix_in_mcp_env",
        "case": "demo-overlay",
        "file": f"{TIDE}/.mcp.json",
    },
]

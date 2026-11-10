# ruff: noqa: E501
"""The broken twins and the scope cases. Their expected.json files are by hand.

Every file is made up. Line numbers in the blocks are what expected.json points at, so
change a block and its expected.json together.
"""

from __future__ import annotations

from corpus_types import Case, make_case

CFG = "home/.claude"
PRJ = "work/parent/proj"

_BROKEN_SETTINGS = f"""\
=== {CFG}/settings.json
{{
  "model": "claude-opus-5-5",
  "permissions": {{
    "allow": [
      "Bash(git status"
    ]
  }},
  "outputStyle": "ghost"
}}
=== {PRJ}/.claude/settings.json
[]
=== {PRJ}/.claude/settings.local.json
{{
  "effortLevel": "high",
  "model" "claude-opus-5-5"
}}
=== managed/managed-settings.json
{{"model": }}
"""

_BROKEN_AGENTS = f"""\
=== {CFG}/agents/good.md
---
name: good
description: A control agent that loads.
---
Do the work.
=== {CFG}/agents/nofront.md
Just text, no front matter.
=== {CFG}/agents/nodesc.md
---
name: nodesc
---
Body.
=== {CFG}/agents/notes.txt
The agents folder holds .md files only.
=== {CFG}/agents/dup-a.md
---
name: twin
description: One of two files with this name.
---
First.
=== {CFG}/agents/dup-b.md
---
name: twin
description: The other file with this name.
---
Second.
=== {CFG}/agents/folded.md
---
name: folded
description: >
  Reviews code
  when asked.
model: claude-sonnet-5-5
---
Review it.
"""

_AGENTS_CAPPED = f"""\
=== {CFG}/settings.json
{{
  "maxEffortLevel": "medium",
  "env": {{
    "CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-5-5",
    "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"
  }}
}}
=== {CFG}/agents/mixed.md
---
name: mixed
description: Pins a model the force variable ignores and an effort the cap lowers.
model: claude-opus-5-5
effort: high
---
Do the work.
=== {CFG}/agents/plain.md
---
name: plain
description: Pins nothing, so no cap lowers it.
---
Do the work.
"""

_BROKEN_PLUGINS = f"""\
=== {CFG}/settings.json
{{
  "enabledPlugins": {{
    "alpha@bartab-demo": true,
    "beta@bartab-demo": true,
    "gamma@bartab-demo": true,
    "delta@bartab-demo": true
  }}
}}
=== {CFG}/plugins/installed_plugins.json
{{
  "version": 2,
  "plugins": {{
    "alpha@bartab-demo": [
      {{"scope": "user", "installPath": "@@CONFIG@@/plugins/cache/bartab-demo/alpha/1.0.0", "version": "1.0.0"}}
    ],
    "gamma@bartab-demo": [
      {{"scope": "user", "installPath": "@@CONFIG@@/plugins/cache/bartab-demo/gamma/1.0.0", "version": "1.0.0"}}
    ],
    "delta@bartab-demo": [
      {{"scope": "user", "installPath": "@@HOME@@/elsewhere/delta", "version": "1.0.0"}}
    ]
  }}
}}
=== {CFG}/plugins/known_marketplaces.json
["bartab-demo"]
=== {CFG}/plugins/cache/bartab-demo/alpha/1.0.0/.claude-plugin/plugin.json
{{
  "name": "alpha",
  "version": "1.0.0"
}}
=== {CFG}/plugins/cache/bartab-demo/alpha/0.9.0/.claude-plugin/plugin.json
{{
  "name": "alpha",
  "version": "0.9.0"
}}
=== {CFG}/plugins/cache/bartab-demo/alpha/0.9.0/.orphaned_at
1761000000000
=== {CFG}/plugins/cache/bartab-demo/gamma/1.0.0/.claude-plugin/plugin.json
{{"name": "gamma" "version": "1.0.0"}}
=== home/elsewhere/delta/.claude-plugin/plugin.json
{{
  "name": "delta",
  "version": "1.0.0"
}}
"""

_BROKEN_SKILLS = f"""\
=== {CFG}/skills/good/SKILL.md
---
name: good
description: A control skill that loads.
---
Do the work.
=== {CFG}/skills/emptydir/notes.txt
This folder has no SKILL.md.
=== {CFG}/skills/badfm/SKILL.md
---
name: badfm
description: "unterminated
---
Body.
=== {CFG}/skills/dup1/SKILL.md
---
name: shared
description: First of two skills with one name.
---
Body.
=== {CFG}/skills/dup2/SKILL.md
---
name: shared
description: Second of two skills with one name.
---
Body.
"""

_BROKEN_INSTRUCTIONS = f"""\
=== {PRJ}/CLAUDE.md
# Imports

Start with @notes/a.md for the cycle.
Then @notes/missing.md is a missing target.
Then @../outside.md sits outside the roots.
Then @notes/h1.md starts a long chain.
=== {PRJ}/notes/a.md
# A
See @b.md next.
=== {PRJ}/notes/b.md
# B
See @a.md back.
=== {PRJ}/notes/h1.md
# H1
See @h2.md next.
=== {PRJ}/notes/h2.md
# H2
See @h3.md next.
=== {PRJ}/notes/h3.md
# H3
See @h4.md next.
=== {PRJ}/notes/h4.md
# H4
See @h5.md next.
=== {PRJ}/notes/h5.md
# H5
Too far to load.
=== work/parent/outside.md
# Outside
Never read.
=== {PRJ}/.claude/rules/bad.md
---
paths: [unclosed
---
Body.
"""

_BROKEN_HOOKS = f"""\
=== {CFG}/settings.json
{{
  "disableAllHooks": true,
  "hooks": {{
    "NotAnEvent": [
      {{"hooks": [{{"type": "command", "command": "echo unknown"}}]}}
    ],
    "PreToolUse": [
      {{"matcher": "Bash", "hooks": ["just a string"]}}
    ],
    "Stop": [
      {{"hooks": [{{"type": "command", "command": "echo done"}}]}}
    ]
  }}
}}
=== managed/managed-settings.json
{{
  "allowManagedHooksOnly": true
}}
"""

_BROKEN_MCP = f"""\
=== {PRJ}/.claude/settings.json
{{
  "enableAllProjectMcpServers": true
}}
=== {PRJ}/.mcp.json
{{
  "mcpServers": {{
    "empty": {{"env": {{"A": "b"}}}},
    "typeless": {{"url": "https://api.example.test/mcp"}},
    "templated": {{"command": "node", "args": ["${{MCP_TOKEN_FILE}}"]}},
    "fine": {{"command": "node", "args": ["ok.js"]}}
  }}
}}
=== managed/managed-mcp.json
{{"mcpServers": {{"x" }}}}
"""

_BROKEN_CLAUDE_JSON = """\
=== home/.claude.json
{"mcpServers": {"notes" "x"}}
"""

_BROKEN_CLAUDE_JSON_ENTRY = """\
=== home/.claude.json
{
  "mcpServers": {
    "notes": {"command": "node", "args": ["notes.js"]}
  },
  "projects": {
    "@@PROJECT@@": "not an object"
  }
}
"""

_SCOPE_SYMLINK = f"""\
=== {CFG}/agents/local.md
---
name: local
description: A plain agent file inside the config folder.
---
Local.
=== {CFG}/agents/linked.md -> ../../../outside/linked-agent.md
=== outside/linked-agent.md
---
name: linked
description: A single file that lives outside every root.
---
Linked.
=== {CFG}/skills/ext -> ../../../outside/skills-dir
=== outside/skills-dir/SKILL.md
---
name: ext
description: A skill folder that lives outside every root.
---
Never loaded.
"""

_SCOPE_UNLISTED = f"""\
=== {CFG}/settings.json
{{
  "model": "claude-sonnet-5-5"
}}
=== {CFG}/CLAUDE.md
# User notes
Prefer plain words.
=== {PRJ}/.claude/settings.json
{{
  "model": "claude-haiku-5-5"
}}
=== {PRJ}/CLAUDE.md
# Unlisted project
Never read.
=== {PRJ}/.claude/agents/hidden.md
---
name: hidden
description: Lives in an unlisted project.
---
Never read.
"""

_SCOPE_MEMORY = f"""\
=== {CFG}/settings.json
{{
  "model": "claude-sonnet-5-5"
}}
=== {CFG}/projects/x/memory/MEMORY.md
MEMORY-SENTINEL-DO-NOT-READ
=== {PRJ}/CLAUDE.md
# Proj
Plain notes.
"""

_SCOPE_ANCESTORS = f"""\
=== work/parent/CLAUDE.md
# Parent
Rules for every project in this repo.
=== work/parent/CLAUDE.local.md
# Parent local
Personal notes for this repo.
=== work/parent/.claude/settings.local.json
{{
  "env": {{
    "REPO_FLAG": "1"
  }}
}}
=== work/parent/.claude/settings.json
{{
  "model": "claude-haiku-5-5"
}}
=== {PRJ}/CLAUDE.md
# Proj
Plain notes.
"""


def cases() -> list[Case]:
    """Return the broken twins and the scope cases."""
    return [
        make_case("broken-settings", _BROKEN_SETTINGS),
        make_case("broken-agents", _BROKEN_AGENTS),
        make_case("agents-capped", _AGENTS_CAPPED),
        make_case("broken-plugins", _BROKEN_PLUGINS),
        make_case("broken-skills", _BROKEN_SKILLS),
        make_case("broken-instructions", _BROKEN_INSTRUCTIONS),
        make_case("broken-hooks", _BROKEN_HOOKS),
        make_case("broken-mcp", _BROKEN_MCP),
        make_case("broken-claude-json", _BROKEN_CLAUDE_JSON),
        make_case("broken-claude-json-entry", _BROKEN_CLAUDE_JSON_ENTRY),
        make_case("scope-symlink", _SCOPE_SYMLINK),
        make_case("scope-unlisted", _SCOPE_UNLISTED, meta={"listed": False}),
        make_case("scope-memory", _SCOPE_MEMORY),
        make_case("scope-ancestors", _SCOPE_ANCESTORS, meta={"git_root": True}),
    ]

# ruff: noqa: E501, ANN401, PLR0913, PLR0917
"""The complex case: every part at every scope the files can reach.

The files are written as blocks, so the line numbers in the expected JSON can be read
off the text. The expected JSON is built here from explicit item calls, not derived
from the files, and ``test_setup_corpus.py`` also checks a hand-picked subset against
literals (the generator is not its own oracle, plan.md section 8).
"""

from __future__ import annotations

from typing import Any

from corpus_types import Case, make_case
from plugin_blocks import plugin_blocks

CFG = "home/.claude"
PRJ = "work/parent/proj"
RD = "~/.claude/plugins/cache/bartab-demo/routing-dashboard/0.1.7"
HM = "~/.claude/plugins/cache/bartab-demo/hivemind/0.1.3"

_FILES = """\
=== managed/managed-settings.json
{
  "model": "claude-sonnet-5-5",
  "env": {
    "ORG_POLICY": "strict"
  },
  "permissions": {
    "deny": [
      "Bash(curl:*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash /opt/policy/audit.sh"}]}
    ]
  }
}
=== managed/managed-settings.d/10-extra.json
{
  "env": {
    "ORG_REGION": "eu"
  }
}
=== managed/managed-mcp.json
{
  "mcpServers": {
    "corp-wiki": {"type": "http", "url": "https://wiki.example.test/mcp", "headers": {"Authorization": "Bearer FAKECORPBEARER0123456789abcdef"}}
  }
}
=== managed/CLAUDE.md
# Policy
Follow the house rules.
=== managed/.claude/skills/audit/SKILL.md
---
name: audit
description: Audit the change against the house rules.
---
Audit it.
=== managed/.claude/agents/policy.md
---
name: policy
description: Checks a change against the house policy.
model: claude-sonnet-5-5
---
Check it.
=== managed/.claude/output-styles/house.md
---
name: house
description: The house voice.
---
Write in the house voice.
=== home/.claude/settings.json
{
  "model": "claude-opus-5-5",
  "effortLevel": "high",
  "env": {
    "BASH_DEFAULT_TIMEOUT_MS": "60000"
  },
  "permissions": {
    "allow": [
      "Bash(git status)"
    ],
    "ask": [
      "Bash(git push:*)"
    ],
    "defaultMode": "acceptEdits",
    "additionalDirectories": ["../shared-notes"]
  },
  "outputStyle": "terse",
  "enabledPlugins": {
    "routing-dashboard@bartab-demo": true,
    "hivemind@bartab-demo": true
  },
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 ~/bin/check-bash.py --api-key sk-ant-api03-FAKEHOOKSECRET000002"}]}
    ]
  }
}
=== home/.claude/CLAUDE.md
# User notes
Prefer plain words.
=== home/.claude/rules/style.md
# Style
Short words win.
=== home/.claude/agents/scout.md
---
name: scout
description: User scout. Searches code and reports.
model: claude-haiku-5-5
---
Search.
=== home/.claude/agents/reviewer.md
---
name: reviewer
description: Reviews a diff.
model: claude-sonnet-5-5
effort: medium
---
Review it.
=== home/.claude/skills/tidy/SKILL.md
---
name: tidy
description: Tidy up a messy file.
---
Tidy the file.
=== home/.claude/commands/ship.md
---
description: Ship the release.
---
Ship it.
=== home/.claude/output-styles/terse.md
---
name: terse
description: Short answers, no preamble.
---
Answer in as few words as possible.
=== home/.claude.json
{
  "numStartups": 40,
  "mcpServers": {
    "notes": {
      "type": "sse",
      "url": "https://admin:hunter2complexpass@notes.example.test/sse",
      "headers": {"X-Api-Key": "fake-xapikey-COMPLEX0123456789"}
    }
  },
  "projects": {
    "@@PROJECT@@": {
      "mcpServers": {
        "scratch": {
          "command": "node",
          "args": ["scratch.js"],
          "env": {"SCRATCH_TOKEN": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb21wbGV4In0.FAKECOMPLEXSIGNATURE0123456789"}
        }
      }
    }
  }
}
=== work/parent/CLAUDE.md
# Parent
Rules for every project in this repo.
=== work/parent/CLAUDE.local.md
# Parent local
Personal notes for this repo.
=== work/parent/.claude/settings.local.json
{
  "env": {
    "REPO_FLAG": "1"
  }
}
=== work/parent/proj/.claude/settings.json
{
  "effortLevel": "medium",
  "permissions": {
    "allow": [
      "Bash(npm test)"
    ]
  },
  "enabledPlugins": {
    "hivemind@bartab-demo": true
  },
  "hooks": {
    "PostToolUse": [
      {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "bash ./scripts/format.sh"}]}
    ]
  }
}
=== work/parent/proj/.claude/settings.local.json
{
  "outputStyle": "review-voice",
  "enabledMcpjsonServers": ["docs"],
  "permissions": {
    "deny": [
      "Read(./.env.local)"
    ]
  },
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command", "command": "echo local-start"}]}
    ]
  }
}
=== work/parent/proj/.mcp.json
{
  "mcpServers": {
    "docs": {
      "command": "npx",
      "args": ["-y", "docs-mcp", "--secret", "FAKECOMPLEXSECRETFLAG0000004"],
      "env": {"DOCS_API_KEY": "sk-live-FAKECOMPLEXENV0000003"}
    }
  }
}
=== work/parent/proj/CLAUDE.md
# Proj

Read @docs/guide.md first.
=== work/parent/proj/docs/guide.md
# Guide
Keep it plain.
=== work/parent/proj/.claude/CLAUDE.md
# Project folder notes
Second project file.
=== work/parent/proj/CLAUDE.local.md
# Local notes
Personal.
=== work/parent/proj/packages/web/CLAUDE.md
# Web package
Loads on demand.
=== work/parent/proj/.claude/rules/review.md
---
paths:
  - "src/**/*.ts"
---
Review the diff for clarity.
=== work/parent/proj/.claude/rules/always.md
# Always
Loaded at launch.
=== work/parent/proj/.claude/skills/release-check/SKILL.md
---
name: release-check
description: Check the release notes before a tag.
allowed-tools: Read, Grep
---
Read the notes and list gaps.
=== work/parent/proj/packages/web/.claude/skills/lint/SKILL.md
---
name: lint
description: Lint the web package.
---
Lint it.
=== work/parent/proj/.claude/commands/tidy.md
---
description: Project command named like the user skill.
---
Tidy.
=== work/parent/proj/.claude/agents/builder.md
---
name: builder
description: Builds the change.
model: claude-sonnet-5-5
---
Build it.
=== work/parent/proj/.claude/agents/reviewer.md
---
name: reviewer
description: Reviews a diff for this project.
model: claude-sonnet-5-5
effort: high
---
Review it.
=== work/parent/proj/.claude/output-styles/review-voice.md
---
name: review-voice
description: Voice for reviews.
---
Be exact.
"""

COMPLEX_SECRETS: list[dict[str, object]] = [
    {
        "value": "sk-ant-api03-FAKEHOOKSECRET000002",
        "kind": "sk_prefix_in_hook_command",
        "case": "complex",
        "file": "home/.claude/settings.json",
    },
    {
        "value": "FAKECORPBEARER0123456789abcdef",
        "kind": "bearer_header",
        "case": "complex",
        "file": "managed/managed-mcp.json",
    },
    {
        "value": "FAKECOMPLEXSECRETFLAG0000004",
        "kind": "secret_named_flag_in_args",
        "case": "complex",
        "file": "work/parent/proj/.mcp.json",
    },
    {
        "value": "sk-live-FAKECOMPLEXENV0000003",
        "kind": "sk_prefix_in_mcp_env",
        "case": "complex",
        "file": "work/parent/proj/.mcp.json",
    },
    {
        "value": "hunter2complexpass",
        "kind": "url_userinfo",
        "case": "complex",
        "file": "home/.claude.json",
    },
    {
        "value": "fake-xapikey-COMPLEX0123456789",
        "kind": "secret_named_header",
        "case": "complex",
        "file": "home/.claude.json",
    },
    {
        "value": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb21wbGV4In0.FAKECOMPLEXSIGNATURE0123456789",
        "kind": "jwt_in_env",
        "case": "complex",
        "file": "home/.claude.json",
    },
]


def src(
    scope: str,
    key: str,
    file: str,
    line: int | None,
    status: str = "in_effect",
    **extra: Any,
) -> dict[str, Any]:
    """Return one expected source."""
    return {
        "scope": scope,
        "key": key,
        "file": file,
        "line": line,
        "status": status,
        **extra,
    }


def item(
    part: str,
    ident: str,
    key: str,
    scope: str,
    sources: list[dict[str, Any]],
    status: str = "in_effect",
    **extra: Any,
) -> dict[str, Any]:
    """Return one expected item. ``extra`` holds effective, group, loads and so on."""
    return {
        "id": f"{part}:{ident}",
        "key": key,
        "scope": scope,
        "status": status,
        "sources": sources,
        **extra,
    }


def _eff(value: str, origin: str = "set") -> dict[str, str]:
    return {"value": value, "origin": origin}


def _expected() -> dict[str, Any]:
    settings = [
        item(
            "settings",
            "effortLevel",
            "effortLevel",
            "project",
            [
                src("project", "effortLevel", ".claude/settings.json", 2),
                src("user", "effortLevel", "~/.claude/settings.json", 3, "overridden"),
            ],
            effective=_eff("medium"),
        ),
        item(
            "settings",
            "env.BASH_DEFAULT_TIMEOUT_MS",
            "env.BASH_DEFAULT_TIMEOUT_MS",
            "user",
            [src("user", "env.BASH_DEFAULT_TIMEOUT_MS", "~/.claude/settings.json", 5)],
            effective=_eff("60000"),
        ),
        item(
            "settings",
            "env.ORG_POLICY",
            "env.ORG_POLICY",
            "managed",
            [src("managed", "env.ORG_POLICY", "managed/managed-settings.json", 4)],
            effective=_eff("strict"),
        ),
        item(
            "settings",
            "env.ORG_REGION",
            "env.ORG_REGION",
            "managed",
            [
                src(
                    "managed",
                    "env.ORG_REGION",
                    "managed/managed-settings.d/10-extra.json",
                    3,
                )
            ],
            effective=_eff("eu"),
        ),
        item(
            "settings",
            "env.REPO_FLAG",
            "env.REPO_FLAG",
            "project_local",
            [
                src(
                    "project_local",
                    "env.REPO_FLAG",
                    "../.claude/settings.local.json",
                    3,
                )
            ],
            effective=_eff("1"),
        ),
        item(
            "settings",
            "model",
            "model",
            "managed",
            [
                src("managed", "model", "managed/managed-settings.json", 2),
                src("user", "model", "~/.claude/settings.json", 2, "overridden"),
            ],
            effective=_eff("claude-sonnet-5-5"),
        ),
    ]
    agents = [
        item(
            "agents",
            "builder",
            "builder",
            "project",
            [src("project", "name", ".claude/agents/builder.md", 2)],
        ),
        item(
            "agents",
            "policy",
            "policy",
            "managed",
            [src("managed", "name", "managed/.claude/agents/policy.md", 2)],
        ),
        item(
            "agents",
            "reviewer",
            "reviewer",
            "project",
            [
                src("project", "name", ".claude/agents/reviewer.md", 2),
                src("user", "name", "~/.claude/agents/reviewer.md", 2, "overridden"),
            ],
        ),
        item(
            "agents",
            "routing-dashboard:scout",
            "scout",
            "plugin",
            [
                src(
                    "plugin",
                    "name",
                    f"{RD}/agents/scout.md",
                    2,
                    plugin="routing-dashboard",
                )
            ],
            facts={"ignored_fields": ["hooks", "permissionMode"]},
        ),
        item(
            "agents",
            "scout",
            "scout",
            "user",
            [src("user", "name", "~/.claude/agents/scout.md", 2)],
        ),
    ]
    always = {"kind": "always", "globs": []}
    on_demand = {"kind": "on_demand", "globs": []}
    instr = [
        item(
            "instructions",
            "managed/CLAUDE.md",
            "managed/CLAUDE.md",
            "managed",
            [src("managed", "file", "managed/CLAUDE.md", None)],
            loads=always,
        ),
        item(
            "instructions",
            "~/.claude/CLAUDE.md",
            "~/.claude/CLAUDE.md",
            "user",
            [src("user", "file", "~/.claude/CLAUDE.md", None)],
            loads=always,
        ),
        item(
            "instructions",
            "../CLAUDE.md",
            "../CLAUDE.md",
            "project",
            [src("project", "file", "../CLAUDE.md", None, location="parent")],
            loads=always,
            location="parent",
        ),
        item(
            "instructions",
            "../CLAUDE.local.md",
            "../CLAUDE.local.md",
            "project_local",
            [
                src(
                    "project_local",
                    "file",
                    "../CLAUDE.local.md",
                    None,
                    location="parent",
                )
            ],
            loads=always,
            location="parent",
        ),
        item(
            "instructions",
            "CLAUDE.md",
            "CLAUDE.md",
            "project",
            [src("project", "file", "CLAUDE.md", None)],
            loads=always,
            imports=[
                {
                    "target": "docs/guide.md",
                    "target_item": "instructions:docs/guide.md",
                    "depth": 1,
                    "state": "read",
                    "line": 3,
                }
            ],
        ),
        item(
            "instructions",
            "docs/guide.md",
            "docs/guide.md",
            "project",
            [src("project", "file", "docs/guide.md", None)],
            loads=always,
        ),
        item(
            "instructions",
            ".claude/CLAUDE.md",
            ".claude/CLAUDE.md",
            "project",
            [src("project", "file", ".claude/CLAUDE.md", None)],
            loads=always,
        ),
        item(
            "instructions",
            "CLAUDE.local.md",
            "CLAUDE.local.md",
            "project_local",
            [src("project_local", "file", "CLAUDE.local.md", None)],
            loads=always,
        ),
        item(
            "instructions",
            "packages/web/CLAUDE.md",
            "packages/web/CLAUDE.md",
            "project",
            [src("project", "file", "packages/web/CLAUDE.md", None)],
            loads=on_demand,
        ),
    ]
    rules = [
        item(
            "rules",
            "~/.claude/rules/style.md",
            "~/.claude/rules/style.md",
            "user",
            [src("user", "file", "~/.claude/rules/style.md", None)],
            loads=always,
        ),
        item(
            "rules",
            ".claude/rules/always.md",
            ".claude/rules/always.md",
            "project",
            [src("project", "file", ".claude/rules/always.md", None)],
            loads=always,
        ),
        item(
            "rules",
            ".claude/rules/review.md",
            ".claude/rules/review.md",
            "project",
            [src("project", "paths", ".claude/rules/review.md", 2)],
            loads={"kind": "on_demand", "globs": ["src/**/*.ts"]},
        ),
    ]
    skills = [
        item(
            "skills",
            "audit",
            "audit",
            "managed",
            [src("managed", "name", "managed/.claude/skills/audit/SKILL.md", 2)],
        ),
        item(
            "skills",
            "lint",
            "lint",
            "project",
            [src("project", "name", "packages/web/.claude/skills/lint/SKILL.md", 2)],
        ),
        item(
            "skills",
            "release-check",
            "release-check",
            "project",
            [src("project", "name", ".claude/skills/release-check/SKILL.md", 2)],
        ),
        item(
            "skills",
            "routing-dashboard:dashboard",
            "dashboard",
            "plugin",
            [
                src(
                    "plugin",
                    "name",
                    f"{RD}/skills/dashboard/SKILL.md",
                    2,
                    plugin="routing-dashboard",
                )
            ],
        ),
        item(
            "skills",
            "ship",
            "ship",
            "user",
            [src("user", "description", "~/.claude/commands/ship.md", 2)],
        ),
        item(
            "skills",
            "tidy",
            "tidy",
            "user",
            [
                src("user", "name", "~/.claude/skills/tidy/SKILL.md", 2),
                src(
                    "project",
                    "description",
                    ".claude/commands/tidy.md",
                    2,
                    "overridden",
                ),
            ],
        ),
    ]
    hooks = [
        item(
            "hooks",
            "SessionStart:*:0",
            "SessionStart",
            "project_local",
            [
                src(
                    "project_local",
                    "hooks.SessionStart",
                    ".claude/settings.local.json",
                    11,
                    line_has="command",
                )
            ],
            group="SessionStart",
        ),
        item(
            "hooks",
            "PreToolUse:Bash:0",
            "PreToolUse",
            "managed",
            [
                src(
                    "managed",
                    "hooks.PreToolUse",
                    "managed/managed-settings.json",
                    13,
                    line_has="command",
                )
            ],
            group="PreToolUse",
        ),
        item(
            "hooks",
            "PreToolUse:Bash:1",
            "PreToolUse",
            "user",
            [
                src(
                    "user",
                    "hooks.PreToolUse",
                    "~/.claude/settings.json",
                    24,
                    line_has="command",
                )
            ],
            group="PreToolUse",
        ),
        item(
            "hooks",
            "PreToolUse:Bash:2",
            "PreToolUse",
            "plugin",
            [
                src(
                    "plugin",
                    "hooks.PreToolUse",
                    f"{HM}/hooks/hooks.json",
                    4,
                    line_has="command",
                    plugin="hivemind",
                )
            ],
            group="PreToolUse",
        ),
        item(
            "hooks",
            "PostToolUse:Edit|Write:0",
            "PostToolUse",
            "project",
            [
                src(
                    "project",
                    "hooks.PostToolUse",
                    ".claude/settings.json",
                    13,
                    line_has="command",
                )
            ],
            group="PostToolUse",
        ),
    ]
    perms = [
        item(
            "permissions",
            "allow:Bash(npm test)",
            "Bash(npm test)",
            "project",
            [
                src(
                    "project",
                    "permissions.allow",
                    ".claude/settings.json",
                    5,
                    line_has="Bash(npm test)",
                )
            ],
            group="allow",
        ),
        item(
            "permissions",
            "allow:Bash(git status)",
            "Bash(git status)",
            "user",
            [
                src(
                    "user",
                    "permissions.allow",
                    "~/.claude/settings.json",
                    9,
                    line_has="Bash(git status)",
                )
            ],
            group="allow",
        ),
        item(
            "permissions",
            "ask:Bash(git push:*)",
            "Bash(git push:*)",
            "user",
            [
                src(
                    "user",
                    "permissions.ask",
                    "~/.claude/settings.json",
                    12,
                    line_has="Bash(git push:*)",
                )
            ],
            group="ask",
        ),
        item(
            "permissions",
            "deny:Bash(curl:*)",
            "Bash(curl:*)",
            "managed",
            [
                src(
                    "managed",
                    "permissions.deny",
                    "managed/managed-settings.json",
                    8,
                    line_has="Bash(curl:*)",
                )
            ],
            group="deny",
        ),
        item(
            "permissions",
            "deny:Read(./.env.local)",
            "Read(./.env.local)",
            "project_local",
            [
                src(
                    "project_local",
                    "permissions.deny",
                    ".claude/settings.local.json",
                    6,
                    line_has="Read(./.env.local)",
                )
            ],
            group="deny",
        ),
        item(
            "permissions",
            "defaultMode",
            "defaultMode",
            "user",
            [src("user", "permissions.defaultMode", "~/.claude/settings.json", 14)],
            effective=_eff("acceptEdits"),
            group="default_mode",
        ),
        item(
            "permissions",
            "directory:../shared-notes",
            "../shared-notes",
            "user",
            [
                src(
                    "user",
                    "permissions.additionalDirectories",
                    "~/.claude/settings.json",
                    15,
                    line_has="../shared-notes",
                )
            ],
            group="directory",
        ),
    ]
    # The part lists deny, ask, then allow (owner decision 5); a stable sort keeps the
    # order inside each kind.
    perms.sort(key=lambda p: {"deny": 0, "ask": 1, "allow": 2}.get(p["group"], 3))
    mcp = [
        item(
            "mcp",
            "corp-wiki",
            "corp-wiki",
            "managed",
            [src("managed", "mcpServers.corp-wiki", "managed/managed-mcp.json", 3)],
        ),
        item(
            "mcp",
            "docs",
            "docs",
            "project",
            [src("project", "mcpServers.docs", ".mcp.json", 3)],
        ),
        item(
            "mcp",
            "notes",
            "notes",
            "user",
            [src("user", "mcpServers.notes", "~/.claude.json", 4)],
        ),
        item(
            "mcp",
            "routing-dashboard:dash-metrics",
            "dash-metrics",
            "plugin",
            [
                src(
                    "plugin",
                    "mcpServers.dash-metrics",
                    f"{RD}/.mcp.json",
                    3,
                    plugin="routing-dashboard",
                )
            ],
        ),
        item(
            "mcp",
            "scratch",
            "scratch",
            "project_local",
            [src("project_local", "mcpServers.scratch", "~/.claude.json", 13)],
        ),
    ]
    plugins = [
        item(
            "plugins",
            "hivemind@bartab-demo",
            "hivemind@bartab-demo",
            "project",
            [
                src(
                    "project",
                    "enabledPlugins.hivemind@bartab-demo",
                    ".claude/settings.json",
                    9,
                ),
                src(
                    "user",
                    "enabledPlugins.hivemind@bartab-demo",
                    "~/.claude/settings.json",
                    20,
                    "overridden",
                ),
            ],
            effective=_eff("enabled"),
        ),
        item(
            "plugins",
            "routing-dashboard@bartab-demo",
            "routing-dashboard@bartab-demo",
            "user",
            [
                src(
                    "user",
                    "enabledPlugins.routing-dashboard@bartab-demo",
                    "~/.claude/settings.json",
                    19,
                )
            ],
            effective=_eff("enabled"),
        ),
    ]
    styles = [
        item(
            "output_style",
            "outputStyle",
            "outputStyle",
            "project_local",
            [
                src("project_local", "outputStyle", ".claude/settings.local.json", 2),
                src("user", "outputStyle", "~/.claude/settings.json", 17, "overridden"),
            ],
            effective=_eff("review-voice"),
        ),
        item(
            "output_style",
            "house",
            "house",
            "managed",
            [src("managed", "name", "managed/.claude/output-styles/house.md", 2)],
        ),
        item(
            "output_style",
            "review-voice",
            "review-voice",
            "project",
            [src("project", "name", ".claude/output-styles/review-voice.md", 2)],
        ),
        item(
            "output_style",
            "terse",
            "terse",
            "user",
            [src("user", "name", "~/.claude/output-styles/terse.md", 2)],
        ),
    ]
    parts = {
        "settings": settings,
        "agents": agents,
        "instructions": instr,
        "rules": rules,
        "skills": skills,
        "hooks": hooks,
        "permissions": perms,
        "mcp": mcp,
        "plugins": plugins,
        "output_style": styles,
    }
    return {
        "case": "complex",
        "generated": True,
        "project": {"name": "Proj", "dir": "work/parent/proj"},
        "parts": {
            name: {"items": items, "unreadable": []} for name, items in parts.items()
        },
        # The plugin agent sets permissionMode (line 6) and hooks (line 7), which Claude
        # Code ignores on a plugin agent (task 6).
        "problems": [
            {
                "id": f"plugin_field_ignored:agents:routing-dashboard:scout:{line}",
                "group": "not_as_set",
                "code": "plugin_field_ignored",
                "part": "agents",
                "item_id": "agents:routing-dashboard:scout",
                "file": f"{RD}/agents/scout.md",
                "line": line,
            }
            for line in (6, 7)
        ],
    }


def case() -> Case:
    """Return the complex case, with generated expected JSON."""
    return make_case(
        "complex",
        _FILES + plugin_blocks(CFG, with_agent=True),
        meta={"git_root": True},
        expected=_expected(),
    )

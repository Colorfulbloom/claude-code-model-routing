# ruff: noqa: E501
"""The empty, simple and typical cases. Their expected.json files are written by hand."""

from __future__ import annotations

from corpus_types import Case, make_case
from plugin_blocks import plugin_blocks

CFG = "home/.claude"
PRJ = "work/parent/proj"

_EMPTY = """\
"""

_SIMPLE = f"""\
=== {CFG}/settings.json
{{
  "model": "claude-sonnet-5-5"
}}
=== {PRJ}/.claude/settings.json
{{
  "effortLevel": "low"
}}
=== {PRJ}/CLAUDE.md
# Proj

Keep answers short.
=== {CFG}/agents/helper.md
---
name: helper
description: Answers quick questions about the repo.
---
Answer briefly.
"""

_TYPICAL_USER_SETTINGS = f"""\
=== {CFG}/settings.json
{{
  "model": "claude-opus-5-5",
  "effortLevel": "high",
  "env": {{
    "BASH_DEFAULT_TIMEOUT_MS": "60000",
    "DISABLE_TELEMETRY": "1"
  }},
  "permissions": {{
    "allow": [
      "Bash(git status)",
      "Read(./docs/**)"
    ],
    "ask": [
      "Bash(git push:*)"
    ],
    "deny": [
      "Read(./.env)"
    ],
    "defaultMode": "acceptEdits"
  }},
  "outputStyle": "terse",
  "enabledPlugins": {{
    "routing-dashboard@bartab-demo": true,
    "hivemind@bartab-demo": true
  }},
  "hooks": {{
    "PreToolUse": [
      {{
        "matcher": "Bash",
        "hooks": [
          {{"type": "command", "command": "python3 ~/bin/check-bash.py --api-key sk-ant-api03-FAKEHOOKSECRET000001"}}
        ]
      }}
    ]
  }}
}}
"""

_TYPICAL_PROJECT = f"""\
=== {PRJ}/.claude/settings.json
{{
  "effortLevel": "medium",
  "permissions": {{
    "allow": [
      "Bash(npm test)"
    ],
    "deny": [
      "Read(./secrets/**)"
    ]
  }},
  "hooks": {{
    "PostToolUse": [
      {{
        "matcher": "Edit|Write",
        "hooks": [
          {{"type": "command", "command": "bash ./scripts/format.sh"}}
        ]
      }}
    ]
  }}
}}
=== {PRJ}/.claude/settings.local.json
{{
  "enabledMcpjsonServers": ["docs"],
  "env": {{
    "BASH_DEFAULT_TIMEOUT_MS": "120000"
  }}
}}
=== {PRJ}/.mcp.json
{{
  "mcpServers": {{
    "docs": {{
      "command": "npx",
      "args": ["-y", "docs-mcp", "--token", "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKE000001"],
      "env": {{"DOCS_API_KEY": "sk-live-FAKEENVSECRET000000002"}}
    }},
    "search": {{
      "type": "http",
      "url": "https://user:hunter2pass@search.example.test/mcp",
      "headers": {{"Authorization": "Bearer FAKEBEARERTOKEN0123456789abcdef"}}
    }}
  }}
}}
=== {PRJ}/CLAUDE.md
# Proj

Style lives in @docs/style.md and nowhere else.
=== {PRJ}/docs/style.md
# Style
See @tone.md for the voice.
=== {PRJ}/docs/tone.md
# Tone
See @words.md for word choice.
=== {PRJ}/docs/words.md
# Words
Short words win.
=== {PRJ}/.claude/rules/review.md
---
paths:
  - "src/**/*.ts"
---
Review the diff for clarity.
=== {PRJ}/.claude/skills/release-check/SKILL.md
---
name: release-check
description: Check the release notes before a tag.
allowed-tools: Read, Grep
---
Read the notes and list gaps.
=== {PRJ}/.claude/agents/builder.md
---
name: builder
description: Builds the change the planner described.
model: claude-sonnet-5-5
effort: medium
---
Build it.
=== {PRJ}/.claude/agents/reviewer.md
---
name: reviewer
description: Reviews a diff for this project.
model: claude-sonnet-5-5
effort: high
---
Review it.
"""

_TYPICAL_HOME = f"""\
=== {CFG}/CLAUDE.md
# User notes
Prefer plain words.
=== {CFG}/agents/planner.md
---
name: planner
description: Plans a change before any file is touched.
model: claude-opus-5-5
effort: high
---
Plan first.
=== {CFG}/agents/reviewer.md
---
name: reviewer
description: Reviews a diff.
model: claude-sonnet-5-5
effort: medium
---
Review it.
=== {CFG}/agents/scribe.md
---
name: scribe
description: Writes release notes.
model: claude-haiku-5-5
effort: medium
---
Write the notes.
=== {CFG}/agents/tester.md
---
name: tester
description: Runs the tests and reports.
model: claude-sonnet-5-5
effort: low
---
Run the tests.
=== {CFG}/skills/tidy/SKILL.md
---
name: tidy
description: Tidy up a messy file.
---
Tidy the file.
=== {CFG}/output-styles/terse.md
---
name: terse
description: Short answers, no preamble.
---
Answer in as few words as possible.
=== home/.claude.json
{{
  "numStartups": 12,
  "oauthAccount": {{"emailAddress": "someone@example.test"}},
  "userID": "DROPPED-KEY-SENTINEL-0001",
  "mcpServers": {{
    "notes": {{
      "type": "sse",
      "url": "https://notes.example.test/sse",
      "headers": {{"X-Api-Key": "fake-xapikey-0123456789abcdef"}}
    }}
  }},
  "projects": {{
    "@@PROJECT@@": {{
      "allowedTools": [],
      "mcpServers": {{
        "scratch": {{
          "command": "node",
          "args": ["scratch.js", "--password=hunter2local"],
          "env": {{"SCRATCH_TOKEN": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.FAKESIGNATUREvalue0123456789"}}
        }}
      }}
    }}
  }}
}}
"""

# Secrets planted in the typical case, with the corpus file that holds each. The masking
# sweep (task 9) checks that none of these reaches an answer. ``NEVER`` values sit in
# ``.claude.json`` keys the reader must drop at parse.
TYPICAL_SECRETS: list[dict[str, object]] = [
    {
        "value": "sk-ant-api03-FAKEHOOKSECRET000001",
        "kind": "sk_prefix_in_hook_command",
        "case": "typical",
        "file": f"{CFG}/settings.json",
    },
    {
        "value": "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKE000001",
        "kind": "github_token_after_secret_flag",
        "case": "typical",
        "file": f"{PRJ}/.mcp.json",
    },
    {
        "value": "sk-live-FAKEENVSECRET000000002",
        "kind": "sk_prefix_in_mcp_env",
        "case": "typical",
        "file": f"{PRJ}/.mcp.json",
    },
    {
        "value": "hunter2pass",
        "kind": "url_userinfo",
        "case": "typical",
        "file": f"{PRJ}/.mcp.json",
    },
    {
        "value": "FAKEBEARERTOKEN0123456789abcdef",
        "kind": "bearer_header",
        "case": "typical",
        "file": f"{PRJ}/.mcp.json",
    },
    {
        "value": "fake-xapikey-0123456789abcdef",
        "kind": "secret_named_header",
        "case": "typical",
        "file": "home/.claude.json",
    },
    {
        "value": "hunter2local",
        "kind": "secret_named_flag_equals_in_args",
        "case": "typical",
        "file": "home/.claude.json",
    },
    {
        "value": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.FAKESIGNATUREvalue0123456789",
        "kind": "jwt_in_env",
        "case": "typical",
        "file": "home/.claude.json",
    },
]
NEVER: list[dict[str, object]] = [
    {
        "value": "someone@example.test",
        "kind": "dropped_claude_json_key",
        "case": "typical",
        "file": "home/.claude.json",
    },
    {
        "value": "DROPPED-KEY-SENTINEL-0001",
        "kind": "dropped_claude_json_key",
        "case": "typical",
        "file": "home/.claude.json",
    },
]


def typical_blocks() -> str:
    """Return the typical case's block text (the base the complex case extends)."""
    return (
        _TYPICAL_USER_SETTINGS + _TYPICAL_PROJECT + _TYPICAL_HOME + plugin_blocks(CFG)
    )


def cases() -> list[Case]:
    """Return the empty, simple and typical cases."""
    return [
        make_case("empty", _EMPTY),
        make_case("simple", _SIMPLE),
        make_case("typical", typical_blocks()),
    ]

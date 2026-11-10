# ruff: noqa: E501
"""Block text for the two plugin install folders (owner answer 10).

The shapes come from this repo's own plugin payloads (``plugin.json``, a skill, a
hooks file, an agent). The top-level shape of ``installed_plugins.json`` and
``known_marketplaces.json`` is not in the docs, so the shape here is made up from the
documented per-install fields (``scope``, ``installPath``, ``version``). Task 6's
reader must report any other shape as Can't tell (``plugin_format_unknown``).

``@@CONFIG@@`` in an install path becomes the absolute config folder at copy time.
"""

MARKET = "bartab-demo"
RD_VERSION = "0.1.7"
HM_VERSION = "0.1.3"

_RD_PLUGIN_JSON = """\
{
  "name": "routing-dashboard",
  "version": "0.1.7",
  "description": "Runs the Routing Dashboard, a local page of your Claude Code token usage and settings, from any session.",
  "author": {"name": "Jorge Calderon"},
  "license": "MIT"
}
"""

_RD_SKILL = """\
---
name: dashboard
description: Start, stop or open the Routing Dashboard for this project, or turn on editing
argument-hint: "[start|stop|reload|status|open]"
disable-model-invocation: true
model: haiku
---
Run the dashboard command and relay its output in one or two short lines.
"""

_RD_MCP = """\
{
  "mcpServers": {
    "dash-metrics": {
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/bin/metrics-server"]
    }
  }
}
"""

# A plugin agent named like a user agent (the complex case).
_RD_AGENT = """\
---
name: scout
description: Read-only scout from the plugin. Searches code and summarizes the result.
tools: Read, Glob, Grep
model: haiku
permissionMode: plan
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: echo plugin-agent
---
You are a read-only scout.
"""

_HM_PLUGIN_JSON = """\
{
  "name": "hivemind",
  "version": "0.1.3",
  "description": "Manages HiveMind, the per-project memory your Claude Code agents share, from any session.",
  "author": {"name": "Jorge Calderon"},
  "license": "MIT"
}
"""

_HM_HOOKS = """\
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/bin/hivemind", "guard"], "if": "Bash(python3 *bin/hivemind*)", "onFailure": "block"}]}
    ]
  }
}
"""


def _install(base: str, plugin: str, version: str) -> str:
    return f"{base}/plugins/cache/{MARKET}/{plugin}/{version}"


def installed_plugins(entries: list[tuple[str, str]]) -> str:
    """Return an ``installed_plugins.json`` text.

    Args:
        entries: ``(plugin name, version)`` pairs, all from the one marketplace.

    Returns:
        The file text. Line 1 is ``{``, line 2 the version, and every plugin takes
        three lines from line 4.
    """
    lines = ["{", '  "version": 2,', '  "plugins": {']
    for number, (name, version) in enumerate(entries):
        comma = "," if number < len(entries) - 1 else ""
        path = f"@@CONFIG@@/plugins/cache/{MARKET}/{name}/{version}"
        lines.append(f'    "{name}@{MARKET}": [')
        lines.append(
            f'      {{"scope": "user", "installPath": "{path}", "version": "{version}"}}'
        )
        lines.append(f"    ]{comma}")
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


def known_marketplaces() -> str:
    """Return a ``known_marketplaces.json`` text."""
    return f"""\
{{
  "{MARKET}": {{
    "source": {{"source": "github", "repo": "example/{MARKET}"}},
    "installLocation": "@@CONFIG@@/plugins/marketplaces/{MARKET}",
    "lastUpdated": "2026-11-01T00:00:00.000Z",
    "autoUpdate": true
  }}
}}
"""


def plugin_blocks(base: str, *, with_agent: bool = False) -> str:
    """Return block text for the two plugins under ``<base>/plugins``.

    Args:
        base: The config folder, relative to the case (``home/.claude`` or ``config``).
        with_agent: Add the plugin agent named ``scout`` to routing-dashboard.

    Returns:
        Block text: both install folders, ``installed_plugins.json`` and
        ``known_marketplaces.json``.
    """
    rd = _install(base, "routing-dashboard", RD_VERSION)
    hm = _install(base, "hivemind", HM_VERSION)
    out = [
        f"=== {base}/plugins/installed_plugins.json\n",
        installed_plugins(
            [("routing-dashboard", RD_VERSION), ("hivemind", HM_VERSION)]
        ),
        f"=== {base}/plugins/known_marketplaces.json\n",
        known_marketplaces(),
        f"=== {rd}/.claude-plugin/plugin.json\n",
        _RD_PLUGIN_JSON,
        f"=== {rd}/skills/dashboard/SKILL.md\n",
        _RD_SKILL,
        f"=== {rd}/.mcp.json\n",
        _RD_MCP,
        f"=== {hm}/.claude-plugin/plugin.json\n",
        _HM_PLUGIN_JSON,
        f"=== {hm}/hooks/hooks.json\n",
        _HM_HOOKS,
    ]
    if with_agent:
        out += [f"=== {rd}/agents/scout.md\n", _RD_AGENT]
    return "".join(out)

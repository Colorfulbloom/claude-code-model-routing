### F-3b8a HiveMind read-only skills drop the Bash deny
status: shipped
kind: code
dates: 2026-11-04 .. 2026-11-04
refs:
  commit: 037d3b5b33c1914915223038985f86b1f7559709 (branch fix/hivemind-deny-leak, merged into development)
summary: hivemind 0.1.1 removes disallowed-tools from status, inbox, related and check; link, init and consolidate keep Bash(python3 *bin/hivemind*).
decisions:
- A skill's disallowed-tools deny lasts until the next user message, and a slash command counts as one, so each HiveMind command denied the very next one (seen live, commands alternated worked and denied).
- Read-only skills have nothing to guard, so they carry no deny; the three writers keep it.
files: plugins/hivemind/skills/status/SKILL.md, plugins/hivemind/skills/inbox/SKILL.md, plugins/hivemind/skills/related/SKILL.md, plugins/hivemind/skills/check/SKILL.md, plugins/hivemind/.claude-plugin/plugin.json, plugins/hivemind/payload, tests/test_plugin_build.py
follow-ups:
- Owner: after updating, run the four read-only commands back to back and confirm none is denied.

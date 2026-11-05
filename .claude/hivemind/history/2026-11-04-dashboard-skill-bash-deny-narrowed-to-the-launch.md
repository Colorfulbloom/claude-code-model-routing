### F-8c16 Dashboard skill Bash deny narrowed to the launcher; fast-worker effort medium
status: shipped
kind: code
dates: 2026-11-04 .. 2026-11-04
refs:
  commit: 5480b8eba1d86e1c96c60fca1a1ae19e53abab17 (branch fix/dashboard-skill-bash-block, merged into development)
summary: routing-dashboard 0.1.2 replaces the skill's bare disallowed-tools Bash (which blocked Bash session-wide, background agents included) with a launcher-only pattern; fast-worker pinned at medium after the effort trial.
decisions:
- disallowed-tools: Bash(python3 *bin/routing-dashboard*). Probed on 2.1.302 with a scripted fake API: the skill's own ! line still runs (undocumented), the model, subagents and background agents are denied only the launcher during the turn, other Bash works.
- Wildcard path, because ${CLAUDE_PLUGIN_ROOT} is expanded in allowed-tools but not in disallowed-tools (probe and skills docs).
- Both commits share unreleased 0.1.2; BUILD.json was reset to the 0.1.1 record before the second build so build_plugins would write it. Merge both commits together.
- fast-worker effort: medium (owner, November 4); leads pass effort high only for risky or tricky tasks.
rejected:
- No deny rule: the allowed-tools grant let the model and a subagent run edits unprompted in the turn (probed).
- $ARGUMENTS in allowed-tools: not expanded, so the ! line is unapproved and the skill aborts (probed).
- Launcher-side refusal: the launcher can't tell its ! line from a model call.
- A second deny Bash(*bin/routing-dashboard*) for direct or /usr/bin/python3 spellings: not probed, could abort the ! line; those spellings need approval in default mode anyway.
files: plugins/routing-dashboard/skills/dashboard/SKILL.md, plugins/routing-dashboard/README.md, plugins/routing-dashboard/.claude-plugin/plugin.json, plugins/routing-dashboard/payload, tests/test_plugin_build.py, agents/fast-worker.md, rules/model-routing.md
gotchas:
- A bare tool name in a skill's disallowed-tools removes the tool for the life of subagents started in that turn, and denies it to running background agents until the next user message.
- claude -p auto-allows echo as read-only, so permission probes need a non-read-only command.
- The fix relies on the ! line ignoring the skill's own deny rule, while the skills docs say a matching deny rule aborts the invocation. Re-probe on Claude Code upgrades.
follow-ups:
- Owner: decide whether to commit the probe scripts (session scratchpad) as a harness extension for re-runs.
- Pattern case not probed for a foreground subagent that outlives the turn.

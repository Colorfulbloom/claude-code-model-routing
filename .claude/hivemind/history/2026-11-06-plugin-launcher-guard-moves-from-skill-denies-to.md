### F-477a Plugin launcher guard moves from skill denies to a PreToolUse hook
status: in-progress
kind: code
dates: 2026-11-06 .. 2026-11-06
refs:
  commit: pending (branch design/dashboard-deny-leak)
summary: routing-dashboard 0.1.7 and hivemind 0.1.3 drop disallowed-tools from every skill and ship a PreToolUse Bash hook whose hidden guard action denies the model's own launcher or wrapper calls, so back-to-back commands no longer alternate denied and working.
decisions:
- Mechanism (probed on 2.1.302): a skill's disallowed-tools deny lasts until the next user message, and the next slash command's own ! line runs before it clears, so it is refused; the refused run installs no deny, so the one after works.
- Fix: PreToolUse never fires for a skill's ! line but fires for every model, subagent and background-agent Bash call in every turn and mode, bypassPermissions included (probed). hooks.json entry: matcher Bash, if Bash(python3 *bin/routing-dashboard*) or Bash(python3 *bin/hivemind*), onFailure block, exec form python3 <bin> guard.
- The guard re-checks the command per segment (split on ; && || | & newline $( backtick and brackets, skip VAR=value and wrappers such as env, deny when the first word is python3* and the segment holds bin/<launcher>). The hook also starts for commands with $(), backticks, $VAR or that Claude Code can't parse, so a bare substring test denied unrelated commands such as grep ... | head -$N (verifier). Bad input, an exception or a failed stdout write denies (fail closed).
- skill_probe classify reports "hook" only when the refusal carries GUARD_REASON, because onFailure block also reports a crashed guard as a PreToolUse error. --bypass reruns shipped under bypassPermissions.
- Owner (November 6): block model-run launcher calls even when the owner would approve; keep the pattern scope of the old deny; fix the HiveMind writers in the same build.
- skill_probe gains a shipped variant (the exit code), a seq skill and a seventh back-to-back check; bare and narrow stay informational.
rejected:
- Split edits into its own skill (A): probed; the everyday skill's allowed-tools grant let the model run edits, and the edits skill's deny still blocked the next command. An edits-only deny on both still alternated edits.
- Launcher token minted by the ! line (B): the model can replay the same command. A UserPromptSubmit-minted token works but adds a hook on every prompt and token state for the same result.
- A broad if Bash(*bin/routing-dashboard*): would block cat or sed on the launcher in this repo, now that the guard is permanent.
files: plugins/routing-dashboard/skills/dashboard/SKILL.md, plugins/routing-dashboard/hooks/hooks.json, plugins/routing-dashboard/bin/routing-dashboard, plugins/routing-dashboard/README.md, plugins/routing-dashboard/.claude-plugin/plugin.json, plugins/hivemind/skills/link/SKILL.md, plugins/hivemind/skills/init/SKILL.md, plugins/hivemind/skills/consolidate/SKILL.md, plugins/hivemind/hooks/hooks.json, plugins/hivemind/bin/hivemind, plugins/hivemind/README.md, plugins/hivemind/.claude-plugin/plugin.json, tests/test_plugin_build.py, tests/test_plugin_launcher.py, tests/test_plugin_hivemind.py, tests/test_skill_probe.py, tools/skill_probe/probe.py, tools/skill_probe/README.md
gotchas:
- The fix relies on PreToolUse skipping ! lines, which is undocumented; rerun tools/skill_probe/probe.py after every Claude Code upgrade.
- 2.1.302 shows a hook deny to the model as "PreToolUse:Bash hook error: <reason>"; the command does not run.
- The hooks docs call `if` best-effort; the guard's own substring check is the backstop.
follow-ups:
- Owner: after updating both plugins, run four dashboard commands and two HiveMind commands back to back (link then status) and confirm none is denied.
- The committed probe covers only the dashboard; the HiveMind hook was checked with a scratch probe (session scratchpad).

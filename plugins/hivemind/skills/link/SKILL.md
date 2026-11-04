---
name: link
description: List history entries waiting for a commit, or link one to its commit
argument-hint: "[<id> <sha or base..head>]"
disable-model-invocation: true
model: haiku
disallowed-tools: Bash(python3 *bin/hivemind*)
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" *)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" --project "${CLAUDE_PROJECT_DIR}" link $ARGUMENTS`

The HiveMind command's output is above. Relay it to the user in a few short lines. Keep ids, paths, SHAs, counts and any line that starts with consolidate: exactly as written. Pass on every line that starts with error:, warning: or note:. Don't run any command. Add nothing else.

---
name: status
description: Show this project's HiveMind store and whether a consolidation has work waiting
disable-model-invocation: true
model: haiku
disallowed-tools: Bash(python3 *bin/hivemind*)
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" *)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" --project "${CLAUDE_PROJECT_DIR}" status $ARGUMENTS`

The HiveMind command's output is above. Relay it to the user in a few short lines. Keep ids, paths, SHAs, counts and any line that starts with consolidate: exactly as written. Pass on every line that starts with error:, warning: or note:. Don't run any command. Add nothing else.

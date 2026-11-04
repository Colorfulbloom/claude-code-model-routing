---
name: related
description: List the facts and history entries that cite the paths you give
argument-hint: "<path>..."
disable-model-invocation: true
model: haiku
disallowed-tools: Bash(python3 *bin/hivemind*)
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" *)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" --project "${CLAUDE_PROJECT_DIR}" related $ARGUMENTS`

The HiveMind command's output is above. Relay it to the user in a few short lines. Keep ids, paths, SHAs, counts and any line that starts with consolidate: exactly as written. Pass on every line that starts with error:, warning: or note:. Don't run any command. Add nothing else.

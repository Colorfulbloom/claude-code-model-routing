---
name: inbox
description: Preview what the next consolidation would fold in, without writing anything
disable-model-invocation: true
model: haiku
disallowed-tools: Bash(python3 *bin/hivemind*)
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" *)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" --project "${CLAUDE_PROJECT_DIR}" inbox $ARGUMENTS`

The consolidation preview is above. If it arrived as a file path with a short preview, read that file with the Read tool. Relay the counts and every proposal (topic, fact, check, evidence, flags) in full, then one line for each other section. Keep ids, paths and commands exactly as written. Pass on every line that starts with error:, warning: or note:. This was a preview, and nothing was written. Don't run any command.

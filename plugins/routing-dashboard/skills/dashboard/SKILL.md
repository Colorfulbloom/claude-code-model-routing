---
name: dashboard
description: Start, stop or open the Routing Dashboard for this project, or turn on editing
argument-hint: "[start|stop|reload|status|open|project <dir>|edits|log] [--port N] [--all] [--no-open] [--key-file]"
disable-model-invocation: true
model: haiku
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard" *)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard" --data "${CLAUDE_PLUGIN_DATA}" --default-project "${CLAUDE_PROJECT_DIR}" --session "${CLAUDE_SESSION_ID}" $ARGUMENTS`

The launcher's output is above. Relay it to the user in one or two short lines. Keep every URL and file path exactly as written. If a line starts with "error:", say what failed and pass on any hint it gives. Never print, guess or ask for an edit key, and never build an edit link yourself. Don't run any command. Add nothing else.

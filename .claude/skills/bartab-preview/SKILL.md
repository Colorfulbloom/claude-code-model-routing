---
name: bartab-preview
description: Start, stop or check the Bar Tab preview from this checkout, on the demo build
argument-hint: "[start|code|stop|status] [--project DIR] [--no-open] [--port N] [--fixture NAME]"
disable-model-invocation: true
model: haiku
allowed-tools: Bash(python3 "${CLAUDE_PROJECT_DIR}/app/bin/bartab.py" *)
---
!`python3 "${CLAUDE_PROJECT_DIR}/app/bin/bartab.py" --default-project "${CLAUDE_PROJECT_DIR}" --session "${CLAUDE_SESSION_ID}" --demo --ingest-pace-ms 30 $ARGUMENTS`

The launcher's output is above. Relay it to the user in one or two short lines. Keep every URL exactly as written, including everything after the `#`. If a line starts with "error:", say what failed and pass on any hint it gives. Never print, guess or ask for a key, and never build a link yourself. Don't run any command. Add nothing else.

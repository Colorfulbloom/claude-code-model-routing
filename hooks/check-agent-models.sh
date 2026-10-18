#!/usr/bin/env bash
# SessionStart hook: warns when the current project has agents with no pinned model.
dir="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/agents"
[ -d "$dir" ] || exit 0
missing=()
for f in "$dir"/*.md; do
  [ -e "$f" ] || continue
  m=$(sed -n '2,/^---$/p' "$f" | grep -E '^model:' | head -1 | sed -E 's/^model:[[:space:]]*//; s/[[:space:]]+$//')
  if [ -z "$m" ] || [ "$m" = "inherit" ]; then
    missing+=("$(basename "$f" .md)")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Model routing: ${#missing[@]} project agent(s) have no pinned model (${missing[*]}). Dispatches to them will be blocked until a model is passed. Run /route-project to pin them."
fi
exit 0

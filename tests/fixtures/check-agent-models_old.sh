#!/usr/bin/env bash
# SessionStart hook: warns about project and user agents with no model or effort in their frontmatter.
MSG_PROJECT_UNPINNED='Model routing: %s project agent(s) have no model or effort in their frontmatter (%s). Dispatches to them are blocked until the session passes a model, so run /route-project to pin them.\n'
MSG_USER_UNPINNED='Model routing: %s user agent(s) in %s have no model or effort in their frontmatter (%s). Dispatches to them are blocked until the session passes a model, so add model and effort lines to each file.\n'

# Prints the space-separated names of the unpinned agents in a folder.
unpinned() {
  local f model effort names=()
  for f in "$1"/*.md; do
    [ -e "$f" ] || continue
    model=$(field "$f" model)
    effort=$(field "$f" effort)
    if [ -z "$model" ] || [ "$model" = "inherit" ] || [ -z "$effort" ]; then
      names+=("$(basename "$f" .md)")
    fi
  done
  echo "${names[*]}"
}

# Prints a frontmatter value with one pair of surrounding quotes removed.
field() {
  sed -n '2,/^---$/p' "$1" | grep -E "^$2:" | head -1 \
    | sed -E "s/^$2:[[:space:]]*//; s/[[:space:]]+\$//; s/^\"(.*)\"\$/\1/; s/^'(.*)'\$/\1/"
}

proj="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/agents"
user="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agents"
if [ -d "$proj" ]; then
  n=$(unpinned "$proj")
  # shellcheck disable=SC2059
  [ -z "$n" ] || printf "$MSG_PROJECT_UNPINNED" "$(echo $n | wc -w | tr -d ' ')" "$n"
fi
if [ -d "$user" ] && [ "$user" != "$proj" ]; then
  n=$(unpinned "$user")
  # shellcheck disable=SC2059
  [ -z "$n" ] || printf "$MSG_USER_UNPINNED" "$(echo $n | wc -w | tr -d ' ')" "$user" "$n"
fi
exit 0

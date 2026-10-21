#!/usr/bin/env bash
# Installs the model-routing setup (agents, rules, hooks, skills, reference doc)
# into the Claude Code config directory and registers two hooks in settings.json.
# Runs on bash 3.2 (macOS) and bash 4/5 (Linux). Needs python3 for the JSON work.
set -euo pipefail

# ============================================================================
# Messages
# Every string a user reads lives in this section. Reword freely, but keep the
# printf placeholders (%s) in the same number and order. Logic starts below.
# ============================================================================

msg_usage() {
  cat <<'EOF'
Usage: install.sh [--dry-run] [--uninstall] [--help]

Installs the model-routing setup (agents, rules, hooks, skills and the
reference doc) into the Claude Code config directory, CLAUDE_CONFIG_DIR when
set and $HOME/.claude otherwise. Anything it replaces is backed up first
under <config dir>/backups/.

Options:
  --dry-run    Print the plan. Change nothing.
  --uninstall  Remove what a previous install added (it reads the manifest).
  --help, -h   Show this text.

Exit codes: 0 ok, 1 failure, 2 usage error.
EOF
}

MSG_UNKNOWN_FLAG='Unknown option: %s\n'
MSG_BASH_VERSION='bash %s\n'
MSG_CLAUDE_VERSION='claude %s\n'
MSG_TARGET='Target: %s\n'
MSG_DRY_BANNER='Dry run. Nothing is created, written or deleted.\n'
MSG_FILES_HEADING='Files\n'
MSG_FILE_ADD='  add        %s\n'
MSG_FILE_UNCHANGED='  unchanged  %s\n'
MSG_FILE_REPLACE='  replace    %s (old copy saved to %s)\n'
MSG_FILE_REMOVE='  remove     %s\n'
MSG_FILE_MOVE='  edited     %s (kept at %s)\n'
MSG_FILE_GONE='  missing    %s (already gone)\n'
MSG_FILE_SAMENAME='  warning    %s also declares name: %s. Claude Code will load only one of the two. Rename or remove that file.\n'
MSG_SETTINGS_HEADING='Settings (%s)\n'
MSG_SETTINGS_ADD='  add        %s hook, matcher %s\n'
MSG_SETTINGS_SKIP='  skip       %s hook, matcher %s (already there)\n'
MSG_SETTINGS_REMOVE='  remove     %s hook, matcher %s\n'
MSG_SETTINGS_ABSENT='  skip       %s hook, matcher %s (not there)\n'
MSG_SETTINGS_BACKUP='  settings.json saved to %s\n'
MSG_SETTINGS_NOFILE='  no settings.json found\n'
MSG_MANIFEST_HEADING='Manifest (%s)\n'
MSG_MANIFEST_WRITE='  write      %s\n'
MSG_MANIFEST_UNCHANGED='  unchanged  %s\n'
MSG_MANIFEST_REMOVE='  remove     %s\n'
MSG_MANIFEST_MISSING='No manifest at %s. Only the two hook entries can be removed.\n'
MSG_MANIFEST_LINE='    %s\n'
MSG_SUMMARY_INSTALL='Summary: %s added, %s replaced, %s unchanged. Settings entries: %s added, %s skipped.\n'
MSG_SUMMARY_SAMENAME='Same-name agent files: %s found. Each one needs a rename or a removal, or Claude Code keeps only one of the pair.\n'
MSG_SUMMARY_UNINSTALL='Summary: %s removed, %s kept in backup, %s already gone. Settings entries: %s removed, %s skipped.\n'
MSG_SUMMARY_BACKUP='Backups: %s\n'
MSG_SUMMARY_NO_BACKUP='Backups: none needed\n'
MSG_NEXT_HEADING='Next steps\n'
MSG_NEXT_INSTALL_1='  1. Restart Claude Code so the hooks and agents load.\n'
MSG_NEXT_INSTALL_2='  2. Run /route-project inside each project that has its own agents.\n'
MSG_NEXT_INSTALL_3='  3. Optional. Run /setup-model-routing for the settings this installer leaves alone (main model, effortLevel, subagent catch-all model).\n'
MSG_NEXT_UNINSTALL_1='  1. Restart Claude Code so it stops loading the removed files.\n'

MSG_ERR_NO_PYTHON='Error: python3 is not on PATH. Install it and run this again.\n'
MSG_ERR_NO_CLAUDE='Error: claude is not on PATH. Install Claude Code first.\n'
MSG_ERR_BAD_TARGET='Error: the target path contains a double quote, dollar sign, backtick or backslash: %s\n'
MSG_ERR_NO_SOURCE='Error: nothing to install in %s\n'
MSG_ERR_BAD_MANIFEST_PATH='Error: the manifest lists an unsafe path, so nothing was changed: %s\n'
MSG_ERR_SETTINGS_PARSE='Error: %s is not valid JSON. Nothing was changed.\n'
MSG_ERR_SETTINGS_NOT_OBJECT='Error: %s is not a JSON object. Nothing was changed.\n'
MSG_ERR_SETTINGS_HOOKS='Error: "hooks" in %s is not an object. Nothing was changed.\n'
MSG_ERR_SETTINGS_EVENT='Error: hooks.%s in %s is not a list. Nothing was changed.\n'
MSG_ERR_SETTINGS_OTHER='Error: could not update %s: %s\n'
MSG_ERR_COPY='Error: could not write %s\n'
MSG_ERR_TARGET_NOT_DIR='Error: %s exists but is not a directory. Nothing was changed.\n'
MSG_ERR_NOT_WRITABLE='Error: %s is not writable. Nothing was changed.\n'
MSG_ERR_SETTINGS_DANGLING='Error: %s is a symlink whose target does not exist. Nothing was changed.\n'

# ============================================================================
# End of Messages
# ============================================================================

# ---- Arguments --------------------------------------------------------------
DRY=0
UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --help|-h) msg_usage; exit 0 ;;
    *)
      # shellcheck disable=SC2059
      printf "$MSG_UNKNOWN_FLAG" "$arg" >&2
      msg_usage >&2
      exit 2
      ;;
  esac
done

# The format strings come from the Messages section above, never from input.
# shellcheck disable=SC2059
say() { local fmt="$1"; shift; printf "$fmt" "$@"; }
# shellcheck disable=SC2059
die() { local fmt="$1"; shift; printf "$fmt" "$@" >&2; exit 1; }

# ---- Prerequisites ----------------------------------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

command -v python3 >/dev/null 2>&1 || die "$MSG_ERR_NO_PYTHON"
say "$MSG_BASH_VERSION" "$BASH_VERSION"
if [ "$UNINSTALL" -eq 0 ]; then
  command -v claude >/dev/null 2>&1 || die "$MSG_ERR_NO_CLAUDE"
  CLAUDE_VERSION="$(claude --version 2>&1 | head -n 1 || true)"
  say "$MSG_CLAUDE_VERSION" "$CLAUDE_VERSION"
fi

# ---- Target -----------------------------------------------------------------
T="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
while [ "${#T}" -gt 1 ] && [ "${T%/}" != "$T" ]; do T="${T%/}"; done
case "$T" in
  /*) ;;
  *) T="$(pwd -P)/$T" ;;
esac
# shellcheck disable=SC1003
case "$T" in
  *'"'*|*'$'*|*'`'*|*'\'*) die "$MSG_ERR_BAD_TARGET" "$T" ;;
esac
# A file (or a broken link) where the target directory should be.
if { [ -e "$T" ] || [ -L "$T" ]; } && [ ! -d "$T" ]; then die "$MSG_ERR_TARGET_NOT_DIR" "$T"; fi
say "$MSG_TARGET" "$T"

# Hook command prefix. The literal text $HOME/.claude is kept unexpanded when
# the target is the default location, so settings.json stays portable.
if [ "$T" = "$HOME/.claude" ]; then
  # shellcheck disable=SC2016
  PREFIX='$HOME/.claude'
else
  PREFIX="$T"
fi
CMD_PRE="python3 \"${PREFIX}/hooks/require-agent-model.py\""
CMD_SESSION="bash \"${PREFIX}/hooks/check-agent-models.sh\""

if [ "$DRY" -eq 1 ]; then say "$MSG_DRY_BANNER"; fi

# ---- Plan: source <TAB> destination (relative to T) <TAB> mode ---------------
PLAN=""
add_plan() { PLAN="${PLAN}${1}	${2}	${3}"$'\n'; }

for f in "$REPO_DIR"/agents/*.md; do
  if [ -f "$f" ]; then add_plan "$f" "agents/$(basename "$f")" 644; fi
done
for f in "$REPO_DIR"/rules/*.md; do
  if [ -f "$f" ]; then add_plan "$f" "rules/$(basename "$f")" 644; fi
done
for name in require-agent-model.py check-agent-models.sh; do
  if [ -f "$REPO_DIR/hooks/$name" ]; then add_plan "$REPO_DIR/hooks/$name" "hooks/$name" 755; fi
done
if [ -d "$REPO_DIR/skills" ]; then
  SKILL_FILES="$(find "$REPO_DIR/skills" -type f ! -name .DS_Store | LC_ALL=C sort)"
  while IFS= read -r f; do
    if [ -n "$f" ]; then add_plan "$f" "skills/${f#"$REPO_DIR"/skills/}" 644; fi
  done <<EOF
$SKILL_FILES
EOF
fi
if [ -f "$REPO_DIR/docs/model-routing-reference.md" ]; then
  add_plan "$REPO_DIR/docs/model-routing-reference.md" "model-routing-reference.md" 644
fi
[ -n "$PLAN" ] || die "$MSG_ERR_NO_SOURCE" "$REPO_DIR"

MANIFEST="$T/model-routing-manifest.txt"

# settings.json may be a symlink (dotfiles setups). Work on the real file so the
# link survives and its target receives the hooks.
SETTINGS_REAL="$T/settings.json"
if [ -L "$SETTINGS_REAL" ]; then
  [ -e "$SETTINGS_REAL" ] || die "$MSG_ERR_SETTINGS_DANGLING" "$T/settings.json"
  SETTINGS_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$SETTINGS_REAL")"
fi
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=""
NEED_BACKUP=0

# Picks the backup dir name once (adds a numeric suffix if the name is taken).
# Creates nothing; whoever needs the dir creates it.
pick_backup_dir() {
  if [ -n "$BACKUP_DIR" ]; then return 0; fi
  local base cand n
  if [ "$UNINSTALL" -eq 1 ]; then
    base="$T/backups/model-routing-uninstall-$STAMP"
  else
    base="$T/backups/model-routing-$STAMP"
  fi
  cand="$base"
  n=1
  while [ -e "$cand" ]; do
    n=$((n + 1))
    cand="$base-$n"
  done
  BACKUP_DIR="$cand"
}

# ---- Writability preflight ----------------------------------------------------
# need_writable <path>: the path itself when it exists, else its nearest existing
# ancestor, must be a directory we can write to and enter. Stops the run with
# nothing written otherwise.
need_writable() {
  local p="$1"
  while [ ! -e "$p" ] && [ ! -L "$p" ]; do p="$(dirname "$p")"; done
  if [ ! -d "$p" ] || [ ! -w "$p" ] || [ ! -x "$p" ]; then die "$MSG_ERR_NOT_WRITABLE" "$p"; fi
}

# Runs before anything is copied or written, for a real run and a dry run alike
# (a dry run reports the same error, because the real run would fail).
preflight() {
  local src rel mode paths
  if [ "$UNINSTALL" -eq 1 ] && [ ! -e "$T" ]; then return 0; fi
  need_writable "$T"
  need_writable "$(dirname "$SETTINGS_REAL")"
  need_writable "$T/backups"
  if [ "$UNINSTALL" -eq 0 ]; then
    while IFS="$(printf '\t')" read -r src rel mode; do
      if [ -z "$src" ]; then continue; fi
      need_writable "$(dirname "$T/$rel")"
    done <<EOF
$PLAN
EOF
  elif [ -f "$MANIFEST" ]; then
    paths="$(grep -v '^#' "$MANIFEST" | grep -v '^[[:space:]]*$' || true)"
    while IFS= read -r rel; do
      if [ -z "$rel" ]; then continue; fi
      case "$rel" in
        /*|..|../*|*/..|*/../*) continue ;;  # refused later with its own message
      esac
      if [ -e "$T/$rel" ]; then need_writable "$(dirname "$T/$rel")"; fi
    done <<EOF
$paths
EOF
  fi
}

# ---- Settings merge (python3) -------------------------------------------------
# Output lines (tab separated) read by do_settings:
#   backup <path> | add/skip/remove/absent <event> <matcher> | nofile | error <code> [detail]
run_settings() {
  local mode="$1" dry="$2"
  python3 - "$mode" "$SETTINGS_REAL" "$dry" "$BACKUP_DIR" "$(dirname "$SETTINGS_REAL")" "$CMD_PRE" "$CMD_SESSION" <<'PY'
import json, os, shutil, sys, tempfile

mode, path, dry, backup_dir, tdir, cmd_pre, cmd_session = sys.argv[1:8]
dry = dry == "1"
entries = [
    ("PreToolUse", "Agent", cmd_pre),
    ("SessionStart", "startup", cmd_session),
]

def out(*parts):
    print("\t".join(parts))

existed = os.path.exists(path)
if existed:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        out("error", "parse")
        sys.exit(1)
    if not isinstance(data, dict):
        out("error", "notobject")
        sys.exit(1)
else:
    data = {}
    if mode == "uninstall":
        out("nofile")

hooks = data.get("hooks")
if "hooks" in data and not isinstance(hooks, dict):
    out("error", "hooks")
    sys.exit(1)
for event, _, _ in entries:
    if isinstance(hooks, dict) and event in hooks and not isinstance(hooks[event], list):
        out("error", "event", event)
        sys.exit(1)

def has_ours(group, matcher, command):
    if not isinstance(group, dict) or group.get("matcher") != matcher:
        return False
    hs = group.get("hooks")
    if not isinstance(hs, list):
        return False
    return any(isinstance(h, dict) and h.get("type") == "command" and h.get("command") == command for h in hs)

changed = False
if mode == "install":
    for event, matcher, command in entries:
        lst = hooks.get(event) if isinstance(hooks, dict) else None
        if isinstance(lst, list) and any(has_ours(g, matcher, command) for g in lst):
            out("skip", event, matcher)
            continue
        if not isinstance(hooks, dict):
            hooks = {}
            data["hooks"] = hooks
        if event not in hooks:
            hooks[event] = []
        hooks[event].append({"matcher": matcher, "hooks": [{"type": "command", "command": command, "timeout": 10}]})
        out("add", event, matcher)
        changed = True
else:
    for event, matcher, command in entries:
        lst = hooks.get(event) if isinstance(hooks, dict) else None
        removed = False
        if isinstance(lst, list):
            keep = []
            for g in lst:
                if has_ours(g, matcher, command):
                    before = g["hooks"]
                    after = [h for h in before
                             if not (isinstance(h, dict) and h.get("type") == "command" and h.get("command") == command)]
                    if len(after) != len(before):
                        removed = True
                    if after:
                        g["hooks"] = after
                        keep.append(g)
                    # a group we emptied is dropped
                else:
                    keep.append(g)
            if removed:
                if keep:
                    hooks[event] = keep
                else:
                    del hooks[event]
        if removed:
            out("remove", event, matcher)
            changed = True
        else:
            out("absent", event, matcher)
    if changed and isinstance(hooks, dict) and not hooks:
        del data["hooks"]

if not changed:
    sys.exit(0)

if existed:
    out("backup", os.path.join(backup_dir, "settings.json"))
if dry:
    sys.exit(0)

try:
    if existed:
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(path, os.path.join(backup_dir, "settings.json"))
    os.makedirs(tdir, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile("w", dir=tdir, delete=False, encoding="utf-8")
    try:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.chmod(tmp.name, (os.stat(path).st_mode & 0o7777) if existed else 0o644)
        os.replace(tmp.name, path)
    except Exception:
        try:
            tmp.close()
        except Exception:
            pass
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise
except Exception as exc:
    out("error", "other", str(exc))
    sys.exit(1)
PY
}

SET_ADDED=0; SET_SKIPPED=0; SET_REMOVED=0
# Runs the merge and prints its lines through the Messages section.
# do_settings <mode> <dry 0|1> <quiet 0|1>. A quiet run only checks that the
# file can be merged (used before any file is copied).
do_settings() {
  local mode="$1" dry="$2" quiet="$3" out rc=0 kind a b
  pick_backup_dir
  out="$(run_settings "$mode" "$dry")" || rc=$?
  while IFS="$(printf '\t')" read -r kind a b; do
    case "$kind" in
      add) if [ "$quiet" -eq 0 ]; then say "$MSG_SETTINGS_ADD" "$a" "$b"; SET_ADDED=$((SET_ADDED + 1)); fi ;;
      skip) if [ "$quiet" -eq 0 ]; then say "$MSG_SETTINGS_SKIP" "$a" "$b"; SET_SKIPPED=$((SET_SKIPPED + 1)); fi ;;
      remove) if [ "$quiet" -eq 0 ]; then say "$MSG_SETTINGS_REMOVE" "$a" "$b"; SET_REMOVED=$((SET_REMOVED + 1)); fi ;;
      absent) if [ "$quiet" -eq 0 ]; then say "$MSG_SETTINGS_ABSENT" "$a" "$b"; SET_SKIPPED=$((SET_SKIPPED + 1)); fi ;;
      nofile) if [ "$quiet" -eq 0 ]; then say "$MSG_SETTINGS_NOFILE"; fi ;;
      backup) if [ "$quiet" -eq 0 ]; then say "$MSG_SETTINGS_BACKUP" "$a"; NEED_BACKUP=1; fi ;;
      error)
        case "$a" in
          parse) die "$MSG_ERR_SETTINGS_PARSE" "$T/settings.json" ;;
          notobject) die "$MSG_ERR_SETTINGS_NOT_OBJECT" "$T/settings.json" ;;
          hooks) die "$MSG_ERR_SETTINGS_HOOKS" "$T/settings.json" ;;
          event) die "$MSG_ERR_SETTINGS_EVENT" "$b" "$T/settings.json" ;;
          *) die "$MSG_ERR_SETTINGS_OTHER" "$T/settings.json" "$b" ;;
        esac
        ;;
    esac
  done <<EOF
$out
EOF
  if [ "$rc" -ne 0 ]; then exit 1; fi
}

print_backup_summary() {
  if [ "$NEED_BACKUP" -eq 1 ] && [ -n "$BACKUP_DIR" ]; then
    say "$MSG_SUMMARY_BACKUP" "$BACKUP_DIR"
  else
    say "$MSG_SUMMARY_NO_BACKUP"
  fi
}

# ---- Same-name agent scan -----------------------------------------------------
# Read-only. Warns about files under <target>/agents/ that are not ours but whose
# frontmatter name equals one of our agent names. File names and values are
# untrusted text: they are only compared with [ = ] and printed through %s.
SAMENAME=0
scan_samename() {
  local src rel mode names="" ours="" f nm line shown n
  [ -d "$T/agents" ] || return 0
  while IFS="$(printf '\t')" read -r src rel mode; do
    case "$rel" in
      agents/*.md) names="${names}$(basename "$rel" .md)"$'\n'; ours="${ours}${T}/${rel}"$'\n' ;;
    esac
  done <<EOF
$PLAN
EOF
  while IFS= read -r -d '' f; do
    # Our own six paths are covered by the add, replace and unchanged logic.
    n=0
    while IFS= read -r line; do
      if [ "$line" = "$f" ]; then n=1; fi
    done <<EOF
$ours
EOF
    if [ "$n" -eq 1 ]; then continue; fi
    # Only frontmatter counts: line 1 is ---, the block ends at the next ---.
    line="$(awk 'NR == 1 && $0 != "---" { exit } NR > 1 && $0 == "---" { exit } NR > 1 && /^name:/ { print; exit }' "$f" 2>/dev/null || true)"
    if [ -z "$line" ]; then continue; fi
    nm="${line#name:}"
    nm="${nm#"${nm%%[![:space:]]*}"}"
    nm="${nm%"${nm##*[![:space:]]}"}"
    case "$nm" in
      \"?*\") nm="${nm#\"}"; nm="${nm%\"}" ;;
      \'?*\') nm="${nm#\'}"; nm="${nm%\'}" ;;
    esac
    while IFS= read -r line; do
      if [ -n "$line" ] && [ "$line" = "$nm" ]; then
        shown="$(printf '%s' "${f#"$T"/}" | LC_ALL=C tr -d '\000-\037\177')"
        say "$MSG_FILE_SAMENAME" "$shown" "$line"
        SAMENAME=$((SAMENAME + 1))
        break
      fi
    done <<EOF
$names
EOF
  done < <(find "$T/agents" \( -type f -o -type l \) -name '*.md' -print0)
}

# ---- Install ------------------------------------------------------------------
do_install() {
  local added=0 replaced=0 unchanged=0 src rel mode dest bk
  do_settings install 1 1
  say "$MSG_FILES_HEADING"
  while IFS="$(printf '\t')" read -r src rel mode; do
    if [ -z "$src" ]; then continue; fi
    dest="$T/$rel"
    if [ ! -e "$dest" ]; then
      say "$MSG_FILE_ADD" "$rel"
      added=$((added + 1))
      if [ "$DRY" -eq 0 ]; then
        mkdir -p "$(dirname "$dest")"
        cp "$src" "$dest" || die "$MSG_ERR_COPY" "$dest"
        chmod "$mode" "$dest"
      fi
    elif cmp -s "$src" "$dest"; then
      say "$MSG_FILE_UNCHANGED" "$rel"
      unchanged=$((unchanged + 1))
    else
      pick_backup_dir
      bk="$BACKUP_DIR/$rel"
      NEED_BACKUP=1
      say "$MSG_FILE_REPLACE" "$rel" "$bk"
      replaced=$((replaced + 1))
      if [ "$DRY" -eq 0 ]; then
        mkdir -p "$(dirname "$bk")"
        cp "$dest" "$bk"
        cp "$src" "$dest" || die "$MSG_ERR_COPY" "$dest"
        chmod "$mode" "$dest"
      fi
    fi
  done <<EOF
$PLAN
EOF

  scan_samename

  say "$MSG_SETTINGS_HEADING" "$T/settings.json"
  do_settings install "$DRY" 0

  # Manifest: header plus sorted destination paths. Rewritten only on change.
  local body
  body="# model-routing manifest
# Written by install.sh from claude-code-model-routing.
# Paths below are relative to the Claude Code config directory.
# install.sh --uninstall reads this list. Do not edit by hand.
$(printf '%s' "$PLAN" | cut -f2 | LC_ALL=C sort)"
  say "$MSG_MANIFEST_HEADING" "$MANIFEST"
  if [ -f "$MANIFEST" ] && [ "$(cat "$MANIFEST")" = "$body" ]; then
    say "$MSG_MANIFEST_UNCHANGED" "$MANIFEST"
  else
    say "$MSG_MANIFEST_WRITE" "$MANIFEST"
    if [ "$DRY" -eq 0 ]; then
      mkdir -p "$T"
      printf '%s\n' "$body" > "$MANIFEST"
    fi
  fi
  if [ "$DRY" -eq 1 ]; then
    printf '%s\n' "$body" | grep -v '^#' | while IFS= read -r l; do say "$MSG_MANIFEST_LINE" "$l"; done
  fi

  say "$MSG_SUMMARY_INSTALL" "$added" "$replaced" "$unchanged" "$SET_ADDED" "$SET_SKIPPED"
  if [ "$SAMENAME" -gt 0 ]; then say "$MSG_SUMMARY_SAMENAME" "$SAMENAME"; fi
  print_backup_summary
  say "$MSG_NEXT_HEADING"
  say "$MSG_NEXT_INSTALL_1"
  say "$MSG_NEXT_INSTALL_2"
  say "$MSG_NEXT_INSTALL_3"
}

# ---- Uninstall ----------------------------------------------------------------
do_uninstall() {
  local removed=0 moved=0 gone=0 rel src dest bk d paths
  do_settings uninstall 1 1
  if [ ! -f "$MANIFEST" ]; then
    say "$MSG_MANIFEST_MISSING" "$MANIFEST"
  else
    paths="$(grep -v '^#' "$MANIFEST" | grep -v '^[[:space:]]*$' || true)"
    # Refuse the whole run if any listed path could escape the target.
    while IFS= read -r rel; do
      if [ -z "$rel" ]; then continue; fi
      case "$rel" in
        /*|..|../*|*/..|*/../*) die "$MSG_ERR_BAD_MANIFEST_PATH" "$rel" ;;
      esac
    done <<EOF
$paths
EOF
    say "$MSG_FILES_HEADING"
    while IFS= read -r rel; do
      if [ -z "$rel" ]; then continue; fi
      dest="$T/$rel"
      if [ ! -e "$dest" ]; then
        say "$MSG_FILE_GONE" "$rel"
        gone=$((gone + 1))
        continue
      fi
      src="$(printf '%s' "$PLAN" | awk -F'\t' -v r="$rel" '$2 == r { print $1; exit }')"
      if [ -n "$src" ] && cmp -s "$src" "$dest"; then
        say "$MSG_FILE_REMOVE" "$rel"
        removed=$((removed + 1))
        if [ "$DRY" -eq 0 ]; then rm -f "${T:?}/${rel:?}"; fi
      else
        pick_backup_dir
        bk="$BACKUP_DIR/$rel"
        NEED_BACKUP=1
        say "$MSG_FILE_MOVE" "$rel" "$bk"
        moved=$((moved + 1))
        if [ "$DRY" -eq 0 ]; then
          mkdir -p "$(dirname "$bk")"
          mv "$dest" "$bk"
        fi
      fi
    done <<EOF
$paths
EOF
    # Remove directories the install made, only when empty.
    if [ "$DRY" -eq 0 ]; then
      while IFS= read -r rel; do
        if [ -z "$rel" ]; then continue; fi
        d="$(dirname "$rel")"
        while [ "$d" != "." ] && [ "$d" != "/" ]; do
          rmdir "${T:?}/${d:?}" 2>/dev/null || true
          d="$(dirname "$d")"
        done
      done <<EOF
$paths
EOF
    fi
  fi

  say "$MSG_SETTINGS_HEADING" "$T/settings.json"
  do_settings uninstall "$DRY" 0

  if [ -f "$MANIFEST" ]; then
    say "$MSG_MANIFEST_HEADING" "$MANIFEST"
    say "$MSG_MANIFEST_REMOVE" "$MANIFEST"
    if [ "$DRY" -eq 0 ]; then rm -f "${MANIFEST:?}"; fi
  fi

  say "$MSG_SUMMARY_UNINSTALL" "$removed" "$moved" "$gone" "$SET_REMOVED" "$SET_SKIPPED"
  print_backup_summary
  say "$MSG_NEXT_HEADING"
  say "$MSG_NEXT_UNINSTALL_1"
}

preflight

if [ "$UNINSTALL" -eq 1 ]; then
  do_uninstall
else
  do_install
fi

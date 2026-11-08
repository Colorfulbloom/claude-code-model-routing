# Edit architecture for the full editing scope (2026-11-08)

Scope from the owner: settings (all keys, arrays included), agents, rules folders, skills, hooks, CLAUDE.md and its imports, MCP config, output styles. Risky surfaces (hooks, statusLine, apiKeyHelper, MCP commands) are editable behind a stronger confirm step (20-decisions.md, last owner section). This file gives options and a recommendation. It is not a build plan.

## Recommendation

1. A surface registry, as data, names every editable thing. Each entry gives its scopes and path patterns, file format, allowed operations, validator, risk tier, when a change takes effect, and which combiner reports the effect. The client never sends a path. It sends project id, surface, scope, item name and an operation, and the server builds the path from the registry, as edit_store does now (/Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/edit_store.py:6, 210-238).
2. Typed operations for structured edits, plus one whole-text operation for markdown bodies and the raw view (option C below). The server plans the new bytes, validates them, works out the risk from the parsed before and after, and returns one preview shape for every surface.
3. edit_store stays the only writer, generalised from three settings files to any registry target. Keep the backup folder, file names, ledger version 1 and target id (23-domain-carryover.md B1). Add four optional ledger fields: `group`, `mode`, `via`, `surface`.
4. Four risk tiers. The server enforces the risky tier: a risky save must carry an acknowledgment hash of the exact risky text the preview showed. The page decides how that confirm looks, after the design freeze lifts.
5. Local and user MCP servers live in `.claude.json`, which Claude Code rewrites without a lock (26-08-write-races.md). The dashboard never writes that file. Owner decision below on whether it runs `claude mcp` itself or shows the command to copy.

## Options for the edit model

| Option | How it works | Gains | Costs |
|---|---|---|---|
| A. Whole file text | Client sends the full new text of any file; server validates and diffs | One code path, one diff shape | Client builds JSON and YAML, so formatting churn and lost comments; the server must infer what changed to judge risk; big diffs for one-key edits |
| B. Typed operations only | Client sends `{surface, scope, item, op, args}`; server plans the bytes | Minimal byte diffs (json_edit splicing), server owns paths and formatting, risk is known from the operation | Every surface needs its own operations; no free-form editing of markdown bodies |
| C. Typed operations plus whole text for text bodies (recommended) | B for JSON keys, array items, front matter fields, create and delete; a `replace_text` operation for markdown bodies and a raw view of any file | Keeps B's minimal diffs and adds free editing where text is the content; one preview shape | Risk on `replace_text` must come from a semantic compare of the parsed before and after, not from the operation name |

## Operations per surface

| Surface | Scopes writable | Format and edit kind | Operations | Notes |
|---|---|---|---|---|
| Settings keys | user, project, local | JSON, byte splice (json_edit) | `set`, `remove`, `insert_item`, `remove_item`, `replace_text` (raw) | Managed refused as now (edit_store.py:273-285) |
| Permissions | same | JSON arrays | `insert_item`, `remove_item` by value, resolved to an index under the lock | Rule syntax validator |
| Hooks in settings | same | JSON objects inside arrays | `insert_item`, `remove_item`, `set` on nested paths | Risky |
| `statusLine`, `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `otelHeadersHelper` | same | JSON | `set`, `remove` | Risky |
| `.mcp.json` | project | JSON splice | `set`, `remove`, `replace_text` | Commands and args risky |
| Local and user MCP | in `.claude.json` | not written by the dashboard | see owner decision | |
| Agents | user, project | YAML front matter round trip (ruamel.yaml, body bytes untouched) plus body text | `set_field`, `remove_field`, `replace_text`, `create`, `delete` | Front matter `hooks`, `mcpServers` risky |
| Skills | user, project | `<name>/SKILL.md` front matter plus body, plus other files in the folder | same as agents, plus `create_file`, `delete_file`, `delete_folder` (group) | `!`cmd`` lines, `shell`, `hooks`, executable files risky |
| Rules folders | user, project | markdown with optional `paths` front matter | `replace_text`, `set_field paths`, `create`, `delete` | |
| CLAUDE.md, CLAUDE.local.md, imported files | user, project, local; imports only inside allowed roots | whole text | `replace_text`, `create` | Managed read only. An import outside the project and config folders is read only with a reason |
| Output styles | user, project | front matter plus body | `set_field`, `replace_text`, `create`, `delete` | Takes effect after a restart (https://code.claude.com/docs/en/output-styles.md) |
| Plugin and managed items | none | read only | none | 26-03-plugin-collector.md |

json_edit needs two new operations. Today it can replace a value at any path, including an array index (json_edit.py:212-224), but it only inserts and removes object keys (json_edit.py:273-279, 281, 369). `insert_item` (at an index or the end) and `remove_item` (by index) follow the same splice-and-oracle pattern (json_edit.py:179-210). This is the main new core code for permissions and hooks.

Create and delete already have a model. A create writes an empty `.absent` backup and undo unlinks the file; edit_store also tracks a `.claude` folder it made and removes it only if empty (edit_store.py:669-671, 968-981, 1025-1028). Delete is the mirror: back up the bytes, unlink, and undo recreates. Item names for a new file come from a strict regex with no separators, as harness case paths do.

## Validators

Each validator returns errors (block the save) and warnings (allow it). A save refuses what Claude Code would skip, so the user never saves a file that silently stops loading.

- Settings: the schemastore schema, vendored and pinned (https://json.schemastore.org/claude-code-settings.json). Type errors on known keys block. Unknown keys warn, because the schema may lag (18-config-surfaces.md item 1). Strict JSON: no comments, no trailing commas, as json_edit already enforces (json_edit.py:54-70).
- Permission rules: a parser for `Tool(specifier)`, plus a warning when a deny or ask in any scope shadows a new allow (26-02-scope-combination.md).
- Hooks: event names, matcher shape, handler type (`command`, `http`, `mcp_tool`, `prompt`, `agent`) and its required fields (https://code.claude.com/docs/en/hooks.md).
- MCP: name shape, stdio (`command`, `args`, `env`) versus `http` and `sse` (`url`, `headers`), and `${VAR}` syntax (https://code.claude.com/docs/en/mcp.md).
- Agents: `agent_fields.json` (19 fields) and Claude Code's own name rules, such as no `:` and at most 256 characters (/Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/agent_fields.json:14). Skills need a matching `skill_fields.json`; that list is not gathered yet.
- Markdown: UTF-8, the 1 MiB cap edit_store already has (edit_store.py:71), import targets that resolve (warning), and import depth (warning).
- Output styles: `name`, `description`, `keep-coding-instructions`, `force-for-plugin` (output-styles.md).

## Symlinked dotfiles

Many setups link `~/.claude/settings.json`, `CLAUDE.md` or the `agents` folder into a dotfiles repo. Today edit_store refuses a symlinked leaf and any symlinked subfolder (O_NOFOLLOW, edit_store.py:88-89, 300-309) but follows a symlinked base folder (edit_store.py:359, 763; inference from the open flags).

| Option | Result | Risk |
|---|---|---|
| Refuse (today) | The item shows read only with "This file is a link" | Common setups can't be edited |
| Write through to the link target (recommended) | Resolve the link, check the target is a regular file owned by the user, run the same dir-fd walk on the target's folder, replace the target | The edit lands in the dotfiles repo, which is what the user wants. The preview must name the real path |
| Replace the link with a file | Breaks the user's setup | Never |

Under write-through, the target id is computed from the resolved path, so the ledger follows the real file. Non-link targets keep the same id formula, `sha256(join(realpath(base), *rel, name))[:16]` (edit_store.py:288-290), so existing backups still match. Two cautions from the docs and issues: a symlinked `.claude` folder makes `settings.local.json` count as repo-supplied for trust (https://code.claude.com/docs/en/permissions.md), and issue #5938 reported project deny rules ignored when user `settings.json` is a link (closed not planned, https://github.com/anthropics/claude-code/issues/5938). The preview should warn on both.

## Ledger and backups

Keep everything edit_store has: per-target folder `<config>/routing-dashboard/backups/<target id>/`, `NNNNNN-<edit id>.bak` or `.absent`, `ledger.json` `{"version": 1, "rows": [...]}`, 0700 folders and 0600 files, thread lock plus `flock` on `.lock`, read-back verify, retention of 20 rows (edit_store.py:69-84, 288-290, 554-562, 817-885, 1125-1158).

Additions, all optional fields so version 1 still reads:

- `group`: one id shared by every row of a multi-file operation, such as deleting a skill folder. Undo and restore act on the whole group, and pruning keeps or drops a group whole.
- `mode`: the file mode at backup time, so undo restores executable skill scripts. Today a replaced file keeps its mode and a new file gets 0600 (edit_store.py:450, 989).
- `via`: `splice`, `frontmatter`, `text`, `create`, `delete`, or `cli` for a Claude Code command.
- `surface`: the registry surface id, so history can be grouped by what the user edited.

[NEEDS CONFIRMATION: whether the current app's ledger reader ignores unknown row fields. If the old and new apps can run against the same backups folder, this decides whether the version stays 1.]

The SQLite database mirrors ledger rows for history views. The ledger files stay the source of truth (app-audit/architecture.md 5.4).

## The common preview shape

One shape for every surface, so the designer's single review rail can render any edit (app-audit/design.md, Joint list item 4). Field names are illustrative.

```
preview {
  surface, scope, item, op
  target: { display_path, real_path_if_link, layer, exists, writable, read_only_reason }
  files: [ { display_path, diff: { hunks: [ { old_start, new_start, lines: [ {kind: " "|"+"|"-", text} ] } ] } } ]
  effect: null | { applies: "live"|"new_session"|"restart"|"reload_plugins",
                   rows: [ { label, before: {value, status, source}, after: {value, status, source} } ] }
  validation: { errors: [ {code, line, text} ], warnings: [ {code, line, text} ] }
  risk: { tier: "safe"|"careful"|"risky", reasons: [text], ack: null | { hash, shows: [ {label, text} ] } }
  bases: { file: hmac, trail: hmac, others: { path: hmac|status } }
  history: { undo: row|null, backups: [row] }
}
```

- `files` holds one entry for single-file edits and several for a group. Diff text is masked with the same rules as reads (26-07-read-gate.md).
- `effect` comes from a per-surface effect provider over the combiners in 26-02. Settings use today's overlay-and-resolve preview (api_edit.py:1351-1379). Agents report pin-relevant fields. CLAUDE.md reports the load list and import chain. MCP reports which entry wins for that name. Hooks report the merged handlers for the event. Permissions report the merged lists and shadowing.
- `bases` keeps today's HMAC scheme: raw file bytes, the trail, and the other files, keyed by the launch (api_edit.py:66-67, 128-130, 1152-1172, 1348-1366). For a group, `bases.others` covers every file in the group.
- `history` reuses today's row fields (api_edit.py:1512-1558).

## Risk tiers

| Tier | What | Confirm |
|---|---|---|
| Read only | Managed files, plugin files, server-managed cache, files outside allowed roots, `.claude.json` | none |
| Safe | CLAUDE.md and rules text, agent and skill descriptions and bodies, output styles, model and effort keys, `deny` and `ask` rules | normal Save |
| Careful | `allow` rules, `additionalDirectories`, `defaultMode`, `env` (values masked), `enabledPlugins`, agent `tools` and `permissionMode`, skill `allowed-tools`, any delete | normal Save, warnings stated |
| Risky | hooks anywhere (settings, agent and skill front matter), `statusLine`, `subagentStatusLine`, `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `otelHeadersHelper`, MCP `command` and `args`, MCP `env` and `headers`, skill `!`cmd`` lines and `shell`, executable files in a skill, `disableAllHooks`, `defaultMode: bypassPermissions` | stronger confirm |

How the server enforces the risky tier:

- The preview lists each risky value in full in `risk.ack.shows` (the user's own command text, unmasked except secrets), with when it runs (event, matcher, or "on every status refresh").
- It returns `risk.ack.hash`, an HMAC over those texts keyed by the launch.
- Save must echo that hash. A save without it, or with a hash for different text, is refused. A raw-text edit that touches any risky key gets the same treatment, because risk comes from comparing the parsed before and after.
- The page shape for this confirm (second button, typed name, checkbox) is a design decision for after the freeze. The API needs only the hash.

## MCP in local and user scope

| Option | How | Gains | Costs |
|---|---|---|---|
| M1. Copy command (recommended for the first release) | The dashboard builds the exact `claude mcp add-json <name> '<json>' -s user` or `claude mcp remove <name> -s local` line and shows it to copy | Keeps "never run claude" (22-rules-engine.md), no race with `.claude.json`, no secrets in our process table | The user runs a command; no undo from the dashboard |
| M2. Dashboard runs `claude mcp` | Spawns the CLI with `-s local` or `-s user` (https://code.claude.com/docs/en/mcp.md); records a `via: cli` ledger row with before and after hashes of `.claude.json` | One-click | Runs claude from the server; `add-json` puts the server JSON, secrets included, in argv while it runs; undo must be the inverse command, not a byte restore, because restoring `.claude.json` would erase Claude Code's own later changes |
| M3. Splice `.claude.json` directly | json_edit on the file | Same machinery as settings | Lost updates when a session rewrites the file (26-08-write-races.md); rejected |

Recommendation: M1 now, M2 later only if the owner accepts running `claude` and argv exposure. Prefer `${VAR}` references over literal secrets in either case.

## Owner decisions needed

1. Local and user MCP: copy command (M1) or the dashboard runs `claude mcp` (M2).
2. Symlinked files: write through to the link target (recommended) or keep them read only.
3. The tier list above, in particular whether `allow` rules and `env` sit in Careful or Risky.
4. Rename of agents, skills and rules: leave it out of the first release, or support it as a delete plus create group.

## UNVERIFIED

- Skill front matter field list for a `skill_fields.json`.
- Whether the current app tolerates new optional ledger fields.
- That a symlinked base folder is followed today; inferred from open flags, not run.
- argv visibility of `claude mcp add-json` to other local users on macOS.
- The schemastore schema's coverage of current keys.
- No part of this design was spiked; the json_edit array operations are the first spike candidate.

# M6 build plan, Bar Tab Edit core

Written by the lead (deep-reasoner) on November 11, 2026, on branch `feature/bartab-m6` from `5e0aeec`, where M0 to M5 are committed and M5's CI is green. Revised the same day after the owner answered section 9 and the designer reviewed the plan (section 14), then a last time after the verifier's pass and the designer's edits-off boards. Sections 6.5 and 6.6 list what those two changed. This plan turns plan-a.md section 5, "M6. Edit core", into ordered tasks. M6 ships as two PRs, M6a and M6b, each with its own stop line and verifier pass. M6 is the first milestone that writes the owner's real files, so security comes first in every section. Nothing is installed, started or committed until the owner says go.

Sources are plan-a.md (sections 2 to 6, 9 and 10), m5-build.md (format), m0-spikes.md (spikes 4 and 5), research 26-01 (`docs/rebuild/research/26-01-edit-architecture.md`) and 26-08 (`26-08-write-races.md`), the M6 boards and their sources in the session scratchpad under `m6-design/` (`site/m6.js`, `m6.css`, `strings-m6.js`, `review-body.html`, shots `b-*` and `x-*`, published as artifact 8xYKvKCzWd7fdPHR79FAJp), the edits-off boards in `m6-design/shots-o/` (`o-insp`, `o-plugin`, `o-changes`, `o-route`, `o-restart`) with their strings in `m6-design/site/strings-m6o.js` (keys `eo_*`, drafted by tech-writer), the old write core (`dashboard/edit_store.py`, `json_edit.py`, `api_edit.py`, `server.py` and their tests), the launcher `app/bin/bartab.py`, the skill `.claude/skills/bartab-preview/SKILL.md`, and three scout inventories run on November 11 (old write core, new server, new web).

Absolute scratchpad path for the boards: `/private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/m6-design/`.

## 1. What M6 delivers

M6 lets the owner change a setting or an agent from Bar Tab and trust what happens to the file.

On a surface page, Edit opens one rail beside the inspector. The owner picks a value and a Save to row. Each Save to row shows its full path, its link target when the file is a link, and whether a value saved there would take effect or be overridden. Under the rows, a live "This save" summary shows the file, Set to, Runs at now and after, and the diff with real line numbers. All of it comes from a server preview that reruns on every change.

The Save button names its destination ("Save to Project local") and never swaps places with another button. Save holds until This save shows the preview for the current choice, so the owner never writes a value whose diff he hasn't seen. "Saved." shows at once with Undo. A moment later, a recheck reads the file again and confirms the change, or reports that another program overwrote it. Review changes then shows what the other program changed since the save.

The agent form is one full page for both new and edit, opened from the Agents page. Role presets fill real fields. Custom shows once the form differs from every preset, and the role is never saved. The side column is "This save", which shows the whole file the save would create or the diff it would make. A name check shows, for each Save in row, whether the name is free and which file would win.

A Changes page under Your setup lists every save for the project, newest first, with its undo state and its recheck outcome. It also lists older backups and shows the real backup folder. Every "Saved." message links to it, and it adds no sidebar item. It works with edits off. Only Undo needs edits on.

Every write goes through one server writer, and that writer knows only a fixed list of files. When a file is a link, it writes through to the real target and shows that path. It backs up the old file first, refuses when the file changed after the preview, and writes atomically. Then it records the save in the same ledger the old app reads.

Edits are off unless the server starts with `--allow-edits`. That is the state the owner sees on most starts, so it is designed too. Edit stays in place, disabled but focusable, with a reason line that names the server's own launch command plus `--allow-edits`. The sidebar foot, and the More page on phones, say "Editing off" or "Editing on". If Bar Tab restarts while a page is open, the page notices before Save and says so at once.

### Two PRs

| PR | Scope | Owner sees at the end |
|---|---|---|
| M6a | The edit switch and keys, the write core, settings edits, the Changes page, the edits-off state, and the agent entry points held back | Change effort on a throwaway project, see the effect and diff, save, see "Saved." and the recheck, undo, and find it all on Changes. With edits off, every page says why and how to turn them on |
| M6b | The front matter writer, the agent API and the agent form for new and edit, plugin agents read-only | Add an agent from a preset, edit an existing one, and undo both |

In M6a, "Add an agent" and agent Edit don't appear. Both agent routes redirect at route level, `review/agents/new` to the Agents page and `review/agents/<name>/edit` to that agent on it, so neither renders the placeholder's `ph_body` (`app/web/src/strings/en.ts:173`) any more (designer item 34). `ro_m6` (`en.ts:865`) has no caller in `app/web/src`, so a1 removes it, and the agent reason words say agent editing comes next without naming a milestone (item 35).

### Deferred, and why

| Item | Lands in | Why |
|---|---|---|
| Editing an existing agent's system prompt, CLAUDE.md, rules files | M7 | Needs CodeMirror and `replace_text` (plan-a M7). New agents get a plain text area in M6b (owner, question 3) |
| Array edits (allowed models, fallback models, deny and ask rules) | M7 | Spike 4 ported `append_item` and `remove_item` to M7 (`docs/rebuild/planning/m0-spikes.md:40`) |
| `hooks`, `mcpServers`, `permissionMode` on agents, and every risky settings key | M8 | They run commands or loosen permissions. Shown read-only with reason code `risky_until_m8` |
| Runs at for each model option before it's picked | Not planned | Designer item 11 is met for the effort and effort cap options. A model list has many options, and each would need a resolver run per keystroke. The picked model still shows Runs at |
| "Copy to my agents" for plugin agents | Later | Owner, November 11 |
| Delete, rename, group undo | Later | plan-a section 2, "Explicitly later" |
| `ledger_mirror` in SQLite | Later, only if history gets slow | Owner, question 6. Ledger files are the source of truth (26-01) |
| `.claude.json` writes of any kind | Never | 26-08 recommendation. Claude Code rewrites it with no lock |

## 2. Decisions this plan makes

Owner answers are in section 9. The designer's items are mapped one by one in section 6.3.

| Item | Pick | Why |
|---|---|---|
| Edit switch | `--allow-edits` is a `start` option of `app/bin/bartab.py`, passed on to `serve.py --allow-edits`. Off by default | Owner, question 1. The skill puts `$ARGUMENTS` after the global options (`.claude/skills/bartab-preview/SKILL.md:9`). `parse_args` makes an unprefixed option list a `start` (`app/bin/bartab.py:1484-1486`) and reads it with `parse_options` (`:1455-1476`). So `/bartab-preview --allow-edits` reaches `start` with no skill change once `ACTIONS["start"]` (`:1263-1266`) lists the option. The skill's `argument-hint` (`SKILL.md:4`) gains it, so the owner sees it |
| Launcher modes | The launcher records the running mode (`edits: true` or `false`) in the run record it already reads through `live_server` (`app/bin/bartab.py:2485`). `start --allow-edits` beside a server running with edits off stops it and starts it again with edits on, and open tabs get the restart box. A plain `start` or `code` beside a running server keeps its mode and prints "Editing is on" or "Editing is off". A code minted that way carries the rights of the running mode, and the output says so plainly. To turn edits off, stop, then start | Main session decision under the owner's standard. The owner typed the command, so that is the intent. Only the local user can run the launcher |
| Edits state | `GET /api/app` gains `edits {state, instance}`. `state` is `on`, `off` or `unavailable` (demo and fixture runs whose folders sit in the checkout). `instance` is the server instance id (`app/server/access.py:71`). `GET /api/projects` gains `edit_block` per project, null when editable | Designer item 2. An empty `editable_projects` (`app/server/models.py:127`) can't tell "edits off" from "this project can't be edited" |
| When a project is not editable with edits on | Only `folder_not_found`. A project with no `.claude` folder is editable, because the writer makes that one folder and records it as `made_dir`, as the old app does (`dashboard/edit_store.py:972-977`). Every other block is per item, not per project. That covers plugin agents, managed settings and the reason codes | Designer's new need 8. So item 2's "this project can't be edited" words appear only for a missing project folder, and the plugin case is per item |
| Reason line words | The `eo_*` strings in `m6-design/site/strings-m6o.js` with `{cmd}` filled from the page's `bartab-command` meta tag (`app/server/csp.py:133`, read at `app/web/src/lib/launch.ts:25`) plus ` --allow-edits`. Nothing is baked in, so the skill shows `/bartab-preview --allow-edits` and a demo or launcher start shows its own command. tech-writer confirms in a1 that "Start Bar Tab with ..." stays true under the launcher modes above | Owner, November 11, and the designer's new need 1 |
| Edit keys | One key per project per server run, `secrets.token_urlsafe(32)`, held in memory only. A swap returns the key for the code's project in `edit_keys` when edits are on (`app/server/access.py:173` returns `{}` today). The page already stores and hands off `bartab.editKeys` (`app/web/src/app/access.ts:43-45`) | plan-a section 3, "the project's edit key" |
| Write header | `X-Bartab-Edit` on every edit write, beside `X-Bartab-Key` | Custom headers force a CORS preflight that the server never answers |
| Routes mounted with edits off | History, the recheck read and "mark seen" are always mounted. Preview, save and undo are mounted only with edits on. With edits off they answer `{code: "edits_off"}`, not a bare 404 | Designer item 1 (blocker). Changes must work on the default start |
| plan-a's `GET /api/edit/targets` | Replaced by `scopes[]` in the preview answer | One call gives the rows, their paths and their outcomes, so the rail never draws rows from one read and outcomes from another |
| Writer thread | Each preview, save and undo runs the whole writer in one worker thread (`run_in_threadpool`), with no `await` while a permit is active | The permit is thread-local (3.5). An `await` inside it could resume on another thread or let another request run under it |
| Local layer | The local file is chosen exactly as the old `target_for` and `project_files` choose it (`dashboard/edit_store.py:210-270`). The root file under the version rule is writable. When the starting folder has its own `settings.local.json` as a leftover, it is a fourth file that is read-only to edits but reachable by undo of its old rows. So a project has up to four settings files | Parity with the old app's rows. a4's interop test compares the choice on the same fixtures |
| Field registry | `app/server/edit_fields.py`. Settings fields model, effortLevel, maxEffortLevel and autoCompactWindow, each edited at the key path the resolver reports for that file (top level, an `env` twin such as `env.CLAUDE_CODE_EFFORT_LEVEL`, or a `modelSettings` entry). A file that doesn't set the field gets the top-level key. Thinking, cache lifetime and the model lists get reason code `field_until_m7` | Owner, question 4. Fact C-1ff9 names the four keys. The board edits `env.CLAUDE_CODE_EFFORT_LEVEL` in Project local (`m6-design/site/m6.js:30`). Designer item 14 |
| Agent fields | Description, model, effort, color, tools, disallowedTools, skills, maxTurns, background, isolation, memory, omitClaudeMd and autoCompactWindow. `initialPrompt` and `experimental` get `field_until_m7`, an existing body `body_until_m7`, and hooks, mcpServers and permissionMode `risky_until_m8` | Owner, question 5. Designer item 31 |
| Backup and ledger folder | The old app's folder, `<config>/routing-dashboard/backups/<target id>/`, where `<config>` is `CLAUDE_CONFIG_DIR` or `HOME/.claude` (`app/server/store_paths.py:37-42`). Same backup names, same `ledger.json` version 1, same `.lock`, same 20 newest rows per file, no age expiry. The page names the real folder | Owner, question 7. Old constants at `dashboard/edit_store.py:70-75`, prune at `:1125-1158` |
| Target id | `sha256(fsencode(realpath(file)))[:16]` | The old id hashes `join(realpath(base), *rel, name)` (`dashboard/edit_store.py:288-290`). That is the same string for every file the old app can edit, because it refuses links. Task a4 proves the two agree |
| Version token | The token is a base64url JSON payload `{v: 1, target_id, dev, ino, sha256, body_sha256, read_at}` plus an HMAC-SHA256 tag under a per-run secret. The server checks in a fixed order. A bad tag or a payload from another run is `bad_version`. A `body_sha256` that differs from the sent body's is `preview_mismatch`. A `dev`, `ino` or `sha256` that differs from the file now is `changed` | Separate fields let the server tell the two refusals apart. Binding the body means a save with another value is refused (designer item 9, enforced on the server too) |
| Canonical body | The request parsed by its pydantic model, dumped with `model_dump(mode="json")`, with `seq`, `version` and `request_id` removed, serialized as UTF-8 JSON with sorted keys and no spaces (`separators=(",", ":")`, `ensure_ascii=False`). `choice_key` is its sha256. The page computes nothing. It holds Save until the latest answer's `seq` is its latest request and that answer has no pending successor | One definition on the server, so page and server can't disagree on spacing or key order |
| What changed on disk | The server keeps each preview's bytes in an in-memory cache keyed by token (64 entries, 1 MiB each). A refusal diffs them against the file now | The designer's need for "what changed on disk" in the refusal. After a restart, the refusal says the file changed with no key list |
| Double presses | Every save and undo carries a `request_id`. Under the per-target lock the writer marks the id in flight before any write. A repeat while in flight waits for the first result. A repeat within 10 minutes gets the first result. The same id with a different canonical body is refused with `request_reused` | Without it, a second press of Save sends a stale token and shows a false refusal. The in-flight mark stops two presses racing past the cache |
| Recheck | The writer schedules two read-only checks, at about 2 s and 10 s after the save, and stores the result on the ledger row. `GET /api/edit/rows/<id>` only reads it | 26-08 recommends about 2 s then once more. A server-side check still runs when the owner leaves (designer item 19) |
| What another program changed | The writer rebuilds the bytes it wrote by applying the row's operation to the backup and checks them against the row's `after_sha256`. `GET /api/edit/rows/<id>/drift` returns the masked diff from those bytes to the file now. A hash mismatch returns `cant_rebuild` | Designer item 17 (blocker), owner's pick of an inline diff. No new file type in the backups folder, so the old app's prune is unaffected |
| Overwritten seen | `POST /api/edit/rows/<id>/seen` stores the row id in the `prefs` table, inside the store root, so it works with edits off | Designer item 18. The ledger lives outside the store root and needs edits on |
| History | Read straight from ledger files. New rows carry `project`, `display_path`, `real_path`, `field`, `subject` and `scope`, so a scan of `backups/*/ledger.json` finds rows for files that no longer exist. Old rows match through the ids of the project's three settings files, with subject "main session" | Owner, question 6. Old rows carry no path. The old reader ignores unknown row fields (`dashboard/edit_store.py:782-800`). Designer item 21 |
| Changes page | Route `#/p/<project>/setup/changes`, parsed before `setup/<part>` (`app/web/src/app/routes.ts:167` handles `setup` today). "Your setup" stays the current sidebar item | Owner, November 11 |
| Shared project line | Shown only when `git ls-files --error-unmatch` lists the file. The call follows the old hardening in `dashboard/git_check.py:295-305`. `--no-lazy-fetch`, `-c core.fsmonitor=false`, a fixed argument list ending in `--`, an environment of only `PATH`, `HOME` and `GIT_NO_LAZY_FETCH=1`, the project root as `-C`, and a 2 s timeout. A new file gets no line | Owner, November 11. The hardening stops a project's `.git/config` from running a program |
| Front matter | Byte splicing for single-line scalars and for `tools` or `disallowedTools` as a comma string. ruamel 0.19.1 with a byte-equality guard only for list-form `tools`, `disallowedTools` and `skills`. A guard failure refuses with `frontmatter_drift` | Spike 5's decision (`docs/rebuild/planning/m0-spikes.md:50`). ruamel is pinned in `app/pyproject.toml` |
| New agent body | The role's starter text in a plain React Aria TextArea, saved as the file body | Owner, question 3 |
| String ownership | Only the lead edits `en.ts`, `help.ts`, `glossary.ts`, `lists.ts`, `models.py`, `edit_fields.py`, `conftest.py` and the skill's `argument-hint`. Workers edit pages, components and their own modules | As in M4 and M5 |

## 3. Security model

Every item has a test in section 11.

### 3.1 Edits are off unless enabled

- `--allow-edits` exists on `app/bin/bartab.py start` and on `serve.py`. Without it, preview, save and undo answer `edits_off`, `editable_projects` is `[]`, `edit_keys` is `{}`, and `write_guard.permit` raises.
- History, the recheck read and "mark seen" stay mounted, because they write nothing outside the store root.
- With `--allow-edits`, the write guard is installed in every mode, not only real mode (today `app/server/serve.py:294` installs it for real mode). So every server that can edit refuses writes outside its roots and permits.
- "Real home" means `realpath(HOME)` everywhere in this plan.
- In fixture and demo mode, `--allow-edits` is refused unless `--claude-dir` and every project root sit outside the Bar Tab checkout and outside any git work tree that contains it, as `_tmp_base` does for tests (fact T-c826). The state is then `unavailable`. So a test can never write into `tests/fixtures/` or `app/fixtures/`.

### 3.2 Gate, keys and origin

- The existing gate stays in front (`app/server/gate.py:137-151`). It checks Host, Origin, Sec-Fetch-Site, JSON Content-Type, the 64 KiB body, 3 s body time, and `X-Bartab-Key` with `hmac.compare_digest`.
- Edit writes add three rules in the gate. Origin must be present and equal the server's origin (today it is checked only when present, `gate.py:156-157`). `X-Bartab-Edit` must appear exactly once. The key must belong to the project named in the body, compared in constant time.
- A wrong or unknown edit key answers `edit_key_unknown`. With edits off the answer is `edits_off`. The page shows the restart box for both and returns the rail to read-only (designer item 6, board `o-restart`).
- The page notices a restart before Save. It knows the instance it loaded under from the `bartab-instance` meta tag (`app/server/csp.py:132`, read at `app/web/src/lib/launch.ts:24`). A key handoff on the access channel or an `/api/app` answer with another `edits.instance` shows the restart box at once, with Save held. The box and the foot line then use the new server's mode, `eo_restart_h` and `eo_restart_b` for edits off and `eo_restart_on_h` and `eo_restart_on_b` for edits on. A restart that leaves the tab without a valid read key reaches the M0 lost-gate page instead (`app/web/src/api/client.ts:205-208`).
- A user-scope edit uses the current project's key, and the preview lists every project it reaches (owner decision O2).
- No key is ever in a URL, a log line, an error body, a ledger row or a backup name. Only the swap answer carries edit keys. No CORS middleware is added.
- Tests assert "refused" rather than exact codes where the gate answers, as M0 did.

### 3.3 Writable allowlist

- No path ever comes from the client. The client names a project key, a scope (`user`, `project`, `local`) and a field, or an agent name and a Save in scope. The server builds the path.
- Settings paths are `<config>/settings.json`, `<project>/.claude/settings.json` and the local file the old `target_for` would pick (section 2, "Local layer"), with `app/server/git_root.py:86` checked for parity in a4. A leftover local file makes up to four, and it is never written by a new save. Agent paths are `<config>/agents/<name>.md` and `<project>/.claude/agents/<name>.md`.
- These are never writable, checked after resolving every link. Managed settings and the managed folder, plugin folders and the plugin cache, any `.claude.json`, the Bar Tab store root, and the backups folder itself.
- Agent names are checked before any path is built. No path separator, no `..`, no leading dot, no control or format characters, NFC-stable, at most 255 bytes as a file name, and no colon. A failure is `bad_name`.
- Create uses `O_EXCL`, so it never overwrites. A name whose file exists in that scope is refused with `exists`.
- As in the old app, these are refused. Not a regular file (`dashboard/edit_store.py:295-316`), and a hard link (`st_nlink` over 1), not owned by the user, or over 1 MiB (`edit_store.py:387-395`).

### 3.4 Symlinks, written through to the target

- A link at the leaf or at `.claude` is followed to its real file. The rail, This save, the diff header, the phone foot, the ledger row and the Changes page all show the real path beside the display path.
- The real file must live under the real home folder or the real project root. Anything else is refused with `link_outside` (owner, question 2). A dangling link is refused with `link_dangling`.
- The local layer also allows a real path under the git root that holds it, because that file lives at the git root.
- The real file then passes every check in 3.3, so a link to a never-writable path is refused.
- Links are resolved once, at check time, to a real path. From then on the writer never follows a link. It opens a trusted base (the real home folder or the real project root) with `O_DIRECTORY | O_NOFOLLOW`, then walks each component of the real path below it with `O_NOFOLLOW`, as the old `_open_step` does (`dashboard/edit_store.py:317`, used at `:359-382`). A component that has become a link since the check fails the walk and refuses with `changed`.
- The writer records the folder's `(st_dev, st_ino)` from `fstat` at check time and compares them again at write time, before the rename. A difference refuses with `changed`. That closes the gap between checking a folder link and writing through it.
- The temp file goes in the real folder and is renamed onto the real file, so the link itself stays.

### 3.5 The runtime write guard

Real mode installs an audit hook that refuses every write outside the store root (`app/server/write_guard.py:311-327`, called at `app/server/serve.py:294`). M6a adds two things.

- `install(..., extra_roots)` adds `<config>/routing-dashboard/backups` only when edits are on. The store root is `<config>/routing-dashboard/bartab` (`app/server/store_paths.py:45-47`), so the backups folder sits beside it, not inside.
- `write_guard.permit(target)` is a context manager for the current thread only. It names exact files. Those are the real target, temp files matching `.routing-dashboard-<16 hex>.tmp` in the real target's folder, and for a create the one `agents` folder it may make. Only `edit_store.py` calls it, and only for a target the registry built.
- The permit binds folders by identity, not by name. It holds the `(st_dev, st_ino)` of each permitted folder, taken by `fstat` of the folder fd the writer opened in 3.4.
- Today a bare name under any `dir_fd` is allowed (`app/server/write_guard.py:51-55`, `:133-134`), and `os.open(name, dir_fd=)` raises its audit event with no `dir_fd`, so it is judged against the working folder. With edits on, the hook changes two rules.
  - A bare name under a `dir_fd` is allowed only when `fstat(dir_fd)` matches a folder the current thread's permit holds, or a folder inside the store or backups roots. `os.fstat` raises no audit event, so the hook doesn't re-enter itself.
  - A write `open` with a relative path is refused. The writer opens every file it writes by absolute path, after the fd checks, then confirms with `fstat` on the new fd and `os.stat(name, dir_fd=folder_fd, follow_symlinks=False)` that the file sits in the checked folder.
- Renames and removes pass `src_dir_fd` and `dst_dir_fd`, which the hook judges by the same identity rule.
- Tests run in subprocesses, because the hook can't be removed. They include a rename by `dir_fd` into a folder the permit doesn't hold, a bare-name write under an fd for an outside folder, and a relative write `open`. All three are refused.

### 3.6 Backup, atomic write and verify

Ported from `_apply` (`dashboard/edit_store.py:932-1038`), in this order under the per-target lock.

1. Take the threading lock and the shared `fcntl.flock` on the target folder's `.lock` (opened `O_NOFOLLOW`, 0600, retry every 0.02 s for 5 s, `edit_store.py:827-852`). The old app takes the same lock, so the two apps exclude each other.
2. Mark the `request_id` in flight. Walk to the real file (3.4) and read it once. Check the token in the order section 2 gives. A mismatch refuses with `bad_version`, `preview_mismatch` or `changed`.
3. Write the backup `NNNNNN-<edit id>.bak` with `O_EXCL`, 0600, folders 0700, and fsync it. A missing file gets an `.absent` marker.
4. Write the ledger row to a temp file and rename it into place.
5. Write the new bytes to the temp file in the real folder (`O_EXCL | O_NOFOLLOW`, 0600, then the old file's mode), `F_FULLFSYNC` on macOS.
6. Walk again and compare device, inode and bytes with step 2. A change refuses with `changed` and removes the temp file.
7. Rename by `dir_fd`, fsync the folder, read back and compare. A mismatch is `raced`, and the row says so.
8. Prune to the newest 20 rows per file with the old orphan rules.
9. Schedule the two rechecks.

The window between step 6 and step 7 can't be closed, because Claude Code takes no lock (26-08). The recheck covers it.

### 3.7 Changed-file refusal and the version token

- Preview returns `version` and `read_at`. Save sends the same body plus `version`.
- A file that changed returns 409 `changed` with a fresh preview, the keys that changed on disk, and whether the edited key was among them. Nothing is written.
- A body that differs from the previewed one returns 409 `preview_mismatch` with a fresh preview for the body sent.
- Undo of a file unchanged since its save applies at once. Undo of a changed file returns 409 `changed_since_save` with an undo preview and its own token. "Undo anyway" sends that token. Force skips only the hash check against the saved row, as in the old app (fact S-fe14), never the token.
- Undo, restore and drift never trust a row's path. They rebuild the target from the registry for the project the edit key belongs to, then check that `sha256(fsencode(realpath))[:16]` equals the ledger folder's id and that the row's `project`, when present, equals the key's project. Any mismatch is `forged_row`. a4 ports `ForgedRowTests` (`tests/test_edit_store.py:2873`).

### 3.8 Front matter byte equality (M6b)

- Splice methods replace only the bytes of one value on one line and keep the line ending and quoting style.
- A value that needs quoting is written double-quoted with YAML escapes. A multi-line or block scalar sends the edit to the ruamel path.
- The guard compares every line outside the edited key's span, front matter and body, byte for byte. A difference refuses with `frontmatter_drift`.
- CRLF, a BOM, and a missing closing fence are refused with `frontmatter_unsupported`.
- Can start other agents follows N2. Off removes `Agent` from a limited `tools`, or appends `disallowedTools: Agent` when `tools` is omitted.

### 3.9 Masking and leaks

- Masking is span-aware. Before a diff is built, both sides are masked as whole texts. The JSON parser finds the value span of every secret-looking key or value (`json_edit.value_span`, rules from `app/server/masking.py`), and the same spans are replaced on both sides. Then the diff runs. So a context line, a value that spans lines, or a line that holds part of a secret never shows it. Ledger values and history values run through the same masker.
- Backups keep raw bytes, because Undo needs them. They are 0600 in 0700 folders.
- The leak test runs every edit flow on a throwaway setup, then searches every response body, captured log line, ledger row and backup file name for the read key, the edit keys, the mint secret, the access code and a planted secret value. Any hit fails.

### 3.10 Tests never touch the owner's files

- Every pytest runs under the session `fake_home` (`app/server/tests/conftest.py:137-143`) with the real-folder audit guard (`conftest.py:40-113`). New fixtures `edit_config` and `edit_project` make a config folder and a project tree in `tmp_path`, outside any git work tree.
- E2E servers start with `--allow-edits`, a copied fixture tree in the test's temp folder and `--claude-dir` there, which 3.1 enforces. `app/web/e2e/server.ts` spawns `serve.py` with no `env` today (`:130-133`), so it inherits the real `HOME`. a2 makes it pass `HOME` and `CLAUDE_CONFIG_DIR` set to the test's temp home, for every server, edits on or off.
- No agent reads `~/.claude`, `~/.claude.json`, real transcripts or real settings, runs the launcher, uses real-data mode, or reads `server.json` or a launch descriptor. Launcher changes are tested as subprocesses in temp folders, as M0 did.

## 4. Server

### 4.1 Modules

| Module | PR | Contents |
|---|---|---|
| `json_edit.py` | M6a | Verbatim port of `dashboard/json_edit.py`, pure, no I/O. No array functions |
| `edit_store.py` | M6a | The one writer (fact E-5b16 carries over). Targets, refusals, links, lock, backup, ledger, atomic write, verify, prune, create, undo, tokens, preview cache, request ids, rechecks, rebuilt after-bytes |
| `edit_fields.py` | M6a, extended in M6b | The registry. Settings fields with key paths, value checks and reason codes. Agent fields with write method (`splice`, `ruamel_guarded`, `read_only`), control kind and reason code |
| `edit_preview.py` | M6a | Builds a preview. Runs the resolver with the candidate value in a copied layer for Runs at after, the outcome per scope, and Runs at per option for enum fields |
| `api_edit.py` | M6a | Routes in 4.2, split into an always-mounted router and an edits-on router |
| `git_tracked.py` | M6a | The tracked check, cached on the file's stat signature |
| `access.py`, `gate.py`, `serve.py`, `write_guard.py`, `api_app.py`, `app/bin/bartab.py` | M6a | Keys, write rules, the flag, `edits` state, `permit`, the launcher option |
| `agent_write.py` | M6b | Splice and guarded ruamel edits, the new-file renderer, N2 mapping, the guard |
| `api_agent_form.py` | M6b | Agent form, name check, tool and skill lists |
| `data/tool_names.json` | M6b | Claude Code tool names with the docs URL and date they were read from |

### 4.2 Routes

All answers carry `server_time`. Edit writes need `X-Bartab-Edit`. GETs need only the read key.

Always mounted.

| Route | Answer |
|---|---|
| `GET /api/edit/history?project=` | `rows[] {id, time, subject {kind, name}, field, from, to, scope, display_path, real_path, op (set, create, undo, restore), undo_state (can_undo, changed_since, undone, deletes_file, not_undoable), undone_at, recheck {state, changed_keys, ours_survived, seen}, not_undoable_reason}`, `older {count, rows[]}`, `backup_folder {display, real}`, `edits` |
| `GET /api/edit/rows/<id>?project=` | `{state (checking, confirmed, overwritten), changed_keys[], ours_survived, checked_at, seen}` |
| `GET /api/edit/rows/<id>/drift?project=` | `{lines[] {kind, old_n, new_n, text}}` from the bytes Bar Tab wrote to the file now, masked, or `{code: "cant_rebuild"}` |
| `POST /api/edit/rows/<id>/seen` | Stores the seen mark in `prefs`. Read key only |
| `GET /api/edit/open?project=&item=` | The latest overwritten row not yet seen for an item's files, so the inspector shows the warning again (designer item 18) |

Mounted only with edits on. With edits off each answers `{code: "edits_off"}`.

`POST /api/edit/preview`. Body `{project, op, scope, field, value}` for settings (`op: "set"`). In M6b also `{project, op: "create_agent", save_in, fields, body}` and `{project, op: "agent_set", name, scope, fields}`. Plus `seq`.

| Field | Contents |
|---|---|
| `seq` | Echoed, so the page drops answers older than its latest request |
| `choice_key` | sha256 of the canonical body without `seq`. The page holds Save until it equals the key of the current choice |
| `target` | `scope`, `display_path`, `real_path`, `link`, `exists`, `git_tracked`, `new_file` |
| `effect` | `set {from, to}`, `runs {now {value, status}, after {value, status}}`, `applies` (`new_session`, `new_run`, `picked_up`) |
| `options[]` | For effort and effort cap, each option with the value it would run at and its status in the picked scope (designer item 11) |
| `scopes[]` | One row per writable scope. `scope`, `display_path`, `real_path`, `link`, `git_tracked`, `writable`, `read_only_reason`, `current_value` (designer item 12), `outcome {status, beaten_by}` if saved there |
| `reaches[]` | Projects a user-scope save changes, with each one's outcome (O2) |
| `warnings[]` | `{code, params}`. `wont_win`, `name_clash`, `config_change_hook` (26-08), `shared_repo` |
| `diff` | `lines[] {kind, old_n, new_n, text}` with real line numbers, `new_file` |
| `file` | M6b. The whole agent file after the save as `lines[] {n, text}` |
| `tools_mapping` | M6b. Final `tools` and `disallowedTools` and which N2 rule applied |
| `summary` | `{verb (creates, changes), lines_changed, display_path}` for the phone bar |
| `read_at`, `version` | Read time and the token |
| `refusal` | `null` or `{code, params}` when a save to the picked scope would be refused, such as `link_outside` |

`POST /api/edit/save`. The preview body plus `version` and `request_id`. 200 `{row_id, saved_at, recheck_after_ms}` at once. 409 `changed` or `preview_mismatch` returns `{preview, changed_keys[], edited_key_changed}` in one answer. 422 returns `{code, params}` for the refusals in section 3.

`POST /api/edit/undo`. `{project, row_id, request_id}`, plus `version` and `anyway: true` for the confirm. 200 `{row_id}`. 409 `changed_since_save` returns `{undo_preview {diff, version}}`. A create's undo deletes the file and an empty `agents` folder the save made (`made_dir`, `rmdir` by `dir_fd`, fact E-6ccf).

M6b adds `GET /api/agents/<name>/form?project=&scope=` (every field from `app/server/data/agent_fields.json` with `value`, `line`, `writable`, `method`, `control`, `read_only_reason`, `risk_tier`, `ignored` for plugin agents, plus `source {scope, plugin}`, `display_path`, `real_path`, `body`, `body_bytes`, `version`, and `options {tools[], skills[]}`) and `GET /api/agents/name-check?project=&name=` (`{valid, invalid_code, scopes[] {scope, display_path, real_path, exists, winner {scope, display_path}}}`). A model name outside the catalog is checked by `GET /api/models/check?name=` against `app/server/model_catalog.py`, answering `known`, `alias` or `unknown` (designer item 27).

`GET /api/app` gains `edits {state, instance}` and `GET /api/projects` gains `edit_block`. OpenAPI and `schema.d.ts` are regenerated in each PR.

Size. The gate's 64 KiB limit (`app/server/gate.py:30`) applies to the serialized request bytes, not to the agent body alone. The agent form counts the UTF-8 bytes of the JSON it would send, including escapes, for its size note and refusal.

The M6b name check compares the front matter `name` of every agent file in both scopes, case-insensitive, not the file names. A file whose name differs from its front matter still clashes by its front matter name.

### 4.3 Ledger rows

New rows keep every old field (`dashboard/edit_store.py:862-885`) and add `project`, `display_path`, `real_path`, `field`, `subject`, `scope`, `app: "bartab"`, `request_id` and `recheck {state, changed_keys, ours_survived, at}`. The new reader accepts old rows, where `real_path` falls back to the path the target id names. Task a4 writes with each app and reads with the other.

## 5. Web

### 5.1 Data layer

`app/web/src/api/edit.ts` holds `postEdit()`, which adds `X-Bartab-Key` and the project's `X-Bartab-Edit` from `access.getEditKeys()` (`app/web/src/app/access.ts:79`).

- `usePreview` debounces 250 ms, aborts the previous request, keeps only the latest `seq`, and reports `pending` while the latest choice has no matching `choice_key`.
- `useSave` refuses to send while `pending`. A press during `pending` is held and sent once the matching preview has rendered, or dropped if the choice changes again.
- A 409 puts the fresh preview in the cache and returns the changed keys.
- After save, undo or a settled recheck, the hooks invalidate the setup part, the item, the Agents queries and `/api/app`, so list chips, Where it's set rows and the To fix count update (designer item 13).
- `useRecheck` reads the row at about 2 s and 10 s and stops. `useDrift`, `useHistory`, `useOpenWarning` and `useMarkSeen` wrap the always-mounted routes.
- `edits_off`, `edit_key_unknown` and an `edits.instance` that differs from the loaded instance map to one restart state, which holds Save and shows the restart box at once (3.2). The hook then reads `/api/app` for the current mode. Other errors map to reason codes, never raw server text.

### 5.2 Edits off (M6a)

The boards are `o-insp`, `o-plugin`, `o-changes`, `o-route` and `o-restart` in `m6-design/shots-o/`, at 375 and 1440, light and dark. Their words are the `eo_*` keys in `m6-design/site/strings-m6o.js`.

- Edit stays in the inspector foot (`app/web/src/pages/setup/ItemInspector.tsx:194`), `aria-disabled` and focusable, with one visible reason line under it tied by `aria-describedby` (`eo_reason`, `o-insp`). No tooltip. `{cmd}` comes from the `bartab-command` meta tag plus ` --allow-edits` (section 2, designer item 3 and new need 1).
- A project folder that is missing shows its own reason instead (item 2). With edits on, that is the only project-level block (section 2).
- An edit URL opened with edits off renders the item page with `eo_route` above it, and focus moves to that note, not the h1 (item 5, new need 7, `o-route`).
- The disabled label and reason line keep AA text contrast in both themes. The sheet test checks it (item 8).
- `footerLines` (`app/web/src/lib/history.ts:50`, rendered at `app/web/src/app/Shell.tsx:289-290`) takes the edit mode as a new argument and adds `eo_ft_off` or `eo_ft_on` (item 7, new need 5).
- On phones the sidebar foot isn't shown, so the More page carries the same line in its history card, beside the facts it already shows (`app/web/src/pages/MorePage.tsx:20-38`) (new need 6).
- The line opens a new help entry, `shell.editing` (`eo_help_h`, `eo_help_b`) (new need 4).
- The Changes page shows `eo_hist_note` once, at the top. Each row's Undo is `aria-disabled` with no repeated reason (item 4, `o-changes`).
- A plugin agent's inspector keeps its own read-only reason and shows no Edit at all (`o-plugin`). There is no "Copy to my agents" in M6.
- The restart box (`o-restart`) shows in the rail or the agent form as 3.2 describes, with a Reload button (`eo_reload`).

### 5.3 Settings edit (direction B)

- Route `setup/<part>/<item>/edit` renders the rail beside the list at 721 px and up. At 720 px and under it is a full-height sheet over the item page that covers the tab bar (component 28, D4), with a sticky foot that shows the file and the change above Save.
- The rail holds the field control (Segmented for effort, Select for model), the hint, Save to rows with the outcome and the "set now" mark per row, the user-scope warning, This save, the backup note and Save, from `railB` in `m6-design/site/m6.js:53-56`.
- Each effort option shows what it would run at in the picked scope, from `options[]` (item 11).
- Every status in Runs at, in the Save to outcomes and in the recheck outcome shows its mark glyph and its word from the `--status-*` set, never hue alone (CLAUDE.md, Design, "Reuse first").
- While a preview is pending, This save marks itself as updating with `aria-busy`, and Save holds as 5.1 says (item 9).
- A picked row with a preview `refusal` shows its reason beside Save, and Save doesn't send. Rows that aren't writable show so before they are picked (item 10).
- Save reads "Save to {scope}" and stays in one place. The busy label swap keeps the button's width (item 16).
- After a refusal, Save ignores presses until the fresh preview has rendered. Focus moves to the refusal message, which has `tabindex="-1"` and no `role="alert"`, so a screen reader reads it once (item 15).
- Saved replaces the rail with the inspector and its Saved box. It holds Undo, the recheck line and "All changes". The recheck line is announced once, when it settles (item 20).
- Overwritten keeps its warning with the changed keys and whether our value survived. Review changes opens the drift diff inline under the warning, with focus moved to it (item 17). The warning comes back on a later visit until it is marked seen (item 18).
- Undo after a change shows the undo diff with "Keep the file as it is" and "Undo anyway".

### 5.4 Changes page (M6a)

Route `#/p/<project>/setup/changes`, from `historyPage()` in `m6-design/site/m6.js:168-182`.

- Breadcrumb "Your setup / Changes". Groups by day. Columns When, Change, File and Undo.
- Change names the subject and the field, such as "Model for builder" or "New agent planner" (item 21). File shows the scope chip, the display path and the link target.
- Undo shows the button and the undo state, plus the recheck outcome (item 19).
- Undo of a changed file opens the undo diff and its two buttons inline as a full-width panel under its row, with focus moved to it (item 22).
- An empty page says what will appear and links to Your setup (item 23).
- At 375, stacked rows keep the column words for screen readers, as visually hidden labels (item 24).
- Older backups sit in a Disclosure. The backup folder line shows the real folder with Copy path, and no "mock path" chip (item 25).
- Every "Saved." links here, and Your setup links to it in its header.

### 5.5 Agent form (M6b)

- Routes `review/agents/new` and `review/agents/<name>/edit` (`app/web/src/app/routes.ts:158-161`). The Agents page gains "Add an agent" and the inspector gains Edit (actions at `app/web/src/pages/review/AgentInspector.tsx:289`). With edits off both follow 5.2.
- Sections Role and model (Model and effort in edit), Name and details, Tools and options, System prompt. The sticky top bar holds "← Agents", Cancel and the primary button, "Create {name}.md" or "Save to {name}.md".
- The side column has Jump to and the This save card, with the whole new file as an all-added diff and a New file badge, or the edit diff with its link note. While the name is empty, This save shows a placeholder.
- Create stays enabled and in place. Pressing it with a required field empty moves focus to the first one, with its error beside it, and the top bar's "Name and description are required" stays (item 28).
- Presets Lead, Worker and Reviewer live in `app/web/src/lib/agent-presets.ts`. Custom shows when the form differs from every preset. The role is never sent.
- The model list shows price words from `/api/prices` `relative` (`app/server/models.py:156`). "Use a full model name" opens a text entry with a live check against the model catalog (item 27).
- Tools and skills are picked from lists in the form answer, never typed from memory. A value already in the file that isn't in the list shows as is, with a note (item 26).
- More fields holds background (Switch), isolation (Select), memory (Select), omitClaudeMd (Switch) and autoCompactWindow (number), each with a help line (item 32).
- The name check runs per Save in row against front matter names, case-insensitive (4.2). A clash with a winning project agent shows the warning with "Use another name", which focuses the Name field and selects its text. This save repeats the clash.
- The System prompt is a plain TextArea in the monospace face at the board's height, with no line numbers and no "Press Esc, then Tab" line (item 29). When the serialized request passes 48 KiB a size note shows under it, and past the gate's 64 KiB a worded refusal blocks Save (item 30, 4.2).
- The read-only group shows one reason line per reason, `field_until_m7` and `risky_until_m8` (items 31 and 33).
- Plugin agents open a read-only page with the plugin chip, their source and the Ignored status word on fields Claude Code ignores for plugins. No "Copy to my agents".
- At 720 px and under, the phone action bar shows the summary, "Show the file" and the primary button. The tab bar stays hidden (`app/web/src/app/nav.ts:84-86`).

### 5.6 Components (wave 5)

New folders, each with a sheet entry (`app/web/src/sheet/manifest.test.ts:27-30` requires one). M6a builds Diff (29), SaveToList, ThisSave with its updating state, EditRail with the phone sheet (27, 28), SavedBox, RefusedMessage, OverwrittenBox with the drift diff, UndoConfirm, EditsOffNote and PhoneActionBar (49). M6b builds StickyActionBar (50), FormField (38), TextField with TextArea (39), TagList (40), ColorChoice (41), ListboxPopover (42, extending `Select`), Disclosure (43), RoleCards (44), ModelList with price mark (45) and FilePreview (46). Segmented (13) and Switch exist. New tokens follow the `--m5-*` pattern as `--m6-*`, only where `m6.css` needs a value `tokens.css` lacks, each with its contrast grade in the header comment.

### 5.7 Help and strings

New help ids `edit.save`, `edit.scopes`, `edit.history` and `shell.editing` land in M6a, and `agents.savein` in M6b, each named by a literal prop (fact K-819f). Reason and refusal codes join the closed-enum tests on both sides. tech-writer applies the owner's copy fixes in task a1.
- `ed_set_after` drops "line 3".
- `an_where_user` reads "User, every project".
- The name-clash text names the scope "This project only", as the Save in row does.

## 6. Coverage

### 6.1 Owner picks, November 11

| Pick | Where |
|---|---|
| Direction B, one surface | 5.3, tasks a9 and a11 |
| Live This save beside the control, from a server preview | 4.2 preview, 5.1, task a9 |
| Save names its destination and never swaps with Preview | 5.3. No Preview button exists. Double-press test in task a16 |
| Each Save to row shows the outcome if saved there | `scopes[].outcome`, `edit_preview.py` |
| The agent page shows the file it would create, or its diff | `file` and `diff`, FilePreview, task b12 |
| Changes page under Your setup, linked from every Saved., no new sidebar item | 5.4 |
| Saving to a scope that won't win is allowed, with a warning | `warnings[] wont_win`. Save stays enabled |
| A user agent named like a project agent is allowed, with a warning and Use another name | 5.5 |
| Shared project line only when git tracks the file | `git_tracked.py` |
| No Copy to my agents for plugin agents | 5.5 |
| The real backup folder and expiry, before wording is final | Section 9, question 7. Task a1 words the real folder |
| Copy fixes | 5.7, task a1 |

### 6.2 Owner answers, November 11

All eight are the lead's picks, with question 8 as B. Section 9 records them.

### 6.3 Designer review, item by item

Section 14 holds the designer's review. Each item lands in a task. None is deferred, except the part of item 11 noted in section 1.

| # | Severity | Where it lands | Task |
|---|---|---|---|
| 1 | Blocker | History, recheck read, drift and seen always mounted. Only preview, save and undo need edits on | a2, a5, a11 |
| 2 | Should | `edits {state, instance}` in `/api/app`, `edit_block` per project (only `folder_not_found`) | a2, a11 |
| 3 | Should | Disabled, focusable Edit with a reason line naming the command. Same for Add an agent and agent Edit in M6b | a11, b12 |
| 4 | Should | One note at the top of Changes, row Undo `aria-disabled` | a11 |
| 5 | Should | Edit URLs with edits off render the item page with the reason | a11 |
| 6 | Should | `edits_off` and `edit_key_unknown` codes, one restart state | a2, a8 |
| 7 | Nice | Sidebar foot line, and the same line on the More page | a11 |
| 8 | Should | AA contrast on the disabled label and reason, checked on the sheet | a9 |
| 9 | Blocker | `choice_key`, Save holds, This save updating, token bound to the body (`preview_mismatch`) | a3, a5, a8, a9, a11 |
| 10 | Should | Preview `refusal` beside Save, non-writable rows shown before picking | a11 |
| 11 | Should | `options[]` Runs at for effort and effort cap. Not for model (section 1) | a5, a11 |
| 12 | Nice | `scopes[].current_value` for the "set now" mark | a5, a11 |
| 13 | Should | Query invalidation after save, undo and recheck | a8 |
| 14 | Should | `field_until_m7` for Thinking, Cache lifetime, Allowed and Fallback models | a0, a1 |
| 15 | Should | Focus to the message with `tabindex="-1"`, no `role="alert"` | a9, a11 |
| 16 | Nice | Width-stable busy label | a9 |
| 17 | Blocker | `rows/<id>/drift` from rebuilt after-bytes, shown inline under Review changes | a3, a5, a9, a11 |
| 18 | Should | Seen mark in `prefs`, `/api/edit/open` brings the warning back | a5, a11 |
| 19 | Should | Server-side rechecks stored on the row, shown on Changes | a3, a5, a11 |
| 20 | Nice | Recheck line announced once when settled | a11 |
| 21 | Should | `subject` on history rows | a3, a5, a11 |
| 22 | Should | Inline undo panel under the Changes row | a11 |
| 23 | Should | Empty Changes state | a11 |
| 24 | Should | Visually hidden column words at 375 | a11 |
| 25 | Nice | Real backup folder, no mock chip | a1, a11 |
| 26 | Should | Tool and skill lists in the form answer, `tool_names.json` sourced from the docs by a scout | b7a, b7, b12 |
| 27 | Should | Full model name entry with a live catalog check | b7, b12 |
| 28 | Should | Create stays enabled, focus to the first empty required field | b12 |
| 29 | Should | Plain TextArea without line numbers or the Esc line | b10, b1 |
| 30 | Nice | Size note past 48 KiB, worded refusal past 64 KiB | b7, b12 |
| 31 | Should | `field_until_m7` for initialPrompt and experimental | a0, b7 |
| 32 | Should | Controls and help lines for the five wider scalars | b1, b10, b12 |
| 33 | Nice | One reason line per reason in the read-only group | b12 |
| 34 | Should | M6a hides Add an agent and agent Edit, and agent edit URLs open the agent on Agents | a11 |
| 35 | Should | `ro_m6` replaced in M6a, agent words without a milestone | a1, a11 |
| 36 | Should | Written state list for the screenshot tasks | 8.3, a13, b13 |
| 37 | Should | Edits off drawn now. Other undrawn states reviewed by the designer from shots | a14b, b14b |
| 38 | Should | Screenshot fixture that matches the board data | 8.4, a13 |
| 39 | Nice | Known differences in the judge's brief | 8.5, a14, b14 |

### 6.4 The designer's earlier UX needs

The first designer pass listed what the preview must return. 4.2 carries each one. That covers the target and real path, from, to and Runs at now and after, the outcome per scope, diff lines with real numbers, read time and token. It also covers the refusal with a fresh preview, the row id at once, the recheck states, undo with a confirm token, the Changes rows, and the agent form's whole-file preview, name check, Save in paths, price words, presets, tools mapping, read-only reasons, plugin fields and phone summary.

### 6.5 Verifier corrections

The verifier passed the plan as sound with corrections. Each one lands here.

| Correction | Kind | Where | Task |
|---|---|---|---|
| Write guard and `dir_fd`. Bind permits by folder identity through `fstat`, refuse relative write opens, subprocess test for a rename into an unpermitted folder | Must | 3.5 | a2, a3 |
| Undo, restore and drift rebuild the target from the registry, check the folder id and the row's project, port ForgedRowTests | Must | 3.7 | a3, a4 |
| Interop in a separate `/usr/bin/python3` process with only `dashboard/` on its path and `PYTHONDONTWRITEBYTECODE=1`, with the on-disk vocabulary pinned | Must | 11, Interop | a4 |
| Folder-link time-of-check gap. Component walk with `O_NOFOLLOW` from a trusted base, and the folder's `fstat` compared again at write time | Must | 3.4 | a3 |
| Test servers get `HOME` and `CLAUDE_CONFIG_DIR`. The write guard is installed in every mode with `--allow-edits`. Real home is `realpath(HOME)` | Must | 3.1, 3.10 | a2 |
| a4 port list gains HostileTests, CrashTests, RacedTests, ReadOnlyTests, CreateCrashTests, PruneMarkerTests, UndoCreateCrashTests and the descriptor-leak tests | Should | 8.2, a4 | a4 |
| Token. Separate payload fields tell `changed` from `preview_mismatch`. The canonical body is defined | Should | 2 | a3, a5 |
| `request_id` in-flight mark under the lock, `request_reused` for the same id with another body | Should | 2, 3.6 | a3 |
| `git_tracked` hardening as in `dashboard/git_check.py:295-305` | Should | 2 | a5 |
| Span-aware masking for diff and context lines | Should | 3.9 | a5 |
| Local layer matches the old `target_for` and `project_files`, up to four files | Should | 2, 3.3 | a3, a4 |
| The 8.4 fixture seeds settings rows only in M6a | Should | 8.4, 8.5 | a13 |
| The b5 corpus path | Should | 8.2, b5 | b5 |
| The M6b name check uses front matter names, case-insensitive | Should | 4.2, 5.5 | b7 |
| The 64 KiB limit applies to serialized request bytes | Should | 4.2, 5.5 | b7, b12 |
| The writer runs in one worker thread with no `await` while a permit is active | Should | 2 | a3, a5 |
| `review/agents/new` redirects at route level in M6a | Should | 1 | a11 |
| a16 uses `app/scripts/npmw --npx` | Should | 8.2 | a16, b16 |
| plan-a's `/api/edit/targets` is replaced by `scopes[]` | Should | 2 | None |
| Glyph plus word for Runs at statuses and recheck outcomes | Should | 5.3 | a9, a11 |
| Line offsets. `edit_store.py:387-395` for the size, owner and hard link refusals, `gate.py:156-157`, and `ph_body` rather than `ro_m6` for the placeholder | Should | 1, 3.2, 3.3 | None |

### 6.6 The designer's new needs, from the edits-off boards

The hand-off named nine needs and listed eight. The eight are below, and the launcher modes the main session decided close the list, because the `eo_*` words depend on them. [NEEDS CONFIRMATION: the ninth need, if it is not the launcher modes.]

| Need | Where | Task |
|---|---|---|
| The reason line uses the server's own command from the `bartab-command` meta tag plus `--allow-edits`, never a baked-in string | 2, 5.2 | a11 |
| A restart is noticed before Save through `bartab-instance`, and the restart box shows at once | 3.2, 5.1 | a8, a11 |
| After a restart the page reads the current mode, so the box words and the foot line match it | 3.2, 5.1 | a8, a11 |
| A `shell.editing` help entry | 5.2, 5.7 | a1, a11 |
| `footerLines()` takes the edit mode | 5.2 | a11 |
| The mode line has a phone home on the More page | 5.2 | a11 |
| Edit-link focus goes to the `eo_route` note | 5.2 | a11 |
| When a project can be non-editable with edits on | 2. Only `folder_not_found`. The plugin case is per item | a2 |
| The launcher modes, so the `eo_*` words stay true | 2 | a1, a2 |

## 7. Copy tasks for tech-writer

All at medium. Each returns a key table that the lead types into `en.ts`, `help.ts` and `glossary.ts`.

| Task | What | Waits for |
|---|---|---|
| a1, M6a deck | Start from `m6-design/site/strings-m6.js`, `strings-m6o.js` (the `eo_*` keys) and the reused `ed_` keys. Confirm the `eo_*` words stay true under the launcher modes in section 2, including "Start Bar Tab with {cmd}" when a server is already running. Add `forged_row`, `bad_version`, `request_reused` and the `shell.editing` help entry. Remove the orphan `ro_m6`. Replace demo values with slots. Apply the three copy fixes. Words for every M6a refusal and reason code (`changed`, `preview_mismatch`, `changed_since_save`, `raced`, `link_outside`, `link_dangling`, `not_regular`, `hard_link`, `not_owner`, `too_large`, `managed`, `edits_off`, `edit_key_unknown`, `field_until_m7`, `cant_rebuild`), the edits-off reason lines for skill, launcher and demo, the sidebar foot line, the Changes note and empty state, the warnings, the shared-repo line, recheck states, drift heading, the backup line naming `<config>/routing-dashboard/backups`, agent words that say editing comes next, and the help entries `edit.save`, `edit.scopes`, `edit.history` | Task a0 key list and the edits-off board |
| b1, M6b deck | Agent form words, `bad_name`, `exists`, `frontmatter_drift`, `frontmatter_unsupported`, `risky_until_m8`, `body_until_m7`, the five wider fields with help lines, the size note and refusal, the model check states, the tool and skill list notes, required-field errors, and the help entry `agents.savein` | Task b0 key list |

## 8. Ordered tasks

Tiers follow the owner's routing rules. fast-worker runs at medium unless the row says high. Every brief starts with `Kind: rebuild-m6`, carries the HiveMind line from `hivemind_lib.py related <paths>` and the date rule (`date -Iseconds` only).

### 8.1 Limits in every brief

- Work only in `/Volumes/Warehouse/Projects/claude-code-model-routing-bartab`.
- Never read anything under `~/.claude`, real transcripts, real settings or `~/.claude.json`. Never pass `--real`, never run the launcher, and never read `server.json` or a launch descriptor.
- Servers only on ports 47000 to 47999, never 8377. Never print, guess or ask for a key.
- Use `app/scripts/uvw` and `app/scripts/npmw` for every uv and npm call, and download nothing.
- Never edit `dashboard/`, `tests/`, `plugins/`, `tools/`, `hooks/`, `agents/`, `rules/`, `skills/` or `install.py`. Reading the old write core is fine. The lead alone edits the skill's `argument-hint`.
- Every test writes only inside throwaway HOME, config and project folders under `tmp_path`, outside any git work tree.
- Write scripts with Write and run one plain command per call. No heredocs, because the guard refuses them. Keep the literal text `.claude.json` and the launcher's file name out of Bash commands.
- New timing tests use `app/server/tests/timing_policy.py` (`limit`, `wait_limit`) with `@pytest.mark.timing`.
- A worker doing visual or CSS work gets the whole visual goal in its brief, views its own screenshots of every touched state with Read before it reports, and runs the narrow spec first. The full matrix waits for the exit run.
- The judge and the designer review Playwright screenshots. Neither opens the real server in Chrome, because the one-time code is gated.

HiveMind ids for briefs: E-5b16, E-6ccf, S-fe14, C-0a1c, C-1ff9, U-0aa1, U-3f27, U-436d, U-ea51, T-7629, T-5589, T-c826, T-3ad1, D-c684, D-3ca7, K-6860, K-819f, W-7178, plus whatever `related` returns per task. `related` resolves to the main checkout's store, which knows `dashboard/` paths but few `app/` paths.

### 8.2 Tasks

M6a.

| # | Task | Files | Agent and tier | Needs | Check | Cost |
|---|---|---|---|---|---|---|
| a0 | Pre-flight and contract. Time, branch, clean tree. Edit models in `models.py`, `edit_fields.py` with settings fields and codes, `edits` and `edit_block` models, `edit_config` and `edit_project` fixtures, OpenAPI and `schema.d.ts`, the M6a key list. The skill's `argument-hint` | `app/server/{models,edit_fields}.py`, `app/server/tests/conftest.py`, `app/web/src/api/{openapi.json,schema.d.ts}`, `.claude/skills/bartab-preview/SKILL.md` line 4 | Lead | None | Models import, export runs, `tsc` passes | In the lead row |
| a1 | M6a copy deck (section 7) | Scratchpad deck, typed by the lead | tech-writer medium | a0, edits-off board | String lint and help guards pass after typing | $9 to $14 |
| a2 | Switch, keys, gate and guard (high). The launcher modes in section 2 (`start --allow-edits`, the mode in the run record, restart into edits on, "Editing is on" or "off" on a plain `start` or `code`). `serve.py --allow-edits`, the fixture-mode refusal, the guard installed in every mode with edits on, `edits {state, instance}` and `edit_block`, per-project edit keys, the gate's write rules, `edits_off` and `edit_key_unknown`, the two routers. `write_guard.permit` with folder identity binding, the `dir_fd` and relative-open rules in 3.5, and the backups extra root. `e2e/server.ts` passes `HOME` and `CLAUDE_CONFIG_DIR` | `app/bin/bartab.py`, `app/server/{serve,access,gate,write_guard,api_app,store_provider,projects,main}.py`, `app/web/e2e/server.ts`, tests | fast-worker high | a0 | Gate refusal matrix. Write guard tests in subprocesses, including the three refusals in 3.5. Launcher tests as subprocesses in temp folders, including `/bartab-preview`-style argument lists such as `--default-project D --session S --real --allow-edits`, a restart from edits off into edits on, and the mode line on a plain `start` and `code` | $16 to $23 |
| a3 | Write core (high). `json_edit.py` port and `edit_store.py` with 3.3 to 3.7. The component walk and folder identity checks, absolute opens confirmed by `fstat`, the token payload and canonical body, request ids with the in-flight mark, forged-row checks, the local-layer choice, the preview cache, server rechecks, rebuilt after-bytes, new row fields, all in one worker thread per call | `app/server/{json_edit,edit_store}.py`, tests | fast-worker high | a2 for `permit` | Links (leaf, folder, dangling, outside, to a forbidden path, a folder swapped for a link between check and write), refusals, backup before write, prune, `O_EXCL` create, undo and undo anyway, `bad_version`, `preview_mismatch` and `changed`, in-flight and reused request ids, forged rows, recheck results, rebuild against `after_sha256`. pyright strict, coverage 85 percent | $25 to $36 |
| a4 | Ported tests, properties, race and interop (high). Port `tests/test_json_edit.py` whole and these `tests/test_edit_store.py` classes. Walk (`:235`), Save (`:402`), Hostile (`:670`), Crash (`:875`), Restore (`:958`), Raced (`:1095`), Retention (`:1219`), ReadOnly (`:1323`), Create (`:1509`), CreateCrash (`:1625`), PruneMarker (`:1702`), UndoCreateCrash (`:1778`), UndoCreate (`:1820`), the descriptor-leak classes CreateDescriptor (`:2364`) and ForceDescriptor (`:3100`), Force (`:2440`), ForgedRow (`:2873`) and ForceCrash (`:3000`). hypothesis properties. The 26-08 race test. The interop test in section 11, run as a separate `/usr/bin/python3` process | `app/server/tests/test_port_{json_edit,edit_store}.py`, `test_edit_race.py`, `test_ledger_interop.py`, `app/server/tests/interop_old.py` (the subprocess driver), `test_edit_properties.py` | fast-worker high | a3 | All pass. The race test passes three runs in a row. The interop run leaves no `__pycache__` in `dashboard/` | $17 to $25 |
| a5 | Settings edit API (high). `edit_preview.py` with `options[]`, `current_value`, outcomes and `reaches`, `api_edit.py` settings routes, history with subject and recheck, drift, seen, open warnings, `git_tracked.py` with the old hardening, span-aware masking, warnings | `app/server/{edit_preview,api_edit,git_tracked}.py`, tests | fast-worker high | a3, a4 green | TestClient on throwaway setups. Every field in 4.2. 409 answers. History and drift with edits off. Leak test and a secret on a context line and across lines (3.9). A `.git/config` with `core.fsmonitor` set runs nothing. Closed-enum test on the server side. A timing test bounds one preview | $23 to $32 |
| a8 | Web data layer. `api/edit.ts` per 5.1 | `app/web/src/api/edit.ts`, tests | fast-worker | a0 | Vitest on a fake clock. Latest `seq` wins, `pending` holds Save, a held press sends after the matching preview, 409 flow, edit header, invalidation list, restart state, recheck schedule | $7 to $11 |
| a9 | M6a components (high). Diff, SaveToList, ThisSave with updating, EditRail and phone sheet, SavedBox, RefusedMessage, OverwrittenBox with drift, UndoConfirm, EditsOffNote, RestartBox, PhoneActionBar, each on the sheet with every state | `app/web/src/components/*`, `app/web/src/sheet/*`, tests | fast-worker high | a0, a1 typed | Vitest. Sheet test with axe at 375 and 1440, light and dark, forced colours, reduced motion, AA on the disabled Edit label, and glyph plus word on every status. The worker views its shots against `b-edit`, `b-saved`, `x-refused`, `x-symlink`, `x-over`, `x-undo` and the edits-off boards `o-insp`, `o-changes`, `o-route` and `o-restart` in `m6-design/shots-o/` | $14 to $20 |
| a11 | Settings edit pages, Changes, edits off (high). Inspector Edit and its reason line from the `bartab-command` meta tag, the edit route and its `eo_route` note with focus, the rail at both widths, saved, recheck, overwritten with drift, refused, undo, the restart box, Changes with every 5.4 state and its note, `footerLines` with the mode, the More page line, the `shell.editing` help, and both agent routes redirected at route level | `app/web/src/pages/setup/*`, `app/web/src/pages/MorePage.tsx`, `app/web/src/lib/history.ts`, `app/web/src/app/{routes.ts,router.tsx,Shell.tsx}`, tests | fast-worker high | a5, a8, a9 | Vitest. Narrow e2e specs for the settings flow, edits off and a restart with axe at 375 and 1440. The worker views its shots against the boards | $20 to $29 |
| a13 | Screenshot fixture and set. The fixture in 8.4 and a Playwright spec that captures every state in 8.3 at 375 and 1440, light and dark, into `test-results/m6a-shots/` | `app/web/e2e/fixtures/m6_edit.ts`, `app/web/e2e/m6a-shots.spec.ts` | fast-worker | a11 | Every listed state has four shots | $6 to $9 |
| a14 | Visual review. The judge reads the a13 shots against `b-*`, `x-*` and the edits-off boards `o-insp`, `o-plugin`, `o-changes`, `o-route` and `o-restart`, with the known differences in 8.5 | None. A difference list | judge | a13 | List with board, state, width and theme per item | $4 to $7 |
| a14b | Designer review of the undrawn states from the a13 shots, at medium (main session dispatch) | None. A UX list | designer medium | a13 | List per state | $5 to $8 |
| a15 | Fix round 1. One batch from a14, a14b and the lead's review | Pages, components, CSS | fast-worker (high if CSS-heavy) | a14, a14b | Narrow specs pass. The worker views before and after shots | $8 to $14 |
| a16 | End to end, after the fixes. Keyboard walkthroughs 1 to 3 and 6, a real double-click on every primary button, accessibility snapshots, axe on every new route, and the shard balance check with `app/scripts/npmw --npx playwright test --list --shard=N/6` for N 1 to 6 | `app/web/e2e/{edit-settings,edit-keyboard,changes,edits-off}.spec.ts`, `app/web/e2e/a11y.ts` | fast-worker | a15 | All pass three runs in a row. No shard more than 25 percent over the mean | $8 to $12 |
| a17 | Exit runs. T2 suite, the full Playwright and axe matrix, the old suite alone with its log named for `feature-bartab-m6` (T-7629), the protected-path diff, the leak search | Logs in the scratchpad | scout | a16 | All green. The diff is empty | $2 to $4 |
| a18 | Fix round 2 for exit and Linux CI failures, and the M6a report. The main session dispatches the verifier | None | Lead and fast-worker | a17 | Report written | $8 to $14 |

M6b, after M6a's verifier pass and the owner's go.

| # | Task | Files | Agent and tier | Needs | Check | Cost |
|---|---|---|---|---|---|---|
| b0 | Contract. Agent form models, agent fields in `edit_fields.py` with controls and codes, OpenAPI, the M6b key list | `app/server/{models,edit_fields}.py`, `app/web/src/api/*` | Lead | M6a merged to the branch | `tsc` passes | In the lead row |
| b1 | M6b copy deck (section 7) | Scratchpad deck | tech-writer medium | b0 | String lint and help guards pass | $5 to $8 |
| b7a | Tool names. Read the Claude Code docs page that lists the tools and return names with the URL and the date read | `app/server/data/tool_names.json`, written by the lead from the list | scout | None | Every name has a URL | $2 to $3 |
| b5 | Front matter writer (high). `agent_write.py` per 3.8, the new-file renderer, N2. The 63 repo agent files and the 66 spike edge files from `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/spikes-m0/spike5-scripts/` (read allowed) copied into `app/fixtures/frontmatter-edge/` | `app/server/agent_write.py`, `app/fixtures/frontmatter-edge/**`, tests | fast-worker high | b0 | Each writable field round-trips on every corpus file with bytes unchanged outside the key, or refuses with a code. hypothesis on generated front matter | $12 to $18 |
| b7 | Agent API (high). Form, name check by front matter name (case-insensitive), model check, tool and skill lists, the serialized size rule, `create_agent` and `agent_set` preview and save, plugin read-only | `app/server/{api_agent_form,api_edit,edit_preview}.py`, tests | fast-worker high | b5, b7a | Create then Undo leaves no file and no empty folder. Name clashes in both scopes, including a file whose name differs from its front matter and a case-only difference. `exists` refused. Each field round-trips | $15 to $21 |
| b10 | Agent form components (high). StickyActionBar, FormField, TextField and TextArea, TagList, ColorChoice, ListboxPopover, Disclosure, RoleCards, ModelList, FilePreview, on the sheet | `app/web/src/components/*`, `app/web/src/sheet/*`, tests | fast-worker high | b0, b1 typed | As a9, against `b-agent` and `x-agent-*` | $14 to $20 |
| b12 | Agent pages (high). New and edit, Add an agent and Edit with the edits-off state, presets and Custom, the name and model checks, required-field focus, More fields, read-only group, plugin page, phone bar | `app/web/src/pages/review/Agent*`, `app/web/src/lib/agent-presets.ts`, tests | fast-worker high | b7, b10 | As a11 for the agent flow | $18 to $26 |
| b13 | Screenshots of every agent state in 8.3 | `app/web/e2e/m6b-shots.spec.ts` | fast-worker | b12 | Four shots per state | $4 to $6 |
| b14 | Visual review by the judge | None | judge | b13 | Difference list | $4 to $6 |
| b14b | Designer review of the undrawn agent states, at medium (main session dispatch) | None | designer medium | b13 | List per state | $5 to $8 |
| b15 | Fix round 1 | Pages, components, CSS | fast-worker | b14, b14b | As a15 | $6 to $10 |
| b16 | End to end. Walkthroughs 4 and 5, double-clicks, snapshots, axe, and shard balance with `app/scripts/npmw --npx playwright test --list --shard=N/6` | `app/web/e2e/edit-agents.spec.ts` | fast-worker | b15 | As a16 | $8 to $12 |
| b17 | Exit runs, as a17 | Logs | scout | b16 | All green | $2 to $4 |
| b18 | Fix round 2 and the M6b report. The main session dispatches the verifier | None | Lead and fast-worker | b17 | Report written | $6 to $10 |

Order. One lead at a time in this worktree. In M6a, a0 runs first. Then a1, a2 and a8 start together. a3 needs a2, a4 needs a3, and a5 needs a3 and a4. a9 starts once a1 is typed and the edits-off board exists. a11 needs a5, a8 and a9. Then a13, a14 and a14b together, a15, a16, a17 and a18. In M6b, b0 first, then b1, b7a and b5 together, b10 once b1 is typed, b7, b12, then b13 to b18 in the same pattern. M6 adds no package.

### 8.3 Screenshot state list (designer item 36)

M6a, task a13. Each at 375 and 1440, light and dark.
1. Edit rail on Effort, Project local picked, This save current (`b-edit`). At 375, the sheet with its foot.
2. This save updating, Save holding.
3. User picked through a link, with the user-scope warning and `reaches` (`x-symlink`).
4. A row refused with `link_outside`.
5. Save busy.
6. Refused after a file change, focus on the message (`x-refused`).
7. Saved with the recheck checking, then confirmed (`b-saved`).
8. Overwritten with our change kept (`x-over`), and with our change lost, each with Review changes open.
9. Undo confirm after a change (`x-undo`).
10. Changes with rows in every undo state and recheck outcome (`x-history`), Changes empty, and a Changes row with its undo panel open.
11. Edits off, against the boards in `m6-design/shots-o/`. Inspector with the reason line (`o-insp`), a plugin agent's inspector (`o-plugin`), Changes with its note (`o-changes`), an edit URL with focus on its note (`o-route`), the restart box in both modes (`o-restart`), the sidebar foot line, and the More page line at 375.
12. A settings field with `field_until_m7`.
13. Agents page and inspector in M6a with no Add an agent or Edit, and an agent edit URL landing on Agents.

M6b, task b13.
1. New agent from Lead (`b-agent`), with the name empty and with a name.
2. Custom after a change, and the clash with Use another name (`x-agent-clash`).
3. Required-field error after Create.
4. Edit an agent through a link, with the read-only group (`x-agent-edit`).
5. More fields open with the five wider controls.
6. Full model name entry, known and unknown.
7. Tools and skills pickers open.
8. The size note and the size refusal.
9. `exists` and `frontmatter_drift` refusals.
10. Plugin agent (`x-agent-plugin`).
11. Add an agent and agent Edit with edits off.

### 8.4 Screenshot fixture (designer item 38)

`app/web/e2e/fixtures/m6_edit.ts` builds a throwaway home and project under the test's temp folder, outside every git work tree, matching the board data in `m6-design/site/m6.js:2-5`.
- Project "Tidewater reporting" at a temp `work/tidewater-reporting`, with `git init` and one commit inside the temp folder, so `.claude/settings.json` is tracked.
- `.claude/settings.local.json` with `env.CLAUDE_CODE_EFFORT_LEVEL` set to `xhigh` (`m6.js:30`).
- `.claude/settings.json` with `effortLevel` `medium`.
- User `settings.json` as a link to a temp `dotfiles/claude/settings.json` with `model` `opus` and `effortLevel` `xhigh` (`m6.js:32`), and an effort cap of high so xhigh runs as high.
- User agent `builder.md` linked into the temp dotfiles folder, a project agent `reviewer.md` for the clash, and a plugin agent `linter` in a temp plugin cache.
- In M6a, a ledger seeded with settings rows only, written through the M6a writer in setup, never by hand. The history board's two agent rows ("New agent planner" and "Model for builder") join in b13, once the M6b writer exists. 8.5 lists the difference.

### 8.5 Known differences for the judge (designer item 39)

- The backup folder line shows the real temp folder, not `~/Library/Application Support/bartab/backups`, and has no "mock path" chip.
- Paths start at the test's temp folder, not `~/work`.
- Read times and saved times come from the test clock.
- Line numbers follow the fixture files, which can differ from the board's demo numbers.
- The new agent's System prompt is a plain TextArea without line numbers or the Esc line (item 29).
- The edits-off states compare against the designer's edits-off board, not `b-*`.
- M6a's Changes page has settings rows only, so the board's two agent rows are missing until M6b.
- The plugin page and `o-plugin` show no "Copy to my agents". The owner left it out of M6.
- `o-plugin` shows a Demo data shell and a To fix count. The test shell and its count differ, and that is expected.

## 9. Owner decisions

Answered by the owner on November 11. All eight are the lead's picks, with question 8 as B.

| # | Question | Answer |
|---|---|---|
| 1 | How edits get turned on | A. `--allow-edits` on each start, off by default. The reason line names `/bartab-preview --allow-edits` for the skill and the launcher command plus `--allow-edits` |
| 2 | Links whose real file sits outside home | A. Write through under the real home folder or the project root, refuse anything else |
| 3 | A new agent's system prompt | A. Plain text area for new agents only. Existing bodies wait for M7 |
| 4 | Settings fields | A. Model, effort, effort cap and compact window at the file's own key path |
| 5 | Agent fields | A. The wider list |
| 6 | Where history is read from | A. The ledger files, no SQLite mirror |
| 7 | Backup folder and expiry | A. `<config>/routing-dashboard/backups/`, 20 per file, no age expiry, shared with the old app. Copy names the real folder |
| 8 | How M6 ships | B. Two PRs, M6a and M6b, each with its own stop line and verifier pass |

The designer's three questions (section 14) are answered too. The reason line names the commands above. The edits-off state is drawn now, and the other undrawn states are reviewed from screenshots in tasks a14b and b14b. Review changes shows the drift diff inline.

## 10. Cost estimate

List-price ranges. plan-a put M6 at $70 to $120. M4 planned $171 to $270 and came to about $380 after the owner approved more. M5 planned $148 to $237. I have no per-run cost from the dashboard in this tree. [NEEDS CONFIRMATION: dashboard cost per run for each agent.]

### M6a

| Dispatch | Count | Estimate |
|---|---|---|
| Lead build, security reviews, typing strings, fix briefs and the report | 1 | $28 to $44 |
| fast-worker at high, tasks a2, a3, a4, a5, a9 and a11 | 6 | $115 to $165 |
| fast-worker at medium, tasks a8, a13, a15, a16 and a18 | 5 | $37 to $60 |
| tech-writer at medium, task a1 | 1 | $10 to $15 |
| judge, task a14 | 1 | $4 to $7 |
| scout, task a17 | 1 | $2 to $4 |
| Build only | | $196 to $295 |
| Designer review of shots at medium, a14b (main session) | 1 | $5 to $8 |
| Verifier on Opus (main session) | 1 | $8 to $15 |
| Total for M6a | | $209 to $318 |

Stop line. The lead stops and reports before starting the next task once M6a build spend passes $250.

### M6b

| Dispatch | Count | Estimate |
|---|---|---|
| Lead build, reviews, typing strings, fix briefs and the report | 1 | $18 to $30 |
| fast-worker at high, tasks b5, b7, b10 and b12 | 4 | $59 to $85 |
| fast-worker at medium, tasks b13, b15, b16 and b18 | 4 | $24 to $38 |
| tech-writer at medium, task b1 | 1 | $5 to $8 |
| scout, tasks b7a and b17 | 2 | $4 to $7 |
| judge, task b14 | 1 | $4 to $6 |
| Build only | | $114 to $174 |
| Designer review of shots at medium, b14b (main session) | 1 | $5 to $8 |
| Verifier on Opus (main session) | 1 | $6 to $12 |
| Total for M6b | | $125 to $194 |

Stop line. The lead stops and reports before starting the next task once M6b build spend passes $145.

### All of M6

| Part | Estimate |
|---|---|
| Plan step and its two revisions, lead, three scouts and one tech-writer pass | $25 to $38 |
| M6a | $209 to $318 |
| M6b | $125 to $194 |
| Total | $359 to $550 |

The first draft put the single-PR build at $236 to $360. The split adds a second contract, exit run, judge pass, designer review and verifier pass. The designer's 39 items add the edits-off state, the drift diff, the server rechecks, the body-bound token, the Changes page states, and the wider agent form controls. The verifier's corrections add about $15 to $22 to M6a, mostly in a2 to a5 (folder identity in the guard, the component walk, forged rows, the interop subprocess and the longer port list), and about $1 to M6b.

Where it could overrun.
1. The preview's resolver runs. One per writable scope plus one per effort option. If the M4 resolver can't take a copied layer cheaply, a5 grows.
2. Links. Folder links with `dir_fd` and the device and inode checks are fiddly on macOS.
3. Linux CI. Every milestone so far needed fix commits after the build.
4. The race test. Seams that make it deterministic may need a second pass.

## 11. Tests and exit

### New suites

| Area | PR | Tests |
|---|---|---|
| Switch and keys | M6a | Edits off answers `edits_off` on preview, save and undo, keeps history, drift and seen working, and grants nothing. Swap returns a key only with edits on. A key works only for its project. Fixture mode refuses `--allow-edits` with a writable root inside the checkout. `edits.start` follows the launcher's skill mark |
| Launcher | M6a | `start --allow-edits` and the skill-style argument list reach `serve.py --allow-edits`. Beside a server running with edits off it stops and restarts it with edits on. A plain `start` or `code` keeps the running mode and prints it. The mode is in the run record |
| Gate | M6a | Write refusal matrix. No Origin, wrong Origin, `Sec-Fetch-Site: cross-site`, missing or repeated edit key, wrong key, another project's key, oversized body, non-JSON. Asserts "refused" |
| Write guard | M6a | In subprocesses. A permit allows only its files and folders, by identity, and only on its thread. Without edits, a permit raises. A rename by `dir_fd` into an unpermitted folder, a bare name under an fd for an outside folder, and a relative write `open` are refused. A link from a permitted path to an outside path is refused. The guard is on in fixture mode with edits on |
| Allowlist and links | M6a | Every forbidden path, after links. Leaf link, folder link, dangling link, link outside `realpath(HOME)`, link to a forbidden file. A folder swapped for a link between check and write refuses with `changed`. The real file changes and the link stays a link. The local file matches the old choice, and a leftover local file is never written by a new save |
| Backup and atomic write | M6a | Backup fsynced before the temp file. A crash at each seam (ForceCrash port) leaves the old file or the new one, never a torn file. Mode kept. Prune keeps 20 |
| Token and refusal | M6a | A forged tag is `bad_version`. Bytes changed, same bytes with a new inode, and file removed are `changed`. A body changed after the preview is `preview_mismatch`. 409 carries a fresh preview and changed keys. A repeat request id returns the first result, a repeat in flight waits for it, and the same id with another body is `request_reused` |
| Write race | M6a | The 26-08 test. A hostile writer replaces the file at each seam in the writer through test hooks, and a timed run replaces it every 20 ms (`timing` marker). Every lost update is refused, reported as `raced`, or reported as overwritten by the recheck. None is silent |
| Recheck and drift | M6a | Checking, confirmed, overwritten with our value kept or gone, recorded on the row with no page open. Drift lines from rebuilt after-bytes, and `cant_rebuild` on a hash mismatch |
| Interop | M6a | The old side runs as a separate `/usr/bin/python3` process with only `dashboard/` on its path and `PYTHONDONTWRITEBYTECODE=1`, on the test's temp config. Old writes, new reads. New writes, old reads (old `rows`, `undo_state`, `restore`). Target ids agree. The pinned on-disk vocabulary is `kind` in edit, undo, restore. `op` in replace, insert, remove, create. `time` as `_now` writes it (`dashboard/edit_store.py:724-727`, UTC `isoformat`). Backup names matching `_REAL_BACKUP_RE` (`:83`). Ledger `version` 1. History sorted by (time, backup number) newest first, as `dashboard/api_edit.py:2175-2177` does |
| Masking and leaks | M6a | Section 3.9 |
| Preview | M6a | Every field in 4.2 on throwaway setups, `options[]`, `current_value`, outcomes, `reaches`, warnings, `choice_key` |
| Undo | M6a, M6b | Unchanged applies at once. Changed needs the confirm token. Create undo deletes the file and its made folder. A row whose folder id, path or project doesn't match the registry is `forged_row` (ForgedRowTests port) |
| Front matter | M6b | Byte equality outside the key for each field on the corpus. Drift and unsupported refusals. N2 both ways |
| Web | Both | Vitest for every hook and component. Save holding while pending. The restart box on an instance change before any Save, worded by the new mode. `footerLines` with the mode. Custom detection. Name and model checks. Refusal focus |
| Pages | Both | Playwright with axe on every new route and state at 320, 375 and 1440, light and dark, forced colours and reduced motion |

### Keyboard walkthroughs

Playwright with the keyboard only, at 375 and 1440. Each step asserts focus and the visible text.

1. Change effort and undo (M6a). From the setup list, open Effort, press Edit, pick medium, move through the Save to rows and hear each outcome, press Save to Project local. "Saved." is announced, then the recheck line once. Undo restores the file, and Changes shows the row as undone.
2. Refusal (M6a). With the file changed on disk after the preview, Save is refused, focus lands on the message, the preview shows the new file, and a second Save succeeds.
3. Overwritten and undo after a change (M6a). Another write lands after the save. The warning shows, Review changes opens the drift with focus in it, the undo diff shows, "Keep the file as it is" leaves the file alone, and "Undo anyway" restores it.
4. New agent (M6b). Add an agent, pick Lead, change the model (Custom appears), type a name that a project agent uses, hear the clash, press Use another name, type a free one, create. Create then Undo leaves no file.
5. Edit an agent (M6b). Change the model on a linked agent file. This save names the real file. Save, recheck confirmed.
6. Edits off (M6a). Tab to Edit, hear it disabled with the reason line naming the command. Open Changes, hear the note once, and reach a row's disabled Undo.

### Accessibility snapshots

a16 snapshots the rail, This save updating, Saved with the recheck, refused, overwritten with drift, the undo confirm, Changes, Changes empty and the edits-off inspector. b16 snapshots the new agent page with a clash, the edit page with the read-only group, More fields and the plugin page. They gate like any test, and M9's VoiceOver script reuses the list.

### Kept green in both PRs

- The M0 to M5 exit runs, with pytest, Vitest and Playwright counts in each report.
- Standards. ruff, ruff format, pyright strict, coverage at 85 percent on `app/server`, tsc, ESLint, Stylelint and Prettier.
- The old suite alone, `/usr/bin/python3 -m unittest discover -s tests` from the worktree root, log named for `feature-bartab-m6` (T-7629), expected 3575 tests and 88 skipped.
- `git diff --stat 5e0aeec -- dashboard tests plugins tools hooks agents rules skills install.py` stays empty.
- Playwright shard balance checked with `--list` across the six CI shards (`.github/workflows/bartab.yml`, e2e job).

### Exit

M6a.
- The owner changes effort on a throwaway project, sees the effect and diff, saves, sees "Saved." and the recheck, undoes it, and finds both on Changes. With edits off, every page says why and names the command.
- Every M6a security test passes, and the leak search finds nothing.
- Verifier pass on Opus. Axe, walkthroughs 1 to 3 and 6, accessibility snapshots and the forced-colours checks pass.

M6b.
- The owner adds an agent from a preset and edits an existing one on the same page, and undoes both.
- Front matter byte equality holds on the whole corpus.
- Verifier pass on Opus. Axe, walkthroughs 4 and 5, snapshots and forced colours pass.
- The owner decides whether M8 stays in release 1 (O11).

## 12. Risks and leftovers

### Leftovers M6 depends on

1. The client already stores and hands off edit keys (`app/web/src/app/access.ts:43-45`, `getEditKeys` at `:79`), with no caller yet.
2. The three edit routes parse and register (`app/web/src/app/routes.ts:158-167`, `app/web/src/app/router.tsx:179-185`) but render the placeholder. a11 and b12 fill them.
3. `writable` is in the schema (`app/web/src/api/schema.d.ts:1960`) but nothing reads it. a11 uses it.
4. `agent_fields.json` is ported byte for byte (`app/server/data/agent_fields.json`).
5. `/api/prices` already returns `relative` (`app/server/models.py:156`).
6. The edits-off boards are done (`m6-design/shots-o/`, strings in `m6-design/site/strings-m6o.js`).

### Risks

1. Writing the owner's real files. Section 3, the M6a verifier pass before M6b starts, and a first real save on a throwaway project cover it.
2. Lost updates from Claude Code. It takes no lock (26-08), so the gap between the last check and the rename stays open. The server recheck reports it, and Undo stays one press away.
3. Interop drift. If the old app changes its ledger while M6 is built, the interop test fails. The old app is in bug-fix mode only.
4. A ConfigChange hook can block a save from taking effect (26-08). The preview warns when one exists, and the recheck confirms the file, not the running session.
5. Resolver cost per keystroke. The 250 ms debounce, `seq`, and the a5 timing test keep it bounded.
6. Rebuilt after-bytes. If an operation isn't deterministic, drift answers `cant_rebuild`. The test covers every operation.
7. Two leads. M6 runs alone in this worktree. The designer's reviews touch no file in `app/`.
8. HiveMind. `hivemind_lib.py` resolves to the main checkout's store, so consolidation waits for the merge into development.
9. Budget. Section 10 sits far above plan-a's $70 to $120. Two stop lines hold it.

## 13. Designer reviews

- The plan review is done (section 14) and folded in item by item (section 6.3).
- The edits-off boards are done, in `m6-design/shots-o/`, and are the reference for that state.
- a14b and b14b review the undrawn states from screenshots at medium, before each fix round.

## 14. Designer plan review

Folded into this plan item by item in section 6.3. The review lists UX needs, and architecture choices stay with the lead.

Reviewed by the designer on November 11, 2026, against direction B and the shared states (boards `b-edit`, `b-saved`, `b-agent`, `x-*`). The plan covers the rail, This save, the refusal and the undo confirm well. The gaps sit in four places. The default edits-off state isn't designed and loses the Changes page. Save can send a value the preview hasn't drawn yet. The overwritten state has no data behind its primary button. Several states have no board for the visual review to compare against. Each item below is a UX need. How to meet it is the lead's call.

Severity. Blocker means the screen shows something false or a picked state can't work. Should means a visible gap the owner would hit. Nice means polish.

### Edits off, the default state

No board draws it, and the owner will see it on most starts. The screens need the following.

| # | UX need | Screen | Plan ref | Severity |
|---|---|---|---|---|
| 1 | The Changes page needs its history while edits are off. Today the 404 router covers every `/api/edit/*` route, so the default start would break a page that Your setup links to. History is read-only, and only Undo needs edits on | Changes | 3.1, 4.2 history, task 2, 11 | Blocker |
| 2 | The page needs to tell "edits are off for this server" apart from "this project can't be edited". An empty `editable_projects` reads the same for both, and the two need different words | Inspector, Agents, Changes | 3.1, `GET /api/app`, task 2 | Should |
| 3 | Edit stays where it sits in the inspector foot, `aria-disabled` and focusable, with one visible reason line under it tied by `aria-describedby`. No tooltip only. The line names the command that turns edits on. "Add an agent" and agent Edit behave the same in M6b | Inspector, Agents | 5.2, 5.4, task 11, 12 | Should |
| 4 | The Changes page says once, at the top, that Undo needs edits on, and each row's Undo is `aria-disabled` with no repeated reason per row | Changes | 5.3, task 11 | Should |
| 5 | An edit URL opened while edits are off renders the item page with the reason, not the placeholder or an error | Edit routes | 12 leftover 2, task 11, 12 | Should |
| 6 | If the server restarts during a visit (edits now off, or keys gone), a save or preview gets a code the page can word as "restarted, reload to edit" and the rail returns to read-only. Today 404 and a refused key would both reach the owner as a generic failure | Rail, agent form | 3.2, 5.1, task 8 | Should |
| 7 | One quiet fact line in the sidebar foot, "Editing off" or "Editing on", so the mode shows on every page without a banner | Sidebar foot | task 11 | Nice |
| 8 | The disabled Edit label and its reason line keep AA text contrast in both themes, though WCAG exempts disabled controls | Inspector | task 9 | Should |

### Settings rail

| # | UX need | Screen | Plan ref | Severity |
|---|---|---|---|---|
| 9 | Save may only send when This save shows the preview for the current choice. While a preview is pending, This save marks itself as updating and Save holds (busy or ignored). Otherwise a fast pick then Save writes a value whose diff the owner never saw | Rail, phone foot | 5.1 `usePreview`, 5.2, task 8, 11 | Blocker |
| 10 | When the preview's `refusal` is set for the picked row (for example `link_outside`), Save shows the reason beside it and doesn't send. The row also shows as not writable before it's picked (`scopes[].writable`) | Rail | 4.2 `refusal`, 5.2 | Should |
| 11 | The hint under the control ("The effort cap is high, so xhigh and max run as high") needs, for every option, what it would run at, before the owner picks it. The preview gives Runs at only for the picked value | Rail | 4.2 `effect`, task 6 | Should |
| 12 | The "set now" mark under an option needs the current value in the picked file, and it moves when the owner picks another Save to row | Rail | 4.2 `effect.set.from` | Nice |
| 13 | After Save, Undo and a recheck, the list chip, the inspector's Where it's set rows and the To fix count show the new state. A stale "Lowered" beside "Saved." contradicts the save | Settings list, inspector, sidebar | 5.1, task 8, 11 | Should |
| 14 | Settings fields that wait for M7 (Thinking, Cache lifetime, Allowed and Fallback models) need their own reason code and words. The code list has none for them | Inspector | 2 Q4, 7 task 1 | Should |
| 15 | The refusal message gets focus or `role="alert"`, not both, because VoiceOver reads it twice when both apply. Focus to the message with `tabindex="-1"` matches the board | Rail | 5.2 | Should |
| 16 | The busy label swap on Save keeps the button's width, so the foot doesn't shift | Rail, phone foot | 5.2, task 9 | Nice |

### Saved, recheck and overwritten

| # | UX need | Screen | Plan ref | Severity |
|---|---|---|---|---|
| 17 | "Review changes" in the overwritten box needs something to show, the lines that differ between what Bar Tab wrote and the file now. The recheck returns key names only, and no task says where the button goes | Inspector, overwritten | 4.2 rows, 5.2, task 6, 11 | Blocker |
| 18 | The overwritten warning stays "until it's dealt with", so the inspector needs that state again when the owner comes back to the item later, and a way to mark it seen. Today the box exists only in the moment after Save | Inspector | 4.3 `recheck`, 5.2 | Should |
| 19 | Changes rows show the recheck outcome (Overwritten, your change kept or lost), because the owner may leave before the 10 s recheck. History rows don't carry it | Changes | 4.2 history | Should |
| 20 | The recheck line is announced once when it settles, not on each poll | Saved box | 5.2 | Nice |

### Changes page

| # | UX need | Screen | Plan ref | Severity |
|---|---|---|---|---|
| 21 | The Change column needs a subject as well as the field, such as "Model for builder" or "New agent planner". History rows carry `field` only | Changes | 4.2 history | Should |
| 22 | Undo of a changed file from this page needs the same undo diff and the two buttons, shown inline as a full-width panel under its row, with focus moved to it. No board draws it there | Changes | 5.3, x-undo, task 11 | Should |
| 23 | An empty Changes page says what will appear and links to Your setup | Changes | 5.3 | Should |
| 24 | At 375, stacked rows keep the column words available to screen readers. Hiding the header row hides them | Changes | 5.3, task 11 | Should |
| 25 | The backup folder line shows the real folder (section 9, question 7). The board's "mock path" chip goes | Changes | 5.3 | Nice |

### Agent form (M6b)

| # | UX need | Screen | Plan ref | Severity |
|---|---|---|---|---|
| 26 | Tools and skills are picked from lists, never typed from memory. The form needs the tool names and the project's skills to offer | Agent form | 4.2 form, 5.4, task 7 | Should |
| 27 | "Use a full model name" on the board needs a text entry with a live check, or the link goes | Agent form | 5.4, task 12 | Should |
| 28 | Create stays enabled and in place. Pressing it with a required field empty moves focus to the first one, with its error beside it. The top bar's "Name and description are required" line stays. This save shows a clear placeholder while the name is empty | Agent form | 5.4, task 12 | Should |
| 29 | The plain text area (question 3) drops the board's line numbers and the "Press Esc, then Tab" line, since a text area doesn't trap Tab. It keeps the monospace face and the board's height | Agent form | 2, 5.4, task 1b | Should |
| 30 | The gate's 64 KiB body limit needs words before Save, as a size note near the text area once a prompt gets close, and a worded refusal past it | Agent form | 3.2, task 12 | Nice |
| 31 | `initialPrompt` and `experimental` need their own reason. `body_until_m7` speaks about the system prompt | Agent form | 5.4 | Should |
| 32 | The wider field list (question 5) adds background, isolation, memory, omitClaudeMd and autoCompactWindow, which no board draws. Each needs a named control (Switch, Select or number) from the existing set and a help line, inside More fields | Agent form | 2 Q5, task 10, 12 | Should |
| 33 | The read-only group has one reason line per reason (M7 and M8), not one line for both | Agent form | 5.4 | Nice |

### The M6a and M6b split

Nothing in M6a is half-done if the agent entry points stay as they are in M5.

| # | UX need | Screen | Plan ref | Severity |
|---|---|---|---|---|
| 34 | In M6a, "Add an agent" and agent Edit don't appear, and the agent edit URLs lead to the agent's page, not the placeholder | Agents | 9 Q8, 12 leftover 2 | Should |
| 35 | `ro_m6` is replaced in M6a. Agent reason words then say agent editing comes next, without naming a milestone the owner never sees | Agents inspector | 5.6 | Should |

### Visual review coverage

Task 14 compares against boards, and several states have none. The judge can't grade those.

| # | UX need | Screen | Plan ref | Severity |
|---|---|---|---|---|
| 36 | Task 13 needs a written state list. From the boards: edit (both widths, phone sheet with foot), saved with recheck confirmed, refused, link, overwritten, undo confirm, Changes, new agent, clash, edit agent, plugin agent | All | task 13 | Should |
| 37 | Undrawn states need a reference. Edits off on each page, recheck checking, overwritten with our change lost, a refused row (`link_outside`), Save busy, preview updating, Changes empty, Changes undo confirm, the `exists` and `frontmatter_drift` refusals, a user-scope save that reaches other projects, and the M7 field reasons. Either I draw them before the build, or I review their shots after task 13. See the owner decisions | All | task 13, 14 | Should |
| 38 | The task 13 project reproduces the board data, so shots compare like for like. That means a user settings file linked to a dotfiles folder, an effort cap that lowers xhigh, a git-tracked shared settings file, a project agent that clashes, and a plugin agent | All | task 13 | Should |
| 39 | Known differences go in the judge's brief so they aren't reported, such as the real backup folder and the demo line numbers | All | task 14 | Nice |

### Owner decisions

1. Edits-off words. Which command do you type to start with edits on? The reason line should name exactly that.
2. Undrawn states (item 37). A, I draw them as a short board round before the build, about $8 to $15. B, I review their task 13 shots instead and the build follows my written notes, cheaper but it can mean a fix round. I'd pick A for edits off alone, because it's the screen you'll see most, and B for the rest.
3. Overwritten (item 17). Should "Review changes" show the diff of what changed since the save, or open the Changes page row? I'd pick the diff, inline, because the box already says what to look at.

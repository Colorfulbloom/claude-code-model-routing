# Routing Dashboard: functional requirements for a rebuild

Scope: what the current app does. Paths are relative to the repo root
/Volumes/Warehouse/Projects/claude-code-model-routing unless absolute. Line numbers were read on branch chore/hivemind-consolidation-nov-7. Nothing was run, and nothing under ~/.claude, real transcripts or real settings was read.

Items marked CONFLICT are places where two sources in the repo disagree. Those need a decision before a rebuild copies either one.

## 1. Pages and views

The page is one HTML shell (dashboard/static/index.html, lang="en" at line 2) that shows one section at a time from a hash router.

Routes (dashboard/static/js/router.js:1-17 comment, PAGES at 19-23):
- #/live, #/overview, #/models, #/agents, #/agents/<name or @main>, #/sessions, #/sessions/<id>, #/settings, #/settings/<agent>/<setting> (the "trail"), #/attention, #/files, #/rules.
- The all-projects section is the overview route when the project is "All" (router.js sectionFor, approx. line 91 of the file).
- Query parameters: project, range (today, 7d, 30d; format.js:42), theme (light or dark), setting (router.js:30, BAND_SETTINGS). An unknown route falls back to overview (router.js:131-132 area, parseRoute).

Pages:
- Live (pages/live.js header 1-14; live_flow.js header). One session of one project, minute by minute. States: wait, idle, live, paused, lost, empty, pick, unknown, unreadable. Shows a "Dispatches in this session" canvas (live_flow.js): one card per run, columns by depth, connectors, "agents at once" chips, "Round n" chips for resumed runs. Under 720px it becomes a list. Refresh: polled (see section 6). Interaction: pause, session choice (the poller sends session=<id>, live_poll.js:2-12), "Show n finished".
- Overview (pages/overview.js header 1-4). Usage for the project over the range. Reads one view of /api/usage, so a range change fetches nothing. Refresh: loads on route or range change, and a loading strip polls /api/projects once a second while the usage answer is pending (app.js:20-26).
- Agents (pages/agents.js header 1-7). Each agent's runs, tokens, estimated cost, cache, model and effort. Rows keep server order (highest estimated cost first). Columns "Pinned to" and "Pin check" (pincheck.py) show whether a run used its pinned model and effort. Hidden in All projects.
- Agent detail (pages/agent-detail.js header 1-4). One agent or @main, from the view's by_agent list.
- Models (pages/models.js header 1-3). Usage by model with the agents that ran on each. One order for the cost card, tokens card and table.
- Sessions (pages/sessions.js header 1-4; SHORT_LIST = 10 at line 12). Newest first. "Show all" expands the list already in the payload. All projects adds a Project column.
- Session detail (pages/session-detail.js header 1-4). One session from the 30-day view, whatever range the address holds, so it has no range control.
- All projects (pages/all-projects.js header 1-6). Two cards listing every transcript folder in by_project. A listed folder links to its project; an unlisted folder is plain text.
- Settings (pages/settings.js header 1-12; TILES at 23-32). A band of cells, one per setting: model, effortLevel, maxEffortLevel, autoCompactWindow, promptCacheTtl, alwaysThinkingEnabled, fallbackModel, availableModels. Beside the band, a pane shows the open setting's body and a rail that says why the value is what it is.
  - Editable in the page: model, effort, effort cap, compact window (settings.js:34-36, api_edit.py:1-6). Others are read-only (read_frame.js header).
  - Cell order is a drag and drop or Earlier and Later buttons (band.js:11-13). Order is saved in the browser's localStorage, keyed by project path. No settings file changes (ar_note string, strings.json). Reset removes it.
  - Mouse drag only (band_drag.js:1-14). Touch uses the buttons. Arrange toggles these controls (band_arrange.js:1-14). Under 720px the band becomes a sticky strip and a list.
- Trail (pages/trail.js header 1-10). "What decides" one value: the winner, every value that lost, the rules behind them, and the files read.
- Needs attention (pages/attention.js header 1-9). Values that do not apply as set, or that the dashboard cannot work out, grouped by status. The server sets the groups and row order (api_settings.py _attention, around 153-216).
- Installed files (pages/files.js header 1-8). Each file the installer would write into the config folder, and whether the copy matches ("match" and other states, api_settings.py:363-369). Words and a mark for each state.
- Rules reference (pages/rules.js header 1-12). Every rule from rules.json (84 rules) with its reason, the Claude Code version it was checked on, a search box and a confidence filter. Data from api_settings.py:321.

Edit flow on the Settings page (edit_flow.js, edit_review.js, edit_backup.js, edit_pick.js headers): pick a level, preview, review in the rail, save, then undo, undo anyway, or restore from older backups. Nothing is written until the owner confirms in the review (edit_backup.js header 1-6).

## 2. Data sources

All reads are by folder argument. collect.py says it never reads the environment or the home folder (collect.py header). api_settings.py says the same for its routes.

- Claude Code transcripts (JSONL): <config dir>/projects/<folder>/ files. transcripts.py:1-16 keeps only usage fields of assistant rows, plus agent links from user rows. Horizon is 61 days (transcripts.py:443-444, Reader.horizon_days=61). Folders map to projects by sanitized path (transcripts.py:93-166).
- Subagent metadata: meta files next to agent transcripts, read for the agent type (transcripts.py:236-259).
- Settings files at each scope (collect.py:296-337; the project file at 336, user file at 337, local file at 315):
  - user: <config dir>/settings.json
  - project: <project>/.claude/settings.json
  - local: <repo root>/.claude/settings.local.json (local_root.py; the repo root is worked out by git_check.py:232 repo_root)
  - managed: /Library/Application Support/ClaudeCode on macOS, /etc/claude-code on Linux, C:\Program Files\ClaudeCode on Windows (server.py:105-109). Managed files are read, never written.
- Environment variables named by the rules: collect.py:370 collect_env, from shell env passed in by the server.
- Agent files: <project>/.claude/agents/*.md and <config dir>/agents/*.md (collect.py:406-416). Frontmatter field table: dashboard/agent_fields.json (4 top-level keys, including fields); frontmatter parsed by agent_frontmatter.py.
- Rules files: <project>/.claude/rules and <config dir>/rules (collect.py:435-440).
- Rules table: dashboard/rules.json (schema_version 3; 12 models, 10 variables, 84 rules).
- Prices: dashboard/prices.json (API list prices in USD per million tokens, keyed by rules.json model ids; prices.py:1-15). Every cost on screen is an estimate.
- Project list: <config dir>/routing-dashboard.json (projects.py:1-22). Read again on every request.
- Git state: git_check.py reads only .git entries it can lstat and open (git_check.py docstring). It answers repo place (root, linked, subfolder, no_repo) and whether git ignores the local settings file.
- Installer plan for the Installed files page: built in memory from the repo's dashboard payload and the choices in the config folder (api_settings.py:363-369).
- Reads and caching:
  - Settings, rules and files: no cache, read on every request (api_settings.py header, "Nothing here caches").
  - Usage: an in-memory per-file cache on the Reader. A file is parsed again only when it grew (transcripts.py:462-470 read_folder). The reader starts a warm read of every transcript on a daemon thread at server start (api_usage.py:141-146). A built All-projects answer is kept per scope (api_usage.py header).
  - Live: per-folder records and a per-session index, rebuilt only when a file changes (api_live.py header).
- Scale notes in the repo: one All-projects build takes "a couple of seconds on 150,000 records" (api_usage.py header). A /api/live call takes "about 7 ms (30 ms after a change) with 300 transcript files" (live_poll.js:16 comment).

## 3. Writes

The default launch writes nothing. "writes no file of any kind, __pycache__ included" (server.py:8-14 docstring). Only --allow-edits adds POST routes.

Write routes (server.py:157-171, only when --allow-edits):
- /api/edit/preview (api_edit.py:1925)
- /api/edit/save (api_edit.py:1950)
- /api/edit/undo, which also covers "undo anyway" (api_edit.py:2067)
- /api/edit/backup-preview (read-only preview of a backup, api_edit.py:2132)
- /api/edit/restore (api_edit.py:2104; a restore is a save whose bytes are a checked backup)

Read routes for edits: /api/edit (mode), /api/edit/targets (api_edit.py:1899), /api/edit/history (api_edit.py:2153).

Settable keys (api_edit.py:1-6 and SETTINGS table at 304-307): effortLevel, maxEffortLevel, model, autoCompactWindow. Nothing else. No path or key name comes from a request, only a setting name checked against the table (api_edit.py:1-6).

What a save can do (README.md:425-441 and api_edit.py:1-14): change a line that exists, add a line, remove a line, or create the file with its .claude folder. It leaves every other byte alone. It never touches managed settings or symlinks (README.md:425-441, edit_store.py:1-16).

Write steps (edit_store.py:1-30 docstring, module docstring): read the file, plan, write the backup, write the ledger, write a temp file, walk again and compare bytes, rename by descriptor, fsync, read back and compare, prune to the newest 20 rows (edit_store.py:70 RETENTION = 20). Every file operation uses a directory descriptor. A file over 1 MiB is refused (edit_store.py:71 MAX_FILE). Reads never write.

Backups and ledger: <config dir>/routing-dashboard/backups/<target-id>/ with NNNNNN-<edit id>.bak, ledger.json, and .lock. Folders 0700, files 0600 (edit_store.py:1-30; README.md:485-487). A file that did not exist gets an empty .absent marker (edit_store.py docstring). The ledger masks values. Rows include time, kind (edit, undo, restore), layer, key_path, old and new values, backup name, and before and after SHA-256 hashes (README.md:455-483).

Other writes in the repo that are not the server: dashboard/reference_page.py writes docs/rules-reference.md (reference_page.py header). Not part of the running app.

Edit security gate (server.py:474-526, _handle_write and _token_ok):
- Host must be 127.0.0.1:<port> or localhost:<port> (server.py:385-388).
- Origin must match the same origin (server.py:389-394).
- Sec-Fetch-Site must be same-origin when sent (server.py:395-408).
- Content-Type must be application/json (415 otherwise).
- No Transfer-Encoding. Content-Length required and at most 65536 bytes (DRAIN_CAP, server.py:97).
- X-Dashboard-Token must be this launch's token (server.py:515-526). The token is new on each launch (server.py:8-14 docstring). It is printed only in the link, as #/settings?edit=<token>, and a fragment never reaches a server or a log (README.md:437; server.py:14-15).
- The body must be a JSON object (400 otherwise).
- The browser keeps the token in sessionStorage and memory and sends it only in the header (edit_session.js:1-12).
- The server compares file bytes just before the rename (README.md:447). A write by another program in that window is lost. A stated limit.
- Save fires Claude Code ConfigChange hooks (README.md:443).
- The flag refuses to start on win32 and refuses a --fixture folder inside the repo (README.md:441; server.py:8-14).

Undo: plain undo refuses a file changed since the save. Undo anyway needs a preview. Older backups restores earlier rows (README.md:449-455; edit_backup.js header). Retention is 20 rows per file, and an undo counts as one (README.md:485).

## 4. Launch and lifecycle

Entry points:
- Slash command: /routing-dashboard:dashboard [start|stop|reload|status|open|project <dir>|edits|log] [--port N] [--all] [--no-open] [--key-file] (skills/dashboard/SKILL.md:3-4). Model pinned to haiku in the skill's frontmatter (SKILL.md:6).
- The skill runs one line: python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard" with --data, --default-project, --session and the arguments (SKILL.md:9). The allowed Bash rule covers that launcher line only (SKILL.md:7).
- Launcher actions, from bin/routing-dashboard:16-20: start (default), stop [--all], reload, status [--all], open, project DIR, edits, log.
- Direct server: python3 dashboard/server.py with --config-dir, --project, --port, --fixture, --allow-edits, --launch-fd (server.py:619-641; main at 663).

Port and browser:
- Default port 8377 (server.py:96; plugin README:35). The plugin takes a free port when 8377 is busy. --port fails rather than picking another (plugin README:48).
- The server binds 127.0.0.1 only (server.py:95, with no option to change it, server.py:8-9).
- The launcher opens the page in the browser, and skips the open over SSH or on Linux with no display (plugin README:52). The exact browser call was not traced. --no-open skips it (plugin README:50).
- --launch-fd N writes the URL line to an open file descriptor so the edit key never lands in the log (server.py:9-15 docstring; bin/routing-dashboard:26-27 says the key is never printed or logged).
- Edit key over SSH: edits --key-file writes the link to a file only the owner can read, in the plugin data folder (plugin README:58-64). The file is deleted by stop and reload (plugin README:64).

State and multi-project:
- State lives in the plugin data folder: servers/<id>.json, servers/.lock, logs/<id>.log, links/<id>.url. The id is sha1 of the real project path, first 12 hex characters (bin/routing-dashboard:22-24).
- One server per project. A second session in the same project reuses it (plugin README:35). status shows all servers (plugin README:42).
- Projects list: routing-dashboard.json in the config folder, read per request, adds more projects to the dropdown (projects.py:1-22; README.md:413-416).
- The Project dropdown picks one project or All (README.md:391).

Stop:
- Ctrl-C or SIGTERM stops a direct server (server.py:9-15).
- The plugin's SessionEnd hook stops the server when the last Claude Code process in its project exits (plugin README:66-68; hooks.json:3-5). A manual launch is marked manual and not stopped by that hook (plugin README:72).
- A crash leaves a stale server that the next command notices (plugin README:70).
- stop --all stops all plugin servers.

## 5. Platform and environment

- macOS. Tested on macOS, bash 3.2.57, python3, Claude Code 2.1.302 (README.md:520; plugin README:128). Linux is untested (README.md:198, 520). Windows is not supported (plugin README:128; server.py refuses edits on win32, README.md:441).
- Python 3.9 or later, standard library only (README.md:403; plugin README:127; api_settings.py, api_edit.py and collect.py headers; bin/routing-dashboard:8). Prerequisite list at README.md:192-199.
- Claude Code 2.1.302 is the tested version (README.md:9-12 quick start). Settings behavior depends on Claude Code 2.1.211 and later for the repo-root local settings file (README.md:425-431; git_check.py docstring).
- Offline: the server reads local files only. No route calls out (server.py routes at 144-153). Prices and rules ship as files in the repo. The page loads only its own static files (CSP at server.py:119-122: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:). I did not check for a network call in every JS file. [NEEDS CONFIRMATION: a grep for fetch or external URLs in dashboard/static/js]
- Localhost only: bind 127.0.0.1 (server.py:95), Host and Origin checks (server.py:385-394), no login (README.md:411-412).
- Claude Code plugin packaging:
  - Plugin name routing-dashboard, version 0.1.7 (plugins/routing-dashboard/.claude-plugin/plugin.json:3).
  - Marketplace model-routing with two plugins: routing-dashboard and hivemind (README.md:37-45, 495-500).
  - Layout: plugins/routing-dashboard/bin/routing-dashboard (the launcher), skills/dashboard/SKILL.md, hooks/hooks.json, and payload/ (a copy of the dashboard, agents, hooks, rules, skills and docs; payload/BUILD.json holds the payload hash). The launcher runs payload/dashboard/server.py (bin/routing-dashboard:565).
- Hooks shipped by the dashboard plugin (hooks/hooks.json:3-8):
  - SessionEnd: runs the launcher with session-end.
  - PreToolUse on Bash, matching python3 *bin/routing-dashboard*, that blocks a model's own launcher call (onFailure: block). Refers to the guard in L-bd45 and L-979a of HiveMind.
- Skills shipped: one skill, dashboard (skills/dashboard/SKILL.md). The payload folder also holds route-project and setup-model-routing skills (plugins/routing-dashboard/payload/skills), which the plugin's own skill list does not expose. [NEEDS CONFIRMATION: whether payload skills are used by the dashboard plugin at all]
- CONFLICT: plugin README:68 says "the plugin's one hook, on SessionEnd". hooks.json shows two entries (SessionEnd and PreToolUse guard, lines 3-8).

## 6. Non-functional

Accessibility:
- AA floor on all text, non-text 3:1 (CLAUDE.md:14; tokens.css header lines 3-6, which list computed contrast ratios).
- Accepted exception, owner, since October 30: --rk-1 and --rk-2 in light mode under 3:1 for non-text, on the condition that stacked bars keep legend totals or a kinds table and a visible start edge (CLAUDE.md:14).
- Status is shape and word, never hue alone (tokens.css header line 2; CLAUDE.md Design section, status tokens).
- Screen reader items exist on the Live dispatch canvas (live_flow.js header). Reduced motion and focus order were not surveyed.

Light and dark:
- Light by default, dark under prefers-color-scheme, forced by data-theme (tokens.css:2-3). A theme query parameter exists (router.js THEMES, query.theme).

Widths:
- Target widths 1440 and 375 (CLAUDE.md:18). Desktop E2E tests use 1440 (tests/test_band_arrange_e2e.py:184, 191).
- Narrow layout breakpoint at 720px in app.css (68, 169, 274, 311) and live.css (93, 177), plus JS checks at 720 (band_arrange.js header; live_flow.js header).

Strings and i18n:
- All on-screen copy in dashboard/static/strings.json (823 keys, English only; lang="en" at index.html:2). One file, no locale files found in dashboard/static.
- t(key, slots) and tn(key, slots) in format.js:14-38. A key missing from strings.json shows the key itself (format.js:15).
- Keys are counted only in a literal t("key") call (tests/test_static_strings.py, per format.js:13 comment).
- Every server value is data and goes into the DOM as text (page headers; no markup from data).

Performance:
- /api/live about 7 ms per call with 300 files (live_poll.js:16 comment).
- One All-projects build a couple of seconds on 150,000 records (api_usage.py header).
- Warm-up of every transcript on server start (api_usage.py:141-146).
- Test suite: 3575 tests, 88 skipped, about 370 seconds from the repo root (recorded in .claude/rules/project-facts.md:5, dated 2026-11-07; not re-run for this report). 86 skips need MR_E2E=1.

Refresh behavior summary:
- Live: polled. One request at a time, once a second while the page is visible (live_poll.js:16, app.js not involved). Wait 10 seconds after a server error (RETRY_MS, live_poll.js:17).
- Usage pages: loaded per project and range, drawn from one payload; a loading strip polls /api/projects once a second until usage lands (app.js:20-26, 93).
- Settings, rules, files, attention: fetched on load, no timer.
- Clock: a one-second tick on the live page (live.js:910 setInterval 1000).

## CONFLICTS and gaps

1. Live refresh rate. README.md:393 says the live page refreshes "every 3 seconds while the tab is in view". live_poll.js:16 sets POLL_MS = 1000 and live_poll.js:2 says "every few seconds". Code is 1 second. Decide which one the rebuild promises.
2. Editable settings. README.md:425 says a launch "can change one setting, the main session's effort level". api_edit.py:1-6 and SETTINGS (api_edit.py:304-307) list four: effortLevel, maxEffortLevel, model, autoCompactWindow. settings.js:34-36 agrees with the code. README is stale.
3. Plugin hook count. plugin README:68 says one hook. hooks.json has two.
4. Not checked: whether the page makes any network request beyond its own origin, the exact browser-open call, the keyboard and focus rules in each page, and full e2e coverage per page. Listed as NEEDS CONFIRMATION above.
5. Not checked: the design benchmark (docs/design/usage-stack/) beyond its existence, and the per-page visual specification.

## HIVEMIND
USED T-7629: suite timing cited from the recorded fact, not re-run.
END HIVEMIND

# Routing Dashboard, architecture audit of the current app

Written 2026-11-08T01:47-05:00 by the architecture lead for the from-scratch rebuild. Repo read at branch chore/hivemind-consolidation-nov-7, commit 7d8af23. Nothing in the repo changed.

Paths are relative to /Volumes/Warehouse/Projects/claude-code-model-routing unless absolute. "path:line" cites the line read on that commit.

Sources this builds on, without repeating them: stack-research/20-decisions.md (owner decisions win, later sections override earlier ones), 10-features.md, 01-inventory.md, 22-rules-engine.md, 23-domain-carryover.md, 19-launcher.md and 18-config-surfaces.md in /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/stack-research/.

How it was checked:
- Read the module headers, function lists and the route, cache and edit code paths.
- Built the demo set into the scratchpad (tests/fixtures/demo/build_demo.py) and ran `dashboard/server.py --fixture <built set> --port 18977`, read-only. Called every GET route and recorded status, size and shape. The server was stopped afterwards. Nothing under ~/.claude, no real transcript and no real settings file was read.

Demo payload sizes (Tidewater reporting, warm reader, 538 transcript files):

| Route | Status | Bytes | Time |
|---|---|---|---|
| /api/projects | 200 | 906 | 1 ms |
| /api/settings?project=tidewater-reporting | 200 | 51,950 | 4 ms |
| /api/usage?project=tidewater-reporting | 200 | 235,856 | 69 ms |
| /api/usage?project=all | 200 | 267,491 | 75 ms |
| /api/rules | 200 | 83,316 | 1 ms |
| /api/files | 200 | 448 | 1 ms |
| /api/edit | 200 | 37 | <1 ms |
| /api/edit/targets?project=tidewater-reporting | 200 | 1,032 | 4 ms |
| /api/edit/history?project=tidewater-reporting | 200 | 18 | <1 ms |
| /api/live?project=tidewater-reporting | 200 | 201 | 11 ms |
| /api/live?project=all, /api/settings?project=all | 400 | 25 | <1 ms |

Inside one usage view (30d), the `sessions` list is 117,001 bytes and `by_agent` is 21,446 bytes, and the payload carries three views (today, 7d, 30d).

---

## 1. Component inventory

### 1.1 Backend modules (dashboard/*.py, 12,961 lines, Python 3.9 standard library only)

| Module | Path | What it does | Inputs | Outputs | Depended on by |
|---|---|---|---|---|---|
| server | dashboard/server.py (740) | HTTP server, route table, security gate, static files, CLI, Context. Binds 127.0.0.1 only. | argv, os.environ (main only, server.py:663), fixture folder | JSON, static bytes, URL line on stdout or --launch-fd | launcher, 12 test files |
| api_usage | dashboard/api_usage.py (287) | /api/usage and the reader fields of /api/projects. Holds Cache (reader, built answers, live index). Warm-up thread. Zone and clock. | Context, ?project | 3 precomputed views per scope | server, api_live (Cache) |
| api_settings | dashboard/api_settings.py (411) | /api/settings (collect then resolve per request), /api/rules, /api/files (installer plan). Attention groups, rule records. | Context, ?project | entries, rows, rules, files, attention | server, api_usage, api_edit |
| api_live | dashboard/api_live.py (627) | /api/live, one session of one project, minute buckets, dispatch runs, etag. | Context, ?project, ?session, ?etag | live payload or {unchanged} | server |
| api_edit | dashboard/api_edit.py (2,179) | Edit read routes (mode, targets, history) and write routes (preview, save, undo, restore, backup-preview) for 4 settings. Builds views by running the resolver over overlays. | Context, query or JSON body | targets, previews with HMAC bases, edit rows | server |
| collect | dashboard/collect.py (465) | Reads settings files (user, project, local, managed and managed-settings.d), env named by rules, agent and rules folders. Masks secrets. | folders passed in, shell env | collected dict with file and line per value | api_settings, api_edit, resolve, json_edit |
| resolve | dashboard/resolve.py (1,893) | Pure resolver. Lines up candidates per row, gets rule votes, combines them, writes the reason. Also the fixture runner CLI. | Inputs, rules.json, agent_fields.json | entry list (key, value, status, layer, file, line, rule ids, reason) | api_settings, api_edit, api_usage, pincheck, projects, prices, usage |
| rules_schema | dashboard/rules_schema.py (1,081) | Schema check of rules.json, constants (EFFORT_LEVELS, LAYERS). CLI. | rules.json | error list | resolve, api_edit |
| transcripts | dashboard/transcripts.py (760) | JSONL reader. Keeps usage fields of assistant rows plus agent links. Per-file cache, re-reads only grown bytes. 61-day horizon. Folder to project matching. | <config>/projects/** | Record rows, Links, ReadResult | api_usage, api_live |
| usage | dashboard/usage.py (889) | Pure aggregation. build_views for today, 7d, 30d. Dedupe by message id. | records, now, tz, prices, catalog, pin_fn | View dicts | api_usage, api_live |
| prices | dashboard/prices.py (277) | Loads and checks prices.json, prices one request (tiers, fast, geo, cache). CLI check. | prices.json, catalog | USD parts or None | usage, api_usage, api_live |
| pincheck | dashboard/pincheck.py (245) | Joins resolver winner with what runs did. States matches, matches_lowered, overridden, differs, mixed, cannot_check. | resolver entries, runs | PinCheck per agent | api_usage via usage.build_views |
| projects | dashboard/projects.py (203) | Project list from <config>/routing-dashboard.json, read per request, plus the launch folder. Keys, states, plan. | Context | ProjectList, /api/projects base | api_usage, api_settings, api_edit, edit_store |
| agent_frontmatter | dashboard/agent_frontmatter.py (533) | Strict YAML-subset front matter reader with line numbers. Checks agent_fields.json. CLI. | agent file text | fields, errors, lines | collect, resolve |
| json_edit | dashboard/json_edit.py (495) | Byte-span JSON edits (replace, insert, remove, new file), masking, structured diff. Pure. | bytes | bytes, diff | api_edit |
| edit_store | dashboard/edit_store.py (1,158) | The only writer. Targets by project and layer, dir-fd walk, backup, ledger, temp, rename, fsync, verify, prune to 20. Refuses symlinks, hard links, managed, files over 1 MiB. | Target, plan callback | ledger rows, files under <config>/routing-dashboard/backups | api_edit, server |
| git_check | dashboard/git_check.py (317) | lstat-only repo place, repo root reader, one hardened `git check-ignore`. | project path | root, linked, subfolder, no_repo; ignore state | local_root, api_edit |
| local_root | dashboard/local_root.py (81) | Which settings.local.json a project uses (repo root since 2.1.211) and the leftover file. | project, version | Local(path, leftover) | api_settings, api_edit, edit_store |
| version | dashboard/version.py (149) | Installed Claude Code version from files on PATH (native, Homebrew cask, npm), compare versions. | PATH text | "x.y.z" or None | api_settings, local_root |
| reference_page | dashboard/reference_page.py (171) | Dev tool. Writes docs/rules-reference.md from rules.json plus reference_copy.md. | rules.json | markdown file | tests only |

Repo-root modules the dashboard imports:
- agent_md.py (137): agent file walks and front matter helpers shared with install.py. Imported by collect.py:30 after collect.py:23-27 puts the repo root on sys.path.
- install.py (1,589): the installer. Imported by api_settings.py:25 for /api/files only.

### 1.2 API routes (server.py:140-171)

Read routes, GET and HEAD, each `(ctx, query) -> (status, payload)`:

| Route | Handler | Query | Reads | Cache |
|---|---|---|---|---|
| / and /static/<file> | server.Handler._send_static | none | dashboard/static | none (Cache-Control no-store) |
| /api/projects | api_usage.api_projects | none | routing-dashboard.json, launch folder, reader counters, PATH for version | none |
| /api/usage | api_usage.usage | project (key, `all`, or none for current) | all transcripts via Reader, prices.json, rules.json catalog, and for one project the full collect plus resolve for the pin check | built answer per scope, 60 s and fingerprint (api_usage.py:47, 242-275) |
| /api/settings | api_settings.settings | project (none for current; `all` gives 400) | settings files at 4 layers, env, agents, rules folders, git, PATH | none, every request collects and resolves |
| /api/rules | api_settings.rules | none | rules.json in memory, PATH | none |
| /api/files | api_settings.files | none | install.py plan over the repo or fixture repo, choices file, config folder | none |
| /api/live | api_live.live | project (required, not `all`), session, etag | one project transcript folder | per-folder session index keyed by signature |
| /api/edit | api_edit.edit_info | none | EditState | none |
| /api/edit/targets | api_edit.targets | project, setting | resolver many times over overlays | none |
| /api/edit/history | api_edit.history | project | ledgers under <config>/routing-dashboard/backups | none |

Write routes, POST only, present only with --allow-edits (server.py:155-171), each `(ctx, body)`:

| Route | Handler | Body | Writes |
|---|---|---|---|
| /api/edit/preview | api_edit.preview | project, setting, target, action, value | nothing |
| /api/edit/save | api_edit.save | plus base_file, base_trail, base_others HMACs | one settings file, backup, ledger |
| /api/edit/undo | api_edit.undo | edit id, optional undo anyway with base_file | same |
| /api/edit/restore | api_edit.restore | backup row, base_file | same |
| /api/edit/backup-preview | api_edit.backup_preview | backup row | nothing |

Gate for every POST: Host, Origin required, Sec-Fetch-Site same-origin, Content-Type application/json, no Transfer-Encoding, Content-Length at most 65,536, one X-Dashboard-Token equal to the launch token by hmac.compare_digest, JSON object body (server.py:474-527).

### 1.3 Front-end modules (dashboard/static, 10,842 lines of JS, no build, CSP script-src and style-src 'self')

Core:

| Module | Path | What it does | Depended on by |
|---|---|---|---|
| index.html | dashboard/static/index.html (35) | Shell with 13 hidden `section[data-page]`, loads tokens.css, app.css, live.css, app.js | server |
| app | js/app.js (634) | Boot, state, project and range switching, payload loading, usage loading poll, edit session wiring, render dispatch | index.html |
| router | js/router.js (142) | Hash parse and build, PAGES, BAND_SETTINGS, sectionFor, navFor | 15 importers |
| api | js/api.js (109) | fetchJSON, postJSON, createApi with a never-expiring promise cache per page load | app.js |
| shell | js/shell.js (182) | Sidebar, top bar, project switcher, version chip | app.js |
| live_poll | js/live_poll.js (147) | Live poller, one request in flight, etag, 1 s poll, 10 s retry | pages/live.js |
| edit_session | js/edit_session.js (192) | Takes the token from the hash, keeps it in sessionStorage and memory, asks /api/edit for the mode, sends writes | app.js |

Shared components and helpers:

| Module | Path | Exports |
|---|---|---|
| h | js/h.js (106) | h, s, externalLink, setLocalHref, frag, clear. DOM builder, text only, URL checks |
| components | js/components.js (173) | chip, pinPill, card, kpi, delta, estLine, inline, table, pageHead, rangeControl, footerLine, emptyState, projectPickerEmpty |
| charts | js/charts.js (204) | ring, miniRing, stackedTokens, hbars, daybars, legendRows, kindsLegend, hatchDefs, modelClass |
| format | js/format.js (148) | t, tn, renderText, number, cost, percent, date and hour formatting, RANGES |
| icons | js/icons.js (53) | icon set in one stroke style |
| usage-page | js/usage-page.js (190) | fillUsage, the one entry for every usage page with empty, loading and error states |
| usage-cards | js/usage-cards.js (139) | KPI row, per-bucket, cost and tokens by model and agent, cache, effort, kinds table |
| usage-loading | js/usage-loading.js (273) | Loading strip with files-read count, placeholder cards, error notice with Try again |
| pin-view | js/pin-view.js (214) | Words of a pin check for the Agents table and Agent detail |
| band_order | js/band_order.js (143) | Pure fit and move rules of the Settings band |
| strings | static/strings.json (825 lines) | Every on-screen word |
| styles | tokens.css (135), app.css (944), live.css (196) | Tokens, page styles, Live styles |

Edit UI (14 files, about 3,500 lines): edit_flow.js (1,031, state and actions), edit_card.js (818, editing body, rail, foot), edit_review.js (458), edit_foot.js (269), edit_words.js (268), edit_ui.js (154), edit_backup.js (151), edit_pick.js (91), edit_setting.js (84), edit_ref.js (9, mirrors api_edit.ref_of through tests/fixtures/edit_ref_table.json).

Pages (js/pages, one module per section): live.js (926) and live_flow.js (684), overview.js (31), all-projects.js (80), agents.js (65), agent-detail.js (117), models.js (53), sessions.js (72), session-detail.js (76), settings.js (337) with band.js (617), band_arrange.js (202), band_drag.js (317), read_frame.js (60) and where.js (129), trail.js (289), attention.js (128), files.js (72), rules.js (205).

### 1.4 Data files

| File | What it is | Read by |
|---|---|---|
| dashboard/rules.json | Schema v3. 12 models, 10 variables, 84 rules with quotes, experiments, confidence | resolve.load_rules at start-up (server.py main) |
| dashboard/agent_fields.json | 19 front matter fields Claude Code reads | resolve.load_agent_fields |
| dashboard/prices.json | List prices per catalog id, tiers and modifiers, verified_on | prices.load_prices, lazily on first usage call |
| dashboard/experiments/*.json (23) and harness/ | Experiment records cited by rules, and the precedence harness | tests, rules references |
| dashboard/reference_copy.md | Hand-written part of docs/rules-reference.md | reference_page.py |
| <config>/routing-dashboard.json | Project list and plan, read per request | projects.load |
| <config>/model-routing-choices.json | Installer choices | api_settings.files via install.load_choices |
| <config>/routing-dashboard/backups/<id>/ | NNNNNN-<edit>.bak or .absent, ledger.json, .lock | edit_store |
| browser localStorage `band-order:<project path>` | Band cell order (pages/band.js:219-263) | band.js |
| browser sessionStorage | Edit token and launch id (app.js:106-110, edit_session.js:4-7) | edit_session.js |

### 1.5 Plugin and repo pieces

| Piece | Path | What it does | Depends on |
|---|---|---|---|
| Marketplace | .claude-plugin/marketplace.json | model-routing marketplace with routing-dashboard and hivemind | plugin folders |
| Plugin manifest | plugins/routing-dashboard/.claude-plugin/plugin.json | name, version 0.1.7 | build_plugins |
| Launcher | plugins/routing-dashboard/bin/routing-dashboard (1,230) | start, stop, reload, status, open, project, edits, log, guard, session-end. One server per project id sha1(realpath)[:12] (bin/routing-dashboard:363-364). State, lock, logs, link files in CLAUDE_PLUGIN_DATA | payload/dashboard/server.py |
| Slash command | plugins/routing-dashboard/skills/dashboard/SKILL.md | One `!` line runs the launcher with --data, --default-project, --session. Pinned to haiku | launcher |
| Hooks | plugins/routing-dashboard/hooks/hooks.json:3-8 | SessionEnd stops idle servers. PreToolUse guard blocks a model's own launcher call | launcher |
| Payload | plugins/routing-dashboard/payload/ | Byte copy of dashboard/, install.py, agent_md.py, agents, rules, hooks, skills, docs. BUILD.json hash | tools/build_plugins.py |
| Builder | tools/build_plugins.py (410) | Writes payloads, --check for drift, refuses a changed payload under an unchanged version | git ls-files |
| Installer | install.sh, install.py (1,589), agent_md.py | Installs routing agents, rules, hooks, skills, reference doc into the config folder, six hook entries in settings.json | repo agents/, rules/, hooks/, skills/ |
| Routing hooks | hooks/require-agent-model.py, hooks/check-agent-models.sh | Installer payload, not the app | install.py |
| HiveMind | hooks/hivemind_*.py, plugins/hivemind/ | Separate plugin, shares hivemind_lib.py with the dashboard payload | not the app |
| Skill probe | tools/skill_probe/ | Checks the PreToolUse guard behaviour per Claude Code version | test_skill_probe.py |

### 1.6 Test areas (tests/, 48,140 lines of Python in 68 files, 16,900 lines of .mjs)

| Area | Files (lines) | Covers |
|---|---|---|
| Resolver and rules | test_resolve (2,676) plus 123 folders in tests/fixtures/resolution, test_rules_schema (1,836), test_api_rules, test_reference_page, test_doc_anchors, test_harness_guard (1,080) | Precedence, rules.json schema, doc anchors, harness guard. The fixtures are the porting spec |
| Collectors | test_collect (919), test_collect_overlay, test_agent_frontmatter, test_agent_md, test_local_root, test_git_check (900), test_version | File reading, masking, front matter, repo root, version |
| Usage and live | test_transcripts (874), test_transcripts_links, test_usage (1,261), test_prices, test_pincheck, test_api_usage (1,149), test_api_live (1,287), tests/fixtures/transcripts, live, live_flow, rounds | Reader, aggregation, pricing, pin check, live payload |
| Edit core | test_edit_store (3,119), test_json_edit, test_api_edit (5,141), test_api_edit_settings (1,236), test_edit_server, test_edit_security (1,060), test_picker | Writes, backups, ledger, gate, routes |
| Server and projects | test_server (1,115), test_server_launch, test_projects, test_api_settings, test_api_files, test_features, test_parity, test_demo | Routes, gate, CLI, project list, installer parity, demo truth |
| Front end without a browser | test_pages_js, test_shell_js, test_settings_js, test_edit_card_js, test_edit_session_js, test_live_js, test_live_flow_js, test_attention_js, test_files_js, test_rules_js over tests/js/*.mjs and fakedom.mjs | Page modules on a fake DOM |
| Static and design | test_static_shell (735), test_static_strings, test_tokens_contrast | Shell, string keys, contrast grades |
| Browser E2E (MR_E2E=1, headless Chrome) | test_pages_e2e, test_shell_e2e, test_settings_e2e, test_band_arrange_e2e, test_edit_e2e, test_edit_e2e_repo_root, test_edit_e2e_settings, test_live_e2e, test_live_flow_e2e, test_e2e_checks over tests/e2e_checks/*.json, test_plugin_e2e, test_plugin_hivemind_e2e | Rendered pages at 1440 and 375 |
| Plugin and install | test_plugin_build (821), test_plugin_launcher (1,259), test_plugin_hivemind, test_skill_probe, test_hook_roster, test_hivemind (4,397) | Payload drift, launcher, guard, HiveMind |
| Harness | tests/helpers.py (806, Sandbox, home guards), test_tmp_guard | Throwaway HOME, temp base outside git |

---

## 2. Sitemap from the system side

Every page also depends on the boot calls: /static/strings.json, /api/projects, /api/edit, and for the current project /api/usage and /api/settings, plus /api/rules and /api/files (app.js:383-416, 602-630). A project switch loads usage and settings for the new project whatever page is open (app.js:383-407, 577). Query parameters live in the hash: project, range (today, 7d, 30d), theme (light, dark), setting (Settings only), edit (token, stripped before routing). router.js:46-53, 79-96.

| Route | Section module | API calls the page needs | Data each call reads | Refresh | Query params |
|---|---|---|---|---|---|
| #/ and #/overview | pages/overview.js | /api/usage?project, /api/settings?project (Needs attention card) | transcripts, prices, catalog; settings files, agents, env | Once per project per page load. Range switch fetches nothing. Loading strip polls /api/projects every 1 s until usage lands (app.js:202-238) | project, range, theme |
| #/overview with project=all | pages/all-projects.js | /api/usage?project=all | every transcript folder, project list | same | project=all, range, theme |
| #/agents | pages/agents.js | /api/usage?project | as overview, with pin check from the resolver | same | project, range, theme |
| #/agents/<name or @main> | pages/agent-detail.js | /api/usage?project | by_agent of the view | same | project, range, theme |
| #/models | pages/models.js | /api/usage?project | by_model | same | project, range, theme |
| #/sessions | pages/sessions.js | /api/usage?project | sessions of the view, 10 shown, Show all expands locally | same | project, range, theme |
| #/sessions/<id> | pages/session-detail.js | /api/usage?project | the 30d view only, whatever the range | same | project, theme |
| #/live | pages/live.js, live_flow.js | /api/live?project&session&etag | one project transcript folder | 1 s poll while visible and not paused, 10 s after an error, stops on 4xx (live_poll.js:16-17). Clock tick every 1 s (live.js:910) | project, theme. The session choice is not in the URL |
| #/settings | pages/settings.js, band.js, read_frame.js, where.js, edit_* | /api/settings?project; with edits on, /api/edit/targets?project&setting and /api/edit/history?project; POST preview, save, undo, restore, backup-preview | settings files, env, agents; ledgers | Once per page load. After a write every project's cache is dropped and refetched (app.js:163-195) | project, theme, setting, edit |
| #/settings/<agent>/<setting> | pages/trail.js | /api/settings?project; for @main effortLevel also /api/edit/targets | as settings | same | project, theme |
| #/attention | pages/attention.js | /api/settings?project | attention groups built by the server | same | project, theme |
| #/files | pages/files.js | /api/files | installer plan over the repo, config folder | once per page load | theme (same for every project) |
| #/rules | pages/rules.js | /api/rules | rules.json, installed version | once per page load. Search and filter are local | theme |
| unknown | rewritten to overview | | | | |

---

## 3. Data flow

### 3.1 Start-up and reads

```
launcher (plugin bin) ──Popen──> server.py main
   argv, env ──> Context(config_dir, project_dir, managed_dir, shell_env, rules.json, agent_fields.json)
   start_warm thread ──> transcripts.Reader.read(<config>/projects/**)   [every folder, 61-day horizon]
                                       │
                                       └─> Cache.reader (records in memory, per-file size/mtime signature)

browser boot (app.js)
   GET /static/strings.json
   GET /api/projects ──> projects.load(routing-dashboard.json) + reader counters + version (PATH)
   GET /api/edit
   GET /api/usage?project=K ──> lock ─> Reader.read (stat, parse grown bytes)
                                 ├─> projects.load
                                 ├─> collect + resolve (pin check entries)           [every request]
                                 ├─> usage.build_views x3 ranges ─> pincheck
                                 └─> Cache.built[K] (fingerprint, payload, 60 s)
   GET /api/settings?project=K ──> local_root (git_check lstat) ─> collect(settings x4, env, agents, rules dirs)
                                   ─> resolve(rules.json) ─> rows, rules, files, attention   [no cache]
   GET /api/rules ──> rules.json in memory + version
   GET /api/files ──> install.list_agents/load_choices/build_plan(repo) ─> byte compare in config folder

browser cache: api.js once() keeps each promise for the page load (api.js:55-66).
```

### 3.2 Live flow

```
pages/live.js active and tab visible
  every 1 s, one in flight: GET /api/live?project=K&session=S&etag=E
     ─> Reader.read_folder(folder of K) (grown bytes only)
     ─> Cache.live[folder] = (signature, session index + Links)   [rebuilt when the folder changes]
     ─> usage.dedupe, minute buckets, runs tree, etag sha256[:16]
     ─> {unchanged:true} when E matches, else full answer
  error ─> 10 s retry; 4xx ─> stop ("unknown")
```

### 3.3 Edit flow

```
launcher edits ─> server --allow-edits ─> token = token_urlsafe(32), EditState(token, launch_id, edit_store.Store)
   URL line ─> --launch-fd pipe ─> launcher ─> browser opens #/settings?edit=<token>
browser: edit_session.take() strips the token, keeps it in sessionStorage + memory, GET /api/edit for mode

Settings page, open cell (effortLevel | maxEffortLevel | model | autoCompactWindow)
  GET /api/edit/targets?project&setting ─> _view: collect + resolve, then resolve again per level per file over overlays
  POST /api/edit/preview {project, setting, target, action, value}
       ─> json_edit splice in memory ─> resolve over overlay ─> diff, warnings,
          base_file / base_trail / base_others HMACs (keyed by the launch)
  POST /api/edit/save {... + bases}
       ─> edit_store.save(target, plan) under thread lock + flock(.lock):
            1 read file  2 plan: recompute preview, compare HMACs, else Stale
            3 write backup  4 write ledger  5 temp file  6 walk again, compare, rename by dir fd
            7 fsync dir, read back, compare  8 prune to 20 rows
       ─> response: edit row + fresh /api/settings answer
  browser: dropProjectData, reload current project, targets and history fresh
  POST /api/edit/undo | backup-preview then restore ─> same store path; undo of a create unlinks
Files touched: one of <config>/settings.json, <project>/.claude/settings.json, <repo root>/.claude/settings.local.json,
               <config>/routing-dashboard/backups/<sha256(realpath)[:16]>/
```

### 3.4 Writes outside the edit flow

None at run time. reference_page.py writes docs/rules-reference.md (dev only). The launcher writes its own state, logs and link files under CLAUDE_PLUGIN_DATA.

---

## 4. Current-site findings

Severity: B bug, C doc and code conflict, D dead or stray, K coupling, I install-specific, G gap for "read anybody's setup", P performance or scale.

| # | Kind | Finding | Where |
|---|---|---|---|
| 1 | C | The server docstring says a save "changes an effort value on a line that already exists" and "adds no line and creates no file". The code edits four settings, adds lines, removes lines and creates files. | dashboard/server.py:15-19 vs dashboard/api_edit.py:1-6, 304-309; dashboard/edit_store.py:25-30 |
| 2 | C | README says an edit launch "can change one setting, the main session's effort level". Code has four. | README.md:425 vs dashboard/api_edit.py:1-6 |
| 3 | C | README says Live refreshes every 3 seconds. The poller uses 1 s, and two comments say "every few seconds". | README.md:393; dashboard/static/js/live_poll.js:1, 16; dashboard/static/js/api.js:95; dashboard/api_live.py:7 |
| 4 | C | Plugin README says "the plugin's one hook". The same README later says "both of the plugin's hooks", and hooks.json has two. | plugins/routing-dashboard/README.md:68 vs :115; plugins/routing-dashboard/hooks/hooks.json:3-8 |
| 5 | B | Usage and settings never refresh in an open tab. api.js keeps every successful promise for the page load, and only an edit drops it. The server keeps a 60 s window for "today" freshness, but the page never asks again. | dashboard/static/js/api.js:55-66; dashboard/static/js/app.js:163-195, 383-407; dashboard/api_usage.py:15-18, 47 |
| 6 | P | Every project switch loads both /api/usage and /api/settings, even on Live, Files and Rules, which need neither. Boot always loads /api/rules and /api/files. | dashboard/static/js/app.js:383-416, 577-581 |
| 7 | P | /api/usage sends all three ranges at once, and each view carries its full sessions list (demo: 235,856 bytes, 117,001 of them sessions in the 30d view). Payload grows with history, which conflicts with keeping history past 30 days. | dashboard/usage.py:10, 106, 537-570; measured on the demo |
| 8 | P | Every /api/usage call for one project runs the full collect and resolve before it can check its cache, because the resolver entries are part of the fingerprint. | dashboard/api_usage.py:242, 255-262 |
| 9 | P | /api/settings collects and resolves on every request with no cache. /api/edit/targets runs the resolver many times per call. | dashboard/api_settings.py:6, 254-285; dashboard/static/js/app.js:33-34 (comment) |
| 10 | P | The launcher runs one server per project, and each server warms a reader over every transcript of the config folder. Two open projects hold two full in-memory copies. | plugins/routing-dashboard/bin/routing-dashboard:363-364; dashboard/api_usage.py:7-11, 129-145 |
| 11 | G | History stops at the reader horizon of 61 days, and Claude Code deletes transcripts after cleanupPeriodDays (default 30). Nothing persists usage, so anything older than the cleanup is gone. | dashboard/transcripts.py:444, 478, 524 |
| 12 | G | No plugin collector. rules_schema lists a "plugin" layer, and nothing feeds it, so plugin agents, skills, hooks and settings are invisible. | dashboard/rules_schema.py:273; dashboard/collect.py:406-445 (two scopes only) |
| 13 | G | Collected surfaces are settings, env, agents (project and user only) and rules folder listings. Not read at all: CLAUDE.md and memory imports, skills, hooks as a surface, MCP (.mcp.json, ~/.claude.json), plugins, output styles, keybindings, statusLine, permissions as a view, managed agents, MDM and server-managed settings. | dashboard/collect.py:1-14, 296-447 |
| 14 | G | The front matter reader takes a strict YAML subset. Block scalars (`description: |`), an unquoted ": " inside a value and other common YAML make a file "rejected", and then model, effort, compact window and cache rows read Unknown. Ordinary third-party agents will often land there. | dashboard/agent_frontmatter.py:16-31; dashboard/resolve.py:204-220 |
| 15 | G | The project list comes only from routing-dashboard.json plus the launch folder. Another user's projects show only as unlisted folders in All projects, with no settings view. | dashboard/projects.py:1-22, 165-192; dashboard/static/js/pages/all-projects.js:1-5 |
| 16 | G | Version detection knows only the native installer, a Homebrew cask and npm. Anything else shows unknown, and every rule then reads as not due. | dashboard/version.py:119-140 |
| 17 | G | The model catalog and family regex are fixed in code and rules.json. A new model needs a code and rules release before it is named or priced. | dashboard/resolve.py:351-352; dashboard/rules.json models; dashboard/prices.json |
| 18 | G | Settings shows only the main session. Agent settings appear only on trail routes reached from Attention or pin checks, and there is no page that lists an agent file's resolved fields. | dashboard/static/js/router.js:28-31; dashboard/static/js/pages/settings.js:1-12 |
| 19 | K, I | api_settings imports the installer at module load, so every server process loads install.py, and /api/files only works where the repo or a fixture repo sits beside it. | dashboard/api_settings.py:22-25; dashboard/server.py:98 |
| 20 | K | collect.py puts the repo root on sys.path and imports agent_md.py, a module shared with the installer. The dashboard cannot ship without it. | dashboard/collect.py:23-30; agent_md.py:1-4 |
| 21 | I | Rule and experiment links are hard-coded to the GitHub repo's main branch. | dashboard/api_settings.py:28-30, 126-127 |
| 22 | I | Installed files compares the config folder with this repo's installer plan. For anyone who never ran install.sh every file reads missing, which the plugin README accepts. | dashboard/api_settings.py:363-411; plugins/routing-dashboard/README.md:5 |
| 23 | I | Backups live in a folder named after the product inside the user's config folder. Correct to keep (decision B1), but it is a write into ~/.claude that a "read anybody's setup" user may not expect. | dashboard/edit_store.py:12-15, 74 |
| 24 | K | One launch token unlocks edits on every listed project, because the edit routes pick the project from the body. The owner now wants one key per project. | dashboard/api_edit.py:1782-1798; dashboard/server.py:690-694 |
| 25 | K | The edit token sits in sessionStorage, readable by any script on the origin for the tab's life. Decision B2 drops it to memory only. | dashboard/static/js/app.js:106-110; dashboard/static/js/edit_session.js:4-7 |
| 26 | B | Band order is stored per origin, and the launcher falls back to a free port when 8377 is taken, so a saved order disappears when the port changes. | dashboard/static/js/pages/band.js:219-263; plugins/routing-dashboard/bin/routing-dashboard:557-561, 794-806 |
| 27 | G | Live refuses project=all and shows one session at a time. The chosen session is not in the URL, so a Live view cannot be linked or restored. | dashboard/api_live.py:18-23; dashboard/static/js/router.js:46-53 |
| 28 | P | HTTP/1.0 with one connection per file. The server raised its listen backlog to 128 because a burst of about 45 module requests reset connections at boot. | dashboard/server.py:336, 583-587 |
| 29 | D | server.py lists a Windows managed folder, yet edits refuse win32 and the launcher imports fcntl, so Windows never runs. | dashboard/server.py:105-109, 174-185 |
| 30 | D | Stray untracked empty folder `nonexistent/x` at the repo root, and `__pycache__` folders at the root and in dashboard/ (ignored by .gitignore:1). The server sets dont_write_bytecode, so they come from tests or tools. | nonexistent/x; __pycache__/; dashboard/__pycache__/; dashboard/server.py:68 |
| 31 | D | No CI. .github holds only an issue template, so the 3,575-test suite runs by hand. | .github/ISSUE_TEMPLATE/bug.md |
| 32 | K | Test coupling to data. Adding a rule breaks test_api_rules until e2e check texts and docs/rules-reference.md change (R-06c2). String keys count only in literal t() calls (K-819f). | tests/e2e_checks/rules.json; tests/test_static_strings.py |
| 33 | K | The plugin payload is a byte copy of the repo, so the stdlib-only rule is enforced by a payload import test, and every dashboard change needs a version bump and rebuild (L-13fb). | tools/build_plugins.py:1-20; tests/test_plugin_build.py:381-420 |
| 34 | G | Masking checks names and sk-/Bearer prefixes only. A URL with user:pass (ANTHROPIC_BASE_URL) is shown in clear. | dashboard/collect.py:32-78 |
| 35 | C | The pin check today compares runs against the resolver winner (the phase 2 overlay). The owner picked phase 1, pinned front matter against what ran, so the rebuild narrows it. | dashboard/pincheck.py:1-60 |

---

## 5. Keep, change, drop, add

Verdicts assume the owner decisions in 20-decisions.md: FastAPI and Pydantic, SQLite with WAL, React 19 with Vite and React Aria Components, TanStack Query polling by default, one server for all projects with one edit key per project, plugin collector, pin check phase 1, editing scope over settings, agents, rules folders, skills, hooks, CLAUDE.md and MCP config, and install-specific features as an optional layer.

### 5.1 Backend

| Component | Verdict | Why |
|---|---|---|
| server.py HTTP class, routes, static | Drop, replace | FastAPI routers and a static mount. The spike in spikes/1-gate ports the gate to ASGI |
| server.py security gate | Keep the rules, change the form | Port as pure ASGI middleware with --no-proxy-headers, --http h11 and a receive timeout (spike 1). Token check becomes per project |
| Context dataclass | Change | Becomes app state built at lifespan start: config dir, managed dir, env snapshot, catalogs, DB handle, key store. Project stops being part of it |
| fixture mode (--fixture) | Keep | It drives every test and the demo. Same folder layout, same "never read the real machine" rule |
| api_usage | Change | Becomes a query layer over SQLite with from, to and grouping parameters. Drop the three precomputed views and the built-answer cache |
| Cache and warm thread | Drop | Replaced by the ingest service and the database |
| api_live | Keep logic, change source | Minute buckets, runs tree, rounds and etag port. Reads come from the database tail plus the newest file bytes |
| api_settings settings and rules | Keep logic | Same payload ideas (entries, rows, rules, attention). Add a cache keyed by file signatures so a poll is cheap |
| api_settings files | Change to optional | Moves into the routing layer, shown only when the installer's choices file exists. Must not import install.py into the core |
| api_edit | Change | Keep the overlay-and-resolve preview, HMAC bases and stale checks. Generalise from four settings to a target registry. Split the 2,179 lines into settings edits, file edits and history |
| collect | Keep, extend | Same masking and file-and-line output. Add managed agents, plugin sources and the new surfaces. Remove the sys.path and agent_md import |
| resolve | Keep | Pure, fixture-backed, 123 cases. Move its 20 constant tables into one "Claude Code shape" data module (22-rules-engine.md) |
| rules_schema | Change | Pydantic models for rules.json. Keep the cross-catalog checks as model validators |
| rules.json, experiments, harness | Keep | They are the evidence base. Generate test expectations from data to end R-06c2 |
| transcripts | Keep parser, change caching | Record and Links extraction ports. The per-file cache becomes ingest offsets in SQLite |
| usage | Keep math | Dedupe, pricing per kind, deltas and buckets move to SQL plus small Python helpers |
| prices and prices.json | Keep | Ship the file, reprice all history at current rates (owner), dev-only refresh against LiteLLM and the pricing page |
| pincheck | Change | Phase 1 only, front matter model and effort against what ran. Keep the state words that still apply |
| projects | Change | Project registry from ~/.claude.json keys, transcript first-row cwd and routing-dashboard.json (A6). Keep the file format |
| agent_frontmatter | Change | Full YAML via ruamel.yaml round-trip for reading and writing. Keep the strict reader only as a "Claude Code would also reject this" check where experiments back it |
| json_edit | Keep | Byte splicing is the edit core for every JSON surface, settings and .mcp.json |
| edit_store | Keep | Dir-fd walk, backup, ledger, verify, retention 20, same folder names (B1). Generalise targets beyond the three settings files |
| git_check, local_root | Keep | Hardened git call and repo-root rule port as is |
| version | Keep, extend | Add more install layouts. Keep "never run claude" |
| reference_page | Keep as dev tool | Or render the rules reference from the API and drop the markdown copy |

### 5.2 Front end

| Component | Verdict | Why |
|---|---|---|
| index.html, app.js boot and state | Drop | React root, TanStack Query for data, router state for project and range |
| router.js | Change | React Router createHashRouter. Keep the route names, @main key and query names. Add session to Live |
| api.js once() cache | Drop | TanStack Query with stale times and refetchInterval fixes finding 5 |
| h.js, components.js, charts.js, icons.js | Drop code, keep shapes | Rebuilt as React components. Charts stay hand SVG (decision). Hatch patterns and the start edge rule stay for the accessibility exception |
| format.js and strings.json | Change | Typed t() and tn() over Intl.PluralRules, English only (owner). Keep strings.json as the one copy file |
| usage-page, usage-cards, usage-loading | Change | One UsagePage layout with the same empty, loading and error states |
| pin-view.js | Change | Words for phase 1 states only |
| band_order.js | Keep logic | Pure fit and move rules port to a hook. Drag through React Aria (owner) |
| band.js, band_arrange.js, band_drag.js | Change | React Aria drag and drop replaces the custom drag. Store the order in the database, not localStorage, which fixes finding 26 |
| edit_* (14 files) | Change | Keep the flow (pick, preview, review, save, undo, restore). Rebuild as one edit state machine plus per-surface editors |
| edit_ref.js | Keep idea | The shared Python and JS key table goes away if types come from OpenAPI |
| live_poll.js | Change | refetchInterval with etag. Same one-in-flight and back-off rules |
| pages | See the joint list | Page fate is the designer's call |
| tokens.css | Keep | The design source |
| app.css, live.css | Change | Rewritten per component on the same tokens |

### 5.3 Plugin, tools and tests

| Component | Verdict | Why |
|---|---|---|
| Launcher | Keep, change | Still the only entry point. One server per data folder instead of per project, `uv run --frozen`, per-project edit link, server writes its own pid and port (19-launcher.md) |
| SKILL.md and hooks.json | Keep | Same slash command, SessionEnd and PreToolUse guard. Fix the README hook count (finding 4) |
| Payload copy and build_plugins | Change | Payload carries the Python package, uv.lock and the built Vite files. Drop the stdlib-only import test |
| install.py, agent_md.py, routing hooks | Separate | Stay with the routing setup. The app reads their output only through the optional layer |
| HiveMind | Out of scope | Separate plugin. Only the shared hivemind_lib.py version bump rule touches the payload |
| Test suite | Change | pytest, Vitest, Playwright with axe at 375 and 1440. Port the resolver fixtures, the edit-store safety tests and the gate tests first. Add CI |

### 5.4 New components the rebuild would benefit from

| New component | Side | What it does | Serves |
|---|---|---|---|
| Surface registry | backend | One data module listing every config surface: paths per scope, reader, writer, risk class (safe, careful, risky, read-only), and which rules apply. The "Claude Code shape" module from 22-rules-engine.md grows into this | read anybody's setup, edit scope |
| Surface collectors | backend | Readers for CLAUDE.md and memory (with @imports up to 4 hops), rules folders with paths globs, skills and legacy commands, hooks from settings, plugins and front matter, MCP from .mcp.json and ~/.claude.json (read-only, masked), output styles, keybindings, statusLine, permissions | read anybody's setup |
| Plugin collector | backend | Reads ~/.claude/plugins/installed_plugins.json, known_marketplaces.json and cache/<mkt>/<plugin>/<ver>/ for agents, skills, hooks and settings. Feeds the resolver's existing plugin layer and marks plugin agents' ignored fields (hooks, mcpServers, permissionMode, initialPrompt) | plugin collector decision |
| Project registry | backend | Merges ~/.claude.json project keys, transcript cwd and routing-dashboard.json. Gives each project a stable id for URLs, keys and preferences | one server for all projects |
| Ingest service | backend | One writer task. Tails transcript files by (device, inode, size, offset), parses with the current parser, writes requests, sessions, runs and links. Survives cleanup deletions | SQLite history past 30 days |
| SQLite store and migrations | backend | WAL, numbered migrations, index in CLAUDE_PLUGIN_DATA. Tables for requests, sessions, runs, links, ingest offsets, preferences (band order), audit of edits (mirror of ledgers, never the source of truth) | history, preferences |
| Usage query API | backend | /usage with from, to, group by (model, agent, effort, day, hour) and paged sessions. Replaces three precomputed views | findings 7, 8 |
| Freshness endpoint | backend | Etag per resource (settings signature, ingest high-water mark) so polling costs one stat per surface | finding 5, live |
| Edit key store | backend | One key per project, made by the launcher, held in memory by the server and in a 0600 link file only when asked (--key-file). Gate checks key against the project in the body | per-project edit key |
| Target registry and editors | backend | Each editable surface names its target files and its edit kind: JSON splice (settings, .mcp.json), front matter round-trip with body bytes untouched (agents, skills, rules with paths), whole-text markdown with diff (CLAUDE.md, rules bodies), create and delete for files in folders. All write through edit_store | edit settings, agents, rules, skills, hooks, CLAUDE.md, MCP |
| Validators | backend | Settings schema from schemastore vendored and pinned, permission rule syntax, hook matcher and handler shape, MCP server shape, agent fields from agent_fields.json. A save refuses what Claude Code would skip | safe edits |
| Pin check phase 1 | backend | Front matter model and effort per agent against models and efforts the runs recorded. No precedence overlay | owner decision |
| Optional routing layer | backend and UI | Installed files, routing docs links, installer choices. Turned on when model-routing-choices.json is present | install-specific as a layer |
| Diagnostics view | backend and UI | What the server could not read and why (permission, parse error, missing folder, unknown version), per surface | read anybody's setup |
| OpenAPI types | build | openapi-typescript from FastAPI so the front end and back end share payload types | replaces edit_ref table drift |
| Docs drift check | dev tool | Compares rule quotes and anchors against live docs pages, run by hand after each Claude Code upgrade (D-1534) | rules trust |

---

## 6. Joint list

design.md was not in /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/app-audit/ when this pass finished (checked at 2026-11-08T01:53:29-05:00, while the designer was still taking screenshots). The main session reconciles.

What I need from the designer to merge the two views:
1. A verdict per page (Live, Overview, All projects, Agents, Agent detail, Models, Sessions, Session detail, Settings, Trail, Needs attention, Installed files, Rules reference), with the reason.
2. Which shared components stay as concepts: KPI row, stacked token bar, ring, hbars, day bars, chips and pills, Stat band with More and Arrange, rail, trail panel, dispatch canvas, loading strip.
3. The new screens for the new surfaces (CLAUDE.md, skills, hooks, MCP, plugins, agents list) and the state each screen needs, so I can check the API exposes it (per the review rule in model-routing.md).
4. How the edit flow should look across surfaces: one review rail for all, or a per-surface editor. That decides whether the target registry needs a common preview shape.
5. Whether Live should show several sessions or projects at once, and whether a Live session belongs in the URL (finding 27).
6. Whether band order and other view preferences should follow the user across ports and browsers (database) or stay per browser.
7. Which states a page must show for an unreadable or partly readable surface (diagnostics).

Draft rows from the architecture side, for the designer to confirm or overrule:

| Component | Owner side | Verdict | Reason |
|---|---|---|---|
| Overview, Agents, Models, Sessions and details | design (pages), architecture (usage query API) | Keep pages, change data | Range-parameter queries replace three precomputed views |
| Live and dispatch canvas | design, architecture | Keep, change transport | Polling with etag stays. Session goes in the URL |
| Settings band and trail | design, architecture | Keep concept | Resolver payload ports as is |
| Needs attention | both | Keep, widen | Should also list unreadable surfaces |
| Installed files | both | Move to optional routing layer | Install-specific |
| Rules reference | both | Keep | Evidence base for every status word |
| Surface pages (CLAUDE.md, skills, hooks, MCP, plugins, agents) | both | Add | Owner editing scope and read anybody's setup |
| Diagnostics | both | Add | Says what could not be read |
| Edit flow | both | Keep the flow, generalise | Preview, review, save, undo, restore for every surface |
| Band order storage | architecture | Change to database | Survives port changes |

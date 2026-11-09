# M1 build plan, Bar Tab data core

Written by the lead (deep-reasoner) on November 8, 2026, on branch `feature/bartab-m1` from the M0 commit `ad32428`. It turns plan-a.md section 5, "M1. Data core", into ordered tasks. The designer reviews section 5 before the build starts. Nothing is installed, started or committed until the owner says go.

Sources are plan-a.md (sections 3, 5, 6, 7, 9 and 10), research/20-decisions.md, research 26-05, 26-08 and 26-10, m0-build.md (sections 4, 5 and 10), m0-spikes.md, standards.md, components.md, the `a-firstrun-*` boards, the M0 code in `app/`, and a scout inventory of the old core on November 8.

## 1. What M1 delivers

The owner starts the preview on the demo build and watches first run read it with real progress. Then the shell opens with "Updated" times, the history line and "Prices as of {date}". Under that sits a SQLite store that one writer thread fills, a daily backup, a price feed with its checks, and a recorder that proves the new totals equal the old app's.

M1 never touches real data or the shared data folder. The preview reads the demo build and keeps its store in the worktree's `app/.data/`. The paths for `<config>/routing-dashboard/` are coded and tested against a fake config folder, and the owner points the preview at real data in M2 (O9).

## 2. Decisions this plan makes

The designer and owner can push back on any of them. Items that need an owner answer are in section 9.

| Item | Pick | Why |
|---|---|---|
| Port scope | Batch A in M1 (transcripts, usage dedupe and views, prices with `normalize_model`, projects). Batch B (resolve, collect, rules schema, agent front matter, agent_md) moves to M4 unless the owner says otherwise | Batch A is all the exit needs. Batch B is about 4,100 old lines and 700 tests, and M4 already lists "the 123 resolver fixtures pass on the port". Keeping B in M1 pushes the top of the estimate past $100 (section 8) |
| Ported module names | `transcripts.py`, `usage.py`, `prices.py`, `projects.py`, plus `model_catalog.py` for `normalize_model` and the models list | Flat names per plan-a section 8. The old `prices` imports `resolve` only for `normalize_model` (`dashboard/prices.py`, `resolve.py:303`), so that one function moves out and Batch A stands alone |
| Model catalog source | `app/server/data/rules.json`, a byte copy of `dashboard/rules.json`, with a test that the two stay equal until M9 | `normalize_model` reads the catalog from the rules file. A copy keeps `dashboard/` out of the payload |
| Ported tests | Old unittest classes run under pytest, imported whole (T-3ad1). Private-name patches (`_listdir_checked`, `_scan`) keep working because names stay flat | pytest runs `unittest.TestCase` as it is. No rewrite to bare functions |
| Store folder | Everything Bar Tab writes in the shared folder sits under `<config>/routing-dashboard/bartab/`. M1 defaults the store to `<data>/store/` and only tests use the shared layout | N1 keeps the folder shared with the old app. A subfolder of our own makes "never touch an old file" a one-line path check |
| Writer lock | `bartab/writer.lock` with `flock` `LOCK_EX` and `LOCK_NB`. A second server that can't take it runs as a follower that reads only | Two Bar Tab servers on one store must never both write. The old app's `.lock` files are never opened |
| Writer thread | One `store_writer` thread owns the only write connection and runs every write as a job (ingest pass, minute rebuild, backup, price copy record, checkpoint) | Plan-a section 3 asks for one SQLite writer. Network fetches run on their own thread and hand results to the writer, so a 10 s timeout never stalls ingest |
| Readers | A fresh connection per request with `PRAGMA query_only=ON` and one short read transaction | Long readers block WAL checkpoints (26-05, Risks) |
| First-run state | `ingest.state` reports the first full ingest only. Once `history.first_ingest` is set it stays `done`. Later pass failures go to `history.pass_error` | The M0 page shows first run whenever `ingest.state` isn't `done` (`app/web/src/app/App.tsx:49`). Without this rule every restart would show first run again |
| Progress unit | The bar moves by bytes, the label counts files | A few large transcripts would freeze a file-based bar. `fr_files` stays the label |
| Demo pace | A dev flag `--ingest-pace-ms N` sleeps between files. The server refuses it unless `--demo` is set | The demo set reads in well under a second, so first run would flash past. The owner and Playwright need to see it move |
| Cost tiers in `minute_usage` | Rows carry `speed`, `service_tier`, `inference_geo` and a `tier` index, all in the key. A change in tier thresholds rebuilds the table | Old prices apply fast mode, geo multipliers and a per-request prompt-size tier (`prices.py:210-252`). Minute sums lose those unless they are split by them |
| HTTP client | Python `urllib` behind an injected `Transport`, no new package | Two fixed GETs a day. A custom User-Agent is set, because the default one gets 403 on some hosts (D-1534) |
| Network in tests | A session-wide guard in `conftest.py` makes any non-loopback `socket.connect` fail the test | "No test reaches the network" becomes a rule the suite enforces, not a habit |
| Oracle runner | `app/oracle/record.py`, stdlib only, run with `/usr/bin/python3` from the repo root. It builds the demo with a fixed `--now`, calls `api_usage.usage` through `server.fixture_context` in process, and copies `truth.json` | Plan-a section 6. No server starts and no port opens. The old code stays the old interpreter's business |
| `claude_version` | From the demo's `session.json` on the demo build. For real data, the newest transcript row's `version` field [NEEDS CONFIRMATION: rows carry `version`, checked on fixtures in task 1] | The new app never runs `claude` (research 20, round 3) |
| `to_fix_count` | `null` until M4 | The page already hides a null or zero count. A zero would claim a check that hasn't run |

## 3. Ordered tasks

Tiers follow the owner's routing rules. fast-worker runs at medium unless the row says high. Every brief starts with `Kind: rebuild-m1`, carries the HiveMind line from `hivemind_lib.py related <paths>`, the date rule (`date -Iseconds` only), and these limits. Work only in `/Volumes/Warehouse/Projects/claude-code-model-routing-bartab`. Never read `~/.claude` beyond named files, real transcripts, real settings or `~/.claude.json`. Never touch port 8377. Use `app/scripts/uvw` and `app/scripts/npmw` for every uv and npm call. Never edit `dashboard/`, `tests/`, `plugins/`, `tools/`, `hooks/`, `agents/`, `rules/`, `skills/` or `install.py`.

HiveMind ids for briefs: T-7629, T-5589, T-c826, T-3ad1, D-c684, V-e876, D-1534, L-979a, I-14ae, L-13fb, C-06bf, D-3ca7, plus whatever `related` returns per task.

| # | Task | Files | Tier | Check |
|---|---|---|---|---|
| 0 | Pre-flight. Time, branch, clean tree. Add the network guard and a session fixture that builds the demo into a temp folder with `build_demo.py <out> --now 2026-10-30T18:00 --tz America/New_York` to `app/server/tests/conftest.py`, so no worker edits that file | `app/server/tests/conftest.py` | Lead | One test that opens a socket to 1.1.1.1 fails with the guard's message |
| 1 | Lookups. LiteLLM `model_prices_and_context_window.json` field names for Anthropic rows (`litellm_provider`, input, output, cache read, cache write 5m and 1h, tier fields such as `above_200k`, fast mode or geo fields if any), key forms (dated, alias, `[1m]`), file size today. OpenRouter `/api/v1/models` shape and pricing fields for `anthropic/*`. Claude Code `modelPricing`, whether code.claude.com documents it, its shape and which scopes it reads. Which old modifiers (fast x2, `us` x1.1, the Haiku 5.5 tier over 100,000) LiteLLM carries. Whether demo or fixture transcript rows carry `version`. Read fixtures only, never real transcripts | None. A table of fact, value and URL or path:line | scout | Every row has a source. Settles plan-a's open item on tiers and modifiers |
| 2 | Owner item, picker. On `#/` with no launch project, the sidebar Select behind the scrim shows no project until one is picked. `useActiveProject` drops its first-project fallback on the picker route only. The "How Claude Code decides" fixme test stays as it is | `app/web/src/app/active-project.ts`, `app/web/src/app/Shell.tsx`, tests beside them, one step in `app/web/e2e/routes.spec.ts` | fast-worker | Vitest for both cases (picker shows blank, other routes keep the fallback). The e2e step on `#/` with an empty `bartab.project` sees an empty Select. `test.fixme` at `routes.spec.ts:293` unchanged |
| 3 | Port Batch A. `transcripts.py`, `usage.py`, `prices.py`, `projects.py` and `model_catalog.py` (`normalize_model` and the catalog loader). Cut `projects.py` free of the old server `Context` into a plain dataclass of paths and a clock. Rename `missing_folder` to `folder_not_found`. Port `test_transcripts.py`, `test_transcripts_links.py`, `test_usage.py`, `test_prices.py`, `test_projects.py` and the `normalize_model` cases from `test_resolve.py`. Copy `rules.json` and `prices.json` into `app/server/data/` with drift tests | `app/server/{transcripts,usage,prices,projects,model_catalog}.py`, `app/server/data/rules.json`, `app/server/data/prices-old.json`, `app/server/tests/test_port_*.py` | fast-worker | Every ported test passes under pytest. ruff, ruff format, pyright strict. Old test counts noted beside new ones (52, 27, 101, 64, 38). `git diff --stat ad32428` on the protected paths is empty |
| 4 | Store and migrations. `store_paths.py` (the folder layout, the `bartab/` guard, 0700 folders and 0600 files), `platform_os.py` (flock, fsync, file identity, the one place for OS calls), `store.py` (open, pragmas, quick check, migration runner, read connections) and the five migrations in section 4 | `app/server/{store_paths,platform_os,store}.py`, `app/server/migrations/000{1..5}_*.sql`, tests | fast-worker | Migration test, schema text-column test, coexistence test and lock test from section 7 pass. Coverage stays at 85 percent |
| 5 | Ingest and the writer (high). `ingest.py` (scan, stat-only decide, offset reads, per-file parser state for links, rounds and stops, dirty-cell `minute_usage` rebuild, `run_events`), `store_writer.py` (thread, job queue, pass schedule, progress snapshot, retry schedule, follower mode) | `app/server/{ingest,store_writer}.py`, tests | fast-worker high | Every ingest test in section 7 passes, including the hypothesis stateful test. Cold ingest time of the demo build is printed by a test marked `slow` |
| 6 | Backup and history. `backup.py` (online copy, quick check on the copy, rotate to seven, clean-stop copy), `history.py` (the history status answer) | `app/server/{backup,history}.py`, tests | fast-worker | Backup restore test, rotation test, failed-copy test |
| 7 | Price feed (high). `price_feed.py` (fetch schedule, checks, last good copy, cross-check, source order), `price_transport.py` (the injected `Transport` and the real `urllib` one), the bundled dated copy and its manifest, `api_prices.py`. One GET to LiteLLM's raw URL for the bundled copy, logged with its `date -Iseconds` time. Tests run on fixture files only | `app/server/{price_feed,price_transport,api_prices}.py`, `app/server/data/prices/litellm-anthropic-<date>.json`, `app/server/data/prices/manifest.json`, `app/server/tests/fixtures/prices/*` | fast-worker high | Price tests in section 7 pass with the network guard on. The bundled copy holds Anthropic rows only |
| 8 | Real provider and API. `store_provider.py` behind the same interface as `fixture_provider.py`. `/api/app` and `/api/projects` from the store, `/api/prices` mounted, `as_of` and `etag` on all three. `serve.py` gains `--claude-dir`, `--store`, `--demo`, `--ingest-pace-ms` and `--no-price-fetch`. The lifespan starts the writer and the price thread and runs the clean-stop backup. `POST /api/access/mint` also asks a failed ingest to retry now. OpenAPI export and `schema.d.ts` regenerated | `app/server/{store_provider,main,serve,api_app,models,openapi_export}.py`, `app/web/src/api/openapi.json`, `app/web/src/api/schema.d.ts`, `.claude/skills/bartab-preview/SKILL.md` (demo default), tests | fast-worker | TestClient on the demo build reaches `done` with real counts. The M0 fixture scenarios still serve. The OpenAPI staleness test passes |
| 9 | Recorder and totals. `app/oracle/record.py` and its JSON in `app/fixtures/oracle/demo/` (usage for today, 7 and 30 days, `truth.json`, `manifest.json` with the old commit sha and build args, `allowed-differences.json`). `usage_query.py` for totals per project, agent, model and day over `minute_usage`, priced at query time. Differential tests | `app/oracle/record.py`, `app/fixtures/oracle/demo/*`, `app/server/usage_query.py`, `app/server/tests/test_differential.py` | fast-worker | Recorder run twice gives the same bytes. Differential test passes with the price table pinned to `prices-old.json` |
| 10 | String deck. Keys for the history line, "Updated", "Prices as of", price source words, the cross-check notice, a failed backup, rows with no usage, kept files, a pass error after first run, and `store_newer` if the owner adds it (question 4). Waits for the designer review | Draft returned as a key table, typed into `app/web/src/strings/en.ts` by the lead | tech-writer | String lint passes. Owner reads the deck |
| 11 | Web. First run fed by the real ingest (bar by bytes), the shell's "Updated" and history line, "Prices as of" and the cross-check notice where the designer places them, the More page lines at 375. Prices query hook. E2E on the demo build with `--ingest-pace-ms` | `app/web/src/pages/GatePages.tsx`, `app/web/src/app/Shell.tsx`, `app/web/src/pages/MorePage.tsx`, `app/web/src/api/client.ts`, tests, `app/web/e2e/firstrun-real.spec.ts` | fast-worker | Vitest, tsc, ESLint, Stylelint, Prettier. E2E watches the bar move, the step announced once, then Live. Axe clean |
| 12 | Batch B, only if the owner keeps it in M1. Port `resolve.py`, `collect.py`, `agent_md.py`, `agent_frontmatter.py`, `rules_schema.py` with their tests (253, 85, 19, 80, 9 and 252) in two dispatches | `app/server/{resolve,collect,agent_md,agent_frontmatter,rules_schema}.py`, tests, `app/server/data/agent_fields.json` | fast-worker, two dispatches | Every ported test passes. pyright strict |
| 13 | Exit runs. T2 suite, the M0 Playwright suite plus the new specs, the cold ingest time, then the old suite alone with the log named `feature-bartab-m1` (T-7629), then the protected-path diff | Logs in the scratchpad | scout | All green. The diff is empty |
| 14 | Browser check in Chrome under the tab-group rules. First run moving and done, the shell with the history line, More at 375, the blank picker Select, at 1440 and 375, light and dark, against `a-firstrun-*` and the designer's notes | None. Returns a difference list | judge | Differences fixed in one batch, or listed for the owner |
| 15 | One fix round from tasks 13 and 14, then consolidation and the report. The main session dispatches the verifier | None | Lead | Report written |

Order and parallel work. Task 0 runs first. Then 1, 2, 3, 4 and 9's recorder half run in parallel, because they touch separate files. Task 5 starts when 3 and 4 are in. Tasks 6 and 7 follow 4 (7 also needs 1 and 3), and they run beside 5. Task 8 needs 5, 6 and 7. Task 9's totals half needs 5. Task 10 runs as soon as the designer review lands. Task 11 needs 8 and 10. Task 12, if kept, runs beside 5 to 9. Then 13, 14 and 15. Only the lead edits `conftest.py`, `pyproject.toml` and `models.py`'s shared types, so parallel workers never collide there. M1 adds no package, so neither lockfile changes.

## 4. Store, ingest, backup and first run

### Folder layout

| Path | Owner | Notes |
|---|---|---|
| `<config>/routing-dashboard/backups/`, `ledger.json`, `.lock`, `*.bak`, `.ledger-*.tmp`, `.routing-dashboard-*.tmp` | Old app | Never opened for write, never locked, never listed by a writer (`edit_store.py:74-85`, `:558`, `:827-842`) |
| `<config>/routing-dashboard.json` | Old install | Read only by `projects.py`, as the old app does (`projects.py:34`) |
| `<config>/routing-dashboard/bartab/bartab.db` and its `-wal` and `-shm` | Bar Tab | The store |
| `bartab/writer.lock` | Bar Tab | The single-writer lock |
| `bartab/db-backups/bartab-<UTC stamp>.db` | Bar Tab | Seven copies. Not named `backups`, so nobody confuses them with the old settings backups |
| `bartab/prices/last-good.json` and `bartab/prices/.incoming-*.tmp` | Bar Tab | Written by temp file and rename |

`<config>` is `CLAUDE_CONFIG_DIR`, else `$HOME/.claude`, as the old app resolves it (`server.py:221-230`). In M1 the server takes `--store` and `--claude-dir` and has no default that reaches either real folder. The defaults switch in M2.

Every write goes through `store_paths.writable(path)`, which refuses any path outside the store root. Folders are 0700 and files 0600, matching the old store.

### Migrations

Numbered SQL files in `app/server/migrations/`, applied in order inside one transaction each, with `PRAGMA user_version` set to the file number. Before a migration runs on an existing store, the backup job makes a pre-migration copy. A store whose `user_version` is newer than the code knows is refused, never touched (question 4 asks how the page says so).

| File | Tables and views |
|---|---|
| `0001_base.sql` | `meta (key, value)`. `files` with the 26-05 columns plus `no_usage`, `shrinks`, `read_errors`, `first_seen`, `last_seen`. `requests (file_id, key, ts, input, output, cache_read, cache_write_5m, cache_write_1h, thinking, model, request_id, effort, speed, service_tier, inference_geo)`, primary key `(file_id, key)`, without rowid, with an index on `key`. `sessions (session_id, folder, project_key, first_ts, last_ts, cwd, branch, claude_version)`. `runs (session_id, run_id, file_id, agent_type)`. `links (parent_file_id, child_id, session_id, ts, resolved)` with an index on `(session_id, child_id)`. View `best_requests` with the 26-05 window order (output desc, ts desc, path desc) |
| `0002_run_events.sql` | `run_events (file_id, seq, session_id, run_key, kind, at, finished, by_kind, by_run)`, primary key `(file_id, seq)`, `kind` one of launch, brief, stop. `file_state (file_id, offset, state)`, where `state` is a small JSON object of flags and counters (stopped, finished, last round), never row text |
| `0003_minute_usage.sql` | `minute_usage (session_id, run_key, minute, model, effort, speed, service_tier, inference_geo, tier, input, output, cache_read, cache_write_5m, cache_write_1h, thinking, requests)`, primary key on the first nine columns, without rowid. `minute` is UTC `YYYY-MM-DDTHH:MM` |
| `0004_history.sql` | `passes (id, kind, started, finished, files_seen, files_read, bytes_read, rows_added, rescans, error_code)` and `backups (id, at, file, bytes, ok, reason_code)`. `meta` keys `first_ingest`, `last_pass`, `tier_hash` |
| `0005_price_copies.sql` | `price_copies (id, fetched_at, source, sha256, bytes, check_ok, reason_code, models, cross_check_state, cross_check_models)` |

`prefs` waits for M2, where Pause and the last project need it, and `ledger_mirror` waits for M6. Each table lands in the milestone that first reads it.

Rules that keep history safe, from plan-a section 3 and 26-05. Offsets and rows commit together. A file that disappears gets `missing=1` and keeps its rows. A file that shrinks, changes inode or fails the head and tail hash is rescanned, and its old rows stay unless the rescan finds the same keys. A rescan never deletes rows whose file is missing. Rows with no usage are counted per file, never dropped silently.

### The single writer and its pass schedule

One `store_writer` thread opens the only write connection (WAL, `synchronous=NORMAL`, `BEGIN IMMEDIATE` per batch, commit at most every 50,000 rows). It takes `writer.lock` first. If another server holds it, this server runs as a follower. It reads the store, reports the holder's progress from `meta`, and tries the lock again every 10 s.

1. Start. Open, `PRAGMA quick_check`, migrate, then the start backup when the newest copy is over 24 hours old.
2. Full pass. List every project folder under `<claude-dir>/projects/`, stat every transcript, and set `files_total` and `bytes_total` to the work still to read. Read changed files from their offsets, then rebuild the dirty `minute_usage` cells and `run_events`, commit, and `wal_checkpoint(PASSIVE)`. The first full pass that finishes sets `meta.first_ingest`.
3. Hot loop, every 1 s. List and stat the folders of running sessions (a request in the last 30 minutes) and their `subagents/` folders.
4. Cold loop, every 10 s. List and stat every folder.
5. Daily backup at the first pass after 24 hours, and the clean-stop copy from the lifespan shutdown.
6. Price copies. The price thread hands each fetch result to the writer as a job.

Dirty cells. A pass collects the keys it inserted or changed, looks up the old and new winner rows for those keys in `best_requests`, and marks their `(session_id, minute)` cells. Each dirty cell is deleted and rebuilt from `best_requests`. Keys cross sessions when Claude Code copies messages into a resumed session, so the rebuild never assumes one session per key.

Progress. The writer keeps an in-memory snapshot (state, files and bytes done and total, error, retrying) behind a lock. `/api/app` reads the snapshot, not the database, so polling at 1 s costs nothing during first run.

Failures. Whole-run causes map to the M0 codes (m0-build.md section 10). `config_dir_missing` when `<claude-dir>/projects/` is absent. `config_dir_unreadable` on a permission error, with the folder. `store_unwritable` on a read-only or full disk, with the store path. `store_damaged` when `quick_check` fails. `unexpected` for anything else, with the log path. One unreadable transcript never fails the run. It counts in `files.read_errors` and becomes a To fix row in M4. Retries run at 10 s, 30 s and 60 s, then every 5 minutes, with `state: running`, `retrying: true` and `error: null` while each runs. The launcher's `start` against a running server calls `mint`, which also starts a retry at once, so the first-run command "try again" works without a restart.

### `/api/app` in M1

The M0 fields keep their names and error codes. New fields are added, none renamed.

| Field | M1 value |
|---|---|
| `server_time`, `instance` | As in M0 |
| `as_of`, `etag` | `as_of` is the end of the last pass that checked the sources. `etag` changes when the store's data generation changes. The `{unchanged: true}` reply lands in M2 with the 1 s timeline |
| `claude_version` | Section 2 |
| `ingest` | `state`, `files_done`, `files_total`, `bytes_done`, `bytes_total`, `error {code, file}`, `retrying`, with the first-run rule from section 2 |
| `history` | `oldest` (oldest stored request), `first_ingest`, `last_pass`, `last_backup`, `backup_failed {at, reason_code}` or null, `no_usage_rows`, `kept_files` (rows kept after the source was removed), `unreadable_files`, `pass_error {code, file}` or null |
| `running[]` | `{project, session}` for sessions with a request in the last 30 minutes |
| `to_fix_count` | null until M4 |
| `editable_projects`, `rules_version_gap`, `routing_layer` | Empty, null and false until M6, M5 and M4 |

`/api/projects` keeps the M0 shape. Projects come from the store's sessions, grouped by folder and `cwd`, plus the old `routing-dashboard.json` list when it exists. `state` is `ok` when the folder has `.claude`, `no_claude_folder` when it doesn't, and `folder_not_found` when the folder is gone. Keys are the readable slugs of the old `slug()` (`projects.py:148`), made unique with a suffix.

### Backup job

`backup.py` copies the live store with `sqlite3.Connection.backup()` from the writer's connection into `db-backups/.bartab-<stamp>.db.tmp`, runs `PRAGMA quick_check` on the copy, fsyncs it and renames it. Only a copy that passes may rotate out the oldest of the seven. A failed copy is deleted, recorded in `backups` with its reason, and shown as `history.backup_failed`, never in To fix (plan.md section 5). The clean-stop copy waits at most 5 s for a pass to end and is skipped when the last good copy is under an hour old. Restoring is not in the UI in M1. A test proves that a copy opens, passes its check and gives the same totals.

## 5. UI state and data for the designer review

Each item lists what the screen needs. The words come from task 10 after this review.

### First run on a real ingest

- Board. `a-firstrun-1440-*`, `a-firstrun-375-*`, `a-firstrun-failed-*`, `a-firstrun-retry-*`. Steps 1 and 2 show Done, step 3 is live (m0-build.md section 4, unchanged).
- Data. `ingest.state`, `files_done` and `files_total` for the label, `bytes_done` and `bytes_total` for the bar, `error {code, file}`, `retrying`. Polled every 1 s.
- Change from M0. Real numbers instead of a fixture clock. The bar moves by bytes while the label counts files, so the two can disagree for a while ("40 of 482 files" at 61 percent). The designer decides whether that is acceptable or the label shows bytes too.
- Rule. First run shows only until the first full ingest finishes. A failure on a later start never shows first run again. It shows as `history.pass_error` in the history line.
- Demo pace. On the demo build the owner sees the bar take about 15 seconds through `--ingest-pace-ms`. Real data needs no pace.
- Events. On done, the page moves to the launch project's Live, as in M0.

### "Updated" time

- Today. The shell shows "Updated {time}" from the time of the last answer (`Shell.tsx:283-285`).
- Proposal. Show `as_of`, the end of the last pass that checked the transcripts, so the time means "data checked at". The connection line keeps its M0 meaning while calls fail. The designer decides whether both meanings show, and where "Updated" sits in the sidebar footer and on More at 375.
- Data. `as_of` from `/api/app`, every 10 s while visible.

### History line

- Board. None. It is new in M1. Plan.md section 5 and r3-designer R8 say it shows the last backup time and says a failed backup in plain words, and that rows with no usage show beside it as a count with its reason.
- Data. `history.oldest`, `first_ingest`, `last_pass`, `last_backup`, `backup_failed {at, reason_code}`, `no_usage_rows`, `kept_files`, `unreadable_files`, `pass_error`.
- Proposed placement. The sidebar footer under the version line at 721 px and up, and the More page at 720 px and below. M3 adds it to the usage pages and uses `first_ingest` for "All history" (research 26-10).
- Need from the designer. Which fields show at rest, which only on a problem, the order, and whether a failed backup or a pass error uses the notice line (component 8) or plain text in the footer.

### Prices as of

- Data. `GET /api/prices` gives `source` (model_pricing, litellm, last_good, bundled), `as_of`, `cross_check {state, models[]}` and per-model rates. Polled every 60 s.
- Proposed placement. "Prices as of {date}" in the footer and on More, beside the version line (m0-build.md section 4, More page). A cross-check disagreement shows as a notice line naming the models, and no price changes. The "API-rate estimate" label and the subscriber help line land on cost cards in M2.
- Need from the designer. Whether the source word shows at rest or only when it isn't LiteLLM, and the notice wording slot.

### Project picker

- Owner item. On `#/` with no launch project, the sidebar Select behind the scrim shows no project until one is picked. It no longer falls back to the first project.
- Data. Unchanged. `value` is null on the picker route until a pick.

### Not changed

The "How Claude Code decides" label at 1440 waits for the owner's pick. Its fixme test stays.

## 6. Price feed

### Source order

1. The user's `modelPricing` rates, per model, when task 1 confirms the setting and its shape. M1 reads the managed and user scopes only, because the resolver port moves to M4.
2. The active LiteLLM copy, the newest fetch that passed every check.
3. The last good copy, when the latest fetch failed or none ran in 48 hours.
4. The bundled dated copy in `app/server/data/prices/`, when no fetch has ever passed.

`source` in `/api/prices` names the source for most rows, and each model row carries its own. Every cost is priced at query time, so all history reprices at current rates, and query caches key on the table's hash (plan-a section 3).

### Fetch and checks

- Schedule. At start when the last attempt is over 24 hours old, then every 24 hours, on the price thread. `--no-price-fetch` and `BARTAB_OFFLINE=1` turn it off.
- Transport. HTTPS GET to the two fixed URLs only, a custom User-Agent, no cookies, a 10 s timeout, a size cap set at four times the size task 1 measures, and a redirect to another host refused.
- LiteLLM checks, in order. It parses as a JSON object. Anthropic provider rows are kept and the rest dropped. Every model in the current catalog is present (`model_catalog.py`), plus every model the store has priced in the last 30 days. Each price is in range after converting per token to per million tokens (input 0.05 to 100, output 0.2 to 500). Cache read is between 8 and 12 percent of input. Tier and modifier fields follow task 1. A failure keeps the last good copy and records `reason_code` (`not_json`, `too_large`, `missing_model`, `out_of_range`, `cache_ratio`, `fetch_failed`, `redirect_refused`).
- Last good copy. Written to `bartab/prices/last-good.json` by temp file and rename, with its row in `price_copies`.
- Cross-check. OpenRouter's public models list, fetched on the same schedule. When an `anthropic/*` model's input or output price differs from the active table by more than 1 percent, `cross_check.state` is `disagree` with the models listed. No price changes.
- Bundled copy. Anthropic rows only, named with its fetch date, with `manifest.json` holding the URL, date and sha256. It is refreshed by hand with a release, never by a repo job (research 20, pricing source).
- Labels. Every cost reads as an "API-rate estimate" with "Prices as of {date}". The date is the active copy's fetch date, the bundled copy's date, or "your settings" for `modelPricing` rows (wording from task 10).

### `GET /api/prices`

`source`, `as_of`, `etag`, `cross_check {state: agree|disagree|not_checked, models[]}`, and `models[] {model, source, input, output, cache_read, cache_write_5m, cache_write_1h, tiers[], modifiers, relative}`. `relative` is the ratio to Sonnet's blended rate, for the agent form's price words in M6.

## 7. Tests and exit

### New suites

| Area | Tests |
|---|---|
| Ported core | Every ported old test under pytest, with old and new counts side by side in the report |
| Ingest oracle | After any sequence of appends, partial last lines, late links, truncation, inode swaps and deletions, the store equals a full re-read through the ported `transcripts.Reader` and `usage.dedupe`. A hypothesis stateful test drives it, seeded |
| Late links | Link row before the agent file and agent file before the link row both resolve (26-05) |
| Rescan safety | A missing file keeps its rows with `missing=1`. A shrink keeps old rows and counts `shrinks`. "Never delete rows on rescan" is a named test |
| `minute_usage` | Equals a full rebuild from `best_requests` after every step of the stateful test. A tier-threshold change rebuilds it |
| `run_events` | Rounds and stops equal the old `Links.rounds` and `Links.stops` on `tests/fixtures/rounds/` and the demo build |
| Migrations | Builds every schema version in order on a copy, inserts rows at each version, and checks that row counts survive. A store newer than the code is refused untouched |
| Schema privacy | Every TEXT column is on an allowlist of names (paths, ids, model, timestamps, branch, cwd, version, codes). A new one fails the test. `file_state.state` keys are checked against a fixed set |
| Coexistence | A fake config folder seeded with old-app files (`backups/x/ledger.json`, `.lock`, a `.bak`, `routing-dashboard.json`) goes through ingest, backup and a price copy. Every old file keeps its bytes and mtime, and nothing appears outside `bartab/` |
| Writer lock | A second writer on the same store becomes a follower and never writes. It takes over after the first one stops |
| Backup | A copy restores, opens, passes `quick_check` and gives equal totals. Rotation keeps seven. A copy that fails its check never displaces a good one |
| First run | `ingest` walks waiting, running and done with real counts on the demo build. Each failure code fires from a crafted folder. Retry sets `retrying`. A later pass failure leaves `state` at `done` and sets `pass_error` |
| Price feed | Fixture files for good, missing model, out of range, cache ratio off, malformed and oversized, plus a timeout and a cross-host redirect, through the injected transport. The fallback order runs from `modelPricing` down to the bundled copy. The OpenRouter disagreement sets the notice and changes no price |
| Differential | Demo totals for today, 7 and 30 days per project, agent, model and day equal the recorded `api_usage.usage` and `truth.json`, with prices pinned to `prices-old.json`, outside `allowed-differences.json` |
| API | `/api/app`, `/api/projects` and `/api/prices` on the demo build, `as_of` and `etag` present, the OpenAPI export current |
| Web | Vitest for the bytes bar, the history line states, the prices line and the blank picker. Playwright for the real first run on the demo build, at 375 and 1440, light and dark, with axe |

### Kept green

- The M0 exit run. The M0 pytest suite, Vitest, the full M0 Playwright and axe matrix and the sheet run, still on the fixture scenarios.
- Standards checks. ruff, ruff format, pyright strict, coverage at 85 percent on `app/server`, tsc, ESLint, Stylelint and Prettier.
- The old suite alone, `/usr/bin/python3 -m unittest discover -s tests` from the worktree root, with its log named for `feature-bartab-m1` (T-7629). Expected about 3575 tests and 88 skipped.
- `git diff --stat ad32428 -- dashboard tests plugins tools hooks agents rules skills install.py` stays empty.

### Exit, from plan-a M1

- Demo totals for 30 days equal the old app's recorded `/api/usage` and `truth.json` from `build_demo.py`.
- The schema test finds no text column outside the allowlist.
- Cold ingest time on the demo build is recorded here, in a results section added at the end of the build.
- The owner opens the preview on the demo build, watches first run move and lands in the shell with "Updated", the history line and "Prices as of".

## 8. Cost estimate

List-price ranges, scaled from plan-a's table and M0's actual shape. I have no per-run cost from the dashboard in this tree. [NEEDS CONFIRMATION: dashboard cost per run for each agent.]

| Dispatch | Count | Estimate |
|---|---|---|
| This plan step, lead | 1 | $3 to $5 |
| Lead build, reviews and consolidation, deep-reasoner on Opus at high | 1 | $15 to $22 |
| fast-worker at high, tasks 5 and 7 | 2 | $13 to $23 |
| fast-worker at medium, tasks 2, 3, 4, 6, 8, 9, 11 and one fix round | 8 | $19 to $33 |
| scout, tasks 1 and 13 | 2 | $2 to $4 |
| judge, task 14 in Chrome | 1 | $2 to $4 |
| tech-writer at medium, task 10 | 1 | $2 to $3 |
| Total with Batch B in M4 | | $56 to $94 |
| Task 12, Batch B kept in M1, two fast-worker dispatches | 2 | add $8 to $14, total $64 to $108 |

The main session's designer review (about $2 to $4) and verifier pass (about $5 to $10) are outside these totals. With Batch B the top of the range passes the $100 line, which is why the plan moves it to M4.

## 9. Risks and owner questions

### Risks

1. Incremental rounds and stops. The old parser keeps link state in memory per read (`transcripts.py:392-437`). Resuming it from `file_state` at an offset is new, so the stateful oracle test runs it against a full re-read at every step.
2. Dedupe across sessions. Resumed sessions copy message ids into new files, so a dirty cell can sit in another session. The rebuild works per key, and the oracle test plants such copies.
3. Coexistence. The old app may run at the same time on port 8377. In M1 it can't collide, because the store sits in the worktree. From M2 the `bartab/` guard, the writer lock and the coexistence test carry it.
4. Price feed shape. LiteLLM may not carry fast mode, the geo multiplier or the Haiku 5.5 tier the old table has. Task 1 settles it. Where LiteLLM lacks a modifier, the old multiplier stays in a small local table, recorded in the manifest, and the differential test pins the old prices anyway.
5. Typing the port. pyright strict on about 2,100 old lines in Batch A takes real work, and more if Batch B stays. If it blows the budget, the lead stops and reports instead of relaxing the standard.
6. Demo pace hides real speed. The cold ingest time is measured with pace off.
7. The 1 s hot loop and the 10 s cold loop are untested on a large real tree. M2 measures them on real data.

### Owner questions

1. Batch B. Move the resolver, collect, rules schema and agent front matter port to M4 (and agent front matter to M6 if M4 doesn't need it), as this plan does? I recommend yes. It keeps M1 at $56 to $94.
2. Demo only in M1. The preview runs on the demo build and keeps its store in `app/.data/`, and real data starts in M2 as O9 says. Confirm.
3. Price fetch in the preview. Keep the two daily GETs on from M1, or off until M2? I recommend on, so the feed runs for weeks before cutover.
4. A newer store. When a store was migrated by a newer Bar Tab, the server refuses it. Add a sixth first-run code `store_newer` with its own sentence, or report it as `unexpected` with the log? I recommend the new code. It changes the M0 contract, so m0-build.md section 10 gets the line first.
5. `modelPricing` scope. If task 1 shows project scopes can set it, M1 still reads only managed and user scopes until the resolver lands. Fine to defer?

## 10. Owner answers and designer review, November 8

The owner took every pick in section 9. This section overrides anything above that disagrees with it.

### Owner answers

1. Batch B moves to M4, with agent front matter and agent_md going to M6. The budget is $56 to $94, with a stop and report past $100.
2. M1 runs on the demo build only. Real data starts in M2 (O9).
3. The two daily price fetches are on in the preview from M1.
4. `store_newer` is a sixth first-run code. The gate gets its own sentence and the next step "update Bar Tab", drafted by tech-writer.
5. `modelPricing` comes from the managed and user scopes only until the resolver lands in M4.
6. The first-run progress label shows size only ("1.2 of 2.0 GB"), matching the bar, and `aria-valuetext` says the same.
7. A price disagreement isn't shown on screen in M1. The data stays in `/api/prices` for M2's cost cards.
8. "Updated" means data checked, shown as an absolute clock time in minutes.
9. The `pass_error` notice ("updates stopped") shows on every page.
10. The sidebar widens from 224 px to 240 px. The one-line label test is live again and components.md entry 1 says so.

### Designer review folded in

- Retries keep the last error and expose the next retry time, so first run holds one finding with "Trying again at {time}" and announces once, not on every retry.
- Totals are unknown while folders are listed, so the page never shows "0 of 0" or a bar with no width. Totals stay fixed for the pass, so the bar never moves back.
- `pass_error` after the first ingest shows as a notice line (component 8) above the page at both widths and on every page. The next good pass clears it.
- The M0 connection line keeps its meaning and shows only while calls fail. Data freshness (`as_of`) sits quietly in the footer and on More. Followers read `as_of` from the writer's `meta`, and `pass_running_since` shows a long pass isn't stale.
- A later good backup clears `backup_failed`. Its `reason_code` comes from a closed list.
- At rest the history line shows only "History since {oldest}" and "Last backup {time}". `backup_failed`, `pass_error` and `unreadable_files` show only when present. `kept_files` and `no_usage_rows` stay quiet. `last_pass` is dropped because `as_of` says the same.
- The prices line shows the source word only when it isn't LiteLLM, and keeps its last value when `/api/prices` fails.
- The picker Select on `#/` shows a placeholder, not a blank, so a screen reader never says "Project," with nothing after.
- `as_of` refreshes at once when the tab becomes visible. Footer times show minutes and are never live regions.
- On done, focus moves to Live's h1. A transcript folder with no files never flashes first run.

### The M1 contract for `GET /api/app`

This replaces the `/api/app` table in section 4. The M0 fields keep their names. m0-build.md section 10 points here.

| Field | Type | Meaning |
|---|---|---|
| `server_time`, `instance`, `claude_version`, `running[]`, `editable_projects` | As in M0 | `editable_projects` stays empty until M6 |
| `as_of` | time or null | End of the last pass that finished, read from the store's `meta`, so a follower reports the writer's value |
| `pass_running_since` | time or null | Start of the pass now running, from `meta` |
| `etag` | string | Changes when the store's data generation changes |
| `ingest.state` | waiting, running, done, failed | The first full ingest only. It stays `done` once `history.first_ingest` is set. A store with no transcripts at all finishes at once as `done` |
| `ingest.files_done`, `ingest.bytes_done` | int | Work done in this pass |
| `ingest.files_total`, `ingest.bytes_total` | int or null | Null while folders are listed. Fixed for the pass once set |
| `ingest.error` | `{code, file}` or null | The last whole-run failure. It stays through automatic retries and clears on success |
| `ingest.retrying` | bool | True while a retry run executes |
| `ingest.retry_at` | time or null | When the next automatic retry starts |
| `history.oldest` | time or null | Oldest stored request |
| `history.first_ingest` | time or null | When the first full ingest finished |
| `history.last_backup` | time or null | Newest good copy |
| `history.backup_failed` | `{at, reason_code}` or null | Cleared by a later good copy. Codes `no_space`, `unwritable`, `check_failed`, `copy_failed` |
| `history.pass_error` | `{code, file, since}` or null | A whole-pass failure after the first ingest. Cleared by the next good pass |
| `history.unreadable_files`, `history.kept_files`, `history.no_usage_rows` | int | Counts |
| `to_fix_count` | null | Until M4 |

Whole-run codes for `ingest.error.code` and `history.pass_error.code` are `config_dir_missing`, `config_dir_unreadable`, `store_unwritable`, `store_damaged`, `store_newer` and `unexpected`.

## 11. Results, November 8

The build ran on `feature/bartab-m1` and nothing is committed. The exit runs below ran from 11:01 PM to 11:13 PM.

| Check | Result |
|---|---|
| Demo totals against the old app | All 18 recorded `/api/usage` payloads (six scopes by today, 7 and 30 days) match on totals, agents, models and days. Costs match within 1e-6. The 30-day totals equal `truth.json` for every project with transcripts |
| Allowed differences | Four, all in `/api/projects`. `missing_folder` reads as `folder_not_found`, and quarry-notes shows as an unlisted project |
| Schema privacy | Every TEXT column is on the allowlist |
| Cold ingest of the demo build | 538 files, 12,792,502 bytes and 7,289 rows in 0.286 s with pace off. A pass with no changes takes 0.007 s |
| pytest with coverage | 1,063 passed, coverage 96 percent |
| Launcher tests alone | 154 passed |
| ruff, ruff format, pyright strict | Clean |
| Web checks | typecheck, ESLint, Stylelint, Prettier, Vitest (696) and build all pass |
| Playwright with axe | 72 passed, the M0 suite included |
| Old suite alone | 3,575 tests, 88 skipped, OK, in 367 s |
| Protected paths | `git diff --stat ad32428` is empty |

Deviations from the plan, each for a reason.

- The cache read check uses a band of 1 to 12 percent of input, not the plan's 8 to 12 percent. LiteLLM's November 8 file has Opus 5.5 and Sonnet 5.5 at 5 percent and Fable 5.1 at 2.5 percent, and those rows match the old price table.
- `modelPricing` is read from managed sources only. Claude Code's settings reference (https://code.claude.com/docs/en/settings-reference#modelpricing) gives its scope as "Managed" and "Claude Code ignores it in user, project, and local settings, in --settings, and on Windows in the user-writable HKCU registry." That narrows owner answer 5. M1 reads no managed file (`managed_settings_path` is None), so the layer is dormant until M4.
- The layer follows the same page. A row needs all four rates, each 0 to 10000. The multiplier applies on top of a row's rates, and a row skips the fast-mode and US-only surcharges ("Claude Code uses a row's rates exactly as you wrote them, without adding the fast-mode surcharge or the US-only-inference rate. If you also set multiplier, Claude Code applies it on top of the row's rates.").
- The old "all" scope counts every transcript folder (`dashboard/usage.py:84`), so the new "all" does too.
- A paced demo holds once for 2 seconds before the writer starts, so "Counting files" is visible. It's a single hold, not one per step. Real data has no pace and no hold.
- The transport refuses a redirect to another host and follows a redirect that stays on the same host over HTTPS. The plan only said the first part.
- In demo mode only, the preview opens the first listed project when the checkout folder matches none.

Two changes the owner should see.

- The store_newer page says "A newer Bar Tab upgraded…" instead of naming both versions, because the server doesn't know the newer version.
- The demo picker now shows a "Folder not found" row for quarry-notes. The demo has transcripts for it but no project list entry and no folder on disk, so it shows as an unlisted project.

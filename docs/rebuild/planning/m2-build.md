# M2 build plan, Bar Tab Live

Written by the lead (deep-reasoner) on November 9, 2026, on branch `feature/bartab-m2` from `82dbddd`, where M0 and M1 are committed. It turns plan-a.md section 5, "M2. Live", into ordered tasks. The designer reviews section 5 before the build starts. Nothing is installed, started or committed until the owner says go.

Sources are plan-a.md (sections 3, 5, 6, 7 and 10), m1-build.md (sections 2, 4, 10 and 11), standards.md, components.md (shared rules, entries 10, 11, 12, 18, 20, 22, 24, 33, 37 and the M1 round), the tokens.css header, the `a-live-*` and `a-session-*` boards, the M1 code in `app/`, and a scout inventory of the old `/api/live` code and tests on November 9. Line numbers for the old app come from that inventory and point at `dashboard/api_live.py` as it is today (627 lines), so they differ from plan-a's "280-404".

## 1. What M2 delivers

Live is the home page and the screen the owner lives on. M2 builds it as drawn on `a-live`, not as a copy of the old page.

The owner starts the demo and watches a made-up session run on a fake clock. The four tiles count up. In "Who is working" the tokens-per-minute bars fill in, lanes grow toward Now, new runs appear indented under the run that started them, and a resumed run gets its "Round 2" mark. Model check says whether each agent ran on the model and effort its file sets. Latest requests lists the newest requests with an API-rate cost and "Prices as of {date}". Pause holds the page still, and a hidden tab stops asking the server.

Then the owner points the preview at their own `~/.claude` through the checkout run path (O9). From here on the owner uses Bar Tab for daily Live work, so the store starts keeping history early. The store sits in `<config>/routing-dashboard/bartab/` behind the M1 path guard and writer lock, and nothing outside that folder is written.

## 2. Decisions this plan makes

The designer and owner can push back on any of them. Items that need an owner answer are in section 8.

| Item | Pick | Why |
|---|---|---|
| Time model | The server builds the timeline at a clock T and ignores every request after T. The clock comes from the provider (real, fixed, replay at a rate, or set by a test). Live asks at T = now | The old route works the same way (`api_live.py`, records count only when `ts <= now`), so the old app at T stays a usable oracle. The demo's fake clock and the replay oracle need no transcript writes |
| Value at T on the page | The payload also carries everything needed to pick values at any earlier T (`cum[]`, `states[]`, `parent_at`, `rounds[]`). A pure `timeline-at.ts` module picks them | Session review (M3) reuses the payload with the replay line, and Vitest can prove the picker against the old app now, before M3 |
| Open minute | Whole minutes come from `minute_usage`. The minute that holds T is summed from `best_requests` with `ts <= T` | A `minute_usage` cell holds the whole minute, which would leak requests after T on a fake clock or in replay |
| Lane segments | One segment per round, from the round's start to its last request. A working run's current segment ends at T | Matches the board, where tech-writer shows a round 1 bar and a short round 2 bar at Now. Gaps inside a round are not drawn |
| Running and active | Running is a request in the last 30 minutes, strict (`>`). Active is a request in the last 60 seconds. Run state is finished, else working when `T - active_at < 60 s`, else idle | Ported from `api_live.py:75-78` and `:356-369`. The M1 hot loop's `running_folders` uses `>=` (inclusive). That only decides which folders get a fast stat, so it stays, and the timeline uses the strict rule |
| Parents and unlinked runs | Earliest launch link at or before T names the parent. No link means parent `main` with `parent_known: false`. `parent_at` says when the link appeared | Ported from `_parents` (`api_live.py:178-203`). A foreground child has no link until it finishes (fact V-7b16), so at T it reads as unlinked. `parent_at` keeps that true when the page picks an earlier T |
| Done | A stop at or before T with `finished`, no round started after it, and every child done. Main is never done | Ported from `api_live.py:307-336`, rebuilt from `run_events` rows (launch, brief, stop) |
| Labels and privacy | A run's name is its agent type from the child's `.meta.json`, plus a number when several share it ("scout 2"). The answer carries branch names, model ids and agent types, never `cwd`, message text, tool data or descriptions | The old Live returns no text either (`api_live.py` docstring, privacy tests at `tests/test_api_live.py:804-825`). The store keeps `sessions.cwd` for project mapping, so a test checks it never leaves |
| Numbers | New tokens are input, output and both cache writes. Cache reads are their own series. Cost is priced per request at query time and summed. Latest requests' `tokens` includes cache reads, as the old route does (fact V-1c9f) | Same numbers as the old Live, so the oracle compares them directly. Prices stay pinned to `prices-old.json` in the oracle tests, as in M1 |
| "In the last minute" | On Live, a rolling 60 seconds before T, from `best_requests`. In replay (M3), the bucket that holds T | Matches the old `last_minute` (`api_live.py:422-424`) at T = now. Replay has no rolling window to match |
| Axis | The whole session on one axis. `bucket_seconds` is the smallest of 60, 120, 300, 600, 900, 1800 and 3600 that gives at most 60 bars. Buckets align to UTC minutes | Plan-a section 3. The old Live showed only the last 30 minutes, but the board draws the whole session (6:10 to Now). Designer pass 2 may change the long-session layout. The server's bucket choice is one function, so a change there stays small |
| Etag | A hash of the answer without the fields that move only because T moved: `server_time`, `as_of`, `axis.end` and the end of each working run's last segment (`etag_of` in `app/server/timeline.py`). `{project, server_time, etag, unchanged: true}` when it matches, as in the old route (`api_live.py:619-626`). On a moving clock, 1 s polls with no new request answer `unchanged` (`test_timeline_etag.py`). A new request, state, round or bucket changes it. The page's as-of time refreshes only with a full answer. Gzip on answers over 1 KB | Plan-a section 3. Live polls every second, so most answers are the short form. Gzip keeps a long session's first answer small |
| Hot loop | Folders of sessions with a request in the last 60 seconds are stat-checked every 500 ms. Running folders stay at 1 s and the rest at 10 s | The exit asks for Live data within 2 s of the transcript. A 1 s stat loop plus a 1 s poll can reach 2 s on its own. The stat-only pass took 7 ms on the demo with no changes (m1-build.md section 11) |
| Page clock | The page keeps an offset to `server_time`, moves Now every second between answers, and never steps back more than 2 s | The board's working lanes reach Now, and Now moves even when the data doesn't. The old page used the same 2 s rule (`STEP_BACK_MS`) |
| Polling | TanStack Query with `refetchInterval` 1 s on the timeline and 5 s on the session list, off while Pause is on or `document.visibilityState` is hidden. A visible tab refetches at once. Three failures in a row move to a 10 s retry and the lost state | Plan-a section 3 and the old page's `live_poll.js:16-17` |
| Announcements | One polite live region on the page. It says run state changes only, at most once per row per minute, and the first answer after a load or a session switch sets the baseline and says nothing | Component 11 and WCAG 2.2.2 and 4.1.3. The old page read time, tokens and cost every minute. The new page says only what changed state |
| Pause | Per tab, not stored. A reload starts live | Plan-a lists Pause under server preferences. A Pause left on overnight would hide live data the next morning, and storing it needs a write route on a server that is otherwise read-only on real data. Question 5 asks the owner |
| `prefs` table | Deferred again. The last project stays in the tab's storage as it is today | Nothing in M2 needs a server write. Keeping the real-data server read-only outside its store makes section 7 simpler |
| Session list | `/api/live/sessions` lists running sessions across every project, plus the newest ended session for the current project | The old app has no cross-project list. Its Live picked among one project's `running[]`. The Session Select spans projects (plan-a section 3), and the nothing-running state needs the last ended session |
| Demo flow | `serve.py --flow <scenario>` builds a `live_flow` scenario (`tests/fixtures/live_flow/build_flow.py`) and serves it with a clock. `--clock-rate N` runs the clock N times real time from the session start. `--test-clock` adds a test-only `POST /api/dev/clock`. All three are refused with `--real` | The owner watches the goal run on the demo, and Playwright steps the clock to exact minutes. The old builder is run, never edited |
| Model check | Port the old resolver read side and pin check now, as in question 1 option A | The card is on Live, the owner's main screen, and the board shows a real reason ("the effort cap in Project local lowers it"). A narrow reader would give different answers from the M4 resolver and get built twice |
| Real-data mode | One server flag, `--real`. The server works out both paths itself, writes only inside the store root, and installs a Python audit hook that refuses any write outside it | Section 7. One flag means no hand-typed path can point the store somewhere else |
| Demo marker | `/api/app` gains `mode` (demo, fixture, flow, real) and `clock`. The shell shows a quiet "Demo data" mark in every mode but real | Once real data arrives, the owner must never mistake the demo for their own numbers. The designer places it (section 5) |

## 3. Ordered tasks

Tiers follow the owner's routing rules. fast-worker runs at medium unless the row says high. Every brief starts with `Kind: rebuild-m2` and carries the HiveMind line from `hivemind_lib.py related <paths>`, the date rule (`date -Iseconds` only) and these limits. Work only in `/Volumes/Warehouse/Projects/claude-code-model-routing-bartab`. Never read anything under `~/.claude`, real transcripts, real settings or `~/.claude.json`. Never pass `--real` to anything. Servers only on ports 47000 to 47999, never 8377. Never print, guess or ask for a key. Use `app/scripts/uvw` and `app/scripts/npmw` for every uv and npm call, and fetch no new Python. Never edit `dashboard/`, `tests/`, `plugins/`, `tools/`, `hooks/`, `agents/`, `rules/`, `skills/` or `install.py`.

HiveMind ids for briefs: T-7629, T-5589, T-c826, T-3ad1, D-c684, V-1c9f, V-7b16, W-734f, Q-0ec1, L-979a, L-bd45, I-14ae, D-3ca7, plus whatever `related` returns per task.

| # | Task | Files | Tier | Check |
|---|---|---|---|---|
| 0 | Pre-flight. Time, branch, clean tree. In `app/server/tests/conftest.py`, point `HOME` and `CLAUDE_CONFIG_DIR` at a temp folder for the whole session, and add an audit hook that fails a test on any open under the real `~/.claude`. Add a session fixture that builds each `live_flow` scenario into a temp folder. Write the timeline and session-list Pydantic models in `models.py`, so the contract is fixed before workers start | `app/server/tests/conftest.py`, `app/server/models.py` | Lead | A test that opens a path under the real config folder fails with the guard's message. The models import and the OpenAPI export runs |
| 1 | Lookups. Whether the demo and `live_flow` builds carry agent files and settings that give judge a Lowered effort, as `a-live` draws. Every file and environment variable the old `resolve.resolve` and `collect.py` read, with path:line. Which Python 3.11 audit events cover file writes, renames, deletes, folder creation and `sqlite3.connect`, and whether SQLite's `-wal` and `-shm` files bypass them (docs.python.org audit events table). Playwright's `page.clock` in the pinned version. Whether fixture transcript rows carry `version` (m1-build.md section 2, still open). Fixtures and docs only | None. A table of fact, value and path:line or URL | scout | Every row has a source |
| 2 | Live recorder. Extend `app/oracle/record.py` to build each scenario with `build_flow.py`, set `session.json` `now` to each sampled T, call `api_live.live` in process through `server.fixture_context` (fact W-734f), and write a reduced projection (runs, parents, rounds, states, tokens, cost, buckets, totals, last minute, latest requests) per T. Also record the old pin check for each scenario's agents (`pincheck.check_agent` over `resolve.resolve` entries). Sampled T is every minute from the session start to the scenario clock, plus T at 59 s and 61 s after each run's last request in `busy` | `app/oracle/record.py`, `app/fixtures/oracle/live/<scenario>/*.json`, `manifest.json`, `allowed-differences.json` | fast-worker | Two runs give the same bytes. About 140 files. The old commit sha is in the manifest |
| 3 | Timeline core (high). `timeline.py` builds the session timeline at a clock T over a read connection. Sessions, runs, parents, dispatch order, `label_n`, together, rounds, done, states, segments, buckets and `cum[]`, the open minute, last minute, totals, latest requests and the etag. `live_sessions.py` builds the session list. Adds `parent_at` from link times if `run_events` lacks it | `app/server/{timeline,live_sessions}.py`, tests | fast-worker high | Behaviour tests for every rule in section 2, ported from the old `Running`, `SessionChoice`, `Numbers` and `Dispatch` test classes (the old file has 100 tests). The server-at-T replay oracle passes on all four scenarios outside the allowed list. pyright strict, coverage 85 percent |
| 4 | Clocks and the demo flow. A `Clock` in `provider.py` (real, fixed, rate, test). `serve.py` gains `--flow`, `--clock-rate` and `--test-clock`, refused with `--real` and `--claude-dir`. `POST /api/dev/clock` mounts only with `--test-clock`. `/api/app` gains `mode` and `clock` | `app/server/{provider,serve,store_provider,api_app,api_dev}.py`, tests | fast-worker | The flow demo reaches `done` and serves a timeline. The dev route is absent without the flag. The refusals fire |
| 5 | Live API. `GET /api/sessions/{id}/timeline` and `GET /api/live/sessions` with `as_of`, the etag and the short `unchanged` answer, the error codes in section 4, gzip, then the OpenAPI export and `schema.d.ts` | `app/server/{api_live,main}.py`, `app/web/src/api/openapi.json`, `app/web/src/api/schema.d.ts`, tests | fast-worker | TestClient on all four scenarios. `cwd` never appears in any answer. OpenAPI staleness test passes |
| 6 | Model check. Port the read side of `resolve.py` and `collect.py` and all of `pincheck.py` with their tests, cut free of the old server `Context` as M1 did for `projects.py`. Then `model_check.py` builds the timeline's `model_check` from the session's runs. Two dispatches, the port first | `app/server/{resolve,collect,pincheck,model_check}.py`, `app/server/data/agent_fields.json` if needed, tests | fast-worker, two dispatches | Every ported test passes under pytest, old and new counts side by side. The new check equals the recorded old pin check on all four scenarios |
| 7 | Real-data mode (high). Server `--real` (section 7), the audit-hook write allowlist, `TMPDIR` and `sys.dont_write_bytecode` inside the store, `claude_version` from the newest session. Launcher `--real`, run state under `bartab/run/`, a shared uv environment, a `status` line with pass times and lag in numbers only. The skill change from question 3 and the guard cases from question 4. A real-mode write audit test with a fake `HOME` | `app/server/{serve,store_paths,write_guard}.py`, `app/bin/bartab.py`, `.claude/skills/`, `app/server/tests/test_real_mode.py`, `app/server/tests/test_launcher.py` | fast-worker high | Section 7's tests pass. Launcher tests as subprocesses with `["guard"]` (fact L-979a) |
| 8 | Designer passes 1 to 3 (dispatched by the main session, not this lead). Live at 375, a long session, nothing running and the ended session. Then the designer's review of this plan | Boards in the archive, notes in components.md | designer | Picked by the owner before tasks 10 to 12 |
| 9 | String deck. Every Live word on the board, plus the states in section 5 that have no board (ended, nothing running, paused, lost, session gone, unpriced, unlinked, the demo mark, announcements, "API-rate estimate" and the subscriber help line). Waits for task 8 | Draft as a key table, typed into `app/web/src/strings/en.ts` by the lead | tech-writer | String lint passes. Owner reads the deck |
| 10 | Wave 2 components. Tile (18), status chip (10), run-state chip (11), badge (12), stacked bars and legend by model (20, no kind patterns yet), timeline lane (22), table in a well (24), each with every state on the component sheet. Tile, chips, badge and table can start before task 8. The lane and the bars wait for passes 1 and 2 | `app/web/src/components/*`, `app/web/src/sheet/*`, tests | fast-worker | Vitest, the sheet test fails on any manifest state without a render, axe on the sheet at 375 and 1440, light and dark |
| 11 | Live data layer (high). Query hooks for the timeline and session list with etag, visibility and Pause gating, the 10 s retry, the page clock, `timeline-at.ts` (values at T), and the announcer (per row per minute, baseline on load) | `app/web/src/lib/{timeline-at,live-clock,announcer}.ts`, `app/web/src/api/live.ts`, tests | fast-worker high | Vitest with fake timers. The Vitest oracle picks values at every recorded T from the end-of-session payload and matches the old app outside the allowed list |
| 12 | Live page. Header with run state, title and sub, Session Select, Updated and Pause. Tiles, Who is working, Model check, Latest requests, every state in section 5, the demo mark, the cost label. Routes `#/p/<project>/live?session=<id>` | `app/web/src/pages/LivePage.tsx`, `LivePage.css`, `app/web/src/app/{routes,router}.ts*`, tests, `app/web/e2e/live.spec.ts` | fast-worker | Vitest, tsc, ESLint, Stylelint, Prettier. Playwright with axe at 320, 375 and 1440, light and dark, forced colours and reduced motion |
| 13 | Live end-to-end. The fake-clock run counting announcements, Pause and hidden tab, the 2 s latency check and the eight-hour size check from section 6 | `app/web/e2e/live-clock.spec.ts`, `app/server/tests/test_live_latency.py`, `test_timeline_size.py` | fast-worker | All pass three runs in a row |
| 14 | Exit runs. T2 suite, the full Playwright and axe matrix, then the old suite alone with its log named for `feature-bartab-m2` (T-7629), then the protected-path diff | Logs in the scratchpad | scout | All green. The diff is empty |
| 15 | Browser check in Chrome under the tab-group rules. Live on the `busy` flow at 1440 and 375, light and dark, against `a-live-*` and the pass 1 to 3 boards | None. Returns a difference list | judge | Differences fixed in one batch, or listed for the owner |
| 16 | One fix round from tasks 14 and 15, consolidation and the report. The owner then starts the preview on real data. The main session dispatches the verifier | None | Lead | Report written |

Order and parallel work. Task 0 runs first. Then 1, 2, 4, 6's port half and 7 run in parallel, because they touch separate files. Task 3 starts when 1 lands (it needs nothing from 2 to start, and runs its oracle once 2 is in). Task 6's second half needs 3. Task 5 needs 3 and 4. Task 8 runs beside all of that, since it is the main session's dispatch. Task 9 waits for 8. Task 10's first half can start any time after 0, and its lane and bars wait for 8. Task 11 needs 5 and 2. Task 12 needs 9, 10 and 11. Task 13 needs 12. Then 14, 15 and 16. Only the lead edits `conftest.py`, `pyproject.toml`, `models.py` and `en.ts`, so parallel workers never collide there. M2 adds no package, so neither lockfile changes. If the pinned Playwright lacks `page.clock`, task 13 stops and the lead asks the owner before any upgrade.

## 4. API contract

All times are ISO strings in UTC. The page formats them in the browser's zone. Every answer carries `as_of`, `server_time` and `etag`. A request whose `etag` matches gets `{project, server_time, etag, unchanged: true}` and nothing else. Errors use the one envelope `{code, path}` (`ErrorEnvelope` in `app/server/models.py`), where `path` is the request field at fault or null. It never carries input or file paths. Model ids are catalog ids. The page owns every word.

### `GET /api/sessions/{id}/timeline?project=<key>&etag=<tag>`

Errors. `bad_request` (400, a missing or repeated parameter), `unknown_project` (404), `unknown_session` (404, no such session in this project, which the page shows as session gone).

| Field | Type | Contents |
|---|---|---|
| `project`, `server_time`, `as_of`, `etag`, `unchanged` | | As above. `server_time` is the clock T |
| `session` | object | `id`, `project`, `branch` (or null), `started`, `last_request`, `running`, `active`, `state` (working, idle, ended), `requests`, `unpriced_requests` |
| `axis` | object | `start`, `end` (T while running, else the last request rounded up to its bucket), `bucket_seconds`, `ticks[]` (times for x labels), `token_ticks[]` (1, 2 or 5 times a power of ten, at most 5 steps, as `usage.token_ticks`) |
| `buckets[]` | list | `start`, `by_model {model: new_tokens}` (models with 0 left out), `cache_read`, `cost` (or null when every request in it is unpriced), `requests` |
| `models[]` | list | `model`, `tokens` over the axis, in catalog order, for the chart legend |
| `last_minute` | object or null | `tokens`, `cost`, `cache_read`, `hit_rate`, `requests` over the 60 s before T. Null when the session has ended |
| `totals` | object | `tokens` (new), `input`, `output`, `cache_read`, `cache_write`, `cost`, `unpriced_requests`, `hit_rate`, `requests`, `runs`, `runs_working`, `runs_finished`, all at T |
| `runs[]` | list | `run_id` (12-hex hash, same scheme as the old route), `agent` (agent type, `null` for the main session, `unnamed` when unknown), `label_n` (or null), `parent` (`main`, a `run_id`, or null for main), `parent_known`, `parent_at` (or null), `depth`, `dispatch_order`, `together {key, n}` (or null), `model`, `effort` (the pair with the most requests), `first_request`, `last_request`, `state` at T (working, idle, finished), `states[] {at, state}`, `rounds[] {n, at, last_request, by, by_kind}` where `by` is `main`, a `run_id` or null and `by_kind` is coordinator, peer, human or null, `segments[] {start, end}`, `tokens`, `cost` (or null), `cum[] {tokens, cache_read, cost}` per bucket |
| `requests[]` | list | The eight newest at or before T. `id`, `at`, `run_id`, `model`, `effort`, `tokens` (every kind, cache reads included), `new_tokens`, `cache_read`, `output`, `cost` (or null) |
| `model_check` | object | `rows[]` per agent type in the session, `{agent, set {model, effort} each {value, file, line, scope} or null, ran {model, effort, mixed}, status, reason_code, params, runs, mismatched_runs}`, plus `in_effect_count`. `status` is one of the seven status words (In effect, Overridden, Ignored, Lowered, Invalid, Default, Unknown). `file` is a display path such as `.claude/agents/judge.md` |
| `prices` | object | `as_of`, `source`, `cross_check_state`, so the cost label needs no second call |

Sizes. The answer is one session's whole axis, so its size grows with runs and buckets, never with minutes past 60 buckets. Task 13 measures an eight-hour session with 200 runs.

### `GET /api/live/sessions?project=<key>&etag=<tag>`

Errors. `bad_request` (400), `unknown_project` (404).

| Field | Type | Contents |
|---|---|---|
| `server_time`, `as_of`, `etag`, `unchanged` | | As above |
| `sessions[]` | list | Running sessions in every project, newest last request first, ties by id descending. `id`, `project`, `project_name`, `branch`, `started`, `last_request`, `active`, `runs_working`, `requests` |
| `latest_ended` | object or null | The newest session in `project` that is not running. `id`, `branch`, `started`, `last_request`, `requests` |

### `GET /api/app` in M2

The M1 contract (m1-build.md section 10) keeps every field. M2 adds two.

| Field | Type | Meaning |
|---|---|---|
| `mode` | demo, fixture, flow, real | What the server reads |
| `clock` | `{kind: real, fixed, rate, test, rate_n}` | `rate_n` only for `rate` |

`claude_version` on real data comes from the newest session's `version` (task 1 checks the field). `running[]` keeps its M0 shape and now drives the sidebar's Working mark from real sessions.

## 5. UI state and data for the designer review

Each item lists what the screen needs. The words come from task 9 after this review. Three of the states below have no board yet. They wait for designer passes 1 to 3 (plan-a section 2, items 1 to 3), which were not drawn during M0 and M1.

### Page states

| State | When | Data |
|---|---|---|
| First load | No answer yet | Skeleton bones at measured heights for the header, tiles, lanes and both lower cards, `aria-busy` and one screen-reader line |
| Working | The session has a request in the last 60 s | `session.state` working |
| Idle | Running, but no request in the last 60 s | `session.state` idle, `last_request` |
| Ended, still shown | The session in the URL stopped running while open, or the owner picked an ended one | `session.state` ended, `last_request`. Polling drops to every 10 s, so a resume brings it back |
| Nothing running | No running session in this project | `latest_ended` (or null), and `sessions[]` for other projects that are running. Needs pass 3 |
| No sessions at all | `latest_ended` null and nothing running | A first-use empty state |
| Session gone | The URL names a session this project doesn't have | `unknown_session`. Offers the newest running one |
| Paused | The owner pressed Pause | The page time freezes at the pause, and the button reads Resume |
| Lost | Three failed polls in a row | The last good data stays on screen, a raised finding says the dashboard can't reach the server and when it tries again (every 10 s). The M0 server-stopped gate still takes over when every call fails |
| Updates stopped | `history.pass_error` from M1 | The M1 notice line already covers it on every page |
| Demo data | `mode` is not real | A quiet mark the designer places |

### Header

- Board. The run state (glyph and word, no pill per D8), the branch as the title, the sub "Tidewater reporting, started 6:10 PM, 30 minutes so far", then on the right the Session Select, "Updated {time}" and Pause.
- Data. `session.state`, `branch`, `project_name`, `started`, `server_time` and `axis.start` for the duration, `as_of` for Updated.
- Need from the designer. The title when `branch` is null. Whether "Updated" in the header means the last answer (seconds, as drawn) while the sidebar footer means data checked (minutes, M1 owner answer 8), or one meaning for both. What Paused shows beside the button.

### Tiles

- Spent so far. `totals.cost`, `last_minute.cost`, proof spark from `buckets[].cost`. Label "API-rate estimate" and "Prices as of {date}" from `prices` (plan-a M2 "Lands too"). `unpriced_requests` above zero needs a line.
- Tokens. `totals.tokens`, `last_minute.tokens`.
- Read from cache. `totals.hit_rate`, `last_minute.hit_rate`, ring proof.
- Agents working. `totals.runs_working`, `runs_finished`, `runs`, dots from each run's state.
- Ended session. `last_minute` is null, so the second lines need an ended form.

### Who is working

- Chart. `buckets[].by_model` stacked by model, `models[]` for the legend with totals, `token_ticks[]`, `axis.ticks[]`. The last bar is the open minute and grows between answers.
- Lanes. One row per run in `dispatch_order`, nested by `parent` and `depth`. Each row has the name (`agent` plus `label_n`), model and effort with the swatch, `segments[]` on the track, round marks from `rounds[]` (mark from round 2 on), the run-state chip, "Last request {n} s ago" for working and idle or "Ran {n} min" for finished, `tokens` and `cost`.
- Unlinked runs. `parent_known` false sits under the main session. It needs a mark that says the starter isn't known yet, because a foreground run gets its link only when it ends and then moves under its real parent. The designer decides the mark and whether the move is announced.
- Depth. The `many` scenario has 24 runs at three levels. Pass 2 decides the indent cap and how 24 rows fit.
- Long sessions. `bucket_seconds` above 60 changes the x labels and makes a short round thinner than one bar. Pass 2 decides.
- Rows are not links in M2, because the run view lands with Session review in M3. Pass 2 confirms the row has no hover until then.
- Unpriced. A run with `cost` null needs a cost cell that says why.

### Model check

- Data. `model_check.rows[]` with `status`, `set` (file, line, scope), `ran`, `reason_code` and `params`, and `in_effect_count` for the "The other 5 agents ran as their files set" line.
- "See why" points at the setup surface page, which lands in M4. The designer decides whether it hides or opens Agents until then.
- Empty. A session with only the main session still has one row. A session whose agents have no files needs a sentence.

### Latest requests

- Data. `requests[]`, newest first. Time with seconds, agent name, model and effort, tokens, cost. The board shows five rows and the API sends eight. The designer picks the count at each width.
- Footer. "Estimated at API list price" with "Prices as of {date}", and the subscriber help line from plan-a section 3.

### Session Select

- Data. `sessions[]` across projects plus the current one when it has ended. Each option has the branch, start time and project name.
- Event. Picking a session in another project goes to that project's Live route (plan-a section 3).
- Need from the designer. Grouping by project, and how the current ended session shows in the list.

### Events the page handles

| Event | What happens |
|---|---|
| Poll answer with new data | Values change in place. No motion outside reduced-motion rules. Run state changes go to the announcer |
| Poll answer `unchanged` | Nothing changes except Now |
| A run changes state or starts | One polite line, at most once per row per minute. The first answer after load or a switch is the baseline and says nothing |
| The session ends | One polite line, then the ended state |
| Another session starts while one is pinned | A notice with a Switch button (question 6) |
| Pause and Resume | Polling stops and starts. The button label swaps. One polite line |
| Tab hidden and shown | Polling stops while hidden and refetches at once when shown |
| Three failed polls | Lost state, then a retry every 10 s, and back to live on the first good answer |
| Route change to another session | The baseline resets, focus goes to the h1, the route status speaks |
| Data checked time moves | Footer only, never announced |

## 6. Tests and exit

### New suites

| Area | Tests |
|---|---|
| Timeline rules | Ported behaviour cases from the old `Running` (window edges at 29:59 and 30:01, records after T ignored), `SessionChoice`, `Numbers` (buckets, cache reads, ticks, latest eight, cost) and `Dispatch` (parents, together, `label_n`, rounds, states, done, peers, cycles, zones) classes |
| Replay oracle, server at T | For `busy`, `many`, `unlinked` and `empty`, at every recorded T, the timeline built at T equals the old `/api/live` at T on runs, parents, rounds, states, tokens and cost, buckets in the overlapping 30 minutes, totals, last minute and latest requests, outside `allowed-differences.json` |
| Replay oracle, page at T | Vitest loads each scenario's end-of-session timeline and the recorded old payloads, picks values at every T with `timeline-at.ts`, and compares the same fields |
| Model check | The new `model_check` equals the old pin check on every scenario. Ported resolver and pin check tests pass |
| Privacy | No answer carries `cwd`, message text, tool data or a description. The schema text-column test from M1 still passes |
| Fake-clock run | Playwright on the `busy` flow with `--test-clock`. The test steps the server clock one minute at a time from 22:10 to 22:40 and advances `page.clock` one second per poll. It records every text written to the polite region with a MutationObserver and asserts the count equals the run state changes in the recorded payloads after the per-row, per-minute limit, and that no unchanged answer announces anything. Repeated with reduced motion |
| Pause and hidden tab | Playwright counts requests to the timeline and session routes. With Pause on, zero in 5 s of page time. With the page hidden through a dispatched `visibilitychange` and an overridden `visibilityState`, zero. On show, one at once. Vitest covers the same in the hook |
| Latency | A pytest with the real writer on a temp tree appends a request row 20 times and polls the timeline. The median lag is under 1.5 s and the worst under 2.0 s. A Playwright twin on the `busy` flow checks the lane's token text within 2.5 s, which includes the 1 s poll |
| Long session size | A generated eight-hour session with 200 runs. The timeline builds in under 100 ms at the 95th percentile, and its gzip body is under 200 KB. The numbers go into the results section |
| Real mode | Section 7 |
| Web | Vitest for every component state, the announcer and the page clock. Playwright with axe on Live at 320, 375 and 1440, light and dark, forced colours and reduced motion, on `busy`, `many`, `unlinked`, `empty` and the nothing-running fixture |

Run Playwright from `app/web` with its config, `../scripts/npmw exec playwright -- test -c playwright.config.ts`. From the repo root it finds no config, and Vitest or Vite run there drop a stray `node_modules/` at the root.

### Allowed differences to start with

1. Runs not started at T appear on the new timeline. Live at T = now never has one.
2. "done" reads as finished, and run states use working, idle and finished.
3. `label_n` and `together` count the whole session, so "scout" at an early T can read "scout 1".
4. Buckets cover the whole session at `bucket_seconds`. Only the minutes inside the old 30-minute window are compared, and only when `bucket_seconds` is 60.
5. Model names are ids. The old `model_display` is not compared.
6. In the page-at-T oracle, "last minute" is the bucket that holds T, not a rolling 60 seconds.
7. The old route has no session list across projects, so `/api/live/sessions` has no oracle. Its tests use crafted stores.

Any other difference fails. Each entry names its reason in the JSON, as in M1.

### Kept green

- The M0 and M1 exit runs, with pytest and Vitest counts in the report.
- Standards checks. ruff, ruff format, pyright strict, coverage at 85 percent on `app/server`, tsc, ESLint, Stylelint and Prettier.
- The old suite alone, `/usr/bin/python3 -m unittest discover -s tests` from the worktree root, log named for `feature-bartab-m2` (T-7629). Expected 3575 tests and 88 skipped.
- `git diff --stat 82dbddd -- dashboard tests plugins tools hooks agents rules skills install.py` stays empty.

### Exit, from plan-a M2

- Run states, parents, rounds, tokens and costs match the old `/api/live` at every sampled minute, outside the allowed list, both at T and picked from the end payload.
- Live data stays within 2 s of the transcript (median and worst recorded in the results).
- The owner watches the `busy` flow on the fake clock at 1440 and 375, then starts the preview on real data and uses it for daily Live work.

## 7. Real data

Agents never read real data. Only the owner's own launch does. Every agent brief in M2 forbids `--real` and real paths, and question 4 asks whether a hook should enforce that.

### How the owner starts it

With question 3 option A, the owner types `/bartab-preview` in Claude Code in this checkout. The skill's line becomes the following, and `/bartab-demo` keeps today's demo line.

```
python3 "${CLAUDE_PROJECT_DIR}/app/bin/bartab.py" --default-project "${CLAUDE_PROJECT_DIR}" --session "${CLAUDE_SESSION_ID}" --real $ARGUMENTS
```

- The launcher's `--real` refuses `--demo`, `--ingest-pace-ms`, `--fixture` and `--data`.
- It keeps its run state (`server.json`, `port`, `launcher.lock`, `logs/`) in `<config>/routing-dashboard/bartab/run/`, outside the checkout, because logs can name real project folders. The uv environment stays in the checkout's `app/.data/uv/`, because it holds code only. A demo server and a real server can run side by side on different ports.
- It starts the server with `serve.py --real` and the M0 launch-fd handshake, and prints the one-time link as today.
- `bartab.py --real status` prints the last hot and cold pass times and the lag in numbers only, so the owner can paste them into a chat without sharing data.
- The first start on real data shows first run with real progress. Real data has no pace.

### What the server reads

- `<config>` is `CLAUDE_CONFIG_DIR`, else `$HOME/.claude` (`store_paths.config_dir_default`, as the old app resolves it).
- Transcripts. `<config>/projects/*/*.jsonl`, each session's `subagents/` files and their `.meta.json`. Usage numbers, ids, times, models, effort, branch and cwd only, as in M1.
- `<config>/routing-dashboard.json`, read only, for the project list (M1).
- For Model check (task 6). `<config>/settings.json`, `<config>/agents/*.md`, the managed settings file, and in each listed project `.claude/settings.json`, `.claude/settings.local.json` and `.claude/agents/*.md`. Task 1 lists every file and environment variable the old resolver reads, and the final list goes in the results section. `~/.claude.json` is not read in M2.
- The network. The two daily price GETs from M1, nothing else.

### Where the store goes

| Path | Contents |
|---|---|
| `<config>/routing-dashboard/bartab/bartab.db` with `-wal` and `-shm` | The store |
| `bartab/writer.lock` | The single-writer lock from M1 |
| `bartab/db-backups/` | Seven copies (M1) |
| `bartab/prices/` | Last good price copy (M1) |
| `bartab/run/` | Launcher state and logs (new) |
| `bartab/tmp/` | `TMPDIR` for the real-mode server (new) |

The old app's files in `<config>/routing-dashboard/` (backups, ledger, `.lock`, `.bak` files) are never opened for write, locked or listed by a writer (N1, M1 coexistence test).

### What guarantees nothing is written outside it

1. One flag. `serve.py --real` works out `<config>` and the store root itself and refuses `--claude-dir`, `--store`, `--demo`, `--flow`, `--test-clock` and `--ingest-pace-ms`. No path is typed.
2. The M1 path guard. Every write goes through `store_paths.writable`, which refuses any path outside the store root or named like an old-app file.
3. A runtime write guard. In real mode the server installs a Python audit hook at start, before any other import opens a file. It refuses `open` with a write mode, `os.rename`, `os.replace`, `os.remove`, `os.mkdir`, `shutil` copies and `sqlite3.connect` for any path outside the store root, and logs the refusal by code. Audit hooks can't be removed once set. SQLite writes its `-wal` and `-shm` files beside the database inside C code, which the hook can't see, so the hook checks the database path at `sqlite3.connect` instead. Task 1 confirms the event names for Python 3.11.
4. No bytecode and no stray temp files. Real mode sets `sys.dont_write_bytecode` and points `TMPDIR` at `bartab/tmp/`.
5. Transcripts and settings are opened read-only (`rb`), and SQLite opens nothing outside the store.
5a. Real reads. Settings and agent files are read only for the projects listed in `routing-dashboard.json` (with `~` expanded against HOME), plus user scope and the managed folder: `/Library/Application Support/ClaudeCode` on macOS, `/etc/claude-code` on Linux and `C:\Program Files\ClaudeCode` on Windows, as the old app's `dashboard/server.py:105-109`. A project known only from a transcript `cwd` still shows usage, but nothing under that `cwd` is read, Model check uses user and managed scope only, and its `display_path` is `~/...` under HOME or else its name, never the raw `cwd`.
6. The test. `test_real_mode.py` builds a fake `HOME` with a `.claude` folder holding transcripts, settings, agents and every old-app file. It starts the server as a subprocess with that `HOME` and `--real`, runs first run, a hot pass, timeline and session polls, a backup, a price copy through the offline transport and a clean stop. Then every file outside `bartab/` keeps its bytes and mtime, no new file appears outside it, and the audit log has no refusals. A second case plants a write outside the root and checks the hook refuses it.
7. Test isolation. Task 0's `conftest.py` points `HOME` and `CLAUDE_CONFIG_DIR` at a temp folder and fails any test that opens a path under the real `~/.claude`.

## 8. Owner questions

Each has my pick first.

1. Model check source. Live's Model check needs to know what each agent's file and the settings set, which comes from the resolver. M1 moved that port to M4.
   - A (my pick). Port the resolver read side, collect and the pin check in M2 (task 6), and drop them from M4. It adds $8 to $14 here and takes about the same off M4. The card on the owner's main screen then gives the same answer M4 will.
   - B. Ship Model check in M2 with "ran with" only, and add the "set" half and the statuses in M4. Needs a designer state for a half card.
   - C. Hide Model check on Live until M4.
2. Designer passes 1 to 3. Live at 375, the long session and the nothing-running and ended states have no boards yet. The plan needs them before the lane, the chart and the page are built.
   - A (my pick). The main session dispatches them now. Tasks 0 to 7 and the first half of 10 run beside them, so no time is lost.
   - B. Build from the current board and fix after the passes. It builds the lane twice.
3. Preview commands for real data.
   - A (my pick). `/bartab-preview` starts on real data and becomes the daily driver. A new `/bartab-demo` keeps the demo with pace and gains the flow and clock options.
   - B. Keep `/bartab-preview` on the demo and add `/bartab-live` for real data.
   - C. One command, with `--real` typed after it. The launcher's rule that globals come before the action makes this awkward, so it needs a parser change.
4. Keeping agents off real data. The launcher's guard action exists and is tested, but M0 left it unwired until M9.
   - A (my pick). Wire it now as a PreToolUse hook in this checkout's `.claude/settings.json`, extended to deny any Bash command that passes `--real` or names the real config folder. Fact L-bd45 says the hook skips a skill's `!` line, so the owner's command still works. This changes project settings, so it needs your yes.
   - B. Rely on the brief rules only.
   - C. Leave it unwired, and make the launcher refuse `--real` unless a marker file the owner creates exists in `bartab/`.
5. Pause.
   - A (my pick). Per tab, not stored, so a reload starts live.
   - B. Stored on the server as plan-a says, so it survives a reload. Needs a write route.
6. A newer session starts while Live shows another.
   - A (my pick). Live stays on the session it opened on (the route gets `?session=`) and shows a notice with a Switch button.
   - B. Live follows the newest running session on its own, as the old page did, and announces the switch.
7. A session ends while it is on screen.
   - A (my pick). It stays, in the ended state with its final numbers, until you switch. Polling slows to 10 s so a resume brings it back.
   - B. Live moves to the nothing-running state at once.
8. Price disagreement on Live. M1 kept the OpenRouter cross-check out of sight for M2's cost cards.
   - A (my pick). A quiet line under "Prices as of" on the Spent tile, only when the check disagrees.
   - B. Keep it hidden until Summary in M3.
9. Store and launcher state on real data.
   - A (my pick). The store in `<config>/routing-dashboard/bartab/` (N1), and launcher state and logs in `bartab/run/`, so nothing real lands in the checkout.
   - B. Launcher state in the checkout's `app/.data/real/`. Its logs could hold real folder names inside the repo, where agents read.
10. Demo mark. Show a quiet "Demo data" mark in the shell whenever the server isn't on real data?
    - A (my pick). Yes, placed by the designer.
    - B. No mark.
11. Budget (section 9). It sits above plan-a's $40 to $70, because M1 ran about a quarter over its plan and M2 adds the model check port, the real-mode guard and the flow demo.
    - A (my pick). The full build with question 1 option A, $75 to $126, with a stop and report at $120.
    - B. The trimmed build, $65 to $112, with a stop at $105.
    - C. Either build without task 6, $67 to $112 full, with a stop at $105.

## 9. Cost estimate

List-price ranges. M1 was planned at $55 to $95 and came in around $71 to $112, about a quarter over, so each row below carries that calibration. M2 also takes on three things plan-a's $40 to $70 didn't price. Those are the model check port, the real-mode safety work, and the flow demo with its clocks. I have no per-run cost from the dashboard in this tree. [NEEDS CONFIRMATION: dashboard cost per run for each agent.]

| Dispatch | Count | Estimate |
|---|---|---|
| This plan step, lead and one scout | 1 | $8 to $12 |
| Lead build, reviews, string typing and consolidation, deep-reasoner on Opus at high | 1 | $18 to $28 |
| fast-worker at high, tasks 3, 7 and 11 | 3 | $21 to $36 |
| fast-worker at medium, tasks 2, 4, 5, 10, 12, 13 and one fix round | 7 | $21 to $35 |
| fast-worker at medium, task 6 (two dispatches) | 2 | $8 to $14 |
| scout, tasks 1 and 14 | 2 | $2 to $4 |
| judge, task 15 in Chrome | 1 | $3 to $5 |
| tech-writer at medium, task 9 | 1 | $2 to $4 |
| Total with question 1 option A | | $83 to $138 |
| Build only, after this plan step, with option A | | $75 to $126 |
| Build only, with option B or C (no task 6) | | $67 to $112 |

A trimmed build saves about $10 to $15. The lead types the session-list route and the two `/api/app` fields itself, and task 13's checks fold into task 12's dispatch. That gives $65 to $112 with option A. The full plan keeps the exit tests in their own dispatch, which is easier to review.

Stop line. The lead stops and reports before starting the next task once build spend passes $120 on the full plan with option A, $105 on the trimmed plan or without task 6.

Outside these totals. Designer passes 1 to 3 ($10 to $20 by plan-a's per-pass rate), the designer's plan review at medium ($2 to $4), and the verifier pass on Opus ($5 to $10) are the main session's dispatches.

## 10. Risks and leftovers from M1

### Leftovers M2 depends on

1. Designer passes 1 to 3 were never drawn. Plan-a scheduled them beside M0 and M1, and no `a-live` fix, long-session or nothing-running board exists in the archive's `shots/`. Question 2.
2. The resolver port moved to M4 (m1-build.md section 10, answer 1), but Live's Model check needs it. Question 1.
3. `{unchanged: true}` was deferred to M2 with the 1 s timeline (m1-build.md section 4). Task 5.
4. The "API-rate estimate" label and the subscriber help line were deferred to M2's cost cards, with the price disagreement kept in `/api/prices` (m1-build.md section 10, answer 7). Tasks 9 and 12, question 8.
5. `prefs` was deferred to M2. This plan defers it again (section 2).
6. `store_paths.config_dir_default` is unused, and the server has no default that reaches a real folder (m1-build.md section 4). Task 7 adds `--real`.
7. `claude_version` on real data from transcript rows is still unconfirmed (m1-build.md section 2). Task 1.
8. The 1 s hot loop and 10 s cold loop were never measured on a large real tree (m1-build.md section 9, risk 7). The owner's first real start measures them through `status`.
9. The launcher guard and SessionEnd hooks are unwired until M9 (m0-build.md section 10). Question 4.
10. Live is a placeholder route today, and the M0 fixture provider has no session or Live scenarios.

### Risks

1. Round and stop rules rebuilt from `run_events`. The old code reads links in memory. The new one reads launch, brief and stop rows, where a launch row's `run_key` is the dispatcher and a brief row's is the briefed run. The server-at-T oracle at every minute is the guard.
2. Late links. A foreground child moves under its parent only when it ends. `parent_at` covers replay. On Live the row moves, so the designer decides how.
3. The oracle covers only the old 30-minute window for buckets. The `many` scenario's first 30 minutes are checked on runs and totals only.
4. Long sessions. Payload size and the axis rule wait on pass 2. The eight-hour test measures the size.
5. The audit hook can't see SQLite's own `-wal` and `-shm` writes. The `sqlite3.connect` path check and the fake-HOME test cover them.
6. The owner's real tree may be large. First run on real data has no pace and shows real progress, and the store is kept from then on, so a slow first ingest happens once.
7. Two leads. M2 runs in its own worktree. The designer passes are review and drawing only and touch no file in `app/`.
8. Budget. Section 9's honest range sits above plan-a's. The stop line holds it.

## 11. Designer review focus

The designer's review of this plan should look at these, against the picked direction.

- Section 5's state list. Whether every Live state the boards need has data and an event, and which need pass 3.
- Unlinked runs that later move under their parent, and whether that move is announced.
- The header's Updated time against the footer's data-checked time.
- The ended session and the nothing-running state with `latest_ended`.
- The announcement rule (state changes only, per row per minute) and its wording slots.
- Lanes as non-links until M3, and "See why" before M4.
- The demo mark's place.

## 12. Owner answers and designer review, November 9

The owner took every pick in section 8 (all A) and said go for the parts that don't depend on the designs. This section overrides anything above that disagrees with it.

### Owner answers

1. Model check source is option A. The resolver read side, collect and the pin check port in M2 (task 6) and leave M4.
2. Designer passes 1 to 3 run now in a separate designer agent. The lane, the chart, the tiles, the page states and the task 9 strings wait until the owner picks the boards. Backend tasks 0 to 7 run now.
3. `/bartab-preview` starts on real data. `/bartab-demo` keeps the demo.
4. The launcher guard becomes a PreToolUse hook in this checkout's `.claude/settings.json`, extended to deny any Bash command that passes `--real` or names the real config folder. Subprocess guard tests prove it (fact L-979a). No agent launches real mode, not even to test it.
5. Pause is per tab and not stored.
6. Live stays on the session it opened on and shows a notice with a Switch button when a newer one starts.
7. An ended session stays on screen, polled every 10 s.
8. The price disagreement line sits in the Latest requests footer under "Prices as of", where the designer placed it, not on the Spent tile.
9. The store is `<config>/routing-dashboard/bartab/`, with launcher state in `bartab/run/`.
10. The demo mark is shown.
11. The budget is $75 to $126 for the build, with a stop and report before the next task once build spend passes $120.

### Designer review folded in

| Need | Change to the contract |
|---|---|
| Labels never rename a shown row | `label_n` is assigned once, when the ingest first sees a run, in order of first request and then run id among the runs of that agent type in the session. It is stored on `runs.label_n` (migration 0006) and never changes. The first run of a type has `label_n` 1 and shows the bare name, and the next shows "{type} 2". A file that lands late takes the next free number instead of pushing others along. This replaces the whole-session count in section 2 |
| Unpriced detail | `runs[]`, `buckets[]`, `totals` and `last_minute` each carry `unpriced {requests, models[]}`. Cost stays the sum of the priced requests, so a cell can say "at least {cost}", or "no price for {model}" when every request is unpriced and `cost` is null |
| Announcer events | The page derives start, finish, new round, session end and resume from the difference between two answers. Working to idle is never announced. Close changes are batched into one line. An unlinked run's move under its parent folds into its finish line. Returning from a hidden tab sets a new baseline. `session.states[] {at, state}` adds the session-level history (working, idle, ended), so a resume after a gap of more than 30 minutes shows as ended then working, and `session.ended_at` gives the ended time. The way out of the ended state is the Session Select, the newer-session notice, and the nothing-running state's list of running sessions |
| Unlinked runs | A foreground child's link is the dispatcher's tool result, written when the child finishes (fact V-7b16), so a finished run with no link isn't settled yet. `runs[].parent_state` is `known`, `waiting` or `unknown`. It is `waiting` while the run has no link and is not finished, or finished less than 5 minutes before T. After that it is `unknown` for good. `run_id` is the 12-hex hash of the agent id, so it stays the same across answers. The undocumented `parentAgentId` in `.meta.json` is not used |
| Header times | The header shows no "Updated" time while live. Paused uses the page's own pause time. Lost uses the `server_time` of the last good answer ("Last reached the server at"). Ended uses `session.ended_at`. The timeline's `as_of` and the footer's `as_of` are the same value, the end of the last finished ingest pass from the store's `meta`. Under a fixed, rate or test clock the fixture is fully read, so both report the clock T |
| Long sessions | No contract change. The page works out per-minute averages from `bucket_seconds`, the open bucket from `axis.end` while `session.running`, and "finished earlier" folding from `runs[].states[]` |
| Session Select | `sessions[]` items gain `state` (working or idle). The page renders the current session from `timeline.session` when it isn't in `sessions[]`. The "no sessions" command row reads the project's `display_path` from `/api/projects`, which the shell already holds, so `/api/app` doesn't change for it |
| Latest requests | The API keeps 8 and the page shows 5 |
| Links | "See why" is hidden until M4. Lane rows are not links until M3 |
| Demo mark | A shell badge driven by `/api/app` `mode` |

Allowed difference 3 in section 6 now reads: `label_n` follows first-seen order and never renames, so the old route's "scout" with one run and "scout 1" with two both read "scout" here.

## 13. Designs approved, November 9

The owner approved designer passes 1 to 3 as drawn and took every copy pick, so the UI build is unblocked. The design source is `docs/design/redesign-a/m2.js`, `m2.css`, `m2.html` and `strings-m2.js`, and components.md has an "M2 Live round" section with the designer's build decisions. The boards are the 13 `a-m2-*` PNGs in the archive's `shots/`.

Owner copy answers.
1. Costs from $1,000 up drop the cents, in "at least {cost}" and in every cost cell.
2. "Finding starter" stays.
3. "in all" stays.
4. "Last reached the server at {time}" stays.
5. `nt_switch` with no branch falls back to `hd_no_branch`.
6. `an_resumed` means only an ended session that came back.
7. "within a few seconds" stays.

Board words that name the demo project ("Tidewater reporting", `/work/tidewater-reporting`) become `{project}` and `{path}` placeholders in `en.ts`. Task 9 is the lead typing `strings-m2.js` into `en.ts`, since tech-writer already drafted it.

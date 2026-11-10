# M3 build plan, Bar Tab Review

Written by the lead (deep-reasoner) on November 9, 2026, on branch `feature/bartab-m3` from `0ff7fdf`, where M0, M1 and M2 are committed. It turns plan-a.md section 5, "M3. Review", into ordered tasks. The designer reviews sections 4 and 6 before the UI build starts. Nothing is installed, started or committed until the owner says go.

Sources are plan-a.md (sections 2, 3, 4, 5, 6 and 10), m2-build.md (sections 2 to 13), m1-build.md (sections 4, 7 and 11), standards.md, components.md (shared rules, entries 4, 13, 14, 18 to 24, 36, "Differences resolved" and the M2 Live round), the `a-summary`, `a-summary-earlier`, `a-sessions`, `a-session`, `a-agents`, `a-agent-inspector` and `a-models` boards and their source in `docs/design/redesign-a/a.js`, the M2 code in `app/`, the old `dashboard/usage.py` and the M1 oracle payloads in `app/fixtures/oracle/demo/`.

## 1. What M3 delivers

Review is the second thing the owner opens after Live. M3 builds its four pages and Session review as direction A draws them, in the canonical look the M0 sheet set, not the round 1 look on the boards.

The owner leaves Live by the sidebar, the tab bar or Live's "See all sessions" link and lands on Summary for the last 30 days. Four tiles compare the range with the one before. Cost per day shows which models did the spending, by kind of cost, and Earlier and Later page it back a month at a time while the tiles keep their range. "Where the money went" splits cost by agent, Model check says which agents didn't run as their files set over the range, and the four most expensive sessions open in Session review.

The Range Select offers Today, 7 days, 30 days, 90 days, 12 months and All. Today compares with yesterday up to the same time (owner pick O4). Sessions lists the range's sessions by day, with a running session first. Agents shows one table for usage and setup, with a group for agents that didn't run. Models shows cost, share, tokens, cache share and who used each model, then what the cost is made of.

Session review opens any session from the range. The owner drags the replay line, or uses the arrow keys, and watches the lanes from M2 fill in minute by minute, with runs not started yet shown muted. Back to now returns to the end. A running session keeps updating every 5 seconds.

Everything runs on the demo build and the `live_flow` scenarios, and on the owner's real data through the M2 preview. Totals match the old app's `/api/usage` for today, 7 and 30 days, and an independent count from a longer demo build for 90 days, 12 months and All.

## 2. Decisions this plan makes

The designer and owner can push back on any of them. Items that need an owner answer are in section 8.

| Item | Pick | Why |
|---|---|---|
| Ranges | `today`, `7d`, `30d`, `90d`, `12m`, `all`, default `30d`. Today runs from local midnight to T and compares with yesterday from midnight to the same time. `7d`, `30d` and `90d` are that many local days ending today and compare with the same number of days before. `12m` is 365 local days. `all` starts at the oldest stored request and has no prior window | Plan-a section 3 and owner pick O4. The old app has `today`, `7d` and `30d` only (`dashboard/usage.py:106`) with the same window rule (`usage.py:165`), so those three keep the old app as oracle |
| Time zone | The server's zone. On real data that is the machine's local zone. On the demo and flow builds it is the build's `session.json` `tz`. Every answer returns `tz`, and the page formats the dates it is given | The old app worked the same way, and the M1 differential already depends on it. Bar Tab is local, so the browser and the server share a zone |
| Remembering the range | The range lives in the URL (`?range=`). The last pick is kept per tab in sessionStorage and used when a Review link has no range. `prefs` stays deferred | M2 deferred `prefs` and kept the real-data server read-only outside its store. Question 4 asks the owner |
| Sums | Review numbers come from `minute_usage`, priced per cell at query time as in M1 (`usage_query.py`). Migration 0007 adds an index on `minute_usage (minute)` | The table's key starts with `session_id` (`migrations/0003_minute_usage.sql:21-24`), so a range query today scans every row. `usage_query.py` leaves out runs, sessions, hit rates and cost by kind, which M3 adds |
| Speed on long histories | Task 6 measures every Review endpoint on a generated 12-month store. A daily or hourly rollup table is built only if a target is missed | A rollup is a second copy of the numbers that the writer must keep right. Measure first, as M2 did for the eight-hour timeline |
| Freshness | Review answers carry `as_of` and an etag over the last finished ingest pass, the price table hash, the query and the local date. A matching etag gets the short `unchanged` answer. The page refetches every 60 s and on window focus. The server keeps the last 32 answers by etag | Plan-a section 3. The local date is in the etag so Today rolls over at midnight with no new request |
| Model check over a range | The same row shape and status mapping as the timeline's `model_check` (`model_check.py`), built from the range's runs per agent type, in project scope only | The old app ran its pin check for a single project only (`usage.py`, `pin_fn` docstring). One mapping means Live, Summary and Agents agree |
| Agents in M3 | The usage half. Rows for agents that ran, with Set to, Ran with, Check, Runs and Cost, plus Main session and Unnamed agent rows. The "No runs" group lists user and project agent files from the ported `collect.py`. Plugin agents, the inspector and agent names as links land with the setup half in M4. "Add an agent" stays hidden until M6 | Plan-a M3 and M4 split Agents this way. `collect.py` reads no plugin agents today (no match for "plugin" in it) |
| Session review data | The same `GET /api/sessions/{id}/timeline` answer as Live. The page picks values at T with `timeline-at.ts`. No new server parameter | M2 built the payload for this (m2-build.md section 2, "Value at T"). One answer per session means dragging the line never asks the server |
| Precision in replay | Run states, parents and rounds are exact at every minute. Tokens and cost are exact at each bucket's end. On sessions over an hour, where `bucket_seconds` is above 60, the numbers hold between bucket ends and the label says so | `timeline-at.ts` header. A server answer per minute would mean a request on every drag step and two code paths. Designer pass 9 words the label |
| Replay control | A native `<input type="range">` styled as the handle and cut line, with `step` 1 minute, an explicit `aria-valuetext` such as "6:25 PM", and Page Up and Page Down set to 5 minutes in its key handler. Home and End go to the start and to Now | React Aria Components 1.22.1 fixes the Slider's page step at a tenth of the range (`react-stately` `useSliderState.mjs:24-31`) and builds `aria-valuetext` from a number formatter (`:156`), so component 23's keys and time label don't fit it. Standards say native elements first. Task 1 found no source for the key override, so task 9b proves it in Chromium first (section 12, task 1 results) |
| Replay URL | `?at=<minute>` from the axis start, written with history replace, so a drag never fills the back stack. No `at` means the end | Plan-a's route table names `?at=<minute>`. A shared link reopens the same minute |
| A running session in review | It polls every 5 s with the etag and stops once ended. When the line is at the end it follows Now. When the owner moved it, it stays where it was put | Plan-a section 3, "Session review polls every 5 s while running" |
| Announcements in Review | Data changes are never announced. The replay control speaks its own value. The pager's window label sits in a polite live region (component 21). A range change speaks through the M0 route status | Review data moves only every 60 s and nothing on it is urgent. The M2 announcer stays a Live feature |
| Cost chart | Follows the range if the owner picks question 2 option A. Today shows 24 hours, 7 and 30 days show days, 90 days shows 13 weeks, 12 months and All show months. Earlier and Later move by one window and never change the tiles | The board was drawn for 30 days only. A 30-day chart under "Last 12 months" answers the wrong question. Pass 8 draws the units |
| Sessions page | 50 sessions per page, newest first, grouped by local day, with an opaque cursor. Running sessions sort first inside Today | Plan-a section 3. 53 sessions sit in the demo's 30 days for one project, so paging is tested on real numbers |
| Cost labels | Every Review cost card says it is an API-rate estimate with "Prices as of {date}". The price disagreement line from M2 also shows under Cost per day | Plan-a section 3, Prices. Pass 7 places it |
| Live in M3 | "See all sessions" in Live's Session Select opens Sessions. Live lane rows stay plain unless the owner picks question 3 option B | M2 left both for M3 (m2-build.md section 12, "Links") |
| Fixture mode | The M0 fixture provider answers `unknown_project` on every Review route, as it does for the timeline. Review end-to-end tests run on the demo build and the flow scenarios | The fixture scenarios have no usage rows (`fixture_provider.py:265-274`) |
| Wide-range oracle | A long demo build made in process by the recorder, with `build_demo.HISTORY_DAYS` set to 400 and `_truth` wrapped to keep the generator's own request list. `tests/` is never edited | Plan-a M3 asks for `truth.json` from a longer build. The builder has no flag for its 62 days (`tests/fixtures/demo/build_demo.py:48-49`), and the old reader stops at 61 days (`dashboard/transcripts.py:444`), so the old app can't serve as oracle past 30 days anyway |

## 3. Ordered tasks

Tiers follow the owner's routing rules. fast-worker runs at medium unless the row says high. Every brief starts with `Kind: rebuild-m3` and carries the HiveMind line from `hivemind_lib.py related <paths>`, the date rule (`date -Iseconds` only) and these limits. Work only in `/Volumes/Warehouse/Projects/claude-code-model-routing-bartab`. Never read anything under `~/.claude`, real transcripts, real settings or `~/.claude.json`. Never pass `--real` to anything. Servers only on ports 47000 to 47999, never 8377. Never print, guess or ask for a key. Use `app/scripts/uvw` and `app/scripts/npmw` for every uv and npm call, and download nothing. Never edit `dashboard/`, `tests/`, `plugins/`, `tools/`, `hooks/`, `agents/`, `rules/`, `skills/` or `install.py`.

HiveMind ids for briefs: T-7629, T-5589, T-c826, T-3ad1, D-c684, D-2e12, V-1c9f, W-734f, Q-0ec1, L-979a, I-14ae, D-3ca7, plus whatever `related` returns per task.

| # | Task | Files | Tier | Check | Cost |
|---|---|---|---|---|---|
| 0 | Pre-flight. Time, branch, clean tree. Write the five Review answer models and the `Range` type in `models.py`, so the contract in section 4 is fixed before workers start. Add a session fixture in `conftest.py` that builds the long demo once per worker into a temp folder outside every repo (T-c826) | `app/server/models.py`, `app/server/tests/conftest.py` | Lead | The models import and the OpenAPI export runs. The fixture builds and its time is recorded | In the lead row |
| 1 | Lookups. Claude Code's `cleanupPeriodDays` default and what it deletes (code.claude.com settings), for the history line on wide ranges. The native range input's Page Up, Page Down, Home and End steps in the pinned Playwright Chromium and WebKit, and whether the accessibility tree exposes its `aria-valuetext` in both engines. For each Review card, the old `/api/usage` field and its path:line in `dashboard/usage.py` (hit rate, share, deltas, ran-with ties, session agents order, Main runs). The long build's time and size with `HISTORY_DAYS` 400, run in the scratchpad. `EXPLAIN QUERY PLAN` for a 30-day window on the demo store. Fixtures and docs only | None. A table of fact, value and path:line or URL | scout | Every row has a source | $1 to $3 |
| 2 | Wide-range recorder. `app/oracle/record.py --long` builds the long demo in process (section 5), captures the generator's request list, and writes per-project totals for `90d`, `12m` and `all` and their prior windows, plus sums per model, per agent type (from each run's `.meta.json` `agentType`) and per local day. The manifest names the old commit sha, the build arguments and the patched constants | `app/oracle/record.py`, `app/fixtures/oracle/demo-long/truth-long.json`, `manifest.json` | fast-worker | Two runs give the same bytes. The `30d` totals from the same code equal the standard build's `truth.json` logic on that build | $4 to $7 |
| 3 | Review query core (high). Windows for the six ranges in a zone, with prior windows and DST days. Sums with cost by kind, hit rate, runs and sessions. Per agent (most-used model and effort pair, ties to the first seen), per model (agents that used it, share), per session (agents, runs, tokens, cost, state) and chart bars per unit with the pager window. Migration 0007 for the `minute` index. Differential tests against the M1 payloads and the long truth (section 5) | `app/server/{review_windows,review_query}.py`, `app/server/migrations/0007_minute_index.sql`, `app/server/tests/test_review_query.py`, `test_differential_review.py` | fast-worker high | Section 5 passes outside the allowed list. pyright strict, coverage 85 percent | $12 to $20 |
| 4 | Agents and Model check over a range. `agents_review.py` builds ran rows with Set to from the resolver entries, the source scope, and the status from `model_check.py` over the range's runs. The "No runs" group comes from user and project agent files through `collect.py`. Main session and Unnamed agent rows | `app/server/agents_review.py`, tests | fast-worker | The Check column equals the old `by_agent[].pin` through M2's status mapping for `30d` in every demo project. An agent file with no runs lands in "No runs" | $6 to $10 |
| 5 | Review API. `GET /api/summary`, `/api/cost-chart`, `/api/sessions`, `/api/agents` and `/api/models` with range validation, the etag and the short `unchanged` answer, the answer cache, gzip and the error envelope. Provider methods in `store_provider.py`, `unknown_project` in `fixture_provider.py`. Then the OpenAPI export and `schema.d.ts` | `app/server/{api_review,provider,store_provider,fixture_provider,main}.py`, `app/web/src/api/openapi.json`, `schema.d.ts`, tests | fast-worker | TestClient on the demo build for every range. `cwd` never appears in any answer. OpenAPI staleness test passes | $6 to $10 |
| 6 | Range speed. A generated store with 12 months at a heavy rate (section 7). Measure each endpoint at `30d`, `12m` and `all` | `app/server/tests/test_review_size.py` | fast-worker | 95th percentile under 250 ms per endpoint and range. The numbers go in the results. A miss adds a rollup dispatch (high) and asks the owner first | $4 to $7 |
| 7 | Designer passes 7 to 9, then the designer's review of this plan at medium (dispatched by the main session, not this lead). Section 6 says what each pass covers | Boards in the archive, notes in components.md | designer | The owner picks before tasks 9b and 11 to 13 | $17 to $34 |
| 8 | String deck. Every Review word on the pass 7 to 9 boards, plus the range names and windows, Today's comparison, the pager reasons, empty, loading and error lines, the replay value and precision label, the API-rate line on each card, and the "records start on" line. Waits for task 7 | Draft as a key table, typed into `app/web/src/strings/en.ts` by the lead | tech-writer | String lint passes. Owner reads the deck | $3 to $6 |
| 9a | Wave 3 components, first half. Share bar (19), pager (21), segmented pages (13), stacked bars with kind patterns (20), scope bar (4) with the Range Select, each with every state on the component sheet. Can start before task 7 and takes the pass 7 changes in the fix round | `app/web/src/components/*`, `app/web/src/sheet/*`, tests | fast-worker | Vitest. The sheet test fails on any manifest state without a render. Axe on the sheet at 375 and 1440, light and dark | $8 to $12 |
| 9b | Wave 3 components, second half. Replay line (23) over the M2 lane, as section 2 decides. Waits for pass 9 | `app/web/src/components/ReplayLine/*`, `TimelineLane` changes, sheet, tests | fast-worker | Vitest for every key. Sheet states at rest, hover, focus and dragging | $4 to $8 |
| 10 | Review data layer. Query hooks for the five routes with the range from the URL, the etag, 60 s refetch and refetch on focus. `range.ts` for presets, the tab memory and links. `replay.ts` for the line's state, the `at` param with history replace, and following Now | `app/web/src/api/review.ts`, `app/web/src/lib/{range,replay}.ts`, tests | fast-worker | Vitest with fake timers and a mocked fetch | $5 to $8 |
| 11 | Summary and Sessions pages, every state in section 6, the phone segmented pages and the routes | `app/web/src/pages/review/{SummaryPage,SessionsPage}.tsx`, CSS, `app/web/src/app/router.tsx`, tests, `app/web/e2e/review.spec.ts` | fast-worker | Vitest, tsc, ESLint, Stylelint, Prettier. Playwright with axe at 320, 375 and 1440, light and dark, forced colours and reduced motion | $10 to $16 |
| 12 | Agents and Models pages | `app/web/src/pages/review/{AgentsPage,ModelsPage}.tsx`, CSS, tests, `review.spec.ts` | fast-worker | As task 11 | $7 to $12 |
| 13 | Session review (high). Scope bar with back link, Session Select and Open in Live, the four tiles, "Who worked when" with the replay line, Back to now, a running session, a gone session. Live's "See all sessions" link | `app/web/src/pages/review/SessionReviewPage.tsx`, CSS, `app/web/src/pages/live/SessionSelect.tsx`, tests, `app/web/e2e/replay.spec.ts` | fast-worker high | Vitest. Playwright with axe as task 11, on `busy`, `many`, `unlinked` and `empty` after they end, and on `busy` while it runs | $10 to $16 |
| 14 | Review end to end. The keyboard walkthroughs, the replay keys, pager ends, chart text alternatives, the accessibility snapshots, and the browser replay check in section 7 | `app/web/e2e/{review-keyboard,replay-oracle}.spec.ts` | fast-worker | All pass three runs in a row | $8 to $12 |
| 15 | Exit runs. T2 suite, the full Playwright and axe matrix, then the old suite alone with its log named for `feature-bartab-m3` (T-7629), then the protected-path diff | Logs in the scratchpad | scout | All green. The diff is empty | $2 to $3 |
| 16 | Browser check in Chrome under the tab-group rules. The five pages at 1440 and 375, light and dark, against the pass 7 to 9 boards | None. Returns a difference list | judge | Differences fixed in one batch, or listed for the owner | $4 to $7 |
| 17 | One fix round from tasks 15 and 16, a second only for Linux CI failures, consolidation and the report. The main session dispatches the verifier | None | Lead and fast-worker | Report written | $8 to $15 |
| 18 | Removed. VoiceOver runs once, at M9 (owner answer 5). Task 14's accessibility snapshots and the forced-colors runs in tasks 11 to 13 cover M3 | | | | |

The lead's own share (task 0, every review, typing `en.ts`, the fix round's brief, consolidation and the report) is $25 to $40.

Order and parallel work. Task 0 runs first. Then 1, 2, 4 and 9a run in parallel, because they touch separate files. Task 3 starts when 1 lands and runs its long-range tests once 2 is in. Task 5 needs 3 and 4. Task 6 needs 5. Task 7 runs beside all of that, since it is the main session's dispatch. Task 8 waits for 7. Task 9b waits for pass 9. Task 10 needs 5. Tasks 11 and 12 need 8, 9a and 10, and can run together because they touch separate pages (the lead merges `router.tsx` and `review.spec.ts`). Task 13 needs 8, 9b and 10. Task 14 needs 11 to 13. Then 15, 16 and 17. Only the lead edits `conftest.py`, `pyproject.toml`, `models.py` and `en.ts`, so parallel workers never collide there. M3 adds no package, so neither lockfile changes.

## 4. API contract

The Pydantic models in `app/server/models.py` (the "Review (M3)" block) are the contract. Section 12 changes several fields below after the designer's plan review, and it wins where they differ.

All times are ISO strings in UTC, and dates are local dates in the answer's `tz`. Every Review route takes `project` (required), `range` (default `30d`) and `etag`. Every answer carries `project`, `range`, `window`, `server_time`, `as_of`, `etag`, `unchanged` and `prices`. A request whose `etag` matches gets `{project, server_time, etag, unchanged: true}` and nothing else. Errors use the one envelope `{code, path}`. They are `bad_request` (400, a missing or repeated parameter, or an unknown range) and `unknown_project` (404). Model ids are catalog ids. Agent keys are `@main`, `@unnamed` or the agent type. The page owns every word.

### Shared fields

| Field | Type | Contents |
|---|---|---|
| `window` | object | `start`, `end` (T), `prior_start`, `prior_end` (both null for `all`), `tz`, `oldest` (the oldest stored request in this project, or null) |
| `prices` | object | `as_of`, `source`, `cross_check_state`, as on the timeline |
| `unpriced` | object | `{requests, models[]}` wherever a cost appears, as M2's designer review set it. Cost stays the sum of the priced requests |

### `GET /api/summary?project=<key>&range=<r>`

| Field | Type | Contents |
|---|---|---|
| `tiles` | object | `cost`, `sessions`, `tokens`, `cache_share`. Each is `{value, prior, change_pct, change_abs}` (`models.py` `CountTile`, `CostTile`, `ShareTile`). `change_pct` is relative and null when the prior is null or zero. `change_abs` is the difference, in share units for cache share, which has no `change_pct`. The cost tile also carries `unpriced` |
| `money[]` | list | Cost by agent. `agent`, `model` (its most-used model), `cost`, `share`, `unpriced`. Biggest first |
| `model_check` | object | `rows[]` and `in_effect_count`, the timeline's shape over the range |
| `top_sessions[]` | list | The four most expensive sessions, in the `/api/sessions` row shape |
| `session_count` | int | Sessions with a request in the range |
| `no_usage_sessions` | int | Sessions in the range with no usage rows, for the M1 notice |

### `GET /api/cost-chart?project=<key>&range=<r>&end=<date>`

`end` is the last local date of the chart window and defaults to the range's end. Earlier and Later move it by one window. The tiles never read this route.

| Field | Type | Contents |
|---|---|---|
| `chart` | object | `start`, `end`, `unit` (hour, day, week, month), `has_earlier`, `has_later`, `reason_code` (null, `no_earlier_data` with `oldest`, or `newest`) |
| `bars[]` | list | `start`, `by_model {model: {cost, kinds {input, output, cache_read, cache_write}}}`, `unpriced` |
| `legend[]` | list | `model`, `cost` over the chart window, in catalog order |
| `kinds` | object | Dollar totals for `input`, `output`, `cache_read`, `cache_write` over the window, for the kinds line |
| `y_ticks[]` | list | Dollar ticks, 1, 2 or 5 times a power of ten |

With question 2 option B the route keeps plan-a's shape, `unit` is always `day` and the window is always 30 days.

### `GET /api/sessions?project=<key>&range=<r>&cursor=<c>`

| Field | Type | Contents |
|---|---|---|
| `count` | int | Sessions in the range |
| `days[]` | list | `day` (a local date), `sessions[]`. Each session has `id`, `started`, `last_request`, `branch` (or null), `state` (working, idle, ended), `agents[]` (agent keys by cost), `runs`, `tokens`, `cost`, `unpriced` |
| `next` | string or null | Opaque cursor for the next 50 |

The scope bar's Session Select in Session review reads the same route with the page's range.

### `GET /api/agents?project=<key>&range=<r>`

| Field | Type | Contents |
|---|---|---|
| `ran[]` | list | `agent`, `scope` (user, project, main, unnamed, or `no_file` for a type that ran with no user or project file), `set {model, effort}` each `{value, file, line, scope}` or null, `ran {model, effort, mixed}`, `status` (one of the seven words, or null when nothing is set), `reason_code`, `params`, `runs`, `sessions`, `cost`, `share`, `unpriced`. Biggest cost first |
| `never_ran[]` | list | `agent`, `scope`, `set`, from user and project agent files with no run in the range |

### `GET /api/models?project=<key>&range=<r>`

| Field | Type | Contents |
|---|---|---|
| `rows[]` | list | `model`, `cost`, `share`, `tokens`, `cache_share`, `used_by[]` (agent keys), `unpriced`. Biggest cost first |
| `kinds[]` | list | `model` and dollars for `input`, `output`, `cache_read`, `cache_write` |
| `legend` | object | Dollar totals per kind |

### Session review

`GET /api/sessions/{id}/timeline` is unchanged from M2. An ended session's answer never changes, so after the first answer every poll is `unchanged`, and polling stops once `session.state` is `ended`.

## 5. Differential tests against the old app

Fixtures only. No test reads real data, starts the old server or opens a port for it.

### Oracles

| Oracle | Fixture | How it runs | Compares |
|---|---|---|---|
| Old `api_usage.usage` for `today`, `7d` and `30d` | The demo build at `2026-10-30T18:00` America/New_York | The 18 payloads M1 recorded in `app/fixtures/oracle/demo/` (old commit `e9ff175`). They hold the whole view, so M3 needs no new old-app recording | Totals, prior totals and deltas, cost by kind, hit rate, runs and sessions, `by_agent` (cost, share, runs, ran with, pin), `by_model` (cost, share, tokens, hit rate, agents), buckets per hour (today) and per day, and the session list with its agents, runs, tokens and cost |
| `truth.json` | The same build | Read as in M1 | `30d` totals per project, so a bug shared by old and new still fails |
| `truth-long.json` | The long build from task 2 | The recorder calls `build_demo.build` in process with `HISTORY_DAYS` 400, wraps `_truth` to keep the request list, and sums it with its own code for each window | `90d`, `12m` and `all` totals and prior totals per project, and sums per model, per agent type and per local day |
| Old `api_live.live` at T | The M2 recordings for `busy`, `many`, `unlinked` and `empty` | Reused as recorded | Session review values at T in the browser (section 7) |

Money agrees within 1e-6, and every token and count agrees exactly, as in M1. The store is priced with `prices-old.json`, so a price change never reads as a regression. The long build is cached per worker. If task 1 finds it takes over 30 s, the long tests move behind a `slow` marker that runs in T2 and at exit, never skipped.

### Allowed differences to start with

1. Model names are ids. The old `display_name`, `cat` and `share_lt1` are page concerns and are not compared.
2. `thinking` is 0 where the old answer says null (M1, `usage_query.py` docstring).
3. Shares are compared as fractions to 1e-9. The page rounds them.
4. The old pin answer maps through M2's status mapping (`model_check.py` docstring) before it is compared. Where the docstring says "NO CLEAN MAPPING" the entry names the reason.
5. The old session list counts every session with a request in the window. The new one also carries `state` and `last_request`, which have no oracle and are tested on crafted stores.
6. `90d`, `12m` and `all` have no old answer. Their only oracle is `truth-long.json`.
7. The old `by_effort`, `recent_runs`, `runs_per_day` and axis ticks have no Review card in direction A and are not compared.

Any other difference fails. Each entry names its reason and plan section in the JSON, as in M1.

## 6. Designer passes and UI state

### What exists and what doesn't

| Screen | Boards today | State |
|---|---|---|
| Summary | `a-summary`, `a-summary-earlier` at both widths and themes | Drawn for 30 days in the round 1 look. No Today, no wide range, no empty, loading or error state, no API-rate line |
| Sessions | `a-sessions` | Drawn. No paging, no empty range |
| Session review | `a-session` | Drawn on the pre-M2 lane at minute 15 of a 30-minute session. None of M2's fold, unlinked, unpriced, long-session or 375 lane rules, no running session, no gone session |
| Agents | `a-agents`, `a-agent-inspector` | Drawn with a plugin agent in "No runs" and names as links, which are M4 here. The inspector is M4 |
| Models | `a-models` | Drawn. Model names show as links with nowhere to go |
| Range Select with Today | None | Component 14 is on the sheet, but no open Range Select with six presets is drawn |
| Scope bar, segmented pages, pager, share bar, kind patterns, replay line | On the round 1 boards and the sheet | Need the canonical look from "Differences resolved" (items 1, 5 and 9) |

The boards are good enough for the server work and task 9a, but not for the pages. Three passes are needed, as M2 needed passes 1 to 3. The main session dispatches them, and they run beside tasks 0 to 6.

### Pass 7, Review pages in the canonical look

- Summary, Sessions, Agents and Models redrawn on the M0 to M2 components at 1440 and 375, light and dark.
- The Range Select open, with Today, 7 days, 30 days, 90 days, 12 months and All, and the scope bar sub for each.
- Today's tile comparison with yesterday up to the same time, and All with no comparison.
- A range longer than the stored history, with the "records start on {date}" line. On real data the store holds only the transcripts that still existed at first ingest (task 1 checks Claude Code's cleanup period).
- An empty range, and loading and error states for each card (component 24 and 37).
- Unpriced cells, the API-rate line and "Prices as of" on each cost card, and the price disagreement line.
- Sessions paging (50 a page) and the running row.
- Agents without the inspector. Names plain until M4, Main session and Unnamed agent rows, a mixed Ran with, an agent with no file, and no plugin rows until M4.
- Models with plain model names, and the kinds section at 375.

### Pass 8, the cost chart per range

Only with question 2 option A. Units and x labels for 24 hours, 7 days, 30 days, 13 weeks and 12 months. Bar density at 375. What the pager moves by and its window label. The kind patterns on cost per day, with the legend totals and kinds line the `--rk` exception relies on (project CLAUDE.md, Accessibility floor). With option B this pass shrinks to the kind patterns and the pager ends and folds into pass 7.

### Pass 9, Session review on the M2 lane

- The replay line over M2's lane at 1440 and 375, with the handle, its 24 px target, focus and dragging.
- Lanes at T. The fold rule, unlinked badges and "Not started yet" rows at an early minute.
- A long session where numbers hold between bucket ends, and how the label says so.
- Whether the tiles show the whole session, as `a-session` draws ("Whole session so far"), or the values at the line.
- A running session in review, with the line at Now and after it was moved.
- The scope bar's Session Select, Open in Live only while running, and a gone session.
- Lane rows as links if the owner picks question 3 option B.

### Page states

| State | When | Data |
|---|---|---|
| First load | No answer yet | Skeleton bones per card, `aria-busy` and one screen-reader line |
| Range with data | The usual case | As section 4 |
| Empty range | `session_count` 0 | `window.oldest` says whether anything is stored at all |
| History shorter than the range | `window.oldest` after `window.start` | The "records start on" line, and tiles with a null prior |
| Card error | One route fails | A raised error row on that card. The others stay |
| Lost | Every route fails | The M0 server-stopped gate |
| Updates stopped | `history.pass_error` | The M1 notice line on every page |
| Demo data | `mode` is not real | The M2 shell badge |
| Session gone | `unknown_session` on the timeline | A sentence and a link back to Sessions |
| Session running | `session.running` | "This session is still running", Open in Live, 5 s polling |

### Events the pages handle

| Event | What happens |
|---|---|
| Range change | The URL changes, every card refetches, focus stays on the Select, the route status speaks the new range |
| Earlier or Later | Only the chart refetches. The window label speaks politely. At an end the button is `aria-disabled` with the reason tied by `aria-describedby` |
| A refetch with new data | Values change in place, never announced |
| Replay key or drag | The lanes, chart fade and tiles move to T. The control speaks its time. The URL's `at` is replaced |
| Back to now | The line goes to the end and follows Now while running |
| The reviewed session ends | Polling stops. The sub drops "still running" and Open in Live goes |
| Row link | A session row opens Session review with the range kept for the back link |

## 7. Tests and exit

### New suites

| Area | Tests |
|---|---|
| Windows | Every range at a fixed T, Today against yesterday up to the same time, DST start and end days in America/New_York, a range longer than the history, and `all` with no prior |
| Differential | Section 5, for every demo project and every range, plus the long build |
| Agents | Set to, Ran with, Check and the "No runs" group on the demo, and the Check column against the old pin |
| API | Each route on the demo for every range. Etag and `unchanged`. `bad_request` on an unknown range or a repeated parameter. No answer carries `cwd`, message text or a description. The schema text-column test from M1 still passes |
| Range speed | A generated store with 12 months of 6 sessions a day, 10 runs each and 90 minutes per run. Each endpoint under 250 ms at the 95th percentile at `30d`, `12m` and `all` |
| Replay keys | Vitest and Playwright on component 23. Left and Right move one minute, Page Up and Page Down five, Home and End go to the start and to Now. `aria-valuetext` reads the time. The URL's `at` follows with replace |
| Replay values | Playwright on the ended `busy` flow at five recorded minutes. Lane states, rounds, tokens and cost on screen equal the recorded old `/api/live` at that T, outside M2's allowed list |
| Pager | Earlier until `no_earlier_data` and Later until `newest`. Each end shows its reason and stays focusable. The tiles never change while paging |
| Chart text | Every chart has a `role="img"` label, and its legend totals and kinds line hold the same numbers as the bars |
| Exact accessible text | Playwright asserts the exact accessible name or text, from the typed strings, of each chart's `role="img"` label (the Session review chart's label at two values of T), the replay control's `aria-valuetext` and its settled summary line, each pager end's `aria-describedby` reason, the Range Select's name and value, and the route status line after a range change. Required by the designer's review because VoiceOver waits for M9 |
| Keyboard walkthroughs | Playwright with the keyboard only, at 375 and 1440. "Read the 30-day cost by agent" goes from Live to Summary's "Where the money went" and on to Agents. "Replay a past session" goes from Sessions to Session review, moves the line by keys and returns with Back to now. Each step asserts focus and the visible text |
| Web | Vitest for every component state, the hooks and the range and replay helpers. Playwright with axe on the five routes at 320, 375 and 1440, light and dark, forced colours and reduced motion, on the demo build and the flow scenarios |

Run Playwright from `app/web` with its config, `../scripts/npmw exec playwright -- test -c playwright.config.ts`, as in M2.

### Accessibility snapshots instead of VoiceOver

VoiceOver runs once, at M9 (owner answer 5). In M3, task 14 takes Playwright accessibility snapshots (`toMatchAriaSnapshot`) of the Range Select open, the Summary tiles, Cost per day's label and legend, a pager end, the Agents table, the replay control at two minutes, and Back to now. They gate like any test. The M9 script reuses this list.

### Kept green

- The M0, M1 and M2 exit runs, with pytest, Vitest and Playwright counts in the report.
- Standards checks. ruff, ruff format, pyright strict, coverage at 85 percent on `app/server`, tsc, ESLint, Stylelint and Prettier.
- The old suite alone, `/usr/bin/python3 -m unittest discover -s tests` from the worktree root, log named for `feature-bartab-m3` (T-7629). Expected 3575 tests and 88 skipped.
- `git diff --stat 0ff7fdf -- dashboard tests plugins tools hooks agents rules skills install.py` stays empty.

### Exit, from plan-a M3

- Totals match per agent, model and day against the old `/api/usage` for today, 7 and 30 days, and against the long build's truth for 90 days, 12 months and All, outside the allowed list.
- The replay keys, pager ends and chart text alternatives pass.
- The keyboard-only walkthroughs "read the 30-day cost by agent" and "replay a past session" pass at 375 and 1440.
- Axe, the Playwright accessibility snapshots and the forced-colors checks pass on every Review route. VoiceOver waits for M9.

## 8. Owner questions

Each has my pick first.

1. Designer passes 7 to 9. The Review boards predate the canonical look and the M2 lane, and Today, wide ranges and the replay rules on the M2 lane have no boards.
   - A (my pick). The main session dispatches them now. Tasks 0 to 6 and 9a run beside them, so no time is lost.
   - B. Build from the current boards and fix after a later pass. The pages and the replay line get built twice.
2. The cost chart and the range. Plan-a drew a 30-day chart that pages by 30 days whatever the range.
   - A (my pick). The chart follows the range. 24 hours for Today, days for 7 and 30 days, weeks for 90 days, months for 12 months and All. Needs pass 8 and adds about $4 to $8 to tasks 3 and 11.
   - B. Keep plan-a's 30-day chart with its pager for every range.
3. Lane rows and a run view. Component 22 makes each lane row a link "to the run", but no run view is drawn or in plan-a's release 1 table.
   - A (my pick). No run view in release 1. Lane rows stay plain on Live and Session review.
   - B. A row opens Session review with that run picked and its own requests listed under the lanes. Adds a route field, pass 9 work and about $12 to $20.
4. Remembering the range. Plan-a puts the last range in server preferences, and M2 deferred that table.
   - A (my pick). The range lives in the URL, and each tab keeps its last pick. A new tab starts on 30 days.
   - B. A server `prefs` table and the first write route on the real-data server.
5. The first VoiceOver pass. Plan-a says owner or designer, but an agent can't hear VoiceOver.
   - A (my pick). You run the 15-minute script in section 7 at the end of M3.
   - B. Move the first pass to M6 and rely on Playwright's accessibility snapshots until then.
6. Budget (section 9). It sits well above plan-a's $50 to $90, because M2 ran about twice its plan and M3 has five screens and three designer passes.
   - A (my pick). The full build with questions 2 and 3 as picked, $127 to $212 for the lead's build, with a stop and report before the next task once build spend passes $200.
   - B. The trimmed build, $109 to $185, with a stop at $175.

### Owner answers, November 9

This list overrides anything above that disagrees with it.

1. A. The main session dispatches designer passes 7, 8 and 9 now, plus the designer's plan review at medium. Tasks 0 to 6 and 9a run beside them. Every task that depends on the boards (8, 9b, 10 to 14 and the pass 7 changes to 9a) waits for the owner's design pick and the plan-review notes.
2. A. The cost chart follows the range, and pass 8 is in.
3. A. No run view in release 1. Lane rows stay plain on Live and Session review.
4. A. The range lives in the URL, and each tab keeps its last pick.
5. Changed by the owner. One VoiceOver pass for the whole product, at M9 only. The M3 and M6 passes are removed here and in plan-a.md. Every milestone keeps axe, keyboard walkthroughs at 375 and 1440, Playwright accessibility snapshots and the forced-colors checks. Task 18 is removed.
6. A. The full build, $127 to $212 for the lead's build. The lead stops and reports before the next task once build spend passes $200.

## 9. Cost estimate

List-price ranges. M2 was planned at $75 to $126 for its build and came in around $155 to $190 in all, about 1.5 to 2 times its plan and more than twice plan-a's $40 to $70. Each row here starts from M2's per-dispatch shape and carries that calibration. I have no per-run cost from the dashboard in this tree. [NEEDS CONFIRMATION: dashboard cost per run for each agent.]

| Dispatch | Count | Estimate |
|---|---|---|
| This plan step, lead | 1 | $8 to $12 |
| Lead build, reviews, string typing, fix briefs and consolidation, deep-reasoner on Opus at high | 1 | $25 to $40 |
| fast-worker at high, tasks 3 and 13 | 2 | $22 to $36 |
| fast-worker at medium, tasks 2, 4, 5, 6, 9a, 9b, 10, 11, 12, 14 and the fix round | 11 | $70 to $117 |
| scout, tasks 1 and 15 | 2 | $3 to $6 |
| judge, task 16 in Chrome | 1 | $4 to $7 |
| tech-writer at medium, task 8 | 1 | $3 to $6 |
| Build only, after this plan step | | $127 to $212 |
| Designer passes 7 to 9 and the plan review at medium (main session) | 4 | $17 to $34 |
| Verifier on Opus (main session) | 1 | $5 to $10 |
| Total for M3 | | $157 to $268 |
| Contingency, a rollup table if task 6 misses (fast-worker high) | 1 | $8 to $12 |

The trimmed build saves about $18 to $27. It takes question 2 option B (no pass 8, smaller task 3 and 11), merges tasks 11 and 12 into one dispatch, and folds task 14's walkthroughs into tasks 11 and 13. That gives $109 to $185.

What drives the cost.
- Five screens and six new components, against M2's one screen. Tasks 9 to 14 are about half the build.
- The axe and Playwright matrix. Five routes at three widths, two themes, forced colours and reduced motion, on two data sets. Every UI dispatch runs it, and every fix round runs it again.
- The lead. Reviewing eleven worker diffs and typing the deck costs more than M2's seven.

Where it could overrun.
1. Late or changed boards. If the pages start before passes 7 and 9 are picked, they are built twice. Question 1 holds that line.
2. Linux CI. M2 needed two fix commits after its build for tests that passed on macOS (`2318a2a`, `0ff7fdf`). Timing-sensitive replay and pager tests are the likely repeats. The second fix round in task 17 is priced for it.
3. The differential. Comparing the old view's prior windows, deltas, cost by kind, pin and session lists for the first time can surface old quirks that each need an allowed-difference entry and a reason. Task 3 at high carries this.
4. Range speed. A missed target in task 6 adds the rollup contingency and a migration that the writer must keep in step.
5. Question 3 option B adds $12 to $20 and a third of pass 9.

Stop line. The lead stops and reports before starting the next task once build spend passes $200 on the full plan, or $175 on the trimmed plan.

## 10. Risks and leftovers from M2

### Leftovers M3 depends on

1. The Review routes exist as placeholders in `app/web/src/app/router.tsx:100-106`, and the nav already lists them.
2. `timeline-at.ts` picks values at any T from one answer, and M2's Vitest oracle checks it at every recorded minute. Session review builds on it.
3. Lane rows were left non-links "until M3" (m2-build.md section 12). Question 3 settles what that means.
4. Live's "See all sessions" link in the Session Select has no target yet. Task 13 points it at Sessions.
5. `prefs` is deferred a third time (question 4).
6. `usage_query.py` covers totals, agents, models and days only. Runs, sessions, hit rates and cost by kind are new in task 3.
7. The resolver read side and pin check came forward to M2, so Agents can show Set to and Check in M3 without M4's collectors.

### Risks

1. Old quirks in the differential. Prior windows, deltas and the pin carry the old app's rules for the first time. The allowed list with reasons is the guard, and task 3 runs at high.
2. Replay precision. Numbers on sessions over an hour hold between bucket ends. Pass 9 words it, and the browser replay check runs only on minute buckets, where it is exact.
3. Wide ranges on real data. Claude Code removes old transcripts on its own schedule, so 12 months and All show only what the store has kept since the owner's first real start in M2. The "records start on" line says so.
4. The long build's size. 400 days is about six times the demo. Task 1 measures it before tasks 2 and 3 depend on it.
5. Query speed on a year of history. Task 6 measures it, and the rollup is the fallback.
6. The native range input. Its look differs by engine, so the handle is drawn by CSS on top of a transparent input. Forced colours need their own check.
7. Two leads. M3 runs in its own worktree. The designer passes are drawing only and touch no file in `app/`.
8. Budget. Section 9's honest range sits far above plan-a's. The stop line holds it.

## 11. Designer review focus

The designer's review of this plan should look at these, against the picked direction.

- Section 4's fields. Whether every card and state in section 6 has the data it needs.
- The range presets, Today's comparison and the "records start on" line.
- The cost chart units (question 2) and the kinds line the `--rk` exception relies on.
- Replay precision on long sessions, and tiles at the line or for the whole session.
- The native range input as the replay control, and its focus ring at 375.
- Agents without plugin rows, names as plain text until M4, and "Add an agent" hidden until M6.
- Announcements. Range changes through the route status, the pager label polite, and no data announcements.

## 12. Designer plan review folded in, November 9

The designer reviewed this plan at medium and reported 16 UX needs. This section overrides anything above that disagrees with it. The contract changes are already in `app/server/models.py`. Items marked pending wait for an owner answer the main session will send.

### Changes to the answers

| Need | Change |
|---|---|
| 1. VoiceOver only at M9 | Task 18 and its exit line are removed (owner answer 5). Section 7 gains the "Exact accessible text" row |
| 2. Unpriced costs | Every cost that can miss requests carries an `Unpriced` beside it. That covers `tiles.cost` (`unpriced`, `prior_unpriced`), each `legend[]` entry, each bar's model part, the chart answer's `unpriced` (for the kinds line), each `kinds[]` row on Models and the Models answer's `unpriced` (for its legend). A model with no price keeps its legend entry and its Models row, with `cost` null, `share` null, and its `tokens` and `requests`. A share is null whenever its own cost is null, never 0 |
| 3. Partial prior | `window.prior_partial` is true when `oldest` falls after `prior_start`, and `window.partial` when it falls after `start`. With `prior_partial`, `change_pct` and `change_abs` are null on every tile, so no false "Up 300%" can show. `prior` stays, so the page can still say what the partial prior was |
| 4. Cost chart window | On the newest page the chart window is the range's window, so the legend total equals the Cost tile, with the first bucket clipped to the window start (13 weeks for 90 days has a short first week). Bars carry `end` as well as `start`, both clipped to the window and to T, plus `open` (holds T), `holds_oldest` and `no_records` (ends before `oldest`, shown as no records, not $0). Earlier pages are whole windows of the same length, ending where the newer page starts. `chart` has `earlier_reason`, `later_reason` and `newest`. All is one page from `oldest` to T, in days, weeks or months by span (section 13), with both pager ends reached (`no_earlier_data` and `newest`). The chart end is not in the URL, and a range change resets it to newest |
| 5. Card errors | Every answer carries `errors[] {card, code}`. Sums come from one SQLite read and fail together as a route error. The setup reads (agent files and settings, for Model check and Set to) can fail alone. Then `summary.model_check` is null with an error for `model_check`, and on Agents each `set` is null with `set_reason` `read_failed` and an error for `agent_setup`. Tiles, money and rows stay |
| 6. Sessions across the range start | Rows carry `started_before_range` and `whole {tokens, cost, unpriced}`. `tokens`, `cost` and `runs` count the range only. A session sits under the local day of its first request inside the range, so a straddling session sits under the range's first day. Pending, in-range or whole cost on the row. Both are in the answer, so the answer is a page switch |
| 7. Sessions paging | The sort is newest first by (first request in range, id). `next` anchors on the last row's sort key, not an offset, so a refetch of loaded pages never moves or repeats rows. New sessions arrive only at the top. The page keys rows by id and joins a day split across pages under one header. The end is `next` null with `count`, for "That's all {count} sessions". Pending, Show more or numbered pages. The cursor serves Show more. Numbered pages would add a `page` parameter |
| 8. Session review Select | No server change. The page shows the current session from `timeline.session` as the value even when it is outside the first 50, and links to Sessions when `next` is not null |
| 9. Mixed runs | `AgentRow.ran_pairs[] {model, effort, runs}`, most runs first, beside the M2 `ran`. `runs_as_set` and `runs_not_as_set` come from the model check, null when nothing is set. Summary's `model_check` rows keep M2's `runs` and `mismatched_runs`, which give the same split. M2's `RanPair` is not changed, so Live's contract stays as it is |
| 10. Agents add up | `ran[]` holds every agent key with a request in the range, so it adds up to Where the money went and the Cost tile. A type with no user or project file has `scope` `no_file`, which the page words as an unknown source until M4 adds plugin agents. `set` is null with `set_reason` `no_file`, `sets_nothing` or `read_failed`. `AgentMoney` and `AgentRow` carry `requests` for unpriced rows |
| 11. Range change | Page only. Bones at measured heights with `aria-busy`, never old numbers under the new label. Each query is keyed by range, so a late answer for an older range is dropped. The chart pager resets to newest. The page checks `?range=` before asking, and an unknown value falls back to 30 days and replaces the URL, so no card ever gets `bad_request` |
| 12. Failed refetch | Page only. TanStack Query keeps the last good data. The card shows its own `as_of` as "updated {time}" while a refetch fails |
| 13. Replay for screen readers | Page only, from `timeline-at.ts`. The control's `aria-valuetext` is the time. A polite line once a drag or key repeat settles (500 ms) gives the counts by run state and the cost so far. The per-minute chart's `role="img"` label follows T |
| 14. Long sessions | Page only. The replay page step is 5 minutes, or larger when `bucket_seconds` is above 300, by the amount pass 9 sets. An `?at=` past the axis clamps to the end without a message. Risk 6, the forced-colours check and the `:has(input:focus-visible)` ring stay |
| 15. Tile deltas | Pending. The old app already ends the prior window at the same time of day, N days back (`dashboard/usage.py:165-171`, `prev_end` is `today - days` at `now_local.time()`), so its 7 and 30 day prior is not whole days. `review_windows.py` builds the prior by one named rule with a module switch. `same_time` is that old rule and the default, because the oracle uses it. `whole_days` ends the prior at the midnight that starts the current window. The differential runs with `same_time`, and a unit test covers both |
| 16. No `--rk` ramp on cost charts | Cost charts use the kind fill patterns with legend totals and the kinds line as the text alternative. Task 9a's sheet test checks no cost chart reads an `--rk` token |

### Kept as the plan has it

One timeline answer per session, the separate cost-chart route, `window` with `oldest` and the pager reasons, the `aria-disabled` pager ends with their reasons, no data announcements, range with etag and `as_of` on every answer, the native range input, the running-session rules, the states table, and the page owning every word.

### Copy for task 8

Partial prior, "at least" totals, "No price for {model}", no records, the straddling session row, the list end, the no-file and unknown-source cells, stale-card freshness, and the replay summary line.

### Task 1 results, November 9

- Claude Code deletes session transcripts and their `subagents/` folders once they're older than `cleanupPeriodDays`, which defaults to 30 days (code.claude.com/docs/en/claude-directory, "Cleaned up automatically"). So on real data, 90 days, 12 months and All grow only from the store's own history after the owner's first real start. The "records start on" line and `window.partial` carry that. When the sweep runs is not documented on the pages read.
- Only Chromium is installed in `.pw-browsers` (`app/web/playwright.config.ts:21` has one project), and M3 downloads nothing. The replay key checks and accessible-text checks run in Chromium only. WebKit is covered by the owner's M9 VoiceOver pass in Safari.
- No source says whether `preventDefault` on keydown stops a native range input's own Page Up and Page Down step. Task 9b proves it in Chromium with a test before building on it.
- `aria-valuetext` is the accessible value of a range input (MDN), and Playwright 1.64.1's aria snapshot uses it for slider roles. Whether a snapshot prints the `aria-describedby` description is not confirmed, so the pager end reasons are asserted with `toHaveAccessibleDescription`, not a snapshot.

### Task 2 results, November 9

`/usr/bin/python3 app/oracle/record.py --only long` writes `app/fixtures/oracle/demo-long/` (`truth-long.json` 460 KB, `truth-30d.json`, `manifest.json`), byte-identical over two runs. It raises if its own 30-day sums differ from the build's `truth.json`. Tidewater reporting holds 2,879 requests in 30 days, 8,596 in 90 days, 30,954 in 12 months and 33,895 in All. The long build takes about 2 s and 93 MB, so no `slow` marker is needed.

### Task 3 results, November 9

- `review_windows.py`, `review_query.py` and migration 0007 are in. All 18 recorded `/api/usage` payloads match for today, 7 and 30 days, and the long build matches `truth-long.json` for 30 days, 90 days, 12 months and All, by total, model, agent and day. pytest is 3,223 passed with coverage at 97 percent.
- One allowed difference. The old app drops `previous` when the oldest request falls after the prior start. The new answer keeps the prior and sets `prior_partial` (row 3 above). The test checks that both agree on when it happens.
- Review code returns UTC datetimes and takes local dates from the zone, because aware datetimes that share one `ZoneInfo` compare by wall time and miss the repeated hour on November 1.
- Session rows list `@main` in `agents` when the main session made requests. The old list left it out.
- Sessions sort newest first by their first request inside the range, as row 7 says. The "running first inside Today" rule in section 2 is dropped.
- `no_usage_sessions` is always 0 in practice, because the store keeps sessions only from requests with usage. The M1 notice keeps its own count.
- One scan costs about 2.5 µs per `minute_usage` cell. The 400-day demo answers 12 months in 0.11 s, but a heavy year near 1.5 million cells would take several seconds. Task 6 measures it, and a rollup table is likely.

### Task 4 results, November 9

`agent_setup.py` gives each agent key its scope, set, `set_reason` and check. `model_check.judge_agent` is now the one check that both the timeline and Agents call, and the timeline's output is unchanged. On the demo, `check_agent` equals the old pin for every agent in every project, outside three "NO CLEAN MAPPING" cases (`scribe` in Driftwood, Harbor Light and Tidewater reporting, where the file names Haiku 4.5 and the runs used Haiku 5.5). A failed setup read returns `failed`, which the API turns into card errors. Open item. With no model setting anywhere, the resolver's default gives `SetValue.value` the string "None", on Live too. The fix round settles it.

### Task 9a results, November 9

ShareBar, Pager, Segmented (pages), StackedBars with kind patterns and bar marks, and ScopeBar are on the sheet with every state. Vitest is 1,456 passed and the sheet spec with axe is 10 of 10. The sheet test fails if a cost chart reads an `--rk` token. The worker guessed 12 looks the spec doesn't draw (partial bar outline, no-records baseline, kind pattern shapes, unpriced stub, ShareBar edge and no-model fill, ShareBar name in tables, no disabled Segmented, Pager phone layout and button variant, ScopeBar back link and Open in Live). Passes 7 to 9 settle them.

### Task 5 results, November 9

- `api_review.py` serves the five routes, built in `review_answers.py` through new `StoreProvider` methods. The fixture provider answers `unknown_project`. A bad range, cursor, end date or a repeated parameter gives `bad_request` with `path` naming the field (`errors.FieldError`).
- The server zone is new in `server_zone.py`. Demo and flow builds use their `session.json` `tz`. Real mode reads `TZ`, then the `/etc/localtime` symlink, then falls back to UTC, and reads nothing else. This adds one read to m2-build.md section 7's list.
- The etag leaves out `server_time`, `as_of`, the window and prior ends and the open bar's end. The 32-answer cache is keyed by route, project, range, cursor or page, local date, the last ingest pass and the price hash. It never caches before a pass finishes. Between passes a cached answer keeps its window end and session states, which is at most one pass old.
- On both demo projects and all six ranges, the cost tile equals the newest chart page's legend, bars and kinds, the Agents rows, the Models rows and Where the money went, within 1e-9. No answer carries a cwd, a path, message text or a description. pytest is 3,362 passed with coverage at 97 percent, and web typecheck passes on the new types.
- `AgentRow.runs` follows the old rule (subagent runs, 0 for `@main`), while `runs_as_set` and `runs_not_as_set` count main as one run per session.

### Task 6 results, November 9

The routes miss the 250 ms target. On a generated year of 1,971,000 cells (6 sessions a day, 10 runs of 90 minutes each), a cold call takes about 0.33 to 0.68 s at 30 days and about 4 s at 12 months and All, at the 95th percentile. A cache hit takes 2 to 3 ms. Reading the rows costs about 3.3 s of the 4.1 s. The `minute_usage_minute` index is used and isn't the problem.

Measured on a scratch copy of the store, summary at 12 months took the following. 

| Fix | Summary 12 months |
|---|---|
| None | 4,114 ms |
| Covering index (database 305 to 462 MB) | 3,407 ms |
| SQL `GROUP BY` hour | 3,206 ms |
| Hourly rollup table | 292 ms |
| Hourly rollup with folder and agent type, no joins | 271 ms |

The cache doesn't save it on real data. While any session runs, each ingest pass clears the cache, so every 60 s refetch is a cold call. `test_review_size.py` records the numbers, and its target assertion is `xfail(strict=True)` until the owner decides (question 7 below). It adds about 3 minutes to the suite on one worker.

### Question 7, range speed (new, November 9)

7. Review on a year of heavy history.
   - A (my pick). An hourly rollup table that the single writer keeps beside `minute_usage` (migration 0008, backfilled from `minute_usage` on upgrade). Reads use hour rows for hours that sit wholly inside one chart bar or day, and minute rows only for hours that straddle a window or bucket edge. That is exact in every zone, half-hour offsets included. It should land near 250 ms at 12 months and about 30 ms at 30 days, and the size test then runs in seconds. One fast-worker at high, about $10 to $16, taken from the $8 to $12 contingency plus a little more.
   - B. Keep the speed as measured. 30 days answers in about half a second cold, but 12 months and All take about 4 s each time a pass has run, and the Summary page asks two routes.
   - C. SQL grouping by hour only. About 22 percent faster, still over 3 s at 12 months.

### Pending owner questions

Sent by the designer through the main session. Session cost across the range start (item 6), Show more or numbered pages (item 7) and the tile delta rule (item 15). The server answers all three ways already, so none blocks tasks 1 to 6. Question 7 above, range speed, is the lead's. The owner answered all four on November 9, in section 13.

## 13. Designs approved, November 9

The owner picked designer passes 7 to 9, so the UI build is unblocked. The design source is `docs/design/redesign-a/m3.js`, `m3.css`, `m3.html` and `strings-m3.js`, copied from the archive's `work-m3/` as M2 did. The boards are the 23 `a-m3-*` names in the archive's `shots/`, each at 1440 and 375, light and dark.

Owner decisions.
1. A session that started before the range shows its cost inside the range only, with a flag saying it started earlier. The server's `started_before_range` and `whole` carry it.
2. Sessions page in fifties. The list says "Showing 50 of 53" and a "Show 3 more" button loads the rest. Focus moves to the first new row.
3. An empty range shows one page-level empty card, not an empty state per card.
4. The API-rate note sits once per page, under the first cost card. The Cost tile says "API-rate estimate".
5. Check shows the existing Default status when nothing is set.
6. The cost chart is option A. Bars split by model only, with a "Made of" line of kind totals that links to Models. The pattern-by-kind bars stay on the Models page.
7. All picks its chart unit from the stored span. Up to 31 days is days, up to 13 weeks is weeks, longer is months. All has no pager.
8. A disabled Later stays visible and says "Nothing later yet".
9. Replay tiles show the value at the line with the whole session under it, and switch to "Whole session so far" at the end.
10. Long sessions get the precision label in tech-writer's plainer wording, "On long sessions they update every 10 minutes, but runs update every minute."
11. Replay arrow keys move 1 minute. Page Up and Page Down move 5, or one bucket when `bucket_seconds` is above 300 (row 14).
12. Runs that haven't started fold into "starts later" under a parent with more than 4 children.
13. Question 7 is A. Migration 0008 adds the hourly rollup, backfilled on upgrade and exact in every zone. The size test leaves xfail once it meets 250 ms.
14. The prior rule stays `same_time`.

Owner copy decisions.
1. Every count gets a singular form, such as "1 request has no price", "1 starts later" and "Show 1 more".
2. The model check count line no longer claims a file for every agent, because the Main session takes its setup from settings. tech-writer drafts the new line.
3. The cache tile on ranges other than Today reads "Across the whole range".
4. `md_note` is dropped.
5. The empty card's time is a key with a placeholder, and every board value that names the demo project becomes `{project}`.

Fix found in review. The model check's set value shows the text "None" when nothing is set, on Live too. It becomes no set value, so the Check cell shows Default.

Dispatched on November 9. Task 8 to tech-writer, task 9b and task 10 to fast-worker, and the rollup with the All unit and the "None" fix to fast-worker at high. Tasks 11 to 13 follow once tasks 8 to 10 land.

### Task 8 results, November 9

tech-writer drafted the additions and the lead typed them into `en.ts` as one M3 block. Every count is a `_one` and `_other` pair. Range phrases (`rg_p_*` mid-sentence, `rg_n_*` as a noun) fill `{range}` in `em_h`, `sel_h`, `sr_back` and `rt_range`. The new keys cover chart image labels, the replay summary, the stale-card line, the starts-later fold and the Agents source cells. The pager keys are `pager_prev`, `pager_next` and `pager_newest`, because `pg_` already names page titles. `sr_keys` takes `{n}` for the page step. `st_default` reuses `status_default`, and `gone_h`, `gone_b` and `t_unpriced` keep their M2 text.

Lead defaults on tech-writer's open questions, for the owner to confirm.
1. `rv_chk_q` takes the "set for it" wording. The M2 keys `mc_q`, `mc_ok_*` and `mc_all_ok_*` still say "its file sets" and stay as approved for Live.
2. The Main session counts as an agent in `mc_sum_n`, as it is a row in the check.
3. `sr_prec_long` keeps the owner's wording, and the label sits under the tiles it qualifies.
4. `top_all_one` reads "See {n} session", since the board draws it as a link to Sessions.
5. The started-earlier tooltip doesn't add the whole-session cost.
6. `sr_sum` keeps zero counts as written.
7. The back link reads "Sessions in the last 30 days".
8. Session review uses the M2 `gone_b`.

### Rollup, All unit and set value results, November 9

Migration 0008 adds `hour_usage`, keyed by hour first, with the summed columns plus `first_minute` for run order. It has no agent or folder column, because a run's agent type arrives late. The ingest writer rebuilds each touched (session, hour) group in the same transaction as the minute cells, and the tier-hash rebuild clears it too. Every ingest test now checks that the hour rows equal the minute rows grouped by hour when the store closes. Reads take hour rows for hours wholly inside one bucket and minute rows only at cut points. A reference scan stays minute only, and the two match on the demo, the long build and a crafted store in six zones, Lord Howe and Chatham included. The size test is live with no xfail. On the generated year the worst p95 is 213 ms (Summary at 12 months), so the headroom is about 15 percent. All's unit follows the stored span, so the 62-day demo shows weeks. A setting with no value now gives no set value instead of the text "None", on Live and Review. pytest is 3,403 passed with coverage at 97 percent.

### UI build results, November 9

Tasks 9b to 13 are in. ReplayLine is a native range input, and in Chromium a cancelled Page Up or Page Down stops the native tenth-of-range step, so the component's own step is the only one. TimelineLane takes `cut` as a fraction of the axis. The Review shell, Summary, Sessions, Agents, Models and Session review are wired in the router, and their tests live in `e2e/review.spec.ts`, `review-agents.spec.ts` and `session-review.spec.ts`.

The judge compared the build with the boards at 1440 and 375 and found no blockers. Two fix rounds closed the should-fix items.
- Summary cards align to the top.
- Model check on Review uses a compact one-line variant of the Live card.
- The pager has arrows, and a scope note shows when the chart is paged back.
- Sidebar Review links keep the range.
- The Range Select is full width at 375 and has its heading.
- Today spans the whole day with a Now marker.
- The chart scale no longer floors at $1.
- Tiles show the average line when the prior window holds no records.
- An ended session reads "No starter found".
- Idle time counts from the line.
- The line ends on the last request's minute.
- The session Select lists five sessions.

Left as built because the board agrees. "Go to end" hides at the end, and the Models kind total sits left of centre at 375.

Owner-approved departure from the M2 board, November 9. A lane's price cell on Live and Session review shows "No price" (`c_none_short`). The model name moves to a screen-reader-only span and the cell's title, which read "No price for {model}". The full line wrapped to three lines in the Main session lane at 1440 and ran into the name at 375. `TimelineLane` draws it, so Live and Session review share the change.

### Verifier fix round, November 9

Model check wording no longer claims an agent file for the Main session, which takes its setup from settings. tech-writer traced which reasons Main can reach (in effect, default, both lowered reasons, expected unknown, ran differs, ran mixed and no pin) and reworded those lines to "as set", "it's set to" or "{file} line {line} sets". Reasons only file agents reach (overridden, ignored, invalid) keep "Its file sets". `mc_r_no_pin_main` covers Main with nothing set. The shared keys change Live's wording too, which the owner accepted. The compact Review card now uses the board's one-line sentences (`mc_l_*`) for overridden, ran differs or mixed, and lowered by a cap, and falls back to the title elsewhere.

Checks after the fix rounds. Vitest 2,419 passed, Playwright 143 passed with 3 skipped (live-capture), and typecheck, ESLint, Stylelint and Prettier are clean. pytest is 3,403 passed at 97 percent, unchanged since the rollup, since neither fix round touched the server.

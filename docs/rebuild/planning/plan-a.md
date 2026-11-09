# Bar Tab release 1 plan, direction A "Timeline"

Written by the lead (deep-reasoner) on November 8, 2026. It replaces `plan.md`, which the owner rejected. Release 1 is a new app with a new design. The old app in `dashboard/` is a source of domain rules and test oracles only. Its screens, routes and layouts are not a model for anything here. The product is now Bar Tab, with plugin id and command `bartab` and `/bartab`, and the tagline "Watch every agent run in Claude Code, see what it costs, and tune the setup behind it." Earlier files and the boards call it the Routing Dashboard. "Claude Code" appears only in descriptive text (research 20, "name").

Sources are cited as path:line, research file and section, or board name. Boards are the PNG files in `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/design-redesign/shots/`, named `a-<board>-<1440|375>-<light|dark>.png`. Board source is `docs/design/redesign-a/`. Stack, security, access, launcher, packaging, platform and accessibility choices come from `research/20-decisions.md` and are not reopened here. That includes React Aria Components, TanStack Query for polling, `openapi-typescript` for API types, Vitest with Testing Library, and Playwright with axe.

## 1. Summary

- Live is the home page and lands first after the skeleton, in M2. Everything else is ordered by how often the owner uses it (Live, then Review, then Setup, then edits).
- Session review reuses Live's timeline with a replay line. To make that possible the SQLite store keeps per-run timing (launches, rounds, stops) and per-minute tokens for every session, not just the running one.
- The old app's `/api/live` honours a fixed clock and ignores records after it (`dashboard/api_live.py:26-33`). So the old app at "now = T" is a working oracle for replay at minute T. The panel said replay had no oracle (r3-senior-dev R9). It does.
- Ten milestones, M0 to M9. Each ends with something the owner can open in the browser. Risky edits (M8) can move to release 1.1 at the M6 gate.
- New code lives in `app/`, with the front end in `app/web` and the backend in `app/server` (O15). The owner runs the preview from the checkout (O9), so no plugin version bump happens before cutover (`tools/build_plugins.py:96-108`, project fact L-13fb). Cutover also renames the plugin to `bartab`.
- Prices update daily without an app release. The user's own `modelPricing` comes first, then LiteLLM's price file with checks, and every cost is labelled an API-rate estimate with its price date (section 3, Prices).
- Agents are created and edited on one full page (boards `a-dir-full-*`) in M6, with the system prompt editor in M7.
- Rough cost is $455 to $805 at list price, up from $425 to $755 for agent creation, the price feed and the rename. It is not taken from the dashboard's cost per run, so treat it as [NEEDS CONFIRMATION: per-run cost data].
- The owner accepted the plan's picks on November 8, and settled N1 and N2 the same day (section 9).

## 2. Release 1 scope by screen

### Navigation and shell

The shell follows component 1 and 2 in `docs/design/redesign-a/components.md`. At 721 px and up there is a 224 px sidebar with the brand, the project Select, and four groups. Live stands alone, Review holds Summary, Sessions, Agents and Models, Setup holds Your setup and To fix, and Reference holds How Claude Code decides and Glossary. At 720 px and below a sticky top bar shows page and project, and a five-item tab bar sits at the bottom (Live, Review, Setup, To fix, More). Main content stops at 1280 px if the owner accepts design call D7.

Routes put the project first, so every link names its project. The hash router keeps the access code in the fragment until it is swapped (research 20, "after research round 3").

| Route | Screen |
|---|---|
| `#/` | Redirects to the last project's Live, or the project picker sheet when there is none |
| `#/p/<project>/live?session=<id>` | Live |
| `#/p/<project>/review/summary?range=30d` | Summary |
| `#/p/<project>/review/sessions?range=30d` | Sessions |
| `#/p/<project>/review/sessions/<id>?at=<minute>` | Session review with replay |
| `#/p/<project>/review/agents?range=30d` | Agents |
| `#/p/<project>/review/agents/new` and `/<name>/edit` | Agent form, full page |
| `#/p/<project>/review/models?range=30d` | Models |
| `#/p/<project>/setup?scopes=1` | Your setup |
| `#/p/<project>/setup/<part>/<item>` and `/edit` | Surface page, inspector, edit rail |
| `#/p/<project>/to-fix` | To fix |
| `#/reference/decides`, `#/reference/glossary` | Reference |
| `#/more` | Phone only, the overflow list |
| Bare pages | Locked, first run, server stopped |

### In release 1

| Screen | Boards | What it shows | Notes |
|---|---|---|---|
| Live (home) | `a-live` | Session title with run state, four tiles (spent so far, tokens, read from cache, agents working), "Who is working" with the new-tokens-per-minute chart over the timeline lanes, Model check, Latest requests, Session Select across projects, Updated time, Pause | Lanes nest by Started by. A finished lane stops, a working lane reaches Now. Round marks show on the lane |
| Session review | `a-session` | Scope bar (back to range, Session Select, Open in Live), four tiles, "Who worked when" with the replay line and Back to now | Same lane component as Live. Runs not yet started at the cut show muted with "Not started yet" |
| Summary | `a-summary`, `a-summary-earlier` | Range Select, four tiles with the prior-period comparison, Cost per day with Earlier and Later, Where the money went, Model check, Most expensive sessions | The pager is chart-local. Tiles keep the page range (component 21) |
| Sessions | `a-sessions` | Range Select, sessions grouped by day, running session first with its run state, agents as badges, runs, tokens, cost with share bar | A row opens Session review |
| Agents | `a-agents` | One table for usage and setup. Agent, where it is set, Set to, Ran with, Check, Runs, Cost. A "No runs in the last 30 days" group lists agents that never ran, plugin agents included | A row opens the inspector beside a narrowed table (`a-agent-inspector`). "Add an agent" and Edit open the agent form |
| Agent form, new and edit | `a-dir-full-new`, `a-dir-full-edit` (with `-top` and `-prompt`), plus Review, Saved and plugin screens from `a-agent-new-review`, `a-agent-new-saved`, `a-agent-saved`, `a-agent-plugin` | Sticky action bar with ← Agents, Cancel and Preview. Sections Role and model (Model and effort in edit), Name and details, Tools and options, System prompt. Sticky side column with Jump to and the live agent file | Replaces the rail and the tabbed draft for agents (research 20, "agent form"). The phone tab bar hides here |
| Models | `a-models` | Models table (cost, share bar, tokens, from cache, used by), then "What the cost is made of" with model colours and kind patterns | Owner approved this revision (research 20, last section) |
| Your setup | `a-setup`, `a-setup-scopes` | Notice line, then the setup map table with ten parts (Settings, Agents, Instructions, Rules files, Skills, Hooks, Permissions, MCP servers, Plugins, Output style). The Switch "Show where each comes from" adds scope columns | Map rows are links to surface pages |
| Surface page | `a-surface`, `a-surface-readonly` | Breadcrumb, list and inspector. The inspector shows Runs at, set-to line with file and line, where it is set (top wins), Why with confidence, usage, Edit and Copy path | Read-only items show the lock mark and the owner reason |
| Edit rail | `a-edit-draft`, `a-edit-review`, `a-edit-saved`, `a-edit-overwritten`, `a-edit-text` | Drafting, review (effect, diff, warnings), saved with Undo, overwritten with Review changes and Undo, text body editing | At 375 the rail is a full-height sheet (component 28). Agents use the full-page form instead |
| MCP handoff | `a-edit-mcp` | Command row with Copy, the remove command, and a check line with Check again | The app never writes `.claude.json` (research 26-08, Recommendation) |
| Risky confirm | `a-edit-risky` | Command, when it runs, "I read this command", a danger button with its own verb | M8, cuttable to 1.1 |
| To fix | `a-tofix`, `a-tofix-empty` | Groups Couldn't read, Won't load, Not as set, then Can't tell (not counted), then Notices (not counted) | Sidebar and tab bar show the counted total |
| How Claude Code decides | `a-decides` | Rules with confidence badges, search field, version-gap banner | Reads `rules.json` |
| Glossary | `a-glossary` | Terms from the typed glossary | Words owned by tech-writer |
| Locked, first run | `a-locked`, `a-firstrun` | Gate page with the copy command, progress steps for the first ingest | Bare pages, no shell |
| Component sheet | `a-components` | Every component in every state | Dev and test build only |

### Not yet drawn, needed for release 1

Four states have no board, and Live at 375 needs a fix pass. Each needs a short designer pass, dispatched by the main session, before its milestone's UI work.

1. Live at 375 needs a fix pass. The board shows clipped run names ("Main ses...", "jud..."), effort text running into the token count, and the chart legend over the "80K" label (`a-live-375-light.png`). Due before M2 UI.
2. Live and replay for a long session. Boards show a 30-minute session. A three-hour session needs a wider bucket and a scrolling or compressed lane axis. Due before M2 UI.
3. Live with nothing running, and the session-ended state. Due before M2 UI.
4. The More page and the project picker at 375. Due before M0 shell work ends, since the tab bar lands in M0.
5. Agent creation and editing. Now drawn as the full-page form with its Review, Saved and plugin screens (components.md, "Picked layout"). No pass needed.
6. Server stopped, code used, code expired, and key for another project (plan.md section 7, "Access after reload"). Due before M0 ends.

### Explicitly later

| Item | Why it waits |
|---|---|
| Installed files page (routing layer) | Direction A has no board and no nav slot for it (decision O8). Research 20 puts the pin check in the optional routing layer too, but A draws Model check on Live, Summary and Agents in core copy without the word pin (r3-content R7, plan.md section 6). The owner confirmed the model check as core (O13) |
| Creating other files, delete, group undo, file rename | Agent creation ships in M6, because its Undo deletes one new file, which the old store already does for a create (app-audit/architecture.md 3.3). The rest needs group undo. File rename is held (research 20, round 3) |
| Cross-project Sessions page | Live's Session Select already spans projects |
| SSE | Polling is the default and SSE stays a spike (research 20) |
| Linux, then Windows | macOS first, every OS call behind one platform module (research 26-09) |

## 3. Data and API

### Principles

- The API speaks codes and numbers, and the page owns words (plan.md section 6).
- Every answer carries `as_of` and an `etag`. A request with a matching etag gets `{unchanged: true}`, as the old Live does (`dashboard/api_live.py:20-24`).
- Costs are never stored. The store keeps tokens per kind, and the server prices them at query time with the current price table (section 3, Prices), so all history reprices at current rates (research 20, after gap research). Answers cache on a hash of that table.
- Nothing stores message text, tool data or agent descriptions. A schema test fails if a text column appears (plan.md section 7, Privacy).

### App-wide reads

| Endpoint | Fields | Used by | Refresh |
|---|---|---|---|
| `POST /api/access/swap` | Body `{code}`. Returns the read key and the edit keys this tab holds | Locked page | Once |
| `GET /api/app` | `server_time`, `claude_version`, `rules_version_gap`, `routing_layer`, `editable_projects[]`, `ingest {state, files_done, files_total, bytes_done, bytes_total}`, `history {oldest, first_ingest, last_pass, last_backup, backup_failed}`, `running {project, session}[]`, `to_fix_count` for the current project | Shell (Live "Working" mark, To fix count, version line), first run | 10 s, 1 s during first run |
| `GET /api/projects` | `key`, `name`, `display_path`, `state` (ok, no_claude_folder, folder_not_found), `running` | Project Select | On open of the Select, and 60 s |

### Live and Session review share one payload

The lanes, tiles and chart on Live and on Session review come from one shape, the session timeline. The server computes every rule. The page only picks values at a time T. On Live, T is now. On Session review, T is the replay line.

`GET /api/sessions/<id>/timeline?project=<key>&etag=<tag>`

| Field | Contents |
|---|---|
| `session` | `id`, `project`, `branch`, `started`, `last_request`, `running` (request in the last 30 minutes, `api_live.py:81`), `active` (request in the last 60 seconds) |
| `axis` | `start`, `end`, `bucket_seconds` (60 for sessions up to an hour, then wider so there are at most 60 bars; [NEEDS CONFIRMATION: designer pass 2]), tick labels |
| `buckets[]` | `start`, `by_model {model: new_tokens}`, `cache_read`. New tokens are input, cache writes and output, as today (`api_live.py:35-41`) |
| `runs[]` | `run_id` (hashed), `parent`, `parent_known`, `depth`, `dispatch_order`, `agent`, `label_n`, `model`, `effort`, `segments[{start, end}]`, `rounds[{n, at, by}]`, `states[{at, state}]` (working, idle, finished), `first_request`, `last_request` |
| `runs[].cum[]` | Per bucket, cumulative `tokens`, `cache_read`, `cost`. The page reads index `floor((T - start) / bucket)` |
| `requests[]` | For Latest requests. `at`, `run_id`, `model`, `effort`, `tokens`, `cost`. Live shows the eight newest up to T |
| `model_check` | Per agent in the session, `set {model, effort, file, line, scope}`, `ran {model, effort}`, `status` (one of the seven words), `reason_code`, `params` |
| `totals_at_end` | Cost, tokens, cache share, runs, so tiles need no sum on the page |

Live takes "in the last minute" values from the last bucket. The run state at T is the last `states[]` entry at or before T, or "Not started yet" when T is before `first_request`. This keeps logic out of the page. The server owns the rules, which are ported from `api_live.py:280-404` (parents, rounds, done, idle by `ACTIVE_SECONDS`).

`GET /api/live/sessions?project=all` returns running sessions across projects, newest first, for Live's Session Select. Choosing another project's session navigates to that project's Live route (plan.md section 5, Usage, kept).

Refresh. Live polls the timeline every 1 s with the etag, only while the tab is visible and Pause is off. It announces run state changes only, at most once per row per minute (component 11). Session review polls every 5 s while `running` is true and stops when the session ends. Long sessions are a size risk, covered in section 10.

Ingest and freshness. One ingest thread is the only SQLite writer. It runs a full pass at start, then a stat-only incremental pass every second over the folders of running sessions and every 10 s over the rest. A no-change pass took 13 ms at 300k rows (26-05, Results). Requests read through short read transactions and never write. The target is Live data at most 2 s behind the transcript file. Polling is the default, so watchfiles is not used in release 1 (research 20, verifier pass).

### Review pages

All Review endpoints take `project` and `range` (today, 7d, 30d, 90d, 12m, all, default 30d; today compares with yesterday up to the same time) and return the window dates and the prior window for comparisons. They refetch every 60 s and on window focus.

| Endpoint | Fields |
|---|---|
| `GET /api/summary` | `tiles {cost, sessions, tokens, cache_share}` each with `prior`, `money[] {agent, model, cost, share}`, `model_check[]` (the same shape as the timeline's, over the range), `top_sessions[] {id, started, branch, agents[], runs, tokens, cost}` (four), `session_count`, `no_usage_sessions` |
| `GET /api/cost-per-day?end=<date>&days=30` | `window {start, end, has_earlier, has_later, reason_code}`, `days[] {date, by_model {model: {cost, kinds {input, output, cache_read, cache_write}}}}`, `legend[] {model, cost}`. The pager moves `end` by 30 days. Tiles do not change |
| `GET /api/sessions` | `count`, `days[] {date, sessions[] {id, started, branch, running, agents[], runs, tokens, cost}}`, `next` cursor (50 per page) |
| `GET /api/agents` | `ran[] {name, source {scope, plugin}, set {model, effort, file, line}, ran {model, effort, mixed}, status, runs, cost, share}`, `never_ran[]` with the same set fields. The catalog lists every agent the setup collectors find, plugin agents included (research 20, after the coverage matrix) |
| `GET /api/agents/<name>/form` | Every front matter field from `dashboard/agent_fields.json` (name, description, tools, disallowedTools, model, effort, color, permissionMode, skills, maxTurns, memory, hooks, mcpServers, initialPrompt, background, isolation, autoCompactWindow, omitClaudeMd, experimental) with value, line, `writable`, `risk_tier` and `ignored` for plugin agents, plus the body and the real path |
| `GET /api/agents/name-check?name=&save_in=` | `free`, or the file that would win. A project agent beats a user agent with the same name |
| `GET /api/models` | `rows[] {model, cost, share, tokens, cache_share, used_by[]}`, `kinds[] {model, input, output, cache_read, cache_write}` in dollars, `legend {kind: cost}` |

### Setup, To fix and Reference

| Endpoint | Fields | Refresh |
|---|---|---|
| `GET /api/setup` | `parts[] {part, summary_code, params, statuses[]}`, `scopes[]` per part when `scopes=1`, `notices[]` | 10 s with a stat-only signature etag per collector (plan.md section 7, Collector contract) |
| `GET /api/setup/<part>` | `items[]` in the item shape of plan.md section 7 (id, name, scope, sources, winner, status, reason, `writable`, `read_only_reason`, `risk_tier`, `loads`, `confidence`, `feature`, applies-when), plus `usage` for the inspector line ("all 53 main sessions ran at high") | 10 s, and the inspector reads the item etag while the rail is open |
| `GET /api/problems` | `rows[] {kind (problem, read_failure, cant_tell, notice), code, thing, file, line, params, confidence, fix {kind, target}}`, `counted` | 10 s |
| `GET /api/rules` | Rules with id, text code, confidence (tested, documented, assumed), quotes, version tested | Once per load |

The glossary is static, built from the typed strings.

### Edits

The edit API follows research 26-01 and plan.md section 5 ("Editing flow", "After Save"). `GET /api/edit/targets?item=<id>`, `POST /api/edit/preview`, `POST /api/edit/save`, `POST /api/edit/undo`, `GET /api/edit/history?project=<key>` and `GET /api/edit/rows/<id>` for the recheck poll (about 2 s, then once more, research 26-08). Every write passes the ASGI gate and the project's edit key.

Agent creation uses the same preview and save with a `create_agent` operation and `save_in` (user or project). Review shows the whole new file as an all-added diff with a "New file" badge, and Undo deletes the file.

### Prices

The source order follows research 20 ("pricing source").
1. The user's Claude Code `modelPricing` rates, read by the settings collector.
2. LiteLLM's `model_prices_and_context_window.json` from raw.githubusercontent.com/BerriAI/litellm/main, fetched once a day, Anthropic provider rows only, converted from per token to per million tokens.
3. The last good copy, kept beside the database.
4. A bundled dated copy in `app/server/data/`, for a new install that is offline.

A new LiteLLM copy replaces the last good one only when it parses, lists every current Claude model, has every price in range, and has cache read at about 10 percent of input. A failed check keeps the last good copy and records why. OpenRouter's public models list is fetched daily as a cross-check. When an input or output price disagrees, a notice says so, and no price changes. There is no scraping of Anthropic's pricing page and no repo price job.

`GET /api/prices` returns `source` (model_pricing, litellm, last_good, bundled), `as_of`, `cross_check {state, models[]}`, and per model `input`, `output`, `cache_read`, `cache_write_5m`, `cache_write_1h` and `relative` to Sonnet for the agent form's price words. Every cost card says it is an API-rate estimate with "Prices as of {date}", and cost help tells subscribers the figure is not their bill. The old `prices.py` also applies tiers and other modifiers [NEEDS CONFIRMATION: which of them LiteLLM's Anthropic rows carry].


### What SQLite keeps

The database sits beside the backups and the ledger in `<config>/routing-dashboard/`, outside `${CLAUDE_PLUGIN_DATA}` (research 20, after the coverage matrix). The ingest schema from research 26-05 ("Schema summary") is the base. Release 1 adds what Live, replay and Review need.

| Table | Contents | New in this plan |
|---|---|---|
| `files`, `requests`, `sessions`, `runs`, `links`, view `best_requests` | As in 26-05. Rows survive a missing source file (`missing=1`) | No |
| `run_events` | `session_id`, `run_key`, `kind` (launch, brief, stop), `finished`, `at`, `by_run`. Fed from the link, brief and stop rows that `transcripts.py` keeps today as `Links.rounds` and `Links.stops` | Yes. 26-05 left stops and rounds out ("Simplified") |
| `file_state` | Per-file parser state for rounds and stops, so a pass can resume from its offset | Yes, named as needed in 26-05 |
| `minute_usage` | `session_id`, `run_key`, `minute`, `model`, `effort`, `input`, `output`, `cache_read`, `cache_write_5m`, `cache_write_1h`, `requests`. Maintained by the ingest after dedupe | Yes. Feeds the timeline, cost per day and Models without scanning `best_requests` on every poll (26-05 notes 84 to 112 ms per query at 300k rows) |
| `meta` | Schema version, prices hash, first ingest time | Yes |
| `price_copies` | Fetched at, source, sha256, check result and reason, cross-check result | Yes |
| `prefs` | Server-side preferences (last project, range, Pause) | Yes (research 20, preferences stored server-side) |
| `ledger_mirror` | Read copy of ledger rows for history views. Ledger files stay the source of truth (26-01, line 79) | Yes |

Rules that keep history safe. Never delete rows on a rescan unless the source still exists. On a shrink, keep old rows and record the rescan (26-05, Risks). Back up daily, at start when the last copy is over 24 hours old, and at clean stop. Run `PRAGMA quick_check` before rotating and keep seven copies (plan.md section 10 item 12). Count rows with no usage and show the count as a notice.

### Security notes

The gate, keys, masking and CSP follow research 20 and 26-07. The price feed adds the app's only outbound calls. It sends GET requests to two fixed HTTPS URLs, LiteLLM's raw file and OpenRouter's models list. It sends no cookies, no keys and nothing from the user's setup or transcripts. Each response has a size cap and a 10 s timeout, redirects to another host are refused, and the body is parsed as data only. A failure falls back to the last good copy and shows on the history status, so an offline machine keeps working.

## 4. Component library

### Order of build

Components follow `docs/design/redesign-a/components.md`. Each lands in the milestone whose screen first needs it. The canonical rules from "Differences resolved" apply from day one, so nothing is built twice.

| Wave and milestone | Components (number in components.md) | React Aria Components or pattern |
|---|---|---|
| 1, M0 | Sidebar (1), tab bar and top bar (2), page header (3), card (5), well (6), raised finding (7), notice line (8), button (9), Select (14), skeleton bones (37), empty state (33), gate page (35), progress steps (34), model swatch (36) | Link in `nav`, Button, Select with ListBox and Popover (tray at 375), ProgressBar |
| 2, M2 | Tile (18), status chip (10), run-state glyph (11), badge (12), stacked bars (20, tokens per minute), timeline lane (22), table in a well (24) | Link per lane row, Table (APG Table), SVG `role="img"` |
| 3, M3 | Scope bar (4), segmented control as pages (13), pager (21), share bar (19), stacked bars with kind patterns (20), replay line (23) | Slider with `aria-valuetext`, Button pair with a polite window label, `nav` with Link |
| 4, M4 and M5 | Breadcrumb (3), Switch (16), scope label and chip (12), list and inspector (26), To fix row and group (32), search field (15) | Breadcrumbs, Switch, SearchField |
| 5, M6 | Edit rail (27), segmented choice (13), diff (29), phone sheet (28). Agent form parts: form field (38), text field (39), tag list (40), color choice (41), listbox popover (42), disclosure (43), role cards (44), model list with price mark (45), agent file preview (46), phone action bar (49), sticky page action bar (50) | RadioGroup, Modal with Dialog, ordered list for the diff, TextField with TextArea, TagGroup with ComboBox, Select with ListBox sections, Disclosure, RadioGroup cards |
| 6, M7 | Editor (30), command row and check line (31) | CodeMirror 6 lazy loaded, Button, `role="status"` |
| 7, M8 | Risky confirm (25), checkbox (17) | Checkbox, `role="group"` |

Shared rules are built once in M0 as CSS on `tokens.css`. That covers focus on `:focus-visible`, hover with no movement, disabled as `aria-disabled` with a visible reason, busy as a label swap with `aria-busy`, glyphs as empty-alt `content`, 24 px targets, and 32 px buttons (components.md, "Shared rules"). Class names use the canonical `lane-seg` and `segmented` (Differences resolved, item 14).

The chosen state is one standard for every selectable component (components.md, "Chosen state made canonical"). It is a `--select-bg` fill, a 2px `--accent` edge or the 3px start bar on rows, and a mark that is not colour ("✓ Selected", a ✓, or the bar). Focus is an outline outside that edge and never reuses it. The sidebar, tab bar and Switch keep their own looks. It lands in M0 with the shared rules, and the sheet test checks fill, edge, mark and focus on every chosen state. Tabs (47) and the step list dialog (48) are superseded and not built.

### Component sheet test

The sheet is a second Vite entry, `app/web/sheet.html`, built for dev and test only and never shipped in the payload. A typed manifest lists every component and every state from components.md. A test fails when a component in the manifest has no rendered state, so a missing state is a build error.

For each state, at 375 and 1440, light and dark, Playwright does the following.

- Runs axe with the `wcag22aa` tag set.
- Checks the computed focus outline on `:focus-visible` against `--focus-width` and `--focus-ring`, and that no hover changes layout.
- Measures target size (24 px minimum, 32 px for buttons, 52 px for tab bar items).
- Emulates forced colors and reduced motion, and checks that status and run state keep glyph and word.
- Scans rendered contrast for text and for model swatches and bars against their surface, skipping clip-hidden text. The `--rk` exception stays scoped to bars with legend totals (research 21).
- Writes a screenshot to the review set beside `a-components-*.png`. Screenshots are review material, not gates (plan.md section 8, kept).

## 5. Milestones

One lead per working tree, one PR per milestone, on a feature branch. The lead commits only when the owner says so. The verifier runs on Opus only. "Owner sees" is what the owner can open in a browser at the milestone's end, on the demo fixture unless it says real data.

### M0. Skeleton

- Goal. The owner types the preview slash command, gets the locked page or first run, swaps the code, and lands in an empty shell with the full navigation at 1440 and 375, light and dark.
- Lands. `app/` layout, `pyproject.toml` and `uv.lock`, FastAPI app with the ASGI gate (`--http h11`, `--no-proxy-headers`, receive timeout), read key and single-use code swap, per-request CSP nonce, Vite and React 19 with the hash router, typed `t()` and `tn()`, `tokens.css` copied in as the single sheet, shell, gate pages, wave 1 components, the component sheet, the More page and the project picker at 375, the launcher, CI on Linux.
- Spikes inside M0. Code swap end to end, SessionEnd with one shared server, uv SIGTERM, `json_edit` array insert, ruamel byte equality (plan.md section 12, Open questions).
- Tests. The gate refuses a bad Host, Origin, Sec-Fetch-Site or Content-Type, an oversized body and a missing token, and the tests assert "refused" rather than exact codes (research 20, spike 1). Every GET needs the read key (research 26-07). The dev server's CSP is looser than prod, and a test checks the built app serves the strict one (research 20, verifier pass). Launcher tests as subprocesses with `["guard"]` (project fact L-979a). Route harness with title, focus on h1, polite route status, scroll padding, reflow at 320 and 375. Component sheet run.
- Exit. Axe clean on every gate page and the empty shell at both widths and themes. The built `dist` is tracked and the launcher runs `uv sync --frozen --project app --no-dev`, then starts the server with that environment's own Python, offline on a second start (research 20, M0 spike 3). O1 and O6 are decided.

### M1. Data core

- Goal. The owner sees first run ingest the demo fixture with real progress, then the shell with "Updated" times and the history line.
- Lands. Ported pure core with flat module names (transcripts parser rules, usage dedupe, prices, projects, resolver, rules schema, agent front matter). Ingest into SQLite with `run_events`, `file_state` and `minute_usage`, through numbered migrations (research 20, Data). The single ingest writer and its pass schedule (section 3). History status, backup job, `/api/app`, `/api/projects`. The differential recorder (section 6). The price feed with its checks, last good copy, bundled copy, OpenRouter cross-check and `/api/prices` (section 3, Prices).
- Tests. Ported pure tests under pytest (plan.md section 8). Ingest oracle against a full re-read, late links in both orders, truncate and missing-file cases, "never delete rows on rescan", and a backup restore. A migration test builds every schema version in order on a copy and checks row counts survive. Price checks run on fixture files (good, missing model, out of range, cache ratio off, malformed, oversized) through an injected transport, so no test reaches the network. The fallback order runs from `modelPricing` down to the bundled copy. Differential cost tests pin the price table to a copy of the old `prices.json`, so a price change never reads as a regression.
- Exit. Demo totals for 30 days equal the old app's recorded `/api/usage` and `truth.json` from `build_demo.py`. The schema test finds no text column. Cold ingest time on the demo fixture is recorded.

### M2. Live

- Goal. The owner opens Live and watches a session run on a fake clock. Lanes grow, rounds appear, the model check and latest requests update, Pause holds the page. Then the owner points the preview at real data.
- Lands. Timeline endpoint, `/api/live/sessions`, Live page, wave 2 components, the Live fixes from designer passes 1 to 3.
- Lands too. The checkout run path (O9). The API-rate label and "Prices as of {date}" on Live's cost tile and Latest requests.
- Tests. Replay oracle on the `busy`, `many`, `unlinked` and `empty` scenarios (section 6). Vitest for the value at T. Playwright on a fake clock, counting announcements (research 21, 4.1.3 and 2.2.2). Pause and a hidden tab both stop polling.
- Exit. Run states, parents, rounds, tokens and costs match the old `/api/live` at every sampled minute, outside the allowed-differences list. Live data stays within 2 s of the transcript. The owner uses the preview on real data for daily Live work from here on, so the store starts keeping history early.

### M3. Review

- Goal. The owner moves from Live to Summary, Sessions, Agents and Models, pages Cost per day back a month, opens a past session and drags the replay line minute by minute.
- Lands. Summary, Sessions, Session review, Agents (usage half), Models, the Range Select with Today and the scope bar, wave 3 components.
- Tests. Differential totals per agent, model and day against the old `/api/usage` for today, 7 and 30 days, and against `truth.json` from a longer demo build for wider ranges. Replay Slider keys (component 23). Pager ends with their reason. Chart text alternatives.
- Exit. Totals match. Keyboard-only walkthroughs pass for "read the 30-day cost by agent" and "replay a past session" at 375 and 1440. First VoiceOver pass (owner or designer).

### M4. Setup read side and To fix

- Goal. The owner opens Your setup, flips "Show where each comes from", opens any part, reads why a value runs, and sees every real problem on To fix with a count in the nav.
- Lands. Collectors in the senior developer's order (settings, agents with full YAML, plugin agents and settings, skills, CLAUDE.md with imports, hooks, MCP from `.mcp.json`, masked `~/.claude.json`), from plan.md section 3. Setup map, surface pages, inspector with read-only reasons, problems feed, To fix page, the Agents setup half. Wave 4 components.
- Tests. The 123 resolver fixtures pass on the port. Each part has a reader, a clean fixture, a broken twin and a "Couldn't read" state (plan.md section 2, Machine checks). Closed-enum test that fails on a code with no string. Differential against old `/api/settings` for settings and agents.
- Exit. Walkthroughs "explain one agent's model and effort" and "find one problem on To fix" pass by keyboard alone at both widths.

### M5. Reference

- Goal. The owner reads How Claude Code decides with search and confidence, and the Glossary, and follows the version-gap notice from Your setup to the right rule.
- Lands. `/api/rules`, both reference pages, the search field, the typed glossary from tech-writer.
- Tests. Differential against old `/api/rules`. The rule count fact R-06c2 applies only to old files, so the new test reads `rules.json` directly.
- Exit. Axe clean, search result count announced politely.

### M6. Edit core

- Goal. The owner changes effort on a project, reviews the effect and diff, saves, sees "Saved." at once and undoes it. Then the owner adds an agent from a role preset and edits an existing agent on the same full page.
- Lands. Registry of writable fields, server preview, the edit rail and phone sheet, backup and undo with the changed-file refusal, the recheck and the overwritten state, the writable allowlist, agent front matter through ruamel with the byte-equality check, writes through a symlink to its target with the real path shown (research 20, round 3), wave 5 components. The full-page agent form for new and edit, from the Agents page. Role presets Lead, Worker and Reviewer fill real fields only, Custom shows after a change, and the role is never saved. The model list shows relative price words from `/api/prices` in both new and edit. The name check applies the rule that a project agent beats a user agent. Save in is User or This project. Fields follow `dashboard/agent_fields.json`, and "Can start other agents" off leaves `Agent` out of `tools` when tools are limited, or adds it to `disallowedTools` when `tools` is omitted (N2). `hooks`, `mcpServers` and `permissionMode` show read-only with their reason until M8, because they run commands or loosen permissions. Plugin agents are read-only, and the form flags the fields Claude Code ignores for them.
- Tests. Ported `edit_store` and `json_edit` tests plus hypothesis, the 26-08 write-race test, old and new apps reading each other's ledgers (`edit_store.py:796-799` per plan.md section 7), a real double-click on every swapped button, and aria snapshots for saved, undo and overwritten. Create then Undo leaves no file. Name clashes in both scopes. A preset then a change shows Custom. Each field round-trips with front matter bytes unchanged outside the edited key.
- Exit. Verifier pass (Opus). Second VoiceOver pass. The owner decides whether M8 stays in release 1.

### M7. Text bodies and MCP

- Goal. The owner edits CLAUDE.md, a rules file and an agent body in place, and adds an MCP server either by editing `.mcp.json` or by copying the `claude mcp` command.
- Lands. CodeMirror 6 loaded on Edit only (also the agent form's System prompt section, with the role's starter text), `replace_text` with a larger body cap than the old 65,536 bytes, front matter bytes unchanged on body edits, command row and check line, `.mcp.json` edits. Deny and ask rules if O14 places them here.
- Tests. CSP holds with CodeMirror (research 26-04). A body edit on a symlinked file writes the target. Esc then Tab leaves the editor. Front matter byte compare. "Check again" re-reads masked `~/.claude.json` on request only.
- Exit. Walkthrough "change one safe value and undo it" passes for a text body.

### M8. Risky edits (cuttable to 1.1)

- Goal. The owner adds a hook or an allow rule behind the risky confirm and sees the command in full before it can be saved.
- Lands. The tiered classifier and `risk.ack`, hooks, statusLine, apiKeyHelper, MCP command and args, allow rules and free env keys (research 20, risky surfaces). SKILL.md text editing, because skill bodies can hold `!cmd` lines that need this classifier (plan.md section 10 item 1, O12). Agent `hooks`, `mcpServers` and `permissionMode` become editable behind the same confirm. Wave 7 components.
- Tests. The button stays `aria-disabled` until the box is checked. Tab reaches the checkbox first. A double-click on Preview never lands on the danger button. The server refuses a risky operation without `risk.ack`.
- Exit. Verifier pass (Opus). Owner reads every risky confirm.

### M9. Cutover

- Goal. The owner's `/bartab` command opens the new app, and the old app is gone from the payload.
- Lands. Payload swap, the rename to Bar Tab, README rewrites, a git tag for the last old release (section 7). A USPTO search for the name runs before any public launch (research 20, "name").
- Exit. Differential suite green, axe and Playwright matrix green, a week of owner use on real data, verifier pass (Opus), third VoiceOver pass.

## 6. Testing strategy

### Layers

| Layer | Tool | Scope | Who runs it |
|---|---|---|---|
| T1 | pytest, Vitest | The changed area, seconds | Worker |
| T2 | pytest with xdist, Vitest, pyright, ruff, `tsc`, ESLint | All new tests, about 2 to 3 minutes | Lead and CI on Linux |
| T3 | Playwright with `@axe-core/playwright` | Every route and the component sheet at 320, 375 and 1440, light and dark, forced colors, reduced motion | Lead at milestone end |
| Old suite | `/usr/bin/python3 -m unittest discover -s tests` | Only when old files change. It runs alone and takes about 370 s (project fact T-7629) | Lead |

Never run a Claude Code harness batch as a check (project fact T-07ef).

### Data correctness with the old app as oracle

The recorder calls the old route functions in process with `server.fixture_context`, so no server starts and no port opens (`dashboard/server.py:284-314`). For replay it sets the clock per minute with `dataclasses.replace(ctx, fixed_now=T)` (`server.py:212`, `:310`). It writes JSON payloads with a manifest naming the old commit sha. Payloads are regenerated by one command and never hand-edited. An allowed-differences list names every intended change, and a difference outside it fails (plan.md section 8, R8).

| Oracle | Fixture | Compares |
|---|---|---|
| `api_usage.usage` | Demo, built by `build_demo.py` with a fixed `--now` | Totals, per agent, per model, per day for today, 7 and 30 days |
| `truth.json` | Same build | An independent count, so a bug shared by old and new still fails |
| `api_live.live` at a fixed clock T, for every minute of a session | Scenarios `busy`, `many`, `unlinked` and `empty` from `tests/fixtures/live_flow/build_flow.py` | Replay at T. Run list, parents, rounds, states, tokens, cost |
| `api_settings.settings` | Demo and the 123 resolver folders | Winners, statuses, files and lines |
| `api_settings.rules` | `rules.json` | Rule list and confidence |

Allowed differences start with these. Runs not started yet appear on the new timeline. "done" becomes Finished. Status words follow the seven-word set. The new app counts "Couldn't read" if the owner picks O7 option A.

The `busy` scenario is the session drawn on `a-live` and `a-session` (Tidewater reporting, `feature/quarter-close`, deep-reasoner, two scouts, two fast-workers, judge, and a tech-writer resumed for a second round, per `tests/fixtures/live_flow/README.md`). It builds on the demo set, so it serves both the replay oracle and screenshot review. The demo set alone writes subagent files but no link rows (`tests/fixtures/demo/build_demo.py:256-262`), so it cannot show Started by. The JSON files in `tests/fixtures/live/` are payload mocks and `tests/fixtures/rounds/` holds row snippets, so neither is an oracle input.

### Screenshot review

Each milestone captures every touched screen at 375 and 1440, light and dark, on the `busy` scenario and the demo set. A judge compares them with A's boards and reports differences as a list. Pixel baselines do not gate.

### Manual passes

VoiceOver at M3, M6 and M9, charts and the replay Slider included. Help and error text read by the owner with tech-writer each milestone.

## 7. Coexistence and cutover

### During the build

- The old app stays on development in bug-fix mode. Its fixes keep its own look and its own `dashboard/static/tokens.css` (CLAUDE.md, Design).
- `app/` is not in `routing_dashboard_files` (`tools/build_plugins.py:96-108`), so changes there need no plugin bump before cutover. Any fix to `dashboard/` still needs the bump and a rebuild (project fact L-13fb).
- From M2 the owner runs the new app on real data (decision O9). Before M2 the lead runs it with `uv run` from `app/` against the demo set and the `live_flow` scenarios. The port comes from a high range and is never 8377.
- The owner runs the preview from the checkout (O9). A stdlib script in `app/` starts the same server with `uv sync --frozen --project app --no-dev` and the environment's own Python (M0 spike 3). There is no second plugin, no bump and no pinned-test change.

### Cutover in M9

1. `tools/build_plugins.py` gets a `bartab` plugin in place of `routing-dashboard`. Its files function lists `app/server/**/*.py`, `app/pyproject.toml`, `app/uv.lock` and `app/web/dist/**`, and drops `dashboard/`. New files are staged first, because the build reads `git ls-files` only (L-13fb).
2. `plugins/bartab/` holds the plugin. The launcher becomes `bin/bartab`, the slash command `/bartab`, and the guard hook matches `Bash(python3 *bin/bartab*)` (L-bd45). The marketplace entry changes to match, with no "claude" in its name (research 20, "name").
3. Tests that pin plugin names change with it. That means `tests/test_plugin_build.py:298` and `:494` and the launcher and guard tests (L-979a). `tools/skill_probe/probe.py` runs again (L-bd45), and the old suite runs alone (T-7629).
4. `${CLAUDE_PLUGIN_DATA}` follows the plugin id, so launcher state and logs start fresh. The database, backups and ledger sit outside it in `<config>/routing-dashboard/` and carry over (N1).
5. Copy names the product Bar Tab and uses "Claude Code" only in descriptive text, with no Claude or Anthropic logo and no "official" near Claude. A USPTO search runs before any public launch.
6. A git tag marks the last old release. Rollback is that tag plus the old `routing-dashboard` plugin, which is safe because backups and the ledger stay compatible.
7. Old code is deleted one release later, with its tests.

## 8. Code location

Recommendation. A top-level `app/`, with the backend in `app/server` and the front end in `app/web`. The owner accepted it (O15).

| Path | Contents |
|---|---|
| `app/pyproject.toml`, `app/uv.lock` | `[tool.uv] package = false`, no build system, Python 3.11 or later, pinned below 3.15 (research 20, Judge's picks and spike 2, README Current stack) |
| `app/server/` | Flat modules (`main.py`, `gate.py`, `ingest.py`, `timeline.py`, `collect_*.py`, ported core). Flat names match the uv recipe, `PYTHONPATH=<payload>`, and keep the old `mock.patch` strings working in ported tests (plan.md section 8) |
| `app/server/tests/` | pytest, outside `tests/`, so the old `discover -s tests` run never picks them up (project fact T-7629) |
| `app/web/` | Vite project, `package.json` with exact pins, `src/`, `sheet.html` |
| `app/web/dist/` | Built output, git-tracked at milestone ends (research 20, verifier pass) |
| `app/web/e2e/` | Playwright and axe |
| `app/fixtures/` | Recorded oracle payloads and their manifest |
| `.nvmrc` at the repo root | Node 24 (research 20, round 3) |

Not inside `dashboard/`, because the payload builder takes every `.py` and `.json` there and all of `dashboard/static` (`tools/build_plugins.py:99-101`). New files would ship early and force a bump on every change. Extend `NoHomePathsInTestsTest` to `app/` (project fact T-3ad1), and keep `MR_TEST_TMP` outside every repo (T-c826).

## 9. Owner decisions

The owner accepted the plan's picks on November 8 (research 20, "plan-a decisions"). That covers O1, O2, O6 to O15, D1 to D10 and the agent-edit picks A1 to A5. Three answers differ from the plan, and they are folded in above.

### Resolved

| Id | Decision | Answer |
|---|---|---|
| O1 | Access after reload | sessionStorage per tab, BroadcastChannel handoff, launcher re-mints a code |
| O2 | User-scope edits | The preview names every project the edit reaches |
| O3 | Product name | Bar Tab, plugin id and command `bartab` and `/bartab`, renamed at cutover (owner's own pick) |
| O4 | Today preset | Added to the range presets (owner's own pick) |
| O5 | Narrator | "the dashboard" for now, may change with the name |
| O6 | Build and supply chain | Linux CI, locked installs, tracked `dist`, launcher on any `python3` |
| O7 | Couldn't read | Counts in To fix |
| O8 | Installed files page | Later, after a design pass |
| O9 | Preview from M2 | Run from the checkout, no second plugin |
| O10 | Effort env key | Registry-named env keys are normal fields, other env keys are risky |
| O11 | M8 in release 1 | Decided at the M6 gate, leaning yes |
| O12 | Skills text | In M8 with the classifier, to 1.1 if M8 is cut |
| O13 | Model check | Core, with "pin" only inside the routing layer |
| O14 | Deny and ask rules | M7 if the M0 array-insert spike passes, else 1.1 |
| O15 | Code location | `app/server` and `app/web` |
| D1 to D10 | Design calls on A | As recommended in the first draft of this plan (inline confirm, both statuses worst first, middle dot, sheet covers tab bar, neutral notice mark, live To fix count hidden at zero, 1280 px, no pill on run states, Fable triangle, heavier dark Idle glyph) |
| A1 to A5 | Agent-edit picks | Full-page form, full model list with price words in edit, short "Set by {role}" summary, chosen-state standard (research 20, "agent form") |

| N1 | Data folder name after the rename | Keep `<config>/routing-dashboard/` through release 1, so the old app, Bar Tab and a rollback share backups and the ledger. Move it one release later with a migration (owner, November 8) |
| N2 | Where "Can start other agents" writes | Off leaves `Agent` out of `tools` when the agent's tools are limited, and adds `Agent` to `disallowedTools` when the agent has every tool (`tools` omitted). Both are documented in code.claude.com/docs/en/sub-agents, "Let subagents spawn their own subagents" (owner, November 8) |

Nothing is still open. Two calls are scheduled. O11 is made at the M6 gate, and O14 follows the M0 spike result.

## 10. Risks and estimate

### Risks

1. Timeline payload size on long sessions. A long session with many runs means many cumulative arrays polled every second. Mitigations are the etag, wider buckets, and `minute_usage` so the server never rescans requests. Measure in M2 on a generated eight-hour session.
2. Replay correctness. Stops and rounds are new in the store (26-05, "Simplified"). The old app at a fixed clock is the oracle, but only for minutes inside its 30-minute running window (`api_live.py:26-29`). Sessions with longer gaps need hand-checked expected files.
3. Design gaps. Four states have no board, and Live at 375 needs a fix pass. Late passes block M2 UI. Run designer passes 1 to 4 beside M0 and M1.
4. Packaging found late. M0 builds the whole launcher, uv and tracked `dist` path first (plan.md section 12, risk 2).
5. Data loss in editing. The changed-file refusal, the recheck and the diff on "Undo anyway" cover it (research 26-08).
6. Transcript format drift drops output silently. Count rows with missing usage and show the notice (26-05, Risks).
7. Scope against capacity. M8 is the cut lever, and M7 is the second.
8. Price feed. A third-party file can change shape or lag a launch. The checks, the last good copy and the OpenRouter cross-check cover it, and the user's `modelPricing` always wins.
9. Name clearance. A live BARTAB mark exists in Class 39 and bar apps use BarTab. A USPTO search is due before any public launch (research 20, "name").

### Estimate per milestone

These are rough list-price ranges, scaled from plan.md's table to this plan's scope. Leads are deep-reasoner on Opus at high. Workers are fast-worker at medium, high for the gate, ingest and edit core. Verifier passes are Opus.

| Milestone | Dispatch | Estimate |
|---|---|---|
| M0 Skeleton | Lead, 3 workers, scout | $35 to $60 |
| M1 Data core | Lead, 3 workers (high on ingest and the price feed), scout | $55 to $95 |
| M2 Live | Lead, 2 workers, judge for screenshots | $40 to $70 |
| M3 Review | Lead, 3 workers, judge | $50 to $90 |
| M4 Setup and To fix | Lead, 3 workers, scout, judge | $60 to $100 |
| M5 Reference | Lead, 1 worker | $10 to $20 |
| M6 Edit core and agent form | Lead, 4 workers (high), scout, verifier | $70 to $120 |
| M7 Text bodies and MCP | Lead, 2 workers | $25 to $45 |
| M8 Risky edits | Lead, 2 workers (high), verifier | $35 to $60 |
| M9 Cutover and rename | Lead, 1 worker, scout, verifier | $20 to $40 |
| Designer passes 1 to 6 | Designer | $25 to $45 |
| Designer plan reviews before UI builds (M2, M3, M4, M6, M7, M8) | Designer at medium | $10 to $20 |
| Copy decks | tech-writer, medium | $20 to $40 |
| Total | | $455 to $805 |

Every milestone except possibly M5 passes the $20 plan gate and most leads pass $5, so each needs the owner's yes before dispatch. [NEEDS CONFIRMATION: per-run cost from the dashboard to replace these ranges.]

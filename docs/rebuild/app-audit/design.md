# Routing Dashboard, design audit of the current app

Written 2026-11-08 (01:44 to about 02:40 EST) by the designer, for the from-scratch rebuild (React 19, Vite, React Aria Components, plain CSS on tokens.css). Review only. No new directions, nothing built, nothing in the repo changed.

Settings used. The project CLAUDE.md Design section is present and was followed: design source `dashboard/static/tokens.css`, benchmark Stack direction A (`docs/design/usage-stack/`), Chrome on, Figma off, widths 1440 and 375, output in the scratchpad. The usability rules in `~/.claude/designer/usability-for-apps.md` apply to this page and were used as the yardstick. No copy was drafted, so tech-writer was not needed for these working notes.

How it was checked.
- Built the demo set (`tests/fixtures/demo/build_demo.py`) and the `busy` Live scenario (`tests/fixtures/live_flow/build_flow.py`) into this folder. Served each read-only, without `--allow-edits`, on ports 48731 and 48732. Both servers are stopped.
- Captured every page in headless Chrome over the DevTools protocol at 1440 and 375, light and dark (emulated `prefers-color-scheme`, reduced motion on). 72 captures plus 20 state captures, each with an overflow scan, a target-size scan, a landmark and heading scan and an unnamed-control scan.
- Computed contrast for every rendered text node against its real composited background, on 12 pages in both themes (42 distinct pairs).
- The edit flow could not be rendered, because the brief rules out `--allow-edits`. It is described from code (edit_*.js headers and builders) and marked as such.

Output folder: `/private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/app-audit/` (called `<audit>` below).
- `<audit>/shots/` page captures, named `<nn>-<page>-<width>-<theme>.png`.
- `<audit>/shots2/` trail, phone menu, Arrange, other Settings cells, keyboard focus.
- `<audit>/crops/` close-ups cited in the findings.
- `<audit>/shots/report.json`, `<audit>/shots2/report.json` scan results. `<audit>/contrast-out/report.json` contrast pairs.
- `<audit>/capture.mjs`, `scan.js`, `contrast.js` the capture and scan tools.

---

## 1. Visual sitemap

### Shell and navigation

One page shell (`dashboard/static/index.html`), hash routes (`js/router.js:1-14`). Every page shares the same frame.

- Sidebar (`js/shell.js:13-35`), 240 px at desktop. Group one is "This project" (or "All projects") with Live, Overview, Agents, Models, Sessions, Settings, Needs attention. Group two is "Reference" with Installed files and Rules reference.
- Top bar. Project select (all listed projects plus All projects) and a static version chip "Claude Code 2.1.310" (`js/shell.js:37-45`).
- Phone (720 px and under). The top bar stacks the menu button, the product name, the Project select and the version chip (about 150 px tall). The menu opens the sidebar as a 240 px drawer over the page, with the rest of the page inert (`js/shell.js:84-135`).
- Query state travels in the hash: `project`, `range` (today, 7d, 30d), `theme`, `setting`.

```
Sidebar ─┬─ Live ───────────── session link ──▶ Session detail
         │                     (idle) "See recent sessions" ──▶ Sessions
         ├─ Overview ───────── "See all 13" ──▶ Needs attention
         │   (project = All) ─▶ All projects ── project link ──▶ that project's Overview
         ├─ Agents ─────────── agent link ──▶ Agent detail ─┬─ "Open the trail" ──▶ Trail
         │                                                  └─ session link ──▶ Session detail
         ├─ Models              (no outbound links)
         ├─ Sessions ───────── session link ──▶ Session detail ── agent link ──▶ Agent detail
         ├─ Settings ── band cell (?setting=) ──▶ pane + "Why this value" rail
         │               rail "Rules behind this value" ──▶ Trail (main session only)
         ├─ Needs attention ── "Open the trail" per row ──▶ Trail (main session or any agent)
         ├─ Installed files     (no outbound links)
         └─ Rules reference ── rule id ──▶ GitHub (external)
Trail ── "change" link ──▶ Settings (?setting=)        Trail has no breadcrumb or back link.
```

Dead ends and hidden routes.
- Trail is reachable only from Needs attention, Agent detail and the Settings rail. It has no sidebar entry and no breadcrumb. Its page head says "Settings".
- Agent settings have no page of their own. They appear only as trails (`#/settings/<agent>/effort`). Main-session keys and agent keys differ (`effortLevel` against `effort`), so a hand-typed trail URL with the wrong key lands on "This project has no effort for builder" with no way back (`<audit>/shots/11-trail-*.png`, `<audit>/shots2/37-trail-bad-375-light.png`).
- Under All projects the sidebar still offers Live, Settings and Needs attention. Each shows only a "pick a project" card (`js/components.js:164-173`, `js/pages/live.js:180`, `js/pages/settings.js:177`, `js/pages/attention.js:112`).

### Pages and captures

Pattern for every row: `<audit>/shots/<file>-{1440,375}-{light,dark}.png`. State rows are light only.

| Page | Route | What it shows | Capture file |
|---|---|---|---|
| Live | `#/live` | Latest session minute by minute. Status line with Pause, 4 KPIs, tokens per minute (kind bar, new-token bars by model, cache-read lane), agents in this session, dispatch canvas, latest requests | `01-live` (busy fixture) |
| Live idle | `#/live` | "No recent session" card with "See recent sessions" | `20-live-idle` |
| Overview | `#/overview` | 4 KPIs with deltas, tokens per day, cost by model ring, tokens by agent, cache by agent rings, tokens by effort, Needs attention preview (3 of 13) | `02-overview` |
| Models | `#/models` | Cost by model ring, tokens by model bars, models table | `03-models` |
| Agents | `#/agents` | Cost by agent bars, cache rings, agents table with Ran with, Pinned to, Pin check | `04-agents`, `25-agents-all` |
| Agent detail | `#/agents/<name>` | 4 KPIs, "Did it run as pinned?" card, runs over time, tokens and cost by kind, recent runs | `05-agent-detail` |
| Sessions | `#/sessions` | Table of 10 newest, "Show all 53 sessions" | `06-sessions`, `26-sessions-all` |
| Session detail | `#/sessions/<id>` | 4 KPIs, agents in this session, tokens by agent | `07-session-detail` |
| All projects | `#/overview?project=all` | Same KPIs and day bars, cost ring with "Not priced" row, tokens by project, projects table with unlisted folder | `08-all-projects` |
| Settings band and pane | `#/settings?setting=` | Band of 8 cells (Model, Effort, Effort cap, Compact window, Cache lifetime, Extended thinking, Fallback models, Allowed models), Arrange, a "Run at" picker, "Where it's set, top wins" rows, "Why this value" rail | `09-settings`, `10-settings-effort`, `<audit>/shots2/32-settings-model`, `33-settings-compact`, `24-settings-driftwood` |
| Settings Arrange | Arrange pressed | Popover list with up and down buttons per cell, Reset, Done; drag at desktop | `<audit>/shots2/31-settings-arrange-{1440,375}-light.png` |
| Trail | `#/settings/<agent>/<key>` | "What decides the effort for builder", Winner, Other values found, Rules behind this value, Files read (disclosures) | `<audit>/shots2/11-trail-main`, `11-trail-builder` |
| Needs attention | `#/attention` | Cards per status (Unknown, Lowered, Ignored, Overridden, Invalid) with rows linking to trails | `12-attention`, `27-attention-driftwood` |
| Installed files | `#/files` | Files the installer places, state chip, what to do | `13-files` |
| Rules reference | `#/rules` | 84 rules, search, confidence filter (All, Tested, Documented, Assumed), each with reason, version line, docs disclosure | `14-rules` (13,805 px tall at 1440) |
| Empty states | various | Saltmarsh "No usage yet", Harbor Light "No usage in this range", Lantern "Folder not found" | `21-overview-saltmarsh`, `22-overview-harbor`, `23-overview-lantern` |
| Phone menu | menu open | Drawer over the page | `<audit>/shots2/30-menu-open-375-{light,dark}.png` |

Not captured. The edit flow (needs `--allow-edits`), the loading strip and the usage error notice (need a slow or failing server), the Live states paused, lost and unreadable.

---

## 2. UI component inventory

Token use is good across the board. app.css and live.css hold no literal colours. Every colour, radius, space and type size is a `var(--…)` except four 9 px glyph marks (`app.css:211`, `live.css:14,26`) and two ring numbers (`app.css:243` 20 px, `app.css:319` 14 px). Class names follow design rounds, not components (`.s4-`, `.s5-`, `.s6-`, `.s7-`, `.p2-`, `.g21`), which makes the CSS hard to map to components.

| Component | What it does | Where | Tokens | States seen or coded |
|---|---|---|---|---|
| App shell | Sidebar plus main column, sticky top bar | `index.html`, `js/shell.js:49`, `app.css:68-100` | `--sidebar-bg`, `--page-bg`, `--border` | desktop, drawer under 720 px, drawer open with inert page |
| Sidebar nav item | Icon plus label, current page filled | `js/shell.js:13-35`, `app.css:83` (`.nv`, min-height 40) | `--nav-active-bg`, `--nav-hover-bg`, `--accent` on active | rest, hover, current, focus ring |
| Project picker | Native select of listed projects and All | `js/shell.js` (switcher) | `--border-strong`, `--card-bg` | per project state (ok, no .claude folder, missing folder) shown only after picking |
| Version chip | Static "Claude Code 2.1.310", unknown variant | `js/shell.js:37-45` | `--surface-2`, `--border` | known, unknown. No "newer than rules" state on the chip |
| Page head | H1, intro line, optional crumbs, right slot | `js/components.js:117` | `--text-xl`, `--text-muted` | with crumbs (Agent detail, Session detail), without |
| Range control | Segmented Today, 7 days, 30 days | `js/components.js:127`, `app.css:192,278` | `--surface-2` track, `--card-bg` selected | selected, full width on phone |
| Card | Icon tile, title, question subtitle, body, optional disclosure | `js/components.js:35`, `app.css:107` | `--card-bg`, `--border`, `--radius-lg`, `--shadow-card` | open, collapsible (`.cd-dis` summary) on Trail |
| KPI tile | Label caps, big value, note, delta pill | `js/components.js:52`, `:70` delta, `app.css:202,211` | `--card-bg`, `--text-2xl`, delta on `--surface-2` | with delta up or down, without, "points" delta |
| Status chip | Mark glyph plus word for the 7 statuses | `js/components.js:12`, `app.css:53` (`.st`) | `--status-*-mark/fg/bg`, dashed border for unknown | in effect, overridden, ignored, invalid, lowered, default, unknown |
| Pin pill | Matches pin, Pin overridden, Differs from pin | `js/components.js:19`, `js/pin-view.js:129` | status tokens | three states plus a note line |
| Data table | Caps header on `--surface-2`, rows, link cells | `js/components.js:108` (`table3`), `app.css:410`, phone `app.css:472-476` (`.tb`) and `:283-287` (`.dt`) | `--surface-2`, `--border` | desktop, phone stacked (two different stacking patterns) |
| Stacked token bar | Cache read, input, cache write, output per row, legend with totals | `js/charts.js:89`, `:101` | `--rk-1..4`, start edge | desktop row, phone row with value above |
| Ring (donut) | Cost by model with centre total and legend table | `js/charts.js:50`, `:79` | `--cat-1..4`, hatch for not priced (`:42`) | priced, partly priced with hatch row |
| Mini ring | Cache hit rate per agent | `js/charts.js:117` | `--accent`, `--chart-track` | 4 across, 2 across on phone |
| Horizontal bars | Cost by agent, tokens by effort | `js/charts.js:108` | `--accent`, `--chart-track` | zero value shows empty track |
| Day bars | Stacked bars per day by model, axis in HTML | `js/charts.js:138` | `--cat-*`, `--chart-grid`, `--chart-axis` | full range, sparse, hatch for other models |
| Footer line | "Read from the transcripts in … Reload the page to update." | `js/components.js:148` | `--text-muted` | usage pages, Live variant |
| Empty state | Heading, line, optional action | `js/components.js:158`, `:164`; Live and Lantern have their own | `.es` `app.css:269` | four visual forms (see findings) |
| Loading strip and busy cards | Progress strip over skeleton cards while the reader warms | `js/usage-loading.js:58,122,148,172` | `.ld-*` `app.css:911-938` | reading, done; transition gated by reduced motion (`app.css:918`) |
| Error notice | Usage load failure with Retry | `js/usage-loading.js:207,227` | `.nt` | error, retrying, focus settle (`:263`) |
| Settings band | One cell per setting, value plus status, underline on the open cell | `js/pages/band.js:131`, `app.css:494` (`.s4-stat`) | `--border` separators, `--accent` underline | open, read-only, "N more" fold (`band.js:165-184`), phone shows one cell plus "7 more" |
| Arrange | Order the band cells, saved per browser | `js/pages/band_arrange.js`, `band_drag.js`, `band_order.js` | `.btn` | closed, open, drag (mouse), up and down buttons, Reset, Done |
| Pane: level picker | "Run at" segmented radios with "now" under the running level | `js/edit_card.js:135`, `:170` model, `:197` compact box | `--surface-2`, `--card-bg` | read-only (looks the same as editable), picked, over cap, cap first |
| Pane: where it's set rows | Scope label, file and line, value, status | `js/edit_card.js:342`, `:383` | status tokens | winner, overridden, ignored, invalid, not set |
| Rail | "Why this value", review, foot | `js/pages/settings.js:252`, `js/edit_card.js:579`, `js/edit_review.js:388,435` | `--surface` panel | rest, review, warnings (`edit_review.js:96-127`), diff (`:194`) |
| Undo strip and results | Last edit line, Undo, Undo anyway, stale and damaged lines | `js/edit_foot.js:24,63,106,113,169` | `.s4-ok` | ok, warn, quiet (code only) |
| Older backups | List and restore preview | `js/edit_backup.js:48,95,130` | `.nt`, diff | list, preview, confirm (code only) |
| Notices | Lock, token, edit-off notes | `js/edit_ui.js:110,132,152` | `.nt` | edit off, locked, token missing (code only) |
| Trail panel | Winner, other values, rules, files read as disclosures | `js/pages/trail.js` | card tokens, mono for values | open and closed disclosures |
| Attention list | Card per status, row with value, chip, "Open the trail" | `js/pages/attention.js:63-72` | status tokens | per status group, empty |
| Rules list | Rule id (external link), confidence badge, reason, version line, docs disclosure | `js/pages/rules.js` | `.ru-*` | filtered, searched, "No rule matches" |
| Live status line | Working or idle pill, session link, branch, Pause | `js/pages/live.js:96-105`, `live.css:14-26` | `--status-*`, `.lv-pill` | working, idle, paused, lost, unknown, unreadable |
| Live agents list | Per agent bar, working or idle pill, last request | `js/pages/live.js` | `--accent`, status | working, idle |
| Dispatch canvas | Absolute cards on a dotted grid, connectors, "agents at once" chips, Round chips | `js/pages/live_flow.js:87,153`, `live.css:143-172` | `--card-bg`, `--border`, `--accent` connectors | desktop canvas, list under 720 px, "Show n finished", guessed link dashed |
| Latest requests table | Last 8 requests with a "New" badge | `js/pages/live.js` | `.lv-new` | new, settled |

---

## 3. Current-site findings

Severity follows the critique skill: Critical blocks a task, Moderate slows or misleads, Minor is polish.

### First impression

The usage pages read well. Big numbers first, a question under every card title, status as glyph plus word, and calm card styling that holds up in both themes. This is the strongest part of the app and the benchmark (Stack A) is visible in it. The setup side (Settings, Trail, Needs attention, Rules) reads like the resolver's output. It is precise and honest, but it speaks in file paths, env keys and precedence words, and it covers one setting family for the main session only.

### Usability

| # | Finding | Severity | Where | Recommendation |
|---|---|---|---|---|
| U1 | The setup a person wants to read (agents, skills, hooks, CLAUDE.md, MCP, plugins, permissions) is not on screen at all. Agents appear only if they ran. An agent that never ran, its file, description and tools are invisible | Critical for the owner's goals | Agents `04-agents`, Agent detail `05-agent-detail` | Add a setup map and an agent catalog built from files, with usage as one section of each item |
| U2 | Agent settings have no page. They exist only as trails reached from Needs attention or a pin card. The Settings page covers the main session only | Critical | `js/pages/settings.js:1-12`, router keys `effortLevel` vs `effort` | One settings view per scope and per agent, with the same band and rail |
| U3 | The band headline shows the set value, not what runs. Effort reads "xhigh Lowered" while the picker below says "high now". People read the big word | Moderate | `09-settings-1440-light.png` | Lead with what runs ("high"), then "set to xhigh, lowered by the cap" |
| U4 | The read-only "Run at" picker looks exactly like the editable one. Nothing says it is off until the rail line "Editing is off" | Moderate | `09-settings`, `24-settings-driftwood` | Read-only shows the level as text or a disabled control with a lock line beside it |
| U5 | "Where it's set, top wins" lists "This project, just you" twice (env line and effortLevel line) with no difference in the label | Moderate | `09-settings-1440-light.png` | Name the second line by what it is ("env block" vs "setting") |
| U6 | Trail page head says "Settings", there is no breadcrumb, and the same rule sentence repeats in every "Other values" card | Moderate | `<audit>/shots2/11-trail-builder-1440-light.png` | Crumb "Settings / builder / Effort", say the rule once above the list |
| U7 | Needs attention lists Overridden rows, which are normal precedence, beside Invalid and Unknown. 13 rows for Tidewater, most of them fine. Rows for one setting (builder Effort) are split across three groups | Moderate | `12-attention-1440-light.png` | Count only judged problems (Invalid, Unknown, Ignored, Lowered against a pin). Group by setting and agent, statuses inside. Matches my rule "facts quiet, checks loud" |
| U8 | Under All projects the sidebar offers Live, Settings and Needs attention, which each show only "pick a project" | Moderate | `js/components.js:164-173` | Either hide them under All or make them work across projects (one server for all projects is the new model) |
| U9 | Usage never refreshes in an open tab. The footer says "Reload the page to update" | Moderate | `js/components.js:148`; architecture finding 5 | Refetch on focus and on an interval, show "Updated at" |
| U10 | Session names are "Session from October 30, 4:01 PM" and repeat the Started column next to them | Minor | `06-sessions`, `05-agent-detail` recent runs | Use the branch or a short id as the link text, keep time in its own column |
| U11 | Runs column mixes units ("82" for agents, "53 sessions" for the main session) | Minor | `04-agents` | Separate columns or a note row for the main session |
| U12 | Empty states use four different forms: card with outlined link-button (Live idle), icon card (No usage yet), message inside a chart card (Harbor Light), grey card with no action (Lantern) | Moderate | `<audit>/crops/empties.png` | One empty-state component: what will appear, one action. Harbor Light needs a "Show 30 days" button, Lantern needs "Fix the path" |
| U13 | Lantern's fix is "edit config/routing-dashboard.json by hand" while the range control still shows | Minor | `23-overview-lantern` | Offer the fix in the app (projects list editor), hide controls that cannot apply |
| U14 | Band order lives per browser and per port, so it is lost when the plugin picks another port. Arrange is heavy for its value (drag, buttons, popover, explanation paragraph on phone) | Minor | `band.js:232-263`, `<audit>/shots2/31-settings-arrange-375-light.png` | Keep a fixed task order (rule 19) or store it server side. Drop Arrange unless the owner wants it |
| U15 | Rules reference repeats "Checked on 2.1.302 … due for a new check" on all 84 rules, 13,805 px tall at desktop | Minor | `<audit>/crops/rules-top.png` | Say it once in a banner and on the version chip. Group rules by setting |
| U16 | Live canvas leaves most of its dotted area empty at 1440 and the tokens-per-minute card has a tall blank lower half beside the agents list | Minor | `01-live-1440-light.png` | Size the canvas to its content, balance the two cards |
| U17 | The Live session is not in the URL, so a view cannot be linked or restored | Minor | architecture finding 27 | Put session in the route |

### Visual hierarchy

- What draws the eye first. On usage pages the KPI row, which is right. On Settings the band's big values, which are the set values, not the running ones (U3).
- Reading flow. Overview runs KPIs, time, models, agents, cache, effort, attention. Good. Agent detail leaves a blank block under "Runs over time" because the right card is taller (`05-agent-detail-1440-light.png`).
- Emphasis. The "Did it run as pinned?" card is the best piece of copy-led design in the app. It states the answer, then the cause with file and line. Session detail is the weakest page at 1440, three short cards and half a screen empty, with no timeline of runs.
- Duplication. Cost by model ring appears on Overview, Models and All projects. Cache by agent rings appear on Overview and Agents. Tokens by agent appears on Overview and Session detail. Each repeat is the same component at the same size.

### Consistency

| Element | Issue | Recommendation |
|---|---|---|
| Model order | Overview day-bar legend runs Opus, Sonnet, Haiku, Fable while the ring and Models table sort by cost (Fable first) | One model order per page, by cost, everywhere |
| Phone tables | Two stacking patterns: `.tb` hides thead with `display:none` (`app.css:473`) and `.dt` keeps it as `.sr` with `::before` labels (`app.css:283-287`). Both set `display:block` on table parts, which drops table semantics in Chrome | One pattern. Real list markup on phone, or a scrolling table with a sticky first column |
| Links | Table links are underlined text; "Open the trail" is accent with an arrow; "See all 13" is accent underlined; "See recent sessions" is a link inside a button outline | Two styles only: inline link and button |
| Value truncation | Driftwood band "claude-opu…" and attention "env.CLAUDE_CODE_EF…" cut the part that matters | Wrap or show the friendly name; never truncate an id at its start |
| Status words | "Not known" headline with "Unknown" chip under it (double word) | One word per state |
| CSS naming | Round prefixes (`.s4-` 112 uses, `.s6-` 119, `.p2-` 77) | Name by component in the rebuild |

### Accessibility (WCAG 2.1 AA, plus the 21-accessibility.md checklist)

Summary. 2 major, 6 moderate, 4 minor. No contrast failures on visible text.

| # | Issue | Criterion | Severity | Evidence | Recommendation |
|---|---|---|---|---|---|
| A1 | Document title is the project name only on every page ("Tidewater reporting, Routing Dashboard") | 2.4.2 | Major | every row in `<audit>/shots/report.json` | "Page, Project, Routing Dashboard" |
| A2 | No focus move or announcement on route change | 2.4.3, 4.1.3 | Major | 21-accessibility.md | Focus the H1 (tabindex -1), one polite status line |
| A3 | No skip link to main content; 9 nav links plus the top bar before content | 2.4.1 | Moderate | `js/shell.js`, no "skip" in app.css | Skip link, or rely on landmarks plus heading focus |
| A4 | Phone tables lose table semantics (`display:block`) and one pattern hides headers from assistive tech (`display:none`) | 1.3.1 | Moderate | `app.css:283-287`, `:472-476` | See Consistency |
| A5 | Phone drawer has no scrim; the page behind stays at full strength while it is inert | 1.3.1 cue, usability | Moderate | `<audit>/shots2/30-menu-open-375-light.png` | Scrim plus React Aria Modal |
| A6 | No `color-scheme` meta and no forced-colors rules | 1.4.11 in forced colors | Moderate | `colorScheme: null` in scans; no `forced-colors` in CSS | Add both |
| A7 | Read-only picker looks operable (U4) | 3.3.2, 4.1.2 | Moderate | `09-settings` | Disabled state with reason beside it |
| A8 | Dispatch canvas chip "2 agents at once" covers the deep-reasoner card's cost "$3.22" | 1.4.10-like overlap | Moderate | `<audit>/crops/live-overlap.png` | Route chips in the gutter, never over a card |
| A9 | Inline links in tables are 16 to 21 px tall (agent names, session links, crumbs) | 2.5.8 (WCAG 2.2) | Minor | `small` lists in report.json | Row-wide hit areas or 24 px min |
| A10 | Visually hidden `.sr` text inside bar segments composites as 1.1 to 4.5 contrast in scans | none (hidden) | Minor | `<audit>/contrast-out/report.json` | Fine as is; keep it out of contrast tooling by marking it |
| A11 | Live charts redraw every second; Pause exists and the status line is polite | 2.2.2 | Pass | `js/pages/live.js:266,280` | Keep Pause, announce state changes only |
| A12 | Focus ring visible (2 px accent, offset 2) | 2.4.7 | Pass | `app.css:23`, `<audit>/shots2/34-focus-tab3-1440-light.png` | Keep |
| A13 | All SVGs named or hidden (0 unnamed across 72 captures); status always glyph plus word | 1.1.1, 1.4.1 | Pass | report.json `svgNoName` | Keep |
| A14 | No horizontal overflow at 375 on any page | 1.4.10 | Pass | report.json `scrollW` 375 everywhere | Add a 320 px check in the rebuild |

### Contrast check (computed from rendered nodes, composited backgrounds)

| Element | Foreground | Background | Ratio | Required | Pass |
|---|---|---|---|---|---|
| Body text on card, light | #1b1f24 | #ffffff | 16.56 | 4.5 | yes |
| Muted text on page, light (footer, intros) | #555d67 | #f5f6f8 | 6.17 | 4.5 | yes |
| Muted on card, light (labels) | #555d67 | #ffffff | 6.67 | 4.5 | yes |
| Model badge on surface-2, light | #555d67 | #eceef1 | 5.74 | 4.5 | yes |
| Active nav, light | #1d5bb8 | #dfe6f2 | 5.16 | 4.5 | yes (lowest visible pair) |
| Rail link on surface, light | #1d5bb8 | #f5f6f8 | 5.99 | 4.5 | yes |
| "New" badge, light | #1d5bb8 | #ffffff | 6.48 | 4.5 | yes |
| Done chip, light | #1f6a3a | #e4f1e8 | 5.67 | 4.5 | yes |
| Pin overridden chip, light | #8a4b00 | #f8ecd9 | 5.83 | 4.5 | yes |
| Differs from pin chip, light | #a3262a | #f9e5e5 | 6.06 | 4.5 | yes |
| Lowered chip, light | #6b3fa0 | #efe7f8 | 6.14 | 4.5 | yes |
| Active nav, dark | #86b4ff | #293342 | 6.07 | 4.5 | yes |
| Model badge, dark | #a4abb4 | #242930 | 6.32 | 4.5 | yes |
| Muted on page, dark | #a4abb4 | #1a1e23 | 7.23 | 4.5 | yes |
| Differs from pin chip, dark | #f09a9c | #3d1c1d | 7.10 | 4.5 | yes |
| Pin overridden chip, dark | #f0b56b | #3a2a12 | 7.58 | 4.5 | yes |
| Lowered chip, dark | #c9b0f0 | #2c2240 | 7.77 | 4.5 | yes |
| Done chip, dark | #8fd3a4 | #15301f | 8.15 | 4.5 | yes |

42 distinct visible pairs across 12 pages and two themes, all at or above 5.16. Non-text pairs follow the tokens.css header (light `--cat-2..4` 3.06 to 3.08 on card, `--rk-1` 1.54 and `--rk-2` 2.50 under the owner's exception, which holds because every stacked bar has legend totals and a start edge).

### Narrow width (375)

- No overflow anywhere. Every card stacks, charts keep their axes.
- The top bar takes about 150 px of an 812 px screen before the page title (`<audit>/crops/ov375-top.png`). The current page name is not in the bar.
- Settings on a phone shows one cell plus "7 more ? Unknown". The status under "7 more" is the worst hidden status, but it reads as the status of "more" (`09-settings-375-light.png`).
- Agents table stacks to 8 label rows per agent (`<audit>/crops/phone-tables.png`), 4 agents fill two screens.
- Long paths wrap mid-token in Needs attention and Trail on phone (`projects/tidewater-` / `reporting/.claude/…`).

### What works well

- Status as mark plus word everywhere, with the seven-word vocabulary held by tokens.
- Every cost says "Estimated at API list price", every page says what it reads and what it never keeps.
- Card subtitles as questions ("Is the cache working?") orient a cold reader fast.
- "Did it run as pinned?" and "Why this value" answer first and cite file and line.
- Dark mode is a true second theme, not an inversion; the kinds ramp flips sensibly.
- Live honours reduced motion, pauses in a background tab and has Pause.

### Priority recommendations

1. Make setup the spine of the app. Add a setup map and catalog pages for agents, skills, hooks, rules, CLAUDE.md, MCP and plugins, built from files, with usage folded into each item. This serves "read anybody's setup simple to complex".
2. One editor pattern for every surface, built from today's flow (pick, preview with diff, review, save, undo, restore), not fourteen setting-specific modules.
3. Collapse status noise. Needs attention counts only judged problems, grouped by thing, and every row ends in the fix.

---

## 4. Keep, change, drop, add (UI side)

Owner goals used as the yardstick: G1 read anybody's setup simple to complex; G2 edit settings, agents, rules folders, skills, hooks, CLAUDE.md and MCP config; G3 history past Claude Code's 30-day cleanup; G4 plugin-provided agents and settings; G5 one server for all projects.

### Pages

| Page | Verdict | Reason |
|---|---|---|
| Live | Keep, change | Strongest live view. Put session in the URL, let it pick any project's session from one server (G5), fix chip overlap, size the canvas to content |
| Overview | Keep, change | Good shape. Cut the repeated cards (cache rings, cost ring) to one each across pages, add longer ranges (G3), add a "Your setup" summary row that links into the setup map (G1) |
| All projects | Change | Becomes the home of a one-server app (G5): project list with setup health and usage, including projects without transcripts |
| Agents | Change into Agent catalog | Every agent from files and plugins (G1, G4), usage columns beside it, source chip (user, project, plugin, managed) |
| Agent detail | Change | Definition first (description, model, effort, tools, file, source), then pin check, then usage. Edit from here (G2) |
| Models | Keep, merge | Fold the ring into Overview's; keep the table as a Models section or tab |
| Sessions | Keep, change | Range up to all stored history (G3), better link names, filter by project and branch |
| Session detail | Change | Add a run timeline (the dispatch canvas in replay) so it earns its page |
| Settings band and pane | Keep concept, change | Keep band, "where it's set" rows and the rail. Lead with what runs. Add scope switch (main session, each agent) and every editable key, not 8 fixed cells |
| Settings Arrange | Drop | Low value, high cost, lost on port change. Use a fixed task order (usability rule 19) |
| Trail | Keep, change | Merge into the setting's rail or a full-height panel with a crumb. Say the rule once |
| Needs attention | Change | Becomes "To fix": judged problems only, grouped by thing, fix action per row, plus unreadable surfaces (diagnostics) |
| Installed files | Move to optional layer | Install-specific; show only when the routing choices file exists |
| Rules reference | Keep, change | Group by setting, one version banner, search stays. It is the evidence behind every status word |

### Shared components

| Component | Verdict | Reason |
|---|---|---|
| Shell, sidebar, top bar | Keep, change | Add a scrim to the phone drawer, put the page name in the phone bar, regroup nav for setup (see Add) |
| Project picker | Change | One server for all projects: a searchable picker with project state shown in the list (React Aria ComboBox) |
| Version chip | Change | Carry the "newer than rules" state once, link to Rules |
| Range control | Keep, extend | Add 90 days and All history (G3), or a date range |
| Card, KPI tile, delta | Keep | Benchmark quality. Rebuild as React components on the same tokens |
| Status chip, pin pill | Keep | The seven-status vocabulary is the core of the system |
| Data table | Keep, change | One phone pattern with real semantics. React Aria Table for sort and row actions |
| Stacked token bar, ring, mini ring, hbars, day bars | Keep shapes | Hand SVG, HTML axes, hatch and start edge rules stay |
| Footer line | Change | Becomes "Updated at …" with live refresh |
| Empty state | Change | One component, what will appear plus one action |
| Loading strip, busy cards | Keep idea | Skeletons from the loaded layout so nothing jumps |
| Error notice | Keep, generalise | One notice with retry, placed where the data was |
| Settings band | Keep | Good scan of many values; add the scope switch |
| Level picker | Keep, change | Clear read-only state; same control for every enum setting |
| Where it's set rows | Keep | The precedence list is the clearest explanation in the app |
| Rail, review, undo strip, older backups | Keep the flow, generalise | Same review rail for every surface: diff, side effects, Save, Undo, Restore |
| Trail panel | Change | Folds into the rail or a panel |
| Dispatch canvas | Keep | Unique and valuable; reuse it for session replay |
| Arrange controls | Drop | See Settings Arrange |

### Add (named, not designed)

| New view or component | What it would help with | Goal |
|---|---|---|
| Setup map | One screen that shows every layer that shapes a session (managed, user, project, local, plugin, CLI) and what each holds: settings, agents, skills, hooks, rules, CLAUDE.md, MCP, output styles. Simple view first, detail on click | G1, G4 |
| Agent catalog and agent page | All agents from every source with model, effort, tools, source and usage | G1, G2, G4 |
| Skills, hooks, rules, CLAUDE.md, MCP and plugins pages | One list-and-inspector pattern per surface: list on the left, selected item's details and file on the right | G1, G2, G4 |
| File editor with diff and backup | Edit a markdown or JSON file (CLAUDE.md, agent body, rules file, skill), preview the diff, save with backup, undo, restore older | G2 |
| Structured field editors | Front matter fields, hook entries, MCP servers and permissions as form rows with validation beside each field, raw view one step away (rule 22) | G2 |
| Source chip | Where a thing comes from (user, project, local, plugin name, managed), read-only marker for managed and plugin items | G1, G4 |
| Diagnostics panel | What could not be read and why, per surface, with the fix | G1 |
| History range and retention note | Shows how far stored history reaches beyond Claude Code's cleanup, and when ingest last ran | G3 |
| Projects home | Every project the server knows, its setup health and recent usage; add or remove a project in the app | G5 |
| Command palette or search | Jump to any agent, setting, file or session by name | G1 |

---

## Joint list

Merged from this file and `<audit>/architecture.md` (sections 4 to 6). Side is who owns the change: design (screens and states), architecture (data and API), or both. Where the architect drafted a row, my verdict confirms or overrules it, and the reason says which.

| Component | Side | Verdict | Reason |
|---|---|---|---|
| Live page and dispatch canvas | both | Keep, change | Architect: polling with etag, session in URL (finding 27). Design: any project's session from one server, chip overlap fix, canvas sized to content. Confirms the draft |
| Overview | both | Keep, change | Architect: range queries replace three views (findings 7, 8). Design: dedupe cards, longer ranges, setup summary row |
| All projects | both | Change into Projects home | Architect: project registry (A6, finding 15). Design: the home page of a one-server app with health per project |
| Agents | both | Change into Agent catalog | Architect: plugin collector, managed agents, full YAML reader (findings 12, 14). Design: every agent, not only those that ran |
| Agent detail | both | Change | Definition first, pin check phase 1 (architect finding 35), edit entry point |
| Models | design | Merge into Overview or a tab | Duplicated ring; table stays |
| Sessions and Session detail | both | Keep, change | Architect: paged sessions from SQLite (G3). Design: run timeline replay, better link names |
| Settings band and trail | both | Keep concept, change | Architect: resolver payload ports, cached by file signature. Design: lead with what runs, scope switch for agents (architect finding 18), trail folds into the rail |
| Band Arrange and order storage | both | Drop (overrules the draft) | Architect drafted "move order to the database". Design drops Arrange for a fixed task order, so no storage is needed. If the owner wants Arrange kept, the database is the right home |
| Needs attention | both | Change to "To fix" | Architect: widen with unreadable surfaces. Design: judged problems only, grouped by thing, fix per row. Overridden rows leave the count |
| Diagnostics | both | Add | Architect drafted it. Design places it inside "To fix" and as an inline state on each surface page |
| Installed files | both | Move to optional routing layer | Both agree; shown only when the choices file exists |
| Rules reference | both | Keep, change | Architect: keep as evidence, render from the API. Design: group by setting, one version banner |
| Surface pages (CLAUDE.md, skills, hooks, MCP, plugins, rules folders) | both | Add | Architect: surface registry and collectors. Design: one list-and-inspector pattern for all of them |
| Setup map | both | Add | New from the design side. Needs a per-layer summary from the surface registry |
| Edit flow | both | Keep the flow, generalise | Architect: target registry with edit kinds (JSON splice, front matter round-trip, whole-text markdown, create and delete). Design: one review rail for every surface, so the registry needs a common preview shape (diff lines, side effects, warnings, hash for stale check) |
| File editor with diff and backup | both | Add | Rides on the generalised edit flow and edit_store |
| Structured field editors and validators | both | Add | Architect: validators per surface. Design: errors beside the field, raw view one step away |
| Source chip and read-only markers | both | Add | Needs source and writability per item from the registry (plugin and managed items read-only) |
| Project picker | both | Change | Architect: project registry with stable ids. Design: searchable picker with state in the list |
| Range control and history | both | Keep, extend | Architect: ingest service and SQLite. Design: 90 days, All history, retention note |
| Freshness and refresh | both | Change | Architect: TanStack Query with etags (finding 5). Design: "Updated at", no "reload the page" footer |
| Shell, cards, KPIs, chips, tables, charts | design | Keep shapes, rebuild in React | Benchmark quality, token-clean CSS; fix phone tables, drawer scrim, titles and focus on route change |
| Empty, loading and error states | design | Change | One empty-state component, skeletons from the loaded layout, one error notice |
| tokens.css | design | Keep | The design source; add `color-scheme` meta and forced-colors rules |
| app.css, live.css | design | Change | Rewrite per component; drop round-numbered class prefixes |
| Strings | both | Keep one copy file | Typed t() and tn() (owner); new surfaces need tech-writer copy |

### Answers to the architect's seven questions

1. Page verdicts are in section 4, Pages.
2. Shared components that stay as concepts: KPI row, stacked token bar, ring, hbars, day bars, chips and pills, the band (without Arrange and without the More fold on desktop), the rail, the dispatch canvas, the loading skeletons. The trail panel folds into the rail. Arrange goes.
3. New screens and the state each needs.
   - Setup map: per layer (managed, user, project, local, plugin, CLI and env) the count and names of what it holds per surface, plus a health flag.
   - Agent catalog: per agent name, source, file path, writable flag, description, model, effort, tools, ignored fields for plugin agents, last run, runs in range, pin check result.
   - Surface pages (skills, hooks, rules, CLAUDE.md, MCP, plugins): per item name, source, path, writable flag, parse state with message and line, and the file text or parsed fields for the inspector.
   - Projects home: per project id, name, path, folder state, setup health counts, last session time, usage in range.
   - "To fix": per problem the thing it belongs to, the judged status, cause in plain words, file and line, and a route to the fixing view.
4. One review rail for all surfaces. The registry needs a common preview shape: diff lines, the resolved effect on running values where one exists, warnings, the file hash for the stale check, and backup and undo rows per file.
5. Live shows one session at a time, chosen from any project the server knows, and the session goes in the URL. A small "other live sessions" list beside the status line covers several at once without a wall of canvases.
6. Preferences: none needed once Arrange is dropped. If view preferences appear later, keep them per browser unless the owner asks for sync.
7. Unreadable or partly readable surfaces show, on their own page, the parts that did read plus an inline error card naming the file, the reason and the fix; the same item appears once in "To fix". A surface that cannot be read at all keeps its nav entry with a count of zero and a "Couldn't read" state, never a blank page.

### Open questions for the owner

- Drop Settings Arrange? I recommend yes.
- Should Overridden values leave the Needs attention count? I recommend yes; they stay visible in each setting's "where it's set" list.
- Should agents that never ran appear in the Agents list? I recommend yes, as the catalog.
- How far back should history go by default in the range control (90 days, all stored)?

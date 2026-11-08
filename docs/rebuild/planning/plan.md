# Routing Dashboard rebuild plan

Written by the judge on November 8, 2026, from the four round 3 files, with rounds 1 and 2 for reasoning. Research files 20 and 21 are givens. Citations name the panel file and section. Anything marked "judge" is my own call. I did not re-check the panel's claims about Claude Code docs or the old code, so the verifier pass in the agenda still applies.

## 1. Summary

- The app is a local web page that shows what runs in each Claude Code project and why, lets the owner change it safely, and shows what it cost. It reads anybody's setup. The model-routing install becomes an optional layer (r2-content 1, r2-architect 1).
- Release 1 is the old app's behavior on a new stack, plus history kept past 30 days, a read-everything setup view, and a small first set of edits (r3-senior-dev R1, r3-architect R1).
- Release 1 edits four settings keys and an agent's model and effort (M6). It then edits CLAUDE.md, rules and agent body text with a lazy CodeMirror (M6b). The owner can cut M6b if time runs short.
- Hooks, statusLine, MCP commands, allow rules, env, skills text, delete and groups come after 1.0. The server refuses them in plain words with the real path and no promise (C1).
- Two design rounds gate the UI milestones and run beside backend work. The setup round covers the sidebar and Projects home. The rail round covers the text editor variant (r3-designer R2, r3-architect R2, r3-senior-dev R2).
- UX patterns are settled. The setup map is an APG Table. The risky confirm is inline in the rail. The scope switch is a Switch. Alert Dialog is for delete only (r3-designer R3, r3-architect R3).
- After Save the rail says "Saved." at once. There is no visible "checking" state. A poll watches the three files Claude Code also writes, and an overwrite warning stays on the row (r3-designer R4, r3-architect R4, r3-content R4).
- "To fix" has four groups. Three count and "Can't tell" does not. One split remains on whether "Couldn't read" counts (O7).
- Testing ports about 1,260 pure tests, rewrites about 1,060, and replaces the JS checks. Differential tests use payloads recorded from the old app. Screenshots are review artifacts, not gates (r3-architect R8, r3-senior-dev R8).
- Build is eight milestones (M0 to M7, plus M6b). Estimated list-price cost is roughly $400 to $800 for release 1. That passes the $20 plan gate, so it needs the owner's yes before dispatch. Seven owner decisions are open, and O1 and O6 must close before M0 ends.

## 2. Product

Purpose, in one line (draft for tech-writer, r2-content 1). "See what runs in each project and why, change it safely, and see what it cost." Each page answers one question. "What runs here, and why?" "What changes if I save this?" "What did it cost?" "What's running right now?"

Audience. One reader who knows Claude Code well but has not memorized its precedence rules. The owner comes first. The test is a stranger's setup, so the fixture corpus needs one setup with no routing install (r2-architect 1, r2-designer 1).

Done for release 1 has three parts. All three must pass.

The owner's tick list (r2-content 1, with item 9 added by judge from the old app's parity rule):
1. I can open any of my projects from one Projects page.
2. For any setting or agent, I can see what runs, where it is set and why.
3. "To fix" lists only real problems, and each says what to do next.
4. Usage totals for the last 30 days match the old dashboard.
5. Usage older than 30 days is still there after Claude Code deletes its transcripts.
6. I can change a value, see what will change before I save, and undo it.
7. Every page works at phone width and with the keyboard alone.
8. No page tells me to reload it.
9. Every old page and every old edit is marked done or dropped on purpose (parity matrix, r1-senior-dev 12).

Machine checks (r1-architect 1). Every registry surface has a reader, a clean fixture, a broken fixture and a "Couldn't read" state. The 123 resolver fixtures pass on the port. Demo-fixture usage totals equal the old app's. The edit-store safety tests pass and the old and new apps read each other's ledgers. Axe reports no violations on any route at 375 and 1440. A transcript removed by Claude Code's cleanup keeps its rows.

Job walkthroughs (r1-designer 1, kept in r2-designer 1). Five keyboard-only jobs pass at 375 and 1440 on the simple, typical and complex fixtures. Explain one agent's running model and effort. Find and fix one problem from "To fix". Change one safe value and undo it. Read the 30-day cost by agent. Watch a live session. A job passes when a cold reader finishes it without reading a file path first.

## 3. Release 1 scope and what follows

### In release 1.0

- Usage pages on SQLite with history ranges, ported from the Stack A design. Overview, Sessions and Session detail. Models folds into Overview (C3, judge below).
- Live and the dispatch canvas, with the session in the URL and a cross-project session picker (r3-senior-dev R9, r3-designer R9). "Started by" replaces "Dispatched by".
- Setup read side. Collectors in the senior developer's order: settings, agents (full YAML), plugin agents and settings, skills, CLAUDE.md with imports, hooks, MCP from .mcp.json, then masked ~/.claude.json (r1-senior-dev 5). Setup map, one list-and-inspector page per shipped collector, agent catalog that lists agents that never ran, "To fix", and the reference pages.
- Optional routing layer (pin check phase 1, Installed files), shown only when the layer is detected through the API's `feature` tag (r2-architect 1). Judge's placement is M5.
- Projects home, first-run states, locked-tab and server-stopped states, one server with per-project edit keys and a read key.
- Edits. M6 covers the four old keys and agent model and effort. M6b covers CLAUDE.md, rules and agent body text.
- The old app's must-match list. The precedence list, the seven status words, pin check phase 1, undo with older backups, Live with Pause (r2-designer 2). Fixes required on usage and Live are the accessibility items, the phone table, the drawer scrim, the Live chip overlap and "Updated {time}" (r2-designer 4).

### Not in 1.0, in order

1. Release 1.1. First risky surface with the full tiered classifier and `risk.ack`. Hooks, statusLine, apiKeyHelper, MCP command and args, allow rules and env (risky per research 20). `.mcp.json` edits and the MCP copy command with "Check again". SKILL.md text. Deny and ask rules, unless pulled into 1.0 (see section 10).
2. Release 1.2. Single-file create. Delete with group undo and its Alert Dialog. Skill folders and executable files. Output styles. File rename stays held (research 20).
3. Later, unordered. Linux, then Windows only with an owner yes. Jump-to search. CSV export. Canvas replay on session detail and a cross-project sessions page. Inverse-operation undo. SSE spike. Tree View where nesting is real, such as a CLAUDE.md import chain.

Dropped from the old app. Settings Arrange, the Trail page (its content becomes each inspector's "Why" section), the round-numbered CSS prefixes, the separate version chip (r1-designer 4).

## 4. Sitemap and routes

Agreed (r2-architect 3, r2-designer 3, r3-senior-dev R7). Projects is home. The project goes in the path as a readable slug from the folder name, stored in the project registry so it never shifts. Item ids sit in the path. Range sits in the query. The Live session sits in the path. The launch code is read and stripped before the router mounts. Under no project, only Projects shows, so the "Pick a project" dead ends go away.

| Route | Page |
|---|---|
| `#/projects` | Projects (home) |
| `#/p/<slug>/overview`, `/sessions`, `/sessions/<id>`, `/live/<session>` | Usage group |
| `#/p/<slug>/setup` | Setup map |
| `#/p/<slug>/agents/<item>`, `/skills`, `/instructions`, `/settings`, `/permissions`, `/hooks`, `/mcp`, `/plugins` | One surface page each, shown only when its reader ships |
| `#/p/<slug>/to-fix` | To fix, with a worded count in the sidebar |
| `#/reference/decides`, `#/reference/glossary` | Reference group |

Group words. "Usage" is the first group, settled in r3-designer R7 and r3-content R7. Setup, To fix and Reference follow. Final group names and order are for the setup design round to confirm at 375 (r2-designer 3). Judge note on the sidebar. Stack A already uses "This project" and "Reference" as headings (r3-designer hivemind note), so the round may fold the groups under those.

Route rule. Each segment is the glossary slug of the nav label, lowercase English, and a table test ties every registered segment to one glossary key (r3-senior-dev R7). Pages get titles in the pattern "Page, Project, Product name" (r1-content 3, 21-accessibility 2.4.2).

Page set for 1.0. Projects, Overview, Sessions, Session detail, Live, Setup map, surface pages, To fix, Reference. Five designs are new. Projects home, setup map, the surface template, "To fix" and the review rail (r2-designer 3). No command palette.

## 5. Setup view, editing, "To fix", usage and history

### Setup view

Three levels, simple to complex (r1-designer 5, r2-architect 5).
- Level 1, the setup map. One row per surface with the result that runs, such as "Opus 5.5, high" or "6 agents", plus worded status marks.
- Level 2, a Switch labeled "Show where each comes from". It adds scope columns to the same table. At 375 the columns collapse to chips under each row. The switch state lives in the URL query (r3-architect R3).
- Level 3, a surface page. List on the left, inspector on the right. The inspector shows what runs first, then "set to X in file, line N", then why, then usage beside the definition.

Every item shows four things in the same words (r1-content 5). Name, source chip, what applies (leading), and one-sentence why. Example. "Runs at high", then "Set to xhigh in Project local. The effort cap lowers it."

Rules the panel agreed on.
- The seven status words stay the only chips. Confidence ("Based on Claude Code's docs. Not tested on {version}.") goes in the inspector's Why section, not a chip (r2-designer 5).
- Surfaces that combine by name, union or concatenation keep the seven words. The "why" line and a `loads` field (always, on demand with globs, or only when no CLAUDE.md exists) carry the difference. No eighth status (r2-architect 5).
- The Command line layer and Your shell read "not visible here", never empty (r2-architect 9).
- A read-only item always gives the reason and the owner (plugin name, "your organization") in one line, with Copy path (r2-designer 5).
- Where predicted and observed differ, observed leads (r2-content 5).
- Plugin agents show the fields Claude Code ignores for them.
- Chip rows wrap at 375 and never clip. A one-line "why" truncates in the list and shows in full in the inspector (r2-designer 5).

Patterns and criteria (r3-designer R3, r3-architect R3, accepted by both). APG Table with one link per row, not Tree View, because the layers are a stack and nothing nests (WCAG 1.3.1, 2.4.3). Grid only where cells are controls. APG Switch for the scope toggle, because it adds columns and does not swap panels (WCAG 3.2.2). The chip's second line is part of its accessible name (WCAG 2.5.3). "Plugin {name}" truncates visually and keeps the full name in the accessible name.

### Editing flow

One review rail for every surface, with one state machine and one server preview shape (r2-architect 6, 26-01).
- The inspector is in view mode until Edit. Edit shows only when this project's edit key is present. Otherwise a lock line says how to turn editing on.
- States are viewing, drafting, previewing, review, saving, saved, overwritten and failed. The risky confirm state exists in the machine and is held (r3-architect R3).
- Save works only from a server preview. The rail shows the effect first (value before and after, and when it applies), then the diff, then warnings with a field path, then the real path for a symlink. Effect phrases come from the registry as codes: Applies now, in a new session, after restart, after /reload-plugins (r1-content 6).
- Buttons name the action and target, such as "Save to settings.local.json". Edit text is built from templates, not per-field strings (r1-content top concern 3).
- Undo is byte restore with the changed-file refusal. "Undo anyway" shows a diff of what it would erase, inline. Per-file undo plus a project history list meets Nielsen H3 (r2-designer 10, r2-architect "Changed my mind"). Inverse-operation undo waits.
- A user-scope edit names the other projects it reaches (r2-content 6 draft).
- The server enforces the write rule in section 10 item 1.

Risky tier, held for 1.1. Design now, build later. The confirm is inline in the rail. It shows the full command and when it runs, then a checkbox "I read this command" enables a differently worded button placed away from Save. That meets WCAG 3.3.4 and defeats a double-click. At 375 the rail is a full-height sheet, which is an APG Dialog (Modal), and the confirm stays inline inside it (r3-designer R3).

MCP handoff. For local and user scope the page shows the `claude mcp` command with Copy, says the app cannot undo it, shows how to remove the server, and offers "Check again". "Check again" re-reads masked ~/.claude.json on request only. The server never watches, writes or runs it (r2-architect 6, research 20). Judge note. WCAG 3.3.4 does not apply to a page that shows a command, so the need here is Nielsen H5 and H9 (r2-designer 10).

Text editor. CodeMirror 6 loads lazily on Edit, so read-only visits never pay its 193 KB (26-04). Tab stays unbound with an Escape hint (WCAG 2.1.2). The rail round designs the text-body variant either way, so M6b is not a retrofit (r3-designer R1, r3-senior-dev R2).

### After Save (R4, settled)

- "Saved." appears at once with Undo live, announced politely through role status (WCAG 4.1.3). React Aria `announce()` must be passed "polite" (21-accessibility notes).
- The save answer returns the ledger row with `recheck: pending`. The app, not the rail, polls that row at about 2 seconds, then once more if still pending (26-08). Only user settings.json, settings.local.json and .mcp.json are rechecked, because Claude Code writes those (r3-designer R4).
- For those three files a quiet, unannounced check mark may sit beside the saved row. No "Checking" word.
- On overwrite the row shows a persistent warning with what changed, plus "Review changes" and "Undo". It is announced politely and moves no focus (judge, section 10). The item and project history keep the overwritten state afterwards, so a person who left the page still sees it.
- Draft words (r3-content R4). "Saved." and "Saved, but another program changed this file right after. Review it before you go on." [NEEDS CONFIRMATION: whether the recheck can tell if our change survived. If not, use "Another program changed this file after you saved. Your change may be gone."]

### "To fix"

Purpose. It counts problems the person can fix in their own setup, never normal precedence (research 20; r3-designer R6, r3-content R6).

Groups, in this order, and an empty group does not render.
1. Couldn't read. The app could not open the file. Counted or not is O7.
2. Won't load. Claude Code skips the value or file. Counted. A file Claude Code itself cannot parse belongs here (r3-architect R6, no panelist objected).
3. Not as set. The value that runs differs from the one set (Ignored, Lowered, and similar). Counted.
4. Can't tell. The app cannot tell which value wins, including a value newer than the rules. Never counted, with its own heading.

Zero counted problems shows "Nothing to fix", with "Can't tell" still below.

Not in the count (C2, R6). "Claude Code newer than the rules" appears once as a banner on How Claude Code decides and one status line on the setup map. "Rows with no usage" appears beside the history status on usage pages. Both ride the feed as a fourth kind, `notice`, outside every count (r3-architect R6). Server health goes to a status line.

Row pattern (r1-content 7). A title naming the thing and the problem, one cause sentence with file and line, one consequence sentence, one action. Each row carries its fix kind from day one: open the editor at a field or line, send a prefilled operation, copy a command, or "can't fix here" with the reason. In 1.0 a fix button appears only where an editor exists. Elsewhere the row gives the fix in words plus the path (r2-senior-dev 7). The router builds the URL from item id, field path and line.

Codes ship with their collectors. Each code has a rule, a fixture, a cause string and a fix label, and a closed-enum test fails the build on a missing string (r2-senior-dev 7). Draft fix text per code is in r2-content 7 (Invalid, Ignored, Lowered, Skipped file, same-folder clash, shadowed allow, Import).

An unreadable surface keeps its page, shows what did read, and shows an inline error card with the file, the reason and the fix. It is never blank (r1-designer 7).

### Usage and history

- One labeled Select for range, at both widths. Presets are 7 days, 30 days, 90 days, 12 months and All history. The default is 30 days (research 20, r1-designer 8). "Today" is O4. The page intro sentence states the range.
- All history shows where it starts: "All history, since {oldest session}". Help says the dashboard has kept its own copy since the first ingest (r2-content 8).
- Every answer carries `as_of`. Pages show "Updated {time}" and refresh by polling. During the first history read a progress line sits over skeletons shaped like the loaded page (r1-designer 8, r2-architect 8).
- The history status shows the last backup time and says a failed backup in plain words there, not in "To fix" (r3-designer R8).
- Cost note (R5, settled). "Estimated at API list price" appears once per cost card and under the cost KPI, never per figure. No "lower bound" on any figure. Cost help carries one sentence that output cost may be low on some Claude Code versions. The ingest stores `stop_reason` so a conditional note can come later if a spike proves a signal (r3-architect R5, r3-content R5).
- Charts. Hand SVG with `role=img`, a visible title, a kinds table or legend totals, and patterns. The `--rk` contrast exception stays scoped (21-accessibility).
- Live keeps Pause, the polite status line and 1 s polling with an etag. It announces state changes only (WCAG 2.2.2, 4.1.3). The picker is a Select in the Live header, newest first, across projects. Choosing another project's session navigates to that project's Live route, so `/api/live` stays one folder per request (r3-senior-dev R9).

## 6. Words

One glossary, owned by tech-writer as a map keyed by enum value. Each entry has label, second line, definition and banned synonyms (r2-content 9). Strings are typed, so a missing word is a compile error.

Agreed terms (r1-content 9, r3-content R7).
- Scope, never "layer" on screen. Scope chips use the docs names as the label. Who-and-where words are line two (C4): Managed, Command line, Project local, Shared project, User, Plugin {name}, Your shell.
- Instructions (CLAUDE.md, CLAUDE.local.md, AGENTS.md, rules files), never "Memory", which is auto memory in the docs.
- Rules files means `.claude/rules/*.md`. The resolver reference is "How Claude Code decides" (nav and route).
- Seven status words: In effect, Overridden, Ignored, Invalid, Lowered, Default, Unknown.
- To fix, Won't load, Not as set, Can't tell, Couldn't read, Nothing to fix.
- Started by, never "Dispatched by". Never on screen: surface, layer, dispatch, installer. "Pin" appears only inside the routing layer. Core copy asks "Did each agent run on the model its file sets?" (r3-content R7).
- "Not visible here" for layers the server cannot see. "Updated {time}", never "reload the page".

Lint (r1-content 11, r2-senior-dev 9). A value rule catches em dashes, exclamation marks, banned words, Title Case headings and colons inside prose, with a short allowlist of label keys. A key-suffix rule does not work (`_t` on 109 keys, `_h` on 60 of 823). This is untested opinion. Length budgets per key family run in Playwright at 320 and 375. Longest nav label is "How Claude Code decides" at 23 characters.

API speaks codes, page owns words. Server-side prose is limited to rule reason templates in rules.json and quoted doc lines, which tech-writer reviews with strings.json (r1-architect 9).

Narrator ("the dashboard" or "we") and the product name are O5 and O3.

## 7. System needs the UI depends on

Each item is a UX need the panel asked the API to meet (r2-architect 10, r3 files). They go to the architect to fold in before OpenAPI types lock.

- Item shape (26-02 plus registry). Stable id, name, scope, sources, winner, status, reason, `writable`, `read_only_reason` as a code with parameters naming owner, file and line, `risk_tier`, `loads`, `confidence`, `feature` tag, and when a change applies. Frozen in M1 so the design round has real data.
- Field schema per registry field. Type, allowed values and their source, default, doc anchor, and list price for models (usability rule 25). A built-in tools list must be added. MCP tool names stay free text with a pattern check (r2-architect 10).
- Error envelope. One shape with `code`, `path` (for example `["permissions","deny",3]`), `line` and parameters. Front matter errors name their key. Text errors keep the line only. The 422 `input` echo is stripped (26-07). Add a suggestion parameter where known (WCAG 3.3.1, 3.3.3).
- Recheck state. Ledger rows hold `recheck: pending | confirmed | overwritten`, pollable. Overwrite also records which keys changed. Rows carry an optional `app` field (the old reader accepts unknown fields, edit_store.py:796-799).
- Polling. TanStack Query with per-surface etags and `as_of`. The inspector reads the surface etag while the rail is open, to say the file changed under the edit. Ingest and history status give progress as files and bytes done of total. SSE stays a spike (research 20).
- Problems feed. Kinds `problem`, `read_failure`, `cant_tell`, `notice`. Each row has a code, thing, file, line, parameters, confidence and fix kind. Readers return partial results and never fail a page.
- Confidence and visibility. `documented` against `tested` per combiner (only settings combinations have rules evidence: 84 rules, 50 tested, 23 documented, 11 assumed). The command-line layer and each session's shell report "not visible here".
- Session answer. Read access, projects this tab can edit, whether the routing layer is detected. Per-project capability feeds the nav and the rail.
- History status. Oldest stored row, first ingest, last pass, rows with no usage, files kept after cleanup, last backup time.
- Access after reload. Pending O1. Whatever wins, the locked page keeps the requested route and returns to it after unlock (r2-designer 10). Code-swap states are fresh, used, expired, server restarted, and key for another project (r2-architect 13, r2-senior-dev 13).
- Collector contract. `read(project) -> items, diagnostics`, plus `signature(project)` as a stat-only fingerprint for the cache and etag, and `unreadable` with a reason (r2-architect 5). M1 measures the cold cost of the full read on the complex fixture, which is unmeasured.
- Body cap. DRAIN_CAP is 65536 (server.py:141) against MAX_FILE of 1 MiB. Text edits need a larger cap and a new `replace_text` operation.
- Privacy. The ingest schema stores tokens, model, ids, cwd and branch only. A schema test fails if a text column appears (r2-architect 8).

## 8. Testing strategy

Principle. Keep the old suite green on development until cutover. Build the new suite beside it. Port evidence first (r1-architect 11, r1-senior-dev 11).

Port by category.
- Carries over nearly verbatim, about 1,260 methods plus the 123 resolver fixtures. Resolve, rules schema, collect, git_check, json_edit, edit_store, edit_security, transcripts, prices and similar. pytest runs the unittest classes unchanged. A conftest replaces tests/helpers.py. New modules keep flat import names until cutover, which saves 171 mock.patch strings and matches the uv recipe (r2-architect 11).
- Rewritten against the new layer, about 1,060 methods. Old expected values act as the spec.
- Dies. The http.server and fake-DOM JS tests (796 checks). A scout extracts the 258 edit-check names as a behavior list, and workers write component tests from it. The 5,860-line edit_card_checks is not ported.
- New. Hypothesis on json_edit and edit_store. An ingest oracle from the spike 5 reference. A race test from 26-08 with a writer thread rewriting during save and recheck. A committed openapi.json with a drift check. Generated TypeScript types checked in CI. One string per enum value. A named "never delete rows on rescan" test. A restore test that opens the newest backup and compares row counts.

Differential tests (R8, settled). Run the old app under /usr/bin/python3 against the committed fixtures and write JSON payloads. The new tests compare to that JSON. Two conditions keep this honest. A manifest names the old repo's commit sha. An explicit allowed-differences list names every intended change, such as the Unknown group and the seven status words. A diff outside the list fails. Payloads are regenerated by a command and never hand-edited (r3-architect R8, r3-senior-dev R8). They retire with the old app but also serve as real data for design renders (r3-designer R8).

Setup fixture corpus. Committed files for the 123 resolver folders and the demo fixture. One deterministic generator adds sizes (empty, simple, typical, complex) and stress cases (long names, 50 agents, 200 permission rules), checked against committed expected JSON so the generator is not its own oracle. Each surface has a broken twin: bad JSON, bad YAML, symlink, unreadable file, same-folder clash, orphaned plugin version (r2-senior-dev 11).

Front end. Vitest with Testing Library. Playwright with `@axe-core/playwright` tagged wcag22aa. Each row of 21-accessibility becomes an assertion, written once in M3 and run on every page: title, focus on h1, polite route status, scroll-padding for focus-not-obscured, 24 px target size, reflow at 320 and 375, forced colors, reduced motion, text spacing. Add aria snapshots for save, undo, copy and route announcements with a count proving only state changes announce. Add computed-style checks, overflow, target-size and rendered-contrast scans (skipping clip-hidden text). Add keyboard-only scripts for the five jobs, a pointer-free drag alternative check, and a real double-click on every swapped confirm.

Screenshots (R8, settled). Pixel baselines do not gate. A fixed capture set goes to the designer's review each milestone against the picked direction.

Tiers (r1-senior-dev 11, r2-senior-dev 11).
- T1, the changed area, seconds, run by the worker.
- T2, all new pytest plus Vitest, typecheck and lint, about 2 to 3 minutes, run by the lead and in CI on Linux. Touched routes at 375 and 1440, light.
- T3, the full axe and Playwright matrix at 320, 375 and 1440, light and dark, at milestone end. The old 370 second suite runs only when old files change. Never run a Claude Code harness batch as a check (T-07ef).

Manual passes, planned as owner or designer checks. VoiceOver at M3, M6 and cutover, charts included. Help and error text quality (WCAG 3.3.3, 2.4.6) read by the owner each milestone with tech-writer. Focus order sanity. Chart tooltip dismissal (WCAG 1.4.13). The risky confirm's clarity when it ships (r2-senior-dev 10, r2-designer 10).

Platform note. CI runs on Linux. flock and directory-descriptor tests work there. APFS case traps stay local on macOS (r2-senior-dev 11). CI minutes are an owner question (O6).

## 9. Milestones

I merged the architect's and senior developer's lists. The architect took the senior developer's M0 (r2-architect 12). The senior developer's table drives the order because it carries the UI milestones and the design gates. The architect's risky tier and groups became release 1.1 and 1.2.

New code lives in a top-level `app/` folder (`app/server`, `app/web`), outside the plugin payload until cutover, run by uv on a high port, never 8377. One PR per milestone. The old app stays on development in bug-fix mode as the oracle. Both apps share the backups folder and flock covers both writers. Group edits stay off until cutover (old pruning, RETENTION 20, knows no groups). The new UI carries a visible "New dashboard (preview)" label until cutover (r2-content 12).

Two design rounds (R2, settled). Designer renders two or three directions per round at 375 and 1440, from recorded payloads and with tech-writer's words, then the owner picks. Each round starts from drafted data shapes and returns a short list of UX needs before types lock (r3-architect R2).
- Setup round. Starts when M1 drafts the item and map shapes. Covers setup map, surface template, inspector, "To fix", sidebar and project picker, Projects home. Pick due before M3's shell work on the sidebar, and no later than the start of M4 UI.
- Rail round. Runs in M4 and M5. Covers the rail, field editors, the text-body variant, the overwritten state and the read-only line. Pick due before M6 UI. A later short round covers the risky confirm before 1.1.
- Pick deadline. If the owner has not picked when the backend half is done, the backend merges behind a feature flag and only that UI waits (r3-senior-dev R2).

Cost estimates are mine, not from the dashboard's cost per run [NEEDS CONFIRMATION: dollars per milestone, which the dashboard data would replace]. I scaled the senior developer's effort weights (r1-senior-dev 12) to rough list-price ranges. Leads are `deep-reasoner` (Opus, high). Workers are `fast-worker` (medium; pass high for risky or tricky tasks such as M1 and M6). Scout does inventories and test runs. Judge does Chrome checks. Verifier is Opus. Only one lead runs per working tree.

| M | What it proves | New UI | Design and owner picks | Copy deck (tech-writer, medium) | Dispatch plan | Est. cost |
|---|---|---|---|---|---|---|
| M0 | Walking skeleton through the real launcher and a built payload with tracked dist. Spikes. Single-use code swap, SessionEnd with a shared server, json_edit array insert, ruamel byte-equality, backup, CI. Glossary. | First-run, code-swap, locked-tab, server-stopped states | Owner decides O1, O3, O6 before M0 ends | Glossary pass, first-run, code swap, locked tab, server stopped | Lead plus 2 workers, 1 scout | $20 to $40 |
| M1 | Pure core ported (resolver, rules, collect, prices, transcripts parser, edit_store, json_edit), ASGI gate, project registry, keys, item and map shapes frozen with the cold-read measurement | None | Setup round starts | None | Lead plus 3 workers (high on gate and edit_store), scout for test runs | $40 to $80 |
| M2 | SQLite ingest, usage query API, history status, backup job, differential harness, no row loss on rescan. Runs beside M1 only in a second worktree with the owner's yes | None | Setup round runs | History copy | Lead plus 2 workers, scout | $25 to $50 |
| M3 | Shell, tokens, charts, usage pages, Projects home, accessibility harness on every route. Matches the old totals | Yes (shell, usage) | Setup pick due. VoiceOver pass | Usage copy | Lead plus 4 workers, judge for browser checks, designer review | $70 to $130 |
| M4 | Setup read side, collectors, setup map, surface pages, "To fix" feed and page, reference pages | Yes (setup UI) | Rail round runs | Surface copy, fix text per code | Lead plus 3 workers, scout, designer review | $40 to $80 |
| M5 | Live and the dispatch canvas on a fake clock, session in URL, cross-project picker, routing layer (judge placement) | Yes (Live, routing layer) | Rail round pick due | Live copy | Lead plus 2 workers, judge | $25 to $50 |
| M6 | Edit core in the new stack. Registry, preview shape, rail, four keys, agent model and effort, backup and undo, writable allowlist, recheck. The data-safety milestone | Yes (rail) | VoiceOver pass. Verifier here | Edit templates, error codes, saved and overwritten | Lead plus 3 workers (high), scout, verifier | $50 to $100 |
| M6b | CodeMirror text editor for CLAUDE.md, rules and agent bodies, body cap, front matter byte compare | Yes (text variant) | Owner may cut at the M6 gate | Text editor copy | Lead plus 2 workers | $20 to $40 |
| M7 | Cutover. Parity matrix, differential green, a week of owner use on real data, plugin payload swap, README rewrites | Label removal | VoiceOver pass. Verifier here | README and plugin README | Lead plus 1 worker, scout, verifier | $15 to $30 |

Totals (estimate). Milestones $305 to $600. Two design rounds $30 to $60. Six copy decks $18 to $60. Verifier passes $30 to $75. Scouts and judge checks $10 to $20. Overall roughly $400 to $800. The cost gate puts any plan above about $20 total before the owner (model routing rule), and each lead above about $5 as well. Judge note. The memory note says the owner accepts overruns and wants totals reported, not nagging, so I state the gate once and move on.

Cutover details (r1-senior-dev 12). Entry needs a parity matrix, differential tests green, Playwright and axe green, and a week of owner use. Only the owner touches real ~/.claude. At cutover build_plugins takes the new payload list, plugin.json goes to 0.2.0, the old `dashboard/` leaves the payload list, and a git tag marks the last old release. Rollback is the tag plus the old plugin version, safe because the backups and ledger stay compatible. Old code is deleted one release after. The ledger, backups and project list carry unchanged. The database starts empty and ingests whatever transcripts still exist, so history begins at first run, and the owner is told plainly.

## 10. Settled by the judge

1. R1, classifier and skills. The architect's smaller server rule ships in M6 and M6b. Every operation must target a registry field marked writable, and `replace_text` on an agent file must leave front matter bytes unchanged. Refusals name the field in plain words. The full tiered classifier and `risk.ack` come with the first risky surface in 1.1. Reason (judge): 1.0 never edits settings.json as raw text, so no hook is reachable, and the allowlist plus byte compare is cheaper than the classifier and closes the same hole. This meets the designer's concern and the senior developer's "classifier with the text editor". Skills text waits for 1.1 because skill bodies can hold `!cmd` lines that need the classifier (r3-architect R1).
2. R1, deny and ask rules. Out of 1.0 by default. The M0 array-insert spike still runs. If it passes and M6 has slack, the owner can pull them in at the M6 gate. Reason (judge): the architect conceded them out and the senior developer conceded them in only if the spike passes, so a gate fits both.
3. R1, M6b. In 1.0, and the owner may cut it at the M6 gate if the schedule slips. Reason: an inspector that shows a body with no way to edit it is a dead end (usability rule 18, H3), and the senior developer asked for the cut lever.
4. R1, delete. Out of 1.0 (r3-designer R1 conceded). It needs group undo.
5. R2. Two design rounds gate UI milestones and run beside backend work (all three agree). The setup pick lands before M3's sidebar work if possible and no later than the start of M4 UI. Reason (judge): this keeps the designer's sidebar concern and the senior developer's critical-path rule.
6. R3. Table, inline confirm, Switch, Alert Dialog for delete only. The architect moved to the designer (r3-architect R3).
7. R4. "Saved." at once, no visible "checking", persistent overwrite warning, polling. All agree. One difference: the designer wants role alert for the overwrite and the architect and content want polite. I chose polite plus a persistent visible warning. Reason (judge): the person may be typing elsewhere, and WCAG 4.1.3 allows either.
8. R5. No per-figure label. One "may be low" sentence in cost help. A conditional note waits for a spike that proves the undercount signal (r3-architect R5, r3-content R5, r3-designer R5 fallback). Reason: 26-06 found final output counts on 2.1.302.
9. R6, version gap and no-usage rows. Both outside "To fix" (all four). A Claude Code parse failure goes to "Won't load" (r3-architect R6).
10. R7, routes. New path scheme, reference at `#/reference/decides` and `#/reference/glossary`, "pin" only in the routing layer, group word "Usage" (r3-content R7). Judge choice on the segment: content and senior developer said `/decides`, the designer and architect said `#/reference` as an example.
11. R7, redirect map. None. Old links already die with the single-use code (r3-senior-dev R7), and the locked page keeps the requested route. An unknown route shows Projects with a short "That link is out of date" line. Reason (judge): the architect's concern is bookmarks, and those carry no valid code. This is cheap to reverse.
12. R8, backup. The server's single ingest writer runs SQLite's online backup at start if the last copy is over 24 hours old, after the first ingest pass of each day, and at clean stop if rows changed. It runs `PRAGMA quick_check` before rotating out the oldest copy and keeps seven copies, and a test restores the newest copy. The architect and senior developer each conceded the clean-stop point to the other, so they ended on opposite sides. Reason (judge): clean stop costs little and is best-effort, while the daily and start triggers cover the case where SessionEnd kills the server first (L-2116).
13. R9. Replay and a cross-project sessions page wait. The cross-project Live picker and the session in the URL ship in 1.0 (r3-designer R9, r3-senior-dev R9).
14. C1. A not-yet-editable item states the reason and the real path, with no promise (all four after r3-architect C1).
15. C2. "Can't tell" is a separate uncounted group.
16. C3. Models folds into Overview in M3. Reason (judge): content dropped the page as a repeat, and building a page to remove it is waste in a from-scratch build. The designer had said "later"; this is a mild override.
17. C4. Docs scope names are the chip label and who-and-where is line two (r3-designer C4, no objection).
18. Access reload and user-scope edits stay with the owner (O1, O2).

## 11. Owner decisions

### O1. Access after reload, new tab and deep link
- Option A. Key in memory only, as research 23 B2 said.
- Option B. sessionStorage per tab, BroadcastChannel handoff to new tabs, and a launcher command that mints a fresh code for the running server. The locked page keeps the requested route.
- For B (designer, architect, senior developer). Without it a reload, a new tab or a deep link loses even read access, which breaks H3 and H9 daily. The old app already used sessionStorage (edit_session.js:4-7).
- For A. The key never sits in browser storage (judge's reading of B2; the panel did not restate B2's reasons).
- Lean. B. Decide before M0 ends, because the gate and every locked state depend on it. Whether Chrome copies sessionStorage into a tab opened from the page is unverified (r1-architect 13).

### O2. User-scope edits under per-project keys
- Option A. The preview names the other projects the edit reaches, and nothing more.
- Option B. A stricter rule, such as an extra confirm or a separate user-scope key.
- For A (architect, senior developer). One key per project is already decided, and a named effect meets the need cheaply.
- For B. Any project's key can change ~/.claude/settings.json, which every project reads.
- Lean. A for 1.0. The architect asked the owner to say if they want more.

### O3. Product name
- Option A. Keep "Routing Dashboard" for the whole app.
- Option B. Give the core app a new name and keep "Routing Dashboard" for the optional layer.
- For B (content, alone). The name now describes only the optional layer, and titles, strings and the slash command fix it.
- For A. No one else spoke to it. It avoids a rename in the launcher and plugin.
- Lean. None from the panel. Decide before the M0 glossary pass.

### O4. A "Today" range preset
- Option A. Add it (content). Stack A shows Today.
- Option B. Leave it out (architect). Research 20 omits it and Live covers today.
- Designer. Owner call.
- Lean. None. Judge's view: leave it out of 1.0, since a preset is cheap to add later.

### O5. Narrator in copy
- Option A. "The dashboard" (content's lean), as in "The dashboard can't tell which value wins."
- Option B. "We."
- Lean. A. Only content spoke.

### O6. Build and supply chain
- Items. A Python 3.9 launcher with a 3.11+ backend and two test environments until cutover. Committed Vite output at milestone ends with a drift check, and a looser dev CSP. Linux CI on GitHub Actions. Locked installs (`npm ci`, exact pins, `ignore-scripts`, `uv sync --frozen`).
- Senior developer's case. The launcher runs on whatever python3 starts it and the committed bundle changes every build. Nobody answered in round 2 (r2-senior-dev 13).
- Open. Actions minutes depend on repo visibility and plan [NEEDS CONFIRMATION]. Local Node is 20.19.6, so Node 24 needs an nvm install.
- Lean. Accept the senior developer's set. Cost is the owner's call. Needs an answer for CI in M0.

### O7. Does "Couldn't read" count in "To fix"?
- Option A. It counts (designer, content). An unreadable file hides every problem behind it, so the badge should say so. Zero would be false comfort (H2, H8 on alarm balanced against this).
- Option B. It is listed first but uncounted, with its own number in the heading (architect). It holds only the app's limits, such as no permission or a file over the size cap, so counting it alarms people for no fault of their setup (H2).
- Agreed either way. Claude Code parse failures go to "Won't load", which counts.
- Lean. A, two of three. Judge suggestion if the owner wants a middle path: count permission and encoding failures and leave size-cap limits uncounted. That adds a code split the panel did not discuss.

## 12. Risks and open questions

Risks.
1. Scope against capacity (r1-senior-dev top concern 1). The decisions describe four products. The 1.0 cut and the M6b cut lever are the controls.
2. Packaging found late (r1-senior-dev top concern 2). The launcher, uv recipe, tracked dist, nonce, code swap and shared-server lifecycle meet at the plugin boundary. M0 builds the whole path first.
3. Data loss in editing (r1-architect top concern 2). Byte restore can erase Claude Code's later writes, which the changed-file refusal, the recheck and the shown diff on "undo anyway" address. Groups cannot be atomic, so they wait.
4. "What runs" can overclaim on the new surfaces (r1-architect top concern 3). Only settings has tested rules. Confidence stays in the inspector and "not visible here" stays explicit.
5. Losing behavior in the port (r1-senior-dev top concern 3). Mitigated by the behavior inventory, recorded payloads and the allowed-differences list.
6. Design lag. No benchmark exists for setup and edit screens (r1-designer top concern 1). Mitigated by the two rounds and the pick deadline.
7. Words drift. Three app terms clash with Claude Code's glossary (r1-content top concern 1). Mitigated by the glossary, typed keys and the lint.
8. Cost. Roughly $400 to $800 list price, a rough estimate that needs the dashboard's per-run data.

Open questions.
- Array-insert spike (json_edit.py:281, 369) and ruamel byte-equality are not done. The single-use code swap and uv SIGTERM with a shared server also need spikes (r1-senior-dev 12).
- Can the post-save recheck tell whether our change survived? The interval is a guess (26-08 line 62). [NEEDS CONFIRMATION]
- Does a missing `stop_reason` mark an undercount reliably? 26-06 line 20 saw `end_turn` copied onto every row of a reply, so the signal is untested (r2-architect 8).
- Cold cost of the full setup read on the complex fixture is unmeasured. M1 measures it.
- Offline OpenAPI export is unverified (26-07).
- React Aria's touch-action style under the nonce CSP is untested (research 20 spike 3).
- Preferences (theme) need a write route, and its key rule is undecided. A `color-scheme` meta comes first (r2-architect 13, r1-designer 13).
- Whether the project registry needs a separate display name beyond the slug [NEEDS CONFIRMATION] (r2-content 3).
- Manual-only rows are planned as owner checks. The panel's claim that automation finds about 57 percent of issues is vendor data (21-accessibility).
- The verifier pass on Opus, then Fable, is still ahead (agenda step 5). I read panel files and the two givens only, and I did not open the old code or the Claude Code docs.

HIVEMIND
NEW dashboard: The planning panel ended R8 backup trigger on crossed concessions (architect adds clean stop, senior developer drops it), so the judge's plan sets all three triggers (start over 24h, after first daily ingest, clean stop if rows changed). | check: grep -n 'clean stop' docs/rebuild/planning/r3-architect.md docs/rebuild/planning/r3-senior-dev.md | evidence: docs/rebuild/planning/r3-architect.md, docs/rebuild/planning/r3-senior-dev.md
END HIVEMIND

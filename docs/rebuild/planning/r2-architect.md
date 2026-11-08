# Round 2 responses, architect

Written 2026-11-08T11:19-05:00 by the architect (deep-reasoner). Code paths are in /Volumes/Warehouse/Projects/claude-code-model-routing. Research paths are in docs/rebuild/. One scout checked browser storage facts on MDN (cited as "scout, MDN" with URLs).

## 1. Purpose and audience

Agree. Content and designer, one reader who knows Claude Code but not its precedence rules.

Push back. None on audience. Designer's five walkthroughs and my machine checks are two halves of one "done" list. Keep both.

Answers.
- Designer, is "a stranger's setup" the right test? Yes. The fixture corpus needs one setup with no routing install, and release 1 passes on it. The owner decided the app reads anybody's setup, with the install as an optional layer (research/20-decisions.md, after the gap research).
- Content, does the API flag routing-layer items? Yes. Each item and field carries an optional `feature` tag (for example `routing`), and the session answer says whether the layer is detected. Copy then never needs a string-level check.

## 2. First-release scope

Agree. Designer, hold the risky tier one milestone. Senior developer, a hard cut is needed.

Push back. Senior developer, four settings keys can't prove the registry. All four are scalars in one JSON file (api_edit.py:303-308, four entries, not five). They never touch array operations, which 26-01 calls "the main new core code", nor front matter, text or create. Agent model and effort add a YAML file, which helps. My cut for 1.0 is every schema-typed scalar key, `deny` and `ask` rules (safe tier, and they prove `insert_item`), agent fields, and CLAUDE.md and rules text. CodeMirror loads as a lazy chunk on Edit, so its 193 KB never reaches a read-only visit (opinion on cost). Designer, single-file delete fits 1.0, but a skill folder is a group and waits.

Answers.
- Designer, does holding risky leave the API unfinished? No, with one catch. The risk classifier must ship in 1.0 anyway. "Edit as text" on settings.json can add a hook, and 26-01 judges risk from the parsed before and after. In 1.0 the server refuses any change that touches a risky key, with a "not editable yet" code. `risk.ack` stays null until the risky milestone.
- Senior developer, second surface type? Yes. Front matter and one array surface, as above.

## 3. Sitemap and navigation

Agree. Designer and content, Projects is home, project and item in the path, range in the query, no "Pick a project" pages.

Push back. Senior developer, keeping current route names saves little. router.js is rewritten for React Router anyway, recorded payloads are API answers, not routes, and project-in-path changes every route.

Answers.
- Designer, can project ids be stable and readable? Yes. A slug from the folder name, with a suffix on a clash, stored in the project registry so it never shifts. The launcher's sha1(realpath)[:12] id stays internal (research/19-launcher.md).
- Designer's worded count in the sidebar comes from the same cached setup summary as point 5, so it costs no extra call.

## 4. Current app, keep and change

Agree. Senior developer, the old app is the oracle until cutover. Designer, the keep, change and drop list.

Push back. Nothing to add.

Answers. None addressed to me.

## 5. Setup view

Agree. Designer, three levels and a table, not a node graph. Senior developer, build collectors before the map. Content, four things per item in the same words.

Push back. Senior developer, the map's summary shape should be fixed in M1 even though the map is built later, so the design round has data to draw.

Answers.
- Senior developer, collector interface. Agree with `read(project) -> items, diagnostics`. Add `signature(project)`, a stat-only fingerprint for the cache and the etag, and return the 26-02 item shape with `confidence` and `writable` plus `read_only_reason`.
- Designer, level 1 from one call? One call, but it runs every reader, because counts come from each surface. A warm call checks stat signatures only. The cold cost on the complex fixture is unmeasured, so M1 measures it.
- Content, an eighth status for on-demand files? No. Keep seven statuses and add a `loads` field (always, on demand with its path globs, or only when no CLAUDE.md exists), per 26-02's memory row. The "why" line words it.

## 6. Editing flow

Agree. Designer, effect first, then diff, with a confirm button away from Save. Content, buttons name action and target. Senior developer, port edit_store's write path nearly verbatim.

Push back. Content, the registry should carry codes, not words. Display name, plural and effect verb live in strings keyed by surface and field id, and `effect.applies` stays an enum. Same templates, one home for words.

Answers.
- Designer, field paths? Yes, small API work. Each validation item gets `path` (for example `["permissions","deny",3]`) beside `line`. JSON Schema validators report a path per error, front matter errors name their key, and text errors keep the line only.
- Designer, recheck as an event? Delivered by polling. The save answer returns the row with `recheck: pending`, and the rail reads that row about 2 seconds later (26-08). The decisions set polling as default (research/20-decisions.md lines 33 and 37).
- Content, does the page learn the MCP command ran? Only when the person asks. "Check again" re-reads `.claude.json`, masked, and reports whether that name now holds that config. The server never watches it, because the owner ruled the app never writes or runs it (research/20-decisions.md, round 3).

## 7. "To fix" and diagnostics

Agree. Designer, group by thing, then "Won't load" before "Not as set". Content, one row pattern.

Push back. Senior developer, a fix button only where an editor exists is right for 1.0, but the row shape should carry its fix kind from day one, so new editors light up rows without a schema change.

Answers.
- Designer, can each problem route to the fixing view? Yes. The fix carries item id, field path and line. The router builds the URL, because the API returns ids, not routes.
- Content's "Unknown" question, system view. The feed already separates `problem`, `read_failure` and a third kind, `cant_tell`, for values newer than the rules. Grouping is the designer's call.

## 8. Usage and history

Agree. Designer, one Select and the cost note once per card. Senior developer, online backup and never deleting rows on rescan.

Push back. Content, "Today" isn't in the owner's preset list (research/20-decisions.md, round 3), and Live already covers today. The owner decides.

Answers.
- Designer, `as_of` on every answer and the stored start date? Yes. Ingest progress as a count? Yes. The scan lists files first, so it knows "files and bytes done of total".
- Content, lower bound. 26-06 found the final output count in the transcript on 2.1.302 streaming, against a fake API. The lower-bound claim rests on older, closed issues (25-verifier-gap-research.md line 5). "At least" on every figure overclaims. I propose the API counts requests with no final `stop_reason` (25 item 2 asks to store it), and the note appears only when that count is above zero. Inference, untested.
- Content, no message text? Confirmed. The spike schema stores tokens, model, ids, cwd and branch only (26-05, "Schema summary"), matching the footer (strings.json:470). A schema test should fail if a text column appears.
- Senior developer, who owns the backup? The server's single ingest writer. It runs a backup after the first pass of each day and at start if the last one is over 24 hours old. It never depends on SessionEnd.

## 9. Words and content

Agree. Content, one glossary, Claude Code's scope names, and keep "surface", "rules" and "dispatch" off screen. Senior developer, typed keys.

Push back. Content, the "Command line" chip can't show a value. The server never sees `--settings` or `--effort`, so that row reads "not visible here", never empty. Content owns those words.

Answers.
- Content, codes not echoed text? Yes. One envelope with code, path, line and parameters. The 422 `input` echo is stripped (26-07, tests 2 to 4).
- Senior developer and content, one mechanism. OpenAPI enums become TypeScript unions, and strings typed as `Record<StatusCode, string>` make a missing word a compile error.

## 10. UX standards check

Agree. Designer, the table and the four added criteria (SC 3.3.4, 3.2.2, 1.4.13, 2.1.2). Senior developer, checklist rows become Playwright assertions.

Push back. Designer, "events" should be read as polled state, not push. The decisions keep server-sent events (SSE) as a spike only (README.md line 12; research/20-decisions.md line 33). Polling still meets Nielsen H1 if the poll is cheap.

Answers to the designer's four gaps.
1. Access on reload. Not covered. API work plus an owner call. I propose three layers. sessionStorage holds the keys per tab and "survives over page reloads" (scout, MDN, https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage). A new tab gets an empty one, so an unlocked tab hands the keys to a new tab over BroadcastChannel, which is same-origin only (scout, MDN BroadcastChannel). With no tab open, the locked page names the launcher action that mints a fresh code through a 0600 control file. This changes research B2 "memory only" (23-domain-carryover.md), so the owner decides.
2. Field paths on errors. Not covered today. Small API work (point 6).
3. Page events. Partly covered. Three needs, each by poll. File changed while editing uses a per-surface etag compared to the preview's base while the rail is open. Overwrite after save uses the ledger row's recheck state. Ingest progress uses the history status answer. The page turns state changes into polite announcements (SC 4.1.3).
4. Option lists for pickers. Half covered. Today each setting has `levels(ctx)`, and models come from the rules.json catalog (api_edit.py:247-253, 299-308). Generalize that into a field schema per registry field, with type, allowed values and their source, default, doc anchor, and list price for models (usability rule 25). One gap is that no vendored file lists Claude Code's built-in tools, so the tools picker needs one. MCP tool names stay free text with a pattern check.

Other answers.
- Senior developer, manual-only rows from my side. Screen reader wording and order, diff reading order, the rail's focus order, and clarity of the risky confirm. Opinion.
- My cross-file undo row stands unanswered. I hold that per-file undo plus a project history list meets H3.

## 11. Testing

Agree. Senior developer, unittest classes run under pytest unchanged, tiers T1 to T3. Designer, one corpus generator with size and breakage flags.

Push back.
- Senior developer, the differential test can't import old and new code in one process if both keep flat names. Two `resolve` modules clash on sys.path. Capture old answers by running the old app under /usr/bin/python3 into recorded payloads, then compare.
- Designer, screenshot baselines shouldn't gate merges. Aria snapshots and computed styles gate, and screenshots go to the designer's milestone review. This sides with the senior developer.

Answers. Senior developer, flat import names until cutover? Yes. It matches the uv recipe, `package = false` with PYTHONPATH set to the payload (research/20-decisions.md, spike 2), and saves all 171 mock.patch strings.

## 12. Build order and coexistence

Agree. Senior developer, M0 as a walking skeleton through the real launcher and built payload. Designer, a direction round before setup read and before edits. All three orders put usage first, because its benchmark exists.

Push back. Designer, the "new dashboard" label helps, but backups need it in data. Add an optional `app` field to ledger rows. The old reader accepts unknown fields (edit_store.py:796-799).

Answers.
- Designer, can the read side ship before the edit API? Yes, if M1 fixes the item shape with `writable`, `read_only_reason`, `risk_tier` and the field schema. The inspector shows Edit as off until edits land.
- Senior developer, folder name. `app/`, with `app/server` and `app/web`, is fine.
- Senior developer, owner count for one server. The launcher already keeps an owners list per server record (plugins/routing-dashboard/bin/routing-dashboard:476-544). One server re-keys the record by data folder, and the stop rule becomes "no owners in any project". No new lease.
- Content, how many milestones? Eight (M0 to M7), with copy decks for usage UI, setup read and edits, plus a glossary pass in M0.

## 13. Open floor

Agree. Senior developer, Python 3.9 launcher, supply-chain pins and builds committed at milestone ends. Content, the product name is the owner's call.

Answers.
- Designer, what belongs in 1.0? First-run states, yes, since they need only the history status and project list. Theme needs a preferences write route, whose key rule is still open. Jump-to and CSV export can wait, and the read model makes both cheap later.
- Content, code swap states from the system side. Fresh, used, expired, and dead because the server restarted. A restarted server may take a new port, and then the old link fails before the page loads.

## Changed my mind

- Undo. I drop inverse-operation undo from release 1. Byte restore with the changed-file refusal stays, and "undo anyway" shows a diff of what it erases. That meets SC 3.3.4 at far lower test cost.
- M0. The senior developer's walking skeleton replaces my M0.
- Output cost. I said every answer flags output as a lower bound. 26-06 weakens that, so a count of possibly undercounted requests replaces the blanket flag.
- Settings scope. "Every key" becomes every scalar key the schema types. Object keys such as hooks and statusLine are risky and wait.

## Debate list

| id | point | question | my side | who disagrees |
|---|---|---|---|---|
| D1 | 2 | How much editing ships in 1.0? | Scalar settings, deny and ask rules, agent fields, markdown text with lazy CodeMirror | Senior developer (four keys plus agent model and effort, no text editor); designer (adds delete and skills text) |
| D2 | 2, 6 | Must the risk classifier ship in 1.0 with risky held? | Yes, or raw-text edits can add hooks unconfirmed | Senior developer (enforcement only with the first risky surface) |
| D3 | 10, 13 | How does access survive reload, new tab and deep link? | sessionStorage, BroadcastChannel handoff, launcher mints a code | Research B2 (memory only); owner decides |
| D4 | 10 | Are page "events" push or poll? | Poll with etags and row state, SSE stays a spike | Designer (asked for events) |
| D5 | 11 | Do screenshot baselines gate merges? | No, review only | Designer |
| D6 | 3 | Keep current route names? | No, the scheme changes anyway | Senior developer |
| D7 | 9 | Chip label: docs scope names or who-and-where words? | Docs names, with who-it-affects as the second line | Designer (who-and-where as label) |
| D8 | 7 | Does "Unknown" count in "To fix"? | Separate `cant_tell` kind, outside the count | Designer's two groups; content raised it |
| D9 | 8 | How to label output cost? | Note only when undercounted requests exist | Content and 25-verifier ("lower bound" per figure) |
| D10 | 8 | Add a "Today" preset? | Not in 1.0, Live covers it | Content |
| D11 | 11 | Differential tests in one process or via recorded payloads? | Recorded payloads from the old app | Senior developer (in-process implied) |
| D12 | 10 | Is per-file undo plus history enough for Nielsen H3? | Yes | Nobody yet, raised only by me |
| D13 | 13 | Is naming other projects in the preview enough for user-scope edits under per-project keys? | Minimum; owner may want more | Raised only by me |

HIVEMIND
NEW dashboard-settings: Today's editable settings are four entries in api_edit.SETTINGS (SETTING, CAP, model, COMPACT), each with a `levels(ctx)` value list; model values come from the rules.json models catalog (api_edit.py:247-253, 299-308). | check: sed -n 303,308p /Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/api_edit.py | evidence: dashboard/api_edit.py
NEW dashboard-plugin: The launcher already tracks an owners list per server record and stops a server left with none (plugins/routing-dashboard/bin/routing-dashboard:476-544). | check: grep -n 'owners' /Volumes/Warehouse/Projects/claude-code-model-routing/plugins/routing-dashboard/bin/routing-dashboard | evidence: plugins/routing-dashboard/bin/routing-dashboard
END HIVEMIND

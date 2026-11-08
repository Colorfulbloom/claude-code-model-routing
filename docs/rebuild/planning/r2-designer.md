# Round 2 responses, designer

Written November 8, 2026 (11:16 EST) by the designer. I read brief.md, my r1-designer.md and the three other r1 files. I checked claims against the code, the Stack A boards in `docs/design/usage-stack/a-usage/`, research/21-accessibility.md and MDN. I did not run the app. Any wording below is a placeholder for tech-writer.

Short names follow round 1. Nielsen H1 to H10, WCAG 2.2 SC numbers, APG pattern names, D20 for research/20-decisions.md, "usability rule N" for `~/.claude/designer/usability-for-apps.md`.

## 1. Purpose and audience

Agree: content specialist, one reader who knows Claude Code but not its precedence rules, and the intro line answers the page's question. Architect, "done" stated as checks a test can run.

Push back: architect and senior developer, both "done" lists are system checks only. Neither proves a person can finish a job. Keep my five keyboard-only job walkthroughs beside them, run on the fixture corpus at 375 and 1440. A route can pass axe and still strand a cold reader, as Needs attention does today with 13 rows of mostly normal precedence (`shots/12-attention-1440-light.png`, design.md U7). Nielsen's own advice is that heuristics do not replace task tests (H1 to H10 are inspection, not testing).

Answers: content specialist, yes. The intro answers the question in one sentence. Stack A already does this ("Usage in Tidewater reporting over the last 30 days, read from its transcripts", `01-overview-light.html`).

## 2. First-release scope

Agree: architect, release 1 reads everything and edits one file per operation, with groups and delete later. Senior developer, the registry and preview shape must be right on day one.

Push back: senior developer, editing only five keys plus agent model and effort makes the Instructions page read-only in release 1. CLAUDE.md and rules files are the setup a person changes most (opinion), and an inspector that shows a body with no way to change it is a dead end (usability rule 18, H3). CodeMirror is lazy-loaded per route, so its 193 KB does not touch first paint (26-04). I side with the architect's release 1, text edits included.

Architect, "Editing comes in the next release" on a risky field is promise copy, and the content specialist rightly bans it. The read-only line should give the reason and the real path with Copy path, so the person can still act.

Answers: architect, yes, a risky field can show read-only in release 1. It shows the full command, the file and line, and Copy path. No promise. Owner decides the order.

## 3. Sitemap and navigation

Agree: architect, the project slug in the path, item ids in the path, range in the query, Live session in the path, launch code stripped before the router mounts. Content specialist, "Usage" as the group word and "Instructions" over "Memory".

Push back: senior developer, keeping today's route names saves little. The Trail page goes, eight setup pages are new and Live gains a session segment, so most routes change anyway. Keep the usage route names, which carry the recorded payloads, and use the new scheme for the rest.

Answers:
- Architect, yes, Projects is home. The nav shows one worded count on "To fix" only. Per-surface counts live on the setup map, which loads the problems feed anyway. So the nav needs one cheap total per project, not the feed.
- Architect and content specialist, slug from the folder name, display name on screen. A readable slug helps a person recognise a pasted link (H6).
- Content specialist, keep one Setup group, setup map first, then pages in order of how often people open them (usability rule 6). Ten links under one heading scan fine in a sidebar. Revisit once the direction round renders it at 375.
- Senior developer, one list-and-inspector template with a surface prop serves every surface page. New designs needed for release 1 are five. Projects home, setup map, the surface template, "To fix" and the review rail.

## 4. Current app, keep and change

Agree: everyone, carry the usage pages and Live as they are and use the old app as the oracle (senior developer). Content specialist, keep the voice and its patterns.

Push back: none.

Answers: senior developer, required for 1.0 on usage and Live are only the accessibility fixes and the stale-data fix. That is route title, focus and announcement (A1, A2), the phone table (A4), the drawer scrim (A5), the Live chip over a card (A8, `crops/live-overlap.png`) and "Updated" in place of "Reload the page to update" (U9). Not required and movable later are folding Models into Overview, the session detail replay, one model order per page and chart dedupe.

## 5. Setup view

Agree: architect, one read model for map, catalogs, pages and "To fix". The "not visible here" layer for the command line and the shell, and a label for observed against predicted. Senior developer, collectors first, map after.

Push back: none on structure. One design note for the architect's concern 3. Confidence ("documented, not tested") belongs in the inspector's Why section, not as an eighth chip. The seven status words stay the only chips (Reuse first, project Design section), and facts stay quiet (my "facts quiet, checks loud" lesson).

Answers:
- Architect, writable plus a read-only reason code with parameters is enough, if the parameters name who owns the value (the plugin name, "your organization"). Then the line can say where to change it. No free-text fix needed.
- Content specialist, yes, a one-line why fits under each row at 375 if it truncates to one line in the list and shows in full in the inspector. Chip rows must wrap, never clip (my "chip rows wrap" lesson).

## 6. Editing flow

Agree: architect, the state machine, Save only from a server preview, inverse-operation undo, per-file outcomes for groups, and naming the other projects a user-scope edit reaches. Content specialist, button labels name action and target, and "Applies now" style phrases come from the registry.

Push back: architect, the rail should not hold a 2-second "checking" state before "saved". The save succeeded, so say so at once and keep Undo live (H1). The recheck runs quietly. Only an overwrite earns an announced warning beside the item, with what changed and its actions. A blocking spinner after every save trains people to ignore it.

Answers:
- Architect, yes to the recheck state, with the change above.
- Content specialist, checkbox. A checkbox labeled for reading the command enables a differently worded confirm placed away from Save. Typed names suit irreversible deletes (GitHub repo delete). Here the file change is undoable, and the thing to prove is that the command was read. The double-click test from round 1 still applies.
- Senior developer, the rail cannot do without these fields. Effect before and after with when it applies, the diff, errors and warnings with a field path, the real path for a symlink, the risk tier, and the ack data for risky saves. Other-projects effect is needed as soon as user scope is editable. Group outcomes can wait for groups.

## 7. "To fix" and diagnostics

Agree: architect, a typed problems feed with four fix kinds and partial results that never fail a page. Senior developer, a fix button only where an editor exists, words plus path elsewhere. Content specialist, the row pattern of title, cause, consequence and one action, and Claude Code's own "Settings Error" words.

Push back: architect, Unknown sits in your release 1 codes as a counted problem. In the current app Unknown means "The dashboard can't tell what this value is" (Stack A `01-overview-light.html`). That is the app's limit, not a broken setup. Counting it alarms people for no fault of theirs (H2, H8). The content specialist raised this, and I now agree (see Changed my mind).

Answers:
- Architect, read failures get their own group, listed first, because an unreadable file hides every problem behind it. Order is "Couldn't read", then "Won't load", then "Not as set", then an uncounted "Can't tell".
- Content specialist, as above. Unknown leaves the count.

## 8. Usage and history

Agree: architect, one query API with a compare window, `as_of` on every answer, a history status with both dates, and a database backup. Senior developer, no precomputed views until a query is slow, and a named "never delete rows on rescan" test.

Push back: content specialist, "Today" is not in the owner's presets (D20 line 74 lists 7d, 30d, 90d, 12 months, All history). Stack A shows Today as a segment, so the benchmark and the decision differ. That goes to the owner. On the cost label, Stack A shows "Estimated at API list price" once under each cost card and the cost KPI, not under every figure in a table. I would keep that.

Answers: architect, yes. Live's session picker is the active sessions list, a Select in the Live header at both widths, newest first, any project.

## 9. Words and content

Agree: content specialist, the glossary, the clash list ("Surface", "Rules", "Dispatch"), "Started by" on Live, length budgets at 320 and 375, and option A "How Claude Code decides". Architect, codes from the API and words on the page, one envelope with a field path, and no echoed input.

Push back: none.

Answers: content specialist, layer and surface names first, please, since the setup map's columns and the chip widths depend on them.

## 10. UX standards check

Agree: architect, most rows. The field-schema answer per surface closes my "enumerations for pickers" gap (H6). The `as_of`, ingest status and pollable recheck close my "rail events" gap (H1). The field path in the 422 envelope closes my "errors anchor to fields" gap (SC 3.3.1). React Aria's `announce()` defaults to assertive and must be passed "polite" (21-accessibility.md notes).

Push back: architect, four rows.
- SC 3.3.4 and the MCP copy command. The criterion covers pages that modify user data. A page that shows a command the person runs elsewhere submits nothing, so 3.3.4 does not apply. The real need is H5 and H9. The command panel must say the app cannot undo it and show how to remove the server.
- APG Tree View for the setup map. A layered setup is a stack, not a hierarchy, so use APG Table with a link per row. Use Grid only where cells are themselves interactive. Tree View adds a keyboard model nobody needs here.
- APG Dialog (Modal) for the risky confirm. The rail is already the review step, so the confirm sits inline in it. A modal over a review adds a second review. Alert Dialog is for delete only.
- APG Tabs for a scope switch. "Show where each comes from" adds columns to the same table, so it is a Switch or toggle button, not Tabs, which swap panels.

Answers to your direct question.
- Cross-file undo. I rate it lower than you. H3 asks for a clearly marked exit, and per-item Undo in the rail plus a project history list with Undo per row meets it. A global "undo my last change" is ambiguous when Claude Code also writes these files. Group undo is required the day groups ship, as one action.
- Reload. I rate it higher, a release 1 blocker. I agree with sessionStorage plus a launcher action that mints a new code. MDN says a page session "survives over page reloads and restores", and a new tab copies storage only from an opener (https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage). A Cmd-clicked or bookmarked deep link has no opener, so it still lands locked. UX need, the locked page keeps the requested route and returns to it after unlock.
- Senior developer, manual-only rows. A VoiceOver pass per milestone (charts 1.1.1 included), 3.3.3 and 2.4.6 wording quality (with tech-writer), and the forced-colors and 1.4.12 visual look. Everything else can be a test, including 3.2.6 by comparing the help control's position across routes.

## 11. Testing

Agree: senior developer, the three tiers, the behaviour list from the old JS checks, and aria snapshots over pixel snapshots. Architect, one setup corpus with broken twins per surface. Content specialist, the style lint and length budgets.

Push back: none, after the change below.

Answers: content specialist and senior developer, the length budgets need the overflow scan at 320 and 375 that I asked for in round 1, run on the stress names. That one scan covers both.

## 12. Build order and coexistence

Agree: senior developer, a walking skeleton through the real launcher in M0, a new top-level folder outside the payload, and one PR per milestone. Architect, each milestone usable on the demo fixture.

Push back: architect and senior developer, neither milestone list has a design step. The CLAUDE.md Design section says nothing is built before the owner picks a direction. Stack A covers usage, settings, attention, files, rules, all projects and empty states, but not the setup map, the surface template, the inspector or the review rail (`docs/design/usage-stack/a-usage/`, 12 pairs). Two direction rounds belong in the plan. One goes before the setup read UI (architect M3, senior developer M4). One goes before the edit core UI (M4 or M6). Each runs in parallel with the backend milestone before it, so it adds no calendar time. I keep the visible "new dashboard" label while both apps run.

Answers: senior developer, static built output is enough for design review. I render directions as static pages in the scratchpad. Hot reload helps the build phase, not my reviews.

## 13. Open floor

Agree: architect, the "server stopped" state, the database backup and one error envelope. Content specialist, first-run download copy, the single-use code page states and the product name question. Senior developer, the supply-chain minimum.

Push back: none.

Answers: architect, a locked tab asks one question and offers one action. It says the tab has no access, gives the command that prints a fresh link with Copy, and shows no key and no data. After unlock it lands on the route the person asked for. A "server stopped" tab says so and gives the start command, with "Check again".

## Changed my mind

- Scope chip words. I proposed "you, all projects" style labels. I now back the content specialist's docs names (User, Shared project, Project local, Managed, Plugin {name}) with the who line as secondary text. They match what `/status` and the settings docs show, so people meet the same word in both places (H4, external consistency).
- Unknown in "To fix". I listed it as a problem. It now sits in an uncounted "Can't tell" group, for the reason in point 7.
- Pixel baselines. I asked for screenshot baselines. I drop them as asserted tests, per the senior developer. Overflow, target-size and contrast scans plus a capture set for the designer's review per milestone catch what I need.
- Release 1 deletes. I had file delete in release 1. Delete moves to the group-undo release with the architect's order, because a deleted skill folder needs group undo.
- Help placement. I keep one help disclosure per section and add the content specialist's Glossary page under Reference.

## Debate list

| id | point | question | my side | who disagrees |
|---|---|---|---|---|
| D1 | 2 | Do text edits (CLAUDE.md, rules, agent body) ship in release 1? | Yes, with CodeMirror lazy-loaded | Senior developer (five keys plus agent model and effort only) |
| D2 | 2, 6 | How does a not-yet-editable item read? | Reason, real path and Copy path, no promise | Architect ("Editing comes in the next release") |
| D3 | 12 | Do direction rounds gate the setup read UI and the edit UI milestones? | Yes, two rounds, run beside backend milestones | Architect and senior developer (no design step in their lists) |
| D4 | 10, 13 | How does access survive a reload, a new tab and a deep link? | sessionStorage plus a launcher mint, and the locked page keeps the route | Research B2 (memory only), owner call |
| D5 | 7 | Does Unknown count in "To fix"? | No, an uncounted "Can't tell" group | Architect (counted release 1 code) |
| D6 | 6 | Does the rail block in "checking" for about 2 seconds after Save? | No, "saved" at once, warn only on overwrite | Architect |
| D7 | 10 | Which APG patterns for the setup map, risky confirm and scope switch? | Table, inline confirm in the rail, Switch. Alert Dialog for delete only | Architect (Tree View, modal Dialog, Tabs) |
| D8 | 3 | Keep current route names, or the new path scheme? | New scheme, usage route names kept | Senior developer |
| D9 | 8 | Is "Today" a range preset? | Owner call. D20 omits it, Stack A shows it | Content specialist (includes it) |
| D10 | 3 | Fold Models into Overview, or keep a Models page? | Fold, later than 1.0 | Content specialist (keeps Models) |
| D11 | 13 | Does the product keep the name "Routing Dashboard"? | Owner call, before strings and titles lock | Raised by content specialist only |

HIVEMIND
NEW dashboard: Stack A's overview board (docs/design/usage-stack/a-usage/01-overview-light.html) shows the range as a three-segment radiogroup (Today, 7 days, 30 days) and "Estimated at API list price" once per cost card and under the cost KPI, while research/20-decisions.md line 74 sets presets 7d, 30d, 90d, 12 months, All history with no Today. | check: grep -o 'role="radio"[^>]*>[^<]*' docs/design/usage-stack/a-usage/01-overview-light.html | evidence: docs/design/usage-stack/a-usage/01-overview-light.html
END HIVEMIND

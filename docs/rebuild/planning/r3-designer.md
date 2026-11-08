# Round 3 debates, designer

Written November 8, 2026 (11:21 EST) by the designer. I read brief.md, debates.md and all four r2 files, and rechecked research/20-decisions.md, 21-accessibility.md, 26-06, 26-08, the Stack A boards in `docs/design/usage-stack/a-usage/` and `~/.claude/designer/usability-for-apps.md`. I did not run the app. Short names as before. Nielsen H1 to H10, WCAG 2.2 SC numbers, APG pattern names (https://www.w3.org/WAI/ARIA/apg/patterns/), D20 for 20-decisions.md, "usability rule N" for the usability file. Any wording is a placeholder for tech-writer.

## R1

Strongest case. The owner's own editing scope names "settings, agents, rules folders, skills, hooks, CLAUDE.md files, MCP config" (D20, after the gap research). A 1.0 that edits four settings keys plus two agent fields leaves every text surface on that list read-only. The Instructions page would show a body with no way to change it, a dead end (H3, H7). CodeMirror is a lazy chunk on Edit, so its 193 KB never reaches a read-only visit (26-04). Deny and ask rules are the safe tier (D20, round 3, allow is risky) and prove array insert, which 26-01 calls the main new core code. SKILL.md is markdown with front matter, so once the text editor exists for CLAUDE.md it is one more registry entry, single file, no folder work. On the classifier I side with the architect. An agent file edited as text can add front matter keys the classifier must judge, so the server must refuse a risky change from day one, or the held tier leaks through the text editor (26-01 "Risk tiers").

What I concede. Delete waits for group undo (moved in r2). The rail round designs the text-body variant either way, so if the owner keeps text as M6b, no screen is retrofitted. Fields land first in build order, as the senior developer orders it.

Final position. Architect's 1.0 set plus SKILL.md text, no delete, classifier in 1.0 with risky refused in plain words and the line that triggered it.

## R2

Strongest case. The project Design section says nothing is built before the owner picks a direction, and the owner approved "start design directions for the new screens" (D20, last section). Stack A covers usage, settings, attention, files, rules, all projects and empty states (12 pairs), but not the setup map, the surface template, the inspector, the review rail or the new sidebar with its project picker and "To fix" count. The sidebar matters for timing. The shell lands in M3 in the senior developer's table, so the setup round must include the sidebar and Projects home and be picked before M3 starts, not "by M3". The rail round runs in M4 and M5 and includes the text-body variant, the risky confirm, the read-only line and the overwritten state. Both rounds render on the fixture corpus at 375 and 1440, with tech-writer's words, and both run beside backend milestones, so they add no calendar time.

What I concede. The rounds never sit on the critical path. If a pick is late, backend work goes on and only that UI waits. The risky confirm can get its own short round later, since risky is held.

Final position. Two rounds, setup (with sidebar and Projects home) picked before M3, rail (with text variant) picked before M6.

## R3

Strongest case, four patterns.

Setup map, APG Table, not Tree View. Tree View is a hierarchical list whose parent items expand and collapse. The map is a stack of layers per surface. Level 1 is one row per surface, level 2 adds layer columns, level 3 is a separate page. Nothing nests, so a tree's arrow-key model, aria-level and expand state would describe a structure that does not exist (SC 1.3.1). Table gives row and column headers a screen reader reads per cell, and each row holds one link, so Tab order is the reading order (SC 2.4.3). Use Grid only where cells are themselves controls.

Risky confirm, inline in the rail. APG Dialog (Modal) makes everything behind it inert. The diff, the full command and when it runs are already in the rail, so a modal over it either hides that evidence or repeats it. The person confirms what they can see. A checkbox ("I read this command") enables a differently worded button placed away from Save, which meets SC 3.3.4 (confirmed and reversible) and defeats a double-click (my "double-click a swapped confirm" lesson). A modal on every risky save trains click-through, which works against H5 (opinion).

Scope switch, APG Switch or a toggle button (APG Button, aria-pressed). Tabs swap one panel for another. "Show where each comes from" adds columns to the same table, so it is on or off. Changing it is not a change of context (SC 3.2.2). If "scope switch" means picking which scope to write to, that is APG Radio Group or a Select, still not Tabs.

Alert Dialog for delete only, because delete is the one action whose undo is a group operation.

What I concede. APG lists "action confirmation prompts" as an Alert Dialog example, so a modal confirm is not wrong by the book. At 375 the rail is a full-height sheet, which is itself a modal Dialog, and the confirm stays inline inside it. Tree View may fit later where nesting is real, a CLAUDE.md import chain or a skill folder's files. React Aria Components ships all of these (D20 spike 3), so cost does not decide it.

Final position. Table, inline confirm (rail as modal sheet at 375), Switch or toggle button, Alert Dialog for delete only.

## R4

Strongest case. Nielsen H1 asks for feedback within a reasonable time, and Nielsen's response-time limits put flow of thought at about 1 second ("Response Times: The 3 Important Limits"). A rail that holds "Checking" for about 2 seconds after the save already succeeded breaks that on every save. The recheck covers only the three files Claude Code also writes, user settings.json, settings.local.json and .mcp.json (26-08 line 6), and its interval is a guess (26-08 line 62). So a blanket checking state is wrong for CLAUDE.md, agents, rules and skills, and its length is unproven. Say "Saved" at once, polite (SC 4.1.3, role status), with Undo live. When the recheck finds our change gone, that contradicts what we just said, so it earns role alert (APG Alert, important without moving focus) beside the item, with what changed and its actions. Push or poll does not change any of this. I accept polling.

What I concede. For those three files the rail may show a quiet, unannounced "Checking" mark beside the saved row, with Undo still live. Polling with etags and row state, and SSE stays a spike (D20, owner after the verifier). UX needs, by screen. The rail needs the row's recheck state and, on overwrite, which keys changed. The inspector needs the surface etag while the rail is open, to say the file changed under the edit. Project history and the item need the overwritten state kept on the ledger row, so a person who navigated away still sees it. Pages need `as_of` for "Updated {time}".

Final position. "Saved" at once, quiet check mark on the three shared files only, alert on overwrite that persists on the row, polling.

## R5

Strongest case. 26-06 found the final output_tokens in the transcript on 2.1.302 ("Findings"), and the lower-bound claim rests on older closed issues (25-verifier line 5). A "lower bound" mark on every figure states something our own test did not see, and it adds noise to every card (usability rule 23, H8). Stack A says "Estimated at API list price" once per cost card and under the cost KPI, never per figure (`01-overview-light.html`). Keep that placement. Use the architect's trigger with the content specialist's words. The undercount line shows on a card only when the answer counts requests with no final stop_reason above zero, and it reads like "Output cost may be low" with a reason in cost help.

What I concede. The trigger is untested inference (architect, r2 point 8). If M2 cannot prove it, fall back to the content specialist's single line in cost help. Wording is tech-writer's.

Final position. List-price note once per card, undercount line only when the count is above zero, else one line in cost help.

## R6

Strongest case. "To fix" counts problems the person can fix in their setup (D20, "without normal overrides"). "Claude Code newer than the rules" and "rows with no usage" are the app's limits, so counting them alarms people for nothing (H2, H8, my "facts quiet, checks loud" lesson). The version gap goes once in the "How Claude Code decides" banner and as one status line on the setup map, because it lowers confidence in every prediction there. Rows with no usage go beside the history status on usage pages, as a count with its reason. Four groups, in this order. "Couldn't read" first, because an unreadable file hides every problem behind it. Then "Won't load", then "Not as set", all counted. Then "Can't tell", uncounted, under its own heading. An empty group does not render, and zero counted problems shows a "Nothing to fix" state with "Can't tell" still below.

What I concede. The feed keeps all its kinds as codes (architect). Grouping and placement are page decisions, not schema ones.

Final position. Content's four groups, three counted, and both app-limit items out of "To fix".

## R7

Strongest case. Two things called "rules" one group apart confuse a cold reader (content, r2 point 3). Rename "Rules reference" to "How Claude Code decides" in the nav and the route. Put it under a "Reference" heading with the Glossary, at `#/reference` and `#/reference/glossary`. Stack A already uses a "Reference" heading. Use the new path scheme throughout. "Pin" stays in the routing layer only, since the install is optional (D20). Core copy asks "Did each agent run on the model its file sets?" The first nav group is "Usage".

What I concede. I drop my r2 "keep usage route names". The architect showed recorded payloads are API answers, not routes, and the senior developer dropped route names too. I drop "pin" from my own round 1 question (content was right). "Activity" fits Live a little better, but "Usage" matches the page question "What did it cost?" Low stakes either way.

Final position. "How Claude Code decides" at `#/reference`, new scheme, "pin" in the routing layer only, "Usage".

## R8

Strongest case. Pixel baselines as pass-fail gate on noise. My own lessons show sub-pixel baseline snapping reading as 28,000 changed pixels. What gates instead are aria snapshots, computed styles and three scans at 320, 375 and 1440. Overflow, target size (SC 2.5.8) and rendered contrast that skips clip-hidden text. A fixed-width capture set goes to my review per milestone against the picked direction. On differential tests I side with the architect. Two `resolve` modules clash in one process, and recorded old-app payloads double as real data for design renders, so directions draw from the engine's output instead of guesses (my "run the engine for demo data" lesson). On backup, the UX need is that history status shows the last backup time and a failed backup is said in plain words there, not in "To fix".

What I concede. Who runs the backup and when is the architect's and senior developer's call. Both "at start and clean stop" and "after the first daily pass" serve the screen.

Final position. Review-only captures with gating scans, recorded payloads, backup time shown on the history status.

## R9

Strongest case for later. The session detail replay is a new feature on a 926 line plus 684 line canvas (architecture.md 1.3), and Live already shows the dispatch flow while it happens. Session detail's half-empty screen (`shots/07-session-detail-1440-light.png`) is fixed by the layout in the port, not by a replay. Live's session picker across projects stays in 1.0. It lists active sessions newest first in a Select (architect agreed, r2 point 8), and the session goes in the URL (senior developer, M5).

What I concede. The replay and a full cross-project sessions list wait past 1.0. I raised the replay in round 1 and drop it.

Final position. Moved to the senior developer's side on both, with the cross-project Live picker kept in 1.0.

## C4

Strongest case. None to make. I moved in r2 ("Changed my mind"). Docs names on the chip match `/status` and the settings docs (H4, external consistency), and they are shorter at 375 (content, r2 point 9).

What I concede. All of it, with three design conditions. The who-and-where line is part of the chip's accessible name (SC 2.5.3). Chip rows wrap at 375, never clip. "Plugin {name}" truncates visually with the full name kept in the accessible name.

Final position. Moved to docs names on the chip, who-and-where as line two. No objection.

HIVEMIND
NEW dashboard: Stack A's sidebar uses the group headings "This project" and "Reference", with no "Usage" or "Activity" heading. | check: grep -c 'Reference' docs/design/usage-stack/a-usage/01-overview-light.html | evidence: docs/design/usage-stack/a-usage/01-overview-light.html
END HIVEMIND

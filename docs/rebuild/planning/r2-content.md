# Round 2 responses, digital content specialist

Saved by the main session from tech-writer's reply (tech-writer is read-only).

Lens: the words on screen. I read brief.md, my own r1-content.md and r1-designer.md, r1-architect.md and r1-senior-dev.md, and I checked two facts again: research/26-06-output-tokens.md "Findings", and the route list in dashboard/static/js/router.js:21 and :101. Wording below is draft copy for the owner to review, and opinion unless it cites a source.

## 1. Purpose and audience

Agree: with the designer, a cold reader who did not build the setup is the right test. With the architect, "done" should be checks a test can run.

Push back: the designer's question "did each agent run as pinned?" uses install vocabulary. Claude Code's docs never say "pin". An agent's model is set in its file (code.claude.com sub-agents.md). On a stranger's setup the core question should read "Did each agent run on the model its file sets?" "Pin" stays in the optional routing layer (20-decisions.md, after the gap research).

Answers:
- Designer, one-line purpose (draft): "See what runs in each project and why, change it safely, and see what it cost." Page questions, drafts: "What runs here, and why?" "What changes if I save this?" "What did it cost?" "What's running right now?"
- Architect, it's one audience with two kinds of setup. A stranger's setup changes the words in three ways. Core copy never says pin, installer or routing. Every empty state allows for zero agents, hooks or rules. Routing-layer copy shows only when the layer is detected.
- Senior developer, the "done" list in words the owner can tick (draft):
  1. I can open any of my projects from one Projects page.
  2. For any setting or agent, I can see what runs, where it's set and why.
  3. "To fix" lists only real problems, and each one tells me what to do next.
  4. Usage totals for the last 30 days match the old dashboard.
  5. Usage older than 30 days is still there after Claude Code deletes its transcripts.
  6. I can change a value, see what will change before I save, and undo it.
  7. Every page works at phone width and with the keyboard alone.
  8. No page tells me to reload it.

## 2. First-release scope

Agree: with all three, the risky tier waits until its confirm has been designed and tried.

Push back: on the architect's read-only risky field reading "Editing comes in the next release." That puts a promise on screen that the release can't back (Nielsen heuristic 2, my r1 point 2). Draft instead: "You can't edit this here. It's set in .claude/settings.json, line 14."

On scope size, no side between the senior developer's narrow edit set and the architect's wide one. But scope drives copy cost. Whichever scope wins, the edit copy has to be templates fed by the registry.

## 3. Sitemap and navigation

Agree: with the designer, Projects is home, project-only pages hide when no project is open, and Models folds into Overview. With the architect, the project goes in the path.

Push back: the designer keeps a page called "Rules reference" while the same sidebar has "Instructions (CLAUDE.md and rules)". Two different things called "rules" end up one group apart. The senior developer wants to keep current route names, so `#/rules` would stay (router.js:21). URLs are copy people read and share, so the resolver page needs a new name in the nav and the route alike. Example: "How Claude Code decides" at `#/decides` or `#/reference`.

Answers:
- Designer, keep "Instructions" (the docs' scope name, memory.md) and drop "Memory", which means auto memory there. "Usage" over "Activity", low stakes; "Activity" fits better if Live stays in the group. Debate D3.
- Architect, slugs should be the folder name, lowercased, with a short suffix only when two folders share a name. [NEEDS CONFIRMATION: whether projects get a separate display name at all.]

## 4. Current app, keep and change

Agree: with the senior developer, the old app is the oracle, and that holds for copy too. With the designer's change list (U3, U4, U9, U12).

Push back: the senior developer asks for no change on usage and Live that 1.0 doesn't need. Three copy changes are required, not polish. "Reload the page to update" becomes false once pages refresh (design audit U9). "Dispatched by" on Live clashes with Claude Code's Dispatch feature (glossary.md). Install words in core strings (`s_transcripts_t`, `f_action_*`) break on a stranger's setup. Each is a string swap.

## 5. Setup view

Agree: with the designer, three levels with what runs first. With the architect, the command-line layer and session shells show as "not visible here", never as empty.

Answers:
- Designer, a layer chip reads "User", with "You, all projects" as its second line and part of its accessible name.
- Architect, predicted and observed (draft). Predicted: "Runs at high". Observed: "Ran at high in the last session, {date}". When they differ, observed first. Confidence: "tested" carries no mark; "documented" gets "Based on Claude Code's docs. Not tested on {version}."

## 6. Editing flow

Agree: with the designer's checkbox plus a differently worded confirm button ("I read this command", then "Save hook"). With the architect's state list.

Addition: user-scope effect copy in the preview. Draft: "This file applies to every project. {n} other projects read it, including {first two names}."

Answers (drafts):
- Checking: "Saved. Checking the file once more."
- Confirmed: "Saved."
- Overwritten: "Saved, but another program changed this file right after. Review it before you go on." [NEEDS CONFIRMATION: whether the recheck can tell if our change survived.]
- MCP "Check again": "Added. {name} is in ~/.claude.json." If not found: "Not added yet. Run the command, then check again."

## 7. "To fix" and diagnostics

Agree: with the architect and the designer, the count holds judged problems only. With the senior developer, a row with no editor gives the fix in words plus the path.

Push back: the architect's release 1 codes include "Claude Code newer than the rules" and "transcript rows with no usage". Neither is a problem in the person's setup, and the person can't fix either. They belong in a status line or the reference banner (Nielsen heuristic 8).

Answers:
- Designer, "Won't load" and "Not as set" work. Unknown needs its own group, "Can't tell". Read failures form a fourth group, "Couldn't read".
- Architect, yes, cause and fix labels from code and parameters, if parameters carry the name, file, line, value set, value that runs and winning file.
- Senior developer, fix text per code (drafts):
  - Invalid: "Claude Code skips this value. {value} isn't one of {allowed}." Fix: "Change it to a valid value."
  - Ignored: "Claude Code doesn't read {key} here." Fix: "Move it to {file}."
  - Lowered: "{agent} sets {effort}, but {cap file} caps it at {cap}." Fix: "Raise the cap or lower the agent's effort."
  - Unknown: "The dashboard can't tell which value wins." Fix: "Check with /status in Claude Code."
  - Skipped file: "Claude Code can't parse this file, so it skips all of it." Fix: "Open the file at line {line}."
  - Same-folder clash: "Two files define {agent}, and Claude Code picks one by read order." Fix: "Rename or delete one."
  - Shadowed allow: "A deny rule blocks this allow rule." Fix: "Remove one of them."
  - Import: "{file} imports {path}, which isn't there." Fix: "Fix the path."

## 8. Usage and history

Agree: with the designer, the cost note goes once per card (usability rule 23). With the architect, every answer carries its built time.

Push back: the architect and the designer both want "output is a lower bound" on cost. Our spike found the transcript recorded the final output_tokens on 2.1.302 (26-06 "Findings"). The lower-bound claim rests on closed GitHub issues (25-verifier-gap-research.md). Put it once in cost help. Draft: "On some Claude Code versions, transcripts can record less output than was used, so output cost may be low." Debate D5.

Answers:
- Architect, two dates (draft): control "All history, since {oldest session}". Help: "The dashboard has kept its own copy since {first ingest}. Older sessions are here because Claude Code still had them then."
- Designer, alternative wording: "Claude Code's session records can miss some output, so output cost may be low."

## 9. Words and content

Agree: with the architect, the API speaks in codes and the page owns the words, and the screen says "scope", not "layer". With the senior developer, one typed strings file.

Push back: the designer makes "you, all projects" and "this project, just you" the labels. Keep the docs' names as the label and the who-and-where words as the second line, because /status and the settings docs say "User", "Shared project" and "Project local" (settings.md), and because of length at 375 ("Project local" 13 characters against 22). Debate D1.

Answers:
- Architect, I'll own the glossary as a map keyed by enum value: label, second line, definition, banned synonyms.
- Designer, label lengths: User 4, Managed 7, Your shell 10, Command line 12, Project local 13, Shared project 14, "Plugin {name}" grows. Longest nav label "How Claude Code decides" at 23.
- Senior developer, string families per milestone: M0 first-run download, code swap states, locked tab, server stopped. M3 nav, page titles, range labels, "Updated {time}", empty, loading and error states, history note. M4 scope chips, status words, problem codes, read-only reasons, "not visible here", confidence. M5 Live states, "Started by". M6 effect phrases, edit templates, error envelope codes, checking and overwritten. M7 README and plugin README.

## 10. UX standards check

Agree: with the designer's four gaps and the architect's table, including field paths in the error envelope and validation that never echoes input. With the senior developer, testable rules become tests.

Additions: WCAG 2.2 SC 2.5.3 label in name, and SC 2.4.6 headings and labels ("Winner" and "Files read" need their subject). Both testable.

Answers: manual-only from the content side is whether help and error text actually help (SC 3.3.3). An owner read at each milestone covers it.

## 11. Testing

Agree: with the senior developer, typed keys retire test_static_strings.py and the K-819f gap.

Push back: length budgets still need rendered checks; keep the designer's overflow scan at 320 and 375. Typed keys don't catch style, so the lint (em dashes, exclamation marks, banned words, colons in prose) is still needed. My r1 question on label keys versus prose for the colon lint is still open.

## 12. Build order and coexistence

Agree: with the designer, a direction round comes before the setup and edit milestones, and comps use real words. With the senior developer, copy that arrives late blocks Playwright.

Note: the coexistence label should be "New dashboard (preview)", dropped at cutover (cutover checklist).

Answers: one glossary pass before M0 ends and one copy deck per milestone with screens (M0, M3, M4, M5, M6), plus docs at M7. [NEEDS CONFIRMATION: dollars per copy deck at tech-writer high effort.]

## 13. Open floor

Agree: with the architect on locked-tab and server-stopped states, and with the designer that first run belongs in release one.

Answers (drafts):
- Locked tab: "This tab lost access when it reloaded. Run /routing-dashboard:dashboard in Claude Code for a new link." [NEEDS CONFIRMATION: the rebuild's launcher command and whether it can mint a code for a running server.]
- Server stopped: "The dashboard server stopped. Start it again from Claude Code." Never "error".
- First run in release one; export and jump-to later.

Still open from r1: the product name, and "the dashboard" against "we" as the narrator.

## Changed my mind

- Cost note: once per card, plus any figure that stands alone (KPI tile, tooltip), instead of on every figure.
- Models page: drop it; it repeats Overview.
- Output label: now argue against "at least" on cards, after reading 26-06.

## Debate list

| id | point | question | my side | who disagrees |
|---|---|---|---|---|
| D1 | 5, 9 | Is a scope chip labeled with the docs' name or with who-and-where words? | Docs name as label ("Project local"), who-and-where as second line | Designer |
| D2 | 3, 9 | Does the resolver reference keep the name "Rules" and the route `#/rules`? | Rename both, for example "How Claude Code decides" | Designer, senior developer |
| D3 | 3 | Is the first nav group "Usage" or "Activity"? | "Usage", low stakes | Designer |
| D4 | 2 | Does a field that isn't editable yet promise the next release? | No promise. Say where it's set | Architect |
| D5 | 8 | Does every cost carry "output is a lower bound"? | No. Once in cost help, "may be low" | Architect, designer |
| D6 | 7 | Do "Claude Code newer than the rules" and "rows with no usage" count in "To fix"? | No. Status line or reference banner | Architect |
| D7 | 7 | Is Unknown its own "Can't tell" group, and read failures "Couldn't read"? | Yes, four groups | Designer (two groups) |
| D8 | 1 | Does "pin" appear in core copy? | No, only in the routing layer | Designer |
| D9 | 13 | Does the product keep the name "Routing Dashboard"? | Owner's call, before strings and titles | Raised only by me |

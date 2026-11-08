# Round 3 debates, architect

Written 2026-11-08T11:23-05:00 by the architect (deep-reasoner). I read brief.md, debates.md and all four r2 files. I fetched the WAI-ARIA APG pages (treeview, table, dialog-modal, alertdialog, switch, tabs), WCAG 2.2 Understanding 3.3.4 and 4.1.3, and the NN/g article on heuristic 1. Code paths are in /Volumes/Warehouse/Projects/claude-code-model-routing. Research paths are in docs/rebuild/.

## R1

Strongest case. The cut should follow risk, not file count. In 26-01's tier table, CLAUDE.md and rules text, agent bodies, and model and effort keys are all "Safe" (research/26-01-edit-architecture.md, "Risk tiers"). None of them can hold a risky construct. Skill bodies can, because `!`cmd`` lines are risky (same table), so skills text waits. Text is also the surface people change most (designer r2 point 2, opinion), and an inspector with a body but no Edit is a dead end (Nielsen H3). CodeMirror loads lazily on Edit, so read-only visits never pay its 193 KB (26-04).

On the classifier, the senior developer is right that the full tiered classifier can wait. What 1.0 needs is a smaller server rule, because the API is the trust boundary, not the page. Every operation must target a registry field marked writable, with values from its field schema. That excludes `defaultMode: bypassPermissions`, which a "scalar key" cut would otherwise reach (26-01, Risky row). And `replace_text` on agent files must leave the front matter bytes unchanged, since `hooks` and `mcpServers` live there (26-01, Agents row). That is an allowlist and a byte compare, not a semantic diff.

What I concede.
- Deny and ask rules leave 1.0. `insert_item` is new core code (26-01 line 38) and the senior developer's array spike is not done (json_edit.py:281, 369).
- "Every schema-typed scalar key" drops to the four old keys (api_edit.py:303-308). More scalars come later as registry rows.
- The tiered classifier with `risk.ack` ships with the first risky surface, not in 1.0.
- Delete and skills text wait, as the designer already moved.

Final position. 1.0 edits the four keys, agent model and effort, and CLAUDE.md, rules and agent body text (M6b inside 1.0). The server enforces a writable allowlist and body-only text, and the full classifier waits for the risky milestone.

## R2

Strongest case. Two direction rounds are right, and my milestone list was wrong to leave them out. The project Design section says nothing is built before the owner picks a direction (CLAUDE.md, Design). Stack A has no setup map, surface template, inspector or review rail (designer r2 point 12). The architecture risk runs the other way too. A direction drawn on invented data can ask for state the API never exposes. So each round must start from the frozen data shapes, and its UX needs must come back before those shapes lock.

The order I propose.
- The setup round starts when the M1 item shape and map summary shape are drafted (`writable`, `read_only_reason`, `confidence`, `loads`, counts). It renders on the fixture corpus at 1440 and 375, and finishes before the setup read UI starts (M4 in the senior developer's table).
- The rail round runs during M4 and M5 and finishes before the edit UI (M6). It includes a text-body variant, so M6b is not a retrofit (senior developer r2 point 12).
- Each round returns a short list of UX needs (fields, states, events). I fold them into the API before its OpenAPI types lock.
- Backend milestones never wait on a round.

What I concede. The rounds gate UI milestones. My "design reviews the build" framing was too late.

Final position. Two rounds, each gating its UI milestone, running beside backend work. The rail round includes a text-body variant, and each round starts from drafted data shapes and returns UX needs before the types lock.

## R3

Strongest case for my side. My round 1 table named Tree View, Dialog (Modal) and Tabs as candidate keyboard models (r1-architect.md line 235). It was a list of patterns to check, not a recommendation. Checked against APG, the designer's picks are better on all four.

- Setup map. APG says "a tree view widget presents a hierarchical list" whose items "may be expanded or collapsed". A precedence stack is ordered layers, not parents and children. APG Table is "a static tabular structure", and APG sends interactive cells to Grid. A table with one link per row fits. Each of the three levels is its own route and its own table, so drill-down is navigation, not expansion.
- Risky confirm. WCAG 2.2 SC 3.3.4 needs only "at least one" of reversible, checked or confirmed. The rail is already the review step, and byte-restore undo makes the save reversible. A modal makes the page under it inert (APG Dialog) and adds a second review of the same diff.
- Scope switch. APG Tabs "display one panel of content at a time". Showing where values come from adds columns to the same table, so it is APG Switch ("one of two values: on or off"), with a label that "does not change when its state changes".
- Alert Dialog "interrupts the user's workflow" (APG). That fits an irreversible delete only.

What I concede. All four picks. I add three build conditions. The switch state lives in the URL query, so a reload or a shared link keeps it. The confirm button sits away from Save and appears only after its checkbox, so a double click can't pass it (designer r2 point 6). At 375, if the rail opens as a sheet, the sheet itself follows APG Dialog (Modal), and the confirm stays inline in it. In 1.0 no Alert Dialog ships, since delete waits. "Undo anyway" uses the inline confirm with its diff, because the ledger keeps the bytes it replaces.

Final position. Moved to the designer's side. Table for the map, inline confirm in the rail, Switch for scope, Alert Dialog for delete only, plus the three build conditions above.

## R4

Strongest case. There are two questions here. On transport, push or poll is settled. The owner accepted "polling default with SSE as spike" (research/20-decisions.md, "Owner, 2026-11-08 after the verifier"), and the designer's r2 point 10 accepts polled `as_of`, ingest status and recheck state. On the rail, the designer is right about words, and my real need is in the data. NN/g's heuristic 1 asks for "appropriate feedback within reasonable time". The write has landed and been read back when Save answers, so "Saved" is the true status. A spinner for a recheck that 26-08 calls "a guess" on its interval (26-08 line 62) is backstage detail.

What the data must keep, whatever the rail shows.
- The ledger row holds `recheck: pending | confirmed | overwritten`, and the page polls that row once at about 2 seconds, then once more if still pending (26-08 Recommendation).
- The poll belongs to the app, not the rail. If the person has moved on, the warning still reaches them through the app-level live region, and the item and the project history show "overwritten" afterwards.
- Page freshness uses per-surface etags and `as_of`, polled by TanStack Query.

WCAG 2.2 SC 4.1.3 maps success to `role="status"` (ARIA22) and warnings to `role="alert"` (ARIA19). "Saved" goes out politely. I propose the overwrite warning also goes out politely, and moves no focus, because the person may be typing elsewhere (opinion). React Aria's `announce()` must be passed "polite" (21-accessibility.md, Notes). Content owns the words.

What I concede. No visible or announced "checking" state. "Saved" at once, Undo live at once.

Final position. Moved to the designer's side on the rail, with three conditions. The data keeps a pollable three-state recheck. The overwrite warning reaches the person wherever they are. Page updates poll with etags, and SSE stays a spike.

## R5

Strongest case for my side. 26-06 found the final output count in the transcript on 2.1.302 streaming (26-06 Findings, line 7). The lower-bound claim rests on closed issues #27361, #21971 and #22686 (25-verifier-gap-research.md line 5), so "lower bound" on every figure overclaims. My conditional note only appears when the data shows a risk.

What I concede. My trigger, a request with no final `stop_reason`, is untested inference. 26-06 saw `stop_reason` applied to every row of a reply (line 20), so I can't yet say what an undercounted row looks like. Shipping an unproven detector is worse than one honest static line. Content's sentence in cost help is cheaper and true on any version. Stack A's "Estimated at API list price" once per card stays (designer r2 point 8).

Final position. Moved to content's side for 1.0. One "may be low" sentence in cost help, no per-figure label. The ingest stores `stop_reason` so a conditional note can come later if a spike proves a signal.

## R6

Strongest case. Content is right that "Claude Code newer than the rules" and "rows with no usage" are not problems in the person's setup, and the person can't fix them (Nielsen H8, H9). Architecturally they stay in the same feed as a fourth kind, `notice`, outside every count. "Newer than the rules" shows on the reference page and the setup map header, because it lowers confidence everywhere. "Rows with no usage" shows in the history status line on usage pages.

One sharpening on the four groups. A file Claude Code itself can't parse belongs in "Won't load", which counts, because Claude Code skips it (content's "Skipped file" code). "Couldn't read" should hold only the app's own limits, such as no permission or a file over the size cap. Those are like "Can't tell", the app's limit and not a broken setup. So I'd list "Couldn't read" first, as the designer wants, but outside the count, with its own number in its heading (opinion, H2).

What I concede. Both codes leave the count. Four groups, in the designer's order.

Final position. Four groups in order "Couldn't read", "Won't load", "Not as set", "Can't tell". Only "Won't load" and "Not as set" count. The two system codes become uncounted notices.

## R7

Strongest case. Routes are interface too, so I hold three points. The router is rewritten anyway (createHashRouter, research/20-decisions.md line 18), and project-in-path changes every route, so the new scheme costs nothing extra. The senior developer has dropped "keep current names" (r2 point 3). Route segments should be stable nouns chosen once, so a later label change never breaks a link. And a small redirect map from old hash routes (router.js:21) to new paths keeps owner bookmarks working at cutover.

On words, content's case holds. Two things called "rules" one group apart is a real clash (glossary.md). "Pin" never appears in Claude Code's docs, and the API's `feature: routing` tag (my r2 point 1) lets the page show routing-layer words only when the layer is detected.

What I concede. All the word calls go to content. "How Claude Code decides" as the label, "pin" only in the routing layer, "Usage" for the first group (low stakes).

Final position. New path scheme with stable noun segments (for example `#/reference` for "How Claude Code decides"), usage segment names kept, a redirect map from old routes, and content's words throughout.

## R8

Strongest case. Recorded payloads, not in-process. Old and new code both keep flat module names until cutover (senior developer agreed, r2 point 11), so two `resolve` modules clash on sys.path. The old app runs on /usr/bin/python3, while the new backend needs 3.11 or newer (research/20-decisions.md, verifier pass). Recorded payloads also outlive the old app, so the oracle survives cutover. On screenshots, the panel already agrees. The designer dropped pass-fail baselines (r2 "Changed my mind"), so aria snapshots and computed styles gate, and captures go to milestone review.

Backup. The server's single ingest writer owns it, through SQLite's online backup API. It runs at start if the last copy is over 24 hours old, after the first ingest pass of each day, and at clean stop if rows changed since the last copy. Each copy gets `PRAGMA quick_check` before the oldest is rotated out. WAL mode covers an unclean stop.

What I concede. Clean-stop backup, from the senior developer, because SessionEnd can stop the server before a daily point fires. Recorded payloads need a regenerate command run whenever the corpus changes, and they are never hand-edited.

Final position. Recorded payloads from the old app, screenshots review-only, and backups by the ingest writer at start, daily and at clean stop, with a check and a few rotated copies.

## C1

I concede. "Editing comes in the next release" is a promise the release can't back (content r2 point 2, Nielsen H2). The API already carries `read_only_reason` as a code with parameters naming the owner, file and line (my r2 point 5, designer r2 point 5). So the page says why and where, with Copy path, and no timeline.

Final position. Moved to the designer, content and senior developer side.

## Other near-consensus items

No objection to C2, C3 or C4.


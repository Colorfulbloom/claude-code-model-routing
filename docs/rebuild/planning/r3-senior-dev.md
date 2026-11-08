# Round 3 debates, senior developer

Written 2026-11-08T11:22-05:00. Planning only. Nothing in any repo changed. "Old code" means /Volumes/Warehouse/Projects/claude-code-model-routing. Research paths are under docs/rebuild/. Sizes and weights are my opinion. I read brief.md, debates.md and all four r2 files. I raise no objection to C1 to C4, since C1 and C4 match what I argued in round 2.

## R1 First-release editing scope

Strongest case. The old app has never done three things the wide cut needs, and each is a first, not a port.
- Array edits. json_edit only adds and removes object keys (dashboard/json_edit.py:281, 369). Deny and ask rules need insert and remove on arrays, and 26-01 calls that "the main new core code". My spike for it is still not done.
- Text edits. The write body cap is DRAIN_CAP = 65536 (dashboard/server.py:141). A body edit needs a new cap, a new replace operation, a per-request nonce and CodeMirror (193 KB gzipped, 26-04).
- Delete. It needs new ledger rows and undo of a delete (dashboard/edit_store.py, RETENTION = 20 at line 70 prunes by row count, not by file).

Cost is not the only reason. The cheapest proof of the registry is a thin one. Four settings keys (dashboard/api_edit.py:303-309) plus agent model and effort give two file formats, JSON and YAML, and one preview shape. If the rail and ledger work there, every later surface is a registry entry.

On the classifier, field editors can only reach registered field ids. A hook cannot be reached by a field editor, so enforcement in M6 is the registry itself, which refuses an unregistered path. The classifier becomes load-bearing the day a free-text editor ships. An agent body edit is free text over a file whose front matter can hold hooks.

What I concede.
- The architect is right that four scalar keys alone do not exercise arrays. I accept deny and ask rules in 1.0 if the M0 spike for `insert_item` passes. If it fails, they slip.
- The designer and architect are two against one on CLAUDE.md and rules text, and the dead-end argument holds. An Instructions page that shows a body and cannot change it is a gap (usability rule 18, Nielsen H3). CodeMirror is lazy, so it never touches a read-only visit.
- The classifier ships with the text editor, not later. That answers the architect's raw-text concern.
- Delete leaves 1.0. The designer already agreed.

Final position. Moved partly to the architect. 1.0 is M6 (four keys, agent model and effort) then M6b (CLAUDE.md, rules and agent body text with CodeMirror and the classifier), both before cutover. M6b is cuttable by the owner if the schedule slips. Deny and ask arrays join if the M0 spike passes. Create, delete, skills and risky keys come after.

## R2 Design rounds and milestones

Strongest case. The designer is right that CLAUDE.md's Design section forbids building UI before the owner picks a direction. Stack A covers usage, settings and attention, but not the setup map, the surface template, the inspector or the review rail (r2-designer.md point 12, and `docs/design/usage-stack/a-usage/`). So the pick must land before the UI half of M4 and M6. My concern is only the critical path. If a round blocks the backend half, a slow owner pick stalls the build. The two halves are separable. M4 is collectors, the item shape and the To fix feed, plus a UI. M6 is the edit core, the registry and the preview, plus a rail.

The order I propose uses the table in r2-senior-dev.md point 12. The setup round runs during M1 to M3. The rail round runs during M4 to M5. M0 to M3 never wait on a pick, because usage has a benchmark.

What I concede.
- The rule is a gate on UI work, not on milestones. The designer's "design leads" and my "never on the critical path" are the same rule if the rounds start two milestones early.
- The rail round must include a text-body variant (a CodeMirror pane and a markdown diff) even if M6b is cut. Otherwise M6b becomes a retrofit of a rail built for fields. Architect and designer asked for this, and it costs one more direction in the round.
- The architect asked that M1 fix the item shape with `writable`, `read_only_reason`, `risk_tier` and the field schema, so the design round has data to draw. Agreed.

One added rule. Each round has a pick deadline. If the owner has not picked when the backend half is done, the backend merges behind a feature flag and the UI waits. Nothing else stalls.

Final position. Yes, a direction round gates each UI milestone, not the backend milestones. Rounds run beside earlier milestones. The rail round includes a text-body variant. A pick deadline keeps the critical path clear.

## R7 Words and routes

Strongest case. My round 1 line, keep current route names, saved nothing. The old routes are single segments in the PAGES list (dashboard/static/js/router.js:18-21) and the parse function (router.js:95-110), and every test of them (the 796 JS checks and the router tests) is rewritten for the new project-in-path scheme. Old bookmarks are already dead, because the launcher link carries a single-use code. So no legacy redirect table is needed either.

That makes route names pure copy. A person reads and pastes a URL (Nielsen H6 recognition, the designer's point on slugs). Content is right that the sidebar would hold "Instructions (CLAUDE.md and rules)" beside a page called Rules reference, and `#/rules` keeps the clash in the address bar. Renaming costs one entry in a route table and one string key. It adds no test cost.

My engineering rule for any name: the route segment is the glossary slug of the nav label, lowercase, English. A table test asserts that each registered segment maps to one glossary key. That ties the URL to the words and stops drift.

What I concede.
- Rename "Rules reference" and its route. I back content's option A, "How Claude Code decides", with a route under a Reference group, for example `#/reference/decides`. The exact segment is opinion, and the owner or tech-writer sets it.
- Usage route names survive only where the glossary slug matches. That is the designer's position, and it follows from my rule.

On the other two sub-questions. "Pin" stays in the routing layer. The first nav group word, Usage or Activity, is not in any URL, so it costs nothing for the build. I have no side on it and defer to content and designer.

Final position. Moved to content on the rename. New scheme, route segment equals glossary slug, no legacy redirects, "pin" only in the routing layer, group word left to content and designer.

## R8 Testing

Strongest case. Three sub-questions, and the panel has mostly converged.

Screenshot baselines. Designer, architect and I now all say review artifacts, not pass-fail. Aria snapshots, computed styles, overflow, target-size and contrast scans gate. The designer reviews a capture set per milestone. Evidence is the repo's own habit. The old suite never asserted pixels, and its Chrome work was by hand (K-486e, X-b9fc: width emulation and reload per width). A pixel baseline fails on font hinting between macOS and the Linux CI runner.

Differential tests. I said in-process. The architect's objection is correct. Old and new both keep flat module names, so two `resolve` modules cannot share one sys.path. Recorded payloads from the old app fix it. The old app runs under /usr/bin/python3 against the committed fixtures (123 resolver folders and the demo fixture) and writes JSON. The new tests compare to that JSON. Two conditions keep this honest.
- The recording script names the old repo's commit sha in a manifest, so the oracle is frozen and reproducible.
- An explicit allowed-differences list names every intended change, such as the Unknown group and the seven status words. A diff outside the list fails. Without it, the test either never passes or hides real regressions.

Backup. The database has no backup today because it does not exist. Who runs it matters because my own r2 answer, at start and clean stop, has a hole. The launcher can stop the server after SessionEnd hands cleanup to a detached worker (L-2116), so a clean stop may not run, and a SIGKILL never does. The architect's plan, a backup at start if the last is over 24 hours old and after the first ingest pass each day, has no such hole. The server's single ingest writer runs it with SQLite's online backup API. Keep seven copies. A test restores the newest copy and compares row counts.

What I concede. In-process differential tests, and clean stop as the backup trigger. Both go to the architect.

Final position. Moved to the architect on differentials (recorded payloads, frozen sha, allowed-differences list) and on backup timing (server, daily after first ingest, plus start if over 24 hours). Screenshots are review only.

## R9 Session replay and cross-project sessions list

Strongest case. Replay is a new feature, not a port, and the old app cannot supply it. Live reads only sessions that ran in the last RUNNING_MINUTES (dashboard/api_live.py:22-23), keeps minute buckets for 30 minutes and a dispatch run list, and needs one project (api_live.py:18-20, project=all gets 400). An ended session has no canvas state to draw. Replay needs a full-session reconstruction at an arbitrary time, a time scrubber and a pause. That scrubber brings an APG Slider, a drag alternative (WCAG 2.2 SC 2.5.7) and a pause control (SC 2.2.2). The canvas is already 926 lines (live.js) plus 684 (live_flow.js) (app-audit/architecture.md 1.3), with 11 live payload fixtures (tests/fixtures/live). Replay doubles that test surface and has no oracle in the old app. It also does not serve any of the designer's five job walkthroughs. A person who wants to know what an ended session did is served by the session detail table, which exists (session-detail.js, 76 lines).

The cross-project list is different. It was only expensive because Live scanned transcript folders. With the SQLite history from M2, the sessions table already holds session id, project, start and last-seen time. A Live header Select, newest first across projects, is then a read of one table.

What I concede. The designer's Live picker across projects, as the Select in r2-designer.md point 8, ships in 1.0. It is S cost once M2 lands. Choosing another project's session navigates to that project's Live route, so `/api/live` stays one folder per request and its 1 s poll cost does not change. The session also goes in the URL in M5, as I already said.

What I hold. Replay on session detail, and a cross-project sessions page, both after 1.0. Chip overlap (A8) is fixed now.

Final position. Split. The cross-project picker and session in the URL ship in 1.0. Canvas replay and a separate cross-project sessions page come after 1.0.

HIVEMIND
NEW dashboard-live: /api/live lists only sessions with a request in the last RUNNING_MINUTES and refuses project=all, so an ended session has no canvas data and a cross-project picker must navigate between per-project routes. | check: sed -n 18,30p /Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/api_live.py | evidence: dashboard/api_live.py
END HIVEMIND

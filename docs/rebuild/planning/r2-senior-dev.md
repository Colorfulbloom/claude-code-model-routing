# Round 2 responses, senior developer

Written 2026-11-08T11:20-05:00. Planning only. Nothing in any repo changed. Short names as in round 1. "Old code" means /Volumes/Warehouse/Projects/claude-code-model-routing. Sizes and weights are my opinion.

Checks I made against old code this round.
- The old app edits four settings keys, not five. The table is `effortLevel`, `maxEffortLevel`, `model` and `autoCompactWindow` (dashboard/api_edit.py:303-309). edit_store.py:6 says no agent file is editable.
- The write body cap is `DRAIN_CAP = 65536` (dashboard/server.py:141), under `MAX_FILE` of 1 MiB. Text edits need a new cap.
- The launcher record already holds an `owners` list, one entry per Claude Code process, and `add_owner` dedupes it (plugins/routing-dashboard/bin/routing-dashboard:463-556). A shared server extends that record. It does not need a new idea.
- Edits take an flock on the backup store's `.lock` (dashboard/edit_store.py:15, 827).

## 1. Purpose and audience

Agree. Architect (done as runnable checks) and designer (five job walkthroughs). They fit. Content's four "done" items are checkable too, with the glossary and style lint.

Push back. None. One correction to myself, see "Changed my mind".

Answers.
- Architect asked if the done checks fit a CI budget. Yes, with tiers. Pure pytest, Vitest and typecheck run in a few minutes. Walkthroughs and the full axe matrix run at milestone end only.
- Content asked for a "done" list the owner can tick. I will not write it. Content should, from the architect's six checks and the designer's five jobs. I will only confirm each item has a test.

## 2. First-release scope

Agree. Designer and architect both hold the risky tier back. So do I.

Push back. Designer and architect, on what else ships in 1.0. Designer lists agent bodies, CLAUDE.md and rules text, skills text, deny and ask rules, and create and delete. Architect lists every settings key, CLAUDE.md and rules text, and single-file create. Two against one, so I give ground, but not all of it.

My case is cost and order, not the idea. Each of those items needs something the old app has never done.
- Text editing needs CodeMirror (193 KB gzipped), a per-request nonce, a raised body cap (DRAIN_CAP) and a new `replace_text` operation.
- Deny and ask rules need array insert and remove in json_edit. Today it only adds and removes object keys (json_edit.py:281, 369), and my spike for that is still not done.
- Create and delete need new ledger rows and undo of a delete.

Proposed split. Release 1.0 ships field editors for the four old keys, then agent model and effort. Agent front matter is the second surface type, so it proves the registry with real YAML. Text edits for CLAUDE.md, rules and agent bodies come next as M6b, after the rail is proven. The owner decides if M6b joins 1.0. Permission arrays, create and delete follow. This is debate D1.

Answers.
- Architect asked whether the registry can be proven on a few keys first. Yes, with settings keys plus agent front matter. Those are two formats, JSON and YAML.
- Designer asked which safe editor is cheapest. A scalar settings key (`effortLevel`), then the other old keys, then an agent scalar. Arrays are the dearest.
- Architect asked about a read-only risky field. I accept the read-only row. The wording is debate D5.

## 3. Sitemap and navigation

Agree. Designer and architect on `#/p/<pid>/...` with range in the query.

Push back. Myself. I said keep current route names. That only helps tests that die anyway, since 796 JS checks and the router tests are rewritten. Drop that line. Keep the API route names only where the old shape survives, which is the settings payload.

Push back. Designer, on twelve setup pages. Cheap only if each is one list-and-inspector component with a surface prop. Content adds Output styles and Plugins. Each extra page is a registry entry, a collector and a fixture, so the nav lists only surfaces that have a reader. Sidebar order and group names stay design questions. A command palette waits.

Answers. Designer asked how many pages 1.0 needs. Projects, Overview, Sessions, Session detail, Live, Setup map, a surface page per shipped collector, To fix and Reference. The surface pages are one component.

## 4. Current app, keep and change

Agree. Designer's keep list matches mine.

Push back. Designer, on Live and session changes. Put the session in the URL (small, M5). Defer the dispatch-canvas replay on session detail and the cross-project sessions list. They are new features on a 926 line plus 684 line canvas (architecture.md 1.3). Fix the chip overlap now.

Answers. Designer asked what ports straight.
- tokens.css (135 lines) copies as is. Plain CSS on tokens is decided (20-decisions.md:18).
- app.css (944) and live.css (196) port per component. Class names drop the round-numbered prefixes.
- charts.js (186 lines) is hand SVG ported one to one from the Stack generator. It becomes TSX with tick steps from the server.
- By content's count about 476 of 823 string keys are not edit keys. They move with a key check. Edit keys are rewritten as templates.
- band_drag and Arrange die.

## 5. Setup view

Agree. Architect on one read model and confidence on unproven combiners. Content on lead with what runs.

Push back. Architect, on the map. It is one summary endpoint over collector output, so it comes after the collectors. If the designer wants it earlier it ships as a stub with counts.

Answers. None addressed to me. On the collector interface, architect's item shape (26-02) works for my `read(project) -> items, diagnostics`. Add `unreadable` with a reason and `confidence` to it. The fixture corpus is covered in point 11.

## 6. Editing flow

Agree. Architect on one state machine. Content on templates.

Push back. Architect, on inverse-operation undo. Keep byte restore plus the changed-file refusal in 1.0. Inverse undo needs its own tests and only matters once permission arrays land, because Claude Code appends allow rules to settings.local.json (26-08). Build the post-save recheck in 1.0 though. It is a 2 second re-read and it is the data-safety piece.

Push back. Content, on "the registry carries display name and effect verb". Architect says the API speaks codes and the page owns words (point 9). Agree with architect. The registry carries string keys. strings.json holds the words.

Answers.
- Content asked if typed slots fit typed `t()`. Yes. Each key has a typed params shape, so `t("ed_saved", { name, effect })` fails to compile on a missing slot.
- Designer asked if "Check again" is cheap. It is an S task. It refetches the masked `~/.claude.json` collector. It comes late, because that collector is last in my read order.
- Designer asked for the cut preview fields. The screen needs effect, diff, warnings with field path, and the real path. I would cut group and per-file outcome until groups ship.
- Architect asked about the body cap. Agree, raise it with text edits.

## 7. "To fix" and diagnostics

Agree. Designer, architect and content on judged problems only.

Push back. Architect's release 1 code list. It has 13 codes. Each code is a rule, a fixture and one cause string. Ship the codes whose data a shipped collector already gives, and add plugin and transcript-gap codes with their collectors (opinion, not counted per code).

Answers. None addressed to me. I back architect's ask that content writes one cause string and one fix label per code. A closed-enum test then fails the build on a code without a string.

## 8. Usage and history

Agree. Architect on the query API and the history status answer. Designer on one range Select.

Push back. None on content. On backup, architect says the database needs a backup but not who runs it. My answer. The server runs it with SQLite's online backup, at start and at clean stop, because SessionEnd can stop the server (so a daily timer may never fire). Keep a few copies. That is open for the architect.

Answers. None addressed to me. Designer's progress line and updated-at time are cheap if each answer carries `as_of` and the history status carries a rows count.

## 9. Words and content

Agree. All three on one glossary and typed keys. Content's three clashing words (surface, rules, dispatch) cost nothing to avoid on screen.

Push back. Content, on the style lint. A key-suffix rule will not work. Suffixes are `_t` on 109 keys and `_h` on 60 of 823. Use a value rule (colons inside text with a period or more than five words) plus a short allowlist of label keys. Opinion, not tested.

Debate. Content wants docs scope names (Shared project, Project local). Designer wants who-and-where words. Cost is the same either way, one key per layer id. I lean to content's names as the chip and designer's words as the second line, which content already proposes (D6).

Answers. Content asked for strings per milestone. Use my table in point 12. Copy for M3 (shell and usage) and M4 (setup read) is first. Edit templates are due before M6.

## 10. UX standards check

Agree. Designer's four gaps, and architect's table.

Push back. Designer, on an open "reload loses the key" gap. It is real, and I add that the old app already solved it with sessionStorage (dashboard/static/js/edit_session.js:4-7). I side with architect: sessionStorage plus a launcher command that mints a new code. The launcher already writes a 0600 link file and already probes the server (bin/routing-dashboard:326, 692), so a mint call is S to M. This needs an owner decision before M0 ends (D4).

Answers. On the manual-only checklist rows. Plan as owner checks at cutover. VoiceOver pass, focus order sanity and chart tooltip dismissal (1.4.13). Everything else gets a test.

## 11. Testing

Agree. Architect's order, differential tests and hypothesis.

Push back. Designer, on cost. Axe on every route and state at 1440, 375 and 320, light and dark, plus keyboard scripts, plus VoiceOver at every milestone. Per change that is too slow. Per change, run touched routes at 375 and 1440 light. At milestone end, run the full matrix, dark and 320. Run VoiceOver at M3, M6 and cutover. Opinion.

Push back. Designer, on screenshot baselines. I said no pixel snapshots. Keep them as review artifacts the designer looks at, not pass-fail tests (D3).

Answers.
- Designer asked for one fixture generator. Yes for sizes and stress cases. Generated trees must be deterministic and checked against committed expected JSON, so the generator is not its own oracle. The 123 resolver folders and the demo fixture stay as files.
- Architect asked which CI runner. Linux for lint, types, Vitest and pytest. flock and directory-descriptor calls exist on Linux. Macs stay for local runs, because APFS case traps (I-9984) are macOS only. Minutes cost is an owner question [NEEDS CONFIRMATION: repo visibility and plan].
- Content asked for the colon lint answer. See point 9.

## 12. Build order and coexistence

Agree. Architect's milestones and folder outside the payload. Designer's "new dashboard" label.

Push back. Designer, on design leading each milestone. Good rule, but "no build before a pick" must not block the critical path. My order puts setup screens at M4 and the rail at M6, behind the shell (M3). So the setup round runs during M1 to M3 and the rail round during M4 to M5. The designer is never on the critical path. Designer's two rounds fit. The cost is a rail design that must include a text-body variant, so M6b is not a retrofit.

Push back. Architect, on the shared backups folder. flock covers both writers, so my "never write one project from both apps" caveat softens. The old pruner (RETENTION = 20, edit_store.py:70) and group rows still mean groups stay off until cutover. Agree with architect there.

Answers.
- Architect asked for the folder name. `app/`, with `app/server/` and `app/web/`.
- Architect asked about M2 beside M1. Yes, in a second worktree, with the owner's yes. M2 needs the transcript parser from M1. Copy it verbatim at the start of M2, since the two share only the registry.
- Architect asked about a launcher control channel. Yes, S to M, see point 10. The `owners` record already supports several Claude Code sessions. The server record needs a project list instead of one project.
- Content asked for a milestone list. It is in the table. Dollars per milestone [NEEDS CONFIRMATION: dashboard cost per run].

| M | Content | Strings and design due |
|---|---|---|
| M0 | Skeleton, spikes, CI | Glossary, first run and code-swap copy |
| M1 | Pure core, ASGI gate | none |
| M2 | Ingest, usage API, backup | History copy |
| M3 | Shell, usage pages | Usage copy, setup direction picked |
| M4 | Setup read, To fix | Surface copy, fix text per code |
| M5 | Live | Live copy, rail direction picked |
| M6 | Edit core, field editors | Edit templates |
| M6b | Text editor, if the owner agrees | Text editor copy |
| M7 | Cutover | README rewrite |

## 13. Open floor

Agree. Content on product name, first-run and code-swap screens. Architect on user-scope edits and the logging gap. Designer on first run.

Push back. Designer's jump-to and CSV export. Both come after 1.0. Export is small, so it can slip in earlier if the owner wants it.

Answers.
- Designer asked if Vite hot reload is needed. For workers yes, for design review no. Designers review built output.
- Content asked for the code swap states. My reading from decisions: fresh, already used, expired, server restarted (launch id changed) and a key for another project. Architect confirms.
- Architect's point on user-scope files. A project key can change `~/.claude/settings.json`. Minimum for 1.0, the preview names affected projects (S). Stricter rules are an owner call (D7).
- Nobody replied to my four items, which are Python 3.9 against 3.11, tracked build output, CI cost and supply chain. They stay open (D8).

## Changed my mind

- "Five settings keys edit today" was wrong. It is four, and none is an agent file. Agent model and effort is a new surface, so I keep it in 1.0 as the second surface type that proves the registry.
- "Keep current route names" is dropped for pages. The router and page tests are rewritten anyway.
- The "never write one project from both apps" warning is softened. flock covers it.
- I treated the key question as a given. I now think it blocks M0 exit.
- I now put the post-save recheck in 1.0.

## Debate list

| id | point | Question | My side | Who disagrees |
|---|---|---|---|---|
| D1 | 2 | Do text edits, deny and ask arrays, and create and delete ship in 1.0? | Fields plus agent model and effort in 1.0. Text edits as M6b if the owner agrees. Arrays, create and delete after | Designer, architect |
| D2 | 12 | Must a direction round finish before each build milestone? | Yes, but run in parallel with earlier milestones. Rail round includes a text variant | Designer wants design first. No real clash if timing holds |
| D3 | 11 | Are screenshot baselines pass-fail tests? | No. Review artifacts only. Use aria snapshots and computed styles | Designer |
| D4 | 10 | How does access survive reload and new tab? | sessionStorage plus a launcher minted code. Decide before M0 ends | Architect agrees. Owner decides. Research says memory only |
| D5 | 2 | What does a not-yet-editable item say? | A plain read-only reason. No "coming soon" | Architect (next-release wording) against content |
| D6 | 9 | What do scope chips say? | Docs names on the chip, who-and-where words on line two | Designer, content |
| D7 | 13 | Can any project key edit user-scope files? | Preview names other projects in 1.0. Stricter later | Architect wants an owner call |
| D8 | 13 | Python 3.9 launcher, 3.11 backend, tracked build output, CI minutes, supply chain | Bundle committed at milestone ends only. Locked installs. Linux CI | Nobody answered. Owner for cost |
| D9 | 8 | Who runs the database backup and when? | Server, at start and clean stop | Architect to confirm |
| D10 | 4 | Session replay on the canvas and cross-project sessions list in 1.0? | Later | Designer |
| D11 | 13 | Does the product keep the name Routing Dashboard? | Raise before strings fix it | Content only |

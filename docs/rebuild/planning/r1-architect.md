# Round 1 positions, architect

Written 2026-11-08T11:13-05:00 by the architect (deep-reasoner). Lens is how the system serves each point. That means the state, data, events and APIs each screen needs, what the surface registry, readers, resolver, edit core and SQLite store must expose, feasibility and risk, and where a UX wish conflicts with the decided architecture.

Paths without a leading slash are in /Volumes/Warehouse/Projects/claude-code-model-routing (code, read on chore/hivemind-consolidation-nov-7) or in docs/rebuild/ of the rebuild-docs worktree (research and audits). Screenshots are in /Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/app-audit/. I did not run the app. I did not read ~/.claude/designer/usability-for-apps.md, because the brief reserves it for the designer.

API names below are illustrative. They show what data must exist, not final routes.

## 1. Purpose and audience

Position: The app is the owner's local window onto one Claude Code data folder and every project in it. It does four jobs, and each job has one system part behind it.
- What is set and what runs. Surface registry, readers and resolver.
- What is wrong and how to fix it. One problems feed.
- What it cost and when. Ingest into SQLite and a usage query API.
- Change it safely. The edit core (json_edit, edit_store, validators, ledger).

"Anybody's setup" means no reader assumes install.sh ran, so the routing pieces sit in a detected optional layer. I recommend we state "done" for the first release as checks a test can run.
- Every registry surface has a reader, a clean and a broken fixture, and a "Couldn't read" state.
- The 123 resolver fixtures pass on the port.
- Usage totals on the demo fixture equal the current app's for the same 30 days.
- The edit-store safety tests pass, and the old and new apps read each other's ledgers.
- axe reports no violations on any route at 375 and 1440.
- A transcript deleted by Claude Code's cleanup keeps its rows.

Why:
- Owner scope, plugin collector and optional layer, see research/20-decisions.md, sections after the gap research and after the coverage matrix.
- Components behind each job, see app-audit/architecture.md 5.4 (surface registry, collectors, ingest service, edit key store, validators, diagnostics view).
- Rows kept after a source file is deleted, see research/26-05-transcript-ingest.md, Recommendation and Results ("A deleted source file kept all rows").
- Opinion. Done stated as tests keeps a wide scope honest and gives the verifier something to check.

Weigh in:
- Content specialist. Is "owner first, anybody's setup" one audience or two? Does a stranger's setup change any words?
- Senior developer. Can these done checks run in a CI time budget, given the current suite takes about 370 seconds?

## 2. First-release scope

Position: Release 1 reads everything and edits one file per operation. Group and risky edits follow, because they need the most new core code.
- Release 1. Every reader in the registry, the resolver with its three new combine modes, the problems feed, usage and Live on SQLite. Edits for every settings key the vendored schema knows (scalar set and remove, permission and list arrays), CLAUDE.md and rules text, agent fields and body, and create of a single file.
- Release 1.1. The risky tier (hooks, statusLine, credential helpers, MCP command and args) once hook and MCP validators exist, plus `.mcp.json` edits and the MCP copy command.
- Release 2. Multi-file groups (skill folders, executable files), delete with group undo, output styles.

Release 1 must match today. That means Live and its nine states, the usage pages, the settings band that leads with what runs, the trail, Needs attention (as "To fix"), the rules reference, and the edit flow with preview, stale refusal, undo, undo anyway and restore. It also means fixture mode, the gate, and the launcher with its guard hook.

Why:
- New core code, see json_edit only inserts and removes object keys today (json_edit.py:273-281, quoted in research/26-01-edit-architecture.md "Operations per surface"). Array operations are "the main new core code for permissions and hooks" (same file).
- Groups and modes are new ledger fields, see research/26-01-edit-architecture.md "Ledger and backups".
- Current pages, Live states and edit flow, see research/10-features.md sections 1 and 3.
- Opinion. Shipping reads before writes gives the owner a usable app early and lets the risky tier land with its validators, not before them.

Weigh in:
- Designer. In release 1, a risky field shows as read-only with "Editing comes in the next release". Does that work in your rail, or do you want risky in release 1?
- Owner, through the judge. Is this order acceptable, given the owner decided risky surfaces are editable but not when?

## 3. Sitemap and navigation

Position: The system side sets five constraints on the URL scheme.
- Project goes in the path as a stable registry id, for example `#/p/<pid>/setup/agents/<item>`. Cross-project pages live outside it (`#/projects`, `#/rules`). The id is a readable slug the server maps to the real path, so the client never sends a path.
- Every item has a stable id (surface, scope, name). Deep links, React Aria collection keys and the problems feed all use it.
- Range goes in the query (`range=30d`, or `from` and `to`). The Live session goes in the path, which fixes today's unlinkable Live view.
- The launch code sits in its own fragment slot. The page reads it and strips it with `history.replaceState` before the router mounts.
- Query cache keys mirror the route (`[pid, resource, params]`), so a project switch fetches only what the open page needs.

Edit capability is per project. The nav and the rail both need it, so one session endpoint returns read access, the projects this tab can edit, and whether the routing layer is detected.

Why:
- Client never sends a path, see research/26-01-edit-architecture.md Recommendation 1; edit_store.py:6, 210-238.
- Project switch loads usage and settings on every page, see app-audit/architecture.md finding 6 (app.js:383-416, 577-581).
- Live session not in the URL, see finding 27 (api_live.py:18-23, router.js:46-53).
- Project list only from routing-dashboard.json, see finding 15. Launcher project id is sha1(realpath)[:12], see research/19-launcher.md.
- Hash router and key in the fragment, see research/20-decisions.md, judge's picks and owner round 3.

Weigh in:
- Designer. Is Projects the home page? If the setup nav shows a problem count per surface, every page load needs the problems feed for that project. Do you want that?
- Content specialist. Slugs show in the address bar. Should they be the folder name or the display name?

## 4. Current app, keep and change

Position: Keep the logic, change the transport and caching.
- Keep. The resolver and its 123 fixtures, json_edit byte splicing, the edit_store write steps and ledger format, the transcript parser and dedupe, Live's minute buckets and runs tree, git_check, fixture mode, the gate's rules. Also keep the edit error codes and the history row flags (`undoable`, `not_undoable_reason`, `restore_state`, `undo_anyway`), which already give the UI good recovery data.
- Change. Usage moves from three precomputed views to range queries. The settings answer gets a cache keyed by file stats. The page cache moves from load-once promises to TanStack Query with refetch. The project list comes from a registry. Agent front matter reads through ruamel.yaml.
- Drop. The install.py import in the core, the sys.path hack, Arrange.

The Stack usage pages carry over as a design. Their loaders change, because sessions become paged and ranges become parameters.

Why:
- Error codes, see api_edit.py:1720-1775 (stale with a fresh preview, raced, unverified, changed_since_save, backup_damaged, not_undoable). History flags, see api_edit.py:1551-1558.
- Usage payload size and staleness, see app-audit/architecture.md findings 5, 7, 8, 9. The demo's 30-day sessions list alone is 117,001 bytes.
- Strict YAML subset rejects ordinary agents, see finding 14 (agent_frontmatter.py:16-31).
- Install coupling, see findings 19 and 20.
- The band's "high now" under "xhigh Lowered" comes from the resolver, so it must survive the port, see shots/09-settings-1440-light.png.

Weigh in:
- Senior developer. Do you port resolve.py whole first and move its constant tables later, or split it while porting? I lean whole first, so the fixtures prove the port before the refactor.

## 5. Setup view

Position: One read model feeds the setup map, catalogs, surface pages and "To fix". Each reader returns items in the common shape from 26-02 plus registry data. That is id, name, surface, scope, sources (layer, file, line, summary), winner or all, status, reason, writable, read-only reason, risk tier, when a change applies, parse state and confidence. The map is a summary endpoint with counts, names and health per layer and surface.

Three limits must show on screen.
- The command-line layer (`--settings`, `--agents`, `--effort`) and each session's shell are invisible to the server. The map marks them "not visible here", never empty.
- The server's environment is the launch shell, not a running session's.
- Only settings combinations have rules.json evidence and harness cases. The memory, MCP, skills and hooks combiners are documented only, so their statuses carry "documented" confidence until harness cases exist.

"What runs" is either observed (pin check from transcripts) or predicted (resolver). The API labels which.

Cost. A setup read stats every file in every layer, plugin caches included. Cache by stat signatures with one etag per project.

Why:
- Common item shape and per-surface combiners, see research/26-02-scope-combination.md Recommendation and "Per surface".
- Rules evidence covers settings only (84 rules, 50 tested, 23 documented, 11 assumed), see research/22-rules-engine.md. No rule covers permissions, hooks or plugins, see 26-02 "rules.json against the documented exceptions".
- The current page already admits the invisible layer, see shots/09-settings-1440-light.png footer "Your shell, --effort and /effort can beat these files."
- State each new screen needs, see app-audit/design.md, "Answers to the architect's seven questions" item 3.
- Plugin records rewritten at session start, see research/26-03-plugin-collector.md Recommendation 5.

Weigh in:
- Designer. Is writable plus a read-only reason enough for your read-only markers, or do you need the fix too (for example "edit the dotfiles repo")?
- Content specialist. What words separate "predicted" from "observed"?

## 6. Editing flow

Position: One edit state machine in the page and one preview shape from the server (26-01). States are viewing, drafting, previewing, review, risky confirm, saving, checking, saved, overwritten and failed.
- Field editors send typed operations. The text editor sends `replace_text`. Both get the same preview.
- CodeMirror may show a local diff while typing, but Save works only from a server preview. The server diff is what gets written.
- Save returns the ledger row with a recheck pending. The recheck from 26-08 ends as confirmed or overwritten, and the page polls the row for it.
- Undo of a splice edit re-plans the inverse operation on today's bytes, so a Claude Code write after ours survives. Byte restore stays for text edits and for "undo anyway".
- A group edit can't be atomic across files, so the API reports each file's outcome.
- Local and user MCP returns a command to copy, with no ledger row.
- A user-scope edit reaches every project. The preview's effect names the other projects.
- Text saves need a larger body cap than today's 64 KiB.

Why:
- Preview shape, risk tiers and ack hash, see research/26-01-edit-architecture.md "The common preview shape" and "Risk tiers".
- Post-save recheck, Claude Code appends allow rules to settings.local.json, see research/26-08-write-races.md Recommendation and "What Claude Code writes".
- Today's undo refuses a changed file and "undo anyway" overwrites it (edit_store.py:34-39, api_edit.py:1481-1489). Under a wider scope that would erase Claude Code's own later writes. Inference.
- Body cap. DRAIN_CAP = 65536 (server.py:141) against MAX_FILE = 1 MiB (edit_store.py:71). JSON escaping can grow a text body further. Inference.
- MCP copy command, see research/20-decisions.md, owner round 3.

Weigh in:
- Designer. Can the rail hold a "checking" state for about 2 seconds after Save, then "saved" or "another program changed this file"?
- Senior developer. Is the inverse-operation undo worth its tests in release 1, or does byte restore with the changed-file refusal stay until release 2?

## 7. "To fix" and diagnostics

Position: Problems are a typed feed from the server, not page logic. Each row has a stable id, a kind (judged problem or read failure), a code, the thing it belongs to, file and line, cause parameters, confidence, and a fix. The fix is one of four kinds. Open an editor at a field or line, send a prefilled operation the rail can preview, copy a command, or "can't fix here" with the reason (managed, plugin).

The count holds judged problems only. Overridden stays a fact on its item.

Release 1 codes. Invalid, Unknown, Ignored, Lowered against a pin, a file Claude Code would skip, an unreadable file (permission, encoding, size), a same-folder agent name clash, an allow shadowed by a deny or ask, plugin agent ignored fields, an import outside the allowed roots, an unreadable plugin record, transcript rows with no usage, and Claude Code newer than the rules.

Readers return partial results plus errors and never fail a page. Server health (ingest lag, database errors) goes to a status line, not to "To fix".

Why:
- The owner decided Needs attention becomes "To fix" without normal overrides, see research/20-decisions.md, after the coverage matrix.
- Overridden rows crowd the page (13 rows for Tidewater, most normal), see shots/12-attention-1440-light.png, app-audit/design.md U7.
- Same-folder clash is unpredictable, see research/26-02-scope-combination.md, Subagents row.
- Shadowed allow, see 26-02, permissions evaluator. Missing usage as drift signal, see research/26-05-transcript-ingest.md Risks.
- Parse once more before "Couldn't read", see research/26-08-write-races.md Recommendation 4.
- Partial pages, see app-audit/design.md answer 7.

Weigh in:
- Content specialist. One cause sentence and one fix label per code. Can you write them from codes and parameters alone?
- Designer. Do read failures sit in the same list as judged problems, or in their own group?

## 8. Usage and history

Position: One usage query API replaces the three precomputed views.
- Parameters are from, to, a group (day, hour, model, agent, effort, project) and a compare window for deltas. Sessions page with a cursor. Presets resolve on the server in the local time zone, so day buckets match the page.
- Cost is computed at query time from prices.json at current rates. Each answer says the basis is list price, gives the unpriced token count, and flags output as a lower bound.
- A history status answer gives the oldest stored row, the first ingest date, the last pass, rows with no usage and files kept after cleanup. "All history" needs both dates, because a first ingest also picks up older transcripts still on disk.
- Every answer carries the time it was built, for "Updated at".
- Live polls each second with an etag. Each poll asks the single ingest writer to tail that one folder first, so Live never waits on a full pass.
- The database holds the only copy past 30 days, so it needs its own backup beside the ledger.

Why:
- Three views in one payload, see app-audit/architecture.md finding 7 (usage.py:537-570). Deltas use a previous period today, see usage.py:52-58.
- 300k rows in 1.8 s cold, 13 ms for a no-change pass, group by day and model in 112 ms, see research/26-05-transcript-ingest.md Results.
- Reprice all history at current rates, see research/20-decisions.md, after the gap research. Output is a lower bound, and each content block repeats the usage, see research/25-verifier-gap-research.md, research/26-06-output-tokens.md.
- Presets and the "where All history starts" line, see research/26-10-history-range.md; owner round 3.
- Time zone rules, see research/23-domain-carryover.md A7.
- Live polls at 1 s with back-off, see app-audit/architecture.md 3.2.

Weigh in:
- Designer. Do you want the "active sessions" list beside Live's status line (your answer 5)? It comes cheaply from file times across projects.
- Content specialist. Words for the two dates behind "All history".

## 9. Words and content

Position: The API speaks in codes and the page owns the words. Statuses, problem codes, error codes, risk tiers, when-it-applies values, layers and surfaces are closed lists in the OpenAPI schema. A test fails when a value has no string, which replaces today's scan for literal `t("key"` calls.

Two kinds of prose stay on the server. They are the rule reason templates in rules.json and the quoted doc lines. Both are copy, so the content specialist reviews them with strings.json.

The code says "layer" for the resolver and the docs say "scope". I recommend one word on screen and the enum name only in code. Opinion. "Scope" fits readers better, because Claude Code's docs use it.

Errors share one envelope with a code, a field path or line when known, and parameters. Validation answers never echo the input, so the page shows the value it already holds beside the message.

Why:
- Reason text is built on the server from rules.json templates, see resolve.py:1421-1441.
- String scan only counts literal calls, see project fact K-819f in .claude/rules/project-facts.md.
- 422 bodies echo `input` by default, and the fix drops it, see research/26-07-read-gate.md, tests 2 to 4 and "Exact settings".
- Seven status words, see app-audit/design.md, Reuse first in the project CLAUDE.md Design section.

Weigh in:
- Content specialist. Please own the glossary as a list keyed by enum value, so the test can check it.

## 10. UX standards check

Position: The architecture can deliver most of what the standards ask. Five places need API work or an owner call.
- Undo is per file, newest row only (Nielsen heuristic 3). A global "undo my last change" across files is not in the model. Per-item undo in the rail plus a history list is.
- System status (heuristic 1, WCAG 2.2 SC 4.1.3) needs a built-at time on every answer, an ingest status, the post-save recheck state, and edit capability per project.
- Error prevention (heuristic 5) is strong. Validators, stale checks and the risky hash meet WCAG 2.2 SC 3.3.4 for data changes, since an edit is reversible, checked and confirmed. The MCP copy command is the exception, because the app can't undo what it didn't run.
- Recovery (heuristic 9) is served by today's error codes, if the envelope keeps a field path for SC 3.3.1 and 3.3.3.
- Under the memory-only key plan, a reload or a new tab loses read access, not just editing. That breaks heuristics 1 and 3 until the owner picks a fix (point 13).

I can't check the designer's usability-for-apps.md rules, because the brief reserves that file for the designer.

Why: each row names the standard, what the UX needs, and whether the API delivers it.

| Standard | UX need | Delivered by | Gap |
|---|---|---|---|
| Nielsen 1, visibility of system status | "Updated at", ingest progress, save outcome, edit on or off | as_of per answer, history status, recheck state on the ledger row, session capabilities | Recheck result arrives after the save answer, so the row must be pollable. First ingest of a large history needs a progress value |
| Nielsen 2, match the real world | Plain words, not file and key jargon | Codes mapped to strings (point 9) | Rule reason templates are server prose |
| Nielsen 3, user control and freedom | Cancel, undo, restore | Drafts live in the page until Save, so cancel is free. Undo and restore per file (api_edit.py:1481-1489, 2067-2131) | No cross-file undo. Group undo is new (ledger `group`). No undo for the MCP command |
| Nielsen 4, consistency | Same rail and status words everywhere | One preview shape (26-01), one item shape (26-02), one status list | None if every surface uses both shapes |
| Nielsen 5, error prevention | Block bad saves, warn on risky ones | Validators that refuse what Claude Code would skip, stale bases, ack hash, shadowing warning (26-01, 26-02) | Effect on other projects for user scope is missing today. ConfigChange hook warning is inference (26-08) |
| Nielsen 6, recognition over recall | Pickers with valid values, current value shown | Registry must expose a field schema (type, allowed values, default, doc link) | Not in the 26-01 preview shape yet. Needs a field-schema answer per surface |
| Nielsen 7, flexibility | Raw text one step away, deep links | `replace_text` on any file, stable item ids | None |
| Nielsen 8, minimalist design | "To fix" shows only problems | Problems feed with a kind per row (point 7) | None once Overridden leaves the count |
| Nielsen 9, recover from errors | Say what went wrong and how to fix it | Error codes with a fresh preview on stale (api_edit.py:1727-1742) | Keep the field path in the 422 envelope |
| Nielsen 10, help | Why a value is what it is | Rules reference, doc links per registry entry | New combiners have no rules yet |
| WCAG 2.2 SC 3.3.4 (AA) | Data changes reversible, checked or confirmed | Backups and undo, validators, the review step | MCP copy command is outside the app |
| WCAG 2.2 SC 3.3.1 and 3.3.3 | Name the field, suggest a fix | Validator rows carry code, line, text (26-01 Validators) | Add a suggestion parameter where one is known |
| WCAG 2.2 SC 3.3.7 | Don't make people retype | Editors start from the current value in the preview answer | None |
| WCAG 2.2 SC 4.1.3 | Save, undo and Live changes announced politely | Distinct answer codes per outcome | React Aria announce() defaults to assertive (research/21-accessibility.md notes) |
| WCAG 2.2 SC 2.2.2 | Pause auto-updating content | Live Pause exists today (live.js:266 per 21-accessibility.md) and polling stops when hidden | None |
| WAI-ARIA APG Tree View, Grid, Combobox, Dialog (Modal), Tabs | Keyboard models for the setup map, tables, project picker, risky confirm, scope switch | Stable item ids for collection keys | None from the API, if ids are stable across polls |
| Stack benchmark (docs/design/usage-stack/) | KPI deltas against a previous period | Compare window in the usage query | Must be added; today's views precompute it (usage.py:52-58) |

Weigh in:
- Designer. Which of these rows do you rate differently from the UX side? I most want your view on cross-file undo and the reload problem.

## 11. Testing

Position: Port the evidence first, then add oracles for the new parts.
- Port in this order. The 123 resolver fixture folders as parametrized pytest over the same files, the edit_store and json_edit safety tests, then the gate tests. Gate tests assert "refused", not exact codes.
- Ingest gets an oracle. The pure Python reference from spike 5 recomputes totals from the files, and hypothesis drives appends, truncations, late links and rewrites.
- Differential tests while both apps live. Same fixture, old settings rows against new resolver rows, old usage totals against new ones. They retire at cutover.
- Setup fixture corpus. One tree per complexity step, and a broken twin per surface (bad JSON, bad YAML, symlink, unreadable file, same-folder clash, orphaned plugin version).
- Contracts. OpenAPI exported offline, generated types checked in CI, one string per enum value.
- New combiners get harness cases before their statuses claim "tested".
- A race test from 26-08, with a writer thread rewriting the file during save and recheck.
- Per change, lint, types, touched pytest areas, Vitest and Playwright on touched routes. Before merge, the full pytest run and Playwright with axe on every route at 375 and 1440.

Why:
- Fixture count and test inventory, see research/22-rules-engine.md. Gate codes vary, see research/20-decisions.md, spike 1.
- Ingest reference and its checks, see research/26-05-transcript-ingest.md Results.
- No CI today, see app-audit/architecture.md finding 31.
- The harness in dashboard/experiments/harness has 193 cases (research/22-rules-engine.md). Project fact T-07ef says never run a harness batch as a check, so new cases are owner-run.
- Offline OpenAPI export is unverified, see research/26-07-read-gate.md UNVERIFIED.

Weigh in:
- Senior developer. Which CI runner? macOS matters for the flock and dir-fd tests.

## 12. Build order and coexistence

Position: Each milestone ends usable on the demo fixture.
- M0 skeleton. uv project, FastAPI with the gate, read key and code swap, SQLite migrations, fixture mode, OpenAPI types, CI, React shell. Size M.
- M1 read core. Registry, readers, project registry, resolver port, problems feed. Size L.
- M2 history. Ingest, usage query, Live, differential tests. Size M.
- M3 read UI. Projects home, Stack usage pages, setup map, catalogs, "To fix", rules reference. Size L.
- M4 edit core. Generalized edit_store, json_edit array operations (first spike), preview shape, settings to parity then all keys, text and agent edits. Size L.
- M5 risky tier and MCP. Size M. M6 groups, skills, delete. Size M. M7 cutover. Size S.

The new app lives in its own top-level folder, outside the plugin payload until cutover, and runs from uv on a high port. Both apps share the backups folder, and flock covers both writers. Group edits stay off until cutover, because the old app's pruning can split a group. The old app persists no usage, so the new database starts at its first ingest.

Sizes are opinion. Dollars should come from the senior developer, using the dashboard's cost per run.

Why:
- The old ledger reader checks only the version and that rows are objects (edit_store.py:796-799), so new optional fields should read fine in the old app. From the code, not run. This answers the open question in research/26-01-edit-architecture.md "Ledger and backups".
- Old pruning keeps 20 rows per file (edit_store.py:70) and knows no groups.
- Every payload change needs a version bump and rebuild, see project fact L-13fb. Keeping the new app out of the payload until cutover avoids that churn.
- Port 8377 is reserved for the owner's running copy, see the brief and research/19-launcher.md.
- No usage store today, see app-audit/architecture.md finding 11.

Weigh in:
- Senior developer. Folder name, and whether M2 can run in parallel with M1 in a second worktree (they share only the project registry).

## 13. Open floor

Position: Five gaps from the system side.
1. Keys after a reload. With memory-only keys and a spent single-use code, a reload or a new tab loses read access. I recommend sessionStorage, which is per origin and survives a reload, as today's edit_session.js does. Pair it with a launcher action that mints a new code for the running server. Cookies are a poor fit, because RFC 6265 section 8.5 says cookies don't isolate by port. The owner decides, since research B2 said memory only.
2. User-scope files under per-project keys. Any project's edit key can change ~/.claude/settings.json, which every project reads. At minimum the preview names the other projects. The owner may want more.
3. One server's lifecycle. SessionEnd stops the server when no owners remain, so an open tab needs a "server stopped" state and a restart hint.
4. Database backup and integrity, since it holds the only copy past 30 days.
5. A logging policy and one error envelope.

Also, server-side preferences need a write route, and the key rule for it is undecided.

Why:
- Today's token survives a reload through sessionStorage, see dashboard/static/js/edit_session.js:4-7. Research B2 drops it to memory, see research/23-domain-carryover.md B2. The single-use code, see research/20-decisions.md owner round 3; research/26-09-platforms.md item 2.
- One key per project, see research/20-decisions.md, after the gap research. One token for every project today, see app-audit/architecture.md finding 24.
- SessionEnd stop rule under one server, see research/24-coverage-matrix.md contradiction C5; research/19-launcher.md.
- Database not rebuildable once sources are cleaned, see research/24-coverage-matrix.md C6; research/26-05-transcript-ingest.md Risks.
- Logging and errors gap, see research/24-coverage-matrix.md ranked gap 14; research/26-07-read-gate.md access log results.
- Whether Chrome copies sessionStorage into a tab opened from the page is UNVERIFIED.

Weigh in:
- Designer. What should a locked tab say and offer?
- Senior developer. Is a control channel from the launcher to the running server (to mint a code) simple enough, given the launcher already probes the server?

## Top three concerns

1. Keys and access across reloads, tabs and scopes. The memory-only key plus a single-use code means a reload shows nothing, and the per-project edit key still lets any project change user-scope files every project reads. Both need an owner decision before M0, because the gate, the session endpoint and every page's locked state depend on them.
2. Truth after a save in files Claude Code also writes. Byte-restore undo can erase Claude Code's later writes to settings.local.json, the post-save recheck needs a state the page can poll, and group edits can't be atomic. The edit state machine and the ledger row need these states from the start, not as patches.
3. "What runs" can overclaim on the new surfaces. Only settings combinations have tested rules. The memory, MCP, skills and hooks combiners are documented only, and the command-line layer and session shells are invisible. Without a confidence field and an explicit "not visible here" layer, the setup map will state guesses as facts.

HIVEMIND
NEW dashboard: The edit_store ledger reader checks only `version == 1` and that `rows` is a list of objects (edit_store.py:796-799), so unknown optional row fields pass the old app's reader. Not run, read from code. | check: grep -n 'doc.get("version") != 1' /Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/edit_store.py | evidence: dashboard/edit_store.py
NEW dashboard: The write gate's body cap DRAIN_CAP is 65536 bytes (server.py:141), below edit_store's MAX_FILE of 1 MiB (edit_store.py:71), so a whole-text edit of a large file cannot pass today's cap. | check: grep -n '^DRAIN_CAP\|^MAX_FILE' /Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/server.py /Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/edit_store.py | evidence: dashboard/server.py, dashboard/edit_store.py
END HIVEMIND

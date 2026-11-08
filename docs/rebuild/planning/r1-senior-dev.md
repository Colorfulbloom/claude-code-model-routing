# Round 1 positions, senior developer

Written 2026-11-08T11:11-05:00. Lens: what is realistic to build and ship, build order, effort and risk, test porting, coexistence and cutover. Planning only. Nothing in any repo changed.

Sources read. brief.md, agenda.md, research/20-decisions.md, README.md, research/21, 22, 24, 26-01, 26-05, 26-08, 26-09, 26-10, 19, app-audit/architecture.md and design.md, the project-facts rules file, and the current code for tests, tools/build_plugins.py and edit_store.py. Screenshots viewed were shots/09-settings-1440-light.png and shots/01-live-1440-light.png.

Counting note. Test numbers below are `def test_` method counts from grep over tests/*.py (about 3,450) and `test(` calls over tests/js/*.mjs (796). They are not the 3,575 run total in project fact T-7629, which also counts generated fixture methods. Effort labels (S, M, L, XL) and percentage weights are my opinion, sized by lines of code and tests touched. I have no dollar data, so the main session should price each milestone from the dashboard's cost per run [NEEDS CONFIRMATION: dollar figures per milestone].

## 1. Purpose and audience

Position: Build for the owner first and write the code so that it reads anybody's setup, which is what the decisions already say. "Done" for the first release is a testable list, not a feeling. It means the new app does everything the old one did except Arrange and the Installed files page (which becomes the optional layer), keeps history past 30 days, reads every surface in the editing scope without writing most of them, and edits the five settings keys that edit today plus an agent's model and effort. Everything else in the editing scope ships in numbered follow-up releases. A first release that tries to finish all of 20-decisions.md at once will not finish.

Why: 20-decisions.md lists four products in one. These are a usage app with an ingest database, a setup reader with eight or more new collectors, a generalised editor with four risk tiers and a text editor, and a shared server with per-project keys. The current app took the same effort for two of them (usage plus four-setting edit). Opinion, based on the size of the audit tables in app-audit/architecture.md section 5.

Weigh in: Content specialist, please write the "done" list in words the owner can tick without reading code.

## 2. First-release scope

Position: Ship in this order of inclusion.

In release 1.0.
- All usage pages with history ranges, on SQLite.
- Live and the dispatch canvas.
- Setup read side. Settings band and where-it-is-set rows, To fix, rules reference, agent catalog including never-ran agents, plugin collector, read-only lists for CLAUDE.md, rules, skills, hooks and MCP from files.
- Edit of the existing four settings plus agent model and effort, through the generalised registry and one review rail, with backup, undo and restore.
- One server, per-project edit keys, read key.

Held for 1.1 and later.
- Text editor (CodeMirror 6, 193 KB gz per research/26-04) and all markdown body edits.
- Risky tier surfaces (hooks, statusLine, apiKeyHelper, MCP command and args).
- Skill folders with grouped create and delete, output styles, the ledger `group` field.
- Setup map polish, command palette, Projects add and remove in the app, several Live sessions at once.
- Linux. Keep the platform module boundary, skip the port.
- React Aria drag and drop. Arrange is dropped (design.md section 4), so nothing in the plan needs drag.

Why: The registry and the preview shape must be right on day one, but each added surface is an operation set plus a validator plus a screen. That is incremental work once the core exists (research/26-01 operations table). Cutting the text editor alone removes a 193 KB chunk, a per-request nonce dependency in the editor, and its accessibility work.

Weigh in: Architect, say whether the registry can be proven with five keys before the other surfaces exist, or whether you need a second surface type in 1.0 to trust the shape.

## 3. Sitemap and navigation

Position: Fewer routes is cheaper. Keep the current route names, the @main key and the query names (architecture.md section 5.2) so recorded payloads and tests carry over. Add session to the Live URL. Put project in the path or hash once, not in four places. Do not build a command palette in 1.0.

Why: router.js is 142 lines and 15 modules import it. Every route rename is a change in every page and every test. The hash router and edit key stay in the fragment per the givens.

Weigh in: Designer, how many new pages does the sitemap really need for 1.0 if each surface list is one component with a surface prop?

## 4. Current app, keep and change

Position: Carry over the usage pages, Live, the Settings band concept, the rules reference and the status vocabulary as is. Rebuild the code, not the behaviour. Treat the old app as the oracle. Until the old code is deleted, every number the new usage and live pages show for the demo fixture must equal what the old app shows.

Why: design.md section 3 calls the usage pages the strongest part and the Stack benchmark. Screenshots 01-live-1440-light.png and 09-settings-1440-light.png show a Live page with a dispatch canvas, cards, charts and a table. The canvas alone is live.js 926 lines plus live_flow.js 684 (architecture.md 1.3). That is an L port, not a rebuild from nothing, so keep its pure layout logic and fixtures (tests/fixtures/live has 11 payload files).

Weigh in: Designer, name any change to the usage or Live pages that is not required for 1.0, so I can move it to a later release.

## 5. Setup view

Position: Build the read side from files in this order. Settings (exists), agents (exists, now with full YAML), plugin agents and settings (research/26-03), skills, CLAUDE.md with imports, hooks from settings, MCP from .mcp.json, then `.claude.json` MCP read-only and masked. Each collector returns the same shape so one list-and-inspector component serves them all. Setup map comes after the collectors, not before.

Why: Each collector is S to M (a reader, a fixture or three, a mask test). The map is only a summary over their output. Building it first means building it twice. Parse failures must show as a state, so the collector contract needs `unreadable` with a reason from the first collector (design.md answer 7).

Weigh in: Architect, I want one collector interface with `read(project) -> items, diagnostics` and a fixture corpus of three setups (empty, typical, heavy). Agree or give a better split.

## 6. Editing flow

Position: Generalise edit_store and json_edit in place, port them nearly verbatim, and do not redesign them. Spike first on the two unverified pieces, which are json_edit array `insert_item` and `remove_item`, and ruamel.yaml byte-equality on the demo agents. Ship settings and agent front matter fields in 1.0. Add the risky tier's server enforcement (acknowledgment hash) when the first risky surface ships, not before.

Why: edit_store is the most tested code in the repo (241 tests in test_edit_store, 31 in test_edit_security, 116 in test_json_edit) and the one place a bug destroys user data. The ledger reader checks only `version == 1` and that each row is an object (dashboard/edit_store.py:796-799), so additive optional fields do not break it. That answers the open question in research/26-01 for the reader. The api_edit callers have not been checked. Old and new apps can therefore share the backups folder during coexistence, with one caveat. Do not let both apps write the same project at once.

Weigh in: Designer, the review rail needs one preview shape. Tell me which fields of research/26-01's preview shape the screen cannot do without, so I can cut the rest from 1.0.

## 7. "To fix" and diagnostics

Position: To fix in 1.0 lists judged problems from the resolver plus unreadable surfaces from collectors. Each row says what is wrong and which file and line. A "fix" button appears only where an editor exists (the five keys and agent model and effort). Everywhere else the row gives the fix in words and the path.

Why: A fix action for every row depends on the whole edit scope, which does not ship in 1.0. Words plus path is honest, testable and cheap. Nielsen heuristic 9 (help users recover from errors) is met by the explanation, and the button is a bonus.

Weigh in: Content specialist, draft the fix text per resolver status so a row never ends without a next step.

## 8. Usage and history

Position: Ingest to SQLite as in research/26-05, keeping transcripts.py parsing rules and the usage.py dedupe rule. Use the old Reader plus usage code as the test oracle. Back up the database, because after Claude Code's cleanup it is the only copy of old usage. Use SQLite's online backup, daily, kept next to backups and the ledger. Store the first-ingest date, because "All history starts on" needs it. Defaults and presets are as decided (30 days, 7d, 30d, 90d, 12 months, All history). Do not precompute views until a measured query is slow.

Why: The spike matched a pure reference at 300k rows with 84 ms for a sum and 112 ms for group by day and model (26-05 results). The rebuild's own research says rows are lost on a shortened source file (26-05 Risks), so the ingest must never delete rows on a rescan. Add that as a named test. The three precomputed views and the built-answer cache are dropped (architecture.md 5.1).

Weigh in: Architect, who owns the backup job and where does it run, given one server and the SessionEnd stop rule no longer fits (24-coverage-matrix.md C5)?

## 9. Words and content

Position: Keep strings.json as the one copy file and make keys typed, so a missing or unused key is a compile error. That retires tests/test_static_strings.py and project fact K-819f. Write new surface copy in batches per milestone, never after the screen is built.

Why: The old test only counts literal `t("key"` calls, which is why helper-passed keys read as unused. A typed `t<K extends StringKey>` removes the problem. Copy that arrives late blocks every screen's Playwright check, because the checks read visible text.

Weigh in: Content specialist, give me the list of new strings per milestone so the worker can wait on them.

## 10. UX standards check

Position: I can only comment on cost. The 21-accessibility.md checklist is testable and should be tests, not review items. Route title, focus on h1, polite route announcement, target size, reflow at 320 and 375, forced colors, reduced motion and axe at 375 and 1440 each get one Playwright assertion, written once in the shell milestone and then run on every page. Skip pixel-snapshot tests, which are flaky and cost upkeep. Use aria snapshots and computed-style assertions instead.

Why: Deque's automation finds about 57 percent of issues (21-accessibility.md notes, vendor data), so axe is a floor and the manual list stays. But the 2.4.2, 4.1.3, 2.4.11, 1.4.10 rows already name a test method each.

Weigh in: Designer and architect, which of the checklist rows do you consider manual-only? I will plan those as owner checks at cutover.

## 11. Testing

Position: Keep the old suite untouched and green on development until cutover. Build the new suite beside it. Port by category, not file by file.

Carries over nearly verbatim (about 1,260 methods plus the 123 resolver fixtures). test_resolve 252, test_rules_schema 252, test_collect 85 and overlay 19, test_git_check 85, test_local_root 9, test_version 27, test_json_edit 116, test_edit_store 241, test_edit_security 31, test_transcripts and links 79, test_prices 64. pytest runs unittest.TestCase classes unchanged, so the first port is a path change plus a conftest that replaces tests/helpers.py (806 lines, home guards and Sandbox). Do not rewrite them into pytest idiom. That is churn with no new coverage.

Rewritten against a new layer (about 1,060 methods). The edit route tests (api_edit 368, api_edit_settings 102, edit_server 50, picker 38), api_settings 59, api_usage 71, api_live 100, usage 101, pincheck 53 (narrowed to phase 1), projects 38 and agent_frontmatter 80 (strict reader replaced by ruamel). Reuse their fixtures and expected values as the spec. For usage and live, add a differential test that runs the demo transcripts through the old code and the new ingest and compares totals.

Dies. test_server 50 and test_static_shell 48 (http.server), the JS side (796 checks over 16,900 lines on a fake DOM, plus 22 Python wrappers), and the 86 browser tests the owner runs by hand. These become Vitest with Testing Library and Playwright with axe. Do not port the 5,860-line edit_card_checks. A scout should extract the 258 check names as a behaviour list, and the worker writes component tests from that list.

Untouched. test_hivemind 320, plugin_hivemind 46, skill_probe 54, hook_roster 10, harness_guard 117, installer tests.

Add. hypothesis on json_edit and edit_store (parse before and after is the oracle), a committed openapi.json with a drift check like build_plugins --check, and a check that generated TypeScript types are current.

Per change, three tiers. T1 is the changed area only, seconds, run by the worker. T2 is the whole new pytest plus Vitest plus typecheck plus lint, about two to three minutes, run by the lead. T3 is Playwright with axe at both widths, run at milestone end. The old 370-second suite runs only when old files change.

Why: Sizes from architecture.md 1.6 and grep. The unittest and pytest point is documented behaviour of pytest. Old tests insert `dashboard/` into sys.path and import flat modules (tests/test_resolve.py:24-27). If the new package keeps flat module names during the port, each file needs one line changed. If it uses a package with relative imports, every mock.patch string breaks, and there are 171 mock.patch calls in tests/*.py.

Weigh in: Architect, can the pure modules keep flat import names until after cutover?

## 12. Build order and coexistence

Position: New code goes in a new top-level folder in this repo (I call it `app/`, architect to name it), merged to development by one PR per milestone. No long-lived branch. The old app lives on development as the working product and the test oracle, in bug-fix-only mode. build_plugins.py ships a fixed list of folders (tools/build_plugins.py:96-121, reads git ls-files at 153), so a new top-level folder does not enter the payload and triggers no plugin version bump (project fact L-13fb). Shared data (rules.json, agent_fields.json, prices.json, experiments) stays in dashboard/ and the new app reads it by path in development. A build step copies it at cutover. Fixtures under tests/fixtures are append-only until cutover. New fixtures go in app/tests/fixtures.

Milestones. Weight is my opinion of share of total effort.

| M | Content | Size | Weight | Main risk |
|---|---|---|---|---|
| M0 | Walking skeleton and spikes. uv project, Node 24, CI, hello page and one API through the real launcher and a built payload with tracked dist. Spikes. Single-use code swap, uv SIGTERM and SessionEnd with a shared server, json_edit array ops, ruamel byte-equality | M | 5% | Packaging. Found late, it costs a milestone |
| M1 | Port pure core (resolver, rules, collect, prices, transcripts parser, edit_store, json_edit) with their tests. ASGI gate, project registry, keys | L | 12% | Import and mock paths, helper port |
| M2 | SQLite ingest, usage query API, differential tests, backup job | M | 8% | Format drift, row loss on rescan |
| M3 | Shell, tokens, charts, usage pages, a11y and Playwright harness | XL | 20% | React Aria Table and ComboBox under CSP, phone tables |
| M4 | Setup read side and collectors, To fix, rules page, catalog | L | 12% | Collector breadth |
| M5 | Live and the dispatch canvas | L | 8% | Canvas layout and timers on a fake clock |
| M6 | Edit core in the new stack, registry, preview shape, review rail, five keys, agent model and effort | XL | 15% | Data loss, stale checks, races (26-08) |
| M7 | Cutover prep. Parity matrix, docs, payload swap, owner dogfood | M | 4% | See point 12 cutover |
| Later | Markdown edits and text editor, skills, hooks and risky tier, MCP, output styles, Linux | L each | 16% | Scope |

Parallel tracks. After M1 freezes the OpenAPI file, the front end (M3) can build against recorded payloads while backend work (M2, M4) continues. Two leads in two worktrees needs the owner's yes again (memory note on the usage build). A worktree agent starts at origin/main, not development (project fact D-3ca7).

Cutover. Entry criteria are a parity matrix with every old page and every old edit marked done or dropped on purpose (24-coverage-matrix.md Matrix A), differential tests green, Playwright and axe green, and a week of the owner using the new app on real data. Only the owner touches real ~/.claude. Agents use fixtures. At cutover, build_plugins gets the new payload list, plugin.json goes to 0.2.0, the old dashboard/ moves out of the payload list, and a git tag marks the last old release. Rollback is the tag plus the old plugin version, and it is safe because the backups folder and ledger stay compatible. Delete old code one release after, not at cutover.

Data carry-over is small. The ledger and backups carry unchanged. The project list file keeps its format. The database starts empty and ingests whatever transcripts still exist, so history begins at first run. Tell the owner that plainly.

Why: Evidence in the sources above. The skeleton goes first because the launcher, guard hook (project facts L-bd45, L-979a), uv recipe (20-decisions.md spike 2) and tracked dist all meet at the plugin boundary, and each has its own tests (test_plugin_launcher 73, test_plugin_build 51). The test_plugin_build import test (stdlib only) must be replaced at cutover (architecture.md 5.3).

Weigh in: Architect, confirm one server with several Claude Code sessions needs an owner count or lease in the launcher, since the SessionEnd rule stops "idle servers" today.

## 13. Open floor

Position: Four items nobody owns yet.
- Python versions. /usr/bin/python3 is 3.9.6 and is what the old suite and the launcher run on. The new backend needs 3.11 or later through uv. The launcher must stay 3.9-compatible since it runs on whatever python3 starts it. Two test environments exist until cutover, so scripts must name which one they use.
- Tracked build output. The decisions require built Vite files in git. Hashed file names change on every build, so every UI PR would carry a large binary-ish diff and a payload version bump. Build and commit the bundle at milestone ends and release commits only, with a drift check, and run dev from the Vite dev server (which needs a looser CSP, as 20-decisions.md notes). Build into the payload path directly so the bundle is tracked once, not twice.
- No CI exists (architecture.md finding 31). Add GitHub Actions for T2 on Linux in M0. Owner decision on the cost of Actions minutes for a private repo [NEEDS CONFIRMATION: repo visibility and minutes].
- Supply chain. React, React Aria, TanStack, CodeMirror, Vite, Vitest, Playwright, openapi-typescript and uv's Python packages bring hundreds of transitive packages. The coverage matrix lists the policy as an open gap. Minimum is `npm ci` from a committed lockfile, exact pins, `ignore-scripts` for installs, and `uv sync --frozen`. This is an S task in M0.

Also. Do not run `claude` or any Claude Code harness batch as a test (project fact T-07ef). Playwright browsers are a large first download. Node on this machine is 20.19.6, so Node 24 needs an nvm install first.

Weigh in: Designer, say whether a Vite dev server with hot reload is needed for your work, or whether static built output is enough for design review.

## Top three concerns

1. Scope against capacity. The decisions describe four products at once. Without a hard first-release cut (parity plus history plus read-everything plus five edit keys) the build has no finish line, and the riskiest code (the editor, the risky tier) arrives before the core is proven.
2. Packaging found late. The launcher, uv recipe, tracked build output, per-request nonce, single-use code swap and shared-server lifecycle all meet at the plugin boundary, and only the first two have spikes. Build a walking skeleton through the real launcher and a built payload in M0, before any feature.
3. Losing behaviour in the port. About 1,260 pure-logic tests carry over cheaply, but about 1,060 API-layer tests and all 796 JS checks are rewritten. Without a behaviour inventory and differential tests that use the old app as the oracle, the new suite can pass while quietly dropping cases the old one pinned. The old code must stay until that comparison is green.

HIVEMIND
USED T-7629, T-5589, L-13fb, L-bd45, L-979a, D-3ca7, K-819f, R-06c2, W-7178, T-3ad1
NEW dashboard-plugin: tools/build_plugins.py ships a fixed folder list (routing_dashboard_files at lines 96-121, git ls-files at 153), so a new top-level folder does not enter the payload and needs no plugin version bump | check: sed -n 96,125p tools/build_plugins.py | evidence: tools/build_plugins.py
NEW testing-edit-core: edit_store._read_ledger accepts any rows that are dicts when version is 1, so extra optional row fields do not break the reader | check: sed -n 782,801p dashboard/edit_store.py | evidence: dashboard/edit_store.py
END HIVEMIND

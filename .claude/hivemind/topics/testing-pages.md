# testing-pages

### P-db96 Static and node check traps
fact: A new app.css block headed ' * Title' fails test_one_section_per_page_with_shared_first, so Settings CSS uses one-line comments inside "Settings and trail", and test_settings_page_layout_stays_inside_its_scope checks each rule's leftmost class. Object.assign( on anything but an object literal in dashboard/static/js fails test_no_file_gets_around_the_link_helpers. fakedom createPage() swaps globalThis.document, so patch document after the page exists. edit_session_checks.mjs shows how to reach app.js's ctx from a copy. To prove a node check bites, mutate a scratch tar copy of the repo, not the tree.
check: grep -n "Object.s.*assign\|shared_first" tests/test_static_shell.py
evidence: tests/test_static_shell.py, tests/js/fakedom.mjs, tests/js/edit_session_checks.mjs
fp: b5295d512535
as_of: 0a1241f 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### P-153a Card source lists hold six files
fact: CARD_FILES in test_edit_card_js.py and the source list in edit_card_checks.mjs hold edit_card, edit_flow, edit_pick, edit_review, edit_foot and edit_ui. A new card module joins both.
check: grep -n "edit_pick" tests/test_edit_card_js.py tests/js/edit_card_checks.mjs
evidence: tests/test_edit_card_js.py, tests/js/edit_card_checks.mjs
fp: 2f4a44ed6e55
as_of: 0a1241f 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### P-2fdd edit_card_checks: project keys, flows persist
fact: edit_card_checks.mjs drives the Settings page with a unique project key per app and targets stamped with it, because targetsData returns null on a project mismatch. Flows persist between checks, so a check on notSavedProjects starts with fresh(), an off render.
check: grep -n "function fresh" tests/js/edit_card_checks.mjs
evidence: tests/js/edit_card_checks.mjs, dashboard/static/js/edit_flow.js
fp: 75e5082368e4
as_of: 0a1241f 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### P-d516 fakedom: disabled focus, topbar outside the root
fact: fakedom focus() ignores a disabled element. page.doc.documentElement is not the parent of the app tree, so find shell options with page.topbar.find.
check: grep -n "app.topbar.find" tests/js/edit_session_checks.mjs
evidence: tests/js/fakedom.mjs, tests/js/edit_session_checks.mjs
fp: 4944b52148d5
as_of: 0a1241f 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### P-71ad One live object binds once per window
fact: A page that keeps one live object binds window and document listeners once, as band.js and trail.js do with boundTo, because createPage makes a new window for each test page.
check: grep -n boundTo dashboard/static/js/pages/band.js dashboard/static/js/pages/trail.js
evidence: dashboard/static/js/pages/band.js, dashboard/static/js/pages/trail.js
fp: ade7c2ced682
as_of: 0a1241f 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### P-c029 e2e_checks JSON also feeds the node pages test
fact: pages.mjs reads every tests/e2e_checks/*.json through test_pages_js.py as well as the browser sweep, so a text change updates that file. In the E2E rail .s4-note also matches the shared-file and still-holds notes, so waits match Pick a file by text (PICK_NOTE).
check: grep -n PICK_NOTE tests/test_edit_e2e.py
evidence: tests/js/pages.mjs, tests/test_edit_e2e.py, dashboard/static/js/edit_review.js
fp: def54428e57f
as_of: 0a1241f 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0

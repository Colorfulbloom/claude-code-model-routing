# dashboard-browser

### X-2617 Chrome extension traps: resize_window, navigating to /api
fact: resize_window reported 375, then 1440, while innerWidth stayed 1818, so read innerWidth after each resize. A new tab can open at 500x679 and stay there; under 721 the real (max-width: 720px) rules apply, so check innerWidth before a wide check. frame-ancestors 'none' rules out an iframe. server.py's Sec-Fetch-Site guard exempts only GET / with Mode navigate and Dest document, so a navigate to /api/settings gets forbidden. Read JSON with fetch() from the loaded page.
check: /usr/bin/python3 -m unittest discover -s tests -p test_server.py -k cross_site
evidence: dashboard/server.py, tests/test_server.py
fp: 1aa46b7cce4f
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-10-30
last_used: 2026-11-02
uses: 7

### X-1bf6 Usage pages draw through fillUsage; checks wait on data-usage
fact: Only the section sectionFor names draws. Usage pages draw through fillUsage in usage-page.js, which owns the empty, wait, error and unreadable states. data-rendered doesn't wait on /api/usage. app.js sets data-usage="1" once the first answer for the current project is drawn, so a check of usage numbers waits for both. Chrome's innerText applies text-transform, so e2e text compares casefold.
check: grep -n "data-usage" dashboard/static/js/app.js
evidence: dashboard/static/js/app.js, dashboard/static/js/usage-page.js, tests/test_pages_e2e.py
fp: 97d01afbfa3c
as_of: 6206393 2026-11-02
author: fast-worker
created: 2026-10-30
last_used: 2026-10-30
uses: 0

### X-b269 e2e_checks JSON also feeds the node pages test
fact: pages.mjs reads every tests/e2e_checks/*.json through test_pages_js.py as well as the browser sweep, so a text change updates that file. In the E2E rail .s4-note also matches the shared-file and still-holds notes, so waits match Pick a file by text (PICK_NOTE). The E2E fixture (project line, no local file) preselects a local create, so no Pick a file shows there: waits use positive signs (picked row, diff, New file tag, Save on).
check: grep -n PICK_NOTE tests/test_edit_e2e.py
evidence: tests/js/pages.mjs, tests/test_edit_e2e.py, dashboard/static/js/edit_review.js
fp: 65295df8b882
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-11-01
last_used: 2026-11-02
uses: 4

### X-b9fc Width emulation leaves clientWidth real; reload per width
fact: Setting html style width leaves documentElement.clientWidth at the real viewport, and band_drag.js clamps drags by clientWidth, so drag results under emulation are not exact. A hash-only navigate keeps the page and its Arrange state, so reload before each width.
check: grep -n "clientWidth" dashboard/static/js/pages/band_drag.js
evidence: dashboard/static/js/pages/band_drag.js
fp: db0df9ed7a24
as_of: a452d5d 2026-11-03
author: judge
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### X-5529 Browser worlds: Save bar and managed allowlist
fact: Without --allow-edits the server has no write routes, so no Save bar (.s4-rf) or Not saved state shows; Save bar checks need --allow-edits. A --fixture copy outside the repo with a project model line, served with --allow-edits, gives a managed-allowlist world where blocked model options are disabled and labelled "(not allowed)".
check: grep -n "ed_model_opt_blocked" dashboard/static/strings.json; grep -n "def write_routes_for" dashboard/server.py
evidence: dashboard/server.py, dashboard/static/strings.json, tests/fixtures/resolution/available-managed-over-user-and-project/managed/managed-settings.json
fp: b0ba4391fcce
as_of: a452d5d 2026-11-03
author: judge
created: 2026-11-03
last_used: 2026-11-03
uses: 0

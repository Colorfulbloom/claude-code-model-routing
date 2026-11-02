# testing-node

### N-9919 settings_checks.mjs reads payloads from MR_PAYLOADS
fact: tests/js/settings_checks.mjs needs MR_PAYLOADS, a folder tests/test_settings_js.py fills from its CASES list (write_payloads), so run it through that test. A real fixture a node check names with real(...) joins CASES, or the check fails with ENOENT.
check: grep -n 'CASES\|MR_PAYLOADS' tests/test_settings_js.py tests/js/settings_checks.mjs
evidence: tests/test_settings_js.py, tests/js/settings_checks.mjs
fp: 055afdc66199
as_of: 399f865 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 1
promote: approved

### N-5baa fakedom events, localStorage and whole-page counts
fact: fakedom dispatch runs capture listeners, then the target's, then bubble, with stopPropagation, stopImmediatePropagation, defaultPrevented and removeEventListener. addEventListener takes true or {capture}. createPage has a localStorage beside sessionStorage, and Object.defineProperty on page.win makes it throw. Whole-page button counts skip .s6-arr (buttons() in edit_card_checks.mjs), and bandOf matches s5-a as one class among several.
check: node --experimental-default-type=module tests/js/band_reorder_checks.mjs
evidence: tests/js/fakedom.mjs, tests/js/edit_card_checks.mjs, tests/js/edit_session_checks.mjs
fp: f9aecd42cadd
as_of: 6206393 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### N-5dc5 Band modules hold state between node checks
fact: pages/band_arrange.js keeps the Arrange open flag for one project path, pages/band.js keeps a Map for blocked storage, and pages/band_drag.js keeps the press and click eater. Each node check takes a new path (payloadFor) and ends every press with a release or quiet end, or the next check fails with a misleading error.
check: grep -n 'payloadFor' tests/js/band_reorder_checks.mjs
evidence: dashboard/static/js/pages/band_arrange.js, dashboard/static/js/pages/band.js, dashboard/static/js/pages/band_drag.js
fp: 7d678a36cc35
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### N-2a80 The band is 1056 wide in a 1360 window
fact: A 1360 window less the 240 sidebar and two 32 gutters (--space-6) leaves a 1056 band, so 8 cells of 132 (MIN_CELL) fit. Node tests in settings_checks.mjs read app.css and tokens.css to hold this.
check: /usr/bin/python3 -m unittest discover -s tests -p test_settings_js.py
evidence: tests/js/settings_checks.mjs, dashboard/static/app.css, dashboard/static/js/band_order.js
fp: 152447204974
as_of: 6206393 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### N-e2fd edit_card_checks rows at rest have no radio
fact: In tests/js/edit_card_checks.mjs, rows at rest are plain div.s6-r with no radio input, so find them by their s4-ln text (plainRows), not through rowIn or rowOf, which walk p2-row inputs.
check: grep -n "const plainRows\|const rowIn\|const rowOf" tests/js/edit_card_checks.mjs
evidence: tests/js/edit_card_checks.mjs
fp: 52153401ae2f
as_of: 057353e 2026-11-02
author: fast-worker
created: 2026-11-02
last_used: 2026-11-02
uses: 0

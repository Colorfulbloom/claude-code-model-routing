# dashboard-band

### A-3436 Arrange cells are links at rest, divs while pressed
fact: Band cells are a.s4-stat links at rest and div.s4-stat only while Arrange is pressed, so an E2E wait for CELLS (nav.s5-a > div.s4-stat[data-setting]) before press_arrange() never succeeds; wait on the a.s4-stat cells first.
check: grep -n "resting\|^CELLS" tests/test_band_arrange_e2e.py
evidence: tests/test_band_arrange_e2e.py, dashboard/static/js/pages/band.js
fp: 65d978477e91
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### A-cb5f band_reorder_checks.mjs runs from test_settings_js.py
fact: tests/js/band_reorder_checks.mjs is run by tests/test_settings_js.py (REORDER), not by test_shell_js.py or test_pages_js.py. A status-line string change updates its assertions there and in tests/test_band_arrange_e2e.py. fakedom createPage() defaults to narrow (matchMedia answers phone), so desktop band checks pass {narrow: false}.
check: grep -n REORDER tests/test_settings_js.py
evidence: tests/test_settings_js.py, tests/js/band_reorder_checks.mjs, tests/js/fakedom.mjs
fp: 2452d1aaf0fc
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### A-aed6 element.click() never moves focus in E2E
fact: In E2E a JS element.click() never moves focus, and the desktop Arrange press leaves focus where it was (only phones focus the first step), so a test that asserts focus on Arrange focuses it and presses Enter, or sends a CDP mouse click.
check: grep -n "isNarrow()) arrange.focusFirst" dashboard/static/js/pages/band.js; grep -n "press_enter(self.page)" tests/test_band_arrange_e2e.py
evidence: dashboard/static/js/pages/band.js, tests/test_band_arrange_e2e.py
fp: 5deb0676307f
as_of: a452d5d 2026-11-03
author: verifier
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### A-8f4c Band drag classes and where their styles apply
fact: A drag adds .s6-ghost to the source cell, .is-dragging to the rows and a .s6-lift copy, and Esc is a capture-phase keydown on document. .s6-ghost and .s6-mdrop styles sit under .s6-a (the band nav) and again under .s7-trow for the tray row, so a cell anywhere else gets no ghost or drop styling. The lift and slot line stay in the nav.
check: grep -n "s6-a .s6-ghost\|s7-trow .s6-ghost" dashboard/static/app.css
evidence: dashboard/static/app.css, dashboard/static/js/pages/band_drag.js
fp: bf266687a9cc
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### A-f16f Settings render restores Arrange focus first
fact: While arranging over 720px the step buttons sit inside data-setting cells, so the settings.js render restores a focused Arrange action before a focused setting.
check: grep -n "else if (arrangeKey)" dashboard/static/js/pages/settings.js
evidence: dashboard/static/js/pages/settings.js
fp: 57eda423d1c7
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-11-03
last_used: 2026-11-03
uses: 0

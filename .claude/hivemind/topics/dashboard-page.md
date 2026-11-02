# dashboard-page

### K-486e Browser trials: adoptedStyleSheets, narrow widths, drags
fact: The CSP has style-src 'self', so an injected style tag does nothing and live CSS trials use document.adoptedStyleSheets. When resize_window leaves innerWidth alone, set document.documentElement.style.width, dispatch resize, adopt the inner rules of the @media (max-width) blocks, and read body.scrollWidth. The computer tool has no mouse-down, so mid-drag reads need scripted PointerEvents (pointerType mouse, buttons 1) on document.
check: grep -n "Content-Security-Policy\|style-src" dashboard/server.py
evidence: dashboard/server.py, dashboard/static/js/pages/band_drag.js
fp: 2d721482bed6
as_of: 02a9206 2026-11-02
author: designer
created: 2026-11-01
last_used: 2026-11-02
uses: 2

### K-6860 Nested :has() drops the whole rule
fact: Nested :has() is invalid CSS, so the browser drops the whole rule with no error. The Settings rail padding was dead this way while pages/settings.js set --s4-foot correctly. Check rail padding by computed value, not by the variable. test_the_rail_foot_docks_by_itself_at_1240_and_the_page_holds_no_second_dock pins the fixed selector.
check: /usr/bin/python3 -m unittest discover -s tests -p test_static_shell.py -k the_rail_foot_docks
evidence: dashboard/static/app.css, dashboard/static/js/pages/settings.js, tests/test_static_shell.py
fp: bc8a98ebb069
as_of: 6206393 2026-11-02
author: designer
created: 2026-11-01
last_used: 2026-11-02
uses: 2
promote: approved

### K-9709 Settings rail needs grid-auto-rows max-content
fact: .s4-rb is a height-bound grid and .p2-df has overflow hidden, so without grid-auto-rows max-content on the pane a diff can shrink and clip with no scroll at 1241 and up. Fixture diffs of a few lines hide this.
check: grep -n "^\.s4-rb{\|^\.p2-df{" dashboard/static/app.css
evidence: dashboard/static/app.css
fp: ae21f4eededb
as_of: 6206393 2026-11-02
author: designer
created: 2026-11-01
last_used: 2026-11-02
uses: 1

### K-9e3f edit_flow.js stays clear of pages/settings.js
fact: edit_flow.js must not import a file that reaches pages/settings.js (edit_review.js and edit_backup.js do). That closes an import cycle through edit_card.js, and node checks fail with "Cannot access 'redrawer' before initialization". Pure rules the flow needs go in edit_pick.js.
check: grep -n "^import" dashboard/static/js/edit_flow.js
evidence: dashboard/static/js/edit_flow.js, dashboard/static/js/edit_pick.js
fp: b7e691421e2e
as_of: 6206393 2026-11-02
author: fast-worker
created: 2026-11-01
last_used: 2026-11-02
uses: 1

### K-7dc3 Where it's set rows: a list value needs s6-wide
fact: .s6-r rows have three columns with the third empty at rest, so a list value would wrap one name per line. where.js adds s6-wide for an array value. rowNode puts cls in a class array, so pass a flat string: a nested array renders ",s6-wide".
check: grep -n 's6-wide' dashboard/static/js/pages/where.js dashboard/static/app.css
evidence: dashboard/static/js/pages/where.js, dashboard/static/app.css
fp: 8f24b8704751
as_of: 6206393 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### K-819f String keys count only in a literal t() call
fact: tests/test_static_strings.py counts a string as used only in a literal t("key" or tn("key" call, so a key passed to a helper such as pathLine("key", ...) reads as unused.
check: /usr/bin/python3 -m unittest discover -s tests -k strings
evidence: tests/test_static_strings.py, dashboard/static/js/edit_foot.js
fp: 1c20ccb57cd5
as_of: 399f865 2026-11-02
author: fast-worker
created: 2026-11-01
last_used: 2026-11-02
uses: 9
promote: approved

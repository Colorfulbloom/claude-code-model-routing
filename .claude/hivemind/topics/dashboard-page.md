# dashboard-page

### K-486e Live CSS trials need adoptedStyleSheets
fact: The page's CSP has style-src 'self', so it blocks an injected style tag, and a live CSS trial on the dashboard uses document.adoptedStyleSheets. An injected style looks like a fix that had no effect.
check: grep -n "Content-Security-Policy\|style-src" dashboard/server.py
evidence: dashboard/server.py
fp: dffaaa3fd398
as_of: 7da3051 2026-11-01
author: designer
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### K-6860 Nested :has() drops the whole rule
fact: Nested :has() is invalid CSS, so the browser drops the whole rule with no error. The Settings rail padding was dead this way while pages/settings.js set --s4-foot correctly. Check rail padding by computed value, not by the variable. test_the_rail_foot_docks_by_itself_at_1240_and_the_page_holds_no_second_dock pins the fixed selector.
check: /usr/bin/python3 -m unittest discover -s tests -p test_static_shell.py -k the_rail_foot_docks
evidence: dashboard/static/app.css, dashboard/static/js/pages/settings.js, tests/test_static_shell.py
fp: 367091f9dfac
as_of: 7da3051 2026-11-01
author: designer
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### K-9709 Settings rail needs grid-auto-rows max-content
fact: .s4-rb is a height-bound grid and .p2-df has overflow hidden, so without grid-auto-rows max-content on the pane a diff can shrink and clip with no scroll at 1241 and up. Fixture diffs of a few lines hide this.
check: grep -n "^\.s4-rb{\|^\.p2-df{" dashboard/static/app.css
evidence: dashboard/static/app.css
fp: 6a9363d1d0fa
as_of: 7da3051 2026-11-01
author: designer
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### K-9e3f edit_flow.js stays clear of pages/settings.js
fact: edit_flow.js must not import a file that reaches pages/settings.js (edit_review.js and edit_backup.js do). That closes an import cycle through edit_card.js, and node checks fail with "Cannot access 'redrawer' before initialization". Pure rules the flow needs go in edit_pick.js.
check: grep -n "^import" dashboard/static/js/edit_flow.js
evidence: dashboard/static/js/edit_flow.js, dashboard/static/js/edit_pick.js
fp: 2850a90cb901
as_of: 7da3051 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### K-819f String keys count only in a literal t() call
fact: tests/test_static_strings.py counts a string as used only in a literal t("key" or tn("key" call, so a key passed to a helper such as pathLine("key", ...) reads as unused.
check: /usr/bin/python3 -m unittest discover -s tests -k strings
evidence: tests/test_static_strings.py, dashboard/static/js/edit_foot.js
fp: 678a44757e97
as_of: 7da3051 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0

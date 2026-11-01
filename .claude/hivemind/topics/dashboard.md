# dashboard

### W-d2ec Chrome extension traps: resize_window, navigating to /api
fact: resize_window reported 375, then 1440, while innerWidth stayed 1818, so read innerWidth after each resize. frame-ancestors 'none' rules out an iframe. server.py's Sec-Fetch-Site guard exempts only GET / with Mode navigate and Dest document, so a navigate to /api/settings gets forbidden. Read JSON with fetch() from the loaded page.
check: /usr/bin/python3 -m unittest discover -s tests -p test_server.py -k cross_site
evidence: dashboard/server.py, tests/test_server.py
fp: beb3d3798880
as_of: 0766733 2026-10-31
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 4

### W-7178 Browser-free JS checks run under node
fact: tests/test_shell_js.py runs tests/js/checks.mjs on fakedom.mjs. tests/test_pages_js.py runs the real app.js over pages.mjs and every route in tests/e2e_checks/. Both skip without node. Alone: node --experimental-default-type=module tests/js/checks.mjs, and --check syntax-checks a module. Modules hold state, so each check imports a fresh copy: app.js?run=N or pages/x.js?copy=N. h() sets value as a property, so read o.value.
check: /usr/bin/python3 -m unittest discover -s tests -p test_shell_js.py
evidence: tests/test_shell_js.py, tests/js/rules_checks.mjs, dashboard/static/js/h.js, tests/test_pages_js.py
fp: 33b0db260eba
as_of: 0a1241f 2026-11-01
author: fast-worker
created: 2026-10-30
last_used: 2026-11-01
uses: 8

### W-f6ed macOS traps in server tests: bytecode prefix, second bind
fact: /usr/bin/python3 3.9.6 sets sys.pycache_prefix under $HOME/Library/Caches, so a no-writes test that hashes source folders passes even with dont_write_bytecode False. Run the child with -X pycache_prefix=, as NoWrites does; -B would defeat it. A second bind to 0.0.0.0 fails even for a loopback-only socket, so check with lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN -Fn.
check: /usr/bin/python3 -X pycache_prefix= -c "import sys;print(sys.pycache_prefix)"
evidence: tests/test_server.py
fp: f1a0242fb4ac
as_of: 0766733 2026-10-31
author: fast-worker
created: 2026-10-30
last_used: 2026-10-31
uses: 2

### W-4654 Rules for one key share one combine; order picks rule_id
fact: All rules for one key and scope share one combine, or resolve.py raises "rules for X combine in different ways". A rule beside a lowest_value row needs lowest_value and a value_order. rule_id goes to the earliest equally specific voter in rules.json, so a values rule sits after the per-model rule.
check: /usr/bin/python3 dashboard/resolve.py | tail -1
evidence: dashboard/rules.json, dashboard/resolve.py
fp: 02f79bcf4f0f
as_of: 0766733 2026-10-31
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 1

### W-e6b6 Usage pages draw through fillUsage; checks wait on data-usage
fact: Only the section sectionFor names draws. Usage pages draw through fillUsage in usage-page.js, which owns the empty, wait, error and unreadable states. data-rendered doesn't wait on /api/usage. app.js sets data-usage="1" once the first answer for the current project is drawn, so a check of usage numbers waits for both. Chrome's innerText applies text-transform, so e2e text compares casefold.
check: grep -n "data-usage" dashboard/static/js/app.js
evidence: dashboard/static/js/app.js, dashboard/static/js/usage-page.js, tests/test_pages_e2e.py
fp: f8a0753e3638
as_of: 0a1241f 2026-11-01
author: fast-worker
created: 2026-10-30
last_used: 2026-10-30
uses: 0

### W-4518 Settings: external links, Escape, implicit project
fact: Links to other sites go only through externalLink in h.js, https only. trail.js hears Escape in the capture phase to act before shell.js. A missing_folder project answers with empty entries unless it is implicit, which still resolves.
check: grep -n "not project.implicit" dashboard/api_settings.py
evidence: dashboard/static/js/h.js, dashboard/static/js/pages/trail.js, dashboard/api_settings.py
fp: 2db97570cc0d
as_of: 0a1241f 2026-11-01
author: deep-reasoner
created: 2026-10-31
last_used: 2026-11-01
uses: 4

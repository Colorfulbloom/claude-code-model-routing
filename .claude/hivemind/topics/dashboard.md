# dashboard

### W-871e A Sec-Fetch-Site guard must exempt the top-level load of /
fact: A server that refuses cross-site Sec-Fetch-Site also refuses a plain link from another site. server.py exempts only GET / with Mode navigate and Dest document, a page with no settings that frame-ancestors keeps unframed. Keep it that way. A Chrome extension navigate to /api/settings got forbidden, so read JSON with fetch() from the loaded page.
check: /usr/bin/python3 -m unittest discover -s tests -p test_server.py -k test_cross_site_link_opens
evidence: dashboard/server.py, tests/test_server.py
fp: 123182b228b8
as_of: 3fd2d26 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 1

### W-d2ec resize_window's success message does not prove the size changed
fact: The Chrome extension's resize_window has not reached 375, and its success message proves nothing. On October 30 it reported 375, then 1440, while innerWidth stayed 1818. The page sets frame-ancestors 'none', so an iframe cannot stand in. Read innerWidth after each resize.
check: grep -n "frame-ancestors" dashboard/server.py
evidence: dashboard/server.py, tests/test_shell_e2e.py
fp: 30dd51a6fc57
as_of: 3fd2d26 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 2

### W-1acf fetchJSON reads error bodies so failed fetches finish
fact: Before 493d2de a 404 body went unread, and the e2e count saw 1 resource timing entry where 2 were expected. Chrome likely leaves an unfinished response out of Resource Timing, inferred from the code and counts. Keep the read on every status.
check: grep -n "await res.text()" dashboard/static/js/api.js
evidence: dashboard/static/js/api.js, tests/js/checks.mjs
fp: 0f700c2bfa02
as_of: 3fd2d26 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 0

### W-7178 Browser-free JS checks run under node
fact: tests/js/checks.mjs and fakedom.mjs run through tests/test_shell_js.py, which skips without node. Alone: node --experimental-default-type=module tests/js/checks.mjs. The same flag with --check syntax-checks a module under dashboard/static/js. Each scenario needs a fresh import("app.js?run=N"), because app.js holds module state. h() sets value as a property, so read o.value.
check: /usr/bin/python3 -m unittest discover -s tests -p test_shell_js.py
evidence: tests/test_shell_js.py, tests/js/checks.mjs, dashboard/static/js/h.js
fp: 14346e7526b7
as_of: 0e72fd4 2026-10-30
author: fast-worker
created: 2026-10-30
last_used: 2026-10-30
uses: 1

### W-f6ed macOS traps in server tests: bytecode prefix, second bind
fact: /usr/bin/python3 3.9.6 sets sys.pycache_prefix under $HOME/Library/Caches, so a no-writes test that hashes source folders passes even with dont_write_bytecode False. Run the child with -X pycache_prefix=, as NoWrites does, because -B would defeat the test. A second bind to 0.0.0.0 fails even when the first socket is loopback-only, so check loopback with lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN -Fn.
check: /usr/bin/python3 -X pycache_prefix= -c "import sys;print(sys.pycache_prefix)"
evidence: tests/test_server.py
fp: adc193b6c0d9
as_of: 3fd2d26 2026-10-30
author: fast-worker
created: 2026-10-30
last_used: 2026-10-30
uses: 0

### W-4654 Rules for one key share one combine; order picks rule_id
fact: All rules for one key and scope share one combine. A rule beside a lowest_value row needs combine lowest_value and a value_order, or resolve.py raises "rules for X combine in different ways". rule_id goes to the earliest of the equally specific voters in rules.json, so a values rule sits after the per-model rule beside it.
check: /usr/bin/python3 dashboard/resolve.py | tail -1
evidence: dashboard/rules.json, dashboard/resolve.py
fp: 56ac5933f5b5
as_of: 3fd2d26 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 0

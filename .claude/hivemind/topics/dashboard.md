# dashboard

### W-871e A Sec-Fetch-Site guard must exempt the top-level load of /
fact: A server that refuses cross-site Sec-Fetch-Site also refuses a plain link from another site. server.py exempts only GET / with Mode navigate and Dest document. That page holds no settings and frame-ancestors stops framing, so keep the exemption to a page with no data.
check: /usr/bin/python3 -m unittest discover -s tests -p test_server.py -k test_cross_site_link_opens
evidence: dashboard/server.py, tests/test_server.py
fp: 806584d37230
as_of: 0e72fd4 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 0

### W-d2ec resize_window's success message does not prove the size changed
fact: The Chrome extension's resize_window has not reached 375. The Shell lead saw a floor near 1000 CSS px and got 1440 from a 1183 request. A repeat on October 30 reported success from 1440 to 375 while innerWidth stayed 1818. The page sets frame-ancestors 'none', so an iframe cannot stand in. Read innerWidth after each resize.
check: grep -n "frame-ancestors" dashboard/server.py
evidence: dashboard/server.py, tests/test_shell_e2e.py
fp: c88f5b082769
as_of: 0e72fd4 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 0

### W-1acf fetchJSON reads error bodies so failed fetches finish
fact: Before 493d2de a 404 body went unread, and the e2e count saw 1 resource timing entry where 2 were expected, while a Node check counted both fetch calls. Chrome likely leaves an unfinished response out of Resource Timing. That cause comes from the code and the counts, not from watching a browser. Keep the read on every status.
check: grep -n "await res.text()" dashboard/static/js/api.js
evidence: dashboard/static/js/api.js, tests/js/checks.mjs
fp: 0f700c2bfa02
as_of: 0e72fd4 2026-10-30
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
uses: 0

### W-f6ed Apple python3 keeps bytecode away from the source folder
fact: /usr/bin/python3 3.9.6 sets sys.pycache_prefix under $HOME/Library/Caches, so a no-writes test that hashes source folders passes even with dont_write_bytecode False. Run the child with -X pycache_prefix= as NoWrites does. -B would defeat the test.
check: /usr/bin/python3 -X pycache_prefix= -c "import sys;print(sys.pycache_prefix)"
evidence: tests/test_server.py
fp: b5fd3afffdad
as_of: 0e72fd4 2026-10-30
author: fast-worker
created: 2026-10-30
last_used: 2026-10-30
uses: 0

### W-8e61 Check loopback-only with lsof, not a second bind
fact: On macOS a second bind to 0.0.0.0 on the same port fails even when the first socket is loopback-only, so that trick proves nothing. Use lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN -Fn.
check: grep -n '"lsof", "-nP"' tests/test_server.py
evidence: tests/test_server.py
fp: b5fd3afffdad
as_of: 0e72fd4 2026-10-30
author: fast-worker
created: 2026-10-30
last_used: 2026-10-30
uses: 0

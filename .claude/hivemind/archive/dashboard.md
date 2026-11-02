# dashboard

### W-8e61 Check loopback-only with lsof, not a second bind
fact: On macOS a second bind to 0.0.0.0 on the same port fails even when the first socket is loopback-only, so that trick proves nothing. Use lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN -Fn.
check: grep -n '"lsof", "-nP"' tests/test_server.py
evidence: tests/test_server.py
fp: adc193b6c0d9
as_of: 3fd2d26 2026-10-30
author: fast-worker
created: 2026-10-30
last_used: 2026-10-30
uses: 0
superseded_by: W-f6ed
retired: 2026-10-30 superseded

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
retired: 2026-10-30 retired-by-lead

### W-871e A Sec-Fetch-Site guard must exempt the top-level load of /
fact: A server that refuses cross-site Sec-Fetch-Site also refuses a plain link from another site. server.py exempts only GET / with Mode navigate and Dest document, which holds no settings and can't be framed. A Chrome extension navigate to /api/settings got forbidden, so read JSON with fetch() from the loaded page.
check: /usr/bin/python3 -m unittest discover -s tests -p test_server.py -k test_cross_site_link_opens
evidence: dashboard/server.py, tests/test_server.py
fp: 123182b228b8
as_of: 3fd2d26 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 1
superseded_by: W-d2ec
retired: 2026-10-31 superseded

### W-d2ec Chrome extension traps: resize_window, navigating to /api
fact: resize_window reported 375, then 1440, while innerWidth stayed 1818, so read innerWidth after each resize. frame-ancestors 'none' rules out an iframe. server.py's Sec-Fetch-Site guard exempts only GET / with Mode navigate and Dest document, so a navigate to /api/settings gets forbidden. Read JSON with fetch() from the loaded page.
check: /usr/bin/python3 -m unittest discover -s tests -p test_server.py -k cross_site
evidence: dashboard/server.py, tests/test_server.py
fp: be3a5991a90c
as_of: 7da3051 2026-11-01
author: deep-reasoner
created: 2026-10-30
last_used: 2026-11-02
uses: 5
superseded_by: X-2617
retired: 2026-11-02 superseded

### W-e6b6 Usage pages draw through fillUsage; checks wait on data-usage
fact: Only the section sectionFor names draws. Usage pages draw through fillUsage in usage-page.js, which owns the empty, wait, error and unreadable states. data-rendered doesn't wait on /api/usage. app.js sets data-usage="1" once the first answer for the current project is drawn, so a check of usage numbers waits for both. Chrome's innerText applies text-transform, so e2e text compares casefold.
check: grep -n "data-usage" dashboard/static/js/app.js
evidence: dashboard/static/js/app.js, dashboard/static/js/usage-page.js, tests/test_pages_e2e.py
fp: 97d01afbfa3c
as_of: 6206393 2026-11-02
author: fast-worker
created: 2026-10-30
last_used: 2026-11-02
uses: 1
superseded_by: X-1bf6
retired: 2026-11-02 superseded

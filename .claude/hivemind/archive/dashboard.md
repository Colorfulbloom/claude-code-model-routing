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

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

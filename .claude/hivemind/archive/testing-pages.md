# testing-pages

### P-c029 e2e_checks JSON also feeds the node pages test
fact: pages.mjs reads every tests/e2e_checks/*.json through test_pages_js.py as well as the browser sweep, so a text change updates that file. In the E2E rail .s4-note also matches the shared-file and still-holds notes, so waits match Pick a file by text (PICK_NOTE). The E2E fixture (project line, no local file) preselects a local create, so no Pick a file shows there: waits use positive signs (picked row, diff, New file tag, Save on).
check: grep -n PICK_NOTE tests/test_edit_e2e.py
evidence: tests/js/pages.mjs, tests/test_edit_e2e.py, dashboard/static/js/edit_review.js
fp: 4c9dda5d6703
as_of: 7da3051 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 1
superseded_by: X-b269
retired: 2026-11-02 superseded

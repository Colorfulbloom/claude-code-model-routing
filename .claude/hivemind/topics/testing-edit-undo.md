# testing-edit-undo

### U-0aa1 Ledgers are per file, history is per project
fact: Edit ledgers are per file, while history merges the layers by (time, seq), newest first. Server rows[-1] is one file's newest row and page rows[0] is the project's newest. undoable and undo_anyway are per file, but the foot draws Undo and Undo anyway only for history.rows[0], so a row can be its own file's newest, carry a flag and still sit in Older backups.
check: grep -n "rows\[-1\]" dashboard/api_edit.py; grep -n "history.rows\[0\]" dashboard/static/js/edit_foot.js
evidence: dashboard/api_edit.py, dashboard/static/js/edit_foot.js, dashboard/static/js/edit_pick.js
fp: 49d432c6d2fc
as_of: 7da3051 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 0
promote: approved

### U-7c6a The confirm ignores presses for guard.ms
fact: The confirm of an Undo anyway or restore ignores presses for guard.ms (500) after the preview draws. Node checks set guard.ms to 0 at the top and put 500 back around the double-click check. E2E waits 0.6 s in wait_back_review.
check: grep -n "guard.ms\|time.sleep(0.6)" tests/js/edit_card_checks.mjs tests/test_edit_e2e.py
evidence: dashboard/static/js/edit_flow.js, tests/test_edit_e2e.py, tests/js/edit_card_checks.mjs
fp: 379cafef8f5d
as_of: 7da3051 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### U-3f27 ForceCrashTests group seams by write kind
fact: Crash tests for force and restore live in ForceCrashTests. Each reset()s the world per seam, with seams grouped by what the write kind reaches: after_mkdir only when .claude is missing, unlink and rmdir seams only for deletes, temp and rename seams only for non-deletes.
check: /usr/bin/python3 -m unittest discover -s tests -p test_edit_store.py -k ForceCrashTests
evidence: tests/test_edit_store.py
fp: 85925f2c3c73
as_of: 7da3051 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### U-436d A bad backup name reads pruned
fact: A ledger row whose backup name fits neither NNNNNN-<16hex>.bak nor .absent reads backup_pruned, shows backup_display null and refuses restore with 409. The store never opens it, so a tampered name can't leave the backups folder. A half pair reads backup_damaged first.
check: grep -n "_valid_backup\|_valid_marker" dashboard/edit_store.py
evidence: dashboard/edit_store.py, tests/test_api_edit.py
fp: 4577ead0a112
as_of: 7da3051 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 0

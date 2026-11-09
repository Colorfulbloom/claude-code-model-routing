# testing-edit

### E-5b16 Write core: one writer, lock exceptions, Python 3.9 flags
fact: edit_store.py alone writes settings; test_edit_security allows only two other named writes: reference_page.py's PAGE_PATH open and server.py's --launch-fd descriptor. api_edit's save recomputes inside the store's locked commit, so _StaleSignal and _Answer must not subclass StoreError or OSError, or _commit_locked wraps them as WriteFailed. A preview or save reports every row that moved, agent rows included. On Python 3.9.6, O_NOFOLLOW|O_DIRECTORY on a symlink raises ENOTDIR and O_NOFOLLOW on a leaf raises ELOOP.
check: grep -n "class _StaleSignal\|class _Answer" dashboard/api_edit.py
evidence: dashboard/api_edit.py, dashboard/edit_store.py, tests/test_edit_security.py
fp: 241bce98cf1f
as_of: a452d5d 2026-11-03
author: verifier
created: 2026-10-31
last_used: 2026-11-09
uses: 16

### E-e2f0 Edit page: token first, a write drops all project data
fact: api.js caches usage and settings for the whole page load. take() in edit_session.js runs first at boot and in a hashchange listener registered before the router's. After a write, onWrite runs refreshAll in app.js: every project's data goes and generation moves, so an answer in flight drops itself. A new write route must use that path, or pages keep the old value. refreshAll waits on settings and edit data, never on /api/usage.
check: grep -n "generation\|onWrite" dashboard/static/js/app.js
evidence: dashboard/static/js/app.js, dashboard/static/js/api.js, dashboard/static/js/edit_session.js
fp: db6b8f9f6fcf
as_of: 6206393 2026-11-02
author: fast-worker
created: 2026-10-31
last_used: 2026-11-01
uses: 8

### E-83df Effort edge cases: unknown model, max, dotted paths
fact: With no known model, _computed_becomes' cap branch uses the top-level cap, so the (agent-)effort-lowered-by-cap-model-unknown rules lower the row; only the unsupported-level branch returns None. A user effortLevel on an agent row still resolves Unknown (WINNER_PRECEDENCE). max is invalid as effortLevel in every settings file: Claude Code skips it, so a file edit can't reach it. max stays valid for maxEffortLevel, where it means no cap. A modelSettings entry's path is dot-joined and model ids hold dots, so never split it.
check: ls tests/fixtures/resolution/effort-max-in-settings-invalid; grep -n 'path="modelSettings' dashboard/resolve.py
evidence: dashboard/resolve.py, dashboard/rules.json, dashboard/experiments/2026-10-29-effort-invalid-values.json
fp: 7cab5451bf3b
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-10-31
last_used: 2026-11-09
uses: 9

### E-2fea Edit tests: fixture, real managed folder, half-closed sockets
fact: build_fixture in test_edit_e2e.py is the minimal --allow-edits fixture; its env drops CLAUDE_CODE_EFFORT_LEVEL. Display paths are relative to the fixture, and backups land in <fixture>/config/routing-dashboard/backups/<id>/. A refused save can leave empty store folders. server.live_context uses the REAL managed folder, so tests dataclasses.replace(ctx, managed_dir=<temp>, root=<temp>). A raw POST that promises unsent bytes needs half_close, or the server waits out its 15 s timeout.
check: grep -n "managed_dir=self.managed" tests/test_api_edit.py
evidence: tests/test_edit_e2e.py, tests/test_api_edit.py, tests/test_edit_server.py, dashboard/server.py
fp: 09c8587420e3
as_of: 6206393 2026-11-02
author: fast-worker
created: 2026-10-31
last_used: 2026-11-01
uses: 3

### E-6ccf Edit core traps: empty text, rmdir needs dir_fd
fact: json_edit.mask_text raises IndexError on empty or all-space text, so structured_diff takes None for a new file's before text and a gone file's after text, never "". edit_store.py calls os.rmdir with dir_fd, test_edit_store.py lints that, and server.edits_supported lists rmdir.
check: grep -n "needs_dir_fd =" dashboard/server.py
evidence: dashboard/json_edit.py, dashboard/server.py, dashboard/edit_store.py, tests/test_edit_store.py
fp: 6a0028bed3fb
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-08
uses: 2

# testing-edit

### E-5b16 Write core: one writer, lock exceptions, Python 3.9 flags
fact: edit_store.py alone writes settings; test_edit_security lints write calls and exempts only reference_page.py's one open. api_edit's save recomputes inside the store's locked commit, so _StaleSignal and _Answer must not subclass StoreError or OSError, or _commit_locked wraps them as WriteFailed. A preview or save reports every row that moved, agent rows included. On /usr/bin/python3 3.9.6, O_NOFOLLOW|O_DIRECTORY on a symlink raises ENOTDIR and O_NOFOLLOW on a leaf raises ELOOP.
check: grep -n "class _StaleSignal\|class _Answer" dashboard/api_edit.py
evidence: dashboard/api_edit.py, dashboard/edit_store.py, tests/test_edit_security.py
fp: 7f1e2cc90f5b
as_of: 0766733 2026-10-31
author: verifier
created: 2026-10-31
last_used: 2026-10-31
uses: 0

### E-e2f0 Edit page: token first, a write drops all project data
fact: api.js caches usage and settings for the whole page load. take() in edit_session.js runs first at boot and in a hashchange listener registered before the router's. After a write, onWrite runs refreshAll in app.js: every project's data goes and generation moves, so an answer in flight drops itself. A new write route must use that path, or pages keep the old value. refreshAll waits on settings only, never on /api/usage.
check: grep -n "generation\|onWrite" dashboard/static/js/app.js
evidence: dashboard/static/js/app.js, dashboard/static/js/api.js, dashboard/static/js/edit_session.js
fp: 1ad7ec72cc3b
as_of: 0766733 2026-10-31
author: fast-worker
created: 2026-10-31
last_used: 2026-10-31
uses: 0

### E-83df Effort edge cases: unknown model, max, dotted paths
fact: With no known model, _computed_becomes returns None, so a cap lowers nothing and an in_effect effort row can overstate the level. max is invalid as effortLevel in every settings file: Claude Code skips it, so a file edit can't reach it. max stays valid for maxEffortLevel, where it means no cap. A modelSettings entry's path is dot-joined and model ids hold dots, so never split it.
check: ls tests/fixtures/resolution/effort-max-in-settings-invalid; grep -n 'path="modelSettings' dashboard/resolve.py
evidence: dashboard/resolve.py, dashboard/rules.json, dashboard/experiments/2026-10-29-effort-invalid-values.json
fp: 7a170c0ef754
as_of: 0766733 2026-10-31
author: deep-reasoner
created: 2026-10-31
last_used: 2026-10-31
uses: 0

### E-2fea Edit tests: fixture, real managed folder, half-closed sockets
fact: build_fixture in test_edit_e2e.py is the minimal --allow-edits fixture; its env drops CLAUDE_CODE_EFFORT_LEVEL. Display paths are relative to the fixture, and backups land in <fixture>/config/routing-dashboard/backups/<id>/. A refused save can leave empty store folders. server.live_context uses the REAL managed folder, so tests dataclasses.replace(ctx, managed_dir=<temp>, root=<temp>). A raw POST that promises unsent bytes needs half_close, or the server waits out its 15 s timeout.
check: grep -n "managed_dir=self.managed" tests/test_api_edit.py
evidence: tests/test_edit_e2e.py, tests/test_api_edit.py, tests/test_edit_server.py, dashboard/server.py
fp: 659196cbb9b4
as_of: 0766733 2026-10-31
author: fast-worker
created: 2026-10-31
last_used: 2026-10-31
uses: 0

### E-8d1b Static and node check traps
fact: A new app.css block headed ' * Title' fails test_one_section_per_page_with_shared_first, so a sub-block uses a one-line comment. Object.assign( on anything but an object literal in dashboard/static/js fails test_no_file_gets_around_the_link_helpers. fakedom createPage() swaps globalThis.document, so patch document after the page exists. edit_session_checks.mjs shows how to reach app.js's ctx from a copy. To prove a node check bites, mutate a scratch tar copy of the repo, not the tree.
check: grep -n "Object.s.*assign\|shared_first" tests/test_static_shell.py
evidence: tests/test_static_shell.py, tests/js/fakedom.mjs, tests/js/edit_session_checks.mjs
fp: 0c99383bebaf
as_of: 0766733 2026-10-31
author: fast-worker
created: 2026-10-31
last_used: 2026-10-31
uses: 0

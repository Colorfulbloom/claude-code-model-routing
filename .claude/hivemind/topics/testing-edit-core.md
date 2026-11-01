# testing-edit-core

### C-0a1c Edit rows: absent markers, created files deleted by hand
fact: A row with before_sha256 "absent" must name a .absent marker, and a half pair reads backup_damaged, because that path ends in a delete. edit_store._file_hash returns "absent" for a missing file and None only for a refused one, and _trim relies on that. A created file deleted by hand trims its create row: rows() hides it, restore raises UnknownEdit (not ChangedSinceSave), the undo route answers 404 unknown_edit, and the next save drops the row and prunes its marker. The store can't tell that from a create that crashed after the ledger write.
check: /usr/bin/python3 -m unittest discover -s tests -p test_edit_store.py -k deleted_by_hand
evidence: dashboard/edit_store.py, tests/test_edit_store.py
fp: 257f88949d00
as_of: c5bce3a 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### C-65f8 Remove: a gone line's id names an add
fact: _target_id hashes layer and key path, so once a line goes its id names an add, and a remove checks entry is not None twice. At the route, a line already gone answers 400 not_editable, not 409 stale. Inside plan, under the lock, a line gone since the route's read raises _StaleSignal with no preview.
check: grep -n "fresh.entry is None" dashboard/api_edit.py
evidence: dashboard/api_edit.py
fp: 743a997b4765
as_of: c5bce3a 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### C-df72 Edit-route tests: wont_apply rows, API-only worlds
fact: The route refuses a preview or save for a row that is not pickable, so a test that needs a wont_apply payload calls inner_preview(world, target, value) in test_api_edit.py. The user file's top-level effortLevel is not read with Sonnet or Opus set, so those rows are wont_apply and edit-route tests use the modelSettings add. A browser-free check of a world uses build_fixture, ts.start and EditApi get and post. A remove body has "action":"remove" and no "value" key. An insert diff shows the previous last line as deleted, because it gains a comma.
check: grep -n "def inner_preview" tests/test_api_edit.py; grep -n "class EditApi" tests/test_edit_e2e.py
evidence: tests/test_api_edit.py, tests/test_edit_e2e.py, dashboard/static/js/edit_session.js
fp: ff66d91a3760
as_of: c5bce3a 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### C-3cbd Real-git tests: wrapper git, partial clone
fact: ignore_state builds its own env, so real-git tests use a wrapper git script in a throwaway bin dir that sets GIT_CONFIG_NOSYSTEM and execs the real git by absolute path. To prove a lazy-fetch safeguard, clone --filter=blob:none --no-checkout from a file:// bare repo with uploadpack.allowFilter and allowAnySHA1InWant true, then read-tree HEAD and update-index --skip-worktree .gitignore. A raw check-ignore then fires core.sshCommand, and with --no-lazy-fetch it doesn't.
check: /usr/bin/python3 -m unittest discover -s tests -p test_git_check.py
evidence: tests/test_git_check.py, dashboard/git_check.py
fp: e60d478c4804
as_of: c5bce3a 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### C-06bf Repo copies for probes: .claude, throwaway HOME
fact: A probe copy of the repo excludes .claude, or rsync carries the owner's settings.local.json into it. A shell that exports a throwaway HOME also makes git status show that file as untracked, because the global ignore lives under the real HOME. Run git without the export.
check: git check-ignore -v .claude/settings.local.json
evidence: .gitignore
fp: 2e3aab966fe0
as_of: c5bce3a 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 0

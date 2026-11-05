# testing-edit-core

### C-0a1c Edit rows: absent markers, created files deleted by hand
fact: A row with before_sha256 "absent" must name a .absent marker, and a half pair reads backup_damaged, because that path ends in a delete. edit_store._file_hash returns "absent" for a missing file and None only for a refused one, and _trim relies on that. A created file deleted by hand trims its create row: rows() hides it, restore raises UnknownEdit (not ChangedSinceSave), the undo route answers 404 unknown_edit, and the next save drops the row and prunes its marker. A replace row whose backup equals the file trims the same way, so forced undo and restore of either raise UnknownEdit, never no_change. The store can't tell that from a create that crashed after the ledger write.
check: /usr/bin/python3 -m unittest discover -s tests -p test_edit_store.py -k deleted_by_hand
evidence: dashboard/edit_store.py, tests/test_edit_store.py
fp: c91d60092b57
as_of: 7da3051 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 2

### C-65f8 Remove: a gone line's id names an add
fact: _target_id hashes layer and key path, so once a line goes its id names an add, and a remove checks entry is not None twice. At the route, a line already gone answers 400 not_editable, not 409 stale. Inside plan, under the lock, a line gone since the route's read raises _StaleSignal with no preview.
check: grep -n "fresh.entry is None" dashboard/api_edit.py
evidence: dashboard/api_edit.py
fp: c67b1e71cf8e
as_of: 6206393 2026-11-02
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### C-df72 Edit-route tests: wont_apply rows, API-only worlds
fact: The route refuses a preview or save for a row that is not pickable, so a test that needs a wont_apply payload calls inner_preview(world, target, value) in test_api_edit.py. The user file's top-level effortLevel is not read with Sonnet or Opus set, so those rows are wont_apply and edit-route tests use the modelSettings add. A browser-free check of a world uses build_fixture, ts.start and EditApi get and post. A remove body has "action":"remove" and no "value" key. An insert diff shows the previous last line as deleted, because it gains a comma.
check: grep -n "def inner_preview" tests/test_api_edit.py; grep -n "class EditApi" tests/test_edit_e2e.py
evidence: tests/test_api_edit.py, tests/test_edit_e2e.py, dashboard/static/js/edit_session.js
fp: 099acc63933b
as_of: 6206393 2026-11-02
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 3

### C-06bf Repo copies for probes: .claude, throwaway HOME
fact: A probe copy of the repo excludes /.claude (anchored), or rsync carries the owner's settings.local.json into it; a bare .claude also drops tests/fixtures/demo/projects/*/.claude, and the demo shows those projects as missing_folder. A shell that exports a throwaway HOME also makes git status show that file as untracked, because the global ignore lives under the real HOME. Run git without the export. To probe edit_card_checks.mjs, insert checks before the MR_ONLY runner line in the copy and run test_edit_card_js.py there, because it builds MR_PAYLOADS.
check: git check-ignore -v .claude/settings.local.json
evidence: .gitignore, tests/test_edit_card_js.py
fp: 7a42fe8261ef
as_of: abaaff3 2026-11-04
author: verifier
created: 2026-11-01
last_used: 2026-11-02
uses: 6
promote: approved

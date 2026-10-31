### F-f629 Phase 2 slice 1: settings write core and Change effort screens (#79 to #90, PR #93)
status: shipped
kind: code
dates: 2026-10-31 .. 2026-10-31
refs:
  commit: 0766733e3dc81e24519701f9755b2f523c06be1e (branch feature/phase-2-write-core, merged into development)
  url: https://github.com/Colorfulbloom/claude-code-model-routing/issues/21
summary: With --allow-edits, the main session's effort trail gets a Change effort card with a preview, a diff, a save and an undo. A default launch stays read-only and a POST to an edit route gets a 405. The slice edits one existing effort value and adds no line and no file. Full suite 2285 tests, 38 skipped. The owner ran all MR_E2E checks, 39 tests, OK in real Chrome, and passed the #90 check byte for byte with cmp.
decisions:
- json_edit.py splices one value's bytes and leaves every other byte alone.
- edit_store.py is the only module that writes settings. It backs up first, saves atomically and keeps the newest 20 rows per file.
- collect.py takes an overlay of file bytes, so a preview runs the real resolver.
- Each edit needs the key from the printed link. edit_session.js takes it out of the address and sends it only in the X-Dashboard-Token header of a POST.
- edit_ref.js builds the same match key as api_edit.py, and a shared fixture keeps the two from drifting.
- After a write every project's cached data goes, and the page waits on settings and never on usage, so a usage warm-up can't hold the card on Saving.
- Undo works only on the newest save to a file, and only while the file still matches that save.
- A level that needs a cap change stops and points to the cap, because this screen can't change one.
- Verification added ledger_damaged and config_dir_missing in place of a plain write_failed. Backups older than a moved-aside ledger stay until someone deletes them by hand.
rejected:
- A second copy of the precedence rules for previews. The overlay runs the real resolver.
- Inserting a key, creating a file, removing a key and widening the editable keys in this slice. All of those moved to #92.
- Editing env values and agent files. Neither is editable in slice 1.
files: CLAUDE.md, README.md, dashboard/api_edit.py, dashboard/api_settings.py, dashboard/api_usage.py, dashboard/collect.py, dashboard/edit_store.py, dashboard/json_edit.py, dashboard/server.py, dashboard/static/app.css, dashboard/static/js/api.js, dashboard/static/js/app.js, dashboard/static/js/edit_card.js, dashboard/static/js/edit_ref.js, dashboard/static/js/edit_session.js, dashboard/static/js/pages/settings.js, dashboard/static/js/pages/trail.js, dashboard/static/strings.json, tests/fixtures/edit_ref_table.json, tests/js/edit_card_checks.mjs, tests/js/edit_ref_checks.mjs, tests/js/edit_session_checks.mjs, tests/js/fakedom.mjs, tests/test_api_edit.py, tests/test_collect_overlay.py, tests/test_e2e_checks.py, tests/test_edit_card_js.py, tests/test_edit_e2e.py, tests/test_edit_security.py, tests/test_edit_server.py, tests/test_edit_session_js.py, tests/test_edit_store.py, tests/test_json_edit.py, tests/test_server.py, tests/test_static_strings.py
gotchas:
- How /effort writes settings.json is unverified, so a write landing just before the rename can be lost. This risk is accepted for slice 1.
- Targets load only on the main session's effort trail and on Settings in the ready state, because each call runs the resolver many times.
facts: E-5b16, E-e2f0, E-83df, E-2fea, E-8d1b, T-7629
follow-ups:
- #92 holds everything after slice 1 and the Last session decision, which needs the owner.
- #91 is separate, and epic #21 stays open.

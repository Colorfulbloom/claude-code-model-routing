### F-b6cb Stage 3: add, create and remove lines on the Settings page (#106 to #112, PR #125)
status: shipped
kind: code
dates: 2026-11-01 .. 2026-11-01
refs:
  commit: c5bce3af96ae252b575026f77cebaea6669e3313 (branch feature/settings-add-create-remove, merged into development)
summary: Settings can add a line, create a file and remove a line, each with a review and an Undo. Undo restores the file byte for byte, or removes a created file and an empty .claude it made. Full suite on c5bce3a: 2602 tests, 39 skipped, about 270 seconds. PR #125 reports the 5 test_edit_e2e.py tests passing with MR_E2E=1. Part of #92.
decisions:
- A level press preselects a new local file, and a local file git doesn't ignore shows a warning.
- ignore_state runs git check-ignore with --no-lazy-fetch, core.fsmonitor=false and GIT_NO_LAZY_FETCH=1, outside the write lock. This closes the later ticket S-d4f6 waited for.
- The server refuses a preview or save for a row that can't be picked, and a save that would pass the 1 MiB cap.
- The repo lock still blocks all writes in a subfolder, worktree or submodule, and undo stays open.
- Accepted limit: a program writing in the instant before Undo deletes a file loses those bytes.
- Accepted limit: a created file deleted by hand leaves the history, because the store can't tell it from a crashed create.
- edit_store.py uses os.rmdir with dir_fd, and server.edits_supported lists rmdir.
- Consolidation added topic testing-edit-core (prefix C), because six topics sat near the 4 KB cap.
rejected:
- Proposal that isNotSaved ignores S.frame. Line 142 of edit_flow.js checks S.frame now, so the fact was stale at the merge.
- Proposal that a CDP fetch stub with eval needs Page.setBypassCSP. script-src 'self' holds, but the remedy needs a browser to check and the proposal had no check.
files: dashboard/api_edit.py, dashboard/edit_store.py, dashboard/git_check.py, dashboard/json_edit.py, dashboard/server.py, dashboard/static/app.css, dashboard/static/js/app.js, dashboard/static/js/edit_card.js, dashboard/static/js/edit_flow.js, dashboard/static/js/edit_foot.js, dashboard/static/js/edit_pick.js, dashboard/static/js/edit_review.js, dashboard/static/js/edit_session.js, dashboard/static/strings.json, tests/js/edit_card_checks.mjs, tests/js/edit_session_checks.mjs, tests/test_api_edit.py, tests/test_edit_card_js.py, tests/test_edit_e2e.py, tests/test_edit_security.py, tests/test_edit_server.py, tests/test_edit_store.py, tests/test_git_check.py, tests/test_json_edit.py
gotchas:
- The proposed check `-k lazy` ran 0 tests, because the test is named a_missing_gitignore_blob_in_a_partial_clone. C-3cbd checks the whole test_git_check.py.
- A proposal said a vanished line always answers 400 not_editable. That holds at the route, but inside plan a line gone since the route's read raises _StaleSignal, a 409 stale. C-65f8 records both.
- The verifier's and lead's counts of 2592 were stale. A git archive of c5bce3a counts 2602, and the tree with the uncommitted tests counts 2609.
facts: C-0a1c, C-65f8, C-df72, C-3cbd, C-06bf, E-6ccf, S-d4f6, T-7629, P-2fdd, P-c029
follow-ups:
- T-7629 in .claude/rules/project-facts.md still says 2364 tests until the owner approves the 2602 update.
- Uncommitted edits to tests/test_edit_e2e.py and tests/js/edit_card_checks.mjs bring the suite to 2609 tests and 46 skipped once they land.

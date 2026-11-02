### F-4db4 Settings E2E cap cases wait on the project row
status: shipped
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: 62063930618a4d19f552bc9aa5a56ab089ca802f (branch feature/settings-wider-key-table, merged into development)
summary: Three Chrome cap cases timed out in wait_review because a cap pick above the shared cap has no preselect (pick_file rail, no diff); tests now wait for Pick a file, press the project row, then the review.
decisions:
- Fixed the tests, not the code. The lowest cap applies and changes are judged by what runs after the edit, so the local create is wont_apply and preselect stays null (owner rule: preselect is the local file or null).
- Added EditSettingsApi.test_first_picks_preselect_what_the_browser_cases_expect, a no-browser test that pins the preselect each browser case relies on.
- Left commitWindow (edit_flow.js:389-391) alone. Its early returns mirror the box's disabled rule (edit_card.js heldOff plus controlsOff), so a bad number can't reach them.
rejected:
- Preselecting the project row for the cap: it breaks the owner rule that nothing moves to a shared file on its own.
- Blaming the late cap_first fix (api_edit.py:1008): it touches effortLevel rows only, and the effort cell still shows Start with the cap.
files: tests/test_edit_e2e_settings.py
gotchas:
- A browser case that waits for a diff right after a pick only works where the level preselects a row. Check the level row's preselect in the targets answer first.
follow-ups:
- Owner reruns MR_E2E=1 on test_edit_e2e_settings.py to confirm. A headless run with the skip marks stripped passed 6 of 6.
- T-7629 suite count is stale on this branch: 2982 tests, 58 skipped.

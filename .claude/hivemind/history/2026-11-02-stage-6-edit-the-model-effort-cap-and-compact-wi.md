### F-b10c Stage 6: edit the model, effort cap and compact window on the Settings page (#118, #119, #120, #121, #122, PR #132)
status: shipped
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: 62063930618a4d19f552bc9aa5a56ab089ca802f (branch feature/settings-wider-key-table, merged into development)
summary: Besides effortLevel, the Settings page now edits model, maxEffortLevel and autoCompactWindow. One SETTINGS table in api_edit.py lists the four, and the server refuses any setting outside it. Full suite: 2982 tests, 58 skipped (56 MR_E2E), about 265 seconds. PR #132 reports 14 of 14 in test_edit_e2e_settings.py passing with MR_E2E=1 and 8 judge Chrome checks passing. Part of #92. The lead left no history entry, so the consolidation records it; F-4db4 covers the E2E cap-case fix on the same branch.
decisions:
- One table, SETTINGS in api_edit.py, names the four editable keys. A request names a setting and the server checks it against the table, so nothing else can be written. A request without one is for effort.
- When one cap below a level is all that stands in the way, _via_cap offers the level through a change to that cap. With more than one cap below, cap_first keeps the picker on and the cap goes first, limited to levels where every cap below can change.
- max is accepted as a cap value, because max sets no cap.
- A cap in the user's own files that holds a level back stops the page with Start with the cap. A warning replaces the old lowered save.
- The user's own availableModels blocks a model instead of warning, and the save answers 422 model_blocked.
- Auto for the compact window always writes a per-model line, so it needs a model the dashboard knows.
- The page judges a cap, model or compact window change by what runs after the edit.
- Setting keys moved into edit_setting.js, and the strings that change with the setting into edit_words.js.
rejected:
- The old lowered save when a cap holds a level back. A warning and Start with the cap replace it.
- Preselecting the project row for a cap pick above the shared level. Nothing moves to a shared file on its own, so the rail asks for a file first (see F-4db4).
files: dashboard/api_edit.py, dashboard/static/app.css, dashboard/static/js/api.js, dashboard/static/js/app.js, dashboard/static/js/edit_backup.js, dashboard/static/js/edit_card.js, dashboard/static/js/edit_flow.js, dashboard/static/js/edit_foot.js, dashboard/static/js/edit_pick.js, dashboard/static/js/edit_review.js, dashboard/static/js/edit_session.js, dashboard/static/js/edit_setting.js, dashboard/static/js/edit_ui.js, dashboard/static/js/edit_words.js, dashboard/static/js/pages/settings.js, dashboard/static/js/pages/where.js, dashboard/static/strings.json, tests/js/edit_card_checks.mjs, tests/js/edit_session_checks.mjs, tests/js/settings_checks.mjs, tests/test_api_edit.py, tests/test_api_edit_settings.py, tests/test_edit_card_js.py, tests/test_edit_e2e_settings.py, tests/test_edit_server.py
gotchas:
- A cap pick above the shared level preselects no file, because only the project row applies. A browser case must wait for Pick a file and press the project row before the review.
- The verifier did not see the last fix, which limits cap_first to levels where every cap below can change. The full suite ran after it.
facts: T-7629, P-153a
follow-ups:
- The new pickers and the cap panel are unchecked at a real 1440 and 375 window.
- The owner hand steps in #120 and #122 are being reworded.

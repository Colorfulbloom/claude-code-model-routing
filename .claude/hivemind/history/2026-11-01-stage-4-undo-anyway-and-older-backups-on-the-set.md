### F-d2eb Stage 4: Undo anyway and Older backups on the Settings page (#113, #114, PR #128)
status: shipped
kind: code
dates: 2026-11-01 .. 2026-11-01
refs:
  commit: 7da3051ff1f68cdfe954d4faca6b174bd46469c2 (branch feature/settings-undo-anyway, merged into development)
summary: Settings can undo a save after the file has changed and restore any older backup. Undo anyway sits at the rail foot, Older backups lists the earlier copies, and each shows a preview that writes nothing. Full suite: 2750 tests, 52 skipped, about 255 seconds. PR #128 reports the 18 test_edit_e2e.py tests passing with MR_E2E=1. Part of #92. This work had no lead, so the consolidation records it.
decisions:
- Undo stays at one level and a restore has no Undo, so Older backups is the way back.
- Undo anyway skips only the hash check. Each write takes its own backup, and the server refuses a file that changed after its preview.
- A backup that is damaged or not valid JSON is never written. /api/edit/backup-preview and /api/edit/restore exist only with --allow-edits.
- Undo anyway and restore stay open under the repo lock, as Undo does.
- A press within 500 ms of a preview drawing is ignored, so a double click can't confirm a preview nobody saw.
- Accepted limit: when the file isn't valid JSON the preview shows no diff, and the contents can only be copied back by hand from that backup.
- Accepted limit: a hand-made POST to /api/edit/restore can still restore the newest row, because the edit key already reaches those bytes through a forced Undo.
- Consolidation added topics dashboard-page (prefix K) and testing-edit-undo (prefix U), because seven topics sat near the 4 KB cap with about 3 KB of new facts. The guard.ms fact the brief filed under testing-edit went to testing-edit-undo for that reason.
rejected:
- A server check against restoring the newest row. Ledgers are per file, so it would also refuse rows the list needs.
- Proposal to record that a dropped stash shows in git fsck. It is general git knowledge, not a fact of this project.
files: README.md, dashboard/api_edit.py, dashboard/edit_store.py, dashboard/json_edit.py, dashboard/server.py, dashboard/static/app.css, dashboard/static/js/api.js, dashboard/static/js/app.js, dashboard/static/js/edit_backup.js, dashboard/static/js/edit_card.js, dashboard/static/js/edit_flow.js, dashboard/static/js/edit_foot.js, dashboard/static/js/edit_pick.js, dashboard/static/js/edit_review.js, dashboard/static/js/edit_session.js, dashboard/static/js/pages/settings.js, dashboard/static/strings.json, tests/js/edit_card_checks.mjs, tests/js/edit_session_checks.mjs, tests/test_api_edit.py, tests/test_edit_card_js.py, tests/test_edit_e2e.py, tests/test_edit_security.py, tests/test_edit_server.py, tests/test_edit_store.py, tests/test_json_edit.py, tests/test_static_shell.py
gotchas:
- The agents' counts of 2748 and 2749 predate the last test changes. A static discovery of 7da3051 counts 2750, and the 52 skips are 50 MR_E2E, 1 MR_DOCS_LIVE and 1 MR_SUBAGENT_DOCS.
- S-fe14 and P-153a were stale after the merge. Store.restore now takes force, and the card source lists gained edit_backup. Both are updated.
- A backup-name proposal missed the half pair: a marker on a row with a real before hash reads backup_damaged, not backup_pruned. U-436d records it.
facts: U-0aa1, U-7c6a, U-3f27, U-436d, K-486e, K-6860, K-9709, K-9e3f, K-819f, T-7629, S-fe14, P-153a, P-db96, C-0a1c, C-06bf, E-6ccf
follow-ups:
- PR #128 left keyboard scroll of the rail in Safari unchecked.
- PR #128 says the verifier checked the feature before the last two small fix batches, so it hasn't seen those two.

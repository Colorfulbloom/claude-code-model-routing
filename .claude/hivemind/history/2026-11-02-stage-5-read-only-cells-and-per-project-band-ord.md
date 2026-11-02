### F-17fe Stage 5: read-only cells and per-project band order on the Settings page (#115, #116, #117, #105, PR #130)
status: shipped
kind: code
dates: 2026-11-01 .. 2026-11-02
refs:
  commit: 02a92069e9974703b5e82c6fa89180c386b6c8a6 (merge of PR #130, branch feature/settings-read-only-cells, into development; feature commit 5bc775d)
summary: The Settings band gains Extended thinking, Fallback models and Allowed models as read-only cells, so it shows 8. 15 rules and 27 fixtures back them, and the rules reference covers them. The band order is set per project by mouse drag or the Arrange list and stored in the browser. Full suite: 2866 tests, 52 skipped, about 260 seconds. PR #130 reports 53 tests in the test_*_e2e.py files passing with MR_E2E=1. Part of #92. The lead left no history entry, so the consolidation records it.
decisions:
- availableModels uses a new combine form, managed_or_merge. A managed list wins whole, and otherwise the lists merge, because the settings docs say "lists merge instead of overriding".
- Extended thinking reads Not known when an allowlist may replace the session model, so availableModels runs before alwaysThinkingEnabled.
- A fallback chain drops models the allowlist refuses, then keeps three, following "at most three distinct allowed models" in settings-reference.
- MAX_THINKING_TOKENS stops counting as a secret name, because the resolver needs its value. A value with a secret prefix still hides.
- Band order lives in browser storage per project, so no settings file changes. Touch and pen don't drag; Arrange covers keyboard and touch.
- ed_undo_fail_config_dir_t no longer gives restart advice that doesn't work.
- Consolidation added topics dashboard-resolver (prefix R) and testing-node (prefix N), because dashboard, dashboard-settings, dead-ends, testing and testing-pages all sat at the 4 KB cap. The narrow-width and scripted-drag browser fact merged into K-486e, the Where it's set row fact went to dashboard-page, and the macOS sed and timeout fact merged into D-c684.
rejected:
- Dragging a row from the More list into the band. It isn't in #105, and Arrange reaches every position.
- Worker duplicates of the lead's 13 facts. Each merged into the lead's record, keeping worker detail such as ENOENT for a missing real(...) payload and the whole-tree scratch copy (P-db96).
- Two unparsed lines, one on Where it's set rows and one on macOS timeout and sed. Both are covered by accepted records.
files: dashboard/collect.py, dashboard/resolve.py, dashboard/rules.json, dashboard/rules_schema.py, dashboard/static/app.css, dashboard/static/js/band_order.js, dashboard/static/js/icons.js, dashboard/static/js/pages/band.js, dashboard/static/js/pages/band_arrange.js, dashboard/static/js/pages/band_drag.js, dashboard/static/js/pages/read_frame.js, dashboard/static/js/pages/settings.js, dashboard/static/js/pages/where.js, dashboard/static/js/router.js, dashboard/static/strings.json, docs/rules-reference.md, tests/e2e_checks/rules.json, tests/js/band_reorder_checks.mjs, tests/js/edit_card_checks.mjs, tests/js/edit_session_checks.mjs, tests/js/fakedom.mjs, tests/js/settings_checks.mjs, tests/test_api_edit.py, tests/test_api_settings.py, tests/test_collect.py, tests/test_resolve.py, tests/test_rules_schema.py, tests/test_settings_js.py, tests/test_static_shell.py, plus 95 files under tests/fixtures/resolution/
gotchas:
- A static discovery of 02a9206 counts 2866 tests. The 52 skips are 50 MR_E2E, 1 MR_DOCS_LIVE and 1 MR_SUBAGENT_DOCS (a runtime skipTest). The PR's 53 e2e tests include tests in those files that MR_E2E doesn't gate.
- S-2dda went stale with this merge. Only permissions.defaultMode still lacks a resolver row.
- Chrome ignored resize_window, so the judge checked 1440 and 375 by emulated widths. K-486e records the method.
facts: R-4e38, R-f2df, R-ea92, R-8829, R-06c2, N-9919, N-5baa, N-5dc5, N-2a80, K-7dc3, K-486e, S-2dda, T-7629, D-c684, P-db96
follow-ups:
- The three cells and the drag are unchecked at a real 1440 and 375 window.
- The judge and the verifier haven't seen the final fix batch.
- Known limits from PR #130: the More starts here line follows the saved order, lower Arrange rows can sit under the docked foot in a short window during an edit, and a wholly invalid managed availableModels reads Unknown.

### F-a219 Stage 1: Settings rebuilt as a flat page with a stat band (#95 to #103, PR #123)
status: shipped
kind: code
dates: 2026-10-31 .. 2026-11-01
refs:
  commit: 0a1241f871d76189e129f99db35a723a8eec87e3 (branch feature/settings-stat-band, merged into development)
summary: Settings is a flat page. A stat band picks the setting, one file list is the picker, and the rail explains the value and turns into the review. Effort is the only editable setting. Full suite on 0a1241f, run November 1: 2364 tests, 39 skipped, 37 of them MR_E2E. PR #123 reports test_edit_e2e.py passing with MR_E2E=1.
decisions:
- No level answer names a shared file by default.
- A project in a repo subfolder, worktree or submodule locks all writes, user file included, and undo stays open.
- Levels over the cap are disabled.
- repo_place in git_check.py walks with lstat alone, so it reads no repo file and starts no process.
- _runs_as in api_edit.py alone lowers a level the resolver left uncapped.
- A late save answer after a project switch lands on the right project.
rejected:
- A git call in git_check.py did not ship in this PR. The module leaves it to a later ticket, and S-d4f6 records what that call must set.
files: dashboard/api_edit.py, dashboard/git_check.py, dashboard/static/app.css, dashboard/static/js/app.js, dashboard/static/js/band_order.js, dashboard/static/js/edit_card.js, dashboard/static/js/edit_flow.js, dashboard/static/js/edit_foot.js, dashboard/static/js/edit_pick.js, dashboard/static/js/edit_review.js, dashboard/static/js/edit_ui.js, dashboard/static/js/pages/band.js, dashboard/static/js/pages/read_frame.js, dashboard/static/js/pages/settings.js, dashboard/static/js/pages/trail.js, dashboard/static/js/pages/where.js, dashboard/static/js/router.js, dashboard/static/js/shell.js, dashboard/static/strings.json, tests/e2e_checks/settings.json, tests/e2e_checks/trail.json, tests/js/checks.mjs, tests/js/edit_card_checks.mjs, tests/js/edit_session_checks.mjs, tests/js/fakedom.mjs, tests/js/pages.mjs, tests/js/settings_checks.mjs, tests/test_api_edit.py, tests/test_e2e_checks.py, tests/test_edit_card_js.py, tests/test_edit_e2e.py, tests/test_edit_server.py, tests/test_git_check.py, tests/test_pages_e2e.py, tests/test_settings_e2e.py, tests/test_static_shell.py, tests/test_static_strings.py
gotchas:
- A proposal's check pointed at core.fsmonitor in git_check.py, but no commit on a local or fetched branch holds that text.
- The cap gap in a run's proposal was already closed in _runs_as, so the fact records the fixed state.
- Moving a fact between topics needs a new id, because check ties the id prefix to the topic. E-8d1b became P-db96 and E-a599 became S-3c1a.
facts: S-fe14, S-d4f6, S-47b6, S-519d, S-2dda, S-9770, S-3c1a, P-db96, P-153a, P-2fdd, P-d516, P-71ad, P-c029, E-6ccf, T-7629
follow-ups:
- T-7629 in .claude/rules/project-facts.md still says 2285 tests until the update is approved.
- Tickets #95 to #103 close after the owner's checks, as PR #123 says.
- S-d4f6 applies when the later git call lands in git_check.py.

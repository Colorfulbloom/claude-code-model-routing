# testing-edit

### E-8d1b Static and node check traps
fact: A new app.css block headed ' * Title' fails test_one_section_per_page_with_shared_first, so a sub-block uses a one-line comment. Object.assign( on anything but an object literal in dashboard/static/js fails test_no_file_gets_around_the_link_helpers. fakedom createPage() swaps globalThis.document, so patch document after the page exists. edit_session_checks.mjs shows how to reach app.js's ctx from a copy. To prove a node check bites, mutate a scratch tar copy of the repo, not the tree.
check: grep -n "Object.s.*assign\|shared_first" tests/test_static_shell.py
evidence: tests/test_static_shell.py, tests/js/fakedom.mjs, tests/js/edit_session_checks.mjs
fp: b5295d512535
as_of: 0a1241f 2026-11-01
author: fast-worker
created: 2026-10-31
last_used: 2026-11-01
uses: 7
superseded_by: P-db96
retired: 2026-11-01 superseded

### E-a599 Edit test worlds: repo place, target ids
fact: World in test_api_edit.py patches git_check.repo_place to no_repo, so a repo-lock test replaces world.place. Real-process tests stay no_repo only because they build under helpers._tmp_base; an MR_TEST_TMP inside a git repo changes that. _target_id hashes layer and key path only, so one id names that layer in every project, and a save compares base hashes.
check: grep -n "def _target_id" dashboard/api_edit.py; grep -n "world.place" tests/test_api_edit.py
evidence: dashboard/api_edit.py, tests/test_api_edit.py, tests/helpers.py
fp: e2b321068120
as_of: 0a1241f 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 0
superseded_by: S-3c1a
retired: 2026-11-01 superseded

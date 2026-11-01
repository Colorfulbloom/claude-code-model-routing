# dashboard-settings

### S-fe14 Undo anyway needs edit_store.py
fact: An Undo anyway path needs edit_store.py, because Store.restore raises ChangedSinceSave itself, after the check callback. The newest-row and undo-row rules live in api_edit.undo's check callback.
check: grep -n "raise ChangedSinceSave\|def check" dashboard/edit_store.py dashboard/api_edit.py
evidence: dashboard/edit_store.py, dashboard/api_edit.py
fp: 5505a63930f9
as_of: c5bce3a 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### S-d4f6 A child git must stop fsmonitor and lazy fetch
fact: git_check.ignore_state starts git with -c core.fsmonitor=false, --no-lazy-fetch and GIT_NO_LAZY_FETCH=1. On git 2.54, check-ignore ran core.fsmonitor from a repo's config or include.path, and ran core.sshCommand through a lazy fetch for a missing .gitignore blob in a partial clone.
check: grep -n "no-lazy-fetch" dashboard/git_check.py
evidence: dashboard/git_check.py, tests/test_git_check.py
fp: 87b70513655e
as_of: c5bce3a 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 3

### S-47b6 Query values: parseRoute keeps four, take keeps the rest
fact: parseRoute in router.js rebuilds query from project, range, theme and setting only, so a new query value needs parseRoute as well as queryString. take() in edit_session.js strips edit= and keeps the rest, so #/settings?edit=KEY&project=<name> opens a project with editing on.
check: grep -n "search.get" dashboard/static/js/router.js
evidence: dashboard/static/js/router.js, dashboard/static/js/edit_session.js
fp: fd742862cb3c
as_of: c5bce3a 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### S-519d Fixture mode reads shell_env from session.json
fact: fixture_context takes shell_env from the fixture's session.json alone, so a CLAUDE_CODE_EFFORT_LEVEL in the server's environment does nothing. A shell-locked state needs shell_env in session.json.
check: grep -n 'session.get("shell_env")' dashboard/server.py
evidence: dashboard/server.py
fp: 4f0066e410cc
as_of: c5bce3a 2026-11-01
author: designer
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### S-2dda Three settings have no resolver rows
fact: rules.json and resolve.py have no rows for alwaysThinkingEnabled, permissions.defaultMode or fallbackModel, checked case-insensitively, so a Settings cell for one needs resolver work first.
check: grep -n -i "alwaysThinkingEnabled\|fallbackModel\|defaultMode" dashboard/rules.json dashboard/resolve.py
evidence: dashboard/resolve.py, dashboard/rules.json
fp: 0d287eb331eb
as_of: 0a1241f 2026-11-01
author: designer
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### S-9770 modelSettings effort lines: own model only, no becomes
fact: The resolver adds a modelSettings.<name>.effortLevel line only for the row's own model, so none for another model or with no model set. That line never gets a becomes from a cap, because rule effort-lowered-by-cap has key effortLevel only. api_edit._runs_as lowers it, and it is the only place that does.
check: grep -n '"rule_id": "effort-lowered-by-cap"' dashboard/rules.json
evidence: dashboard/rules.json, dashboard/resolve.py, dashboard/api_edit.py
fp: c76718e4995f
as_of: c5bce3a 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 1

### S-3c1a Edit test worlds: repo place, target ids
fact: World in test_api_edit.py patches git_check.repo_place to no_repo, so a repo-lock test replaces world.place. Real-process tests stay no_repo only because they build under helpers._tmp_base; an MR_TEST_TMP inside a git repo changes that. _target_id hashes layer and key path only, so one id names that layer in every project, and a save compares base hashes.
check: grep -n "def _target_id" dashboard/api_edit.py; grep -n "world.place" tests/test_api_edit.py
evidence: dashboard/api_edit.py, tests/test_api_edit.py, tests/helpers.py
fp: 5d6b403fc85f
as_of: c5bce3a 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 1

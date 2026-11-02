# dashboard-settings

### S-fe14 Undo anyway: force skips only the hash check
fact: Undo anyway calls Store.restore with force=True, and force skips only the hash check. api_edit._undo_rule (newest row, not an undo or restore row) still runs as the check callback, and a damaged or pruned backup still refuses.
check: grep -n "force=True" dashboard/api_edit.py; grep -n "if not force" dashboard/edit_store.py
evidence: dashboard/edit_store.py, dashboard/api_edit.py
fp: 3e0088b84f42
as_of: 7da3051 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 3

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
fp: 71099ab5e001
as_of: 7da3051 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 0

### S-519d Fixture mode reads shell_env from session.json
fact: fixture_context takes shell_env from the fixture's session.json alone, so a CLAUDE_CODE_EFFORT_LEVEL in the server's environment does nothing. A shell-locked state needs shell_env in session.json.
check: grep -n 'session.get("shell_env")' dashboard/server.py
evidence: dashboard/server.py
fp: dffaaa3fd398
as_of: 7da3051 2026-11-01
author: designer
created: 2026-11-01
last_used: 2026-11-02
uses: 2

### S-2dda permissions.defaultMode has no resolver row
fact: rules.json and resolve.py have no row for permissions.defaultMode, checked case-insensitively, so a Settings cell for it needs resolver work first. alwaysThinkingEnabled, fallbackModel and availableModels got rows in 5bc775d.
check: grep -n -i "defaultMode" dashboard/rules.json dashboard/resolve.py
evidence: dashboard/resolve.py, dashboard/rules.json
fp: 91ac63ec40e3
as_of: 02a9206 2026-11-02
author: designer
created: 2026-11-01
last_used: 2026-11-02
uses: 2

### S-9770 modelSettings effort lines: own model only, no becomes
fact: The resolver adds a modelSettings.<name>.effortLevel line only for the row's own model, so none for another model or with no model set. That line never gets a becomes from a cap, because rule effort-lowered-by-cap has key effortLevel only. api_edit._runs_as lowers it, and it is the only place that does.
check: grep -n '"rule_id": "effort-lowered-by-cap"' dashboard/rules.json
evidence: dashboard/rules.json, dashboard/resolve.py, dashboard/api_edit.py
fp: fb390bc554a7
as_of: 7da3051 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 1

### S-3c1a Edit test worlds: repo place, target ids
fact: World in test_api_edit.py patches git_check.repo_place to no_repo, so a repo-lock test replaces world.place. Real-process tests stay no_repo only because they build under helpers._tmp_base; an MR_TEST_TMP inside a git repo changes that. _target_id hashes layer and key path only, so one id names that layer in every project, and a save compares base hashes.
check: grep -n "def _target_id" dashboard/api_edit.py; grep -n "world.place" tests/test_api_edit.py
evidence: dashboard/api_edit.py, tests/test_api_edit.py, tests/helpers.py
fp: d635fbda74d7
as_of: 7da3051 2026-11-01
author: verifier
created: 2026-11-01
last_used: 2026-11-01
uses: 1

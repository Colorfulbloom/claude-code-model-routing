# dashboard-resolver

### R-4e38 wrong_type candidates answer only to wrong_type rules
fact: set_cases marks a value of the wrong type for alwaysThinkingEnabled, fallbackModel or availableModels with case wrong_type, and such a candidate is judged only by conditions with when: wrong_type. Every other rule skips it.
check: grep -n 'wrong_type' dashboard/resolve.py
evidence: dashboard/resolve.py
fp: e1efc1f13697
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### R-f2df merged rows keep non-first entries in effect
fact: A managed_or_merge row (availableModels) keeps every non-managed entry in effect, with merged, the list that runs, only on the first entry. A Lowered fallbackModel entry also carries merged, the kept chain. A consumer that assumes non-first entries lost must skip these rows.
check: grep -n 'merged' dashboard/resolve.py
evidence: dashboard/resolve.py, tests/test_api_settings.py
fp: cf6e10006a70
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### R-ea92 Allowlist runs first: thinking row and fallback chain
fact: _main_rows runs availableModels before alwaysThinkingEnabled, because the thinking row's model is None when the allowlist may replace the session model (a blocked model setting, or an alias swapped for a permitted version). That check uses the catalog id with model_permitted, since an alias passes by substitution. A fallback chain drops models the allowlist refuses, then keeps three (CHAIN_LIMIT), as settings-reference says "at most three distinct allowed models".
check: /usr/bin/python3 -m unittest discover -s tests -p test_resolve.py -k thinking
evidence: dashboard/resolve.py, dashboard/rules.json, tests/fixtures/resolution/thinking-model-blocked-by-allowlist
fp: 7cf50f746f4f
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 2

### R-8829 MAX_THINKING_TOKENS is never a secret name
fact: collect.NOT_SECRET_NAMES exempts MAX_THINKING_TOKENS from secret-name masking, so is_secret_name is false for it everywhere, api_edit and json_edit included. A value with an sk- or Bearer prefix still hides.
check: grep -n NOT_SECRET_NAMES dashboard/collect.py
evidence: dashboard/collect.py, tests/test_collect.py
fp: 3d6f1fdcb632
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### R-06c2 A new rule count breaks test_api_rules until two files follow
fact: Adding or removing a rule in rules.json breaks test_api_rules until the All, Tested, Documented and Assumed texts in tests/e2e_checks/rules.json change and docs/rules-reference.md is rebuilt with /usr/bin/python3 dashboard/reference_page.py.
check: /usr/bin/python3 -m unittest discover -s tests -p test_api_rules.py
evidence: tests/e2e_checks/rules.json, tests/test_api_rules.py, dashboard/reference_page.py
fp: 255b4ac29c79
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 6
promote: approved

### R-3ecc Agent rule ids start with agent- or subagent-
fact: pin-view.js isAgentRule picks the agent sentences by a rule_id starting "agent-", so agent-scope rule ids start with agent- or subagent- and no other scope uses agent-.
check: grep -n isAgentRule dashboard/static/js/pin-view.js
evidence: dashboard/static/js/pin-view.js, dashboard/rules.json
fp: 56e198f73bac
as_of: a452d5d 2026-11-03
author: verifier
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### R-c047 Fixture expected.json pairs entries one to one
fact: resolve.compare pairs a named (key, scope, agent) row's entries one to one, so expected.json lists every entry of such a row. Fields it leaves out go unchecked, so a missing key such as model needs a unit test.
check: grep -n "def compare" -A12 dashboard/resolve.py
evidence: dashboard/resolve.py, tests/test_resolve.py
fp: 58b05f5b61dd
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-11-03
last_used: 2026-11-03
uses: 0

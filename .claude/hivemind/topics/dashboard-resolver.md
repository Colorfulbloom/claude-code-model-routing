# dashboard-resolver

### R-4e38 wrong_type candidates answer only to wrong_type rules
fact: set_cases gives a wrong-type value for alwaysThinkingEnabled, fallbackModel or availableModels case wrong_type, and only conditions with when: wrong_type judge it.
check: grep -n 'wrong_type' dashboard/resolve.py
evidence: dashboard/resolve.py
fp: e1efc1f13697
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### R-f2df merged rows keep non-first entries in effect
fact: A managed_or_merge row (availableModels) keeps every non-managed entry in effect, with merged (the list that runs) only on the first. A Lowered fallbackModel entry's merged is the kept chain. Non-first entries are not lost.
check: grep -n 'merged' dashboard/resolve.py
evidence: dashboard/resolve.py, tests/test_api_settings.py
fp: cf6e10006a70
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### R-ea92 Allowlist runs first: thinking row and fallback chain
fact: _main_rows runs availableModels before alwaysThinkingEnabled, because the thinking row's model is None when the allowlist may replace the session model (model_permitted on the catalog id: an alias passes by substitution). A fallback chain drops refused models, then keeps three (CHAIN_LIMIT).
check: /usr/bin/python3 -m unittest discover -s tests -p test_resolve.py -k thinking
evidence: dashboard/resolve.py, dashboard/rules.json, tests/fixtures/resolution/thinking-model-blocked-by-allowlist
fp: 7cf50f746f4f
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 2

### R-8829 MAX_THINKING_TOKENS is never a secret name
fact: collect.NOT_SECRET_NAMES exempts MAX_THINKING_TOKENS from secret-name masking everywhere (api_edit, json_edit too); an sk- or Bearer value still hides.
check: grep -n NOT_SECRET_NAMES dashboard/collect.py
evidence: dashboard/collect.py, tests/test_collect.py
fp: 3d6f1fdcb632
as_of: 02a9206 2026-11-02
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### R-06c2 A new rule count breaks test_api_rules until two files follow
fact: Adding or removing a rule in rules.json breaks test_api_rules until the two files project-facts R-06c2 names follow.
check: /usr/bin/python3 -m unittest discover -s tests -p test_api_rules.py
evidence: tests/e2e_checks/rules.json, tests/test_api_rules.py, dashboard/reference_page.py
fp: 255b4ac29c79
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-11-02
last_used: 2026-11-08
uses: 9
promote: approved

### R-3ecc Agent rule ids start with agent- or subagent-
fact: pin-view.js isAgentRule finds agent sentences by a rule_id starting "agent-", so only agent-scope ids start with agent- or subagent-.
check: grep -n isAgentRule dashboard/static/js/pin-view.js
evidence: dashboard/static/js/pin-view.js, dashboard/rules.json
fp: 56e198f73bac
as_of: a452d5d 2026-11-03
author: verifier
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### R-c047 Fixture expected.json pairs entries one to one
fact: resolve.compare pairs a named (key, scope, agent) row's entries one to one, so expected.json lists every entry. A field it leaves out goes unchecked, so test a missing key in a unit test.
check: grep -n "def compare" -A12 dashboard/resolve.py
evidence: dashboard/resolve.py, tests/test_resolve.py
fp: 58b05f5b61dd
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-11-03
last_used: 2026-11-09
uses: 2

### R-7c9c Agent files resolve loads; no plugin layer
fact: An agent file loads only with a non-empty name and description, and no collector feeds a plugin layer; project-facts R-7c9c has the detail.
check: grep -n 'no_description\|f\["loadable"\]' dashboard/resolve.py; grep -c plugin dashboard/collect.py (expect 0)
evidence: dashboard/resolve.py, dashboard/collect.py
fp: e52c40f7d390
as_of: 7d8af23 2026-11-09
author: scout
created: 2026-11-09
last_used: 2026-11-09
uses: 0
promote: approved

# testing

### T-7629 Full suite runs 2602 tests in about 270 seconds
fact: discover -s tests runs 2602 tests in about 270 s on c5bce3a, 39 skipped: 37 need MR_E2E=1, owner only, 2 need MR_DOCS_LIVE=1 or MR_SUBAGENT_DOCS. Run it alone. A broken pty test can leave a hung process.
check: /usr/bin/python3 -c "import unittest,sys; sys.path.insert(0,'tests'); print(unittest.TestLoader().discover('tests').countTestCases())"
evidence: tests
fp: 62e64d26d461
as_of: c5bce3a 2026-11-01
author: deep-reasoner
created: 2026-10-20
last_used: 2026-11-01
uses: 22
promote: proposed

### T-5589 Subsets: discover -k; dotted names fail
fact: Dotted names (tests.test_x) fail with "No module named 'helpers'"; use discover -s tests -k <pattern> or -p test_x.py. discover comes first: -v before it is rejected.
check: /usr/bin/python3 -m unittest tests.test_parity 2>&1 | grep "No module named"
evidence: tests/helpers.py
fp: 99286733860d
as_of: c5bce3a 2026-11-01
author: deep-reasoner
created: 2026-10-20
last_used: 2026-11-01
uses: 79
promote: approved

### T-d689 Installer messages need a parity allowance
fact: A new installer message needs an allowance in apply_allowances (tests/helpers.py) and a HarnessSelfTests case: parity tests diff stdout with install_old.sh.
check: grep -n "def apply_allowances" tests/helpers.py
evidence: tests/helpers.py, tests/test_parity.py
fp: 961803e83ac4
as_of: 203ae0d 2026-10-30
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-29
uses: 1

### T-2160 A resumed round starts at a real brief
fact: promptId follows the parent's prompt. A brief is a user row with origin.kind coordinator, human, or peer from an agent the transcript did not launch.
check: grep -n "def is_brief" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py, tests/fixtures/rounds/README.md
fp: 3a06f4c51c50
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-29
uses: 3

### T-07ef Settings harness: no real API call
fact: dashboard/experiments/harness/ runs claude -p in a throwaway HOME against fakeapi.py on 127.0.0.1. "/effort status" and "/autocompact" send no request. Never run a batch as a check. Only text_reply true cases write normal assistant rows, so only they can back a claim about the top-level effort field. With no model set a case starts on claude-opus-5-5, where a user top-level effortLevel doesn't count and the request carries medium, so a case for another model sets it.
check: grep -n "PROMPT_ALLOWLIST = " dashboard/experiments/harness/runcase.py
evidence: dashboard/experiments/harness/README.md, dashboard/experiments/harness/runcase.py, dashboard/experiments/harness/results-step2-compact.jsonl
fp: b8cce11c735d
as_of: 0766733 2026-10-31
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-31
uses: 11
promote: approved

### T-6b2f Collector where maps have tuple keys
fact: collect.py where maps use tuple keys (modelSettings names hold dots); json.dumps needs jsonable() from tests/test_collect.py.
check: grep -n "def jsonable" tests/test_collect.py
evidence: dashboard/collect.py, tests/test_collect.py
fp: 75d9e963b7d4
as_of: 0766733 2026-10-31
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-31
uses: 4

### T-3ad1 tests/*.py: no home paths, no imported TestCase
fact: NoHomePathsInTestsTest bans home path prefixes in tests/*.py, so sample paths start at /work/. tests/fixtures/ is not scanned. Import a test module whole (import test_x as x): from test_x import TestClass makes discover run that class twice.
check: grep -n "NoHomePathsInTestsTest" tests/test_hivemind.py
evidence: tests/test_hivemind.py
fp: 751bc849be0e
as_of: 0766733 2026-10-31
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-31
uses: 7

### T-d32f Copied server tree needs install.py
fact: api_settings imports install.py at import, so tests/test_server.py copy_tree copies it.
check: grep -n "install.py" tests/test_server.py
evidence: dashboard/api_settings.py, tests/test_server.py
fp: e75c6d27bbb0
as_of: 0766733 2026-10-31
author: fast-worker
created: 2026-10-31
last_used: 2026-10-31
uses: 3

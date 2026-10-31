# testing

### T-7629 Full suite runs 1665 tests in about 204 seconds
fact: discover -s tests from the repo root runs 1665 tests in about 204 s on 3fd2d26, 18 skipped: 16 end-to-end tests need MR_E2E=1 and the owner runs them, 2 need MR_DOCS_LIVE=1 or MR_SUBAGENT_DOCS. Run it alone. A broken pty test can leave a hung process.
check: /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
evidence: tests
fp: ea54fe1acf6d
as_of: 3fd2d26 2026-10-30
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-30
uses: 18
promote: approved

### T-5589 Subsets run through discover -k; dotted names fail
fact: Dotted names (python3 -m unittest tests.test_x) fail with "No module named 'helpers'"; use discover -s tests -k <pattern> or -p test_x.py. discover comes first: -v before it is rejected.
check: /usr/bin/python3 -m unittest tests.test_parity 2>&1 | grep "No module named"
evidence: tests/helpers.py
fp: 99286733860d
as_of: ce1f71d 2026-10-30
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-30
uses: 66
promote: approved

### T-c826 MR_TEST_TMP is optional and created when missing
fact: tests/helpers.py _tmp_base creates MR_TEST_TMP if set and missing; unset means the system temp dir.
check: grep -n -A4 "def _tmp_base" tests/helpers.py
evidence: tests/helpers.py
fp: 99286733860d
as_of: ce1f71d 2026-10-30
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-30
uses: 41
promote: approved

### T-d689 New installer messages need a parity allowance
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
check: grep -n "def is_brief" -A20 hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py, tests/fixtures/rounds/README.md
fp: 3a06f4c51c50
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-29
uses: 3

### T-07ef The settings harness makes no real API call
fact: dashboard/experiments/harness/ runs claude -p in a throwaway HOME against fakeapi.py on 127.0.0.1. "/effort status" and "/autocompact" send no request. Never run a batch as a check. Only text_reply true cases write normal assistant rows, so only they can back a claim about the top-level effort field.
check: grep -n "PROMPT_ALLOWLIST = \|def check_frontmatter" dashboard/experiments/harness/runcase.py
evidence: dashboard/experiments/harness/README.md, dashboard/experiments/harness/runcase.py
fp: 81c2d5ef2810
as_of: 203ae0d 2026-10-30
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-30
uses: 9
promote: approved

### T-6b2f Collector where maps have tuple keys
fact: collect.py where maps use tuple keys (modelSettings names hold dots); json.dumps needs a converter, as jsonable() in tests/test_collect.py.
check: grep -n "def jsonable" tests/test_collect.py
evidence: dashboard/collect.py, tests/test_collect.py
fp: b27ebfc18420
as_of: 0e72fd4 2026-10-30
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-30
uses: 3

### T-3ad1 tests/*.py: no home paths, no imported TestCase
fact: NoHomePathsInTestsTest bans the home path prefixes in every tests/*.py file, so sample paths use a neutral root such as /work/. tests/fixtures/ is not scanned. Import a test module whole (import test_x as x): from test_x import TestClass makes discover run that class twice.
check: grep -n "NoHomePathsInTestsTest" tests/test_hivemind.py; grep -n "^import test_" tests/test_api_usage.py
evidence: tests/test_hivemind.py, tests/test_api_usage.py
fp: 2f556a57df43
as_of: ce1f71d 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 1

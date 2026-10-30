# testing

### T-7629 Full suite runs 1152 tests in about 165 seconds
fact: discover -s tests from the repo root runs 1152 tests (2 skipped, they need MR_DOCS_LIVE=1 or MR_SUBAGENT_DOCS) in about 165 s. Run it alone.
check: /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
evidence: tests
fp: 2597b9945850
as_of: 84354c6 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 10
measured: 1152 tests, 2 skipped, 163.9s @84354c6+wip 2026-10-29
promote: approved

### T-5589 Subsets run through discover -k; dotted names fail
fact: Dotted names (python3 -m unittest tests.test_x) fail with "No module named 'helpers'"; use discover -s tests -k <pattern> or -p test_x.py.
check: /usr/bin/python3 -m unittest tests.test_parity 2>&1 | grep "No module named"
evidence: tests/helpers.py
fp: 99286733860d
as_of: 84354c6 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 35
promote: approved

### T-c826 MR_TEST_TMP is optional and created when missing
fact: tests/helpers.py _tmp_base creates MR_TEST_TMP if set and missing; unset means the system temp dir.
check: grep -n -A4 "def _tmp_base" tests/helpers.py
evidence: tests/helpers.py
fp: 1a7f2c83b755
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 16
promote: approved

### T-baa7 Broken pty tests can leave stray processes
fact: test_picker.py and test_hivemind.py drive real ptys; a broken one can leave a hung unittest process (ps -eo pid,etime,command | grep "[u]nittest").
check: grep -n "import pty" tests/test_picker.py tests/test_hivemind.py
evidence: tests/test_picker.py, tests/test_hivemind.py
fp: 028bf5912fe9
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-21
uses: 3

### T-d689 New installer messages need a parity allowance
fact: A new installer message needs an allowance in apply_allowances (tests/helpers.py) and a HarnessSelfTests case, because parity tests diff stdout with install_old.sh.
check: grep -n "def apply_allowances" tests/helpers.py
evidence: tests/helpers.py, tests/test_parity.py
fp: 007d7af47e6f
as_of: 72a81f7 2026-10-29
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
fact: dashboard/experiments/harness/ runs claude -p in a throwaway HOME against fakeapi.py on 127.0.0.1. "/effort status" and "/autocompact" send no request. Never run a batch as a check.
check: grep -n "PROMPT_ALLOWLIST = \|def check_frontmatter" dashboard/experiments/harness/runcase.py
evidence: dashboard/experiments/harness/README.md, dashboard/experiments/harness/runcase.py
fp: 7440bb514860
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-29
uses: 2
promote: approved

### T-735d install.py imports agent_md.py from its own folder
fact: The installer's frontmatter helpers live in agent_md.py at the repo root; install.py puts its folder on sys.path, and snapshot_source copies the module.
check: grep -n "agent_md" install.py tests/helpers.py
evidence: install.py, tests/helpers.py
fp: 00b6816b8d22
as_of: 84354c6 2026-10-29
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-29
uses: 0

### T-6b2f Collector where maps have tuple keys
fact: collect.py where maps use tuple keys (modelSettings names hold dots); json.dumps needs a converter, as jsonable() in tests/test_collect.py.
check: grep -n "def jsonable" tests/test_collect.py
evidence: dashboard/collect.py, tests/test_collect.py
fp: b27ebfc18420
as_of: 84354c6 2026-10-29
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-29
uses: 0

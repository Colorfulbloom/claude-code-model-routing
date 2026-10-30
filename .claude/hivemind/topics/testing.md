# testing

### T-7629 Full suite runs 986 tests in about 140 seconds
fact: From the repo root, /usr/bin/python3 -m unittest discover -s tests runs 986 tests (2 skipped) in about 140 s; the count grows, measured has the latest. Run it alone, not beside a harness batch. The skips need MR_DOCS_LIVE=1 or MR_SUBAGENT_DOCS.
check: /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
evidence: tests
fp: 8faa286cfebd
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 10
measured: 986 tests, 2 skipped, 138.5s @72a81f7 2026-10-29
promote: approved

### T-5589 Subsets run through discover -k; dotted names fail
fact: Dotted names (python3 -m unittest tests.test_x) fail with "No module named 'helpers'"; discover -s tests -k <pattern> or -p test_x.py runs a subset.
check: /usr/bin/python3 -m unittest tests.test_parity 2>&1 | grep "No module named"
evidence: tests/helpers.py
fp: 1a7f2c83b755
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 27
promote: approved

### T-c826 MR_TEST_TMP is optional and created when missing
fact: tests/helpers.py _tmp_base creates MR_TEST_TMP if it is set and missing; unset means the system temp dir.
check: grep -n -A4 "def _tmp_base" tests/helpers.py
evidence: tests/helpers.py
fp: 1a7f2c83b755
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 14
promote: approved

### T-baa7 Broken pty tests can leave stray unittest processes
fact: test_picker.py and test_hivemind.py drive real ptys; a broken pty test can leave a hung unittest process, and ps -eo pid,etime,command | grep "[u]nittest" lists any strays.
check: grep -n "import pty" tests/test_picker.py tests/test_hivemind.py
evidence: tests/test_picker.py, tests/test_hivemind.py
fp: 028bf5912fe9
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-21
uses: 3

### T-d689 New installer messages need a parity allowance
fact: Parity tests compare install.py stdout with tests/fixtures/install_old.sh line by line; a new installer message needs an allowance in apply_allowances (tests/helpers.py) plus a HarnessSelfTests case in tests/test_parity.py.
check: grep -n "def apply_allowances" tests/helpers.py
evidence: tests/helpers.py, tests/test_parity.py
fp: 007d7af47e6f
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-29
uses: 1

### T-2160 A resumed round starts at a real brief, not a new promptId
fact: promptId follows the parent's prompt. A brief is a user row with origin.kind coordinator or human, or peer from an agent the transcript did not launch; nudges, task notifications and hand-backs are not. SubagentStop fires at each stop before the wake row lands.
check: grep -n "def is_brief" -A20 hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py, tests/fixtures/rounds/README.md
fp: 3a06f4c51c50
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-29
uses: 3

### T-07ef The settings harness measures precedence with no real API call
fact: dashboard/experiments/harness/ runs claude -p in a throwaway HOME against fakeapi.py on 127.0.0.1 and refuses real keys; its README has the case rules. "/effort status" and "/autocompact" send no request, so their output lands in result. autoCompactWindow never shows in the request, and a 5m cache ttl looks like the default. Never run a batch as a check.
check: grep -n "PROMPT_ALLOWLIST = \|def check_frontmatter" dashboard/experiments/harness/runcase.py
evidence: dashboard/experiments/harness/README.md, dashboard/experiments/harness/runcase.py
fp: 7440bb514860
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-29
uses: 0
promote: approved

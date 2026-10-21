# testing

### T-7629 Full suite runs 358 tests in about a minute
fact: From the repo root, /usr/bin/python3 -m unittest discover -s tests runs 358 tests in about a minute (51 to 77 s seen, varies with load).
check: /usr/bin/python3 -m unittest discover -s tests
evidence: tests
fp: c5f6560794cc
as_of: 2c33011 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-21
uses: 3
measured: 358 tests, 63.8s @2c33011 plus the uncommitted Phase 2 build and fixes 2026-10-21
promote: approved

### T-5589 Subsets run through discover -k; dotted names fail
fact: python3 -m unittest tests.test_x fails with "No module named 'helpers'" because the tests import helpers through the path that discover sets up; discover -s tests -k <pattern> or -p test_x.py runs a subset without that error.
check: /usr/bin/python3 -m unittest tests.test_parity 2>&1 | grep "No module named"
evidence: tests/helpers.py
fp: 1a7f2c83b755
as_of: 2c33011 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-21
uses: 7
promote: approved

### T-c826 MR_TEST_TMP is optional and created when missing
fact: tests/helpers.py _tmp_base creates MR_TEST_TMP if it is set and missing; unset means the system temp dir.
check: grep -n -A4 "def _tmp_base" tests/helpers.py
evidence: tests/helpers.py
fp: 1a7f2c83b755
as_of: 2c33011 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-21
uses: 2
promote: approved

### T-baa7 Broken pty tests can leave stray unittest processes
fact: test_picker.py and test_hivemind.py drive real ptys; a broken pty test can leave a hung unittest process, and ps -eo pid,etime,command | grep "[u]nittest" lists any strays.
check: grep -n "import pty" tests/test_picker.py tests/test_hivemind.py
evidence: tests/test_picker.py, tests/test_hivemind.py
fp: 7cf8581c7a3c
as_of: 2c33011 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-21
uses: 3

### T-6bd7 SubagentHandback appeared only in auto mode on Claude Code 2.1.305
fact: Version-dependent observation on Claude Code 2.1.305: headless claude -p subagents got SubagentHandback only with --permission-mode auto; under acceptEdits they ended with plain text and SubagentStop carried last_assistant_message. The check prints the installed version and shows that capture reads both endings; it does not test the mode behaviour, which needs a live run on each new version.
check: claude --version; grep -n -E "last_assistant_message|transcript_tool_input" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: 584e36e394bb
as_of: 2c33011 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-20
uses: 0
promote: no

### T-d689 New installer messages need a parity allowance
fact: Parity tests compare install.py stdout with tests/fixtures/install_old.sh line by line; a new installer message needs an allowance in apply_allowances (tests/helpers.py) plus a HarnessSelfTests case in tests/test_parity.py.
check: grep -n "def apply_allowances" tests/helpers.py
evidence: tests/helpers.py, tests/test_parity.py
fp: 007d7af47e6f
as_of: 2c33011 2026-10-21
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-21
uses: 0

### T-91ac SessionStart source values on 2.1.306
fact: Headless claude -p on 2.1.306 sends SessionStart source startup (new session), resume (--resume and --continue), compact (/compact) and clear (/clear, new session_id); status shows Recent work only for startup, clear and compact.
check: grep -n "RECENT_SOURCES =" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: 584e36e394bb
as_of: 2c33011 2026-10-21
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-21
uses: 1

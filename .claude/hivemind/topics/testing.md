# testing

### T-7629 Full suite runs 254 tests in about 51 s
fact: From the repo root, /usr/bin/python3 -m unittest discover -s tests runs 254 tests in about 51 s.
check: /usr/bin/python3 -m unittest discover -s tests
evidence: tests
fp: d25dc39e37f1
as_of: 6e0d514 2026-10-20
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-20
uses: 1
measured: 254 tests, 51s @6e0d514 plus the uncommitted HiveMind build 2026-10-20
promote: approved

### T-5589 Subsets run through discover -k; dotted names fail
fact: python3 -m unittest tests.test_x fails with "No module named 'helpers'" because the tests import helpers through the path that discover sets up; discover -s tests -k <pattern> or -p test_x.py runs a subset without that error.
check: /usr/bin/python3 -m unittest tests.test_parity 2>&1 | grep "No module named"
evidence: tests/helpers.py
fp: 2cc8cef7b312
as_of: 6e0d514 2026-10-20
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-20
uses: 4
promote: approved

### T-c826 MR_TEST_TMP is optional and created when missing
fact: tests/helpers.py _tmp_base creates MR_TEST_TMP if it is set and missing; unset means the system temp dir.
check: grep -n -A4 "def _tmp_base" tests/helpers.py
evidence: tests/helpers.py
fp: 2cc8cef7b312
as_of: 6e0d514 2026-10-20
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-20
uses: 1
promote: approved

### T-baa7 Broken pty tests can leave stray unittest processes
fact: test_picker.py and test_hivemind.py drive real ptys; a broken pty test can leave a hung unittest process, and ps -eo pid,etime,command | grep "[u]nittest" lists any strays.
check: grep -n "import pty" tests/test_picker.py tests/test_hivemind.py
evidence: tests/test_picker.py, tests/test_hivemind.py
fp: c95fa4d30766
as_of: 6e0d514 2026-10-20
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-20
uses: 2

### T-6bd7 SubagentHandback appeared only in auto mode on Claude Code 2.1.305
fact: Version-dependent observation on Claude Code 2.1.305: headless claude -p subagents got SubagentHandback only with --permission-mode auto; under acceptEdits they ended with plain text and SubagentStop carried last_assistant_message. The check prints the installed version and shows that capture reads both endings; it does not test the mode behaviour, which needs a live run on each new version.
check: claude --version; grep -n -E "last_assistant_message|transcript_tool_input" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: b0f99968f11e
as_of: 6e0d514 2026-10-20
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-20
uses: 0
promote: no

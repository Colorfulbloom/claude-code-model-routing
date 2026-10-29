# testing

### T-7629 Full suite runs 456 tests in about 110 seconds
fact: From the repo root, /usr/bin/python3 -m unittest discover -s tests runs 456 tests in about 110 s.
check: /usr/bin/python3 -m unittest discover -s tests
evidence: tests
fp: 20f37316bf48
as_of: 35db33d 2026-10-29
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 6
measured: 456 tests, 118.9s @35db33d+feature/routing-dashboard 2026-10-29
promote: approved

### T-5589 Subsets run through discover -k; dotted names fail
fact: Dotted names (python3 -m unittest tests.test_x) fail with "No module named 'helpers'"; discover -s tests -k <pattern> or -p test_x.py runs a subset.
check: /usr/bin/python3 -m unittest tests.test_parity 2>&1 | grep "No module named"
evidence: tests/helpers.py
fp: 1a7f2c83b755
as_of: 9c7985a 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 10
promote: approved

### T-c826 MR_TEST_TMP is optional and created when missing
fact: tests/helpers.py _tmp_base creates MR_TEST_TMP if it is set and missing; unset means the system temp dir.
check: grep -n -A4 "def _tmp_base" tests/helpers.py
evidence: tests/helpers.py
fp: 1a7f2c83b755
as_of: 9c7985a 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-29
uses: 5
promote: approved

### T-baa7 Broken pty tests can leave stray unittest processes
fact: test_picker.py and test_hivemind.py drive real ptys; a broken pty test can leave a hung unittest process, and ps -eo pid,etime,command | grep "[u]nittest" lists any strays.
check: grep -n "import pty" tests/test_picker.py tests/test_hivemind.py
evidence: tests/test_picker.py, tests/test_hivemind.py
fp: 05fcb8c98cfb
as_of: 9c7985a 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-21
uses: 3

### T-6bd7 SubagentHandback appeared only in auto mode on Claude Code 2.1.305
fact: On Claude Code 2.1.305, headless claude -p subagents got SubagentHandback only with --permission-mode auto; under acceptEdits they ended in plain text and SubagentStop carried last_assistant_message. The check shows capture reads both endings.
check: claude --version; grep -n -E "last_assistant_message|transcript_tool_input" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: b7b34e576946
as_of: 9c7985a 2026-10-21
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
fp: b7b34e576946
as_of: 9c7985a 2026-10-21
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-21
uses: 1

### T-2160 A resumed round starts at a real brief, not a new promptId
fact: promptId follows the parent's prompt. A brief is a user row with origin.kind coordinator or human, or peer from an agent the transcript did not launch; nudges (no origin), task-notification rows and workers' hand-backs are not. SubagentStop fires at each stop before the wake row lands; a plain-text stop's last row can land after capture reads.
check: grep -n "def is_brief" -A20 hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py, tests/fixtures/rounds/README.md
fp: 1ba85b303b01
as_of: deb3d7e 2026-10-22
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-29
uses: 3

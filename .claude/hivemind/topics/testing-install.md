# testing-install

### I-44e3 Installer messages need a parity allowance
fact: A new installer message needs an allowance in apply_allowances (tests/helpers.py) and a HarnessSelfTests case: parity tests diff stdout with install_old.sh.
check: grep -n "def apply_allowances" tests/helpers.py
evidence: tests/helpers.py, tests/test_parity.py
fp: 961803e83ac4
as_of: 203ae0d 2026-10-30
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-29
uses: 1

### I-cac7 A resumed round starts at a real brief
fact: promptId follows the parent's prompt. A brief is a user row with origin.kind coordinator, human, or peer from an agent the transcript did not launch.
check: grep -n "def is_brief" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py, tests/fixtures/rounds/README.md
fp: 3a06f4c51c50
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-29
uses: 3

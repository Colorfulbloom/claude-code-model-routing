# testing-install

### I-44e3 Installer messages need a parity allowance
fact: A new installer message needs an allowance in apply_allowances (tests/helpers.py) and a HarnessSelfTests case: parity tests diff stdout with install_old.sh.
check: grep -n "def apply_allowances" tests/helpers.py
evidence: tests/helpers.py, tests/test_parity.py
fp: 68bf9655738d
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-10-21
last_used: 2026-11-03
uses: 2

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

### I-3123 Picker tests follow ins.ALIASES order
fact: tests/test_picker.py indexes and walks ins.ALIASES (haiku, sonnet, claude-opus-5-5, fable), so renaming or reordering an alias breaks its defaults and cursor cases.
check: grep -n "ins.ALIASES" tests/test_picker.py
evidence: install.py, tests/test_picker.py
fp: 4438fdb8e738
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### I-b01b Same-second run files fold by capture_order
fact: Run files one agent captures in the same second are X.json and X-2.json, and X-2.json sorts first by name, so add_tally_samples folds runs by capture_order (time, then tally rows), never by file name.
check: grep -n "def capture_order" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py, tests/test_hivemind.py
fp: 76750e072f31
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### I-3e12 Apply tests need a prep snapshot first
fact: cmd_apply exits 1 "no prep snapshot" unless prep wrote inbox/prep-snapshot.json, so apply tests call ApplyTest.apply() or self.prep() first, and snap() comparisons skip inbox/consolidating.lock (LOCK_REL), whose holder line changes on every lock.
check: grep -n "LOCK_REL =\|def apply(self)" tests/test_hivemind.py
evidence: tests/test_hivemind.py, hooks/hivemind_lib.py
fp: a42f186dc8e2
as_of: a452d5d 2026-11-03
author: verifier
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### I-9984 APFS name checks are case-sensitive, open() is not
fact: On macOS APFS a name check against a tuple such as INBOX_SKIP is case-sensitive but open() and unlink() are not, so "INJECTED.json" reaches injected.json. Compare a name read from a file against exact os.listdir results (run_file_names) before acting on it.
check: grep -n "present = set(run_file_names" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: 3cbef149e46e
as_of: a452d5d 2026-11-03
author: verifier
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### I-14ae webbrowser.open falls through to the next browser
fact: webbrowser.open() tries each registered browser until one succeeds, so a failing BROWSER stub falls through to macOS open and a test opens real tabs. Use webbrowser.get().open(url), as the launcher does.
check: /usr/bin/python3 -I -c "import webbrowser,inspect;print(inspect.getsource(webbrowser.open))" | grep -n "for name in _tryorder"
evidence: plugins/routing-dashboard/bin/routing-dashboard, tests/test_plugin_launcher.py
fp: 9dbebbf88d66
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-11-03
last_used: 2026-11-03
uses: 0

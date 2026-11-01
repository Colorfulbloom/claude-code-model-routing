# dead-ends

### D-168e history commands without --store write the live store
fact: hivemind_lib.py history add, link, rollup and index find the store from the cwd project when --store is absent, so a smoke run from inside this repo writes .claude/hivemind/history/; pass --store <throwaway store>.
check: grep -n "def find_store" -A12 hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: 50d53980d8c5
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-30
uses: 2

### D-c684 Env-leak asserts fail unless they ignore macOS python3 shim vars
fact: The macOS /usr/bin/python3 shim adds CPATH, LIBRARY_PATH, SDKROOT, MANPATH and __CF_USER_TEXT_ENCODING to every child process, so an env-leak assertion on a Python fake ignores them (SYSTEM_ADDED in tests/test_harness_guard.py).
check: env -i PATH=/usr/bin /usr/bin/python3 -c 'import os;print(sorted(os.environ))'
evidence: tests/test_harness_guard.py
fp: 33743e0d54ce
as_of: 203ae0d 2026-10-30
author: fast-worker
created: 2026-10-29
last_used: 2026-10-29
uses: 1

### D-1534 Doc anchors and quotes need the rendered page and curl
fact: code.claude.com headings carry custom ids, so check anchors against the rendered HTML id="..." attributes, not .md heading slugs. Python urllib's default User-Agent gets 403; send a custom one as tests/test_doc_anchors.py does. WebFetch summarises long pages and that test checks anchors only, so confirm a new quote with curl -sL <url>.md | grep.
check: curl -sL https://code.claude.com/docs/en/sub-agents | grep -o 'id="supported-frontmatter-fields"'
evidence: tests/test_doc_anchors.py, dashboard/rules.json
fp: cca9f214c303
as_of: 0766733 2026-10-31
author: verifier
created: 2026-10-29
last_used: 2026-10-31
uses: 11
promote: approved

### D-6bed Patching os.stat alone misses pathlib on Python 3.9
fact: Python 3.9 pathlib keeps its own reference to os.stat, so patching os.stat misses Path.exists, Path.read_text and Path.iterdir; a home guard wraps the Path methods directly, as tests/test_resolve.py does.
check: /usr/bin/python3 -m unittest discover -s tests -p 'test_resolve.py' -k Guard
evidence: tests/test_resolve.py
fp: 49fd95a17782
as_of: 47fab08 2026-10-31
author: fast-worker
created: 2026-10-29
last_used: 2026-10-29
uses: 4

### D-b739 A global gitignore hides fixture settings.local.json files
fact: The owner's global git ignore lists **/.claude/settings.local.json, which would leave fixture local layers out of commits; line 5 of the repo .gitignore negates it for tests/fixtures/**. git check-ignore -v shows which rule wins.
check: git check-ignore -v --no-index tests/fixtures/resolution/effort-max-in-settings-invalid/project/.claude/settings.local.json
evidence: .gitignore
fp: 2e3aab966fe0
as_of: 203ae0d 2026-10-30
author: verifier
created: 2026-10-29
last_used: 2026-10-30
uses: 3
promote: approved

### D-2e12 Rows with one message.id can carry growing output_tokens
fact: Transcript rows that share a message.id can carry growing usage, so keeping the first row undercounts output. usage.py keeps the largest output_tokens. Tested on made-up fixtures only.
check: /usr/bin/python3 -m unittest discover -s tests -p 'test_usage.py' -k largest_output
evidence: dashboard/usage.py, tests/test_usage.py
fp: fbb580237bd6
as_of: ce1f71d 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-31
uses: 1

### D-3ca7 Worktree agents: git -C, computed command names, busy heredocs
fact: The worktree guard refuses what it cannot check first: git -C <dir>, a command named by a variable or a quoted path with a space, and a heredoc body mixing quotes, backticks and $( ). Plain heredocs, even after cd or into the scratchpad, variables as arguments, gh --jq pipes and for loops ran (October 30 probes). A new isolation worktree starts at origin/main, not development.
check: in a worktree-isolated agent run: git -C . log -1 --oneline
evidence: .gitignore
fp: 2e3aab966fe0
as_of: ce1f71d 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-30
uses: 7

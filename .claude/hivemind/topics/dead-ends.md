# dead-ends

### D-168e history commands without --store write the live store
fact: hivemind_lib.py history add, link, rollup and index find the store from the cwd project when --store is absent, so a smoke run from inside this repo writes .claude/hivemind/history/; pass --store <throwaway store>.
check: grep -n "def find_store" -A12 hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: 50d53980d8c5
as_of: 72a81f7 2026-10-29
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-21
uses: 1

### D-c684 Env-leak asserts fail unless they ignore macOS python3 shim vars
fact: The macOS /usr/bin/python3 shim adds CPATH, LIBRARY_PATH, SDKROOT, MANPATH and __CF_USER_TEXT_ENCODING to every child process, so an env-leak assertion on a Python fake ignores them (SYSTEM_ADDED in tests/test_harness_guard.py). A fake that walks the throwaway root uses os.path.realpath (TMPDIR is under the /var symlink) and errors="replace".
check: env -i PATH=/usr/bin /usr/bin/python3 -c 'import os;print(sorted(os.environ))'
evidence: tests/test_harness_guard.py
fp: 1a3d2399a51a
as_of: 72a81f7 2026-10-29
author: fast-worker
created: 2026-10-29
last_used: 2026-10-29
uses: 0

### D-1534 Doc anchors and quotes need the rendered page and curl
fact: code.claude.com headings carry custom ids (the sub-agents "Frontmatter reference" is #supported-frontmatter-fields), so check anchors against the rendered HTML id="..." attributes, not slugs of .md headings. Python urllib's default User-Agent gets 403; send a custom one as tests/test_doc_anchors.py does. WebFetch summarises long pages, so confirm exact quotes with curl -sL <url>.md | grep.
check: curl -sL https://code.claude.com/docs/en/sub-agents | grep -o 'id="supported-frontmatter-fields"'
evidence: tests/test_doc_anchors.py, dashboard/rules.json
fp: 78e8d95d4481
as_of: 72a81f7 2026-10-29
author: verifier
created: 2026-10-29
last_used: 2026-10-29
uses: 0
promote: approved

### D-6bed Patching os.stat alone misses pathlib on Python 3.9
fact: Python 3.9 pathlib keeps its own reference to os.stat, so patching os.stat misses Path.exists, Path.read_text and Path.iterdir; a home guard wraps the Path methods directly, as tests/test_resolve.py does.
check: /usr/bin/python3 -m unittest discover -s tests -p 'test_resolve.py' -k Guard
evidence: tests/test_resolve.py
fp: 1c69f502490f
as_of: 72a81f7 2026-10-29
author: fast-worker
created: 2026-10-29
last_used: 2026-10-29
uses: 0

### D-b739 A global gitignore hides fixture settings.local.json files
fact: The owner's global git ignore lists **/.claude/settings.local.json, which would leave fixture local layers out of commits; line 5 of the repo .gitignore negates it for tests/fixtures/**. git check-ignore -v shows which rule wins.
check: git check-ignore -v --no-index tests/fixtures/resolution/effort-max-in-settings-invalid/project/.claude/settings.local.json
evidence: .gitignore
fp: ebc9da0043e0
as_of: 72a81f7 2026-10-29
author: verifier
created: 2026-10-29
last_used: 2026-10-29
uses: 0
promote: approved

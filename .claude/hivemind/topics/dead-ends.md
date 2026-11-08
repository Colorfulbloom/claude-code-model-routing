# dead-ends

### D-168e history commands without --store write the live store
fact: hivemind_lib.py history add, link, rollup and index find the store from the cwd project when --store is absent, so a smoke run from inside this repo writes .claude/hivemind/history/; pass --store <throwaway store>.
check: grep -n "def find_store" -A12 hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: 2587fb68144c
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-10-21
last_used: 2026-11-04
uses: 9

### D-c684 macOS traps: python3 shim vars, sed \b, no timeout
fact: /usr/bin/python3 adds CPATH, LIBRARY_PATH, SDKROOT, MANPATH and __CF_USER_TEXT_ENCODING to every child, so env-leak asserts ignore them (SYSTEM_ADDED in tests/test_harness_guard.py). BSD sed has no \b (it changes nothing and exits 0), and there is no timeout command. Rewrite files with Python re.sub.
check: printf 'FIVE\n' | sed 's/\bFIVE\b/X/'
evidence: tests/test_harness_guard.py
fp: 33743e0d54ce
as_of: 6206393 2026-11-02
author: fast-worker
created: 2026-10-29
last_used: 2026-11-04
uses: 4
promote: approved

### D-1534 Doc anchors and quotes need the rendered page and curl
fact: code.claude.com headings carry custom ids, so check anchors against the rendered HTML id="..." attributes, not .md slugs. urllib needs a custom User-Agent, as tests/test_doc_anchors.py sends. WebFetch summarises, so confirm a new quote with curl -sL <url>.md | grep.
check: curl -sL https://code.claude.com/docs/en/sub-agents | grep -o 'id="supported-frontmatter-fields"'
evidence: tests/test_doc_anchors.py, dashboard/rules.json
fp: 85e8db8cfa8f
as_of: abaaff3 2026-11-04
author: verifier
created: 2026-10-29
last_used: 2026-11-06
uses: 31
promote: approved

### D-6bed Patching os.stat alone misses pathlib on Python 3.9
fact: Python 3.9 pathlib keeps its own reference to os.stat, so patching os.stat misses Path.exists, read_text and iterdir; a home guard wraps the Path methods, as tests/test_resolve.py does.
check: /usr/bin/python3 -m unittest discover -s tests -p 'test_resolve.py' -k Guard
evidence: tests/test_resolve.py
fp: 35abeb69ec5c
as_of: 6206393 2026-11-02
author: fast-worker
created: 2026-10-29
last_used: 2026-11-02
uses: 5

### D-b739 A global gitignore hides fixture settings.local.json files
fact: The owner's global git ignore lists **/.claude/settings.local.json, which would drop fixture local layers from commits; the repo .gitignore negates it for tests/fixtures/**. git check-ignore -v shows which rule wins.
check: git check-ignore -v --no-index tests/fixtures/resolution/effort-max-in-settings-invalid/project/.claude/settings.local.json
evidence: .gitignore
fp: 2e3aab966fe0
as_of: a452d5d 2026-11-03
author: verifier
created: 2026-10-29
last_used: 2026-11-02
uses: 7
promote: approved

### D-2e12 Rows with one message.id can carry growing output_tokens
fact: Transcript rows that share a message.id can carry growing usage, so the first row undercounts output. usage.py keeps the largest output_tokens. Tested on made-up fixtures only.
check: /usr/bin/python3 -m unittest discover -s tests -p 'test_usage.py' -k largest_output
evidence: dashboard/usage.py, tests/test_usage.py
fp: fbb580237bd6
as_of: ce1f71d 2026-10-30
author: deep-reasoner
created: 2026-10-30
last_used: 2026-10-31
uses: 1

### D-3ca7 Worktree agents: git -C, computed command names, busy heredocs
fact: The worktree guard refuses git -C <dir>, a command named by a variable or a quoted path with a space, any command that sets HOME, a script path built from $HOME or ${VAR:-x}, and a heredoc that mentions git. Heredocs, for loops and a pipe into diff failed in some runs, so use one plain command per call with literal paths and write scripts with Write; compare with a ref through git archive <ref> <path> | tar -x -C <scratch>. A new isolation worktree starts at origin/main, not development.
check: in a worktree-isolated agent run: git -C . log -1 --oneline
evidence: .gitignore
fp: 2e3aab966fe0
as_of: ff41524 2026-11-07
author: deep-reasoner
created: 2026-10-30
last_used: 2026-11-06
uses: 24
promote: approved

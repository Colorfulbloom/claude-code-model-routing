# dead-ends

### D-168e history commands without --store write the live store
fact: hivemind_lib.py history add, link, rollup and index find the store from the cwd project when --store is absent, so a smoke run from inside this repo writes .claude/hivemind/history/; pass --store <throwaway store>.
check: grep -n "def find_store" -A12 hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: 584e36e394bb
as_of: 2c33011 2026-10-21
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-21
uses: 1

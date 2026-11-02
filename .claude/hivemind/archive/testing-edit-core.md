# testing-edit-core

### C-3cbd Real-git tests: wrapper git, partial clone
fact: ignore_state builds its own env, so real-git tests use a wrapper git script in a throwaway bin dir that sets GIT_CONFIG_NOSYSTEM and execs the real git by absolute path. To prove a lazy-fetch safeguard, clone --filter=blob:none --no-checkout from a file:// bare repo with uploadpack.allowFilter and allowAnySHA1InWant true, then read-tree HEAD and update-index --skip-worktree .gitignore. A raw check-ignore then fires core.sshCommand, and with --no-lazy-fetch it doesn't.
check: /usr/bin/python3 -m unittest discover -s tests -p test_git_check.py
evidence: tests/test_git_check.py, dashboard/git_check.py
fp: e60d478c4804
as_of: c5bce3a 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-01
uses: 0
superseded_by: G-b77c
retired: 2026-11-02 superseded

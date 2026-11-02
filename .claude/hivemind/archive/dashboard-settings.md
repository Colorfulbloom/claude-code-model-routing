# dashboard-settings

### S-d4f6 A child git must stop fsmonitor and lazy fetch
fact: git_check.ignore_state starts git with -c core.fsmonitor=false, --no-lazy-fetch and GIT_NO_LAZY_FETCH=1. On git 2.54, check-ignore ran core.fsmonitor from a repo's config or include.path, and ran core.sshCommand through a lazy fetch for a missing .gitignore blob in a partial clone.
check: grep -n "no-lazy-fetch" dashboard/git_check.py
evidence: dashboard/git_check.py, tests/test_git_check.py
fp: 87b70513655e
as_of: c5bce3a 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-01
uses: 3
superseded_by: G-3a73
retired: 2026-11-02 superseded

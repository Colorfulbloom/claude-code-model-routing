# dashboard-git

### G-3a73 A child git must stop fsmonitor and lazy fetch
fact: git_check.ignore_state starts git with -c core.fsmonitor=false, --no-lazy-fetch and GIT_NO_LAZY_FETCH=1. On git 2.54, check-ignore ran core.fsmonitor from a repo's config or include.path, and ran core.sshCommand through a lazy fetch for a missing .gitignore blob in a partial clone.
check: grep -n "no-lazy-fetch" dashboard/git_check.py
evidence: dashboard/git_check.py, tests/test_git_check.py
fp: 87b70513655e
as_of: c5bce3a 2026-11-01
author: deep-reasoner
created: 2026-11-01
last_used: 2026-11-04
uses: 8

### G-b77c Real-git tests: wrapper git, partial clone
fact: ignore_state builds its own env, so real-git tests use a wrapper git script in a throwaway bin dir that sets GIT_CONFIG_NOSYSTEM and execs the real git by absolute path. To prove a lazy-fetch safeguard, clone --filter=blob:none --no-checkout from a file:// bare repo with uploadpack.allowFilter and allowAnySHA1InWant true, then read-tree HEAD and update-index --skip-worktree .gitignore. A raw check-ignore then fires core.sshCommand, and with --no-lazy-fetch it doesn't.
check: /usr/bin/python3 -m unittest discover -s tests -p test_git_check.py
evidence: tests/test_git_check.py, dashboard/git_check.py
fp: e60d478c4804
as_of: c5bce3a 2026-11-01
author: fast-worker
created: 2026-11-01
last_used: 2026-11-02
uses: 5

### G-c2d7 A bare repo named .git reads unknown
fact: git_check.repo_root reads the common dir's config (at most 64 KiB, _MAX_CONFIG) and treats core.bare true as a refusal, so a worktree of a bare repo in a folder named .git reads unknown and locks. A missing config is not bare, because hand-made test worktrees have none.
check: /usr/bin/python3 -m unittest discover -s tests -p test_git_check.py -k bare
evidence: dashboard/git_check.py, tests/test_git_check.py
fp: e9f9618b6092
as_of: 057353e 2026-11-02
author: fast-worker
created: 2026-11-02
last_used: 2026-11-02
uses: 0

### G-066f Build tests copy by the payload's own file list and close git
fact: Drift tests copy sources into a temp folder by the payload's relative file list, because git ls-files fails outside a repo and the build then walks folders. A test that commits in a copied tree sets GIT_CONFIG_NOSYSTEM=1, GIT_CONFIG_GLOBAL=/dev/null, HOME at the temp folder, and author and committer names and emails.
check: grep -n "GIT_CONFIG_NOSYSTEM\|def payload_files" tests/test_plugin_build.py
evidence: tests/test_plugin_build.py, tools/build_plugins.py
fp: 9732b37b403b
as_of: abaaff3 2026-11-04
author: fast-worker
created: 2026-11-03
last_used: 2026-11-04
uses: 2

### G-3e60 build_plugins.py: tracked files, two payloads, one guard
fact: tools/build_plugins.py builds from git ls-files, so an untracked new source is left out and --check still passes; stage it first. PLUGINS rows take "files" as a callable(repo). hooks/hivemind_lib.py ships in the routing-dashboard and hivemind payloads, so a change needs both plugin.json bumps; the guards run routing-dashboard first. A second payload change under a version BUILD.json already records is refused: restore BUILD.json from the base (development's after a rebase, then bump one patch) and build once.
check: grep -n 'ls-files\|plugin\["files"\](repo)\|def version_guard' tools/build_plugins.py
evidence: tools/build_plugins.py, tests/test_plugin_build.py
fp: fe436690746b
as_of: ff41524 2026-11-07
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-06
uses: 6
promote: approved

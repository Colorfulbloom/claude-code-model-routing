# testing

### T-7629 Full suite: 3575 tests, about 370 seconds
fact: discover -s tests runs 3575 tests in about 370 s, 88 skipped (development ff41524, November 7): MR_E2E=1 (owner only) gates all but the MR_DOCS_LIVE=1 and MR_SUBAGENT_DOCS (runtime skipTest) ones. Run it alone, and name its log per branch: background leads of one session share a scratchpad. A broken pty test can leave a hung process. A branch that adds tests counts higher.
check: HOME=$(mktemp -d) /usr/bin/python3 -c "import unittest,sys; sys.path.insert(0,'tests'); print(unittest.TestLoader().discover('tests').countTestCases())"
evidence: tests
fp: 8a10448c3210
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-10-20
last_used: 2026-11-08
uses: 51
promote: approved

### T-5589 Subsets: discover -k; dotted names fail
fact: Dotted names (tests.test_x) fail with "No module named 'helpers'"; use discover -s tests -k <pattern> or -p test_x.py. discover comes first: -v before it is rejected.
check: /usr/bin/python3 -m unittest tests.test_parity 2>&1 | grep "No module named"
evidence: tests/helpers.py
fp: 1122432f340e
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-10-20
last_used: 2026-11-09
uses: 146
promote: approved

### T-07ef Settings harness: no real API call
fact: dashboard/experiments/harness/ runs claude -p in a throwaway HOME against fakeapi.py on 127.0.0.1. "/effort status" and "/autocompact" send no request. Never run a batch as a check. Only text_reply true cases write normal assistant rows, so only they can back a claim about the top-level effort field. With no model set a case starts on claude-opus-5-5, where a user top-level effortLevel doesn't count and the request carries medium, so a case for another model sets it. The guard refuses --plugin-dir and plugin-loading settings keys, so plugin load checks can't run in it.
check: grep -n "PROMPT_ALLOWLIST = " dashboard/experiments/harness/runcase.py
evidence: dashboard/experiments/harness/README.md, dashboard/experiments/harness/runcase.py, dashboard/experiments/harness/results-step2-compact.jsonl
fp: 49f9f8fce33c
as_of: a452d5d 2026-11-03
author: deep-reasoner
created: 2026-10-29
last_used: 2026-11-08
uses: 21
promote: approved

### T-6b2f Collector where maps have tuple keys
fact: collect.py where maps use tuple keys (modelSettings names hold dots); json.dumps needs jsonable() from tests/test_collect.py.
check: grep -n "def jsonable" tests/test_collect.py
evidence: dashboard/collect.py, tests/test_collect.py
fp: 3d6f1fdcb632
as_of: 6206393 2026-11-02
author: deep-reasoner
created: 2026-10-29
last_used: 2026-11-02
uses: 6

### T-3ad1 tests/*.py: no home paths, no imported TestCase
fact: NoHomePathsInTestsTest bans home path prefixes in tests/*.py, so sample paths start at /work/. tests/fixtures/ is not scanned. Import a test module whole (import test_x as x): from test_x import TestClass makes discover run that class twice.
check: grep -n "NoHomePathsInTestsTest" tests/test_hivemind.py
evidence: tests/test_hivemind.py
fp: 75223c371bf9
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-10-30
last_used: 2026-11-09
uses: 44
promote: approved

### T-d32f Copied server tree needs install.py
fact: api_settings imports install.py at import, so tests/test_server.py copy_tree copies it.
check: grep -n "install.py" tests/test_server.py
evidence: dashboard/api_settings.py, tests/test_server.py
fp: 71950d0f007a
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-10-31
last_used: 2026-11-03
uses: 5

### T-a651 test_server pins the server's options and constructor
fact: tests/test_server.py pins build_parser's option dest set (options = {a.dest ...}) and Server.__init__'s parameters (self, ctx, port, write_routes), so a new server flag or parameter fails it until those asserts change.
check: grep -n "options = {a.dest\|parameters)," tests/test_server.py
evidence: tests/test_server.py, dashboard/server.py
fp: 69196d207b20
as_of: a452d5d 2026-11-03
author: scout
created: 2026-11-03
last_used: 2026-11-03
uses: 0

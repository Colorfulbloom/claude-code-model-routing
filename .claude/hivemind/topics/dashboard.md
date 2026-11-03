# dashboard

### W-7178 Browser-free JS checks run under node
fact: tests/test_shell_js.py runs tests/js/checks.mjs on fakedom.mjs. tests/test_pages_js.py runs the real app.js over pages.mjs and every route in tests/e2e_checks/. Both skip without node. Alone: node --experimental-default-type=module tests/js/checks.mjs, and --check syntax-checks a module. Modules hold state, so each check imports a fresh copy: app.js?run=N or pages/x.js?copy=N. h() sets value as a property, so read o.value.
check: /usr/bin/python3 -m unittest discover -s tests -p test_shell_js.py
evidence: tests/test_shell_js.py, tests/js/rules_checks.mjs, dashboard/static/js/h.js, tests/test_pages_js.py
fp: 33b0db260eba
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-10-30
last_used: 2026-11-02
uses: 13
promote: approved

### W-f6ed macOS traps in server tests: bytecode prefix, second bind
fact: /usr/bin/python3 3.9.6 sets sys.pycache_prefix under $HOME/Library/Caches, so a no-writes test that hashes source folders passes even with dont_write_bytecode False. Run the child with -X pycache_prefix=, as NoWrites does; -B would defeat it. A second bind to 0.0.0.0 fails even for a loopback-only socket, so check with lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN -Fn.
check: /usr/bin/python3 -X pycache_prefix= -c "import sys;print(sys.pycache_prefix)"
evidence: tests/test_server.py
fp: f1a0242fb4ac
as_of: 0766733 2026-10-31
author: fast-worker
created: 2026-10-30
last_used: 2026-11-03
uses: 4

### W-4654 Rules for one key share one combine; order picks rule_id
fact: All rules for one key and scope share one combine, or resolve.py raises "rules for X combine in different ways". A rule beside a lowest_value row needs lowest_value and a value_order. rule_id goes to the earliest equally specific voter in rules.json, so a values rule sits after the per-model rule.
check: /usr/bin/python3 dashboard/resolve.py | tail -1
evidence: dashboard/rules.json, dashboard/resolve.py
fp: 8cd77006292f
as_of: 6206393 2026-11-02
author: deep-reasoner
created: 2026-10-30
last_used: 2026-11-02
uses: 6

### W-4518 Settings: external links, Escape, implicit project
fact: Links to other sites go only through externalLink in h.js, https only. trail.js hears Escape in the capture phase to act before shell.js. A missing_folder project answers with empty entries unless it is implicit, which still resolves.
check: grep -n "not project.implicit" dashboard/api_settings.py
evidence: dashboard/static/js/h.js, dashboard/static/js/pages/trail.js, dashboard/api_settings.py
fp: 2db97570cc0d
as_of: 0a1241f 2026-11-01
author: deep-reasoner
created: 2026-10-31
last_used: 2026-11-01
uses: 4

### W-88a3 Reader.read_folder keeps other folders' cache
fact: transcripts.Reader.read_folder(folder, now) shares the per-file cache and _lock with read. A full read drops every cache path it did not see, so only read_folder leaves other folders' entries alone.
check: /usr/bin/python3 -m unittest discover -s tests -p test_api_live.py -k another_folders_cache
evidence: dashboard/transcripts.py, tests/test_api_live.py
fp: 856f37bf2b97
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-11-03
last_used: 2026-11-03
uses: 0

### W-734f A live-route test world without the demo set
fact: A /api/live test world needs only session.json (now, tz), config/routing-dashboard.json with absolute project paths, and transcripts under config/projects/<transcripts.sanitize(realpath(project))>/; server.fixture_context(root, None, None, RULES, FIELDS) then works.
check: /usr/bin/python3 -m unittest discover -s tests -p test_api_live.py
evidence: tests/test_api_live.py, dashboard/api_live.py
fp: 07c87256d217
as_of: a452d5d 2026-11-03
author: fast-worker
created: 2026-11-03
last_used: 2026-11-03
uses: 0

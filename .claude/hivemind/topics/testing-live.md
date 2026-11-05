# testing-live

### Q-0ec1 Live E2E: clocks, worlds and nav links by text
fact: tests/e2e_checks/live.json runs on the demo's default clock, where Live is empty, so chart checks go in test_live_e2e.py (LIVE_NOW, IDLE_NOW). tests/fixtures/live_flow/build_flow.py builds a dispatch world with a later "now" in session.json and transcripts under config/projects/<transcripts.sanitize(cwd)>. Live is the sidebar's first link (shell.js), so E2E tests find nav links by text, not index.
check: grep -n "LIVE_NOW\|IDLE_NOW" tests/test_live_e2e.py; grep -n 'session\["now"\]' tests/fixtures/live_flow/build_flow.py
evidence: tests/test_live_e2e.py, tests/e2e_checks/live.json, tests/fixtures/live_flow/build_flow.py, dashboard/static/js/shell.js
fp: e86d44846713
as_of: abaaff3 2026-11-04
author: fast-worker
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### Q-f176 Live flow captures: zero-width main, hidden unlinked note
fact: main [data-page=live] has zero width, so a CDP screenshot clipped to it fails with "Cannot take screenshot with 0 width"; clip to the nearest ancestor with a width, as test_live_flow_e2e.py does. p.lv-fl-unlinked is always in the DOM and hidden when every run is linked, so count it only when visible. At 720 px and under the canvas is a list in dispatch-tree order, not dispatch-number order.
check: grep -n "getBoundingClientRect().width" tests/test_live_flow_e2e.py; grep -n "dispatch-tree order" dashboard/static/js/pages/live_flow.js
evidence: tests/test_live_flow_e2e.py, dashboard/static/js/pages/live_flow.js
fp: fb459b8a4b6f
as_of: abaaff3 2026-11-04
author: fast-worker
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### Q-f491 Reader._parse spies take *rest
fact: test_api_usage (spy_on_parse) and test_api_live (ReadFolder.spy) spy Reader._parse with positional args, so a new _parse parameter needs *rest in both spies. test_transcripts asserts the record and cache entry field lists, so a new field changes those asserts too.
check: grep -n "def spy\|_fields" tests/test_api_usage.py tests/test_api_live.py tests/test_transcripts.py
evidence: tests/test_api_usage.py, tests/test_api_live.py, tests/test_transcripts.py
fp: 506f42409a56
as_of: abaaff3 2026-11-04
author: fast-worker
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### Q-aa2f Held-usage page checks must release
fact: A pages.mjs check that holds usage (bootHeld) and never releases it leaves the grace timer and 1 s /api/projects poll running into the next check, so later request counts fail in a cascade. Each held-usage check releases and awaits data-usage (finish) before it ends.
check: grep -n "bootHeld\|finish(app)" tests/js/pages.mjs
evidence: tests/js/pages.mjs, dashboard/static/js/app.js
fp: cb6189238218
as_of: abaaff3 2026-11-04
author: fast-worker
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### Q-9852 /api/projects request counts are pinned
fact: tests/js/checks.mjs pins exact /api/projects counts across project switches and a recovered boot, and test_shell_e2e.py pins one per load, so client code that fetches /api/projects on a project switch breaks them.
check: grep -n 'count("/api/projects")' tests/js/checks.mjs; grep -n 'api_requests("/api/projects")' tests/test_shell_e2e.py
evidence: tests/js/checks.mjs, tests/test_shell_e2e.py
fp: 1947428ff1f4
as_of: abaaff3 2026-11-04
author: verifier
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### Q-ddf2 CDP Fetch tests pump their own waits
fact: An E2E test that holds or fulfills /api/projects through CDP Fetch answers paused requests from its own loop (wait_pumped in test_pages_e2e.py), because boot calls /api/projects and Page.wait_for never drains paused events. A page.eval template that takes a CSS selector through %s needs json.dumps, or ".x" throws a SyntaxError and "tag.x" a ReferenceError.
check: grep -n "def wait_pumped\|% json.dumps(selector)" tests/test_pages_e2e.py
evidence: tests/test_pages_e2e.py
fp: 46f91f6a5d7f
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-04
uses: 0

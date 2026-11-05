# dashboard-live

### V-1c9f /api/live token fields and hit_rate
fact: In /api/live, minutes[].tokens and by_model count new tokens only (input, both cache writes, output); cache_read is its own field per minute and per request. requests[].tokens is the all-kinds total, so a Live bar includes cache. hit_rate (usage.py) is cache_read / (cache_read + input + cache_write), close to the cache-read share.
check: grep -n "fresh = \|req.tokens = " dashboard/api_live.py; grep -n "denom = " dashboard/usage.py
evidence: dashboard/api_live.py, dashboard/usage.py, tests/test_api_live.py
fp: 435949b04400
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### V-7b16 Subagent links: toolUseResult.agentId, foreground ones late
fact: A dispatcher's user row carries toolUseResult.agentId (the child's run id); every subagent row carries its own agentId. A background launch writes that row at once (async_launched), a foreground Agent call only when the child finishes, so it reads as unlinked until then. meta.json parentAgentId, spawnDepth and toolUseId are undocumented.
check: grep -n "foreground agent is linked" dashboard/api_live.py
evidence: dashboard/api_live.py, dashboard/transcripts.py
fp: a24405a0da25
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### V-e876 Byte prefilters: a key needle keeps its colon
fact: A byte prefilter needle for a JSON key includes its colon (b'"toolUseResult":'). A bare needle also matches a string value, such as a Grep pattern in a tool input, and that row's usage is lost. Rounds fixtures have sorted keys and a top-level "agentId" on every row, so an agentId needle looks only after the toolUseResult key.
check: /usr/bin/python3 -m unittest discover -s tests -p test_transcripts_links.py -k word_keeps
evidence: dashboard/transcripts.py, tests/test_transcripts_links.py, tests/fixtures/rounds/worker-handback-wakes-lead.jsonl
fp: 08487d310a1d
as_of: abaaff3 2026-11-04
author: verifier
created: 2026-11-04
last_used: 2026-11-04
uses: 0
promote: approved

### V-2f56 Live page clock, ticker and poll
fact: The Live page has one clock, nowMs() = server_time + (env.now() - receivedAt), held against step-backs under STEP_BACK_MS (2 s). A 1 s ticker (env.startTick/stopTick) only repaints; syncTick runs it while the page is active, the tab visible and the state live or idle. live_poll.js polls every 1000 ms.
check: grep -n "function syncTick\|function nowMs\|STEP_BACK_MS =" dashboard/static/js/pages/live.js; grep -n "POLL_MS = " dashboard/static/js/live_poll.js
evidence: dashboard/static/js/pages/live.js, dashboard/static/js/live_poll.js
fp: d6c41d7d3bfd
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### V-e534 Live rules go in live.css with an lv- prefix
fact: The LiveCss tests in test_static_shell.py cover only live.css (lv- classes, tokens only, motion under no-preference); a new Live sheet needs its own asserts. A live.css rule on an app class (sb-row, swatch, dy) needs that name in the test's shared set.
check: /usr/bin/python3 -m unittest discover -s tests -p test_static_shell.py -k every_class_starts_lv
evidence: tests/test_static_shell.py, dashboard/static/live.css, dashboard/static/index.html
fp: de3a178e456d
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### V-968a Live mocks render without a session
fact: A Live mock needs no session: stub /api/live with tests/fixtures/live/live.json via Page.addScriptToEvaluateOnNewDocument, then dump the DOM. Serve it from a plain static server rooted at dashboard/, because server.py's CSP (style-src 'self') silently drops inline style="" such as bar widths.
check: ls tests/fixtures/live/live.json; grep -n "style-src" dashboard/server.py
evidence: tests/fixtures/live/live.json, dashboard/server.py
fp: c44b614ab5c2
as_of: abaaff3 2026-11-04
author: designer
created: 2026-11-04
last_used: 2026-11-04
uses: 0

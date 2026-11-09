# dashboard-live

### V-1c9f /api/live token fields and hit_rate
fact: In /api/live, minutes[].tokens and by_model count new tokens only (input, cache writes, output); cache_read is its own field. requests[].tokens includes cache, so a Live bar does. hit_rate (usage.py) is cache_read / (cache_read + input + cache_write).
check: grep -n "fresh = \|req.tokens = " dashboard/api_live.py; grep -n "denom = " dashboard/usage.py
evidence: dashboard/api_live.py, dashboard/usage.py, tests/test_api_live.py
fp: 435949b04400
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-09
uses: 3

### V-7b16 Subagent links: toolUseResult.agentId, foreground ones late
fact: A dispatcher's user row carries toolUseResult.agentId (the child's run id); every subagent row carries its own agentId. A background launch writes that row at once (async_launched), a foreground Agent call only when the child finishes, so it reads as unlinked until then.
check: grep -n "foreground agent is linked" dashboard/api_live.py
evidence: dashboard/api_live.py, dashboard/transcripts.py
fp: a24405a0da25
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-09
uses: 4

### V-e876 Byte prefilters: a key needle keeps its colon
fact: A JSON key needle keeps its colon (project-facts V-e876). Rounds fixtures have sorted keys and a top-level "agentId" on every row, so an agentId needle looks only after the toolUseResult key.
check: /usr/bin/python3 -m unittest discover -s tests -p test_transcripts_links.py -k word_keeps
evidence: dashboard/transcripts.py, tests/test_transcripts_links.py, tests/fixtures/rounds/worker-handback-wakes-lead.jsonl
fp: 08487d310a1d
as_of: 7d8af23 2026-11-09
author: verifier
created: 2026-11-04
last_used: 2026-11-08
uses: 4
promote: approved

### V-2f56 Live page clock, ticker and poll
fact: The Live page's one clock is nowMs() = server_time + (env.now() - receivedAt), held against step-backs under STEP_BACK_MS (2 s). A 1 s ticker only repaints; syncTick runs it while the page is active, visible and live or idle. live_poll.js polls every 1000 ms.
check: grep -n "function syncTick\|function nowMs\|STEP_BACK_MS =" dashboard/static/js/pages/live.js; grep -n "POLL_MS = " dashboard/static/js/live_poll.js
evidence: dashboard/static/js/pages/live.js, dashboard/static/js/live_poll.js
fp: d6c41d7d3bfd
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### V-968a Live mocks render without a session
fact: tests/fixtures/live/*.json are /api/live payload mocks. Stub /api/live with one via Page.addScriptToEvaluateOnNewDocument and serve from a static server rooted at dashboard/, because server.py's CSP (style-src 'self') drops inline style="" such as bar widths.
check: ls tests/fixtures/live/live.json; grep -n "style-src" dashboard/server.py
evidence: tests/fixtures/live/live.json, dashboard/server.py
fp: c44b614ab5c2
as_of: 7d8af23 2026-11-09
author: designer
created: 2026-11-04
last_used: 2026-11-09
uses: 1

### V-0acf /api/live: one project, a 30-minute window, a fixture clock
fact: /api/live serves one project (project=all gets 400 pick_project) and only sessions with a request in the last RUNNING_MINUTES (30); it has no "at" parameter. It ignores records after now, so a fixture clock replays minute T inside that window. server._fixture_now takes session.json "now" only as ISO with an offset, else it silently uses the real clock.
check: grep -n "pick_project\|^RUNNING_MINUTES\|records after now" dashboard/api_live.py; grep -n "def _fixture_now" -A8 dashboard/server.py
evidence: dashboard/api_live.py, dashboard/server.py
fp: 6242c1496b60
as_of: 7d8af23 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0
promote: approved

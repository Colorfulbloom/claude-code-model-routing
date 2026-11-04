### F-8e67 Live page cache lanes (direction B) and liveness states
status: in-progress
kind: code
dates: 2026-11-03 .. 2026-11-03
refs:
  commit: pending (branch feature/live-cache-lanes)
summary: Live chart card shows a session bar by kind, new tokens per minute, a cache-read lane, a Now band, a ticking request age and a wait line; poll drops to 1 s
decisions:
- /api/live minutes[].tokens and by_model count new tokens only (input + cache writes + output); cache_read is a separate field per minute and per request; requests[].tokens stays the all-kinds total, so the table keeps its meaning
- the lane scale is computed on the page from max(minutes[].cache_read), no server lane axis; peak 0 draws the baseline and a lone 0 label
- one page clock nowMs() = server_time + (env.now() - receivedAt), held against latency step-backs under 2 s; a separate 1 s ticker (env.startTick/stopTick) only repaints, and runs only while active, visible and live or idle
- the header blink fires only when an answer brings a new newest request id, never on a tick or other changed numbers (designer plan review)
- reduced motion keeps only the animation block; it does not stop the tick (designer: a changing number is not motion; Pause stops it)
- Cache read column right after Tokens per the brief; the board's last position was a mock artifact (designer confirmed)
- POLL_MS 1000: median /api/live 0.3 ms on the largest test world, 6.6 ms unchanged and 30.3 ms after a change with 300 transcript files (HTTP 7.2 / 31.7 ms), under the owner's 50 ms rule
- idle header keeps the shipped "Last request at <time>"; the quiet board's "Started ... 25 min" came from text replacement in gen.py
rejected:
- keeping minutes[].tokens as the all-kinds total and adding a new field: two meanings for one chart, and by_model would still need a new-token twin
- driving the tick through env.setTimer: it would shift the poller's fake clock in the node checks
- dropping the phone table labels: designer kept them, the fix is flex with a 6px gap
files: dashboard/api_live.py, dashboard/static/js/pages/live.js, dashboard/static/js/live_poll.js, dashboard/static/live.css, dashboard/static/strings.json, tests/test_api_live.py, tests/js/live_checks.mjs, tests/fixtures/live, tests/test_live_e2e.py, tests/test_static_shell.py, plugins/routing-dashboard
gotchas:
- tools/build_plugins.py refuses a second rebuild at the same uncommitted version; restore payload/BUILD.json to HEAD first, then rebuild
- live.css rules that touch app classes (sb-row, swatch, dy) need those names in the test_static_shell LiveCss shared allowlist
- tests/e2e_checks/live.json runs on the demo's default clock (empty card), so chart-card checks live in test_live_e2e.py
follow-ups:
- owner runs MR_E2E=1 test_live_e2e.py
- no test puts a 1h cache write into the new-token sum (World.add hardcodes 0)
- fixture totals.cache_read (640,000) is below the minutes' window sum (671,900), predates this build
- the arrived board state was not compared in Chrome (fixed demo clock)

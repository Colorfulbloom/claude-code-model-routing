### F-fd33 Live page dispatch canvas, direction A: who dispatched whom, rounds and states
status: in-progress
kind: code
dates: 2026-11-04 .. 2026-11-04
refs:
  commit: pending (branch feature/live-dispatch-canvas)
summary: A "Dispatches in this session" canvas on the Live page, fed by session.runs[] from dispatch links and resume rows the transcript reader now keeps.
decisions:
- Parent link from the dispatcher's user row toolUseResult.agentId only; meta.json parentAgentId, spawnDepth and toolUseId are undocumented (only the demo builder writes them), so unused.
- No Failed state: the docs say a background subagent ending on an API error is marked failed, but no transcript field documents it and no fixture shows one. A stopped run reads Done or Idle.
- Done = last stop up to now finished (SubagentHandback call, or no tool_use with stop_reason end_turn), no later round, no open child. Main is never done. Working/Idle from active_at (later of last request and current round start) against 60 s.
- Rounds copy hivemind_lib's brief rule (coordinator or human origin, or a peer that is not a launched child and not a hand-back, after a stop). by is @main for coordinator, the run for a known peer, else null.
- Run ids are sha256 first 12 hex of the agent id, so raw ids never leave the server. Whole session scope, like the agents card. label_n numbers repeat runs per route key in dispatch order ("scout 1").
- An unlinked run (foreground agents until they finish) hangs off Main session with a dashed line and a note drafted by tech-writer.
- Prefilter: a line with the "toolUseResult": key is a user row and is parsed only when "agentId" follows; keeps the cold read at +7 to 8 percent (the first version cost +79 percent).
- Rules in live.css with the lv-fl- prefix so LiveCss checks cover them; narrow at the project's 720 px.
rejected:
- Reading meta.json parentAgentId or toolUseId as a fallback: undocumented for real Claude Code.
- A parent_pending flag for foreground children: no proven per-child signal.
- Bare b'"toolUseResult"' needle: also matches a Grep pattern value and dropped that assistant row's usage (end verifier).
- Scroll hints over the canvas (mock): they covered card figures and the round chip; moved to a row under the canvas.
files: dashboard/transcripts.py, dashboard/api_live.py, dashboard/static/js/pages/live_flow.js, dashboard/static/js/pages/live.js, dashboard/static/live.css, dashboard/static/strings.json, tests/test_transcripts_links.py, tests/test_api_live.py, tests/js/live_flow_checks.mjs, tests/test_live_flow_js.py, tests/test_live_flow_e2e.py, tests/fixtures/live_flow/build_flow.py, tests/fixtures/live/flow_*.json, plugins/routing-dashboard
gotchas:
- A blocking (foreground) Agent call writes its link row only when the child finishes, so the child sits under Main session until then.
- Reader._parse is spied with positional args in test_api_usage and test_api_live; a new parameter needs *rest in both spies, and test_transcripts asserts the _Entry field list.
- build_plugins refuses a second payload change at an unshipped version; reset payload/BUILD.json from HEAD, then build again.
- The demo set has no link rows, so on it every agent shows unlinked with the note.
follow-ups:
- Owner E2E run of test_live_flow_e2e.py and test_live_e2e.py with MR_E2E=1 before merge.
- Check the accessibility tree at 375 in Safari: display: contents on the aria-hidden card layer.
- If Claude Code documents a failed-run field, add the Failed state the boards drew.

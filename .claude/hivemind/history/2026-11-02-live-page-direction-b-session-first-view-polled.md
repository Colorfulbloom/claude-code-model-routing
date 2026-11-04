### F-e969 Live page, direction B: session-first view polled every 3 seconds
status: shipped
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: 0be31523c2211a1d764790430b94339286a0b2af (branch feature/live-page, merged into development)
summary: New Live page and read-only GET /api/live route that show one project's running session minute by minute
decisions:
- One new route, /api/live, polled every 3 s while the Live section and the tab are visible; no server push (owner default).
- The route reads only the project's transcript folder (Reader.read_folder) on the shared per-file cache, and keeps a per-folder session index keyed by the folder signature, so a poll touches one session's records.
- The live route never holds api_usage Cache.lock while reading, so a slow All projects build on /api/usage does not block it; it still waits on Reader._lock during a cold full read.
- Running means a request in the last 30 minutes (RUNNING_MINUTES); active means a request in the last 60 s; never "Ended", idle shows "Last request at {time}".
- Etag over the payload minus server_time; relative times are computed by the page from server_time, so the etag changes only on data, minute or active changes.
- Sticky session: the page sends the shown session id; the server flags session_gone and falls back to the newest running session (designer review need 1 and 2).
- Styles in a new dashboard/static/live.css to stay clear of app.css, which another lead edits; strings added as live_* keys and existing keys reused where the meaning matched.
- Chart legend totals cover the 30 charted minutes, not the whole session; colours by charts.modelClass (categorical, not the --rk ramp, so the owner's ramp exception does not apply).
- Under-a-cent row cost shows "<$0.01" (live_cost_lt_cent); last-minute growth under a cent reads "Under $0.01 in the last minute" (tech-writer fix).
rejected:
- Server push (SSE or long polling): the owner chose polling, and polling fits the read-only standard-library server.
- Rebuilding the session index incrementally per appended line: more code for a dedupe pass that stays in tens of milliseconds per changed poll.
- Building the E2E demo set with build_demo --now: the demo data depends on its clock, so the Tidewater session moves; the test builds at the default clock and moves only session.json "now".
- A per-second retry countdown in the Not updating notice: it would re-announce in the status region every second.
files: dashboard/api_live.py, dashboard/transcripts.py, dashboard/api_usage.py, dashboard/server.py, dashboard/static/js/pages/live.js, dashboard/static/js/live_poll.js, dashboard/static/live.css, dashboard/static/index.html, dashboard/static/js/app.js, dashboard/static/js/router.js, dashboard/static/js/shell.js, dashboard/static/js/icons.js, dashboard/static/js/api.js, dashboard/static/js/charts.js, dashboard/static/strings.json, tests/test_api_live.py, tests/test_live_js.py, tests/js/live_checks.mjs, tests/test_live_e2e.py, tests/fixtures/live
gotchas:
- A new index.html section needs tests/e2e_checks/<page>.json, the page counts in tests/test_e2e_checks.py, the section count in tests/test_shell_e2e.py and the section list in tests/js/fakedom.mjs.
- Switching to All projects while Live is visible must stop the poller before its reset, or one GET /api/live?project=all goes out (verifier find, fixed, node check added).
- The demo set's c57d41c0 session runs 20:01 to 20:48 UTC on October 30 at the default clock; session.json now 20:24:44Z reproduces the designer's "mid" numbers (755K, $0.94, 24 requests).
follow-ups:
- Owner runs the browser E2E: MR_E2E=1 /usr/bin/python3 -m unittest discover -s tests -p test_live_e2e.py
- Rows with neither a message id nor a request id that share time, session and run get the same row id (rare; nice to fix).

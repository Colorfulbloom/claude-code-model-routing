### F-1512 Usage loading strip, direction C: files-read count, placeholders, retry notice
status: shipped
kind: code
dates: 2026-11-04 .. 2026-11-04
refs:
  commit: 2e7e11b1d254777eea6abe39530b0b4e1ccd8d0c (branch feature/usage-loading-strip, merged into development)
summary: While /api/usage is pending the usage pages show a strip with an honest files-read count over placeholder cards, and a failed answer shows a retry notice with the right cause.
decisions:
- Reader.files_read counts a file after it is parsed (old skipped files at once), reset before each scan, never touched by read_folder; /api/projects reader block carries it.
- 300 ms grace gated by a flag set by the timer (a timer can fire early); Needs attention is held back during the grace too so nothing shifts.
- Strip and error notice nodes are kept per page section and updated in place; the poll never re-renders the page unless reader.readable flips, so focus and the live region stay stable.
- A wait that starts after boot asks /api/projects once when the grace ends (only for a visible usage page of a project whose folder exists), so a fast load never adds a request and the strip opens on the real stage.
- Status region announces once per stage (read stage with the total only); the first stage is written 50 ms after insertion so it is announced.
- Retrying keeps the notice node and changes only the button; a failed retry draws a new alert; success moves focus to the h1.
- Any non-ok usage answer, and an ok payload with no view, shows the error notice; the transcripts state stays for reader.readable false and payload.unreadable.
- usageAgain drops a kept 4xx or no-view answer before asking again.
rejected:
- Re-rendering the usage pages on every poll answer, because it rebuilds Needs attention every second and loses focus.
- Fetching /api/projects at the start of every wait, because it broke exact request counts in tests/js/checks.mjs and tests/test_shell_e2e.py.
- Sizing rows placeholders for the tallest case, because most pages would jump up when data lands (designer).
files: dashboard/transcripts.py, dashboard/api_usage.py, dashboard/static/js/usage-loading.js, dashboard/static/js/usage-page.js, dashboard/static/js/app.js, dashboard/static/js/api.js, dashboard/static/js/pages/overview.js, dashboard/static/js/pages/all-projects.js, dashboard/static/app.css, dashboard/static/strings.json, tests/js/pages.mjs, tests/test_pages_e2e.py, tests/test_transcripts.py, tests/test_api_usage.py, tests/test_api_live.py, plugins/routing-dashboard
gotchas:
- tools/build_plugins.py copies only tracked files, so stage a new source file before the build, or the payload silently leaves it out.
- A node page test that leaves usage held keeps its grace timer and poll running against the next test's fetch.
follow-ups:
- Retry state is global, not per project, so a click on another project's Try again while one retry runs is dropped.
- Node tests do not cover a save during a wait or retry, or the after-boot reader refresh.
- Owner runs the three new E2E checks with MR_E2E=1.

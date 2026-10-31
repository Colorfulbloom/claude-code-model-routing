### F-89f8 Draw only the visible page and name a folder the server can't read (#72, PR #78)
status: shipped
kind: code
dates: 2026-10-31 .. 2026-10-31
refs:
  commit: 9af3208b965013b0353f6baeaae8d55eb570b25b (branch fix/72-visible-page-draws, merged into development)
summary: Every route change drew all 12 page modules while one section showed. Now only the section sectionFor names draws. An unreadable transcripts folder now shows "Can't read the transcripts" and names the folder, where it used to read as no usage. No lead ran this work.
decisions:
- A payload that lands for a hidden page waits, and moving to that page draws it for the current project and range.
- A folder counts as unreadable when it can't be listed, or when it has files and none of them open. A folder of files skipped as old stays readable.
- unreadable and top_unreadable join the fingerprint, so a kept answer rebuilds when the failure changes.
- The existing string takes the path, so the change needs no new copy.
rejected:
- Reusing no_usage for a read failure. no_usage keeps its meaning, and a project with no transcript folder still shows "No usage yet".
files: dashboard/api_usage.py, dashboard/static/js/app.js, dashboard/static/js/pages/overview.js, dashboard/static/js/pages/rules.js, dashboard/static/js/pages/settings.js, dashboard/static/js/usage-page.js, dashboard/transcripts.py, tests/js/pages.mjs, tests/test_api_usage.py, tests/test_transcripts.py
gotchas:
- A project path over 200 characters matches a failed folder on its first 200 characters, because a failed folder has no rows to confirm it.
- One failed project folder doesn't show on All projects, which shows what it could read. A top folder failure shows on every usage page.
- agent-detail.js, session-detail.js and trail.js keep their last draw while hidden.
facts: W-e6b6

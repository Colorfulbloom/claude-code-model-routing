### F-c6ef Usage route and end-to-end page sweep, Join track (#55, #56)
status: shipped
kind: code
dates: 2026-10-30 .. 2026-10-30
refs:
  commit: 3fd2d26a0a03a53784b25972b23c7929fd8fdb13 (branch feature/usage-join, merged into development)
summary: Round 2, Join track. /api/usage serves today, 7 day and 30 day views for one project or All projects, with a start-up warm thread (#55). A sweep loads 14 routes at 1440 and 375 in light and dark, 56 loads (#56). The suite on 3fd2d26 is 1665 tests, 18 skipped, about 204 s. The owner ran the 16 browser tests, 16 of 16 passed on f9cbd33. Scaled result on 150,231 made-up records, no real transcripts: cold build 0.94 to 1.23 s, cached 0.17 s, payload up to 2.1 MB.
decisions:
- Fixture clock in session.json. now and tz sit there and build_demo.py writes both, because the set ages out of the windows on the real clock and screenshots need the same window as the round 3 screens.
- Emulation.setDeviceMetricsOverride sets 375, because --window-size=375,900 only reached innerWidth 500. The sweep asserts innerWidth on every load.
- The browser's request list from the DevTools Network domain is the check that the page requested only 127.0.0.1, and the access log is the cross-check, because a server log lists only what reached it.
- Verifier deferred to round 3 V3, shared with Usage pages. None ran on this branch.
- /api/usage with no project value means the current project, as /api/settings does.
- Consolidation stayed inside the caps and left config.json alone. W-8e61 merged into W-f6ed, T-baa7 into T-7629, and W-871e, W-d2ec, W-1acf were tightened. 13 effort-unknown HiveMind tally rows from October 20 and 21 folded into 5, samples kept, by editing tallies.json, which brought token-tallies from 17,330 to 15,776 bytes.
rejected:
- --dump-dom for each load. A one-shot run can't hold back a request or take a screenshot.
- An iframe host page for 375. The override made it unnecessary.
- Agents launching headless Chrome. The owner runs MR_E2E=1.
- Proposed worktree guard refusals of heredocs, inline python, cd && git, gh --jq pipes and path variables. A probe of those shapes in a worktree ran them all, and only git -C was refused. D-3ca7 stands with the wider list. The probe's CONTRADICTS on D-3ca7 was also rejected, because shape 5 is a variable as an argument, which D-3ca7 already lists as running.
- Proposed facts on /api/projects skipping the usage lock (api_usage.py says so) and on the demo set's first two projects (too narrow), a reminder to run test_projects.py (the full suite covers it), gh --comments output (unchecked) and the location.hash output block in the Chrome tool (unchecked).
- Proposed fact that a top-level navigate to /api/settings always gets forbidden. Sec-Fetch-Site none passes the guard, so W-871e records the extension's navigate only.
gotchas:
- Page boot awaits loadProject, which awaits api.usage, so data-rendered stays unset while /api/usage is held back. A test that holds it back waits on the section. This stays out of the topics for space.
- A built demo set without now falls back to the real clock and ages out of the windows.
- A cached answer takes about ten times as long at scale as on the demo, 0.17 s against 0.016 s. It was not profiled.
- Most pages are stubs until round 3, so status and stacked bar checks find nothing yet. A positive control test covers them.
facts: W-4654, T-7629, T-3ad1, T-5589, W-871e, W-d2ec, W-1acf, W-f6ed, D-3ca7
follow-ups:
- V3 verifier and the judge's comparison with the round 3 screens are still to come.
- Held for the Settings merge, because the code is on feature/settings-pages only: the Escape listener in the capture phase, external links through externalLink in h.js (6928dc3, which replaced the proposed setAttribute wording), and missing_folder with entries for an implicit project. Propose them again with the Settings consolidation.
- Promotion: project-facts T-7629 to 1665 tests, owner approved. The main session applies the line, and T-7629 stays promote: proposed until then.
- token-tallies has about 600 bytes left. The next overrun needs more folding or the owner's call on the cap.

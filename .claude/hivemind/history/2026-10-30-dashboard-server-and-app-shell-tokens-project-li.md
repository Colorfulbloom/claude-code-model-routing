### F-d571 Dashboard server and app shell: tokens, project list, page stubs (#37, #43, #53, #54)
status: shipped
kind: code
dates: 2026-10-30 .. 2026-10-30
refs:
  commit: 0e72fd47274587aa06c8e11393a9571d763afb79 (branch feature/dashboard-shell, merged into development)
summary: Round 1, track B of the usage build. A read-only server on 127.0.0.1 (#37), shell and chart tokens (#53), the project list and per-project settings (#43), and the app shell with every route and 12 page stubs (#54). The suite is 1598 tests, 13 skipped, on 0e72fd4. Consolidation added topic dashboard and facts W-871e, W-d2ec, W-1acf, W-7178, W-f6ed, W-8e61, widened D-3ca7 and refreshed T-7629.
decisions:
- --fixture is required for any run on the demo set, so the real shell and managed folder stay unread. A fixture run takes them from session.json and FOLDER/managed.
- Default port 8377. --port overrides it and 0 asks the system for a free port.
- A Sec-Fetch-Site guard and a Cross-Origin-Resource-Policy header go beyond #37, so a no-cors GET from another page can't reach the server. The one exemption is a top-level GET of / with Mode navigate and Dest document, which holds no settings.
- tests/strings_pending.txt lists keys no page uses yet, 194 lines at merge. Page tickets remove lines as they land, and the test fails on an unlisted unused key and on a listed key that is now used.
- Route handlers live outside server.py, which holds only the route table, so tracks don't meet in one file. api_settings.py shipped here. api_usage.py comes with U-6 and does not exist on 0e72fd4, and /api/usage is not routed yet.
- 30 days is the default range on every page. The screens built Sessions at 7 days.
- The menu panel opens below the top bar so the menu button stays usable, with no scrim (owner).
- Consolidation split new facts into topic dashboard (prefix W), because testing and dead-ends were at their limits and existing T and D ids can't move. This edited config.json topics, id_prefix and five slices.
- Consolidation folded 11 tally rows of near-identical kinds into their neighbors (ticket, ticket-comment, docs-copy and three scout kinds) to bring token-tallies under 16KB. Samples are kept, up to the 20 per row cap.
rejected:
- Agents launching headless Chrome, including through wrappers or test subprocesses. The owner runs MR_E2E=1. A held proposal advising a launch through a test subprocess was rejected for this reason.
- The proposed fact that heredocs into a scratchpad are refused in worktree agents, as worded. Two probes showed short heredocs and heredocs with expansions run; a body mixing quotes, backticks and $( ) was refused. D-3ca7 records the narrower shape.
- The proposed fact that resize_window has a floor near 1000 CSS px, as worded. The repeat changed nothing at any width, so W-d2ec records both sessions and no floor.
files: dashboard/server.py, dashboard/api_settings.py, dashboard/projects.py, dashboard/static/, examples/routing-dashboard.example.json, tests/js/, tests/strings_pending.txt, tests/test_server.py, tests/test_projects.py, tests/test_shell_e2e.py, tests/test_shell_js.py, tests/test_static_shell.py, tests/test_static_strings.py, tests/test_tokens_contrast.py
gotchas:
- A read of an error body is required in fetchJSON (W-1acf). The cause given is inferred, not watched in a browser.
- The designer reviewed the open menu panel at top:0, not the final position below the top bar.
- 11 of the 13 skips are test_shell_e2e, which a default suite run does not exercise.
- A new isolation worktree starts at origin/main (9fe48f7), so development code is missing there (D-3ca7).
facts: W-871e, W-d2ec, W-1acf, W-7178, W-f6ed, W-8e61, D-3ca7, T-7629
follow-ups:
- Promotion candidate: project-facts T-7629 to 1598 tests, 13 skipped, about 187 seconds. T-7629 stays promote: proposed until the owner approves.
- Issue #43 is still open on GitHub at this entry, though PR #70 ships it.
- token-tallies sits at 16059 of 16384 bytes, so the next consolidation will likely go over. The owner picks a larger limit or further folding.

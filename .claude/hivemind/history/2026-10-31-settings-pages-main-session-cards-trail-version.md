### F-fbdd Settings pages: Main session cards, trail, version chip, Needs attention, Rules reference, Installed files (#41, #42, #44, #45, #63, #64, #65, #69)
status: shipped
kind: code
dates: 2026-10-30 .. 2026-10-31
refs:
  commit: cca09ebed03d8f2c511b94a6803f6390206c7de3 (branch feature/settings-pages, merged into development)
summary: Round 3, Settings track, merged as PR #74. Settings shows the four Main session cards, every row opens its trail in the What decides panel, the version chip reads files, Needs attention, Rules reference and Installed files are built, and Overview gets the Needs attention card. PR #74 reports 1871 tests, 36 skipped. The owner's 34 browser tests all passed on d717fdf, after 29 of 32 on 539391d.
decisions:
- externalLink in h.js is the one path to another site, because every link then passes one https check and opens with no opener or referrer.
- Rule links stay on blob/main until development merges into main, so #42's rule links resolve only after that. The owner merges when phase 1 closes.
- Rule pages link to GitHub, not a served copy, because a served copy needs an exception to the #37 path rule.
- The server's listen queue is 128, because the default of 5 resets a burst of connections and one reset module stops the page. It's the likely cause of the two hung loads, but no browser run has shown that.
- The version is read from files only, never by running claude. A miss reads unknown, and no public source confirms the Caskroom path.
- Consolidation stayed inside the caps and left config.json alone. W-871e merged into W-d2ec, T-c826 retired because project-facts.md holds it word for word. All five held proposals came back: W-4518 holds externalLink, Escape and the implicit project, T-d32f holds install.py, and W-7178 took the ?copy=N import. 11 suspect or unchecked facts were rechecked and refreshed, T-7629 by test load count and the PR reports, not a suite run.
rejected:
- A served copy of the rule pages, for the #37 path rule reason above.
files: dashboard/api_settings.py, dashboard/server.py, dashboard/version.py, dashboard/static/js/h.js, dashboard/static/js/pages/trail.js
gotchas:
- No agent has seen the new pages in Chrome. The owner's end-to-end run covers them.
- A copied server tree needs install.py, because api_settings imports it.
facts: W-4518, T-d32f, W-7178, W-d2ec
follow-ups:
- #41 stays open on an unsettled /effort status check.
- #18 stays open, because its owner check runs on Needs attention.
- Merge development into main when phase 1 closes, so the rule links resolve.

### F-ec2b Usage pages: Overview, Agents, Models, Sessions, All projects and the usage states (#57 to #62)
status: shipped
kind: code
dates: 2026-10-30 .. 2026-10-30
refs:
  commit: ce1f71dd89d4b680f84ece354d32fb781a1c008c (branch feature/usage-pages, merged into development)
summary: Round 3, Usage pages track, merged as PR #73. Overview, Agents, Models, Sessions and their detail pages read /api/usage, All projects compares every transcript folder, and fillUsage draws the no usage, no range, not priced and unreadable states. PR #73 reports 1690 tests, 21 skipped, and the owner's 19 browser tests all passed on cbb22a3. Verifier V3 came back sound with corrections and was not rerun after the fixes, on the owner's instruction.
decisions:
- Clip-pattern head at 375. .dt thead uses the .sr clip pattern, not display:none, because the sweep reads innerText and the head must stay in the page. The LABEL_BAD check reads the computed style and fails any stacked cell with no drawn column name, because the ::before labels are not in innerText. An e2e test proves it catches a removed data-l.
- data-usage is the usage-drawn marker. data-rendered no longer waits on /api/usage, so app.js sets data-usage="1" after the first answer for the current project is drawn. A check that reads usage numbers waits for both.
- Moved-folder note. A listed project whose folder is gone but whose saved transcripts still give usage shows that usage under one note, es_missing_usage_t, because the pin check reads the folder and can show no pin or an unknown one. A project with no transcripts stays on Folder not found.
- No refetch on a range change. Switching range redraws from the stored payload and fetches nothing. A failed payload is asked for again on the next route or project change, never on a range change. test_range_fetches_nothing_and_project_fetches_once covers it.
- Consolidation stayed inside the caps and left config.json and project-facts.md alone. 12 token-tallies rows folded by merging same-task kinds at the same agent, model and effort, all 330 samples kept, which brought the table from 16,994 to 15,696 bytes. The kinds are ticket and ticket-draft into ticket-copy, docs-draft, docs-copy and readme-docs into docs, commit-and-pr-text into commit-pr-text, docs-lookup into doc-quote-lookup, dashboard-feature into feature-build.
- W-1acf retired, because the comment at the read in api.js says the same thing. That made room for W-e6b6, which merges the fillUsage, data-usage and innerText proposals. W-d2ec and W-871e got shorter.
- T-7629 stays as it was, count and as_of, because the owner updates it at the end of the build. apply had stamped as_of with ce1f71d from a verifier note, so the old fp and as_of went back by hand. The contradiction from the Usage lead was not folded in.
rejected:
- display:none on the stacked head. It took the column names out of innerText, and the sweep failed 10 loads at 375 on 69e7834.
- Proposed fact that .dt thead is display:none at 375 with labels hidden from innerText. Stale, cbb22a3 replaced it with the clip pattern.
- Proposed fact that the e2e captures stop at 900px with no phone menu shot. Stale, the sweep now saves full-page shots at 375 and an e2e test saves the open menu.
- Proposed fact that strings_pending.txt takes only literal t("key") callers. It misses RUNTIME_PREFIXES, and the test's own failure message says what to do.
- Proposed fact on the demo's by_project rows in the all view. Too narrow, and tests/e2e_checks/all-projects.json holds those texts.
- Proposed fact that a shell value's resolver entry has no path. Already stated at dashboard/resolve.py and at sourceOf in pin-view.js.
- Proposed fact that the unknown-model pin path needs a demo copy. Already in code as collect_nomodel in tests/test_pages_js.py.
- Proposed fact that the worktree guard refuses a plain Python heredoc and for loops. It conflicts with the October 30 probes behind D-3ca7, its evidence path has nothing on it, and I could not check it from the main checkout.
- Proposed trick of a temporary line in tests/js/pages.mjs to see the check list. Low value, and it edits a test file for a debug print.
gotchas:
- No agent checked 375 in Chrome, because the extension window didn't resize. The owner's end-to-end run covers it.
- The 5 unparsed HIVEMIND lines failed only because the files were on a branch at capture. Their paths exist on development now, except tests/js/rules_checks.mjs.
facts: W-e6b6, W-7178, W-d2ec, W-871e, T-07ef, T-3ad1, D-2e12
follow-ups:
- #72: draw only the visible section, show Can't read the transcripts for an unreadable project folder, and profile a cached /api/usage.
- #58 owner check on real transcripts, Main session effort under Ran with, against /effort status.
- #63 fills the Needs attention card after the Settings branch rebases.
- Held for the Settings merge, because the code is on feature/settings-pages only: api_settings importing install.py so a copied server tree must carry it, and the pages/x.js?copy=N import for fresh module state. Propose them again with the Settings consolidation, with the three held in F-c6ef.
- T-7629 is behind. PR #73 reports 1690 tests, 21 skipped. The owner's update comes at the end of the build.
- token-tallies has 688 bytes left of 16,384. The next overrun needs more folding or the owner's call on the cap.

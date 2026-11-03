### F-919d HiveMind consolidation after Live, Stage 5 and the plugin
status: in-progress
kind: mixed
dates: 2026-11-03 .. 2026-11-03
refs:
  commit: pending (branch chore/hivemind-consolidation-nov3)
  file: .claude/hivemind/topics/dashboard-plugin.md
summary: Folds the 107 inbox run files from #144 to #147, salvages the plugin and Live proposals the capture hook dropped, adds two topics, and applies the two owner-approved project-facts edits.
decisions:
- Salvaged 21 unparsed NEW lines by hand: they were dropped because their evidence paths existed only on feature branches when captured; all exist on development now, and each was checked by its own check command.
- Split by subject into two new topics, dashboard-plugin (prefix L) and dashboard-band (prefix A), because dashboard, dashboard-page, testing-node and testing-pages could not take the plugin and band facts under 4096 bytes. This edited config.json topics and id_prefix; the dashboard* slices already cover both.
- Raised history_index_max_lines from the default 40 to 60 in config.json. history rollup only rolls finished quarters and all 42 entries are in 2026-Q4, so check could not pass otherwise.
- E-83df rewritten: with no known model the cap branch now uses the top-level cap (resolve.py _computed_becomes), which the 2026-11-02 contradictions reported.
- T-7629 and project-facts.md set to 3319 tests, 77 skipped, about 329 s at a452d5d; 75 MR_E2E skips counted by loading the suite and reading skip decorators, not by an MR_E2E run.
- Added L-13fb (plugin payload rebuild and version bump) to project-facts.md, approved by the owner on November 3.
- D-3ca7 softened: several worktree agents reported heredocs, for loops, a pipe into diff and ${VAR:-x} refused, which the old "ran" sentence contradicted.
rejected:
- The page has no automatic refresh: stale since the Live page polls.
- /api/usage size and timing, /api/projects lock note, server bind-failure note: one-off measurement, code comment, or a test gap for a ticket.
- Demo transcripts three rows per message id: duplicate of D-2e12.
- Phone band layering and Arrange drop-down clipping: bug reports (the first fixed in 4435c1d), not facts.
- Rail .s4-p wrapping, scroll-margin 110 px clearance, test_e2e_checks gating list, Live All projects extra GET: code-local, fragile or review findings.
- Resumed-agent tally overwrite and apply-time snapshot dead ends: fixed by F-1906 and #144.
- 375 emulation by unwrapping media blocks: duplicate of K-486e.
- Full-suite proposal with scratchpad evidence: folded into T-7629 instead.
files: .claude/hivemind/config.json, .claude/hivemind/topics/dashboard-plugin.md, .claude/hivemind/topics/dashboard-band.md, .claude/hivemind/topics/testing.md, .claude/hivemind/topics/testing-edit.md, .claude/hivemind/topics/testing-install.md, .claude/hivemind/topics/dead-ends.md, .claude/rules/project-facts.md
gotchas:
- testing-pages, testing-edit and dead-ends sit within 30 bytes of 4096; the next fact there needs a shrink or a split.
- The repo hooks/ has no worktree guard, so D-3ca7 rests on agent reports, not on a read of the guard.
facts: L-13fb, L-bd45, L-7075, L-2116, L-cbc8, W-88a3, W-734f, N-289e, P-0fe8, A-3436, A-cb5f, A-aed6, A-8f4c, A-f16f, X-b9fc, X-5529, G-066f, R-3ecc, R-c047, S-b40c, I-3123, I-b01b, I-3e12, I-9984, I-14ae, T-a651, T-7629, T-07ef, E-5b16, E-83df, D-3ca7, X-2617, K-486e, P-db96, N-5baa
follow-ups:
- hivemind_lib: let rollup fold shipped entries inside the current quarter, so history/INDEX stays under its cap without raising it.
- Owner: consider promoting D-3ca7's softer wording and I-14ae (webbrowser.get().open) to project-facts.md.

### F-361e HiveMind consolidation after #91 and #104
status: shipped
kind: mixed
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: 6594de7493fa7a48165667141f5d68b9f187ac4e (branch chore/hivemind-consolidation-104, merged into development)
  file: .claude/hivemind/topics/testing.md
summary: Commits the waiting HiveMind state from #91 and #104, decides the two open proposals, refreshes the full-suite count and fixes the #104 history entry.
decisions:
- Accepted the bare-repo proposal as G-c2d7 after reading _is_bare and running test_git_check.py (85 OK).
- Accepted the edit_card_checks row proposal as N-e2fd after reading plainRows, rowIn and rowOf and running test_edit_card_js.py (5 OK).
- T-7629 refreshed to 3110 tests, 60 skipped, about 283 s; the skip split (58 MR_E2E, 1 MR_DOCS_LIVE, 1 MR_SUBAGENT_DOCS) comes from loading the suite and reading skip decorators, not from an MR_E2E run. project-facts.md got the same pure count refresh.
- S-3c1a reworded: helpers._tmp_base now refuses a base inside a git work tree, so the old "MR_TEST_TMP inside a repo changes that" warning no longer holds.
- F-bd91 corrected: bare repo named .git is refused, and ed_row_lock_start_local is in use as the local row note.
rejected:
- Running the suite with MR_E2E=1 to count skips: the owner runs those, and the decorators answer the question.
files: .claude/hivemind/topics/dashboard-git.md, .claude/hivemind/topics/testing-node.md, .claude/hivemind/topics/testing.md, .claude/hivemind/topics/dashboard-settings.md, .claude/hivemind/history/2026-11-02-the-dashboard-reads-and-writes-the-repo-root-s-s.md, .claude/rules/project-facts.md
gotchas:
- T-c826 in project-facts.md has no topic record left; its update goes to the owner as a promotion.
facts: G-c2d7, N-e2fd, T-7629, S-3c1a
follow-ups:
- Owner: approve the T-c826 wording change in project-facts.md (MR_TEST_TMP must sit outside every repo).

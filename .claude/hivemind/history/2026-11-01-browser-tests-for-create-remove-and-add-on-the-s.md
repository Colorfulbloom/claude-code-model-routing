### F-b993 Browser tests for Create, Remove and Add on the Settings page (PR #127)
status: shipped
kind: code
dates: 2026-11-01 .. 2026-11-01
refs:
  commit: 907bd7f0cfcbdd131b9ce4b04bec884dc36fc768 (branch test/settings-write-e2e, merged into development)
summary: Seven new browser tests in test_edit_e2e.py cover Undo after Create, Remove and Add, Remove then Cancel, the Remove line link's contrast and the remove review at 375, with 2 new node checks in edit_card_checks.mjs. No product code changed. The commit set the full suite at 2609 tests with 46 skipped. PR #127 reports the 12 test_edit_e2e.py tests passing with MR_E2E=1. Part of #92. This work had no lead, so a later consolidation records it.
decisions:
- Each test builds its own throwaway project and compares against copies made before the write.
files: .claude/hivemind/topics/testing.md, .claude/rules/project-facts.md, tests/js/edit_card_checks.mjs, tests/test_edit_e2e.py
facts: T-7629

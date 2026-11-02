### F-6fc5 No-markup scan reads the Stage 6 card files
status: shipped
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: ab7ca9aba9f8ad4411b11d2b175af3222e6b4819 (branch fix/markup-scan-stage-6-files, merged into development)
summary: The Node no-markup scan in edit_card_checks.mjs now reads edit_setting.js and edit_words.js, matching the nine CARD_FILES in test_edit_card_js.py (PR #134).
decisions:
- Added the two names to the scan list only; the scan found no markup in either file.
rejected:
- One shared list for Python and Node: the Node file also runs alone under MR_ONLY, so sharing needs a new env var.
files: tests/js/edit_card_checks.mjs
gotchas:
- A new card module must be added to both CARD_FILES and the Node scan list, or the scan silently skips it.
follow-ups:
- Optional: pass CARD_FILES to the Node run through the env built at test_edit_card_js.py:464.

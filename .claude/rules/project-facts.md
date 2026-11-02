# Project facts (reviewed)

Owner-approved facts promoted from HiveMind. Only deep-reasoner edits this file, and only after the owner approves a promotion. Limit: 60 lines.

- T-7629 Full suite: from the repo root, `/usr/bin/python3 -m unittest discover -s tests` runs 2982 tests (58 skipped) in about 265 seconds (2026-11-02). 56 of the skips need `MR_E2E=1`, and the owner runs those. The other two need `MR_DOCS_LIVE=1` and `MR_SUBAGENT_DOCS`. Run it alone, not beside a harness batch.
- T-5589 Test subsets: `discover -s tests -k <pattern>` or `-p test_x.py` works; dotted names such as `tests.test_x` fail with "No module named 'helpers'".
- T-c826 MR_TEST_TMP is optional: tests/helpers.py creates the directory when it is set and missing; unset means the system temp dir.
- E-5b16 Write core: `edit_store.py` alone writes settings.
- T-07ef Settings harness: `dashboard/experiments/harness/` measures precedence with no real API call (fakeapi.py on 127.0.0.1, throwaway HOME). `claude -p "/effort status"` and `"/autocompact"` send no request. Never run a batch as a check.
- D-1534 Doc anchors: check code.claude.com anchors against the rendered HTML `id="..."` attributes, not .md heading slugs. Python urllib needs a custom User-Agent; the default gets 403.
- D-b739 Fixture ignores: a global gitignore can drop `.claude/settings.local.json`; the repo `.gitignore` negates it for `tests/fixtures/**`. Check with `git check-ignore -v`.
- K-6860 Nested `:has()`: it is invalid CSS, so the browser drops the whole rule with no error. Check Settings rail padding by computed value, not by `--s4-foot`.
- U-0aa1 Undo history: edit ledgers are per file, and history merges the layers by (time, seq). Server `rows[-1]` is one file's newest row and page `rows[0]` is the project's newest, so a row with `undoable` or `undo_anyway` can still sit in Older backups.
- R-06c2 Rule count: adding or removing a rule in `dashboard/rules.json` breaks `test_api_rules` until the All, Tested, Documented and Assumed texts in `tests/e2e_checks/rules.json` change and `docs/rules-reference.md` is rebuilt with `/usr/bin/python3 dashboard/reference_page.py`.
- N-9919 Settings node checks: `tests/js/settings_checks.mjs` reads payloads from `MR_PAYLOADS`, which `tests/test_settings_js.py` fills from its CASES list, so run it through that test. A fixture a check names with `real(...)` joins CASES, or the check fails with ENOENT.
- D-c684 macOS traps: `/usr/bin/python3` adds CPATH, LIBRARY_PATH, SDKROOT, MANPATH and `__CF_USER_TEXT_ENCODING` to every child, so env-leak asserts ignore them (SYSTEM_ADDED in `tests/test_harness_guard.py`). BSD sed has no `\b` and exits 0 having changed nothing, and there is no `timeout` command. Rewrite files with Python `re.sub`.
- C-06bf Probe copies: exclude `.claude`, or rsync carries the owner's `settings.local.json` into the copy. A shell that exports a throwaway HOME also shows that file as untracked in `git status`, so run git without the export.

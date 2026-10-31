# Project facts (reviewed)

Owner-approved facts promoted from HiveMind. Only deep-reasoner edits this file, and only after the owner approves a promotion. Limit: 60 lines.

- T-7629 Full suite: from the repo root, `/usr/bin/python3 -m unittest discover -s tests` runs 2285 tests (38 skipped) in about 220 seconds (2026-10-31, on 0766733). 36 of the skips need `MR_E2E=1`, and the owner runs those. Run it alone, not beside a harness batch.
- T-5589 Test subsets: `discover -s tests -k <pattern>` or `-p test_x.py` works; dotted names such as `tests.test_x` fail with "No module named 'helpers'".
- T-c826 MR_TEST_TMP is optional: tests/helpers.py creates the directory when it is set and missing; unset means the system temp dir.
- E-5b16 Write core: `edit_store.py` alone writes settings.
- T-07ef Settings harness: `dashboard/experiments/harness/` measures precedence with no real API call (fakeapi.py on 127.0.0.1, throwaway HOME). `claude -p "/effort status"` and `"/autocompact"` send no request. Never run a batch as a check.
- D-1534 Doc anchors: check code.claude.com anchors against the rendered HTML `id="..."` attributes, not .md heading slugs. Python urllib needs a custom User-Agent; the default gets 403.
- D-b739 Fixture ignores: a global gitignore can drop `.claude/settings.local.json`; the repo `.gitignore` negates it for `tests/fixtures/**`. Check with `git check-ignore -v`.

# Project facts (reviewed)

Owner-approved facts promoted from HiveMind. Only deep-reasoner edits this file, and only after the owner approves a promotion. Limit: 60 lines.

- T-7629 Full suite: from the repo root, `/usr/bin/python3 -m unittest discover -s tests` runs 254 tests in about 51 s (2026-10-20).
- T-5589 Test subsets: `discover -s tests -k <pattern>` or `-p test_x.py` works; dotted names such as `tests.test_x` fail with "No module named 'helpers'".
- T-c826 MR_TEST_TMP is optional: tests/helpers.py creates the directory when it is set and missing; unset means the system temp dir.

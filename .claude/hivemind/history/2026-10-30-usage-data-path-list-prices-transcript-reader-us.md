### F-bbb6 Usage data path: list prices, transcript reader, usage views, pin check, per-model cap, demo set (#40, #48 to #52)
status: shipped
kind: code
dates: 2026-10-30 .. 2026-10-30
refs:
  commit: 203ae0da65041ab17a399e94a4159b548c82554c (branch feature/usage-data, merged into development)
summary: Round 1, track A of the usage build. prices.json and prices.py hold list prices for the 12 catalog models (#48); transcripts.py reads usage records and keeps no content (#49); a valid per-model maxEffortLevel now replaces its file's top-level cap (#50); usage.py builds the views (#51); pincheck.py says whether each agent ran as pinned (#52); tests/fixtures/demo holds the made-up demo set (#40). The full suite grew to 1454 tests. Facts D-2e12, D-3ca7, T-3ad1; refreshed T-7629.
decisions:
- #52 order, worst first, is differs, mixed, overridden, cannot_check, matches_lowered, matches. The ticket listed four states; the build added mixed and cannot_check. Model and effort are checked separately and the agent takes the worse, and a file that pins one setting is checked on that one.
- Oldest data is per folder: ReadResult.oldest_by_folder feeds build_views, which takes the smallest value over the scope's folders, so a skipped old file gives earlier data only to its own project.
- build_views takes a pin_fn callable from pincheck.checker instead of a new View field, so the resolver join stays in pincheck.py. It runs only for a single-project scope.
- Demo paths: project paths in the demo's routing-dashboard.json stay relative to the set, and build_demo.py makes them absolute under out_dir, so nothing machine-specific is committed.
- Only a valid level replaces a top-level cap. The harness on Claude Code 2.1.302 showed per-model max ran xhigh, while per-model turbo ran low with the settings file still accepted. A fixture guards that case.
rejected:
- A global oldest moment, because one skipped file fooled every project.
- cannot_check for a setting with no recorded value. cannot_check now means only that the expected value is Unknown, and a setting no run recorded adds nothing to the agent's state.
- Merging the dedupe namespaces of message id and request id. They stay separate keys, so a row with only a request id does not merge with a row that has a message id. Known limit.
files: dashboard/prices.json, dashboard/prices.py, dashboard/transcripts.py, dashboard/usage.py, dashboard/pincheck.py, dashboard/resolve.py, dashboard/rules.json, dashboard/rules_schema.py, docs/rules-reference.md, dashboard/experiments/harness/cases-model-settings.json, dashboard/experiments/harness/results-2026-10-30-cap-values.jsonl, dashboard/experiments/2026-10-29-model-settings-max-effort.json, tests/test_prices.py, tests/test_transcripts.py, tests/test_usage.py, tests/test_pincheck.py, tests/test_demo.py, tests/test_resolve.py, tests/test_rules_schema.py, tests/fixtures/transcripts/, tests/fixtures/demo/, tests/fixtures/resolution/
gotchas:
- rules.json already said a per-model cap replaces the file's top-level cap, but the code kept the lowest (#50), and no fixture covered it until cap-same-file-per-model-replaces.
- Rows that share a message id keep the largest output_tokens, not the first (D-2e12).
- build_demo.py refuses a folder that holds anything and has no truth.json, before any delete.
facts: D-2e12, D-3ca7, T-3ad1
follow-ups:
- Promotion candidate: project-facts T-7629 to 1454 tests in about 178 seconds. Owner approves; T-7629 stays promote: proposed until then.
- Shell consolidation re-adds the proposals held back because their evidence is on feature/dashboard-shell.

### F-59cd Stop showing the user file's effort level when the model is unknown, Documented default model label, tally cap (#41, PR #77)
status: shipped
kind: code
dates: 2026-10-31 .. 2026-10-31
refs:
  commit: a95084ceb609ee81932968f9885a676a1883dc5b (branch fix/41-effort-unknown-headline, merged into development)
summary: With no known model the dashboard can't say whether the user file's top-level effortLevel applies, so the tile, the trail and Needs attention now show Unknown with no value. model-main-default moves from Assumed to Documented, and this project's tally topic cap rises to 32 KB. No lead ran this work.
decisions:
- valueNotShown hides the value only for effort-level-user-settings-model-unknown and agent-effort-user-settings-model-unknown. The entry keeps the value because the reason text needs it.
- model-main-default became Documented because model-config now says the account type decides the default model. The Rules page counts became Documented 9 and Assumed 8.
- Both rules swap their managed settings quote for the model-config line that says a top-level effortLevel in the user file doesn't count for Opus 5.5.
- The tally cap is a project setting in config.json, because topics/token-tallies.md stood at 16,011 bytes and would pass 16 KB at the next consolidation.
rejected:
- Hiding the value on every Unknown entry. Other Unknown entries still show theirs.
- Raising the default cap in hooks/hivemind_lib.py. The default, the README line and the 4 KB topic cap stayed as they were.
files: dashboard/rules.json, dashboard/static/js/pages/settings.js, docs/rules-reference.md, tests/e2e_checks/rules.json, tests/fixtures/resolution/model-main-default-unknown/expected.json, tests/js/attention_checks.mjs, tests/js/settings_checks.mjs, tests/test_settings_js.py, .claude/hivemind/config.json
gotchas:
- The same merge carried 09c015a, 85eedab and 33cddf8 (agent pins) and 8e57744 (a consolidation), so the merge diff is wider than this entry.
- The Rules page counts in tests/e2e_checks/rules.json went unconfirmed at merge. The owner's later MR_E2E run on PR #93 passed.
facts: T-07ef

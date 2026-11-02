### F-d83b A top-level effort cap lowers an agent's effort row with no model known (#136)
status: in-progress
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: pending (branch fix/136-agent-rows-no-model)
summary: New rule agent-effort-lowered-by-cap-model-unknown lowers an agent effort row with no known model under a top-level maxEffortLevel; agent pins say "the agent's model".
decisions:
- Data-only resolver fix: a scope-agent twin of #91's effort-lowered-by-cap-model-unknown (layers env to user, no default). The #91 guard in _condition_matches and the cap branch of _computed_becomes already handle it, so resolve.py is unchanged.
- Pin card picks three new "agent's model" strings when the winning rule_id starts with "agent-", with literal t() keys per branch so test_static_strings sees them used.
- Rule quotes reused from #91's rule; scout and verifier re-checked them on settings-reference (anchor maxeffortlevel) on 2026-11-02.
- Reason and pin strings drafted by tech-writer.
rejected:
- Dropping the guard for agent rows so agent-effort-lowered-by-cap lowers them: its reason has a {model} slot that would print an unknown model.
- Keying the pin wording on pin.source: rule_id is what says whose model is unknown, and it keeps #137's tests as written.
- A key-building helper in pin-view.js: test_static_strings counts only literal t("...") keys and reported six keys unused.
files: dashboard/rules.json, dashboard/static/js/pin-view.js, dashboard/static/strings.json, docs/rules-reference.md, tests/e2e_checks/rules.json, tests/js/pages.mjs, tests/test_resolve.py, tests/fixtures/resolution
gotchas:
- A user-layer effortLevel with no model stays Unknown under a cap (agent-effort-user-settings-model-unknown), because unknown ranks above lowered.
- pincheck._cap finds no cap file for an agent whose model the catalog lacks while the main model is known, so the pin card uses the no-source sentence. Same as known agent models that differ from main's.
follow-ups:
- Owner: one phrasing for agent no-model text? The rule reason says "can't tell which model {agent} runs on", the pin strings say "doesn't know the agent's model".

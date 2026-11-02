### F-0fa8 A top-level effort cap lowers the main effort row with no model known (#91)
status: shipped
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: a8923da7cd4dd305b516b0056ef9423166cb1ee7 (branch fix/91-cap-with-no-model, merged into development)
summary: With no main model, project high under a user cap of low now shows Lowered at low on the trail and the Settings page, matching limits_for.
decisions:
- New rule effort-lowered-by-cap-model-unknown (when model_unknown, computed cap, layers env to user, no default) instead of rewording effort-lowered-by-cap, because the old reason names {model} and the no-model case needs its own caveat about per-model caps.
- _computed_becomes computes the cap before the model lookup; _condition_matches blocks any other computed-cap condition when the model is unknown, so effort-lowered-by-cap and agent-effort-lowered-by-cap answer as before.
- Agent rows with an unknown model stay uncapped (out of #91 scope); flagged as a follow-up.
- verified_on on the new rule copies 2.1.302 and October 29 from the sibling rules, because the schema requires it and the reused quotes were checked then.
- Removed the Settings warning's nomodel branch and string ed_warn_nomodel_cap_t; the case can't occur now, and the row shows the Stage 6 cap warning with Start with the cap.
rejected:
- Rewording effort-lowered-by-cap to drop {model}, because it changes known-model copy and loses the model name.
- Applying the cap to agent rows too, because it is outside the issue's done-when.
files: dashboard/resolve.py, dashboard/rules.json, dashboard/api_edit.py, dashboard/static/js/edit_review.js, dashboard/static/strings.json, docs/rules-reference.md, tests/test_resolve.py, tests/test_api_edit.py, tests/js/edit_card_checks.mjs, tests/e2e_checks/rules.json, plus 6 fixture folders under tests/fixtures/resolution/
gotchas:
- A new rule changes the All and Documented counts in tests/e2e_checks/rules.json and needs docs/rules-reference.md regenerated.
- pin-view.js picks the cap sentence by rule_id suffix lowered-by-cap and renders a null model as Unknown, so a no-model lowered pin reads "caps Unknown at low".
follow-ups:
- pin-view.js wording for a no-model lowered effort pin (needs tech-writer copy).
- Agent effort rows with an unknown model under a top-level cap.
- HiveMind apply deferred, because the inbox also holds the #104 lead's proposals and apply clears the whole inbox.

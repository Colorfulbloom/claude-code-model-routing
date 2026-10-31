### F-e861 Effort resolution, Lowered and Invalid, modelSettings matching (#7, #8, #9)
status: shipped
kind: code
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: d628b3580c0391bb12a713d92f18a57c70cfb082 (branch discovery/effort-and-model-settings, merged into development)
summary: Schema v3 (model catalog, {"from"} model matching, combine/value_order, computed becomes), 14 new rules and 1 changed, 9 experiment records from 87 harness cases on 2.1.302, 12 fixtures, harness prompt/text_reply/transcript support.
decisions:
- Verifier fix round: harness guard tightened, schema checker stricter, a levels-table quote on every catalog entry with effort levels; full suite 584 tests OK.
- Model catalog lives in rules.json (release order, aliases, effort levels, default) so "this model and later" and fallback are data, not code.
- combine is a required rule field (highest_layer, or lowest_value with value_order); maxEffortLevel and the per-model cap use lowest_value.
- Lowered uses becomes {"computed": "cap"|"fallback"}; the condition matches only when the value is above the cap or missing from the model's levels.
- An agent with no effort resolves effort for its own model (tested), not the session's level; docs/model-routing-reference.md still says "session's effort".
- Harness prompt allowlist is only "say hi" and "/effort status"; no env or args allowlist additions were needed.
rejected:
- A name_form condition field for alias vs canonical modelSettings entries: deferred to #5 and #16 (owner approved October 29); the reason text and catalog aliases cover it for now.
- A trailing "+" on model ids for "and later": an object is stricter and clearer.
files: dashboard/rules_schema.py, dashboard/rules.json, dashboard/experiments/2026-10-29-agent-effort.json, dashboard/experiments/2026-10-29-effort-auto.json, dashboard/experiments/2026-10-29-effort-cap-transcript.json, dashboard/experiments/2026-10-29-effort-fallback-levels.json, dashboard/experiments/2026-10-29-effort-invalid-values.json, dashboard/experiments/2026-10-29-effort-status-session.json, dashboard/experiments/2026-10-29-effort-user-key-by-model.json, dashboard/experiments/2026-10-29-model-settings-max-effort.json, dashboard/experiments/2026-10-29-model-settings-name-matching.json, dashboard/experiments/harness/runcase.py, dashboard/experiments/harness/fakeapi.py, dashboard/experiments/harness/cases-effort-sources.json, dashboard/experiments/harness/cases-effort-lowered-invalid.json, dashboard/experiments/harness/cases-model-settings.json, dashboard/experiments/harness/results-2026-10-29-effort.jsonl, tests/test_rules_schema.py, tests/test_harness_guard.py, tests/fixtures/resolution
gotchas:
- `claude -p "/effort status"` prints the status line with no API call, so the harness can record it.
- On 2.1.302, /effort status with CLAUDE_CODE_EFFORT_LEVEL=auto prints "auto (currently high)" while no level is sent.
- Invalid settings values (max, auto, unknown) print no warning on stderr in -p mode.
follow-ups:
- Ticket comments for #7, #8 and #9 drafted in the session scratchpad, not posted; #7, #8 and #9 moved to Review.
- Docs ticket for the agent-without-effort line drafted, not filed.
- name_form condition field: #5 and #16.
- Fix the docs/model-routing-reference.md line on agents without effort.
- Managed settings and the interactive Settings Warning remain untested.

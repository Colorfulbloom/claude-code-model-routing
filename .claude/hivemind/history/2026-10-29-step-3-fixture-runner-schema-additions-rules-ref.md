### F-9fdd Step 3: fixture runner, schema additions, rules reference page (#5, #15, #14)
status: shipped
kind: code
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: 61b1e07c00e265c1ab1ea8b4ff90b3f71208fadf (branch feature/step-3, merged into development)
summary: First resolver dashboard/resolve.py runs all 46 fixtures green; schema v3 gained variables, via, if_set, range with int becomes, ceiling combine, name_form and reader_rejected_untested; 2 new rules (43 total); generated docs/rules-reference.md with placeholder copy; suite 985 OK (2 skipped) after the verifier fix round. Stopped at the 400K budget before the tech-writer pass.
decisions:
- Variable-to-layer mapping lives in rules.json `variables` (optional top level, schema stays v3); list order is precedence inside one layer, which is what makes FORCE_PROMPT_CACHING_5M beat CLAUDE_CODE_PROMPT_CACHE_TTL.
- `via` = the candidate came through that variable; `if_set` = a gate on variables being set, needed for CLAUDE_CODE_SUBAGENT_MODEL_FORCE, which is a switch and never a candidate.
- Statuses come from votes: each rule votes its first matching condition; invalid > ignored exclude; the row's order rules pick the winner; winner status unknown > lowered > default > in_effect; the rest overridden.
- Comparison: per row the fixture names, one-to-one pairing, expected fields must equal, runner may add fields; rows not named are not checked; rule_ids must appear (the winner also carries the row's order rules).
- Fixture convention: shell env file session.json:shell_env, flags session.json:flags, modelSettings entries use the row key and scope plus `path`. 18 expected.json files normalized, format only.
- A raised clamp (env below 100000) shows In effect with becomes 100000; the top clamp shows Lowered. No eighth status word.
- New rule auto-compact-window-default from a1 and a15: Opus 5.5 default 1000000, other models Unknown. The a15 fixture exposed the gap.
- "missing closing fence" counts as parse_error (agent-files f1); untested reader kinds give Unknown via new rule agent-file-reader-rejected-untested (assumed).
rejected:
- Subset matching with no row exactness: too weak, it misses extra entries.
- Rule-level forcing that swaps the layer order: within-layer variable rank plus if_set covers both force variables with less schema.
- Bending a fixture to pass: the a15 fixture keeps the record's 1m and a rule was added instead.
files: dashboard/resolve.py, dashboard/rules.json, dashboard/rules_schema.py, dashboard/reference_page.py, dashboard/reference_copy.md, docs/rules-reference.md, tests/test_resolve.py, tests/test_rules_schema.py, tests/test_reference_page.py, tests/fixtures/resolution
gotchas:
- The {winner} reason slot renders the source, so "{agent} runs on {winner}" reads as a file path; three reasons need rewording (subagent-model-order, subagent-model-force, agent-effort-order).
- agent-file-location-order's reason renders "beats ." when the winner has no loser.
- docs/rules-reference.md is generated; rerun dashboard/reference_page.py after any rules.json change or test_page_matches_render fails.
follow-ups:
- Done in round 2: tech-writer copy applied to dashboard/reference_copy.md, 8 reasons reworded, page regenerated; #5, #14, #15 in Review; comments drafted in the session scratchpad, not posted. Owner accepted the 18 fixture normalizations.
- FORCE_PROMPT_CACHING_5M (and any fixed-value variable) counts when set to any non-empty value, "0" included. Assumed, not tested; needs a harness case in throwaway folders.
- Reason attribution: the entry's reason comes from the first rule in rules.json order that voted its status, so the clamp sentence (auto-compact-window-values) and subagent-model-force's reason never show on the entries they describe. Prefer a voter whose condition carries becomes, via or if_set.
- CLAUDE_CODE_SUBAGENT_MODEL_FORCE set alone isn't covered: per the docs the frontmatter model is ignored and the agent runs on the main model, but the rules show the frontmatter In effect.
- Same-name tie rows show Unknown with subagent-model-order's reason, which reads wrong.
- Open copy questions: which managed sources the dashboard reads, how it gets --settings content, and which transcript field it reads (tech-writer suggests params.output_config.effort).
- Verifier fix round: overridden entries explain with the row's order rule, winners with their most specific voter; agent effort judged by the agent's model (agent-effort-user-settings-opus-5-5); agent auto-compact follows sub-agents#subagent-auto-compact-window (values rule, ceiling against the session window, Unknown when that window is unknown); unreadable agents' value rows show Unknown; compare checks per-entry rule_ids, rule_id and reason; every default has a rule and a clean reason (test); home guard covers pathlib, lstat, access and symlinks; schema never raises on bad key or scope; model_unknown when case; anchor sub-agents#supported-frontmatter-fields; live anchor test behind MR_DOCS_LIVE=1. 55 rules, 66 fixtures.
- Open: an agent on Haiku 4.5 with a level set shows In effect (no agent no-effort-support rule or record); clamps ignore the model's context window until the catalog has one (phase 1); the docs cap every window at the context window, not only clamps; ANTHROPIC_DEFAULT_MODEL isn't in variables; the agent auto-compact row matches modelSettings by the agent's model while its default goes by the main model (confirm); an empty CLAUDE_CODE_AUTO_COMPACT_WINDOW renders "to ." in auto-compact-window-values (no fixture yet); _drop_shadowed (a vote whose if_set is a proper superset replaces another) is a runner rule, not data.
- CONSOLIDATION skipped twice (budget); the coordinator runs it in a separate dispatch after the merge, including the T-7629 count update (902 tests, about 140 to 156 seconds).

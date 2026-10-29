### F-775c Settings layer order per dashboard key (#6)
status: in-progress
kind: code
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: pending (branch discovery/settings-layer-order)
summary: Discovery #6. Ten rules in dashboard/rules.json give each dashboard key its layer order, backed by 36 harness cases on 2.1.302 and eleven fixture folders.
decisions:
- Schema gained a flag layer (--model, --effort, --autocompact), separate from cli (--settings), because --settings ranks below ANTHROPIC_MODEL while --model ranks above it. Owner approved.
- The env layer is the process environment after settings env blocks overwrite the shell; the resolver works it out first (rule env-block-order) and then uses it in the model order. No per-variable rules. Owner approved.
- ENABLE_PROMPT_CACHING_1H and ANTHROPIC_DEFAULT_MODEL count at the default layer, because both rank below every file.
- The seed effortLevel rule now carries the full effort order, so both effortLevel rules agree.
- Fixtures are folders with config/, project/, session.json and expected.json under tests/fixtures/resolution/, with no runner; #5 builds it. session.json was added for the shell env, flags and --settings, which the #5 layout did not cover.
- Experiments use a fake API on 127.0.0.1 with a fake key; the harness refuses real keys, base URLs and endpoint-changing settings.
rejected:
- One cli layer for both --settings and session flags: the model order can't be written with it.
- Per-variable rules such as env.ANTHROPIC_MODEL: the owner chose one env layer resolved first.
- Testing managed settings: writing /Library/Application Support/ClaudeCode needs admin rights, so managed positions come from the docs.
files: dashboard/rules.json, dashboard/rules_schema.py, tests/test_rules_schema.py, dashboard/experiments/, dashboard/experiments/harness/, tests/fixtures/resolution/
gotchas:
- A 5m prompt cache result looks the same as the default, because the 5 minute lifetime sends no ttl field.
- autoCompactWindow never appears in the API request, so the harness can't test it.
- Doc quotes in rules.json keep the docs' own backticks and drop only link markup; every quote matches the Markdown source exactly.
- CLAUDE_CODE_SUBAGENT_MODEL_FORCE is its own Documented rule (subagent-model-force), because a condition can't depend on another variable or carry its own confidence.
follow-ups:
- Answered: --effort beats a managed effortLevel. model-config#set-the-effort-level says "users can still change the level with `/effort` or `--effort`", so flag sits above managed (comment-7 for #7).
- The schema has no combine mode; "lowest cap wins" for maxEffortLevel lives only in the reason text (#8).
- #5 builds the fixture runner and needs the variable-to-layer mapping from the fixtures' via fields (comment-5).
- modelSettings.<model>.autoCompactWindow and .maxEffortLevel are not covered yet (#9).
- When the Claude Desktop app or a self-hosted environment runner starts the session, its launch environment beats settings env blocks (settings-reference#how-env-values-interact-with-your-shell). No rule covers it.
- Project and local settings can't set some variables in their env blocks (settings-reference#variables-claude-code-ignores-in-env). env-block-order has no conditions for them.
- Invalid CLAUDE_CODE_AUTO_COMPACT_WINDOW values are ignored (model-config#claude_code_auto_compact_window-values). auto-compact-window-order has no conditions for them.

### F-36e5 Discovery step 2: cache, auto-compact, agent files (#10-#13) and #26 docs fix
status: in-progress
kind: code
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: pending (branch discovery/step-2)
summary: 16 new and 4 changed rules (41 total) from 44 harness cases on 2.1.302 in three records; schema gained a plugin layer, combine all, condition plans/when/default_value and an other_file slot; 15 fixtures; agent_fields.json and a strict one-level frontmatter reader; #26 applied with a hook test; verifier fix round tightened the frontmatter guard and made the reader linear; suite 723 OK.
decisions:
- Owner, October 29: plan subscription makes billing-dependent cache cells Unknown, reason "one hour within plan usage, five minutes once usage credits start" (main default and an agent's 1h); plan values subscription, api_key, cloud_provider, missing shows Unknown; the harness's requested-TTL record (k12) stands in for the real-account claude -p check.
- /autocompact with no argument is the observable for the main window; the agent frontmatter window stays Assumed (env beats it per docs; 2.1.302 code passes it as a ceiling).
- Across settings files the higher file wins for the auto-compact window whether it sets a per-model or a top-level value (a4, a5); this settles the #9 rule's Assumed cross-file order.
- Cache steps 2 to 4 live in the two order rules (agent layer added to the subagent rule), steps 1, 5 and 6 are their own rules per bucket. Values other than 5m and 1h are Invalid; they are case sensitive.
- agentFile and rulesFile are file-kind keys; same-name files in one tree are Unknown naming both files; .md.bak never loads.
- The strict reader rejects shapes Claude Code tolerates (unclosed [, a second colon), so those show Unknown instead of a guess.
- Schema stays at version 3: every addition is optional or a new enum value.
rejected:
- A compaction probe (fake usage plus a call to a missing tool): lowered windows never triggered compaction in -p, only the ~1M limit did.
- A real claude -p check on the owner's account: it would read and write the real ~/.claude.
- Numeric range conditions for autoCompactWindow: out of scope; the values rule lists only abc and empty as Ignored and gives the clamping in its reason.
files: dashboard/rules.json, dashboard/rules_schema.py, dashboard/agent_fields.json, dashboard/agent_frontmatter.py, dashboard/experiments/2026-10-29-prompt-cache-sources.json, dashboard/experiments/2026-10-29-auto-compact-window.json, dashboard/experiments/2026-10-29-agent-files.json, dashboard/experiments/harness/runcase.py, dashboard/experiments/harness/README.md, dashboard/experiments/harness/cases-cache-ttl-sources.json, dashboard/experiments/harness/cases-auto-compact.json, dashboard/experiments/harness/cases-agent-files.json, dashboard/experiments/harness/results-step2-cache.jsonl, dashboard/experiments/harness/results-step2-compact.jsonl, dashboard/experiments/harness/results-step2-agents.jsonl, tests/test_rules_schema.py, tests/test_agent_frontmatter.py, tests/test_harness_guard.py, tests/test_hook_roster.py, tests/fixtures/resolution, hooks/require-agent-model.py, docs/model-routing-reference.md, rules/model-routing.md, skills/route-project/SKILL.md, skills/setup-model-routing/SKILL.md
gotchas:
- `gh issue view N --comments` prints nothing in this shell; use --json body,comments.
- /autocompact labels an --autocompact flag window "from settings".
- Claude Code's agent frontmatter parser is lenient: an unclosed [ and a second colon still load; a repeated key loads with the last value.
- The docs-quote test in tests/test_agent_frontmatter.py skips unless MR_SUBAGENT_DOCS points at a local copy of sub-agents.md.
follow-ups:
- Owner reruns install.py after the merge (#26).
- Numeric range conditions for the resolver (#5).
- Ticket comments drafted in the session scratchpad, not posted; #10-#13 and #26 moved to Review.

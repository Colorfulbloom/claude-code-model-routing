### F-cd23 HiveMind Phase 1: shared memory for all agents
status: shipped
kind: code
dates: 2026-10-20 .. 2026-10-20
refs:
  commit: 2c330118d377760ef454c89b1772cffb8e07224c (feature/hivemind, merged into development)
summary: Shared memory for every agent in a project. A start hook injects compact one-line facts for each agent type within a per-type budget, once per agent; a stop hook saves each agent's HIVEMIND block to the inbox after a secret scan; a guard hook blocks every agent except deep-reasoner and the main session from writing the store; a session-start status line flags problems. deep-reasoner runs CONSOLIDATION (prep, decide, apply, check) at the end of each feature. Installed globally by install.py; each project opts in with hivemind_lib.py init.
decisions:
- Content fingerprints, not git history, decide when a fact is suspect (git misses uncommitted edits and breaks on squash merges and shallow clones).
- Random fact ids (T-7f3a) so parallel branches cannot collide.
- Inbox gitignored; accepted facts are committed and reviewed in each feature's diff.
- Expiry after 28 active days unused; active days are the union of local agent-run dates and git commit dates, kept in a local gitignored file so the working tree does not change daily.
- Read-only agents propose through their report and stay read-only.
- deep-reasoner's own project memory moved into HiveMind and was turned off; designer keeps its cross-project memory.
- Stores are opt-in per project; hooks install for every project. Worktree agents share the main checkout's store.
- Status line shows on startup, resume, clear and compact through its own entry, so the existing startup hook stays byte-identical.
- No repeated loading: inject once per agent id (resume re-fires the start hook), compact lines only, per-type budgets, no text at all for agents with no relevant facts, main session never gets facts.
rejected:
- Blocking writes by memory text alone (owner rule: enforcement by hooks).
- Calendar-day expiry.
- A committed active-days file (daily diff noise).
files: .claude/hivemind/.gitignore, .claude/hivemind/INDEX.md, .claude/hivemind/archive/.gitkeep, .claude/hivemind/config.json, .claude/hivemind/inbox/.gitignore, .claude/hivemind/tallies.json, .claude/hivemind/topics/dead-ends.md, .claude/hivemind/topics/failed-briefs.md, .claude/hivemind/topics/testing.md, .claude/hivemind/topics/token-tallies.md, .claude/rules/project-facts.md, README.md, agents/deep-reasoner.md, agents/designer.md, agents/fast-worker.md, agents/judge.md, agents/scout.md, agents/verifier.md, docs/hivemind/history-backfill-2026-10-20.md, docs/model-routing-reference.md, hooks/hivemind-capture.py, hooks/hivemind-guard.py, hooks/hivemind-inject.py, hooks/hivemind_lib.py, install.py, rules/model-routing.md, skills/setup-model-routing/SKILL.md, tests/helpers.py, tests/test_features.py, tests/test_hivemind.py (+1 more)
gotchas:
- Calibration on Claude Code 2.1.305: resume fires SubagentStart and SubagentStop again; agents that end with a SubagentHandback tool call send no last_assistant_message, so the block is read from the transcript; SubagentHandback appeared only in auto mode; PreToolUse from subagents carries agent_type.
- Token tallies come from transcripts (the stop hook reports no token count): the harness figure equals the last message's input plus cache plus its output.
- Verifier found a guard bypass through capitalization on case-insensitive macOS; fixed with case-insensitive and inode comparison.
- Bash redirects can still bypass the guard; the regex secret scan has gaps; hook inputs verified on 2.1.305 only.
- The first CONSOLIDATION caught a stale migrated note (the test temp folder no longer has to exist) and replaced it.
facts: T-7629, T-5589, T-c826, T-baa7, T-6bd7
follow-ups:
- Owner decision on promoting T-7629, T-5589 and T-c826 to project-facts.md.
- Phase 2: feature history. Later: separate HiveMind repository, with HiveMind as an optional installer choice.

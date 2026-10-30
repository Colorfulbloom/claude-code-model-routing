### F-8cf3 HiveMind consolidation after discovery steps 2 and 3
status: shipped
kind: content
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: c57acf37c8c605cde9860b7121c08013bf7e7427 (branch chore/hivemind-consolidation, merged into development)
  file: .claude/hivemind/topics/testing.md
  file: .claude/hivemind/topics/dead-ends.md
summary: Folded 126 inbox run files (30 proposals, 11 contradictions) from F-775c, F-e861, F-36e5 and F-9fdd into the testing and dead-ends topics.
decisions:
- T-7629 rewritten in place (id kept, promote set to proposed) because project-facts.md cites it; the full suite ran alone at 72a81f7: 986 tests, 2 skipped, 138.5 s.
- Gotchas that describe an approach that fails went to dead-ends, so testing stays under its 4KB limit without a config change.
- Retired T-6bd7 (2.1.305 behavior, never used) and T-91ac (2.1.306 sources, already encoded in RECENT_SOURCES) to make room.
- Harness checks use grep, never runbatch.py; network checks used curl and gh read-only.
rejected:
- Splitting testing into a testing-harness topic: needs a config.json topic and prefix, and shrinking was enough.
- Proposals for bugs already fixed in code (rules_schema TypeError, frontmatter_keys bypasses, quadratic _split_flow, env substring block, compare ignoring rule_id): code and tests carry them now.
- gh issue view --comments prints nothing in a non-TTY shell: did not reproduce (gh 2.102.0 printed both comments).
- Agent frontmatter leniency on 2.1.302: already recorded in dashboard/experiments/2026-10-29-agent-files.json.
files: .claude/hivemind/topics/testing.md, .claude/hivemind/topics/dead-ends.md, .claude/hivemind/archive/testing.md, .claude/hivemind/tallies.json, .claude/hivemind/topics/token-tallies.md, .claude/hivemind/INDEX.md
gotchas:
- Every agent files a T-7629 CONTRADICTS when the count grows; the fact now says the count grows and measured holds the latest run.
facts: T-7629, T-07ef, D-c684, D-1534, D-6bed, D-b739
follow-ups:
- Owner: approve the project-facts.md lines proposed for T-7629, T-07ef, D-1534 and D-b739.

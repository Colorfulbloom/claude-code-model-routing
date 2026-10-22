### F-1906 HiveMind tally samples per resumed round
status: in-progress
kind: code
dates: 2026-10-21 .. 2026-10-21
refs:
  commit: pending (branch development)
summary: A subagent resumed with SendMessage records one tally sample per round, found from its captures and real briefs, and later rounds go to a separate <kind>+resumed row.
decisions:
- First pass (9c7985a) split rounds at a new promptId. A verifier found it unsound: promptId follows the parent prompt, so 44 real resumes kept it and 173 nudges, task notifications and worker hand-backs changed it.
- Rounds are anchored to captures. SubagentStop fires at each stop before the wake row lands. Each capture stores inbox/rounds/<agent_id>.json (transcript, rows read, round, start row, kind), and the next capture scans only the rows after it.
- A new round starts only at a real brief after a stop: origin.kind coordinator or human, or peer from an agent the transcript did not launch (toolUseResult.agentId) whose body is not a hand-back. Without state, capture scans the whole transcript for briefs (anchor transcript).
- prev comes from the transcript at the round's start row, not from stored figures, because a plain-text stop's final row can land after the capture reads.
- A later capture of the same round (after a nudge, a notification or a worker's report woke the agent) replaces that round's sample. Only run files with tally.anchor replace; older formats are skipped as duplicates.
- Round > 1 samples go to a <kind>+resumed row, and stored ones move there on apply, so resumes never move fresh-dispatch medians.
- 9c7985a-format files with round > 1 and no anchor are skipped as "unanchored round"; their boundary came from the wrong rule.
- A resumed round with no Kind: line inherits the previous round's kind and files as <previous kind>+resumed. Owner decision, 2026-10-22: inherit instead of untagged (the first pass had left it untagged). Round 1 with no Kind: line stays untagged; a brief with its own Kind: line takes that kind. On real data 264 of 274 coordinator follow-ups have no Kind: line.
- apply deletes round state files older than 30 days.
rejected:
- promptId boundaries: wrong in both directions on real data.
- Treating a lead's own workers' hand-backs as rounds: they wake the lead inside one feature and would split its cost.
- Sample increase over a stored cumulative figure: off by the late final row; the transcript at the brief row is exact.
- Previous total from tallies.json samples, and latest-wins per agent_id: as in the first pass.
files: hooks/hivemind_lib.py, tests/test_hivemind.py, tests/fixtures/rounds/, README.md, docs/model-routing-reference.md, .claude/hivemind/topics/testing.md
gotchas:
- Run files sort by name; two captures of one agent in the same second sort the -2 suffix first. Not seen in practice.
- If a capture runs before a plain-text final row is written and the next stop is a real brief, the stored round-1 sample stays short by that final message (about 300 tokens on a 201K run); only a same-round recapture corrects it.
- Old-format waiting inbox files of a resumed agent carry the whole run under the first round's kind; apply skips them when the agent already has a sample.
facts: T-2160, T-7629
follow-ups:
- Install the fix into ~/.claude/hooks after the owner's go.

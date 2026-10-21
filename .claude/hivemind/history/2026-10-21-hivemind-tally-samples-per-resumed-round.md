### F-1906 HiveMind tally samples per resumed round
status: in-progress
kind: code
dates: 2026-10-21 .. 2026-10-21
refs:
  commit: pending (branch development)
summary: A subagent resumed with SendMessage now records one tally sample per round, the increase over the round before, under that round's Kind, instead of overwriting its first sample with the cumulative total.
decisions:
- Rounds come from the transcript: a user prompt row with a new promptId after the agent stopped (last assistant row made no tool call or called SubagentHandback). A prompt that arrives mid-run stays in its round. No promptIds means one round, as before.
- Capture keeps the cumulative figures in tally and adds round and prev (figures at the end of the round before); apply computes the increase in the configured metric.
- prev is read from the transcript, not from tallies.json, so a round still gets its increase after an apply in between, or when the earlier round's sample was trimmed or never captured.
- A sample is keyed by agent_id and round and never replaced; a repeat is skipped as a duplicate. Old samples without round count as round 1. A sample gains round only above 1, so fresh samples and old tallies.json files are unchanged.
- A later round with no increase (compaction can shrink the final context), no prev or a bad round gives no sample; apply prints the count and reasons on stderr.
rejected:
- Previous total from tallies.json samples: needs a cumulative field on every sample and breaks when the earlier sample is trimmed by tally_samples_max or never captured.
- Keeping latest-wins dedupe per agent_id: that is the bug.
- Inheriting the first round's Kind when a resume prompt has none: the brief asked for the existing untagged fallback.
files: hooks/hivemind_lib.py, tests/test_hivemind.py, README.md, docs/model-routing-reference.md, .claude/hivemind/topics/testing.md, .claude/hivemind/topics/dead-ends.md
gotchas:
- An old-format run file (captured before this fix) of a resumed agent has no round and carries its first round's Kind; apply now skips it as a duplicate instead of overwriting, so that round gets no sample unless a lead adds it by hand.
- Kind is read from the first user row of the round; if a compaction summary row ever lands before the resume prompt, the round would be untagged. Not observed.
facts: T-2160, T-7629
follow-ups:
- Confirm on a live run that a prompt sent to a still-working agent is folded into its round as the code assumes.

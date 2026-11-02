### F-8e49 HiveMind tally rounds keep the later capture in one second
status: in-progress
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: pending (branch fix/tally-resumed-agents)
summary: Re-requested resumed-agent tally fix was already shipped (F-1906) and live; this closes its one open gap, where two captures of an agent in the same second let the earlier figure win.
decisions:
- Diagnosis: capture-anchored rounds, per-round Kind and increase over prev shipped in 0b75193 and deb3d7e, and the live ~/.claude/hooks/hivemind_lib.py equals development 6594de7 byte for byte. The brief came from a memory note last updated before that fix.
- Existing tests already cover the four requested scenarios (two Kinds, resume under one prompt, nudge, old tallies.json). They fail on f36fddb and on 9c7985a, checked in a scratch copy.
- add_tally_samples folds runs sorted by capture_order (run time, then tally rows read) instead of file-name order, because X-2.json sorts before X.json and the earlier capture replaced the later one.
- Verifier pair (Opus and Fable) not dispatched: the change is a stable sort plus one test, which the lead's subset and full-suite runs cover.
rejected:
- Rebuilding round anchoring from scratch: already shipped and tested.
- Storing rows on each sample and replacing only when larger: changes the tallies.json sample schema for the same result as a sort.
files: hooks/hivemind_lib.py, tests/test_hivemind.py
gotchas:
- Sorting by run time also reorders runs of different agents within one apply, which only changes which samples the per-row cap trims; time order matches name order apart from the same-second suffix case.
follow-ups:
- Owner: copy hooks/hivemind_lib.py to ~/.claude/hooks after merge.
- Owner: the memory note tally-resumed-agent-overwrite.md is stale; it should say the fix shipped in F-1906.

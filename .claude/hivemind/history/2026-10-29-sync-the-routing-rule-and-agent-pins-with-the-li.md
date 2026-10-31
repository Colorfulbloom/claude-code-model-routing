### F-14f0 Sync the routing rule and agent pins with the live setup (#28)
status: shipped
kind: code
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: 2709a5c540337b3df0bc10508de7e62cc82213b1
summary: rules/model-routing.md now matches the installed copy (October 28 changes), agent defaults ship the installed pins, and a --reset reinstall left the live setup unchanged (plain dry run 0 replaced, 19 unchanged).
decisions:
- Ship the owner's installed pins as repo defaults, so the rule's verifier line and agents/verifier.md agree and a fresh install gets the setup the owner runs.
- Reinstall with --reset, because the saved choices from October 22 would otherwise restore the old designer, scout and verifier pins.
rejected:
- A plain --yes reinstall, because it reads the stale saved choices.
files: rules/model-routing.md, agents/fast-worker.md, agents/judge.md, agents/scout.md, agents/verifier.md, README.md, docs/model-routing-reference.md, tests/test_features.py, tests/test_picker.py
gotchas:
- install.py prefers ~/.claude/model-routing-choices.json over repo defaults, so edits made directly in ~/.claude must reach the repo and the choices file, or a reinstall rolls them back.
follow-ups:
- Drop the fast-worker effort trial line after November 4, once the owner picks an effort.

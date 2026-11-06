### F-b0ef Tally rows get their own expiry window, with a sample archive
status: shipped
kind: code
dates: 2026-11-04 .. 2026-11-04
refs:
  commit: c7af0275dd1fc54ff7ade89e892afc2bcec001a0 (branch chore/trim-token-tallies, merged into development)
summary: New tally_expiry_active_days (defaults to expiry_active_days) trims token-tallies.md without touching fact expiry; expired rows keep their summary in archive/token-tallies.md and their raw samples in archive/tallies.json. This store sets 14; routing-dashboard 0.1.6, hivemind 0.1.2.
decisions:
- Owner picked a separate tally window over lowering expiry_active_days (would expire facts sooner) or raising tally_topic_max_bytes (only headroom).
- Owner asked that expired tally data be archived, not lost, so raw samples go to archive/tallies.json; a repeat expiry appends samples.
- The key stays out of DEFAULT_CONFIG so it follows each store's own expiry_active_days.
files: hooks/hivemind_lib.py, .claude/hivemind/config.json, tests/test_hivemind.py, README.md, plugins/routing-dashboard/.claude-plugin/plugin.json, plugins/hivemind/.claude-plugin/plugin.json, plugins/routing-dashboard/payload, plugins/hivemind/payload
follow-ups:
- The next consolidation apply does the actual trim, about 100 rows expected.

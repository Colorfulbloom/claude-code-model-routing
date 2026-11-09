### F-7098 Bar Tab M1 data core: ingest, store, backup, prices, first run
status: in-progress
kind: code
dates: 2026-11-08 .. 2026-11-08
refs:
  commit: pending (branch feature/bartab-m1)
summary: Ported the Batch A core, built the SQLite store with 5 migrations, the single writer and ingest, backups, the history status, the price feed and the oracle recorder, and wired the M1 contract into first run, the footer, the notice and More. Demo totals equal the old app.
decisions:
- Batch B (resolve, collect, rules schema) moved to M4, agent front matter and agent_md to M6 (owner)
- Everything Bar Tab writes in the shared folder goes under <config>/routing-dashboard/bartab/ behind a path guard and writer.lock; M1 has no real default paths
- ingest.state reports the first full ingest only; later failures go to history.pass_error, because the M0 page shows first run whenever state isn't done
- Cache read check is a 1 to 12 percent band (plan said 8 to 12); LiteLLM has opus-5-5 and sonnet-5-5 at 5 percent and fable-5-1 at 2.5 percent
- modelPricing read from managed sources only, per Claude Code's settings reference; dormant in M1. Override rows need all four rates 0 to 10000, take the multiplier and skip fast and US surcharges (docs)
- Fix round: the price feed starts from a writer on_ready callback after migrate; run_once backs off 15 minutes on a raise and waits 24 hours only after both jobs are submitted
- Fix round: pass_error since lives in the writer snapshot and holds through code changes until the error clears
- Fix round: id-less request keys carry the file id, matching the old dedupe that keeps every id-less record; no migration for old n|offset keys because M1 is unreleased
- Fix round: reads of a store whose user_version is behind get an empty in-memory store, so /api/app never 500s mid-migration
- Old "all" scope is every folder, so the new "all" matches it
- minute_usage keys carry speed, service_tier, inference_geo and tier, so query-time pricing keeps old modifiers and tiers
- store_newer added as a sixth first-run code (owner)
rejected:
- Literal "about 10 percent" cache ratio, which would reject today's real LiteLLM file
- Assuming one session per message key in minute rebuilds, because resumed sessions copy message ids
- Raising the global Playwright timeout for the Linux sheet failure; only that test got 240 s like the hover tests
files: app/server (18 new modules, migrations 0001-0005, data/), app/oracle/record.py, app/fixtures/oracle/demo/, app/web/src (first run, footer, notice, More history, picker placeholder), app/web/e2e/firstrun-real.spec.ts, app/web/e2e/m1.spec.ts, docs/rebuild/planning/m1-build.md, docs/design/redesign-a/components.md
gotchas:
- sqlite conn.backup() hangs while the source connection has an open write transaction (U-638e)
- uvw --directory app runs from app/, so name test files relative to it (I-376d)
- Two workers sharing files: one ran ruff format . (write form) over the other's edits; edits survived, but give parallel workers disjoint files
- A worker run reformatted app/web/src/styles/tokens.css; it was restored from HEAD, because it must stay a byte copy
facts: I-376d, U-638e
follow-ups:
- Push and confirm CI on Linux (launcher DISPLAY fix and the sheet timeout)
- Add an upload-artifact step on failure to the workflow (needs a pinned SHA)
- Owner calls on the picker modal vs the popover board, sidebar icon glyphs, locked gate button weight, and the notice date format when not today

# Live flow fixtures

`build_flow.py <out_dir> <scenario>` builds the demo set into `out_dir` (through `tests/fixtures/demo/build_demo.py`), then adds one newer session to the Tidewater reporting transcript folder. That session is the Live page's latest, so the dispatch canvas has something to draw. Everything is made up and nothing is committed except the builder. The same arguments give the same bytes (seed 71, every time an offset from October 30, 2026, 22:10 UTC).

The built `session.json` gets the scenario's clock in `now`. `flow.json` beside it lists the clock, the session id and each run (agent type, agent id, whether a link row exists, rounds).

| Scenario | Clock (UTC) | Shape |
|---|---|---|
| `busy` | 22:40:00 | Main session on Opus, a deep-reasoner, two scouts launched together (done), two fast-workers launched together (done), a judge (working), and a tech-writer that finished, was resumed by the coordinator at 22:39:12 and is mid round 2 |
| `many` | 23:10:00 | A deep-reasoner and a designer with 20 workers between them in groups of 2 and 3 (most done, three working), plus a tech-writer (done) and a verifier (working). The deep-reasoner's first scout is resumed in round 2 by a peer message from the designer |
| `empty` | 22:18:00 | The main session only |
| `unlinked` | 22:40:00 | `busy` plus a third scout, working, whose dispatcher wrote no link row (a foreground child) |

Row shapes follow `tests/fixtures/rounds/`. A dispatch link is a user row in the dispatcher's file with `toolUseResult {"status": "async_launched", "agentId": <child id>}`. A resume is a user row in the child's file with `origin {"kind": "coordinator"}`. A child that is done ends on an `end_turn` text row or a `SubagentHandback` call. Models are all priced in `dashboard/rules.json`.

`tests/test_live_flow_e2e.py` is the opt-in browser test (`MR_E2E=1`) that serves each scenario with `--fixture`.

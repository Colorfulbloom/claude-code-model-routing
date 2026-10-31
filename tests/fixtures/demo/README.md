# Demo set

This folder holds made-up settings, agents and generated transcripts for the usage pages, tests and screenshots. Every name, path and value is invented.

## Build it

Run the build from the repo root.

    /usr/bin/python3 tests/fixtures/demo/build_demo.py <out_dir> [--now ISO] [--tz NAME]

The defaults are `--now 2026-10-30T18:00` and `--tz America/New_York`.

The build copies `config/`, `projects/`, `repo/` and `session.json` into `out_dir`, adds an empty `managed/` folder, and writes transcripts into `out_dir/config/projects/`. Transcripts are never committed, and the same arguments give the same bytes. A run on the set never reads the real managed folder, shell or `~/.claude`.

The built `session.json` is the committed one plus `now` (the demo clock, UTC with an offset) and `tz` (the zone name). A server started with `--fixture <out_dir>` reads both, so the set stays inside the usage windows instead of aging out on the real clock.

`build_demo.py` also writes `out_dir/truth.json`, an independent count of what it generated for the 30 days up to `--now`.

The paths committed in `config/routing-dashboard.json` are relative to the set. The build makes them absolute under `out_dir`.

`repo/` stands in for the repo the Installed files page compares `config/` with, so a run on the set reads no real file. Builder and reviewer in `repo/agents/` have other model and effort lines than the copies in `config/`. The saved choices in `config/model-routing-choices.json` give them back, so both still show Matches.

Serve a built set with `/usr/bin/python3 dashboard/server.py --fixture <out_dir>`. On the committed folder, `--fixture tests/fixtures/demo` shows every project as Folder not found, because a relative path resolves against `config/`, the folder that holds `routing-dashboard.json`, not against the set.

## Planted cases

Each row is a case planted on purpose, with where it lives and the screen it drives.

| Case | Where it is planted | Screen it drives |
| --- | --- | --- |
| Main-session effort has a winner and values that lost (Tidewater reporting) | `config/settings.json`, project `settings.json` and `settings.local.json` | Settings, Overview |
| October 29 case, a top-level `effortLevel` in the user file that Opus 5.5 ignores | `config/settings.json` | Settings, Needs attention |
| Main session set to xhigh and lowered to high (Matches pin, with the Lowered note) | `settings.local.json` env xhigh, Opus cap high | Overview, Settings |
| builder pinned to xhigh, env xhigh wins, Fable cap lowers it to medium (Pin overridden) | `config/agents/builder.md`, Tidewater `settings.local.json` and `settings.json` | Agents, Agent detail, Needs attention |
| reviewer pinned to high, env xhigh wins uncapped (Pin overridden) | `config/agents/reviewer.md`, Tidewater `settings.local.json` | Agents, Agent detail, Needs attention |
| scribe pinned to Haiku 4.5 at medium, runs on Haiku 5.5 at high (Differs from pin) | `config/agents/scribe.md`, generated transcripts | Agents, Agent detail, Needs attention |
| Per-model caps, Fable at medium, Opus at high, Sonnet uncapped | Tidewater `settings.json` `modelSettings` | Settings, Models |
| Main-session effort differs in Driftwood | Driftwood `settings.json` and `settings.local.json` | Overview (project switch) |
| Driftwood main model `claude-opus-6-preview` is made up, so it is Not priced | Driftwood `settings.local.json`, generated transcripts | Models, Overview |
| Invalid value and an unparsed project settings file | Driftwood `settings.json`, `settings.local.json` | Settings, Needs attention |
| Harbor Light has no `.claude` folder and no session today | `projects/harbor-light/`, generated transcripts | Empty and states |
| Saltmarsh has a `.claude` folder and no transcripts, "No usage yet" | `projects/saltmarsh/.claude/` | Empty and states |
| Lantern is listed but its folder does not exist, "Folder not found" | `config/routing-dashboard.json` | Empty and states |
| A transcript folder with no entry in the list (quarry-notes) | generated transcripts | All projects |
| A value from a settings `env` block | Tidewater `settings.local.json` | Settings |
| A secret-looking value in an `env` block, shown hidden | `config/settings.json` | Settings |
| A rules file in each scope | `config/rules/writing.md`, Tidewater `.claude/rules/review.md` | Rules, Installed files |
| 1-hour cache writes and thinking tokens | generated transcripts | Overview, Models |
| Rows that repeat a message id while the output grows | generated transcripts | Sessions, Session detail |
| Every row has `inference_geo` `global` | generated transcripts | Cost on every screen |
| Files older than 61 days | generated transcripts | Reader |
| Installed Claude Code is newer than the rules | `session.json` | Top bar, Settings, Rules reference |
| One installed agent differs and one is missing | `repo/`, `config/` | Installed files |

Across the listed projects with a folder, all seven status words and all three confidence words appear. A settings ticket that adds a case adds a row here.

## Tidewater reporting, default arguments

These figures cover the 30 days from October 1, 2026 at local midnight to `--now`. Cost uses standard list prices.

| Figure | Value |
| --- | --- |
| Input tokens | 5,987,439 |
| Output tokens | 3,317,776 |
| Cache read tokens | 89,076,369 |
| Cache write 5-minute tokens | 17,040,156 |
| Cache write 1-hour tokens | 1,827,034 |
| Thinking tokens | 999,663 |
| Requests | 3,259 |
| Subagent runs | 190 |
| Sessions | 53 |
| Cost | $319.62 |

`tests/test_demo.py` checks these figures against `truth.json`.

# M4 build plan, Bar Tab setup read side and To fix

Written by the lead (deep-reasoner) on November 9, 2026, on branch `feature/bartab-m4` from `7db2be8`, where M0 to M3 are committed. M3's CI was still running when this branch was cut. If it fails, the fixes land on `feature/bartab-m3` and are merged in here before task 0. It turns plan-a.md section 5, "M4. Setup read side and To fix", into ordered tasks. The designer reviews sections 5 and 9 before the UI build starts. Nothing is installed, started or committed until the owner says go.

Sources are plan-a.md (sections 2, 3, 4, 5, 6, 9 and 10), plan.md (sections 2, 3, 5, 6 and 7), m1-build.md (sections 2, 4 and 10), m2-build.md (sections 2, 7, 8 and 12), m3-build.md (sections 3 and 9 to 13), components.md (shared rules, entries 3, 12, 15, 16, 26, 32 and 33, "Differences resolved" and "Chosen state made canonical"), the `a-setup`, `a-setup-scopes`, `a-surface`, `a-surface-readonly`, `a-tofix`, `a-tofix-empty`, `a-agents`, `a-agent-inspector` and `a-agent-plugin` boards and their source in `docs/design/redesign-a/a2.js` and `agents.js`, research notes 18, 20, 22, 26-02, 26-03, 26-07 and 26-08, `~/.claude/designer/usability-for-apps.md`, the M3 code in `app/`, the old `dashboard/collect.py`, `resolve.py` and `api_settings.py`, and two scout inventories run on November 9.

## 1. What M4 delivers

Setup is the third thing the owner opens, after Live and Review. M4 builds its read side as direction A draws it, in the canonical look the M0 sheet set.

The owner opens Your setup and sees one row per part, ten in all. Each row says what runs, such as "Opus 5.5, high" or "6 agents", with a worded status. Flipping "Show where each comes from" adds a column per scope, or chips under each row at 375. Any row opens its surface page, a list on the left and an inspector on the right. The inspector says what runs, where it is set and on which line, which scope wins, and why, with how sure the dashboard is. A read-only item says who owns it and why it can't change here.

To fix lists only real problems, grouped as Couldn't read, Won't load and Not as set, then Can't tell and Notices, which are not counted. Each row names the thing and the problem, gives the cause with file and line, says what happens because of it, and offers one action. The sidebar and tab bar show the counted total.

The Agents page gets its setup half. Agent names open the inspector beside a narrowed table, plugin agents appear with the fields Claude Code ignores for them, and Live's Model check gets its "See why" link.

Everything runs on fixtures and the demo build. On real data the owner sees the same pages through the M2 preview, reading only what section 7 lists.

## 2. Decisions this plan makes

The designer and owner can push back on any of them. Items that need an owner answer are in section 11.

| Item | Pick | Why |
|---|---|---|
| Collector shape | One module per collector with `read(ctx) -> Collected`, `signature(ctx) -> str` and a `parts` list. `Collected` holds items, diagnostics (problem rows) and `unreadable[]` with a reason code per file. A reader never raises for a bad file. It returns what it could read | plan.md section 7, "Collector contract", and "Readers return partial results and never fail a page" |
| One read path | Every collector opens files through a new `read_scope.py`. It checks the path against the project's allowed roots after `realpath`, applies the size cap, reads one byte snapshot, retries once on a parse failure, and decodes UTF-8 strictly. A refusal is a reason code, never an exception | Section 7 needs one place that enforces the real-mode read list and one place a test can audit. 26-08 asks for one snapshot and one retry |
| Size cap | 1 MiB per file, 32 MiB for `~/.claude.json`, past which the file is Couldn't read with `too_large` | `collect.py` reads whole files with no cap (`collect.py:162`). 1 MiB matches the old MAX_FILE. `~/.claude.json` can be large and must still parse |
| Masking | Extend the ported `collect.mask` to research 26-07's rules (more secret words, GitHub, Slack, AWS and JWT value shapes, URL userinfo, secret-named flags in `args`). The old tests stay as they are and new cases are added | 26-07 lines 70 to 73. The old mask knows six words and two prefixes (`collect.py:33`, `:38`). Hooks, MCP env and headers are new places secrets live |
| Bodies | CLAUDE.md, rules files, SKILL.md and agent bodies are read in memory for imports, `paths` globs, line counts and front matter. No answer carries body text in M4 | The inspector needs facts about a file, not its text. M7 brings the editor, which is where text belongs. It keeps the setup answers small and the privacy line simple |
| Writable | Every item is `writable: false` in M4. Items M6 will make editable carry `read_only_reason: null`, and the page shows neither Edit nor a lock. Truly read-only items carry their reason code (managed, plugin, user or local MCP, command line, not visible) | A lock on a value that becomes editable two milestones later would teach the wrong thing. plan.md section 5 says a read-only item always gives its owner |
| Shell and command line | The Command line scope always reads "not visible here". Your shell keeps M2's behaviour for the model check (the server's environment at start, filtered to the rules variables), and the inspector says the value is what Bar Tab saw when it started. Question 9 asks the owner | plan.md section 5 says both read "not visible here". M2 already feeds the server's environment to the resolver (`main.py:117-126`), so dropping it now would change Live's Model check |
| Model check parity | `model_check.resolve_entries` gains `local_path` (the repo-root local file) and `plan` (from `routing-dashboard.json`), as the old `api_settings.resolved` passes (`api_settings.py:254-275`) | The M2 port leaves both out (`model_check.py:161-170`), so a worktree project misses its repo-root `settings.local.json` and an API-key plan reads as unset. The differential would fail on both |
| Managed `modelPricing` | The settings collector feeds the managed `modelPricing` layer to the price feed, which has been dormant since M1 | m1-build.md section 11 says the layer waits for the resolver, and Claude Code reads `modelPricing` from managed settings only |
| Refresh | `/api/setup`, `/api/setup/{part}` and `/api/problems` carry an etag over the collectors' signatures. The page refetches every 10 s while visible, as plan-a section 3 says. A signature is stat-only over the files and folders the last read touched. Nothing runs in the background, so no file is watched | plan-a section 3. plan.md says the server never watches `~/.claude.json`. Request-driven stat calls keep that true |
| Parts and items | Ten parts, as `a-setup` draws them. Settings (one item per key), Agents (per name), Instructions (per file in load order), Rules files (per file), Skills (per name), Hooks (per event, matcher and handler), Permissions (per rule, plus `defaultMode`), MCP servers (per name), Plugins (per plugin id), Output style (the setting and the style files) | plan-a section 2, Your setup |
| Problems | One feed, `/api/problems`, built from every collector's diagnostics, the resolver's statuses and the ingest's unreadable transcripts. Overridden is never a problem. Kinds and the first code list are in section 5 | plan.md section 5, "To fix" says it never counts normal precedence. The old "Needs attention" counted overridden values that differ from the winner (`api_settings.py:31`, `:142-190`) |
| Couldn't read counts | Yes, as owner pick O7. `to_fix_count` in `/api/app` becomes the counted total for the current project | plan-a section 9, O7. M1 left it null "until M4" (m1-build.md section 4) |
| Agents setup half | `AgentScope` gains `plugin` and `managed`. `no_file` stays only for a type with no file anywhere (a built-in agent). The Agents page opens the inspector beside the narrowed table at `review/agents?agent=<name>`, and the same item is reachable at `setup/agents/<name>`. Live's "See why" opens the setup route | plan-a section 2, Agents row. M3 left names plain and plugin agents out (m3-build.md section 2) |
| Search field | Built in M5, where its only consumer is | plan-a puts component 15 in wave 4 "for M4 and M5". No M4 board draws a search on a setup list. A long list is a designer question for pass 11 instead |
| Routing layer | `/api/app` keeps `routing_layer: false` through M4 | m1-build.md left it for M4, but the Installed files page that uses it is later (O8), and no M4 screen reads it |
| Claude version | Stays M5's. The setup map has a notice slot, and M5 fills it with the version gap | Real mode reports an empty `claude_version` today (`store_provider.py:1031`). plan-a M5 owns the version-gap notice |
| Fixture count | The resolver corpus is 122 folders plus a README, not 123 | `find tests/fixtures/resolution -mindepth 1 -maxdepth 1 -type d` gives 122. They already pass on the port (`app/server/tests/test_port_resolve.py`, 374 passed on November 9) |
| Demo setup | A setup overlay in `app/fixtures/setup/demo-overlay/` is copied over the demo build's projects when the demo starts. It adds skills, CLAUDE.md files with imports, hooks, `.mcp.json`, two plugins and a fake `.claude.json` inside the demo's own HOME. It also adds three listed projects (an empty setup, a broken setup and a large setup) so one demo server shows every state | The old demo set has settings and agents only. Fixture mode answers `unknown_project` for data routes (fact J-b0ae), so e2e runs on the demo build as M3 did. `tests/` is never edited |

## 3. Ordered tasks

Tiers follow the owner's routing rules. fast-worker runs at medium unless the row says high. Every brief starts with `Kind: rebuild-m4` and carries the HiveMind line from `hivemind_lib.py related <paths>`, the date rule (`date -Iseconds` only) and these limits. Work only in `/Volumes/Warehouse/Projects/claude-code-model-routing-bartab`. Never read anything under `~/.claude`, real transcripts, real settings or `~/.claude.json`. Never pass `--real` to anything. Servers only on ports 47000 to 47999, never 8377. Never print, guess or ask for a key. Use `app/scripts/uvw` and `app/scripts/npmw` for every uv and npm call, and download nothing. Never edit `dashboard/`, `tests/`, `plugins/`, `tools/`, `hooks/`, `agents/`, `rules/`, `skills/` or `install.py`. Write scripts with Write and run one plain command per call, because the Bar Tab guard refuses heredocs and generated command text. Keep the literal text `.claude.json` and the launcher's file name out of Bash commands, because the guard refuses any command that names them (scout finding, November 9). Test code may build those paths inside a fake HOME.

HiveMind ids for briefs: T-7629, T-5589, T-c826, T-3ad1, D-c684, D-3ca7, L-979a, I-14ae, T-6b2f, R-7c9c, R-c047, R-8829, R-ea92, W-4654, S-2dda, M-b3d4, J-b0ae, J-c864, plus whatever `related` returns per task.

| # | Task | Files | Tier | Check | Cost |
|---|---|---|---|---|---|
| 0 | Pre-flight. Time, branch, clean tree, M3 CI fixes merged if any. Write the setup answer models (section 5) and the `Collected` and `Collector` types in `setup_contract.py`, so the contract is fixed before workers start. Add a session fixture in `conftest.py` that copies the setup corpus into a temp folder outside every repo (T-c826) | `app/server/models.py`, `app/server/setup_contract.py`, `app/server/tests/conftest.py` | Lead | The models import and the OpenAPI export runs | In the lead row |
| 1 | Lookups, docs and fixtures only. From code.claude.com, with anchors checked against the rendered HTML (fact D-1534). CLAUDE.md load order, the ancestor walk and nested on-demand loading, the import syntax and hop limit (research gives 4, unconfirmed), whether Claude Code reads `AGENTS.md` itself, HTML comment stripping. Skill locations (user, project, nested, managed, plugin, legacy commands) and SKILL.md front matter. Plugin files (`installed_plugins.json` fields, `known_marketplaces.json`, the `enabledPlugins` entry, the cache layout, the orphaned marker, `plugin.json` component paths). The hooks schema and event list. The `.mcp.json` schema, `managed-mcp.json` name and place, the `~/.claude.json` key names for user and local servers and for project approvals. Output style places and built-in names. Permission rule syntax. Also how the old recorder can call `api_settings` for a resolver folder (W-734f), and why `test_port_collect_overlay.py` has 15 tests against the old 19 | None. A table of fact, value and URL or path:line | scout | Every row has a source, and an unconfirmed row says so | $3 to $5 |
| 2 | Setup corpus. `app/fixtures/setup/` with a generator and committed expected JSON. Sizes empty, simple, typical and complex. Stress cases with long names, 50 agents, 200 permission rules, 20 plugins and a 6-level CLAUDE.md tree. A broken twin per part (bad JSON, bad YAML, symlink out of scope, same-folder clash, orphaned plugin version, import cycle, import out of scope, missing import). Couldn't read cases made at test time (mode 000, invalid UTF-8, over the cap), since git can't store them. The demo overlay and its three extra projects. Waits for task 1 | `app/fixtures/setup/**`, `app/fixtures/setup/build_corpus.py`, `app/server/tests/test_setup_corpus.py` | fast-worker | Two runs give the same bytes. The expected JSON is written by hand for simple and broken, so the generator is not its own oracle (plan.md section 8) | $7 to $12 |
| 3 | Read scope and masking (high). `read_scope.py` (allowed roots per project from section 7, `realpath`, the symlink rule from question 7, the caps, one snapshot, one retry, reason codes). `masking.py` with the 26-07 rules over the ported `collect.mask`. The real-mode read audit (section 7) with a decoy HOME. `model_check.resolve_entries` gains `local_path` and `plan` | `app/server/{read_scope,masking,model_check}.py`, `app/server/tests/{test_read_scope,test_masking,test_real_reads}.py`, `app/server/tests/read_audit_child.py` | fast-worker high | The decoy files are never opened or listed. Every ported mask test still passes. The 18 masking cases in 26-07 pass. pyright strict, coverage 85 percent | $12 to $18 |
| 4 | Settings, Permissions and Output style collectors over the ported `collect` and `resolve`, with the managed `modelPricing` layer wired to the price feed | `app/server/collect_settings.py`, `collect_permissions.py`, `collect_output_style.py`, tests | fast-worker | The 122 resolver folders give the same entries through the collector as through `resolve.load_fixture`. Clean, broken and Couldn't read states per part | $7 to $11 |
| 5 | Old `/api/settings` recorder and the differential (high). Section 6 | `app/oracle/record.py`, `app/fixtures/oracle/settings/**`, `app/server/tests/test_differential_settings.py` | fast-worker high | Section 6 passes outside the allowed list. Two recorder runs give the same bytes | $10 to $16 |
| 6 | Agents with full YAML, and the plugin collector (high). Agents by name across managed, project, user and plugin, with every front matter field from `agent_fields.json`, the plugin-ignored fields and the same-folder clash. Plugins from `installed_plugins.json`, `enabledPlugins` across scopes, the cache folders and each plugin's agents, skills, hooks, MCP and settings, handed to the later collectors. The orphaned version skip. Unknown format as Can't tell | `app/server/collect_agents.py`, `collect_plugins.py`, tests | fast-worker high | Clean, broken and Couldn't read per part. A plugin agent shows `permissionMode`, `hooks` and `mcpServers` as ignored (26-03 line 45). The old agent tests stay green | $12 to $18 |
| 7 | Skills, Instructions and Rules files. Skills by name with SKILL.md front matter, the plugin namespace and legacy commands. CLAUDE.md, CLAUDE.local.md and the files task 1 confirms, in load order, with imports to the hop limit, cycles, missing targets and out-of-scope targets. Rules files with `paths` globs as `loads`. The capped walk for nested files (section 7) | `app/server/collect_skills.py`, `collect_instructions.py`, tests | fast-worker | As task 4. An import chain shows in order with its depth. A cycle stops and reports once | $9 to $14 |
| 8 | Hooks, MCP and the masked `~/.claude.json` (high). Hooks from settings at every scope, plugin `hooks.json` and front matter, keyed by event, matcher and handler, with `disableAllHooks` and `allowManagedHooksOnly`. MCP by name across local, project, user, plugin and managed, with approvals. The `~/.claude.json` reader keeps three key groups and drops the rest at parse (section 7) | `app/server/collect_hooks.py`, `collect_mcp.py`, `claude_json.py`, tests | fast-worker high | Every secret in the corpus is masked in every answer. A test parses a fake file holding other keys and proves none reach any answer, log or error. Clean, broken and Couldn't read per part | $12 to $18 |
| 9 | Problems feed, setup map and API. `/api/setup`, `/api/setup/{part}`, `/api/problems`, `to_fix_count` in `/api/app`, the ingest's unreadable transcripts as Couldn't read rows, Agents `scope` and plugin rows in `/api/agents`, the etag over signatures, then the OpenAPI export and `schema.d.ts` | `app/server/{setup_answers,problems,api_setup,store_provider,fixture_provider,main,agent_setup}.py`, `app/web/src/api/openapi.json`, `schema.d.ts`, tests | fast-worker | TestClient on the corpus and the demo. The closed-enum test passes on the server side. No answer carries body text, `cwd` or an unmasked secret | $8 to $13 |
| 10 | Setup speed. The complex and stress fixtures plus a generated tree with 30 plugins. Measure `/api/setup`, each part and `/api/problems`, cold and with matching signatures | `app/server/tests/test_setup_size.py` | fast-worker | Cold p95 under 300 ms for the map and each part, signature check under 20 ms, on the stress tree. The numbers go in the results. A miss asks the owner before any cache work | $4 to $7 |
| 11 | Designer passes 10 to 12, then the designer's review of this plan at medium (dispatched by the main session, not this lead). Section 9 says what each covers | Boards in the archive, notes in components.md | designer | The owner picks before tasks 12 and 15 to 17 | $20 to $38 |
| 12 | String deck. Every M4 word on the pass 10 to 12 boards, plus each problem code's title, cause, consequence and action, each read-only reason, scope names and second lines, `loads` words, confidence lines, the part summaries, empty, loading and error lines, and the "when Bar Tab started" shell line. Waits for task 11 | Draft as a key table, typed into `app/web/src/strings/en.ts` by the lead | tech-writer | String lint passes. The closed-enum test passes on the page side. Owner reads the deck | $5 to $9 |
| 13 | Wave 4 components. Breadcrumb (3), Switch (16), scope label and scope chip (12), list and inspector (26), To fix row and group (32), each with every state on the sheet. Can start before task 11 and takes the pass changes in the fix round | `app/web/src/components/*`, `app/web/src/sheet/*`, tests | fast-worker | Vitest. The sheet test fails on any manifest state without a render. Axe on the sheet at 375 and 1440, light and dark | $8 to $12 |
| 14 | Setup data layer. Query hooks for the map, a part and problems with the etag and 10 s refetch while visible, the Switch state in `?scopes=1`, item routes, and the To fix count in the shell from `/api/app` | `app/web/src/api/setup.ts`, `app/web/src/lib/setup-routes.ts`, tests | fast-worker | Vitest with fake timers (fact J-f0a7) | $4 to $7 |
| 15 | Your setup and surface pages (high). The map with the Switch, every surface page with its list and inspector, read-only reasons, the Couldn't read card with partial results, empty and long lists, the phone list-as-page with its back link | `app/web/src/pages/setup/*`, CSS, `app/web/src/app/router.tsx`, tests, `app/web/e2e/setup.spec.ts` | fast-worker high | Vitest, tsc, ESLint, Stylelint, Prettier. Playwright with axe at 320, 375 and 1440, light and dark, forced colours and reduced motion | $12 to $18 |
| 16 | To fix and the Agents setup half. The To fix page, the nav count, the Agents inspector beside the narrowed table, plugin rows, names as links, Live's "See why" | `app/web/src/pages/setup/ToFixPage.tsx`, `app/web/src/pages/review/AgentsPage.tsx` and its table, `app/web/src/pages/live/ModelCheckCard.tsx`, tests, `app/web/e2e/tofix.spec.ts` | fast-worker | As task 15 | $9 to $14 |
| 17 | M4 end to end. The two keyboard walkthroughs, the accessibility snapshots and the exact accessible text list in section 10 | `app/web/e2e/{setup-keyboard,tofix-keyboard}.spec.ts` | fast-worker | All pass three runs in a row | $7 to $11 |
| 18 | Exit runs. T2 suite, the full Playwright and axe matrix, then the old suite alone with its log named for `feature-bartab-m4` (T-7629), then the protected-path diff | Logs in the scratchpad | scout | All green. The diff is empty | $2 to $3 |
| 19 | Browser check in Chrome under the tab-group rules. Your setup, three surface pages, To fix and Agents at 1440 and 375, light and dark, against the pass 10 to 12 boards | None. Returns a difference list | judge | Differences fixed in one batch, or listed for the owner | $4 to $7 |
| 20 | One fix round from tasks 18 and 19, a second only for Linux CI failures, consolidation and the report. The main session dispatches the verifier | None | Lead and fast-worker | Report written | $10 to $18 |

The lead's own share (task 0, every review, typing `en.ts`, the fix briefs, consolidation and the report) is $30 to $45.

Order and parallel work. Task 0 runs first. Then 1, 3 and 13 run in parallel, because they touch separate files. Task 2 waits for 1. Tasks 4, 6, 7 and 8 need 2 and 3, and run two at a time (4 with 6, then 7 with 8), because each pair touches separate collector files and the lead reviews them between pairs. Task 5 needs 4. Task 9 needs 4 to 8. Task 10 needs 9. Task 11 runs beside all of that, since it is the main session's dispatch. Task 12 waits for 11. Task 14 needs 9. Tasks 15 and 16 need 12, 13 and 14, and can run together because they touch separate pages (the lead merges `router.tsx`). Task 17 needs 15 and 16. Then 18, 19 and 20. Only the lead edits `conftest.py`, `pyproject.toml`, `models.py`, `setup_contract.py` and `en.ts`, so parallel workers never collide there. M4 adds no package. A YAML library is not needed, because the ported `agent_frontmatter.py` reader serves SKILL.md and output style front matter too. If task 1 finds SKILL.md front matter that reader can't parse, the lead asks the owner before adding a package.

## 4. Collectors in the plan's order

The order is plan.md section 3's (senior developer, r1-senior-dev 5). Each collector has a reader, a clean fixture, a broken twin and a Couldn't read state (plan.md section 2, Machine checks). The old app has readers for the first two only (scout inventory, `dashboard/collect.py`), so the rest have no old oracle and rely on the corpus's hand-written expected JSON.

| # | Collector | Reader | Files (templates) | Clean fixture | Broken twin | Couldn't read | Oracle |
|---|---|---|---|---|---|---|---|
| 1 | Settings, with Permissions and Output style | `collect_settings.py` over the ported `collect.collect` and `resolve.resolve` | Managed `managed-settings.json` and `managed-settings.d/*.json`, `<config>/settings.json`, `<project>/.claude/settings.json`, `<project>/.claude/settings.local.json`, the repo-root local file (question 5), `<config>/output-styles/*.md` and `<project>/.claude/output-styles/*.md` (front matter only) | `typical` with model, effort, env, permissions and an output style | Bad JSON in the local file (Won't load), a top level that is an array, a bad managed file (Won't load, startup stops), a permission rule with bad syntax, an output style that names no file | User settings at mode 000 | Old `/api/settings` (section 6) and the 122 resolver folders |
| 2 | Agents with full YAML | `collect_agents.py` over the ported `agent_frontmatter.py` and `agent_md.py` | `<config>/agents/**`, `<project>/.claude/agents/**`, managed agents if task 1 confirms a place, plugin agents from collector 3 | `typical` with five agents, one overridden by name | No front matter, no description, a non-`.md` file, two files with one name in one folder, a block scalar the reader rejects | One agent file at mode 000, one over the cap | Old `/api/settings` agent rows |
| 3 | Plugin agents and settings | `collect_plugins.py` | `<config>/plugins/installed_plugins.json`, `known_marketplaces.json`, `enabledPlugins` in every settings scope, each install folder's `plugin.json`, `agents/`, `skills/`, `hooks/hooks.json`, `.mcp.json` and `settings.json` (question 3) | Two plugins built from this repo's own payloads (`plugins/routing-dashboard`, `plugins/hivemind`) as install folders, with a made-up `installed_plugins.json` per the documented fields (question 10) | Enabled but not installed, an orphaned version folder, a bad `plugin.json`, an install path outside the plugins folder, an unknown file version | `installed_plugins.json` at mode 000 | None. Hand-written expected JSON |
| 4 | Skills | `collect_skills.py` | `<config>/skills/*/SKILL.md`, `<project>/.claude/skills/*/SKILL.md`, nested `.claude/skills` from the capped walk, managed and plugin skills, legacy `commands/*.md` (front matter and names only) | Three skills, one from a plugin with its namespace | A folder with no SKILL.md, bad front matter, two skills with one name in one scope | One SKILL.md at mode 000 | None |
| 5 | CLAUDE.md with imports, and rules files | `collect_instructions.py` | `<config>/CLAUDE.md`, `<config>/rules/*.md`, `<project>/CLAUDE.md`, `<project>/.claude/CLAUDE.md`, `<project>/CLAUDE.local.md`, `<project>/.claude/rules/*.md`, ancestors' CLAUDE.md and CLAUDE.local.md (question 5), nested CLAUDE.md from the capped walk, import targets inside the allowed roots (question 6), managed CLAUDE.md | A chain of three imports, one rules file with `paths` globs | An import cycle, a missing import, an import past the hop limit, an import outside the roots, bad rules front matter | A CLAUDE.md with invalid UTF-8 | None |
| 6 | Hooks | `collect_hooks.py` | The `hooks` key in every settings file (already read), plugin `hooks/hooks.json`, `hooks` in agent and skill front matter | Three hooks across user, project and a plugin | An unknown event name, a handler that is not an object, `disableAllHooks` on in user scope, `allowManagedHooksOnly` on | A plugin `hooks.json` at mode 000 | None |
| 7 | MCP from `.mcp.json` | `collect_mcp.py` | `<project>/.mcp.json`, managed `managed-mcp.json`, plugin `.mcp.json`, approvals in settings | Two project servers, one plugin server, one approved and one not | Bad JSON, an entry with neither `command` nor `url`, a `${VAR}` with no default (Can't tell, since the session's environment isn't visible) | `.mcp.json` at mode 000 | None |
| 8 | Masked `~/.claude.json` | `claude_json.py`, feeding `collect_mcp.py` | `<config>/.claude.json`, else `$HOME/.claude.json` (26-08 line 9), only the three key groups in section 7 | User and local servers with env and headers holding fake secrets | Bad JSON, a `projects` entry that is not an object | Over 32 MiB, mode 000 | None. A test proves no other key reaches an answer |

The Couldn't read state is the same for every part. The part keeps its page, shows what did read, and shows an inline error card with the file, the reason and what to do (plan.md section 5). The setup map row shows the part's result with a Couldn't read mark, and the file appears once on To fix.

## 5. API contract

The Pydantic models in `app/server/models.py` (a new "Setup (M4)" block) are the contract. Task 0 writes them. Section 16 changes several fields below after the designer's plan review, and it and the models win where they differ. All times are ISO strings in UTC. Every answer carries `project`, `server_time`, `as_of`, `etag` and `unchanged`. A matching `etag` gets `{project, server_time, etag, unchanged: true}`. Errors use the one envelope `{code, path}`, with `bad_request` (400), `unknown_project` (404) and `unknown_part` (404). Paths are display paths (`~/...` under HOME, project-relative inside a project, or the managed folder's name), never raw. The page owns every word.

### `GET /api/setup?project=<key>&scopes=<0|1>`

| Field | Type | Contents |
|---|---|---|
| `parts[]` | list | `part` (one of the ten), `summary_code` and `params` (for example `model_effort` with model and effort, or `count` with n), `statuses[] {status, count}`, `counted_problems`, `unreadable` (true when any file of the part couldn't be read) |
| `scopes[]` | list, only with `scopes=1` | Per part, per scope (managed, command_line, project_local, project, user, plugin, shell), `{state, summary_code, params}`, where `state` is `set`, `not_set`, `not_visible` or `unreadable` |
| `notices[]` | list | `code` and `params`. Empty in M4 unless a collector raises one. M5 adds the version gap |

### `GET /api/setup/{part}?project=<key>`

| Field | Type | Contents |
|---|---|---|
| `items[]` | list | The item shape below |
| `unreadable[]` | list | `file`, `reason` (`permission`, `not_utf8`, `too_large`, `vanished`, `folder_unlistable`) |
| `empty_reason` | string or null | `none_found`, or `not_visible` for a part the server can't see |

Item shape, from plan.md section 7 and plan-a section 3.

| Field | Contents |
|---|---|
| `id` | Stable, a hash of part, scope and key path. The URL item segment |
| `name` | The key, agent, skill, server, plugin, hook or file name |
| `scope` | Where the winning value sits, or the item's own scope for a union part |
| `sources[]` | Every place it is set, top wins: `{scope, file, line, value, status, plugin}` with `value` masked |
| `winner` | Index into `sources`, or null |
| `status` | One of the seven words |
| `reason` | `{code, params}` from the resolver or the collector |
| `confidence` | `tested`, `documented` or `assumed` |
| `loads` | `always`, `on_demand` with `globs[]`, `when_no_claude_md`, or null |
| `applies` | `now`, `new_session`, `restart` or `reload_plugins`, or null |
| `writable`, `read_only_reason` | False in M4. The reason is a code with params (`managed`, `plugin` with name, `claude_json_command`, `command_line`, `not_visible`) or null |
| `risk_tier` | `safe`, `risky` or null, for M6 and M8 |
| `feature` | `core` in M4 |
| `facts` | Per part, the inspector's extra lines. For instructions `lines`, `bytes`, `imports[] {target, depth, state}`. For agents the front matter fields with `ignored` for plugin agents. For hooks `event`, `matcher`, `command` (masked). For MCP `transport`, `command` or `url` (masked), `env_keys[]` (names only), `approved` |
| `usage` | For agents and model and effort settings, `{code, params}` such as runs at a value over 30 days, from the store. Null elsewhere |
| `real_path` | For a symlink, the target's display path |

### `GET /api/problems?project=<key>`

| Field | Contents |
|---|---|
| `rows[]` | `kind` (`read_failure`, `problem`, `cant_tell`, `notice`), `group` (`couldnt_read`, `wont_load`, `not_as_set`, `cant_tell`, `notice`), `code`, `part`, `item_id` or null, `file`, `line`, `params`, `confidence`, `fix {kind, target}` where `kind` is `open_item`, `copy_command` or `cant_fix_here` with a reason |
| `counted` | Couldn't read, Won't load and Not as set rows |

First code list, for task 1 and the deck to settle. Couldn't read: `permission`, `not_utf8`, `too_large`, `folder_unlistable`, `transcript_unreadable`. Won't load: `json_invalid`, `not_object`, `managed_invalid`, `value_invalid`, `frontmatter_invalid`, `agent_no_name`, `agent_no_description`, `agent_not_md`, `same_name_in_folder`, `skill_no_md`, `import_missing`, `import_too_deep`, `import_cycle`, `hook_bad_event`, `hook_bad_handler`, `mcp_bad_entry`, `plugin_not_installed`, `plugin_manifest_invalid`, `output_style_missing`, `permission_rule_invalid`. Not as set: `ignored`, `lowered`, `plugin_field_ignored`, `hooks_disabled`. Can't tell: `unknown`, `import_out_of_scope`, `env_not_visible`, `plugin_format_unknown`, `walk_stopped`. Notice: `rows_no_usage`, plus M5's `version_gap`. The closed-enum test fails when a code has no string, on both sides.

### Changes to answers that exist

- `/api/app`: `to_fix_count` is the counted total for the current project.
- `/api/agents`: `AgentScope` gains `plugin` and `managed`. Rows carry `item_id` for the inspector link. `never_ran[]` includes plugin agents.
- Timeline `model_check` rows gain `item_id`, so "See why" has a target.

## 6. Differential against the old `/api/settings`

Fixtures only. No test reads real data, starts the old server or opens a port for it. The recorder runs the old route function in process, as M1 to M3 did (plan-a section 6).

| Oracle | Fixture | How it runs | Compares |
|---|---|---|---|
| Old `api_settings.settings` | Each project of the demo build at its fixed `now` | `server.fixture_context`, as the M1 recorder does (fact W-734f), one payload per project | `entries` (key, value masked, status, layer, file, scope, line, agent, rule_id), `rows`, `files` with status, `attention` |
| Old `api_settings.settings` or `resolved` | Each of the 122 resolver folders | The way task 1 finds. A folder lacks `routing-dashboard.json`, so the recorder may build the context from the folder's `session.json` and `dashboard.json` | The same fields |
| Old `pincheck` | The demo build | Reused from M2 | Agents `set` and Check stay equal to M3's |

The manifest names the old commit sha. Payloads are regenerated by one command and never hand-edited.

Mapping and allowed differences to start with.
1. Status words are the same seven. The page words them, so nothing maps.
2. The old `attention` groups map to To fix as unknown to Can't tell, lowered and ignored to Not as set, invalid to Won't load. Overridden leaves the list, because To fix never counts normal precedence (plan.md section 5). The old equal-value skip (`api_settings.py:142-150`) has nothing to skip.
3. A settings file the old app marks `unparsed` becomes Won't load with `json_invalid` or `not_object`. One it marks `unreadable` becomes Couldn't read.
4. Display paths follow section 5, and the old `path_display` fields are page concerns.
5. The old answer has no items for skills, instructions, hooks, MCP, plugins or output style, so those parts have no old answer.
6. The Command line scope reads `not_visible` in real mode. Fixture folders with `flags` or `cli_settings` in `session.json` still feed the resolver, so their entries compare as recorded.
7. Plugin agents appear in the new Agents part and not in the old answer.

Any other difference fails. Each entry names its reason and plan section in the JSON, as in M1.

## 7. Real data

Agents never read real data. Only the owner's own launch does. Every brief forbids `--real` and real paths, and the M2 guard hook refuses both. This section says what the server reads on the owner's machine.

### What M2 already reads

M2's rule (m2-build.md section 7, item 5a, and `store_provider.py:500-523`). Settings and agent files are read only for projects listed in `routing-dashboard.json`, plus user scope and the managed folder. An unlisted project's `cwd` comes from a transcript, so nothing under it is read. The exact list today is the following.
- `<config>/routing-dashboard.json`, `<config>/settings.json`, `<config>/agents/**` and the names in `<config>/rules/`.
- Managed `managed-settings.json` and `managed-settings.d/*.json`.
- In each listed project, `.claude/settings.json`, `.claude/settings.local.json`, `.claude/agents/**` and the names in `.claude/rules/`.
- The environment, filtered to the rules variables and env-block names (`collect.py:370-404`), plus `HOME`, `CLAUDE_CONFIG_DIR`, `TZ` and `/etc/localtime`.

User-level settings are not a new read. M4 shows every key of them on screen, masked, where M2 used only model, effort and pins.

### What M4 adds

Each line names its owner question. Nothing here is read for an unlisted project, and nothing is read until the owner answers.

| New read | Inside the M2 roots | Question |
|---|---|---|
| `<config>/CLAUDE.md` and the contents of `<config>/rules/*.md` | Yes | 2 |
| `<config>/skills/*/SKILL.md`, `<config>/commands/*.md`, `<config>/output-styles/*.md` | Yes | 2 |
| In listed projects, `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, rules file contents, `.claude/skills/**/SKILL.md`, `.claude/commands/*.md`, `.claude/output-styles/*.md`, `.mcp.json`, and nested CLAUDE.md and `.claude/skills` from a capped walk of the project tree | Yes | 2 |
| Managed `CLAUDE.md`, `managed-mcp.json` and any managed skills or agents folder task 1 confirms | Yes | 2 |
| `<config>/plugins/` (`installed_plugins.json`, `known_marketplaces.json` and the install folders under it) | Inside `<config>`, but a new tree | 3 |
| A plugin `installPath` outside `<config>/plugins/` | No | 3 |
| `~/.claude.json`, masked, three key groups only | No | 4 |
| The repo-root `.claude/settings.local.json` of a listed project that sits below its git root | No, a parent folder | 5 |
| CLAUDE.md and CLAUDE.local.md in the ancestors of a listed project | No, parent folders | 5 |
| Import targets outside the allowed roots | No | 6 |
| Symlink targets outside the allowed roots | No | 7 |
| Auto memory (`<config>/projects/<folder>/memory/MEMORY.md`) | Inside `<config>`, but the owner's memory | 8 |

The capped walk skips dot folders other than `.claude`, `node_modules`, `vendor`, `dist` and `build`, goes 6 levels deep and stops after 5,000 folders with a `walk_stopped` Can't tell row. It lists folder entries and opens only the named files.

The `~/.claude.json` reader parses the file once and keeps only these keys, then drops the parsed object. Top-level `mcpServers` (user scope). `projects[<listed project's real path>].mcpServers` (local scope). That entry's `enabledMcpjsonServers`, `disabledMcpjsonServers` and `enableAllProjectMcpServers`. Task 1 confirms the names from the docs. Env and header values, URL userinfo and secret-named args are masked before anything leaves the reader. A parse error reports `json_invalid` with a line and never the text. Nothing is logged from it.

### How the rule is enforced

1. One read path. Every collector reads through `read_scope.py`, which knows the allowed roots for the project in hand and refuses the rest by reason code (`outside_scope`), which the page shows as "not read here".
2. The roots come from the project list and the config folder alone. No path is typed. An unlisted project has no project root.
3. The read audit test. `test_real_reads.py` builds a decoy HOME with a `.claude` folder, listed and unlisted projects, a parent folder with its own CLAUDE.md, a plugin with an outside install path, an import to a folder outside, an auto memory file and a file named like an SSH key. It starts the server as a subprocess through `read_audit_child.py`, which installs an audit hook that records every `open`, `os.listdir` and `os.scandir` path and then runs `serve.main` with `--real`. It polls every setup route, problems and the Agents page. Then every recorded path sits under an allowed root or the app's own code and Python, and no decoy appears. It runs once per answer of questions 2 to 8, so a "no" is tested too.
4. Test isolation stays as M2 set it. `conftest.py` points `HOME` and `CLAUDE_CONFIG_DIR` at a temp folder and fails any test that opens a path under the real `~/.claude`.

## 8. Guard and write guard

- `write_guard.py` needs no change. It refuses writes outside the store root and allows reads everywhere (`write_guard.py:1-6`). M4 adds no write. Every setup read opens files read-only, and the real-mode write test from M2 runs again with the new collectors live, so a stray write by any collector fails it.
- Reads have no runtime guard today. Section 7's `read_scope.py` is the read-side counterpart, enforced in code and proven by the audit test. It is not an audit hook in production, because a hook that refuses reads would also block Python's own imports and the store.
- The Bash guard hook from M2 (owner answer 4) refuses any agent command that names the real Claude folder or `.claude.json`. So every M4 fixture is made up, plugin shapes come from docs and this repo's own payloads (question 10), and briefs keep those literals out of commands. The guard blocked a scout's Bash read of the one allowed usability file on November 9. The Read tool worked for the lead.
- `NoHomePathsInTestsTest` covers `app/` (fact T-3ad1), so sample paths in tests start at `/work/`.
- Mode 000 fixtures need a non-root user. On Linux CI the Couldn't read tests skip with a reason when the process runs as root, and a second case uses invalid UTF-8, which works as any user.
- No new network call. No new write route. `/api/setup*` and `/api/problems` are GET routes behind the read key like every other.

## 9. Designer passes and UI state

### What exists and what doesn't

| Screen | Boards today | State |
|---|---|---|
| Your setup | `a-setup`, `a-setup-scopes` (round 4, `a2.js:22-34`) | Pre-canonical look. No unreadable part, empty part, loading or error. Scope chips at 375 drawn in source, PNG unchecked |
| Surface page and inspector | `a-surface`, `a-surface-readonly` (round 4, `a2.js:35-70`), with the managed read-only reason | Pre-canonical. Drawn for a settings key only. No Couldn't read card with partial results, no empty or long list, no item variants for instructions, rules, skills, hooks, permissions, MCP, plugins or output style |
| To fix | `a-tofix`, `a-tofix-empty` (round 4, `a2.js:150-161`) | Pre-canonical. Titles are h4 where canonical is h3, read errors use the Invalid chip where canonical is the ✕ finding, and the count sits in the `.q` slot where canonical has two slots (components.md, "Differences resolved", items 8, 11 and 13) |
| Agents setup half | `a-agents`, `a-agent-inspector`, `a-agent-plugin` (agent edit round, `agents.js`) | Drawn before the chosen-state rule landed, unconfirmed by pixel check. M3's `a-m3-p7-agents` has no inspector |
| Edit, risky and MCP inspectors | `a-edit-*` (round 4) | Write side, M6 to M8. Not needed now |

No M2 or M3 round board covers a setup screen. All M4 screens are drawn only in the pre-canonical look, so the pages need passes, as M2 needed passes 1 to 3 and M3 passes 7 to 9. The boards are good enough for the server work and task 13, but not for the pages. The main session dispatches the passes, and they run beside tasks 0 to 10.

### Pass 10, Your setup in the canonical look

- The map with ten parts at 1440 and 375, light and dark, with the Switch off and on, and chips at 375.
- A part with a Couldn't read file, a part with nothing found, and a part the server can't see.
- The Command line and Your shell scopes, "not visible here", and the shell line from question 9.
- Loading, a card error and long values.

### Pass 11, surface pages and the inspector

- The list and inspector for each item kind. A settings key, an agent, a plugin agent with ignored fields, an instruction file with its import chain and `loads`, a rules file with globs, a skill, a hook with its masked command, a permission rule, an MCP server with env names and the `~/.claude.json` owner line, a plugin with its contents, an output style.
- Every read-only reason (managed, plugin, user or local MCP, command line) with Copy path, and an item M6 will make editable, with no lock.
- The Couldn't read card over a partial list, an empty list, a long list (200 permission rules), a symlink with its real path, an import outside the roots.
- The phone list-as-page and the inspector's back link.
- Usability lessons 14 (the inspector follows the selection), 16 (an error beside its cause with the fix) and 22 (a simple view first, raw one step away) apply.

### Pass 12, To fix and the Agents setup half

- To fix with all five groups, h3 titles, the ✕ finding for Couldn't read and the two header slots. Each fix kind in M4: open the item, copy a command, or can't fix here with the reason. No editor buttons until M6.
- "Nothing to fix" with Can't tell still below (plan.md section 5), a long list, the nav count hidden at zero (D6).
- The Agents inspector beside the narrowed table, plugin rows, names as links, and Live's "See why" target.

### Page states

| State | When | Data |
|---|---|---|
| First load | No answer yet | Skeleton bones per card, `aria-busy` and one screen-reader line |
| Normal | The usual case | As section 5 |
| Part with a file it couldn't read | `unreadable[]` not empty | The inline card over the partial list |
| Part with nothing found | `items` empty, `empty_reason` `none_found` | An in-list empty state that says what would appear |
| Part not visible | `empty_reason` `not_visible` | A sentence saying why the server can't see it |
| Card error | One route fails | A raised error row on that card |
| Lost | Every route fails | The M0 server-stopped gate |
| Nothing to fix | `counted` 0 | The page-level empty state, with Can't tell and Notices still below |
| Demo data | `mode` is not real | The M2 shell badge |
| Unknown item | An item id no longer in the part | A sentence and a link back to the part |

### Events the pages handle

| Event | What happens |
|---|---|
| Switch | The URL's `scopes` changes with history replace, columns or chips appear, focus stays on the Switch, nothing is announced beyond its state |
| Pick an item | The URL changes, the inspector follows, focus moves to the inspector h2 |
| A refetch with new data | Values change in place, never announced. A picked item that vanished shows the unknown-item state |
| To fix action | Opens the item, or copies the command with a polite "Copied" |
| Nav count change | The accessible name of the To fix link changes ("To fix, 4"), never announced |

## 10. Tests and exit

### New suites

| Area | Tests |
|---|---|
| Collectors | Per part, the clean fixture, the broken twin and the Couldn't read state, against hand-written expected JSON. Partial results always come back |
| Resolver | The 122 folders keep passing on the port, and give the same entries through the settings collector |
| Differential | Section 6, for every demo project and resolver folder |
| Masking | The old mask tests, the 18 cases from 26-07, and a sweep that plants a fake secret in every place the corpus can hold one and checks no answer carries it |
| Real reads | Section 7's audit test, once per owner answer |
| Write guard | M2's real-mode write test with every collector live |
| Closed enum | Fails when a problem code, reason code, part or scope has no string on the page side or no rule on the server side |
| API | Each route on the corpus and the demo. Etag and `unchanged`. `bad_request` and `unknown_part`. No answer carries body text, `cwd` or an unmasked secret. The schema text-column test from M1 still passes |
| Setup speed | Section 3, task 10 |
| Web | Vitest for every component state and the hooks. Playwright with axe on Your setup, three surface pages, To fix and Agents at 320, 375 and 1440, light and dark, forced colours and reduced motion |
| Exact accessible text | Playwright asserts, from the typed strings, the Switch's name and state, the breadcrumb's current page, the inspector region's label and h2, each To fix group heading with its count, each fix action's name, and the To fix link's name with its count |
| Keyboard walkthroughs | Playwright with the keyboard only, at 375 and 1440. "Explain one agent's model and effort" goes from Your setup to the Agents part and the inspector's Why, and from Review's Agents page to the same item. "Find one problem on To fix" goes from the nav count to a row and on to its item. Each step asserts focus and the visible text |

Run Playwright from `app/web` with `../scripts/npmw exec playwright -- test -c playwright.config.ts`, with its own `--output` when two runs share the worktree (fact J-c864).

### Accessibility snapshots instead of VoiceOver

VoiceOver runs once, at M9 (owner, November 9). Task 17 takes Playwright accessibility snapshots of the setup map with the Switch off and on, a surface list with one item picked, the inspector of a read-only item, the Couldn't read card, a To fix group and the Agents inspector. They gate like any test. The M9 script reuses this list.

### Kept green

- The M0 to M3 exit runs, with pytest, Vitest and Playwright counts in the report.
- Standards checks. ruff, ruff format, pyright strict, coverage at 85 percent on `app/server`, tsc, ESLint, Stylelint and Prettier.
- The old suite alone, `/usr/bin/python3 -m unittest discover -s tests` from the worktree root, log named for `feature-bartab-m4` (T-7629). Expected 3575 tests and 88 skipped.
- `git diff --stat 7db2be8 -- dashboard tests plugins tools hooks agents rules skills install.py` stays empty.

### Exit, from plan-a M4

- The resolver fixtures pass on the port (122 folders).
- Each part has a reader, a clean fixture, a broken twin and a Couldn't read state.
- The closed-enum test fails on a code with no string.
- The differential against the old `/api/settings` passes for settings and agents, outside the allowed list.
- The walkthroughs "explain one agent's model and effort" and "find one problem on To fix" pass by keyboard alone at 375 and 1440.
- Axe, the Playwright accessibility snapshots and the forced-colors checks pass on every M4 route. VoiceOver waits for M9.

## 11. Owner questions

Each has my pick first.

1. Designer passes 10 to 12. Every M4 board is in the pre-canonical round 4 or agent-round look, and Couldn't read, empty, long-list and most item kinds have no board.
   - A (my pick). The main session dispatches passes 10 to 12 now, plus the plan review at medium. Tasks 0 to 10 and 13 run beside them.
   - B. Build from the round 4 boards and fix after a later pass. The pages get built twice.
2. New files inside the roots M2 already reads (user config folder, listed projects, managed folder). That is CLAUDE.md files, rules file contents, SKILL.md and legacy command front matter, output style files, `.mcp.json`, managed CLAUDE.md and `managed-mcp.json`, and a capped walk of each listed project for nested CLAUDE.md and `.claude/skills`. Bodies are read in memory and never sent.
   - A (my pick). Allow all of it, as section 7 lists.
   - B. Allow it without the nested walk. Nested CLAUDE.md files and skills show as Can't tell.
   - C. Names and front matter only, no CLAUDE.md or rules bodies. Import chains and `paths` globs can't be shown.
3. Plugins. Plugin agents, skills, hooks and MCP live under `<config>/plugins/`, which M2 never read, and an install path can point elsewhere.
   - A (my pick). Read `<config>/plugins/` and install folders under it. An install path outside it shows "not read here" as Can't tell.
   - B. Follow install paths anywhere.
   - C. No plugin reads in M4. Plugins shows only `enabledPlugins` from settings, and plugin agents stay "unknown source".
4. `~/.claude.json`. It holds user and local MCP servers, and M2 never read it. The reader keeps three key groups, masks them and drops the rest at parse.
   - A (my pick). Read it when a setup or problems answer needs it and its stat signature changed. No background read, so nothing watches it.
   - B. Read it at server start and on "Check again" only, which lands in M7. User and local servers can be up to a session old.
   - C. Don't read it in M4. User and local MCP scopes show "not visible here" until M7.
5. Parent folders of a listed project. Claude Code reads the repo-root `.claude/settings.local.json` for a project below its git root (the old app does too, `local_root.py`), and CLAUDE.md and CLAUDE.local.md in every ancestor folder [NEEDS CONFIRMATION: ancestor walk, task 1].
   - A (my pick). Read exactly those file names in the ancestors, stat first, and find the git root by looking for `.git` without running git.
   - B. Don't. Both show as Can't tell with "not read here", and Model check keeps M2's answer for such projects.
6. Imports outside the allowed roots, such as `@/other/repo/notes.md`.
   - A (my pick). List the import with its path and "not read here" as Can't tell, and don't open it.
   - B. Follow any import up to the hop limit.
   - C. Follow no imports at all.
7. Symlinks whose target is outside the allowed roots, such as an agent file linked to a dotfiles repo.
   - A (my pick). Follow a single-file symlink and show its real path, since Claude Code reads it. Don't follow a symlinked folder out of the roots.
   - B. Follow none. Such files show "not read here".
8. Auto memory (`MEMORY.md` under each project's transcript folder). The glossary keeps "Memory" for it and out of Instructions.
   - A (my pick). Don't read it. Instructions says auto memory isn't shown.
   - B. Read its size and line count only, for the Instructions part.
9. Your shell. plan.md says it reads "not visible here", but M2's Model check uses the server's environment from when it started.
   - A (my pick). Keep M2's behaviour, and the inspector says the value is what Bar Tab saw when it started, with confidence `assumed`.
   - B. Show "not visible here" everywhere and drop the environment from the resolver. Live's Model check can then change for anyone who sets effort in the shell.
10. Plugin fixtures. Agents may not read your installed plugin files, and research 26-03 wanted a real file with your consent.
    - A (my pick). Build plugin fixtures from the docs and this repo's own plugin payloads, with a made-up `installed_plugins.json`. Add a real sample later if a format gap shows on your data.
    - B. You copy a redacted `installed_plugins.json` and one `enabledPlugins` entry into `app/fixtures/setup/` yourself before task 2.
11. Budget (section 12). It sits far above plan-a's $60 to $100, because M2 ran about twice its plan, M3 came to about $160 to $240 against plan-a's $50 to $90, and six of M4's eight collectors have no old reader to port.
    - A (my pick). The full build, $171 to $270 for the lead's build, with a stop and report before the next task once build spend passes $250.
    - B. The trimmed build, $142 to $226, with a stop at $210. It takes question 4 option C, merges tasks 14 into 15 and 17 into 15 and 16, and runs pass 12 as part of pass 11.

## 12. Cost estimate

List-price ranges. M2 was planned at $75 to $126 for its build and came in around $155 to $190 in all. M3 came to about $160 to $240 against plan-a's $50 to $90, which sits inside its own plan of $157 to $268. Each row here starts from M3's per-dispatch shape. I have no per-run cost from the dashboard in this tree. [NEEDS CONFIRMATION: dashboard cost per run for each agent.]

| Dispatch | Count | Estimate |
|---|---|---|
| This plan step, lead and two scouts | 1 | $10 to $15 |
| Lead build, reviews, string typing, fix briefs and consolidation, deep-reasoner on Opus at high | 1 | $30 to $45 |
| fast-worker at high, tasks 3, 5, 6, 8 and 15 | 5 | $58 to $88 |
| fast-worker at medium, tasks 2, 4, 7, 9, 10, 13, 14, 16, 17 and the fix round | 10 | $70 to $113 |
| scout, tasks 1 and 18 | 2 | $5 to $8 |
| judge, task 19 in Chrome | 1 | $4 to $7 |
| tech-writer at medium, task 12 | 1 | $5 to $9 |
| Build only, after this plan step | | $171 to $270 |
| Designer passes 10 to 12 and the plan review at medium (main session) | 4 | $20 to $38 |
| Verifier on Opus (main session) | 1 | $5 to $10 |
| Total for M4 | | $206 to $333 |

The trimmed build saves about $29 to $44 and gives $142 to $226. It drops the `~/.claude.json` reader (question 4 option C), folds task 14 into 15 and task 17's walkthroughs into 15 and 16, and has the designer draw To fix and the Agents half inside pass 11.

What drives the cost.
- Eight collectors, six with no old reader, each with three fixtures and a state. Tasks 2 to 8 are about 40 percent of the build.
- Masking and the read audit. Both are security work and run at high.
- Four new routes and the Agents change through the axe and Playwright matrix, on the corpus and the demo.
- The string deck. About 40 problem codes, each with a title, cause, consequence and action, plus the read-only reasons and part summaries. It is about twice M3's deck.
- The lead. About fourteen worker diffs to review, against eleven in M3.

Where it could overrun.
1. Undocumented formats. `installed_plugins.json`, the `enabledPlugins` entry and the `~/.claude.json` keys are documented only in part (26-03 lines 72 to 75). If task 1 leaves gaps, the plugin and MCP collectors carry Can't tell paths and extra tests. Tasks 6 and 8 run at high for this.
2. Late or changed boards. Three passes, and the surface page has ten item kinds. Question 1 holds the line, and the pages wait for the pick.
3. Owner answers that widen reads. Each "yes" to questions 2 to 8 adds collector work and an audit case. Each "no" adds a Can't tell path and its words. Either way, a late change after task 3 reworks `read_scope.py` and the audit test.
4. Linux CI. M2 and M3 both needed fix commits after the build for tests that passed on macOS. Mode 000 files, symlinks, case-sensitive paths and walk order are the likely repeats. The second fix round in task 20 is priced for it.
5. The differential. The old app's display fields, attention rules and fixture contexts surface quirks the first time they're compared, each needing an allowed-difference entry and a reason. Task 5 at high carries this.
6. Setup speed. Stat signatures over large plugin caches and a big project walk may miss 20 ms. A cache would be new work, and task 10 asks first.

Stop line. The lead stops and reports before starting the next task once build spend passes $250 on the full plan, or $210 on the trimmed plan.

## 13. Risks and leftovers

### Leftovers M4 depends on

1. `to_fix_count` has been null since M1 (`store_provider.py:877`, `:903`). Task 9 fills it.
2. The ingest's unreadable transcripts were promised as To fix rows (m1-build.md section 4). Task 9 adds them as `transcript_unreadable`.
3. The managed `modelPricing` layer has been dormant since M1 (m1-build.md section 11). Task 4 wires it.
4. The M2 model check passes no `local_path` or `plan` (`model_check.py:161-170`). Task 3 adds both, which can change Model check on Live and Review for a worktree project or an API-key plan. The differential and the M2 and M3 oracles show any change.
5. "See why" is hidden on Live, Agents names are plain, and plugin agents read as an unknown source (m2-build.md section 12, m3-build.md section 2). Task 16 links them.
6. The setup routes exist as placeholders in `app/web/src/app/router.tsx:122-125`, and the nav already lists them.
7. The item shape was meant to freeze in M1 (plan.md section 7), but `models.py` has no setup model yet. Task 0 writes it.
8. `app/server/tests/test_port_collect_overlay.py` has 15 tests against the old file's 19. Task 1 says whether four were dropped on purpose.
9. Real mode reports an empty `claude_version` (`store_provider.py:1031`). M5 owns it.

### Risks

1. Secrets on screen. Hooks, MCP env, headers and args are new places for secrets, and the old mask knows six words and two prefixes. The 26-07 rules, the sweep test and task 8 at high are the guard.
2. Reads beyond the owner's rule. Every new collector is a new way to open a file. One read path and the audit test with decoys are the guard.
3. Formats that drift. Plugin and `~/.claude.json` shapes can change with Claude Code. Readers tolerate unknown fields and report an unknown version as Can't tell, never as a broken page.
4. Big trees. A monorepo walk or a large plugin cache can be slow. The walk caps and task 10 bound it.
5. Agents can't see real formats. Every fixture is made up from docs. The owner's first real start shows gaps, and question 10 option B is the fallback.
6. Two leads. M4 runs in its own worktree. The designer passes are drawing only and touch no file in `app/`.
7. Budget. Section 12's honest range sits about three times above plan-a's. The stop line holds it.

## 14. Designer review focus

The designer's review of this plan should look at these, against the picked direction.

- Section 5's fields. Whether every item kind, state and fix kind in section 9 has the data it needs.
- The inspector's `facts` per part, and whether the simple view and the raw view split the way usability lesson 22 asks.
- Items that become editable in M6 shown with no Edit and no lock.
- The Couldn't read card over partial results, and the setup map row for a part with an unreadable file.
- "Not visible here" for the Command line and the shell line from question 9.
- To fix with no editor actions until M6, and the Copied announcement.
- The Agents inspector beside the narrowed table, and the same item at its setup route.
- No search on setup lists in M4, and how a 200-rule list reads without one.

## 15. Owner answers, November 9

The owner took every pick in section 11 (all A). This section overrides anything above that disagrees with it.

1. A. The main session dispatches designer passes 10 to 12 and the plan review at medium now. Tasks 0 to 10 and 13 run beside them. Tasks 12 and 14 to 17 and the pass changes to 13 wait for the owner's design pick and the review notes.
2. A. Every new read inside the M2 roots in section 7 is allowed, the capped nested walk included. Bodies are read in memory and never sent.
3. A. `<config>/plugins/` only. An install path outside it is Can't tell with "not read here".
4. A. The masked `~/.claude.json`, three key groups only, read on demand when its stat signature changes. Nothing reads it in the background.
5. A. The exact ancestor file names (the repo-root `.claude/settings.local.json`, CLAUDE.md and CLAUDE.local.md), stat first, with the git root found by `.git` alone.
6. A. Imports outside the roots are listed as not read and never opened.
7. A. Single-file symlinks are followed and show their real path. Symlinked folders out of the roots are not.
8. A. No auto memory.
9. A. The shell environment as M2 had it, with confidence `assumed` and the "when Bar Tab started" line.
10. A. Plugin fixtures are made up from the docs and this repo's own payloads.
11. A. The full build, $171 to $270. The lead stops and reports before the next task once build spend passes $250.

M3's CI run on `feature/bartab-m3` (42741546511) ended cancelled, with no fix commits on that branch, so nothing was merged before task 0.

## 16. Designer plan review folded in, November 9

The designer reviewed this plan at medium and reported 29 UX needs. This section overrides anything above that disagrees with it. The contract changes are already in the "Setup (M4)" block of `app/server/models.py`, and tasks 4 to 9 build to it. Two owner questions are pending, whether the full path shows on screen (need 15) and plugin agents that share a user agent's name. The contract serves either answer.

### Changes to the answers

| Need | Change |
|---|---|
| 1. Switch with no flash | `SetupPartRow.scopes` is always in `/api/setup`, so flipping the Switch fetches nothing. `?scopes=1` stays as page state in the URL only |
| 2. Map summaries | `SetupPartRow.summary.params` carries what the drawn summaries use (effective model and effort, agents with no recent runs, on-demand globs). `SetupPartRow.empty` gives the empty or not-visible reason on the map row |
| 3. Shell line | `SetupMap.server_started_at` dates the shell scope ("when Bar Tab started") |
| 4. Value that runs | `SetupItem.effective {value, origin, by_item}` with `origin` `set`, `cap`, `default` or `unknown`. The page never parses `reason.params` |
| 5. Key per source | `SetupSource.key` names what sets it there (`effortLevel`, `env.CLAUDE_CODE_EFFORT_LEVEL`, `--effort`, a front matter key) |
| 6. Possible scopes | `SetupItem.reach[] {scope, visible}`. A Command line entry appears only for a key with a flag. Shell and Command line are `visible: false` |
| 7. Linked items | `ItemReason.ref_item` and `Effective.by_item` carry the other item's id (the cap that lowers a value) |
| 8. Rule and version | `Confidence {level, tested_on}`. `ItemReason.rule_id` |
| 9. Stable ids | `id` is `<part>:<key path>` with no scope, readable and stable when a value moves between scopes. `agents:<name>` is shared by `setup/agents/<name>`, Review, Live's "See why", refetches and the URL |
| 10. Unknown keys | `SetupItem.key` and `label_known`. The closed-enum test covers codes, parts and scopes, and skips open-ended settings keys, which fall back to the raw key |
| 11. Facts per kind | `ItemFacts` with one typed member per kind. Skills give description, the slash form with the plugin namespace and `legacy_command`. Permissions give kind (allow, ask, deny, default mode, extra folder), tool and pattern. Plugins give version, marketplace, enabled per scope, orphaned versions and `contents` as item ids. Output style gives the active style and whether it is built in |
| 12. Imports | `ImportRef {target, target_item, depth, state, line}`, with `state` `read`, `missing`, `cycle`, `too_deep` or `not_read` kept apart |
| 13. Masked flag | Every value that can hold a secret is `MaskedText {text, masked}`. That covers source values, hook commands, MCP command, URL, args, env and headers, agent fields and the read-only command |
| 14. Read-only help | `ReadOnly.command` holds the `claude mcp` command for user and local MCP servers. For plugin items `params` names the plugin, and the page words how to change it |
| 15. Full path | `full_path` beside every display `file` (sources, unreadable files, problem rows). Pending the owner, the page can show it or keep it for Copy path only |
| 16. Order | `SetupItem.order` repeats the part's own order (load order, top-wins order, hook event order, then name). Refetches never reorder rows |
| 17. Unreadable detail | `UnreadableFile.scope` and `problem` (the To fix row id). `SetupItem.may_change` flags items whose answer a failed file could change |
| 18. Not read here | `SetupItem.not_read` (`outside_scope` or `plugin_outside_plugins`) is its own state, apart from Couldn't read and Unknown, and `outside_scope` reaches the API |
| 19. Groups | `SetupItem.group` and `SetupPartAnswer.groups[] {key, count}` in order. Permissions group by kind then scope, hooks by event, and agents add a "No runs yet" group from the store |
| 20. Empty actions | `EmptyInfo {reason, action, target}`, where `action` is `docs` with an anchor URL or `copy_path` with a folder path |
| 21. Problem rows | `ProblemRow.id` is stable, and `thing` is the display name the title names |
| 22. Copy path | `FixKind` gains `copy_path` |
| 23. One count | `AppInfo` gains `to_fix {state, count, etag}`, built from the same cached problems pass as `/api/problems`, whose etag it repeats. `state` is `ok`, `unchecked` or `failed`, so "couldn't check" is its own state. The page refetches the app answer when the problems etag moves. Task 9 adds it and keeps `to_fix_count` for M1's tests |
| 24. Plugin name | `AgentFacts.plugin` on the item, and task 9's Agents rows carry `plugin` beside the widened `scope` |
| 25. Agent inspector | Both routes read the same `agents:<name>` item from `/api/setup/agents` for every setup line. Cost, runs and Ran with come from `/api/agents`, over the page's range on `review/agents?agent=`, and over 30 days on `setup/agents/<name>`, where the label states the range |
| 26. Ignored fields | `AgentField {name, value, line, ignored}`, so an ignored field keeps its value and line |
| 27. Vanished item | Page only. Focus lands on the unknown-item sentence's link (tasks 15 and 16) |
| 28. Phone back link | Page only. The back link returns focus and scroll to the item by its id in the URL (task 15) |
| 29. Accessible text | Section 10's exact accessible text and snapshot lists add a masked value, a "not read here" item and the Couldn't read card (task 17) |

### Kept as the plan has it

One read path with partial results, per-scope state, Overridden never counted, `writable: false` with a null reason, no body text, `item_id` on Agents and Model check rows, the limited fix kinds (now with `copy_path`), the states and events tables, the Switch in the URL, etags, and the three extra demo projects.

### Copy for task 12

The raw-key fallback, the masked-value line, "not read here" with its plugin case, the empty-state actions, and "couldn't check" on the nav.

### Owner answers to the review's two questions, November 9

1. Paths. The short display path stays on screen, and Copy path copies the full local path. Every item, unreadable file and problem row carries both `file` and `full_path`.
### Task 1 results, November 9

- The old `api_settings.settings(server.fixture_context(folder, None, None, rules, fields), {})` runs in process on any resolution folder as it is. With no `routing-dashboard.json`, the old `projects.load` makes the folder's project implicit. The scout ran it on three folders, one with no `config/` and one with no `session.json`. Task 5 uses this path.
- The ported `agent_frontmatter.py` reader rejects hyphenated keys (`allowed-tools`, `argument-hint`, `disable-model-invocation`), nesting deeper than one level (the docs' hooks example) and an unquoted colon in a value. So SKILL.md front matter as the docs write it fails that reader, and so would an agent with nested hooks. `ruamel.yaml` 0.19.1 has been locked since M0 (`app/pyproject.toml:9`), so M4 parses front matter for display with `ruamel.yaml` in safe mode and adds no package. The agent statuses still come from the ported resolver, which the differential compares with the old app. A file the strict reader rejects but YAML parses gets a Can't tell row rather than a false Won't load.
- `test_port_collect_overlay.py` has 15 tests against the old 19. The four missing (two in `NoOverlay`, two in `Structure`) test old `api_settings` paths the port doesn't have, and its docstring says they were left on purpose. It says six, and the count is four, so task 4 fixes the docstring.
- The top-level shapes of `installed_plugins.json` and `known_marketplaces.json` are not in the docs. Task 6's reader tolerates unknown shapes and reports them as Can't tell (`plugin_format_unknown`).

Docs facts the collectors build on, read on November 9 from code.claude.com with anchors checked against the rendered ids. Page names are under `https://code.claude.com/docs/en/`.
- CLAUDE.md (`memory`). Load order is managed, `~/.claude/CLAUDE.md`, then `./CLAUDE.md` or `./.claude/CLAUDE.md`, then `./CLAUDE.local.md`, broadest first. Managed is `/Library/Application Support/ClaudeCode/CLAUDE.md` on macOS and `/etc/claude-code/CLAUDE.md` on Linux. CLAUDE.md and CLAUDE.local.md load from the working folder and every folder above it to the filesystem root, root content first. Subfolder CLAUDE.md files load on demand. Imports are relative to the importing file, at most four hops, skipped in code spans and fenced blocks, not taken from a quoted path. Block-level HTML comments are stripped. `claudeMdExcludes` holds absolute-path globs, merges across layers and can't exclude the managed file. `AGENTS.md` is read directly only when no CLAUDE.md, CLAUDE.local.md or `.claude/CLAUDE.md` exists in the working folder or above (v2.1.277 and later), which is `loads: when_no_claude_md`.
- Rules (`memory`). `.claude/rules/` is read recursively, and `~/.claude/rules/` loads before project rules. Only `paths` is read from front matter, as a YAML list or a comma-separated string. Bad YAML loads the rule with no paths. No `paths` means it loads at launch.
- Skills (`skills`). Places are managed, `~/.claude/skills/<name>/SKILL.md`, `.claude/skills/<name>/SKILL.md`, nested `<subdir>/.claude/skills/`, `--add-dir` folders (not visible here) and plugin `skills/`. Legacy `.claude/commands/*.md` still works. Plugin skills are invoked as `/plugin-name:skill-name`. On a clash managed beats user beats project, and a skill beats a command file.
- Plugins (`plugins/loading`, `plugins-reference`, `sub-agents`). `installed_plugins.json` sits under `~/.claude/plugins/` unless `CLAUDE_CODE_PLUGIN_CACHE_DIR` moves it, and each install has `scope`, `installPath` and `version`. With owner answer 3 a moved cache folder is outside `<config>/plugins/`, so it reads as `plugin_outside_plugins`. `known_marketplaces.json` entries have `source`, `installLocation`, `lastUpdated` and `autoUpdate`. `enabledPlugins` maps `plugin@marketplace` to a Boolean. The cache is `cache/<marketplace>/<plugin>/<version>/`, and an old version folder holds `.orphaned_at`. `plugin.json` needs only `name`. Its `skills` adds to the default folder while `agents`, `commands`, `hooks`, `mcpServers` and `outputStyles` replace theirs. A plugin's `settings.json` keeps only `agent` and `subagentStatusLine`. Plugin agents ignore `hooks`, `mcpServers` and `permissionMode`.
- Hooks (`hooks`). Event, then matcher group, then handlers. Places are user, project, local, managed, plugin `hooks/hooks.json`, skill and agent front matter. There are 33 events, and the collector takes the list from the page, not this summary. Handler types are `command`, `http`, `mcp_tool`, `prompt` and `agent`. In agent front matter `Stop` becomes `SubagentStop`. `disableAllHooks` can't turn off managed hooks unless it is set in managed settings, and `allowManagedHooksOnly` keeps managed, SDK and force-enabled plugin hooks.
- MCP (`mcp`, `managed-mcp`, `settings-reference`). No `type` means stdio. `http` (alias `streamable-http`), `sse` and `ws` take `url` and `headers`, and a `url` with no `type` is an error. `${VAR}` and `${VAR:-default}` expand in command, args, env, url and headers. Local servers sit in `~/.claude.json` under the project's path, user servers at its top level, and project servers in `.mcp.json`. On a name clash local beats project beats user, with no field merge, and `managedMcpServers` beats all. Approvals are settings keys. `enabledMcpjsonServers` and `enableAllProjectMcpServers` are written to `.claude/settings.local.json`, and `disabledMcpjsonServers` counts from any settings file. `managed-mcp.json` sits in the managed folder.
- Output styles (`output-styles`). User, project (nearest wins), managed and plugin `output-styles/` folders. Front matter `name`, `description`, `keep-coding-instructions`, `force-for-plugin`. Built-ins are Proactive, Concise, Explanatory and Learning, case-sensitive, and a wrong case falls back to Default. `/output-style` writes `.claude/settings.local.json`.
- Permissions (`permissions`, `settings-reference`). A rule is a bare tool name or `Tool(specifier)`, with `*` wildcards and `:*` as an alias. `defaultMode` is `default` (alias `manual`), `acceptEdits`, `plan`, `auto`, `dontAsk` or `bypassPermissions`, and the last two are ignored from project and local settings. `additionalDirectories` lists extra folders.
- Managed folder (`managed-settings`). `managed-settings.json`, `managed-settings.d/*.json` (alphabetical, hidden and non-JSON files ignored), `managed-mcp.json`, `CLAUDE.md`, and `.claude/skills/`, `.claude/agents/` and `.claude/output-styles/` inside it. All of these sit in the managed root that owner answer 2 allows.

With these facts the `~/.claude.json` reader keeps two key groups, top-level `mcpServers` and `projects[<listed project's real path>].mcpServers`. It also keeps that entry's approval keys when a file still has them, because older files may, but settings are the documented source.

### Owner answers to the review's questions, continued

2. A plugin agent that shares a name with a user or project agent is a separate item, named under its plugin. Its id is `agents:<plugin>:<name>` and its route is `setup/agents/<plugin>:<name>`, while the file agent keeps `agents:<name>`. Agent names hold no colon, so the two forms never collide. Task 6 builds both items, and task 9 keeps them apart in `/api/agents` and in Live's "See why" link, matching each run's agent type to the item it names.

### Build results so far, November 9

- Task 3, read scope and masking. `read_scope.py`, `masking.py` and `git_root.py` are in, with the audit child and helpers. The model check now reads the repo-root local file through the scope as overlay bytes and takes the plan from `projects.load_plan`. Server suite 3546 passed, 1 skipped. Coverage is read_scope 95, masking 100 and git_root 92 percent.
- Lead change after task 3. The `.claude.json` path no longer depends on which files exist. The default config folder reads `<home>/.claude.json`, and a moved config folder reads only its own copy, because Claude Code ignores the home file when `CLAUDE_CONFIG_DIR` is set (research 26-08 line 9). Scope tests 53 passed.
- Task 13, wave 4 components. Vitest 2508 passed, and typecheck, lint, lint:css and format are clean. The sheet spec with axe passed 10 of 10.
- Task 2, setup corpus. 18 cases, `secrets.json` and a demo overlay of 77 files, all under `app/fixtures/setup/`. `build_corpus.py --check` is ok and 76 corpus and home-path tests pass. Only `complex` and `stress` have generated answers, and the rest are hand-written. The worker added `broken-claude-json-entry` because one file cannot hold bad JSON and a bad project entry at once.
- Corpus decisions changed by the lead. Settings always carries `model` and `effortLevel` items, because the setup map links to them (task 4 updates `empty` and `simple`). A plugin install path outside `plugins/` uses the code `plugin_outside_plugins`, and a file that ruamel parses but the strict reader rejects uses `frontmatter_reader_gap` (task 6 updates both).

## 17. Owner picks for passes 10 to 12, November 9

The owner picked the M4 designs with every recommendation. The board source now sits in `docs/design/redesign-a/` (`m4.html`, `m4.js`, `m4.css`, `strings-m4.js`), copied from the design archive as M3 did. `strings-m4.js` is the copy base for task 12, and its header lists the designer edits. The labels "Tool" and "Matches" (`pm_f_tool`, `pm_f_match`) still need tech-writer review. The designer plan-review needs in section 16 still apply.

### Owner decisions

1. With the Switch on, Your setup shows scope chips, option B (`p10-scopes-chips`), not seven scope columns. Task 15.
2. A project that is not on Bar Tab's list reads "Not read here" in its project scopes, with a notice and a "How a project gets on the list" link. `SetupMap.listed` is in `models.py`. Task 9 adds `Project.listed` to `/api/projects` with the OpenAPI and `schema.d.ts` update, because the field changes the committed schema. Tasks 15 and 16 show it.
3. At 1440 with no item in the URL, the page picks the first item that needs a look, or else the first item. Task 15.
4. At phone width the list is the page, and the inspector opens as its own page with a back link. Task 15.
5. Long lists are grouped (permissions under Deny, Ask first and Allow), with Jump to chips and Show n more. Chips appear only on exceptions. Task 15, and the collectors already set `group`.
6. Ancestor CLAUDE.md and CLAUDE.local.md files are read all the way up to the filesystem root, as Claude Code does. This is the scope of ancestor reads under question 5, and `read_scope.py` already walks to the root. They show as "Parent folder" under Shared project, through `SetupSource.location` and `SetupItem.location` set to `parent`. The "Not read here" parent row (`nr_parent`) is dropped. Task 7 sets `location`.
7. Couldn't read rows on To fix offer Copy path, with the `copy_path` fix kind and `full_path` as the target. Task 9.
8. A user MCP server with no command or URL offers a Copy command for `claude mcp remove <name> -s user`. Bar Tab only copies the command and never runs it. Task 8 sets `ReadOnly.command`, and task 9 puts it in the `copy_command` fix.

### Copy decisions for task 12

- `fx_sub` gets a singular form.
- `ro_plugin` ends "so Bar Tab leaves them as they are".
- `sp_sub_perms` reads "Which tools Claude can use, and which need a yes first".
- `sc_shell_2` reads "Seen at {time}, when Bar Tab started", with `SetupMap.server_started_at` from need 3.

### Designer data needs and where they land

- The listed flag. `SetupMap.listed` now, `Project.listed` in task 9.
- A location for ancestor files. `location: parent`, task 7.
- A Can't tell row for imports outside the roots. `import_out_of_scope`, task 7, as the corpus has it.
- Command-line sources. `reach` with `command_line` and `visible: false`, tasks 4 and 6.
- `copy_path`. In `FixKind` and `EmptyAction`, task 9.
- The skill description. `SkillFacts.description`, task 7.
- Hook event words and the masked placeholder shape. `HookFacts.event` and `MaskedText`, task 8, with the words in task 12.
- The server start time. `SetupMap.server_started_at`, task 9.

## 18. Build results, continued

- Task 4, Settings, Permissions and Output style. `collect_settings.py`, `collect_permissions.py`, `collect_output_style.py`, `settings_layers.py` and `setup_items.py` are in. `collect.py` takes an optional file access, so the setup path opens nothing outside `read_scope`. The managed `modelPricing` reaches the price feed through `ManagedPricing`. Server suite 4088 passed, 1 skipped, with the M2 oracle and the M3 differential unchanged. The 122 resolver folders give equal entries. Coverage is 95 to 100 percent per module.
- Task 4 decisions the lead kept. A user value the resolver calls `ignored` shows as `overridden` when a higher file scope wins, so `typical` stays clean. Permission rules group by raw text and mask afterwards, so two secret rules never merge. Command line reach comes from `resolve.FLAGS`. `UnreadableFile.part` is now in `models.py` so one collector can feed several parts.
- Task 5, the Settings differential. The recorder writes 127 old answers (5 demo projects and the 122 resolver folders) under `app/fixtures/oracle/settings/`, byte-stable over two runs. The differential compares entries, rows, files and attention per section 6. It allows 7 kinds of difference, each with a pinned count: `unparsed-file`, `json-error-line`, `ignored-beaten`, `default-unknown`, `default-only-row`, `plain-key` and `missing-folder`. Three new answers were wrong (a non-winning unknown source with no row, an env override plain items ignored, and a merged list shown as one file's list). They sit as strict xfails, and task 4 is fixing them.
- Task 5 decisions the lead kept. Agent entries are not compared, because the M3 pin differential owns them. A listed project whose folder is missing still shows user and managed settings. The committed payloads come from the system Python 3.9 as before, and a trailing-comma error line differs on 3.13.
- Task 7, Skills, Instructions and Rules files. `collect_skills.py`, `collect_instructions.py` and `front_matter.py` (ruamel safe mode, never raises, key lines and error line) are in. Ancestor files carry `location: parent`. 230 tests across its files, coverage 97 to 98 percent. Imports follow a hop limit of 4, skip code spans and fenced blocks, and a diamond import is no cycle. AGENTS.md loads only when no CLAUDE.md or CLAUDE.local.md exists (research 26-02). A stopped walk is one Can't tell row from the instructions part. Skill precedence goes by scope first, then a skill before a command, marked assumed. A follow-up applies `claudeMdExcludes`.
- Task 6, Agents and Plugins. `collect_agents.py`, `collect_plugins.py`, `agent_files.py` and `problem_rows.py` are in. 147 tests, coverage 95 to 99 percent. A plugin agent is its own item `agents:<plugin>:<name>`. Plugin agents that set hooks, mcpServers or permissionMode give Not as set rows (`plugin_field_ignored`). The strict-reader gap is `frontmatter_reader_gap` at confidence assumed. The plugins handoff carries skills, commands, hooks and MCP lists, plugin output styles, and the full component list. Plugin items stay at confidence assumed until a real `installed_plugins.json` shape is checked. Open: the resolver still opens agent and settings files with a plain open inside the allowed roots, not through `read_scope`.
- Task 8, Hooks, MCP and the masked `.claude.json` reader. `claude_json.py`, `collect_hooks.py`, `collect_mcp.py`, `mcp_entry.py`, `command_mask.py`, `json_lines.py` and `plugin_inputs.py` are in. 325 tests, coverage 97 to 100 percent. The reader decodes only `mcpServers`, the listed project entry and its approval keys, and caches by stat signature. Hooks follow the docs' 33 events in page order. `command_mask.py` masks free-text commands. User and local MCP servers are read-only with the matching `claude mcp remove` command. Codes follow the plan list (`hook_bad_event`, `hook_bad_handler`, `mcp_bad_entry`, `env_not_visible`, `hooks_disabled`).
- Task 8 fix round, running. It masks hook commands inside the Agents part's hooks field (a leak a strict xfail pinned) and lists skill front matter hooks. Plugin MCP servers always get `mcp:<plugin>:<name>`, and `disabledMcpServers` counts as an approval key. Workspace trust is not modelled.
- Task 8 fix round, done. Agent hook commands and URLs are masked inside the Agents part, nested past 12 levels hidden whole. Skill front matter hooks are listed after agent hooks, and plugin skills keep theirs (hooks docs, "Limits on skill hooks"). Plugin MCP ids are always `mcp:<plugin>:<name>`. `disabledMcpServers` turns off user, local, plugin and managed servers, never project `.mcp.json` ones, with the reason code `mcp_not_approved` and `params.by`.
- Task 9, the setup answers, problems feed and API. `setup_answers.py`, `problems.py`, `setup_codes.py` (the code registry and closed-enum test), `setup_store.py` and `api_setup.py` are in, with `/api/setup`, `/api/setup/{part}` and `/api/problems`. `AppInfo.to_fix` and `Project.listed` are added, `AgentScope` has `managed` and `plugin`, and Agents and timeline rows carry `item_id`. OpenAPI and `schema.d.ts` are regenerated. Run counts are lazy, so Agents never triggers a second 30-day scan. The read audit polls every setup route. Server suite 5143 passed, 2 skipped. Coverage is 98 to 100 percent on the new modules. On the stress case `/api/setup` takes 76 ms cold and 11 ms warm.
- Open after task 9. The serve demo flag does not apply the setup overlay yet, and adding it changes the demo project list the M1 to M3 end-to-end tests count, so it lands with task 15. `SetupItem.real_path` is absolute for a symlink target outside the roots and should be a display path. The `setup-empty` demo shows two `ignored` rows for an empty `CLAUDE_CODE_EFFORT_LEVEL`. The empty-state docs anchors are unchecked (fact D-1534).
- Budget stop, November 10. Build spend passed the $250 line after task 9, so the build stopped before task 10 and reported. The owner approved finishing M4 with about $130 more.
- Merge. feature/bartab-m3 (CI fixes 6744f31 and ce3c63f) fast-forwarded into feature/bartab-m4, and the M4 change to `e2e/sheet.spec.ts` was reapplied over the grouped spec.
- Task 10, setup speed. On the stress case every route is 78 to 101 ms cold at p95 and about 15 ms warm, both inside target. A 30-plugin tree is 173 to 196 ms cold, inside target, but about 42 ms warm against the 20 ms target, because the signature walk stats every plugin file. The plan says a miss goes to the owner before any cache work, so the warm test is a non-strict xfail (`WARM_MISSES`) and no cache was added.
- Collector fixes with task 10. `real_path` is now a display path. An empty environment variable the resolver marks ignored (rule `effort-env-empty-ignored`, tested) stays a source but gives no To fix row, and the differential allows it as `empty-variable-is-no-row` (count 6). The user `effortLevel` row on Opus 5.5 is a separate cause and stays.
- Docs links. The empty-state links name pages only, with no anchors, and all nine pages answer.
- Task 12, strings. tech-writer drafted the deck (scratchpad `m4-string-deck.md`), and 539 keys are typed into `en.ts`. `setup-codes.test.ts` fails when a server code has no words. "Tool" and "Matches" stay after review. `WHY_CODES` and the `walk_stopped` cant-fix reason are in `setup_codes.py`. Open for the owner are where "How a project gets on the list" points, and whether main-session usage counts runs or sessions.
- Task 14, data layer. `api/setup.ts` and `lib/setup-routes.ts` are in, and the shell reads `to_fix`. The setup reads take the etag as a query parameter, as Review does. 51 tests.
- Task 15, Your setup and the surface pages. The map with the Switch and scope chips, one surface page for all ten parts with its list and inspector, the Couldn't read card, empty states, auto-pick and the phone list-as-page are in. `serve.py --demo` applies the setup overlay once per build behind `setup-overlay.done`, so the demo has 8 projects. Vitest 4407 passed. `setup.spec.ts` passed 43 of 43, with axe at 320, 375 and 1440 in both themes, forced colours and reduced motion. The older e2e specs pass after one route-name change. Departures: the unlisted-project link goes to the project picker until the owner says where it points, instruction rows have no numbered circles, and the demo has no not-read items, so the spec patches those answers in flight.
- Task 16, To fix and the Agents setup half. The To fix page with every group and fix kind is in, along with the nav count's unchecked and failed names, the Agents inspector beside the narrowed table, plugin and managed rows, and Live's "See why". `tofix.spec.ts` passed 44 of 44 with axe. Departures: a plugin or managed agent's inspector says Bar Tab can't tell what runs, because the resolver doesn't judge those agents, and the notice row is a plain sentence.
- Lead fix after tasks 15 and 16. Permissions now order Deny, Ask first, Allow, per owner decision 5 (task 17). Two DRAFT keys that repeated existing words are removed. tech-writer reviewed the other eight and changed one word (`in_masked_word` is "Hidden"). The All time usage line drops its stray comma.
- Task 17, end to end. `setup-keyboard.spec.ts` (11 tests) and `tofix-keyboard.spec.ts` (5 tests) each passed three runs in a row, with aria snapshots for the section 10 states and need 29. The 1440 auto-pick now writes the item to the URL with replace. No section 10 text differed from the page beyond an aria-hidden arrow.
- Task 18, exit runs, November 10.
  - Server suite: 5150 passed. One warm timing check missed by 0.37 ms and passed alone.
  - Web unit: 4396 passed, and the static checks are clean.
  - Playwright and axe: 400 passed, 3 skipped.
  - Old app suite: 3575 tests OK, 88 skipped, in 369 s.
  - The protected-path diff against ce3c63f is empty.
- Task 19, visual check. There are no blockers in the setup shots. `app/web/dist` was stale, so the judge built to the scratchpad. The should-fix list is below, and task 20 waits for the owner's budget call, because it would pass the stop line.
  1. The agent item's status pill shows load status (In effect), while Model check and the board show Overridden or Lowered. The board's callout ("ran at medium, but its file sets xhigh") is missing on both agent inspectors. This is a correctness gap between pages.
  2. The agent inspector's Where list mixes env and settings layers into the agent's own file rows (7 rows against the board's 2).
  3. Settings shows a flat list with raw keys, not the board's Model and effort and Other settings groups, and Per-model settings prints raw JSON.
  4. Hooks titles show raw `PreToolUse:Bash` instead of plain words, and a matcher breaks mid-word.
  5. A plugin that is not read shows In effect, not the board's Unknown pill.
  6. To fix at 1440 puts the action under the text, not in a right-hand column.
  7. Instructions lack the numbered load order, the mono title and the auto memory note, and the back link says "Back to Instructions".
  8. The Couldn't read card puts Copy path mid-card and adds a group heading.
  9. Agent panels lack the board's footer link and the cost in the run line.
  10. The project picker rows overlap with long paths.
  11. Owner calls: Review cost bars and the 375 tab strip, the Live pill position, the mobile trail pill position, and map pills wrapping.
  12. The map's permissions summary still reads allowed first.
  13. `tofix.spec.ts` has one `patch()` race that fails once and passes on rerun.
- Owner answers, November 10. Accept the 30-plugin warm miss with no cache work. "How a project gets on the list" keeps pointing to the project picker. User plugins showing in every project is expected. The owner ran real data and liked it. Item 11 is fixed to match the board, like the others.
- Deck Q8, open for the owner. `runs_at_value` counts main sessions, not requests. For `@main` a run is the session (`review_query.py`, the `Scan.runs` docstring), and each session counts once under its most-used model and effort pair, ties to the first seen. To count requests, sum each run's `requests` per pair. To count every session that touched a value, `scan` would return each run's full pair set instead of its top pair.
- Task 20, fix round.
  - Part A, agents and plugins.
    - An agent item's status is now the outcome of what runs, judged by `model_check.judge_agent`. `SetupItem.check` carries Model check's reason, and a test over every demo agent and corpus case proves the item and Model check agree.
    - Both inspectors show the callout. The agent Where list shows only the agent's own file rows, filtered on the page.
    - A not-read plugin shows the Unknown pill.
    - The footer links match the board, and the setup run line carries cost.
  - Part B, page visuals.
    - Settings are grouped into Model and effort and Other settings, client side, with a readable per-model summary.
    - Hook rows read in plain words.
    - To fix actions sit in a right column at 1440.
    - Instructions show load order, the auto memory note and the board's back link. The Couldn't read card order matches.
    - Picker rows truncate.
    - The map's permissions summary reads denied first.
    - The `patch()` race is caught. tech-writer reviewed the ten new words, and `hk_nm_PreToolUse` keeps the board's "Before {tool}".
  - Part C, item 11.
    - Review hides cost bars and the 375 tab strip only while an agent is picked. M3's page at rest is unchanged.
    - The Live pill sits inline with the title.
    - The phone trail puts the pill at the right of the scope.
    - Map status pills stay inline. Before and after shots are in the scratchpad's `m4-item11/`.
- Task 21, the last fix round, from the verifier's findings. The owner's test for every call is whether it would be the best choice for usability and security if it shipped tomorrow.
  - The map's permissions summary lists denied first. That departs from the board on purpose, because it is more secure and it matches the part page (owner call, November 10).
  - The corpus `notes/` folders were dropped by a local exclude. The repo `.gitignore` now negates `app/fixtures/**/notes/` and its files, so all seven corpus notes would be added.
  - Model check reads agent files through `read_scope`, the same as the Agents part (`agent_files.find_records`, passed to `collect.collect` as `reuse`). That brings the 1 MiB cap, strict UTF-8 and the outside-scope refusal. A decoy where `.claude/agents` is a symlink outside the roots shows both sides agree (`test_model_check_agents.py`).
  - The settings differential compares agent load statuses with the old answer. Three kinds are allowed and pinned: `agent-not-md` (1), `agent-same-name` (2) and `agent-unknown-field` (1). Two new-side bugs it found are fixed, so KNOWN_WRONG is empty.
    - An unclosed bracket in a description loads, as Claude Code does, with a Can't tell row.
    - A flow-mapping description reads unknown, because the reader gap is checked first.
  - `masking.mask_url` scans in linear time. Its regex was quadratic on long runs of letters, so one 1 MiB line in an agent file took minutes. That line now takes about 2 seconds through the whole Agents part. A property test pins the scan to the old regex.
  - The pill and the headline of an agent name the same cause, both taken from its status and check code. Overridden names the winner, and Lowered names the cap.
  - A lowered agent setting gets an `agent_lowered` To fix row in Not as set, one per lowered setting, with the fix pointing at the cap. Overridden makes none. The corpus case `agents-capped` covers it.
  - The Review link for plugin and managed agents hides only when they have no runs.
  - At 375 with an agent picked, the Review scope bar title is clipped like the tabs, so screen readers keep the heading. The Range select stays.
  - A run is any agent run, the main session included, on every page. Sessions and Agents now count the main session, and a visible note under both tables says so. The old-app differences are pinned with exact-count tests.
  - The Summary Model check line counts k from the same rows as n, without In effect and Default, so k can't exceed n.
  - The launcher test's fake server honours its idle limit, stops after at most 10 minutes, and records its pid so teardown always stops it. The 14-hour stray was this fake, which never had an idle exit. The real server's idle exit was not at fault.
  - The 320 px, forced colours and reduced motion checks now cover the To fix page and the Agents inspector.

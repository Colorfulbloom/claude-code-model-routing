# Judge: coverage matrix (2026-11-08), condensed by main session

Verdict: stack choices well covered (backend, front end, gate, CSP, uv, a11y, rules engine, launcher). The new edit scope is NOT covered.

## Matrix A highlights (current app)
- REPLACE: server.py (FastAPI + ASGI gate), rules_schema.py (Pydantic), agent_frontmatter.py (ruamel + byte-splice fallback), shell/router/api/components/live_poll (React stack), JS tests on fakedom (Vitest), E2E (Playwright + axe), test_server (TestClient).
- CHANGES: api_edit (4 keys only today), api_live, api_settings (split /api/files), api_usage (SQLite), collect (add plugin, skills, hooks, MCP, CLAUDE.md loaders), edit_store (JSON-only, 3 fixed targets, no client path), transcripts (SQLite cursors; supersede/orphan rows transcripts.py:308; late subagent links), usage (tzdata, DST), version, prices, projects, charts, edit UI (11 files, 3,525 lines; inventory said 14), launcher, SessionEnd hook, build_plugins.
- AS-IS: json_edit (object paths only; array edits unverified), local_root, git_check (hardened), reference_page, data files, harness, PreToolUse guard, skill, tokens.css.
- OPTIONAL layer: pincheck/pin-view, Installed files page, installer/agentic setup tests. Out of scope: HiveMind.
- UNDECIDED: fixture/demo run mode (--fixture, tests/fixtures/demo).

## Matrix B (surfaces): read/edit coverage
Covered read: settings (not MDM/HKLM/remote-settings), agents (not managed/--agents/plugin), env (10 vars), model/effort, transcripts. No read loader: CLAUDE.md/memory/@imports, skills, hooks (beyond own), MCP, plugins, output styles, statusLine, permissions, keybindings, credential helpers. Edit covered: settings (4 keys), agents (planned). Risky: ~/.claude.json, hooks, statusLine, apiKeyHelper, MCP stdio commands.

## Matrix C gaps
Read gate (no read token; secrets now exposed via CLAUDE.md/MCP; /docs and /openapi.json exposure; 422 echoing input), per-project keys on one server, no ingest benchmark, transcript format drift, editor widget a11y and CSP, test port plan (3,575 tests, 16,900 .mjs lines), CI none, npm/PyPI supply-chain policy, logging/error envelope, retention vs "index regenerable".

## Ranked gaps
1. Edit architecture for new scope + risk tiers (markdown, YAML, folders, create/delete, symlinks; code-running surfaces). Owner tier decision, then design + spike ~$4-8.
2. Resolution model beyond model/effort (lists merge, memory concatenates, MCP doesn't merge, skills vs agents precedence differ). Scout + judge ~$2-4.
3. Text editor component (CodeMirror-style may inject styles, CSP trap). Scout + CSP spike ~$2-3.
4. Transcript ingest and retention (benchmark on synthetic fixtures ~$2-3; owner decision on retention/location).
5. Read gate and sensitive display (extend spike 1 to GETs/errors ~$1-2).
6. Races with Claude Code writes, esp. ~/.claude.json (~$2).
7. Shared-server lifecycle (SessionEnd, uv SIGTERM) (~$1-2).
8. Plugin collector design (~$1).
9. Setup fixture corpus simple to complex (~$2-3).
10. Optional-layer mechanism (owner). 11. Platform scope macOS vs anybody (owner). 12. Packaging/CI (~$1-2). 13. Preferences location (localStorage per origin, port floats) (owner). 14. Logging/errors (fold into 5). 15. Docs rewrite.

## Contradictions
C1 SSE vs polling (polling wins; is watchfiles still used?). C2 Paraglide vs typed t (owner). C3 Radix/dnd-kit vs React Aria (owner). C4 d3-hierarchy vs DOM cards (D20). C5 server per project (F10, F23 B4) vs one server (D20); SessionEnd stop rule no longer fits. C6 DB as regenerable index in plugin data vs history past 30 days (not regenerable; plugin data deleted on uninstall). C7 plugin agent ignored fields 16 vs 19. C8 PEP 723/PyInstaller vs pyproject+uv.lock (D20). C9 macOS-only owner-only vs anybody. C10 localStorage vs server-side preferences. C11 rules engine "as is" vs redesign list. C12 edit UI file count. C13 guard extension may be unnecessary (launcher spawns uv itself).

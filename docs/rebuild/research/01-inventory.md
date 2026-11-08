# Scout report 1: inventory of hand-rolled code (2026-11-08)

Repo: /Volumes/Warehouse/Projects/claude-code-model-routing. No package.json, pyproject.toml, setup.cfg or requirements file. Page CSP is script-src and style-src 'self', so any JS library must be vendored same-origin.

| Piece | path:lines | LOC | Dependents | Replacement category |
|---|---|---|---|---|
| HTTP server class (Handler, Server) | dashboard/server.py:334-608 | 275 | server.py main; 12 test files import server | Web framework |
| Routes table | dashboard/server.py:94-150 | ~57 | routes into api_*.py | Web framework routing |
| Request/response, JSON body parse | dashboard/server.py:358-473, 528-545 | ~135 | every route | Framework request parsing/validation |
| Edit-key auth (Host, Origin, Sec-Fetch-Site, Content-Type, Content-Length, token) | dashboard/server.py:474-527; token 690-693; URL printed 716; api_edit.EditState | 54+ | api_edit.py; write routes | Framework auth/CSRF plus hand check |
| Static files and content types | dashboard/server.py:546-579; CONTENT_TYPES and CSP at 94-150 | 34 | index.html, js, css, strings.json | Static file server |
| Live polling, server | dashboard/api_live.py:528-627 (live()); helpers 90-527 | 627 file | server.py:149 | SSE/streaming or none |
| Live and usage polling, client | static/js/live_poll.js:1-147; app.js:93, 341-490; pages/live.js | ~300 | live.js, app.js | fetch/timer helper or SSE |
| File watching | none; transcripts.py stat signatures 260, 503, 563 | - | Reader | watchdog/watchfiles |
| rules_schema validation | dashboard/rules_schema.py:1-1081 | 1081 | api_edit.py, resolve.py | jsonschema, pydantic (ajv/zod on JS) |
| Transcript JSONL reader and cache | dashboard/transcripts.py:443-760 | 760 file | api_live.py, api_usage.py | No drop-in lib; cache custom |
| Usage, resolver, prices, collect | resolve.py 1893; usage.py 889; prices.py 277; collect.py 465 | 3524 | resolve has 8 importers | Domain logic |
| Edit store, layout-preserving JSON edit | edit_store.py 1158; json_edit.py 495 | 1653 | api_edit.py | No common lib keeps layout |
| Other API modules | api_edit 2179; api_settings 411; api_usage 287; agent_frontmatter 533; pincheck 245; projects 203; git_check 317; local_root 81; version 149; reference_page 171 | - | server.py | Domain logic; front matter could use a YAML lib |
| h.js DOM builder + URL checks | static/js/h.js | 106 | 32 importers | htm, lit-html, Preact; DOMPurify for URLs |
| router.js hash router | static/js/router.js | 142 | 15 importers | Router lib |
| charts.js hand SVG (ring, stackedTokens, hbars, daybars, hatch patterns) | static/js/charts.js | 204 | 6 importers | Chart.js, uPlot, ECharts, Plot, D3 |
| components.js (chip, card, kpi, delta, table3, pageHead, rangeControl, emptyState) | static/js/components.js | 173 | 21 importers | Preact, Lit, Web Components |
| i18n and number/date format | static/js/format.js (t, tn, Intl) | 148 | 35 importers | i18next, MessageFormat, Fluent |
| strings.json + check | static/strings.json 825; tests/test_static_strings.py 152 | 977 | every t() call | i18n resource |
| App shell and boot | static/js/app.js | 634 | index.html | Preact, Svelte, Lit, Vue |
| Edit UI (14 files) | static/js/edit_*.js | 3525 | page modules | Form/state lib |
| Pages | static/js/pages/*.js | ~4050 | app.js | Component framework |
| CSS | tokens.css 135, app.css 944, live.css 196 | 1275 | index.html | No build by design |
| fakedom test DOM | tests/js/fakedom.mjs | 230 | 11 .mjs, 2 .py | jsdom, happy-dom, linkedom |
| Node check files | tests/js/*.mjs | 16900 | test_shell_js.py, test_pages_js.py, test_settings_js.py | node:test, Vitest |
| Python server test launch | tests/test_server.py | 1115 | 12 test files | pytest + HTTP client |
| Python test harness | tests/helpers.py (Sandbox, home guards) | 806 | most tests | pytest; Sandbox project-specific |
| Plugin build | tools/build_plugins.py | 410 | test_plugin_build.py | Packaging |
| Installer | install.py (3.9 gate at 1553) | 1589 | plugin payload | Packaging/CLI |
| Launcher | plugins/routing-dashboard/bin/routing-dashboard (imports fcntl, POSIX only) | 1230 | hooks.json guard; test_plugin_launcher.py | CLI/process supervision |

Totals: dashboard/*.py 12961 lines in 20 files. static/js 10842. CSS 1275. index.html 35. tests/*.py 48946 in 68 files. tests/js/*.mjs 16900. tests/ total 79540 incl fixtures 12793.

Stdlib-only enforcement:
- "Standard library only, Python 3.9" docstrings in server.py:64 and 16 other dashboard modules.
- install.py:1553 Python 3.9 gate (message at 106), mirrored in plugin payload.
- tests/test_plugin_build.py:381-420 test_every_server_import_resolves_inside_the_payload fails on third-party imports in payload dashboard/*.py.
- tests/test_agent_md.py:27-28, 65-68, 79 (agent_md.py only).
- hooks/hivemind_lib.py ships in two plugins (bump both on change).
- Floor 3.9 enforced only at install.py:1553.
- Launcher imports fcntl, so Windows likely unsupported; server.py has a win32 managed-settings path.

# Rebuild stack: current picks and owner decisions (2026-11-08)

Owner: rebuild the Routing Dashboard from scratch, full framework stack. Personal project, owner is the only user. macOS only (Apple silicon, macOS 27.2).

## Owner decisions
- Form factor: local web app (server on 127.0.0.1 plus browser), launched from the Claude Code plugin slash command. No desktop wrapper, no TUI, no Claude Code mods pane for now.
- uv is an acceptable user prerequisite (first run needs network).
- A database is wanted; the app may write files beyond settings.
- React, not Svelte.
- Scope: edit settings AND agent files ("a spot for the user to tweak their setup").
- Node: per-project pin through existing nvm (.nvmrc, Node 22+); no container now. Docker Desktop free tier applies if needed later.

## Judge's picks (from 11, 12, 13 and the judge's synthesis; alternatives in brackets)
- Backend: Python 3.11+, FastAPI + Pydantic v2 + Uvicorn [Litestar]. SSE via fastapi.sse (0.135.0+). Hand-written ASGI gate for Host, Origin, Sec-Fetch-Site, Content-Type, size cap, token; Starlette TrustedHostMiddleware [Litestar CSRFConfig].
- Data: SQLite with WAL, stdlib sqlite3, plain SQL, numbered migrations [DuckDB; SQLAlchemy Core]. Index in ${CLAUDE_PLUGIN_DATA}; backups, edit ledger and preferences outside it.
- Live: SSE plus watchfiles [1 s polling]. HTTP/1.1 six-connection limit noted.
- Edits: port json_edit.py byte splicing and edit_store.py write pattern; agent front matter via ruamel.yaml round-trip with body bytes untouched [byte splicing for scalar fields].
- Front end: React 19 + Vite SPA, no meta-framework [Svelte 5]. Radix Primitives [React Aria Components]. Plain CSS on existing tokens.css [Tailwind v4]. Hand-built SVG charts [Recharts]. TanStack Query [SWR]. Dispatch tree as DOM cards + SVG connectors [React Flow]. dnd-kit + Alt+Arrow buttons [pragmatic-drag-and-drop]. Paraglide JS [i18next]. openapi-typescript [orval]. Hash router (edit token in URL fragment).
- Tests: pytest + xdist + hypothesis; Vitest + Testing Library; Playwright Test + @axe-core/playwright at 375 and 1440.
- Tooling: uv, ruff, pyright [mypy].
- Packaging: stdlib launcher stays (python3 bin/routing-dashboard, behind the PreToolUse guard hook), starts the server with `uv run` on a pyproject + uv.lock; built Vite files ship in the plugin payload [PyInstaller binary].

## Known unknowns flagged by the judge (to spike first)
1. Uvicorn/h11 and the Transfer-Encoding / Content-Length gate.
2. uv offline behaviour after first run; uv run with a multi-module pyproject.
3. Vite + Radix under CSP script-src/style-src 'self'.
4. SSE with several tabs on HTTP/1.1.
5. dnd-kit maintenance status. 6. Hash routing with React Router. 7. Paraglide plurals. 8. ruamel.yaml width/quote behaviour.

## Verifier pass (2026-11-08, Opus) — changes pending owner approval
- Holds: FastAPI (0.162.2, >=3.10, SSE 0.135.0), Starlette 1.10 (>=3.11), httpx2 claim true (add httpx2 to dev deps), SQLite WAL, DuckDB 2.0 limits, CLAUDE_PLUGIN_DATA facts, ruamel round-trip, Vite/Vitest floors, Paraglide plurals (Intl.PluralRules), React Router createHashRouter, openapi-typescript, Docker free tier.
- Wrong: Pydantic 2.14.3 needs >=3.10 not 3.11 (harmless). uv prefers managed Python by default; first run downloads one. Subagent fields also include autoCompactWindow, omitClaudeMd, experimental; plugin agents also ignore initialPrompt (dashboard/agent_fields.json already has all 19).
- Changes proposed: drag -> port band_drag.js as a hook (dnd-kit core stale since Dec 2024; @dnd-kit/react 0.5.3 pre-1.0; fallback Pragmatic DnD 4.0.0 or React Aria DnD). Components -> spike Radix under style-src 'self' (react-remove-scroll injects <style>); consider React Aria as single kit; Base UI 1.9.0 missed option. Live -> polling via TanStack Query refetchInterval by default; SSE spike only (HTTP/2 needs TLS, so no server fixes six-connection cap). Drop TrustedHostMiddleware (port-blind); turn off Uvicorn --proxy-headers / forwarded-allow-ips. Node pin 22.22+ or 24 (React Router 8.5.1 needs >=22.22.0). Packaging: uv run --frozen --project <payload>, UV_PROJECT_ENVIRONMENT under plugin data; built Vite files must be git-tracked (build_plugins.py:153); launcher must locate uv and fail clearly. Dev server needs looser CSP than prod. i18n: Paraglide only if locales planned, else typed t()/tn() over Intl.PluralRules. Charts: hand SVG stands; @visx/pattern if a helper is wanted. ruamel: width large + preserve_quotes, byte-equality check; maintainer PyPI risk, keep byte splicing fallback.
- Still unverified: Uvicorn/h11 Transfer-Encoding gate; offline uv run end to end; Radix under strict CSP.

## Owner, 2026-11-08 after the verifier
- Accepted all four changes: own drag hook (port band_drag.js), components spike Radix vs React Aria, polling default with SSE as spike, drop TrustedHostMiddleware and Uvicorn proxy headers. Smaller fixes accepted with them (Node 22.22+ or 24, uv run --frozen with env under plugin data, tracked build output, dev CSP).
- English only for now: typed t()/tn() over Intl.PluralRules, no Paraglide.

## Spike results (2026-11-08), files under scratchpad/spikes/
1. Edit gate (spikes/1-gate): ports fully to FastAPI 0.162.2 / Uvicorn 0.54.0 with a pure ASGI middleware over scope["headers"]. Required: --no-proxy-headers (else X-Forwarded-* rewrites client and scheme), --http h11, asyncio.wait_for around receive() (short body hangs forever otherwise; 408 after 3 s). Parser refuses some cases first with 400, so tests assert "refused", not exact codes. h11 merges equal duplicate Content-Length (harmless).
2. uv offline (spikes/2-uv): later runs need no network (0.24 s). Recipe: UV_PROJECT_ENVIRONMENT, UV_PYTHON_INSTALL_DIR, UV_CACHE_DIR, UV_TOOL_DIR all under plugin data; UV_PYTHON_PREFERENCE=only-managed; pyproject with [tool.uv] package = false and no build-system; PYTHONPATH=<payload>; uv run --frozen --project <payload> --no-dev; retry online once; match "Failed to download"/"No interpreter found" for a connect-and-retry message; probe uv paths, never auto-install. First run ~82 MB. Local uv is 0.10.2 inside Anaconda.
3. CSP (spikes/3-csp): React Aria Components 1.22.1 passes under the exact strict CSP (dialog focus, scroll lock, popover, tooltip, select, tabs, keyboard and pointer reorder); only its touch-action <style> is blocked (touch only; nonce via csp-nonce meta likely fixes, untested). Radix 1.8.1 silently loses dialog scroll lock and select scrollbar hiding; a per-request nonce (get-nonce setNonce plus nonce prop on Select.Viewport, meta csp-nonce, index.html rewritten per request) fixes it. Gzipped JS: Radix 104 KB, React Aria 159 KB. Verdict: React Aria.

## Owner, 2026-11-08 after the spikes
- React Aria Components is the component kit, including its drag and drop (no custom drag hook, no Radix).
- Plan is on hold at the owner's request.

## Owner, 2026-11-08 after the gap research (files 16-23)
- One edit key per project (one server serves all projects).
- Prices: reprice all history at current rates, as now.
- Pin check: phase 1 only, agent's pinned model and effort vs what actually ran.
- Add a plugin collector (plugin agents and settings).
- Editing scope: settings, agents, rules folders, skills, hooks, CLAUDE.md files, MCP config.
- install.sh and the agentic setup stay separate; the app reads anybody's setup; install-specific features become an optional layer.

## Owner, 2026-11-08 after the coverage matrix, verifier and app audit (files 24, 25, app-audit/)
- Risky surfaces (hooks, statusLine, apiKeyHelper, MCP commands): editable behind a stronger confirm step.
- Platform: all platforms if feasible, otherwise macOS only (research round decides).
- Database lives beside backups and the ledger, outside ${CLAUDE_PLUGIN_DATA}; only rebuildable caches inside.
- Preferences stored server-side.
- Optional routing layer (Installed files, pin check) shown only when a model-routing install is detected.
- Drop Settings Arrange. Needs attention becomes "To fix", without normal overrides. Agents become a catalog that lists agents that never ran.
- Default history range: owner asked what banks do; pending answer.
- Stray empty nonexistent/x deleted (empty dirs only, untracked).
- Research copied to worktree ../claude-code-model-routing-rebuild-docs, branch docs/dashboard-rebuild-research, docs/rebuild/ (uncommitted). Screenshots and spike sources archived at /Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive (outside git).

## Owner, 2026-11-08 after research round 3 (files 26-01 to 26-10): took every recommendation
- MCP local and user scope: the dashboard shows the `claude mcp` command for the owner to copy; it never runs claude and never writes .claude.json. Project .mcp.json is edited directly.
- Symlinked files: write through to the link target.
- Risk tiers: permission allow rules and env are risky (strongest confirm). File rename is held for a later release.
- Platforms: macOS now, with every OS call behind one platform module; Linux next; Windows only with an owner yes.
- Read key added; the page opens with a single-use code swapped for the key (needs a small spike).
- History: 30-day default, presets 7d, 30d, 90d, 12 months, All history, with where All history starts shown on screen.
- Node 24 in .nvmrc; standalone uv 0.13 or later (installed at build start, not now).
- CSP: per-request nonce (covers CodeMirror 6 and React Aria's touch style).
- Approved: commit this research on docs/dashboard-rebuild-research (README index first), start the plan, start design directions for the new screens.

## Owner, 2026-11-08 redesign
- The rebuild is a full UI and UX redesign, not the old app on a new stack. The panel plan's parity framing is rejected (docs/rebuild/planning/plan.md needs re-planning around the picked direction).
- Live is where the owner spends about 90% of their time; Agents, Sessions and Models are the other useful pages; Overview stays as a review view.
- Picked redesign direction A "Timeline" (boards in /Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/design-redesign/). Revisions requested: Summary cost-per-day paging, Models bars in model colors, dark-mode subtle surfaces for Live sub-sections.
- Owner: Live is the home page. Keep a separate Summary page under Review.
- Owner: Agents is one page under Review, as drawn in A (usage and setup together). Owner loves the revised Models page (model colors plus kind patterns in 'What the cost is made of').

## Owner, 2026-11-08 plan-a decisions
- All planner picks in docs/rebuild/planning/plan-a.md accepted (O1, O2, O6 to O15, D1 to D10) and the agent-edit picks A1 to A5, except:
- O3 Product name: choose a new, less technical name now (in progress).
- O4 Today preset: add Today to the range presets.
- O5 Narrator: "the dashboard" for now; may change with the new name.

## Owner, 2026-11-08 pricing source
- Prices update automatically, not with app releases. Order of use: the user's Claude Code `modelPricing` rates; then LiteLLM's model_prices_and_context_window.json (raw.githubusercontent.com/BerriAI/litellm/main), fetched once a day, Anthropic provider rows only; then the last good copy; then a bundled dated copy for a new offline install.
- Checks before using a new copy: parses, every current Claude model present, prices in range after per-token to per-MTok conversion, cache read about 10% of input. A failed check keeps the last good copy.
- OpenRouter's public models list is a daily cross-check; a disagreement on input or output price shows a warning.
- Every cost is labelled an API-rate estimate with "Prices as of {date}". Subscribers get a help line that the figure is not their bill (Claude Code costs docs).
- No scraping of Anthropic's pricing page and no repo-side price feed job. simonw/llm-prices is not a source.
- Evidence: scout research November 8 (LiteLLM matched Anthropic's page on all 10 current models; same-day updates for Opus, Sonnet and Haiku 5.5 launches).
- Agent add and edit use layout C, a page with tabs and the agent file beside it.

## Owner, 2026-11-08 name
- Product name: Bar Tab. Tagline: "Watch every agent run in Claude Code, see what it costs, and tune the setup behind it." Plugin id and command: `bartab`, `/bartab`. Listing line: "Bar Tab, a plugin for Claude Code."
- Anthropic's Claude Code legal page bars "Claude Code" in a product name (code.claude.com/docs/en/legal-and-compliance), so it appears only in descriptive text. No Claude or Anthropic logo, no "official" near Claude, no "claude" in the marketplace or repo name.
- Narrator in UI copy stays "the dashboard" or writes around it; "Bar Tab" names the product only.
- Clash check November 8: no Claude Code plugin uses bartab; bar and hospitality apps use BarTab; a live BARTAB mark in Class 39 only; software marks dead. A USPTO search is due before any public launch. "Agent Bar" is a nearby Claude Code menu bar app, so avoid "Agent" in the name.
- On phone, the app's tab bar hides on the agent form pages; leave through "← Agents".

## Owner, 2026-11-08 agent form
- Agent add and edit is a full page with no tabs (boards a-dir-full-*): routes #/review/agents/new and #/review/agents/<name>/edit, sticky top bar with Cancel and Preview, stacked sections (Role and model, Name and details, Tools and options, System prompt), sticky side column with the agent file and Jump to. Supersedes the side rail and the tabbed C draft.
- Role presets fill real fields only; "Set by {role} on Tools and options" shows the two lines not shown elsewhere; Custom after a change; role is never saved.
- Edit uses the full model list with relative price words, same as new.
- The selected state (--select-bg, 2px accent edge, "✓ Selected") is the standard for every selectable component.

## Owner, 2026-11-08 N1 and N2
- N1: keep the data folder `<config>/routing-dashboard/` through release 1, so the old app and Bar Tab share backups and the ledger; move it one release later with a migration.
- N2: "Can start other agents" off leaves `Agent` out of `tools` when the agent's tools are limited, and adds `Agent` to `disallowedTools` when the agent has every tool (tools omitted). Both are documented in code.claude.com/docs/en/sub-agents. plan-a.md N2 and components.md follow this rule.

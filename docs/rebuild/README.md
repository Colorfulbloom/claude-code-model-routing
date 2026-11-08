# Routing Dashboard rebuild research

This folder holds the research for a from-scratch rebuild of the Routing Dashboard, done on November 8, 2026. It covers what the current app does, which stack to rebuild it on, and the gaps the new editing scope opens. `research/20-decisions.md` is the source of truth. Its sections run in the order the decisions were made, so a later section overrides an earlier one.

## Current stack

These are the final picks in `research/20-decisions.md`. Earlier picks it overrides are left out.

- Backend: Python 3.11 to 3.14 (pinned below 3.15), FastAPI, Pydantic v2 and Uvicorn (`--http h11`, `--no-proxy-headers`), with a hand-written ASGI gate. No TrustedHostMiddleware.
- Access: a read key plus one edit key per project, since one server serves every project. The page opens with a single-use code swapped for the key.
- Data: SQLite with WAL through stdlib `sqlite3`, plain SQL and numbered migrations. The database sits beside the backups and the edit ledger, outside `${CLAUDE_PLUGIN_DATA}`. Only rebuildable caches go inside it.
- Live data: polling through TanStack Query `refetchInterval`. Server-sent events (SSE) stay a spike.
- Front end: React 19 and Vite as a single-page app, with no meta-framework. It uses React Aria Components, drag and drop included. It also uses plain CSS on `tokens.css`, hand-built SVG charts, TanStack Query, `openapi-typescript` and a React Router hash router.
- Text editor: CodeMirror 6.
- Content Security Policy (CSP): a per-request nonce.
- Strings: English only, typed `t()` and `tn()` over `Intl.PluralRules`.
- Edits: a port of the `json_edit.py` byte splicing and the `edit_store.py` write pattern. Agent front matter goes through a `ruamel.yaml` round trip with a byte-equality check, and byte splicing is the fallback.
- Tests: pytest, xdist and hypothesis; Vitest and Testing Library; Playwright Test with `@axe-core/playwright` at 375 and 1440.
- Tooling: standalone uv 0.13 or later, ruff and pyright. Node 24 in `.nvmrc`.
- Packaging: the stdlib launcher stays behind the PreToolUse guard hook. It runs `uv run --frozen --project <payload>` with the environment under plugin data. The built Vite files are git-tracked in the plugin payload.
- Platforms: macOS now, with every OS call behind one platform module. Linux is next, and Windows waits for an owner yes.

## File index

Some early files (02, 03 and 11 to 15) contain picks that `20-decisions.md` later overrides. They are still worth reading for the evidence behind each pick.

### Decisions

- `research/20-decisions.md`: what did the owner decide, and what is the current stack?

### Inventories and audits

- `research/01-inventory.md`: which parts of the current app are hand-rolled, and what could replace each one?
- `research/10-features.md`: what does the current app do, page by page, and what does a rebuild have to keep?
- `research/24-coverage-matrix.md`: does the research cover the stack and the new edit scope, and where are the gaps?
- `app-audit/architecture.md`: how is the current app built, file by file?
- `app-audit/design.md`: how does the current app look and behave, and what should the rebuild change?

### Stack research

- `research/02-python-frameworks.md`: which Python web frameworks and distribution options fit?
- `research/03-frontend-and-libs.md`: which front-end, charting, Python helper and test libraries fit, and how big are they?
- `research/11-form-factor.md`: should the app be a local web app, a desktop wrapper or a terminal UI?
- `research/12-backend.md`: which backend framework, gate and live-data approach fit best?
- `research/13-frontend.md`: which front-end framework, components, styling, charts, drag and drop, i18n and tests fit?
- `research/14-containers.md`: is a containerized dev setup needed, and what is on this machine?
- `research/15-database-agentfiles.md`: which database fits, and how do we edit agent files safely?

### Gap research

- `research/16-data-sources.md`: where does usage data come from, and which sources are optional?
- `research/17-sharing-setups.md`: how do people share agentic setups, and what can a plugin carry?
- `research/18-config-surfaces.md`: which config surfaces does Claude Code have, and how do the scopes combine?
- `research/19-launcher.md`: how should the launcher start, find and stop the server?
- `research/21-accessibility.md`: which accessibility gaps does the current app have, and what is the checklist for the rebuild?
- `research/22-rules-engine.md`: what are the rules engine's inputs and outputs, and does it port as is?
- `research/23-domain-carryover.md`: which domain pieces and data carry over (git checks, prices, pin check)?

### Round 3 research

- `research/26-01-edit-architecture.md`: how should edits work across the full editing scope?
- `research/26-02-scope-combination.md`: how does each surface combine across scopes?
- `research/26-03-plugin-collector.md`: how do we read installed plugins safely?
- `research/26-04-text-editor.md`: which text editor runs under a strict CSP?
- `research/26-05-transcript-ingest.md`: how should transcripts get into SQLite, and how fast is it?
- `research/26-06-output-tokens.md`: are output tokens in the transcript final, and how do we count them without double counting?
- `research/26-07-read-gate.md`: does the dashboard need a read token?
- `research/26-08-write-races.md`: how do we avoid losing writes to Claude Code's own writes?
- `research/26-09-platforms.md`: which platforms should ship, and in what order?
- `research/26-10-history-range.md`: what should the default history range be?

### Verifier reports

- `research/25-verifier-gap-research.md`: does the gap research (16 to 23) hold up, and what needs correcting?

The verifier's pass on the stack picks has no file of its own. It sits inside `research/20-decisions.md`.

## Spike code and screenshots

Spike code and screenshots live in `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive`, outside git. `spikes/` holds the spike folders, and `app-audit/` holds the audit screenshots and capture scripts. Some research files cite spike paths in a session scratchpad under `/private/tmp`. Those folders are now in the archive, under `spikes/` (round 3 under `spikes/round3/`).

## What is next

- A build plan, in progress.
- Design directions for the new screens, in progress.

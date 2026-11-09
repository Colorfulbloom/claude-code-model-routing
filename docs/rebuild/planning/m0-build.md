# M0 build plan, Bar Tab skeleton

Written by the lead (deep-reasoner) on November 8, 2026, on branch `feature/bartab-m0` from `62aa704`. It turns plan-a.md section 5, "M0. Skeleton", into ordered tasks. The designer reviews section 4 before the build starts. Nothing is installed, started or committed until the owner says go.

Sources are plan-a.md (sections 3, 4, 5, 7, 8, 9), research/20-decisions.md, plan.md sections 7 and 12, components.md, tokens.css, the standards research at `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/standards/standards-research.md`, the spike sources in `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/spikes/`, and the boards in `.../design-redesign/shots/`.

## 1. What M0 delivers

The owner types the preview command in Claude Code. The browser opens on first run or the locked page, swaps the code for a key, and lands in an empty shell with the full navigation at 1440 and 375, light and dark. Every page in the nav exists as an empty, accessible page. The gate, the launcher, the tracked build and Linux CI are real, so packaging problems show up now and not at cutover.

M0 writes nothing outside the worktree except browser tabs. `dashboard/`, `tests/`, `plugins/` and `tools/` stay untouched, so no plugin bump happens (L-13fb, decision O9).

## 2. Decisions the plan makes

These settle the items the standards research and plan-a left for M0. The designer and owner can push back on any of them.

| Item | Pick | Why |
|---|---|---|
| Python layout | `app/pyproject.toml`, flat modules in `app/server/`, tests in `app/server/tests/` | Plan-a section 8. Old `discover -s tests` never sees them (T-7629) |
| Import root | `PYTHONPATH=app/server`, ruff `src = ["server"]`, pyright `executionEnvironments` with root `server` and `extraPaths = ["server"]` | Flat names match the uv recipe and keep `import gate` style. No `known-first-party` list to maintain |
| Launcher | `app/bin/bartab.py`, stdlib only, runs on Python 3.9 | O6 says the launcher runs on any `python3`, and macOS `/usr/bin/python3` is 3.9. Ruff `per-file-target-version` and a pyright execution environment hold it to 3.9 while `server/` targets 3.11 |
| Local Python | `app/.python-version` set to 3.13, `requires-python = ">=3.11,<3.15"` | Pyright checks against 3.11, so newer syntax is caught. CI runs 3.11 and 3.14 |
| Front end layout | `app/web/src/` with `app/`, `components/<Name>/`, `pages/`, `lib/`, `strings/`, `api/`. No barrel files | PascalCase component files, kebab-case for the rest (standards decision 7) |
| Router | React Router hash router (`createHashRouter`) | Research 20 verifier pass. Node 24 meets its engine floor |
| Raw hex ban | Stylelint `color-no-hex: true`, turned off only for `tokens.css` | Every colour goes through a token |
| EditorConfig | `app/.editorconfig` with `root = true` | EditorConfig only applies below its folder, so `dashboard/` keeps its style |
| Prettier and Stylelint | Config in `app/web/`, run only on `app/web` | Same reason |
| `reportAny` | Not set. It's a basedpyright rule, not pyright | Strict mode already flags unknown types |
| Shell scripts | `set -euo pipefail` in every wrapper | Standards research, source unverified, so ShellCheck runs in CI |
| Preview data folder | `app/.data/` in the worktree, gitignored | M0 has no database or ledger. Real `<config>/routing-dashboard/` use starts in M2 (N1) |
| Port | First free port in 47000 to 47999, saved per data folder and reused | A stable origin keeps sessionStorage and BroadcastChannel working across restarts. Never 8377 |
| First run steps | The launcher shows "Download Python" and "Install the dashboard's packages" in Claude Code. The browser page shows both as Done and runs "Read your usage history" live | Those two steps finish before the server exists, so no server can report them. A second, temporary stdlib server would be a new attack surface. See section 4, first run |
| Locked page project name | Routes use the project key from `/api/projects`. The key must be a readable slug | The locked page has no read key, so it can't fetch a display name. It shows the slug |
| Launch facts for bare pages | The server writes the launch command and a server instance id into `index.html` per request, beside the CSP nonce | The locked and stopped pages need the command without a key. Neither value is a secret |

## 3. Ordered tasks

Tiers follow the owner's routing rules. fast-worker runs at medium unless the row says high. Every brief carries `Kind: rebuild-m0`, the HiveMind line, the date rule (`date -Iseconds` only), and these limits. Work only in `/Volumes/Warehouse/Projects/claude-code-model-routing-bartab`. Never read `~/.claude` beyond named files, real transcripts, real settings or `~/.claude.json`. Never touch port 8377. Use the wrappers from task 3 for every uv and npm call.

HiveMind ids for briefs: T-7629, T-5589, T-c826, T-3ad1, D-c684, L-13fb, G-3e60, L-bd45, L-979a, I-14ae, W-7178, K-819f, K-6860, D-3ca7, E-6ccf.

| # | Task | Files | Tier | Check |
|---|---|---|---|---|
| 1 | Pre-flight. Record the time, branch and a clean tree. Snapshot what must not change: `nvm alias default`, `node -v`, `which -a python3 uv`, listings of `~/.local/bin` and `~/.cache/uv` (names only) | Scratchpad only | Lead | Snapshot file saved |
| 2 | Version lookup. Latest uv 0.13 or later with release sha256 for `aarch64-apple-darwin` and `x86_64-unknown-linux-gnu`. The installer's no-PATH and unmanaged-install variables. Which uv variables keep Python executables out of `~/.local/bin` (`UV_PYTHON_BIN_DIR`, `UV_PYTHON_INSTALL_BIN`). Whether `uv run` forwards SIGTERM. Node 24 latest. Exact versions at least 14 days old for every package in section 5, typescript-eslint's supported TypeScript range, which compiler rules ship in `eslint-plugin-react-hooks` presets, and full commit SHAs for `actions/checkout`, `actions/setup-node`, `astral-sh/setup-uv` | None. Report a table of name, version, date, URL | scout | Every row has a URL |
| 3 | Safe tooling. Unpack the pinned uv tarball into `.tools/uv/` after a sha256 match. `nvm install 24` without `nvm alias default`. Write `app/scripts/uvw` and `app/scripts/npmw`, which export the variables in section 5 and exec the tool. Add the gitignore lines in section 5 | `.gitignore`, `.nvmrc`, `app/scripts/uvw`, `app/scripts/npmw` | Lead | Task 1 snapshot unchanged. `uvw --version` is 0.13 or later. `npmw --version` runs under Node 24 |
| 4 | Standards and config. Write `docs/rebuild/standards.md` from the research with section 2's picks folded in. Create the config files. Prove each tool runs on one hello module | `docs/rebuild/standards.md`, `app/pyproject.toml`, `app/.python-version`, `app/.editorconfig`, `app/web/package.json`, `app/web/package-lock.json`, `app/web/tsconfig.json`, `app/web/tsconfig.node.json`, `app/web/eslint.config.mjs`, `app/web/.prettierrc.json`, `app/web/.prettierignore`, `app/web/stylelint.config.mjs`, `app/web/vite.config.ts`, `app/web/playwright.config.ts`, `app/uv.lock` | fast-worker | ruff check, ruff format check, pyright, ESLint, Stylelint, Prettier check, tsc and Vitest all pass on the hello modules. `git diff --stat -- dashboard tests plugins tools` is empty |
| 5 | M0 string deck. Port the shell, nav, gate and first-run keys from `docs/design/redesign-a/strings*.js` with the brand as Bar Tab. Draft the new ones in section 4 (server stopped, code used, code expired, server restarted, key for another project, More page, project picker states, placeholder pages, route titles, route status line) | Draft returned as a key table, then typed into `app/web/src/strings/en.ts` by the lead | tech-writer | Owner style lint in task 11 passes. Owner reads the deck |
| 6 | Server core and gate (high). Port the pure ASGI gate from `spikes/1-gate/gate_middleware.py`. Read key, single-use codes and `POST /api/access/swap`. Per-request CSP nonce with `index.html` rewritten per request. `GET /api/app` and `GET /api/projects` with their final Pydantic response models, backed by a fixture provider until M1. Static serving of `dist`. Error handler that hides file names. Offline OpenAPI export | `app/server/main.py`, `gate.py`, `access.py`, `csp.py`, `api_app.py`, `fixture_provider.py`, `models.py`, `openapi_export.py`, `app/server/tests/` | fast-worker high | pytest with coverage at 85 percent or more on `app/server`, ruff, pyright strict |
| 7 | Launcher (high). `start`, `code` (mint a fresh code for the running server), `stop`, `status`, `session-end`, `guard`. Finds uv and fails clearly. Runs `uv sync --frozen` with step lines on first run, then `uv run --frozen --project app --no-dev`. Detached start, waits for the launch line, opens the browser with `webbrowser.get().open` (I-14ae). Carries spikes 2 and 3 | `app/bin/bartab.py`, `app/server/tests/test_launcher.py`, `.claude/skills/bartab-preview/SKILL.md` | fast-worker high | Subprocess tests with `["guard"]` and JSON on stdin (L-979a). A test browser stub never opens a real tab |
| 8 | Spikes 4 and 5, in parallel with 6 and 7. Sources in the scratchpad. Results in `docs/rebuild/planning/m0-spikes.md` | `docs/rebuild/planning/m0-spikes.md` | fast-worker | Each spike states pass or fail with its evidence |
| 9 | Web skeleton. Vite, React 19 with React Compiler, hash router, typed `t()` and `tn()` over `Intl.PluralRules`, `tokens.css` copied byte for byte, shared rules CSS, access client (swap, sessionStorage, BroadcastChannel), TanStack Query client whose fetch adds the key and maps refusals, route harness, API types from `openapi-typescript` | `app/web/index.html`, `app/web/src/main.tsx`, `src/app/`, `src/lib/`, `src/api/`, `src/styles/tokens.css`, `src/styles/shared.css` | fast-worker | `cmp` of both tokens.css files. Vitest for `t()`, `tn()`, the access client and the router. tsc, ESLint |
| 10 | Wave 1 components and the component sheet. Components 1, 2, 3, 5, 6, 7, 8, 9, 14, 33, 34, 35, 36, 37 with the chosen-state standard. `app/web/sheet.html` as a dev and test entry, never in `dist`. A typed manifest of every state | `app/web/src/components/*`, `app/web/sheet.html`, `app/web/src/sheet/` | fast-worker | Vitest per component with Testing Library. Manifest test fails on a missing state |
| 11 | Shell and screens. Sidebar, top bar, tab bar, page headers, empty placeholder pages for every route in plan-a section 2, the More page, the project picker, the gate pages and first run. Owner-style string lint over `en.ts` | `app/web/src/pages/*`, `app/web/src/app/Shell.tsx`, `app/web/src/strings/lint.test.ts` | fast-worker | Vitest. Lint finds no em dash, exclamation mark or colon in prose values |
| 12 | Playwright and axe. Route harness at 320, 375 and 1440, light and dark, forced colors and reduced motion. Sheet run per plan-a section 4. Code swap end to end (spike 1). Built app serves the strict CSP | `app/web/e2e/*.spec.ts` | fast-worker | Suite green locally under the wrappers |
| 13 | CI on Linux. One workflow with a path filter on `app/**`, `.nvmrc` and itself. `permissions: contents: read`, actions pinned to full SHAs. Python job on 3.11 and 3.14, web job, dist drift check, ShellCheck on the wrappers | `.github/workflows/bartab.yml` | fast-worker | `actionlint` if present, else a scout review of the YAML. First real run needs a push, which waits for the owner |
| 14 | Build and track `dist`. Launcher second start with `UV_OFFLINE=1` | `app/web/dist/**` | Lead | Second start succeeds offline. `git status` shows dist tracked |
| 15 | Exit runs. T2 and T3 suites, then the old suite alone (T-7629) with a per-branch log name, then `git diff --stat 62aa704 -- dashboard tests plugins tools` | Logs in the scratchpad | scout | All green. The diff is empty |
| 16 | Browser check in Chrome under the tab-group rules. Every gate page and the shell at 1440 and 375, light and dark, against `a-locked-*`, `a-firstrun-*`, `a-components-*` and the shell in `a-tofix-1440-*` and `a-live-375-*` | None. Returns a difference list | judge | Differences fixed in one batch, or listed for the owner |
| 17 | Verifier pass on the finished milestone, then consolidation and the report | None | verifier (Opus, pinned) | Verified claims relayed |

Order and parallel work. Tasks 1 to 3 run first and alone. Then 4 and 5 run in parallel. After 4, tasks 6, 7, 8 and 9 run in parallel. They touch separate folders, and 6 and 7 share only the launch-line format, which this plan fixes in section 6. Then 10, 11, 12 and 13, then 14 to 17. Review findings go to one fix dispatch per round.

## 4. UI pieces, boards and what each screen needs

This is the part for the designer's review. Each screen lists its board, its components.md entries, and the state, data and events it needs. All words come from the task 5 deck.

### App-wide state

- Access. `readKey`, `editKeys {project: key}` and `instanceId` in sessionStorage per tab (O1). A tab with no key asks other tabs on a BroadcastChannel named per origin. Any tab that holds a key answers with the key and its `instanceId`. A tab takes the answer only when that id matches the `instanceId` in its own `index.html`, so a stale key never unlocks a `server_restarted` tab. While a new tab waits for answers (up to 400 ms) it shows a brand-only hold, so the locked page never flashes.
- Server facts. `GET /api/app?project=<key>` every 10 s while the tab is visible, 1 s during first run, and at once when a tab returns to view. M0 fills `server_time`, `instance`, `claude_version` (fixture), `ingest {state, files_done, files_total, bytes_done, bytes_total, error {code, file}, retrying}`, `running[]`, `to_fix_count` for the project in the route, and `editable_projects`. The other fields arrive in M1 with their final names.
- Connection state. The shell keeps `lastAnswerAt` and a `retrying` flag. While calls fail, the Working mark drops and a quiet "Updated {time}" line shows the last answer.
- Projects. `GET /api/projects` at shell start, so the project name shows from the first paint, then on opening the Select and every 60 s. Fields are `key`, `name`, `display_path`, `state` (ok, no_claude_folder, folder_not_found) and `running`.
- Theme. The system setting only, through `prefers-color-scheme`. `data-theme` works but has no control in M0, because preferences need the M1 database.
- Route. Hash routes from plan-a section 2. On every route change the title changes, focus moves to the h1, and a polite status line names the page. A project swap from a detail route drops to the list level when the item doesn't exist in the new project.
- Refusals. A 401 from any call moves the tab to the locked page with a reason code. Three failed calls in a row with no answer move it to the server stopped page. Both keep the requested route. A gate transition sets the title to name the state, moves focus to the card h1 and posts the polite status line, like a route change.
- Brand. Every gate page, the sidebar brand and the command read Bar Tab. The command string comes from `index.html`, never from the bundle.

### Shell at 721 px and up

- Board. The sidebar in `a-tofix-1440-*` and every other `a-*-1440` board. Components 1, 3, 14 and 36.
- Shows. Brand "Bar Tab", the project Select, Live alone with the Working mark, Review (Summary, Sessions, Agents, Models), Setup (Your setup, To fix with its count), Reference (How Claude Code decides, Glossary), and the footer version line.
- Data. `running[]` for the Working mark on Live, `to_fix_count` (hidden at zero, D6), `claude_version`, the project list.
- Events. Picking a project keeps the page and swaps the project in the route. Links carry `aria-current="page"`. Main content stops at 1280 px (D7). The count and Working mark slots keep their width when empty, so nothing pops in.
- Placeholder pages. Each route renders its page header and a page-level empty state (33) that says the page arrives later. This is dev-only wording and goes away milestone by milestone.

### Shell at 720 px and below

- Board. The top and bottom bars in `a-live-375-*` and other `a-*-375` boards. Components 2 and 3.
- Shows. A sticky 52 px top bar with page name and project, and the fixed five-item tab bar (Live, Review, Setup, To fix with count, More). Main keeps 96 px of bottom padding.
- Data. The same as the sidebar.
- Events. Review is current on any Review page and opens Summary when pressed from elsewhere. Setup is current on Your setup and its surface pages. More is current on the More page and on Reference routes. The count is in the accessible name ("To fix, 4"). The tab bar hides on the agent form routes (later milestone, but the shell needs the hook now).

### More page, phone only

- Board. None yet. Plan-a section 2, "Not yet drawn", item 4, due before M0 shell work ends.
- Proposed content for the designer pass. Reference (How Claude Code decides, Glossary), then the version line and "Prices as of" once M1 lands. At 721 px and up, `#/more` redirects to the current project's Live.
- Data. `claude_version`. Nothing else in M0.
- Need from the designer. The page layout, whether the project switch lives here or only in the top bar, and the empty-theme decision above.

### Project picker

- Board. None for 375 yet (same designer pass). At 1440 it is the sidebar Select (component 14). At 375 the Select opens as a bottom tray.
- When it shows. `#/` with no launch project opens it as a sheet. The launcher passes the project it was run from with the code, so most starts skip it.
- Data. The project list with state and running. A project in `no_claude_folder` or `folder_not_found` stays pickable and shows its state in words.
- Events. Picking navigates to that project's Live. Esc or Close returns to the previous route, or stays on the picker when there is none. With no projects at all, the list shows an empty state (33).
- Need from the designer. The trigger in the 375 top bar (tap on the project name, or a separate control), the tray header and how states read.

### Locked page

- Board. `a-locked-1440-*` and `a-locked-375-*`. Components 35, 5, 9 and 6.
- Reason codes from the server or the client, each with its own sentence.

| Code | When | Source |
|---|---|---|
| `no_key` | A tab opened with no code and no key, and no other tab answers | Client |
| `code_used` | The code was already swapped, for example a reloaded first link | Swap answer |
| `code_expired` | The code is older than its lifetime (spike 1 sets it) | Swap answer |
| `server_restarted` | The key or code carries another instance id than the page's `index.html` | Client compares ids, swap confirms |
| `wrong_project_key` | An edit call uses a key for another project | Edit answer, from M6. M0 renders the state on the sheet only |

- Data. The launch command and instance id from `index.html`, the reason code, and the requested route. The route shows as page name and project slug ("Agents, builder" on the board).
- Events. Copy command (with a polite "Copied" status). While locked, the tab listens on the BroadcastChannel and unlocks in place at the kept route when another tab gets a key with the same instance id. The launcher's new tab still opens, and it says the other tab is back (owner, November 8). The words come from tech-writer.

### Server stopped

- Board. None. Plan-a section 2 item 6, due before M0 ends. It reuses the gate page layout.
- When. Three calls in a row with no answer from an already loaded tab. A reload of a stopped server shows the browser's own error, which the app can't change.
- Data. The launch command, the kept route, the time of the last answer as a clock time.
- Events. A slow retry every 10 s while visible, and a "Try now" button beside it. When the server comes back with the same instance id the tab resumes. With a new instance id it moves to the locked page with `server_restarted`.

### First run

- Board. `a-firstrun-1440-*` and `a-firstrun-375-*`. Components 35, 34, 11 (run-state glyphs) and 9.
- Change from the board. Steps 1 and 2 run in Claude Code before the server exists, so the page shows them as Done with no sizes (owner, November 8). Only step 3 is live in the browser. The "41 of 82 MB" bar moves to the launcher's terminal lines.
- Data. `ingest.state` (waiting, running, done, failed), files and bytes done and total, `ingest.error {code, file}` when failed, and `ingest.retrying` while a retry runs. M0 serves a fixture that steps through these states on a test clock, because the real ingest is M1.
- Events. 1 s polling while running. The current step change is announced politely once. On done, the page moves to the launch project's Live. On failed, the step shows the ✕ finding (7) with the reason, the file when there is one, and the command to try again. While `retrying` is true the finding says a retry is under way.
- Need from the designer. Confirm the three-row layout when two rows are already done at load, and the failed state, which has no board.

### Component sheet

- Board. `a-components-1440-*` and `a-components-375-*`.
- Content. Every state of the 14 wave 1 components, plus the shared rules (focus, hover with no movement, `aria-disabled` with a reason, busy label swap) and the chosen state on the Select's listbox options.
- Data. None. Static props from the manifest.

## 5. Tooling that keeps the owner's machine safe

Nothing in M0 changes a global tool, cache, alias or Python install.

- uv. The release tarball for `aarch64-apple-darwin`, version from task 2, unpacked into `.tools/uv/` after a sha256 match. The install script isn't used, because it edits shell profiles and writes to `~/.local/bin` unless told otherwise.
- `app/scripts/uvw` exports these and then runs `.tools/uv/uv "$@"`.
  - `UV_CACHE_DIR=<wt>/.uv-cache`
  - `UV_PYTHON_INSTALL_DIR=<wt>/.uv-python`
  - `UV_PYTHON_BIN_DIR=<wt>/.tools/python-bin`, plus the no-bin variable if task 2 confirms one
  - `UV_TOOL_DIR=<wt>/.tools/uv-tools` and `UV_TOOL_BIN_DIR=<wt>/.tools/bin`
  - `UV_PROJECT_ENVIRONMENT=<wt>/app/.venv`
  - `UV_PYTHON_PREFERENCE=only-managed`, so the Anaconda and system Pythons are never used
  - `UV_NO_MODIFY_PATH=1`
- Node. `nvm install 24` once. A first install never changes an existing default alias, and task 1's snapshot proves it. `app/scripts/npmw` puts `$(nvm which 24)`'s folder first on PATH and runs npm.
  - `npm_config_cache=<wt>/.npm-cache`
  - `npm_config_ignore_scripts=true` (O6). If a package needs its install script, task 4 names it and the lead decides
  - `PLAYWRIGHT_BROWSERS_PATH=<wt>/.pw-browsers`, so browsers stay out of `~/Library/Caches`
- Lockfiles. The first `npm install --save-exact` and `uvw lock` happen once in task 4 and are committed. Every later install is `npmw ci` and `uvw sync --frozen`.
- Gitignore lines. `/.tools/`, `/.uv-cache/`, `/.uv-python/`, `/.npm-cache/`, `/.pw-browsers/`, `/app/.venv/`, `/app/.data/`, `/app/web/node_modules/`, `/app/web/playwright-report/`, `/app/web/test-results/`, `/app/web/coverage/`, `/app/.coverage`.
- Removal. Deleting the worktree removes everything. Node 24 stays in nvm's list, which `nvm uninstall 24` undoes.
- Packages pinned exactly, with versions from task 2.
  - Server: fastapi, uvicorn, pydantic, ruamel.yaml
  - Server dev: pytest, pytest-xdist, pytest-cov, hypothesis, httpx, ruff, pyright
  - Web: react, react-dom, react-aria-components, react-router, @tanstack/react-query
  - Web dev: vite, @vitejs/plugin-react, babel-plugin-react-compiler, typescript, typescript-eslint, eslint, @eslint/js, globals, eslint-plugin-react-hooks, eslint-plugin-jsx-a11y, eslint-config-prettier, prettier, stylelint, stylelint-config-standard, vitest, jsdom, @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, @playwright/test, @axe-core/playwright, openapi-typescript.

## 6. The five spikes

Each spike ends with a pass or fail, its evidence and the decision it settles, written into `m0-spikes.md`. A failure changes the plan before the dependent task goes on.

| # | Spike | How | What it decides |
|---|---|---|---|
| 1 | Code swap end to end | Launcher mints a code as `<instance>.<random>` and opens `#/?code=...`. The page swaps it, stores the keys, and strips the code with `history.replaceState`. Playwright then reloads, opens a second tab by link and by `window.open`, restarts the server, and reuses the old link | Code lifetime and single use. The launcher to server channel for `code` (a 0600 file in the data folder, read by the server, or a local call with a launcher secret). Whether Chrome copies sessionStorage into a linked tab. That BroadcastChannel unlocks a locked tab in place. Settles O1's mechanism |
| 2 | SessionEnd with one shared server | Two fake sessions start the preview against one data folder, then end one at a time through `bartab.py session-end` | The owner list and the stop rule (stop when the last owner ends, or keep running with an idle limit). Whether the preview needs a SessionEnd hook at all before M9, which needs a project setting (owner question 2) |
| 3 | uv and SIGTERM | Start through `uv run`, send SIGTERM to uv's pid and to the process group, and record whether lifespan shutdown runs and whether a child is left | Whether the launcher signals uv, signals the group, or runs `.venv/bin/python -m uvicorn` directly after `uv sync --frozen`. Settles the clean-stop backup hook for M1 |
| 4 | `json_edit` array insert | Extend a scratch copy of `dashboard/json_edit.py` (the original stays untouched) with append to and remove from a JSON array, such as `permissions.deny`, under the same `_oracle` check, on the 123 resolver folders and hypothesis cases | O14. Deny and ask rules go in M7 if it passes, else 1.1 |
| 5 | ruamel byte equality | Round-trip every agent file in the repo's `agents/` and `tests/fixtures/` with ruamel (`width` large, `preserve_quotes`), change one key at a time, and compare all other bytes | Whether M6 uses ruamel for front matter, or the byte-splicing fallback for scalar fields |

Two more checks ride along without being spikes. React Aria's touch-action style under the nonce CSP (task 12), and React's own style handling under strict `style-src` (standards decision 9).

The launch line. The server prints one JSON line on fd 3 when it is ready, with `port`, `instance`, `code` and `pid`, like the old launcher's `read_launch_line`. Tasks 6 and 7 build to this shape.

## 7. Tests and exit checks

### New suites

| Layer | Contents |
|---|---|
| Python, task 6 | Gate refuses a bad Host, Origin, Sec-Fetch-Site and Content-Type, an oversized body, a short body that would hang, and a missing or wrong token. Tests assert "refused", not exact codes (spike 1 of research 20). Every GET needs the read key. Codes are single use and expire. Swap with a stale instance says so. The CSP header carries a fresh nonce on each request and the nonce in `index.html` matches it. The error handler leaks no paths. OpenAPI export runs offline and the committed types match it |
| Python, task 7 | Launcher guard cases as subprocesses with `["guard"]` and JSON on stdin (L-979a). Port choice skips 8377 and busy ports. Missing uv fails with a clear line. The browser stub is a `webbrowser` controller that records calls (I-14ae). Owner list add and remove |
| Vitest | `t()` and `tn()` with plural rules, the string lint, the access client (swap, store, broadcast, refusal mapping), the router (titles, focus target, status line), each wave 1 component's states by role |
| Playwright with axe | Every route and gate page at 320, 375 and 1440, light and dark, with `wcag2a`, `wcag2aa` and `wcag22aa` tags. Forced colors and reduced motion. Focus outline values against `--focus-width` and `--focus-ring`. Hover moves nothing. Target sizes 24, 32 and 52 px. Reflow at 320 with no horizontal scroll. The component sheet run from plan-a section 4. Code swap end to end. The built app sends the strict CSP and the dev server's looser one never ships |
| Static checks | ruff check, ruff format check, pyright strict, tsc, ESLint, Stylelint, Prettier check, coverage at 85 percent on `app/server` |

`NoHomePathsInTestsTest` gets a sibling in `app/server/tests/` that scans `app/` (T-3ad1), so the old test file stays untouched. `MR_TEST_TMP`, when used, sits outside every repo (T-c826).

### Old suite

`dashboard/` must be untouched, so the old suite should pass unchanged. A scout runs `/usr/bin/python3 -m unittest discover -s tests` from the worktree root alone, with a log named for `feature-bartab-m0` (T-7629). Expected 3575 tests with 88 skipped, give or take what development has added since November 7.

### Exit, from plan-a M0

- Axe clean on every gate page and the empty shell at both widths and themes.
- The built `dist` is tracked and the launcher runs `uv run --frozen` offline on a second start.
- O1 is decided by spike 1 and O6 by the CI workflow and locked installs.
- Spikes 4 and 5 have results, so O14 and the M6 front matter path are known.
- The old suite passes and `git diff --stat 62aa704 -- dashboard tests plugins tools` is empty.
- The owner opens the preview, swaps a code and walks the nav at 1440 and 375.

## 8. Cost estimate

List-price ranges. I have no per-run cost data from the dashboard in this tree, so these are scaled from plan-a's table. [NEEDS CONFIRMATION: dashboard cost per run for each agent.]

| Dispatch | Count | Estimate |
|---|---|---|
| Lead, deep-reasoner on Opus at high, the build and its reviews | 1 | $15 to $25 |
| fast-worker at high, tasks 6 and 7 | 2 | $8 to $14 |
| fast-worker at medium, tasks 4, 8, 9, 10, 11, 12, 13 and one fix round | 8 | $16 to $28 |
| scout, tasks 2, 13 and 15 | 3 | $2 to $4 |
| judge, task 16 in Chrome | 1 | $3 to $6 |
| tech-writer at medium, task 5 and the standards prose | 1 | $3 to $6 |
| verifier on Opus at high, task 17 | 1 | $5 to $10 |
| Total | | $52 to $93 |

That is above plan-a's $35 to $60 for M0. The extra comes from the standards setup, CI and the verifier pass, which plan-a's row left out. The total passes the $20 gate and the lead passes $5, so the build waits for the owner's yes. The designer's plan review is separate and dispatched by the main session.

## 9. Owner answers, November 8

The owner approved the build and every pick, with a stop and report if spend heads past $95. The preview command is a project skill at `.claude/skills/bartab-preview/SKILL.md`, and the guard and SessionEnd hooks stay unwired until M9. Linux CI is approved, but nothing is pushed in M0, so the workflow only has to pass a validity check. uv stays in `.tools/`. First run steps 1 and 2 run in Claude Code. A self-unlocked tab doesn't stop the launcher's new tab, which says the other tab is back. The designer's review findings are folded into section 4. Task 11 waits for the new boards. The main session dispatches the verifier, so task 17 ends with a report instead.

The questions as first asked follow for the record.

1. Go for the build at $52 to $93.
2. Where the preview command lives. I recommend a project skill at `.claude/skills/bartab-preview/SKILL.md`, whose `!` line runs `python3 app/bin/bartab.py start`. It shows only when Claude Code runs in this checkout. The launcher's guard and SessionEnd actions exist and are tested, but wiring them as hooks needs a project `.claude/settings.json` entry. I recommend leaving them unwired until the plugin in M9 and relying on spike 2's idle limit.
3. GitHub Actions minutes for a Linux CI job on every push to `app/**` (open since plan.md O6). The first run needs a push of this branch.
4. uv lives only in the worktree's `.tools/` folder for the build. Say so if you want it in `~/.local/bin` as the user prerequisite instead.
5. The first-run change in section 4, where steps 1 and 2 show in Claude Code and only step 3 runs in the browser. The designer reviews it, but it changes what the board promised.
6. The More page and project picker designer pass (plan-a section 2, item 4) and the server stopped state (item 6) need to finish before task 11 starts.

## 10. Interfaces between the server, the launcher and the page

Tasks 6, 7 and 9 build to this contract. Spike results can change it, and any change is written here first.

### Launch

- The launcher runs the server as `serve.py --port N --data DIR --launch-fd 3 --project-dir PATH [--fixture NAME] [--idle-exit-minutes 30]` from `app/server`, through `uv run --frozen --project app --no-dev` or the venv's Python directly (spike 3 decides).
- When it is listening, the server writes one JSON line to the launch fd and closes it: `{"port": int, "pid": int, "instance": str, "code": str, "project": str|null}`.
- The server writes `DIR/server.json` with mode 0600: `port`, `pid`, `instance`, `mint_secret`, `started`, `owners[]`. The launcher adds and removes owners. The server rewrites the file only at start and removes it at clean stop.
- Data folder in M0 is `--data`, else `BARTAB_DATA`, else `app/.data/` in the checkout. Port is the first free one in 47000 to 47999, saved in `DIR/port` and tried first next time. Never 8377.
- The launcher finds uv in this order: `BARTAB_UV`, `<repo>/.tools/uv/uv`, `uv` on PATH, `~/.local/bin/uv`, `~/.cargo/bin/uv`. With none, it prints one `error:` line naming the install page and exits 2.
- uv variables for the server's environment all sit under `DIR/uv/` (cache, Python installs, project environment, bin dir with `UV_PYTHON_INSTALL_BIN=0`), with `UV_PYTHON_PREFERENCE=only-managed`, per research 20 spike 2.
- The browser opens at `http://127.0.0.1:PORT/#/?code=CODE` through `webbrowser.get().open` (I-14ae).
- The preview command is the project skill `.claude/skills/bartab-preview/SKILL.md`, following the old `dashboard` skill's shape, with `python3 "${CLAUDE_PROJECT_DIR}/app/bin/bartab.py" --default-project "${CLAUDE_PROJECT_DIR}" --session "${CLAUDE_SESSION_ID}" $ARGUMENTS`. Guard and SessionEnd stay unwired until M9.

### Access

- The read key is 32 random bytes, base64url. Codes are `<instance>.<random>`, single use, and live 120 seconds unless spike 1 changes it.
- `POST /api/access/swap` with `{"code": str}` answers `{"read_key", "edit_keys": {}, "instance", "project"}`, or a refusal `{"code": "code_used" | "code_expired" | "code_unknown" | "server_restarted"}` with status 403. `server_restarted` means the code's instance part isn't this server's.
- `POST /api/access/mint` with header `X-Bartab-Mint: <mint_secret>` and `{"project": str|null}` answers `{"code"}`. The launcher's `code` action uses it to give a running server a new link.
- Every other `/api/*` call needs header `X-Bartab-Key: <read_key>`. A missing or wrong key gets 401 `{"code": "no_key" | "bad_key"}`.
- Static files and `index.html` need no key. `index.html` carries no secret.

### Gate

A pure ASGI middleware before FastAPI, ported from `spikes/1-gate/gate_middleware.py`. It refuses a Host other than `127.0.0.1:PORT` or `localhost:PORT`, an Origin other than the same two, a `Sec-Fetch-Site` other than `same-origin` or `none`, a POST without `application/json`, a body over 64 KiB, and a body that doesn't arrive within 3 seconds. Uvicorn runs with `--http h11`, no proxy headers and no forwarded IPs.

### Page shell

- The server reads `dist/index.html` once and rewrites it per request with a fresh nonce on every `script` and `link` tag, `<meta name="csp-nonce" content="N">`, `<meta name="bartab-instance" content="I">` and `<meta name="bartab-command" content="/bartab-preview">`.
- Production CSP is `default-src 'none'; script-src 'self' 'nonce-N'; style-src 'self' 'nonce-N'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. Also `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Cache-Control: no-store` on `index.html` and `/api/*`.

### Reads in M0

- `GET /api/app?project=KEY` answers `server_time`, `instance`, `claude_version`, `ingest {state: waiting|running|done|failed, files_done, files_total, bytes_done, bytes_total, error: {code, file}|null, retrying}`, `running[] {project, session}`, `to_fix_count` for KEY (null without KEY), `editable_projects[]`.
- `GET /api/projects` answers `projects[] {key, name, display_path, state: ok|no_claude_folder|folder_not_found, running}`. Keys are readable slugs.
- First-run failure codes. A single unreadable transcript never fails the run. It becomes a To fix row, because readers return partial results. So `ingest.error.code` covers whole-run causes only: `config_dir_missing` (Claude Code's projects folder isn't there), `config_dir_unreadable` (permissions block the folder, with `file`), `store_unwritable` (the data folder can't be written, disk full included, with `file`), `store_damaged` (the database fails its integrity check, with `file`), `unexpected` (anything else, with the log path as `file`). While a retry runs, `ingest.state` is `running` with `retrying: true` and `error: null`, so the page shows step 3 In progress with "Trying again since". Step 3 makes no network call. The M1 price feed runs on its own daily schedule and falls back to the bundled copy offline.
- In M0 both come from `fixture_provider.py` over JSON in `app/fixtures/m0/`, with named scenarios (`demo`, `empty`, `firstrun`, `firstrun_failed`) and an injectable clock that steps the ingest.
- Errors use one envelope, `{"code": str, "path": list|null}`, and never echo input or file paths.
- The OpenAPI schema is exported offline to `app/web/src/api/openapi.json`, and `openapi-typescript` writes `app/web/src/api/schema.d.ts`. A test fails when either is stale.

### Page side

- sessionStorage keys `bartab.readKey`, `bartab.editKeys`, `bartab.instance`, `bartab.route`, and `bartab.project` (the launch project, so `#/` still lands on it after a reload). A 401 `bad_key` maps to `server_restarted`, and a 5xx counts as no answer.
- BroadcastChannel `bartab-access`. Messages are `{"type": "ask"}` and `{"type": "offer", "readKey", "editKeys", "instance"}`. A tab takes an offer only when `instance` matches its `bartab-instance` meta. A new tab waits up to 400 ms for an offer, showing the brand-only hold, before it shows the locked page.
- After a successful swap, a tab posts one unsolicited offer, so locked tabs on the same server unlock in place. A tab that unlocks from an offer posts `{"type": "back", "route"}`, so the launcher's new tab can say the other tab is back.

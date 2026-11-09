### F-1a06 Bar Tab M0 skeleton: gate, launcher, shell, gate pages, CI
status: in-progress
kind: code
dates: 2026-11-08 .. 2026-11-08
refs:
  commit: pending (branch feature/bartab-m0)
summary: New app in app/ (FastAPI server with ASGI gate and code swap, stdlib launcher, React 19 shell with gate pages and wave 1 components), coding standards, Linux CI, five spikes; dashboard/ untouched.
decisions:
- Launcher spawns <data>/uv/env/bin/python serve.py directly after uv sync --frozen, because uv run adds a second pid that differs from server.json (spike 3).
- One shared server stops when its last owner ends, with a 30 minute idle exit as backstop while hooks stay unwired until M9 (spike 2).
- O1 mechanism as built: single-use 120 s codes, sessionStorage per tab, BroadcastChannel offer accepted only on matching instance id, locked tabs unlock in place (spike 1).
- O14 resolves to M7: json_edit append_item and remove_item pass 48 fixtures and 2000 fuzz cases (spike 4).
- M6 front matter: byte splicing for scalars and comma-string tools, ruamel with an outside-key byte-equality guard only for list-form tools (spike 5).
- First run steps 1 and 2 run in Claude Code because they finish before any server exists; while a retry runs ingest reports state running with retrying true.
- TypeScript 6.0.3 and ESLint 9 because typescript-eslint caps below TS 6.1 and jsx-a11y peers ESLint 9; pyright comes from npm so it never writes a home cache; httpx2 replaces httpx for TestClient types.
- uv 0.13.5 and actionlint from sha256-checked tarballs in .tools/, all caches in the worktree; Node 24 via nvm without changing the default alias.
- Verifier fixes: process_ours needs the resolved SERVE path as a whole argument and --data <resolved data>, never a serve.py substring (D1); swap and mint share one threading.Lock (D2); the guard also denies plain or absolute python, env forms, uv/uvw run and bash/sh/zsh -c and eval to depth 4 (D3); the idle tracker sits behind the gate (D6); serve.py parse_args refuses 8377 (D7).
- Owner fixes: placeholder pages use a neutral … empty-state mark, not the ✓; #/ with no launch project shows the shell with the picker as a modal sheet (tray at 375), and Esc goes back only when the router location key isn't "default".
rejected:
- A temporary stdlib server for first-run steps 1 and 2: a second attack surface for two steps that take seconds.
- uv's install script: it edits shell profiles and writes ~/.local/bin.
- React Compiler through @vitejs/plugin-react's native compiler option: the README marks it experimental.
- Folding this feature's HIVEMIND captures here: the capture hook wrote them to the main tree inbox, which the lead was told not to touch; the main session consolidates them.
files: app/server/, app/bin/bartab.py, app/web/, app/pyproject.toml, .github/workflows/bartab.yml, .claude/skills/bartab-preview/SKILL.md, docs/rebuild/planning/m0-build.md, docs/rebuild/planning/m0-spikes.md, docs/rebuild/standards.md
gotchas:
- Launcher pytest tests share one xdist_group (--dist=loadgroup in addopts). The deeper failure was D1: a serial run of test_launcher.py with test_serve.py has pytest's own argv holding serve.py, so a substring match SIGTERMed pytest; -n 4 hid it.
- A check-then-set race under the GIL won't show with a thread barrier alone; test_access.py stores an expiry float subclass whose __le__ sleeps to open the gap.
- A broad prettier --write reformats the generated openapi.json; it and schema.d.ts are in .prettierignore.
- Playwright needs channel chromium (new headless); the old headless shell never fires requestAnimationFrame here.
- React Aria needs the csp-nonce meta or its touch-action style violates style-src.
follow-ups:
- Chrome check against the boards was not possible (extension not connected); Playwright screenshots stood in.
- Mint should accept a project folder and map it to a key once M1 has the real project reader.
- The guard reads uv run's known options only; an unlisted option could hide a non-python launcher form.
- "How Claude Code decides" wraps in the 224px sidebar at 1440, on the a-live-1440 boards too; the one-line e2e test is fixme until the owner picks width, spacing or label.
- Bundle is 188 KB gzipped in one chunk; split when Live lands.
- Move to ESLint 10 when eslint-plugin-jsx-a11y supports it.

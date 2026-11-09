# Bar Tab coding standards

These standards apply to `app/` only. The current `dashboard/` keeps its own style until it is retired, and its unittest suite stays as it is. Every config file named here lives in `app/` or `app/web/`, so nothing reaches outside those folders. EditorConfig, Prettier and Stylelint only apply below the folder that holds their config.

## Tools and how to run them

Run uv through `app/scripts/uvw` and npm through `app/scripts/npmw`. They keep the caches and the Python and Node tooling inside the worktree. Every command below runs from the repository root.

- Python lint and format: `uvw run --frozen --directory app ruff check .` and `uvw run --frozen --directory app ruff format --check .`
- Python tests: `uvw run --frozen --directory app pytest -n 4 --cov` (the 85 percent coverage floor is set in `pyproject.toml`)
- Python types: `npmw --prefix app/web run pyright`. Pyright comes from npm and reads `app/pyproject.toml`, so it is not a Python dependency.
- Web: `npmw --prefix app/web run typecheck`, `lint`, `lint:css`, `format:check`, `test`, `build` and `e2e`
- Installs: `uvw sync --frozen --directory app` and `npmw --prefix app/web ci`. Only a deliberate dependency change touches `app/uv.lock` or `app/web/package-lock.json`.

Every dependency is pinned to an exact version. Dev dependencies follow the same rule. Update them in one reviewed change, never by a floating range.

## Version caveats

- TypeScript is 6.0.3 because typescript-eslint 8.72.0 supports `>=4.8.4 <6.1.0`. Do not move to TypeScript 7 until typescript-eslint supports it.
- ESLint is 9.39.5, not 10, because `eslint-plugin-jsx-a11y` 6.10.2 peers ESLint up to 9. `@eslint/js` stays on the same 9.x line.
- The React Compiler runs through Babel. `vite.config.ts` uses `react()` plus `babel({ presets: [reactCompilerPreset()] })` from `@rolldown/plugin-babel`, as the `@vitejs/plugin-react` README describes. That README marks the Rust port (`compiler: true`) as experimental, so Bar Tab doesn't use it. `@babel/core` is 7.29.7, the newest 7.x that is at least 14 days old.
- `openapi-typescript` 7.13.0 peers TypeScript 5. So `package.json` carries one npm override, `"openapi-typescript": { "typescript": "$typescript" }`, which makes it use the project's TypeScript. Add any further override only for a peer conflict and record it here.
- Install scripts are off (`npm_config_ignore_scripts=true`). No package needs one. `fsevents` is optional and unused.
- The Python launcher in `app/bin` runs on `/usr/bin/python3`, which is 3.9 on macOS. Ruff (`per-file-target-version`) and a Pyright execution environment hold `app/bin/*.py` to 3.9. The server targets 3.11.

## Layout

```
app/
  pyproject.toml, uv.lock, .python-version, .editorconfig
  bin/        launcher, stdlib only, Python 3.9
  scripts/    uvw and npmw
  server/     flat modules, tests in server/tests/
  web/
    src/
      app/         router, shell, providers
      components/  one folder per component, <Name>/<Name>.tsx
      pages/       one file per route
      lib/         plain helpers and clients
      strings/     the string deck
      api/         generated types and the fetch layer
      styles/      tokens.css (copied, never edited here) and shared rules
      test/        Vitest setup
    e2e/           Playwright specs
```

- No barrel files. Import from the file that defines the name.
- Python imports use flat names, such as `import gate`. The import root is `app/server`, set by pytest `pythonpath`, Ruff `src = ["server"]` and Pyright's `server` execution environment (`extraPaths = ["server"]`). There is no `known-first-party` list.
- Pytest finds tests under `app/server/tests/` only, so the old `discover -s tests` run never sees them.
- File names are PascalCase for React components and kebab-case for every other module. Python files are snake_case.

## Python

- Ruff format keeps its defaults. 4 spaces, double quotes, line length 88, LF, magic trailing comma respected.
- Ruff lint selects `E W F I N UP B SIM RUF PL S ASYNC PT D ANN PTH T20 BLE TRY`. Do not add `COM` or `ISC`, because they fight the formatter.
- Per-file ignores. Tests drop `S101`, `PLR2004`, `D`, `ANN` and `PLC0415`. `app/bin/**` drops `T20`, because the launcher prints.
- Docstrings follow the Google convention. Every module has a docstring. TODOs read `TODO(owner): text`.
- Pyright runs in strict mode against Python 3.11. Annotate every public function and method, write `X | None`, use built-in generics, and avoid `Any`. `reportAny` is a basedpyright rule, so it is not set. Strict mode already flags unknown types.
- Use `Protocol` only for types you do not own.
- Pydantic v2. Request models set `extra="forbid"`. Use strict fields where input must not coerce. Every route has a `response_model`, so secret fields never leave. A custom `RequestValidationError` handler never leaks file names.
- FastAPI. One `APIRouter` per module, joined with `include_router`. Use a `lifespan` context manager, never `on_event`. Plain `def` endpoints for sqlite3 work.
- Stdlib habits. `logging.getLogger(__name__)` and no `print` in app code. `pathlib` for paths. `subprocess` with list args, no `shell=True`, and `check` and `timeout` set. sqlite3 always uses placeholders, and its context manager commits or rolls back but does not close.
- Pytest runs with `--strict-markers` and `--import-mode=importlib`. Put fixtures in `conftest.py` and prefer `parametrize`. Coverage on `app/server` fails under 85 percent, tests excluded.
- A tests file imports its module whole, for example `import version`, so discovery never runs a class twice.
- Shell wrappers start with `set -euo pipefail`. The source for that habit is unverified, so ShellCheck runs on them in CI.
- GitHub Actions. Pin third-party actions to a full commit SHA, grant the minimum `GITHUB_TOKEN` permissions, and pass untrusted input through environment variables.

## TypeScript and React

- Prettier. `printWidth` 100, 2 spaces, semicolons, double quotes, `trailingComma: "all"`, LF. ESLint uses `eslint-config-prettier` last. There is no `eslint-plugin-prettier`.
- TypeScript is strict with `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `verbatimModuleSyntax` and `erasableSyntaxOnly`. `tsconfig.json` covers `src` with `"types": ["vite/client"]`. `tsconfig.node.json` covers the config files and `e2e`.
- Use unions or `as const` instead of `enum`. Use `interface` for object shapes and `type` for unions. Prefer `unknown` over `any`. No non-null assertions, and `consistent-type-imports` is an error.
- One alias, `@/*` to `src/*`, set in `tsconfig.json` paths and in Vite `resolve.alias` with an absolute path.
- ESLint flat config. typescript-eslint `recommendedTypeChecked` and `stylisticTypeChecked` with `projectService`, `reactHooks.configs.flat.recommended` (it includes the React Compiler rules in 7.1.1), and jsx-a11y `flatConfigs.recommended`. Plain `.mjs` config files skip type-aware rules. Files outside `tsconfig.json` (`vite.config.ts`, `playwright.config.ts`, `e2e/*.ts`) run through `allowDefaultProject`, which allows 8 files by default. Raise that limit or add a tsconfig when `e2e` grows past it.
- React 19. Components are function declarations. Pass `ref` as a prop, never `forwardRef`. Render `<Context>` as the provider. Compute derived state in render. Do not add `useMemo` or `useCallback` before measuring, because the React Compiler memoizes. Keep keys stable. Type props on the parameter, take children as `React.ReactNode`, and never use `React.FC`.
- Server state goes through TanStack Query. Error boundaries use `react-error-boundary`.
- Routing uses React Router's hash router (`createHashRouter`).
- Strings go through literal `t("key")` and `tn("key")` calls. A key passed through a helper reads as unused to the static key test (K-819f).
- Comments. Short prose file headers, TSDoc only on exported shared API, and `TODO(owner or ticket): text`.

## CSS

- Stylelint extends `stylelint-config-standard`. `color-no-hex` is on, so every color goes through a token. `src/styles/tokens.css` is ignored, because it defines the tokens.
- One declaration per line. Use `:focus-visible` outlines. Put motion inside `@media (prefers-reduced-motion: no-preference)`.
- Themes use `prefers-color-scheme` with a `[data-theme]` override. React Aria state goes through data attributes such as `[data-selected]` and `[data-pressed]`.
- Class names follow the component that owns them. The prototype `s4-` and `cs-` prefixes do not carry over. Token names stay.
- The CSP keeps `style-src` strict with a per-request nonce. M0 checks how React handles inline styles under it.

## Accessibility

- Native elements first, then the APG patterns. Give React Aria Components a `Label` child. No positive `tabindex`.
- Axe runs with the `wcag2a` and `wcag2aa` tags.

## Tests

- Vitest config lives in `vite.config.ts` (jsdom, `src/test/setup.ts`, `src/**/*.test.{ts,tsx}`). Setup imports `@testing-library/jest-dom/vitest`.
- Testing Library queries go in this order. `getByRole` first, `getByTestId` last. Call `userEvent.setup()` before `render`.
- Playwright uses user-facing locators and web-first assertions. Each test stands alone. Specs go in `app/web/e2e/`.
- Test sample paths start at `/work/`, because the old suite bans home paths and the habit carries over (T-3ad1).

## Docs

- Markdown is not hard-wrapped.
- No em dashes, no bold, sentence-case headings, and no colons inside prose sentences. Code, paths and list labels may keep colons.
- Write dates month first.

# Scout report 3: front-end, charting, Python helpers, testing, vendoring (2026-11-08)

Sizes are bundlephobia min+gzip of the npm main entry, rough.

## Front end
| Name | Version | Size | No-build | Notes |
|---|---|---|---|---|
| htmx | 2.0.11 npm latest; 4.0.1 GitHub latest (Nov 1, 2026) | ~18 KB (v4 ~11 KB br) | Yes | 0BSD, 0 deps. Pin version; v4 not npm latest |
| Alpine.js | 3.17.5 (Oct 20, 2026) | ~19 KB | Yes | MIT, dep @vue/reactivity |
| Lit | 3.3.3 (May 14, 2026) | ~6 KB | Yes via prebuilt bundles | Decorators without build UNVERIFIED |
| Preact + htm | 11.2.0 (Nov 6, 2026) + 3.1.1 | 5 KB + 0.7 KB | Yes, htm tagged templates | Closest drop-in for hand h() |
| Petite-Vue | 0.4.1 | ~7 KB | Yes | Activity UNVERIFIED |
| Solid | 1.9.18; 2.0 rc | ~8 KB | Partly (solid-js/html, UNVERIFIED) | |
| Svelte | 5.57.3 | UNVERIFIED | No (compiler) | |
| React + Vite | 19.3.1 / 8.3.6 | - | No (JSX transform; Vite needs Node 20.19+/22.12+) | |

## Charting
| Name | Version | Deps | No-build | Stacked bars | Accessibility | Theming |
|---|---|---|---|---|---|---|
| uPlot | 1.6.32 (Mar 2025) | none | IIFE build | Yes (stack.groups) | not mentioned | not mentioned |
| Chart.js | 4.6.1 (Oct 2026) | @kurkle/color | UNVERIFIED | Yes | canvas: dev adds role=img, aria-label, fallback | JS options, no CSS vars |
| Observable Plot | 0.6.19 (Nov 2026) | d3 + 2 | UNVERIFIED (docs 429) | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ECharts | 6.1.0 (May 2026) | tslib, zrender | UNVERIFIED | UNVERIFIED | Auto screen-reader descriptions | JS theme objects; dark theme built in |
| Frappe Charts | 1.6.3 (Apr 2022) | none | Yes | UNVERIFIED | UNVERIFIED | UNVERIFIED; stale |

None verified to theme from CSS variables. Project has hatch patterns and an accessibility exception that requires legend totals or a kinds table on stacked bars.

## Python helpers
| Name | Version | Min Python | Deps | Wheels |
|---|---|---|---|---|
| pydantic | 2.14.3 (Nov 5, 2026) | 3.11 (main pyproject) | pydantic-core (compiled), typing-extensions, annotated-types, typing-inspection | compiled core |
| jsonschema | 4.26.0 (Jan 2026) | - | attrs, jsonschema-specifications, referencing, rpds-py | rpds-py compiled UNVERIFIED |
| msgspec | 0.22.0 (Sep 2026) | 3.10 | none | compiled only |
| orjson | 3.13.0 (Oct 2026) | 3.10 | none | compiled only (57 wheels) |
| watchfiles | 1.3.0 (Sep 2026) | 3.10 | anyio | compiled abi3 |
No verified library for tailing a growing JSONL file.

## Testing
- pytest 9.2.0 (3.10+): runs the existing unittest suite as is; fixtures/parametrize do not work on TestCase classes; load_tests unsupported.
- Playwright for Python 1.64.1 (PyPI requires 3.10; docs say 3.8): standard for real-browser tests.
- node:test: stable, built in, no DOM.
- jsdom 31.0.0 (Node 22.22+/24.15+/26+, 18 deps, no layout) and happy-dom 21.0.4 (Node 20+): could replace fakedom.
- Vitest 5.1.0: needs Vite; conflicts with no-build unless test-only.

## Vendoring
- Import maps: Baseline widely available since March 2023 (MDN). Map bare names to local files.
- Vendoring local files with an import map is the only offline-safe option for 127.0.0.1; manual updates, keep license files.
- jsDelivr/esm.sh need network.

Open: Observable Plot docs, Chart.js and uPlot sizes and CSS theming, Svelte runtime, Solid html docs, pydantic wheel list, rpds-py wheel type.

Sources: npm registry and GitHub release API for each package; htmx.org; four.htmx.org; alpinejs.dev; lit.dev; preactjs.com; react.dev; chartjs.org docs (accessibility, bar, colors); echarts.apache.org feature and handbook; github.com/leeoniya/uPlot README; PyPI JSON for each Python package; docs.pytest.org/en/stable/how-to/unittest.html; playwright.dev/python/docs/intro; nodejs.org/api/test.html; github.com/jsdom/jsdom; github.com/capricorn86/happy-dom; vitest.dev/guide; developer.mozilla.org importmap page.

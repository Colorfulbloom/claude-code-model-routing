# Front-end stack for the local dashboard rebuild (2026-11-08)

Scope: frameworks, components and styling, charts, live data, tree views, drag and drop, i18n, testing, typed API clients. Read first: the prior survey 03-frontend-and-libs.md in the same folder. It covers htmx, Alpine, Lit, Preact, and the no-build lists, so this report does not repeat them.

## How to read the sources

- Quotes come from WebFetch pages. A small model extracted the text, so each quote is close to the page wording but was not checked against raw HTML. Treat quotes as near-verbatim.
- UNVERIFIED means the page I could open did not say it, or the page would not load. Those items come from my own knowledge or the prior survey and need a check.
- The bundlephobia number for react-dom (1.4 kB) looks wrong for React DOM and is not used here.

## Recommendation in one view

Pick one pairing. Do not mix two component libraries.

- Default: React 19 with Vite as a plain single-page app. Radix Primitives or React Aria for controls, a hand-built SVG layer for the custom charts, dnd-kit for card reorder, TanStack Query for data, Paraglide JS for strings, Vitest, Testing Library, Playwright and axe-core for tests.
- Main alternative: Svelte 5 with Vite as a plain single-page app (or SvelteKit with the static adapter in SPA mode). Bits UI for controls, a hand-built SVG layer for charts, svelte-dnd-action or a custom Alt+Arrow reorder for cards, Paraglide JS for strings, the same test set.

Why a plain single-page app. The backend is Python and already serves files on 127.0.0.1. A meta-framework adds server features (routing, server rendering, server actions) that this app does not use. Next.js static export says some of those features stop working in export mode (see section 1). A plain Vite build gives the same output without that layer.

## 1. Frameworks

| Option | Reactivity | Size note | Build output for a local app | Governance and release |
|---|---|---|---|---|
| React 19 + Vite | Hooks and re-render | react-dom size UNVERIFIED (bundlephobia gave 1.4 kB, not used) | Vite static build | React 19 stable, "December 05, 2024 by The React Team" |
| Svelte 5 | Compiled, runes | Size UNVERIFIED | Vite build, or SvelteKit adapter-static | Svelte 5 stable, October 22, 2024 |
| Vue 3 | Proxy-based reactivity | Size UNVERIFIED | Vite build; no-build use also possible | "Vue does not have a fixed release cycle." |
| SolidJS | Fine-grained signals | Solid 1.9.18 about 8.2 kB min+gz (bundlephobia) | Vite build | "With Solid, reactivity is the basis of its design" |
| Angular | Signals | Heavier by design (size UNVERIFIED) | Angular CLI | Angular v22 released 2026-06-03; "A major release every 12 months" |

Sources:
- React 19 stable: https://react.dev/blog/2024/12/05/react-19 (post dated December 05, 2024; "React 19 is now stable!").
- Svelte 5 stable and runes: https://svelte.dev/blog/svelte-5-is-alive (post dated October 22, 2024; "Svelte 5 is finally stable."; runes "an explicit mechanism for ... declaring reactive state"). Runes page: https://svelte.dev/docs/svelte/what-are-runes ("Runes are symbols that you use in .svelte and .svelte.js / .svelte.ts files to control the Svelte compiler.").
- Vue: https://vuejs.org/guide/introduction.html ("Vue automatically tracks JavaScript state changes and efficiently updates the DOM when changes happen."; SFC is "the recommended way ... if your use case warrants a build setup"; "Enhancing static HTML without a build step" is listed as a use). Release page: https://vuejs.org/about/releases ("Vue does not have a fixed release cycle.").
- Solid: https://docs.solidjs.com/concepts/intro-to-reactivity ("With Solid, reactivity is the basis of its design"). Size from bundlephobia: https://bundlephobia.com/package/solid-js (v1.9.18: 8.2 kB, min+gz).
- Angular: https://angular.dev/overview ("Our fine-grained reactivity model, combined with compile-time optimizations"; "Angular CLI includes a fast, modern build pipeline using Vite and esbuild."). Releases: https://angular.dev/reference/releases (v22, 2026-06-03; major every 12 months; "typically supported for 24 months").
- Vite: https://vite.dev/guide/ ("Vite requires Node.js version 20.19+, 22.12+."; "pre-configured to output highly optimized static assets for production").

Meta-framework fit.
- Next.js static export: https://nextjs.org/docs/app/guides/static-exports (page dated 2026-08-09). It produces an out folder, and its unsupported list includes "Server Actions", "Cookies", "Rewrites", "Redirects", and "Image Optimization with the default loader". It also says "Since route transitions happen client-side, this behaves like a traditional SPA."
- React Router SPA mode: https://reactrouter.com/how-to/spa ("you can enable "SPA Mode" by setting ssr:false"; "generate an index.html at build time that you can serve and hydrate as a SPA").
- TanStack Start SPA mode: https://tanstack.com/start/latest/docs/framework/react/guide/spa-mode ("Prerendering your application's root route only."; output "/_shell.html").
- SvelteKit adapter-static: https://svelte.dev/docs/kit/adapter-static ("This will prerender your entire site as a collection of static files."; fallback page name "commonly 200.html"; "You must ensure SvelteKit's ssr option isn't set to false.").

Verdict. React and Svelte are both fine. React has the larger ecosystem and more accessibility primitives (section 2). Svelte has the smaller runtime and a simpler state model. Solid is smaller still but has fewer ready-made accessible components (UNVERIFIED). Angular is too heavy for this app. Use a meta-framework only in its SPA or static mode, and only if routing or i18n routing needs it.

## 2. Components and styling

Headless primitives.
- Radix Primitives (React): "Components adhere to the WAI-ARIA design patterns where possible." and "Components ship without styles". Source: https://www.radix-ui.com/primitives/docs/overview/introduction
- React Aria (React, Adobe): "React Aria is style-free out of the box", "React Aria is designed with accessibility as a top priority", "React Aria is engineered for internationalization out of the box". Source: https://react-aria.adobe.com/ (the old react-spectrum URL redirects here).
- Bits UI (Svelte 5): "a collection of headless component primitives for Svelte 5"; "exposes a class prop and style prop". Source: https://www.bits-ui.com/docs/getting-started. Melt UI mention UNVERIFIED on that page.
- Reka UI (Vue, formerly Radix Vue): "Accessibility is at the heart of Reka UI."; "We handle intricate accessibility details like aria attributes, keyboard navigation, and focus management". Source: https://reka-ui.com/docs/overview/introduction
- Ark UI: the site did not load (DNS error on www.ark-ui.com; the apex returned 404). UNVERIFIED.

Ports of shadcn/ui.
- shadcn/ui copies code into your repo: "shadcn/ui hands you the actual component code." Source: https://ui.shadcn.com/docs. The page does not name Radix or Tailwind; base library UNVERIFIED on that page.
- shadcn-svelte: "Re-usable components built with Bits UI and Tailwind CSS." Source: https://www.shadcn-svelte.com/docs
- shadcn-vue: site did not say it is built on Reka UI. UNVERIFIED.

Styling.
- Tailwind v4: "Tailwind also generates regular CSS variables for your theme variables so you can reference your design tokens in arbitrary values or inline styles." Also: "Without using inline, your utility classes might resolve to unexpected values because of how variables are resolved in CSS." Source: https://tailwindcss.com/docs/theme
- Plain CSS or CSS modules: no extra layer. Components read var(--token) from tokens.css directly. This is an inference from the design, not from a source.

How each consumes an existing token sheet.
- Radix, React Aria, Bits UI, Reka: unstyled, so they take the token sheet as is. Radix says "Components can be styled with any styling solution" (https://www.radix-ui.com/primitives/docs/overview/introduction). Bits UI takes class and style props.
- shadcn-style code: copies in Tailwind classes. To use tokens.css you map each token into the Tailwind theme with @theme inline (see the Tailwind source above). That is a second naming layer for the same tokens.
- Plain CSS: the token sheet is used with no mapping. Light and dark swap on the root or data attribute, which is the design the project already has.

Pick. Radix or React Aria with plain CSS modules (React). Bits UI with plain CSS (Svelte). Skip Tailwind unless the team already writes Tailwind. Reason: the token sheet is already the design source. Tailwind would add a mapping layer and a second place to change colors. Main alternative: shadcn-style copied components with Tailwind @theme inline.

## 3. Charts

What the project needs: stacked bars with legend totals or a kinds table, hatch fills, rings, day bars, theme from CSS variables, AA text, and widths of 375 and 1440.

| Library | Renderer | Verified facts | Gaps |
|---|---|---|---|
| Recharts (React) | SVG | Props `accessibilityLayer` ("Turn on accessibility support for keyboard-only and screen reader users.") and `role` ("The ARIA role for the chart"). Source: https://recharts.github.io/en-US/api/ | Theming API names only (RechartsThemeProvider); CSS-variable theming UNVERIFIED |
| visx (React) | SVG, built on D3 primitives | Site did not load (DNS error) | UNVERIFIED |
| Nivo (React) | SVG and canvas | "nivo provides a rich set of dataviz components, built on top of D3 and React." Source: https://nivo.rocks/ | Renderer detail UNVERIFIED |
| Apache ECharts | Canvas by default; SVG since v4.0 | "ECharts supports rendering with Canvas, SVG (v4.0+), and VML elements."; "supports automatic generation of descriptions based on chart configuration items". Source: https://echarts.apache.org/en/feature.html | Themes: page silent. Prior survey says a built-in dark theme (not re-checked). CSS-variable theming UNVERIFIED |
| Observable Plot | SVG (general knowledge) | Docs returned 429 (rate limit) | UNVERIFIED |
| LayerChart (Svelte) | UNVERIFIED | Page: "Composable Svelte chart components to build a large variety of visualizations". Source: https://layerchart.com/ | Stacking, renderer UNVERIFIED |
| Chart.js | Canvas | "Thus, it is up to the user to create the canvas element in a way that is accessible."; role and aria-label, plus fallback content. Source: https://www.chartjs.org/docs/latest/general/accessibility.html | Pattern fills: Chart.js has a pattern sample page, but the fetch failed (404). UNVERIFIED |
| uPlot | Canvas | "uPlot is a fast, memory-efficient Canvas 2D-based chart for plotting time series, lines, areas, ohlc & bars."; "A small (~50 KB min)"; stacking: "Positive and negative stacking groups through opts.stack.groups". Source: https://github.com/leeoniya/uPlot | No accessibility text; time-series focus |

Recommendation: a hand-built SVG layer for the bar, ring and day views. Reason: the project needs a legend total, hatch fills in <pattern> elements, and CSS-variable colors on every mark, plus a text table beside each chart. Chart libraries bring their own legend and tooltip rules, which fight those needs. Inference, not sourced: SVG pattern elements and CSS variables in fill attributes work in any SVG chart. Pair with d3-scale and d3-shape if you want math helpers only. Pair this with React or Svelte, whichever you pick.

Main alternative: Recharts (React) with its accessibilityLayer prop, if you accept its default look. Pair with React + Radix. Use ECharts for a complex canvas chart with auto descriptions; it is a heavier, separate theme system.

## 4. Live updates and data fetching

- EventSource (Server-Sent Events). Browser reconnect is built in. MDN: "By default, if the connection between the client and server closes, the connection is restarted." and the retry field: "the browser will wait for the specified time before attempting to reconnect." Source: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events. Limit: "When not used over HTTP/2, SSE suffers from a limitation to the maximum number of open connections" and "the limit is per browser and is set to a very low number (6)." Same source. Impact here: several open Live tabs on HTTP/1.1 can exhaust the six-connection limit. The Python server must handle this.
- Last-Event-ID resume: the spec and server support are UNVERIFIED on the page I read (the page does not name the header).
- WebSocket: MDN's client guide I read covers errors and close events and a pageshow restore, not automatic reconnect. Source: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications. The guide does not describe reconnect after a network drop, so plan to write it.

Pick: SSE for the Live page, because the flow is one way (server to browser) and the browser handles reconnect. Use WebSocket only if the browser must send messages in real time (not stated for this app).

Query layer.
- TanStack Query: "it makes fetching, caching, synchronizing and updating server state in your web applications a breeze." Source: https://tanstack.com/query/latest/docs/framework/react/overview. The React page names React only. Latest core release tag 5.107.1 on November 6, 2026. Source: https://github.com/TanStack/query/releases.
- Svelte, Vue, Solid, and Angular adapters: the page I read did not name them. UNVERIFIED. The streamedQuery reference page returned 404, so streamed-query support is UNVERIFIED.
- SWR: "a React Hooks library for data fetching from Vercel."; "The name comes from stale-while-revalidate." Source: https://vercel.com/oss/swr (the old swr.vercel.app URL redirects here).

Pick: TanStack Query for React. Use it with an EventSource handler that writes into the cache. Event-to-cache wiring is an inference, not sourced. Alternative for Svelte: a small store that wraps EventSource. Keep the store in the app code, which avoids a library dependency.

## 5. Tree and graph for dispatch trees

- React Flow (xyflow): "A customizable React component for building node-based editors and interactive diagrams"; "React Flow is a MIT-licensed open source library." Svelte Flow is named as a sibling project. Source: https://reactflow.dev/
- Cytoscape.js: "A fully featured graph library written in pure JS"; "No external dependencies."; "Uses layouts for automatically or manually positioning nodes". Source: https://js.cytoscape.org/. Canvas use: the page says "ES5 and canvas support are required", and that is the only canvas mention I read.
- ELK (Eclipse Layout Kernel): "ELK itself doesn't render the drawing but only computes positions." Source: https://eclipse.dev/elk/. The elkjs package name was not on that page.
- d3-hierarchy: "construct 'tidy' tree diagrams of hierarchies"; "construct tree diagrams that place leaf nodes at the same depth". Source: https://d3js.org/d3-hierarchy. The page does not say it returns positions without drawing. That is general knowledge, UNVERIFIED here.

Pick: d3-hierarchy (tidy tree) plus SVG drawn by the framework, for a read-only dispatch tree. It is small and matches the no-canvas, no-drag need. Main alternative: React Flow (React) if the tree needs pan, zoom, drag, or edit. Cytoscape.js only if the graph grows past trees.

## 6. Drag and drop and card reorder

- dnd-kit: "First-class support for React, Vue, Svelte, Solid, and TypeScript"; sensors for "mouse, touch, and keyboard". Source: https://dndkit.com/. Maintenance status not stated on that page; check the GitHub repo before choosing (fetch of the repo page did not show a date). UNVERIFIED on maintenance.
- Pragmatic drag and drop (Atlassian): "Works with any frontend framework"; "Tiny: ~4.7kB core"; "These pieces are unopinionated about visual language or accessibility". Source: https://github.com/atlassian/pragmatic-drag-and-drop. The project would build its own keyboard path.
- svelte-dnd-action: "Fully accessible (beta) - keyboard support, aria attributes and assistive instructions for screen readers"; "It is being actively maintained." Source: https://github.com/isaacHagoel/svelte-dnd-action
- SortableJS: "JavaScript library for reorderable drag-and-drop lists". Its keyboard support and dependency count were not on the page. UNVERIFIED.
- Keyboard reorder pattern. WAI-ARIA APG rearrangeable listbox uses Up and Down action buttons with Alt + Up Arrow and Alt + Down Arrow, and "keeps focus on the option that is moved up". Source: https://www.w3.org/WAI/ARIA/apg/patterns/listbox/examples/listbox-rearrangeable/

Pick: dnd-kit (React) with its keyboard sensor, plus Alt+Arrow buttons that follow the APG pattern so that a keyboard user does not depend on drag. Alternative for Svelte: svelte-dnd-action, but its keyboard support is marked beta. Pragmatic drag and drop is the choice if you want the smallest core, and then the keyboard path is yours to build.

## 7. i18n

- Paraglide JS (inlang): "Compiler-first i18n for React, TanStack Start, SvelteKit, and any Vite app."; "Messages compile to ESM functions, so unused translations are eliminated by your bundler."; works with "React, TanStack Start, SvelteKit, React Router, Astro, Vue, Solid, and vanilla JS/TS." Source: https://paraglidejs.com/ (the inlang URL redirects here).
- i18next: "call t() in Node.js, the browser or any framework."; plurals through "key suffixes". Source: https://www.i18next.com/overview/getting-started (the overview/introduction URL returned 404). react-i18next wrapper named on that page.
- FormatJS: ICU message syntax, "it builds on ICU Message Formatting by using the ICU Message Syntax"; the Intl polyfill is recommended where needed. Source: https://formatjs.github.io/docs/intl/
- vue-i18n: "Internationalization plugin for Vue.js." Source: https://vue-i18n.intlify.dev/

Pick: Paraglide JS. It compiles message keys into typed functions, so unused strings drop out and a missing key fails the build. Main alternative: i18next with react-i18next for runtime loading and plural rules. Note for the project: the HiveMind fact K-819f says the static strings test counts a key only when it appears in a literal t("key") call. A compiled message function changes that test. Plan the test change with the switch to Paraglide. Not checked against the repo here.

## 8. Testing

- Vitest: "Vitest (pronounced as veetest) is a next generation testing framework powered by Vite."; "Vitest requires Vite >=v6.4.0 and Node >=v22.12.0". Source: https://vitest.dev/guide/. Needs Vite, so it is a build-time tool and fits the new build step.
- Testing Library: "The more your tests resemble the way your software is used, the more confidence they can give you."; separate packages for Vue and Svelte. Source: https://testing-library.com/docs/react-testing-library/intro/
- Playwright component testing: "It is stable."; works for "React, Vue, Svelte, Solid or anything else: if your dev server can render it, Playwright can test it." Source: https://playwright.dev/docs/test-components . Playwright E2E is the usual choice for the real app and for the 375 and 1440 widths.
- axe-core: "Axe is an accessibility testing engine for websites and other HTML-based user interfaces."; "you can find on average 57% of WCAG issues automatically."; "axe-core could not be certain, and manual review is needed." Source: https://github.com/dequelabs/axe-core. Playwright integration: "@axe-core/playwright package which adds support for running the axe accessibility testing engine". Source: https://playwright.dev/docs/accessibility-testing
- Storybook: "It provides an isolated iframe to render components without interference from app business logic and context."; "Audit story accessibility with Axe." Source: https://storybook.js.org/docs/get-started/why-storybook . Optional for this app.
- Histoire: not checked. UNVERIFIED.

Pick: Vitest and Testing Library for units, Playwright for E2E and component tests at 375 and 1440, axe-core inside Playwright for AA checks. Storybook only if the design work needs a component catalog.

## 9. Typed API client from OpenAPI

- openapi-typescript: "Convert OpenAPI 3.0/3.1 schemas to TypeScript types and create type-safe fetching."; "Static TypeScript types provide zero runtime cost and zero client weight." Source: https://openapi-ts.dev/. The openapi-fetch client name is UNVERIFIED on that page.
- orval: "Transform your OpenAPI specs into type-safe clients, mocks, and validators."; generates hooks for "React Query, SWR, Angular, Vue, Svelte, and Solid."; "Auto-generate MSW handlers with Faker.js data." Source: https://orval.dev/
- hey-api: not checked. UNVERIFIED.

Pick: openapi-typescript for types with zero runtime cost. Reason: the app has a few endpoints, and a small typed fetch wrapper is enough. Main alternative: orval if you want generated TanStack Query hooks and MSW mocks. Open question: does the Python backend emit an OpenAPI schema? FastAPI does by default, but this server's framework is [NEEDS CONFIRMATION: which Python web framework the dashboard server uses]. Without a schema, skip the generator and write the types by hand.

## Pairings

- React path: React 19 + Vite (SPA) + Radix or React Aria + CSS modules on tokens.css + hand SVG charts (Recharts as alt) + d3-hierarchy or React Flow + dnd-kit + TanStack Query + EventSource + Paraglide + Vitest + Testing Library + Playwright with axe-core + openapi-typescript.
- Svelte path: Svelte 5 + Vite (SPA) or SvelteKit with adapter-static in SPA mode + Bits UI + plain CSS on tokens.css + hand SVG charts (LayerChart as alt, UNVERIFIED) + d3-hierarchy or Svelte Flow + svelte-dnd-action (beta keyboard) or custom Alt+Arrow + a store over EventSource + Paraglide + Vitest + Testing Library + Playwright with axe-core + openapi-typescript.
- Mixed pairs are not recommended. A React chart library does not fit a Svelte app, and two component kits mean two focus models.

## Not verified or not checked

- Bundle sizes for React DOM, Svelte, Vue, Angular and Preact runtime (only Solid 8.2 kB was read, from bundlephobia).
- Governance (who owns each project and how decisions are made) was not checked for any framework.
- Ark UI, visx, Observable Plot, shadcn-vue base library, Chart.js pattern fills, streamedQuery, hey-api, Histoire, dnd-kit maintenance status, SortableJS keyboard support, Melt UI, Last-Event-ID support.
- Recharts CSS-variable theming and hatch fills in each chart library.
- Whether the Python server can handle many SSE connections under the six-connection limit. Needs a test.

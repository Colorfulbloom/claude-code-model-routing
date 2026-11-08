# Scout report: accessibility details (2026-11-08), condensed by main session. WCAG/MDN quotes via WebFetch summaries.

Gaps in current app: no per-page title (app.js:571 project-level only), no focus move on route change, no route announcement, no forced-colors rule, no color-scheme meta, no 320 px reflow test, no JS reduced-motion check. Already has: :focus-visible outlines (app.css:23 etc.), reduced-motion gating (app.css:918, live.css:4,187, live_flow.js:18), Live pause button and polite status line (live.js:266,280), polling stops when hidden (live_poll.js), polite regions on rules and edit pages, focus restore after rebuilt controls (app.js:291-319).

Checklist for the rebuild:
| Requirement | How | Test |
|---|---|---|
| 2.4.2 title per route | document.title "Page, Routing Dashboard" | Playwright page.title() |
| Focus on route change | focus page h1 tabindex=-1 (Gatsby user test: heading worked best) | assert activeElement |
| 4.1.3 route announcement | one polite status line | toMatchAriaSnapshot |
| 2.4.11 focus not obscured | scroll-padding-top under sticky shell/toasts | tab through, check boxes |
| 2.5.7 dragging | drag + Move up/Move down buttons (keyboard path alone not enough for pointer) | pointer-free click script |
| 2.5.8 target size | >= 24x24 CSS px | axe target-size + computed size |
| 3.3.7 redundant entry | prefill in edit flow | manual |
| 1.4.11 non-text 3:1 | keep --rk exception scoped | tests/test_tokens_contrast.py |
| 1.4.10 reflow | no horizontal scroll at 320 and 375 | Playwright scrollWidth |
| 1.4.12 text spacing | no clipping | injected CSS |
| 4.1.3 + 2.2.2 live | announce state changes only; keep Pause | fake clock, count announcements |
| reduced motion | CSS and JS gating | emulate reducedMotion |
| theme without inline script | <meta name="color-scheme"> in head; external script if stored theme | first-paint screenshot, CSP check |
| forced colors | borders and SVG shapes, no background-image for meaning | emulate forcedColors |
| charts 1.1.1/1.4.1 | svg role=img aria-labelledby visible title; kinds table; patterns | axe + VoiceOver |
| status messages | role=status on save/undo | aria snapshot |
| 3.2.6 consistent help | same place if help exists | manual |

Notes: React Aria announce() defaults to assertive; pass 'polite' (pinned GitHub source). React Aria DnD: Enter starts drag, Tab between targets, Escape cancels, announcements built in (https://react-aria.adobe.com/dnd). axe tags wcag22aa; skips hidden regions and modals (https://github.com/dequelabs/axe-core/blob/develop/doc/API.md). Playwright docs list wcag2aa/wcag21aa (https://playwright.dev/docs/accessibility-testing). Deque: automation found 57.38% of issues (vendor data).
Sources: W3C WCAG 2.2 Understanding pages (focus-not-obscured-minimum, dragging-movements, target-size-minimum, consistent-help, redundant-entry, status-messages, non-text-contrast, reflow, text-spacing, pause-stop-hide, page-titled, non-text-content), MDN live regions, prefers-reduced-motion, forced-colors, color-scheme, CSP, SVG title, img role.

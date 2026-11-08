# Text editor under a strict CSP (round 3, spike 4)

Written 2026-11-08. Spike folder: `S` = /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/4-editor

## Recommendation

- Use CodeMirror 6 with the per-request nonce (variant b). It ran clean under `style-src 'self' 'nonce-X'`: zero violations, styled editor, merge diff view rendered.
- Do not rely on the shadow DOM route (variant c) as the main plan. It also ran clean with no nonce, but it isolates the editor from page CSS and costs a wrapper. Keep it as the fallback if the server cannot rewrite the HTML per request.
- Reject Monaco. It needs inline styles and blob workers under a strict policy and the upstream issue has been open since 2016. A plain textarea plus jsdiff is the cheap fallback (3.6 KB gz) but gives no syntax highlighting or YAML-aware editing.

## Options

| Option | CSP result | gz size | a11y | Notes |
|---|---|---|---|---|
| CM6, no nonce, document root (a) | FAILS. 3 `style-src-elem` violations, gutters and merge colors unstyled (gutter bg rgba(0,0,0,0)) | 192,875 B | Same as below | Editor is usable but unstyled |
| CM6 + `EditorView.cspNonce` + header nonce (b) | PASS. 0 violations, gutter bg rgb(245,245,245), merge rendered | 192,875 B | role=textbox, aria-multiline=true | Needs nonce in HTML and header |
| CM6 in a shadow root, no nonce (c) | PASS. 0 violations, styled, merge rendered | 192,875 B | Same | style-mod adopts a constructed sheet; page CSS does not reach in |
| Header nonce but no facet (e) | FAILS. Same 3 violations as (a) | 192,875 B | n/a | The header alone does nothing |
| Monaco | Needs `style-src 'unsafe-inline'` and `worker-src blob:` (desk research only, not spiked) | Not measured | Has screen reader mode, Ctrl+M tab toggle | Not recommended |
| textarea + jsdiff | Not run under the CSP; no style injection by design (inference) | 3,559 B (diff + component) | Native textarea | No highlighting, no folding, diff is a separate read-only block |

React 19 entry shared by both builds: 66,885 B gz (not counted above). Sizes: `gzip -9 -c file | wc -c`, in `S/gzsizes.txt`. The CM chunk holds view, state, commands, language, lang-markdown (which pulls lang-html, per `S/cm/node_modules/@codemirror/lang-markdown/package.json`), lang-json, lang-yaml and merge. Vite's own report said 194.54 kB gz at its default level.

## Exact CSP header

Plain server (a, c): `default-src 'self'; script-src 'self'; style-src 'self'`
Nonce server (b, e): `default-src 'self'; script-src 'self'; style-src 'self' 'nonce-<per request>'`
Server: `S/cm/serve.py` (copied from the 3-csp spike, header trimmed to the brief's policy). The nonce is substituted into `<meta name="csp-nonce" content="__CSP_NONCE__">` in index.html; the app reads it and passes `EditorView.cspNonce.of(nonce)`.

## Spike results

Setup: Vite 7.3.7, React 19.3.1, @codemirror/view 6.43.15, merge 6.12.3, lang-yaml 6.1.3 (it exists), style-mod 4.1.4. Chromium 1254 from the 3-csp spike, headless. Ports 41873 and 41874. Five editors on the page: markdown with front matter, JSON, YAML, and a MergeView of two markdown docs.

- a, no nonce: `S/results/a-no-nonce.json`. 3 securitypolicyviolation events and 3 console errors ("Applying inline style violates ... style-src 'self'"). The editors exist (5), tokens are highlighted (41 tokens) but the base theme did not apply. Merge DOM exists (`.cm-mergeView`, 4 `.cm-changedLine`) but changed-line background is transparent.
- b, nonce: `S/results/b-nonce.json`. 0 violations, 0 console messages. Gutter bg rgb(245,245,245), changed-line bg rgba(160,128,100,0.08), 2 merge panes, 3 changed-text spans, 1 `<style>` tag carrying the nonce. Screenshot: `b-nonce.png`.
- c, shadow root: `S/results/c-shadow.json`. 0 violations, styled, `adoptedStyleSheets` length 1 on each of 4 shadow roots, 0 `<style>` tags.
- d, indentWithTab, e, header-only: `d-indentWithTab.json`, `e-nonce-header-no-facet.json` (d has the same CSP failure as a because it ran without a nonce; its use is the keyboard note below).
- Style attributes: CM sets `style.cssText` through CSSOM (view index.js line 74, 86, 95), which CSP does not restrict. No `style-src-attr` violation appeared in any run.
- WebKit: not installed under the spike browsers path, so not run.

Source evidence (style-mod, `S/cm/node_modules/style-mod/src/style-mod.js`):
- Lines 92-98: `if (!root.head && root.adoptedStyleSheets && win.CSSStyleSheet)` uses `new CSSStyleSheet`; otherwise line 100-101 creates a `<style>` tag and sets `nonce`.
- `Document` has `.head`, so the main document always takes the `<style>` branch. Only a ShadowRoot takes the adoptedStyleSheets branch. So variant (c) needs a shadow root; "rely on adoptedStyleSheets" in the plain document does not work (confirmed by variant a).
- Lines 123 and 132-133: `insertRule` into the sheet, then `root.adoptedStyleSheets = [...]`.
- `@codemirror/view/dist/index.js` line 8380-8383: `mountStyles` reads `EditorView.cspNonce` and passes `{ nonce }` to `StyleModule.mount`. Line 9044 defines the facet. Doc comment in `dist/index.d.ts` line 1425-1428.

## Keyboard and accessibility (CM6)

- Content element attributes (all variants): `role="textbox"`, `aria-multiline="true"`, `contenteditable="true"`, `spellcheck="false"`; I added `aria-label="File editor"` through `EditorView.contentAttributes`. Source: view index.js lines 8340-8356.
- Default setup, Tab: focus left the first editor for the next one, no trap (`S/results/kbd-default-nonce.json`). CM leaves Tab unbound on purpose to avoid a keyboard trap: https://codemirror.net/examples/tab/
- With `indentWithTab`: Tab indented ("  X---"), Shift+Tab outdented, Escape then Tab moved focus to the next editor, and Escape, wait 2.5 s, Tab indented again (`S/results/kbd-indentWithTab-nonce.json`). Source for the 2 second window: view index.js lines 4652 and 5001-5003. Docs: same URL as above. `toggleTabFocusMode` is bound to Ctrl-m (Shift-Alt-m on macOS) in the default keymap (commands index.js line 1794, 1816).
- Recommendation for the rebuild: do not add `indentWithTab` to config files unless a visible hint says "Press Escape then Tab to leave the editor". Plain Tab is safer for keyboard users.

## Desk research

- CM6 style injection: style-mod README comment on `StyleModule.mount` ("If a Content Security Policy nonce is provided, it is added to the `<style>` tag"), style-mod.js line 78-80 (local). Facet docs: https://codemirror.net/docs/ref/#view.EditorView%5EcspNonce (the page was too large for the fetch tool to confirm; local d.ts used instead).
- Monaco and strict CSP: https://github.com/microsoft/monaco-editor/issues/271 ("Do not use inline styles!", opened 2016, still open; maintainers in December 2023 said no plan within six months; nonce works only for scripts in the loader; hash approach fails because style content changes at runtime). Monaco workers: https://github.com/microsoft/monaco-editor/blob/main/docs/integrate-esm.md (Vite uses `new Worker(..., { type: 'module' })`; page says nothing about CSP). Blob workers and `worker-src`: https://www.w3.org/TR/CSP (fallback chain worker-src, child-src, script-src, default-src); real-world examples need `worker-src blob:` (search result, not primary docs).
- Monaco a11y: https://github.com/Microsoft/monaco-editor/wiki/Accessibility-Guide-for-Integrators (`accessibilitySupport`), https://github.com/Microsoft/monaco-editor/wiki/Monaco-Editor-Accessibility-Guide. Word wrap is disabled when accessibilitySupport is "on" (GitLab MR discussion, secondary).
- jsdiff: https://github.com/kpdecker/jsdiff. Exports `diffLines`, `diffJson`, `createPatch`, `structuredPatch`; BSD-3-Clause; ships types since v8; installed 8.0.4.

## Setup notes for the rebuild

- Nonce needed: yes, for CM6 in the main document. The server must generate a fresh nonce per HTML response, put it in the header and in a meta tag (or a `data-` attribute), and the app must add `EditorView.cspNonce.of(nonce)` to every editor's extensions (each MergeView pane too; mine did).
- The built JS must stay external files (`script-src 'self'`); Vite's output was clean in all runs.
- Static serving of index.html without per-request rewriting rules out (b). Then use (c) and mount the editor in a shadow root, and import editor styling inside it.
- Lazy-load the editor chunk (193 KB gz) so other pages do not pay for it.
- Pick one language per file kind: markdown() for CLAUDE.md, agents and skills; json() for settings. YAML front matter inside markdown is highlighted by lang-markdown only as generic content (inference, not verified); use `yaml()` on the front matter slice if needed.

## UNVERIFIED

- Real screen reader behavior (VoiceOver, NVDA) with CM6 and MergeView. Only DOM attributes were read.
- WebKit and Firefox results (not installed).
- Monaco and textarea+diff under the strict CSP were not run; Monaco claims rest on issue #271 and search results; the textarea claim is an inference.
- Whether front matter in lang-markdown gets YAML highlighting.
- Minified production behavior with a CSP `report-uri`; only console and DOM events were collected.
- Gzip level: sizes use `gzip -9`; the server will likely use a different level.

# Direction A components

The component spec for the Routing Dashboard rebuild, direction A. It sits beside the design source, `site/tokens.css`, whose header holds the surface system and every contrast grade. This file never repeats a token value. It names tokens, and tokens.css says what they are.

The sheet that shows every component in every state is `shots/a-components-<1440|375>-<light|dark>.png`. It's built from `site/components.js` with the canonical rules in `site/components.css`. Those rules are scoped to `.cs`, so the round 1 to 4 screens still show the pre-canonical look. The build applies the canonical rules app-wide (see "Differences resolved").

Status of this file: designer spec. Words on screen come from `site/strings*.js`, drafted by tech-writer (the sheet words are in `site/strings3.js`). The purpose lines below are designer drafts for the build team, not product copy.

Stack mapping: React 19, React Aria Components (RAC), plain CSS, hand-drawn SVG. Each entry names the RAC component, or the WAI-ARIA Authoring Practices (APG) pattern when RAC has none.

## Shared rules

These rules apply to every component.

- Focus. Every focusable element shows `outline: var(--focus-width) solid var(--focus-ring)` at `var(--focus-offset)` on `:focus-visible` only. A control whose native input is visually hidden (segmented choice, custom checkbox) draws the ring on its visible box through `:has(input:focus-visible)`. Never remove an outline without that replacement.
- Hover. Neutral surfaces use `--nav-hover-bg`. The primary button uses `--accent-hover`. Hover never moves anything: the lift is 0, and pressed moves 1px down (owner rule, October 23).
- Disabled. Use `aria-disabled="true"` instead of the `disabled` attribute on buttons, so the control stays focusable and its reason can be read. Show a dashed `--border-strong` border with `--text-muted` text. Never use opacity alone. A disabled control always has a visible reason nearby, tied with `aria-describedby`.
- Loading. There's no spinner and no lasting motion. A busy control keeps its size, swaps its label to the writer's busy word (`cs_saving`) and sets `aria-busy="true"`. A busy region shows skeleton bones at measured heights, `aria-busy="true"` and one screen-reader line (`cs_tb_loading`).
- Glyph marks. Status and run-state glyphs come from CSS `::before`. Write them with empty alt text, `content: var(--status-in-effect-mark) / ""`, so screen readers say the word only, not "black circle In effect".
- Targets. Every pointer target is at least 24 by 24 px with spacing, and at least 32 px tall for buttons. Phone tab bar items are 52 px tall.
- Type. Body is `--font-sans` at `--text-md`. Code, paths, keys and line numbers use `--font-mono`. Name the family on every new block, because a framework body font can leak in.
- Never colour alone. Status = glyph + word. Model = shape + name (`.sw`). Kind = pattern + legend text. Diff = +/- glyph + line tint.

## Layout rules

- Shell. Two columns at 721 px and up: a 224 px sidebar (`--sidebar-bg`, sticky, full height) and a fluid main. At 720 px and below the sidebar is hidden. A sticky 52 px top bar shows the page name and project, and a fixed 5-item tab bar sits at the bottom.
- Main padding. At 1440: `--space-5` top, `--space-6` sides, `--space-7` bottom. At 375: `--space-3` top, `--space-4` sides (the 16 px gutter), and 96 px bottom so the tab bar never covers content.
- Max width. Main content stops at 1280 px and stays left-aligned. This is new in this round, because the screens were drawn at 1440 where main is 1152 px. It keeps tables and prose readable on wide monitors. Owner decision 1.
- Page header (`.ph`). `--space-4` below. h1 at `--text-xl` semibold, sub at `--text-md` muted. Right-hand controls wrap under the title at narrow widths.
- Vertical rhythm. `--space-4` between sibling cards and grids, between the tile row and the next card, and under a card header. Inside a card, `--space-4` between blocks, and `--space-2` between rows of a raised list.
- Grids. `.grid` is a one-column stack with `--space-4` gap. `.grid.two` is two equal columns and collapses to one at 720. `.tiles` has 4 columns at 1440 and 2 at 375 (gap `--space-2`). List plus inspector is 340 px + fluid, 280 px + fluid below 1100, and one column at 720.
- Cards at 375. Full width inside the 16 px gutter. Padding drops from `--space-4 --space-5 --space-5` to `--space-3 --space-4 --space-4`, and the radius from `--radius-xl` to `--radius-lg`. Cards never sit side by side on a phone. Wells drop to `--space-2 --space-3` padding.
- Breakpoints. Two only: 720 (phone) and 1100 (narrow desktop, list plus inspector only). Scan the 720 to 1100 range for overflow when a component changes.
- Surfaces. Page, card, well and raised, with their placement rules, live in the tokens.css header ("Surface system"). Don't restate them here, and don't invent a fifth surface.
- Bare pages (locked, first run). No shell. Brand at top left, one card centred at most 560 px wide, `--space-7` from the top (`--space-4` on a phone).

## Components

Each entry lists purpose, anatomy, states, variants, tokens, mapping, keyboard, phone behaviour and copy keys. "Sheet" names its section on the component sheet.

### 1. Sidebar navigation
- Purpose. The main way between pages at 721 px and up. Use it for top-level pages only. In-page views use the segmented control.
- Anatomy. Brand, project Select, grouped links (Live; Review: Summary, Sessions, Agents, Models; Setup: Your setup, To fix; Reference: How Claude Code decides, Glossary), and the footer version line. Each link has an icon (aria-hidden), a label and an optional end slot (the Working mark on Live, the count on To fix).
- States. Default, hover (`--nav-hover-bg`), focus-visible ring, selected (`--nav-active-bg`, `--accent` text, `aria-current="page"`).
- Tokens. `--sidebar-bg`, `--border`, `--nav-hover-bg`, `--nav-active-bg`, `--accent`, `--text`, `--text-muted`, `--radius-md`, `--space-1..4`.
- Mapping. `<nav aria-label>` with RAC Link items. Group headings are text, not buttons.
- Keyboard. Tab through links in order. Enter follows the link.
- Phone. Hidden. The tab bar and the More page replace it.
- Copy keys. `nav_*`, `tofix_count`, `nav_working`.
- Sheet. "Sidebar and tab bar".

### 2. Phone tab bar and top bar
- Purpose. Navigation at 720 px and below. Five items: Live, Review, Setup, To fix (with count) and More.
- Anatomy. Fixed bottom bar with icon over label. The count badge is outlined. The top bar is sticky with the page name and project.
- States. Default (muted), selected (`--accent`, `aria-current="page"`), focus-visible.
- Tokens. `--sidebar-bg`, `--border`, `--accent`, `--text-muted`, `--radius-pill`.
- Mapping. `<nav>` with RAC Link. The count is part of the accessible name ("To fix, 4").
- Keyboard. Tab order follows reading order. The tab bar comes last in the DOM.
- Copy keys. `nav_live`, `nav_review`, `nav_setup_h`, `nav_tofix`, `nav_more`, `tofix_count`.

### 3. Page header and breadcrumb
- Purpose. Names the page and its scope. A breadcrumb appears only on level-3 pages (surface pages under Your setup).
- Anatomy. Optional breadcrumb (link / current), h1, sub line, optional right-hand controls.
- States. The breadcrumb link has default, hover underline and focus. Its target is at least 26 px tall through padding.
- Tokens. `--text-xl`, `--weight-semibold`, `--text-muted`, `--accent`, `--space-4`.
- Mapping. RAC Breadcrumbs in `<nav aria-label="Breadcrumb">`. The current page carries `aria-current="page"`.
- Phone. Hidden while a sheet is open. The sheet header takes over.
- Copy keys. Per page (`su_h1`, `sp_h1`, `rv_h1` and so on).
- Sheet. "Card and page header".

### 4. Scope bar (Review)
- Purpose. Sets what Review shows: a range (default last 30 days) or one session. It's always the top of a Review page.
- Anatomy. Title and sub (range dates or "This session is still running"), then on the right a Range Select, or for a session the back link, a Session Select and "Open in Live".
- States. Range scope, session scope. Select states follow component 14.
- Tokens. Those of the page header and Select.
- Mapping. Header region with RAC Select. The back link is RAC Link.
- Keyboard. Tab to each control. Select opens with Enter, Space or Alt+Down.
- Phone. Controls wrap under the title. The Review views become a segmented control (component 13) under the bar.
- Copy keys. `rv_h1`, `rv_range_lab`, `rv_range`, `rv_range_sub`, `rv_session_scope`, `rv_session_value`, `rv_back`, `rv_open_live`, `rv_still`.

### 5. Card
- Purpose. The unit of a page. One question, one answer. Use one card per question the owner asks of the page.
- Anatomy. Header (h2 title, then an optional count, an optional question in muted text and an optional right slot), then the body (wells, raised findings, text) and an optional foot note.
- Variants. Standard, empty (component 30), gate (bare pages).
- Tokens. `--card-bg`, `--card-border`, `--radius-xl` (phone `--radius-lg`), `--space-4`, `--space-5`, `--text-lg`, `--text-muted`.
- Mapping. `<section aria-labelledby>` pointing at its h2.
- Copy keys. `*_h` (title), `*_q` (question).
- Sheet. "Card and page header".

### 6. Well
- Purpose. Holds data inside a card: chart plots, tables, row lists, diffs, editors and command boxes. Placement rules are in the tokens.css header.
- Anatomy. A bordered inset box. The default padding is `--space-3 --space-4`. List wells set horizontal padding only, and diffs and editors set 0.
- States. None of its own.
- Tokens. `--inset-bg`, `--inset-border`, `--radius-lg`.
- Phone. Padding `--space-2 --space-3`.

### 7. Raised finding
- Purpose. A judged result inside a card: a model check hit, a warning before save, Saved, Overwritten, Preview failed, a To fix row, the effect block, the read-only reason.
- Anatomy. Raised box, optional 4 px start edge, h3 or bold lead, body, optional actions.
- Variants. Plain (effect, read-only reason, To fix row in a group), check (edge `--status-lowered-fg`), warning and overwritten (edge `--status-overridden-fg`, ▲ glyph), saved (edge `--status-in-effect-fg`, ✓), error (edge `--status-invalid-fg`, ✕), risky confirm (component 25).
- Edge rule. A start edge marks a finding that stands alone. Rows inside a group (To fix) get no edge, because the group heading already carries the mark. The edge colour always repeats a glyph and word inside the box.
- States. Saved and Overwritten are `role="status"`. Preview failed is `role="alert"`, because it blocks Save.
- Tokens. `--raised-bg`, `--raised-border`, `--radius-lg`, the `--status-*-fg` for the edge.
- Copy keys. `ed_warn_h`, `ed_warn`, `ed_saved`, `ed_saved_meta`, `ed_undo`, `ed_over`, `ed_review_changes`, `cs_prev_err`, `cs_prev_err_a`, `mc_ex_*`.
- Sheet. "Raised finding".

### 8. Notice line
- Purpose. One fact that affects trust in the page but isn't a problem in the setup, such as the version gap. It sits above the cards.
- Anatomy. A raised strip with a status mark, one sentence and an optional link at the end.
- Variants. Single notice (strip). Several notices go in a Notices card as a list well (To fix).
- Tokens. `--raised-bg`, `--raised-border`, `--radius-lg`, `--text-sm`.
- Mapping. Static text. Use `role="status"` only when it appears after load.
- Phone. The link wraps under the sentence.
- Copy keys. `su_version`, `su_version_link`, `rf_banner`, `fx_n1`, `fx_n2`.

### 9. Button
- Purpose. Starts an action. Use a link for navigation (it may look like a button, for example "Open in MCP servers").
- Variants.
  - Primary: one per view, the action the screen exists for (Save to file, Preview change, Check again, Review changes).
  - Secondary: everything else (Copy path, Undo, Back).
  - Quiet: low-stakes or dismissive actions in text flow (Cancel, Back to last 30 days, Clear search).
  - Danger: only the confirm inside a risky confirm.
  - Icon: Close on the phone sheet, with an aria-label.
- States. Default; hover (neutral `--nav-hover-bg`, primary `--accent-hover`, danger `--status-invalid-bg`, quiet adds an underline); focus-visible ring; pressed (1 px down); disabled (dashed `--border-strong`, muted text, `aria-disabled`); loading (label swaps to `cs_saving`, `aria-busy`, solid border kept so it doesn't read as disabled).
- Tokens. `--accent`, `--accent-hover`, `--text-on-accent`, `--border-strong`, `--card-bg`, `--nav-hover-bg`, `--status-invalid-fg`, `--status-invalid-bg`, `--radius-md`, `--space-3`.
- Mapping. RAC Button (APG Button).
- Keyboard. Enter and Space activate.
- Phone. Action rows stack full width, primary first. On a sheet the actions sit in a sticky foot.
- Placement. Primary sits at the end of an action row, away from Back or Cancel at the start. A button names its target ("Save to settings.local.json").
- Copy keys. Per action. `cs_saving` while busy.
- Sheet. "Buttons", all five variants by six states.

### 10. Status chip
- Purpose. The verdict on a setting value. Exactly seven words: In effect, Overridden, Ignored, Lowered, Invalid, Default, Unknown. Use it only for setting status, never for runs or errors.
- Anatomy. Pill with a glyph (from `--status-*-mark`) and the word.
- States. None (not interactive).
- Tokens. `--status-<word>-fg`, `--status-<word>-bg`, `--status-<word>-mark`, `--status-unknown-border`, `--radius-pill`, `--text-sm`.
- Mapping. Text. The glyph uses the empty-alt `content` rule.
- Copy keys. `st_*`, `gl_t1..7`.
- Sheet. "Status chip".

### 11. Run-state chip
- Purpose. What an agent run or a session is doing: Working, Finished, Idle, Not started yet, and Ended for a session (M2). These are a separate family from setting status.
- Anatomy. Plain glyph + word, with no pill. Working ● `--accent`, Finished ✓ `--status-in-effect-fg`, Idle and Not started yet ◌ `--text-muted`, Ended ■ `--text-muted`.
- States. None. A change of state announces through the lane's polite live region on Live, at most once per row per minute.
- Tokens. `--accent`, `--working`, `--status-in-effect-fg`, `--text-muted`.
- Copy keys. `st_working`, `st_done`, `st_idle`, `c_not_started`, `fr_done`, `fr_now`, `fr_next`.
- Sheet. "Run-state chip".

### 12. Badge, scope label and scope chip
- Purpose.
  - Badge: a neutral fact about an item (confidence Tested/Documented/Assumed, "1 line changed").
  - Scope label: a scope name over its plain meaning (table column heads, where-set rows).
  - Scope chip: scope plus value under a setup-map row at 375.
- Anatomy. Badge is an outlined pill with muted text. A scope chip is the same pill with the scope in medium weight and then the value. A scope label is two lines.
- Tokens. `--border-strong`, `--text-muted`, `--text`, `--radius-pill`, `--text-xs`, `--weight-medium`.
- Copy keys. `rf_tested`, `rf_documented`, `rf_assumed`, `tx_changed`, `sc_*`, `sc_*_2`, `su_nv`.

### 13. Segmented control
- Purpose. A choice between 2 to 5 short options that all fit in one row.
- Variants.
  - Pages: in-page navigation (the Review views at 375). Links with `aria-current="page"`.
  - Choice: a value (effort level in the rail). RAC RadioGroup. An option may carry a second line ("set now").
- Anatomy. Track (`--surface-2`, 3 px inset) with equal segments. The selected segment is `--card-bg` with a 1 px `--border-strong` ring and semibold text.
- States. Default, hover (`--nav-hover-bg`), focus-visible ring on the segment, selected, disabled (dashed track, muted text).
- Tokens. `--surface-2`, `--card-bg`, `--border-strong`, `--nav-hover-bg`, `--radius-md`, `--weight-semibold`, `--text-sm`.
- Mapping. Pages is `<nav>` + RAC Link. Choice is RAC RadioGroup + Radio (APG Radio Group).
- Keyboard. Pages: Tab between links. Choice: Tab into the group, arrows move and select, Tab leaves.
- Phone. Full width. Pages scrolls sideways if the labels don't fit, and never wraps.
- Copy keys. `rv_tab_*`, `ed_field`, `ed_now`.
- Sheet. "Segmented control".

### 14. Select
- Purpose. Picks one value from a list longer than five, or a value whose label is long (Range, Session, Save to, Confidence, Project).
- Anatomy. Button with a muted label, the value in medium weight and a chevron, then a popover listbox.
- States. Default, hover, focus-visible, open, disabled.
- Tokens. `--card-bg`, `--border-strong`, `--text-muted`, `--nav-hover-bg`, `--radius-md`.
- Mapping. RAC Select + ListBox (APG select-only Combobox).
- Keyboard. Enter, Space or Alt+Down opens. Arrows move, Enter picks, Esc closes.
- Phone. The popover opens as a bottom sheet (RAC Popover with a tray layout).
- Copy keys. `rv_range_lab`, `rv_range`, `ed_saveto`, `ed_saveto_v`, `rf_conf`, `rf_conf_all`.

### 15. Search field
- Purpose. Filters a long list in place, on How Claude Code decides and on the Glossary.
- Anatomy (built in M5, `components/SearchField/`). A visible label above the field, then the input, at least 36 px high. A clear button sits at the end of the box as a 32 px target and shows only when there is text. The count sits beside the field as plain text.
- Props. `label` (the visible label, and the field's name), `value`, `onChange`, `clearLabel` (the clear button's name), `placeholder` (a hint that never replaces the label), `count` (visible text, not a live region), `announce` (what a screen reader hears), `delay` (default 600 ms), `className`.
- States. Default, hover (`--nav-hover-bg`), focus-visible (the shared ring on the input), filled with a clear button, and empty result. The page draws the empty result, with "Clear search" (`sf_clear`) as its button.
- Tokens. `--card-bg`, `--border-strong`, `--text`, `--text-muted`, `--radius-md`, `--nav-hover-bg`. A match uses `--m5-mark-bg` for the fill and `--m5-mark-edge` for a 2 px line under the text.
- Mapping. RAC SearchField. One visually hidden `role="status"` region, which is polite, says `announce` once typing pauses for `delay` ms. It speaks only when the text differs from the last announcement. It says nothing on first render or on a route change. A page that loads its data first passes no text until the data arrives, and that first text is the baseline, so it is never announced. The visible count is not a live region.
- Matching (`match.ts`). `matches(query, text)` folds both sides the same way, lower case and then NFKD with combining marks removed, so "cafe" finds "Café". It splits the query on whitespace and needs every word, in any order. An empty query matches everything. `matchFields(query, fields)` matches across named fields and returns the set of fields with a hit, or null for no match. `highlight(text, query)` returns strings and `<mark>` elements, never HTML.
- Keyboard. Esc clears and focus stays in the field. Enter does nothing.
- Forced colors. The input border is `ButtonText`. A match uses `Mark` and `MarkText` with a real underline.
- Copy keys. `dc_search_label`, `dc_search_ph`, `gl_search_label`, `gl_search_ph`, `sf_clear`, and the counts `dc_count_*` and `gl_count_*`.
- Sheet. "SearchField" (empty, typed, no results).

### 16. Switch
- Purpose. Turns a view option on or off with an immediate effect and no Save. It's used once, for "Show where each comes from". Its state lives in the URL query.
- Anatomy. 40 by 24 track with a thumb, then the label. The whole label is the target.
- States. Off, on (`--accent` track), hover (soft `--nav-hover-bg` halo), focus-visible, disabled (dashed track).
- Tokens. `--accent`, `--surface-2`, `--card-bg`, `--border-strong`, `--nav-hover-bg`.
- Mapping. RAC Switch (APG Switch).
- Keyboard. Space toggles.
- Copy keys. `su_switch`.

### 17. Checkbox
- Purpose. Confirms that the person read something before a risky action. It's never used for settings values.
- States. Default, hover, focus-visible, checked, disabled. 24 px box with `accent-color: var(--accent)`.
- Mapping. RAC Checkbox.
- Keyboard. Space toggles.
- Copy keys. `rk_check`.

### 18. Tile
- Purpose. One headline number with its comparison and a small proof graphic. Tiles only open a page, and four at most in a row.
- Anatomy. Label, value (`--text-3xl`), delta line, optional proof (spark, ring or dots, aria-hidden, because the text carries the value).
- States. Default, loading (a bone in place of the value, delta replaced by the loading line), link hover when the tile opens a page.
- Tokens. `--card-bg`, `--card-border`, `--radius-xl`, `--text-3xl`, `--text-muted`, `--accent`, `--chart-track`.
- Mapping. Static text, or RAC Link when it opens a page.
- Phone. 2 per row.
- Copy keys. `rv_t_*`, `st_*` tile words.
- Sheet. "Tile".
- Link form (M5). With `href`, the Link holds only the label, so the link's name is the label. The link's `::after` stretches over the whole tile, and the value, delta, note and proof follow as plain text. Focus shows as one ring on the whole tile, from `.tile-link:has(.tile-link-label:focus-visible)`. That `:has()` sits on the tile itself, because a nested `:has()` is invalid CSS and the browser drops the whole rule. The link keeps an outline of the same width, made transparent, so the sheet check still finds a ring. In forced colors the tile's ring turns `Highlight` and the link's own outline goes away.
- Help (M5). An optional `help` prop (`id`, and `values` with the numbers on the tile) draws the "?" (entry 54) at the tile's top right, level with the label. It sits beside the link, never inside it, on a higher layer (`z-index` 2 over the link's 1). So a press on it opens help and never follows the link. The label keeps room on its right for it. Sheet states "help" and "link-help".

### 19. Share bar
- Purpose. Shows each row's share of a total (cost by agent, model share in a table).
- Anatomy. Name with model swatch and model name, track with a fill in the model colour and a 2 px start edge, value, percent.
- Variants. List (12 px track, in a well) and in-table (8 px track).
- Tokens. `--chart-track`, `--border-strong`, `--m-*`, `--radius-sm`.
- Mapping. List items. The bar is aria-hidden because value and percent are text.
- Phone. Bar under the name, value and percent on the right.

### 20. Stacked bars and legend
- Purpose. Cost or tokens over time, split by model. Kinds are shown by pattern.
- Anatomy. Y ticks, bars stacked by model (`--m-*`), with kinds as patterns `kp1` to `kp4` filled with currentColor. Then x labels, a legend with totals, and a kinds breakdown line.
- Tokens. `--m-*`, `--chart-grid`, `--chart-axis`, `--chart-gap`, `--inset-bg`.
- Mapping. SVG `role="img"` with an aria-label summary. The legend totals and kinds table are the text alternative. Draw labels in HTML, not in a stretched SVG.
- Phone. Same chart with fewer x labels.

### 21. Pager
- Purpose. Moves a chart's window to earlier or later data that can be compared. It's chart-local, so tiles keep their own range.
- Anatomy. Earlier button, window label, Later button, why-line when an end is reached, scope note.
- States. Default, hover, focus-visible, disabled at an end (dashed `--border-strong`, same as buttons, with the why-line tied by `aria-describedby`).
- Mapping. RAC Button pair. The window label sits in a polite live region.
- Keyboard. Tab to each button.
- Copy keys. `pg_*`.

### 22. Timeline lane (Live)
- Purpose. Who is working, when, and who started whom. The centre of Live.
- Anatomy. The tokens-per-minute chart heads the well on the card (axis rule in tokens.css). Below it, one row per run: name, model swatch with model and effort, a track with segments in the model colour, round marks, a run-state chip, the last-request or ran-for line, tokens and cost. Started-by indents with a vertical guide.
- States. Working (the segment reaches Now with the `--now-line` edge), finished, not started yet (muted name, no segment), row hover and focus when the row opens the run.
- Tokens. `--m-*`, `--now-line`, `--inset-bg`, `--inset-border`, `--chart-grid`, `--text-muted`.
- Mapping. A list nested by Started by (`role="list"` per level). Each row is a RAC Link to the run. Segments are aria-hidden, and the row text says the times.
- Phone. Name and state on one line, the track full width below, tokens and cost on the right.
- Copy keys. `tl_*`, `st_working`, `st_done`, `c_not_started`.

### 23. Replay line
- Purpose. Scrubs a session's timeline minute by minute in Review.
- Anatomy. A vertical cut line with a handle at the top. Everything after the cut fades to `color-mix` of the card.
- States. Default, hover, focus-visible ring on the handle, dragging.
- Mapping. RAC Slider (APG Slider) with `aria-valuetext` such as "6:25 PM".
- Keyboard. Left and Right move one minute, Page Up and Page Down five, Home and End go to the start and Now.
- Copy keys. `rv_replay_note`, `rv_tl_h`, `tl_now`.

### 24. Table in a well
- Purpose. Rows to compare across the same columns (sessions, requests, the setup map).
- Anatomy. Header row in muted text. Numbers are right-aligned with tabular figures. The first cell is a link when the row opens something.
- States. Default, row hover (`--nav-hover-bg`), link focus-visible, empty (a sentence that says what will appear plus the action that fills it), error (a raised error row with ✕ above the rows that did load), loading (skeleton bones, `aria-busy`, a screen-reader line).
- Variants. Plain. Setup map, with explicit APG table roles so rows can stack at 375 and optional scope columns behind the Switch.
- Tokens. `--inset-bg`, `--inset-border`, `--border`, `--nav-hover-bg`, `--text-muted`, `--chart-track` (bones).
- Mapping. RAC Table (APG Table). Use APG Grid only if rows become selectable.
- Keyboard. Tab moves through the links.
- Phone. Columns marked `hp` hide. The setup map stacks into name and status, then what applies, then scope chips. Headers stay in the DOM with clip-hiding, never `display:none`.
- Copy keys. `su_col_*`, `rv_t_*`, `cs_tb_empty`, `cs_tb_empty_a`, `cs_tb_error`, `cs_tb_error_a`, `cs_tb_loading`.

### 25. Risky confirm
- Purpose. Stops a change that runs code on the person's computer (hooks, and later MCP servers that the dashboard writes).
- Anatomy. A raised box with an `--status-invalid-fg` start edge and ⚠ heading, the full command in a well, when it runs, the checkbox "I read this command", and the danger button with a different verb from Save. It sits inside the rail, away from Back.
- States. Unchecked (button `aria-disabled` plus a reason line), checked (button live), busy.
- Mapping. `role="group"` labelled by its heading. The button is `aria-describedby` the reason line.
- Keyboard. Tab reaches the checkbox before the button.
- Phone. Inline in the sheet. The sheet foot holds only Back.
- Copy keys. `rk_*`.

### 26. List and inspector
- Purpose. Level 3 of the setup. Pick an item on the left and read or edit it on the right.
- Anatomy. A list card with a well of items (name, value, status chip, optional lock mark). The inspector card holds the h2 with status, the "Runs at" line, "Set to X in file, line N", where it's set (a well of scope rows, top wins), Why (raised, with the confidence line), usage, then Edit and Copy path.
- States. Item: default, hover, focus-visible (inset ring), selected (`--nav-active-bg` with a 3 px `--accent` start bar and `aria-current`). List empty: a sentence plus an action. The inspector is read-only (lock mark and owner reason) or editing (component 27).
- Tokens. `--nav-active-bg`, `--nav-hover-bg`, `--accent`, `--inset-*`, `--raised-*`, `--text-2xl`.
- Mapping. The list is `<nav>` of RAC Link items, one URL per item, so the inspector follows the URL. The inspector is a labelled region.
- Keyboard. Tab through items. Enter opens and moves focus to the inspector h2.
- Phone. The list is the page. Picking an item opens the inspector as its own page with a back link.
- Copy keys. `sp_*`, `in_*`, `ro_*`, `cs_list_empty`, `cs_list_empty_a`.

### 27. Edit rail
- Purpose. Changes one item, always through a server preview.
- Anatomy and states, in order.
  1. Drafting: field (segmented choice, select or editor), hint, "Save to" target, Preview change.
  2. Review: effect first (Now and After with status, plus when it applies), diff, warnings with field path, then Back to editing and Save to file.
  3. Saved: "Saved." with Undo (polite).
  4. Overwritten: a persistent warning with Review changes and Undo.
  5. Preview failed: an error finding with Open file.
- Tokens. Those of its parts.
- Mapping. At 721 px and up, a labelled region that replaces the inspector. At 375, RAC Modal + Dialog (APG modal Dialog) with a focus trap. Esc closes, and asks `cs_closing_q` first when there's an unsaved change.
- Keyboard. Focus moves to the rail heading on open and back to Edit on close.
- Phone. The full-height sheet (component 28).
- Copy keys. `ed_*`, `cs_closing_q`.

### 28. Sheet at phone width
- Purpose. The edit rail at 720 px and below.
- Anatomy. Covers the top bar and tab bar. Header with an icon Close button (40 px) and the title, a scrolling body, and a sticky foot with the actions stacked, primary first.
- Tokens. `--card-bg`, `--border`, `--space-3`, `--space-4`.
- Mapping. RAC Modal (`isDismissable` false while busy) + Dialog.
- Sheet. "Sheet at phone width".

### 29. Diff
- Purpose. The exact change to a file, shown before every save.
- Anatomy. A well with the real path line (and the symlink target when there is one), then numbered lines. The gutter shows + or -, and added and removed lines are tinted.
- Tokens. `--diff-add-bg`, `--diff-add-fg`, `--diff-del-bg`, `--diff-del-fg`, `--inset-*`, `--font-mono`.
- Mapping. Ordered list. Gutter glyphs carry an aria-label ("added", "removed").
- Phone. Lines wrap (`overflow-wrap: anywhere`) and never scroll sideways.
- Copy keys. `ed_diff_h`.

### 30. Editor
- Purpose. Edits a text body (CLAUDE.md, rules files, agent bodies).
- Anatomy. A well with line numbers, the current line on `--code-line` with a caret, the escape hint and a changed-lines badge.
- Mapping. CodeMirror 6 with its accessibility defaults. Esc then Tab leaves the editor.
- Phone. Full width in the sheet, with soft-wrapped lines.
- Copy keys. `tx_*`.

### 31. Command row and check line
- Purpose. Hands a command to the terminal when the dashboard can't write the change (MCP at user scope, the locked tab).
- Anatomy. A well with the command, a Copy button, the remove-later command, and a check line (status mark, sentence, time) with Check again.
- States. Copy: default, then a "Copied" announcement (`cs_copied`, polite) without changing the label. Check line: not found yet, found (In effect), or checking (busy button).
- Mapping. RAC Button. The check line is `role="status"`.
- Phone. Copy goes under the command, full width.
- Copy keys. `mc2_*`, `lk_cmd`, `lk_copy`, `cs_copied`.

### 32. To fix row and group
- Purpose. One counted problem, with the one action that fixes it.
- Anatomy. A group card per kind (Couldn't read, Won't load, Not as set, then Can't tell uncounted). The heading carries the status glyph and count. Each row is raised: an h3 title naming the thing and the problem, the cause with file and line, the consequence in muted text, and one action.
- Tokens. `--raised-*`, `--status-invalid-fg`, `--status-lowered-fg`, `--text-muted`.
- Mapping. A list of rows under each group h2. The title is an h3 (the round 4 screen used h4, which skips a level).
- Copy keys. `fx_*`.

### 33. Empty state
- Purpose. Says what will appear and offers the action that fills it.
- Variants. Page-level (a card with a ✓ mark for "Nothing to fix"), in-list and in-table (a sentence plus a secondary button). A page that isn't built yet uses the neutral page-level mark instead, a … on `--surface-2` with a `--border` ring and `--text-muted` glyph and no status color, because a ✓ there reads as done.
- Tokens. `--status-in-effect-bg`, `--status-in-effect-fg`, `--text-muted`, `--space-6`. Neutral mark: `--surface-2`, `--border`, `--text-muted`.
- Copy keys. `fx_empty_*`, `cs_tb_empty*`, `cs_list_empty*`.

### 34. Progress steps
- Purpose. A known sequence of setup steps (first run).
- Anatomy. A well with one row per step: run-state chip (Done, In progress, Next), step name, and for the current step a progress bar and a size line.
- Mapping. Ordered list. RAC ProgressBar with a label and value text. The current step change is announced politely.
- Copy keys. `fr_*`.

### 35. Gate page
- Purpose. The locked tab and first run, before the shell can load.
- Anatomy. Brand header and one centred card.
- Copy keys. `lk_*`, `fr_*`.

### 36. Model swatch
- Purpose. Marks a model wherever its colour is used. It always sits beside the model name.
- Anatomy. A shape per model (Opus square, Sonnet circle, Haiku diamond, Fable square) in `--m-*`. aria-hidden.
- Tokens. `--m-opus`, `--m-sonnet`, `--m-haiku`, `--m-fable`.
- Note. Opus and Fable share the square. The name always disambiguates, but give Fable its own shape (a rounded square or triangle) in the build. Owner decision 3.

### 37. Skeleton bones
- Purpose. Loading placeholders at the measured height of the loaded content, so nothing jumps.
- Tokens. `--chart-track`, `--radius-sm`.
- Mapping. aria-hidden, with `aria-busy` on the region.

## Differences resolved

Each of these differs between boards today. The canonical version is drawn on the component sheet (`.cs` rules in components.css) and should replace the screen version during the build.

1. Segmented selected look. The Review page tabs used a 1 px `--border-strong` ring with semibold text. The edit rail's effort choice used a 2 px `--accent` ring, which reads as a focus ring. Canonical: the page-tab look for both, so focus stays the only accent ring.
2. Focus on the effort choice. Its radio inputs are hidden with opacity 0, so the focus ring landed on an invisible input. Canonical: the ring on the segment through `:has(input:focus-visible)`.
3. Run states. They were plain in Live's lanes but pills in the first-run steps. Idle used Ignored's hollow circle with the same colours. Canonical: plain glyph + word everywhere, with Idle and Not started yet as a dotted ring ◌, so a run state never reads as a setting status.
4. Hover. Only nav links and table links had hover on the screens. Canonical: hover for every interactive component, and one new token, `--accent-hover` (light #174a96, dark #a9caff, text-on-accent 8.55 and 11.07), added to tokens.css.
5. Disabled. Buttons used dashed `--border-strong`, while the pager used dashed `--border`, which nearly vanishes. Canonical: dashed `--border-strong` for every disabled control.
6. Loading. There was no busy state. Canonical: label swap plus `aria-busy` with a solid border, and no spinner (owner motion rule).
7. Raised boxes. The model check (`.chk-hit`, `.chk-list li`) and the round 4 findings (`.raised`) were two rule sets with different padding sources. Canonical: one raised finding with variants, and the start-edge rule in component 7.
8. Read errors. The draft error row first used the Invalid status chip, but Invalid means a wrong value. Canonical: ✕ glyph + sentence on a raised error finding, so status chips stay with setting status.
9. Bars. The share bar track had a 4 px radius and the list bar 3 px (a literal). Canonical: `--radius-sm` for both, at 8 px and 12 px heights.
10. Badge and chip geometry. The padding differed (0 7px and 1px 8px). Canonical: one pill geometry. A badge has muted text, and a chip has the scope in medium weight.
11. Heading levels. To fix rows used h4 under an h2. Canonical: h3.
12. Status glyphs in CSS content were read aloud by screen readers. Canonical: the empty-alt `content` syntax.
13. Card header slot `.q` held both counts and questions. Canonical: two slots, a count (tabular, muted) next to the title and a question after it.
14. Class collision. `.seg` (a timeline segment) sits next to `.segs` and `.seg-tabs` (the segmented control). Canonical names for the build: `lane-seg` and `segmented`.

## Added in the agent edit round

Styles in `site/agents.css`. Boards are `shots/a-agent-*.png`. Each of these components exists because nothing in 1 to 37 fit.

### 38. Form field
- Purpose. One front matter field in the edit rail. It's needed because the settings rail edits one value at a time, but an agent file holds many fields.
- Anatomy. Label (semibold), then the file line on the right ("Line 4", mono, muted) and Reset when the field differs from the file. Then the control, then a hint. A bottom border separates fields.
- States. Unchanged, changed (Reset appears, and the rail foot counts changed fields beside Preview change), read-only (value in muted mono plus a lock and the reason), error (the hint becomes the error in `--status-invalid-fg` with a ✕, tied by `aria-describedby`, and Preview is disabled with the reason).
- Tokens. `--border`, `--text-muted`, `--font-mono`, `--status-invalid-fg`.
- Mapping. RAC TextField, Select, RadioGroup or TagGroup, each with Label and Text slot="description".
- Phone. Same, full width in the sheet.
- Copy keys. `agf_*`.

### 39. Text field
- Purpose. Multi-line plain text that isn't a document (an agent's description). Documents use the editor (30).
- States. Default, focus-visible ring, error, read-only.
- Tokens. `--card-bg`, `--border-strong`, `--radius-md`, `--leading-body`.
- Mapping. RAC TextField + TextArea.

### 40. Tag list
- Purpose. An editable list of names (tools, disallowed tools).
- Anatomy. Mono pills, each with a 28 px remove button named "Remove {t}", then a dashed "Add a tool" button that opens a combobox of known tools. People pick from what exists and never type tool names from memory.
- States. Default, remove hover, focus-visible on each remove, empty (hint only: "Leave empty to allow every tool").
- Tokens. `--border-strong`, `--radius-pill`, `--nav-hover-bg`, `--font-mono`.
- Mapping. RAC TagGroup + TagList (APG Grid for tags), with RAC ComboBox to add.
- Keyboard. Arrows move between tags, and Delete or Backspace removes the focused tag.

### 41. Color choice
- Purpose. Picks one of Claude Code's eight agent colors.
- Anatomy. Pills with a 12 px swatch (`--agent-*`) and the color word. The selected pill has a 1 px `--border-strong` ring, semibold text and a ✓. The word is always present, so color never carries the choice alone.
- Tokens. `--agent-red..cyan` (aliases of status and category tokens, plus a new cyan), `--border`, `--border-strong`.
- Mapping. RAC RadioGroup. The focus ring sits on the pill through `:has(input:focus-visible)`.

### 42. Listbox popover
- Purpose. The open state of a Select when options need a second line or groups (model: short names, then full names).
- Anatomy. A popover with group labels. Each option shows its value in mono and a muted second line. The current file value is marked "set now", and the picked option gets a ✓.
- Tokens. `--card-bg`, `--border-strong`, `--shadow-card`, `--nav-hover-bg`, `--radius-lg`.
- Mapping. RAC Select + Popover + ListBox with Section and Header.
- Phone. A bottom tray.

### 43. Disclosure
- Purpose. Hides advanced fields (permission mode, skills, max turns and the rest) behind a labeled row with a one-line summary of their current values.
- Mapping. RAC Disclosure (APG Disclosure). The summary stays visible when closed.

### Agents page layout (list plus inspector, table variant)
- The Agents table is the list. When an agent is picked, it narrows to Agent, Check and Cost, and the inspector (480 px, 400 px below 1100) opens beside it. The picked row gets `--nav-active-bg` and a 3 px `--accent` start bar, with `aria-current`.
- Edit replaces the inspector with the rail in the same slot. At 375 the inspector is its own page with an "Agents" back link, and the rail is the full-height sheet (28).
- A symlinked agent file shows the link target under the path in the inspector and repeats it above Save in review, so the save target is never a surprise.

### Differences resolved in this round
15. Row selection class. `tr.sel` picked up the Select button's border and chevron from `.sel`. Canonical: `picked` for selected rows. The build should namespace Select as `select-btn`.
16. Changed-field count. The first draft put "1 field changed" inside the Model field. Canonical: one count in the rail foot beside Preview change, with Reset on each changed field.

## Added in the new-agent round

Boards are `shots/a-agent-new*.png`, and the styles are at the end of `site/agents.css`.

### 44. Role cards
- Purpose. A preset that fills real fields when you add an agent. Claude Code has no role setting, so the choice is never saved. It's needed because the segmented control (13) can't show a sentence for each option.
- Anatomy. Three cards (Lead, Worker, Reviewer), each with a name and one line. Under them sit the hint that a role isn't saved, and a well titled "What {role} set" listing the values it filled (can start other agents, model, effort, tools).
- States. Default, hover, focus-visible (ring on the card through `:has`), selected (1 px `--border-strong` ring and ✓). Custom is a fourth dashed card that shows only after a person changes a value the role set. It's a state, not a choice. Each changed row in the summary gets a "You changed this" badge, and the old value is struck through beside the new one.
- Tokens. `--border`, `--border-strong`, `--nav-hover-bg`, `--card-bg`, `--inset-*`, `--text-muted`.
- Mapping. RAC RadioGroup with Radio cards. Custom is static text with `aria-current`, and picking a preset again refills the fields.
- Phone. One card per row.
- Copy keys. `an_role*`, `an_lead*`, `an_worker*`, `an_reviewer*`, `an_custom*`, `an_set_h`, `an_you_changed`.

### 45. Model list with price mark
- Purpose. Picks a model with a relative price beside each option. It's used where cost matters to the choice, as with a new agent. The edit rail keeps the Select (14, 42).
- Anatomy. Radio rows with the model value in mono, a muted price line and a three-step price mark. Filled steps show a higher price, and dashed steps mean the price isn't known. Below sit the caption "Price compared with Sonnet" and "Use a full model name", which opens the Select of full IDs. The words always carry the price, and the mark only repeats it.
- States. Default, hover, focus-visible (inset ring), selected (`--nav-active-bg` with a 3 px `--accent` start bar).
- Tokens. `--border`, `--border-strong`, `--text-muted`, `--nav-active-bg`, `--accent`.
- Mapping. RAC RadioGroup.
- Copy keys. `an_cost_*`, `an_inherit_cost`, `an_model_cost`, `an_full_name`.

### Other parts of the new-agent form
- Can start other agents is a Switch (16) that adds or removes Agent in the tools list.
- Name is a text field (39) with live checks. A free name gets a ✓ line in `--status-in-effect-fg`. A clash gets a raised warning (7) that names the file that would win, plus one action that moves the save.
- Save in is a color-choice-style pill radio (41) without swatches. The file path below it updates live.
- The system prompt uses the editor (30), with the role's starter text.
- The rail foot says which fields are required beside "Preview new agent".
- Review shows the whole new file as an all-added diff (29) with a "New file" badge.
- After saving, the agent appears in the table under "No runs yet", picked, and the inspector shows "Created." with Undo, which deletes the file.


## Added in the agent form layout round (November 8)

Three layouts for the same fields: A one page, B a stepped dialog, C a page with tabs. Styles in `site/dirs.css`, screens in `site/dirs.js`, all classes prefixed `ly`. Nothing here replaces an earlier component; these are containers for components 38 to 45. Only the picked one stays.

### 46. Agent file preview (A, C)
- Purpose. Shows the file as it will be saved, beside the form, updated on every change.
- Anatomy. Card (2) with "Agent file", one muted line, the path in mono, then a well with line numbers. In edit, a changed line uses `--diff-add-bg/fg` plus a 3 px start bar and a hidden "changed" word, so it doesn't rely on hue. The symlink note sits under the well.
- Tokens. `--card-bg`, `--inset-bg`, `--diff-add-bg`, `--diff-add-fg`, `--text-muted`, `--font-mono`.
- Mapping. A plain region with a heading. Read-only, not focusable.
- Phone. A disclosure (43) "Show agent file" in A, a fifth tab in C.

### 47. Tabs (C)
- Purpose. Splits the form into four groups; one shows at a time, any order.
- Anatomy. Text tabs on a `--border-strong` baseline, selected tab with a 2 px `--accent` underline and semibold text. A tab with edits shows a "{n} changed" badge (5).
- Mapping. APG Tabs with automatic activation, arrow keys between tabs, one tab stop. RAC Tabs.
- Phone. The tab list scrolls sideways.

### 48. Step list dialog (B)
- Purpose. A large modal dialog that walks through the groups, then Review.
- Anatomy. Header with the title and a Close icon button, numbered step list at the start, body that scrolls on its own, footer with Back and "Next: {step}". Done steps show ✓ plus a hidden "Done". In edit the steps are free to jump and the footer always offers "Preview change".
- Mapping. APG Dialog (modal): focus goes to the first field, Tab stays inside, Esc closes, focus returns to "+ Add an agent" or the row. RAC Modal plus Dialog. The step list is a nav with `aria-current="step"`.
- Phone. Full screen, no scrim, the step list hides and the header says "Step n of t, name".
- Known conflict. The prompt editor (30) uses Esc to leave the editor, and the dialog uses Esc to close. Esc inside the editor must only leave the editor, and closing with edits must ask first.

### 49. Phone action bar (A, C)
- Purpose. Keeps the required note and the primary action in reach on a long form.
- Anatomy. Sticky bar at the bottom of the viewport with the note or the changed badge and the primary button. Cancel moves to the "← Agents" link. The app tab bar hides on these focused pages.
- Tokens. `--card-bg`, `--border`.

## Revision of C after the pick (November 8)

The owner picked C and said that in dark mode the background blended into everything, so the eye couldn't find Role or Model. The mockup scopes these rules to `.lyC` in `site/dirs.css`. Once the owner approves, they move into components.css as the canonical states.

### Field groups in a form
- Each field is a raised block (`--raised-bg`, `--raised-border`, `--radius-lg`) with its label as a semibold 14px heading. The tab panel stays the card. Options inside a group sit on `--card-bg`, so the order runs page, then card, then group, then option.
- Warnings inside a group keep their own warn edge and ▲ glyph.

### Chosen state (changes 44 role cards, 45 model list, 13 segmented control)
- Fill `--select-bg`, a 2px `--accent` edge, and "✓ Selected" (`sel_word`) in `--accent`. A segmented option shows ✓ before its label, because "Selected" doesn't fit at 375.
- Unchosen options are quiet: `--card-bg` with a 1px `--border`. Their labels identify them, not their edges.
- Only the primary button uses a solid accent fill. A chosen option never does, so the primary action stays the strongest mark on the page.
- Focus-visible is an outline 3px outside the edge (inset 5px on list rows), so focus and selection never share the same edge.
- Contrast: the accent edge is 6.10 light and 7.51 dark against `--raised-bg`, and 5.55 and 6.65 against `--select-bg`. Text on `--select-bg` is 14.17 and 11.61, muted text 5.71 and 6.04, and the accent word 5.55 and 6.65.

### What Lead set, short form (44)
- It keeps only the fields that live on other tabs ("Can start other agents" and "Tools"), headed "Set by {r} on Tools and options" (`an_set_short_h`). Model and effort sit right below it and in the file. The owner hasn't confirmed this yet.

### Tabs (47)
- The chosen tab's underline is now 3px instead of 2px. Everything else stays the same.

### Should follow once approved
- Segmented tabs (`.seg-tabs`, the range and view switches), which use the same 1px ring as the old segmented control.
- Picked table rows (`tr.picked`) and the inspector list rows (`.surf` list): add `--select-bg` behind the existing 3px start bar.
- Color choice (41) and Save in pills, which use the same ring today.

## Full page, the owner's pick (November 8)

The owner wanted C as a full page, not tabs. Tabs (47) are no longer used for the agent form. Its entry stays only as a record of the tabbed draft. The screens are `dirFull` in `site/dirs.js`, and the styles are the `.lyF` rules in `site/dirs.css`, which build on the C revision rules (`.lyC`).

- Routes are `#/review/agents/new` and `#/review/agents/<name>/edit`. The app tab bar hides on phones.
- A sticky bar at the top (50) holds "← Agents / {title}" on one line, plus the required note or the changed badge, Cancel and the primary button. It stays at the top of the viewport as the page scrolls. On phones it becomes the plain title line, and the actions move to the phone action bar (49).
- There are four section cards in order. In new they are "Role and model" (Role, Model, Effort), then "Name and details", "Tools and options" and "System prompt". In edit the first card is "Model and effort", because edit has no role. Each card has an h2 and the field blocks from the C revision. The System prompt card hides its duplicate field label and gives the editor at least 360px.
- A sticky side column at 1440 holds a one-column "Jump to" list (the section you're in is marked `aria-current` with an accent bar) and the agent file (46) in its well. The well caps its height to the viewport and scrolls on its own.
- On phones the agent file sits behind "Show agent file" (43) after the last section.

### 50. Sticky page action bar
- Purpose. Keeps the way back, the title and the actions in view on a long form.
- Anatomy. `--page-bg` with a 1px `--border` bottom edge, the 16px title with the back link in `--accent`, then actions on the right.
- Mapping. Part of the page header, not a toolbar role. Tab order is back link, then Cancel, then the primary button.

## Chosen state made canonical (November 8, owner approved)

The owner approved three calls. The short "Set by {r} on Tools and options" stays. Edit uses the full model list with prices. The new chosen state is the standard everywhere. Its rules now live once, at the end of `site/components.css` under "Chosen state, canonical". I took the old ring and nav-fill rules out of app.css, agents.css and components.css, and the C-scoped copies out of dirs.css.

- The recipe: `--select-bg` fill, a 2px `--accent` edge, and a mark that isn't colour. That mark is "✓ Selected" (`sel_word`) where it fits, a ✓ glyph where it doesn't, or the existing 3px start bar on rows. Unchosen options stay quiet. A solid accent fill is for the primary button only.
- Focus-visible is an outline 3px outside the edge, or 5px inset on model rows. It never reuses the edge.
- What changed, by component:
  - Role cards (44): "✓ Selected" sits on the title row, from shared markup in `roleCards`. The Custom card keeps its dashed edge.
  - Model list (45): "✓ Selected" sits before the price mark (below the description at 375), from `modelRadios`.
  - Color choice (41) and Save in pills: fill plus a 2px edge, and the existing ✓ is now in accent.
  - Segmented control (13): fill plus a 2px inset edge, with ✓ added before the label by CSS.
  - Segmented page tabs (the Review switch on phones and in the components sheet): fill plus a 2px inset edge, semibold, no ✓ because it's navigation.
  - Picked table rows (Agents) and inspector list rows (Your setup, editing): `--select-bg` behind the existing 3px start bar.
  - Listbox popover options (42): the chosen option gets the fill, and if it also has keyboard focus it gets the 2px edge.
- Left alone on purpose: the sidebar nav and the phone tab bar (navigation, which keeps `--nav-active-bg` and accent text), the Switch (16, an on/off control, not a choice), and the dots on chart tiles (data).

## Picked layout
- The full-page agent form (`dir-full-new`, `dir-full-edit`) is the picked layout for adding and editing agents.
- These are superseded and kept only as a record: A, one page with the "Jump to" list (`dir-a-*`); B, the stepped dialog (`dir-b-*`); and C with tabs (`dir-c-*`, components 47 and 48). Components 46 (agent file preview), 49 (phone action bar) and 50 (sticky page action bar) stay in use through the full page.
- The side-panel form boards (`agent-new*`, `agent-edit-fields`) are superseded by the full page too, but they were recaptured so they show the new chosen state. Their Review, Saved and plugin screens still apply.
- The superseded direction boards (`dir-a`, `dir-b`, `dir-c`) weren't recaptured, so their screenshots show the older chosen state.

## M0 gate and shell round (November 8)

The product is now Bar Tab, and the command is /bartab. Until the M9 rename, the preview command is /bartab-preview, so the preview build shows /bartab-preview wherever these boards show /bartab. Source is in `site/m0.js` and `site/m0.css`, and the words are in `site/strings7.js` (tech-writer drafts).

### Brand (changes 1 and 35)
- A plain "Bar Tab" wordmark, 16px semibold, in the sidebar and the gate header. The R mark is gone. No Claude or Anthropic mark.
- `S.product` drives the page titles ("{page}, {project}, Bar Tab").

### Top bar project button (changes 2)
- At 375 the project name in the top bar is a button (`aria-haspopup="listbox"`, `aria-expanded`) with a ▾ and a name that starts with "Project, {name}". It opens the project tray. While the tray is open, its 2px accent ring is the open state, and the same applies to the sidebar Select (14) at 1440.

### 51. Project picker
- Purpose. Picks the project. It opens from the sidebar Select at 1440 as a popover, from the top bar at 375 as a bottom tray, and as a sheet on `#/` when there's no launch project. On `#/` the shell shows behind a scrim. The sheet is a modal Dialog labelled "Projects" with the page h1, centred at 721 px and up and the bottom tray at 720 px and below. Esc and the scrim go back to the previous route, and do nothing when there is none.
- Anatomy.
  - Header "Projects", with Close at 375.
  - One option per project: name, path in mono, and a state line.
  - The current project uses the chosen state (`--select-bg`, 2px accent, ✓). The keyboard-active option uses `--nav-hover-bg`.
- States in words, never hue alone. Every state can be picked.
  - ✓ Ready (`--status-in-effect-fg`).
  - ● Agent working (`--accent`).
  - ○ No .claude folder (muted), with a line on what opening it gives.
  - ✕ Folder not found (`--status-invalid-fg`), with a line on what opening it gives.
- Empty. "No projects yet", one sentence on how a project appears, and the /bartab command with Copy (12).
- Mapping. APG Listbox inside a popover at 1440, or a modal tray at 375 (RAC Select with a tray Popover). Esc or Close returns focus to the trigger.
- Copy keys. `pk_*`.

### 52. More page (phone only)
- Purpose. Holds what doesn't fit the tab bar. Only Reference links and the version line. The project switch stays in the top bar, and there's no theme row in M0.
- Anatomy. h1 "More", a card "Reference" with two 48px link rows (glyph, label, ›), then "Version" with the Claude Code version.
- At 721px and up, `#/more` redirects to Live, so it has no 1440 board.

### Gate page (35), revised
- Server stopped. The same card shows the h1, one sentence, the /bartab command with Copy and the kept route line. A retry row follows, with ↻ "Checking again every 10 seconds", "Last answer at {time}" and a "Try now" button. Pressing Try now swaps its label to "Checking" with `aria-busy`. The row is a polite status.
- Locked. A reason sentence for each code (`no_key`, `code_used`, `code_expired`, `restarted`, all drawn on the component sheet), then "Run this command...", the command with Copy as the primary action, and the ↻ route line "This tab reopens on Agents, builder once another tab opens the dashboard."
- Locked wait. The wordmark only, centred, with a screen-reader status "Checking for another dashboard tab". It holds for under a second while a new tab asks the others for a key, and it has no motion.
- New-tab line. On the page the new link opens, a polite notice "✓ Your other tab is open again on Agents, builder." sits above the h1.

### Progress steps (34), revised
- Steps 1 and 2 load as ✓ Done with no sizes. Step 3 is live, with a bar and "{n} of {m} files" (`aria-valuetext`).
- The footnote now says the step reads local files and needs no internet connection. That holds only if step 3 makes no network call.
- Failed. Step 3 shows the ✕ Failed chip, then an error finding (7) with a ✕ heading, the file it couldn't read and "Run this command in Claude Code to try again", plus the command with Copy. It's `role="alert"`.
- Retrying. Running the command again moves step 3 back to In progress, with an empty bar and "Trying again since {time}" as a polite status. The error finding goes away.

### Component sheet
- New sections show every state above, so axe covers them: Projects (open and empty), the gate (four locked reasons, the retry row default and loading, first run failed, the new-tab line, the wait hold), and More (a focus-visible row).

## M1 data core round (November 8)

Source is in `site/m1.js` and `site/m1.css`, and the words are in `site/strings8.js` (tech-writer drafts). Owner decisions behind this round:
- The sidebar is 240px.
- "Updated" is the data-checked clock time in minutes.
- The updates-stopped notice shows on every page.
- First run shows size only.
- Price disagreements don't show in M1.

### 1. Sidebar navigation (revised)
- The width is 240px (was 224px), so "How Claude Code decides" fits on one line.
- The footer is now component 53.

### 53. Sidebar footer (new)
- At rest it has five 12px muted lines, in this order:
  1. "Updated {time}", from `as_of`, in minutes
  2. "History since {date}"
  3. "Last backup {time}"
  4. "Prices as of {date}". When prices don't come from LiteLLM it reads "{Bundled | Saved | Custom} prices, {date}" instead.
  5. The Claude Code version
- With problems. A ▲ line in `--status-overridden-fg` takes the top for unreadable files ("Couldn't read {n} files"). A failed backup replaces the backup line in place ("Backup failed at {time}"). So the footer grows by one line at most, to six. Nothing else collapses. Each line is one line with ellipsis, and every draft fits in 32 characters at 240px. The sidebar scrolls if the window is short.
- Detail lives on More at 375. At 1440 the reason sentences arrive with To fix in M4.
- Mapping. Plain text, no live region. The notice line below handles announcements.

### More page (52), revised
- New first card "Your history", with label and value rows: Updated, History since, Last backup, Prices as of. With problems, a ▲ finding (7, overridden edge) for each problem sits above the rows, with its reason sentence. The Last backup row shows "▲ Backup failed at {time}".
- Then Reference, then Version.

### 8. Notice line (revised): updates stopped
- The `pass_error` variant. A 4px `--status-overridden-fg` edge and ▲, then "Updates stopped at {t} because the dashboard couldn't read {f}...". It sits above the page header on every page at both widths, and it clears on the next good pass.
- It's apart from the M0 connection state. That one is the server-stopped gate, shown only while calls fail. The two never share a slot.
- `role="status"` only when it appears after load, announced once.

### 34. Progress steps (revised)
- Counting. Step 3 is In progress with "Counting files" and no bar, so it never shows a 0 of 0 bar.
- Running. The bar and the label both use bytes ("1.2 of 2.0 GB"). Files no longer show, so the label and bar always agree.
- Retrying. Step 3 shows ✕ Failed with the bytes done. One error finding (7) holds the reason, "↻ Next try at {time}" (a polite status, announced once per new time), the line "The dashboard tries again on its own. To try now..." and the command. A retry that's running moves step 3 back to Counting, then Running. This replaces the M0 failed and retry boards (`a-firstrun-failed` is superseded).

### 35. Gate page (revised): store_newer
- An overridden ▲ mark, "This history needs a newer Bar Tab", one sentence with both versions, the next step "Update Bar Tab, then run this command in Claude Code", and /bartab with Copy. The exact update command isn't known yet.

### 51. Project picker (revised): placeholder
- On `#/` with no launch project, the sidebar Select (and the top bar button at 375) shows "Pick a project" in muted text until a pick. The picker opens over a scrim with no option marked chosen, and the top bar title is "Bar Tab".

### Component sheet
- New sections hold all of the above: the footer (rest, problem, the three price source words), the history card (rest and problem), the notice, first run (counting, running, retrying), store_newer, and the placeholder Select.

## M2 Live round (November 9)

Source is in `m2.js`, `m2.css` and `m2.html` in this folder, and the words are in `strings-m2.js` (tech-writer drafts, owner copy answers in `docs/rebuild/planning/m2-build.md` section 13). Boards are `shots/a-m2-<board>-<1440|375>-<light|dark>.png` in the archive: p1 live, headers, unlinked, unpriced; p2 many, many-open, long; p3 ended-switch, nothing-other, nothing-alone, no-sessions, gone, select-open. The owner approved passes 1 to 3 as drawn.

### 11. Run-state chip (revised)
- New state Ended ■ in `--text-muted`, for a session that stopped running. Glyph plus word, no pill, like the others.

### 22. Timeline lane (revised)
- At 375 each lane has four lines: name and cost, model and effort with tokens, the track, then state and age.
- Unlinked runs show a badge, "Finding starter" while a link may still arrive and "No starter found" once it can't, with a dashed tree line. A row that moves under its starter gets a 2px `--accent` ring for about 2 seconds, and none under reduced motion.
- Unpriced cells read "at least {cost}" or "No price for {model}". A bucket with no price is a dashed spark stub.
- Fold rule. Under a parent with more than 4 children, finished subtrees fold into "{n} finished earlier" with a Show or Hide button that sets `aria-expanded`. Working runs and runs that finished in the last 2 minutes never fold. Fold bars use `--text-muted`.
- Long sessions. The axis label reads "averaged over {n} minutes". The open bucket is drawn at partial width, hatched and outlined, at least 5px. Round marks are at least 4px. Indent depth caps at 3 at 1440 and 2 at 375, then the row says "Started by {name}". Tile dots cap at 8 with "+{n}". The spark has no gaps above 32 bars.

### Live header (3, revised)
- No time while live. Paused shows "Paused at {time}". Lost shows "Last reached the server at {time}" plus a warning finding (7) with Try now. Ended shows "Ended at {time}" and no Pause.

### Session Select (14 and 51)
- Reuses component 51's popover at 1440 and tray at 375, with "This project" and "Other projects" groups and a "See all sessions" link at least 26px tall.
- The M0 `.proj` button (51) and the Select lose their mismatched `aria-label`, so the visible label is the accessible name.

## M5 help round (November 10)

Direction A from the designer's help round, built in M5 task 7. The words live in the registry (`strings/help.ts`), the shared lists (`strings/lists.ts`) and the Glossary (`strings/glossary.ts`). The components below hold no copy of their own beyond the `hp_*` strings.

The designer's notes set where each trigger goes. Tiles, cards and charts get the full "?" (entry 54). Column headers and inspector field labels get the term form (entry 55). A status pill that repeats down a column gets no trigger, and its column header carries the status words. A pill shown once in a view gets the full "?" beside it.

### 54. Help button
- Purpose. The "?" that opens one help entry. Use it on tiles, cards and charts, and once beside a status pill that appears once in a view.
- Anatomy. A 24 px circle inside a 32 px target. The target grows to 40 px on a touch screen (`pointer: coarse`) and at 720 px and under. A negative margin keeps the layout space at 24 px, so the target grows over the gap around it and never moves the label beside it.
- Props. `help` (a registry id), `values` (what the spot shows now, keyed by each line's `ref`), `line` (the label of the line to mark "This column"), `word` (the id of a list item to mark "Shown here"), `unit` (picks the title from the entry's `titleByUnit`), `sheetOpen` (component sheet only), `className`.
- States. Closed, hover (`--nav-hover-bg` and `--text`), open (the `--select-bg` fill, an accent ring and an accent mark), with values, line marked, word marked.
- Name. "About {title}" (`hp_trigger`), with `aria-haspopup="dialog"`. React Aria's DialogTrigger sets `aria-expanded`. Every trigger carries `data-help-id`, so "Back to {page}" on the Glossary can put focus back on it.
- Tokens. `--card-bg`, `--border-strong`, `--text`, `--text-muted`, `--nav-hover-bg`, `--select-bg`, `--accent`.
- Forced colors. The circle is `ButtonFace` with a `ButtonText` border. Open is a 3 px `Highlight` ring with a `CanvasText` mark. A `Highlight` fill would hide the mark, because the browser paints a backplate behind the text.
- Sheet. "HelpButton" (closed, open, with values, line marked, word marked).

### 55. Help term
- Purpose. The light trigger. The header or label text itself opens the same panel. Use it on column headers and inspector field labels.
- Anatomy. The text with a dotted `--border-strong` underline, 1.5 px thick and offset 4 px. The box is at least 32 px each way, and a negative block margin keeps the line from growing. Hover turns the text and the underline `--text`. Open is a solid 2 px `--accent` underline with accent text, so the open state never rests on color alone.
- Name. The text alone, with no "About" prefix, because a header that read "About Check" would stop matching the column it names. In a `th` it is the header's only content, so the column keeps its name.
- Props. The same as the help button, plus `children` (the text) and `describedBy` (the id of a note that describes the spot, such as a screen reader line beside a pill).
- Forced colors. `LinkText` for the text and the underline, `Highlight` when open.
- Sheet. "HelpTerm" (closed, open, in a header).

### 56. Help panel
- Purpose. The dialog both triggers open. One component with two layouts, chosen by `tray`.
- Above 720 px. A React Aria Popover under the trigger, 8 px off, that flips above when there is no room and keeps 12 px from the window edge. It is 360 px wide, and never wider than the window minus 24 px. A notch points at the trigger. The popover itself never scrolls, because the notch sits outside its box, so the dialog inside scrolls.
- At 720 px and under. A bottom tray in a modal, with a grip and a Close button (`hp_close`), up to 82 vh high. The tray slides up and the scrim fades in over 160 ms. Neither moves when `prefers-reduced-motion` is set.
- Heading. The entry title as an h2 (`helpTitle`). When a chart passes `unit`, the title comes from the entry's `titleByUnit`, so it matches the card's title, such as "Cost per day".
- Behavior. Focus moves into the dialog on open and returns to the trigger on close. Esc closes it, and so does a click outside (on the scrim, in the tray). `useHelpOpen` reads the layout when the panel opens. A window that crosses 720 px while the panel is open closes it, because a popover can't turn into a tray without losing focus. Pressing a glossary link closes the panel.
- Tokens. `--card-bg`, `--border-strong`, `--shadow-card`, `--scrim`, `--radius-lg`, `--radius-md`, `--nav-hover-bg`.
- Forced colors. The panel is `Canvas` with `CanvasText` text. The border, the notch and the grip are `CanvasText`, and the Close button's border is `ButtonText`.
- Sheet. "HelpPanel" (popover, tray). The sheet draws it in place (`inline`), because a real overlay would cover the other cells.

### 57. Help entry
- Purpose. The body of a help entry, in a fixed order. What the spot shows, then its numbers or columns as a description list, then the shared list, then how to read it, then the glossary links. The panel owns the title, so the entry has none.
- Numbers. The lines sit under "What each one means" (`hp_numbers`). When the spot passes a value for a line's `ref`, the value takes its own column beside that line. The line whose label matches `line` is marked. A pill that passes `word` marks the line whose label matches it.
- Shared list. It sits under its own heading (`hp_list_status`, `hp_list_scopes`, `hp_list_confidence` or `hp_list_project_state`). In the status list, each word is a StatusChip with its shared meaning. Other lists show the word as plain text. The item whose id matches `word` is marked.
- How to read it. The entry's reading, under "How to read it" (`hp_reading`).
- Marked line. The `--select-bg` fill, a 3 px `--accent` start bar and the words "This column" (`hp_this_column`). In a list, and on a pill's line, the words are "Shown here" (`hp_this_setting`). The bar is a border on a pseudo-element, so forced colors keeps it and shows it in `Highlight`. A box shadow would be dropped.
- Glossary links. One per term the Glossary has, named "{term} in the glossary" (`hp_glossary_link`), going to `#/reference/glossary/<id>`. When the current page is one a person can go back to, the link adds `?from=<route>&help=<id>`. The Glossary then shows "Back to {page}" and focuses the trigger again. A link to a missing term does not render, so every link has a page to open.
- Sheet. "HelpEntry" (full, status list, scopes list, no glossary).


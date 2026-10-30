# Proposed token additions, round 3 (#39), settled for U-7 (P-3, October 30, 2026)

The eight round-2 tokens the owner approved stay (`--page-bg`, `--card-bg`, `--sidebar-bg`, `--nav-active-bg`, `--nav-hover-bg`, `--shadow-card`, `--chart-track`, `--chart-gap`). Round 3 adds chart colours. `tokens.css` is unchanged; these live in `tools/base3.css` until U-7 lands them. Every value below is computed with `tools/contrast3.py` (WCAG 2.1 relative luminance) and the dataviz validator (`tools/darken_cat.mjs`); the full pair list is `contrast-r3.json`.

U-7 puts every new colour in all three theme blocks tokens.css already uses: light `:root`, `@media (prefers-color-scheme: dark) :root:not([data-theme="light"])`, and `:root[data-theme="dark"]`. base3.css only has the last one, which is fine for the mock because every page stamps `data-theme`.

## Categorical, for models (identity)

Fixed order by catalog. Opus 5.5 is slot 1, Sonnet 5.5 slot 2, Haiku 5.5 slot 3, Fable 5.1 slot 4. A model outside the catalog draws as a `--text-muted` on `--chart-track` hatch (SVG pattern `oth-*`, legend swatch with the same stripes; no CSS fill or stroke on `.cat-other` marks, because CSS would beat the pattern attribute). Status colours are never reused for a series, and the four hues avoid the green, orange, red and purple of the status tokens.

Light slots 2 to 4 are darkened to at least 3:1 on the card (owner decision, Q11). Each keeps its OKLCH hue and chroma and only drops in lightness, so the dark steps, which already pass, are unchanged.

| Token | Light | Dark | On card (light #ffffff / dark #111417) |
| --- | --- | --- | --- |
| `--cat-1` | #2a78d6 | #3987e5 | 4.42 / 5.08 |
| `--cat-2` | #04a873 (was #1baf7a) | #199e70 | 3.06 / 5.43 |
| `--cat-3` | #c78600 (was #eda100) | #c98500 | 3.07 / 6.02 |
| `--cat-4` | #dc7099 (was #e87ba4) | #d55181 | 3.08 / 4.68 |

Validator, light set on #ffffff: lightness band pass, chroma floor pass, CVD separation pass (worst adjacent #c78600 to #04a873, protan ΔE 9.0, above the 8 target), normal-vision floor pass (worst adjacent 17.7, above 15), contrast pass (all four at or above 3:1). Dark set on #111417: all five checks pass (worst CVD 8.4, normal-vision 19.3). Series colours stay on the card: on the page background (#f5f6f8) slots 2 to 4 sit at 2.83 to 2.85, and on surface-2 at 2.64. A stricter set that clears 3:1 on surface-2 too exists (#0f9b6b, #b77c09, #cf658e) but pushes the yellow toward brown, so it is held back unless the owner wants chart colours off the card.

Distance from the status foregrounds (OKLab ΔE ×100, closest pair): cat-1 to lowered 16.3, cat-2 to in-effect 18.6, cat-3 to overridden 19.5, cat-4 to invalid 22.0. No series colour impersonates a status.

## Sequential ramp, for token kinds (ordered by price)

Cache read, input, cache write, output. In light mode the ramp runs light to dark, so "more expensive is darker". In dark mode the order flips (output is the lightest), so the most expensive kind stays the one with the most contrast against the card.

| Token | Light | Dark | On card (light / dark) |
| --- | --- | --- | --- |
| `--rk-1` cache read | #b7d3f6 | #256abf | 1.54 / 3.43 |
| `--rk-2` input | #6da7ec | #3987e5 | 2.50 / 5.08 |
| `--rk-3` cache write | #2a78d6 | #86b6ef | 4.42 / 8.76 |
| `--rk-4` output | #104281 | #cde2fb | 9.91 / 13.96 |

Accepted light-mode exception (owner, Q4, October 30): `--rk-1` at 1.54:1 and `--rk-2` at 2.50:1 on the white card sit under the 3:1 non-text floor. The exception holds only on two conditions. Every stacked bar keeps legend totals or a kinds table, and every stacked bar has a visible start edge. The mock meets both: the kinds legend carries each total, the session and agent pages carry kinds tables, and `.sb-bar` has a 1px `--border-strong` left edge (3.60 light, 3.84 dark). Text is not affected. The tokens.css header comment and the CLAUDE.md Design section line carry this, in tech-writer's words (see the P-3 report).

The validator judges a sequential ramp by monotonic lightness, which holds in both themes. The ramp is never used for identity.

## Chart chrome

`--chart-grid` alias of `--border` (recessive gridlines), `--chart-axis` alias of `--text-muted` (axis labels at 10px are decorative repeats of values given in the legend or tooltip). Bars for a single series use `--accent` on `--chart-track`. Aliases add no contrast pairs.

## Pin check pills (drift settled)

What ships in base3.css and the rendered pages, each with a mark and a word:

| Pill | Pair | Mark | Light | Dark |
| --- | --- | --- | --- | --- |
| Matches pin, Matches | In effect | check | #1f6a3a on #e4f1e8, 5.67 | #8fd3a4 on #15301f, 8.15 |
| Pin overridden | Overridden | triangle up | #8a4b00 on #f8ecd9, 5.83 | #f0b56b on #3a2a12, 7.58 |
| Differs from pin, Differs | Invalid | cross | #a3262a on #f9e5e5, 6.06 | #f09a9c on #3d1c1d, 7.10 |
| Missing | Invalid | cross | same as Differs | same as Differs |

contrast-r3.json had Differs on the Overridden pair and a "Matches pin, lowered" row for a pill that no longer ships (review #10 replaced it with Matches pin plus a note). Both rows are corrected; the Pin overridden row is new. `.st-match-note` at base3.css:88 is dead CSS and can go.

## Search field (new component, Rules reference)

Nothing in the sheet takes typed text, so the Rules search adds one control: `.search` with a 16px magnifier, `<input type="search">`, 38px tall to match the segmented control's outer height, `--card-bg` fill, 1px `--border-strong` border (3.60 light, 3.84 dark, passes the non-text floor), `--radius-md`, placeholder in `--text-muted` (6.67 / 7.98), typed text in `--text` (16.56 / 15.33), focus ring `--focus-width` `--focus-ring` at `--focus-offset`. Width 260px in the card header beside the confidence filter; 100% at 720px and below, where the header wraps to title, search, filter.

# Claude Code model routing

## Design

Settings for the `designer` agent and any design work. Paths are relative to the repo root unless they start with `~`.

- Freeze: design work starts only when the owner asks, and agents never propose design changes unprompted.
- Design source: `docs/design/redesign-a/tokens.css`, the single design source and token sheet for the rebuild. It covers light and dark with system fonts, plus a surface system. Read its header comment first, because it lists the surface rules and the contrast grades. The token sheet wins any conflict with the implementation.
- Implementation: the rebuild is a React 19 single-page app built with React Aria Components, plain CSS on the token sheet and hand-built SVG charts. FastAPI serves it on 127.0.0.1. Its code lives in [NEEDS CONFIRMATION: rebuild code location, proposed `app/web`].
  - The current app in `dashboard/static/` still runs on development, with its own `tokens.css`. Bug fixes to it keep its existing look and use its own token sheet, not the rebuild's.
- Tokens: `docs/design/redesign-a/tokens.css`, not mirrored anywhere. Contrast grades and surface rules: the header comment in that file.
  - Surfaces: page, card, inset well for data areas (charts, tables, row lists) and raised card for findings. In light mode, wells stay white so the light model colors keep 3:1.
  - Model colors: the `--m-*` aliases. Model bars use the model's color, and cost kinds use fill patterns, so neither rests on hue alone.
- Benchmark: direction A "Timeline", which the owner picked on November 8. The rebuild is a full UI and UX redesign, not the old app on a new stack. Live is the home page and the center of the app. Review holds Summary, Sessions, Agents (one page, usage and setup together) and Models. Setup holds Your setup and To fix, and Reference holds How Claude Code decides and Glossary. The designer agent's usability rules for app and canvas UI apply. Before any design work, read `~/.claude/designer/usability-for-apps.md` if it exists.
  - Direction A's source lives in `docs/design/redesign-a/` (`board.html`, `a.js`, `app.css`, `tokens.css`, `strings.js` and related files). Its screenshots stay outside git in `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/design-redesign/shots/`.
  - Stack A's screens and tools stay in `docs/design/usage-stack/` as history only.
  - Rebuild research and decisions live under `docs/rebuild/` on branch `docs/dashboard-rebuild-research`.
- Reuse first:
  - Status tokens (`docs/design/redesign-a/tokens.css`, the `--status-*` group) for every status cell. Each of the seven statuses shows its mark glyph and its word on screen, never hue alone.
  - Run states (Working, Finished, Not started yet) have their own glyphs and show glyph and word together, like the statuses.
- Accessibility floor: AA contrast on all text and 3:1 for non-text. Accepted exceptions (owner): one, non-text only, since October 30. In light mode, the token-kind ramp's `--rk-1` (1.54:1) and `--rk-2` (2.50:1) sit under the 3:1 non-text floor on the white card. The exception holds only while every bar that uses the ramp keeps legend totals or a kinds table, and a visible start edge. The Models cost-by-kind chart doesn't use the ramp, because cost kinds there use fill patterns.
- Figma: off.
- Chrome: on, under `~/.claude/rules/claude-in-chrome.md`.
- Writer: `tech-writer` drafts every word of copy in a design. Owner style: no em dashes, no colons in prose, dates month first, no bold, sentence-case headings.
- Widths: 1440 and 375. Directions and the picked direction render at both.
- Design output: directions go to the session scratchpad first. Nothing goes in the repo before the owner picks a direction. After the pick, the picked direction's source goes under `docs/design/`.
- Build after the pick: a separate feature for the main session's lead (`deep-reasoner`), working with `fast-worker` on a feature branch, uncommitted. The lead commits only when the owner says so.

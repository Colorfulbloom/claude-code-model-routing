# Claude Code model routing

## Design

Settings for the `designer` agent and any design work. Paths are relative to the repo root unless they start with `~`.

- Freeze: design work starts only when the owner asks, and agents never propose design changes unprompted.
- Design source: `dashboard/static/tokens.css` (plain HTML and JavaScript, no build step, served by Python's standard library on 127.0.0.1). It's a light and dark token sheet with system fonts, and the only design source. Read its header comment first. The token sheet wins any conflict with the implementation.
- Implementation: the page and its script in `dashboard/static/`, beside the token sheet, rendered at http://127.0.0.1 on the server's port. No login, because the page is local and read-only.
- Tokens: `dashboard/static/tokens.css`, not mirrored anywhere. Contrast grades: the header comment in that file.
- Benchmark: none yet. The first direction the owner picks becomes the benchmark. The designer agent's usability rules for app and canvas UI apply to this web page too. Before any design work on it, read `~/.claude/designer/usability-for-apps.md` if it exists.
- Reuse first:
  - Status tokens (`dashboard/static/tokens.css`, the `--status-*` group) for every status cell. Each of the seven statuses shows its mark glyph and its word on screen, never hue alone.
- Accessibility floor: AA contrast on all text. Accepted exceptions (owner): none.
- Figma: off.
- Chrome: on, under `~/.claude/rules/claude-in-chrome.md`.
- Writer: `tech-writer` drafts every word of copy in a design. Owner style: no em dashes, no colons in prose, dates month first, no bold, sentence-case headings.
- Widths: 1440 and 375. Directions and the picked direction render at both.
- Design output: the session scratchpad. Nothing in the repo before the owner picks a direction.
- Build after the pick: the picked direction's page and styles in `dashboard/static/`, as a separate feature for the main session's lead (`deep-reasoner`), working with `fast-worker` on a feature branch, uncommitted. The lead commits only when the owner says so.

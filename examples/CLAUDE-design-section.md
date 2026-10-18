This is a template for the "Design" section the `designer` agent reads. Copy the `## Design` section below into your project's CLAUDE.md (or any file in its CLAUDE.md hierarchy, a `.claude/rules/*.md` file included), fill every bracket, and delete the lines that do not apply. The bullets marked optional can go. Delete this note too.

## Design

Settings for the `designer` agent and any design work. [PATH CONVENTIONS: what paths are relative to, for example "design-source paths are relative to its repo, implementation paths to the theme folder".]

- Freeze: [POLICY ON UNPROMPTED DESIGN CHANGES, for example "designs are final before launch; design work starts only when the owner asks, and agents never propose design changes unprompted"]. Optional.
- Design source: [PATH TO YOUR COMPONENT LIBRARY, DESIGN SYSTEM OR MOCKUPS] ([STACK, for example the framework, its version and the CSS library]). Read its [ONBOARDING DOCS, for example its CLAUDE.md or a reference doc] first. [WHICH SIDE WINS A CONFLICT, for example "the design source wins any conflict with the implementation".]
- Preview: [URL OF THE RUNNING DESIGN SOURCE, for example http://localhost:PORT] ([THE COMMAND THAT STARTS IT and what it writes to disk, if anything]). Start it in the background if it is not running. Optional.
- Implementation: [WHERE THE DESIGN GETS BUILT, for example the paths to components, styles and compiled CSS], rendered at [LOCAL SITE URL]. [LOGIN RULE, for example "admin pages need the owner's existing browser login; never type credentials".]
- Tokens: [PATH TO THE DESIGN TOKENS FILE], [WHERE THEY ARE MIRRORED, if anywhere]. Contrast grades: [WHERE CONTRAST RATIOS ARE DOCUMENTED, if anywhere].
- Benchmark: [THE ONE EXISTING SCREEN OR COMPONENT EVERY DIRECTION IS HELD TO], "[THE OWNER'S OWN WORDS FOR ITS LOOK]". [PATHS TO ITS STORIES OR MOCKUPS, ITS SOURCE AND ITS STYLES.]
- Reuse first:
  - [COMPONENT NAME] ([PATH IN THE DESIGN SOURCE]; [PATH IN THE IMPLEMENTATION]) for [WHAT IT IS FOR, for example badges, tags and status]
  - [COMPONENT NAME] ([PATHS])
  - [A PATTERN OR DETAIL WORTH BORROWING, for example a header bar, an accent edge or a heading treatment]
  - [A COMPONENT THAT IS NOT COMMITTED YET, with "commit it before relying on it", if any]
- Accessibility floor: AA contrast on all text. Accepted exceptions (owner): [TOKEN, WHERE IT IS USED AND ITS RATIO, or "none"].
- Figma: [on or off].
- Chrome: [on or off], under `~/.claude/rules/claude-in-chrome.md`.
- Writer: [WRITER AGENT NAME, for example `tech-writer`] drafts every word of copy in a design. Owner style: [PUNCTUATION AND FORMATTING RULES, for example no em dashes, no colons in prose, dates month first, product versions written in full].
- Widths: [THE WIDTHS TO RENDER AT, for example 1440, 992, 768, 375]. Directions render at [TWO OF THEM, a desktop and a phone width]; the picked direction at all of them.
- Design output: [WHERE VARIANTS, SCREENSHOTS AND SCRIPTS GO, for example the session scratchpad]. Nothing in the repo before the owner picks a direction.
- Build after the pick: [WHAT IS BUILT FIRST, for example stories and styles in the design source], through [AGENT, for example `fast-worker`], [committed or uncommitted]. [THE PORT TO THE IMPLEMENTATION AND WHO LEADS IT, for example "a separate feature for the main session's lead (`deep-reasoner`)".]
- Do not touch: [FILES OR FOLDERS THE DESIGNER MUST LEAVE ALONE, for example untracked exports or scratch folders]. Optional.

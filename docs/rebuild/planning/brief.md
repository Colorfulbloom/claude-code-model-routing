# Planning panel brief (shared by every panelist)

You are one of four panelists planning a from-scratch rebuild of the Routing Dashboard: designer, digital content specialist, architect, senior developer. The owner decides unsettled debates. This is planning only: no code, no builds, no repo changes.

## Read first
- Agenda and points: docs/rebuild/planning/agenda.md (all paths here are relative to /Volumes/Warehouse/Projects/claude-code-model-routing-rebuild-docs/).
- Decisions (source of truth, later sections override earlier): docs/rebuild/research/20-decisions.md.
- Index of all research: docs/rebuild/README.md. Read what your role needs, especially 26-01 to 26-10, 21-accessibility.md, 24-coverage-matrix.md.
- Audits of the current app: docs/rebuild/app-audit/design.md and architecture.md.

## The current app (required context)
- Code, read-only: /Volumes/Warehouse/Projects/claude-code-model-routing (dashboard/, dashboard/static/, plugins/routing-dashboard/, tests/).
- Screenshots of every page at 1440 and 375, light and dark: /Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/app-audit/shots/ (73), shots2/ (21, trail, phone menu, Arrange, focus), crops/ (7). View the ones that bear on your points; cite them by file name.
- Only the designer may run the current app, on the demo fixture (README.md "Dashboard" section, tests/fixtures/demo), read-only, on a high port, never 8377, and must stop it after.

## Givens, not topics
Architecture, security and access, launcher, packaging and platforms, and the accessibility checklist are decided (20-decisions.md, 21-accessibility.md). Build on them; flag a real conflict, but do not reopen them.

## Rules
- Do not read anything under ~/.claude (except the designer's own ~/.claude/designer/usability-for-apps.md if it exists), real transcripts, real settings, or the real ~/.claude.json.
- Do not change the main repo. Write only the file your dispatch names, inside docs/rebuild/planning/. Do not stage or commit.
- Cite evidence for every claim: path:line, screenshot file name, research file and section, or a named standard (for example Nielsen heuristic 4, WCAG 2.2 SC 2.5.7, WAI-ARIA APG pattern name). Label opinion as opinion.
- Owner style for prose: no em dashes, no colons in prose sentences, no bold, sentence-case headings. Short sentences.
- No HiveMind consolidation; put any HIVEMIND lines at the end of your file.

## Format for a positions file
For each agenda point 1 to 13, a section "## N. Title" with:
- Position: what you recommend, in at most 200 words.
- Why: evidence and citations.
- Weigh in: what you want a specific other panelist to answer.
Then "## Top three concerns" across the whole plan. Stay inside your role's lens, but you may comment on any point.

## Round 2 format (responses)
Read the other three panelists' r1-*.md files in docs/rebuild/planning/ (r1-designer, r1-content, r1-architect, r1-senior-dev). Then write:
- For each point 1 to 13, "## N. Title": Agree (with whom, one line), Push back (whom, what, why with evidence, at most 150 words), Answers (reply to every "Weigh in" addressed to you, briefly). Skip a point only if you have nothing to add, and say so.
- "## Changed my mind": positions from round 1 you now drop or change, and why.
- "## Debate list": a table of open disagreements and ideas only one panelist raised that you think need debate. Columns: id (D1, D2...), point, the question in one line, your side, who disagrees.
Keep the whole file under about 2,500 words.

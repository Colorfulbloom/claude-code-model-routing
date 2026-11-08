# Planning panel agenda (draft, November 8)

Panel: designer, digital content specialist (tech-writer), architect (deep-reasoner), senior developer (fast-worker, high effort). Neutral summary by judge.

Shared context for every panelist:
- Current app code, read-only: /Volumes/Warehouse/Projects/claude-code-model-routing (dashboard/, plugins/routing-dashboard/, tests/).
- The current app running on the demo fixture, read-only, on a high port (never 8377).
- Screenshots of every page at 1440 and 375, light and dark: /Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/app-audit/shots (73), shots2 (21), crops (7).
- Audits: docs/rebuild/app-audit/design.md and architecture.md.
- Research and decisions: docs/rebuild/research/ (20-decisions.md is the source of truth).
- Off limits: real ~/.claude, real transcripts, real settings.

## Points

Points removed by the owner as already decided in research (architecture, security, launcher and platforms, accessibility checklist): treat 20-decisions.md and 21-accessibility.md as givens, not topics.

1. Purpose and audience. Who the app is for (owner first, anybody's setup), the jobs it does, and what "done" looks like for the first release.
2. First-release scope. Which surfaces, pages and edit types ship first, and which wait. What the current app does that the first release must match.
3. Sitemap and navigation. Page list, home page, project switching under one server, where usage, setup and editing live, URL scheme.
4. Current app, keep and change. Walk the current pages and screenshots. What works, what fails, what to carry over as is (usage pages, Stack direction).
5. Setup view. Showing a whole setup from simple to complex: setup map, agent catalog, surface lists, source chips, read-only markers, what runs versus what is set.
6. Editing flow. One review rail for every surface, text editor versus field editors, diff, backup, undo, stale-file check, the four risk tiers and the risky confirm, MCP command handoff.
7. "To fix" and diagnostics. What counts as a problem, how each one is explained and fixed, unreadable surfaces.
8. Usage and history. The 30-day default and presets, history past Claude Code's cleanup, cost labels (list price, output lower bound), Live page.
9. Words and content. Terminology (scope, layer, surface names), labels, empty states, errors, help, the rules reference, tone. One glossary.
10. UX standards check (required debate: designer and architect, others may join). Hold the plan for points 2 to 9 against named, citable standards: Nielsen's 10 usability heuristics, WCAG 2.2 AA as given in 21-accessibility.md, WAI-ARIA Authoring Practices patterns for the components used, ~/.claude/designer/usability-for-apps.md, and the project's Stack benchmark. For each, does the plan meet it, where does it fall short, and does the architecture expose the state, data and events the UX needs. Cite the standard for every claim.
11. Testing. Porting the 123 resolver fixtures and edit and security tests, the setup fixture corpus, Playwright with axe, what runs per change.
12. Build order and coexistence. Milestones, where the new app lives while the old one keeps working on development, cutover, data carry-over, cost per milestone.
13. Open floor. Anything a panelist thinks is missing.

## Process

1. Positions: each panelist writes a view on every point, independently.
2. Responses: each reads the other three, agrees or pushes back with reasons.
3. Debates: disagreements and ideas only one panelist raised get a focused debate between those involved.
4. Summary: judge writes the plan from agreements and lists unsettled debates with each side's case for the owner.
5. Check: verifier on Opus, then Fable.

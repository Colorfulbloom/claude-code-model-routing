# Round 1 positions, designer

Written November 8, 2026 (started 11:08 EST) by the designer. My lens is screens, flows, information architecture, interaction patterns, the design system, accessibility in practice and UX standards.

Settings used. The project CLAUDE.md Design section was followed, with design source `dashboard/static/tokens.css`, benchmark Stack direction A (`docs/design/usage-stack/a-usage/`), widths 1440 and 375, Figma off, writer tech-writer. I read `~/.claude/designer/usability-for-apps.md` (cited below as "usability rule N"). I did not run the current app this round. The archived captures cover every page at both widths and themes, and I cite them by file name (`shots/`, `shots2/`, `crops/` under `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/app-audit/`). Any on-screen wording below is a placeholder for tech-writer, not proposed copy.

Short names used for sources.
- design.md is `docs/rebuild/app-audit/design.md` (U1 to U17 usability findings, A1 to A14 accessibility findings).
- arch.md is `docs/rebuild/app-audit/architecture.md` (findings 1 to 35).
- D20 is `docs/rebuild/research/20-decisions.md`. A11y is `research/21-accessibility.md`.
- Nielsen H1 to H10 are the ten heuristics (https://www.nngroup.com/articles/ten-usability-heuristics/).
- APG is the WAI-ARIA Authoring Practices Guide pattern of that name (https://www.w3.org/WAI/ARIA/apg/patterns/).

## 1. Purpose and audience

Position: The app answers four questions about a Claude Code setup, in this order of value. What runs in this project, and why? Can I change it safely? What did it cost, and did each agent run as pinned? What is happening right now? The first user is the owner. The design target is a capable Claude Code user who did not build the setup they are reading, because a screen that works for a stranger's setup also works for the owner's (D20 line 55). Each page leads with one task question, and the next step appears once the answer is on screen (opinion, from my "intent first" lesson). The first release is done when five job walkthroughs pass at 375 and 1440, keyboard only, with zero axe violations, on the simple, typical and complex setup fixtures. The five jobs are these. Explain one agent's running model and effort. Find and fix one problem from "To fix". Change one safe value and undo it. Read the 30-day cost by agent. Watch a live session. A job counts as passing when a cold reader finishes it without reading a file path first.

Why: D20 owner decisions (lines 6-11, 54-55, 63) set read anybody's setup, edit it, and keep history. design.md "First impression" finds the setup side reads like resolver output, precise but in file paths and env keys. Usability rule 8 and Nielsen H2 (match the real world) ask for task words.

Weigh in: Content specialist, can you write the four questions as the app's own one-line purpose, so every page intro can echo one of them? Architect, is "a stranger's setup" the right test, or should the first release assume the owner's routing install?

## 2. First-release scope

Position: Ship the whole read side and the safe and careful edit tiers first. Hold the risky tier one milestone, until its confirm has been rendered, critiqued and tried by the owner. The read side in release one covers Projects home, setup map, agent catalog, one list-and-inspector page per surface, "To fix", usage pages, Live, Sessions, Rules reference. Edits in release one cover settings keys, agent fields and bodies, CLAUDE.md and rules text, skills text, deny and ask rules, and creating and deleting files. The current app must be matched on five things. The precedence list ("Where it's set"), the seven status words, pin check phase 1, undo with older backups, and Live with Pause. Drop Settings Arrange (owner, D20 line 63). Move Installed files to the optional routing layer (D20 line 62).

Why: Every surface editable at once spreads review and test effort thin (opinion). The risky tier is where a bad confirm costs the most, so it earns its own design round (WCAG 2.2 SC 3.3.4, error prevention). The match list comes from design.md section 4 and "What works well". D20 lines 54 and 58 fix the edit scope, so this is about order only.

Weigh in: Architect, does holding the risky tier one milestone leave any API shape unfinished that the safe tier needs, such as `risk.ack` in the preview? Senior developer, which of the safe-tier editors is cheapest to finish first?

## 3. Sitemap and navigation

Position: The home page is Projects, because one server serves every project (D20 line 50). Inside a project the sidebar has three groups. Activity holds Overview, Live and Sessions. Setup holds the map, then Agents, Skills, Instructions (CLAUDE.md and rules), Settings, Permissions, Hooks, MCP servers and Plugins. Then come "To fix" with a worded count, and Reference with the Rules reference. Fold Models into Overview as a section, because its ring repeats Overview's (design.md, Visual hierarchy, Duplication). The project picker sits at the top of the sidebar as a searchable combobox that shows each project's state. Under no project, only Projects shows, which fixes the dead "pick a project" pages (U8). Put the project, page and selected item in the path, for example `#/p/<project>/agents/<name>`, and put range and scope in the query. Then every inspector state can be linked and restored (U17), and a copied link never carries a key. The Trail page goes away. Its content becomes the "Why" section of each item's inspector, with a breadcrumb.

Why: Usability rule 14 (inspector follows selection). APG Combobox for a long, searchable project list. Nielsen H6 (recognition over recall) and Hick's law via usability rule 20 for the grouped sidebar. U6 and `shots2/11-trail-builder-1440-light.png` show a Trail headed "Settings" with no way back.

Weigh in: Content specialist, are "Activity", "Setup" and "Instructions" the right group and page words, or do readers expect "Usage" and "Memory"? Architect, can project ids be stable and readable enough to sit in a path?

## 4. Current app, keep and change

Position: Keep the usage pages almost as they are. That means the KPI row, a question under every card title, the "Estimated at API list price" line, status as mark plus word, the "Did it run as pinned?" card, the "Where it's set, top wins" list, the Live dispatch canvas and the tokens. Rebuild those as React components on the same tokens. Change these. The Settings cell should lead with what runs, not what is set (U3). A read-only control must look read-only and say why beside it (U4). Use one empty-state component with one action (U12). Use one phone table pattern that keeps table semantics (A4). Add a scrim on the phone drawer (A5). Give every route its own title, focus and announcement (A1, A2). Replace "Reload the page to update" with an "Updated" time and live refresh (U9). Show each chart once, and use one model order per page. Fix the Live chip that covers a card (A8). Drop Arrange, the Trail page, the round-numbered CSS prefixes and the static version chip as a separate control. Fold the version into the Rules banner.

Why: `shots/02-overview-1440-light.png` is the benchmark at work. `shots/09-settings-1440-light.png` shows "xhigh Lowered" in the cell while the picker says "high now". `crops/empties.png` shows four empty-state forms. `crops/ov375-top.png` shows about 150 px of chrome before the page title. `crops/live-overlap.png` shows the chip over "$3.22". design.md section 4 has the full keep, change and drop table.

Weigh in: Senior developer, which current CSS, chart code and string keys can port straight across, so the usage pages cost the least to rebuild?

## 5. Setup view

Position: Use three levels, simple to complex. Level 1 is the setup map. It shows one row per surface with the result that runs, such as "Opus 5.5, high", "6 agents" or "3 hooks on 2 events", plus worded status marks. Layers stay hidden until asked for. Level 2 is "Show where each comes from". It turns on layer columns (managed, user, project, local, plugin) with counts per cell. At 375 those collapse to layer chips under each row. Level 3 is the surface page. It uses a list-and-inspector pattern with the list on the left and the selected item on the right. The inspector shows what runs first, then "set to X in file, line N", then why (the old Trail), then usage beside the definition. A source chip carries the layer in words and a lock mark for managed and plugin items. A read-only reason sits in one line. The agent catalog lists every agent from files and plugins, including ones that never ran. Plugin agents show the fields Claude Code ignores for them. A layered setup is a stack, not a flow, so draw it as a table, not a node graph (opinion).

Why: Usability rules 1 to 3 (staged disclosure), 11 (data beside settings), 13 and 14 (status on the card, settings in the inspector) and 22 (simplified view first, raw one step away). 26-02 "Common output per item" already gives name, sources, winner, status and reason. D20 line 63 asks for a catalog that lists agents that never ran. U1 and U2 are the gaps today.

Weigh in: Architect, can the setup map's level 1 come from one cheap call per project, or does it need every surface reader to run? Content specialist, how should a layer read on a chip, for example "You, all projects" against "User"?

## 6. Editing flow

Position: One review rail serves every surface, grown from today's flow. The inspector is in view mode until the person presses Edit. Edit appears only when this project's edit key is present. Otherwise a lock line says how to turn editing on. Structured values get field editors, with pickers built from what exists (models, tools, hook events, effort levels), a rule list with add and remove, and errors beside each field. Text bodies use CodeMirror 6, and "Edit as text" is one step away for any file. The rail shows the effect first (running value before and after, and when it applies), then the diff, warnings and the real path for a symlinked file. Nothing on the page changes until Save, so the preview never contradicts the summary above it. Safe and careful saves use one Save button, and careful saves list their warnings above it. Risky saves show the full command and when it runs, plus a checkbox that enables a differently worded confirm button. The confirm sits away from where Save was, so a double-click cannot pass it. Delete uses an alert dialog. For MCP in user or local scope, show a command panel with Copy and "Check again".

Why: 26-01 sections "The common preview shape" and "Risk tiers". D20 lines 58, 69 and 71. WCAG 2.2 SC 3.3.1, 3.3.3 and 3.3.4. APG Alert Dialog. Usability rules 5, 10, 15 and 16. My lessons "preview beside the truth" and "double-click a swapped confirm" both came from bugs we shipped earlier. 26-04 notes Tab is unbound in CodeMirror on purpose (SC 2.1.2).

Weigh in: Architect, can validation errors carry a field path as well as a line, so an error lands on its field? Can the 2-second post-save recheck (26-08) reach an open rail as an event? Senior developer, is "Check again" after a copied `claude mcp` command cheap to build?

## 7. "To fix" and diagnostics

Position: Count only judged problems, never normal precedence. That means a value Claude Code will not load, a value set but not read, an unknown value, a lowered value against a pin, a file that fails to parse, two agents of one name in one folder, an allow rule that a deny shadows, an import that does not resolve, and a surface that could not be read. Overridden values leave the count and stay in each item's "Where it's set" list. Group rows by the thing (an agent, a setting, a file), with statuses inside, and use two groups, "Won't load" first and "Not as set" second. Each row says what is wrong in plain words, one line on why it matters, and where. It ends in one action that opens the inspector with the field focused, or the editor at the line. The sidebar entry shows a worded count, not a bare dot. An unreadable surface keeps its page and shows what did read, plus an inline error card naming the file, the reason and the fix. It is never a blank page.

Why: `shots/12-attention-1440-light.png` shows 13 rows for Tidewater, mostly Overridden, with builder Effort split across three groups (U7). D20 line 63 asks for "To fix" without normal overrides. Usability rules 16 and 17. Nielsen H9. My "facts quiet, checks loud" lesson. 26-02 flags the same-folder agent clash, and 26-03 asks for a "Couldn't read" state.

Weigh in: Architect, can each problem carry a route to the fixing view, meaning the item, field and line, not only a file? Content specialist, are "Won't load" and "Not as set" the right two group names?

## 8. Usage and history

Position: Keep the 30-day default and the owner's presets (7 days, 30 days, 90 days, 12 months, All history). Five choices plus a custom range is past the five-option line, so use one labeled Select at both widths rather than a segmented control that cannot fit at 375. Say the range in the page intro sentence. When All history is picked, show where it starts beside the control. Show the cost note once per card, not on every number. That note says costs are list-price estimates and output is a lower bound. Swap the footer for an "Updated" time, and refresh on focus and on a timer. During a first-run history read, show a progress line over skeletons shaped like the loaded page, so nothing jumps. Live keeps Pause and the polite status line, puts the session in the URL, picks from any project's sessions, and announces state changes only. Session detail earns its page with a replay of the dispatch canvas.

Why: D20 line 74 (30-day default, presets, start shown on screen). 26-10 notes that long-history products name which limit applies. Usability rule 20 (HIG pop-up for more than about five options). 25-verifier item 2 (lower bound, list price). Usability rule 23 (say it once). A11y rows "4.1.3 + 2.2.2 live". U9, U16 and U17. `shots/07-session-detail-1440-light.png` leaves half a screen empty.

Weigh in: Architect, can every query return its "updated at" time and the stored-history start date? Can ingest report progress as a count? Content specialist, how should "output is a lower bound" read for someone who has never seen a transcript?

## 9. Words and content

Position: One glossary, owned by tech-writer, with every screen held to it. Three rules from the design side. First, use words the reader knows before internal names. Layers read as who and where ("you, all projects", "this project, shared", "this project, just you", "your organization", "plugin name"), and the file path is secondary text, never the label. Second, keep one word per state. The seven status words stay, and no headline repeats its chip ("Not known" over "Unknown", design.md Consistency). Third, every empty state names what will appear and offers the action that fills it, and every error names the cause and the fix. Help sits in one place on every page, a section-level disclosure beside the heading, which meets SC 3.2.6. The Rules reference groups rules by setting, says the version check once in a banner, and drops the per-rule repeat (U15, `crops/rules-top.png`, 13,805 px tall). Strings stay in one typed file, and the writer reviews them per screen.

Why: Usability rules 8, 9, 18 and 23. Nielsen H2 and H10. WCAG 2.2 SC 3.2.6 (consistent help) and 3.3.1. U5 shows "This project, just you" listed twice with no difference. D20 line 38 sets typed t() and tn().

Weigh in: Content specialist, can you own the layer words and surface names first, since the setup map's layout depends on their length at 375?

## 10. UX standards check

Position: The plan is strong on the read model and the edit core. It falls short in four places the UX needs. First, access must survive a reload. With a single-use code and a key held only in memory (D20 line 73, 23-domain B2), a reload, a second tab or a bookmarked deep link loses the key. That breaks Nielsen H3 and H9 unless the page offers a one-step way back. Second, errors must anchor to fields. The preview's validation has code, line and text (26-01), but no field path, so a field editor cannot put the error beside its field (SC 3.3.1, usability rule 16). Third, the rail needs events. "Overwritten by another writer", "file changed while you edit" and ingest progress must reach an open page, or the app fails silently (usability rule 17, H1). Fourth, the risky confirm and delete need one tested APG pattern each. A11y misses SC 3.3.4, 3.2.2, 1.4.13 and 2.1.2, and I add them below. The setup and edit screens have no benchmark yet, because Stack A covers usage pages only. Directions for them must be rendered and picked before their milestone.

Why: The table holds one row per standard, with my verdict and what the architecture must expose.

| Standard | Plan meets | Short of | Architecture must expose |
|---|---|---|---|
| Nielsen H1, visibility of status | Live status line, polling, role=status on save (A11y) | No "Updated" time on usage; post-save overwrite not shown | updated_at per query; recheck result as an event |
| H2, real-world words | 26-02 status words, tech-writer glossary | Layers named by scope keys today (U5) | layer id plus a stable kind, so the page can word it |
| H3, user control and freedom | Undo, older backups, Pause (26-01 history) | Reload or new tab loses the key | key or session that survives reload for the server's life, or a recover path |
| H4, consistency | One preview shape, tokens | Four empty-state forms, two table patterns (U12, A4) | none, design work |
| H5, error prevention | Validators block what Claude Code would skip; stale hash; risky ack hash (26-01) | Risky confirm not designed | risk.ack.shows with event and matcher, as planned |
| H6, recognition over recall | Pickers possible from catalogs | Hook events, tools and models need lists | enumerations per field (models, tools, events, effort levels) |
| H7, flexibility | Deep links in hash | No jump-to search | a name index across items (later) |
| H8, minimalist | Facts quiet in "To fix" (D20 line 63) | Rules page repeats (U15) | none |
| H9, recover from errors | Parse retry, "Couldn't read" (26-08, 26-03) | Errors keyed by line only | field path on each validation item |
| H10, help | Rules reference as evidence | No help placement yet | none |
| WCAG 2.2 SC 2.4.2, 2.4.3, 4.1.3 | A11y checklist rows | none | route metadata (title per page) |
| SC 2.4.11 focus not obscured | scroll-padding under the sticky shell | Sticky rail and Save bar on phone | none |
| SC 2.5.7 dragging, 2.5.8 target size | Move buttons, 24 px floor | Inline table links at 16 to 21 px (A9) | none |
| SC 3.3.1, 3.3.3 error identification and suggestion | errors and warnings in the preview | no suggested fix field | a fix hint or fix route per error |
| SC 3.3.4 error prevention, data (added) | review, check and undo all present | none | keep backups for every surface, groups included |
| SC 3.2.2 on input (added) | none stated | The project picker and range Select must not move focus or route without the person choosing | none |
| SC 1.4.13 content on hover (added) | none stated | Chart tooltips must be dismissable and hoverable | none |
| SC 2.1.2 no keyboard trap (added) | 26-04 keeps Tab unbound | Any `indentWithTab` needs the Escape hint | none |
| SC 1.4.10 reflow at 320 | A11y row | Layer matrix and diff at 320 | none, design work |
| APG patterns | React Aria covers Combobox, Select, Dialog, Alert Dialog, Disclosure, Grid List, Table, Radio Group, Tabs, Breadcrumb, Toolbar (D20 line 46) | No tree view, which keeps setup out of Tree View complexity | selection id in the route |
| usability-for-apps rules 1 to 25 | 13, 14, 18, 22 fit the list-and-inspector plan | 25, cost where it is set. The agent model picker should show list price from prices.json | prices per model to the client |
| Stack A benchmark | usage pages | Setup, inspector and rail have no benchmark | none, a design round |

Weigh in: Architect, this is the required debate. Which of the four gaps (reload access, field paths, rail events, enumerations for pickers) does the architecture already cover, and which do you see as design work, not API work?

## 11. Testing

Position: These are the design-side tests I want per change. Playwright with axe (`wcag22aa` tag) on every route and state, at 1440, 375 and 320, light and dark. Add emulated forced colors and reduced motion. Add an overflow scan, a target-size scan and a rendered contrast scan that skips clip-hidden text. Add one keyboard-only script per first-release job from point 1. Add ARIA snapshots for route announcements and save, undo and copy status lines, with a count that proves only state changes announce. Add a real double-click on every swapped confirm. Screenshot baselines come from a setup fixture corpus at four sizes (empty, simple, typical, complex) plus a broken set (parse errors, unreadable files, symlinks, plugin agents with ignored fields) and stress names (long agent names, 50 agents, 200 permission rules). Each milestone ends with a manual VoiceOver pass and a designer review against the picked direction.

Why: A11y "Test" column. The 21-accessibility note says automation found 57.38 percent of issues (vendor data), so manual passes stay. design.md lists findings that scans did catch (A9 target size, A1 titles). My lessons "chip rows wrap at minimum width", "double-click a swapped confirm" and "app audit scan run" each came from a bug a single-width or scripted-click test missed.

Weigh in: Senior developer, can the setup fixture corpus be one generator with size and breakage flags, so design baselines and resolver tests share it?

## 12. Build order and coexistence

Position: Design leads each milestone by one step. M0 is the shell and components, with tokens, sidebar, project picker, cards, KPI, charts, empty, loading and error states, and the accessibility baseline (titles, focus, announcements, scrim). Port Stack A to React here. M1 is usage parity on SQLite (Overview, Sessions, Live, agent usage). It has the lowest design risk because the benchmark exists. Before M2, I render two or three directions for the setup map, list and inspector, and "To fix", and the owner picks one. M2 builds the read side. Before M3, directions for the review rail, field editors and text editor. M3 builds safe and careful edits. M4 adds risky edits and the MCP command panel, after the confirm round. M5 adds the optional routing layer. While both apps run, the new one carries a visible "new dashboard" label in the sidebar header. That way the owner always knows which app wrote a backup (opinion).

Why: The CLAUDE.md Design section says nothing is built before the owner picks a direction. Stack A covers usage pages only (`docs/design/usage-stack/a-usage/`, 12 page pairs, none for setup or edits). HiveMind tallies show a design-directions round at a median of about 220k tokens. [NEEDS CONFIRMATION: dollars per design round from the dashboard's cost per run, because tallies undercount.]

Weigh in: Architect, can M2's read side ship without the edit API in place, so the inspector design is not blocked on the preview shape?

## 13. Open floor

Position: Five gaps.
- First run. The page needs a state for no projects found, for an empty database while history is read, and for uv still downloading, each with one action.
- Jump to. A name search across agents, skills, settings, files and sessions serves Nielsen H7, and it pays off once a setup has 50 items. It can come after release one.
- Theme. Preferences are server-side (D20 line 61), so a theme switch belongs in a small Preferences panel, and `color-scheme` meta comes first (A6).
- Export. Banks and Monzo offer a CSV of the chosen range (26-10), which fits history past the cleanup. Consider it for the usage pages.
- Ownership. A second person reading a shared repo's setup needs to see which items they can change (writable) and which are someone else's (managed or plugin). The source chip covers it only if the read-only reason is always shown.

Why: Usability rule 18 (every empty state offers the fill action). design.md "Add" table (command palette, projects home). 26-10 Monzo row. D20 lines 61-62.

Weigh in: Everyone, which of these belongs in release one?

## Top three concerns

1. The setup and edit screens have no benchmark and no rendered direction yet. Built straight from the research shapes, they will read like resolver output, the way Settings and Needs attention do today (design.md "First impression", `shots/12-attention-1440-light.png`). A direction round must come before M2 and M3.
2. Access through a reload. A single-use code and a key held only in memory mean a reload, a second tab or a deep link loses access, and that is a daily dead end (Nielsen H3 and H9). The plan needs a one-step way back that keeps the security decision intact.
3. The edit rail needs more than the preview shape gives it. Errors need a field path, and the open page needs events for a file changed underneath, an overwrite after save and ingest progress. The risky confirm needs one accessible, double-click-safe pattern. Without these the rail fails silently or puts errors far from their cause (usability rules 16 and 17, WCAG SC 3.3.1 and 3.3.4).

HIVEMIND
NEW dashboard: The design benchmark folder docs/design/usage-stack/a-usage/ holds 12 page pairs (light and dark) for usage, settings, attention, files, rules, all projects and empty states only; it has no setup-map, catalog, inspector or edit-rail screens, so rebuild setup and edit screens need their own direction round. | check: ls docs/design/usage-stack/a-usage | evidence: docs/design/usage-stack/a-usage/01-overview-light.html
END HIVEMIND

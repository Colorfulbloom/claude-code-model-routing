# Round 1 positions, digital content specialist

Saved by the main session from tech-writer's reply (tech-writer is read-only). Docs quotes come from WebFetch summaries of code.claude.com settings.md, sub-agents.md, mcp.md, memory.md and glossary.md, fetched November 8; near-verbatim, not checked against raw HTML. Strings dump used: scratchpad strings.txt (temporary).

Lens: the words on screen. That means terms, names, labels, empty and error states, confirm text, help and the rules reference, and how well they match what Claude Code itself shows. Every "opinion" label marks my judgment. Everything else cites a path, a string key, a screenshot or a docs URL I read on November 8.

Shorthand used below.
- strings = /Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/static/strings.json
- shots = /Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/app-audit/shots (shots2 and crops the same)
- design audit = docs/rebuild/app-audit/design.md

## 1. Purpose and audience

Position: Write for one reader. That reader knows Claude Code well but hasn't memorized its precedence rules. The owner comes first, and copy must still read right on anybody's setup. So core copy never assumes the model-routing install, "the installer" or a pin. Those words live only in the optional routing layer. Each page answers one question a person brings ("What runs here, and why?", "Where did my tokens go?", "What's broken?"). The page's intro line states that question's answer in one sentence, as it does today. For the first release, "done" for content means four things. Every on-screen term is in one glossary. Every term Claude Code also uses means the same thing it means in Claude Code. Every error says what happened, whether anything changed, and what to do next. No page says "reload the page".

Why:
- The owner asked that the app read anybody's setup, with install-specific features as an optional layer (20-decisions.md, "after the gap research" and "after the coverage matrix").
- Core strings leak install vocabulary today. `s_transcripts_t` (strings:750) names "Installed files". The `f_action_*` keys say "Run the installer" (strings:443). Pin copy shows on every agent page (`c_pin_check`, shots/05-agent-detail-1440-light.png).
- The question subtitles are the design audit's top "what works" item ("Card subtitles as questions orient a cold reader fast", design audit section 3).

Weigh in:
- Architect: does the API give each item a flag for "comes from the routing layer", so copy can stay out of the core without string-level checks?
- Designer: do you agree each page's intro line should answer its question, not describe the page?

## 2. First-release scope

Position: Scope the copy with the features. The strings that must match the current app are the usage pages, the seven status words, the cost and privacy lines, and the edit flow's honesty. The edit flow always says whether a save happened, where the backup is, and what runs after. Port those as patterns, not as 347 separate keys. Today 347 of 823 keys are edit keys, and 87 of them are per-setting copies (`_cap`, `_compact`, `_model`). Swap them for templates that take a setting name and an "effect phrase" from the surface registry. Things that wait get no placeholder copy. No "Coming soon" and no greyed nav items, because a promise on screen is a claim the release can't back.

Why:
- The count comes from strings, by key prefix (run November 8).
- An example of the explosion is `ed_saved_t`, `ed_saved_t_cap`, `ed_saved_t_compact` and `ed_saved_t_model`. They are four keys for one sentence shape.
- Effect phrases genuinely differ. "runs at" fits effort and "starts on" fits model (`ed_back_runs_t`, `ed_back_runs_t_model`), so the slot belongs in the registry and not in the template.
- 26-01-edit-architecture.md gives the preview an `effect.applies` value (live, new_session, restart, reload_plugins). The copy can key off that.

Weigh in:
- Architect: can each registry entry carry a display name, a plural name and an effect verb ("runs at", "starts on", "loads")?
- Senior developer: is a template with typed slots workable in the typed t() and tn() setup the owner picked?

## 3. Sitemap and navigation

Position: Nav names should be the nouns Claude Code uses for the same things. Proposed groups, as opinion:
- Projects as home.
- Setup, with these pages: Setup map, Settings, Permissions, Agents, Skills, Hooks, MCP servers, Instructions (CLAUDE.md, CLAUDE.local.md, AGENTS.md and rules files), Plugins, Output styles.
- Usage, with Overview, Sessions, Models and Live.
- To fix.
- Reference, with How Claude Code decides and Glossary.

"Instructions" follows the docs' own scope names ("User instructions", "Project instructions", "Local instructions"). It avoids "Memory", which docs also use for auto memory. URL segments use the same nouns, lowercased. Page titles follow "Page, Project, Routing Dashboard". Under All projects, hide project-only pages instead of showing "Pick a project" cards.

Why:
- The memory docs table names those scopes as "User instructions", "Project instructions" and "Local instructions" (https://code.claude.com/docs/en/memory.md). Auto memory is a separate system on the same page.
- The glossary has separate entries for Rules, Skill, Subagent, Hook, MCP server and Output style (https://code.claude.com/docs/en/glossary.md).
- Today's dead end is `s_pick_project_h` "Pick a project" on Live, Settings and Needs attention (design audit U8).
- The title pattern comes from design audit A1 and 21-accessibility.md, row 2.4.2.

Weigh in:
- Designer: twelve setup pages is a long rail. Would you rather group by kind (Configuration, Extensions, Instructions)? If so, I need the group labels before I can test them against the docs.

## 4. Current app, keep and change

Position: Keep the voice. It's already plain, honest and specific. Keep these: the question subtitles; "Estimated at API list price" on every cost; the privacy footer's promise; the pattern "Couldn't save. Nothing changed." with a cause and a next step; the "Did it run as pinned?" card, which answers first and cites file and line.

Change these: one name per scope (today there are three vocabularies); one word per status ("Not known" over "Unknown"); say a repeated sentence once (the trail cards, the 84 "Checked on" lines); "Reload the page to update" becomes "Updated {time}"; cut "the dashboard" as a sentence subject where "we" or a passive-free rewrite reads better (opinion, and the owner's call).

Why:
- Three names for the same local file. Settings rows say "This project, just you" (`place_local`, strings:689, shots/09-settings-1440-light.png). The trail says "Local settings" (`layer_local`, strings:516, shots2/11-trail-builder-1440-light.png). The effort cap copy says "Your user file" for the user layer (`ed_cap_who_user`, strings:137).
- "Not known" sits above an "Unknown" chip (`band_not_known` strings:33, `status_unknown` strings:784, design audit Consistency).
- One rule sentence repeats in every "Other values found" card (shots2/11-trail-builder-1440-light.png). "Checked on 2.1.302" repeats on all 84 rules (crops/rules-top.png).
- 92 strings contain "the dashboard" (strings, counted).

Weigh in:
- Owner, through the panel: keep "the dashboard" as the narrator, or switch to "we"? I lean toward keeping it, because "we" implies a team.

## 5. Setup view

Position: Every item shows four things in the same words everywhere: name; source chip with the scope name; what applies, which leads; why, in one sentence.

Lead with what runs. Write "Runs at high", then "Set to xhigh in Project local. The effort cap lowers it." Source chips use the docs' scope names (see point 9), with plugins as "Plugin {name}". A read-only item always says why, in the same spot. "Managed by your organization." "Comes from the {name} plugin. Edits would be lost when it updates." For surfaces that combine by name, union or concatenation, the status word stays one of the seven. The "why" line carries the difference ("Loads when Claude reads a matching file", "Another file with this name wins"). That way people learn seven words, not twelve.

Why:
- The band headline shows the set value while the picker says "high now" (design audit U3, shots/09-settings-1440-light.png).
- The read-only picker looks editable, and the reason sits elsewhere (design audit U4).
- Surfaces combine differently. Memory concatenates, agents and MCP resolve by name, hooks are a union (26-02-scope-combination.md, "Per surface"). 26-02 proposes the seven status words for every surface.
- Plugin cache edits are lost on update (18-config-surfaces.md, item 8).

Weigh in:
- Architect: path-scoped rules and subdirectory CLAUDE.md load on demand. Does "In effect" plus a "loads when" reason hold, or do you need an eighth status?
- Designer: is there room for a one-line "why" under each item at 375?

## 6. Editing flow

Position: Button labels name the action and the target ("Save to settings.local.json", "Delete skill review-pr"), as `ed_save_to` already does. Every preview states when the change applies. The four phrases come from the registry: "Applies now", "Applies in a new session", "Applies after you restart Claude Code", "Applies after /reload-plugins". The risky confirm shows the exact command and when it runs, then asks for one deliberate act. Draft, opinion:

- Heading: "This hook runs a command on your Mac" (alternative: "This hook runs a shell command")
- Body: "Claude Code runs the command below before every Bash call in this project, with your permissions. Read it before you save."
- Control: checkbox "I read this command", then "Save hook".

The MCP handoff gets this draft. "Claude Code keeps this server in ~/.claude.json, and the dashboard never writes that file. To add it, run this in a terminal." Then the command and "Copy command". Edit-off and locked copy must drop `--allow-edits` and "the link the server printed in the terminal" for the plugin wording [NEEDS CONFIRMATION: the rebuild's launcher argument for editing; today `/routing-dashboard:dashboard edits`].

Why:
- Claude Code applies most settings edits live but reads `model` and `effortLevel` only at session start ("When edits take effect", https://code.claude.com/docs/en/settings.md). Output styles need a restart (18-config-surfaces.md, item 9).
- The risk tiers and the ack hash come from 26-01-edit-architecture.md. Allow rules and env are risky (20-decisions.md, round 3).
- Today `ed_off` (strings:260) and `ed_locked` and `ed_token_t` (strings:240, 381) don't fit the plugin path. The README tells plugin users to run `/routing-dashboard:dashboard edits` (README.md, "Dashboard plugin").
- WCAG 3.3.4 error prevention, and Nielsen heuristic 5.

Weigh in:
- Designer: checkbox, typed name or second button for the risky confirm? I can write for any of the three, but the words differ.
- Architect: does the page learn when the copied MCP command has run, so it can say "Added"?

## 7. "To fix" and diagnostics

Position: Every row in "To fix" follows one pattern: a title that names the thing and the problem ("builder, two files define this agent"); one sentence of cause with the file and line; one sentence of consequence; one fix action.

Only judged problems count. That covers Invalid, Unknown, Ignored, an effort lowered against a pin, files Claude Code skips, same-folder agent name clashes, allow rules a deny shadows, imports that don't resolve and unreadable files. Use Claude Code's own words where it has them. A broken JSON file is what Claude Code calls a "Settings Error". A skipped entry is a "Settings Warning". Point to `claude doctor` for Claude Code's own list. An unreadable surface says "Couldn't read {file}", then the reason and the fix, and never shows a blank page.

Why:
- Overridden rows are normal precedence and fill most of today's list (shots/12-attention-1440-light.png, 13 rows, design audit U7). The owner decided "To fix" drops them (20-decisions.md).
- Claude Code labels these "Settings Error" and "Settings Warning", and points people to `claude doctor` ("Fix a broken settings file", https://code.claude.com/docs/en/settings.md).
- Same-folder clashes load one file "chosen by filesystem read order" (https://code.claude.com/docs/en/sub-agents.md).
- Nielsen heuristic 9 and WCAG 3.3.1 and 3.3.3.

Weigh in:
- Designer: should "Unknown" count as a problem, or sit in a separate "Can't tell" group? Lumping "we don't know" with "this is broken" may alarm people.

## 8. Usage and history

Position: Range labels are Today, 7 days, 30 days, 90 days, 12 months and All history. All history always carries its start ("All history, since {date}"). Add one plain line wherever older data shows. "Claude Code deletes transcripts after 30 days by default. The dashboard keeps its own usage record from {date}." Cost keeps "Estimated at API list price" on every figure. The tooltip keeps "What you pay depends on your plan". Whether output gets an "at least" label depends on the architect's finding. The privacy footer stays, and it must stay true now that a database keeps data. "Reload the page to update" becomes "Updated {time}".

Why:
- Presets and the 30-day default are an owner decision (20-decisions.md, round 3). 26-10-history-range.md recommends naming where All history starts.
- `cleanupPeriodDays` defaults to 30 (18-config-surfaces.md item 16, confirmed in 25-verifier-gap-research.md).
- `est_short` and `est_tip` (strings:437). `footer` promises "never message text" (strings:470). `read_at` says "Reload the page to update" (design audit U9).

Weigh in:
- Architect: 25-verifier-gap-research.md calls output a lower bound. 26-06-output-tokens.md found the final value in the fake harness. Which holds for the label? "At least $4.63" is a strong claim to put on every cost.
- Architect: confirm the database stores no message text, so the footer stays true.

## 9. Words and content

Position: One glossary file is the source for every term, and the strings use its labels only. Scope names follow the current settings docs and `/status`: Managed, Command line, Project local, Shared project, User and Plugin. Shell isn't a scope, so call it "Your shell". Each chip gets a second line taken from the docs' "Who it affects" column. Three app terms clash with Claude Code and must not appear on screen: "Surface" means CLI, VS Code or Desktop in Claude Code's glossary; "Rules" means `.claude/rules/` files; "Dispatch" is a phone task router.

So the app's resolver "rules" need a new name, and the Live page says "Started by" instead of "Dispatched by". Strings get length budgets for nav, chips and buttons, tested at 375 and 320.

Why:
- Settings docs name the scopes User, Shared project, Project local and Managed. `/status` lists "Project local settings". The precedence list adds "Command line" (https://code.claude.com/docs/en/settings.md).
- MCP docs say Local, Project and User for the same meanings (https://code.claude.com/docs/en/mcp.md). Memory docs say "Local instructions" (memory.md).
- The glossary defines Surface, Rules and Dispatch (https://code.claude.com/docs/en/glossary.md).
- Current strings use `nav_rules` "Rules reference", `why_rules` "Rules behind this value", `live_flow_h` and `live_flow_dispatched_by` (strings:633, 824, 547, 541).
- Nielsen heuristics 2 and 4.

Weigh in:
- Owner, through the panel: pick a name for the resolver rules. A "How Claude Code decides", with each item a "behavior". B "Precedence reference". C "Evidence". I recommend A.

Draft glossary (proposal, opinion where no source is given):

| Term on screen | Means | Matches Claude Code | Never say |
|---|---|---|---|
| Setup | Everything that shapes a session in one project | Opinion | surface, config surfaces |
| Scope | Where a thing is set and who it affects | settings.md "Each source has a scope" | layer (internal only) |
| Managed | Set by your organization | settings.md | enterprise, policy layer |
| Command line | `--settings` for one session | settings.md precedence list | CLI layer |
| Project local | Just you, this project (settings.local.json, CLAUDE.local.md, MCP local) | settings.md, `/status` | local settings, "This project, just you" as a label |
| Shared project | Everyone in this project (settings.json, CLAUDE.md, .mcp.json) | settings.md | project settings |
| User | You, every project | settings.md | user file, all your projects (as a label) |
| Plugin {name} | Comes from that plugin, read only | glossary Plugin | plugin layer |
| Your shell | An environment variable in the shell | settings.md "Environment variables aren't a level" | Shell scope |
| Agent | A subagent file, or the main session's helper | /agents, `.claude/agents/`; docs say "subagent" | dispatch |
| Main session | The session you started | Opinion | parent, root |
| Instructions | CLAUDE.md, CLAUDE.local.md, AGENTS.md, rules files | memory.md scope names | memory (that's auto memory) |
| Rules files | `.claude/rules/*.md` | glossary Rules | rules (for resolver rules) |
| In effect, Overridden, Ignored, Invalid, Lowered, Default, Unknown | The seven status words, one word each | "in effect", "overrides", "ignores" are docs verbs (settings.md) | Not known, didn't count |
| Applies now, in a new session, after restart, after /reload-plugins | When an edit takes effect | settings.md "When edits take effect" | This applies to a new session (for everything) |
| Estimated at API list price | Cost from token counts | Opinion, current copy | cost, spend (alone) |
| To fix | A judged problem with a fix | Owner decision | Needs attention, issues, errors |

## 10. UX standards check

Position: My part of the debate is the heuristics and success criteria that words decide.
- Nielsen 2 and 4: the plan meets them only if the glossary is enforced by a test, not by review.
- Nielsen 9: error copy already meets it, so port the pattern.
- Nielsen 10: add a Glossary page and one help link per page, in the same place (WCAG 3.2.6).
- WCAG 2.4.2: titles per route.
- WCAG 2.4.6: headings that describe. "Winner" and "Files read" need their subject.
- WCAG 2.5.3: the visible label must sit inside the accessible name. "Open the trail" sr text must start with those words.
- WCAG 3.3.2: each field states its allowed values, as `ed_compact_hint` does.
- WCAG 3.3.4: the risky confirm.

Why:
- 21-accessibility.md checklist, rows 2.4.2 and 3.2.6.
- Design audit A1 (titles are project-only) and U6 (the trail head says "Settings").
- `ed_compact_hint` reads "A whole number from 100,000 to 1,000,000, or Auto". It is a good model for every field editor.
- W3C WCAG 2.2 Understanding pages for 2.4.6, 2.5.3 and 3.3.2 are named standards. Not re-fetched this round.

Weigh in:
- Designer and architect: does the API return validation errors as codes the page maps to strings? It should never echo server text, since 26-07-read-gate.md shows the default 422 echoes input. WCAG 3.3.1 needs our words, not Pydantic's.

## 11. Testing

Position: Add content tests beside the code tests.
1. Keep the used-key and missing-key checks, adapted to typed t().
2. A style lint over strings that catches em dashes, "!", banned words ("surface", "layer", "dispatch", "seamless", "leverage"), Title Case headings and colons inside prose values.
3. A glossary test. Scope and status labels come from one map, and no string hardcodes them.
4. Length budgets per key family, checked by Playwright at 320 and 375.
5. Plural coverage, where every tn() key has one and other.
6. Page titles per route.
7. The rules reference's doc anchors, checked against the rendered HTML ids, as D-1534 already requires.

Why:
- Strings count only in literal t() calls (K-819f, project facts), so the current test must change with the typed t().
- D-1534 covers anchor checks against HTML ids (project facts).
- No string has an em dash today (grep of strings, November 8). The lint keeps it that way as copy grows past 823 keys.
- 21-accessibility.md has the title and reflow rows.

Weigh in:
- Senior developer: can the colon-in-prose lint tell a label ("Model") from a sentence? A fixed allowlist of label keys may be simpler than a heuristic.

## 12. Build order and coexistence

Position: Copy runs one step ahead of each build milestone. First a glossary and a copy deck for that milestone's screens, then design comps with real words, then the build. Design comps with lorem ipsum hide length problems the 375 width will expose. Port order follows the code. Usage strings move nearly as they are. The 84 rule reasons move as they are, renamed. Edit strings get rewritten as templates. The README "Dashboard" section and the plugin README get rewritten at cutover, not before. While both apps run, the new app's copy must not mention old flags.

Why:
- Owner routing says tech-writer drafts every word of copy in a design and runs at high effort for site copy (project CLAUDE.md "Design", Writer).
- The rule reasons live in rules.json and reference_copy.md, which feed reference_page.py (app-audit/architecture.md, line 58).
- README.md "Dashboard" still documents `--allow-edits` and three ranges.

Weigh in:
- Architect: how many milestones? I'd budget one copy deck per milestone and a glossary pass at the start, but I can't price them before the milestone list exists.

## 13. Open floor

Position: Three items nobody owns yet.
1. The product name. "Routing Dashboard" names the optional layer, while the core now reads anybody's setup. That's the owner's call, and I'd raise it before strings, titles and the slash command fix the name. Opinion.
2. First run. The first start downloads about 82 MB through uv. That screen and its failure ("Failed to download", connect and retry) need copy, and the user sees it before anything else.
3. The single-use code page. Its expired and already-used states need copy that never shows the key.

Why:
- 20-decisions.md has the optional routing layer, the spike 2 first run of about 82 MB and the "Failed to download" match, and round 3's single-use code swap.
- The skill tells Claude "Never print, guess or ask for an edit key" (plugins/routing-dashboard/skills/dashboard/SKILL.md).

Weigh in:
- Senior developer: what states does the code swap have (fresh, used, expired, wrong project)? I'll draft one line each.

## Top three concerns

1. Three app terms clash with Claude Code's own glossary. "Surface" means CLI, VS Code or Desktop. "Rules" means `.claude/rules/` files, which the rebuild now edits. "Dispatch" is a phone feature. If the plan's internal words reach the screen, people will read them in Claude Code's sense. The worst case is a Reference page called "Rules" sitting beside an editable Rules folder (https://code.claude.com/docs/en/glossary.md).
2. Scope names are already inconsistent, and the rebuild multiplies the surfaces. Today one file has three names across Settings, the trail and the cap copy. Claude Code's own docs use different names per surface. Without one enforced glossary, a dozen new pages will each pick their own.
3. The edit copy won't scale as written. 347 keys cover four settings. Extending that pattern to hooks, MCP, agents, skills and instructions would be unmaintainable. The registry has to supply names and effect phrases so a few templates can cover every surface. The risky confirm and the MCP handoff need words settled before design locks them.

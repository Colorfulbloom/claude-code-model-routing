# M5 build plan, Bar Tab Reference and help popovers

Written by the lead (deep-reasoner) on November 10, 2026, on branch `feature/bartab-m5` from `ccf37a3`, where M0 to M4 are committed. M4's CI was still running on `feature/bartab-m4` when this branch was cut. If it fails, the fixes land there and are merged in here before task 0. This plan turns plan-a.md section 5, "M5. Reference", into ordered tasks, and adds the help popovers the owner moved into M5 on November 10. The designer reviews sections 4, 5 and 6 before the UI build starts. Nothing is installed, started or committed until the owner says go.

Sources are plan-a.md (sections 2, 3, 4, 5, 6 and 10), m4-build.md (sections 2, 3, 10, 12, 13 and 18), the `a-decides` and `a-glossary` boards (round 4, `docs/design/redesign-a/a2.js` and the archive shots), components.md (entry 15 and the shared rules), the help sweep (`scratchpad/help-sweep/inventory.md`, 56 spots), tech-writer's help draft (`scratchpad/help-sweep/copy.md`, 56 entries), the designer's help spec and mock (`scratchpad/help-design/notes.md`, `site/help.js`, `help.css`, `help-entries.js`, `shots/`), the old `dashboard/rules.json`, `dashboard/api_settings.py` (`rules`, `_rule_record`, `version_field`), `dashboard/version.py` and `docs/rules-reference.md`, the M4 code in `app/`, and a scout inventory of the web strings run on November 10.

## 1. What M5 delivers

M5 gives the owner the two Reference pages and a way to ask "what does this mean" anywhere in the app.

How Claude Code decides lists the 84 rules Bar Tab applies, grouped by the setting they decide. Each rule says in one plain sentence what it decides, shows its confidence word (Tested, Documented or Assumed) and the Claude Code version it was checked on, and opens the docs line it quotes. A search field narrows the list as the owner types, a Confidence select filters it, and the number of matching rules is announced politely once typing settles. When the Claude Code the owner runs is newer than the version the rules were checked on, a notice says so at the top of the page, on Your setup, and on each inspector's Why line. The Your setup notice opens How Claude Code decides with only the rules checked on an older version, and the Why line opens its own rule.

The Glossary holds every term the app uses, typed once. The status words, the scopes and the confidence words come from shared lists that the help popovers, the chips and the glossary all read, so each definition exists in one place. Every term has its own route, so a link lands on it and focuses it.

Help popovers put a "?" on each tile, card and chart, and a dotted-underline term on column headers and inspector field labels, at all 56 spots from the sweep. Direction A is already picked. The popover is anchored to its spot at 721 px and up, and becomes a bottom tray at 720 px and under. Each entry says what the spot shows, what its numbers mean (with the values on screen beside their lines), how to read it, and links to its glossary terms. Entries sit in one registry keyed by id, next to the other strings, and a spot names only its id. Tests fail on a missing id, an unused entry and a dead glossary link.

A tile that opens a page keeps its link, but the link's name becomes the tile label alone, and the value is read after it. The "?" sits beside the link, never inside it.

Everything runs on fixtures and the demo build. Real data shows the same pages, and M5 reads no new file.

### Deferred, and why

| Item | Lands in | Why |
|---|---|---|
| The model catalog (12 models, aliases and effort levels) on How Claude Code decides | Later, after M9 | No board draws it, and the Models page already names each model. The catalog entries carry confidence and quotes, so they can join the page as one more group with no API change |
| Links to experiment records | M9 | The records sit in the old app's `dashboard/experiments/`, which the cutover moves. A link now would point at a path that changes. The page shows "Tested on 2.1.302, October 29" instead, which is what the owner needs to judge a rule |
| Search on setup lists | Not planned | M4 grouped long lists with Jump to chips instead (m4-build.md section 17, decision 5). The owner hasn't asked for search there |
| Help on edit screens | M6 to M8 | Each later milestone adds its own entries to the registry, and the unused-entry test keeps them honest |
| VoiceOver | M9 | Owner, November 9. M5 uses Playwright accessibility snapshots instead, as M4 did |
| Confidence badges on help lines | Not planned | Owner pick, November 10. Confidence belongs to rules, and the Why line already shows it |

### How the help popovers and the glossary connect

The glossary is the anchor for every help link. Each help entry lists one or two glossary term ids. The popover shows one link per term, named "{term} in the glossary", which goes to `#/reference/glossary/<term-id>`. The Glossary page scrolls the term into view under the sticky header and moves focus to it. A test fails when a help entry names a term id the glossary doesn't have.

The shared lists close the loop. The seven status words, the seven scope names and the three confidence words are each defined once, in `app/web/src/strings/lists.ts`. The status chip, the help entries that explain status words (`live.modelcheck`, `agents.check`, `setup.inspector.status`), the Glossary's Status words section and the How Claude Code decides intro all read that list. A change to one definition shows everywhere, and a test fails if any of those words is typed a second time.

The glossary link in a popover renders only when its term exists in the glossary registry. That is the "hidden until its route and anchor exist" rule, and in M5 both land together, so every link shows. Later milestones can add a help entry before its term, and the link simply waits.

## 2. Decisions this plan makes

The designer and owner can push back on any of them. Items that need an owner answer are in section 9.

| Item | Pick | Why |
|---|---|---|
| Rules source | `/api/rules` reads `app/server/data/rules.json`, which is byte-identical to the old `dashboard/rules.json` today (`cmp` on November 10). The answer carries codes and data, never English | plan-a section 3 says "text code". The page owns every word, as on every other M1 to M4 route |
| What a rule says on screen | One plain sentence per rule, written by tech-writer and typed in `en.ts` as `rl_<rule_id>`, plus a group name per setting key as `rg_<key>`. The rule's `reason` sentence is not shown on this page | The `reason` field explains a status for one item, with slots such as `{model}` and `{file}` (average 197 characters, longest 646). On a reference page those slots read badly. The board draws a short summary per rule. Section 9 asks the owner |
| Search | In the browser, over the words on screen | Section 3 gives the reasoning |
| Search state | The query lives in the URL as `?q=` with history replace, and the Confidence filter as `?confidence=`. A link can carry a search, and Back leaves the page rather than stepping through keystrokes | Usability lesson 14 (state follows the URL), and it lets the version-gap notice link to a filtered view |
| Version source | The Claude Code version of the newest session in the store (`store_provider._newest_claude_version`, already used for `/api/app`), and the demo's `session.json` in demo mode | It is the version that actually ran. The old app read the installed package's `package.json` by walking up from the binary (`dashboard/version.py`), which would be a new read outside the M4 roots. Section 9 asks the owner |
| Version gap | `GET /api/app` gains `rules_version_gap`, null or `{installed, checked_on}`. `checked_on` is the oldest `verified_on.claude_version` across the rules and `agent_fields.json`, as the old `version_field` does. The setup map gets a `version_gap` notice with the same params | plan-a section 3 lists `rules_version_gap` in `/api/app`. m4-build.md section 2 left the setup notice slot for M5 |
| Version-gap targets | The Your setup notice links to `#/reference/decides?due=1`, which shows only the rules checked on an older version. Each inspector Why line with a `reason.rule_id` links to `#/reference/decides/<rule_id>` and shows "Checked on 2.1.302" when that rule is due | "Follows the version-gap notice to the right rule". Today all 84 rules were checked on 2.1.302, so the filtered view is every rule, while the Why line names the one rule behind the item the owner is looking at |
| Rule and term routes | `#/reference/decides/<rule_id>` and `#/reference/glossary/<term-id>`, path segments as `setup/agents/<name>` uses. The page scrolls the target into view with the M0 scroll padding, focuses it, and marks it with the chosen-state start bar until another is picked | A hash router can't take a second `#`. Path segments already parse in `routes.ts` |
| Docs links | Each quote shows its docs line in a Disclosure, as the board draws, with a link to `doc_url` that opens in a new tab with `rel="noopener noreferrer"` | The access code sits in the fragment until it is swapped. Browsers never send fragments, but `noreferrer` also drops the local port and path |
| Docs anchors | A scout checks every `doc_url` anchor in rules.json against the rendered HTML ids before the page ships (fact D-1534). A dead anchor is listed for the owner, and the link still opens the page | 71 rules carry quotes. A reference page with dead links teaches distrust |
| Help registry | `app/web/src/strings/help.ts`, beside `en.ts`. Entries keyed by id, with title, shows, numbers (label, means, an optional value ref), reading, glossary term ids and an optional shared list (`status`, `scopes`, `confidence`, `project_state`). `HelpId` is the type of the registry's keys, so a spot naming an unknown id fails `tsc` | Owner, November 10. One file to update, and the compiler guards the ids |
| Glossary registry | `app/web/src/strings/glossary.ts`, terms keyed by id with term, meaning, group (status, scopes, confidence, terms) and optional see-also ids | plan-a section 3 says the glossary is static, built from the typed strings |
| Help component | `HelpButton` (the "?") and `HelpTerm` (the dotted-underline form) open `HelpPanel`, which is a React Aria `DialogTrigger` with a `Popover` above 720 px and a `Modal` tray at 720 px and under. No package is added | react-aria-components 1.22.1 already ships Dialog, Popover, Modal, SearchField and Disclosure (checked in `node_modules`, November 10) |
| Help placement | The designer's rules in `help-design/notes.md`. A full "?" on tiles, cards and charts. The term form on column headers and inspector field labels. Repeated status pills get none, and their column header carries the status words. A pill shown once per view gets the full "?" | Picked direction A |
| Agents at phone width | The Agents card "?" opens `agents.cols`, because Set to and Ran with are hidden at 375. The mock's extra `agents.table` id is not added | Main session pick on the owner's "your call", November 10. One entry, two triggers, so the unused-entry test still holds |
| Tile link | The link's accessible name is the label alone. The link is stretched over the tile with a pseudo-element, and the value, delta and note follow it in the DOM as plain text. The "?" is a sibling above the link layer | Main session pick, November 10. Today the link wraps the whole tile (`Tile.tsx:66-72`), so its name is every number on it, and a button can't sit inside a link. No page passes `href` yet, so only the component and the sheet change |
| Help values | A spot passes the values it shows (`values={{ value: "78%", delta: "81%" }}`), and the popover draws each beside its line. A column header passes `line` to mark its own line "This column", and a pill passes its word to mark it "This setting" | The designer's spec, so the popover explains the number the owner is looking at |
| String ownership | Only the lead edits `en.ts`, `help.ts`, `glossary.ts`, `lists.ts`, `models.py` and `conftest.py`, as in M4. Workers edit pages and components | Parallel workers never collide on the shared files |

## 3. Server

### `GET /api/rules`

One answer, fetched once per page load, with an etag over the file's bytes so a reload of the page costs nothing. It is not per project, because rules are global. The read key applies, as on every GET.

| Field | Type | Source |
|---|---|---|
| `server_time`, `etag`, `unchanged` | as every answer | |
| `installed` | string or null | The version source in section 2 |
| `checked_on` | string | Oldest `verified_on.claude_version` across rules and `agent_fields.json` |
| `rules[]` | list, sorted by `rule_id` | `rules.json` `rules` |
| `rules[].rule_id`, `key`, `scope`, `combine`, `layer_order` | strings and a list | As in the file. `key` and `scope` drive the page's groups and its scope filter |
| `rules[].confidence` | `tested`, `documented` or `assumed` | As in the file |
| `rules[].verified_on` | `{claude_version, date}` | As in the file |
| `rules[].due` | bool | True when `installed` parses and is newer than `verified_on.claude_version`, by the ported `version.older` |
| `rules[].quotes[]` | `{doc_url, quote}` | As in the file. The quote is verbatim docs text and is shown as text, never as HTML |
| `rules[].experiment` | string or null | The record's file name only, so the page can say a test exists. No link (section 1) |

The module is `app/server/rules_reference.py`, with the ported `version.parse`, `older` and `oldest` in `app/server/claude_version.py`. The router is `api_rules.py`, included in `main.py` beside the others. The OpenAPI export and `schema.d.ts` are regenerated.

### Version gap

`AppInfo.rules_version_gap` is `{installed, checked_on}` when `installed` parses and is newer than `checked_on`, else null. An unparsed or empty version is null, so the page shows no notice rather than a wrong one. `setup_codes.NOTICE_CODES` gains `version_gap`, and `setup_answers._notices` adds it with the same params when the gap is set. The closed-enum test makes the page side give it words.

The demo build's `session.json` reports 2.1.310 against rules checked on 2.1.302, so the demo always shows the gap. The fixture tests cover four cases, no version, an unparsable version, the same version and an older one.

### Search, server or client

Search runs in the browser. Four reasons decide it.

1. The words live on the page. The server sends codes, and the owner searches what he reads, which is the tech-writer's summary, the group name and the confidence word from `en.ts`. Only the browser has those.
2. The data is small. 84 rules with quotes come to about 52 KB of JSON, fetched once. Filtering that on each keystroke takes well under a frame.
3. No new input reaches the server. A server search would add a query parameter to parse on every keystroke, and a request per keystroke on a local server. The client filter adds nothing to the API surface.
4. It behaves the same in demo, fixture and real mode, and offline.

The match is plain text, with no fuzzy package. The query and the searchable text are lowercased and folded to NFKD with marks dropped, and the query splits on spaces. A rule matches when every query word is found in its text, which is the rule id, the setting key, the group name, the summary sentence, the confidence word, the version and its quotes. The visible count says how many rules match. The Glossary uses the same function over each term and its meaning.

### Differential against the old `/api/rules`

The recorder gains `--only rules`. It calls the old `api_settings.rules(ctx, {})` in process through `server.fixture_context` twice, once on the demo build (installed 2.1.310 from `session.json`) and once with no version, and writes both answers under `app/fixtures/oracle/rules/` with the manifest's old commit sha. Two runs give the same bytes.

`test_differential_rules.py` compares the new answer with the old one per rule. Rule ids and their order, `confidence`, `verified_on`, `due` and `quotes` must match. The allowed differences, each with a pinned count, are these.

- `reason-not-sent`. The old answer carries `reason`, and the new one sends no English (84).
- `no-repo-links`. The old answer carries `reference_url` and `experiment_url` to GitHub, and the new one carries the experiment file name only (84 and 53).
- `installed-source`. The old answer's `installed` can come from the binary, and the new one from the store. On fixtures both read `session.json`, so the count is 0, and the entry exists to say why.

A second test, `test_rules_file.py`, reads `rules.json` directly and checks the answer against the file, with no hard-coded count. Every rule appears once, `checked_on` is the oldest version in the file, and `due` follows `version.older`. Fact R-06c2 covers only the old app's files, and M5 changes none of them.

On the web side, `rules-words.test.ts` reads `app/server/data/rules.json` from disk and fails when a `rule_id` has no `rl_` sentence or a `key` has no `rg_` group name, and when `en.ts` holds an `rl_` or `rg_` key the file no longer has.

## 4. Web

### How Claude Code decides

Route `#/reference/decides`, with `?q=`, `?confidence=`, `?due=1` and the `/<rule_id>` segment. The layout follows `a-decides` in the canonical look once pass 13 redraws it.

- The page header, then the version-gap notice when `rules_version_gap` is set, with the Unknown chip, the two versions and a "Show these rules" link to `?due=1`.
- One row with the search field and the Confidence select (All, Tested, Documented, Assumed, each with its count).
- One card per setting key, in a fixed order the copy deck gives, with its count. Empty groups hide while searching.
- One row per rule. The rule id in mono, the confidence badge, "Checked on 2.1.302" with a due mark when due, the summary sentence, and a Disclosure "Show the line from the docs" holding each quote and its docs link.
- An empty search state with the query, a "Clear search" button and a pointer to the Glossary.
- Loading bones, a card error and the M0 lost gate, as every page has.

### Glossary

Route `#/reference/glossary`, with `?q=` and the `/<term-id>` segment. Sections follow `a-glossary`. Status words, Scopes and Confidence words come from `lists.ts`, then Terms in alphabetical order. Each term is a `dt` and `dd` pair inside the section, and a term's `dt` carries the id the route targets. The same search field sits at the top. The page has no API call, so it never shows loading or an error.

### The search field

A `SearchField` from React Aria Components (components.md entry 15), built once in `app/web/src/components/SearchField/` and placed on both pages.

- A visible label ("Search rules", "Search the glossary") and a clear button that keeps a 24 px target.
- The visible count sits beside the field ("12 of 84 rules"). It is plain text, not a live region.
- One separate `role="status"` region, visually hidden, announces the count politely. It updates 600 ms after the last keystroke, only when the count or the query changed, and never on page load or on a route change. "No rules match {query}" when nothing matches.
- Esc clears the field and keeps focus in it, as React Aria does. Enter does nothing.
- Matches are marked with `<mark>` built by splitting text, never by setting HTML.

### The help component and registry

| Part | Path | Notes |
|---|---|---|
| Registry | `app/web/src/strings/help.ts` | 56 entries keyed by id. Typed by the lead from the cleaned deck (task 2) |
| Shared lists | `app/web/src/strings/lists.ts` | Status words, scopes, confidence words, project states. Each item is a key into `en.ts`, so the words exist once |
| Glossary | `app/web/src/strings/glossary.ts` | Terms keyed by id. Typed by the lead from the deck |
| Trigger | `app/web/src/components/Help/HelpButton.tsx` | The "?" as a 24 px circle with a 32 px hit area. Name "About {title}", `aria-expanded`, `aria-haspopup="dialog"` |
| Term trigger | `app/web/src/components/Help/HelpTerm.tsx` | A button styled as the header or label text with a dotted underline. In a `th` it stays the header's only content, so the column name is still the header's name |
| Panel | `app/web/src/components/Help/HelpPanel.tsx`, `Help.css` | `DialogTrigger` with `Popover` (placement bottom, flip, offset 8) above 720 px, and `Modal` as a bottom tray with a Close button at 720 px and under. The heading is the entry title as h2. Focus moves into the dialog on open and back to the trigger on close. Esc and an outside click close it. Reduced motion drops the tray slide. Forced colours keep the border, the "?" ring and the underline |
| Entry body | `app/web/src/components/Help/HelpEntry.tsx` | Shows, the numbers as a description list with values beside their lines, a shared list when the entry names one, reading, and the glossary links. Section labels come from `en.ts` |

The guard tests live in `app/web/src/strings/help.test.ts`.

1. Missing id. `HelpId` is `keyof typeof HELP`, so `tsc` fails on an unknown id. The test also scans `src/**/*.tsx` for literal `help="..."` and `helpId="..."` props, and fails on an id the registry lacks, which catches a cast.
2. Unused entry. Every registry id is named by at least one literal prop in the source. Ids must be literals, never built from strings (fact K-819f).
3. Dead glossary link. Every term id an entry names exists in `glossary.ts`, and every term id resolves to a rendered anchor on the Glossary page (a Vitest render).
4. Shared lists once. No status word, scope name or confidence word definition is typed outside `lists.ts` and its `en.ts` keys. The test reads `en.ts` and fails on a second key holding the same definition text.
5. Shape. Every entry has a title and shows or numbers. No entry text carries a colon in prose, an em dash or bold, as the string lint already checks for `en.ts`.

### The Tile link change

No page passes `href` to a Tile today. Only the sheet's `link` state does (`sheet/manifest.tsx:966-974`), so the change lives in the component and the sheet, and no page's link name moves.

`Tile` gains a `help` prop (id and values), drawn as the "?" at the end of the label row. With `href`, the label sits inside a `Link` and the rest outside it. The link gets `::after` stretched over the tile, so the whole tile stays clickable. The value, delta, note and proof follow in DOM order. The "?" is a sibling with a higher stacking layer. Focus shows on the whole tile through `:has(:focus-visible)` on the tile itself, not nested (fact K-6860), and the forced-colours check covers it. Tests assert the link's accessible name equals the label, Tab reaches the link and then the "?", and a click on the value still opens the page.

The help triggers do change Tab order and accessibility snapshots on every page that gains them. Task 12 updates those M2 to M4 specs, and the lead reviews each changed line.

### Routes and notices

Two gaps the scout found need edits beyond the pages.

- `parseRoute` takes exactly two segments after `reference`, and the router's `*` route sends anything else to `/` (`app/routes.ts:84-90`, `app/router.tsx`). Task 11 adds the rule and term segments to both and keeps `project: null`, because `App.tsx`, `Shell.tsx` and `GatePages.tsx` read `parseRoute` for project swaps. The focus rule follows the surface pages' (`router.tsx:56`), so a route with a term focuses the term, and a plain page load focuses the h1.
- Nothing on the page reads `SetupMap.notices` today. Your setup shows its one notice from `answer.listed` (`pages/setup/YourSetupPage.tsx:49-62`, `:101`). Task 11 renders `notices[]` through `NoticeLine`, which the sheet already draws for a version notice (`sheet/manifest.tsx:576-583`), and keeps the unlisted notice as it is, so it never shows twice.
- A precedent for the popover exists. `pages/live/SessionSelect.tsx:57-90` already uses `DialogTrigger`, `Popover` and `Dialog` with a heading slot and a close button.

### Strings the help entries replace

The rule I apply is that help adds and removes little. An on-screen string goes only when it repeats what its help entry says and carries no data, no legend for a mark on screen, no instruction, and no accessible description. Touch readers, screen reader users and a glance at a card all lose something when an explanation moves behind a "?". Section 9 asks the owner, with the wider cut as option B. The scout map from November 10 is the source, with path:line for each key.

Deleted, each once, in the task that wires its spot.

| Key | Text today | Render site | Help id | Why it goes |
|---|---|---|---|---|
| `rq_f_est` | "Costs are estimates at API list prices, not your bill." | `pages/live/RequestsCard.tsx:59` | `live.requests` | Same sentence as `foot_est`, in other words. The Requests foot uses `foot_est`, so the app says it one way |
| `rq_f_sub` | "On a subscription you pay a flat fee, so this is what the same use costs on the API." | `RequestsCard.tsx:60` | `live.spent` | The one subscription sentence lives in the Spent so far entry, the only place the draft already has it. `live.requests` points to it rather than repeating it |
| `rv_chk_q` | "Did each agent run on the model and effort it's set to?" | `pages/review/SummaryCards.tsx:77`, `:87`, `:95` | `summary.modelcheck` | Identical to `mc_q`. Summary uses `mc_q`, so one key holds the question |
| `nr_outside_scope` | Same sentence as `ins_imp_not_read` | Its sites in `pages/setup/InspectorFacts.tsx` | `setup.imports` | Two keys with one sentence. One stays |

Kept on screen, with the help entry saying the same thing in more depth.

| Key | Help id | Why it stays |
|---|---|---|
| Card questions (`tl_q`, `mc_q`, `rq_q`, `rv_who_q`, `ch_q`, `ag_q`, `md_q`, `md_kind_q`, `su_card_q`, `fx_q_*`) | Their cards | One question per card is the Card contract (components.md entry 5). `fx_q_cant_tell` and `fx_q_notice` are the only on-screen reason those groups aren't counted |
| `tl_note` | `live.who` | The legend for indented rows, the dashed starter line and bars that reach Now. A mark on screen needs its legend in view. The entry gains the two lines the draft lacks |
| `kind_legend_note` | `models.chart` | Patterns are kinds, colours are models. The owner's contrast exception for `--rk-1` and `--rk-2` holds only while legends stay. `models.chart` and `summary.costchart` gain the line |
| `runs_def` | `sessions.cols`, `agents.cols` | The owner kept a visible note under both tables in M4 (m4-build.md section 18, task 21) |
| `foot_est` | `summary.costchart` | The honest "estimate, not your bill" line and the price date, once per page. Tests pin one per page |
| `ss_before_aria`, `ag_chk_unchecked_aria`, `ag_src_unknown_aria` | `sessions.before`, `agents.unchecked`, `agents.source` | Screen reader descriptions. Removing them would make a screen reader user open a popover to learn what a sighted user sees at once |
| `ag_ignored_b`, `in_shell_note`, `cr_b`, `cr_fix`, `ch_scope_note`, `ch_unpriced_*`, `t_avg_cache*`, `sr_note`, `pk_st_*_d`, `su_unlisted`, `pm_why`, `in_conf_*` | Their spots | Each carries data, sits beside its cause (usability lesson 16), or is an instruction |
| `t_cost_kx` ("API-rate estimate") | `live.spent` | The tag that keeps a dollar figure honest |

The shared lists come from keys that exist. `lists.ts` points the seven status words at `status_*` (`en.ts:376-382`) for the word and at the seven general `rs_*` Why lines (`en.ts:1164-1171`) for the meaning, so the Why line on an item and the definition in help and the Glossary are one string. The scopes point at `sc_*` and `sc_*_2` (`en.ts:681-695`). Task 2 rewords those keys where the four copies in the draft disagree, and adds definitions only for the confidence words and project states, which have none today.

The cost chart's popover title is the card title, from `ch_h_hour`, `ch_h_day`, `ch_h_week` or `ch_h_month` by the unit the answer gives (`lib/review-cards.ts:54-65`). The entry carries the four title variants, and the spot passes its unit. The entry says how All picks its unit, day up to 31 days, week up to 13 weeks, else month (`app/server/review_windows.py:222-237`).

Deleted exactly once is provable, because task 8 adds the test `app/web` lacks. Today nothing fails when an `en.ts` key loses its last caller (scout, November 10). `unused-keys.test.ts` scans `src/**/*.{ts,tsx}` for literal `t("key"` and `tn("key"` calls and fails on a key no call names. The registry-driven families that `setup-codes.test.ts` already guards (`rs_`, `pc_`, `ro_`, `sl_`, `hk_ev_`, `cr_r_`, `fx_cant_`, plus `rl_` and `rg_`) are exempt by prefix, and keys named in `lists.ts` and `help.ts` count as used. The first run will list keys that are already orphaned, and the lead removes them in task 8 and lists them in the report.

`help.ts` and `glossary.ts` keep labels and meanings in separate fields, because the string lint bans colons in every value (`strings/lint.test.ts:53`), and the draft's "Label: text" lines can't be stored as written. Guard test 5 runs the same lint over both files.

## 5. Design passes the main session dispatches

Help direction A is picked, and the designer's spec and mock layer are the build reference. No new help board is needed.

### Pass 13, the two Reference pages in the canonical look

`a-decides` and `a-glossary` are round 4 boards in the pre-canonical look, with mock rules. Pass 13 redraws both at 1440 and 375, light and dark.

- How Claude Code decides with real rule ids and the group order, the confidence badge and the due mark, the open Disclosure with a long quote, the version-gap notice, the search field with a query and its count, the Confidence select open, no results, and a rule reached by its route with the start bar.
- Glossary with all four sections, a term reached by its route, a search with results and with none, and a long term.
- Help on both pages. Whether the Reference pages get their own "?" spots (the sweep has none), and how a glossary term reached from a help link reads.
- The Your setup notice row for the version gap, and the inspector Why line with its rule link and "Checked on".
- The draft labels from `help-design/notes.md` ("The numbers", "What you see", "The status words", "Reading it", "This column", "This setting", "More in the glossary") go to tech-writer in task 2.

### Designer review of this plan, at medium

Its one question is how well this plan serves the picked help direction and the pass 13 pages. Focus areas are in section 11.

## 6. Copy tasks for tech-writer

All at medium. Each returns a key table that the lead types into `en.ts`, `help.ts`, `glossary.ts` and `lists.ts`.

| Task | What | Waits for |
|---|---|---|
| 2, help cleanup and labels | Start from `help-sweep/copy.md`. One shared status-word list, one scope list and one confidence list, each entry pointing to them instead of repeating them. No duplicate subscription sentence. The cost chart title matches its on-screen label, with variants per range unit (hour, day, week, month). The designer's draft section labels. Latest requests Time reads "logged". Stale lines fixed against the M4 code. Runs include the main session on every page (`app/server/review_query.py:12-14`, `runs_def`), so `sessions.cols` and `agents.cols` are wrong today, and k never exceeds n on Summary's Model check. `live.who` gains the indented-row and Now lines from `tl_note`, `models.chart` and `summary.costchart` gain "patterns are kinds, colours are models", and the cost chart entry names the All cut (31 days, 13 weeks). `live.spent` keeps the subscription sentence and `live.requests` points to it. Labels and meanings stay in separate fields, because the lint bans colons. The kept and deleted lists in section 4 | The scout map (done) |
| 2, glossary | One entry per term the help entries name (42 distinct terms in the draft), plus Started by from the board and every term pass 13 adds. Term, meaning in one or two sentences, group and see-also. The status words, scopes and confidence words are written once, for `lists.ts` | Same dispatch as the help cleanup, because the terms anchor the help links |
| 3, rule sentences | One plain sentence per rule for the 84 rules in `rules.json` (`rl_<rule_id>`), checked against the rule's conditions and quotes. A group name per setting key (17 keys, `rg_<key>`) and the group order. Any rule tech-writer can't word from the file is marked [NEEDS CONFIRMATION] | Nothing. It runs beside the server tasks |
| 4, reference page words | Page titles and intros, the version-gap notice in its three places, the search labels, the count and its announcement with plural forms, the empty search state, the Confidence select, "Checked on", the due mark, the Disclosure label, the glossary section headings | The owner's pick on pass 13 |

## 7. Ordered tasks

Tiers follow the owner's routing rules. fast-worker runs at medium unless the row says high. Every brief starts with `Kind: rebuild-m5`, carries the HiveMind line from `hivemind_lib.py related <paths>`, the date rule (`date -Iseconds` only) and these limits. Work only in `/Volumes/Warehouse/Projects/claude-code-model-routing-bartab`. Never read anything under `~/.claude`, real transcripts, real settings or `~/.claude.json`. Never pass `--real` to anything, and never run the launcher. Servers only on ports 47000 to 47999. Never print, guess or ask for a key. Use `app/scripts/uvw` and `app/scripts/npmw` for every uv and npm call, and download nothing. Never edit `dashboard/`, `tests/`, `plugins/`, `tools/`, `hooks/`, `agents/`, `rules/`, `skills/` or `install.py`. Write scripts with Write and run one plain command per call, because the guard refuses heredocs and generated command text. Keep the literal text `.claude.json` and the launcher's file name out of Bash commands. A worker doing visual or CSS work views its own screenshots with Read before it reports, and doesn't rely on computed pixels alone. Run the narrow spec first, and leave the full matrix to task 13.

HiveMind ids for briefs: T-7629, T-5589, T-c826, T-3ad1, D-c684, D-3ca7, D-1534, K-6860, K-819f, W-7178, R-06c2, plus the M4 list (R-7c9c, J-b0ae, J-c864, J-f0a7) and whatever `related` returns per task. `related` resolves to the main checkout's store, which doesn't know `app/` paths yet, so expect few hits.

| # | Task | Files | Agent and tier | Needs | Check | Cost |
|---|---|---|---|---|---|---|
| 0 | Pre-flight. Time, branch, clean tree, M4 CI fixes merged if any. Write the contract. The Rules models and `AppInfo.rules_version_gap` in `models.py`, the `HelpEntry`, `GlossaryTerm` and list types with the 56 ids as empty stubs, and the `lists.ts` skeleton | `app/server/models.py`, `app/web/src/strings/{help,glossary,lists}.ts` | Lead | None | Models import, OpenAPI export runs, `tsc` passes | In the lead row |
| 1 | Docs anchors. Check every `doc_url` in `rules.json` against the rendered HTML ids (D-1534), with a custom User-Agent | None. A list of rule id, URL and ok or dead | scout | None | Every URL is listed | $2 to $4 |
| 2 | Help cleanup, labels and glossary deck (section 6) | Scratchpad deck, typed by the lead | tech-writer medium | 0 | String lint passes after typing. Owner reads the deck | $8 to $13 |
| 3 | Rule sentences and group names (section 6) | Scratchpad deck, typed by the lead | tech-writer medium | 0 | `rules-words.test.ts` passes after typing | $6 to $10 |
| 4 | `/api/rules`, the version gap in `/api/app` and the setup notice, the ported version helpers, OpenAPI and `schema.d.ts` | `app/server/{rules_reference,claude_version,api_rules,main,setup_codes,setup_answers,store_provider,fixture_provider}.py`, tests, `app/web/src/api/openapi.json`, `schema.d.ts` | fast-worker | 0 | TestClient on demo and fixtures, the four version cases, etag and `unchanged`, closed-enum test on the server side, pyright strict, coverage 85 percent | $6 to $10 |
| 5 | Old `/api/rules` recorder and the differential, plus `test_rules_file.py` | `app/oracle/record.py`, `app/fixtures/oracle/rules/**`, `app/server/tests/test_differential_rules.py`, `test_rules_file.py` | fast-worker | 4 | Section 3 passes outside the allowed list. Two recorder runs give the same bytes | $5 to $8 |
| 6 | Designer pass 13 and the plan review at medium (main session dispatch) | Boards in the archive | designer | None | Owner picks before tasks 11 and 3b | $14 to $24 |
| 7 | Components (high). `HelpButton`, `HelpTerm`, `HelpPanel` with popover and tray, `HelpEntry`, `SearchField` with the count and the status region, the Tile link change, all on the sheet with every state | `app/web/src/components/{Help,SearchField,Tile}/*`, `app/web/src/sheet/*`, tests | fast-worker high | 0 | Vitest. The sheet test with axe at 375 and 1440, light and dark, forced colours and reduced motion. Focus returns to the trigger. The worker views the sheet shots | $12 to $18 |
| 8 | Registry guards. The five tests in section 4, `unused-keys.test.ts`, `rules-words.test.ts`, and the data layer for `/api/rules` with its query hook. The orphaned keys the first unused-key run finds go to the lead | `app/web/src/strings/{help,unused-keys,rules-words}.test.ts`, `app/web/src/api/rules.ts` | fast-worker | 0, 4 | Each test fails on a planted fault and passes after | $5 to $8 |
| 9 | Help spots, part 1. Live, Session review, Summary and the shell (28 spots), with the replaced strings deleted at their render sites | `app/web/src/pages/live/*`, `pages/review/{Replay*,SessionReview*,Summary*,CostChart*}`, `app/Shell.tsx`, `components/{SidebarFooter,ProjectPicker,ScopeBar}/*`, `pages/MorePage.tsx`, tests | fast-worker | 2 typed, 7, 8 | Vitest. The narrow e2e specs for those pages with axe at 375 and 1440. The worker views its shots | $9 to $14 |
| 10 | Help spots, part 2. Sessions, Agents, Models, Your setup and To fix (28 spots), with the replaced strings deleted | `app/web/src/pages/review/{Sessions*,Agents*,Agent*,Models*}`, `pages/setup/*`, `components/{ListInspector,ToFixRow}/*`, tests | fast-worker | 2 typed, 7, 8 | As task 9 | $9 to $14 |
| 11 | Reference pages (high). How Claude Code decides with search, the Confidence select, the gap notice, rule routes and the Disclosure. Glossary with search and term routes. The Your setup notice link and the Why line link with "Checked on". The route segments and the `notices[]` render in section 4 | `app/web/src/pages/reference/*`, `app/router.tsx`, `app/routes.ts`, `app/nav.ts`, `pages/setup/{YourSetupPage,ItemInspector}.tsx`, tests, `app/web/e2e/reference.spec.ts` | fast-worker high | 3 and 3b typed, 6 picked, 7, 8 | Vitest. `reference.spec.ts` with axe at 320, 375 and 1440, light and dark, forced colours and reduced motion | $12 to $18 |
| 3b | Reference page words (section 6, task 4) | Scratchpad deck | tech-writer medium | 6 picked | Typed by the lead | $2 to $4 |
| 12 | M5 end to end. The keyboard walkthroughs and accessibility snapshots in section 10, and the M2 to M4 snapshot and accessible-text updates the Tile change and the help triggers cause | `app/web/e2e/{reference-keyboard,help-keyboard}.spec.ts`, `e2e/a11y.ts`, the M2 to M4 specs whose Tab order or snapshots move | fast-worker | 9, 10, 11 | All pass three runs in a row | $8 to $12 |
| 13 | Exit runs. T2 suite, the full Playwright and axe matrix, the old suite alone with its log named for `feature-bartab-m5` (T-7629), the protected-path diff | Logs in the scratchpad | scout | 12 | All green. The diff is empty | $2 to $3 |
| 14 | Browser check in Chrome under the tab-group rules. Both Reference pages, five help popovers and one tray, and the tiles, at 1440 and 375, light and dark, against pass 13 and the help shots | None. A difference list | judge | 13 | Differences fixed in one batch, or listed for the owner | $4 to $7 |
| 15 | One fix round from tasks 13 and 14, a second only for Linux CI failures, consolidation after the merge, and the report. The main session dispatches the verifier | None | Lead and fast-worker | 13, 14 | Report written | $10 to $16 |

The lead's own share (task 0, every review, typing `en.ts`, `help.ts`, `glossary.ts` and `lists.ts`, the fix briefs and the report) is $25 to $40.

Order and parallel work. One lead at a time in this worktree, and the designer's pass touches no file in `app/`. Task 0 runs first. Then 1, 2, 3, 4 and 7 start together, because they touch separate files or none. Task 5 needs 4. Task 8 needs 4 for the rules hook. Tasks 9 and 10 need the typed deck from 2, plus 7 and 8, and run together because they touch separate page folders. The lead merges shared CSS and the sheet manifest between them. Task 6 runs beside all of that as the main session's dispatch, then 3b. Task 11 needs the pick, 3 and 3b typed, 7 and 8. Task 12 needs 9 to 11. Then 13, 14 and 15. M5 adds no package.

## 8. Cost estimate

List-price ranges. plan-a put M5 at $10 to $20 before the help popovers joined it. M4 planned $171 to $270 for its build and came to about $380, after the owner approved about $130 past the $250 stop line (m4-build.md section 18). M5's server side is small, but the help work touches every page built so far. I have no per-run cost from the dashboard in this tree. [NEEDS CONFIRMATION: dashboard cost per run for each agent.]

| Dispatch | Count | Estimate |
|---|---|---|
| This plan step, lead and one scout | 1 | $8 to $12 |
| Lead build, reviews, typing four string files, fix briefs and the report, deep-reasoner on Opus at high | 1 | $25 to $40 |
| fast-worker at high, tasks 7 and 11 | 2 | $24 to $36 |
| fast-worker at medium, tasks 4, 5, 8, 9, 10, 12 and the fix round | 7 | $48 to $74 |
| scout, tasks 1 and 13 | 2 | $4 to $7 |
| judge, task 14 in Chrome | 1 | $4 to $7 |
| tech-writer at medium, tasks 2, 3 and 3b | 3 | $16 to $27 |
| Build only, after this plan step | | $121 to $191 |
| Designer pass 13 and the plan review at medium (main session) | 2 | $14 to $24 |
| Verifier on Opus (main session) | 1 | $5 to $10 |
| Total for M5 | | $148 to $237 |

What drives the cost.
- The help spots. 56 controls across about twenty files, each with its values, and the strings they replace. Tasks 9, 10 and 12 are about a third of the build.
- Snapshot churn. The Tile change and every new "?" alter accessible names and Tab order that M2 to M4 specs assert.
- Copy. Three decks, with 84 rule sentences checked against conditions and quotes, and about 50 glossary terms.

Where it could overrun.
1. Popover focus and the tray switch at 720 px. A Popover that turns into a Modal mid-resize needs care. Task 7 runs at high for it.
2. Stretched links. The Tile's `::after` layer can swallow clicks meant for the "?", or lose focus visibility in forced colours. The sheet test and screenshots catch it.
3. Linux CI. M2 to M4 all needed fix commits after the build. The second fix round in task 15 is priced for it.
4. Late board changes. Pass 13 is one pass for two simple pages, so the risk is lower than M4's.

Stop line. The lead stops and reports before starting the next task once build spend passes $175.

The split option in section 9, question 8, costs about the same in all, and moves tasks 7 to 10 and part of 12 into their own PR.

## 9. Owner decisions

Each is judged on one test, the owner's. If this shipped to production tomorrow, is it the best choice for usability and security? My pick is first.

1. Design pass 13 for the Reference pages.
   - A (my pick). The main session dispatches pass 13 now, with the plan review at medium. Tasks 0 to 5, 7 and 8 run beside it. The boards are round 4 with mock rules, and the canonical look has moved since.
   - B. Build from the round 4 boards and fix after a later pass. The pages get built twice.
2. What each rule says on screen.
   - A (my pick). One plain sentence per rule from tech-writer, typed in `en.ts`, with a test that every rule in `rules.json` has one. Best for reading, and it keeps English off the API.
   - B. Show the rule's `reason` sentence with its slots filled by generic words ("the model", "the file"). No copy task, but sentences run up to 646 characters and read as explanations of one item, not as rules.
   - C. Rule id, key and confidence only, with the docs quote. Fastest, but the owner has to read every quote to learn what a rule does.
3. Search.
   - A (my pick). In the browser, over the words on screen (section 3). No new input reaches the server, and it searches what the owner reads.
   - B. On the server, with `?q=` on `/api/rules`. It could only search rule ids, keys and quotes, because the words live on the page.
4. Which Claude Code version counts as installed.
   - A (my pick). The version of the newest session in the store. It is what actually ran, and Bar Tab reads nothing new.
   - B. The installed package, found by walking up from the `claude` binary, as the old app did. It is current before the next session starts, but it adds reads outside the M4 roots and runs a path search.
   - C. Both, preferring the package. The most current, with B's new reads.
5. Where the version-gap notice leads.
   - A (my pick). The Your setup notice opens How Claude Code decides filtered to rules checked on an older version, and each inspector Why line links to its own rule with "Checked on".
   - B. The notice opens the page at the top, with no filter and no Why line link.
6. Search on the Glossary too.
   - A (my pick). Yes. About 50 terms, the same component and the same count announcement, at little extra cost.
   - B. How Claude Code decides only, as the board draws.
7. Which on-screen strings the help replaces.
   - A (my pick). Help adds and removes little. Only the four pure duplicates in section 4 go, and legends, card questions, the visible runs note, the estimate foot and every screen reader description stay. Nobody has to open a popover to read what a mark means, and a screen reader user hears what a sighted user sees.
   - B. The wider cut. Also remove `tl_note`, `kind_legend_note`, `runs_def`, `ss_before_aria`, `ag_chk_unchecked_aria` and `ag_src_unknown_aria`. Cards get quieter, but legends move behind a "?", the owner's `--rk` contrast exception loses the legend it depends on, and M4's visible runs note goes back on an owner call.
8. How M5 ships.
   - A (my pick). One milestone and one PR, as planned, $121 to $191 for the build with the stop at $175.
   - B. Two PRs in order. M5a is the Reference pages and the server, about $55 to $90. M5b is the help popovers and the Tile change, about $75 to $115. Each review is smaller, but the shared lists and the glossary anchors land in M5a first, and the total rises by one more fix round and exit run.

## 10. Tests and exit

### New suites

| Area | Tests |
|---|---|
| Rules API | Each field on demo and fixtures. The four version cases. Etag and `unchanged`. The read key. No English in the answer |
| Differential | Section 3, both recordings, outside the allowed list |
| Rules file | `test_rules_file.py` and `rules-words.test.ts`, both reading `rules.json` directly |
| Version gap | `/api/app` and the setup notice for the four cases. The closed-enum test on both sides |
| Registry | The five guard tests in section 4 |
| Search | Vitest for the match function (case, accents, several words, quotes, empty query). The status region updates once per settled query, never on load |
| Help | Vitest for each trigger and the panel. Opening, the values beside their lines, "This column" and "This setting", the shared list, the glossary links, Esc and outside click, focus return. The tray at 720 px and under |
| Tile | The link name is the label alone. Tab order is link then "?". A click on the value opens the page |
| Web pages | Playwright with axe on both Reference pages, and on each page that gained help with one popover open, at 320, 375 and 1440, light and dark, forced colours and reduced motion |

### Keyboard walkthroughs

Playwright with the keyboard only, at 375 and 1440. Each step asserts focus and the visible text.

1. Search. Tab from the page header to the search field, type a query, and the visible count changes. One polite announcement arrives after typing settles, counted as M2 counts them. Esc clears, and the count returns to all. Tab reaches the Confidence select, which narrows the list. Tab reaches a rule's Disclosure, Enter opens the docs line, and its link is next.
2. Help popovers. On Live, Tab to a tile's "?" and Enter opens the popover with focus inside it. Tab walks its links. Esc closes it, and focus is back on the "?". The same on a column header term on Agents and on the inspector pill on Your setup. At 375 the tray opens with focus inside, Tab stays inside it, and Close returns focus.
3. Glossary from help. Open a popover, follow "{term} in the glossary", and focus lands on that term on the Glossary page. Back returns to the page with focus on its h1.
4. Version gap. On Your setup, Tab to the version-gap notice link, which opens How Claude Code decides filtered to rules checked on an older version, with the count. From an inspector Why line, the rule link lands on that rule with focus and the start bar.

### Accessibility snapshots

Task 12 takes Playwright accessibility snapshots of How Claude Code decides with a search, a rule reached by route, the Glossary with a term reached by route, an open popover, the tray, a tile with its "?", and the Your setup notice row. They gate like any test, and M9's VoiceOver script reuses the list.

### Kept green

- The M0 to M4 exit runs, with pytest, Vitest and Playwright counts in the report.
- Standards checks. ruff, ruff format, pyright strict, coverage at 85 percent on `app/server`, tsc, ESLint, Stylelint and Prettier.
- The old suite alone, `/usr/bin/python3 -m unittest discover -s tests` from the worktree root, log named for `feature-bartab-m5` (T-7629). Expected 3575 tests and 88 skipped.
- `git diff --stat ccf37a3 -- dashboard tests plugins tools hooks agents rules skills install.py` stays empty.

### Exit, from plan-a M5 and the help scope

- The differential against the old `/api/rules` passes outside the allowed list, and the rules-file tests read `rules.json` directly.
- Axe is clean on both Reference pages and on every page with help, with a popover open, at 320, 375 and 1440, light and dark.
- The search result count is announced politely, once per settled query.
- The four keyboard walkthroughs pass at 375 and 1440.
- Forced colours keep the "?", the term underline, the popover border, the tile focus and the rule start bar visible. Reduced motion drops the tray slide.
- The registry tests fail on a missing id, an unused entry, a dead glossary link and a repeated shared word.
- Every string the help replaced is deleted exactly once.

## 11. Designer review focus

- Section 4's help placement per spot, especially the status pills that get no "?" and where `live.status`, `review.status` and `shell.projectstate` land.
- Whether `HelpEntry` carries everything the popover draws, values and line marks included.
- The tray at 720 px and under, its Close button and its focus.
- The Tile link change, and whether the stretched link and the "?" read right at both widths.
- One link per glossary term against the mock's single "More in the glossary".
- The Reference pages' states in section 4 against pass 13, and the start bar on a rule or term reached by route.
- The search count beside the field and the separate announcement.
- The version-gap notice in its three places.

## 12. Risks and leftovers

### Leftovers M5 depends on

1. The setup notice slot exists and waits for `version_gap` (m4-build.md section 2). Task 4 fills it.
2. Real mode's `claude_version` was empty when M4's plan was written (m4-build.md section 13, item 9). M4 now fills it from the newest session (`store_provider.py:1066`), so this leftover is closed.
3. The search field (component 15) was deferred from M4 to here (m4-build.md section 2).
4. `#/reference/decides` and `#/reference/glossary` exist in `router.tsx` and the nav as placeholders. Task 11 fills them.
5. Setup items already carry `reason.rule_id` and `confidence.tested_on` (`models.py`, `ItemReason` and `Confidence`), so the Why line link needs no server change.

### Risks

1. Help that drifts from the code. The draft already had two stale lines after M4 task 21. The guard tests catch ids and links, not meaning, so tech-writer reads each entry against the code in task 2, and later milestones touch the registry when they change a number's meaning.
2. Rule sentences that overstate. A one-line summary of a rule with many conditions can say more than the rule does. Task 3 marks any it can't word from the file, and the confidence badge stays beside each sentence.
3. Snapshot churn hides a real regression. Task 12 updates M2 to M4 snapshots, and the lead reviews each changed line rather than regenerating them wholesale. Several specs pin strings by text (`review-agents.spec.ts:444`, `:492`, `:504`, `tofix.spec.ts:451-455`, `:744`, and the page tests that count `foot_est`). Option A in section 9, question 7, keeps all of them.
8. No shared axe helper. Each e2e spec loops its own widths, themes and tags. Task 12 adds `e2e/a11y.ts` with one loop that can hold a popover open, and the new specs use it. Old specs keep their loops.
4. Popover clutter. 56 "?" controls could crowd small cards. Pass 13 and the plan review look at density, and the closed-state shots (`help-a-closed-*`) are the reference.
5. Two leads. M5 runs alone in this worktree. The designer pass touches no file in `app/`.
6. HiveMind. `hivemind_lib.py` resolves to the main checkout's store, so consolidation waits for the merge into development.
7. Budget. Section 8's range sits far above plan-a's $10 to $20, because the help popovers joined M5. The stop line holds it.

## 13. Designer plan review (November 10)

The designer's review lists UX needs, and the architecture choices below are the lead's. The design notes, shots and board source live in the session scratchpad under `m5-design/` (notes.md, the dc and ga boards, `site/m5.js` and `site/m5.css`), and they are the build spec for task 11.

The owner's picks (November 10):
- How Claude Code decides is direction C. A settings list leads to one page per setting. On each page the rules group by the outcome status they explain, with the order ladder. Search shows one results pane across all settings, and on phones the results show alone.
- Glossary is direction A. One column holds the lists first (Status words, Scopes, Confidence words), then Terms A to Z, with Jump to chips.
- Yes to the four smaller calls. That covers the two server additions (rule outcomes, and a route per setting page). A due mark shows only when some rules are due, never when all are, and never inside the due view. The Reference pages carry no "?" spots. "Back to {page}" from the Glossary returns focus to the "?" that opened it.

| Need | Where it lands |
|---|---|
| 1. Help values update in place, and a poll never closes an open popover or moves focus | Task 7. Stable keys and a rerender test |
| 2. The Glossary knows the origin page and spot, shows "Back to {page}", and returns focus to the "?" that opened it, not the h1 | Task 7 puts `data-help-id` on every trigger. Task 11 carries the origin in the route query and restores focus. Walkthrough 3 changes in task 12 |
| 3. Each status word, scope and confidence word has its own link target | Task 11. One anchor per list item id on the Glossary |
| 4. Each rule's outcome statuses on `/api/rules` | Server follow-up. `RuleRow.outcomes`, the distinct `conditions[].status` in first-seen order |
| 5. Each setting page has its own route, so Back works | Task 11. `#/reference/decides/<key>`, and a rule inside it by id |
| 6. A row knows when its match was only in its docs quote, says "Found in the docs line" and opens it | Task 7 makes the matcher return the matched fields. Task 11 renders it |
| 7. The polite count also announces after a Confidence change and after Clear | Task 11 |
| 8. A rule or term route hidden by `?q=` or `?confidence=` still shows its target. A stale id shows a not-found line linking to the whole list | Task 11 |
| 9. The due view has an empty state ("No rules are due" and Show all), and the setup notice says how many rules to re-check | Server follow-up adds `VersionGap.due` and the notice param. Task 11 renders both, and task 3b words them |
| 10. While loading, the Confidence select shows no counts and the count line shows a bone. A `?q=` already in the URL applies once data arrives | Task 11 |
| 11. The tile focus ring shows only when the tile's link has focus | Task 7, without a nested `:has()` (K-6860) |

More from the designer:
- The Reference pages carry no "?" spots.
- A per-row due mark shows only when some rules are due, never when all are.
- New tokens `--m5-mark-bg` and `--m5-mark-edge` for search marks go to task 7. The order ladder component goes to task 11.
- The `cli` and `flag` layers differ. Per `dashboard/rules_schema.py`, `cli` is a file passed with `--settings`, which ranks with the settings files, and `flag` is a session flag such as `--model`, `--effort` or `--autocompact`. Bar Tab can't see either in live use. Task 3b gives tech-writer both names to word.

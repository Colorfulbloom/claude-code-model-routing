# How each surface combines across scopes (2026-11-08)

## Recommendation

Keep `resolve.py` as the combiner for settings keys and give it three more combine modes. Give every other surface its own small reader and combiner, behind one common output shape. Don't push memory, agents, skills, MCP or hooks through rules.json votes.

- resolve.py already does the hard part for settings. It votes per candidate, ranks by layer, and has `highest_layer`, `lowest_value`, `ceiling`, `all` and `managed_or_merge` modes (/Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/resolve.py:1314-1354). The only list merge is `_merged_list` (resolve.py:1241-1264), used by `availableModels` alone.
- The other surfaces don't combine by value. They combine by name (agents, skills, MCP, output styles), by concatenation in a fixed order (memory), or by union (hooks). A rule engine built around one winning value per key would need a fake key per name, so separate combiners are simpler (inference).
- Common output per item, whatever the surface: `name`, `surface`, `sources[]` (layer, file, line, value or summary), `winner` (or `all` for unions), `status` (the seven status words), `reason`. The Setup map, the surface pages and "To fix" all read this one shape (app-audit/design.md, "New screens and the state each needs").

New settings combine modes needed:

| Mode | Keys | Rule | Source |
|---|---|---|---|
| `concat` | `permissions.allow`, `permissions.ask`, `permissions.deny`, `additionalDirectories`, `claudeMdExcludes`, `autoMode` entries | Lists from every scope join | https://code.claude.com/docs/en/settings.md#lists-merge-instead-of-overriding ("Claude Code combines the lists instead of picking one"); https://code.claude.com/docs/en/memory.md#exclude-specific-claude-md-files ("Arrays merge across layers"); https://code.claude.com/docs/en/settings-reference.md#automode ("Claude Code concatenates the entries") |
| `per_entry` | `env` per variable, `enabledPlugins` per plugin id, `modelSettings` per model | Highest scope that names the entry wins that entry | settings-reference.md#env ("when more than one settings file sets a variable, the highest-precedence one applies"); https://code.claude.com/docs/en/plugins/loading.md ("the value that applies is the one from the highest-precedence source that mentions the id"); settings-reference.md#modelsettings |
| `allowed_layers` | `modelPicker` (managed, `--settings`, user only), `enforceAvailableModels` (managed only), `defaultMode` `auto` and `bypassPermissions` (not from project or local) | Highest of the allowed layers wins, others are Ignored | settings-reference.md#modelpicker ("ignores the key in project and local settings"); settings-reference.md#enforceavailablemodels ("reads this key from the managed source alone"); https://code.claude.com/docs/en/permission-modes.md ("If you set "auto" in .claude/settings.json or .claude/settings.local.json, the value doesn't take effect") |

Permissions also need an evaluator, not only a combiner. "Deny rules from any scope are evaluated before allow rules", so a user deny blocks a project allow (https://code.claude.com/docs/en/permissions.md#settings-precedence). The page should show the merged three lists, then flag an allow that a deny or ask from any scope shadows.

## Per surface

| Surface | How scopes combine | Source | Reader |
|---|---|---|---|
| Scalar settings | Highest wins: managed, `--settings`, local, project, user | settings.md#settings-precedence | resolve.py as is |
| `maxEffortLevel` | Lowest cap wins | settings-reference.md#maxeffortlevel ("When several scopes set a cap, the lowest applies") | resolve.py `lowest_value`, matches |
| `fallbackModel` | Whole chain from the highest file, no merge | settings-reference.md#fallbackmodel ("doesn't merge across settings files") | resolve.py `highest_layer`, matches |
| `availableModels` | Managed list as is; otherwise lists merge | settings.md (managed list applies "as-is and ignores entries you add in user, project, or local settings") | resolve.py `managed_or_merge`, matches |
| Permissions lists | Concatenate; deny then ask then allow at evaluation | settings.md, permissions.md | resolve.py plus new `concat` mode and an evaluator |
| `env`, `enabledPlugins`, `modelSettings` | Per entry, highest wins | above | new `per_entry` mode |
| Hooks in settings | Merge across levels; an identical handler in several settings files runs once; a plugin's or skill's copy stays separate | https://code.claude.com/docs/en/hooks.md#hook-locations ("Hook entries merge across settings levels rather than replacing each other"), hooks.md#hook-handler-fields | own combiner: union keyed by (event, matcher, handler) |
| Hook switches | `allowManagedHooksOnly` (managed) blocks user, project, local and plugin hooks; `disableAllHooks` takes the value left after precedence and can't disable managed hooks | hooks.md#hook-locations, hooks.md#disable-or-remove-hooks | own combiner reads the two keys through resolve.py first |
| Hooks in skills and agents | Skill hooks last for the rest of the session; agent hooks run while the agent runs; plugin agents ignore `hooks` | hooks.md#hooks-in-skills-and-agents, https://code.claude.com/docs/en/plugins/components.md | listed beside settings hooks with their lifetime |
| Memory (CLAUDE.md, rules) | Concatenated, not overridden. Managed loads before user and project. User rules load before project rules. Subdirectory CLAUDE.md loads on demand. AGENTS.md only when no CLAUDE.md or CLAUDE.local.md sits in the working directory or above. `claudeMdExcludes` can't exclude the managed file | https://code.claude.com/docs/en/memory.md (sections deploy-organization-wide-claude-md, user-level-rules, agents-md, troubleshoot-memory-issues, exclude-specific-claude-md-files) | own reader: ordered list with import expansion |
| Rules `paths` | "paths is the only field Claude Code reads from a rule" | memory.md#rules-frontmatter-reference | part of the memory reader |
| Subagents | By name: managed, `--agents`, project, user, plugin. A clash inside one folder loads one file "chosen by filesystem read order rather than a documented precedence" | https://code.claude.com/docs/en/sub-agents.md#choose-the-subagent-scope | own reader; flag same-folder clashes as "To fix" because the winner is not predictable |
| Skills | Enterprise over personal over project. Plugin skills are namespaced, so both load. A skill beats a same-named `.claude/commands/` file | https://code.claude.com/docs/en/skills.md ("Resolve skills that share a name") | own reader |
| MCP servers | By name: local, project, user, plugin, connectors; `managedMcpServers` above all. "The entire server entry from that source is used; fields are not merged across scopes" | https://code.claude.com/docs/en/mcp.md#precedence | own reader; project entries also pass the approval keys (`enabledMcpjsonServers`, `disabledMcpjsonServers`, `enableAllProjectMcpServers`) |
| Output styles | User, project and managed folders; the nearest project folder wins among nested ones; the `outputStyle` key picks one by exact name, else Default; read at start | https://code.claude.com/docs/en/output-styles.md | own reader plus resolve.py for `outputStyle` |
| Keybindings | User only | https://code.claude.com/docs/en/claude-directory.md | plain reader |
| `statusLine` | Any settings file; merge rule not documented, so highest wins (inference) | settings-reference.md index | resolve.py `highest_layer` |
| Plugin layer | Plugin agents lowest of five, plugin skills namespaced, plugin MCP below user, plugin hooks beside settings hooks, plugin `settings.json` keeps only `agent` and `subagentStatusLine` | 26-03-plugin-collector.md | plugin collector feeds each reader |

## rules.json against the documented exceptions

Checked the combine mode of every rule in /Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/rules.json (84 rules, tallied by key and `combine`).

- `fallbackModel`, 5 rules, all `highest_layer` (rules.json:5840, 5944, 6026, 6091, 6171). Matches the docs.
- `availableModels`, 4 rules, all `managed_or_merge` (rules.json:6218, 6257, 6321, 6393). Matches. The resolver also removes duplicates and keeps only string items (resolve.py:1250-1264); the docs say nothing on duplicates.
- `maxEffortLevel` and `modelSettings.maxEffortLevel`, `lowest_value`. Matches the docs.
- `modelPicker`: no rule. Gap. It needs `allowed_layers` (managed, `--settings`, user).
- `enforceAvailableModels`: no rule. Gap. Managed only.
- `env`: one rule, `highest_layer`. Fine for one named variable, which is how the rules use it.
- No rule covers permissions, hooks, `enabledPlugins`, `claudeMdExcludes` or `additionalDirectories`. Expected, because rules.json was built for model and effort, but the rebuild's wider scope needs them as data.

## UNVERIFIED

- Whether concatenated lists are deduplicated (permissions, `additionalDirectories`). Docs silent.
- Whether `env` and `enabledPlugins` deep-merge as objects or only resolve per entry. Docs state per variable and per id, which behaves the same for display.
- The explicit deny, ask, allow sequence. Docs state deny before allow and that a matching ask still prompts.
- @import depth, base folder and code-span rule. The fetch missed that section. Earlier research says 4 hops, relative, skipped in code (18-config-surfaces.md); not re-read.
- User versus project CLAUDE.md order, and same-name output styles between user and project.
- Whether a skill and a subagent with the same name interact.
- `keybindings` and `statusLine` merge rules.
- Doc quotes came through WebFetch, which summarizes, so they are near-verbatim.

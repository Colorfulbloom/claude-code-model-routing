# Plugin collector (2026-11-08)

## Recommendation

Read plugins read-only from two records and one folder tree, never from the newest folder name.

1. Read `enabledPlugins` from every settings source and resolve it per plugin id with the highest source that names the id. Managed `true` forces on and managed `false` blocks.
2. Read `<plugins dir>/installed_plugins.json` for each install's scope, project path, `installPath` and `version`. Take the install whose scope applies to the current project.
3. Scan only that `installPath`, using the manifest's path keys over the default folders. Skip any version folder that holds `.orphaned_at`.
4. Mark every plugin item read-only, with source chip "plugin <name>@<marketplace>". For plugin agents, flag the four ignored fields when present. For plugin `settings.json`, show only `agent` and `subagentStatusLine` as live and the rest as dropped.
5. Treat the files as moving targets. Claude Code rewrites `installed_plugins.json` at session start, and open issues show it rewriting other projects' records. Parse defensively, tolerate an unknown `version` field value, and show a "Couldn't read" state rather than failing the page.

The plugin directory is `<config dir>/plugins`, or `CLAUDE_CODE_PLUGIN_CACHE_DIR` when set (loading.md below). The current app has no plugin reader at all, so this is new code, and the resolver's plugin layer gets fed for the first time.

## Facts

### Files on disk

- Root holds `cache/`, `data/`, `marketplaces/`, `synced/` and `.trash/`, under `~/.claude/plugins` or `CLAUDE_CODE_PLUGIN_CACHE_DIR`. Source: https://code.claude.com/docs/en/plugins/loading.md ("Find plugins on disk").
- `installed_plugins.json` "records each install with its scope, installPath, and version". Source: loading.md ("Check which stage a plugin reached"). No official sample of the file exists in the docs.
- `known_marketplaces.json` "records each marketplace Claude Code has fetched, with its source, installLocation, lastUpdated, and autoUpdate". Source: loading.md (same heading). A marketplace added from a local path has no copy under `marketplaces/`, and `installLocation` is that path.
- Cache layout is `cache/<marketplace>/<plugin>/<version>/`, "One directory per installed version". Source: loading.md ("Find plugins on disk").
- Version string comes from the manifest `version`, then the marketplace entry's version, then the source type (12-character commit SHA for git sources, a digest for archives, "unknown" for npm). Source: loading.md ("How Claude Code computes the version").
- An unofficial source copy shows the file shape as `{"version": 2, "plugins": {"<plugin>@<marketplace>": [entry, ...]}}`, each entry with `scope`, `installPath`, `version`, `installedAt`, `lastUpdated`, `gitCommitSha`, and `projectPath` for project and local scope. This is not an Anthropic source, so the collector must not depend on it beyond the three documented fields (inference). The value being a list fits one plugin installed at both user and project scope (inference).

### Active version and orphans

- "Claude Code writes an .orphaned_at marker into the previous version directory. It removes that directory in a background cleanup 14 days later". Source: loading.md ("Cleanup of previous versions").
- The loader reads `installed_plugins.json` and the cache at session start, with no network. Source: loading.md.
- So the active version is the one `installed_plugins.json` names, and an `.orphaned_at` folder is a leftover kept for running sessions (inference from the two facts above).

### Enabling and scopes

- Sources for `enabledPlugins`, lowest to highest: `--add-dir`, user, project, local, `--settings`, managed. "For each plugin id, the value that applies is the one from the highest-precedence source that mentions the id." Source: loading.md ("Find where a plugin is enabled").
- Format is `"<name>@<marketplace>": true | false`. Managed `true` force-enables and managed `false` blocks. Source: loading.md.
- Install scopes user, project and local write the entry into `~/.claude/settings.json`, `.claude/settings.json` and `.claude/settings.local.json`. Source: https://code.claude.com/docs/en/plugins/install.md ("Choose an install scope").
- An installed plugin with a `false` entry or `defaultEnabled: false` "stays off until you turn it on". `defaultEnabled` defaults to true. Sources: install.md, https://code.claude.com/docs/en/plugins/manifest-reference.md.
- Changes reach a running session only after `/reload-plugins` or a new session. Source: loading.md.

### Components

- Standard layout: `.claude-plugin/plugin.json`, `skills/`, `commands/`, `agents/`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `output-styles/`, `themes/`, `monitors/monitors.json`, `bin/`, `settings.json`. Source: manifest-reference.md ("Standard layout").
- Manifest path keys `agents`, `commands` and `outputStyles` replace the default folder scan, `skills` adds to it, and `hooks` and `mcpServers` merge. Paths start with `./` and stay inside the plugin root. Source: manifest-reference.md ("How each key combines with its default location", "Path rules").
- Plugin `settings.json`: "Only two keys take effect, agent and subagentStatusLine, and every other key is dropped." Source: https://code.claude.com/docs/en/plugins/components.md ("Default settings").
- Plugin agents: "Ignored fields: permissionMode, hooks, mcpServers, and initialPrompt." Source: components.md ("Frontmatter fields in plugin agents"). The current app's field list already marks the same four as "Ignored for plugin subagents" (/Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/agent_fields.json:58, :86, :93, :167). This settles contradiction C7 in 24-coverage-matrix.md at four ignored fields.
- Plugin CLAUDE.md is not loaded and plugins have no rules folder (25-verifier-gap-research.md).
- `CLAUDE_PLUGIN_DATA` is `~/.claude/plugins/data/<id>/`, kept across updates, and deleted "when you uninstall the plugin from the last place it's installed". Source: manifest-reference.md ("Environment variables").

### Precedence of plugin items against other layers

- Agents: plugin is the lowest of five locations. Source: https://code.claude.com/docs/en/sub-agents.md ("Choose the subagent scope").
- Skills: plugin skills are namespaced (`plugin:skill`), so they never clash with personal or project skills. Source: https://code.claude.com/docs/en/skills.md.
- MCP: plugin sits below local, project and user, and entries are not merged. Source: https://code.claude.com/docs/en/mcp.md#precedence.
- Hooks: plugin hooks run beside settings hooks. A plugin's copy of a handler that also sits in settings stays separate. Source: https://code.claude.com/docs/en/hooks.md#hook-handler-fields.

### Write activity to expect

- Open: #106146 "Session start rewrites other projects' plugin records in installed_plugins.json" (opened October 30, 2026), https://github.com/anthropics/claude-code/issues/106146
- Open: #106500, symlinked `~/.claude` duplicates project-scope records (November 1, 2026), https://github.com/anthropics/claude-code/issues/106500
- Open: #97264, `CLAUDE_CONFIG_DIR` starting in `$HOME` records project-scope installs (September 25, 2026), https://github.com/anthropics/claude-code/issues/97264

### Current app

- No reader for `installed_plugins.json`, `known_marketplaces.json` or `enabledPlugins` in `dashboard/`. The only mention is a key list in the harness, /Volumes/Warehouse/Projects/claude-code-model-routing/dashboard/experiments/harness/runcase.py:120. No fixture of the file under `tests/fixtures`.

## Collector output per item (for the surface registry)

`plugin_id`, `marketplace`, `install_scope`, `project_path`, `version`, `install_path`, `enabled` with the winning source, `kind` (agent, skill, command, hook, mcp, output style, settings), `path`, `writable: false`, `ignored_fields` (agents), `dropped_keys` (settings), `parse_state`. The fixture corpus needs at least one plugin installed at two scopes, one disabled plugin, one orphaned version folder, and one manifest that overrides `agents`.

## UNVERIFIED

- The real shape of `installed_plugins.json` beyond the three documented fields. Build the fixture from a real file on a test machine with the owner's consent, not from the unofficial source.
- `--keep-data` on uninstall (cli-reference page not read in full).
- Whether the orphan sweep also runs on `/reload-plugins`.
- The full `enabledPlugins` entry in settings-reference.md (fetch was cut off).
- WebFetch quotes come through a summarizing model, so they are near-verbatim, not byte-checked.

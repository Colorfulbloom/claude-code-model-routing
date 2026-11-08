# Scout report: how agentic setups are shared (2026-11-08), condensed by main session. Quotes via WebFetch summaries; star counts unverified.

Recommendation: ship agents, skills and hooks as a plugin; keep rules and CLAUDE.md in a small installer or committed .claude/; test hook-based model enforcement on the Agent tool first. Alternative: keep the copy installer and add an install-state record (ECC pattern).

- Plugins carry skills, agents, hooks, MCP, bin/, output styles, default `agent` and `subagentStatusLine` settings only; other settings keys dropped; plugin-root CLAUDE.md not loaded; no rules folder in layout. https://code.claude.com/docs/en/plugins/manifest-reference
- Enabled plugin's skill/agent names and descriptions cost context every session. https://code.claude.com/docs/en/plugins
- Version pins; auto-update off for non-Anthropic marketplaces; mid-session old paths until /reload-plugins; cache kept 14 days; data deleted on last uninstall. https://code.claude.com/docs/en/plugins/loading https://code.claude.com/docs/en/plugins/security
- userConfig prompts values; ${user_config.KEY} in agent model UNVERIFIED. https://code.claude.com/docs/en/plugins/components
- Plugin agents support model and effort frontmatter; ignore permissionMode, hooks, mcpServers, initialPrompt. Same URL.
- Plugin hooks run every session and inside subagents; same-name plugins: only one registers hooks. https://code.claude.com/docs/en/hooks https://code.claude.com/docs/en/plugins/loading
- Plugins "can execute arbitrary code on your machine with your user privileges." https://code.claude.com/docs/en/plugins/security
- Committed .claude/settings.json can declare extraKnownMarketplaces and enabledPlugins after workspace trust; external plugins still need install. https://code.claude.com/docs/en/plugins/org
- Managed settings control plugin policy, not per-agent models. Same URL.
- Output styles with force-for-plugin override the user's style; instructions, not enforcement. https://code.claude.com/docs/en/output-styles
- User override of plugin agent model: CLAUDE_CODE_SUBAGENT_MODEL (+ _FORCE) global only; mod agent.spawn; same-name user agent shadowing namespaced plugin agent UNVERIFIED. https://code.claude.com/docs/en/sub-agents
- PreToolUse on Agent tool with updatedInput to rewrite model: plausible, UNVERIFIED.
- Examples: anthropics/claude-plugins-official, wshobson/agents (marketplace, per-agent model), VoltAgent/awesome-claude-code-subagents (plugin or copy script), davila7/claude-code-templates (npx, merges config), obra/superpowers (skills + SessionStart hook, official marketplace), SuperClaude (pipx installer), affaan-m/everything-claude-code (npx or plugin; install-state record; "plugins cannot distribute rules"), hesreallyhim/awesome-claude-code (list).
- Other tools: AGENTS.md https://agents.md/ ; Codex AGENTS.md; Cursor rules packaged in plugins https://cursor.com/docs/context/rules ; Gemini CLI extensions https://geminicli.com/docs/extensions/ ; Copilot custom agents.

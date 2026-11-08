# Verifier (Opus) on gap research 16-23 (2026-11-08), condensed by main session
Docs copies and evidence: scratchpad/spikes/verify2/

Verdict: sound with corrections.
- Transcript tokens: dedupe in dashboard/usage.py:117-146 keeps largest output per message.id (then requestId), ties to later timestamp. Cache/input sound. Output can be a mid-stream snapshot (issues #27361, #21971, #22686, closed unfixed), so output is a lower bound. Blog's 100x input claim likely a methodology error (inference). Official: one transcript entry per content block (monitoring-usage.md:812); format internal and changes between versions (:771).
- Retention: cleanupPeriodDays 30 holds; Desktop/Cowork transcripts kept at any age.
- WRONG in 16: hooks DO have token fields (PostToolUse on Agent totalTokens/usage, hooks.md:1935-1938; estimated_cache_write_usd).
- Plugins facts hold (CLAUDE.md not loaded, no rules folder, only agent/subagentStatusLine settings, ignored agent fields incl. initialPrompt, plugin data deleted on uninstall unless --keep-data, old versions removed after 14 days with .orphaned_at).
- Settings: list merge has exceptions (fallbackModel, modelPicker, availableModels whole value); broken files: interactive shows dialog, -p skips.
- MCP precedence local > project > user > plugin > connectors, not merged; managedMcpServers above all.
- uv forwards SIGTERM (since 0.5.2). SIGKILL to uv could orphan Python: record server's own pid.
- Python 3.15 webbrowser on macOS runs /usr/bin/open <url> (key fragment in argv); 3.11-3.14 use osascript stdin. uv only-managed may pick 3.15 unless pinned.
- Rule counts, constant tables, no plugin collector: hold. LiteLLM MIT. WCAG 2.5.7/2.5.8/2.4.11 and React Aria announce assertive default: hold.
- Unverified: subagent "invalid skipped silently" and "edits within seconds" not in sub-agents.md.

Decision impacts:
1. Move DB out of plugin data (beside backups); only rebuildable caches inside.
2. Label output cost as "lower bound, list price"; store stop_reason and row count; harness spike: fakeapi message_delta output 500 multi-block, read throwaway transcript.
3. Pin Python below 3.15, or open browser via osascript stdin, or one-time code swapped for key.
4. MCP edits: project .mcp.json only, or `claude mcp add/remove` for local/user; hooks like permissions with validated form and confirm.
5. Plugin collector: read version in installed_plugins.json, skip .orphaned_at, read-only, show ignored fields.
6. Add Opus 4.5/4.1/4 and Sonnet 4.5/4 prices.
7. Check list-merge exceptions against rules.json combine modes.
8. .claude.json under CLAUDE_CONFIG_DIR when set.

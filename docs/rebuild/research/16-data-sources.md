# Scout report: usage data sources (2026-11-08), condensed by main session. Quotes via WebFetch summaries.

Recommendation: transcripts JSONL primary (zero setup); optional hooks for live dispatch tree; optional status line (takes the user's one slot); optional OTel power path. Admin/Usage APIs not for individual users.

- Transcripts documented location only: projects/<project>/<session>.jsonl and <session>/subagents/; schema undocumented. https://code.claude.com/docs/en/claude-directory
- Retention cleanupPeriodDays default 30, min 1; subagent transcripts removed with parent. Same URL. (Current app horizon 61 days; a DB could keep history past cleanup.)
- CLAUDE_CODE_SKIP_PROMPT_HISTORY and --no-session-persistence skip transcripts. stats-cache.json backs /usage, format unverified.
- Quirks (third party cctop): same requestId written repeatedly with growing counts, keep last snapshot; one record per block; resumed sessions new file; subagents/<agent-id>.jsonl + optional .meta.json; older agents lack toolUseId. https://docs.rs/crate/cctop/latest/source/docs/providers/claude.md
- ccusage dedupes messageId:requestId (snippet), prices from LiteLLM. https://github.com/ryoppippi/ccusage
- Contested: blog claims JSONL token counts are streaming placeholders that undercount ~100x (unverified). https://gille-ai.pages.dev/en/blog/claude-code-jsonl-logs-undercount-tokens
- OTel: CLAUDE_CODE_ENABLE_TELEMETRY=1, OTLP/console/prometheus; claude_code.cost.usage and token.usage with model, effort, agent.name, query_source; api_request events with agent_id, parent_agent_id (events only, not metrics); OTEL_* not passed to subprocesses; ignored in repo .claude/settings.json. https://code.claude.com/docs/en/monitoring-usage
- Hooks: common fields session_id, transcript_path, cwd, effort; SubagentStart agent_id, agent_type; no documented token/cost fields; 1.5 s budget for SessionEnd. https://code.claude.com/docs/en/hooks
- Status line JSON: cost.total_cost_usd, context_window tokens, effort, rate_limits for subscribers; subagentStatusLine tasks with tokenCount; one statusLine per user; cost computed locally at list price unless modelPricing. https://code.claude.com/docs/en/statusline https://code.claude.com/docs/en/costs
- Admin / Usage and Cost APIs unavailable for individual accounts; subscription usage not returned. https://platform.claude.com/docs/en/manage-claude/claude-code-analytics-api

---
name: route-project
description: Per-project step for model routing. Audits this project's own agents, proposes a model tier and effort for each, checks for conflicts with the global routing rules, and applies on approval. Run with /route-project after installing the global setup.
disable-model-invocation: true
---

# Assign model tiers to this project's agents

## Goal

The global setup (`~/.claude/`) already gives every session the `scout`, `fast-worker`, `judge`, `deep-reasoner`, `designer` and `verifier` agents, the routing rules, and a dispatch hook that blocks unpinned agents. An Opus catch-all (`CLAUDE_CODE_SUBAGENT_MODEL`) applies only if `/setup-model-routing` set it.

This step tunes the agents that only exist in this project: pin each one to the tier its work needs, cap its effort, decide which ones may delegate, and make sure nothing in this project overrides the global setup. It's a one-time pass per project.

## Rules for this run

1. Audit first. Change nothing until I approve the proposal in Phase 2.
2. Keep every existing agent: its name, domain, and ownership boundaries. You are adding frontmatter lines, not reorganizing the team.
3. Don't touch agent bodies unless I approve a specific change in Phase 2.
4. Only use facts you read in this repo. If something is unclear, ask.
5. Use the tiers during this run: do the Phase 1 inventory with `scout` and have it return a structured list.
6. No em dashes in anything you write.

## Config facts (verified against the Claude Code docs, September 2026)

- Project agents live in `.claude/agents/` and take priority over user agents with the same name.
- Valid `model` values: `fable`, `opus`, `sonnet`, `haiku`, a full model ID, or `inherit`. `inherit` means the main session's model, so treat `inherit` as unpinned. The global dispatch hook blocks dispatches to unpinned agents unless a model is passed.
- `effort` values: `low`, `medium`, `high`, `xhigh`, `max`; depends on the model. An agent without `effort` resolves effort for its own model, so a level set only for the main model doesn't reach it (tested; the docs do not say). Pin `effort` on every agent.
- Subagents can spawn subagents, up to three layers below the main session. `disallowedTools: Agent` stops an agent from delegating further.
- Project settings override user settings key by key, so a `model`, `env`, or `hooks` entry in `.claude/settings.json` or `.claude/settings.local.json` can beat the global setup.
- CLAUDE.md files and rules are context, not enforcement. If two rules conflict, Claude may follow either one.

## Phase 1: Audit (read-only)

Dispatch `scout` to collect the following, then summarize it for me:

1. Every file in `.claude/agents/`: name, first line of description, tools, model (or "none"), effort (or "none"), and the kind of work its body describes: read-only/search, mechanical implementation, integration implementation, deep reasoning/design, review/audit, or lead/orchestrator (it coordinates other agents). Note any agent whose work clearly mixes tiers.
2. Any project agent named `scout`, `fast-worker`, `judge`, `deep-reasoner`, `designer` or `verifier` (it would shadow the global one).
3. `.claude/settings.json` and `.claude/settings.local.json`: the `model`, `env`, `effortLevel`, `modelSettings`, and `hooks` values, if any.
4. `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, nested CLAUDE.md files, and `.claude/rules/*.md`: any delegation, routing, or model rules, quoted.
5. Whether `.claude/agents/` is tracked in git, and whether `.claude/settings.local.json` is gitignored, so we know which changes reach teammates.

## Phase 2: Proposal (stop here and wait for my approval)

Show me:

**A. Tier map.** A table: agent | current model | proposed model | proposed effort | may delegate? | one-line reason. Guidance:
- Read-only work, search, inventories, log and test summaries: `haiku`, effort `low`, no delegation (`disallowedTools: Agent`).
- Mechanical or well-specified implementation, tests, docs, read-and-report reviews: `sonnet`, effort `medium`, no delegation.
- Integration work across many files with judgment calls: `sonnet`, effort `high`, no delegation.
- Architecture, complex debugging, algorithm design, security-sensitive or novel code, sole ownership of critical primitives: `opus`, effort `high`.
- A lead or orchestrator agent that coordinates other project agents: `opus`, effort `high`, keeps the `Agent` tool. It should follow the same pattern as `deep-reasoner`: plan, dispatch, verify, return one summary.
- An agent whose work mixes tiers: pin it to the tier it needs most often. The orchestrator can raise or lower the tier per dispatch with the `model` parameter.
- Every agent gets an explicit model. Never `fable` and never `inherit`.

**B. Overrides.** Any `model`, `env`, `effortLevel`, `modelSettings`, or `hooks` in project settings that would beat the global setup, with a recommended fix (usually: remove it, or set it to match). I'll decide.

**C. Conflicts.** Any project rule that contradicts the global routing rules, quoted, with a proposed edit or removal. I'll decide.

**D. Shadowing.** Any project agent named `scout`, `fast-worker`, `judge`, `deep-reasoner`, `designer` or `verifier` shadows the global tier agent of that name. Say whether to rename it or keep it.

**E. Body changes.** Anything you'd like to change inside an agent's instructions (for example, a short report format, or lead behavior for an orchestrator agent). List separately. I may say no.

## Phase 3: Apply (only after I approve)

1. Add or update `model`, `effort`, and `disallowedTools` in each agent's frontmatter as approved. Leave everything else in the file exactly as it was.
2. Apply the approved settings and rule changes.
3. Apply approved body changes only.

## Phase 4: Verify

1. Re-read every agent file. Confirm valid YAML, `name` and `description` present, `model` valid and not `inherit`, `effort` present and valid for that model.
2. Confirm no agent in `.claude/agents/` is left unpinned. Run the global hook script against each one to prove it: `echo '{"tool_name":"Agent","tool_input":{"subagent_type":"<name>","prompt":"x"}}' | python3 ~/.claude/hooks/require-agent-model.py; echo "exit $?"` should exit 0 for every agent.
3. Routing dry run: pick three realistic tasks for this project (one search-heavy quick task, one mechanical quick task, one multi-step feature) and show the dispatch plan for each. For the feature, show the lead's plan too: which workers, which model, in what order. Don't execute anything.
4. List every file changed, and tell me what needs a new session to take effect.

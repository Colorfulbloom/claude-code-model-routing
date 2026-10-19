# Model routing reference

Explanation for `~/.claude/rules/model-routing.md`. Nothing imports this file; it costs no tokens per turn. Read it when you want to know why the setup works the way it does.

## Shape

```
Fable (main session)
Plans, decides quick task vs feature, reviews summaries, makes the call. Never codes.
│
├── Quick tasks (one brief, fully specified): dispatch a worker directly
│   ├── fast-worker (Sonnet)     small edit Fable already has the plan for
│   ├── scout (Haiku)            search, run tests, summarize logs
│   ├── deep-reasoner (Opus)     a single hard question
│   └── project agents           pinned to their tier by /route-project
│
├── Design (new or changed UI): hand ONE brief to the designer; the owner picks
│   └── designer (Fable, high)
│       Studies the design system, renders 2 or 3 directions, recommends one.
│       ├── scout (Haiku)          inventories, token and component lookups
│       ├── judge (Sonnet)         Chrome checks, synthesis
│       ├── fast-worker (Sonnet)   captures, renders, the build after the pick
│       └── project writer         all copy (for example a tech-writer project agent)
│
└── Features (anything needing more than one brief): hand ONE design brief to the lead
    └── deep-reasoner as lead (Opus)
        Plans, writes worker briefs, dispatches, verifies, returns ONE summary.
        ├── fast-worker (Sonnet)   x as many as needed, parallel where separable
        ├── project agents         at their pinned tier, for work in their files
        └── scout (Haiku)          searches, test runs, diff and log reading

Codex: OFF. When ON, a peer next to deep-reasoner at layer one.
```

## Tiers

| Tier | Agent | Model | Effort | Use for |
|------|-------|-------|--------|---------|
| Orchestrator | main session | Fable | high by default; xhigh if `/setup-model-routing` set `effortLevel` in settings with your approval | Planning, deciding, reviewing summaries, the final call |
| Lead / reasoner | `deep-reasoner` | Opus | high | Feature lead; architecture, hard debugging, algorithms, high-risk code; `memory: project` (operational lessons per repo, `.claude/agent-memory/deep-reasoner/`) |
| Designer | `designer` | Fable | high | New or changed UI, layout, components, visual design and design critique; leads like deep-reasoner; `memory: user` (`~/.claude/agent-memory/designer/`); settings from the project CLAUDE.md "Design" section |
| Worker | `fast-worker` | Sonnet | medium | Well-specified implementation, tests, docs; cannot delegate (`disallowedTools: Agent`) |
| Judge | `judge` | Sonnet | medium | Synthesis and judgment over gathered material, Chrome work; read-only on files, replaces built-in general-purpose |
| Scout | `scout` | Haiku | low (pinned so a newer Haiku with effort levels cannot inherit the session's) | Search, inventories, test and lint runs, log and diff reading; read-only tools. On Claude Code 2.1.302 (native install) the `haiku` alias resolved to Haiku 5.5 in the owner's test on October 17, 2026. If your build resolves it to an older Haiku, pin the full id `claude-haiku-5-5` in the file. |
| Owner | project agents | pinned by `/route-project` | per agent | Work in the files they own |

## Why the lead pattern exists

Every subagent's output lands in the context of whoever dispatched it. If Fable ran a feature itself, it would dispatch several workers and scouts and read every one of their reports, filling the most expensive context with worker detail it only needs a verdict on. Handing one brief to `deep-reasoner` moves all of that one layer down: the lead absorbs the worker transcripts on Opus, verifies the result, and returns a single summary. Fable stays lean, keeps its judgment for the decision, and pays Fable rates only for planning and review. Subagents can nest up to three layers below the main session, so Fable, then the lead, then workers, fits with room to spare.

## The designer

`designer` (Fable, high; owner decision, October 17, 2026) owns design judgment. It studies the project's design system, renders two or three directions at desktop and phone width, critiques them with the preloaded `design:*` skills and recommends one. It leads like deep-reasoner, so its Fable tokens go to judgment and the rest goes to scout, judge, fast-worker and the project's writer.

- Who dispatches it: the main session. Subagents can't ask the owner questions (`AskUserQuestion` is removed from every subagent), so the owner picks a direction after the designer reports and before anything is built. Resume the same designer for the build to keep its study. A lead may dispatch it for a review-only pass against the picked direction only when the build departs from the designer's spec. When the designer handed over exact values, `judge` compares screenshots against the designer's clips instead.
- Nesting: main session, then designer (layer 1), then its workers (layer 2). Dispatched by a lead, the designer sits at layer 2 and its workers at layer 3, the default limit, where Claude Code withholds `Agent`. None of its workers delegates, so that still works.
- Project settings come from the project CLAUDE.md "Design" section. Subagents load the full CLAUDE.md hierarchy (user rules included) but not the main session's auto memory, so design rules that live only in memory don't reach it. Defaults without a Design section: Chrome only, Figma off, no writes to the project, widths 1440 and 375. Fallbacks for each missing setting are in the agent file and in the README's "Designer settings" section, and `examples/CLAUDE-design-section.md` is a template for the section.
- Figma stays reachable but off. The design plugin's Figma MCP tools reach every subagent; a prompt rule keeps them off unless the Design section says "Figma: on". A `disallowedTools` entry would block Figma in every project.
- `/design` is a command the owner runs. The designer drafts a Claude Design canvas through the Artifact tool (quickstart, intent `design`) instead.

## Model resolution order

For each subagent, the first of these that applies wins:

1. The `model` parameter passed on the dispatch.
2. The agent file's `model` field (`inherit` means the main session's model).
3. `CLAUDE_CODE_SUBAGENT_MODEL`, if set (the `/setup-model-routing` skill offers to set it to `opus` in `~/.claude/settings.json`; the installer does not).
4. The main session's model.

Under a Fable session, an agent with no model or with `inherit` would run on Fable. The dispatch hook exists to stop that.

Built-in agents: Explore follows the main session's model, with one exception under Fable. With a Claude subscription, a Console account or an `ANTHROPIC_BASE_URL` gateway it then runs on the `opus` alias; on Bedrock, Agent Platform, Foundry, Claude Platform on AWS and the apps gateway it stays on Fable. Plan inherits the main session's model. General-purpose is blocked by the hook (historically it used `CLAUDE_CODE_SUBAGENT_MODEL` if set, otherwise the main model); use `judge`.

## The dispatch hook

`~/.claude/hooks/require-agent-model.py` runs as a `PreToolUse` hook on the `Agent` tool. It exits 2 (block, with the reason shown to Claude) when a dispatch passes no `model` and:

- targets a built-in agent (`Explore`, `Plan`), or
- targets an agent not found in the project's `.claude/agents/` or the user agents folder (`$CLAUDE_CONFIG_DIR/agents/` when that variable is set, else `~/.claude/agents/`), or
- targets an agent whose `model` is missing or `inherit`.

It blocks `general-purpose` always, and any found agent without a pinned `effort`, Haiku agents included, even when a model is passed, because an agent without `effort` runs at the session's effort (observed; the docs do not say).

It lets through: plugin agents (names containing `:`), a dispatch with no agent name, any input it cannot parse, and any other dispatch that passes a `model` or targets an agent with a pinned model, provided the agent file, when one is found, also pins an `effort`.

**To relax it** (fill in a model instead of blocking): replace each `block(...)` call with a JSON reply on stdout and exit 0, using `hookSpecificOutput` with `permissionDecision: "allow"` and `updatedInput` set to the original `tool_input` plus `"model": "opus"` (or whichever tier you want as the fallback). The dispatch then proceeds on that model with no retry.

`CLAUDE_CODE_SUBAGENT_MODEL=opus`, when set, is the catch-all for anything the hook doesn't see: agent teams, workflow agents, and sessions that don't load user settings. The installer leaves it unset; `/setup-model-routing` sets it after you approve.

## Startup nudge

`~/.claude/hooks/check-agent-models.sh` runs on `SessionStart` (matcher `startup`). When the current project's `.claude/agents/` or the user `agents/` folder has agents with no model or effort, it adds a line per folder to the session context naming them, with `/route-project` as the fix for project agents and the two frontmatter lines for user agents. It prints nothing otherwise.

## Where this applies

The terminal CLI and the Desktop app's Code tab. Cloud sessions (Claude Code on the web and in the mobile app) don't read `~/.claude/` at all, so none of this reaches them; they need repo-level `.claude/agents/` and settings.

## Codex

Turn Codex on:
1. Requirements: a ChatGPT subscription (Free works) or an OpenAI API key, and Node.js 18.18 or later. Codex usage counts against your Codex limits.
2. Install and sign in to the Codex CLI: `npm install -g @openai/codex`, then `codex login`.
3. In Claude Code: `/plugin marketplace add openai/codex-plugin-cc`, then `/plugin install codex@openai-codex`, then `/reload-plugins`, then `/codex:setup`.
4. In `~/.claude/rules/model-routing.md`, change `Codex: OFF` to `Codex: ON`.

Turn Codex off:
1. In `~/.claude/rules/model-routing.md`, change `Codex: ON` to `Codex: OFF`.
2. Run `/plugin disable codex@openai-codex` so the plugin stops adding context to every turn. `/plugin enable codex@openai-codex` brings it back.

Useful Codex commands once it's on: `/codex:rescue` (hand Codex a task, add `--background` to run it async), `/codex:status`, `/codex:result`, `/codex:cancel`, `/codex:review`, `/codex:adversarial-review`.

## Verification

```bash
# plain install: settings parse and carry the two hook entries
python3 -c 'import json; s=json.load(open("'"$HOME"'/.claude/settings.json")); print([e["matcher"] for e in s["hooks"]["PreToolUse"]], [e["matcher"] for e in s["hooks"]["SessionStart"]])'

# after /setup-model-routing: the optional keys are present too
python3 -c 'import json; s=json.load(open("'"$HOME"'/.claude/settings.json")); print(s.get("model"), s.get("effortLevel"), s.get("env", {}).get("CLAUDE_CODE_SUBAGENT_MODEL"))'

# pinned agent: nothing printed, exit 0
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"fast-worker","prompt":"x"}}' | python3 ~/.claude/hooks/require-agent-model.py; echo "exit $?"

# built-in with no model: block message, exit 2
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","prompt":"x"}}' | python3 ~/.claude/hooks/require-agent-model.py; echo "exit $?"

# built-in with a model: exit 0
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","model":"haiku","prompt":"x"}}' | python3 ~/.claude/hooks/require-agent-model.py; echo "exit $?"

# designer pinned: nothing printed, exit 0 (the hook needs ~/.claude/agents/designer.md on disk)
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"designer","prompt":"x"}}' | python3 ~/.claude/hooks/require-agent-model.py; echo "exit $?"

# no agent files below the top level: prints nothing. Claude Code reads subfolders too, and a backup with
# the same name can load instead of the live file; the hook reads only the top level, so it can't catch this
find ~/.claude/agents -mindepth 2 -name '*.md'

# nudge, from inside a project folder
CLAUDE_PROJECT_DIR="$PWD" bash ~/.claude/hooks/check-agent-models.sh

# agents on disk
ls ~/.claude/agents/
```

In a new session: the model shown (`/model` in the terminal, the model dropdown in the Desktop Code tab) is whatever `/setup-model-routing` set, or your previous default on a plain install; asking "which subagents are available to you?" lists scout, fast-worker, judge, deep-reasoner, designer and verifier; `/context` lists `model-routing.md` under memory files.

## Per project

Run `/route-project` in each project to pin its own agents to a tier. Until then, dispatches to its unpinned agents are blocked unless they pass a model, and the startup nudge names them.

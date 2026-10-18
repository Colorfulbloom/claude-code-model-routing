---
name: setup-model-routing
description: One-time audit of the model-routing install under ~/.claude/ plus the optional global settings install.sh leaves alone (main model, effortLevel, subagent catch-all). Run once with /setup-model-routing after install.sh. Per-project tuning is /route-project.
disable-model-invocation: true
---

# Global model routing: audit and optional settings (run once)

## Goal

Confirm that `install.sh` from `claude-code-model-routing` left my machine in this shape, then offer the three global settings the installer does not touch.

```
Fable (main session)
Plans, decides quick task vs feature, reviews summaries, makes the call. Never codes.
│
├── Quick tasks (one brief, fully specified): dispatch a worker directly
│   ├── fast-worker (Sonnet)     small edit the session already has the plan for
│   ├── scout (Haiku)            search, run tests, summarize logs
│   ├── judge (Sonnet)           weigh gathered material, Chrome checks
│   ├── deep-reasoner (Opus)     a single hard question
│   └── project agents           pinned to their tier by /route-project
│
├── Design (new or changed UI): hand ONE brief to the designer; the owner picks
│   └── designer (Fable, high)
│       └── scout, judge, fast-worker, the project writer
│
└── Features (anything needing more than one brief): hand ONE brief to the lead
    └── deep-reasoner as lead (Opus)
        Plans, writes worker briefs, dispatches, verifies, returns ONE summary.
        └── fast-worker, scout, project agents

verifier (Fable, high): checks a plan or report before it reaches the owner
Codex: OFF. When ON, a peer next to deep-reasoner.
```

What `install.sh` already placed under the config dir:

- `agents/`: `scout`, `fast-worker`, `judge`, `deep-reasoner`, `designer`, `verifier`, each with a pinned `model` and `effort`.
- `rules/model-routing.md` (the routing policy) and `rules/claude-in-chrome.md`.
- `hooks/require-agent-model.py` (the dispatch hook, required) and `hooks/check-agent-models.sh` (the startup nudge), both wired into `settings.json`.
- `skills/setup-model-routing/` and `skills/route-project/`.
- `model-routing-reference.md`, the explanation nothing imports.
- `model-routing-manifest.txt`, the list of everything above.

What this skill adds, each only with my approval:

- `"model": "fable"` so the main session starts on Fable.
- `"effortLevel": "xhigh"` for the main session.
- `"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "opus"}`, the catch-all for anything the hook does not see (agent teams, workflow agents, sessions that do not load user settings).

This skill writes no agent, rule, hook or skill file. `install.sh` owns those. If one is missing or broken, the fix is to rerun the installer.

## Rules for this run

1. Audit first. Change nothing until I approve the proposal in Phase 2.
2. Never drop a key from `settings.json`. Add to `env` and `hooks` if they exist; never replace them.
3. Before writing `settings.json`, back it up to `<config dir>/backups/model-routing-<YYYYmmdd-HHMMSS>/settings.json`, then write the new file through a temp file and move it into place.
4. Only use facts you read on this machine. If something is unclear, ask.
5. Keep the rules file lean. It loads into every session and every line costs tokens on every turn. Explanations belong in the reference doc.
6. Use the tiers during this run: do the Phase 1 inventory with `scout` and have it return a structured list.
7. No em dashes in anything you write.
8. `~/.claude` in this file means `$CLAUDE_CONFIG_DIR` when that variable is set. Use the real path in every command you run.

## Config facts (verified against the Claude Code docs, October 2026)

- `~/.claude/agents/` holds user agents, available in all projects. A project agent in `.claude/agents/` wins over a user agent with the same name. Claude Code scans both folders recursively, and two files with the same name are chosen by filesystem read order, so no copies of agent files belong in subfolders of `agents/`.
- Personal rules in `~/.claude/rules/` apply to every project on the machine.
- `~/.claude/settings.json` applies to every project. Project settings override it key by key.
- `CLAUDE_CONFIG_DIR` overrides the config directory (default `~/.claude`).
- Valid agent `model` values: `sonnet`, `opus`, `haiku`, `fable`, a full model ID such as `claude-opus-5-5`, or `inherit`. `inherit` means the main session's model.
- Subagent model order: the `model` parameter on the dispatch, then the agent file's `model`, then `CLAUDE_CODE_SUBAGENT_MODEL` ("the default model for subagents, agent team teammates, and workflow agents that aren't assigned a model another way"), then the main session's model. Under a Fable session an agent with no model, or with `inherit`, runs on Fable.
- `effort` values: `low`, `medium`, `high`, `xhigh`, `max`; the available levels depend on the model. Every agent pins `effort`, Haiku agents included; Haiku 5.5 takes the same effort levels as the other models. An agent without `effort` runs at the session's effort (observed; the docs do not say), and the dispatch hook blocks it.
- `effortLevel` in settings accepts `low`, `medium`, `high`, `xhigh`; not `max`. Default unset.
- `model` in settings is an alias or a full id. Default is the account's default model. Neither Fable model is the account default on any plan or provider; `"model": "fable"` selects it. Depending on plan and seat tier, Fable usage can bill to usage credits instead of plan limits.
- On the Anthropic API `opus` is Opus 5.5, `sonnet` is Sonnet 5.5, `haiku` is Haiku 5.5 and `fable` is Fable 5.1. Minimum Claude Code versions: Fable 5.1 v2.1.257, Opus 5.5 v2.1.280, Sonnet 5.5 v2.1.284, Haiku 5.5 v2.1.293.
- Subagents can spawn subagents up to three layers below the main conversation. `disallowedTools: Agent` stops an agent from delegating.
- Hooks: a `PreToolUse` command hook that exits 2 blocks the tool call and its stderr is the message Claude sees. `SessionStart` with matcher `startup` runs on a new session and its plain-text stdout is added as context. `timeout` is in seconds. `CLAUDE_PROJECT_DIR` is the project root. The dispatch hook matches the `Agent` tool; verified live on Claude Code 2.1.302.
- Where this setup applies: the terminal CLI and the Desktop app's Code tab, which read the same configuration files. Cloud sessions (Claude Code on the web and in the mobile app) do not read `~/.claude/` at all; they need repo-level `.claude/agents/` and settings. Terminal-dialog commands (`/hooks`, `/permissions`, `/plugin`) work only in the terminal CLI.

If anything you observe on this machine contradicts these facts, stop and tell me before continuing.

## Phase 0: Version check

Run `claude --version`. The docs state no minimum version for this setup as a whole. If the version is below 2.1.293, warn me that the `haiku` alias may not reach Haiku 5.5 on this build (the other aliases need 2.1.257 for Fable 5.1, 2.1.280 for Opus 5.5 and 2.1.284 for Sonnet 5.5), and offer the update before continuing. A native install updates with `claude update` (listed by `claude --help` on 2.1.302); reinstalling with `curl -fsSL https://claude.ai/install.sh | bash` also brings the current build. Do not continue past a warning without my answer.

## Phase 1: Audit (read-only)

Dispatch `scout` to collect the following and return it as a structured list, then summarize it for me:

1. `~/.claude/model-routing-manifest.txt`: does it exist? If not, stop. Tell me to run `./install.sh` from the repo checkout, then come back to this skill. Nothing below applies to an unfinished install.
2. Every path in the manifest exists on disk.
3. Every file in `~/.claude/agents/`: `name`, first line of `description`, `model` (or "none"), `effort` (or "none"). Flag any missing `name` or `description`, any `model` outside `sonnet`, `opus`, `haiku`, `fable`, a full model id, or `inherit`, and any `effort` outside `low`, `medium`, `high`, `xhigh`, `max`.
4. Any `.md` file below the top level of `~/.claude/agents/` (`find ~/.claude/agents -mindepth 2 -name '*.md'`).
5. `~/.claude/settings.json`: whether it parses as JSON, whether it holds the `PreToolUse` entry with matcher `Agent` and the `SessionStart` entry with matcher `startup`, and the current values of `model`, `effortLevel`, `env` and `enabledPlugins`.
6. `~/.claude/CLAUDE.md` and every file in `~/.claude/rules/`: any delegation, routing or model rules other than `model-routing.md`, quoted.
7. `python3 --version` (the dispatch hook needs it).
8. Whether `codex:codex-rescue` is in the available agents.
9. Whether `CLAUDE_CONFIG_DIR` is set, and to what.

## Phase 2: Proposal (stop here and wait for my approval)

Show me:

**A. Optional settings.** The current `~/.claude/settings.json` and the exact result after merging in:

```json
{
  "model": "fable",
  "effortLevel": "xhigh",
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "opus"
  }
}
```

Keep every existing key. If `env` exists, add to it. If `model`, `effortLevel` or `CLAUDE_CODE_SUBAGENT_MODEL` is already set to something else, flag it and ask me which value to keep. Remind me that Fable may bill to usage credits on some plans. I can say yes to all three, some, or none.

**B. Conflicts.** Any delegation or routing rule in `~/.claude/CLAUDE.md` or another rules file that overlaps or contradicts `rules/model-routing.md`, quoted, with a proposal to merge it into `model-routing.md` or remove it. I decide.

**C. Repairs.** Anything from Phase 1 that is missing or broken: a manifest path that is gone, an agent file with no `model` or `effort`, a hook entry missing from `settings.json`, an agent file in a subfolder. For installed files the repair is always "rerun `./install.sh`"; never rewrite an installed file from memory. For a stray file in a subfolder, propose moving it out of `agents/` and ask.

## Phase 3: Apply (only after I approve)

1. Back up `~/.claude/settings.json` to `~/.claude/backups/model-routing-<YYYYmmdd-HHMMSS>/settings.json` (run `date +%Y%m%d-%H%M%S` for the stamp; never guess it).
2. Write the merged settings through a temp file in the same folder, then move it over the original. If the existing file does not parse, stop and tell me instead of replacing it.
3. Apply approved rule merges from B, if any.
4. Nothing else. Repairs from C go through `install.sh`.

## Phase 4: Verify

1. Parse `~/.claude/settings.json` and show me `model`, `effortLevel`, `env.CLAUDE_CODE_SUBAGENT_MODEL` and the matchers under `hooks.PreToolUse` and `hooks.SessionStart`:

   ```bash
   python3 -c 'import json; s=json.load(open("'"$HOME"'/.claude/settings.json")); print(s.get("model"), s.get("effortLevel"), s.get("env", {}).get("CLAUDE_CODE_SUBAGENT_MODEL")); print([e["matcher"] for e in s["hooks"]["PreToolUse"]], [e["matcher"] for e in s["hooks"]["SessionStart"]])'
   ```

2. Test the dispatch hook from a shell and show me the results:
   - `echo '{"tool_name":"Agent","tool_input":{"subagent_type":"fast-worker","prompt":"x"}}' | python3 ~/.claude/hooks/require-agent-model.py; echo "exit $?"` prints nothing and exits 0.
   - `echo '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","prompt":"x"}}' | python3 ~/.claude/hooks/require-agent-model.py; echo "exit $?"` prints the block message on stderr and exits 2.
   - `echo '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","model":"haiku","prompt":"x"}}' | python3 ~/.claude/hooks/require-agent-model.py; echo "exit $?"` exits 0.
3. Run the nudge by hand from a project folder and show me the output: `CLAUDE_PROJECT_DIR="$PWD" bash ~/.claude/hooks/check-agent-models.sh`. It prints nothing when every project and user agent is pinned.
4. Tell me to start a new local session and check, using only things that work in every local surface:
   - The model shown in the UI is what I approved (terminal: `/model`; Desktop app Code tab: the model dropdown next to the send button). On a plain install it is my previous default.
   - Ask "which subagents are available to you?" and expect scout, fast-worker, judge, deep-reasoner, designer and verifier. (`ls ~/.claude/agents/` shows the same.)
   - Ask "read ~/.claude/settings.json and tell me the model, env, and hooks values" and expect the values from step 1. (`/hooks` shows this too, but only in the terminal CLI; the Desktop app replies "isn't available in this environment".)
   - Run `/context` and look for `model-routing.md` under memory files (terminal and cloud; not documented for the Desktop app).
5. List every file you created or changed, with the backup path.

## Codex on or off

The steps live in `~/.claude/model-routing-reference.md` under "Codex". Do not repeat them here. The rules file ships with `Codex: OFF`; turning it on is a one-line edit there plus the plugin install described in the reference.

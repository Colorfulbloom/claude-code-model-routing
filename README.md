# Claude Code model routing

A small set of files for Claude Code that sends each job to the cheapest model that can do it well. The main session plans and decides. Haiku searches, Sonnet builds, Opus leads features, and Fable handles design and verification. A hook blocks any dispatch that names no model. One installer puts it all under `~/.claude/` and backs up anything it replaces.

I wrote up why the setup looks like this in [One brief, one lead, one summary](https://jorgecalderon.codes/blog/one-brief-one-lead-one-summary).

## The shape

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

Every subagent's output lands in the context of whoever dispatched it. Handing a feature to one lead keeps the main session lean and pays the top rate only for planning and review.

## Tiers

| Agent | Model | Effort | Job |
|-------|-------|--------|-----|
| `scout` | Haiku | low | Search, inventories, test and lint runs, log and diff reading, quick web lookups. Read-only tools. |
| `fast-worker` | Sonnet | medium | Well-specified implementation, tests, docs. Cannot delegate. |
| `judge` | Sonnet | medium | Synthesis and judgment over gathered material, Chrome work. Read-only on files. Replaces the built-in general-purpose agent. |
| `deep-reasoner` | Opus | high | Feature lead, architecture, hard debugging, algorithms, high-risk code. Keeps per-repo memory. |
| `designer` | Fable | high | New or changed UI, visual design, design critique. Renders two or three directions and recommends one. |
| `verifier` | Fable | high | Verifies a lead's plan or report claim by claim against the project's sources. Read-only. |
| `tech-writer` (example, not installed) | Fable | medium | A project agent that drafts everything meant for a reader. See [The example project agent](#the-example-project-agent). |

The rules file assumes the main session runs on Fable. The installer does not set the main model; `/setup-model-routing` offers to.

## The two hooks

**`hooks/require-agent-model.py`** runs before every `Agent` tool call. It exits 2 when a dispatch passes no `model` and targets a built-in agent (`Explore`, `Plan`), an agent it cannot find, or an agent whose `model` is missing or `inherit`. It always blocks `general-purpose` (use `judge`), and it blocks any found agent with no pinned `effort`, even when a model is passed. Exit 2 means Claude Code cancels the tool call and shows the hook's message to Claude, which then passes a model and retries. Plugin agents (names with a `:`) and anything the hook cannot parse go through.

**`hooks/check-agent-models.sh`** runs once when a session starts. If the project's `.claude/agents/` has agents with no pinned model, it adds one line to the session context naming them and pointing at `/route-project`. Otherwise it prints nothing.

Both hooks are wired into `~/.claude/settings.json` by the installer. The full list of what the dispatch hook blocks, and how to relax it so it fills in a model instead of blocking, is in `docs/model-routing-reference.md`.

## Rules

- `rules/model-routing.md` is the routing policy. It loads into every session, so it stays short. The explanations live in the reference doc, which nothing imports.
- `rules/claude-in-chrome.md` is the tab-group etiquette for agents that use Claude in Chrome. It exists because `judge` and `designer` open tabs; if you never use Chrome you can delete it after install.

Personal rules in `~/.claude/rules/` apply to every project on your machine.

## Skills

- `/setup-model-routing`, run once after `install.sh`. It audits what the installer placed, then offers three optional global settings (main model `fable`, `effortLevel` `xhigh`, and `CLAUDE_CODE_SUBAGENT_MODEL=opus` as a catch-all) and applies them only after you approve.
- `/route-project`, run once in each project. It pins the project's own agents to a tier and checks that nothing in the project overrides the global setup.

Both skills are user-invoked only. Claude never runs them on its own.

## Prerequisites

- Claude Code with a Pro, Max, Team, Enterprise or Console account.
- Claude Code 2.1.302, the version this setup is tested on. Each model alias the files use has its own minimum, listed in the [model configuration docs](https://code.claude.com/docs/en/model-config). Fable 5.1 needs v2.1.257 or later, Opus 5.5 v2.1.280, Sonnet 5.5 v2.1.284 and Haiku 5.5 v2.1.293.
- bash (macOS's bash 3.2 works) and python3. No jq.
- The `design` plugin (1.2.0, by Anthropic), which the `designer` agent relies on. The agent preloads three of its skills, `design:design-critique`, `design:accessibility-review` and `design:design-system`, and can use its Figma tools (`mcp__plugin_design_figma__*`) when a project's Design section says "Figma: on". Without the plugin the designer still runs, but Claude Code skips the three preloaded skills and logs a warning, and the Figma tools are not there. The plugin's source is the [knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) repo, path `design`. Install it with `/plugin marketplace add anthropics/knowledge-work-plugins`, then `/plugin install design@knowledge-work-plugins`, or turn it on in your claude.ai account, which syncs it to Claude Code.
- Tested on macOS only. Linux is untested.

## Model access

The agent files pin the `haiku`, `sonnet`, `opus` and `fable` aliases. On the Anthropic API those resolve to Haiku 5.5, Sonnet 5.5, Opus 5.5 and Fable 5.1. If your plan or provider does not give you one of them, edit the `model:` line of that agent file before or after install.

Fable is never the account default on any plan or provider, so the files select it explicitly. Depending on your plan and seat tier, Fable usage can bill to usage credits instead of plan limits. Check your plan before you turn it on for the main session.

## Install

```bash
git clone https://github.com/Colorfulbloom/claude-code-model-routing.git
cd claude-code-model-routing
./install.sh --dry-run   # prints the plan, changes nothing
./install.sh
```

Then restart Claude Code so the hooks and agents load. Run `/setup-model-routing` once if you want the optional global settings, and `/route-project` inside each project that has its own agents.

A second run of `install.sh` changes nothing. Exit codes are 0 ok, 1 failure, 2 usage error.

## What the installer changes

Target is `$CLAUDE_CONFIG_DIR` when set, otherwise `~/.claude`. It copies:

- `agents/*.md` to `agents/` (flat, no subfolders)
- `rules/*.md` to `rules/`
- the two hooks to `hooks/`, mode 755
- the skills to `skills/setup-model-routing/` and `skills/route-project/`
- `docs/model-routing-reference.md` to `model-routing-reference.md`

It never overwrites silently. Every file it would replace is copied first to `<target>/backups/model-routing-<YYYYmmdd-HHMMSS>/` under the same relative path. It writes a manifest of what it placed to `<target>/model-routing-manifest.txt`.

It merges exactly two entries into `<target>/settings.json`, creating the file if it is missing. It backs up the old file to the same backup folder, writes through a temp file, skips entries already present, and keeps every other key and hook. If `settings.json` is not valid JSON it stops with exit 1 and changes nothing. It rewrites the file with two-space indentation, so a file formatted another way comes back reformatted, with keys, values and order unchanged.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/require-agent-model.py\"",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$HOME/.claude/hooks/check-agent-models.sh\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

With a custom `CLAUDE_CONFIG_DIR` the real path replaces `$HOME/.claude` in both commands.

The installer does not set `model`, `effortLevel` or `env.CLAUDE_CODE_SUBAGENT_MODEL`. Those are the three settings `/setup-model-routing` offers.

## Uninstall

```bash
./install.sh --uninstall
```

It removes the files listed in the manifest and the two hook entries, and leaves everything else alone. A file you edited after install is moved to `<target>/backups/model-routing-uninstall-<timestamp>/` instead of deleted, and `settings.json` is backed up there first. It does not restore the files an install replaced; those stay in the install backup folder, and you copy them back by hand if you want them.

## The example project agent

`examples/agents/tech-writer.md` is a project agent, not a global one, so the installer leaves it out. It drafts everything in a project that someone else will read, in the owner's voice, with sources and open questions, and never edits files.

To use it, copy it into a project's `.claude/agents/`, fill in the bracketed placeholders, and run `/route-project` there. The routing rule it supports is simple. Any agent that needs prose for a reader hands the drafting to the writer and keeps the technical substance for itself.

## Known limits

- **No copies in subfolders.** Claude Code scans `agents/` recursively, and two files with the same `name` are picked by filesystem read order, not by a documented precedence. Keep backups out of `~/.claude/agents/`. The installer writes its backups to `backups/` for this reason, and `find ~/.claude/agents -mindepth 2 -name '*.md'` should print nothing.
- **Cloud sessions.** Claude Code on the web and in the mobile app does not read `~/.claude/`, so none of this reaches those sessions. They need repo-level `.claude/agents/` and settings.
- **Platform.** Tested on macOS with bash 3.2.57, python3 and Claude Code 2.1.302. Linux is untested.

## Optional: Codex as a peer

The rules file ships with `Codex: OFF`. When it is on, Codex works next to `deep-reasoner` as a second engineer, through the `codex:codex-rescue` agent from the [Codex plugin for Claude Code](https://github.com/openai/codex-plugin-cc). It needs a ChatGPT subscription (Free included) or an OpenAI API key, and Node.js 18.18 or later. The on and off steps are in `docs/model-routing-reference.md` under "Codex".

## Read more

[One brief, one lead, one summary](https://jorgecalderon.codes/blog/one-brief-one-lead-one-summary) is the article behind this repo.

## License

MIT. Copyright 2026 Jorge Calderon. See `LICENSE`.

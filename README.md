# Claude Code model routing

A small set of files for Claude Code that sends each job to the cheapest model that can do it well. The main session plans and decides. A scout searches, a worker builds, a lead runs features, and a designer and a verifier handle design and checks. Each agent's model and effort are set at install. A hook blocks any dispatch that names no model. One installer puts it all under `~/.claude/` and backs up anything it replaces.

I wrote up why the setup looks like this in [Claude Code subagents on cheaper models](https://jorgecalderon.codes/blog/claude-code-subagents-on-cheaper-models).

## The shape

```
Main session
Plans, decides quick task vs feature, reviews summaries, makes the call. Never codes.
│
├── Quick tasks (one brief, fully specified): dispatch a worker directly
│   ├── fast-worker              small edit the session already has the plan for
│   ├── scout                    search, run tests, summarize logs
│   ├── judge                    weigh gathered material, Chrome checks
│   ├── deep-reasoner          a single hard question
│   └── project agents           pinned to their tier by /route-project
│
├── Design (new or changed UI): hand ONE brief to the designer; the owner picks
│   └── designer
│       └── scout, judge, fast-worker, the project writer
│
└── Features (anything needing more than one brief): hand ONE brief to the lead
    └── deep-reasoner as lead
        Plans, writes worker briefs, dispatches, verifies, returns ONE summary.
        └── fast-worker, scout, project agents

verifier: checks a plan or report before it reaches the owner
Codex: OFF. When ON, a peer next to deep-reasoner.
```

Every subagent's output lands in the context of whoever dispatched it. Handing a feature to one lead keeps the main session lean and pays the top rate only for planning and review.

## Agents

| Agent | Job |
|-------|-----|
| `scout` | Search, inventories, test and lint runs, log and diff reading, quick web lookups. Read-only tools. |
| `fast-worker` | Well-specified implementation, tests, docs. Cannot delegate. |
| `judge` | Synthesis and judgment over gathered material, Chrome work. Read-only on files. Replaces the built-in general-purpose agent. |
| `deep-reasoner` | Feature lead, architecture, hard debugging, algorithms, high-risk code. Runs HiveMind CONSOLIDATION at the end of each feature. |
| `designer` | New or changed UI, visual design, design critique. Renders two or three directions and recommends one. |
| `verifier` | Verifies a lead's plan or report claim by claim against the project's sources. Read-only. It is pinned to Opus at high effort. A dispatch passes `model: fable` only for plans and risky milestones. |
| `tech-writer` (example, not installed) | A project agent that drafts everything meant for a reader: docs, logs, tickets, commit messages and site copy. See [The example project agent](#the-example-project-agent). |

Each agent's `model` and `effort` are set in its frontmatter; the installer asks you to pick them (see [Choosing models](#choosing-models)). The installer does not set the main model; `/setup-model-routing` offers to.

`deep-reasoner` and `designer` also ask for a one-hour prompt cache, with `cacheTtl: 1h` under `experimental` in the frontmatter. Subagents get a five-minute cache by default. Both are leads that sit idle while their workers run, so their cache kept expiring. Each request after a gap of more than five minutes wrote the whole context to the cache again.

The other agents stay on five minutes, because my session logs showed a one-hour cache would cost them more than it saves. Claude Code ignores the `1h` while your subscription draws on usage credits, so the two leads get five minutes too. Fable usage can bill to usage credits on some plans, as [Model access](#model-access) explains.

## The hooks

**`hooks/require-agent-model.py`** runs before every `Agent` tool call. It exits 2 when a dispatch passes no `model` and targets a built-in agent (`Explore`, `Plan`), an agent it cannot find, or an agent whose `model` is missing or `inherit`. It always blocks `general-purpose` (use `judge`), and it blocks any found agent with no pinned `effort`, even when a model is passed. Exit 2 means Claude Code cancels the tool call and shows the hook's message to Claude, which then passes a model and retries. Plugin agents (names with a `:`) and anything the hook cannot parse go through.

**`hooks/check-agent-models.sh`** runs once when a session starts. If the project's `.claude/agents/` or the user `agents/` folder has agents with no model or effort, it adds a line per folder to the session context naming them, with `/route-project` as the fix for project agents and the two frontmatter lines for user agents. It then adds one line, `Model routing agents (model/effort): ...`, that lists the agents in the user folder and then the project folder as `name=model/effort` (`none` for a missing value). It prints nothing when neither folder has agents.

**`hooks/hivemind-inject.py`** runs on `SubagentStart`. It gives each subagent one-line records from the project's HiveMind store, once per agent, within that agent's token budget.

**`hooks/hivemind-capture.py`** runs on `SubagentStop`. It reads the HIVEMIND block from the agent's final reply and the agent's token use, and writes one file to the store's `inbox/`. A stop without an `agent_type` writes no file.

**`hooks/hivemind-guard.py`** runs before `Write`, `Edit`, `MultiEdit` and `NotebookEdit`. It denies a subagent's write to the store and to `.claude/rules/project-facts.md`, unless the agent is `deep-reasoner`.

**`hooks/hivemind_lib.py status`** runs on `SessionStart` with an empty matcher, so it fires on startup, resume, clear and compact. It prints one line when the store needs attention. On startup, clear and compact it also prints a short Recent work list from the feature history (not on resume).

The four HiveMind hooks do nothing in a project without `.claude/hivemind/`. All six entries are wired into `~/.claude/settings.json` by the installer. The full list of what the dispatch hook blocks, and how to relax it so it fills in a model instead of blocking, is in `docs/model-routing-reference.md`.

## HiveMind

HiveMind is a per-project memory that all agents share. It is opt-in and reviewed. Agents propose facts, one agent (`deep-reasoner`) decides which to keep, and the result is committed like code.

To opt a project in, run this from the project root:

```bash
python3 ~/.claude/hooks/hivemind_lib.py init
```

The store is committed and reviewed in each feature's diff. Only `inbox/` is ignored. Layout:

- `.claude/hivemind/config.json`: limits, topics and per-agent topic lists
- `.claude/hivemind/INDEX.md`: generated, never edited by hand
- `.claude/hivemind/topics/<topic>.md`: `testing`, `failed-briefs`, `dead-ends` and `token-tallies`
- `.claude/hivemind/tallies.json`: written by the script. `active-days.txt` is written by the script too but stays local (gitignored); active days also count commit dates from git
- `.claude/hivemind/archive/`: retired facts, never injected
- `.claude/hivemind/history/`: one entry file per feature, quarterly rollups, and a generated `INDEX.md`
- `.claude/hivemind/inbox/`: one file per subagent run, ignored by git
- `.claude/rules/project-facts.md`: the reviewed tier, approved by the owner

How facts flow:

1. When a subagent starts, the inject hook gives it one-line records (id, title, a SUSPECT flag if its evidence files changed) within a per-agent token budget. The full record stays in the topic file for the agent to read on demand. The main session gets no facts, only the Recent work list (see Feature history).
2. A subagent that has something to report ends its final reply with a block:

```
HIVEMIND
USED <id>[, <id>][: <note>]
VERIFIED <id>[, <id>][: <note>]
CONTRADICTS <id>: <observation>
NEW <topic>: <fact> | check: <command> | evidence: <path>[, <path>]
END HIVEMIND
```

3. The capture hook writes the parsed block to `inbox/`. Only the last block counts. There is no line or length limit: a USED or VERIFIED line may carry a note after the ids, and a NEW entry may span several lines. A block over 64KB is cut there and flagged `truncated`. Nothing is dropped: a line that does not parse, or a NEW that fails a rule (unknown topic, no evidence path inside the project root), goes to the run file's `unparsed` list with its reason, `status` reports how many wait, and `prep` lists them for CONSOLIDATION to salvage by hand. Lines that match a secret pattern are the one exception and are never stored.
4. At the end of each feature `deep-reasoner` runs CONSOLIDATION with `hivemind_lib.py`: `prep` reports the proposals, it edits `topics/*.md`, `apply` folds in the inbox and regenerates the index, `history add` records the feature, and `check` must pass.

Limits are in `config.json`. `INDEX.md` gets 50 lines, each topic about 4KB, the reviewed tier 60 lines, and each agent type an injection budget. The `token-tallies` topic is a generated table that grows a row for each kind, agent, model and effort, so it gets its own limit of 16KB (`tally_topic_max_bytes`). A fact expires after 28 active days unused. An active day is a day the project had commits or agent runs, so time away loses nothing. Any USED or VERIFIED resets the clock.

### Feature history

Facts are small and checkable. History records what a feature was: what was decided and rejected, which files and commits it touched, and what to do next. `deep-reasoner` adds one entry per feature. It sees the newest 15 index lines when it starts, and the main session sees the newest 8 at startup, clear and compact. Entries are data, not instructions.

```bash
python3 ~/.claude/hooks/hivemind_lib.py history template            # a draft skeleton
python3 ~/.claude/hooks/hivemind_lib.py history add draft.md        # or "-" for stdin; the draft starts with ### NEW <title>
python3 ~/.claude/hooks/hivemind_lib.py history link <id> <sha>     # replace "commit: pending" after the merge
python3 ~/.claude/hooks/hivemind_lib.py history rollup              # fold old quarters into rollup files when the index is over its cap
python3 ~/.claude/hooks/hivemind_lib.py related <path>...           # facts and entries that cite those paths
```

A code feature is recorded with `commit: pending (branch <name>)` before it merges. The status line lists entries that still wait for a commit, and the main session runs `history link` with the commit on development. `history add` refuses secrets and home directory paths, and `check` verifies every stored SHA and flags both in history files.

Token tallies from each run feed `topics/token-tallies.md`, which the cost gate in `rules/model-routing.md` reads. The figure is the harness's per-agent token figure (`tally_metric`, `context_final_plus_out` by default). Each round of an agent is one sample. A fresh agent's sample is its whole run. An agent resumed with SendMessage keeps its agent id. A new round starts only at a real brief after the agent stopped: a message from the coordinator, from a human, or from another agent that is not one of the agent's own workers. Harness nudges, background task notifications and the agent's own workers' reports wake the agent without starting a round, and the later capture of that round replaces its sample. The capture hook keeps per-agent state in `inbox/rounds/` (rows read, round, start row, kind) so the next capture knows where the last one stopped. Without it, the round is found by scanning the transcript for briefs. A later round's sample is its increase over the total at the start of the round, read from the transcript. It is filed under its own `Kind:` line, or under the previous round's kind when the brief has none (`untagged` only when round 1 had no `Kind:` line either), in a separate `<kind>+resumed` row, so resumes never move the fresh-dispatch medians. A round whose total did not grow (context compaction can shrink it) gives no sample, and `apply` says how many runs it skipped and why.

Each sample also records the agent's effort level and the round's duration in milliseconds. Rows are keyed by kind, agent, model and effort, so the table shows what each effort level costs, and its `med_time` column is the median duration as m:ss. The capture hook takes the effort from the SubagentStop payload. If the payload has none, it falls back to the agent's transcript, then to the `effort` pinned in the agent's file (the project's `.claude/agents` first, then `~/.claude/agents`). With none of those, the effort is `unknown`. The duration is the time between the first and last transcript timestamps of the round. That is wall time, so it includes the time an agent waits on its own workers. Rows from before effort was recorded move to effort `unknown`, and their samples have no duration.

Guardrails:

- Memory picks the order and subsets of tests, never whether the full suite runs.
- No secrets and no owner decisions. The secret scan redacts matching lines before anything is stored.
- The guard hook denies subagent writes to the store and to `.claude/rules/project-facts.md`. Promotion into `project-facts.md` is the owner's call.

## Rules

- `rules/model-routing.md` is the routing policy. It loads into every session, so it stays short. The explanations live in the reference doc, which nothing imports.
- `rules/file-reading.md` tells agents to read only the part of a file they need. It keeps reads from filling an agent's context. It has no `paths` frontmatter, so it loads into every session, like `model-routing.md`.
- `rules/claude-in-chrome.md` is the tab-group etiquette for agents that use Claude in Chrome. It exists because `judge` and `designer` open tabs; if you never use Chrome you can delete it after install.

Personal rules in `~/.claude/rules/` apply to every project on your machine.

## Skills

- `/setup-model-routing`, run once after `install.sh`. It audits what the installer placed, then offers three optional global settings (main model `fable`, `effortLevel` `xhigh`, and `CLAUDE_CODE_SUBAGENT_MODEL=opus` as a catch-all) and applies them only after you approve.
- `/route-project`, run once in each project. It pins the project's own agents to a tier and checks that nothing in the project overrides the global setup.

Both skills are user-invoked only. Claude never runs them on its own.

## Prerequisites

- Claude Code with a Pro, Max, Team, Enterprise or Console account.
- Claude Code 2.1.302, the version this setup is tested on. Each model alias the files use has its own minimum, listed in the [model configuration docs](https://code.claude.com/docs/en/model-config). Fable 5.1 needs v2.1.257 or later, Opus 5.5 v2.1.280, Sonnet 5.5 v2.1.284 and Haiku 5.5 v2.1.293.
- python3 3.9 or later. The installer uses only the standard library, and macOS's system python3 works. bash (3.2 works) runs the `install.sh` shim and the startup hook. No jq.
- The `design` plugin (1.2.0, by Anthropic), which the `designer` agent relies on. The agent preloads three of its skills, `design:design-critique`, `design:accessibility-review` and `design:design-system`, and can use its Figma tools (`mcp__plugin_design_figma__*`) when a project's Design section says "Figma: on". Without the plugin the designer still runs, but Claude Code skips the three preloaded skills and logs a warning, and the Figma tools are not there. The plugin's source is the [knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) repo, path `design`. Install it with `/plugin marketplace add anthropics/knowledge-work-plugins`, then `/plugin install design@knowledge-work-plugins`, or turn it on in your claude.ai account, which syncs it to Claude Code.
- Tested on macOS only. Linux is untested.

## Model access

The agent files pin the `haiku`, `sonnet`, `opus` and `fable` aliases by default. On the Anthropic API those resolve to Haiku 5.5, Sonnet 5.5, Opus 5.5 and Fable 5.1. If your plan or provider does not give you one of them, pick another model in the installer or edit the `model:` line of that agent file.

Fable is never the account default on any plan or provider, so a file selects it only when you choose it. The picker shows "may bill to usage credits" next to `fable`. Depending on your plan and seat tier, Fable usage can bill to usage credits instead of plan limits. Check your plan before you turn it on for the main session.

## Designer settings

The `designer` agent reads its project settings from a "Design" section in the project's CLAUDE.md. Any file in the CLAUDE.md hierarchy works, a `.claude/rules/*.md` file included, because subagents load that hierarchy.

The section names eight things. The design source (the design system, component library or mockups that count as the truth), the benchmark (the one existing screen every direction is held to), the components to reuse, Figma on or off, the writer agent that drafts the copy, where variants and screenshots go, who builds after the owner picks a direction, and the widths to render at.

Without a section the designer runs on defaults. Chrome only, Figma off, no writes to the project, widths 1440 and 375. For the settings that have no default it falls back and says so. No design source means it studies the project's existing screens and stylesheets. No benchmark means it names the best existing screen in the project as the benchmark. No writer agent means it drafts the copy itself and marks every line as draft copy. No builder means it reports the spec and stops. The top of its report lists the defaults and fallbacks it used, so you can see which settings a Design section would give you.

Whatever the section says, the designer never commits, never changes config and never touches a database. It builds only when the section allows it, and only after the owner picks a direction.

`examples/CLAUDE-design-section.md` is a template. Copy its `## Design` section into the project CLAUDE.md, fill in every bracket and delete the lines that do not apply.

## Install

```bash
git clone https://github.com/Colorfulbloom/claude-code-model-routing.git
cd claude-code-model-routing
./install.sh --dry-run   # prints the plan, changes nothing
./install.sh             # opens the picker, then installs
./install.sh --yes       # skips the picker and keeps the defaults or your saved choices
```

`install.sh` is a short shim. It checks for python3 3.9 or later and runs `install.py`, which does the work with the standard library only.

Then restart Claude Code so the hooks and agents load. Run `/setup-model-routing` once if you want the optional global settings, and `/route-project` inside each project that has its own agents.

A second run of `install.sh` with the same choices changes nothing. Exit codes are 0 ok, 1 failure, 2 usage error.

## What the installer changes

Target is `$CLAUDE_CONFIG_DIR` when set, otherwise `~/.claude`. It copies:

- `agents/*.md` to `agents/` (flat, no subfolders)
- `rules/*.md` to `rules/`
- the six hook files to `hooks/`, mode 755: `require-agent-model.py`, `check-agent-models.sh`, `hivemind_lib.py`, `hivemind-inject.py`, `hivemind-capture.py` and `hivemind-guard.py`
- the skills to `skills/setup-model-routing/` and `skills/route-project/`
- `docs/model-routing-reference.md` to `model-routing-reference.md`
- `model-routing-choices.json`, the model and effort you picked for each agent (see [Choosing models](#choosing-models))

It never overwrites silently. Every file it would replace is copied first to `<target>/backups/model-routing-<YYYYmmdd-HHMMSS>/` under the same relative path. It writes a manifest of what it placed to `<target>/model-routing-manifest.txt`.

It merges exactly six entries into `<target>/settings.json`, creating the file if it is missing. It backs up the old file to the same backup folder, writes through a temp file, skips entries already present, and keeps every other key and hook. If `settings.json` is not valid JSON it stops with exit 1 and changes nothing. It rewrites the file with two-space indentation, so a file formatted another way comes back reformatted, with keys, values and order unchanged.

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
      },
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/hivemind-guard.py\"",
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
      },
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/hivemind_lib.py\" status",
            "timeout": 10
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/hivemind-inject.py\"",
            "timeout": 10
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/hivemind-capture.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

With a custom `CLAUDE_CONFIG_DIR` the real path replaces `$HOME/.claude` in every command.

The installer does not set `model`, `effortLevel` or `env.CLAUDE_CODE_SUBAGENT_MODEL`. Those are the three settings `/setup-model-routing` offers. The installer never creates a HiveMind store; `init` does, per project.

## If you already have agents

Agents under your own file names stay as they are. The installer writes only its own file names and leaves every other file in `agents/` alone. The dispatch hook still applies to them, though. A dispatch to an agent whose file has no `model` or no `effort` in its frontmatter is blocked, and the session is told to pass a model and go on. The fix is to add both lines to the file. The startup hook lists these agents when a session starts, for the project's `.claude/agents/` and for `<target>/agents/`.

A file that has one of the six names we ship (`scout.md`, `fast-worker.md`, `judge.md`, `deep-reasoner.md`, `designer.md`, `verifier.md`) is replaced. If its content differs from ours, the installer copies it first to `<target>/backups/model-routing-<YYYYmmdd-HHMMSS>/` under the same relative path. The dry run prints `replace` and the backup path for each one, so you see it before anything moves. A file identical to ours is reported as `unchanged`.

A different file that declares one of those six `name` values gets a warning, one line per file, in the plan output and in the dry run. The installer continues anyway. The warning matters because Claude Code scans `agents/` recursively and, when two files share a `name`, loads one by filesystem read order and drops the other without a message. Either agent can win, and nothing tells you which one loaded. Rename the file's `name` or remove the file.

## Choosing models

On a terminal, `./install.sh` opens a picker for the model and effort of each of the six agents. The defaults are the values in the repo's `agents/*.md`. The picker uses curses. If curses is not available, or you pass `--plain`, it asks with numbered prompts instead. Model choices are `haiku`, `sonnet`, `opus`, `fable` or a typed model ID such as `claude-opus-5-5`. Effort choices are `low`, `medium`, `high`, `xhigh` and `max`. Next to `fable` the picker shows "may bill to usage credits". Cancelling changes nothing and exits 1.

The installer writes only the `model:` and `effort:` lines of each installed agent file. Everything else in the file is copied as is.

Flags for choosing:

- `-y`, `--yes` skips the picker.
- `--agent NAME=MODEL[:EFFORT]` sets one agent and can be repeated, for example `--agent scout=sonnet:low`. Without `:EFFORT` it keeps the current effort if the model allows it. `NAME` is a file name under `agents/` without `.md`, and `inherit` is not allowed.
- `--reset` ignores saved choices and starts from the repo defaults.
- `--plain` uses numbered prompts instead of curses.
- `--dry-run`, `--uninstall` and `-h`/`--help` work as before. `--agent` and `--reset` cannot be combined with `--uninstall`.

With no TTY, or with `CI` set, the installer behaves as if you passed `--yes`.

Order of precedence: repo defaults, then saved choices, then `--agent` values, then what you change in the picker. The installer prints one line, `Agent models: ...`, saying which of these applied.

Your choices are saved in `<config dir>/model-routing-choices.json`. A rerun preselects them. Uninstall removes the file, and an agent file you did not edit after install counts as unchanged and is removed with it.

## Tests

From the repo root:

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```

## Uninstall

```bash
./install.sh --uninstall
```

It removes the files listed in the manifest (the choices file included) and the six hook entries, and leaves everything else alone. A file you edited after install is moved to `<target>/backups/model-routing-uninstall-<timestamp>/` instead of deleted, and `settings.json` is backed up there first. The pre-install backup is never put back; if you want a replaced file again, copy it by hand from `<target>/backups/model-routing-<YYYYmmdd-HHMMSS>/`.

## The example project agent

`examples/agents/tech-writer.md` is a project agent, not a global one, so the installer leaves it out. It drafts everything in a project that someone else will read, in the owner's voice, with sources and open questions, and never edits files. Its model and effort are in its own frontmatter.

To use it, copy it into a project's `.claude/agents/`, fill in the bracketed placeholders, and run `/route-project` there. The routing rule it supports is simple. Any agent that needs prose for a reader hands the drafting to the writer and keeps the technical substance for itself.

## Dashboard

The Routing Dashboard is a local page that shows where your tokens went and which of your settings apply. It's read-only unless you start the server with `--allow-edits`. The Project dropdown picks one project, or All projects, the view across every project folder. Usage covers today, 7 days or 30 days.

- Overview. Usage in the project over the range you pick, read from its transcripts.
- Agents. Each agent's runs, tokens, estimated cost and cache, with the model and effort it ran with against its pin.
- Models. Usage by model, with the agents that ran on each.
- Sessions. Recent main sessions and the agents they spawned.
- Settings. What each value is set to and where it comes from.
- Needs attention. Values that don't apply as set, and ones the dashboard can't work out.
- Installed files. Files this repo installs into your Claude Code config, and whether each copy still matches.
- Rules reference. Every rule the dashboard applies, what backs it and the Claude Code version it was checked on.

The installer doesn't install the dashboard, so run it from a clone of this repo. It runs on Python 3.9 with the standard library alone. Start it from the folder of the project you want to see.

```bash
python3 /path/to/claude-code-model-routing/dashboard/server.py
```

It prints `http://127.0.0.1:8377/`, the address to open in your browser. Ctrl-C stops it. `--port N` changes the port, `--project DIR` picks another project, and `--config-dir DIR` picks another config folder. The default config folder is `CLAUDE_CONFIG_DIR`, else `~/.claude`.

The server binds 127.0.0.1 only. A default launch answers GET and HEAD only and writes no file. With `--allow-edits` it also answers POST on its edit routes, and it writes only the settings file you save and its backups. There's no login, because the page is local, but an edit needs the key from the link the flag prints.

To list more projects, add `routing-dashboard.json` to your config folder. `plan` is optional, and it takes `subscription`, `api_key` or `cloud_provider`. The file is read again on every request, so an edit needs no restart. Without it, the list holds the current project only.

```json
{"projects": [{"name": "my-app", "path": "/path/to/my-app"}], "plan": "subscription"}
```

Usage comes from your transcripts, through the dashboard's transcript reader. The reader parses each assistant line, keeps only the usage fields, and retains and writes nothing else. A test proves it. Cost is an estimate at API list price, and what you pay depends on your plan.

The [rules reference](docs/rules-reference.md) lists those fields, the files the reader takes, what a recorded effort level can't prove and every rule the dashboard applies.

### Edit settings with --allow-edits

`--allow-edits` turns on the server's edit routes, so a launch can change one setting, the main session's effort level. Without the flag nothing changes. The server stays read-only, and a POST to an edit route gets a 405.

```bash
python3 /path/to/claude-code-model-routing/dashboard/server.py --allow-edits
```

An edit changes `effortLevel` or `modelSettings.<name>.effortLevel`, on a line that already exists in a user, project or local settings file. It adds no line, creates no file and leaves every other byte alone. It never touches managed settings, and it refuses a symlink, a hard link or a file over 1 MiB.

The flag prints a different link, `http://127.0.0.1:8377/#/settings?edit=<key>`, with a key in the URL fragment. Only that link unlocks editing. The key lasts one launch, so the plain address, a bookmark or a link from an earlier launch stays read-only. A browser doesn't send a fragment to any server, and the server never logs the key.

Every save writes a backup first, to `routing-dashboard/backups/<target-id>/` in your config folder. Project and local files back up there too, so a backup never lands in a repo.

The flag refuses a `--fixture` folder inside this repo, so a save can't change a test fixture. Copy the fixture somewhere else first. It also won't start on Windows, which lacks the file calls the edit store needs.

A save fires [`ConfigChange` hooks](https://code.claude.com/docs/en/hooks#configchange). Claude Code watches its settings files and runs those hooks for each change it detects, so a save or an undo runs them in every session watching that file. A hook can block the change for its session, but the file on disk stays written and the dashboard can't see the result. This repo installs no such hook.

A saved effort change reaches a new session, not a running one. Claude Code [reads `effortLevel` and `modelSettings` once](https://code.claude.com/docs/en/settings#when-edits-take-effect), at session start. Use `/effort` to change a running session.

One narrow window stays open. The server compares the file's bytes just before it renames the new file into place, and it refuses the save if they changed. A write from another program after that check and before the rename is lost, and the backup won't hold it. The server can't lock Claude Code out of these files, so this is an accepted limit.

### Undo a save by hand

Once a file has changed since a save, the server won't undo that save, so the backup is the way back. Each settings file has its own folder in the backup store. The folder's name is the first 16 hex characters of the SHA-256 of the file's real path.

```bash
FILE=~/.claude/settings.json
STORE=~/.claude/routing-dashboard/backups/$(python3 -c 'import hashlib, os, sys; print(hashlib.sha256(os.fsencode(os.path.realpath(sys.argv[1]))).hexdigest()[:16])' "$FILE")
cat "$STORE/ledger.json"
```

Use your own config folder in `STORE` if it isn't `~/.claude`, and point `FILE` at the file you want back. The store sits in the config folder for project and local files too.

`ledger.json` in that folder lists the writes, oldest first, under `rows`. Each row describes one `.bak` file. Pick the row for the save you want to reverse.

- `time` is when the server wrote the row, in UTC.
- `kind` is `edit` for a save and `undo` for an undo.
- `layer` and `key_path` name the settings file and the setting.
- `old_value` and `new_value` show the change, masked.
- `backup` names the `.bak` file, a full copy of the settings file from just before this write.
- `before_sha256` is that backup's hash, and `after_sha256` is the file's hash right after the write.
- `restored_from` and `restored_from_backup` appear on an undo row. They name the row and the backup it copied back.

Put the row's backup back with `cp`, then compare with `cmp`, which prints nothing when the files match. A backup is the whole file, not one line. If something else changed the file since that save, restoring drops that change too, so read the `diff` first. If you want to keep it, change the one line by hand instead.

```bash
BACKUP="$STORE/<backup from the row>"
shasum -a 256 "$BACKUP"     # must equal the row's before_sha256
diff "$FILE" "$BACKUP"      # shows what you are about to replace
cp "$BACKUP" "$FILE"
cmp "$FILE" "$BACKUP"
```

Use `cp`, not `mv`, so the file keeps its mode and the backup stays in place. A hand restore counts as a settings change, so `ConfigChange` hooks fire again. The ledger doesn't record it. If you restored the newest row's backup, the next save drops that row and its backup, because the file already holds those bytes.

After an undo from the server, compare against the row's `restored_from_backup`, not its `backup`. The `backup` on an undo row holds the file from before the undo, so `cmp` reports a difference by design.

The store keeps the newest 20 rows per file, and an undo counts as one. Older rows go after the next successful write, and their backups go with them. Backups older than a `ledger.json` you moved aside stay until you delete them by hand. A backup is read-only to the page, because no route edits or deletes one.

Backups can hold secrets. The ledger masks its values, but a `.bak` file is an exact copy, and `settings.local.json` can hold API keys. The store's folders are mode 0700 and its files 0600. Keep those modes, and don't commit or paste a backup.

## Known limits

- **No copies in subfolders.** Claude Code scans `agents/` recursively, and two files with the same `name` are picked by filesystem read order, not by a documented precedence. Keep backups out of `~/.claude/agents/`. The installer writes its backups to `backups/` for this reason, and `find ~/.claude/agents -mindepth 2 -name '*.md'` should print nothing.
- **Cloud sessions.** Claude Code on the web and in the mobile app does not read `~/.claude/`, so none of this reaches those sessions. They need repo-level `.claude/agents/` and settings.
- **HiveMind guard.** It covers `Write`, `Edit`, `MultiEdit` and `NotebookEdit`, not shell redirects. The hook inputs were verified on Claude Code 2.1.305.
- **Platform.** Tested on macOS with bash 3.2.57, python3 and Claude Code 2.1.302. Linux is untested.

## Optional: Codex as a peer

The rules file ships with `Codex: OFF`. When it is on, Codex works next to `deep-reasoner` as a second engineer, through the `codex:codex-rescue` agent from the [Codex plugin for Claude Code](https://github.com/openai/codex-plugin-cc). It needs a ChatGPT subscription (Free included) or an OpenAI API key, and Node.js 18.18 or later. The on and off steps are in `docs/model-routing-reference.md` under "Codex".

## Read more

[Claude Code subagents on cheaper models](https://jorgecalderon.codes/blog/claude-code-subagents-on-cheaper-models) is the article behind this repo.

## License

MIT. Copyright 2026 Jorge Calderon. See `LICENSE`.

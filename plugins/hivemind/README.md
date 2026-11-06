# HiveMind plugin

HiveMind is a per-project memory that your Claude Code agents share. Agents propose facts, `deep-reasoner` decides which to keep, and the store is committed like code. This plugin gives you seven commands to look after that store from any session. You can see what waits, check the store, preview a consolidation, link history entries to their commits, turn HiveMind on and start a consolidation.

## What you need first

The plugin runs commands only. The HiveMind hooks that capture new facts, and the `deep-reasoner` agent that consolidates them, come from the installer in [claude-code-model-routing](https://github.com/Colorfulbloom/claude-code-model-routing). Run `./install.sh` from a clone.

The plugin carries its own copy of the HiveMind library, so its commands work even when the installed one is missing. Without the hooks, though, nothing captures new facts, and `/hivemind:status` says so.

## Install

Add the marketplace from GitHub, then install the plugin.

```bash
claude plugin marketplace add Colorfulbloom/claude-code-model-routing#development
claude plugin install hivemind@model-routing
```

In a session, run `/plugin marketplace add Colorfulbloom/claude-code-model-routing#development`, then `/plugin install hivemind@model-routing`. The second command opens a panel where you pick a scope.

A plugin you install from your shell loads the next time you start Claude Code. In a session that's already open, run `/reload-plugins`. An install from the panel ends with a summary that says whether the plugin is active yet.

To install from a local clone, add the clone's folder as the marketplace. Claude Code reads a local marketplace in place.

```bash
claude plugin marketplace add /path/to/claude-code-model-routing
claude plugin install hivemind@model-routing
```

To try the plugin for one session without installing it, start Claude Code with `--plugin-dir`.

```bash
claude --plugin-dir /path/to/claude-code-model-routing/plugins/hivemind
```

## Commands

Every command works on the store the hooks use, `.claude/hivemind/` in the current project.

| Command | What it does | Writes |
| --- | --- | --- |
| `/hivemind:status` | Shows the store, what waits in the inbox, history entries waiting for a commit, and whether a consolidation has work | No |
| `/hivemind:check` | Checks the store for problems, and says "check passed" when there are none | No |
| `/hivemind:inbox` | Previews what the next consolidation would fold in | No |
| `/hivemind:related <path>...` | Lists the facts and history entries that cite up to 20 paths | No |
| `/hivemind:link` | Lists the history entries still waiting for a commit | No |
| `/hivemind:link <id> <sha or base..head>` | Records the commit on a history entry | The entry and the history index |
| `/hivemind:init` | Creates the store and turns HiveMind on, and changes nothing when it's already on | `.claude/hivemind/` and `.claude/rules/project-facts.md` |
| `/hivemind:consolidate` | Sends `deep-reasoner` to run a consolidation when work waits | Topics, index and inbox, through `deep-reasoner`, left uncommitted |

`status` ends with one line that says whether a consolidation has work. It reads `consolidate: nothing to do`, `consolidate: work waiting (...)` or `consolidate: in progress (...)`. Work means inbox files, new fact records, expired facts or topic files over their limit. Hook errors show in `status` but don't count as work, and neither do SUSPECT facts.

`status` also checks the library your hooks run, at `~/.claude/hooks/hivemind_lib.py` (or under `$CLAUDE_CONFIG_DIR`). It adds a note when that file is missing or differs from the plugin's copy.

`link` checks that the commit exists in the project before it writes anything. When the project has a `development` branch and the commit isn't on it, `link` warns you and links it anyway. Review and commit what `init` and `link` write, the same as any other change to the store.

`related` takes its paths straight into a shell line, so quote a path that has a space, such as `/hivemind:related "docs/my notes.md"`.

Six of the commands run on Haiku, because they only relay what the library prints. `consolidate` runs on your session's model, because it decides on a dispatch.

### Which project a command uses

The commands use the same project the hooks see. That's `CLAUDE_PROJECT_DIR` when Claude Code sets it, so a session started in a linked worktree uses that worktree's copy of the store. Otherwise it's the main checkout, found through git.

## How consolidate works

`/hivemind:consolidate` first reads the same summary as `status`. On `consolidate: nothing to do`, the command says so and stops. It also stops on `consolidate: in progress`, because another consolidation is already running in that store.

When work waits, it states the dispatch plan with its expected cost. It waits for your yes only when your own routing rules ask for one on that dispatch. Then it sends `deep-reasoner` with a fixed brief that names the store. `deep-reasoner` reviews each proposed fact, edits the topic files, folds them in and runs `check` until it passes.

`deep-reasoner` turns down secrets and owner decisions. It lists any facts worth promoting to `.claude/rules/project-facts.md` and leaves that call to you. A manual consolidation writes no history entry, so its CONSOLIDATION line reports `history none`. The changes stay uncommitted, so you review the diff before anything lands.

The command tells Claude never to run a consolidation step itself. That's an instruction, not a block. The plugin's hook blocks only the wrapper, so `deep-reasoner` can still reach the installed library. If you have no `deep-reasoner` agent, the command says so and stops. The installer adds it.

## Sandbox

If a command fails with the sandbox on, add the wrapper to `sandbox.excludedCommands` in your user settings file, `~/.claude/settings.json`.

```json
{
  "sandbox": {
    "excludedCommands": ["python3 */bin/hivemind\" *"]
  }
}
```

A command on that list runs outside the sandbox, so the sandbox no longer limits it. The [sandboxing docs](https://code.claude.com/docs/en/sandboxing#run-commands-outside-the-sandbox-with-excludedcommands) explain how the list works.

## Permission rules

Each command approves only its own wrapper line. If one of your `ask` or `deny` rules matches `Bash(python3 ...)`, that rule wins and the command fails. The [skills docs](https://code.claude.com/docs/en/skills#permission-checks-on-injected-commands) cover how these checks work.

The wrapper runs only from your own commands. The plugin's PreToolUse hook refuses every call that matches `python3 *bin/hivemind*`, whether Claude, a subagent or a background agent makes it. That holds in every turn and in every permission mode, `bypassPermissions` included. So Claude can't run the wrapper even when you would approve it. The refusal tells Claude to ask you to run the HiveMind command instead.

The hook starts for Bash commands that match that pattern. It also starts for any command with `$()`, backticks or `$VAR`, and for one Claude Code can't parse. In those cases the guard splits the command into its parts and lets it through unless one part runs `python3` on `bin/hivemind`. So the guard leaves your other Bash calls alone. During a consolidation, `deep-reasoner` still runs its own HiveMind steps, because those call the installed library, not the wrapper. The hook uses the fields `if` and `onFailure`, and `onFailure` needs Claude Code 2.1.295 or later. The [hooks docs](https://code.claude.com/docs/en/hooks) explain both.

## Keeping the copy in step

The plugin's `payload/` folder holds a generated copy of `hooks/hivemind_lib.py`. `tools/build_plugins.py` builds it, and a test fails while the copy is out of date.

The `routing-dashboard` payload carries the same file. So a change to the library needs a version bump in both plugins' `plugin.json` before the build accepts it. The version pins installed users, so a change without a bump would never reach them.

```bash
python3 tools/build_plugins.py
python3 tools/build_plugins.py --check
```

## Update

```bash
claude plugin marketplace update model-routing
claude plugin update hivemind@model-routing
```

An update arrives only when the plugin's version number changes. A running session keeps the version it loaded, so start a new session or run `/reload-plugins`. After you update the plugin, rerun `./install.sh` from an up-to-date clone of the repo, or `status` notes that the two libraries differ.

## Uninstall

```bash
claude plugin uninstall hivemind@model-routing
```

Uninstalling removes the commands only. Each project's store and the installed hooks stay where they are, and the hooks keep capturing facts. `./install.sh --uninstall` removes the hooks.

## Requirements

- python3 3.9 or later on the PATH that Claude Code's shell sees. The wrapper uses the standard library only.
- git, for `link`.
- macOS. Linux is untested, and Windows isn't supported.

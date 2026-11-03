# Routing Dashboard plugin

The Routing Dashboard is a local page that shows where your Claude Code tokens went and which of your settings apply. This plugin runs it from any session with one command, `/routing-dashboard:dashboard`, and opens it in your browser.

The plugin runs the dashboard only. The routing agents, rules and hooks come from the installer in [claude-code-model-routing](https://github.com/Colorfulbloom/claude-code-model-routing). The dashboard works without them, and its Installed files view then lists those files as missing.

## Install

Add the marketplace from GitHub, then install the plugin.

```bash
claude plugin marketplace add Colorfulbloom/claude-code-model-routing#development
claude plugin install routing-dashboard@model-routing
```

In a session, run `/plugin marketplace add Colorfulbloom/claude-code-model-routing#development`, then `/plugin install routing-dashboard@model-routing`. The second command opens a panel where you pick a scope.

A plugin you install from your shell loads the next time you start Claude Code. In a session that's already open, run `/reload-plugins`. An install from the panel ends with a summary that says whether the plugin is active yet.

To install from a local clone, add the clone's folder as the marketplace. Claude Code reads a local marketplace in place.

```bash
claude plugin marketplace add /path/to/claude-code-model-routing
claude plugin install routing-dashboard@model-routing
```

To try the plugin for one session without installing it, start Claude Code with `--plugin-dir`.

```bash
claude --plugin-dir /path/to/claude-code-model-routing/plugins/routing-dashboard
```

## Use

`/routing-dashboard:dashboard` starts the dashboard for the current project and opens it at `http://127.0.0.1:<port>/`. It tries port 8377 first and takes a free port when 8377 is busy. A second session in the same project reuses the running server. When no other command is named `/dashboard`, the short form works too.

Add an action after the command for anything else, such as `/routing-dashboard:dashboard status --all`.

- `start` starts the server and opens the page. It's the default.
- `stop` stops this project's server. `stop --all` stops every server the plugin started.
- `reload` restarts the server with the same project and mode, on the same port when it's free.
- `status` shows this project's server, with its address, mode, start time, plugin version and number of sessions. `status --all` shows every server.
- `open` opens this project's page again, read-only.
- `project <dir>` starts a server for another project folder. A path with a space doesn't work, because the command splits its arguments on spaces.
- `edits` restarts the server with editing on.
- `log` prints the last 40 lines of the server's log.

`--port N` sets the port for `start`, `project` or `edits`, and the command fails rather than pick another one. When a server for the project already runs on another port, `start` and `project` keep that server and say so. To change its port, run `stop` first.

`--no-open` skips the browser for `start`, `project`, `edits` and `reload`. `--key-file` saves the edit link to a file, for `edits` and `reload`.

Over SSH, or on Linux with no display, the command doesn't try to open a browser and says so.

## Edit settings

`edits` restarts the server with `--allow-edits` and sends the edit link straight to your browser. The link holds a key, and the key never appears in the conversation. What an edit can change, and how saves are backed up, is in the main README under [Edit settings with --allow-edits](https://github.com/Colorfulbloom/claude-code-model-routing#edit-settings-with---allow-edits).

Over SSH there's no browser to send the link to, so run `edits --key-file` instead. It saves the link to a file only you can read, in the plugin's data folder, and prints the file's path. Forward the dashboard's port to your own machine, then open the link from that file.

```bash
ssh -L <port>:127.0.0.1:<port> <host>
```

The file holds the key, so delete it when you're done. `stop` and `reload` delete it too.

## When the server stops

A server belongs to the Claude Code processes that ran the command in its project. When the last of them exits, the plugin's one hook, on SessionEnd, stops the server. `/clear` and switching sessions with `/resume` don't stop it, because Claude Code itself keeps running. So a server two Claude Code processes share keeps running until both have exited.

If Claude Code crashes, the hook doesn't run. The next dashboard command you run usually notices the server nobody uses any more, stops it and says so. `stop` always works.

A server you start by hand, by running the launcher from a terminal, is marked manual. The hook never stops it, but `stop` and `stop --all` do.

## Sandbox

With Claude Code's sandbox on, the command fails. The launcher has to write to its data folder, run `ps` and listen on a port, and the sandbox blocks that. To fix it, add the launcher to `sandbox.excludedCommands` in your user settings file, `~/.claude/settings.json`.

```json
{
  "sandbox": {
    "excludedCommands": ["python3 */bin/routing-dashboard\" *"]
  }
}
```

A command on that list runs outside the sandbox, so the sandbox no longer limits it. The [sandboxing docs](https://code.claude.com/docs/en/sandboxing#run-commands-outside-the-sandbox-with-excludedcommands) explain how the list works.

## Permission rules

The skill approves only its own launcher line. If one of your `ask` or `deny` rules matches `Bash(python3 ...)`, that rule wins and the command fails. The [skills docs](https://code.claude.com/docs/en/skills#permission-checks-on-injected-commands) cover how these checks work.

## Update

```bash
claude plugin marketplace update model-routing
claude plugin update routing-dashboard@model-routing
```

An update arrives only when the plugin's version number changes. A running session keeps the version it loaded, so start a new session or run `/reload-plugins`. Then run `/routing-dashboard:dashboard reload` so a running server picks up the new code. `status` flags a server that still runs older code.

A marketplace added with `#development` keeps following the development branch. Once the plugin is on main, stop every server, then remove the marketplace and add it again without `#development`. Removing it deletes the plugin's data folder, which is why the servers stop first.

## Uninstall

Stop every server first, because uninstalling deletes the plugin's data folder, and a running server would lose its record. In a session, run `/routing-dashboard:dashboard stop --all`. Then uninstall from your shell.

```bash
claude plugin uninstall routing-dashboard@model-routing
```

`claude plugin marketplace remove model-routing` also uninstalls the plugin and deletes its data folder, so stop the servers before that too. Disabling the plugin with `/plugin disable` leaves running servers alone but turns the hook off, so stop them first there as well.

## Trust

A plugin runs code with your user privileges. The [plugin security page](https://code.claude.com/docs/en/plugins/security) says so plainly. "A Claude Code plugin you install can execute arbitrary code on your machine with your user privileges."

This plugin starts a Python server on 127.0.0.1 only, so it's reachable from your own machine and no other. The server writes a file only in edit mode, and then only the settings file you save and its backups. The plugin keeps its server records and logs in its data folder.

While the command runs, Claude can't use Bash at all. So it can't run the launcher again with another action, such as `edits` or `stop`.

## Requirements

- python3 3.9 or later on the PATH that Claude Code's shell sees. The dashboard uses the standard library only.
- macOS. Tested on Claude Code 2.1.302. Linux is untested, and Windows isn't supported.

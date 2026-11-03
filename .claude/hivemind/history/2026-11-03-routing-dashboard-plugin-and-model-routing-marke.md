### F-3600 routing-dashboard plugin and model-routing marketplace
status: in-progress
kind: code
dates: 2026-11-03 .. 2026-11-03
refs:
  commit: pending (branch feature/routing-dashboard-plugin)
summary: The repo is a plugin marketplace (model-routing) with one plugin, routing-dashboard 0.1.0, that starts and stops dashboard servers from any session
decisions:
- Plugin root is plugins/routing-dashboard with the generated copy under payload/, so the default skills/ and agents/ scans never see the installer's files; payload is committed with a drift test (owner answer)
- One SessionEnd hook, exec form; ownership is the Claude Code process (CLAUDE_PID, used only when it is an ancestor, plus its ps lstart), so /clear and /resume keep the server; reasons clear and resume are ignored
- The hook hands the work to a detached _end worker and returns at once, because SessionEnd has a 1.5 s budget a plugin can't raise
- Launcher exits 0 with an "error:" line in skill mode, because a non-zero exit aborts the skill before the model sees it (sandbox probe)
- Skill sets disallowed-tools: Bash, because allowed-tools also lets the model rerun the launcher with no prompt in that turn (sandbox probe); the ! line still runs
- server.py --launch-fd carries the URL (and "error: port-in-use") on a pipe, so the edit key never reaches the log; exit 1 on a busy port is kept because test_busy_port pins it
- Version guard: payload/BUILD.json records version and hash; the build refuses a changed payload until plugin.json's version goes up, since the version pins installed users
- Build lists sources with git ls-files only when the repo top level is the repo itself, else walks
- install.py unchanged: a new installer message needs a parity allowance (I-44e3)
rejected:
- Session-id ownership with a SessionEnd matcher: after /clear the old id never ends, so the server would leak
- A distinct server exit code for a busy port: test_busy_port pins exit 1
- webbrowser.open: it falls through to the next browser when the first fails, so a failing BROWSER stub opened real tabs; get().open is used
- Repo root as plugin root, monitor, MCP wrapper, SessionStart start: as in the source plan
files: dashboard/server.py, plugins/routing-dashboard/bin/routing-dashboard, plugins/routing-dashboard/skills/dashboard/SKILL.md, plugins/routing-dashboard/hooks/hooks.json, tools/build_plugins.py, .claude-plugin/marketplace.json, tests/test_plugin_launcher.py, tests/test_plugin_build.py, README.md, plugins/routing-dashboard/README.md, tests/test_server_launch.py, tests/test_plugin_e2e.py, tests/test_edit_security.py
gotchas:
- With sandbox.enabled the ! line runs sandboxed (DATA writes, bind and ps fail with EPERM); excludedCommands "python3 */bin/routing-dashboard\" *" fixes it
- Every change to dashboard/, agents/, rules/, hooks/, skills/, install.py, agent_md.py or the reference doc needs a version bump and python3 tools/build_plugins.py
- webbrowser.open falls through to macOS open when a BROWSER stub exits 1
follow-ups:
- Owner E2E from the pushed branch: MR_E2E=1 MR_PLUGIN_SOURCE=Colorfulbloom/claude-code-model-routing#feature/routing-dashboard-plugin
- hivemind plugin as a second marketplace entry
- Linux untested: a console-only browser could block the ! line

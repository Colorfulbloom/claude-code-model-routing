# Skill permission probe

The probe checks that only the user's own command can run the routing-dashboard launcher. The skill's `!` line has to run every time, even when two dashboard commands come back to back. Any other call to the launcher has to be refused, whether the main session, a subagent or a background agent makes it. Other Bash commands still have to work.

The plugin ships that guard as a PreToolUse hook in `plugins/routing-dashboard/hooks/hooks.json`. It matches `Bash(python3 *bin/routing-dashboard*)` and runs the launcher's hidden `guard` action, which denies the call. The skill itself carries no deny rule.

## When to run it

Run it after every Claude Code upgrade. Claude Code decides when hooks fire and how a skill's rules reach other agents, so a new release can change either one. Run it too before you change the `allowed-tools` line in `plugins/routing-dashboard/skills/dashboard/SKILL.md`, or the PreToolUse entry in `plugins/routing-dashboard/hooks/hooks.json`.

## Running the probe

Run it from the repo root.

    python3 tools/skill_probe/probe.py

One run makes no real API call. It prints the Claude Code version, a pass or fail table, and two lines that say whether the shipped skill and hooks.json still match what the probe tested.

The probe has five options.

- `--root DIR` works under `DIR` and keeps it afterward. `DIR` must be new or empty.
- `--keep` keeps the throwaway folder even when the run passes.
- `--variant bare|narrow|shipped|all` picks what to probe. The default is `all`.
- `--bypass` runs `claude` with `--permission-mode bypassPermissions`, so the guard is tested in the mode that skips permission prompts. It works only with `--variant shipped`.
- `-v` prints what each command did, not only the table.

## What it checks

The probe writes a plugin with two skills and runs `claude -p --input-format stream-json` with five user turns in one process. Both skills copy the shipped skill's `!` line and `allowed-tools` rule. Then `scriptapi.py` plays the model. It answers each request with a scripted tool call and logs what Claude Code sends back. A fake launcher logs every run, and it hands the `guard` action to the shipped launcher, so the real guard is under test. The probe counts a refusal as the hook's only when it carries the guard's own reason. A guard that crashes is blocked too, and Claude Code also reports that as a PreToolUse error, but it fails the `shipped` column instead of passing it.

The table has a row for each check and a column for each variant.

- `shipped` has no deny rule and the shipped PreToolUse hook. It's the setup the plugin ships, and the exit code depends on it.
- `narrow` is `disallowed-tools: Bash(python3 *bin/routing-dashboard*)`, the rule the skill used to ship.
- `bare` is `disallowed-tools: Bash`, the plainest deny.

It runs seven checks.

- The `!` line runs, and its output reaches the model.
- The main session, later in the skill's turn, can run `echo` but not the launcher.
- A foreground subagent in that turn can run `echo` but not the launcher.
- A background agent started inside the turn can run `echo` but not the launcher.
- A background agent started before the skill can run `echo` but not the launcher during the turn. After the turn the launcher still must not run.
- In the next turn, `echo` runs and the launcher doesn't.
- Two dashboard commands in a row both run their `!` line.

In `shipped`, the hook refuses every launcher call outside the `!` line, in the skill's turn and in the next one. A call the probe expects inside the skill's turn has to land before that turn ends. A result that arrives later shows as `late` and fails the check.

## The old rules, for comparison

The `narrow` and `bare` columns record how the old `disallowed-tools` rules behaved, and they're for information only. A change there prints a note but doesn't fail the run.

A `disallowed-tools` deny lasts until the next user message, and a slash command counts as that message. But the next command's own `!` line runs before the deny clears. So under `narrow`, the second of two back-to-back commands is denied, and the commands alternate between denied and working. That alternation is why the plugin moved to the hook. On Claude Code 2.1.302, PreToolUse never fired for a skill's `!` line, so the user's command always ran. The hooks docs don't cover this, which is one more reason to run the probe after every upgrade.

`bare` blocks all Bash in the turn and takes the Bash tool away from subagents.

## Exit codes

- `0` means every `shipped` check passed.
- `1` means a `shipped` check failed. The lines under the table name the command, what the probe expected and what it saw. The files stay in the folder the probe prints.
- `2` means the probe refused to run or couldn't finish. For example, `claude` isn't on `PATH`, or a turn didn't finish within 90 seconds.

## Safety

The probe never talks to the real API and never reads or writes your real home or `~/.claude`.

- `claude` gets a throwaway `HOME`, config folder and project under `$TMPDIR` or under the `--root` folder, plus a fake API key. Its API address points at `scriptapi.py`, which listens on 127.0.0.1 only.
- It refuses to start if `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_BASE_URL` is set in your shell. That check and the fixed values come from `dashboard/experiments/harness/runcase.py`.
- It refuses to run if `HOME` or `CLAUDE_CONFIG_DIR` would be your real home, or would be or overlap your real `~/.claude`. It checks the final values, right before `claude` starts.
- It never reads your real settings or transcripts.

## One check depends on timing

This applies to the `narrow` and `bare` columns. A background agent started before the skill can get either of two answers when it calls the launcher after the turn. If the skill also started its own background agent, the call is still denied until the next user message. Without that second agent, the same call needs approval instead. The probe accepts both, because in both cases the launcher doesn't run.

The expected outcomes sit in `EXPECTED` in `probe.py`, recorded on Claude Code 2.1.302.

## Files

- `probe.py` runs the turns for each variant and prints the table.
- `scriptapi.py` is the scripted fake API. The steps it understands are listed at the top of the file.

Both live under `tools/`, outside the plugin payload, so changing them doesn't change the plugin's version.

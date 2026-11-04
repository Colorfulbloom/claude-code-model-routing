# Skill permission probe

This probe checks how a skill's `disallowed-tools` rule reaches the main session, subagents and background agents. The routing-dashboard skill depends on it. Its front matter denies `Bash(python3 *bin/routing-dashboard*)` so the model can't run the launcher itself, while the skill's own `!` line still runs and other Bash commands still work.

## When to run it

Run it after every Claude Code upgrade, and before you change the `disallowed-tools` or `allowed-tools` lines in `plugins/routing-dashboard/skills/dashboard/SKILL.md`.

## Command

From the repo root.

    python3 tools/skill_probe/probe.py

It takes about a minute. It makes no real API call.

Options.

- `--root DIR` works under `DIR` and keeps it. `DIR` must not exist or must be empty.
- `--keep` keeps the throwaway root of a passing run.
- `--variant bare|narrow|both` picks what to run. The default is `both`.
- `-v` prints what each command did, not only the table.

## What it checks

It writes a plugin with one skill, then runs `claude -p --input-format stream-json` with three user turns in one process. The skill has the same `!` line and `allowed-tools` rule as the shipped skill. `scriptapi.py` plays the model. It answers each request with a scripted tool call, and logs the result Claude Code gives back.

The table has one row for each check, and one column for each deny rule.

- `bare` is `disallowed-tools: Bash`, kept for comparison.
- `narrow` is `disallowed-tools: Bash(python3 *bin/routing-dashboard*)`, the rule the skill ships.

The six checks.

- The `!` line runs. Its output reaches the model.
- The main session, later in the same turn. `echo` runs and the launcher is denied.
- A foreground subagent in the turn. Same expectation.
- A background agent started inside the turn. Same expectation.
- A background agent started before the skill. Same expectation during the turn. After the turn the launcher must not run, and `echo` runs again once the next user message arrives.
- The next turn. `echo` runs, and the launcher needs approval, so it does not run.

For `bare`, a pass means Bash is blocked the way it was when the probe was written. That column is information only.

## Exit codes

- `0` means every `narrow` check passed.
- `1` means a `narrow` check failed. The lines under the table say which command did what. The files stay in the folder the probe prints.
- `2` means the probe refused to run or could not finish, for example because `claude` is not on `PATH`, or a turn timed out.

## Safety

- It refuses to start if `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_BASE_URL` is set in your shell. It reuses the check and the fixed environment values from `dashboard/experiments/harness/runcase.py`.
- It refuses to run if `HOME` or `CLAUDE_CONFIG_DIR` would be, or sit inside, your real home or `~/.claude`. It checks the final values, right before `claude` starts.
- `claude` gets a throwaway `HOME`, config folder and project under `$TMPDIR`, and a fake API key. `scriptapi.py` listens on 127.0.0.1 only.
- It never reads your real settings or transcripts.

## Recorded behavior

Recorded on Claude Code 2.1.302. The expected outcomes sit in `EXPECTED` in `probe.py`.

One result depends on timing. When the skill starts its own background agent, a background agent started before the skill is still denied for about three seconds after the turn ends, until the next user message. Without that second agent the same call needs approval instead. The probe accepts both, because in both cases the launcher does not run.

## Files

- `probe.py` runs the three turns for each variant and prints the table.
- `scriptapi.py` is the scripted fake API. The steps it understands are listed at the top of the file.

Both live under `tools/`, not `dashboard/`, so they are not part of the plugin payload and don't change its version.

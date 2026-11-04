# Skill permission probe

The probe checks how a skill's `disallowed-tools` rule reaches the main session, subagents and background agents. The routing-dashboard skill depends on that rule. Its front matter denies `Bash(python3 *bin/routing-dashboard*)`, so the model can't run the launcher itself. The skill's own `!` line still runs, and other Bash commands still work.

## When to run it

Run it after every Claude Code upgrade. Claude Code decides how far the rule reaches, so a new release can change it. Run it too before you change the `disallowed-tools` or `allowed-tools` line in `plugins/routing-dashboard/skills/dashboard/SKILL.md`.

## Running the probe

Run it from the repo root.

    python3 tools/skill_probe/probe.py

One run takes about a minute and makes no real API call. It prints the Claude Code version, a pass or fail table, and a line that says whether the shipped skill's `disallowed-tools` still matches the rule it probed.

The probe has four options.

- `--root DIR` works under `DIR` and keeps it afterward. `DIR` must be new or empty.
- `--keep` keeps the throwaway folder even when the run passes.
- `--variant bare|narrow|both` picks the rules to probe. The default is `both`.
- `-v` prints what each command did, not only the table.

## What it checks

The probe writes a plugin with one skill and runs `claude -p --input-format stream-json` with three user turns in one process. The skill copies the shipped skill's `!` line and `allowed-tools` rule. Then `scriptapi.py` plays the model. It answers each request with a scripted tool call and logs what Claude Code sends back.

The table has a row for each check and a column for each deny rule.

- `bare` is `disallowed-tools: Bash`, kept for comparison.
- `narrow` is `disallowed-tools: Bash(python3 *bin/routing-dashboard*)`, the rule the skill ships.

It runs six checks.

- The `!` line runs, and its output reaches the model.
- The main session, later in the skill's turn, can run `echo` but not the launcher.
- A foreground subagent in that turn can run `echo` but not the launcher.
- A background agent started inside the turn can run `echo` but not the launcher.
- A background agent started before the skill can run `echo` but not the launcher during the turn. After the turn the launcher still must not run, and `echo` works again once the next user message arrives.
- In the next turn, `echo` runs. The launcher needs approval, and since `-p` mode has no one to approve it, it doesn't run.

A call the probe expects inside the skill's turn has to land before that turn ends. A result that arrives later shows as `late` and fails the check.

The `bare` column records how a plain `Bash` deny behaved when the probe was written. It blocks all Bash in the turn and takes the Bash tool away from subagents. That column is for information only, and a change there prints a note but doesn't fail the run.

## Exit codes

- `0` means every `narrow` check passed.
- `1` means a `narrow` check failed. The lines under the table name the command, what the probe expected and what it saw. The files stay in the folder the probe prints.
- `2` means the probe refused to run or couldn't finish. For example, `claude` isn't on `PATH`, or a turn didn't finish within 90 seconds.

## Safety

The probe never talks to the real API and never reads or writes your real home or `~/.claude`.

- `claude` gets a throwaway `HOME`, config folder and project under `$TMPDIR` or under the `--root` folder, plus a fake API key. Its API address points at `scriptapi.py`, which listens on 127.0.0.1 only.
- It refuses to start if `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_BASE_URL` is set in your shell. That check and the fixed values come from `dashboard/experiments/harness/runcase.py`.
- It refuses to run if `HOME` or `CLAUDE_CONFIG_DIR` would be your real home, or would be or overlap your real `~/.claude`. It checks the final values, right before `claude` starts.
- It never reads your real settings or transcripts.

## One check depends on timing

A background agent started before the skill can get either of two answers when it calls the launcher after the turn. If the skill also started its own background agent, the call is still denied until the next user message. Without that second agent, the same call needs approval instead. The probe accepts both, because in both cases the launcher doesn't run.

The expected outcomes sit in `EXPECTED` in `probe.py`, recorded on Claude Code 2.1.302.

## Files

- `probe.py` runs the three turns for each rule and prints the table.
- `scriptapi.py` is the scripted fake API. The steps it understands are listed at the top of the file.

Both live under `tools/`, outside the plugin payload, so changing them doesn't change the plugin's version.

# Resolution fixtures

Each folder here is one fixture for the dashboard's settings resolver. It sets up a config dir, a project and a session, then says which value should win for each key. Fixtures use made-up data only. There's no runner yet, and #5 adds it.

## Files in a fixture

- `config/` is the Claude config dir, with `settings.json` and `agents/`. Agent files here sit in the user layer, and they may sit in subfolders such as `config/agents/a/`.
- `project/` is the project, with `.claude/settings.json` and `.claude/settings.local.json`.
- `session.json` holds the shell environment (`shell_env`), the flags (`flags`) and any `--settings` content (`cli_settings`).
- `dashboard.json` is the dashboard's own config. A fixture adds it only when the case depends on the plan, and its `plan` is `subscription`, `api_key` or `cloud_provider`. Without the file the plan is unset.
- `expected.json` holds the rule ids, the confidence, the source and the expected resolution.

A fixture includes only the files its case needs.

## The expected resolution

Each entry in `expect` gives the key, the value, its status, its layer and the file it came from. For example, `status` is `in_effect` for the winner and `overridden` for a value it beat. `file` is relative to the fixture folder, such as `project/.claude/settings.json`. Each entry also has a `scope`, such as `main`.

An `expected.json` may also carry a `note`, a sentence on why an entry expects what it does when that is not plain from the rule.

`source` points to the experiment record and case behind the fixture, for example `dashboard/experiments/2026-10-29-env-block-order.json#m6`. `claude_version` is the Claude Code version the result was checked on.

## Agent file entries

An entry for an agent file uses the key `agentFile` and names the agent in `agent`. Its value is `null`, because the file is what loads, not a setting. The layer is `project`, `user` or `plugin`, and the file is the agent file's path, such as `project/.claude/agents/probe.md`.

Three extra fields can appear on these entries. `other_file` names the second file when two files declare one name, and each entry names the other. `field` names the frontmatter field Claude Code doesn't read, on an `ignored` entry that sits beside the `in_effect` entry for the same file. `via` names the environment variable behind an `env` entry, such as `FORCE_PROMPT_CACHING_5M`.

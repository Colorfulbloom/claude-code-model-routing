# Resolution fixtures

Each folder here is one fixture for the dashboard's settings resolver. It sets up a config dir, a project and a session, then says which value should win for each key. Fixtures use made-up data only. There's no runner yet, and #5 adds it.

## Files in a fixture

- `config/` is the Claude config dir, with `settings.json` and `agents/`.
- `project/` is the project, with `.claude/settings.json` and `.claude/settings.local.json`.
- `session.json` holds the shell environment (`shell_env`), the flags (`flags`) and any `--settings` content (`cli_settings`).
- `expected.json` holds the rule ids, the confidence, the source and the expected resolution.

A fixture includes only the files its case needs.

## The expected resolution

Each entry in `expect` gives the key, the value, its status, its layer and the file it came from. For example, `status` is `in_effect` for the winner and `overridden` for a value it beat. `file` is relative to the fixture folder, such as `project/.claude/settings.json`. Each entry also has a `scope`, such as `main`.

`source` points to the experiment record and case behind the fixture, for example `dashboard/experiments/2026-10-29-env-block-order.json#m6`. `claude_version` is the Claude Code version the result was checked on.

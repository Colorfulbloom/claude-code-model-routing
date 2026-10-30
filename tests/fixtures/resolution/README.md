# Resolution fixtures

Each folder here is one fixture for the dashboard's settings resolver, `dashboard/resolve.py`. It sets up a config dir, a project and a session, then says which value should win for each key. Fixtures use made-up data only.

Run them all with `/usr/bin/python3 dashboard/resolve.py`. It prints `<name>: ok` or the mismatches for each fixture, and exits 1 when any fixture fails. `tests/test_resolve.py` runs the same fixtures, one test each.

## Files in a fixture

- `config/` is the Claude config dir, with `settings.json`, `agents/` and `rules/`. Agent files here sit in the user layer, and they may sit in subfolders such as `config/agents/a/`.
- `project/` is the project, with `.claude/settings.json`, `.claude/settings.local.json`, `.claude/agents/` and `.claude/rules/`.
- `managed/` is the managed settings folder, and it is optional. It may hold `managed-settings.json` and a `managed-settings.d/` folder of drop-in files. The runner reads it, never the real managed folder.
- `session.json` holds the shell environment (`shell_env`), the flags (`flags`) and any `--settings` content (`cli_settings`).
- `dashboard.json` is the dashboard's own config. A fixture adds it only when the case depends on the plan, and its `plan` is `subscription`, `api_key` or `cloud_provider`. Without the file the plan is unset.
- `expected.json` holds the rule ids, the confidence, the source and the expected resolution.

A fixture includes only the files its case needs.

## The expected resolution

Each entry in `expect` gives the key, the value, its status, its layer, the file it came from and its scope. For example, `status` is `in_effect` for the winner and `overridden` for a value it beat.

One convention names the file and the key, so the runner can compare them as written.

- `file` is relative to the fixture folder, such as `project/.claude/settings.json`.
- A value from the shell environment has the layer `env` and the file `session.json:shell_env`. A value set by an `env` block in a settings file has the layer of that file and the file itself. The variable's row then reads the winning value, with the layer `env` and the settings file as its file.
- A flag has the layer `flag` and the file `session.json:flags`. A `--settings` file has the layer `cli` and the file `session.json:cli_settings`.
- The default layer has the file `null`.
- An entry whose value came from a real file also carries `line`, the line of that value in the file. A shell value, a default and the fixture-only labels (`session.json:flags`, `session.json:cli_settings` and `session.json:shell_env`) carry no `line`.
- A `modelSettings` entry uses the key of the row it feeds (`effortLevel` for the main session, `effort` for an agent, `autoCompactWindow` or `maxEffortLevel`) and the scope of that row, not `model`. Its `path` names the entry, such as `modelSettings.opus.effortLevel`, and its `model` names the catalog id.
- A `via` field names the environment variable behind an `env` or `default` entry, such as `FORCE_PROMPT_CACHING_5M`.
- A `becomes` field holds what a lowered value runs as, or the clamp on an auto-compact window. A `raw` field holds the text an agent's `model` field had when it was `inherit`.
- Rows with no winner get one `default` entry (layer `default`, file `null`). Its value is the model's default effort for an effort row, a rule's `default_value`, or `null`.

An entry may also carry `rule_id` and `reason`, the rule behind it and its rendered sentence. Name them when a fixture shows which rule explains an entry, such as an overridden value, a clamp or a default.

An `expected.json` may also carry a `note`, a sentence on why an entry expects what it does when that is not plain from the rule.

`source` points to the experiment record and case behind the fixture, for example `dashboard/experiments/2026-10-29-env-block-order.json#m6`. `claude_version` is the Claude Code version the result was checked on.

## Agent file entries

An entry for an agent file uses the key `agentFile` and names the agent in `agent`. Its value is `null`, because the file is what loads, not a setting. The layer is `project`, `user` or `plugin`, and the file is the agent file's path, such as `project/.claude/agents/probe.md`.

When an agent file's `agentFile` entry is `unknown` because the dashboard's reader rejects its frontmatter, the agent's `model`, `effort`, `autoCompactWindow` and `subagentPromptCacheTtl` rows can't be read either. The winning entry of each of those rows becomes `unknown` when the agent layer ranks above it, or when the row has only a default. It keeps its value, layer and file, and it takes the `rule_id`, `rule_ids` and `reason` of the `agentFile` entry.

Three extra fields can appear on these entries. `other_file` names the second file when two files declare one name, and each entry names the other. `field` names the frontmatter field Claude Code doesn't read, on an `ignored` entry that sits beside the `in_effect` entry for the same file. `via` is described above.

## How the runner compares

The runner groups entries by row, which is the key, the scope and the agent.

- For every row the expected file names, the runner's entries for that row must pair one to one with the expected entries. A row with a different number of entries fails.
- Each field an expected entry has must equal the runner's field. The runner may carry extra fields, such as `rule_id`, `rule_ids` and `reason`, and the expected entry may leave them out. When an expected entry names `rule_id` or `reason`, the runner's value must equal it. `rule_id` is the rule that explains the entry, and `reason` is the sentence rendered from it.
- Rows the file doesn't name aren't checked.
- The runner's `rule_ids` on an entry list the rules that voted the entry's final status, the most specific first. A winning entry (and an overridden one) then adds the row's order rule, the rule that supplies the row's layer order and combine, with no repeats. An overridden entry also lists any rule that voted it overridden. `rule_id`, the first one, is the rule the reason uses. For an overridden entry that is the order rule.
- Every id in the file's `rule_ids` must appear in the `rule_ids` of an entry in a row the file names. List the rules that voted those entries, and the order rules, not every rule of the row.

Messages name the fixture, the row and the field, such as `row effortLevel/main: value expected "low", got "high"`.

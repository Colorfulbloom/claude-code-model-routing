# Rules reference

The dashboard shows each setting's value with a status word and a reason. This page defines those words, lists what the dashboard reads and what it can't see, and then lists every rule it applies.

## Status words

Every value on screen has one of seven statuses. The status says whether the value counts, and the reason says why.

- In effect. What a new session or agent starts with, before any launch flag or dispatch parameter. A `CLAUDE_CODE_AUTO_COMPACT_WINDOW` value below 100000 shows In effect too, with the value it runs at, because Claude Code raises it to 100000 ([model config, Values and warnings for CLAUDE_CODE_AUTO_COMPACT_WINDOW](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)).
- Overridden. Set here, but another source wins.
- Ignored. Set here, but Claude Code doesn't read it in this case.
- Invalid. Claude Code doesn't accept the value.
- Lowered. Used, but run at a lower level, because of a cap or because the model lacks the level ([model config, Adjust effort level](https://code.claude.com/docs/en/model-config#adjust-effort-level)). A `CLAUDE_CODE_AUTO_COMPACT_WINDOW` value above 1000000 shows Lowered too, because Claude Code runs it at 1000000 ([model config, Values and warnings for CLAUDE_CODE_AUTO_COMPACT_WINDOW](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)).
- Default. Nothing sets it, so the model's or Claude Code's own value applies.
- Unknown. The dashboard can't name the winner, and the reason says why.

## Confidence words

Every rule has one of three confidence words, and each rule names the Claude Code version it was checked on.

- Documented. The Claude Code docs say so, and the rule links the page.
- Tested. Checked on the version the rule names, with the experiment recorded in `dashboard/experiments/`. A Tested rule can quote the docs too, when the test confirms them or covers what they leave out.
- Assumed. Neither the docs nor a test backs the whole rule yet. The screen shows it differently from the other two.

## What the dashboard reads

The dashboard works out each value from these sources, for the main session and for every agent. The Settings page shows the main session's model, effort, cache lifetime and compact window.

- Settings files. The user file `~/.claude/settings.json`, the project's `.claude/settings.json` and `.claude/settings.local.json`, and the managed settings file ([settings, Settings files and who they affect](https://code.claude.com/docs/en/settings#settings-files-and-who-they-affect)). When several set a key, Claude Code takes the highest, in the order managed, `--settings`, local, project, user ([settings, Settings precedence](https://code.claude.com/docs/en/settings#settings-precedence)). Some keys follow their own order, and their rules say so.
- Managed settings file. The dashboard reads only the file-based managed settings. On macOS, that's `/Library/Application Support/ClaudeCode/managed-settings.json` and the `.json` files in the optional `managed-settings.d/` folder beside it ([managed settings, Where each mechanism stores the policy](https://code.claude.com/docs/en/managed-settings#where-each-mechanism-stores-the-policy)). Claude Code merges `managed-settings.json` first, then the folder's files in alphabetical order ([managed settings, Split a file-based policy across teams](https://code.claude.com/docs/en/managed-settings#split-a-file-based-policy-across-teams)). Mobile device management (MDM) and server-managed settings rank above these files, but the dashboard doesn't read them, so they're under What the dashboard can't see. The record is [dashboard/experiments/2026-10-29-managed-settings-macos.json](../dashboard/experiments/2026-10-29-managed-settings-macos.json).
- Shell. The environment variables of the shell the dashboard starts in. A value from there shows the source Shell, and the What decides panel adds the note "Read when the dashboard started. A session from another terminal may differ." Claude Code reads shell variables when it starts, so a change counts from the next launch ([environment variables, Precedence](https://code.claude.com/docs/en/env-vars#precedence)).
- Env blocks. The `env` block in each settings file. Its value overwrites the same variable from the shell, and when several files set a variable, the highest file wins ([settings reference, How env values interact with your shell](https://code.claude.com/docs/en/settings-reference#how-env-values-interact-with-your-shell)). Tested on 2.1.302, with the record in [dashboard/experiments/2026-10-29-env-block-order.json](../dashboard/experiments/2026-10-29-env-block-order.json). The value shows its settings file as the source.
- Agent files. The files in `~/.claude/agents/` and the project's `.claude/agents/`, subfolders included, because Claude Code scans both recursively ([sub-agents, Choose the subagent scope](https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope)). The dashboard reads each file's frontmatter with a strict reader. Claude Code loads some frontmatter that reader rejects, so a rejected file that loads, or one in a form nobody has tested, shows Unknown. Tested on 2.1.302, with the record in [dashboard/experiments/2026-10-29-agent-files.json](../dashboard/experiments/2026-10-29-agent-files.json).
- Rules folders. The files in `~/.claude/rules/` and the project's `.claude/rules/`. Claude Code loads the `.md` files there, a project's subfolders included ([memory, Set up rules](https://code.claude.com/docs/en/memory#set-up-rules)). It loads user rules first, and neither set overrides the other ([memory, User-level rules](https://code.claude.com/docs/en/memory#user-level-rules)). So the dashboard will list each file with its scope and pick no winner.
- Plan. The optional `plan` field in the dashboard's own config, set to `subscription`, `api_key` or `cloud_provider`. The main conversation's default cache lifetime depends on how the account is billed ([prompt caching, Which TTL each request gets](https://code.claude.com/docs/en/prompt-caching#which-ttl-each-request-gets)). With `api_key` or `cloud_provider`, the dashboard shows five minutes. With `subscription` or no field, it shows Unknown, because it can't tell whether usage credits are in use.

## What the dashboard reads from transcripts

The dashboard reads transcripts for its usage numbers and for the effort level each request ran at. One module, the reader, does that work ([dashboard/transcripts.py](../dashboard/transcripts.py)), and one rule covers it.

The reader parses each assistant line, keeps only the usage fields, and retains and writes nothing else. A test proves it.

Transcripts hold what passed through a session, file contents, command output and pasted text included. So the reader copies a fixed list of fields into a record and drops the row. A line has to be read and parsed before its fields can be picked out, so content sits in memory for a moment. Nothing else leaves that step.

The file and effort details below come from [the findings on #14](https://github.com/Colorfulbloom/claude-code-model-routing/issues/14#issuecomment-6497135617) and [the findings on #8](https://github.com/Colorfulbloom/claude-code-model-routing/issues/8#issuecomment-6505920567), on Claude Code 2.1.302. Items marked Inferred don't come from the docs or a test. They come from what #14 saw on one machine, or what [#49](https://github.com/Colorfulbloom/claude-code-model-routing/issues/49) found in the Claude Code 2.1.302 package.

### Which fields it keeps

A record holds these 21 fields and nothing else from the row. They're what the rule means by usage fields, a fixed list and not only token counts.

- Ids. `message_id` from `message.id`, and `request_id` from `requestId`.
- Time. `ts_utc` from `timestamp`.
- Session. `folder`, the transcript folder's name, and `session_id` from `sessionId`, else the session id in the file path.
- Agent. `run_id`, the `<agentId>` in `agent-<agentId>.jsonl`, with none for a main file. `agent_type`, which is `agentType` from the meta file. `is_sidechain` from `isSidechain`, else true for an agent file.
- Model and effort. `model_raw` from `message.model`, and `effort` from the top-level `effort`.
- Place. `cwd` from `cwd`, and `git_branch` from `gitBranch`.
- Tokens. `input` from `usage.input_tokens`, `output` from `usage.output_tokens`, `cache_read` from `usage.cache_read_input_tokens`, and `thinking` from `usage.output_tokens_details.thinking_tokens`.
- Cache writes. `cache_write_5m` and `cache_write_1h` from `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` in `usage.cache_creation`. Any remainder of `usage.cache_creation_input_tokens`, or all of it when there's no split, counts as 5-minute.
- Price labels. `speed` from `usage.speed`, `service_tier` from `usage.service_tier`, and `inference_geo` from `usage.inference_geo`.

Not all of these are numbers. `cwd` is a path, `git_branch` is a branch name and `agent_type` is the agent's name. The dashboard uses `cwd` to name a folder that isn't on the project list, and `git_branch` for the session line "On {branch} in {project}." So a record can hold a path or a branch name you chose. It holds no message text, tool data or agent description.

### How the rule holds

The reader checks each line before it keeps anything. A line whose bytes lack `"assistant"` isn't parsed at all. A line that only quotes the word is parsed, fails the type check and is dropped. Files open with `open(path, "rb")`, and nothing is written. Records sit in a per-file cache in process memory, so they last only while the dashboard runs.

These tests prove it.

- Records. `test_marker_appears_in_no_record` plants a marker in message text, tool inputs, thinking and an agent meta description. The marker appears in no record ([tests/test_transcripts.py](../tests/test_transcripts.py)).
- Responses. `test_planted_text_appears_in_no_response` plants a marker in message text, a tool input, a tool result and agent descriptions. The marker appears in no dashboard response and nothing the server prints ([tests/test_api_usage.py](../tests/test_api_usage.py)).
- Disk. `test_a_read_adds_or_changes_nothing_under_the_config_dir` reads twice and finds the config folder unchanged, with every file opened as `"rb"` ([tests/test_transcripts.py](../tests/test_transcripts.py)).
- Source. `test_module_source_has_no_write_calls` finds no write call in the reader's source, and every `open` there uses `"rb"` ([tests/test_transcripts.py](../tests/test_transcripts.py)).

### Which files it takes

The reader takes main, agent and set-aside transcripts last changed in the past 61 days. It looks in every project folder under `<config_dir>/projects`, whether or not the folder is on the dashboard's project list. The config folder is `--config-dir`, else `CLAUDE_CONFIG_DIR`, else `~/.claude`.

- Main session. `<config_dir>/projects/<project-dir>/<sessionId>.jsonl` ([.claude directory, Application data](https://code.claude.com/docs/en/claude-directory#application-data)).
- Agents. `<config_dir>/projects/<project-dir>/<sessionId>/subagents/agent-<agentId>.jsonl`. The sub-agents docs say "Each transcript is stored as `agent-{agentId}.jsonl`" ([sub-agents, Resume subagents](https://code.claude.com/docs/en/sub-agents#resume-subagents)).
- Set-aside files. `<sessionId>.orphaned-<timestamp>-<suffix>.jsonl` and `<sessionId>.jsonl.superseded-<timestamp>` in the project folder, matched by exact pattern. The docs list both as a previous transcript that Claude Code set aside instead of overwriting or deleting it ([.claude directory, Cleaned up automatically](https://code.claude.com/docs/en/claude-directory#cleaned-up-automatically)). They may hold requests that really were sent and sit in no current file, so the reader takes them.
- Repeated rows. A row that repeats counts once, by id. A set-aside row with neither a message id nor a request id is dropped and counted. Nobody has checked whether real set-aside files repeat rows or add them.
- Agent meta files. The reader takes only `agentType` from `agent-<agentId>.meta.json`. A missing or unreadable meta file gives no agent type, and the agent shows as Unnamed agent.
- Older files. A file whose modified time is older than 61 days is skipped and counted. The 61 days cover the 30-day range and the 30 days before it. Rows are only added to a file, so an older file holds only older rows.
- Deleted files. Claude Code's cleanup can remove a transcript once it's older than `cleanupPeriodDays`, 30 days by default ([.claude directory, Cleaned up automatically](https://code.claude.com/docs/en/claude-directory#cleaned-up-automatically)). That includes main, agent and set-aside files. The reader can't see a removed file, so the 61 days only reach as far as what's still on disk. A comparison with an earlier period can come up short, or show No earlier data to compare.
- Everything else. Symlinks are never followed. Anything else under `projects/` is ignored and counted.
- Project folder name. Inferred. On the machine #14 checked, every character that isn't a letter or digit becomes "-". Past 200 characters, Claude Code keeps the first 200 and adds "-" and a hash, a limit #49 took from the Claude Code 2.1.302 package. The docs show one example, `/home/user/work/my-repo` as `-home-user-work-my-repo`, but state no rule ([.claude directory, Clear local data](https://code.claude.com/docs/en/claude-directory#clear-local-data)).

### Which effort field

The reader takes one effort field, the top-level `effort` on assistant rows. It doesn't read `params.output_config.effort` on `api-request` rows, `perTurnEffort`, Agent tool `input.effort` or the effort in a meta file.

The rules predict what a session starts with, and the transcript shows what it ran at, so together they check the rules. The Overview's Tokens by effort level card and the Ran with column on the Agents page show the recorded level. So does each agent's page, in a line such as "Ran with {model} at {effort}."

Four harness cases wrote normal assistant rows, the ones where the fake API sent a text reply ([dashboard/experiments/harness/README.md](../dashboard/experiments/harness/README.md)). In all four, the top-level `effort` equals the level in the request, a lowered level included. Under a project cap of low, an agent pinned at high and a main session at `--effort high` both recorded low ([dashboard/experiments/2026-10-29-effort-cap-transcript.json](../dashboard/experiments/2026-10-29-effort-cap-transcript.json)). On Opus 4.6, xhigh ran as high, and the assistant rows of the main session and an agent recorded high ([dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json)).

The other cases that sent a request got an error from the fake API. Their assistant rows have no top-level `effort`, even when the request carried a level. So those cases say nothing about a normal assistant row.

### What the cost means

Every cost on screen is an estimate at API list price. The dashboard prices each request from its token counts and [dashboard/prices.json](../dashboard/prices.json), which also names the pricing page and the date the prices were checked. What you pay depends on your plan.

A request with no list price shows Not priced, and totals leave it out. That covers any `service_tier` other than missing or `standard`.

### What the field can't prove

The field shows the level that ran, a lowered one included, but not why it ran at that level. A recorded level doesn't say where it came from. A difference from the rules means a rule is wrong, or something the files can't show was in play, such as `/effort` during the session.

The Pin check column has a limit of its own. It reads today's files, so a run from before a file change can show Differs or Pin overridden.

A missing field can mean more than one thing. Claude Code sends no level on a model without effort levels, such as Haiku 4.5 ([model config, Adjust effort level](https://code.claude.com/docs/en/model-config#adjust-effort-level)). It sends none with `CLAUDE_CODE_EFFORT_LEVEL=auto` either ([model config, Send no effort level](https://code.claude.com/docs/en/model-config#send-no-effort-level)). The harness shows those requests carried no level ([dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json), [dashboard/experiments/2026-10-29-effort-auto.json](../dashboard/experiments/2026-10-29-effort-auto.json)). But no test has covered a normal assistant row with no level sent. So a missing field doesn't prove no level was sent.

The page shows Not recorded, or "effort not recorded" inside a sentence. When an agent's expected level is known but no run recorded one, effort adds nothing to its Pin check.

Older transcripts may have no effort field at all. #14 found effort fields in agent transcripts from 2.1.229 and in main sessions by 2.1.260. That's Inferred, from the transcripts on one machine.

A check against `/effort status` is weaker on 2.1.302. Before v2.1.304, it printed `Effort level: auto (currently high)` even while no level was sent ([model config, Send no effort level](https://code.claude.com/docs/en/model-config#send-no-effort-level)).

## What the dashboard can't see

Some sources change a session after it starts, and others sit outside what the dashboard reads. So a value the dashboard shows as In effect can still change when one of these applies.

- Launch flags. The flags a session started with, such as `--model`, `--effort`, `--autocompact` and `--agents`. Each can change what runs. For example, `--model` beats `ANTHROPIC_MODEL` and the `model` setting ([CLI reference, CLI flags](https://code.claude.com/docs/en/cli-reference#cli-flags)).
- `--settings` content. JSON passed with `--settings`, inline or as a file path, ranks above the user, project and local files and below managed settings ([settings, Change a setting for one session](https://code.claude.com/docs/en/settings#change-a-setting-for-one-session)). It's a launch flag, so the dashboard can't see it in phase 1.
- MDM and server-managed settings. On macOS, MDM policy lives in the `com.anthropic.claudecode` managed preferences domain, and Anthropic's servers or a gateway hold server-managed settings ([managed settings, Where each mechanism stores the policy](https://code.claude.com/docs/en/managed-settings#where-each-mechanism-stores-the-policy)). Both rank above the managed settings file. By default, Claude Code uses the highest-ranked source that sets a policy and skips the rest ([managed settings, How Claude Code combines managed sources](https://code.claude.com/docs/en/managed-settings#how-claude-code-combines-managed-sources)). So a policy from either one can replace what the dashboard shows from the file.
- `/effort` in a running session. A level picked with `/effort` or the `/model` picker beats `--effort` and every settings file, though not `CLAUDE_CODE_EFFORT_LEVEL` ([model config, Adjust effort level](https://code.claude.com/docs/en/model-config#adjust-effort-level)). A pick saved as the default lands under `modelSettings` in the user settings file, where the dashboard reads it for new sessions. A pick for this session only, a `max` pick or a pick in a `-p` run stays in that session. To check one, run `/effort status` there.
- Dispatch parameters. When Claude starts a subagent, it can pass a model alias and an effort level for that run. Both beat the agent's frontmatter, though `CLAUDE_CODE_EFFORT_LEVEL` still beats the effort ([sub-agents, Choose a model](https://code.claude.com/docs/en/sub-agents#choose-a-model); [sub-agents, Choose an effort level](https://code.claude.com/docs/en/sub-agents#choose-an-effort-level)). The effort parameter needs v2.1.292 or later.
- Mod hooks. A mod's `agent.spawn` hook can choose a subagent's model, and Claude Code uses it in place of the dispatch model ([sub-agents, Choose a model](https://code.claude.com/docs/en/sub-agents#choose-a-model); [mods reference, Subagents](https://code.claude.com/docs/en/plugins/mods/reference#subagents)). The docs list a model, not an effort, for this hook.
- Another terminal's environment. The dashboard reads the shell it starts in. A session started from another terminal reads that terminal's variables when it starts, so its values may differ ([environment variables, Precedence](https://code.claude.com/docs/en/env-vars#precedence)). That's why a Shell value carries the note "Read when the dashboard started. A session from another terminal may differ."
- Usage credits. On a subscription, the main conversation's default cache lifetime is one hour within plan usage and five minutes once usage credits start ([prompt caching, Which TTL each request gets](https://code.claude.com/docs/en/prompt-caching#which-ttl-each-request-gets)). An agent's `experimental.cacheTtl` of `1h` is ignored while usage credits are in use ([sub-agents, Frontmatter reference](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields)). The dashboard can't tell whether a session is drawing on usage credits, so those lifetimes show Unknown on a subscription or with no plan set.

<!-- rules -->

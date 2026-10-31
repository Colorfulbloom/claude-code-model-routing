> This page is generated from dashboard/rules.json and dashboard/reference_copy.md. Do not edit it by hand. Regenerate it with `/usr/bin/python3 dashboard/reference_page.py`.

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

## What the dashboard will read from transcripts

Planned for phase 1 and not built yet. The dashboard will read transcripts for one thing, the effort level the latest session and its agents ran at. It will show that level in the Last session column. The rules predict what a session starts with, and the transcript shows what it ran at, so together they check the rules. On October 29 I decided the dashboard will read effort fields only and store nothing.

The details below come from [the findings on #14](https://github.com/Colorfulbloom/claude-code-model-routing/issues/14#issuecomment-6497135617) and [the findings on #8](https://github.com/Colorfulbloom/claude-code-model-routing/issues/8#issuecomment-6505920567), on Claude Code 2.1.302. Items marked Inferred come from what #14 saw on one machine, not from the docs or a test.

### Which field

The dashboard will read `params.output_config.effort` on `api-request` rows, the level in the request Claude Code sent. It's the field the harness used to prove the level that ran ([dashboard/experiments/2026-10-29-effort-cap-transcript.json](../dashboard/experiments/2026-10-29-effort-cap-transcript.json)). The docs list request parameters among what a transcript holds ([.claude directory, Application data](https://code.claude.com/docs/en/claude-directory#application-data)).

Assistant rows, Agent tool calls and agent meta files carry effort too, as #14 found, but the dashboard won't read them. Attachment rows mention `effort` only inside a tool schema, so the dashboard will skip them.

### Where the transcripts are

The dashboard will read the latest main-session transcript for each project and that session's agent transcripts. It won't read older sessions.

- Main session. `~/.claude/projects/<project-dir>/<sessionId>.jsonl` ([.claude directory, Application data](https://code.claude.com/docs/en/claude-directory#application-data)).
- Agents. `~/.claude/projects/<project-dir>/<sessionId>/subagents/agent-<agentId>.jsonl`. The sub-agents docs say "Each transcript is stored as `agent-{agentId}.jsonl`" ([sub-agents, Resume subagents](https://code.claude.com/docs/en/sub-agents#resume-subagents)).
- Latest session. Inferred. It's the newest `<sessionId>.jsonl` directly in the project folder, skipping `*.orphaned-*` and `*.superseded-*` files. The docs describe those two as set-aside copies but don't say how to find the latest session. This rule found the session where I ran `/effort status`.
- Project folder name. Inferred. On the machine #14 checked, every character that isn't a letter or digit becomes "-". The docs show one example, `/home/user/work/my-repo` as `-home-user-work-my-repo`, but state no rule ([.claude directory, Clear local data](https://code.claude.com/docs/en/claude-directory#clear-local-data)).

### What the field can't prove

The field shows the level that ran, a lowered one included, but not why it ran at that level.

A test on #8 covered the lowered case. Under a project cap of low, an agent pinned at high and a main session at `--effort high` both recorded low in their `api-request` rows ([dashboard/experiments/2026-10-29-effort-cap-transcript.json](../dashboard/experiments/2026-10-29-effort-cap-transcript.json)). On Opus 4.6, xhigh ran as high, and the `api-request` rows of the main session and an agent recorded high ([dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json)). So the Last session column will show the lowered level.

A recorded level doesn't say where it came from. A difference from the rules means a rule is wrong, or something the files can't show was in play, such as `/effort` during the session.

A missing field can mean Claude Code sent no level. That happens on a model without effort levels, such as Haiku 4.5 ([model config, Adjust effort level](https://code.claude.com/docs/en/model-config#adjust-effort-level)), and with `CLAUDE_CODE_EFFORT_LEVEL=auto` ([model config, Send no effort level](https://code.claude.com/docs/en/model-config#send-no-effort-level)). In the harness, neither case wrote the field ([dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json), [dashboard/experiments/2026-10-29-effort-auto.json](../dashboard/experiments/2026-10-29-effort-auto.json)).

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

## Rules



### Summary

| Rule | Key | Scope | Confidence | Claude Code version checked |
| --- | --- | --- | --- | --- |
| effort-level-user-settings-opus-5-5 | effortLevel | main | Tested | 2.1.302 |
| model-main-session-order | model | main | Tested | 2.1.302 |
| model-main-default | model | main | Assumed | 2.1.302 |
| env-block-order | env | main | Tested | 2.1.302 |
| effort-level-layer-order | effortLevel | main | Tested | 2.1.302 |
| model-settings-effort-per-model | modelSettings | model | Tested | 2.1.302 |
| max-effort-level-lowest-cap | maxEffortLevel | main | Tested | 2.1.302 |
| max-effort-level-replaced-in-file | maxEffortLevel | main | Tested | 2.1.302 |
| max-effort-level-default | maxEffortLevel | main | Assumed | 2.1.302 |
| prompt-cache-ttl-order | promptCacheTtl | main | Tested | 2.1.302 |
| subagent-prompt-cache-ttl-order | subagentPromptCacheTtl | agent | Tested | 2.1.302 |
| auto-compact-window-order | autoCompactWindow | main | Tested | 2.1.302 |
| subagent-model-order | model | agent | Tested | 2.1.302 |
| subagent-model-force | model | agent | Documented | 2.1.302 |
| subagent-model-force-alone | model | agent | Documented | 2.1.302 |
| subagent-model-default | model | agent | Tested | 2.1.302 |
| effort-env-auto-sends-none | effortLevel | main | Tested | 2.1.302 |
| effort-level-user-settings-model-unknown | effortLevel | main | Documented | 2.1.302 |
| effort-env-empty-ignored | effortLevel | main | Tested | 2.1.302 |
| agent-effort-env-empty-ignored | effort | agent | Tested | 2.1.302 |
| effort-default-model-unknown | effortLevel | main | Assumed | 2.1.302 |
| effort-default-no-effort-support | effortLevel | main | Tested | 2.1.302 |
| effort-default-by-model | effortLevel | main | Tested | 2.1.302 |
| effort-level-settings-values | effortLevel | main | Tested | 2.1.302 |
| model-settings-effort-values | modelSettings | model | Tested | 2.1.302 |
| effort-flag-values | effortLevel | main | Tested | 2.1.302 |
| effort-lowered-by-cap | effortLevel | main | Tested | 2.1.302 |
| effort-lowered-unsupported-level | effortLevel | main | Tested | 2.1.302 |
| effort-ignored-no-effort-support | effortLevel | main | Tested | 2.1.302 |
| agent-effort-order | effort | agent | Tested | 2.1.302 |
| agent-effort-lowered-by-cap | effort | agent | Tested | 2.1.302 |
| agent-effort-lowered-unsupported-level | effort | agent | Tested | 2.1.302 |
| agent-effort-user-settings-opus-5-5 | effort | agent | Tested | 2.1.302 |
| agent-effort-user-settings-model-unknown | effort | agent | Documented | 2.1.302 |
| agent-effort-default-model-unknown | effort | agent | Assumed | 2.1.302 |
| agent-effort-default-no-effort-support | effort | agent | Tested | 2.1.302 |
| agent-effort-default-by-model | effort | agent | Tested | 2.1.302 |
| model-settings-name-matching | modelSettings | model | Tested | 2.1.302 |
| model-settings-max-effort-per-model | modelSettings.maxEffortLevel | model | Tested | 2.1.302 |
| max-effort-level-values | maxEffortLevel | main | Tested | 2.1.302 |
| model-settings-max-effort-values | modelSettings.maxEffortLevel | model | Tested | 2.1.302 |
| model-settings-auto-compact-window | modelSettings.autoCompactWindow | model | Tested | 2.1.302 |
| prompt-cache-force-5m | promptCacheTtl | main | Tested | 2.1.302 |
| subagent-prompt-cache-force-5m | subagentPromptCacheTtl | agent | Tested | 2.1.302 |
| prompt-cache-enable-1h | promptCacheTtl | main | Tested | 2.1.302 |
| subagent-prompt-cache-enable-1h | subagentPromptCacheTtl | agent | Tested | 2.1.302 |
| prompt-cache-default-by-plan | promptCacheTtl | main | Tested | 2.1.302 |
| subagent-prompt-cache-default | subagentPromptCacheTtl | agent | Tested | 2.1.302 |
| auto-compact-window-empty | autoCompactWindow | main | Tested | 2.1.302 |
| auto-compact-window-values | autoCompactWindow | main | Tested | 2.1.302 |
| auto-compact-window-default | autoCompactWindow | main | Tested | 2.1.302 |
| agent-auto-compact-window | autoCompactWindow | agent | Assumed | 2.1.302 |
| agent-auto-compact-window-values | autoCompactWindow | agent | Assumed | 2.1.302 |
| agent-auto-compact-window-default | autoCompactWindow | agent | Assumed | 2.1.302 |
| agent-file-location-order | agentFile | agent | Documented | 2.1.302 |
| agent-file-project-over-user | agentFile | agent | Tested | 2.1.302 |
| agent-file-nested-closest | agentFile | agent | Tested | 2.1.302 |
| agent-file-same-name-one-tree | agentFile | agent | Tested | 2.1.302 |
| agent-file-reader-rejected | agentFile | agent | Tested | 2.1.302 |
| agent-file-reader-rejected-untested | agentFile | agent | Assumed | 2.1.302 |
| agent-file-skipped | agentFile | agent | Tested | 2.1.302 |
| agent-file-unknown-field | agentFile | agent | Tested | 2.1.302 |
| settings-file-unreadable | settingsFile | main | Documented | 2.1.302 |
| settings-file-unreadable-untested | settingsFile | main | Assumed | 2.1.302 |
| settings-file-managed-unparsed | settingsFile | main | Documented | 2.1.302 |
| settings-file-unparsed-skipped | settingsFile | main | Tested | 2.1.302 |
| rules-files-listed | rulesFile | main | Documented | 2.1.302 |

### effort-level-user-settings-opus-5-5

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {model} ignores the top-level effortLevel in {file}. Opus 5.5 and later models take a user settings level only from modelSettings.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#effortlevel](https://code.claude.com/docs/en/settings-reference#effortlevel)

> Opus 5.5 and models released after it ignore it and start at their own default until you save a level for them, which `/effort` writes under `modelSettings`. In project, local, and managed settings, and with `--settings`, this key applies to every model.

- [https://code.claude.com/docs/en/model-config#set-the-effort-level](https://code.claude.com/docs/en/model-config#set-the-effort-level)

> If you set `effortLevel` in managed settings, Claude Code applies it at the settings step of the effort resolution order, and users can still change the level with `/effort` or `--effort`.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-user-key-by-model.json](../dashboard/experiments/2026-10-29-effort-user-key-by-model.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### model-main-session-order

- Key: model
- Scope: main
- Combine: highest_layer
- Layer order (highest first): flag, env, managed, cli, local, project, user, default

Reason:

> {winner} sets the model. --model beats ANTHROPIC_MODEL, which beats the model key in any file, managed included.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#model](https://code.claude.com/docs/en/settings-reference#model)

> `--model` takes precedence over `ANTHROPIC_MODEL`, and both take precedence over this key for one session, including over a managed `model`

- Experiment record: [../dashboard/experiments/2026-10-29-model-main-session-order.json](../dashboard/experiments/2026-10-29-model-main-session-order.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### model-main-default

- Key: model
- Scope: main
- Combine: highest_layer
- Layer order (highest first): flag, env, managed, cli, local, project, user, default

Reason:

> Nothing the dashboard reads sets the model, so the session starts on Claude Code's default model. The account type decides it, unless ANTHROPIC_DEFAULT_MODEL, an organization default or a model recorded on the account applies. So the dashboard can't say which model it is. To check, run /status in a new session started in this project.

Quotes:

- [https://code.claude.com/docs/en/model-config#default-model-setting](https://code.claude.com/docs/en/model-config#default-model-setting)

> The behavior of `default` depends on your account type

- [https://code.claude.com/docs/en/model-config#checking-your-current-model](https://code.claude.com/docs/en/model-config#checking-your-current-model)

> In `/status`, which also displays your account information

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### env-block-order

- Key: env
- Scope: main
- Combine: highest_layer
- Layer order (highest first): managed, cli, local, project, user, env

Reason:

> {key} comes from {file}. A settings env block overwrites the shell, and the higher file wins.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#env](https://code.claude.com/docs/en/settings-reference#env)

> A value here overwrites the same variable exported in your shell, and when more than one settings file sets a variable, the highest-precedence one applies.

- Experiment record: [../dashboard/experiments/2026-10-29-env-block-order.json](../dashboard/experiments/2026-10-29-env-block-order.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-level-layer-order

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {winner} decides the effort. CLAUDE_CODE_EFFORT_LEVEL beats --effort, which beats every settings file. A level picked in a running session with /effort sits between the two, and the dashboard can't see it. Among the files, the highest one with a level that counts for the model wins. In one file, the model's modelSettings level beats the top-level effortLevel, and a canonical-name entry beats an alias entry.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#effortlevel](https://code.claude.com/docs/en/settings-reference#effortlevel)

> `--effort` takes precedence over this key for one session, and `CLAUDE_CODE_EFFORT_LEVEL` takes precedence over both

- [https://code.claude.com/docs/en/model-config#set-the-effort-level](https://code.claude.com/docs/en/model-config#set-the-effort-level)

> If you set `effortLevel` in managed settings, Claude Code applies it at the settings step of the effort resolution order, and users can still change the level with `/effort` or `--effort`.

- [https://code.claude.com/docs/en/settings-reference#effortlevel](https://code.claude.com/docs/en/settings-reference#effortlevel)

> Within the same settings file, Claude Code uses a model's saved level rather than this key.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-level-order.json](../dashboard/experiments/2026-10-29-effort-level-order.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### model-settings-effort-per-model

- Key: modelSettings
- Scope: model
- Combine: highest_layer
- Layer order (highest first): managed, cli, local, project, user

Reason:

> {file} decides effort for {model}, because it's the highest file that sets a level for this model.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#modelsettings](https://code.claude.com/docs/en/settings-reference#modelsettings)

> Across files, Claude Code resolves each model separately: the highest-precedence settings file that sets either an `effortLevel` for that model or a top-level `effortLevel` that applies to that model decides, so an `effortLevel` in managed settings outranks a level you saved in user settings.

- Experiment record: [../dashboard/experiments/2026-10-29-model-settings-effort.json](../dashboard/experiments/2026-10-29-model-settings-effort.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### max-effort-level-lowest-cap

- Key: maxEffortLevel
- Scope: main
- Combine: lowest_value
- Layer order (highest first): managed, cli, local, project, user, default

Reason:

> The lowest cap applies. The cap in {winner} can't be raised from another file.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#maxeffortlevel](https://code.claude.com/docs/en/settings-reference#maxeffortlevel)

> When several scopes set a cap, the lowest applies, so a cap set in one scope can't be raised from another

- Experiment record: [../dashboard/experiments/2026-10-29-max-effort-level-cap.json](../dashboard/experiments/2026-10-29-max-effort-level-cap.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### max-effort-level-replaced-in-file

- Key: maxEffortLevel
- Scope: main
- Combine: lowest_value
- Layer order (highest first): managed, cli, local, project, user

Reason:

> {file} sets a top-level maxEffortLevel of {value}, but the same settings source also sets a modelSettings cap for {model}. That entry replaces this one for {model} only.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#maxeffortlevel](https://code.claude.com/docs/en/settings-reference#maxeffortlevel)

> That entry replaces this key for the model only within the settings source that sets both, such as your user settings or one managed source.

- Experiment record: [../dashboard/experiments/2026-10-29-model-settings-max-effort.json](../dashboard/experiments/2026-10-29-model-settings-max-effort.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 30, 2026

### max-effort-level-default

- Key: maxEffortLevel
- Scope: main
- Combine: lowest_value
- Layer order (highest first): default

Reason:

> No settings file sets maxEffortLevel, so the dashboard sees no cap on the effort level. On a Claude Enterprise plan, an admin can also cap effort per role, and the dashboard can't see that.

Quotes:

- [https://code.claude.com/docs/en/model-config#organization-effort-limits](https://code.claude.com/docs/en/model-config#organization-effort-limits)

> On a Claude Enterprise plan, organization admins set per-role effort limits, described below.

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### prompt-cache-ttl-order

- Key: promptCacheTtl
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, managed, cli, local, project, user, default

Reason:

> {winner} sets the main conversation's cache lifetime. CLAUDE_CODE_PROMPT_CACHE_TTL beats the settings files, and the higher file wins. Only a lowercase 5m or 1h counts, so Claude Code skips any other value and the next source decides.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#promptcachettl](https://code.claude.com/docs/en/settings-reference#promptcachettl)

> `FORCE_PROMPT_CACHING_5M` takes precedence over everything else, then `CLAUDE_CODE_PROMPT_CACHE_TTL`, then this key, and last `ENABLE_PROMPT_CACHING_1H`

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> When more than one control applies, Claude Code takes the first match in this order:

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> The bucket's environment variable

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> The bucket's setting

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> You can set a TTL for either bucket. Each control takes `5m` or `1h`, and Claude Code ignores any other value.

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> Both settings and both environment variables require Claude Code v2.1.242 or later.

- Experiment record: [../dashboard/experiments/2026-10-29-prompt-cache-sources.json](../dashboard/experiments/2026-10-29-prompt-cache-sources.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### subagent-prompt-cache-ttl-order

- Key: subagentPromptCacheTtl
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, managed, cli, local, project, user, agent, default

Reason:

> {winner} sets the cache lifetime for {agent}. CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL beats the settings files, which beat the agent's experimental.cacheTtl. Only a lowercase 5m or 1h counts, so Claude Code skips any other value and the next source decides. On a subscription, the agent's 1h gives one hour within plan usage, five minutes once usage credits start. With no plan in the dashboard config, the dashboard can't tell which applies.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#subagentpromptcachettl](https://code.claude.com/docs/en/settings-reference#subagentpromptcachettl)

> `FORCE_PROMPT_CACHING_5M` takes precedence over everything else, then `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL`, then this key, then `ENABLE_PROMPT_CACHING_1H`, which asks for the one-hour lifetime on every request.

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> When more than one control applies, Claude Code takes the first match in this order:

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> For a subagent's requests, the `cacheTtl` value in the subagent's `experimental` frontmatter field, which requires Claude Code v2.1.248 or later. Claude Code ignores a `1h` there while your Claude subscription is using usage credits

- [https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields)

> Claude Code ignores any other value, ignores `1h` while your Claude subscription is using usage credits, and reads the field only from subagent files.

- [https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields)

> Write `cacheTtl` inside the `experimental` map, not at the top level of the frontmatter.

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> You can set a TTL for either bucket. Each control takes `5m` or `1h`, and Claude Code ignores any other value.

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> Both settings and both environment variables require Claude Code v2.1.242 or later.

- Experiment record: [../dashboard/experiments/2026-10-29-prompt-cache-sources.json](../dashboard/experiments/2026-10-29-prompt-cache-sources.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### auto-compact-window-order

- Key: autoCompactWindow
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {winner} sets the auto-compact window. CLAUDE_CODE_AUTO_COMPACT_WINDOW beats --autocompact, which beats every settings file, and the higher file wins. /autocompact reports a window set with --autocompact as coming from settings.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#autocompactwindow](https://code.claude.com/docs/en/settings-reference#autocompactwindow)

> `--autocompact` takes precedence over this key for one session, and `CLAUDE_CODE_AUTO_COMPACT_WINDOW` takes precedence over both unless Claude Code ignores the variable's value

- [https://code.claude.com/docs/en/model-config#set-the-auto-compact-window](https://code.claude.com/docs/en/model-config#set-the-auto-compact-window)

> the variable takes precedence over the command, the flag, and the `autoCompactWindow` setting.

- Experiment record: [../dashboard/experiments/2026-10-29-auto-compact-window.json](../dashboard/experiments/2026-10-29-auto-compact-window.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### subagent-model-order

- Key: model
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): agent, env, default

Reason:

> {winner} sets the model for {agent}. The agent's frontmatter model, inherit included, beats CLAUDE_CODE_SUBAGENT_MODEL, which beats the main model, unless CLAUDE_CODE_SUBAGENT_MODEL_FORCE is on. A model passed at dispatch, or set by a mod's agent.spawn hook, beats the frontmatter, and the dashboard can't see either.

Quotes:

- [https://code.claude.com/docs/en/env-vars#variables](https://code.claude.com/docs/en/env-vars#variables)

> Two sources take precedence over it: a model Claude passes when it spawns the agent, and a `model` field in the agent's definition, including `inherit`.

- Experiment record: [../dashboard/experiments/2026-10-29-subagent-model-order.json](../dashboard/experiments/2026-10-29-subagent-model-order.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### subagent-model-force

- Key: model
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, default

Reason:

> CLAUDE_CODE_SUBAGENT_MODEL_FORCE is on, so {agent} runs on the model in CLAUDE_CODE_SUBAGENT_MODEL. Claude Code ignores the model in the agent's frontmatter, and Claude can't pass one at dispatch.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model](https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model)

> While `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is on, Claude Code ignores the `model` field in subagent definitions, and Claude can't pass a model when it starts a subagent.

- Experiment record: none
- Confidence: Documented
- Verified on: Claude Code 2.1.302, October 29, 2026

### subagent-model-force-alone

- Key: model
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): agent, default

Reason:

> CLAUDE_CODE_SUBAGENT_MODEL_FORCE is on and CLAUDE_CODE_SUBAGENT_MODEL isn't set, so {agent} runs on the main session's model. Claude Code ignores the model in the agent's frontmatter, and Claude can't pass one at dispatch.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model](https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model)

> If you set only `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, subagents run on the main conversation's model, except that the built-in Explore subagent runs on the [model listed for it under Built-in subagents](#built-in-subagents).

- [https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model](https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model)

> While `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is on, Claude Code ignores the `model` field in subagent definitions, and Claude can't pass a model when it starts a subagent.

- Experiment record: none
- Confidence: Documented
- Verified on: Claude Code 2.1.302, October 29, 2026

### subagent-model-default

- Key: model
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): agent, env, default

Reason:

> Nothing sets a model for {agent}, so it runs on the main session's model. When the dashboard can't tell that model, it can't name this one either. Run /status in a session to see the main model.

Quotes:

- [https://code.claude.com/docs/en/model-config#checking-your-current-model](https://code.claude.com/docs/en/model-config#checking-your-current-model)

> In `/status`, which also displays your account information

- Experiment record: [../dashboard/experiments/2026-10-29-subagent-model-order.json](../dashboard/experiments/2026-10-29-subagent-model-order.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-env-auto-sends-none

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> CLAUDE_CODE_EFFORT_LEVEL is set to {value}, so Claude Code sends no effort level and the API's own default for {model} applies. /effort status shows this as auto.

Quotes:

- [https://code.claude.com/docs/en/env-vars#variables](https://code.claude.com/docs/en/env-vars#variables)

> Set it to `auto` or `unset` to have Claude Code send no effort level, so that the API applies its own default for the model.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-auto.json](../dashboard/experiments/2026-10-29-effort-auto.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-level-user-settings-model-unknown

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {file} sets a top-level effortLevel of {value}, but the dashboard doesn't know the session's model. Opus 5.5 and models released after it ignore this key in the user file, and earlier models use it. So the dashboard can't say whether it counts. To check, run /effort status in a new session started in this project.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#effortlevel](https://code.claude.com/docs/en/settings-reference#effortlevel)

> Opus 5.5 and models released after it ignore it and start at their own default until you save a level for them, which `/effort` writes under `modelSettings`. In project, local, and managed settings, and with `--settings`, this key applies to every model.

- [https://code.claude.com/docs/en/model-config#set-the-effort-level](https://code.claude.com/docs/en/model-config#set-the-effort-level)

> If you set `effortLevel` in managed settings, Claude Code applies it at the settings step of the effort resolution order, and users can still change the level with `/effort` or `--effort`.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-user-key-by-model.json](../dashboard/experiments/2026-10-29-effort-user-key-by-model.json)
- Confidence: Documented
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-env-empty-ignored

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> CLAUDE_CODE_EFFORT_LEVEL is set but empty. Claude Code treats an empty value as not set, so the next source decides the effort. To send no level at all, set it to auto or unset.

Quotes:

none

- Experiment record: [../dashboard/experiments/2026-10-29-effort-env-empty.json](../dashboard/experiments/2026-10-29-effort-env-empty.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-env-empty-ignored

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> CLAUDE_CODE_EFFORT_LEVEL is set but empty. Claude Code treats an empty value as not set, so the next source decides the effort for {agent}.

Quotes:

none

- Experiment record: [../dashboard/experiments/2026-10-29-effort-env-empty.json](../dashboard/experiments/2026-10-29-effort-env-empty.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-default-model-unknown

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> Nothing the dashboard reads sets an effort level that counts. It can't name the default level either, because it doesn't know the session's model. Either nothing it reads sets a model, or that model isn't in its model list. To check, run /effort status in a new session started in this project.

Quotes:

none

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-default-no-effort-support

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {model} doesn't support effort, so Claude Code sends no level and there's no default to show.

Quotes:

- [https://code.claude.com/docs/en/model-config#adjust-effort-level](https://code.claude.com/docs/en/model-config#adjust-effort-level)

> The available effort levels depend on the model. Models not listed here do not support effort

- Experiment record: [../dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-default-by-model

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> Nothing sets an effort level that counts for {model}, so it runs at its default, {value}. /effort status shows this as auto (currently {value}).

Quotes:

- [https://code.claude.com/docs/en/model-config#adjust-effort-level](https://code.claude.com/docs/en/model-config#adjust-effort-level)

> The model's default effort: `high` on every model that supports effort, except that Opus 5.5, Sonnet 5.5, and Haiku 5.5 default to `medium` and Opus 4.7 defaults to `xhigh`

- Experiment record: [../dashboard/experiments/2026-10-29-effort-status-session.json](../dashboard/experiments/2026-10-29-effort-status-session.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-level-settings-values

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): managed, cli, local, project, user

Reason:

> {value} isn't a level effortLevel accepts in {file}, so Claude Code skips it and the next source decides. Settings files take low, medium, high or xhigh.

Quotes:

- [https://code.claude.com/docs/en/model-config#set-the-effort-level](https://code.claude.com/docs/en/model-config#set-the-effort-level)

> `max` isn't accepted as a level in either key

- Experiment record: [../dashboard/experiments/2026-10-29-effort-invalid-values.json](../dashboard/experiments/2026-10-29-effort-invalid-values.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### model-settings-effort-values

- Key: modelSettings
- Scope: model
- Combine: highest_layer
- Layer order (highest first): managed, cli, local, project, user

Reason:

> {value} isn't a level a modelSettings entry accepts in {file}, so Claude Code skips it for {model} and the next source decides. An entry takes low, medium, high or xhigh.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#modelsettings](https://code.claude.com/docs/en/settings-reference#modelsettings)

> `effortLevel`: one of `"low"`, `"medium"`, `"high"`, or `"xhigh"`

- Experiment record: [../dashboard/experiments/2026-10-29-effort-invalid-values.json](../dashboard/experiments/2026-10-29-effort-invalid-values.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-flag-values

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> --effort {value} isn't a level Claude Code knows, so it warns and ignores the flag. The next source decides. The docs also list ultracode as a level, but it wasn't tested on 2.1.302, so this rule doesn't treat it as valid.

Quotes:

- [https://code.claude.com/docs/en/cli-reference](https://code.claude.com/docs/en/cli-reference)

> Options: `low`, `medium`, `high`, `xhigh`, `max`, or `ultracode`.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-auto.json](../dashboard/experiments/2026-10-29-effort-auto.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-lowered-by-cap

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {value} from {file} runs as {becomes}, because maxEffortLevel caps {model} at {becomes}.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#maxeffortlevel](https://code.claude.com/docs/en/settings-reference#maxeffortlevel)

> Any higher level runs at the cap instead, including one from `/effort`, the `/model` picker, `--effort`, `CLAUDE_CODE_EFFORT_LEVEL`, a skill's or subagent's `effort` frontmatter, or the model's own default.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-cap-transcript.json](../dashboard/experiments/2026-10-29-effort-cap-transcript.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-lowered-unsupported-level

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {model} has no {value} level, so {value} from {file} runs as {becomes}, the highest level it has below that.

Quotes:

- [https://code.claude.com/docs/en/model-config#adjust-effort-level](https://code.claude.com/docs/en/model-config#adjust-effort-level)

> If you set a level the active model does not support, Claude Code falls back to the highest supported level at or below the one you set. For example, `xhigh` runs as `high` on Opus 4.6.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### effort-ignored-no-effort-support

- Key: effortLevel
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {model} doesn't support effort, so Claude Code sends no level and {value} from {file} has no effect.

Quotes:

- [https://code.claude.com/docs/en/model-config#adjust-effort-level](https://code.claude.com/docs/en/model-config#adjust-effort-level)

> The available effort levels depend on the model. Models not listed here do not support effort

- Experiment record: [../dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-order

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> {winner} sets the effort for {agent}. CLAUDE_CODE_EFFORT_LEVEL beats the agent's effort frontmatter, which beats --effort and the settings that count for its own model.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields)

> Effort level when this subagent is active. Overrides the session effort level, but not the `CLAUDE_CODE_EFFORT_LEVEL` environment variable.

- Experiment record: [../dashboard/experiments/2026-10-29-agent-effort.json](../dashboard/experiments/2026-10-29-agent-effort.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-lowered-by-cap

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> {agent} is set to {value} in {file} but runs as {becomes}, because maxEffortLevel caps {model} at {becomes}.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#maxeffortlevel](https://code.claude.com/docs/en/settings-reference#maxeffortlevel)

> Any higher level runs at the cap instead, including one from `/effort`, the `/model` picker, `--effort`, `CLAUDE_CODE_EFFORT_LEVEL`, a skill's or subagent's `effort` frontmatter, or the model's own default.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-cap-transcript.json](../dashboard/experiments/2026-10-29-effort-cap-transcript.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-lowered-unsupported-level

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> {agent} runs on {model}, which has no {value} level, so {value} from {file} runs as {becomes}.

Quotes:

- [https://code.claude.com/docs/en/model-config#adjust-effort-level](https://code.claude.com/docs/en/model-config#adjust-effort-level)

> If you set a level the active model does not support, Claude Code falls back to the highest supported level at or below the one you set. For example, `xhigh` runs as `high` on Opus 4.6.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-user-settings-opus-5-5

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> {agent} runs on {model}, which ignores the top-level effortLevel in {file}. Opus 5.5 and later models take a user settings level only from their own modelSettings entry.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#effortlevel](https://code.claude.com/docs/en/settings-reference#effortlevel)

> Opus 5.5 and models released after it ignore it and start at their own default until you save a level for them, which `/effort` writes under `modelSettings`. In project, local, and managed settings, and with `--settings`, this key applies to every model.

- Experiment record: [../dashboard/experiments/2026-10-29-agent-effort.json](../dashboard/experiments/2026-10-29-agent-effort.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-user-settings-model-unknown

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> {file} sets a top-level effortLevel of {value}, but the dashboard can't tell which model {agent} runs on. Opus 5.5 and models released after it ignore this key in the user file, and earlier models use it. So the dashboard can't say whether it counts for {agent}.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#effortlevel](https://code.claude.com/docs/en/settings-reference#effortlevel)

> Opus 5.5 and models released after it ignore it and start at their own default until you save a level for them, which `/effort` writes under `modelSettings`. In project, local, and managed settings, and with `--settings`, this key applies to every model.

- [https://code.claude.com/docs/en/model-config#set-the-effort-level](https://code.claude.com/docs/en/model-config#set-the-effort-level)

> If you set `effortLevel` in managed settings, Claude Code applies it at the settings step of the effort resolution order, and users can still change the level with `/effort` or `--effort`.

- Experiment record: [../dashboard/experiments/2026-10-29-effort-user-key-by-model.json](../dashboard/experiments/2026-10-29-effort-user-key-by-model.json)
- Confidence: Documented
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-default-model-unknown

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> Nothing sets an effort level that counts for {agent}, and the dashboard can't tell which model it runs on. So it can't say that model's default level.

Quotes:

none

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-default-no-effort-support

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> {agent} runs on {model}, which doesn't support effort, so Claude Code sends no level and there's no default to show.

Quotes:

- [https://code.claude.com/docs/en/model-config#adjust-effort-level](https://code.claude.com/docs/en/model-config#adjust-effort-level)

> The available effort levels depend on the model. Models not listed here do not support effort

- Experiment record: [../dashboard/experiments/2026-10-29-effort-fallback-levels.json](../dashboard/experiments/2026-10-29-effort-fallback-levels.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-effort-default-by-model

- Key: effort
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> Nothing sets an effort level that counts for {model}, so {agent} runs at that model's default, {value}. A level that counts only for the main session's model doesn't carry over to {agent}.

Quotes:

- [https://code.claude.com/docs/en/model-config#adjust-effort-level](https://code.claude.com/docs/en/model-config#adjust-effort-level)

> The model's default effort: `high` on every model that supports effort, except that Opus 5.5, Sonnet 5.5, and Haiku 5.5 default to `medium` and Opus 4.7 defaults to `xhigh`

- Experiment record: [../dashboard/experiments/2026-10-29-agent-effort.json](../dashboard/experiments/2026-10-29-agent-effort.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### model-settings-name-matching

- Key: modelSettings
- Scope: model
- Combine: highest_layer
- Layer order (highest first): managed, cli, local, project, user

Reason:

> The entry in {file} matches {model} by canonical name, alias, date suffix, [1m] or a provider-style ID. In one file, a canonical-name entry beats an alias entry.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#modelsettings](https://code.claude.com/docs/en/settings-reference#modelsettings)

> Claude Code writes each entry under the model's canonical name, such as `claude-opus-5-5`, and matches that model's alias, date-suffixed, `[1m]`, and recognized provider-specific IDs to the same entry.

- Experiment record: [../dashboard/experiments/2026-10-29-model-settings-name-matching.json](../dashboard/experiments/2026-10-29-model-settings-name-matching.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### model-settings-max-effort-per-model

- Key: modelSettings.maxEffortLevel
- Scope: model
- Combine: lowest_value
- Layer order (highest first): managed, cli, local, project, user

Reason:

> {file} caps {model} at {value}, replacing that file's top-level maxEffortLevel for this model only. Across files, the lowest cap still applies.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#maxeffortlevel](https://code.claude.com/docs/en/settings-reference#maxeffortlevel)

> That entry replaces this key for the model only within the settings source that sets both, such as your user settings or one managed source.

- Experiment record: [../dashboard/experiments/2026-10-29-model-settings-max-effort.json](../dashboard/experiments/2026-10-29-model-settings-max-effort.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 30, 2026

### max-effort-level-values

- Key: maxEffortLevel
- Scope: main
- Combine: lowest_value
- Layer order (highest first): managed, cli, local, project, user

Reason:

> {value} isn't a level maxEffortLevel accepts in {file}, so Claude Code skips it and any other cap still applies. A cap takes low, medium, high, xhigh or max.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#maxeffortlevel](https://code.claude.com/docs/en/settings-reference#maxeffortlevel)

> string, one of `"low"`, `"medium"`, `"high"`, `"xhigh"`, or `"max"`. A `"max"` value sets no cap

- Experiment record: [../dashboard/experiments/2026-10-29-model-settings-max-effort.json](../dashboard/experiments/2026-10-29-model-settings-max-effort.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 30, 2026

### model-settings-max-effort-values

- Key: modelSettings.maxEffortLevel
- Scope: model
- Combine: lowest_value
- Layer order (highest first): managed, cli, local, project, user

Reason:

> {value} isn't a level a modelSettings cap accepts in {file}, so Claude Code skips it for {model} and any other cap still applies. A cap takes low, medium, high, xhigh or max.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#maxeffortlevel](https://code.claude.com/docs/en/settings-reference#maxeffortlevel)

> string, one of `"low"`, `"medium"`, `"high"`, `"xhigh"`, or `"max"`. A `"max"` value sets no cap

- Experiment record: [../dashboard/experiments/2026-10-29-model-settings-max-effort.json](../dashboard/experiments/2026-10-29-model-settings-max-effort.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 30, 2026

### model-settings-auto-compact-window

- Key: modelSettings.autoCompactWindow
- Scope: model
- Combine: highest_layer
- Layer order (highest first): managed, cli, local, project, user

Reason:

> {file} sets the auto-compact window for {model}. The higher settings file wins, whether it sets a per-model or a top-level window. In one file, the per-model window wins, and a per-model value of auto gives the window tuned for the model.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#modelsettings](https://code.claude.com/docs/en/settings-reference#modelsettings)

> For that model, the value takes precedence over a top-level `autoCompactWindow` in the same settings file. Requires Claude Code v2.1.288 or later

- [https://code.claude.com/docs/en/settings-reference#modelsettings](https://code.claude.com/docs/en/settings-reference#modelsettings)

> `autoCompactWindow`: a number of tokens from `100000` to `1000000`, or `"auto"` for the window tuned for the model.

- Experiment record: [../dashboard/experiments/2026-10-29-auto-compact-window.json](../dashboard/experiments/2026-10-29-auto-compact-window.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### prompt-cache-force-5m

- Key: promptCacheTtl
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, managed, cli, local, project, user, default

Reason:

> FORCE_PROMPT_CACHING_5M is on, so the main conversation's cache lifetime is five minutes, whatever {file} sets.

Quotes:

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> `FORCE_PROMPT_CACHING_5M=1`, which forces five minutes for both buckets

- [https://code.claude.com/docs/en/env-vars#variables](https://code.claude.com/docs/en/env-vars#variables)

> Set to `1` to force the 5-minute prompt cache TTL even when 1-hour TTL would otherwise apply. Overrides `CLAUDE_CODE_PROMPT_CACHE_TTL`, `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL`, `ENABLE_PROMPT_CACHING_1H`, and the `promptCacheTtl` and `subagentPromptCacheTtl` settings

- Experiment record: [../dashboard/experiments/2026-10-29-prompt-cache-sources.json](../dashboard/experiments/2026-10-29-prompt-cache-sources.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### subagent-prompt-cache-force-5m

- Key: subagentPromptCacheTtl
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): env, managed, cli, local, project, user, agent, default

Reason:

> FORCE_PROMPT_CACHING_5M is on, so the cache lifetime for {agent} is five minutes, whatever {file} sets.

Quotes:

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> `FORCE_PROMPT_CACHING_5M=1`, which forces five minutes for both buckets

- Experiment record: [../dashboard/experiments/2026-10-29-prompt-cache-sources.json](../dashboard/experiments/2026-10-29-prompt-cache-sources.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### prompt-cache-enable-1h

- Key: promptCacheTtl
- Scope: main
- Combine: highest_layer
- Layer order (highest first): default

Reason:

> ENABLE_PROMPT_CACHING_1H asks for one hour, because no other variable or settings file sets the main conversation's cache lifetime.

Quotes:

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> `ENABLE_PROMPT_CACHING_1H=1`, which requests one hour for both buckets

- Experiment record: [../dashboard/experiments/2026-10-29-prompt-cache-sources.json](../dashboard/experiments/2026-10-29-prompt-cache-sources.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### subagent-prompt-cache-enable-1h

- Key: subagentPromptCacheTtl
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): default

Reason:

> ENABLE_PROMPT_CACHING_1H asks for one hour, because no other variable, settings file or experimental.cacheTtl sets the cache lifetime for {agent}.

Quotes:

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> `ENABLE_PROMPT_CACHING_1H=1`, which requests one hour for both buckets

- Experiment record: [../dashboard/experiments/2026-10-29-prompt-cache-sources.json](../dashboard/experiments/2026-10-29-prompt-cache-sources.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### prompt-cache-default-by-plan

- Key: promptCacheTtl
- Scope: main
- Combine: highest_layer
- Layer order (highest first): default

Reason:

> Nothing the dashboard reads sets the main conversation's cache lifetime, so the plan decides it. On a subscription it's one hour within plan usage, five minutes once usage credits start. On an API key or a cloud provider it's five minutes. The dashboard can't tell when usage credits start. With no plan in the dashboard config, it can't tell the plan either. To check, run claude -p "hello" --output-format json in this project and read usage.cache_creation.

Quotes:

- [https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself)

> The default for the request's bucket

- [https://code.claude.com/docs/en/prompt-caching#which-ttl-each-request-gets](https://code.claude.com/docs/en/prompt-caching#which-ttl-each-request-gets)

> Unless you choose a TTL yourself, Claude Code requests the one-hour TTL only on a Claude subscription within your plan's included usage.

- [https://code.claude.com/docs/en/prompt-caching#which-ttl-each-request-gets](https://code.claude.com/docs/en/prompt-caching#which-ttl-each-request-gets)

> so Claude Code drops the main conversation to the five-minute TTL

- Experiment record: [../dashboard/experiments/2026-10-29-prompt-cache-sources.json](../dashboard/experiments/2026-10-29-prompt-cache-sources.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### subagent-prompt-cache-default

- Key: subagentPromptCacheTtl
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): default

Reason:

> Nothing sets the cache lifetime for {agent}, so it gets five minutes on every plan.

Quotes:

- [https://code.claude.com/docs/en/prompt-caching#subagents-and-the-cache](https://code.claude.com/docs/en/prompt-caching#subagents-and-the-cache)

> Subagents fall outside the main-conversation TTL bucket, so they get five minutes even on a subscription until you choose a longer one.

- Experiment record: [../dashboard/experiments/2026-10-29-prompt-cache-sources.json](../dashboard/experiments/2026-10-29-prompt-cache-sources.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### auto-compact-window-empty

- Key: autoCompactWindow
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> CLAUDE_CODE_AUTO_COMPACT_WINDOW is set but empty. Claude Code ignores an empty value, so the next source sets the auto-compact window.

Quotes:

none

- Experiment record: [../dashboard/experiments/2026-10-29-auto-compact-window.json](../dashboard/experiments/2026-10-29-auto-compact-window.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### auto-compact-window-values

- Key: autoCompactWindow
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> {file} sets the auto-compact window to {value}. For CLAUDE_CODE_AUTO_COMPACT_WINDOW, Claude Code ignores a value that isn't a number and lowers one above 1000000 to 1000000. It raises a value below 100000 to 100000, so that value still shows In effect. The docs say Claude Code caps a raised or lowered value at the model's context window too. The dashboard's model list has no context windows yet, so it leaves that cap out. On 2.1.302, 200k ran at 100000, and the k suffix needs v2.1.304. In a settings file, Claude Code ignores a value below 100000.

Quotes:

- [https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)

> A warning that quotes your `CLAUDE_CODE_AUTO_COMPACT_WINDOW` value means the value falls outside 100,000 to 1,000,000 or isn't a token count.

- [https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)

> On Claude Code v2.1.304 or later, you can also write the number with `k` for thousands or `M` for millions, as in `200k` or `1M`.

- [https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)

> A number with no suffix is read as that many tokens, so `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200` means 200 tokens even though `/autocompact 200` means 200,000.

- [https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)

> The smaller of 100,000 tokens and your model's context window

- [https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)

> The smaller of 1,000,000 tokens and your model's context window

- Experiment record: [../dashboard/experiments/2026-10-29-auto-compact-window.json](../dashboard/experiments/2026-10-29-auto-compact-window.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### auto-compact-window-default

- Key: autoCompactWindow
- Scope: main
- Combine: highest_layer
- Layer order (highest first): env, flag, managed, cli, local, project, user, default

Reason:

> Nothing the dashboard reads sets the auto-compact window, so Claude Code uses the window tuned for the model. On Opus 5.5 that window is 1000000 tokens. Only Opus 5.5 was checked, so for any other model the dashboard can't say what the window is. To check, run /autocompact in a new session started in this project.

Quotes:

- [https://code.claude.com/docs/en/settings-reference#modelsettings](https://code.claude.com/docs/en/settings-reference#modelsettings)

> `autoCompactWindow`: a number of tokens from `100000` to `1000000`, or `"auto"` for the window tuned for the model.

- Experiment record: [../dashboard/experiments/2026-10-29-auto-compact-window.json](../dashboard/experiments/2026-10-29-auto-compact-window.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-auto-compact-window

- Key: autoCompactWindow
- Scope: agent
- Combine: ceiling
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> {winner} sets the auto-compact window for {agent}. CLAUDE_CODE_AUTO_COMPACT_WINDOW beats the agent's frontmatter unless Claude Code ignores the variable's value. Otherwise {agent} inherits the session's window, from --autocompact, the highest settings file or Claude Code's default. The frontmatter can only lower that window.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window](https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window)

> If you set `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, the subagent uses that variable's window instead and the field has no effect, unless Claude Code ignores the variable's value.

- [https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window](https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window)

> To make one subagent compact earlier than it otherwise would, set `autoCompactWindow` in its frontmatter to a token count from `100000` to `1000000`.

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-auto-compact-window-values

- Key: autoCompactWindow
- Scope: agent
- Combine: ceiling
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> Each source of the auto-compact window for {agent} has its own limits. For CLAUDE_CODE_AUTO_COMPACT_WINDOW, Claude Code ignores a value that isn't a number and lowers one above 1000000 to 1000000. It raises a value below 100000 to 100000, so that value still shows In effect. The docs say Claude Code caps a raised or lowered value at the model's context window too. The dashboard's model list has no context windows yet, so it leaves that cap out. The agent's frontmatter takes 100000 to 1000000, and Claude Code ignores any other value there, 200k included, because it reads as 200. In a settings file, Claude Code ignores a value below 100000.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window](https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window)

> If you set `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, the subagent uses that variable's window instead and the field has no effect, unless Claude Code ignores the variable's value.

- [https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window](https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window)

> To make one subagent compact earlier than it otherwise would, set `autoCompactWindow` in its frontmatter to a token count from `100000` to `1000000`.

- [https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)

> A warning that quotes your `CLAUDE_CODE_AUTO_COMPACT_WINDOW` value means the value falls outside 100,000 to 1,000,000 or isn't a token count.

- [https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)

> The smaller of 100,000 tokens and your model's context window

- [https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values](https://code.claude.com/docs/en/model-config#claude_code_auto_compact_window-values)

> The smaller of 1,000,000 tokens and your model's context window

- [https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window](https://code.claude.com/docs/en/sub-agents#subagent-auto-compact-window)

> Write the value as a plain integer such as `200000`, because in frontmatter Claude Code reads `200k` as 200, which is outside the allowed range.

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-auto-compact-window-default

- Key: autoCompactWindow
- Scope: agent
- Combine: ceiling
- Layer order (highest first): env, agent, flag, managed, cli, local, project, user, default

Reason:

> Nothing sets an auto-compact window for the session, so {agent} inherits the window tuned for the session's model. Its frontmatter can only lower that window. On Opus 5.5 that window is 1000000 tokens. Only Opus 5.5 was checked, so on any other model the dashboard can't say what the window is or whether the frontmatter lowers it. Run /autocompact in a session to see the session's window.

Quotes:

none

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-file-location-order

- Key: agentFile
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): managed, flag, project, user, plugin

Reason:

> {winner} defines {agent}. When agents in different places share a name, Claude Code uses the one from the highest place. From highest to lowest, those are managed settings, the --agents flag, the project, the user folder and a plugin.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope](https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope)

> When multiple subagents share the same name, Claude Code uses the one from the higher-priority location.

- Experiment record: none
- Confidence: Documented
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-file-project-over-user

- Key: agentFile
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): project, user

Reason:

> {winner} defines {agent}. When a project file and a user file share a name, the project file wins.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope](https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope)

> When multiple subagents share the same name, Claude Code uses the one from the higher-priority location.

- Experiment record: [../dashboard/experiments/2026-10-29-agent-files.json](../dashboard/experiments/2026-10-29-agent-files.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-file-nested-closest

- Key: agentFile
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): project

Reason:

> {file} defines {agent}, because its .claude/agents folder is the closest one to the working directory.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope](https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope)

> Project subagents are discovered by walking up from the current working directory, so every `.claude/agents/` between there and the repository root is scanned. When more than one of these nested directories defines the same `name`, Claude Code uses the definition closest to the working directory.

- Experiment record: [../dashboard/experiments/2026-10-29-agent-files.json](../dashboard/experiments/2026-10-29-agent-files.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-file-same-name-one-tree

- Key: agentFile
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): project, user

Reason:

> {file} and {other_file} both use the name {agent}, and Claude Code loads only one of them, chosen by filesystem read order. Change the name field in one so the dashboard can tell which runs.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope](https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope)

> Keep `name` values unique across the whole tree: if two files under the same `.claude/agents/` directory, including its subfolders, declare the same name, Claude Code loads only one of them, chosen by filesystem read order rather than a documented precedence.

- Experiment record: [../dashboard/experiments/2026-10-29-agent-files.json](../dashboard/experiments/2026-10-29-agent-files.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-file-reader-rejected

- Key: agentFile
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): project, user

Reason:

> {file} loads in Claude Code, but the dashboard can't read its frontmatter safely, so it can't say which values apply. Claude Code accepts some frontmatter that the dashboard's reader rejects, such as an unclosed bracket, a second colon in a value or a repeated key.

Quotes:

none

- Experiment record: [../dashboard/experiments/2026-10-29-agent-files.json](../dashboard/experiments/2026-10-29-agent-files.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-file-reader-rejected-untested

- Key: agentFile
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): project, user

Reason:

> {file} has frontmatter the dashboard's reader rejects, in a form nobody has tested in Claude Code. So the dashboard can't say whether Claude Code loads the file or which values apply.

Quotes:

none

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-file-skipped

- Key: agentFile
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): project, user

Reason:

> {file} doesn't load as an agent. Claude Code reads only .md files, treats a file with no name as documentation, and skips one with no description or with frontmatter it can't parse.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#subagent-files-claude-code-skips](https://code.claude.com/docs/en/sub-agents#subagent-files-claude-code-skips)

> Claude Code treats the file as documentation kept beside your agents.

- [https://code.claude.com/docs/en/sub-agents#subagent-files-claude-code-skips](https://code.claude.com/docs/en/sub-agents#subagent-files-claude-code-skips)

> Claude Code reads no fields from the file, skips it, and writes the parse error to the debug log.

- [https://code.claude.com/docs/en/sub-agents#subagent-files-claude-code-skips](https://code.claude.com/docs/en/sub-agents#subagent-files-claude-code-skips)

> Claude Code skips the file and writes the reason to the debug log.

- [https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope](https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope)

> Claude Code scans `.claude/agents/` and `~/.claude/agents/` recursively, so you can organize definitions into subfolders such as `agents/review/` or `agents/research/`.

- Experiment record: [../dashboard/experiments/2026-10-29-agent-files.json](../dashboard/experiments/2026-10-29-agent-files.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### agent-file-unknown-field

- Key: agentFile
- Scope: agent
- Combine: highest_layer
- Layer order (highest first): project, user

Reason:

> {file} sets {key}, which Claude Code doesn't read, so it has no effect. The agent still loads.

Quotes:

- [https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields)

> Multi-word field names use camelCase, such as `maxTurns` and `disallowedTools`, and must match the table exactly: Claude Code ignores a field it doesn't recognize without reporting an error.

- Experiment record: [../dashboard/experiments/2026-10-29-agent-files.json](../dashboard/experiments/2026-10-29-agent-files.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### settings-file-unreadable

- Key: settingsFile
- Scope: main
- Combine: all
- Layer order (highest first): managed, local, project, user

Reason:

> The dashboard can't read {file}, so it can't tell which values that file sets. If the system denies Claude Code the read too, every session starts without that file's policy. To check, run /status in a new session started in this project, or run claude doctor in a terminal. Both record a managed file Claude Code couldn't read.

Quotes:

- [https://code.claude.com/docs/en/managed-settings#find-entries-claude-code-dropped](https://code.claude.com/docs/en/managed-settings#find-entries-claude-code-dropped)

> If the operating system denied the read, for example on a root-only file, every session starts without that source's policies.

- [https://code.claude.com/docs/en/managed-settings#find-entries-claude-code-dropped](https://code.claude.com/docs/en/managed-settings#find-entries-claude-code-dropped)

> For any other read failure, such as an I/O error, every session exits at startup with a message to contact an administrator.

- Experiment record: [../dashboard/experiments/2026-10-29-managed-settings-macos.json](../dashboard/experiments/2026-10-29-managed-settings-macos.json)
- Confidence: Documented
- Verified on: Claude Code 2.1.302, October 29, 2026

### settings-file-unreadable-untested

- Key: settingsFile
- Scope: main
- Combine: all
- Layer order (highest first): managed, local, project, user

Reason:

> The dashboard can't read {file}, so it can't tell which values that file sets. It can't tell whether Claude Code reads it either. To check, run /status in a new session started in this project. Its Setting sources line lists each settings file Claude Code loaded.

Quotes:

none

- Experiment record: none
- Confidence: Assumed
- Verified on: Claude Code 2.1.302, October 29, 2026

### settings-file-managed-unparsed

- Key: settingsFile
- Scope: main
- Combine: all
- Layer order (highest first): managed, local, project, user

Reason:

> {file} isn't valid JSON, or its top level isn't an object, so the dashboard can't tell what it sets. Claude Code refuses to start while a managed file is in that state, so no new session starts until it's fixed. To check, start claude in a terminal. The error it prints names the file.

Quotes:

- [https://code.claude.com/docs/en/managed-settings#find-entries-claude-code-dropped](https://code.claude.com/docs/en/managed-settings#find-entries-claude-code-dropped)

> When a managed settings file, drop-in file, MDM plist, or HKLM registry value is present but can't be parsed as a JSON object, Claude Code refuses to start and prints an error naming the source, even when another admin source delivers a valid policy.

- Experiment record: none
- Confidence: Documented
- Verified on: Claude Code 2.1.302, October 29, 2026

### settings-file-unparsed-skipped

- Key: settingsFile
- Scope: main
- Combine: all
- Layer order (highest first): managed, local, project, user

Reason:

> {file} isn't valid JSON, or its top level isn't an object. Claude Code skips the whole file, so nothing in it applies. The next file or Claude Code's default decides each value instead. To see what's wrong, run claude doctor in a terminal.

Quotes:

none

- Experiment record: [../dashboard/experiments/2026-10-29-settings-invalid-json.json](../dashboard/experiments/2026-10-29-settings-invalid-json.json)
- Confidence: Tested
- Verified on: Claude Code 2.1.302, October 29, 2026

### rules-files-listed

- Key: rulesFile
- Scope: main
- Combine: all
- Layer order (highest first): project, user

Reason:

> {file} is in the {layer} rules folder, and Claude Code loads only .md files there. User and project rules both load, user rules first, and neither overrides the other.

Quotes:

- [https://code.claude.com/docs/en/memory#user-level-rules](https://code.claude.com/docs/en/memory#user-level-rules)

> Claude Code loads user-level rules before project rules, so a project rule appears later in Claude's context than a user rule. Neither set overrides the other: if a user rule and a project rule conflict, Claude may follow either one, so keep the two consistent.

- [https://code.claude.com/docs/en/memory#set-up-rules](https://code.claude.com/docs/en/memory#set-up-rules)

> All `.md` files are discovered recursively, so you can organize rules into subdirectories like `frontend/` or `backend/`:

- Experiment record: none
- Confidence: Documented
- Verified on: Claude Code 2.1.302, October 29, 2026

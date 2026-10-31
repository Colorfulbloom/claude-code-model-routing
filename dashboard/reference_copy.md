# Rules reference

The dashboard will show each setting's value with a status word and a reason. This page defines those words, lists what the dashboard will read and what it can't see, and then lists every rule it will apply.

## Status words

Every value on screen will have one of seven statuses. The status says whether the value counts, and the reason says why.

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
- Assumed. Neither the docs nor a test backs the whole rule yet. The screen will show it differently from the other two.

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

Some sources change a session after it starts, and others sit outside what the dashboard will read. So a value the dashboard will show as In effect can still change when one of these applies.

- Launch flags. The flags a session started with, such as `--model`, `--effort`, `--autocompact` and `--agents`. Each can change what runs. For example, `--model` beats `ANTHROPIC_MODEL` and the `model` setting ([CLI reference, CLI flags](https://code.claude.com/docs/en/cli-reference#cli-flags)).
- `--settings` content. JSON passed with `--settings`, inline or as a file path, ranks above the user, project and local files and below managed settings ([settings, Change a setting for one session](https://code.claude.com/docs/en/settings#change-a-setting-for-one-session)). It's a launch flag, so the dashboard can't see it in phase 1.
- MDM and server-managed settings. On macOS, MDM policy lives in the `com.anthropic.claudecode` managed preferences domain, and Anthropic's servers or a gateway hold server-managed settings ([managed settings, Where each mechanism stores the policy](https://code.claude.com/docs/en/managed-settings#where-each-mechanism-stores-the-policy)). Both rank above the managed settings file. By default, Claude Code uses the highest-ranked source that sets a policy and skips the rest ([managed settings, How Claude Code combines managed sources](https://code.claude.com/docs/en/managed-settings#how-claude-code-combines-managed-sources)). So a policy from either one can replace what the dashboard shows from the file.
- `/effort` in a running session. A level picked with `/effort` or the `/model` picker beats `--effort` and every settings file, though not `CLAUDE_CODE_EFFORT_LEVEL` ([model config, Adjust effort level](https://code.claude.com/docs/en/model-config#adjust-effort-level)). A pick saved as the default lands under `modelSettings` in the user settings file, where the dashboard will read it for new sessions. A pick for this session only, a `max` pick or a pick in a `-p` run stays in that session. To check one, run `/effort status` there.
- Dispatch parameters. When Claude starts a subagent, it can pass a model alias and an effort level for that run. Both beat the agent's frontmatter, though `CLAUDE_CODE_EFFORT_LEVEL` still beats the effort ([sub-agents, Choose a model](https://code.claude.com/docs/en/sub-agents#choose-a-model); [sub-agents, Choose an effort level](https://code.claude.com/docs/en/sub-agents#choose-an-effort-level)). The effort parameter needs v2.1.292 or later.
- Mod hooks. A mod's `agent.spawn` hook can choose a subagent's model, and Claude Code uses it in place of the dispatch model ([sub-agents, Choose a model](https://code.claude.com/docs/en/sub-agents#choose-a-model); [mods reference, Subagents](https://code.claude.com/docs/en/plugins/mods/reference#subagents)). The docs list a model, not an effort, for this hook.
- Another terminal's environment. The dashboard reads the shell it starts in. A session started from another terminal reads that terminal's variables when it starts, so its values may differ ([environment variables, Precedence](https://code.claude.com/docs/en/env-vars#precedence)). That's why a Shell value carries the note "Read when the dashboard started. A session from another terminal may differ."
- Usage credits. On a subscription, the main conversation's default cache lifetime is one hour within plan usage and five minutes once usage credits start ([prompt caching, Which TTL each request gets](https://code.claude.com/docs/en/prompt-caching#which-ttl-each-request-gets)). An agent's `experimental.cacheTtl` of `1h` is ignored while usage credits are in use ([sub-agents, Frontmatter reference](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields)). The dashboard can't tell whether a session is drawing on usage credits, so those lifetimes will show Unknown on a subscription or with no plan set.

<!-- rules -->

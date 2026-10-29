# Settings-order harness

This harness finds out which settings layer wins for a key by running Claude Code against a fake API. It backs the Tested rules in `dashboard/rules.json`, and each result has a record in `dashboard/experiments/2026-10-29-*.json`. It doesn't test managed settings, because writing them needs admin rights.

`runcase.py` runs one case with `claude -p` in a throwaway `HOME`, config dir and project. `fakeapi.py` logs the model, effort and cache lifetime of each request, then answers with an error, or with a short text reply when the case sets `text_reply`. `runbatch.py` runs every case in a case file through `runcase.py`.

## Safety

The harness only allows requests to `fakeapi.py` on 127.0.0.1.

- The harness refuses to start if `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_BASE_URL` is set in your shell.
- It refuses a case with `hooks`, `statusLine`, `apiKeyHelper` or MCP keys in its settings, or with MCP arguments.
- A case can only set environment variables from a short allowlist, in its env or in a settings `env` block. Only `PATH`, `TMPDIR` and `LANG` pass through from your shell.
- A case can only send a prompt from a short allowlist. `/autocompact` is on it without an argument, because it only prints the window and its source and makes no API call.
- Agent files from `agent_files` get the same frontmatter check as `agents`. A file can't set `hooks`, `mcpServers` or `initialPrompt`.
- `git init` runs only when a case asks for it. It gets a closed environment, a home folder inside the throwaway root, no system git config and no global git config.

## Case fields and output

Five optional case fields change what a run does.

- `prompt` is the text passed to `claude -p`. It's `"say hi"` by default, and the only other values allowed are `"/effort status"` and `"/autocompact"`. A `/effort status` case sends no request, so its answer shows up in `result`. `/autocompact` takes no argument, so `"/autocompact 200k"` and `"/autocompact auto"` are refused. It prints the window and its source, and makes no API call.
- `text_reply` is `true` or `false`. When it's `true`, `fakeapi.py` sends a short text reply instead of an error. The session then finishes a turn and writes assistant rows to its transcript. The setting reaches `fakeapi.py` only, never Claude Code.
- `agent_files` is a list of up to 8 agent files to write before the run. Each item has exactly the keys `where`, `path` and `text`.
  - `where` is `user` for `<config>/agents/`, `project` for `<project>/.claude/agents/`, or `nested` for `<project>/sub/.claude/agents/`.
  - `path` is one or two segments joined by `/`. Each segment starts with a letter or digit, then holds letters, digits, `.`, `_` or `-`, up to 64 characters. The last segment ends in `.md` or `.md.bak`, so a case can test whether backup copies load. Absolute paths, backslashes, `.`, `..` and empty segments are refused.
  - `text` is the file content. No two items may resolve to the same file, and an item can't collide with a file from `agents`. The existing `agents` map still works as before.
- `cwd` is `"project"` by default. `"nested"` runs `claude` in `<project>/sub`, which `runcase.py` creates if it's missing.
- `git_init` is `true` or `false`. When it's `true`, `runcase.py` runs `git init -q` in the project before it starts `claude`. It has 20 seconds. If git fails, `runcase.py` removes the throwaway root and exits with code 1 without starting `claude`.

`runcase.py` refuses any other prompt, a `text_reply` or `git_init` that isn't a bool, a bad `agent_files` value or any other `cwd` before it makes a folder or starts a process.

Each case prints one JSON line. Next to `case`, `init_model`, `sent` and `stderr`, it has three keys for effort and agent checks.

- `init_agents` lists the `agents` from the stream-json init row, in the given order. It keeps only strings and cuts each to 100 characters. It's `null` when there's no init row or no list.
- `transcript` lists the effort fields from the throwaway transcripts, read before they're deleted. Each row is `[who, kind, effort, perTurnEffort]`, where `who` is `main` or `subagent` and `kind` is `assistant` or `api-request`. An `api-request` row carries `params.output_config.effort`, with `null` in the last place.
- `result` lists the text of the session's stream-json `result` rows, each cut to 200 characters.

## Re-run

Run a case file from the repo root.

```sh
/usr/bin/python3 dashboard/experiments/harness/runbatch.py dashboard/experiments/harness/cases-model-effort-env.json 18500
```

The other case files are `cases-env-block-subagent.json` and `cases-cache-effort-caps-default.json`. The number is the first local port. Each case after the first uses the next port up.

The batch prints one JSON line per case. Compare those lines with `results-2026-10-29.jsonl`. When a new Claude Code version changes a result, update its record in `dashboard/experiments/` and `verified_on` in `dashboard/rules.json`.

The October 29 effort cases are in `cases-effort-sources.json`, `cases-effort-lowered-invalid.json` and `cases-model-settings.json`. Compare their lines with `results-2026-10-29-effort.jsonl`.

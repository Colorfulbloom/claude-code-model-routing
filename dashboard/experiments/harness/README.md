# Settings-order harness

This harness finds out which settings layer wins for a key by running Claude Code against a fake API. It backs the Tested rules in `dashboard/rules.json`, and each result has a record in `dashboard/experiments/2026-10-29-*.json`. It doesn't test managed settings, because writing them needs admin rights.

`runcase.py` runs one case with `claude -p` in a throwaway `HOME`, config dir and project. `fakeapi.py` logs the model, effort and cache lifetime of each request, then answers with an error. `runbatch.py` runs every case in a case file through `runcase.py`.

## Safety

The harness only allows requests to `fakeapi.py` on 127.0.0.1.

- The harness refuses to start if `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_BASE_URL` is set in your shell.
- It refuses a case with `hooks`, `statusLine`, `apiKeyHelper` or MCP keys in its settings, or with MCP arguments.
- A case can only set environment variables from a short allowlist, in its env or in a settings `env` block. Only `PATH`, `TMPDIR` and `LANG` pass through from your shell.

## Re-run

Run a case file from the repo root.

```sh
/usr/bin/python3 dashboard/experiments/harness/runbatch.py dashboard/experiments/harness/cases-model-effort-env.json 18500
```

The other case files are `cases-env-block-subagent.json` and `cases-cache-effort-caps-default.json`. The number is the first local port. Each case after the first uses the next port up.

The batch prints one JSON line per case. Compare those lines with `results-2026-10-29.jsonl`. When a new Claude Code version changes a result, update its record in `dashboard/experiments/` and `verified_on` in `dashboard/rules.json`.

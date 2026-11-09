# M0 spike results

Five spikes from `m0-build.md` section 6, run on November 8, 2026. Each one names its result, its evidence and the decision it settles. Spike sources sit in the session scratchpad and are not part of the repo.

## Spike 1. Code swap end to end

Pass. Playwright on Chromium 156 against the real server and the built app (`app/web/e2e/access.spec.ts`).

| Check | Result |
|---|---|
| `window.open(url)` | sessionStorage copied. Unlocked at 74 ms |
| `window.open` with noopener, a `target=_blank` link with or without `rel=noopener` | Not copied (Chromium implies noopener on `_blank` links). The BroadcastChannel offer stored the key at 54 to 74 ms and the tab unlocked by 106 ms |
| Locked tab, unlock in place | A tab locked with `no_key` on a deep route unlocked without a reload when another tab swapped a new code. The route stayed. The new tab showed the "other tab is back" line |
| Server restart, same port and data folder | New instance id. The old tab ends locked with `server_restarted` and never uses its stale key |
| Reused link | Locked with `code_used`, no key stored |
| Bad code, foreign instance | `code_unknown`, and `server_restarted` decided on the client with no request |

Decision. O1's mechanism holds as built. Codes are single use and live 120 seconds. The launcher reaches a running server through `POST /api/access/mint` with the `mint_secret` from the 0600 `server.json`. The 400 ms hold never reached the locked page in any run, so it stays at 400 ms.

React Aria under the nonce CSP. The touch-action style case is real. Without `<meta name="csp-nonce">`, React Aria injects an un-nonced `<style>` and Chromium reports a `style-src-elem` violation on the first Select open. With the meta, which the server writes on every request, there is no violation (`usePress.mjs` reads it). The built app loads, unlocks and opens a Select with zero violations.

## Spike 2. SessionEnd with one shared server

Pass. Two fake sessions started the preview against one data folder. The second start reused the same server, pid and port, minted a fresh code and listed two owners. Ending the first session removed its owner and the server stayed up. Ending the second removed `server.json` and stopped the process within 0.3 seconds, with nothing left running. The hook action returns in about 0.07 seconds, because a detached worker does the stop.

Decision. The server stops when its last owner ends, by session id or Claude Code pid. Owners whose Claude Code process is gone are pruned on the next launcher call. An idle exit after 30 minutes with no request is the backstop. Hooks stay unwired until M9 (owner, November 8), so in the preview the idle exit is the only automatic stop.

Notes. Two sessions in one Claude Code process share `CLAUDE_PID`, so they count as one owner. The launcher's own status probes count as requests for the idle clock.

## Spike 3. uv and SIGTERM

Pass both ways. With a stand-in ASGI app, SIGTERM to uv's pid and to the process group both ran lifespan shutdown and left no child, in 0.13 to 0.21 seconds. Running the environment's Python directly behaved the same. uv 0.13.5 forwards SIGTERM, as its docs say.

Decision. The launcher runs `uv sync --frozen --project app --no-dev`, then starts `<data>/uv/env/bin/python -B serve.py` directly. `uv run` adds a second process whose pid differs from the one the server records in `server.json`, and it adds nothing else. The server overrides uvicorn's signal capture so SIGTERM exits 0 after cleanup. A real first start took about 2.3 seconds and 88 MB, and a second start with `UV_OFFLINE=1` worked.

## Spike 4. `json_edit` array insert

Pass. A scratch copy of `dashboard/json_edit.py` gained `append_item` and `remove_item` under the same oracle. 48 fixture settings files (one correctly refused as unparsed), 19 edge documents and 2,000 seeded fuzz cases ran with no failure. Every refusal was justified (`parent_not_object`, `not_array`, `repeated_key` and the rest). Append then remove gives the original bytes back for every array that already existed.

Decision. O14 resolves to M7. Deny and ask rule editing ships in M7 with `append_item` and `remove_item` ported with their oracle. Undoing a created array uses `remove_key` on the topmost key that was created, because removing the last element leaves `[]`.

Known edges. An empty array written as `[ ]` or `[\n]` comes back as `[]` after an append and remove, with equal parsed content. `remove_key` on a top-level `{}` file leaves `{\n}\n`, which is existing behaviour. In the fuzz run, 207 undos of a created array gave the same parsed JSON with different bytes, because `remove_key` writes its own layout around the dropped key on randomly formatted input. None changed the parsed content.

Evidence. The November 8 rerun is in `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/spikes-m0/spike4.log`, with the scripts beside it in `spike4-scripts/`. It shows 48 fixture files, 1,068 operations, 2,000 fuzz cases and no failures.

## Spike 5. ruamel byte equality

Mixed. ruamel.yaml 0.19.1 round-trips all 63 loadable agent files in the repo byte for byte, and single-key edits on them never touch another line. Hand-made edge files show drift that ruamel introduces silently. It joins multi-line scalars and flow lists, normalises flow list spacing and key spacing, strips trailing spaces, flattens `~` and `null`, decodes unicode escapes, and drops `...` and tags. Tabs in plain scalars and duplicate keys fail loudly.

Decision for M6, a mix by field. Byte splicing for `model`, `effort`, `color`, `maxTurns`, and for `tools` or `disallowedTools` written as a comma string, where it never refuses and can't drift. Creating `disallowedTools: Agent` (N2) is one appended line. ruamel with a byte-equality guard on every line outside the edited key only for list-form `tools` and `disallowedTools` edits. When the guard fails, the save is refused with a clear reason instead of written.

Evidence. The November 8 rerun is in `/Volumes/Warehouse/Projects/routing-dashboard-rebuild-archive/spikes-m0/spike5.log`, with the script and the 66 edge files in `spike5-scripts/`. The corpus is every Markdown file with front matter under `agents/` and `tests/fixtures/`. That is 64 files, and one is a fixture built to fail loading, which leaves the 63 above. No file under `~/.claude` was read.

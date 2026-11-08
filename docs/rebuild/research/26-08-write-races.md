# Races with Claude Code's own writes (2026-11-08)

## Recommendation

- Never write `.claude.json` directly. Claude Code rewrites it at least once per run with a read-modify-write and no lock, so a dashboard write that lands between Claude Code's read and its replace is silently lost. Local and user MCP edits go through Claude Code's own commands, or a copy-command step (26-01-edit-architecture.md).
- Keep the current stale check and add a short post-save recheck for files Claude Code also writes: `settings.json` (user), `settings.local.json` and `.mcp.json`. Re-read the file once about 2 seconds after the save (inference on the interval). If our change is gone, mark the ledger row "overwritten by another writer" and show it in the review rail, instead of claiming success.
- Our own `flock` on `.lock` protects dashboard writers from each other only. Claude Code takes no lock, so it can't coordinate with us. Torn files are not the risk on 2.1.302 (the CLI replaces atomically); lost updates are.
- Read paths must tolerate a file that changes mid-read and a file that briefly fails to parse. Parse from one byte snapshot, and on a parse failure retry once before showing "Couldn't read".
- Locate `.claude.json` under `CLAUDE_CONFIG_DIR` when it is set. The probe shows the CLI then ignores `<HOME>/.claude.json`.

## What Claude Code writes

| File | When | Source |
|---|---|---|
| `~/.claude.json` | Claude Code "writes for itself": global options from `/config`, local and user MCP servers, per-project state, `/mcp` toggles | https://code.claude.com/docs/en/settings.md ("Settings files", "Use the /config menu"); 18-config-surfaces.md item 2 |
| Its backups | "Earlier versions of ~/.claude.json, copied when Claude Code rewrites the file. Claude Code keeps the five newest copies, plus a copy of any version it couldn't parse." | https://code.claude.com/docs/en/claude-directory.md ("Cleaned up automatically") |
| User `settings.json` | `/config` options, `/model` default | settings.md ("Use the /config menu", "Change a setting for one session") |
| `settings.local.json` | "Yes, and don't ask again" saves an allow rule; some `/config` options | settings.md ("Keep personal settings out of a repository") |
| `installed_plugins.json` | Session start, installs; open issue #106146 shows it rewriting other projects' records | 26-03-plugin-collector.md |

Claude Code also watches settings files: "Claude Code watches your settings files and reloads them when they change", and a `ConfigChange` hook can block a change from taking effect, except policy settings (settings.md "When edits take effect"; https://code.claude.com/docs/en/hooks.md). So a dashboard save to settings can be refused by the user's own hook. The rail should say "a ConfigChange hook may block this" when one exists (inference).

## Fixture probe (Claude Code 2.1.302, throwaway HOME, fake API)

Evidence and code: /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/6-output/race-probe.md, run folders under `roots/` beside it.

- The CLI reads and writes `<CLAUDE_CONFIG_DIR>/.claude.json`. A seeded `<HOME>/.claude.json` stayed untouched (same inode, size and mtime). This matches the docs: "The same applies to .claude.json, which otherwise sits at ~/.claude.json" (claude-directory.md).
- It rewrote a seeded file from 15 to 736 bytes and kept a foreign key `zz_probe`. The inode changed, so the write is temp file plus rename, not in place.
- It made `backups/.claude.json.backup.<epoch ms>`, mode 0600, holding the file as the CLI found it. No lock or temp file stayed behind.
- Race run: a writer thread replaced the file every 20 ms (10 writes in the run). The final file was valid JSON with all keys. The backup showed the CLI read the file mid-race (`zz_counter` 4) and wrote about 0.15 s later. No lost update showed in this one short run, but the read-then-write window is real, so a write inside it would be lost (inference from the timing).
- `settings.local.json` was not written by any of the four `-p` runs.

## Issue history

Reporters describe non-atomic, unlocked writes and truncated files with many sessions. All of these are closed; none has an Anthropic statement on a fix that the scout found. The probe's atomic replace on 2.1.302 suggests the truncation part was fixed (inference).

- #29217 "Race condition: .claude.json corrupted by concurrent writes from multiple sessions" (February 27, 2026), https://github.com/anthropics/claude-code/issues/29217
- #29051 "claude.json corrupted by concurrent writes (no atomic write / file locking)" (February 26, 2026), https://github.com/anthropics/claude-code/issues/29051
- #64600 "Concurrent writes to .claude.json by parallel workers + MCP truncate the file mid-JSON" (June 2, 2026), https://github.com/anthropics/claude-code/issues/64600
- #73590 "~/.claude.json corrupts repeatedly on Windows, silently wiping user-scope mcpServers" (July 2, 2026, closed for inactivity, a comment says it still happened August 30), https://github.com/anthropics/claude-code/issues/73590
- #9234 "settings.local.json Overwritten During Tool Execution" (October 9, 2025), https://github.com/anthropics/claude-code/issues/9234
- #9875 "Pressing '2' overwrites .claude/settings.local.json instead of appending permissions" (October 18, 2025), https://github.com/anthropics/claude-code/issues/9875

## Mitigations by file

| File | Dashboard writes? | Mitigation |
|---|---|---|
| `.claude.json` | No | Read only, masked. MCP local and user scope through Claude Code commands or copy-command |
| User `settings.json` | Yes | Stale check (existing HMAC bases, api_edit.py:1274-1276, 1348-1366), post-save recheck |
| `settings.local.json` | Yes | Same; Claude Code appends allow rules here during interactive sessions |
| Project `settings.json`, `.mcp.json` | Yes | Same; also edited by people and git checkouts |
| Agents, skills, rules, CLAUDE.md, output styles | Yes | Stale check; Claude Code doesn't write these except the claude.ai skills sync into `~/.claude/skills/` (18-config-surfaces.md item 5) |
| Plugin files, managed files | No | Read only |

## UNVERIFIED

- Lost-update behaviour under real contention. The probe made 10 writes in under a second and saw none.
- Whether `<HOME>/.claude.json` is used when `CLAUDE_CONFIG_DIR` is unset (expected from the docs, not run).
- Whether the CLI writes `.claude.json` more than once per session, and how often in long interactive sessions.
- Whether `settings.local.json` writes from permission approvals are atomic. Interactive approvals were not probed.
- `/output-style` and `/statusline` write targets.
- The 2-second recheck interval is a guess.

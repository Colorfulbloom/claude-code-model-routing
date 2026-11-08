# Transcript ingest into SQLite (round 3 spike 5)

Date: November 8, 2026. Python 3.9.6 (`/usr/bin/python3`, the only interpreter on this Mac) and SQLite 3.54.0. The brief asked for 3.11+, so see UNVERIFIED. Code, data and raw output are in the spike folder `/private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/5-ingest/` (`gen.py`, `ingest.py`, `bench.py`, `out/results-*.json`). All data is synthetic and seeded.

## Recommendation

- Ingest into SQLite with a per-file byte offset and keep one row per (file, message id). Pick the winner across files at query time with a window function. This ran 300k rows (700 MB of JSONL) in 1.8 s cold, and 13 ms for a no-change pass.
- Do not delete a file's rows on a rescan unless the source file is still there. A missing source file only gets a flag, so the DB keeps the data once Claude Code's `cleanupPeriodDays` removes the file.
- Keep the parser rules of `dashboard/transcripts.py` (byte prefilter, kinds, id rules) and the dedupe rule of `dashboard/usage.py`. Only the storage and the incremental read are new.

## Results

Every check compared the DB with a pure Python reference that re-reads all files with `json.loads` and applies the usage.py rule (requests, output, input, cache read, cache write, links, resolved links). Times are one run on a warm page cache.

| size | files | rows | first run s | DB MB | no-change s | append s | late link ok | truncate ok | totals match |
|---|---|---|---|---|---|---|---|---|---|
| 1k | 8 | 1083 | 0.007 | 0.11 | 0.0001 | 0.0024 | yes | yes | yes |
| 50k | 235 | 50010 | 0.298 | 1.96 | 0.0021 | 0.0078 | yes | yes | yes |
| 300k | 1295 | 300043 | 1.806 | 11.25 | 0.0127 | 0.0344 | yes | yes | yes |

Notes on the table (`out/results-*.json`)
- DB MB is the main file after `wal_checkpoint(TRUNCATE)`, so the WAL is 0. Before the checkpoint the WAL was 0.14, 2.0 and 0.59 MB (commits every 50k rows trigger SQLite's auto checkpoint).
- Source size was 2.5, 117 and 701 MB. Deduped requests were 232, 11,708 and 68,517. The DB is about 1.6 percent of the source because only usage fields are kept.
- Append means 1 percent new rows spread over 5 files, with the last assistant line of each file cut in half and written without a newline. The partial pass, then the completed pass, both matched the reference (300k second pass 14.8 ms).
- Late link at 300k: 94 link rows appended to parents after their agent files were ingested resolved in 18.5 ms. 94 agent files that arrived after their link resolved in 94 ms. Final state 871 links, 871 resolved, equal to the reference.
- Truncate at 300k rescanned 3 files in 19.6 ms (one shortened in place, one rewritten longer with other content on the same inode, one replaced by rename with a new inode).
- A deleted source file kept all rows (flag `missing=1`) at every size.
- Query cost over `best_requests` at 300k: SUM(output) 84 ms, group by day and model 112 ms. Fine for a dashboard, but a materialized table is the next step if the page needs it every poll (inference).

## Schema summary (`ingest.py:11-45`)

- files: id, path (unique), kind (main, agent, orphaned, superseded), folder, session_id, run_id, dev, inode, size, mtime_ns, offset, head_hash, last_line_hash, lines, malformed, synthetic, no_id, missing, scans.
- requests: PRIMARY KEY (file_id, key) WITHOUT ROWID, plus ts (canonical UTC text), output, input, cache_read, cache_write_5m, cache_write_1h, thinking, model, request_id, effort. Key is message.id, else `r|requestId`, else `n|byteoffset`.
- sessions: first and last ts, cwd, branch. runs: (session_id, run_id) to file and agentType from the meta file.
- links: (parent_file_id, child_id) with session_id, ts, resolved. Index on (session_id, child_id).
- view best_requests: ROW_NUMBER over key ordered by output desc, ts desc, path desc.
- Connection: WAL, synchronous NORMAL, one writer, `BEGIN` per batch, commit every 50k rows. Offset and rows commit together, so a crash never leaves an offset ahead of its rows.

## How the rules are handled

Dedupe (usage.py:117-146 `dedupe`). A row upserts with `ON CONFLICT(file_id,key) DO UPDATE ... WHERE (excluded.output, excluded.ts) >= (requests.output, requests.ts)`, which keeps the larger output and, on a tie, the later timestamp (`ingest.py:46-55`). Across files the view takes the same order and breaks the last tie by path, which matches the "later file" rule because transcripts.py reads files sorted by path (transcripts.py:`sorted(found, key=lambda f: f.path)`). Keying per file instead of globally is the one design change. A global key cannot be undone when a file is rewritten, and a rescan must remove only that file's contribution.

No ids. A row with neither id is kept and counted in a main or agent file, and dropped in an orphaned or superseded file (transcripts.py:308, `ingest.py:make_request`). Synthetic model rows and rows with a bad timestamp are counted and dropped.

File kinds. The three regexes and the agent layout are copied (transcripts.py:73-75, `_AGENT_RE`; `ingest.py:scan`). Orphaned and superseded files are ingested like main files, so their message ids dedupe against the main file. The generator made 6 percent superseded copies (a 60 percent prefix of the main file plus id-less rows) and 4 percent orphaned files, and the totals matched.

Simplified. transcripts.py also tracks `rounds` and `stops` per file (the Links tuple, transcripts.py:51-57) and merges orphaned links into the `(session_id, None)` key (transcripts.py:47). This spike stores only launch links. Stops and rounds need a small per-file state row to resume from an offset (inference).

Prefilter divergence. transcripts.py:726 treats any line with the `"toolUseResult":` needle as a user row, so an assistant row whose tool input holds that text loses its usage. `ingest.py:_lines` parses any line that has `"assistant"` first. The generator plants such rows (0.05 percent) and the reference counts them, so the match shows the fix works.

Lead's note: the planted rows put the needle inside a string value (`gen.py:167`), which JSON escapes as `\"toolUseResult\":`, so the real needle with its colon would not match them (transcripts.py:726-732 comment, project fact V-e876). The only case transcripts.py still loses is an object key `"toolUseResult"` inside a tool input with no `agentId` after it, which its own comment names. The lead counted the 50k data set: 8 assistant rows mention toolUseResult and 0 of them contain the real needle bytes, so transcripts.py would have counted them too. The planted trap does not show a bug in the current parser.

Late links. A link row is a user row with `toolUseResult.agentId` (transcripts.py:418). On insert the row sets `resolved` from `EXISTS(SELECT 1 FROM runs ...)` (`ingest.py:LINK_INSERT`). When an agent file appears, one UPDATE resolves the waiting links. Both orders are tested. The `links` table is the pending list, so there is no second table.

Incremental read. `_decide` is stat only when dev, inode, size and mtime match (transcripts.py:679 logic). A change in size or mtime first re-hashes the first and last 64 bytes before the stored offset. A mismatch, a size below the offset, or an inode change means a rescan. Otherwise the pass reads from the offset and keeps any bytes after the last newline for the next pass (transcripts.py:`find(b"\n")` break).

## Risks

- Format drift. The transcript format is internal and changes between versions (monitoring-usage.md:771, quoted in file 25). A new field needs no migration here, but a renamed `usage` key silently drops output. Count rows with usage missing and show the count on the page (inference).
- Output is a lower bound. Rows can hold a mid-stream output snapshot (file 25, issues #27361, #21971, #22686), so max-per-message is the best available, not exact.
- cleanupPeriodDays. Claude Code deletes old transcripts (file 25: 30 days holds). After that the DB holds the only copy. Back up the DB, never rebuild it from scratch without checking the source still exists, and never let a rescan of a shortened file replace rows silently (the spike deletes and re-inserts on a rescan, so a source rewritten shorter by the CLI loses rows). A safer variant keeps old rows on a size shrink and records the rescan (inference).
- WAL growth. A reader open for a long time blocks checkpoints. Keep reads short and run `wal_checkpoint(PASSIVE)` after each pass. Observed WAL was at most 2 MB.
- Same-size rewrite beyond the first and last 64 bytes goes unnoticed. The hash is a cheap guard, not a proof.
- Meta files (agentType) are read once when the agent file is first seen. A meta file written later is missed.
- Clock tie-breaks use text order of canonical UTC strings, which holds for fixed width timestamps only.

## UNVERIFIED

- Python 3.11+. Only 3.9.6 ran. The code uses nothing beyond 3.9, but SQLite needs 3.25 or newer for upsert row values and windows, so check the bundled version on each target Python.
- Cold cache and spinning disk timings. All numbers are warm cache on an SSD.
- Real transcript shape. Rows follow tests/fixtures descriptions and transcripts.py, not real files (rules forbid reading them). Real rows are likely larger and mixed, with big tool results.
- Concurrent writers and a reader during ingest.
- Windows file identity (inode is 0 on some filesystems) and network drives.
- Whether Claude Code ever rewrites a file in place with the same inode and size.
- Row size realism. Synthetic rows average 2.3 KB (701 MB over 300k rows).

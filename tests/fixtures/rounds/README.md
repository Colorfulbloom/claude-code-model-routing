# Round fixtures

Sanitized, windowed copies of real subagent transcripts (Claude Code 2.1.27x to 2.1.30x). Row structure is kept: `type`, `promptId` (renamed), `isMeta`, `origin` (kind, renamed `from`), `toolUseResult.agentId` (renamed), message ids (renamed), `stop_reason`, tool names and `usage`. All text is replaced; harness nudge text is kept as the harness writes it. `promptId` is kept only to show that it does not mark rounds: some resumes keep it, and some nudges and notifications change it. Rows between the windows are left out, so the figures are the real ones at each kept row, not a full run.

| File | Shape | Rounds |
|---|---|---|
| `coordinator-resume-same-prompt.jsonl` | Plain-text stop, then a coordinator follow-up under the same `promptId` | 2, the second starts at row 9 |
| `peer-resume-same-prompt-after-nudge.jsonl` | Plain-text stop, `[handback-send-enforce]` nudge, handback, then a follow-up from the lead (peer, not a worker it launched) under the same `promptId` | 2, the second starts at row 10 |
| `nudge-new-prompt.jsonl` | Plain-text stop, then a nudge under a new `promptId` | 1 |
| `task-notification-after-handback.jsonl` | Handback, then a background task notification under a new `promptId`, then a nudge | 1 |
| `worker-handback-wakes-lead.jsonl` | A lead launches two workers, stops to wait, and its worker's hand-back (peer from a launched agent) wakes it under a new `promptId` | 1 |

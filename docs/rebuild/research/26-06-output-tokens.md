# Output tokens in the persisted transcript

Run on November 8, 2026 (02:13 EST), Claude Code 2.1.302 (init_version), model claude-opus-5-5, against a local fake API. No real API call.

## Findings

- The transcript records the final output_tokens from message_delta, not the message_start snapshot. Every assistant row written for the reply carries output_tokens 500. No row shows 1.
- Claude Code writes one assistant row per content block, and each row repeats the whole message usage. With a thinking block plus two text blocks (run 1), message.id msg_fake2 has 3 rows, all with output_tokens 500. Summing output_tokens over rows would count 1500 for a 500-token reply. Dedupe by message.id and take one row.
- With one text block (run 2), message.id msg_fake2 has 1 row, output_tokens 500, input_tokens 10, stop_reason end_turn.
- requestId is null on all rows in this harness (inference: the fake API sends no request-id header).
- The CLI streamed (api.log shows "stream": true), so the non-streaming fallback was written but not exercised.

## Row usages

| Run | Stream | message.id | Rows | block types per row | usage.output_tokens |
| --- | --- | --- | --- | --- | --- |
| 1 | start 1, delta 500, thinking + 2 text blocks | msg_fake2 | 3 | thinking / text / text | 500, 500, 500 |
| 2 | start 1, delta 500, 1 text block | msg_fake2 | 1 | text | 500 |

Each row usage also has input_tokens 10, cache_creation_input_tokens 0, cache_read_input_tokens 0, output_tokens_details.thinking_tokens 0 (even with a thinking block), service_tier "standard". stop_reason is end_turn on every row, including the first block's row (the final stop_reason was applied to earlier blocks too).

## Stream sent (fakeapi, streaming)

1. message_start: id msg_fake2, usage {input_tokens 10, output_tokens 1, cache_creation_input_tokens 0, cache_read_input_tokens 0}
2. Run 1 only: content_block_start index 0 thinking; two thinking_delta; one signature_delta; content_block_stop
3. Run 1 only: content_block_start index 1 text; text_deltas "Hi ", "there, ", "friend."; stop. Then index 2 text, delta "Second text block.", stop
4. Run 2 instead: one text block index 0, delta "done", stop
5. message_delta: delta {stop_reason end_turn, stop_sequence null}, usage {output_tokens 500}
6. message_stop

Non-streaming fallback (text_json, body.stream false) returns the same message with usage output_tokens 500.

## Changes to the copies

- fakeapi.py:27-50 text_sse rewritten (mode from env SPIKE_MODE, "multi" or "single"); fakeapi.py:51-52 text_json added; fakeapi.py:72-75 non-streaming branch; fakeapi.py:66 logs the stream flag. Original: dashboard/experiments/harness/fakeapi.py:27-34.
- runcase.py:712 passes SPIKE_MODE to fakeapi; runcase.py:768-775 writes spike-dump.json into the throwaway root and keeps the root (the original removes it at the end, runcase.py:717 in the harness). Rows are read from the transcript at runcase.py:~750-766.
- README.md (harness) unchanged. Safety section obeyed: shell vars unset with env -u, one case per run, no runbatch.py, ports 41731 to 41734, TMPDIR set to the spike folder so the throwaway root (mkdtemp at harness runcase.py:604) sits inside it.

## Evidence

- /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/6-output/roots/mr-exp-10rwd14a/spike-dump.json (run 1, multi-block)
- /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/6-output/roots/mr-exp-edrznlow/spike-dump.json (run 2, single block)
- Transcript jsonl: <root>/config/projects/<project-slug>/<session>.jsonl in each root
- Run outputs: /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/6-output/run1.out, run2.out; patched code: /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/6-output/fakeapi.py, /private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/6-output/runcase.py

## UNVERIFIED

- Whether rows are written early with 1 and later rewritten in place to 500, or written only after message_delta. The final file shows only 500. Only the end state was read.
- Real API streams: a real message_delta carries cumulative output_tokens, and real mid-stream usage may differ from this fake. Only the fake was tested.
- Whether a multi-block reply with a tool_use block behaves the same (not tested).
- Long replies where Claude Code may flush rows before message_delta arrives (not tested).

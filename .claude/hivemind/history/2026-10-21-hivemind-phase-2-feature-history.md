### F-089d HiveMind Phase 2: feature history
status: in-progress
kind: code
dates: 2026-10-20 .. 2026-10-21
refs:
  commit: pending (branch feature/hivemind-history)
summary: Episodic memory next to the facts store: one entry per finished feature in .claude/hivemind/history/ with commit, file or url refs, a generated INDEX (cap 40, quarterly rollups that move entries whole), the CLI commands history add, link, rollup, index, recent, template and related, check validation of SHAs, paths and url shape, a Recent work block for the main session at startup, clear and compact, and the newest 15 index lines in deep-reasoner's slice.
decisions:
- Recent work rides the existing SessionStart status entry and gates on the stdin source field (startup, clear, compact), so the installer needs no new hook entry and reruns stay clean; calibrated live on 2.1.306, resume sends source resume.
- Entries are written in-progress with commit pending at CONSOLIDATION; history link fills the full SHA and sets shipped when the feature merges into development.
- Rollup moves whole entries by quarter instead of shortening text, so decisions survive; history never expires.
- deep-reasoner's history lines sit outside its facts budget so fact selection is unchanged.
- File refs must be repo-relative or start with ~/, and history files are scanned for home directory paths, following the committed-files rule.
- New history commands resolve the store from --store or the cwd, never from stdin, because history add - reads the draft from stdin.
- Capture skips SubagentStop events without an agent_type (internal subagents left dozens of empty run files per session).
- After the verifier pass, four fixes landed in hooks/hivemind_lib.py, each with a test: history writes also regenerate the top-level INDEX.md and check flags a stale history line there; history labels carry the history/ prefix once; history link run twice adds one commit ref; the INJECT_RULES notes sentence was narrowed.
- The owner chose to narrow the INJECT_RULES notes sentence.
rejected:
- A new SessionStart hook entry for Recent work (would change the installer's byte-identical entries).
- Prose compression in rollups (loses the decisions git does not record).
- A pre-commit hook against home paths (owner declined).
gotchas:
- A review scout ran history add without --store from inside the repo and wrote the live store; it removed its two files. Smoke runs must pass --store (D-168e).
- The installed hooks under the config dir stay at Phase 1 until the installer is rerun, so empty-agent run files keep appearing until then.
- Parity tests needed Allowance 5 for the new installer Next steps line (T-d689).
facts: T-7629, T-d689, T-91ac, D-168e
follow-ups:
- Run history link for this entry when feature/hivemind-history merges into development.
- Rerun the installer so the config dir gets the Phase 2 hooks; until then empty unknown run files keep landing in the inbox.

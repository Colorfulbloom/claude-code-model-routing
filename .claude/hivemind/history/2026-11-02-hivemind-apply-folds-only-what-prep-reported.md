### F-2650 HiveMind apply folds only what prep reported
status: in-progress
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: pending (branch fix/consolidation-prep-snapshot)
summary: Fixes ticket H2. apply used to list the inbox when it started, so a run file captured between prep and apply was folded and deleted with its NEW proposals unseen; prep now writes inbox/prep-snapshot.json and apply folds only those files under an flock.
decisions:
- prep reads each run file once (name, sha256, data), writes inbox/prep-snapshot.json {version 1, time, store, files, errors_bytes} under the lock, and builds its report from the same listing.
- apply without a snapshot, or with an invalid, other-store or stale one (more than 2 hours either way), exits 1 and changes nothing. Failing clearly beats a whole-inbox fallback, which would bring the bug back for anyone who skips prep.
- A second prep keeps a fresh snapshot and tags items from later files [next round], so a preview prep never widens what an open consolidation folds. Later files wait a round; nothing is lost.
- apply folds only snapshot files whose sha256 still matches and that os.listdir returns by exact name; changed files stay, gone files are counted.
- inbox/consolidating.lock is an flock (kernel-released on crash) held for a whole apply and for prep's listing and snapshot write; waits LOCK_WAIT_S (10 s) on contention, fails at once when the filesystem has no flock.
- apply removes the snapshot before rewriting errors.log, and keeps errors.log bytes past errors_bytes, so lines logged after prep survive and a rerun after a crash never cuts twice.
- CLI shape unchanged: prep|apply [<store dir>], exit 0 or 1, same apply summary line. The command sequence is unchanged. README.md:105 and the CONSOLIDATION line in agents/deep-reasoner.md gained one line each on the snapshot and the lock (November 3).
- Verifier pair ran on one brief, independently: pinned Opus (133,191 tokens) and Fable (124,715 tokens). Both found no blocker. Fixes for the case-alias delete, the double errors.log cut, the weak [next round] assert and the lock nits are in.
rejected:
- Apply with no snapshot falling back to the whole inbox: reopens H2.
- Each prep replacing the snapshot: a preview prep during an open consolidation would make its apply fold files the lead never saw.
- Prep refusing while a snapshot is open: blocks a lead for up to 2 hours behind a crashed or preview prep.
- A token passed from prep to apply: changes the CLI the plugin will build on.
- An O_EXCL lock file: goes stale after a crash; flock does not.
files: hooks/hivemind_lib.py, tests/test_hivemind.py
gotchas:
- ApplyTest now runs prep before apply (ApplyTest.apply()), and every nothing-changed snapshot skips inbox/consolidating.lock, because each acquire rewrites its holder line.
- On APFS a name check against INBOX_SKIP is case-sensitive but open and unlink are not; compare against exact os.listdir names.
- Retrying apply after a failed check needs a fresh prep, because a successful apply removes the snapshot.
- Without fcntl the lock does nothing; the snapshot still prevents H2, but two applies could fold twice.
follow-ups:
- Owner: copy hooks/hivemind_lib.py to ~/.claude/hooks after merge (install.py does it). The live copy also lacks the capture_order fix from PR #143.
- Plugin: /hivemind:inbox should not call prep for a preview, because prep now writes a snapshot that pins the fold set for 2 hours; use a read-only action such as the planned summary.
- Done November 3: README.md:105 and the CONSOLIDATION line mention the snapshot, and that a snapshot over two hours old needs a fresh prep (prose through tech-writer).

### F-82d8 Document the transcript reader and add a README Dashboard section (#66)
status: shipped
kind: content
dates: 2026-10-31 .. 2026-10-31
refs:
  file: docs/rules-reference.md
  commit: 47fab08ecebb48814b4fbd1a566cd3068aef3486 (branch feature/usage-docs, merged into development)
summary: PR #75 rewrites the transcripts section of the rules reference to match what's built and adds a Dashboard section to the README. The suite on the rebased tree is 1871 tests, 36 skipped. The live anchor check passed before the rebase, and no cited link changed in it.
decisions:
- Facts that depended on the page branches were rechecked against merged code.
files: README.md, dashboard/reference_copy.md, docs/rules-reference.md

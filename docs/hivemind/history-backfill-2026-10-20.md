# HiveMind feature history: backfill draft for 2026-10-20

Draft entries written by the main session on 2026-10-20, from the session where this work happened, so the decisions and their reasons survive the session. HiveMind Phase 2 (feature history) turns these into real `history/` entries during its first CONSOLIDATION, assigns ids, and fills pending commits. Format follows the Phase 2 plan.

---

### Python installer with model and effort picker
status: shipped
kind: code
dates: 2026-10-20 .. 2026-10-20
refs:
  commit: 6e0d514 (feature/python_installer, merged into development by fast-forward; branch deleted)
summary: install.py replaced the bash install.sh, which is now a short shim that checks for Python 3.9 and runs install.py. A full-screen curses picker sets each of the six agents' model and effort, with defaults read from agents/*.md and choices saved to model-routing-choices.json so a rerun preselects them. Flags --yes, --agent NAME=MODEL[:EFFORT], --reset and --plain; no TTY or CI skips the picker.
decisions:
- Python over bash: the dispatch hook already required python3, so it added no dependency, and the picker and install logic could share code and tests.
- Kept install.sh as a shim so existing instructions and links keep working. The owner plans to remove it later.
- Picker scope is the six agents only; the installer never writes model, effortLevel or env in settings.json (setup-model-routing owns those).
- Rules, agent descriptions, skills, hook message, README and reference doc reworded to name no tier, since tiers became user-chosen; tiers live only in frontmatter. The startup hook prints each agent's model and effort instead.
- Typed full model ids allowed with a strict character check; all five effort levels for every model (max confirmed valid in agent frontmatter by the docs).
rejected:
- dialog and whiptail (not on macOS), gum (extra install), pure bash menus (fragile arrow keys on bash 3.2).
- PyInstaller binary to avoid Python (per-platform builds, size, Gatekeeper on unsigned downloads).
- A bare `install` command on PATH (collides with /usr/bin/install).
- Filling chosen tier names into the prose with anchors (more moving parts than rewording).
gotchas:
- Parity with the old bash script needed deliberate tests for symlinked destinations, broken links, glob order, whitespace trimming in manifest reads, and byte-identical hook command strings (any change duplicates hook entries on rerun).
- The verifier found manifest lines were trimmed (a trailing space would delete the wrong file), typed ids accepted shell characters, and CI=false counted as CI. All fixed before commit.
- Tests run old and new installers side by side in throwaway HOME and CLAUDE_CONFIG_DIR folders; never against the real config.
files: install.py, install.sh, tests/, agents/*.md, rules/model-routing.md, hooks/check-agent-models.sh, hooks/require-agent-model.py, skills/, README.md, docs/model-routing-reference.md
follow-ups:
- Remove install.sh (owner's plan): update README, two shim tests, and the missing-Python message.
- Linux untested; terminal-too-small screen untested.

---

### HiveMind design and diagrams
status: shipped
kind: content
dates: 2026-10-20 .. 2026-10-20
refs:
  url: https://claude.ai/artifact/2fCHsd9FV2CCBEihuMLdRV (design page: architecture, flows, size limits, decisions)
  url: https://claude.ai/artifact/L7o8qC1tGeatbbqimxPEeZ (final flow diagram, direction C, sequence)
  url: https://claude.ai/artifact/32qbR3zcciH44d1wGYaDxM (three diagram directions compared)
summary: Research study on shared memory for AI agents (Claude Code, other coding agents, agent frameworks, research papers, failure modes), a recommended design, and the visual pages used to decide it. The owner named it HiveMind ("they all share one mind").
decisions:
- Two tiers, as every major tool does: a short reviewed rules file always loaded, plus agent-learned facts in a store.
- One writer: only deep-reasoner's end-of-feature pass writes the store; agents propose through a HIVEMIND block in their report, saved to add-only inbox files. Shared files edited by parallel agents lose writes (Claude Code closed that issue as not planned).
- Facts cite their files and are flagged suspect when those change, borrowed from GitHub Copilot Memory.
- The curator pass is named CONSOLIDATION, after how the brain moves short-term memories into long-term storage.
- Size limits are measured by script, never by an agent noticing; shrink first, split by subject, never rotate by date.
- No vector database yet: the store is small, embeddings cannot be reviewed in a diff, and similarity search makes reads unpredictable. Revisit when the store outgrows topics and an index.
- Diagram: the owner picked direction C (sequence) over the designer's recommended A (lifecycle).
rejected: one shared memory directory via symlinks (undocumented, unsafe under parallel writes, gives read-only agents write access); an MCP memory server (every agent a writer, hard to review); calendar-day expiry (an idle month would wipe the store).
gotchas: the study's quotes came through a page-summarizing tool, so treat them as paraphrases. The designer could not use the Chrome extension with two browsers connected and rendered with headless Chrome.

---

### HiveMind Phase 1: shared memory for all agents
status: shipped (installed 2026-10-20; not yet merged)
kind: code
dates: 2026-10-20 .. 2026-10-20
refs:
  commit: pending (branch feature/hivemind; fill in when merged into development)
summary: Shared memory for every agent in a project. A start hook injects compact one-line facts for each agent type within a per-type budget, once per agent; a stop hook saves each agent's HIVEMIND block to the inbox after a secret scan; a guard hook blocks every agent except deep-reasoner and the main session from writing the store; a session-start status line flags problems. deep-reasoner runs CONSOLIDATION (prep, decide, apply, check) at the end of each feature. Installed globally by install.py; each project opts in with `hivemind_lib.py init`.
decisions:
- Content fingerprints, not git history, decide when a fact is suspect (git misses uncommitted edits and breaks on squash merges and shallow clones).
- Random fact ids (T-7f3a) so parallel branches cannot collide.
- Inbox gitignored; accepted facts are committed and reviewed in each feature's diff.
- Expiry after 28 active days unused; active days are the union of local agent-run dates and git commit dates, kept in a local gitignored file so the working tree does not change daily.
- Read-only agents propose through their report and stay read-only.
- deep-reasoner's own project memory moved into HiveMind and was turned off; designer keeps its cross-project memory.
- Stores are opt-in per project; hooks install for every project. Worktree agents share the main checkout's store.
- Status line shows on startup, resume, clear and compact through its own entry, so the existing startup hook stays byte-identical.
- No repeated loading: inject once per agent id (resume re-fires the start hook), compact lines only, per-type budgets, no text at all for agents with no relevant facts, main session never gets facts.
rejected: blocking writes by memory text alone (owner rule: enforcement by hooks); calendar-day expiry; a committed active-days file (daily diff noise).
gotchas:
- Calibration on Claude Code 2.1.305: resume fires SubagentStart and SubagentStop again; agents that end with a SubagentHandback tool call send no last_assistant_message, so the block is read from the transcript; SubagentHandback exists only in auto mode; PreToolUse from subagents carries agent_type.
- Token tallies come from transcripts (the stop hook reports no token count): the harness figure equals the last message's input plus cache plus its output.
- Verifier found a guard bypass through capitalization on case-insensitive macOS; fixed with case-insensitive and inode comparison.
- Bash redirects can still bypass the guard; the regex secret scan has gaps; hook inputs verified on 2.1.305 only.
- The first CONSOLIDATION caught a stale migrated note (the test temp folder no longer has to exist) and replaced it.
files: hooks/hivemind_lib.py, hooks/hivemind-inject.py, hooks/hivemind-capture.py, hooks/hivemind-guard.py, tests/test_hivemind.py, install.py, tests/helpers.py, tests/test_features.py, tests/test_parity.py, agents/*.md, rules/model-routing.md, README.md, docs/model-routing-reference.md, skills/setup-model-routing/SKILL.md, .claude/hivemind/, .claude/rules/project-facts.md
facts: T-7629, T-5589, T-c826, T-baa7, T-6bd7
follow-ups:
- Owner decision on promoting T-7629, T-5589 and T-c826 to project-facts.md.
- Installer next-steps message should mention running init.
- Next CONSOLIDATION: fix T-7629 title vs text; give T-6bd7 a real check.
- Phase 2: feature history. Later: separate HiveMind repository, with HiveMind as an optional installer choice.

---

Cost notes for the token tallies (approximate, from agent reports): installer build about 630K plus verifier 151K and fix round 85K; HiveMind study about 300K; Phase 1 spec 45K; spec verifier 98K; Phase 1 build about 856K; Phase 1 verifier 188K; fix round 114K; designer directions 233K. The designer and both Fable verifier runs exceeded their estimates.

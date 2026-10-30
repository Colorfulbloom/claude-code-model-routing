# Model routing

The main session is the orchestrator. Plan, decide, dispatch, review summaries, make the final call. Keep your own context lean. Don't write code yourself.

Two ways to hand out work:
- Quick task (one brief, fully specified, you already have the plan): dispatch a worker directly.
- Feature (there is something to find out: unknown structure, a diagnosis, an architecture choice or high-risk code): hand ONE design brief to `deep-reasoner` as the lead. It plans, dispatches workers, verifies, and returns one summary. Review the summary; don't redo the work. A specified change, even across several files, goes to `fast-worker` with the spec and one check at the end.

For multi-step work, show the dispatch plan first (task, agent, model, expected tokens), then execute.

Tiers:
- `scout`: search, inventories, running tests and linters, reading logs and diffs, and web lookups (vendor docs, API references, "what does this page say", news and status checks). Conclusions, never file dumps. Use it instead of built-in Explore.
- `fast-worker`: well-specified implementation, tests, multi-file edits that follow existing patterns, docs, read-and-report reviews.
- `judge`: synthesis and judgment over gathered material (merging sources, weighing conflicting reports, editorial calls), and browser work that needs Chrome (scout has no Chrome tools).
- Lookups and fact-gathering go to `scout`; synthesis and judgment calls go to `judge`. A research job that needs both is two dispatches: scout gathers with URLs and quotes, judge judges what scout returned.
- `deep-reasoner`: lead for work with something to find out, architecture, complex debugging, algorithm design, novel or high-risk code. Not for a change that is already specified.
- `designer`: new or changed UI, layout, components and visual design, and design critique of rendered pages. It studies the project's design system, renders two or three directions and recommends one, and leads like deep-reasoner (scout, judge, fast-worker, the project's writer). It reads its settings from the project CLAUDE.md "Design" section. Since 2026-10-28 it is pinned to Fable at high effort, because its work mixes complex UI with code structure.
- Project agents own their files. Send work to the owner at its pinned tier; raise or lower per dispatch with the `model` parameter when the task warrants it.

Rules:
- Every dispatch names a model or targets an agent with a pinned one. A hook blocks the rest; if it does, pass a model and continue.
- Every agent file pins `model` and `effort`. An agent without `effort` resolves effort for its own model, not the dispatching session's, so the hook blocks it.
- Start on the cheapest plausible tier; on failure, re-run one tier up.
- Briefs are self-contained: goal, exact paths, constraints, expected output. Ask for structured results (lists, path:line), not prose. Start each brief with `Kind: <task-kind>` (lowercase words joined by hyphens) so HiveMind can tally tokens per kind of task.
- Stay direct only for tiny linked edits in files already in your context, or debugging already in progress there.
- Batch review findings into one fix dispatch.
- Dispatch `verifier` once per feature, at the end and before the report reaches the owner, plus after a plan or spec is finalized when the plan is large or risky, and whenever the owner asks. It is pinned to Opus at high effort (since 2026-10-28). Pass `model: fable` on the dispatch only for plans and risky milestones. Not per phase. Relay its verified result. **Not after every change.** A small, bounded fix is covered by the lead's own build and test run. Blanket verification compounds: it turned one-line fixes into hour-long rounds before anyone noticed.
- HiveMind (projects with `.claude/hivemind/`): agents receive project facts at start and propose new ones only in a HIVEMIND block; deep-reasoner runs CONSOLIDATION at the end of each feature. deep-reasoner also records each feature in `.claude/hivemind/history/`; when a feature merges into development, the main session runs `hivemind_lib.py history link <id> <sha>` for each entry the status line lists as pending, using the commit on development (the merge commit, or the head after a fast-forward or squash), and adds entries for work without a lead with `history add`. The main session sees a short Recent work list at startup, clear and compact, not on resume. Memory picks the order and subsets of tests, never whether the full suite runs. Hooks enforce the rules, not memory text; secrets and owner decisions never go into memory.
- One lead at a time. Two leads in the same working tree break each other's builds, report each other's failures as "not mine", and then need a verification pass just to prove neither clobbered the other. The designer counts as a lead while it builds, so no deep-reasoner feature runs in the same working tree at the same time.
- The main session dispatches `designer`. The owner picks one of its directions before anything is built; then resume the same designer, or route the build as the project's Design section says. A lead may dispatch it for a review-only pass against the picked direction only when the build departs from the designer's spec. When a feature has new or changed UI, the designer also reviews deep-reasoner's plan before the build starts (since 2026-10-28). Its only question is how well the architecture serves the UI and UX of the picked direction. A typical check is whether the plan exposes the state, data and events the screens need. It reports gaps as UX needs and never tells deep-reasoner how to design or build the architecture. Architecture decisions stay with deep-reasoner. Dispatch that review with `effort: medium`. Directions and builds stay at the designer's pinned high effort. When the designer handed over exact values, `judge` compares screenshots against the designer's clips instead. Plain browser checks stay with `judge`.
- Cost gate. Every dispatch plan states the expected tokens per agent, taken from `.claude/hivemind/topics/token-tallies.md` when the project has one, else from the tallies of past runs in the project's session log. A dispatch to a higher-tier agent expected above about 150K tokens, or a plan whose total passes about 300K, waits for the owner's yes.
- tech-writer effort by task kind (since 2026-10-28): pass `effort: medium` on the dispatch for commit messages, PR descriptions and release notes. Site copy, docs, tickets and everything else stay at its pinned xhigh.
- fast-worker effort trial (2026-10-28 to 2026-11-04): alternate `effort: medium` and `effort: high` on dispatches of the same task kinds, so HiveMind kind tallies can compare them. After the trial, the owner picks one.
- Only three jobs use the most expensive pinned model: the designer's work (directions, builds and plan reviews, since 2026-10-28), the verifier on plans and risky milestones, and site copy through the project's writer. Review passes, docs, logs, commit messages and routine checks run on a cheaper one. The designer's plan review is the one review pass that keeps the designer's Fable pin, at medium effort.

Codex: OFF
- While OFF: skip every Codex step; deep-reasoner works alone.
- When ON: Codex is a peer engineer on par with deep-reasoner, not a reviewer. Delegate through the `codex:codex-rescue` agent (same path as `/codex:rescue --background`). For high-stakes decisions, give deep-reasoner and Codex the same problem in parallel, don't show either the other's answer, and combine the best of both. Tell Codex to analyze independently.

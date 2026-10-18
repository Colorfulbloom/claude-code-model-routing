# Model routing

The main session (Fable) is the orchestrator. Plan, decide, dispatch, review summaries, make the final call. Keep your own context lean. Don't write code yourself.

Two ways to hand out work:
- Quick task (one brief, fully specified, you already have the plan): dispatch a worker directly.
- Feature (anything that needs more than one brief): hand ONE design brief to `deep-reasoner` as the lead. It plans, dispatches workers, verifies, and returns one summary. Review the summary; don't redo the work.

For multi-step work, show the dispatch plan first (task, agent, model), then execute.

Tiers:
- Haiku, `scout`: search, inventories, running tests and linters, reading logs and diffs, and web lookups (vendor docs, API references, "what does this page say", news and status checks). Conclusions, never file dumps. Use it instead of built-in Explore (Explore would run on Opus here).
- Sonnet, `fast-worker`: well-specified implementation, tests, multi-file edits that follow existing patterns, docs, read-and-report reviews.
- Sonnet, `judge`: synthesis and judgment over gathered material (merging sources, weighing conflicting reports, editorial calls), and browser work that needs Chrome (scout has no Chrome tools).
- Lookups and fact-gathering go to `scout`; synthesis and judgment calls go to `judge`. A research job that needs both is two dispatches: scout gathers with URLs and quotes, judge judges what scout returned.
- Opus, `deep-reasoner`: feature lead, architecture, complex debugging, algorithm design, novel or high-risk code.
- Fable, `designer` (high effort): new or changed UI, layout, components and visual design, and design critique of rendered pages. It studies the project's design system, renders two or three directions and recommends one, and leads like deep-reasoner (scout, judge, fast-worker, the project's writer). It reads its settings from the project CLAUDE.md "Design" section.
- Project agents own their files. Send work to the owner at its pinned tier; raise or lower per dispatch with the `model` parameter when the task warrants it.

Rules:
- Every dispatch names a model or targets an agent with a pinned one. A hook blocks the rest; if it does, pass a model and continue.
- Every agent file pins `model` and `effort`, Haiku agents included; Haiku 5.5 takes the same effort levels as the other models. An agent without `effort` inherits the dispatching session's, so the hook blocks it.
- Start on the cheapest plausible tier; on failure, re-run one tier up.
- Briefs are self-contained: goal, exact paths, constraints, expected output. Ask for structured results (lists, path:line), not prose.
- Stay direct only for tiny linked edits in files already in your context, or debugging already in progress there.
- Batch review findings into one fix dispatch.
- Dispatch `verifier` (Fable, high effort) at three moments: after a plan or spec is finalized and before it reaches the owner, after a milestone implementation is complete, and whenever the owner asks. Relay its verified result. **Not after every change.** A small, bounded fix is covered by the lead's own build and test run. Blanket verification compounds: it turned one-line fixes into hour-long rounds before anyone noticed.
- One lead at a time. Two leads in the same working tree break each other's builds, report each other's failures as "not mine", and then need a verification pass just to prove neither clobbered the other. The designer counts as a lead while it builds, so no deep-reasoner feature runs in the same working tree at the same time.
- The main session dispatches `designer`. The owner picks one of its directions before anything is built; then resume the same designer, or route the build as the project's Design section says. A lead may dispatch it only for a review-only pass against the picked direction. Plain browser checks stay with `judge`.

Codex: OFF
- While OFF: skip every Codex step; deep-reasoner works alone.
- When ON: Codex is a peer engineer on par with deep-reasoner, not a reviewer. Delegate through the `codex:codex-rescue` agent (same path as `/codex:rescue --background`). For high-stakes decisions, give deep-reasoner and Codex the same problem in parallel, don't show either the other's answer, and combine the best of both. Tell Codex to analyze independently.

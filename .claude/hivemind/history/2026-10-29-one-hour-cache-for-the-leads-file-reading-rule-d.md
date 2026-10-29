### F-3349 One-hour cache for the leads, file-reading rule, designer sections
status: shipped
kind: code
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: 930c52903e02001e111086a4a4f467557fb34781..91904f1c6ae65f8d778d6aa77cd33529ae8afaba (branch development)
summary: deep-reasoner and designer set experimental.cacheTtl 1h, a new rules/file-reading.md ships, and the designer's usability and plan-review sections moved from the owner's installed copy into the repo.
decisions:
- 1h cache only on the two leads in the repo, which wait on workers. The owner's logs showed it would cost the other agents more. Scrummaster (not in the repo) got it in the installed copies only.
- No log figures in the public docs, because the owner could not confirm their period. The docs carry a general caveat that 1h is ignored while usage draws on usage credits, and the designer stays on Fable.
- The designer's usability pointer says "if it exists", because ~/.claude/designer/usability-for-apps.md is not in the repo.
rejected:
- Shipping usability-for-apps.md with installer support: needs installer code and a review of the file before it goes public.
- Copying the full TTL override order into the reference doc: it goes stale, so the doc links to the prompt-caching docs instead.
files: agents/deep-reasoner.md, agents/designer.md, rules/file-reading.md, README.md, docs/model-routing-reference.md, skills/setup-model-routing/SKILL.md
gotchas:
- install.py replaces an installed agent file that differs from the repo copy, so edits made only to ~/.claude/agents are lost on reinstall (a backup is kept).
follow-ups:
- Suite count in T-7629 is stale (403 tests, about 106s). Two HIVEMIND CONTRADICTS proposals are waiting for consolidation.

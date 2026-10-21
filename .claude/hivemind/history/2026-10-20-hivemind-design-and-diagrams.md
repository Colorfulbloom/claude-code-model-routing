### F-649a HiveMind design and diagrams
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
rejected:
- One shared memory directory via symlinks (undocumented, unsafe under parallel writes, gives read-only agents write access).
- An MCP memory server (every agent a writer, hard to review).
- Calendar-day expiry (an idle month would wipe the store).
gotchas:
- The study's quotes came through a page-summarizing tool, so treat them as paraphrases.
- The designer could not use the Chrome extension with two browsers connected and rendered with headless Chrome.

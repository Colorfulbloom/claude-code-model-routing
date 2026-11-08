# Round 3 debate list (merged by the main session from the four r2 files)

## Owner calls (no panel debate; the judge presents each with the panel's view)
- O1 Access after reload, new tab and deep link. sessionStorage, a launcher command that mints a new code for the running server, BroadcastChannel handoff (architect). Designer, architect and senior developer agree; research 23 B2 said memory only.
- O2 User-scope edits under per-project keys. Any project's edit key can change ~/.claude/settings.json. Minimum is naming the other projects in the preview (senior developer, architect).
- O3 Product name. "Routing Dashboard" now names only the optional layer (content).
- O4 "Today" range preset. Stack A shows Today; 20-decisions presets omit it. Content includes it; architect not in 1.0; designer owner call.
- O5 Narrator in copy: "the dashboard" or "we" (content leans "the dashboard").
- O6 Build and supply chain: Python 3.9 launcher with 3.11+ backend, committed build output at milestone ends, Linux CI minutes, locked installs (senior developer).

## Near consensus (judge settles unless a debater objects in round 3)
- C1 A not-yet-editable item states the reason and the real path, with no "next release" promise (designer, content, senior developer; architect proposed the promise).
- C2 Unknown sits in a separate "Can't tell" group outside the "To fix" count (all four in some form).
- C3 Models folds into Overview (designer, content; timing differs).
- C4 Scope chips use Claude Code's docs scope names as the label, with who-and-where words as line two (content, architect, senior developer; designer disagrees).

## Debates
- R1 First-release editing scope. Fields only (four keys plus agent model and effort, senior developer), or also deny and ask rules and markdown text with lazy CodeMirror (architect), or also delete and skills text (designer). Includes whether the risk classifier ships in 1.0 with the risky tier held (architect yes; senior developer only with the first risky surface). Panel: all four.
- R2 Design rounds and milestones. Must a direction round finish before the setup UI and edit UI milestones, run beside backend milestones, and include a text-body variant? Panel: designer, architect, senior developer.
- R3 UX patterns against WAI-ARIA APG (required designer and architect debate). Setup map Table or Tree View; risky confirm inline in the rail or modal Dialog; scope switch Switch or Tabs; Alert Dialog for delete only. Cite APG and WCAG 2.2. Panel: designer, architect; others may comment.
- R4 System status after save (required designer and architect debate). Does the rail show "checking" for about 2 seconds or "saved" at once with a warning only on overwrite; are page updates push or poll with etags and row state (SSE stays a spike). Cite Nielsen H1 and WCAG 4.1.3. Panel: designer, architect; content for the words.
- R5 Output cost label. Per figure "lower bound", note only when undercounted requests exist (architect), or once in cost help as "may be low" (content). 26-06 found the final count on 2.1.302; 25-verifier cites older issues. Panel: content, architect, designer.
- R6 "To fix" contents. Do "Claude Code newer than the rules" and "rows with no usage" count, or go to a status line or reference banner; two groups or four ("Won't load", "Not as set", "Can't tell", "Couldn't read"). Panel: content, architect, designer.
- R7 Words and routes. Rename "Rules reference" and its route (for example "How Claude Code decides"); keep current route names or the new path scheme; "pin" only in the routing layer; "Usage" or "Activity" for the first nav group. Panel: content, designer, senior developer, architect.
- R8 Testing. Screenshot baselines as pass-fail or review only; differential tests in-process or from recorded old-app payloads; who backs up the database and when. Panel: senior developer, architect, designer.
- R9 Session replay on the Live canvas and a cross-project sessions list in 1.0 or later. Panel: senior developer, designer.

## Round 3 format
For each debate you are on (and any near-consensus item you object to), a section "## R<n>" or "## C<n>" with:
- Strongest case for your side, at most 200 words, with evidence (path:line, screenshot, research file, named standard).
- What you concede.
- Final position in one line, or "Moved to <other side>".
Read every r2-*.md file first. Keep the whole file under about 2,000 words.

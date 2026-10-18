# Claude in Chrome: tab-group rules

Verified 2026-09-19 with a controlled experiment. The MCP tab group is shared by every agent in a
session. It is created by `tabs_context_mcp` with `createIfEmpty`, together with one blank "New Tab"
that belongs to nobody. Two facts drive everything below:

- `navigate` without a `tabId` drives the group's FIRST tab (that blank one), not your own.
- Closing the group's first tab deletes the group even while other tabs are still in it. Every other
  tab is then orphaned: still open in Chrome, but no tool can list, drive or close it. The next
  `createIfEmpty` starts a new group with a new blank tab, so the strays pile up.

Rules for any agent that touches Chrome:

1. Call `tabs_context_mcp` first, then `tabs_create_mcp` for a tab of your own. Pass that `tabId` to
   `navigate` and to every other tool, every time. Never call `navigate` without a `tabId`.
2. Never close the group's first tab (the one that was blank when the group was made, whatever it
   shows now). Close only tabs you created, and close each one as soon as you are done with it.
3. If `tabs_context_mcp` says "No tab group exists" while you still had a tab, another agent closed
   the first tab. Your tab is now a stray: put its URL in your report so the user can close it, and
   do not open more tabs than the task needs.
4. The orchestrator closes the blank first tab last, after every Chrome agent has finished, or
   leaves it for the user.
5. Never touch tabs you did not create, never use the clipboard unless the brief says so, and never
   type credentials: if a site shows a login wall, stop and report.

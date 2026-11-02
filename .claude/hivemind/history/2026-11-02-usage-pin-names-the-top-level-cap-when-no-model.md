### F-24d1 Usage pin names the top-level cap when no model is known
status: shipped
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: 399f86539308d363d1769ff28d22190d994c2402 (branch fix/91-followups, merged into development)
summary: Follow-up to #91 (PR #137). pin-view.js matches effort-lowered-by-cap-model-unknown and uses three new strings naming the top-level maxEffortLevel cap instead of "caps Unknown"; the new rule is restamped 2026-11-02 on 2.1.302 after both quotes were re-checked.
decisions:
- Three full sentences that repeat the rule's caveat word for word, so the page and rules.json say the same thing.
- Kept straight apostrophes in the rule quotes, matching the sibling rules; the docs use curly ones.
rejected:
- One shared caveat string appended after each sentence: fewer keys, but splits one thought across two entries.
files: dashboard/static/js/pin-view.js, dashboard/static/strings.json, dashboard/rules.json, docs/rules-reference.md, tests/js/pages.mjs
gotchas:
- pin-view.js picks the model-unknown wording from a null cap.model (or e.model), not from the rule id, so any lowered-by-cap id with a null model gets it.
follow-ups:
- Agent rows with no model still overstate; tracked in #136.

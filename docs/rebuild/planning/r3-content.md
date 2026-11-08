# Round 3 debates, digital content specialist

Saved by the main session from tech-writer's reply (tech-writer is read-only).

Lens: the words on screen. I read brief.md, debates.md and all four r2 files. I checked research/26-06-output-tokens.md lines 5 to 20, research/25-verifier-gap-research.md line 5, and dashboard/static/js/router.js:21 to 24 again. All wording below is draft copy for the owner to review. It counts as opinion unless it cites a source.

C4 needs no answer. The designer moved to the docs scope names as the chip label, with the who-and-where words as line two (r2-designer.md, "Changed my mind"). All four panelists now agree, so the judge can settle it.

## R4

Strongest case (the words only). A status word must match what has already happened. The write is done when the save answer returns, so "Checking" tells the person something false. It reads as if the save might still fail, the trust problem Nielsen H1 warns about. Every save would show the same two-second word, so people learn to skip it, and then they skip the overwrite warning as well (r2-designer.md, point 6).

- At once, announced politely: "Saved." Undo stays live.
- Overwrite found: "Saved, but another program changed this file right after. Review it before you go on." Actions "Review changes" and "Undo".
- Recheck finds no change: no new message. "Saved." stays.

WCAG 2.2 SC 4.1.3 asks for status messages a screen reader announces without moving focus. One polite "Saved." and one overwrite warning meet it. A third "checking" message only adds noise. React Aria's `announce()` defaults to assertive, so each call must pass "polite" (r2-designer.md point 10, research/21-accessibility.md notes). The overwrite warning could fairly be assertive; I lean polite there too (opinion).

What I concede. Push against poll is not my call. The architect's polled recheck state can sit behind these words unchanged (r2-architect.md point 6). If the recheck can't tell whether our change survived, the overwrite line needs a second version: "Another program changed this file after you saved. Your change may be gone." [NEEDS CONFIRMATION: what the recheck can detect.]

Final position. "Saved." at once, an announced warning only on overwrite, and no "checking" word on screen.

## R5

Strongest case. The figure label has to match the evidence, and the evidence is mixed. Our own spike on Claude Code 2.1.302 found the final output_tokens on every row (26-06 line 7). The lower-bound claim rests on three closed GitHub issues against older versions (25-verifier line 5). "Lower bound" on every figure would claim something our newest test disproves. It also costs width at 375 and repeats on each figure, which usability rule 23 warns against. The designer and Stack A already show the cost note once per card ("Estimated at API list price", r2-designer.md point 8).

So the note shows only when the data gives a reason, using the architect's count of undercounted requests. Draft card note, shown only when that count is above zero: "{n} requests may be missing output, so output cost may be low." Cost help always carries: "On some Claude Code versions, transcripts can record less output than was used."

What I concede. I move most of the way to the architect, with a conditional note instead of "help only". Caveat: 26-06 line 20 found stop_reason "end_turn" copied onto every row, including the first block's row, so a missing stop_reason may not mark a snapshot row reliably. The architect labels the idea untested (r2-architect.md point 8). If the signal fails, the help line is the whole of it.

Final position. No "lower bound" on any figure. The note goes once per card, only when the undercount is above zero, worded "may be low", and cost help always explains.

## R6

Strongest case. "To fix" makes a promise in its own name. Each counted row must be a fault in the person's setup that the person can fix. "Claude Code newer than the rules" fails both tests; only a dashboard update helps. "Transcript rows with no usage" fails them too; Claude Code wrote those rows. Counting either turns the badge into a false alarm (Nielsen H8 and H9). The designer made the same point for Unknown (r2-designer.md point 7). The architect's feed already keeps `cant_tell` outside `problem` (r2-architect.md point 7).

Where each goes, drafts:
- Version gap, a banner on the reference page and one status line on the setup map: "Claude Code {version} is newer than these rules. Results for new settings may be wrong."
- No-usage rows, a line in the usage history help: "{n} sessions had no usage data, so they aren't counted."
- A single value newer than the rules goes into the uncounted "Can't tell" group.

Groups: the designer's four in the designer's order. "Couldn't read", "Won't load" and "Not as set", all counted, then "Can't tell", uncounted.

What I concede. "Couldn't read" goes first and counts, because an unreadable file hides every problem behind it (r2-designer.md point 7). The senior developer's rule holds too: a code ships with its collector (r2-senior-dev.md point 7), so the no-usage line waits for the transcript collector.

Final position. Four groups, three counted. The version gap and the no-usage rows go to a banner and a status line, outside "To fix".

## R7

Strongest case. Most of this settled in round 2.

- Route names. The senior developer and the architect dropped "keep current route names" for pages. The designer keeps only the usage route names (r2-senior-dev.md point 3, r2-architect.md point 3, r2-designer.md point 3). Today's list has "rules" and "trail" (router.js:21 to 24). Both go.
- Reference name. The designer backs "How Claude Code decides" (r2-designer.md point 9). Two things called "rules" side by side break Nielsen H4, and URLs are copy people paste. Draft: nav label "How Claude Code decides", route `#/reference/decides`, with the Glossary at `#/reference/glossary`.
- "Usage" against "Activity". The designer agrees with "Usage" (r2-designer.md point 3). Settled.
- "Pin". Claude Code's docs say an agent's model is set in its file and never say "pin" (code.claude.com sub-agents.md). Core copy asks "Did each agent run on the model its file sets?" "Pin" shows only when the routing layer is detected, through the architect's `feature` tag (r2-architect.md point 1). No panelist argued for "pin" in core copy in round 2.

What I concede. The usage route names can stay if recorded payloads lean on them. If "Activity" later fits better because Live moves into the first group, I won't fight it.

Final position. Rename the reference page and its route, use the new path scheme for all other pages, keep "Usage", and keep "pin" out of core copy.

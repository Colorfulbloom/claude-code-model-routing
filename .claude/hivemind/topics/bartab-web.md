# bartab-web

### J-f0a7 TanStack under fake timers needs a zero tick
fact: Under Vitest fake timers a TanStack Query result reaches result.current only after await vi.advanceTimersByTimeAsync(0); an act ending in a failed fetchNextPage needs one more tick.
check: grep -c "advanceTimersByTimeAsync(0)" app/web/src/api/review.test.tsx
evidence: app/web/src/api/review.test.tsx
fp: 9f721d59add2
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### J-dad4 Range input Page keys: cancel and write the value
fact: Chromium moves a native range input a tenth of its range on Page Up. ReplayLine cancels the key and writes currentTarget.value itself, or fast repeats read a stale value and lose steps.
check: grep -n "currentTarget.value" app/web/src/components/ReplayLine/ReplayLine.tsx
evidence: app/web/src/components/ReplayLine/ReplayLine.tsx, app/web/e2e/replay-keys.spec.ts
fp: 410b4c49a27c
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### J-c864 Concurrent Playwright runs need their own --output
fact: playwright.config.ts writes to test-results/artifacts, so two runs in one worktree clash with ENOENT. Pass --output <scratch dir> to each.
check: grep -n "outputDir" app/web/playwright.config.ts
evidence: app/web/playwright.config.ts
fp: a36643cc25b0
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### J-b0ae Review e2e runs on the demo build
fact: Fixture mode answers unknown_project for every Review route, so Review specs start the server with --demo --no-price-fetch --test-clock.
check: grep -n '"--demo"' app/web/e2e/review.spec.ts
evidence: app/web/e2e/review.spec.ts, app/server/fixture_provider.py
fp: 9d970e30c20b
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### J-ac3a Prior has records: priorHasRecords, not prior_partial
fact: prior_partial is true for an empty prior and a partly covered one. Tiles and the subline use priorHasRecords(w), true when window.oldest is before window.prior_end.
check: grep -n "export function priorHasRecords" app/web/src/lib/review-view.ts
evidence: app/web/src/lib/review-view.ts
fp: 5ba2ab6ba5ef
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### J-5bcb Replay max on an ended session is last_request
fact: The replay line's max on an ended session is the minute of session.last_request, not axis end minus start, so specs read it from last_request.
check: grep -n "last_request" app/web/src/lib/replay.ts
evidence: app/web/src/lib/replay.ts, app/web/e2e/session-review.spec.ts
fp: 8e4c53cb93f8
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### J-0ba9 Review CSS classes are global: prefix per page
fact: Review page CSS applies page-wide, so a generic class such as .review-chart collided across pages. Each file keeps its prefix (review-costbars, sreview-, review-agents-, review-models-).
check: grep -c "^\.sreview-" app/web/src/pages/review/SessionReviewPage.css
evidence: app/web/src/pages/review/ReviewPage.css, app/web/src/pages/review/SessionReviewPage.css
fp: a4b892998812
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### J-b7dc Session review: folds and Tab order in specs
fact: Lanes fold finished and not-started runs, so a row check opens every .lane-fold-button[aria-expanded="false"] first. On a running session the Session Select and Open in Live come before the line, and Back to now is reached by Shift+Tab from it.
check: grep -n "lane-fold-button" app/web/e2e/session-review.spec.ts
evidence: app/web/e2e/session-review.spec.ts
fp: 2c148e261659
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

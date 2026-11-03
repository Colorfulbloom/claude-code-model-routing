### F-84a0 Stage 5 direction A: the band is the editor for Arrange on the Settings page
status: in-progress
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: pending (branch feature/stage5-arrange-in-band)
summary: Over 720px, Arrange turns the Settings band into the editor. Each cell gets Earlier and Later buttons and a grip, the band shows the saved order with no borrowed cell, and the settings past the fold sit in a second row under the line "More starts here at this window size". Earlier, Later and mouse drag cross the fold and announce it. At 720px and under the in-flow list stays, with a note line and Earlier and Later names. Full suite 3136 tests, 68 skipped; band_reorder_checks 72 of 72; MR_E2E file test_band_arrange_e2e.py passed 8 of 8 on November 3 after a test fix (it now waits on the resting a.s4-stat links before pressing Arrange).
decisions:
- Arrange is a toggle (aria-pressed). Over 720px focus stays on it, and Tab walks the band. On a phone focus still moves into the list, because Tab from the head reaches More first and More closes arranging (designer review).
- While arranging the More column is an inert aria-hidden div. It takes the .s6-mdrop look and the drop words only while a drag hovers it.
- Drops while arranging go by keys, then clamp to the row (dropIndexArranged). The band's end slot makes the setting the last band cell, and the second row's first slot makes it the first under More.
- refitBand compares a layout key from the effective fit plus the editing and narrow flags, so the fold redraws on every width change that moves it.
- settings.js restores a focused Arrange action before a focused setting, because the step buttons sit inside data-setting cells.
- --s4-foot is written on the page as well as the rail, so band lists get scroll-margin-bottom of the Save bar height plus 12px at 1240px and under. The phone list gets scroll-margin-top 124px under the sticky band (about 109px).
- Reset stays off at the default order (PR #130 behaviour), though the board shows it on.
- Phone steps keep up and down arrows with the owner's Earlier and Later names.
rejected:
- focusFirst on desktop: it would skip the pressed Arrange in the owner's tab order.
- A measured custom property for the sticky band height: a fixed 124px was enough after the judge's 375 measurement (1.2px clearance at 110px).
files: dashboard/static/app.css, dashboard/static/js/band_order.js, dashboard/static/js/icons.js, dashboard/static/js/pages/band.js, dashboard/static/js/pages/band_arrange.js, dashboard/static/js/pages/band_drag.js, dashboard/static/js/pages/settings.js, dashboard/static/strings.json, tests/js/band_reorder_checks.mjs, tests/js/edit_card_checks.mjs, tests/test_static_shell.py, tests/test_band_arrange_e2e.py
gotchas:
- fakedom createPage() defaults to narrow, so matchMedia answers phone. Desktop band checks need a wide page.
- test_static_shell's scope test allowed only .s4- to .s6- classes; it now accepts .s7-.
- A JS click() never moves focus in E2E, so the desktop Arrange press is focus plus Enter.
- A new Chrome tab opened at 500x679 and resize_window did not change it, so the 1100x700 Save bar check never ran in a browser.
follow-ups:
- Done November 3: MR_E2E=1 test_band_arrange_e2e.py passed 8 of 8 (owner-approved run).
- The 1100x700 Save bar clearance is unchecked in a real browser.
- Done November 3: a move across the fold also names the setting it pushed the other way (sr_moved_into_band_dropped, sr_moved_to_more_raised).
- CONSOLIDATION apply skipped by the owner's brief; the HiveMind check already fails on the base (INDEX.md says 37 entries, folder has 38).

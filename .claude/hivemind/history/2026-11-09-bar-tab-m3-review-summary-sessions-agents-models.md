### F-7132 Bar Tab M3 Review: Summary, Sessions, Agents, Models and Session review
status: in-progress
kind: code
dates: 2026-11-09 .. 2026-11-09
refs:
  commit: pending (branch feature/bartab-m3)
summary: Built the five Review routes on the store (review windows, scan, agent setup, five cached routes), an hourly rollup that keeps every range under 250 ms on a year of history, and the Review shell, Summary, Sessions, Agents, Models and Session review pages to the approved pass 7 to 9 boards. The old usage payloads and the long build match exactly.
decisions:
- Prior window rule stays same_time, as the old app had it (owner)
- Hourly rollup (migration 0008, hour_usage keyed hour first, backfilled) read with minute rows only at cut points, so every zone stays exact, half-hour and 45-minute offsets included (owner question 7, option A)
- All picks days, weeks or months from the stored span and has no pager (owner)
- Cost chart bars split by model only, with a Made of kind line linking to Models; pattern bars stay on Models (owner)
- Sessions page in fifties with Show N more and focus on the first new row; one page-level empty card; the API-rate note once per page (owner)
- Replay control is a native range input, not the RAC Slider, whose page step is fixed at a tenth; Page keys move 5 minutes or one bucket (owner)
- A model setting with no value gives no set value, so Check shows Default, never the text "None"; this changes Live too
- Model check wording drops "its file" wherever the Main session can reach it; the compact Review card uses the board's one-line sentences (mc_l_*)
- Lane price cell shows "No price" with the model in a screen-reader span and title, an owner-approved departure from the M2 board
- VoiceOver moves to one pass at M9; every milestone keeps axe, keyboard walkthroughs at 375 and 1440, accessibility snapshots and forced colours (owner)
rejected:
- RAC Slider for the replay line, because of the fixed page step and number-only valuetext
- Keeping minute-only reads (4 s at 12 months) or SQL hour grouping alone (still over 3 s)
- Denormalised agent and folder columns on hour_usage, because a run's agent type arrives late
- Kind patterns on the Summary cost chart (owner picked option A)
files: app/server (review_windows, review_query, review_answers, api_review, agent_setup, server_zone, migrations 0007 and 0008), app/oracle/long_demo.py, app/fixtures/oracle/demo-long/, app/web/src (api/review.ts, lib/range, lib/replay, lib/review-*, components ReplayLine, Pager, Segmented, ScopeBar, ShareBar, pages/review/*), app/web/e2e (review, review-agents, session-review, replay-keys specs), docs/rebuild/planning/m3-build.md, docs/design/redesign-a/m3.*
gotchas:
- Aware datetimes sharing one ZoneInfo compare by wall time and miss the repeated hour on November 1, so review windows are UTC with local dates from the zone
- Chromium's native Page Up moves a tenth of a range input; the handler cancels it and writes the value itself (J-dad4)
- StackedBars floored its scale at $1, which squashed charts of cents
- Parallel page workers collided on global CSS class names (J-0ba9) and on test-results (J-c864)
facts: J-f0a7, J-dad4, J-c864, J-b0ae, J-ac3a, J-5bcb, J-0ba9, J-b7dc, M-b3d4, M-683f, M-380c, M-7734
follow-ups:
- Owner review of the new copy (model check rewording, mc_l_* lines, ch_scope_note, ag_setup_card, md_img_none, sel_value) and tech-writer's open questions
- Decide which kind pattern set wins (board and Models page CSS against StackedBars' KindPattern)
- Summary tiles' accessible text joins label and qualifier with no space; check in the M9 VoiceOver pass
- Project picker dialog rows overlap (seen by the judge, from an earlier milestone)

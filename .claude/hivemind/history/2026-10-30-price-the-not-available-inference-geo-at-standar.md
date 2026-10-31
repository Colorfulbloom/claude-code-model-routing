### F-5df3 Price the not_available inference geo at standard rates (PR #68)
status: shipped
kind: code
dates: 2026-10-30 .. 2026-10-30
refs:
  commit: 45ff10c69cb01591bfd4debf4c3ebdce574e75c1 (branch fix/price-geo-not-available, merged into development)
summary: Real transcripts carry inference_geo "not_available", which dashboard/prices.json did not list, so those rows would have shown Not priced. The geo table now lists it with a multiplier of 1.
decisions:
- Multiplier 1. The usage report docs say the value marks models that don't support specifying inference_geo, and the pricing page says those models always use standard pricing. Only "us" carries 1.1x.
- Only the exact value is priced. Lookalikes such as "not-available" and "NOT_AVAILABLE" stay Not priced.
rejected:
- Leaving the value unpriced, because real rows would have shown Not priced.
files: dashboard/prices.json, tests/test_prices.py
gotchas:
- No page ties the label to billing by name, so this is a reading of the docs, not a stated rule. Every cost is labeled an estimate, so a wrong reading would not pass as an exact figure.
follow-ups:
- none

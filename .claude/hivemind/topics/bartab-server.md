# bartab-server

### M-b3d4 A new migration: LATEST and the TEXT allowlist
fact: A Bar Tab migration bumps LATEST in app/server/tests/test_store.py, and each new TEXT column joins TEXT_ALLOWLIST there, or the store test fails.
check: grep -n "^LATEST\|^TEXT_ALLOWLIST" app/server/tests/test_store.py
evidence: app/server/tests/test_store.py, app/server/migrations/0008_hour_usage.sql
fp: dcb5db4efef8
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### M-683f Review speed is Python row work, not SQL
fact: On the year-size store, row transfer and per-row Python cost more than the query. Merged partial sums (_Acc.merge), no pydantic objects for runs and fromisoformat over strptime took Summary at 12 months from about 300 to 200 ms after the hourly rollup.
check: grep -n "def merge\|fromisoformat" app/server/review_query.py
evidence: app/server/review_query.py, app/server/tests/test_review_size.py
fp: 31d961de8728
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### M-380c test_review_size runs in the default suite
fact: test_review_size.py is marked slow, but nothing deselects slow by default, so it runs in every pytest run (about 20 s at 5 calls). It asserts p95 under 250 ms, or 750 ms with CI set (CI_SLACK 3.0). REVIEW_SIZE_CALLS=20 takes the full sample.
check: grep -n "CI_SLACK =\|REVIEW_SIZE_CALLS" app/server/tests/test_review_size.py
evidence: app/server/tests/test_review_size.py, app/pyproject.toml
fp: d9d4ecfc8ec1
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

### M-7734 hour_usage must equal minute_usage by hour
fact: The ingest writer rebuilds each touched (session, hour) group of hour_usage with the minute cells, and Store.close() in the tests asserts hour rows equal minute rows grouped by hour, so a new write path that skips the hour rebuild fails every ingest test.
check: grep -n "assert_hours_follow_minutes" app/server/tests/ingest_helpers.py
evidence: app/server/ingest.py, app/server/tests/ingest_helpers.py
fp: c2298b6a2d93
as_of: 0ff7fdf 2026-11-09
author: deep-reasoner
created: 2026-11-09
last_used: 2026-11-09
uses: 0

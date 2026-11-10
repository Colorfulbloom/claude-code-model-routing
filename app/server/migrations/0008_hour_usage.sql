-- Usage per UTC hour, a rollup of minute_usage for the Review routes. hour is the
-- hour's first minute in minute_usage's text format (YYYY-MM-DDTHH:00). The columns
-- are minute_usage's with hour in place of minute, and a row holds the sum of that
-- key's minute cells in the hour. first_minute is the earliest of those minutes,
-- because a run's start and a session's first request in a window are read from it.
-- The table holds no folder and no agent type: both are learned late (a run's type
-- arrives with its meta file), so a read joins sessions and runs as it does for
-- minute_usage.
--
-- The key starts with hour, so a window reads one run of the table in order, with no
-- second lookup per row. The writer's per-hour rebuild also starts from hour.
--
-- The single writer keeps it in step: every time it rebuilds minute cells it rebuilds
-- the hours that hold them (ingest.py, _rebuild_hours). The backfill below makes an
-- existing store match its minute_usage.
CREATE TABLE hour_usage (
    hour TEXT NOT NULL,
    session_id TEXT NOT NULL,
    run_key TEXT NOT NULL,
    model TEXT NOT NULL,
    effort TEXT NOT NULL DEFAULT '',
    speed TEXT NOT NULL DEFAULT '',
    service_tier TEXT NOT NULL DEFAULT '',
    inference_geo TEXT NOT NULL DEFAULT '',
    tier TEXT NOT NULL DEFAULT '',
    input INTEGER NOT NULL DEFAULT 0,
    output INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write_5m INTEGER NOT NULL DEFAULT 0,
    cache_write_1h INTEGER NOT NULL DEFAULT 0,
    thinking INTEGER NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0,
    first_minute TEXT NOT NULL,
    PRIMARY KEY (
        hour, session_id, run_key, model, effort, speed, service_tier,
        inference_geo, tier
    )
) WITHOUT ROWID;

-- A session's whole life (Review's "whole" numbers for a session that started before
-- the window) reads its hour rows by session.
CREATE INDEX hour_usage_session ON hour_usage (session_id);

INSERT INTO hour_usage (
    hour, session_id, run_key, model, effort, speed, service_tier, inference_geo,
    tier, input, output, cache_read, cache_write_5m, cache_write_1h, thinking,
    requests, first_minute
)
SELECT
    substr(minute, 1, 13) || ':00', session_id, run_key, model, effort, speed,
    service_tier, inference_geo, tier, SUM(input), SUM(output), SUM(cache_read),
    SUM(cache_write_5m), SUM(cache_write_1h), SUM(thinking), SUM(requests),
    MIN(minute)
FROM minute_usage
GROUP BY
    session_id, run_key, substr(minute, 1, 13), model, effort, speed, service_tier,
    inference_geo, tier;

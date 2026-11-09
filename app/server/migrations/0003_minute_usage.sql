-- Usage per minute cell. minute is UTC YYYY-MM-DDTHH:MM. The key columns are NOT
-- NULL because a WITHOUT ROWID key cannot hold NULL, so an absent effort, speed,
-- service tier or geo is the empty string.
CREATE TABLE minute_usage (
    session_id TEXT NOT NULL,
    run_key TEXT NOT NULL,
    minute TEXT NOT NULL,
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
    PRIMARY KEY (
        session_id, run_key, minute, model, effort, speed, service_tier,
        inference_geo, tier
    )
) WITHOUT ROWID;

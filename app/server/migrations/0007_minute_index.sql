-- Review sums minute_usage over a time window. The primary key starts with
-- session_id, so a range query without this index reads every row.
CREATE INDEX minute_usage_minute ON minute_usage (minute);

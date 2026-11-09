-- A run's number among the runs of its agent type in one session, kept once it is
-- assigned. The ingest sets it when it first sees the run with a type, so a late
-- file takes the next free number and no shown row is renamed. NULL means the run
-- has no type yet (the timeline reads that as 1). The backfill numbers existing
-- runs by first request, then run id.
ALTER TABLE runs ADD COLUMN label_n INTEGER;

UPDATE runs SET label_n = (
    SELECT COUNT(*) + 1
    FROM runs AS o
    WHERE o.session_id = runs.session_id
        AND o.agent_type = runs.agent_type
        AND (
            COALESCE((SELECT MIN(q.ts) FROM requests AS q WHERE q.file_id = o.file_id), '~'),
            o.run_id
        ) < (
            COALESCE((SELECT MIN(q.ts) FROM requests AS q WHERE q.file_id = runs.file_id), '~'),
            runs.run_id
        )
)
WHERE agent_type IS NOT NULL AND agent_type <> '';

-- The timeline reads one session's files and events by session id.
CREATE INDEX files_session ON files (session_id);
CREATE INDEX run_events_session ON run_events (session_id, at);

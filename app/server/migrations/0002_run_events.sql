-- Launch, brief and stop rows per file, and the small resume state for each file.
CREATE TABLE run_events (
    file_id INTEGER NOT NULL REFERENCES files (id),
    seq INTEGER NOT NULL,
    session_id TEXT,
    run_key TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('launch', 'brief', 'stop')),
    at TEXT,
    finished INTEGER NOT NULL DEFAULT 0,
    by_kind TEXT,
    by_run TEXT,
    PRIMARY KEY (file_id, seq)
);

-- state is a small JSON object of flags and counters (stopped, finished, last
-- round), never row text.
CREATE TABLE file_state (
    file_id INTEGER PRIMARY KEY REFERENCES files (id),
    "offset" INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT '{}'
);

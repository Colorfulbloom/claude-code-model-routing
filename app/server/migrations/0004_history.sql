-- Pass and backup history. The meta table also gets the keys first_ingest,
-- last_pass and tier_hash, written by the ingest worker as it runs. They are not
-- seeded here.
CREATE TABLE passes (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    started TEXT NOT NULL,
    finished TEXT,
    files_seen INTEGER NOT NULL DEFAULT 0,
    files_read INTEGER NOT NULL DEFAULT 0,
    bytes_read INTEGER NOT NULL DEFAULT 0,
    rows_added INTEGER NOT NULL DEFAULT 0,
    rescans INTEGER NOT NULL DEFAULT 0,
    error_code TEXT
);

CREATE TABLE backups (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    file TEXT NOT NULL,
    bytes INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 0,
    reason_code TEXT CHECK (
        reason_code IS NULL
        OR reason_code IN ('no_space', 'unwritable', 'check_failed', 'copy_failed')
    )
);

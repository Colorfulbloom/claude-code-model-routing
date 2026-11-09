-- Bar Tab store, base tables. Counts are INTEGER and every timestamp is canonical
-- UTC text, so text order is time order. No table holds transcript row text.
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('main', 'agent', 'orphaned', 'superseded')),
    folder TEXT NOT NULL,
    session_id TEXT,
    run_id TEXT,
    dev INTEGER NOT NULL DEFAULT 0,
    inode INTEGER NOT NULL DEFAULT 0,
    size INTEGER NOT NULL DEFAULT 0,
    mtime_ns INTEGER NOT NULL DEFAULT 0,
    "offset" INTEGER NOT NULL DEFAULT 0,
    head_hash TEXT,
    last_line_hash TEXT,
    lines INTEGER NOT NULL DEFAULT 0,
    malformed INTEGER NOT NULL DEFAULT 0,
    synthetic INTEGER NOT NULL DEFAULT 0,
    no_id INTEGER NOT NULL DEFAULT 0,
    missing INTEGER NOT NULL DEFAULT 0,
    scans INTEGER NOT NULL DEFAULT 0,
    no_usage INTEGER NOT NULL DEFAULT 0,
    shrinks INTEGER NOT NULL DEFAULT 0,
    read_errors INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

-- One row per message key per file. A key can repeat across files, so the winner
-- is picked by the best_requests view.
CREATE TABLE requests (
    file_id INTEGER NOT NULL REFERENCES files (id),
    key TEXT NOT NULL,
    ts TEXT NOT NULL,
    input INTEGER NOT NULL DEFAULT 0,
    output INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write_5m INTEGER NOT NULL DEFAULT 0,
    cache_write_1h INTEGER NOT NULL DEFAULT 0,
    thinking INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    request_id TEXT,
    effort TEXT,
    speed TEXT,
    service_tier TEXT,
    inference_geo TEXT,
    PRIMARY KEY (file_id, key)
) WITHOUT ROWID;

CREATE INDEX requests_key ON requests (key);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    folder TEXT NOT NULL,
    project_key TEXT,
    first_ts TEXT,
    last_ts TEXT,
    cwd TEXT,
    branch TEXT,
    claude_version TEXT
);

CREATE TABLE runs (
    session_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    file_id INTEGER NOT NULL REFERENCES files (id),
    agent_type TEXT,
    PRIMARY KEY (session_id, run_id)
);

CREATE TABLE links (
    parent_file_id INTEGER NOT NULL REFERENCES files (id),
    child_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    ts TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (parent_file_id, child_id)
);

CREATE INDEX links_session_child ON links (session_id, child_id);

-- Every copy of every key, ranked. rn = 1 is the winner (larger output, then later
-- ts, then later path). Callers filter on rn, or read best_winners.
CREATE VIEW best_requests AS
SELECT
    r.file_id,
    r.key,
    r.ts,
    r.input,
    r.output,
    r.cache_read,
    r.cache_write_5m,
    r.cache_write_1h,
    r.thinking,
    r.model,
    r.request_id,
    r.effort,
    r.speed,
    r.service_tier,
    r.inference_geo,
    f.path,
    f.session_id,
    f.run_id,
    f.kind AS file_kind,
    ROW_NUMBER() OVER (
        PARTITION BY r.key ORDER BY r.output DESC, r.ts DESC, f.path DESC
    ) AS rn
FROM requests AS r
JOIN files AS f ON f.id = r.file_id;

CREATE VIEW best_winners AS
SELECT * FROM best_requests WHERE rn = 1;

-- One row per price fetch. models is the count of models in the copy.
-- cross_check_models is a JSON list of model names that disagreed.
CREATE TABLE price_copies (
    id INTEGER PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('litellm', 'openrouter')),
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL DEFAULT 0,
    check_ok INTEGER NOT NULL DEFAULT 0,
    reason_code TEXT,
    models INTEGER NOT NULL DEFAULT 0,
    cross_check_state TEXT,
    cross_check_models TEXT
);

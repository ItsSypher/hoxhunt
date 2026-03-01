CREATE TABLE IF NOT EXISTS reviews (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    reviewer         TEXT    NOT NULL,
    original_review  TEXT    NOT NULL,
    summary          TEXT,
    rating           INTEGER CHECK (rating BETWEEN 1 AND 10),
    sentiment        TEXT    CHECK (sentiment IN ('positive', 'negative')),
    status           TEXT    NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'done', 'failed')),
    error_message    TEXT,
    processed_at     TEXT,
    UNIQUE (reviewer, original_review)
);

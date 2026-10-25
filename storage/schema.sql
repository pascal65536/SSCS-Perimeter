PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS packages (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    registry TEXT NOT NULL,
    watchlist TEXT NOT NULL,
    github_repo TEXT,
    is_reference INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_log (
    event_id TEXT PRIMARY KEY,
    ingested_at TEXT NOT NULL,
    source_service TEXT NOT NULL,
    outcome TEXT NOT NULL,
    schema_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
    event_id TEXT PRIMARY KEY REFERENCES ingest_log(event_id),
    package_id INTEGER NOT NULL REFERENCES packages(id),
    version TEXT NOT NULL,
    released_at TEXT NOT NULL,
    uploader TEXT,
    size INTEGER,
    yanked INTEGER NOT NULL,
    sha256 TEXT
);
CREATE TABLE IF NOT EXISTS commits (
    event_id TEXT PRIMARY KEY REFERENCES ingest_log(event_id),
    repo TEXT NOT NULL,
    sha TEXT NOT NULL,
    author_login TEXT,
    committed_at TEXT NOT NULL,
    additions INTEGER,
    deletions INTEGER,
    files_changed INTEGER,
    is_merge INTEGER NOT NULL,
    is_anonymous INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS membership_events (
    event_id TEXT PRIMARY KEY REFERENCES ingest_log(event_id),
    repo TEXT NOT NULL,
    login TEXT NOT NULL,
    change_type TEXT NOT NULL,
    role TEXT NOT NULL,
    event_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_profiles (
    login TEXT PRIMARY KEY,
    account_created_at TEXT NOT NULL,
    followers INTEGER,
    public_repos INTEGER,
    snapshot_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pull_requests (
    event_id TEXT PRIMARY KEY REFERENCES ingest_log(event_id),
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    author TEXT,
    created_at TEXT NOT NULL,
    merged_at TEXT,
    merged_by TEXT,
    review_count INTEGER,
    touches_critical INTEGER NOT NULL,
    author_first_contrib_at TEXT
);
CREATE TABLE IF NOT EXISTS repo_snapshots (
    event_id TEXT PRIMARY KEY REFERENCES ingest_log(event_id),
    repo TEXT NOT NULL,
    date TEXT NOT NULL,
    stars INTEGER,
    forks INTEGER,
    watchers INTEGER,
    open_issues INTEGER,
    open_prs INTEGER
);
CREATE INDEX IF NOT EXISTS idx_releases_pit ON releases(released_at);
CREATE INDEX IF NOT EXISTS idx_commits_pit ON commits(committed_at);
CREATE INDEX IF NOT EXISTS idx_pr_pit ON pull_requests(created_at);

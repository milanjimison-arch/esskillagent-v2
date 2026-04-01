"""DDL schema string for E+S Orchestrator v3 SQLite database."""

from dataclasses import dataclass

SCHEMA_VERSION = 3

_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    description TEXT,
    file_path TEXT,
    parallel INTEGER DEFAULT 0,
    user_story TEXT,
    requirements TEXT,
    status TEXT DEFAULT 'pending',
    group_name TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    task_id TEXT,
    review_type TEXT,
    passed INTEGER,
    findings TEXT,
    raw_output TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    pipeline_id TEXT,
    stage TEXT,
    task_id TEXT,
    event_type TEXT,
    detail TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS stage_progress (
    pipeline_id TEXT,
    stage TEXT,
    status TEXT,
    started_at TEXT,
    completed_at TEXT,
    review_attempts INTEGER DEFAULT 0,
    checkpoint_data TEXT,
    PRIMARY KEY (pipeline_id, stage)
);

CREATE TABLE IF NOT EXISTS step_status (
    pipeline_id TEXT,
    stage TEXT,
    step TEXT,
    status TEXT,
    detail TEXT,
    updated_at TEXT,
    PRIMARY KEY (pipeline_id, stage, step)
);

CREATE TABLE IF NOT EXISTS lvl (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id TEXT,
    level TEXT,
    message TEXT,
    detail TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS checkpoints (
    pipeline_id TEXT,
    stage TEXT,
    step TEXT,
    state_json TEXT,
    created_at TEXT,
    PRIMARY KEY (pipeline_id, stage, step)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS pipelines (
    pipeline_id TEXT PRIMARY KEY,
    project_path TEXT NOT NULL,
    requirement_path TEXT,
    current_stage TEXT,
    status TEXT DEFAULT 'running',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS config_cache (
    pipeline_id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS task_groups (
    group_name TEXT PRIMARY KEY,
    sort_order INTEGER NOT NULL,
    task_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS artifacts (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    stage        TEXT NOT NULL,
    kind         TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    blob         BLOB,
    created_ts   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);

CREATE TABLE IF NOT EXISTS lvl_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL,
    stage      TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload    TEXT,
    ts         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lvl_events_run_id ON lvl_events(run_id);

CREATE TABLE IF NOT EXISTS pipeline_lvl_events (
    event_id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    prev_hash TEXT,
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_artifacts (
    artifact_id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    name TEXT NOT NULL,
    stage TEXT NOT NULL,
    file_path TEXT NOT NULL,
    frozen_hash TEXT,
    is_frozen INTEGER DEFAULT 0,
    is_valid INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(pipeline_id, name)
);
"""


@dataclass(frozen=True)
class ArtifactRecord:
    """Immutable data record matching the artifacts table columns."""

    id: str = ""
    run_id: str = ""
    stage: str = ""
    kind: str = ""
    content_hash: str = ""
    blob: bytes | None = None
    created_ts: str = ""


@dataclass(frozen=True)
class LvlEventRecord:
    """Immutable data record matching the lvl_events table columns."""

    id: int = 0
    run_id: str = ""
    stage: str = ""
    event_type: str = ""
    payload: str | None = None
    ts: str = ""

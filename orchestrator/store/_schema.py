"""DDL schema string for E+S Orchestrator v2 SQLite database."""

from dataclasses import dataclass

SCHEMA_VERSION = 2  # stub: tests expect 3

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
"""


@dataclass(frozen=True)
class ArtifactRecord:
    """Stub: fields are intentionally wrong — tests will fail on field assertions."""

    id: str = ""


@dataclass(frozen=True)
class LvlEventRecord:
    """Stub: fields are intentionally wrong — tests will fail on field assertions."""

    id: int = 0

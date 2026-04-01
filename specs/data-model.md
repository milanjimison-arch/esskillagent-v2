# Data Model: E+S Orchestrator v2

**Date**: 2026-04-02 | **Source**: `specs/spec.md` + existing `orchestrator/store/models.py`

---

## Design Principles

- All dataclasses use `@dataclass(frozen=True)` (Constitution VII)
- Sequences use `tuple[...]`, not `list[...]` (immutability)
- Dict fields are opaque JSON blobs; callers must not mutate post-construction
- All public fields have complete type annotations
- Enums use `str` mixin for direct serialization (`class X(str, Enum)`)

---

## Enums

### Stage

Pipeline stages in strict execution order (Constitution I).

```python
class Stage(str, Enum):
    SPEC = "spec"
    PLAN = "plan"
    IMPLEMENT = "implement"
    ACCEPTANCE = "acceptance"
```

### TaskStatus

Lifecycle status for tasks and pipelines.

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"          # NEW: task completed successfully
    BLOCKED = "blocked"    # NEW: task failed, skipped for now
    PASSED = "passed"      # stage-level pass
    FAILED = "failed"      # stage-level fail
    SKIPPED = "skipped"    # explicitly skipped by config
```

**State Machine -- Task Lifecycle**:

```
            +----------+
            | PENDING  |
            +----+-----+
                 |
                 v
            +----------+
            | RUNNING  |
            +----+-----+
                 |
         +-------+-------+
         |               |
         v               v
    +----------+    +----------+
    |   DONE   |    | BLOCKED  |
    +----------+    +----+-----+
                         |
                         v  (retry)
                    +----------+
                    | RUNNING  |  --> DONE or BLOCKED again
                    +----------+
```

**State Machine -- Pipeline Lifecycle**:

```
    PENDING --> RUNNING --> PASSED
                  |
                  +--> FAILED
```

### ReviewVerdict

```python
class ReviewVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
```

### TDDPhase (NEW)

```python
class TDDPhase(str, Enum):
    RED = "red"
    GREEN = "green"
    REFACTOR = "refactor"
```

### MonitorAction (NEW)

Actions the PipelineMonitor can recommend.

```python
class MonitorAction(str, Enum):
    CONTINUE = "continue"
    PAUSE = "pause"
    ROLLBACK = "rollback"
    TERMINATE = "terminate"
```

---

## Core DTOs (existing, from `orchestrator/store/models.py`)

### Task

```python
@dataclass(frozen=True)
class Task:
    id: str                              # e.g. "T001"
    name: str                            # Human-readable description
    stage: Stage                         # Owning pipeline stage
    status: TaskStatus                   # Current lifecycle status
    created_at: datetime                 # UTC creation time
    updated_at: datetime                 # UTC last status change
    metadata: dict[str, Any] = field(default_factory=dict)
    # metadata keys: file_path, parallel, user_story, requirements, group_name
```

### Pipeline

```python
@dataclass(frozen=True)
class Pipeline:
    id: str                              # e.g. "pipeline-001"
    current_stage: Stage                 # Stage currently executing
    status: TaskStatus                   # Aggregate pipeline status
    created_at: datetime                 # UTC creation time
    tasks: tuple[Task, ...] = field(default_factory=tuple)
```

### StageProgress

```python
@dataclass(frozen=True)
class StageProgress:
    stage: Stage
    status: TaskStatus
    attempts: int                        # 1-indexed attempt count
    max_attempts: int
    started_at: datetime
    completed_at: datetime | None = None
```

### Checkpoint

```python
@dataclass(frozen=True)
class Checkpoint:
    pipeline_id: str
    stage: Stage
    timestamp: datetime
    data: dict[str, Any] = field(default_factory=dict)
    # data keys: artifact_paths, content_hashes, completed_task_ids (for implement)
```

### ReviewResult

```python
@dataclass(frozen=True)
class ReviewResult:
    verdict: ReviewVerdict
    score: float                         # [0.0, 1.0]
    reviewer: str                        # e.g. "code-reviewer"
    issues: tuple[str, ...] = field(default_factory=tuple)
    suggestions: tuple[str, ...] = field(default_factory=tuple)
```

### Evidence

```python
@dataclass(frozen=True)
class Evidence:
    type: str                            # e.g. "test_output", "lint_result"
    content: str                         # Raw evidence text
    source: str                          # e.g. "pytest", "ruff"
    timestamp: datetime
```

### AgentInfo

```python
@dataclass(frozen=True)
class AgentInfo:
    name: str                            # Agent directory name
    role: str                            # e.g. "spec", "plan", "implement"
    model: str                           # Model identifier
    capabilities: tuple[str, ...] = field(default_factory=tuple)
```

### AgentResult

```python
@dataclass(frozen=True)
class AgentResult:
    agent: AgentInfo
    output: str                          # Primary text output
    duration_ms: int                     # Wall-clock duration
    success: bool
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
```

### OrchestratorConfig

```python
@dataclass(frozen=True)
class OrchestratorConfig:
    project_dir: str
    stages: tuple[Stage, ...] = (Stage.SPEC, Stage.PLAN, Stage.IMPLEMENT, Stage.ACCEPTANCE)
    max_retries: int = 3
    parallel: bool = False
    skip_stages: tuple[Stage, ...] = field(default_factory=tuple)
```

---

## New DTOs (to be added)

### ScanResult (perception.py)

Result of scanning agent output for clarification/research markers.

```python
@dataclass(frozen=True)
class ScanResult:
    needs_clarification: bool            # True if NC markers or uncertainty detected
    needs_research: bool                 # True if NR markers or tech-risk detected
    nc_markers: tuple[str, ...] = field(default_factory=tuple)   # Extracted [NC:...] values
    nr_markers: tuple[str, ...] = field(default_factory=tuple)   # Extracted [NR:...] values
    uncertainty_score: float = 0.0       # 0.0 = confident, 1.0 = highly uncertain
    details: dict[str, Any] = field(default_factory=dict)
    # details keys: question_count, tbd_count, hedging_count
```

### HealthReport (monitor.py)

Result of PipelineMonitor health check.

```python
@dataclass(frozen=True)
class HealthReport:
    action: MonitorAction                # Recommended action
    blocked_ratio: float                 # 0.0 to 1.0
    blocked_tasks: tuple[str, ...] = field(default_factory=tuple)  # Task IDs
    stale_cascade_depth: int = 0         # How many levels of BLOCKED dependencies
    convergence_trend: str = "unknown"   # "improving", "stagnant", "degrading"
    recommendations: tuple[str, ...] = field(default_factory=tuple)
    timestamp: datetime | None = None
```

### ArtifactHash (stages/)

Content hash for artifact freezing at stage completion.

```python
@dataclass(frozen=True)
class ArtifactHash:
    path: str                            # Absolute file path
    hash_sha256: str                     # SHA-256 hex digest
    stage: Stage                         # Stage that produced this artifact
    frozen_at: datetime                  # UTC freeze timestamp
```

### PipelineEvent (store/models.py)

Unified event type for the LVL decision-support stream.

```python
@dataclass(frozen=True)
class PipelineEvent:
    pipeline_id: str
    event_type: str                      # e.g. "stage_complete", "task_blocked", "monitor_pause"
    stage: Stage | None = None
    task_id: str | None = None
    detail: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## SQLite Schema (existing tables)

All tables defined in `orchestrator/store/_schema.py`. v2 must NOT alter existing table schemas (Constitution constraint) but may add new tables.

### Existing Tables

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| `tasks` | `task_id` | Task records with status, file_path, parallel flag |
| `reviews` | `review_id` | Review results linked to tasks |
| `evidence` | `evidence_id` | Evidence chain: pipeline -> stage -> task |
| `stage_progress` | `(pipeline_id, stage)` | Stage retry tracking |
| `step_status` | `(pipeline_id, stage, step)` | Sub-step status within stages |
| `lvl` | `id` (autoincrement) | LVL audit/decision log |
| `checkpoints` | `(pipeline_id, stage, step)` | Checkpoint state snapshots |
| `settings` | `key` | Configuration key-value store |
| `pipelines` | `pipeline_id` | Pipeline metadata |
| `config_cache` | `pipeline_id` | Cached merged config per pipeline |
| `task_groups` | `group_name` | Task group ordering |

### New Tables (proposed)

#### `artifact_hashes`

Stores content hashes for frozen artifacts at stage completion.

```sql
CREATE TABLE IF NOT EXISTS artifact_hashes (
    pipeline_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    file_path TEXT NOT NULL,
    hash_sha256 TEXT NOT NULL,
    frozen_at TEXT NOT NULL,
    PRIMARY KEY (pipeline_id, stage, file_path)
);
```

#### `monitor_events`

Stores PipelineMonitor health check results and recommendations.

```sql
CREATE TABLE IF NOT EXISTS monitor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id TEXT NOT NULL,
    action TEXT NOT NULL,
    blocked_ratio REAL NOT NULL,
    stale_cascade_depth INTEGER DEFAULT 0,
    convergence_trend TEXT DEFAULT 'unknown',
    recommendations TEXT,
    created_at TEXT NOT NULL
);
```

---

## Store Query Interface

### Task Queries (existing in queries.py)

| Function | Signature | Returns |
|----------|-----------|---------|
| `upsert_task_record` | `(store, task_id, description, file_path, parallel, user_story, requirements, status, group_name)` | `TaskRecord` |
| `get_task_record` | `(store, task_id)` | `TaskRecord \| None` |
| `list_task_records` | `(store)` | `tuple[TaskRecord, ...]` |
| `update_task_status_record` | `(store, task_id, status)` | `TaskRecord` |

### Evidence Queries (existing in queries.py)

| Function | Signature | Returns |
|----------|-----------|---------|
| `insert_evidence_record` | `(store, evidence_id, pipeline_id, stage, task_id, event_type, detail)` | `EvidenceRecord` |
| `list_evidence_records` | `(store, pipeline_id)` | `tuple[EvidenceRecord, ...]` |
| `list_evidence_records_for_stage` | `(store, pipeline_id, stage)` | `tuple[EvidenceRecord, ...]` |

### LVL Queries (existing in _lvl_queries.py)

| Function | Signature | Returns |
|----------|-----------|---------|
| `insert_lvl_log` | `(store, pipeline_id, level, message, detail)` | `LvlLogRecord` |
| `list_lvl_logs` | `(store, pipeline_id)` | `tuple[LvlLogRecord, ...]` |
| `list_lvl_logs_by_level` | `(store, pipeline_id, level)` | `tuple[LvlLogRecord, ...]` |

### New Queries (to be added)

| Function | Signature | Returns | Purpose |
|----------|-----------|---------|---------|
| `create_pipeline_record` | `(store, pipeline_id, project_path, requirement_path)` | `PipelineRecord` | Create pipeline entry |
| `get_pipeline_record` | `(store, pipeline_id)` | `PipelineRecord \| None` | Fetch pipeline by ID |
| `update_pipeline_stage` | `(store, pipeline_id, stage, status)` | `PipelineRecord` | Update current stage |
| `save_checkpoint_record` | `(store, pipeline_id, stage, step, state_json)` | `CheckpointRecord` | Persist checkpoint |
| `get_latest_checkpoint` | `(store, pipeline_id)` | `CheckpointRecord \| None` | Resume point |
| `upsert_artifact_hash` | `(store, pipeline_id, stage, file_path, hash_sha256)` | `ArtifactHashRecord` | Freeze artifact |
| `list_artifact_hashes` | `(store, pipeline_id, stage)` | `tuple[ArtifactHashRecord, ...]` | Verify artifacts |
| `insert_monitor_event` | `(store, pipeline_id, action, blocked_ratio, ...)` | `MonitorEventRecord` | Log health check |
| `get_blocked_task_ratio` | `(store, pipeline_id)` | `float` | BLOCKED ratio for monitor |
| `list_tasks_by_status` | `(store, status)` | `tuple[TaskRecord, ...]` | Filter tasks |

---

## Validation Rules

### Task Validation

- `task_id` must match pattern `T\d{3}` (e.g. T001, T042)
- `description` must not be empty
- `file_path` must not be empty for parallel (`[P]`) tasks (Constitution V)
- `status` must be a valid `TaskStatus` enum value
- Parallel tasks in the same group must have non-overlapping `file_path` values

### Pipeline Validation

- `pipeline_id` must not be empty
- `current_stage` must be a valid `Stage` enum value
- Stage transitions must follow strict order: spec -> plan -> implement -> acceptance
- No stage may be skipped unless listed in `skip_stages` config

### Checkpoint Validation

- `state_json` must be valid JSON
- For implement stage checkpoints, `completed_task_ids` must reference existing tasks
- Checkpoint `stage` must match the stage that produced it

### Monitor Thresholds

- `blocked_ratio > 0.5` triggers `PAUSE` action
- `stale_cascade_depth > 3` triggers `ROLLBACK` recommendation
- `convergence_trend == "degrading"` for 3+ consecutive checks triggers `TERMINATE` recommendation

---

## State Transitions

### Stage Lifecycle

```
                    +---> SKIPPED (if in skip_stages config)
                    |
    PENDING ---> RUNNING ---> PASSED (review gate passed)
                    |
                    +---> FAILED (max retries exhausted)
```

### Review Gate Flow

```
    run() --> _do_review() --> PASS --> _persist_checkpoint() --> StageResult(passed=True)
                  |
                  v
                FAIL --> _do_fix() --> _do_review() --> ... (up to max_retries)
                                                         |
                                                         v
                                              StageResult(passed=False, error="max retries")
```

### TDD Cycle (per task)

```
    Phase A (RED):
        Agent writes tests only --> CheckStrategy.tests_must_fail()
            PASS (tests fail as expected) --> proceed to GREEN
            FAIL (tests pass unexpectedly or import error) --> BLOCKED

    Phase B (GREEN):
        Agent implements code --> CheckStrategy.tests_must_pass()
            PASS (tests pass) --> commit + review
            FAIL (tests still fail) --> retry with error context (up to max_green_retries)
                                    --> BLOCKED after exhausting retries
```

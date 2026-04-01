# Data Model: E+S Orchestrator v2

**Date**: 2026-04-01 | **Source**: [spec.md](spec.md), [constitution.md](constitution.md)

All data transfer objects use `@dataclass(frozen=True)` per Constitution Principle VII. Mutable state lives only in the SQLite store; in-memory representations are always immutable snapshots.

---

## Core Entities

### Task

A unit of work within the implement stage. Parsed from tasks.md.

```python
@dataclass(frozen=True)
class Task:
    task_id: str            # "T001", "T002", etc. Numeric sort key.
    description: str        # Free text after FR tags, before em-dash
    file_path: str          # Primary file path (after em-dash separator)
    parallel: bool          # True if [P] flag present
    user_story: str | None  # "US1", "US2", etc. or None
    requirements: list[str] # ["FR-001", "FR-002"] -- extracted from [FR-###] tags
    group: TaskGroup        # setup | us_N | polish (computed by validator)
    status: TaskStatus      # pending | red_pass | green_pass | failed | skipped
```

**Validation rules**:
- `task_id` must match pattern `T\d+`
- `file_path` must be non-empty when `parallel` is True (FR-008, SPEC-023)
- `requirements` must contain at least one FR tag
- Em-dash (`--`) separator between description and file_path is mandatory (Constitution V)

**Parsed format** (tasks.md contract):
```
- [ ] T001 [P] [US1] [FR-001] [FR-002] Implement user auth -- src/auth.py
- [ ] T002 [US1] [FR-003] Add login form -- src/login.py
- [ ] T003 [FR-010] Setup CI pipeline -- .github/workflows/ci.yml
```

### TaskGroup (Enum)

```python
class TaskGroup(str, Enum):
    SETUP = "setup"     # Tasks without [US*] tag, before first US task
    POLISH = "polish"   # Tasks without [US*] tag, after last US task
    # US groups are dynamic: "us_1", "us_2", etc.
```

**Sort order**: SETUP first, then US groups in numeric order, then POLISH last. Within each group, tasks are sorted by numeric task_id (FR-024, FR-026).

### TaskStatus (Enum)

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    RED_PASS = "red_pass"       # RED phase verified (test fails correctly)
    GREEN_PASS = "green_pass"   # GREEN phase verified (test passes)
    FAILED = "failed"           # Exceeded retry limit
    SKIPPED = "skipped"         # Skipped by user or dependency failure
```

**State transitions**:
```
PENDING -> RED_PASS -> GREEN_PASS
PENDING -> FAILED  (RED phase exceeded retries)
RED_PASS -> FAILED (GREEN phase exceeded retries)
PENDING -> SKIPPED (explicit skip)
```

### Pipeline

A single execution of the four-stage workflow for a project.

```python
@dataclass(frozen=True)
class Pipeline:
    pipeline_id: str          # UUID, generated at creation
    project_path: str         # Absolute path to project directory
    requirement_path: str     # Absolute path to requirement document
    current_stage: StageName  # Which stage is active
    status: PipelineStatus    # running | paused | completed | failed
    created_at: str           # ISO 8601 timestamp
    updated_at: str           # ISO 8601 timestamp
```

### StageName (Enum)

```python
class StageName(str, Enum):
    SPEC = "spec"
    PLAN = "plan"
    IMPLEMENT = "implement"
    ACCEPTANCE = "acceptance"
```

### PipelineStatus (Enum)

```python
class PipelineStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"       # Interrupted, checkpoint saved
    COMPLETED = "completed"
    FAILED = "failed"
```

### StageProgress

Tracks completion state of each stage within a pipeline.

```python
@dataclass(frozen=True)
class StageProgress:
    pipeline_id: str
    stage: StageName
    status: StageStatus     # pending | running | review | passed | failed
    started_at: str | None
    completed_at: str | None
    review_attempts: int    # Number of review+fix cycles
    checkpoint_data: str | None  # JSON blob for resume
```

### StageStatus (Enum)

```python
class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    REVIEW = "review"       # In review gate
    PASSED = "passed"       # Review gate passed
    FAILED = "failed"       # Review gate failed after max retries
```

### Checkpoint

Persisted state snapshot enabling pipeline resume after interruption (FR-002).

```python
@dataclass(frozen=True)
class Checkpoint:
    pipeline_id: str
    stage: StageName
    step: str               # Sub-step within stage (e.g., "constitution", "specify")
    state_json: str          # Serialized state for resume
    created_at: str
```

### ReviewResult

Outcome of a code/security/brooks review.

```python
@dataclass(frozen=True)
class ReviewResult:
    review_type: ReviewType  # code | security | brooks
    passed: bool
    findings: list[str]      # List of issues found
    has_feature_gap: bool    # True if missing functionality detected
    supplemental_tasks: list[str]  # Task descriptions for feature gaps
    raw_output: str          # Full agent output for audit
```

### ReviewType (Enum)

```python
class ReviewType(str, Enum):
    CODE = "code"
    SECURITY = "security"
    BROOKS = "brooks"
```

### Evidence

Audit trail record for LVL compliance (FR-037).

```python
@dataclass(frozen=True)
class Evidence:
    evidence_id: str         # UUID
    pipeline_id: str
    stage: StageName
    task_id: str | None      # Null for stage-level evidence
    event_type: str          # "agent_call", "review", "check", "commit", etc.
    detail: str              # JSON blob with event-specific data
    created_at: str
```

### AgentInfo

Registration record for an AI agent.

```python
@dataclass(frozen=True)
class AgentInfo:
    name: str                # Agent identifier (e.g., "specifier", "code-reviewer")
    directory: str           # Absolute path to agent directory
    knowledge_paths: list[str]  # Absolute paths to knowledge base files
    stages: list[StageName]  # Which stages this agent participates in
```

### AgentResult

Return value from an agent invocation.

```python
@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    output: str              # Agent's text output
    session_id: str | None   # For session continuation
    success: bool
    error: str | None
    token_usage: int | None  # Approximate token count
```

---

## Configuration Model

### OrchestratorConfig

Merged configuration from all layers (FR-019 to FR-021).

```python
@dataclass(frozen=True)
class OrchestratorConfig:
    # Model selection
    models: ModelConfig

    # Test execution
    local_test: bool              # True = LocalCheckStrategy, False = CICheckStrategy
    test_command: str             # e.g., "pytest", "npm test", "cargo test"

    # Timeouts and retries
    ci_timeout: int               # Seconds to wait for CI completion
    max_retries: int              # General retry limit
    max_green_retries: int        # GREEN phase retry limit
    max_fix_retries: int          # Auto-fix loop retry limit
    stage_timeout: int            # Max seconds per stage
    retry_base_delay: float       # Base delay for exponential backoff (seconds)
    retry_multiplier: float       # Backoff multiplier

    # Stage control
    skip_stages: list[StageName]  # Explicit stage skipping (FR-003)

    # Stack and CI
    stack_config: StackConfig     # Technology stack registration
    ci_jobs: dict[str, list[str]] # Stack -> CI job name mapping

    # Paths
    source_dirs: list[str] | None # Explicit source dirs for git add; None = auto-detect
    agent_base_path: str          # Absolute path to ESSKILLAGENT directory

    # Optional features
    wave_enabled: bool
    notifications_enabled: bool
```

### ModelConfig

```python
@dataclass(frozen=True)
class ModelConfig:
    default: str      # e.g., "claude-sonnet-4-6"
    spec: str         # Model for spec stage (typically opus)
    reviewer: str     # Model for review agents (typically opus)
```

### StackConfig

Extensible technology stack registration (FR-045).

```python
@dataclass(frozen=True)
class StackConfig:
    extensions: dict[str, str]    # File extension -> stack name, e.g., {".py": "python", ".rs": "rust"}
    path_prefixes: dict[str, str] # Path prefix -> stack name, e.g., {"frontend/": "frontend"}
    priority: str                 # "extension" or "path" -- which takes precedence on conflict
```

### Configuration Layering Order

```
Layer 1: orchestrator/defaults.yaml     (shipped with code)
Layer 2: brownfield.yaml                (v1 compatibility, project root)
Layer 3: .orchestrator.yaml             (project-specific override)
Layer 4: Environment variables          (ORCHESTRATOR_ prefix)
```

Later layers override earlier layers via deep merge. Environment variables use `ORCHESTRATOR_` prefix with `__` as nested key separator (e.g., `ORCHESTRATOR_MODELS__DEFAULT=claude-opus-4-6`).

### defaults.yaml Schema

```yaml
models:
  default: claude-sonnet-4-6
  spec: claude-opus-4-6
  reviewer: claude-opus-4-6

local_test: true
test_command: "pytest"

ci_timeout: 1800
max_retries: 3
max_green_retries: 3
max_fix_retries: 2
stage_timeout: 3600
retry_base_delay: 2.0
retry_multiplier: 2.0

skip_stages: []

stack_config:
  extensions:
    ".py": python
    ".rs": rust
    ".ts": frontend
    ".tsx": frontend
    ".js": frontend
    ".jsx": frontend
    ".go": go
  path_prefixes:
    "frontend/": frontend
    "src-tauri/": rust
    "tests/": _use_extension    # Special: defer to extension-based classification
  priority: extension

ci_jobs:
  python:
    - "Python Tests"
    - "Coverage Check"
    - "Type Check"
    - "Lint"
  rust:
    - "Rust Tests"
    - "Rust Build Check"
  frontend:
    - "Frontend Tests"
    - "TypeScript Check"
  go:
    - "Go Tests"
    - "Go Lint"

source_dirs: null   # null = auto-detect (scan top-level dirs, exclude .git/.workflow/node_modules)
agent_base_path: ""  # Must be set in project config

wave_enabled: false
notifications_enabled: false
```

---

## SQLite Schema

### v1-Compatible Tables (DO NOT ALTER)

These tables exist in v1's workflow.db. v2 reads them as-is.

```sql
-- Tasks in the implement stage
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    description TEXT,
    file_path TEXT,
    parallel INTEGER DEFAULT 0,
    user_story TEXT,
    requirements TEXT,      -- JSON array of FR tags
    status TEXT DEFAULT 'pending',
    group_name TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- Review outcomes
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    task_id TEXT,
    review_type TEXT,       -- code | security | brooks
    passed INTEGER,
    findings TEXT,           -- JSON array
    raw_output TEXT,
    created_at TEXT
);

-- Audit trail
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    pipeline_id TEXT,
    stage TEXT,
    task_id TEXT,
    event_type TEXT,
    detail TEXT,             -- JSON blob
    created_at TEXT
);

-- Stage completion tracking
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

-- Sub-step status within stages
CREATE TABLE IF NOT EXISTS step_status (
    pipeline_id TEXT,
    stage TEXT,
    step TEXT,
    status TEXT,
    detail TEXT,
    updated_at TEXT,
    PRIMARY KEY (pipeline_id, stage, step)
);

-- LVL audit logs
CREATE TABLE IF NOT EXISTS lvl (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id TEXT,
    level TEXT,
    message TEXT,
    detail TEXT,
    created_at TEXT
);

-- Resume checkpoints
CREATE TABLE IF NOT EXISTS checkpoints (
    pipeline_id TEXT,
    stage TEXT,
    step TEXT,
    state_json TEXT,
    created_at TEXT,
    PRIMARY KEY (pipeline_id, stage, step)
);

-- Key-value settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
```

### v2 New Tables (Additive Only)

```sql
-- Pipeline execution metadata (new in v2)
CREATE TABLE IF NOT EXISTS pipelines (
    pipeline_id TEXT PRIMARY KEY,
    project_path TEXT NOT NULL,
    requirement_path TEXT,
    current_stage TEXT,
    status TEXT DEFAULT 'running',
    created_at TEXT,
    updated_at TEXT
);

-- Configuration cache (new in v2)
CREATE TABLE IF NOT EXISTS config_cache (
    pipeline_id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,    -- Serialized OrchestratorConfig
    created_at TEXT
);

-- Task group ordering (new in v2)
CREATE TABLE IF NOT EXISTS task_groups (
    group_name TEXT PRIMARY KEY,
    sort_order INTEGER NOT NULL,  -- 0=setup, 1-99=US groups, 100=polish
    task_count INTEGER DEFAULT 0
);
```

### Write Coordination

- `asyncio.Lock` instance created by `engine.py`
- Injected into: stages, tdd/runner, review/pipeline
- Store module (`store/`) is lock-free; callers acquire the lock before calling write operations
- Read operations do not require the lock (SQLite WAL mode supports concurrent reads)

### Upsert Strategy

Task records use `INSERT OR REPLACE` to ensure mutable fields (file_path, status, group_name) stay current (FR-036, Pitfall #9):

```sql
INSERT OR REPLACE INTO tasks (task_id, description, file_path, parallel, user_story, requirements, status, group_name, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

---

## CheckStrategy Interface

```python
class CheckStrategy(ABC):
    """Test verification strategy -- local or CI implementation."""

    @abstractmethod
    async def tests_must_fail(
        self, cwd: str, task_id: str, file_path: str
    ) -> tuple[bool, str]:
        """RED phase: verify tests fail (assertion failure, not compile error).
        Returns (success: bool, detail: str)."""

    @abstractmethod
    async def tests_must_pass(
        self, cwd: str, task_id: str, file_path: str
    ) -> tuple[bool, str]:
        """GREEN phase: verify all relevant tests pass.
        Returns (success: bool, detail: str)."""
```

### LocalCheckStrategy

- Runs `test_command` via subprocess
- RED: expects non-zero exit code (test failure)
- GREEN: expects zero exit code (all tests pass)
- No stack scoping needed (runs all tests locally)

### CICheckStrategy

- Commits, pushes, triggers CI via `gh` CLI
- Waits for CI completion within `ci_timeout`
- Uses `detect_stack(file_path)` to determine relevant CI jobs
- RED: relevant test jobs must fail; type-check job failures are acceptable for frontend tasks
- GREEN: all relevant jobs must pass; skipped/cancelled jobs are NOT treated as passing (FR-016)
- Error feedback: per-job structured, max 2000 chars per job (FR-017), `startswith` matching (FR-018)

---

## Entity Relationship Summary

```
Pipeline 1──* StageProgress
Pipeline 1──* Checkpoint
Pipeline 1──* Evidence
Pipeline 1──* Task (via implement stage)
Task *──* ReviewResult (via review pipeline)
OrchestratorConfig ──> StackConfig
OrchestratorConfig ──> ModelConfig
AgentInfo *──* StageName (participation)
AgentResult ──> AgentInfo (source)
```

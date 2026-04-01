"""Frozen dataclass DTOs and enums for the E+S Orchestrator v2 domain model.

FR-054: Enum types capture all pipeline lifecycle states.
FR-055: Frozen dataclass DTOs represent all orchestrator domain objects.

Design rules (from pitfalls.md and CLAUDE.md):
- All dataclasses are frozen (immutable).
- Mutable collections (list, dict) are NEVER stored as field types for
  sequence data — tuples are used instead.
- dict fields (metadata, data) are acceptable because they are opaque blobs
  persisted as JSON; callers must not mutate them post-construction.
- Every public field is type-annotated.
- No bare except; no module-level side-effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    """The four pipeline stages in execution order.

    Values are lowercase strings to simplify serialisation/deserialisation
    without a lookup table.
    """

    SPEC = "spec"
    PLAN = "plan"
    IMPLEMENT = "implement"
    ACCEPTANCE = "acceptance"


class TaskStatus(str, Enum):
    """Lifecycle status for a Task or Pipeline.

    Values are lowercase strings.
    """

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewVerdict(str, Enum):
    """Outcome of a review gate.

    Values are lowercase strings.
    """

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Core DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """Represents a single atomic work item produced by the plan stage.

    Fields
    ------
    id         : Unique task identifier (e.g. "T001").
    name       : Human-readable task description.
    stage      : Which pipeline stage owns this task.
    status     : Current lifecycle status.
    created_at : UTC datetime when the task was created.
    updated_at : UTC datetime of the last status change.
    metadata   : Arbitrary key-value pairs (file_path, parallel flag, etc.).
                 Stored as a dict; callers MUST NOT mutate after construction.
    """

    id: str
    name: str
    stage: Stage
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Pipeline:
    """Represents a full orchestrator run over one project.

    Fields
    ------
    id            : Unique pipeline identifier (e.g. "pipeline-001").
    tasks         : Ordered tuple of Task objects belonging to this pipeline.
    current_stage : The stage currently executing (or last executed).
    status        : Aggregate lifecycle status for the pipeline as a whole.
    created_at    : UTC datetime when the pipeline was created.
    """

    id: str
    current_stage: Stage
    status: TaskStatus
    created_at: datetime
    tasks: tuple[Task, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StageProgress:
    """Tracks retry attempts and timing for one stage execution.

    Fields
    ------
    stage        : The pipeline stage being tracked.
    status       : Current status of this stage execution.
    attempts     : Number of attempts made so far (1-indexed when started).
    max_attempts : Maximum allowed attempts before hard failure.
    started_at   : UTC datetime when the first attempt began.
    completed_at : UTC datetime when the stage completed (None if still running).
    """

    stage: Stage
    status: TaskStatus
    attempts: int
    max_attempts: int
    started_at: datetime
    completed_at: datetime | None = None


@dataclass(frozen=True)
class Checkpoint:
    """Persisted snapshot of pipeline state at the end of a stage.

    Fields
    ------
    pipeline_id : Foreign key linking to the Pipeline this checkpoint belongs to.
    stage       : The stage that completed and triggered this checkpoint.
    timestamp   : UTC datetime when the checkpoint was recorded.
    data        : Arbitrary JSON-serialisable dict (artifact paths, counts, etc.).
                  Callers MUST NOT mutate after construction.
    """

    pipeline_id: str
    stage: Stage
    timestamp: datetime
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewResult:
    """Outcome returned by a review agent after inspecting stage output.

    Fields
    ------
    verdict     : High-level review decision (PASS / FAIL / PARTIAL).
    score       : Normalised score in [0.0, 1.0].
    issues      : Tuple of issue description strings found during review.
    suggestions : Tuple of improvement suggestion strings.
    reviewer    : Identifier of the reviewer agent (e.g. "code-reviewer").
    """

    verdict: ReviewVerdict
    score: float
    reviewer: str
    issues: tuple[str, ...] = field(default_factory=tuple)
    suggestions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Evidence:
    """An artifact or observation captured during a stage execution.

    Fields
    ------
    type      : Category of evidence (e.g. "test_output", "lint_result").
    content   : The raw evidence text/output.
    source    : Tool or agent that produced the evidence (e.g. "pytest", "ruff").
    timestamp : UTC datetime when the evidence was collected.
    """

    type: str
    content: str
    source: str
    timestamp: datetime


@dataclass(frozen=True)
class AgentInfo:
    """Static descriptor for a registered agent.

    Fields
    ------
    name         : Unique agent identifier matching the agent directory name.
    role         : Functional role (e.g. "spec", "plan", "implement", "review").
    model        : The model identifier used by this agent.
    capabilities : Tuple of capability strings (e.g. ("write_spec", "review_spec")).
    """

    name: str
    role: str
    model: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgentResult:
    """Return value from a single agent invocation.

    Fields
    ------
    agent       : Descriptor of the agent that produced this result.
    output      : Primary text output from the agent.
    duration_ms : Wall-clock duration of the agent call in milliseconds.
    success     : True if the agent completed its task without error.
    evidence    : Tuple of Evidence objects collected during execution.
    """

    agent: AgentInfo
    output: str
    duration_ms: int
    success: bool
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OrchestratorConfig:
    """Merged, validated configuration for a single orchestrator run.

    Fields
    ------
    project_dir  : Absolute path to the project root directory.
    stages       : Ordered tuple of Stage values to execute (all four by default).
    max_retries  : Maximum auto-fix retries per stage before hard failure.
    parallel     : Whether parallel TDD task execution is enabled.
    skip_stages  : Tuple of Stage values to skip unconditionally (e.g. (Stage.SPEC,)).
    """

    project_dir: str
    stages: tuple[Stage, ...] = field(
        default_factory=lambda: (
            Stage.SPEC,
            Stage.PLAN,
            Stage.IMPLEMENT,
            Stage.ACCEPTANCE,
        )
    )
    max_retries: int = 3
    parallel: bool = False
    skip_stages: tuple[Stage, ...] = field(default_factory=tuple)

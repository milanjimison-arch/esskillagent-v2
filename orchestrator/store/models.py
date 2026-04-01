"""Frozen dataclass models for the persistent store (v1-compatible schema)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Task:
    """A unit of work in the TDD pipeline."""

    id: str                      # "T001"
    phase_num: int | None        # ordering number
    description: str
    file_path: str | None        # required for [P] tasks
    story_ref: str | None        # "US1"
    parallel: bool               # [P] marker
    depends_on: list[str]        # ["T001", "T002"]
    status: str                  # pending / red / green / failed
    started_at: str | None
    completed_at: str | None
    tdd_phase: str | None        # red / green
    review_notes: str | None


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a test strategy evaluation (in-memory, not persisted)."""

    success: bool
    detail: str
    jobs: list["JobResult"] | None = None  # CI mode per-job results


@dataclass(frozen=True)
class JobResult:
    """Per-job result from CI evaluation."""

    name: str                    # "Frontend Tests", "Rust Tests"
    conclusion: str              # "success" / "failure" / "skipped"
    relevant: bool               # whether related to current task stack
    log_excerpt: str | None      # extracted error log (within 2000-char budget)


@dataclass(frozen=True)
class StageProgress:
    """Persistent record of pipeline progress."""

    id: str                      # spec / plan / implement / acceptance
    status: str                  # pending / running / completed / failed
    started_at: str | None
    completed_at: str | None
    retries: int
    max_retries: int
    gate_verdict: str | None
    gate_feedback: str | None
    checkpoint_sha: str | None


@dataclass(frozen=True)
class StepStatus:
    """Individual step status within a stage."""

    id: int
    phase: str
    step: str
    status: str
    detail: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class Review:
    """An evaluation of stage output."""

    id: int
    phase: str
    stage: str
    reviewer: str                # "code" / "security" / "brooks"
    verdict: str                 # "pass" / "fail"
    critical: int
    high: int
    medium: int
    low: int
    issues: list[dict] | None    # JSON parsed
    superseded: bool
    created_at: str | None


@dataclass(frozen=True)
class Evidence:
    """Audit record linking a decision to its justification."""

    id: int
    phase: str
    stage: str
    verdict: str
    checks_passed: list[str] | None
    checks_failed: list[str] | None
    findings: str | None
    artifacts: list[str] | None
    output_hash: str | None
    prior_id: int | None
    batch_id: str | None
    created_at: str | None


@dataclass(frozen=True)
class LVLEntry:
    """Audit log entry."""

    id: int
    fact: str
    phase: str | None
    stage: str | None
    sub_stage: str | None
    result: str                  # pass / fail / warn / skip / info
    method: str | None
    detail: str | None
    file_hash: str | None
    git_sha: str | None
    agent_id: str | None
    attempt: int
    superseded: bool
    created_at: str | None


@dataclass(frozen=True)
class Checkpoint:
    """Pipeline checkpoint for resume support."""

    id: int
    name: str
    phase: str
    git_sha: str
    stage_snapshot: dict | None  # JSON parsed
    tasks_snapshot: dict | None  # JSON parsed
    created_at: str | None


@dataclass(frozen=True)
class Configuration:
    """Merged configuration from all layers (in-memory, optionally cached)."""

    # models
    model_default: str
    model_spec: str
    model_reviewer: str

    # testing
    test_command: str
    local_test: bool
    ci_timeout: int

    # retries
    max_retries: int
    max_green_retries: int
    max_fix_retries: int

    # timeouts
    stage_timeout: int

    # stage skipping
    skip_stages: list[str]

    # source tracking — underscore prefix marks as implementation detail
    _sources: dict[str, str] = field(default_factory=dict)

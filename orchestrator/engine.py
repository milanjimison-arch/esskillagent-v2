"""Pipeline engine — four-stage sequential flow controller.

FR-001: Executes spec → plan → implement → acceptance in order.
FR-003: Supports explicit stage skipping via skip_stages config.
FR-005: Delegates all stage logic to stages/ sub-package via execute_with_gate().
FR-059: Owns an asyncio.Lock and injects it into stages before execution.
SC-001: This file must remain under 300 lines.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

STAGE_NAMES: tuple[str, ...] = ("spec", "plan", "implement", "acceptance")

# Atomic stages — always re-run from start when resuming
ATOMIC_STAGES: tuple[str, ...] = ("spec", "plan")


class NoCheckpointError(Exception):
    """Raised when resume() is called but no checkpoint file/record exists."""


class TaskNotFoundError(Exception):
    """Raised when retry() is called with a task_id that does not exist."""


class TaskNotRetryableError(Exception):
    """Raised when retry() is called for a task that is not in BLOCKED status."""


@dataclass(frozen=True)
class PipelineResult:
    """Immutable result of a full pipeline run."""
    passed: bool = False
    stage_results: dict[str, Any] = field(default_factory=dict)
    skipped_stages: list[str] = field(default_factory=list)
    failed_stage: str | None = None
    paused: bool = False
    monitor_observations: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class RetryResult:
    """Immutable result of a single-task retry cycle (RED → GREEN → review)."""
    task_id: str = ""
    passed: bool = False
    phases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StatusResult:
    """Immutable snapshot of current pipeline status."""
    pipeline_id: str | None = None
    active: bool = False
    stage_completions: dict[str, bool] = field(default_factory=dict)
    task_counts: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)

@dataclass(frozen=True)
class PipelineEvent:
    """Immutable record of a single LVL event during a pipeline run."""
    event_type: str
    stage: str
    payload: dict[str, Any]
    prev_event_id: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


class PipelineEngine:
    """Sequential pipeline engine."""

    def __init__(self, stages: dict[str, Any], config: dict[str, Any]) -> None:
        self._stages = stages
        self._config = config
        self.lock = asyncio.Lock()  # FR-059
        self._events: list[PipelineEvent] = []  # INV-1/INV-2 event log
        self._red_passed_tasks: set[str] = set()  # INV-3 tracking
        self._tasks: dict[str, str] = dict(config.get("tasks", {}))
        self._store: Any = None  # injected store for status() queries
        self.monitor: Any = None  # FR-064: optional PipelineMonitor
        self._skipped_blocked_tasks: list[str] = []  # FR-065: skipped BLOCKED task IDs
        self._monitor_observations: list[dict[str, Any]] = []  # FR-064: collected observations
        self._paused: bool = False  # FR-065: pause state

    def _check_preconditions(self, stage_name: str) -> bool:
        """Validate preconditions for a stage. Override in subclasses."""
        return True

    def _freeze_stage_artifacts(self, stage_name: str, stage_result: Any) -> None:
        """Freeze artifacts after a stage completes. Override in subclasses."""
        pass

    def _emit_event(self, event_type: str, stage: str, payload: dict) -> None:
        """Emit LVL event, enforce INV-3 red_pass-before-green_start."""
        if event_type == "green_start":
            task_id = payload.get("task")
            if task_id not in self._red_passed_tasks:
                raise ValueError(f"INV-3: green_start for task {task_id!r} without prior red_pass")
        if event_type == "red_pass":
            task_id = payload.get("task")
            if task_id is not None:
                self._red_passed_tasks.add(task_id)
        prev_id = self._events[-1].event_id if self._events else None
        self._events.append(PipelineEvent(
            event_type=event_type, stage=stage,
            payload=payload, prev_event_id=prev_id,
        ))

    def _build_task_list(self) -> list[dict[str, Any]]:
        return [{"id": tid, "status": s} for tid, s in self._tasks.items()]

    def _invoke_monitor(self, stage: str = "") -> list[dict[str, Any]]:
        if not getattr(self, "monitor", None):
            return []
        obs = self.monitor.check(self._build_task_list(), stage=stage)
        self._monitor_observations.extend(obs)
        return obs

    def _evaluate_blocked_status(self) -> bool:
        """FR-065: Skip single BLOCKED task; pause when >50% BLOCKED."""
        blocked_ids = [tid for tid, s in self._tasks.items() if s == "BLOCKED"]
        total = len(self._tasks)
        if total == 0 or not blocked_ids:
            return False
        if len(blocked_ids) == 1:
            self._skipped_blocked_tasks.append(blocked_ids[0])
            return False
        if len(blocked_ids) / total > 0.5:
            self._invoke_monitor(stage="blocked_evaluation")
            self._paused = True
            return True
        return False

    async def _run_non_blocked_tasks(self) -> None:
        """FR-065: Execute TDD cycle for tasks that are not BLOCKED or skipped."""
        skip_set = set(self._skipped_blocked_tasks)
        for tid, status in list(self._tasks.items()):
            if tid not in skip_set and status != "BLOCKED":
                await self._run_single_task_tdd_cycle(tid)

    async def run(self) -> PipelineResult:
        """Execute all stages sequentially under process lock."""
        async with self.lock:
            if self._evaluate_blocked_status():
                return PipelineResult(passed=False, paused=True,
                    monitor_observations=self._monitor_observations or None)
            if self._skipped_blocked_tasks:
                await self._run_non_blocked_tasks()
            skip_stages = self._config.get("skip_stages", [])
            stage_results: dict[str, Any] = {}
            skipped_stages: list[str] = []
            failed_stage: str | None = None
            for name in STAGE_NAMES:
                if name in skip_stages:
                    skipped_stages.append(name)
                    continue
                if not self._check_preconditions(name):
                    failed_stage = name
                    break
                stage = self._stages[name]
                if hasattr(stage, "lock"):
                    stage.lock = self.lock
                result = await stage.execute_with_gate()
                if inspect.iscoroutine(result):
                    result = await result
                stage_results[name] = result
                if result.passed is False:
                    failed_stage = name
                    break
                self._emit_event("stage_complete", name, {"result": "passed"})
                self._freeze_stage_artifacts(name, result)
                self._invoke_monitor(stage=name)
            passed = failed_stage is None
            return PipelineResult(passed=passed, stage_results=stage_results,
                skipped_stages=skipped_stages, failed_stage=failed_stage,
                paused=self._paused,
                monitor_observations=self._monitor_observations or None)

    def _load_checkpoint(self) -> dict | None:
        """Load the last checkpoint. Returns None if no checkpoint exists."""
        return None

    async def resume(self) -> PipelineResult:
        """Resume from the last checkpoint."""
        async with self.lock:
            checkpoint = self._load_checkpoint()
            if checkpoint is None:
                raise NoCheckpointError("no checkpoint found")
            cp_stage = checkpoint["stage"]
            if cp_stage == "acceptance" and checkpoint.get("completed"):
                return PipelineResult(passed=True)
            cp_stage_idx = STAGE_NAMES.index(cp_stage)
            if cp_stage == "implement":
                last_idx = checkpoint.get("last_completed_task_index", -1)
                self._stages["implement"].resume_from_task = last_idx + 1
            skip_stages = self._config.get("skip_stages", [])
            stage_results: dict[str, Any] = {}
            skipped_stages: list[str] = []
            failed_stage: str | None = None
            for name in STAGE_NAMES:
                if name in skip_stages:
                    skipped_stages.append(name)
                    continue
                if name not in ATOMIC_STAGES and STAGE_NAMES.index(name) < cp_stage_idx:
                    continue
                if not self._check_preconditions(name):
                    failed_stage = name
                    break
                stage = self._stages[name]
                if hasattr(stage, "lock"):
                    stage.lock = self.lock
                result = await stage.execute_with_gate()
                if inspect.iscoroutine(result):
                    result = await result
                stage_results[name] = result
                if result.passed is False:
                    failed_stage = name
                    break
                self._emit_event("stage_complete", name, {"result": "passed"})
                self._freeze_stage_artifacts(name, result)
                self._invoke_monitor(stage=name)
            passed = failed_stage is None
            return PipelineResult(passed=passed, stage_results=stage_results,
                skipped_stages=skipped_stages, failed_stage=failed_stage,
                paused=self._paused,
                monitor_observations=self._monitor_observations or None)

    def _get_task_status(self, task_id: str) -> str | None:
        """Return the status string for task_id, or None if not found."""
        return self._tasks.get(task_id)

    def _set_task_status(self, task_id: str, status: str) -> None:
        self._tasks[task_id] = status

    async def _run_red_phase(self, task_id: str) -> Any:
        return SimpleNamespace(passed=True, phase="red")

    async def _run_green_phase(self, task_id: str) -> Any:
        return SimpleNamespace(passed=True, phase="green")

    async def _run_review_phase(self, task_id: str) -> Any:
        return SimpleNamespace(passed=True, phase="review")

    async def _run_single_task_tdd_cycle(self, task_id: str) -> Any:
        phases: list[str] = []
        red = await self._run_red_phase(task_id)
        phases.append("red")
        passed = red.passed
        if passed:
            green = await self._run_green_phase(task_id)
            phases.append("green")
            passed = green.passed
        review = await self._run_review_phase(task_id)
        phases.append("review")
        return SimpleNamespace(passed=passed, phases=tuple(phases))

    async def retry(self, task_id: str) -> RetryResult:
        """Re-execute a single TDD cycle (RED, GREEN, review) for a BLOCKED task."""
        async with self.lock:
            status = self._get_task_status(task_id)
            if status is None:
                raise TaskNotFoundError(f"task {task_id!r} not found")
            if status != "BLOCKED":
                raise TaskNotRetryableError(
                    f"task {task_id!r} has status {status} — only BLOCKED tasks can be retried"
                )
            cycle = await self._run_single_task_tdd_cycle(task_id)
            if cycle.passed:
                self._set_task_status(task_id, "DONE")
            return RetryResult(
                task_id=task_id,
                passed=cycle.passed,
                phases=getattr(cycle, "phases", ()),
            )

    async def status(self) -> StatusResult:
        """Aggregate pipeline state from store into an immutable snapshot."""
        if self._store is None:
            return StatusResult()
        pid: str | None = await self._store.get_active_pipeline_id()
        if pid is None:
            return StatusResult()
        done = set(await self._store.list_completed_stages(pid))
        counts: dict[str, int] = {}
        for t in await self._store.list_tasks(pid):
            s = t["status"]
            counts[s] = counts.get(s, 0) + 1
        return StatusResult(
            pipeline_id=pid, active=True,
            stage_completions={n: n in done for n in STAGE_NAMES},
            task_counts=counts,
            warnings=tuple(await self._store.list_warnings(pid)),
        )

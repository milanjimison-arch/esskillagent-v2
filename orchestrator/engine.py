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
from typing import Any

# ---------------------------------------------------------------------------
# STAGE_NAMES — canonical four-stage order
# ---------------------------------------------------------------------------

STAGE_NAMES: tuple[str, ...] = ("spec", "plan", "implement", "acceptance")


# ---------------------------------------------------------------------------
# PipelineResult — frozen dataclass (immutable DTO)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineResult:
    """Immutable result of a full pipeline run."""

    passed: bool = False
    stage_results: dict[str, Any] = field(default_factory=dict)
    skipped_stages: list[str] = field(default_factory=list)
    failed_stage: str | None = None


# ---------------------------------------------------------------------------
# PipelineEvent — immutable LVL event emitted during pipeline execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineEvent:
    """Immutable record of a single LVL event during a pipeline run."""

    event_type: str
    stage: str
    payload: dict[str, Any]
    prev_event_id: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


# ---------------------------------------------------------------------------
# PipelineEngine — stage flow control only
# ---------------------------------------------------------------------------


class PipelineEngine:
    """Sequential pipeline engine."""

    def __init__(self, stages: dict[str, Any], config: dict[str, Any]) -> None:
        self._stages = stages
        self._config = config
        self.lock = asyncio.Lock()  # FR-059
        self._events: list[PipelineEvent] = []  # INV-1/INV-2 event log
        self._red_passed_tasks: set[str] = set()  # INV-3 tracking

    def _check_preconditions(self, stage_name: str) -> bool:
        """Validate preconditions for a stage. Override in subclasses."""
        return True

    def _freeze_stage_artifacts(self, stage_name: str, stage_result: Any) -> None:
        """Freeze artifacts after a stage completes. Override in subclasses."""
        pass

    def _emit_event(self, event_type: str, stage: str, payload: dict) -> None:
        """Emit an LVL event, enforcing INV-3 red_pass-before-green_start."""
        # INV-3: green_start requires prior red_pass for the same task
        if event_type == "green_start":
            task_id = payload.get("task")
            if task_id not in self._red_passed_tasks:
                raise ValueError(
                    f"INV-3: green_start for task {task_id!r} without prior red_pass"
                )
        # Track red_pass for INV-3
        if event_type == "red_pass":
            task_id = payload.get("task")
            if task_id is not None:
                self._red_passed_tasks.add(task_id)

        # INV-2: prior-event linkage
        prev_id = self._events[-1].event_id if self._events else None
        evt = PipelineEvent(
            event_type=event_type, stage=stage,
            payload=payload, prev_event_id=prev_id,
        )
        self._events.append(evt)

    async def run(self) -> PipelineResult:
        """Execute the pipeline with process lock, preconditions, artifact freezing, and events."""
        async with self.lock:  # FR-059: process lock
            skip_stages: list[str] = self._config.get("skip_stages", [])
            stage_results: dict[str, Any] = {}
            skipped_stages: list[str] = []
            failed_stage: str | None = None

            for name in STAGE_NAMES:
                if name in skip_stages:
                    skipped_stages.append(name)
                    continue

                # INV-4: precondition validation
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

                # INV-1: emit stage_complete event for passing stages
                self._emit_event("stage_complete", name, {"result": "passed"})
                # Freeze artifacts for passing stages
                self._freeze_stage_artifacts(name, result)

            passed = failed_stage is None
            return PipelineResult(
                passed=passed, stage_results=stage_results,
                skipped_stages=skipped_stages, failed_stage=failed_stage,
            )

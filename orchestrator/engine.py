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
#
# Stub: fields are defined but engine.run() does not yet emit events,
# enforce INV-2 chain linkage, INV-3 ordering, or acquire the process lock.
# Tests targeting those behaviors will fail (RED) until implemented.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineEvent:
    """Immutable record of a single LVL event during a pipeline run.

    Fields
    ------
    event_type    : Category of the event (e.g. 'stage_complete', 'red_pass').
    stage         : Pipeline stage that emitted this event.
    payload       : Arbitrary JSON-serialisable dict with event details.
    prev_event_id : ID of the preceding event in the chain (None for first).
    event_id      : Unique identifier auto-generated on construction.
    """

    event_type: str
    stage: str
    payload: dict[str, Any]
    prev_event_id: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


# ---------------------------------------------------------------------------
# PipelineEngine — stage flow control only
# ---------------------------------------------------------------------------


class PipelineEngine:
    """Sequential pipeline engine.

    Owns an asyncio.Lock (FR-059) and injects it into each stage before
    calling execute_with_gate(). Contains no stage-specific logic (FR-005).
    """

    def __init__(self, stages: dict[str, Any], config: dict[str, Any]) -> None:
        self._stages = stages
        self._config = config
        self.lock = asyncio.Lock()  # FR-059: each instance owns its own lock

    async def run(self) -> PipelineResult:
        """Execute the pipeline, returning a PipelineResult.

        Stages listed in config['skip_stages'] are bypassed entirely.
        The pipeline stops immediately when a stage returns passed=False.
        The engine's lock is never held across the run; it is only injected
        into stages so they can coordinate their own SQLite writes.

        NOTE: This implementation does NOT yet:
          - acquire self.lock during execution (process lock, INV-FR-059)
          - call _check_preconditions() before each stage (INV-4)
          - call _freeze_stage_artifacts() after each stage
          - call _emit_event() for stage_complete events (INV-1)
          - enforce INV-2 prior-event linkage
          - enforce INV-3 red_pass-before-green_start ordering
        Tests covering those behaviors are RED until they are implemented.
        """
        skip_stages: list[str] = self._config.get("skip_stages", [])
        stage_results: dict[str, Any] = {}
        skipped_stages: list[str] = []
        failed_stage: str | None = None

        for name in STAGE_NAMES:
            if name in skip_stages:
                skipped_stages.append(name)
                continue

            stage = self._stages[name]

            if hasattr(stage, "lock"):
                stage.lock = self.lock

            result = await stage.execute_with_gate()
            # Guard: if side_effect returned a coroutine (common in mocks), await it
            if inspect.iscoroutine(result):
                result = await result
            stage_results[name] = result

            if result.passed is False:
                failed_stage = name
                break

        passed = failed_stage is None

        return PipelineResult(
            passed=passed,
            stage_results=stage_results,
            skipped_stages=skipped_stages,
            failed_stage=failed_stage,
        )

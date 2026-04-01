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

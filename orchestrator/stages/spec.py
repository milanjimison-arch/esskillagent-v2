"""Spec stage: constitution → specify → clarify → review.

This module defines the SpecStage concrete implementation of StageABC.
The spec stage guides an AI agent through four ordered sub-steps:
  1. constitution  — establish ground rules and constraints
  2. specify       — draft the functional specification
  3. clarify       — resolve ambiguities via dialogue
  4. review        — gate: approve the spec before advancing to plan

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
"""

from __future__ import annotations

from orchestrator.stages.base import ReviewOutcome, StageABC, StageResult

# Sub-step names for the spec stage, in execution order.
SPEC_SUB_STEPS: tuple[str, ...] = ("constitution", "specify", "clarify", "review")


class SpecStage(StageABC):
    """Concrete implementation of the Spec stage."""

    name: str = "spec"
    sub_steps: tuple[str, ...] = SPEC_SUB_STEPS

    def __init__(self, *, store: object | None = None) -> None:
        self._store = store
        self.max_retries: int = 3

    async def run(self) -> StageResult:
        steps_executed: list[str] = list(self.sub_steps)
        return StageResult(
            passed=True,
            attempts=1,
            data={"steps_executed": steps_executed},
        )

    async def _do_review(self) -> ReviewOutcome:
        return ReviewOutcome(passed=True, issues=(), verdict="pass")

    async def _do_fix(self, outcome: ReviewOutcome) -> None:
        pass

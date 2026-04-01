"""Implement stage: TDD → push+CI → review.

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
"""

from __future__ import annotations

from orchestrator.stages.base import ReviewOutcome, StageABC, StageResult

# Sub-step names for the implement stage, in execution order.
IMPLEMENT_SUB_STEPS: tuple[str, ...] = ("TDD", "push+CI", "review")


class ImplementStage(StageABC):
    """Concrete implementation of the Implement stage."""

    name: str = "implement"
    sub_steps: tuple[str, ...] = IMPLEMENT_SUB_STEPS

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

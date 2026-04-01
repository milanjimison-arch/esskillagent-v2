"""Stage ABC implementation.

FR-004: Stage ABC with review gate enforcement, checkpoint persistence, and
auto-fix retry loop.
FR-002: Checkpoint persistence after stage completion.
"""

from __future__ import annotations

import abc


class StageResult:
    """Return value from StageABC.execute_with_gate().

    Attributes:
        passed:   True if the stage completed and review gate passed.
        attempts: Number of review attempts consumed (1-indexed).
        data:     Arbitrary output data produced by the stage.
        error:    Error message if the stage failed, else None.
    """

    __slots__ = ("passed", "attempts", "data", "error")

    def __init__(
        self,
        passed: bool,
        attempts: int,
        data: dict,
        error: str | None = None,
    ) -> None:
        object.__setattr__(self, "passed", passed)
        object.__setattr__(self, "attempts", attempts)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "error", error)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("StageResult is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("StageResult is immutable")


class ReviewOutcome:
    """Result from a single review gate evaluation.

    Attributes:
        passed:   True if the review gate approved the stage output.
        issues:   Tuple of issue strings found during review.
        verdict:  String verdict label (e.g., "pass", "fail", "partial").
    """

    __slots__ = ("passed", "issues", "verdict")

    def __init__(
        self,
        passed: bool,
        issues: tuple[str, ...],
        verdict: str,
    ) -> None:
        object.__setattr__(self, "passed", passed)
        object.__setattr__(self, "issues", issues)
        object.__setattr__(self, "verdict", verdict)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ReviewOutcome is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("ReviewOutcome is immutable")


class StageABC(abc.ABC):
    """Abstract base class for all pipeline stages."""

    @abc.abstractmethod
    async def run(self) -> StageResult:
        """Execute the stage and return a StageResult."""
        raise NotImplementedError

    @abc.abstractmethod
    async def _do_review(self) -> ReviewOutcome:
        """Run the review gate for this stage."""
        raise NotImplementedError

    @abc.abstractmethod
    async def _do_fix(self, outcome: ReviewOutcome) -> None:
        """Apply auto-fix based on a failed review outcome."""
        raise NotImplementedError

    async def execute_with_gate(self) -> StageResult:
        """Template method: run stage body, enforce review gate, persist checkpoint."""
        run_result = await self.run()
        data = run_result.data
        attempts = 0

        for i in range(self.max_retries + 1):  # type: ignore[attr-defined]
            outcome = await self._do_review()
            attempts += 1

            if outcome.passed:
                await self._persist_checkpoint(data)
                return StageResult(passed=True, attempts=attempts, data=data, error=None)

            if i < self.max_retries:  # type: ignore[attr-defined]
                await self._do_fix(outcome)

        return StageResult(
            passed=False,
            attempts=attempts,
            data=data,
            error="review gate failed: max retries exhausted",
        )

    async def _persist_checkpoint(self, data: dict) -> None:
        """Persist a checkpoint snapshot for this stage to the store."""
        self._store.save_checkpoint(data)  # type: ignore[attr-defined]

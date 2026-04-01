"""Stage ABC stub.

FR-004: Stage ABC with review gate enforcement, checkpoint persistence, and
auto-fix retry loop.
FR-002: Checkpoint persistence after stage completion.

This is a minimal stub to prevent ImportError. All public classes and
methods raise NotImplementedError. Tests will fail (RED) until the full
implementation is provided.
"""

import abc


class StageABC(abc.ABC):
    """Abstract base class for all pipeline stages.

    Concrete stages (spec, plan, implement, acceptance) must implement
    run() and the review gate mechanism. The base class owns:
    - review gate enforcement (stage must pass before being marked complete)
    - checkpoint persistence (persisted after each successful completion)
    - auto-fix retry loop (retry up to max_retries on review failure)
    """

    @abc.abstractmethod
    async def run(self) -> "StageResult":
        """Execute the stage and return a StageResult.

        Raises:
            NotImplementedError: Until implemented by a concrete subclass.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def _do_review(self) -> "ReviewOutcome":
        """Run the review gate for this stage.

        Returns:
            ReviewOutcome indicating pass or fail with details.

        Raises:
            NotImplementedError: Until implemented by a concrete subclass.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def _do_fix(self, outcome: "ReviewOutcome") -> None:
        """Apply auto-fix based on a failed review outcome.

        Args:
            outcome: The failed ReviewOutcome from _do_review.

        Raises:
            NotImplementedError: Until implemented by a concrete subclass.
        """
        raise NotImplementedError

    async def execute_with_gate(self) -> "StageResult":
        """Template method: run stage body, enforce review gate, persist checkpoint.

        Implements the review gate loop:
        1. Call run() to produce stage output.
        2. Call _do_review() to evaluate the output.
        3. If review passes, persist checkpoint and return success.
        4. If review fails, call _do_fix() and retry up to max_retries.
        5. If retries exhausted, return failure without checkpoint.

        Returns:
            StageResult with status, attempts used, and checkpoint data.
        """
        raise NotImplementedError

    async def _persist_checkpoint(self, data: dict) -> None:
        """Persist a checkpoint snapshot for this stage to the store.

        Args:
            data: Arbitrary JSON-serialisable dict to persist.

        Raises:
            NotImplementedError: Until implemented by a concrete subclass.
        """
        raise NotImplementedError


class StageResult:
    """Return value from StageABC.execute_with_gate().

    Attributes:
        passed:   True if the stage completed and review gate passed.
        attempts: Number of review attempts consumed (1-indexed).
        data:     Arbitrary output data produced by the stage.
        error:    Error message if the stage failed, else None.
    """

    def __init__(
        self,
        passed: bool,
        attempts: int,
        data: dict,
        error: str | None = None,
    ) -> None:
        raise NotImplementedError


class ReviewOutcome:
    """Result from a single review gate evaluation.

    Attributes:
        passed:   True if the review gate approved the stage output.
        issues:   Tuple of issue strings found during review.
        verdict:  String verdict label (e.g., "pass", "fail", "partial").
    """

    def __init__(
        self,
        passed: bool,
        issues: tuple[str, ...],
        verdict: str,
    ) -> None:
        raise NotImplementedError

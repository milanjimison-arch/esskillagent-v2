"""Acceptance stage: verification → traceability → review.

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
FR-TRACE-001: Generate a traceability matrix mapping FRs → tasks → tests.
FR-TRACE-002: Flag any FR with no implementing task or test as "unimplemented".
FR-TRACE-003: Output the traceability matrix as a structured report (JSON or Markdown).
"""

from __future__ import annotations

from orchestrator.stages.base import ReviewOutcome, StageABC, StageResult

# Sub-step names for the acceptance stage, in execution order.
ACCEPTANCE_SUB_STEPS: tuple[str, ...] = ("verification", "traceability", "review")


class TraceabilityEntry:
    """Represents one FR's row in the traceability matrix.

    Minimal stub — stores attributes but does not implement any business logic.
    """

    def __init__(
        self,
        fr_id: str,
        tasks: list[str],
        tests: list[str],
    ) -> None:
        self.fr_id = fr_id
        self.tasks = tasks
        self.tests = tests


class TraceabilityMatrix:
    """Traceability matrix: maps FRs → tasks → tests and flags unimplemented FRs.

    Minimal stub — all methods return empty/incorrect values; implementation pending.
    """

    def __init__(self, entries: list[TraceabilityEntry]) -> None:  # noqa: ARG002
        # Stub: does not store entries — implementation pending.
        pass

    def unimplemented_frs(self) -> list[str]:
        """Return the list of FR IDs that have no implementing task or no test.

        Stub: always returns empty list.
        """
        return []

    def to_dict(self) -> dict:
        """Return the matrix as a plain dict suitable for JSON serialisation.

        Stub: always returns empty dict.
        """
        return {}

    def to_markdown(self) -> str:
        """Return the matrix rendered as a Markdown table.

        Stub: always returns empty string.
        """
        return ""


def generate_traceability_matrix(
    frs: list[str],
    task_map: dict[str, list[str]],
    test_map: dict[str, list[str]],
) -> "TraceabilityMatrix":
    """Generate a TraceabilityMatrix from spec FRs, task mapping, and test mapping.

    Parameters
    ----------
    frs:
        Ordered list of FR identifiers (e.g. ["FR-001", "FR-002"]).
    task_map:
        Mapping from FR ID to list of implementing task names.
    test_map:
        Mapping from FR ID to list of corresponding test file/function names.

    Returns
    -------
    TraceabilityMatrix
        The generated matrix.

    Stub: returns an empty TraceabilityMatrix regardless of inputs.
    """
    return TraceabilityMatrix(entries=[])


class AcceptanceStage(StageABC):
    """Concrete implementation of the Acceptance stage."""

    name: str = "acceptance"
    sub_steps: tuple[str, ...] = ACCEPTANCE_SUB_STEPS

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

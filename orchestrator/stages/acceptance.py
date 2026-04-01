"""Acceptance stage: verification → traceability → review.

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
FR-TRACE-001: Generate a traceability matrix mapping FRs → tasks → tests.
FR-TRACE-002: Flag any FR with no implementing task or test as "unimplemented".
FR-TRACE-003: Output the traceability matrix as a structured report (JSON or Markdown).
"""

from __future__ import annotations

import hashlib

from orchestrator.stages.base import ReviewOutcome, StageABC, StageResult


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# Sub-step names for the acceptance stage, in execution order.
ACCEPTANCE_SUB_STEPS: tuple[str, ...] = ("verification", "traceability", "review")

_MARKDOWN_HEADER = "| FR | Tasks | Tests | Status |\n|---|---|---|---|\n"


class TraceabilityEntry:
    """Represents one FR's row in the traceability matrix."""

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
    """Traceability matrix: maps FRs → tasks → tests and flags unimplemented FRs."""

    def __init__(self, entries: list[TraceabilityEntry]) -> None:
        self._entries: list[TraceabilityEntry] = entries

    def unimplemented_frs(self) -> list[str]:
        """Return the list of FR IDs that have no implementing task or no test.

        Each FR appears exactly once in the returned list.
        """
        return [
            entry.fr_id
            for entry in self._entries
            if not entry.tasks or not entry.tests
        ]

    def to_dict(self) -> dict:
        """Return the matrix as a plain dict suitable for JSON serialisation.

        Keys are FR IDs in insertion order. Each value contains 'tasks', 'tests',
        and 'status' ('implemented' or 'unimplemented').
        """
        result: dict = {}
        for entry in self._entries:
            is_implemented = bool(entry.tasks) and bool(entry.tests)
            result[entry.fr_id] = {
                "tasks": entry.tasks,
                "tests": entry.tests,
                "status": "implemented" if is_implemented else "unimplemented",
            }
        return result

    def to_markdown(self) -> str:
        """Return the matrix rendered as a Markdown table.

        Always includes the header row, even when there are no entries.
        """
        lines: list[str] = [_MARKDOWN_HEADER]
        for entry in self._entries:
            is_implemented = bool(entry.tasks) and bool(entry.tests)
            status = "implemented" if is_implemented else "unimplemented"
            tasks_str = ", ".join(entry.tasks) if entry.tasks else ""
            tests_str = ", ".join(entry.tests) if entry.tests else ""
            lines.append(f"| {entry.fr_id} | {tasks_str} | {tests_str} | {status} |\n")
        return "".join(lines)


def generate_traceability_matrix(
    frs: list[str],
    task_map: dict[str, list[str]],
    test_map: dict[str, list[str]],
) -> TraceabilityMatrix:
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
        The generated matrix. Extra keys in maps not in frs are ignored.
    """
    entries = [
        TraceabilityEntry(
            fr_id=fr,
            tasks=task_map.get(fr, []),
            tests=test_map.get(fr, []),
        )
        for fr in frs
    ]
    return TraceabilityMatrix(entries=entries)


class AcceptanceStage(StageABC):
    """Concrete implementation of the Acceptance stage."""

    name: str = "acceptance"
    sub_steps: tuple[str, ...] = ACCEPTANCE_SUB_STEPS

    def __init__(
        self,
        *,
        store: object | None = None,
        acceptor_agent=None,
        artifacts: dict[str, str] | None = None,
        required_artifacts: list[str] | None = None,
    ) -> None:
        self._store = store
        self.max_retries: int = 3
        self.acceptor_agent = acceptor_agent
        self.artifacts: dict[str, str] = artifacts if artifacts is not None else {}
        self.required_artifacts: list[str] = required_artifacts if required_artifacts is not None else []

    async def run(self) -> StageResult:
        steps_executed: list[str] = list(self.sub_steps)
        base_data: dict = {"stage_complete": "acceptance", "steps_executed": steps_executed}

        # Stub mode: no acceptor agent
        if self.acceptor_agent is None:
            empty_matrix = generate_traceability_matrix(frs=[], task_map={}, test_map={})
            return StageResult(
                passed=True,
                attempts=1,
                data={
                    **base_data,
                    "traceability": empty_matrix.to_dict(),
                    "unimplemented_frs": empty_matrix.unimplemented_frs(),
                    "traceability_report": empty_matrix.to_markdown(),
                },
            )

        # Validate required artifacts
        if self.required_artifacts:
            missing = [k for k in self.required_artifacts if k not in self.artifacts]
            if missing:
                return StageResult(
                    passed=False,
                    attempts=1,
                    data=dict(base_data),
                    error=f"Missing required artifacts: {', '.join(missing)}",
                )

        # Invoke acceptor agent
        try:
            agent_result = await self.acceptor_agent(self.artifacts)
        except Exception as exc:
            return StageResult(
                passed=False,
                attempts=1,
                data=dict(base_data),
                error=str(exc),
            )

        traceability: dict = agent_result.traceability or {}
        review_passed: bool = agent_result.review_passed
        review_issues = agent_result.review_issues

        # Compute unimplemented FRs from traceability dict
        unimplemented_frs = [
            fr_id
            for fr_id, entry in traceability.items()
            if not entry.get("tasks") or not entry.get("tests")
        ]

        # Freeze artifacts with SHA-256 hashes
        frozen_artifacts: dict[str, str] = {
            name: _sha256_hex(content)
            for name, content in self.artifacts.items()
        }
        # Also freeze the traceability report (as markdown from dict)
        trace_lines = [_MARKDOWN_HEADER]
        for fr_id, entry in traceability.items():
            tasks_str = ", ".join(entry.get("tasks", []))
            tests_str = ", ".join(entry.get("tests", []))
            status = entry.get("status", "unimplemented")
            trace_lines.append(f"| {fr_id} | {tasks_str} | {tests_str} | {status} |\n")
        traceability_report = "".join(trace_lines)
        frozen_artifacts["traceability_report"] = _sha256_hex(traceability_report)

        passed = bool(agent_result.success) and bool(review_passed)

        return StageResult(
            passed=passed,
            attempts=1,
            data={
                **base_data,
                "traceability": traceability,
                "unimplemented_frs": unimplemented_frs,
                "review_passed": review_passed,
                "review_issues": review_issues,
                "frozen_artifacts": frozen_artifacts,
                "traceability_report": traceability_report,
            },
        )

    async def _do_review(self) -> ReviewOutcome:
        return ReviewOutcome(passed=True, issues=(), verdict="pass")

    async def _do_fix(self, outcome: ReviewOutcome) -> None:
        pass

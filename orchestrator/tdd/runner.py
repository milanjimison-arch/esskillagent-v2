"""TDD task runner — manages serial RED-GREEN cycles with parallel batch execution.

SPEC-020: RED phase must complete before GREEN phase for each module.
SPEC-030: Parallel Phase A/B batch execution with git add scoping.
SPEC-040: Per-job error feedback and retry with error context.
"""

from __future__ import annotations


def git_add(files: list[str]) -> None:
    """Stub: stage the given files via git add."""
    pass


class JobStatus:
    """Status values for a TDD job."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class JobResult:
    """Result of a single TDD job execution."""

    def __init__(
        self,
        status: str = JobStatus.PENDING,
        attempts: int = 0,
        error: str | None = None,
        staged_files: list[str] | None = None,
    ) -> None:
        self.status = status
        self.attempts = attempts
        self.error = error
        self.staged_files = staged_files if staged_files is not None else []


class TDDJob:
    """Represents a single TDD job (RED or GREEN phase for one module)."""

    def __init__(
        self,
        module_name: str = "",
        phase: str = "red",
        scoped_files: list[str] | None = None,
    ) -> None:
        self.module_name = module_name
        self.phase = phase
        self.scoped_files = scoped_files if scoped_files is not None else []
        self.status = JobStatus.PENDING
        self.attempt_count = 0


class RunnerResult:
    """Result of a full TDDRunner.run() call."""

    def __init__(self, passed: bool = False, job_results: list | None = None) -> None:
        self.passed = passed
        self.job_results = job_results if job_results is not None else []


class TDDRunner:
    """Orchestrates TDD task execution with serial RED-GREEN and parallel batches."""

    def __init__(self, executor=None, config: dict | None = None) -> None:
        self.executor = executor
        self.config = config or {}

    async def run_job_with_retry(self, job: "TDDJob", context: dict | None = None) -> "JobResult":
        # Stub: returns a result that fails behavioral assertions
        return JobResult(status=JobStatus.PENDING, attempts=0, error=None, staged_files=[])

    async def run_module_tdd_cycle(self, red_job: "TDDJob", green_job: "TDDJob") -> None:
        # Stub: does nothing — behavioral tests will fail
        pass

    async def run_phase_a(self, jobs: list["TDDJob"]) -> list["JobResult"]:
        # Stub: returns empty list — behavioral tests will fail
        return []

    async def run_phase_b(self, jobs: list["TDDJob"]) -> list["JobResult"]:
        # Stub: returns empty list — behavioral tests will fail
        return []

    async def run(self, modules: list[dict]) -> "RunnerResult":
        # Stub: returns a result that fails behavioral assertions
        return RunnerResult(passed=False, job_results=[])

    def classify_error(self, phase: str, error_output: str, exit_code: int) -> str:
        # Stub: returns empty string — assertions expecting 'expected'/'unexpected' will fail
        return ""

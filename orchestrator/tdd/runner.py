"""TDD task runner — manages serial RED-GREEN cycles with parallel batch execution.

SPEC-020: RED phase must complete before GREEN phase for each module.
SPEC-030: Parallel Phase A/B batch execution with git add scoping.
SPEC-040: Per-job error feedback and retry with error context.
"""

from __future__ import annotations

import asyncio


def git_add(files: list[str]) -> None:
    """Stage the given files via git add."""
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

    async def run_job_with_retry(self, job: TDDJob, context: dict | None = None) -> JobResult:
        """Execute a job, retrying up to max_retries times on failure.

        max_retries=0 means 1 attempt total (no retries).
        max_retries=N means up to N+1 total attempts.
        """
        max_retries = self.config.get("max_retries", 0)
        last_result: JobResult = JobResult(status=JobStatus.FAILED, attempts=0, error=None)

        for attempt in range(max_retries + 1):
            job.status = JobStatus.RUNNING
            job.attempt_count += 1

            current_context = context if attempt == 0 else {"error": last_result.error}
            last_result = await self.executor(job, current_context)

            if last_result.status == JobStatus.PASSED:
                job.status = JobStatus.PASSED
                return last_result

        job.status = JobStatus.FAILED
        return last_result

    async def run_module_tdd_cycle(self, red_job: TDDJob, green_job: TDDJob) -> None:
        """Run RED then GREEN for a single module. GREEN is skipped if RED fails."""
        red_result = await self.run_job_with_retry(job=red_job)
        if red_result.status == JobStatus.PASSED:
            await self.run_job_with_retry(job=green_job)

    async def _run_single_job(self, job: TDDJob) -> JobResult:
        """Run a single job and call git_add if it passes with scoped files."""
        result = await self.run_job_with_retry(job=job)
        if result.status == JobStatus.PASSED and job.scoped_files:
            git_add(job.scoped_files)
        return result

    async def run_phase_a(self, jobs: list[TDDJob]) -> list[JobResult]:
        """Execute all RED jobs concurrently."""
        results = await asyncio.gather(*[self._run_single_job(job) for job in jobs])
        return list(results)

    async def run_phase_b(self, jobs: list[TDDJob]) -> list[JobResult]:
        """Execute all GREEN jobs concurrently."""
        results = await asyncio.gather(*[self._run_single_job(job) for job in jobs])
        return list(results)

    async def run(self, modules: list[dict]) -> RunnerResult:
        """Run Phase A (all RED) then Phase B (GREEN for modules where RED passed).

        Returns a RunnerResult with overall pass/fail and per-job outcomes.
        """
        if not modules:
            return RunnerResult(passed=True, job_results=[])

        red_jobs = [mod["red"] for mod in modules]
        red_results = await self.run_phase_a(jobs=red_jobs)

        green_jobs = [
            mod["green"]
            for mod, red_result in zip(modules, red_results)
            if red_result.status == JobStatus.PASSED
        ]
        green_results = await self.run_phase_b(jobs=green_jobs) if green_jobs else []

        all_results = red_results + green_results
        overall_passed = all(r.status == JobStatus.PASSED for r in all_results)

        return RunnerResult(passed=overall_passed, job_results=all_results)

    def classify_error(self, phase: str, error_output: str, exit_code: int) -> str:
        """Classify an error as 'expected' or 'unexpected'.

        In RED phase, an AssertionError with non-zero exit is 'expected'.
        Everything else (SyntaxError, ImportError, zero exit in RED, any error in GREEN)
        is 'unexpected'.
        """
        if phase == "red" and exit_code != 0:
            if "SyntaxError" in error_output or "ImportError" in error_output:
                return "unexpected"
            if "AssertionError" in error_output:
                return "expected"

        return "unexpected"

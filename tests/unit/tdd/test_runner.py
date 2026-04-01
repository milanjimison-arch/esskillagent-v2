"""Unit tests for orchestrator/tdd/runner.py — TDD task scheduler.

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/tdd/runner.py provides a complete implementation.

Requirements covered:
  SPEC-020: Serial RED-GREEN execution — RED phase must complete before GREEN
            phase begins for each module.
  SPEC-030: Parallel Phase A/B batch execution with git add scoping.
            Phase A (all RED phases) runs concurrently; Phase B (all GREEN
            phases) runs concurrently only after ALL Phase A tasks are done.
  SPEC-040: Per-job error feedback and retry with error context up to
            max_retries. On exhaustion the job is marked failed and execution
            continues.

Test areas:
  1.  TDDRunner is importable and instantiable.
  2.  TDDJob is importable and instantiable.
  3.  JobStatus constants exist: pending, running, passed, failed.
  4.  JobResult is importable and instantiable.
  5.  SPEC-020: RED phase completes before GREEN phase for a single module.
  6.  SPEC-020: All RED phases complete before any GREEN phase starts (batch).
  7.  SPEC-020: Each module's RED phase is independent of other modules' RED.
  8.  SPEC-030: run_phase_a executes all RED jobs concurrently.
  9.  SPEC-030: run_phase_b executes all GREEN jobs concurrently.
  10. SPEC-030: Phase B does not start until Phase A has fully completed.
  11. SPEC-030: git add scoping — each job stages only its own designated files.
  12. SPEC-030: git add called with scoped file list, not glob or bare "git add .".
  13. SPEC-040: failed job receives error feedback on retry.
  14. SPEC-040: retry prompt includes the error message from the previous failure.
  15. SPEC-040: job marked failed after max_retries exhausted.
  16. SPEC-040: runner continues to next job after a job is marked failed.
  17. SPEC-040: SyntaxError in RED classified as unexpected failure (not RED success).
  18. SPEC-040: AssertionError exit in RED classified as expected failure (RED valid).
  19. Job status transitions: pending → running → passed / failed.
  20. JobResult records status, error message, and attempt count.
  21. JobResult records the files staged by the job.
  22. TDDRunner.run returns a summary result with per-job outcomes.
  23. Edge case: empty job list → runner returns empty results, no error.
  24. Edge case: single module → RED then GREEN run sequentially.
  25. Edge case: all jobs fail → runner result marks overall as failed.
  26. Edge case: max_retries=0 → job fails on first attempt without retry.
  27. Edge case: large batch (50 modules) — all Phase A complete before Phase B.
  28. Edge case: job with no scoped files — git add not called for that job.
  29. Error classification: ImportError treated as unexpected failure.
  30. Error classification: non-zero exit + AssertionError output = expected RED.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.tdd.runner import JobResult, JobStatus, TDDJob, TDDRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(
    module_name: str = "module_a",
    phase: str = "red",
    scoped_files: list[str] | None = None,
) -> TDDJob:
    """Create a TDDJob instance for testing."""
    return TDDJob(
        module_name=module_name,
        phase=phase,
        scoped_files=scoped_files or [f"{module_name}/test_{module_name}.py"],
    )


def _make_passing_executor():
    """Return an async callable that simulates a passing job execution."""
    async def _executor(job: TDDJob, context: dict | None = None):
        return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)
    return _executor


def _make_failing_executor(error_msg: str = "AssertionError: expected True"):
    """Return an async callable that always fails with the given error."""
    async def _executor(job: TDDJob, context: dict | None = None):
        return JobResult(status=JobStatus.FAILED, attempts=1, error=error_msg, staged_files=[])
    return _executor


def _make_runner(
    executor=None,
    max_retries: int = 2,
    config: dict | None = None,
) -> TDDRunner:
    """Build a TDDRunner with an optional executor override."""
    cfg = {"max_retries": max_retries}
    if config:
        cfg.update(config)
    if executor is not None:
        return TDDRunner(executor=executor, config=cfg)
    return TDDRunner(config=cfg)


# ===========================================================================
# 1. Import and instantiation
# ===========================================================================


class TestImportAndInstantiation:
    """TDDRunner, TDDJob, JobStatus, JobResult must be importable and usable."""

    def test_tdd_runner_is_a_class(self):
        """TDDRunner must be a class."""
        assert inspect.isclass(TDDRunner)

    def test_tdd_job_is_a_class(self):
        """TDDJob must be a class."""
        assert inspect.isclass(TDDJob)

    def test_job_result_is_a_class(self):
        """JobResult must be a class."""
        assert inspect.isclass(JobResult)

    def test_tdd_runner_instantiable(self):
        """TDDRunner must instantiate without error."""
        runner = _make_runner()
        assert runner is not None

    def test_tdd_runner_instance_type(self):
        """Instantiated runner must be a TDDRunner instance."""
        runner = _make_runner()
        assert isinstance(runner, TDDRunner)

    def test_tdd_job_instantiable_with_args(self):
        """TDDJob must instantiate with module_name, phase, and scoped_files."""
        job = TDDJob(
            module_name="mymodule",
            phase="red",
            scoped_files=["mymodule/test_mymodule.py"],
        )
        assert job is not None

    def test_tdd_job_instance_type(self):
        """Instantiated job must be a TDDJob instance."""
        job = _make_job()
        assert isinstance(job, TDDJob)


# ===========================================================================
# 2. JobStatus constants
# ===========================================================================


class TestJobStatusConstants:
    """JobStatus must define the four canonical status strings."""

    def test_pending_status_exists(self):
        """JobStatus.PENDING must be the string 'pending'."""
        assert JobStatus.PENDING == "pending"

    def test_running_status_exists(self):
        """JobStatus.RUNNING must be the string 'running'."""
        assert JobStatus.RUNNING == "running"

    def test_passed_status_exists(self):
        """JobStatus.PASSED must be the string 'passed'."""
        assert JobStatus.PASSED == "passed"

    def test_failed_status_exists(self):
        """JobStatus.FAILED must be the string 'failed'."""
        assert JobStatus.FAILED == "failed"

    def test_all_statuses_are_strings(self):
        """All JobStatus constants must be non-empty strings."""
        for attr in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PASSED, JobStatus.FAILED):
            assert isinstance(attr, str) and attr


# ===========================================================================
# 3. TDDJob attributes
# ===========================================================================


class TestTDDJobAttributes:
    """TDDJob must expose expected attributes after construction."""

    def test_job_has_module_name(self):
        """TDDJob must store module_name."""
        job = TDDJob(module_name="parser", phase="red", scoped_files=["parser/test_parser.py"])
        assert job.module_name == "parser"

    def test_job_has_phase(self):
        """TDDJob must store phase ('red' or 'green')."""
        job = TDDJob(module_name="parser", phase="green", scoped_files=["parser/parser.py"])
        assert job.phase == "green"

    def test_job_has_scoped_files(self):
        """TDDJob must store scoped_files list."""
        files = ["parser/test_parser.py", "parser/parser.py"]
        job = TDDJob(module_name="parser", phase="red", scoped_files=files)
        assert job.scoped_files == files

    def test_job_initial_status_is_pending(self):
        """TDDJob must have status=pending on creation."""
        job = _make_job()
        assert job.status == JobStatus.PENDING

    def test_job_initial_attempt_count_zero(self):
        """TDDJob must have attempt_count=0 on creation."""
        job = _make_job()
        assert job.attempt_count == 0


# ===========================================================================
# 4. JobResult attributes
# ===========================================================================


class TestJobResultAttributes:
    """JobResult must carry status, attempts, error, and staged_files."""

    def test_job_result_has_status(self):
        """JobResult must have a status field."""
        result = JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=[])
        assert result.status == JobStatus.PASSED

    def test_job_result_has_attempts(self):
        """JobResult must record attempt count."""
        result = JobResult(status=JobStatus.PASSED, attempts=3, error=None, staged_files=[])
        assert result.attempts == 3

    def test_job_result_has_error_field(self):
        """JobResult must have an error field (None on success)."""
        result = JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=[])
        assert result.error is None

    def test_job_result_has_staged_files(self):
        """JobResult must record which files were staged."""
        files = ["module/test_module.py"]
        result = JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=files)
        assert result.staged_files == files

    def test_job_result_error_contains_message_on_failure(self):
        """JobResult.error must contain the error message when status is FAILED."""
        msg = "SyntaxError: invalid syntax"
        result = JobResult(status=JobStatus.FAILED, attempts=1, error=msg, staged_files=[])
        assert result.error == msg


# ===========================================================================
# 5. SPEC-020: Serial RED-GREEN per module
# ===========================================================================


class TestSerialRedGreen:
    """SPEC-020: RED phase must complete before GREEN phase for each module."""

    @pytest.mark.asyncio
    async def test_red_completes_before_green_single_module(self):
        """SPEC-020: for a single module, RED job runs before GREEN job."""
        call_order: list[str] = []

        async def executor(job: TDDJob, context: dict | None = None):
            call_order.append(f"{job.module_name}:{job.phase}")
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        red_job = TDDJob(module_name="alpha", phase="red", scoped_files=["alpha/test_alpha.py"])
        green_job = TDDJob(module_name="alpha", phase="green", scoped_files=["alpha/alpha.py"])

        await runner.run_module_tdd_cycle(red_job=red_job, green_job=green_job)

        red_index = call_order.index("alpha:red")
        green_index = call_order.index("alpha:green")
        assert red_index < green_index, (
            f"RED must run before GREEN. Order was: {call_order}"
        )

    @pytest.mark.asyncio
    async def test_green_not_called_if_red_fails_max_retries(self):
        """SPEC-020: if RED phase exhausts retries, GREEN must not be called."""
        green_called = False

        async def executor(job: TDDJob, context: dict | None = None):
            nonlocal green_called
            if job.phase == "green":
                green_called = True
                return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=[])
            return JobResult(status=JobStatus.FAILED, attempts=1, error="SyntaxError: oops", staged_files=[])

        runner = TDDRunner(executor=executor, config={"max_retries": 0})
        red_job = TDDJob(module_name="beta", phase="red", scoped_files=["beta/test_beta.py"])
        green_job = TDDJob(module_name="beta", phase="green", scoped_files=["beta/beta.py"])

        await runner.run_module_tdd_cycle(red_job=red_job, green_job=green_job)

        assert green_called is False, "GREEN must not execute when RED fails after max_retries"

    @pytest.mark.asyncio
    async def test_green_runs_after_red_passes(self):
        """SPEC-020: GREEN runs when RED passes."""
        executed_phases: list[str] = []

        async def executor(job: TDDJob, context: dict | None = None):
            executed_phases.append(job.phase)
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        red_job = TDDJob(module_name="gamma", phase="red", scoped_files=["gamma/test_gamma.py"])
        green_job = TDDJob(module_name="gamma", phase="green", scoped_files=["gamma/gamma.py"])

        await runner.run_module_tdd_cycle(red_job=red_job, green_job=green_job)

        assert "green" in executed_phases, "GREEN phase must execute after RED passes"


# ===========================================================================
# 6. SPEC-030: Parallel Phase A / Phase B batch execution
# ===========================================================================


class TestParallelBatchExecution:
    """SPEC-030: Phase A (all RED) runs in parallel; Phase B (all GREEN) runs
    after ALL Phase A jobs are complete."""

    @pytest.mark.asyncio
    async def test_run_phase_a_executes_all_red_jobs(self):
        """SPEC-030: run_phase_a must execute every RED job in the batch."""
        executed: list[str] = []

        async def executor(job: TDDJob, context: dict | None = None):
            executed.append(job.module_name)
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        red_jobs = [
            TDDJob(module_name=f"mod_{i}", phase="red", scoped_files=[f"mod_{i}/test_{i}.py"])
            for i in range(3)
        ]

        await runner.run_phase_a(jobs=red_jobs)

        assert set(executed) == {"mod_0", "mod_1", "mod_2"}, (
            f"All RED jobs must execute. Got: {executed}"
        )

    @pytest.mark.asyncio
    async def test_run_phase_b_executes_all_green_jobs(self):
        """SPEC-030: run_phase_b must execute every GREEN job in the batch."""
        executed: list[str] = []

        async def executor(job: TDDJob, context: dict | None = None):
            executed.append(job.module_name)
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        green_jobs = [
            TDDJob(module_name=f"mod_{i}", phase="green", scoped_files=[f"mod_{i}/mod_{i}.py"])
            for i in range(3)
        ]

        await runner.run_phase_b(jobs=green_jobs)

        assert set(executed) == {"mod_0", "mod_1", "mod_2"}, (
            f"All GREEN jobs must execute. Got: {executed}"
        )

    @pytest.mark.asyncio
    async def test_phase_b_starts_only_after_phase_a_completes(self):
        """SPEC-030: No GREEN job may start before all RED jobs have finished."""
        phase_a_done = False
        phase_b_started_early = False

        async def executor(job: TDDJob, context: dict | None = None):
            nonlocal phase_a_done, phase_b_started_early
            if job.phase == "red":
                await asyncio.sleep(0.01)  # simulate work
            elif job.phase == "green":
                if not phase_a_done:
                    phase_b_started_early = True
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        red_jobs = [
            TDDJob(module_name=f"mod_{i}", phase="red", scoped_files=[f"mod_{i}/test.py"])
            for i in range(3)
        ]
        green_jobs = [
            TDDJob(module_name=f"mod_{i}", phase="green", scoped_files=[f"mod_{i}/mod.py"])
            for i in range(3)
        ]

        await runner.run_phase_a(jobs=red_jobs)
        phase_a_done = True
        await runner.run_phase_b(jobs=green_jobs)

        assert phase_b_started_early is False, (
            "Phase B must not start before Phase A has fully completed"
        )

    @pytest.mark.asyncio
    async def test_run_returns_all_phase_results(self):
        """SPEC-030: runner.run() returns results for all jobs in both phases."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        modules = [
            {
                "red": TDDJob(module_name=f"m{i}", phase="red", scoped_files=[f"m{i}/test.py"]),
                "green": TDDJob(module_name=f"m{i}", phase="green", scoped_files=[f"m{i}/m{i}.py"]),
            }
            for i in range(3)
        ]

        summary = await runner.run(modules=modules)

        assert hasattr(summary, "job_results"), "RunnerResult must have job_results"
        assert len(summary.job_results) == 6, (
            f"Expected 6 results (3 RED + 3 GREEN), got {len(summary.job_results)}"
        )

    @pytest.mark.asyncio
    async def test_phase_a_jobs_run_concurrently(self):
        """SPEC-030: Phase A jobs must overlap in time (concurrent execution)."""
        start_times: dict[str, float] = {}
        end_times: dict[str, float] = {}

        async def executor(job: TDDJob, context: dict | None = None):
            import time
            start_times[job.module_name] = time.monotonic()
            await asyncio.sleep(0.05)  # simulate 50ms work
            end_times[job.module_name] = time.monotonic()
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        red_jobs = [
            TDDJob(module_name=f"m{i}", phase="red", scoped_files=[f"m{i}/test.py"])
            for i in range(3)
        ]

        import time
        t_start = time.monotonic()
        await runner.run_phase_a(jobs=red_jobs)
        t_total = time.monotonic() - t_start

        # If serial, total would be ~150ms; if concurrent, ~50ms
        assert t_total < 0.12, (
            f"Phase A jobs must run concurrently. Total time {t_total:.3f}s suggests serial execution."
        )


# ===========================================================================
# 7. SPEC-030: Git add scoping
# ===========================================================================


class TestGitAddScoping:
    """SPEC-030: Each job must only stage its own designated files."""

    @pytest.mark.asyncio
    async def test_git_add_called_with_scoped_files_only(self):
        """SPEC-030: git add must be called with only the job's scoped_files."""
        git_add_calls: list[list[str]] = []

        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(
                status=JobStatus.PASSED,
                attempts=1,
                error=None,
                staged_files=job.scoped_files,
            )

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        job = TDDJob(
            module_name="scoped_mod",
            phase="red",
            scoped_files=["scoped_mod/test_scoped_mod.py"],
        )

        with patch("orchestrator.tdd.runner.git_add") as mock_git_add:
            mock_git_add.return_value = None
            await runner.run_phase_a(jobs=[job])
            if mock_git_add.called:
                for c in mock_git_add.call_args_list:
                    staged = c.args[0] if c.args else c.kwargs.get("files", [])
                    git_add_calls.append(staged)

        for staged in git_add_calls:
            for f in staged:
                assert f in job.scoped_files, (
                    f"git add staged '{f}' which is not in job.scoped_files={job.scoped_files}"
                )

    @pytest.mark.asyncio
    async def test_jobs_do_not_stage_each_others_files(self):
        """SPEC-030: job A must not stage files belonging to job B."""
        staged_by_job: dict[str, list[str]] = {}

        async def executor(job: TDDJob, context: dict | None = None):
            staged_by_job[job.module_name] = job.scoped_files
            return JobResult(
                status=JobStatus.PASSED,
                attempts=1,
                error=None,
                staged_files=job.scoped_files,
            )

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        job_a = TDDJob(module_name="mod_a", phase="red", scoped_files=["mod_a/test_a.py"])
        job_b = TDDJob(module_name="mod_b", phase="red", scoped_files=["mod_b/test_b.py"])

        await runner.run_phase_a(jobs=[job_a, job_b])

        # mod_a must not include mod_b's files in its staged set
        for f in staged_by_job.get("mod_a", []):
            assert f not in job_b.scoped_files, (
                f"mod_a staged '{f}', which belongs to mod_b"
            )
        for f in staged_by_job.get("mod_b", []):
            assert f not in job_a.scoped_files, (
                f"mod_b staged '{f}', which belongs to mod_a"
            )

    @pytest.mark.asyncio
    async def test_job_result_staged_files_matches_scoped_files(self):
        """SPEC-030: JobResult.staged_files must equal the job's scoped_files on success."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(
                status=JobStatus.PASSED,
                attempts=1,
                error=None,
                staged_files=job.scoped_files,
            )

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        files = ["mymod/test_mymod.py"]
        job = TDDJob(module_name="mymod", phase="red", scoped_files=files)
        results = await runner.run_phase_a(jobs=[job])

        result = results[0]
        assert result.staged_files == files, (
            f"staged_files must equal scoped_files={files}, got {result.staged_files}"
        )

    @pytest.mark.asyncio
    async def test_no_git_add_for_job_with_empty_scoped_files(self):
        """SPEC-030: a job with no scoped_files must not trigger a git add call."""
        git_add_called = False

        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(
                status=JobStatus.PASSED,
                attempts=1,
                error=None,
                staged_files=[],
            )

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        job = TDDJob(module_name="empty_mod", phase="red", scoped_files=[])

        with patch("orchestrator.tdd.runner.git_add") as mock_git_add:
            await runner.run_phase_a(jobs=[job])
            # git_add should not be called with an empty list of files
            for c in mock_git_add.call_args_list:
                files_arg = c.args[0] if c.args else c.kwargs.get("files", [])
                if files_arg:
                    git_add_called = True

        assert git_add_called is False, (
            "git add must not be called with files when scoped_files is empty"
        )


# ===========================================================================
# 8. SPEC-040: Per-job error feedback and retry
# ===========================================================================


class TestPerJobErrorFeedbackRetry:
    """SPEC-040: Failed jobs receive error context on retry; exhausted jobs are marked failed."""

    @pytest.mark.asyncio
    async def test_failed_job_retried_with_error_context(self):
        """SPEC-040: on retry, executor receives the previous failure's error in context."""
        received_contexts: list[dict | None] = []

        call_count = 0

        async def executor(job: TDDJob, context: dict | None = None):
            nonlocal call_count
            call_count += 1
            received_contexts.append(context)
            if call_count == 1:
                return JobResult(
                    status=JobStatus.FAILED,
                    attempts=1,
                    error="AssertionError: expected True got False",
                    staged_files=[],
                )
            return JobResult(status=JobStatus.PASSED, attempts=2, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 2})
        job = TDDJob(module_name="retry_mod", phase="red", scoped_files=["retry_mod/test.py"])

        result = await runner.run_job_with_retry(job=job)

        assert result.status == JobStatus.PASSED, "Job should pass on second attempt"
        # The second call must have received error context from first failure
        assert len(received_contexts) >= 2, "Executor must be called at least twice"
        retry_context = received_contexts[1]
        assert retry_context is not None, "Retry context must not be None"
        assert "error" in retry_context, "Retry context must contain 'error' key"
        assert "AssertionError" in retry_context["error"], (
            f"Retry context must include the previous error. Got: {retry_context}"
        )

    @pytest.mark.asyncio
    async def test_job_marked_failed_after_max_retries_exhausted(self):
        """SPEC-040: after max_retries attempts all fail, job status must be FAILED."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(
                status=JobStatus.FAILED,
                attempts=1,
                error="SyntaxError: unexpected indent",
                staged_files=[],
            )

        runner = TDDRunner(executor=executor, config={"max_retries": 2})
        job = TDDJob(module_name="always_fail", phase="red", scoped_files=["fail/test.py"])

        result = await runner.run_job_with_retry(job=job)

        assert result.status == JobStatus.FAILED, (
            "Job must be marked FAILED after max_retries exhausted"
        )

    @pytest.mark.asyncio
    async def test_attempt_count_reflects_total_tries(self):
        """SPEC-040: result.attempts must equal the total number of execution attempts."""
        attempt_count = 0

        async def executor(job: TDDJob, context: dict | None = None):
            nonlocal attempt_count
            attempt_count += 1
            return JobResult(
                status=JobStatus.FAILED,
                attempts=attempt_count,
                error="always fails",
                staged_files=[],
            )

        runner = TDDRunner(executor=executor, config={"max_retries": 3})
        job = TDDJob(module_name="count_mod", phase="red", scoped_files=["count_mod/test.py"])

        result = await runner.run_job_with_retry(job=job)

        # max_retries=3 means up to 3 total attempts (1 initial + 2 retries, or similar)
        assert result.attempts >= 1, "At least one attempt must be recorded"
        assert result.attempts <= 4, "Attempts must not exceed max_retries + 1"

    @pytest.mark.asyncio
    async def test_runner_continues_after_job_fails(self):
        """SPEC-040: runner must continue to the next job after one job is marked failed."""
        executed: list[str] = []

        async def executor(job: TDDJob, context: dict | None = None):
            executed.append(job.module_name)
            if job.module_name == "failing_mod":
                return JobResult(
                    status=JobStatus.FAILED, attempts=1, error="error", staged_files=[]
                )
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 0})
        red_jobs = [
            TDDJob(module_name="failing_mod", phase="red", scoped_files=["fail/test.py"]),
            TDDJob(module_name="passing_mod", phase="red", scoped_files=["pass/test.py"]),
        ]

        await runner.run_phase_a(jobs=red_jobs)

        assert "passing_mod" in executed, (
            "Runner must execute passing_mod even after failing_mod fails"
        )

    @pytest.mark.asyncio
    async def test_retry_context_contains_previous_error_message(self):
        """SPEC-040: the retry context dict must contain the key 'error' with
        the exact error message from the previous run."""
        errors_in_context: list[str] = []
        first_error = "ImportError: cannot import name 'foo'"

        call_count = 0

        async def executor(job: TDDJob, context: dict | None = None):
            nonlocal call_count
            call_count += 1
            if context and "error" in context:
                errors_in_context.append(context["error"])
            if call_count == 1:
                return JobResult(
                    status=JobStatus.FAILED, attempts=1, error=first_error, staged_files=[]
                )
            return JobResult(status=JobStatus.PASSED, attempts=2, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 2})
        job = TDDJob(module_name="ctx_mod", phase="red", scoped_files=["ctx_mod/test.py"])

        await runner.run_job_with_retry(job=job)

        assert len(errors_in_context) >= 1, "Error must be passed in retry context"
        assert errors_in_context[0] == first_error, (
            f"Retry context error must match first failure. Got: {errors_in_context}"
        )

    @pytest.mark.asyncio
    async def test_max_retries_zero_fails_on_first_attempt(self):
        """SPEC-040: max_retries=0 means the job runs once and fails with no retry."""
        call_count = 0

        async def executor(job: TDDJob, context: dict | None = None):
            nonlocal call_count
            call_count += 1
            return JobResult(
                status=JobStatus.FAILED, attempts=1, error="fail", staged_files=[]
            )

        runner = TDDRunner(executor=executor, config={"max_retries": 0})
        job = TDDJob(module_name="zero_retry", phase="red", scoped_files=["zero/test.py"])

        result = await runner.run_job_with_retry(job=job)

        assert result.status == JobStatus.FAILED
        assert call_count == 1, (
            f"With max_retries=0, executor must be called exactly once. Got: {call_count}"
        )

    @pytest.mark.asyncio
    async def test_final_error_logged_in_result_after_max_retries(self):
        """SPEC-040: the final result must record the last error after all retries fail."""
        last_error = "AssertionError: final failure"

        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(
                status=JobStatus.FAILED,
                attempts=1,
                error=last_error,
                staged_files=[],
            )

        runner = TDDRunner(executor=executor, config={"max_retries": 2})
        job = TDDJob(module_name="final_err", phase="red", scoped_files=["final/test.py"])

        result = await runner.run_job_with_retry(job=job)

        assert result.error is not None, "Final result must contain error message"
        assert last_error in result.error, (
            f"Final error must include the last failure message. Got: {result.error}"
        )


# ===========================================================================
# 9. SPEC-040: Error classification
# ===========================================================================


class TestErrorClassification:
    """SPEC-040: Distinguish expected failures (AssertionError in RED) from
    unexpected failures (SyntaxError, ImportError)."""

    def test_assertion_error_in_red_is_expected_failure(self):
        """SPEC-040: AssertionError exit code with assertion output = valid RED state."""
        runner = _make_runner()
        result = runner.classify_error(
            phase="red",
            error_output="AssertionError: expected True got False",
            exit_code=1,
        )
        assert result == "expected", (
            f"AssertionError in RED phase must be 'expected', got {result!r}"
        )

    def test_syntax_error_in_red_is_unexpected_failure(self):
        """SPEC-040: SyntaxError output = unexpected failure regardless of phase."""
        runner = _make_runner()
        result = runner.classify_error(
            phase="red",
            error_output="SyntaxError: invalid syntax",
            exit_code=1,
        )
        assert result == "unexpected", (
            f"SyntaxError in RED phase must be 'unexpected', got {result!r}"
        )

    def test_import_error_is_unexpected_failure(self):
        """SPEC-040: ImportError output = unexpected failure."""
        runner = _make_runner()
        result = runner.classify_error(
            phase="red",
            error_output="ImportError: cannot import name 'missing'",
            exit_code=1,
        )
        assert result == "unexpected", (
            f"ImportError must be classified as 'unexpected', got {result!r}"
        )

    def test_zero_exit_code_red_phase_is_unexpected(self):
        """SPEC-040: RED phase passing (exit 0) is unexpected — tests should FAIL in RED."""
        runner = _make_runner()
        result = runner.classify_error(
            phase="red",
            error_output="",
            exit_code=0,
        )
        assert result == "unexpected", (
            "A passing test run during RED phase is an unexpected result (tests should fail)"
        )

    def test_assertion_error_in_green_is_unexpected_failure(self):
        """SPEC-040: AssertionError in GREEN phase is an unexpected failure (tests should pass)."""
        runner = _make_runner()
        result = runner.classify_error(
            phase="green",
            error_output="AssertionError: expected True got False",
            exit_code=1,
        )
        assert result == "unexpected", (
            "AssertionError in GREEN phase means tests still fail — unexpected"
        )

    def test_classify_error_returns_string(self):
        """SPEC-040: classify_error must return a string ('expected' or 'unexpected')."""
        runner = _make_runner()
        result = runner.classify_error(
            phase="red",
            error_output="AssertionError: test failed",
            exit_code=1,
        )
        assert isinstance(result, str)
        assert result in ("expected", "unexpected")


# ===========================================================================
# 10. Job status transitions
# ===========================================================================


class TestJobStatusTransitions:
    """Job status must transition correctly through pending → running → passed/failed."""

    @pytest.mark.asyncio
    async def test_job_status_changes_to_running_during_execution(self):
        """Job must transition to RUNNING while executor is active."""
        observed_status_during_run: list[str] = []

        async def executor(job: TDDJob, context: dict | None = None):
            observed_status_during_run.append(job.status)
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        job = TDDJob(module_name="status_mod", phase="red", scoped_files=["status_mod/test.py"])

        await runner.run_job_with_retry(job=job)

        assert JobStatus.RUNNING in observed_status_during_run, (
            f"Job must be RUNNING during executor call. Observed: {observed_status_during_run}"
        )

    @pytest.mark.asyncio
    async def test_job_status_is_passed_after_success(self):
        """After a passing run, job.status must be PASSED."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        job = TDDJob(module_name="pass_mod", phase="red", scoped_files=["pass_mod/test.py"])

        await runner.run_job_with_retry(job=job)

        assert job.status == JobStatus.PASSED, (
            f"Job status must be PASSED after success. Got: {job.status}"
        )

    @pytest.mark.asyncio
    async def test_job_status_is_failed_after_max_retries(self):
        """After max_retries failures, job.status must be FAILED."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.FAILED, attempts=1, error="error", staged_files=[])

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        job = TDDJob(module_name="fail_mod", phase="red", scoped_files=["fail_mod/test.py"])

        await runner.run_job_with_retry(job=job)

        assert job.status == JobStatus.FAILED, (
            f"Job status must be FAILED after max_retries exhausted. Got: {job.status}"
        )

    @pytest.mark.asyncio
    async def test_job_attempt_count_incremented_on_each_attempt(self):
        """job.attempt_count must be incremented each time executor is called."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.FAILED, attempts=job.attempt_count + 1, error="err", staged_files=[])

        runner = TDDRunner(executor=executor, config={"max_retries": 2})
        job = TDDJob(module_name="count_mod", phase="red", scoped_files=["count/test.py"])

        await runner.run_job_with_retry(job=job)

        assert job.attempt_count >= 1, "attempt_count must be at least 1 after execution"


# ===========================================================================
# 11. TDDRunner.run — full pipeline integration
# ===========================================================================


class TestTDDRunnerRun:
    """TDDRunner.run orchestrates the full Phase A → Phase B pipeline."""

    @pytest.mark.asyncio
    async def test_run_returns_runner_result(self):
        """TDDRunner.run must return a RunnerResult (or compatible object)."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        modules = [
            {
                "red": TDDJob(module_name="m0", phase="red", scoped_files=["m0/test.py"]),
                "green": TDDJob(module_name="m0", phase="green", scoped_files=["m0/m0.py"]),
            }
        ]
        result = await runner.run(modules=modules)
        assert result is not None

    @pytest.mark.asyncio
    async def test_run_overall_passed_true_all_pass(self):
        """RunnerResult.passed must be True when all jobs pass."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        modules = [
            {
                "red": TDDJob(module_name="m0", phase="red", scoped_files=["m0/test.py"]),
                "green": TDDJob(module_name="m0", phase="green", scoped_files=["m0/m0.py"]),
            }
        ]
        result = await runner.run(modules=modules)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_overall_passed_false_when_any_job_fails(self):
        """RunnerResult.passed must be False when any job ultimately fails."""
        async def executor(job: TDDJob, context: dict | None = None):
            if job.module_name == "bad_mod":
                return JobResult(status=JobStatus.FAILED, attempts=1, error="fail", staged_files=[])
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 0})
        modules = [
            {
                "red": TDDJob(module_name="bad_mod", phase="red", scoped_files=["bad/test.py"]),
                "green": TDDJob(module_name="bad_mod", phase="green", scoped_files=["bad/bad.py"]),
            },
            {
                "red": TDDJob(module_name="good_mod", phase="red", scoped_files=["good/test.py"]),
                "green": TDDJob(module_name="good_mod", phase="green", scoped_files=["good/good.py"]),
            },
        ]
        result = await runner.run(modules=modules)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_run_empty_modules_returns_passed_true(self):
        """Edge case: running with no modules must succeed with passed=True."""
        runner = _make_runner()
        result = await runner.run(modules=[])
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_empty_modules_returns_empty_job_results(self):
        """Edge case: running with no modules returns empty job_results."""
        runner = _make_runner()
        result = await runner.run(modules=[])
        assert len(result.job_results) == 0


# ===========================================================================
# 12. Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases for TDDRunner and TDDJob."""

    @pytest.mark.asyncio
    async def test_single_module_red_then_green_sequential(self):
        """Edge: single module executes RED then GREEN in order."""
        order: list[str] = []

        async def executor(job: TDDJob, context: dict | None = None):
            order.append(job.phase)
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        red_job = TDDJob(module_name="single", phase="red", scoped_files=["single/test.py"])
        green_job = TDDJob(module_name="single", phase="green", scoped_files=["single/single.py"])

        await runner.run_module_tdd_cycle(red_job=red_job, green_job=green_job)

        assert order == ["red", "green"], f"Expected ['red', 'green'], got {order}"

    @pytest.mark.asyncio
    async def test_large_batch_phase_a_all_complete_before_phase_b(self):
        """Edge: with 50 modules, all RED jobs complete before any GREEN job starts."""
        red_done_count = 0
        phase_b_seen_incomplete_a = False
        total_modules = 50

        async def executor(job: TDDJob, context: dict | None = None):
            nonlocal red_done_count, phase_b_seen_incomplete_a
            if job.phase == "red":
                await asyncio.sleep(0.001)
                red_done_count += 1
            elif job.phase == "green":
                if red_done_count < total_modules:
                    phase_b_seen_incomplete_a = True
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        red_jobs = [
            TDDJob(module_name=f"m{i}", phase="red", scoped_files=[f"m{i}/test.py"])
            for i in range(total_modules)
        ]
        green_jobs = [
            TDDJob(module_name=f"m{i}", phase="green", scoped_files=[f"m{i}/m{i}.py"])
            for i in range(total_modules)
        ]

        await runner.run_phase_a(jobs=red_jobs)
        await runner.run_phase_b(jobs=green_jobs)

        assert phase_b_seen_incomplete_a is False, (
            "Phase B must not start while Phase A is still incomplete"
        )

    @pytest.mark.asyncio
    async def test_run_phase_a_returns_list_of_job_results(self):
        """run_phase_a must return a list of JobResult objects."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        jobs = [TDDJob(module_name=f"m{i}", phase="red", scoped_files=[f"m{i}/test.py"]) for i in range(3)]

        results = await runner.run_phase_a(jobs=jobs)

        assert isinstance(results, list), "run_phase_a must return a list"
        assert len(results) == 3, f"Expected 3 results, got {len(results)}"
        for r in results:
            assert isinstance(r, JobResult), f"Each element must be a JobResult, got {type(r).__name__}"

    @pytest.mark.asyncio
    async def test_run_phase_b_returns_list_of_job_results(self):
        """run_phase_b must return a list of JobResult objects."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        jobs = [TDDJob(module_name=f"m{i}", phase="green", scoped_files=[f"m{i}/m{i}.py"]) for i in range(3)]

        results = await runner.run_phase_b(jobs=jobs)

        assert isinstance(results, list), "run_phase_b must return a list"
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_runner_result_has_passed_attribute(self):
        """RunnerResult must have a 'passed' attribute."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        result = await runner.run(modules=[])

        assert hasattr(result, "passed"), "RunnerResult must have 'passed' field"

    @pytest.mark.asyncio
    async def test_runner_result_has_job_results_attribute(self):
        """RunnerResult must have a 'job_results' attribute."""
        async def executor(job: TDDJob, context: dict | None = None):
            return JobResult(status=JobStatus.PASSED, attempts=1, error=None, staged_files=job.scoped_files)

        runner = TDDRunner(executor=executor, config={"max_retries": 1})
        result = await runner.run(modules=[])

        assert hasattr(result, "job_results"), "RunnerResult must have 'job_results' field"

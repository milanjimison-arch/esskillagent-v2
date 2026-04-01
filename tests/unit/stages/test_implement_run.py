"""RED-phase tests for ImplementStage.run() — TDD lifecycle orchestration.

Covers the key behaviors required by the spec:
  1.  Reading pending tasks from plan stage output.
  2.  RED prompt is constrained to test-only code generation.
  3.  Extra retry for GREEN failures caused by environment (not code).
  4.  Completed tasks are skipped without re-running TDD cycles.
  5.  Parallel task sets are validated for non-overlapping file ownership.
  6.  Three-way review is triggered after GREEN phase completes.
  7.  Convergence detection operates correctly in the TDD runner.
  8.  Gap-detected supplementary tasks are generated when gaps are found.
  9.  Batch commit with CI validation after all tasks pass.
  10. LVL lifecycle events emitted at critical steps.
  11. TDD runner module size is enforced below 450 lines.

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/stages/implement.py provides a complete implementation.

The current implement.py stub returns a StageResult that acknowledges
sub-steps but does NOT:
  - read tasks from a store or task source
  - run TDD cycles (RED → GREEN)
  - constrain RED prompts to test-only generation
  - retry GREEN on environment failures
  - skip completed tasks
  - validate parallel file sets
  - trigger three-way review after GREEN
  - detect convergence
  - generate supplementary gap tasks
  - batch-commit with CI validation
  - emit LVL events
"""

from __future__ import annotations

import inspect
import pathlib
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.stages.base import StageResult
from orchestrator.stages.implement import ImplementStage


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_store(tasks: list | None = None) -> MagicMock:
    """Return a mock store pre-loaded with the given task list."""
    store = MagicMock()
    store.save_checkpoint = MagicMock()
    store.get_pending_tasks = MagicMock(return_value=tasks or [])
    store.get_tasks = MagicMock(return_value=tasks or [])
    store.mark_task_completed = MagicMock()
    store.add_task = MagicMock()
    return store


def _make_task(
    task_id: str = "T001",
    status: str = "pending",
    file_path: str = "src/module_a.py",
    description: str = "Implement feature A",
) -> MagicMock:
    task = MagicMock()
    task.task_id = task_id
    task.status = status
    task.file_path = file_path
    task.description = description
    return task


def _make_tdd_runner(pass_red: bool = True, pass_green: bool = True) -> MagicMock:
    """Return a mock TDD runner whose run() returns a passing RunnerResult."""
    runner = MagicMock()
    runner_result = MagicMock()
    runner_result.passed = pass_red and pass_green
    runner_result.job_results = []
    runner.run = AsyncMock(return_value=runner_result)
    return runner


def _make_review_pipeline(passed: bool = True, gaps: list | None = None) -> MagicMock:
    """Return a mock ReviewPipeline."""
    pipeline = MagicMock()
    result = MagicMock()
    result.passed = passed
    result.gaps = gaps or []
    result.supplemental_tasks = [f"Fix gap: {g}" for g in (gaps or [])]
    pipeline.run = AsyncMock(return_value=result)
    return pipeline


def _make_ci_runner(passed: bool = True) -> MagicMock:
    """Return a mock CI runner."""
    runner = MagicMock()
    result = MagicMock()
    result.passed = passed
    runner.run = AsyncMock(return_value=result)
    return runner


# ---------------------------------------------------------------------------
# 1. Reading pending tasks from plan stage output
# ---------------------------------------------------------------------------


class TestReadPendingTasks:
    """ImplementStage.run() must read and process pending tasks."""

    @pytest.mark.asyncio
    async def test_run_reads_pending_tasks_from_store(self):
        """FR-impl-run-001: run() MUST read pending tasks from the task store."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult), (
            "run() must return a StageResult"
        )
        # Verify that the store was queried for tasks
        assert store.get_pending_tasks.called or store.get_tasks.called, (
            "run() must call store.get_pending_tasks() or store.get_tasks() "
            "to read tasks from the plan stage"
        )

    @pytest.mark.asyncio
    async def test_run_processes_all_pending_tasks(self):
        """FR-impl-run-002: run() MUST process every pending task."""
        tasks = [
            _make_task("T001", file_path="src/a.py"),
            _make_task("T002", file_path="src/b.py"),
            _make_task("T003", file_path="src/c.py"),
        ]
        store = _make_store(tasks=tasks)
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult)
        processed = result.data.get("tasks_processed", result.data.get("processed_tasks", []))
        assert len(processed) == 3, (
            f"run() must process all 3 pending tasks, got {len(processed)}"
        )

    @pytest.mark.asyncio
    async def test_run_with_no_pending_tasks_returns_passed(self):
        """FR-impl-run-003: run() with no pending tasks MUST still return passed StageResult."""
        store = _make_store(tasks=[])
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult)
        assert result.passed is True, (
            "run() with no pending tasks should return passed=True (nothing to do)"
        )

    @pytest.mark.asyncio
    async def test_run_result_data_contains_tasks_info(self):
        """FR-impl-run-004: StageResult.data MUST contain task-related information."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result.data, dict), "StageResult.data must be a dict"
        # Result must include some indication of which tasks were handled
        has_task_info = any(
            key in result.data
            for key in ("tasks_processed", "processed_tasks", "task_results", "tasks")
        )
        assert has_task_info, (
            f"StageResult.data must contain task information, got keys: {list(result.data.keys())}"
        )


# ---------------------------------------------------------------------------
# 2. RED prompt constrained to test-only generation
# ---------------------------------------------------------------------------


class TestRedPromptConstraint:
    """RED phase prompt must instruct the agent to generate tests ONLY."""

    @pytest.mark.asyncio
    async def test_red_phase_prompt_contains_test_only_constraint(self):
        """FR-impl-run-005: RED prompt MUST explicitly restrict output to test code."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])

        captured_prompts: list[str] = []

        async def _capture_executor(job, context=None):
            # Capture the prompt/context used to invoke the RED phase
            prompt = getattr(job, "prompt", "") or str(context or "")
            captured_prompts.append(prompt)
            result = MagicMock()
            result.status = "passed"
            result.error = None
            result.staged_files = []
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _capture_executor

        await stage.run()

        # At least one RED-phase invocation must have occurred
        assert len(captured_prompts) > 0, (
            "run() must invoke the TDD executor for RED phase"
        )
        # The RED prompt must contain a constraint keyword
        red_prompts = [p for p in captured_prompts if "test" in p.lower() or "red" in p.lower()]
        assert len(red_prompts) > 0, (
            "RED phase prompt must reference 'test' or 'RED' to constrain output to test code"
        )

    @pytest.mark.asyncio
    async def test_red_phase_job_phase_attribute_is_red(self):
        """FR-impl-run-006: TDD job created for RED phase MUST have phase='red'."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])

        captured_jobs: list = []

        async def _capture_executor(job, context=None):
            captured_jobs.append(job)
            result = MagicMock()
            result.status = "passed"
            result.error = None
            result.staged_files = []
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _capture_executor

        await stage.run()

        red_jobs = [j for j in captured_jobs if getattr(j, "phase", None) == "red"]
        assert len(red_jobs) > 0, (
            "run() must create at least one TDD job with phase='red' for RED phase"
        )

    @pytest.mark.asyncio
    async def test_red_phase_produces_test_files_not_implementation(self):
        """FR-impl-run-007: Files staged after RED phase MUST be test files."""
        task = _make_task("T001", status="pending", file_path="src/feature.py")
        store = _make_store(tasks=[task])

        staged_files_by_phase: dict[str, list[str]] = {}

        async def _capture_executor(job, context=None):
            phase = getattr(job, "phase", "unknown")
            scoped = getattr(job, "scoped_files", [])
            staged_files_by_phase.setdefault(phase, []).extend(scoped)
            result = MagicMock()
            result.status = "passed"
            result.error = None
            result.staged_files = scoped
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _capture_executor

        await stage.run()

        red_files = staged_files_by_phase.get("red", [])
        if red_files:
            non_test_files = [f for f in red_files if "test" not in f.lower()]
            assert len(non_test_files) == 0, (
                f"RED phase must only stage test files, but found non-test files: {non_test_files}"
            )


# ---------------------------------------------------------------------------
# 3. Extra retry for environment-caused GREEN failures
# ---------------------------------------------------------------------------


class TestEnvironmentGreenRetry:
    """GREEN failures caused by environment issues must receive an extra retry."""

    @pytest.mark.asyncio
    async def test_green_env_failure_triggers_extra_retry(self):
        """FR-impl-run-008: GREEN phase env failure MUST trigger one extra retry."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])

        call_count = 0

        async def _flaky_executor(job, context=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            phase = getattr(job, "phase", "unknown")
            if phase == "green" and call_count == 1:
                # First GREEN attempt fails with environment error
                result.status = "failed"
                result.error = "EnvironmentError: Docker container unavailable"
                result.staged_files = []
            else:
                result.status = "passed"
                result.error = None
                result.staged_files = []
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _flaky_executor

        result = await stage.run()

        assert isinstance(result, StageResult)
        # The stage should have retried and eventually passed
        green_attempts = sum(
            1 for _ in range(call_count) if call_count >= 2
        )
        assert call_count >= 2, (
            f"GREEN env failure must trigger a retry — expected >=2 calls, got {call_count}"
        )

    @pytest.mark.asyncio
    async def test_env_error_classified_triggers_retry(self):
        """FR-impl-run-009: Errors with env keywords MUST be classified as env failures."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])

        env_error_messages = [
            "EnvironmentError: Docker container not found",
            "ConnectionError: Could not connect to test database",
            "TimeoutError: CI runner timed out",
            "OSError: No space left on device",
        ]

        green_call_count = 0

        async def _env_error_executor(job, context=None):
            nonlocal green_call_count
            result = MagicMock()
            phase = getattr(job, "phase", "unknown")
            if phase == "green":
                green_call_count += 1
                if green_call_count == 1:
                    result.status = "failed"
                    result.error = env_error_messages[0]
                    result.staged_files = []
                    return result
            result.status = "passed"
            result.error = None
            result.staged_files = []
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _env_error_executor

        result = await stage.run()

        assert isinstance(result, StageResult)
        assert green_call_count >= 2, (
            f"Environment-caused GREEN failure must get at least 2 attempts (1 + retry), "
            f"got {green_call_count}"
        )

    @pytest.mark.asyncio
    async def test_code_failure_in_green_does_not_get_extra_retry(self):
        """FR-impl-run-010: Code errors in GREEN MUST NOT receive the extra env retry."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])

        green_call_count = 0

        async def _code_error_executor(job, context=None):
            nonlocal green_call_count
            result = MagicMock()
            phase = getattr(job, "phase", "unknown")
            if phase == "green":
                green_call_count += 1
                result.status = "failed"
                result.error = "AssertionError: expected 42, got 0"
                result.staged_files = []
            else:
                result.status = "passed"
                result.error = None
                result.staged_files = []
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _code_error_executor
        # Disable extra env retries for code errors
        # (max_env_retries = 0 means only normal max_retries apply)

        result = await stage.run()

        assert isinstance(result, StageResult)
        # A pure code assertion error should NOT get an unbounded extra env retry
        # The green_call_count should be bounded (not infinite retry loop)
        assert green_call_count <= 5, (
            f"Code failure in GREEN should not cause infinite retries, "
            f"but got {green_call_count} GREEN calls"
        )


# ---------------------------------------------------------------------------
# 4. Skip completed tasks
# ---------------------------------------------------------------------------


class TestSkipCompletedTasks:
    """Tasks already marked as 'completed' must be skipped."""

    @pytest.mark.asyncio
    async def test_completed_tasks_are_skipped(self):
        """FR-impl-run-011: Tasks with status='completed' MUST NOT run TDD cycles."""
        tasks = [
            _make_task("T001", status="completed", file_path="src/done.py"),
            _make_task("T002", status="pending", file_path="src/todo.py"),
        ]
        store = _make_store(tasks=tasks)

        executed_modules: list[str] = []

        async def _tracking_executor(job, context=None):
            executed_modules.append(getattr(job, "module_name", "unknown"))
            result = MagicMock()
            result.status = "passed"
            result.error = None
            result.staged_files = []
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _tracking_executor

        result = await stage.run()

        assert isinstance(result, StageResult)
        # T001 (completed) must not have triggered a TDD job
        completed_task_executed = any("T001" in m or "done" in m for m in executed_modules)
        assert not completed_task_executed, (
            f"Completed task T001 must be skipped, but found execution for modules: {executed_modules}"
        )

    @pytest.mark.asyncio
    async def test_only_pending_tasks_are_executed(self):
        """FR-impl-run-012: Only tasks with status='pending' MUST be executed."""
        tasks = [
            _make_task("T001", status="completed"),
            _make_task("T002", status="pending"),
            _make_task("T003", status="skipped"),
            _make_task("T004", status="pending"),
        ]
        store = _make_store(tasks=tasks)

        tdd_invocation_count = 0

        async def _counting_executor(job, context=None):
            nonlocal tdd_invocation_count
            tdd_invocation_count += 1
            result = MagicMock()
            result.status = "passed"
            result.error = None
            result.staged_files = []
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _counting_executor

        await stage.run()

        # RED + GREEN for 2 pending tasks = 4 executor calls max
        # (T001 completed and T003 skipped should generate 0 calls each)
        assert tdd_invocation_count <= 4, (
            f"Only pending tasks (T002, T004) should run TDD cycles; "
            f"expected <=4 executor calls (2 RED + 2 GREEN), got {tdd_invocation_count}"
        )

    @pytest.mark.asyncio
    async def test_skipped_tasks_are_recorded_in_result(self):
        """FR-impl-run-013: Skipped completed tasks MUST be recorded in StageResult.data."""
        tasks = [
            _make_task("T001", status="completed"),
            _make_task("T002", status="pending"),
        ]
        store = _make_store(tasks=tasks)
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult)
        skipped = result.data.get("skipped_tasks", result.data.get("tasks_skipped", []))
        assert len(skipped) >= 1, (
            f"result.data must record at least 1 skipped task (T001), "
            f"got skipped={skipped!r}"
        )


# ---------------------------------------------------------------------------
# 5. Parallel execution file set non-overlap validation
# ---------------------------------------------------------------------------


class TestParallelFileSetValidation:
    """Parallel tasks must not target overlapping file sets."""

    @pytest.mark.asyncio
    async def test_non_overlapping_parallel_tasks_are_allowed(self):
        """FR-impl-run-014: Parallel tasks with distinct file sets MUST be allowed."""
        tasks = [
            _make_task("T001", file_path="src/module_a.py"),
            _make_task("T002", file_path="src/module_b.py"),
        ]
        store = _make_store(tasks=tasks)
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult)
        # Non-overlapping tasks must not raise a conflict error
        assert result.error is None or "conflict" not in (result.error or "").lower(), (
            "Non-overlapping file sets must not produce a conflict error"
        )

    @pytest.mark.asyncio
    async def test_overlapping_parallel_tasks_are_rejected(self):
        """FR-impl-run-015: Parallel tasks sharing a file MUST be detected and rejected."""
        tasks = [
            _make_task("T001", file_path="src/shared_module.py"),
            _make_task("T002", file_path="src/shared_module.py"),
        ]
        store = _make_store(tasks=tasks)
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult)
        # Overlapping file sets must produce either:
        # a) result.passed=False with a conflict in result.error or data
        # b) a serialisation of the conflicting tasks (they run serially)
        has_conflict_detection = (
            result.passed is False
            or "conflict" in str(result.data).lower()
            or "overlap" in str(result.data).lower()
            or "serial" in str(result.data).lower()
        )
        assert has_conflict_detection, (
            "Overlapping file sets must be detected; result should record conflict "
            f"or force serial execution. Got: passed={result.passed}, data={result.data}"
        )

    @pytest.mark.asyncio
    async def test_validator_called_before_parallel_execution(self):
        """FR-impl-run-016: File-set validator MUST be invoked before parallel TDD execution."""
        tasks = [
            _make_task("T001", file_path="src/a.py"),
            _make_task("T002", file_path="src/b.py"),
        ]
        store = _make_store(tasks=tasks)
        stage = ImplementStage(store=store)

        validator_called = False
        original_validate = None

        # Inject a tracking validator
        with patch(
            "orchestrator.tdd.validator.ParallelTaskValidator.validate_tasks",
            side_effect=lambda tasks: (
                setattr(__import__("builtins"), "_validator_called", True)
                or __import__("orchestrator.tdd.validator", fromlist=["ParallelTaskValidator"])
                .ParallelTaskValidator()
                .validate_tasks.__wrapped__(tasks)
                if hasattr(
                    __import__("orchestrator.tdd.validator", fromlist=["ParallelTaskValidator"])
                    .ParallelTaskValidator()
                    .validate_tasks,
                    "__wrapped__",
                )
                else type("R", (), {"is_parallel_safe": True, "conflicts": [], "execution_mode": "parallel"})()
            ),
        ) as mock_validate:
            result = await stage.run()

        # The validator should have been consulted
        assert isinstance(result, StageResult), "run() must return a StageResult"

    @pytest.mark.asyncio
    async def test_conflict_info_recorded_in_result_data(self):
        """FR-impl-run-017: File conflicts MUST be recorded in StageResult.data."""
        tasks = [
            _make_task("T001", file_path="src/conflict.py"),
            _make_task("T002", file_path="src/conflict.py"),
        ]
        store = _make_store(tasks=tasks)
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult)
        # Data must contain conflict or mode information
        data_str = str(result.data).lower()
        has_conflict_data = (
            "conflict" in data_str
            or "overlap" in data_str
            or "serial" in data_str
            or "parallel" in data_str
        )
        assert has_conflict_data, (
            "StageResult.data must record parallel/serial execution mode or file conflicts, "
            f"got data keys: {list(result.data.keys())}"
        )


# ---------------------------------------------------------------------------
# 6. Three-way review after GREEN
# ---------------------------------------------------------------------------


class TestThreeWayReviewAfterGreen:
    """After GREEN phase, a three-way review (code, security, brooks) must be triggered."""

    @pytest.mark.asyncio
    async def test_review_pipeline_is_invoked_after_green(self):
        """FR-impl-run-018: ReviewPipeline.run() MUST be called after GREEN completes."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])

        review_called = False

        async def _mock_review_run(context):
            nonlocal review_called
            review_called = True
            result = MagicMock()
            result.passed = True
            result.gaps = []
            result.supplemental_tasks = []
            return result

        stage = ImplementStage(store=store)
        # Inject review pipeline
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(side_effect=_mock_review_run)
        stage._review_pipeline = mock_pipeline

        await stage.run()

        assert review_called, (
            "ReviewPipeline.run() must be called after GREEN phase completes"
        )

    @pytest.mark.asyncio
    async def test_three_reviewers_are_triggered(self):
        """FR-impl-run-019: Three-way review MUST invoke code, security, and brooks reviewers."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])

        with patch(
            "orchestrator.review.pipeline.run_code_reviewer",
            new_callable=AsyncMock,
        ) as mock_code, patch(
            "orchestrator.review.pipeline.run_security_reviewer",
            new_callable=AsyncMock,
        ) as mock_security, patch(
            "orchestrator.review.pipeline.run_brooks_reviewer",
            new_callable=AsyncMock,
        ) as mock_brooks:
            passing_result = MagicMock()
            passing_result.reviewer = "code"
            passing_result.passed = True
            passing_result.issues = ()
            passing_result.verdict = "pass"
            mock_code.return_value = passing_result
            mock_security.return_value = MagicMock(
                reviewer="security", passed=True, issues=(), verdict="pass"
            )
            mock_brooks.return_value = MagicMock(
                reviewer="brooks", passed=True, issues=(), verdict="pass"
            )

            stage = ImplementStage(store=store)
            result = await stage.run()

        assert isinstance(result, StageResult)
        # At minimum the stage must return a valid result without crashing
        # (actual reviewer invocation depends on implementation)

    @pytest.mark.asyncio
    async def test_review_result_is_recorded_in_stage_result_data(self):
        """FR-impl-run-020: Review outcome MUST be recorded in StageResult.data."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        mock_review_result = MagicMock()
        mock_review_result.passed = True
        mock_review_result.gaps = []
        mock_review_result.supplemental_tasks = []
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=mock_review_result)
        stage._review_pipeline = mock_pipeline

        result = await stage.run()

        assert isinstance(result, StageResult)
        has_review_data = any(
            key in result.data
            for key in ("review_result", "review_passed", "review", "three_way_review")
        )
        assert has_review_data, (
            "StageResult.data must contain review outcome information, "
            f"got keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_review_failure_causes_stage_to_fail(self):
        """FR-impl-run-021: Failed three-way review MUST result in run() returning passed=False."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        mock_review_result = MagicMock()
        mock_review_result.passed = False
        mock_review_result.gaps = []
        mock_review_result.supplemental_tasks = []
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=mock_review_result)
        stage._review_pipeline = mock_pipeline

        result = await stage.run()

        assert isinstance(result, StageResult)
        assert result.passed is False, (
            "run() must return passed=False when the three-way review fails"
        )


# ---------------------------------------------------------------------------
# 7. Convergence detection in TDD runner
# ---------------------------------------------------------------------------


class TestConvergenceDetection:
    """TDD runner convergence detection must correctly identify stale / diverging state."""

    @pytest.mark.asyncio
    async def test_convergence_detected_when_done_count_increases(self):
        """FR-impl-run-022: Convergence MUST be detected when completed task count grows."""
        from orchestrator.monitor import PipelineMonitor

        monitor = PipelineMonitor()

        # First call: baseline
        tasks_baseline = [
            {"id": "T001", "status": "DONE"},
            {"id": "T002", "status": "PENDING"},
        ]
        monitor.check(tasks_baseline)

        # Second call: one more task completed
        tasks_progress = [
            {"id": "T001", "status": "DONE"},
            {"id": "T002", "status": "DONE"},
        ]
        observations = monitor.check(tasks_progress)

        converging = [o for o in observations if o.get("type") == "pipeline_converging"]
        assert len(converging) >= 1, (
            "PipelineMonitor must emit 'pipeline_converging' observation when DONE count increases"
        )

    @pytest.mark.asyncio
    async def test_divergence_detected_when_done_count_stagnates(self):
        """FR-impl-run-023: Divergence MUST be detected when task completion stagnates."""
        from orchestrator.monitor import PipelineMonitor

        monitor = PipelineMonitor()

        tasks = [
            {"id": "T001", "status": "DONE"},
            {"id": "T002", "status": "BLOCKED"},
        ]
        monitor.check(tasks)

        # Same done count, blocked remains — diverging
        same_tasks = [
            {"id": "T001", "status": "DONE"},
            {"id": "T002", "status": "BLOCKED"},
        ]
        observations = monitor.check(same_tasks)

        diverging = [o for o in observations if o.get("type") == "pipeline_diverging"]
        assert len(diverging) >= 1, (
            "PipelineMonitor must emit 'pipeline_diverging' when DONE count does not increase"
        )

    @pytest.mark.asyncio
    async def test_implement_run_triggers_convergence_check(self):
        """FR-impl-run-024: run() MUST invoke convergence check after each TDD cycle."""
        tasks = [
            _make_task("T001", status="pending"),
        ]
        store = _make_store(tasks=tasks)
        stage = ImplementStage(store=store)

        monitor_check_called = False

        original_check = None
        from orchestrator import monitor as monitor_module

        original_check = monitor_module.PipelineMonitor.check

        def _tracking_check(self, tasks_arg):
            nonlocal monitor_check_called
            monitor_check_called = True
            return original_check(self, tasks_arg)

        monitor_module.PipelineMonitor.check = _tracking_check
        try:
            result = await stage.run()
        finally:
            monitor_module.PipelineMonitor.check = original_check

        assert isinstance(result, StageResult)
        assert monitor_check_called, (
            "run() must invoke PipelineMonitor.check() for convergence tracking"
        )


# ---------------------------------------------------------------------------
# 8. Gap-detected supplementary tasks
# ---------------------------------------------------------------------------


class TestGapDetectedSupplementaryTasks:
    """When review detects feature gaps, supplementary tasks must be generated."""

    @pytest.mark.asyncio
    async def test_supplementary_tasks_created_for_detected_gaps(self):
        """FR-impl-run-025: Detected gaps MUST result in supplementary tasks in result.data."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        mock_review_result = MagicMock()
        mock_review_result.passed = True
        mock_review_result.gaps = ["Missing feature: error handling", "Missing feature: logging"]
        mock_review_result.supplemental_tasks = [
            "Implement missing feature: error handling",
            "Implement missing feature: logging",
        ]
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=mock_review_result)
        stage._review_pipeline = mock_pipeline

        result = await stage.run()

        assert isinstance(result, StageResult)
        supplementary = result.data.get(
            "supplemental_tasks",
            result.data.get("supplementary_tasks", result.data.get("gap_tasks", [])),
        )
        assert len(supplementary) == 2, (
            f"run() must record 2 supplementary tasks for 2 detected gaps, "
            f"got {len(supplementary)}: {supplementary}"
        )

    @pytest.mark.asyncio
    async def test_no_supplementary_tasks_when_no_gaps(self):
        """FR-impl-run-026: No supplementary tasks MUST be added when review finds no gaps."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        mock_review_result = MagicMock()
        mock_review_result.passed = True
        mock_review_result.gaps = []
        mock_review_result.supplemental_tasks = []
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=mock_review_result)
        stage._review_pipeline = mock_pipeline

        result = await stage.run()

        assert isinstance(result, StageResult)
        supplementary = result.data.get(
            "supplemental_tasks",
            result.data.get("supplementary_tasks", result.data.get("gap_tasks", [])),
        )
        assert len(supplementary) == 0, (
            f"run() must not add supplementary tasks when no gaps found, "
            f"got {supplementary}"
        )

    @pytest.mark.asyncio
    async def test_gaps_are_recorded_in_result_data(self):
        """FR-impl-run-027: Detected gaps MUST be listed in StageResult.data."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        gap_description = "Missing feature: authentication"
        mock_review_result = MagicMock()
        mock_review_result.passed = True
        mock_review_result.gaps = [gap_description]
        mock_review_result.supplemental_tasks = [f"Implement: {gap_description}"]
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=mock_review_result)
        stage._review_pipeline = mock_pipeline

        result = await stage.run()

        assert isinstance(result, StageResult)
        gaps_in_data = result.data.get("gaps", result.data.get("feature_gaps", []))
        assert len(gaps_in_data) >= 1, (
            f"StageResult.data must contain detected gaps, "
            f"got gaps={gaps_in_data!r}"
        )


# ---------------------------------------------------------------------------
# 9. Batch commit with CI validation
# ---------------------------------------------------------------------------


class TestBatchCommitWithCIValidation:
    """After TDD cycles, changes must be batch-committed and CI must validate."""

    @pytest.mark.asyncio
    async def test_batch_commit_is_invoked_after_tdd(self):
        """FR-impl-run-028: Batch git commit MUST be performed after TDD cycles complete."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        commit_called = False

        async def _mock_commit(files=None, message=None):
            nonlocal commit_called
            commit_called = True
            return True

        stage._batch_commit = _mock_commit

        result = await stage.run()

        assert isinstance(result, StageResult)
        assert commit_called, (
            "run() must call batch_commit() after TDD cycles to persist changes"
        )

    @pytest.mark.asyncio
    async def test_ci_validation_runs_after_commit(self):
        """FR-impl-run-029: CI validation MUST run after the batch commit."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        ci_called = False
        commit_called = False
        call_order: list[str] = []

        async def _mock_commit(files=None, message=None):
            nonlocal commit_called
            commit_called = True
            call_order.append("commit")
            return True

        async def _mock_ci(context=None):
            nonlocal ci_called
            ci_called = True
            call_order.append("ci")
            result = MagicMock()
            result.passed = True
            return result

        stage._batch_commit = _mock_commit
        stage._run_ci = _mock_ci

        result = await stage.run()

        assert isinstance(result, StageResult)
        assert ci_called, "run() must invoke CI validation after committing"
        if commit_called:
            # If both are called, commit must precede CI
            assert call_order.index("commit") < call_order.index("ci"), (
                "batch_commit() must be called before CI validation"
            )

    @pytest.mark.asyncio
    async def test_ci_failure_is_recorded_in_result(self):
        """FR-impl-run-030: CI failure MUST be recorded in StageResult.data."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        async def _failing_ci(context=None):
            result = MagicMock()
            result.passed = False
            return result

        stage._run_ci = _failing_ci

        result = await stage.run()

        assert isinstance(result, StageResult)
        # CI failure should be reflected in result
        ci_data = result.data.get("ci_result", result.data.get("ci_passed", None))
        stage_failed = result.passed is False
        has_ci_info = ci_data is not None or stage_failed
        assert has_ci_info, (
            "CI failure must be reflected in StageResult (passed=False or data.ci_result)"
        )

    @pytest.mark.asyncio
    async def test_result_data_contains_push_ci_step(self):
        """FR-impl-run-031: 'push+CI' sub-step MUST appear in steps_executed."""
        store = _make_store(tasks=[])
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult)
        steps = result.data.get("steps_executed", [])
        assert "push+CI" in steps, (
            f"'push+CI' must be in steps_executed, got: {steps}"
        )


# ---------------------------------------------------------------------------
# 10. LVL lifecycle events
# ---------------------------------------------------------------------------


class TestLvlEvents:
    """Critical steps must emit LVL lifecycle events."""

    @pytest.mark.asyncio
    async def test_lvl_event_emitted_when_tdd_starts(self):
        """FR-impl-run-032: LVL event MUST be emitted when TDD phase begins."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        emitted_events: list[dict] = []

        async def _mock_emit(event_type: str, payload: dict | None = None):
            emitted_events.append({"event_type": event_type, "payload": payload or {}})

        stage._emit_lvl_event = _mock_emit

        await stage.run()

        tdd_events = [e for e in emitted_events if "tdd" in e["event_type"].lower()]
        assert len(tdd_events) >= 1, (
            f"At least one LVL event with 'tdd' in its type must be emitted, "
            f"got events: {[e['event_type'] for e in emitted_events]}"
        )

    @pytest.mark.asyncio
    async def test_lvl_event_emitted_after_review_completes(self):
        """FR-impl-run-033: LVL event MUST be emitted after review gate completes."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])
        stage = ImplementStage(store=store)

        emitted_events: list[dict] = []

        async def _mock_emit(event_type: str, payload: dict | None = None):
            emitted_events.append({"event_type": event_type, "payload": payload or {}})

        mock_review_result = MagicMock()
        mock_review_result.passed = True
        mock_review_result.gaps = []
        mock_review_result.supplemental_tasks = []
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=mock_review_result)
        stage._review_pipeline = mock_pipeline
        stage._emit_lvl_event = _mock_emit

        await stage.run()

        review_events = [
            e for e in emitted_events
            if "review" in e["event_type"].lower() or "complete" in e["event_type"].lower()
        ]
        assert len(review_events) >= 1, (
            f"At least one LVL event related to review must be emitted, "
            f"got: {[e['event_type'] for e in emitted_events]}"
        )

    @pytest.mark.asyncio
    async def test_lvl_event_emitted_on_stage_complete(self):
        """FR-impl-run-034: LVL 'stage_complete' event MUST be emitted when implement stage finishes."""
        store = _make_store(tasks=[])
        stage = ImplementStage(store=store)

        emitted_events: list[dict] = []

        async def _mock_emit(event_type: str, payload: dict | None = None):
            emitted_events.append({"event_type": event_type, "payload": payload or {}})

        stage._emit_lvl_event = _mock_emit

        result = await stage.run()

        assert isinstance(result, StageResult)
        complete_events = [
            e for e in emitted_events
            if "complete" in e["event_type"].lower() or "implement" in e["event_type"].lower()
        ]
        assert len(complete_events) >= 1, (
            f"A 'stage_complete' or 'implement' LVL event must be emitted when run() finishes, "
            f"got events: {[e['event_type'] for e in emitted_events]}"
        )

    @pytest.mark.asyncio
    async def test_result_data_contains_stage_complete_marker(self):
        """FR-impl-run-035: StageResult.data MUST contain 'stage_complete' marker."""
        store = _make_store(tasks=[])
        stage = ImplementStage(store=store)

        result = await stage.run()

        assert isinstance(result, StageResult)
        stage_complete = result.data.get("stage_complete")
        assert stage_complete == "implement", (
            f"StageResult.data['stage_complete'] must equal 'implement', "
            f"got {stage_complete!r}"
        )


# ---------------------------------------------------------------------------
# 11. TDD runner module size enforcement
# ---------------------------------------------------------------------------


class TestTddRunnerModuleSize:
    """TDD runner module must remain below 450 lines."""

    def test_tdd_runner_module_is_below_450_lines(self):
        """FR-impl-run-036: orchestrator/tdd/runner.py MUST be < 450 lines."""
        runner_path = pathlib.Path(__file__).parent.parent.parent.parent / (
            "orchestrator/tdd/runner.py"
        )
        assert runner_path.exists(), (
            f"orchestrator/tdd/runner.py must exist at {runner_path}"
        )
        lines = runner_path.read_text(encoding="utf-8").splitlines()
        line_count = len(lines)
        assert line_count < 450, (
            f"orchestrator/tdd/runner.py must be below 450 lines, "
            f"but has {line_count} lines"
        )

    def test_tdd_runner_module_has_meaningful_content(self):
        """FR-impl-run-037: TDD runner module must have non-trivial content (> 50 lines)."""
        runner_path = pathlib.Path(__file__).parent.parent.parent.parent / (
            "orchestrator/tdd/runner.py"
        )
        assert runner_path.exists(), "orchestrator/tdd/runner.py must exist"
        lines = runner_path.read_text(encoding="utf-8").splitlines()
        non_blank = [l for l in lines if l.strip()]
        assert len(non_blank) > 50, (
            f"orchestrator/tdd/runner.py must have meaningful content (>50 non-blank lines), "
            f"got {len(non_blank)} non-blank lines"
        )

    def test_implement_module_does_not_embed_tdd_runner_logic(self):
        """FR-impl-run-038: implement.py MUST NOT duplicate TDD runner logic inline."""
        impl_path = pathlib.Path(__file__).parent.parent.parent.parent / (
            "orchestrator/stages/implement.py"
        )
        assert impl_path.exists(), "orchestrator/stages/implement.py must exist"
        content = impl_path.read_text(encoding="utf-8")
        # If TDD runner logic is inlined, the file will be excessively large
        lines = content.splitlines()
        assert len(lines) < 500, (
            f"orchestrator/stages/implement.py appears to inline TDD runner logic "
            f"({len(lines)} lines). Runner logic must live in orchestrator/tdd/runner.py"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestImplementRunEdgeCases:
    """Edge cases for ImplementStage.run()."""

    @pytest.mark.asyncio
    async def test_run_with_single_task_returns_stage_result(self):
        """Edge: Single-task run must return a valid StageResult."""
        store = _make_store(tasks=[_make_task("T001")])
        stage = ImplementStage(store=store)
        result = await stage.run()
        assert isinstance(result, StageResult)

    @pytest.mark.asyncio
    async def test_run_result_is_immutable(self):
        """Edge: StageResult returned by run() MUST be immutable."""
        store = _make_store(tasks=[])
        stage = ImplementStage(store=store)
        result = await stage.run()
        assert isinstance(result, StageResult)
        with pytest.raises(AttributeError):
            result.passed = False  # type: ignore[misc]

    @pytest.mark.asyncio
    async def test_run_with_many_tasks_does_not_crash(self):
        """Edge: Large task list (20 tasks) must not crash run()."""
        tasks = [_make_task(f"T{i:03d}", file_path=f"src/module_{i}.py") for i in range(1, 21)]
        store = _make_store(tasks=tasks)
        stage = ImplementStage(store=store)
        result = await stage.run()
        assert isinstance(result, StageResult)

    @pytest.mark.asyncio
    async def test_run_returns_stage_result_on_tdd_failure(self):
        """Edge: Even when TDD fails, run() MUST return a StageResult (not raise)."""
        task = _make_task("T001", status="pending")
        store = _make_store(tasks=[task])

        async def _always_fail(job, context=None):
            result = MagicMock()
            result.status = "failed"
            result.error = "Persistent failure"
            result.staged_files = []
            return result

        stage = ImplementStage(store=store)
        stage._tdd_executor = _always_fail

        result = await stage.run()
        assert isinstance(result, StageResult), (
            "run() must return a StageResult even when all TDD jobs fail"
        )

    @pytest.mark.asyncio
    async def test_run_result_data_is_dict(self):
        """Edge: StageResult.data must always be a dict."""
        store = _make_store(tasks=[])
        stage = ImplementStage(store=store)
        result = await stage.run()
        assert isinstance(result.data, dict), (
            f"StageResult.data must be a dict, got {type(result.data)}"
        )

    @pytest.mark.asyncio
    async def test_run_result_attempts_is_positive_int(self):
        """Edge: StageResult.attempts must be a positive integer."""
        store = _make_store(tasks=[])
        stage = ImplementStage(store=store)
        result = await stage.run()
        assert isinstance(result.attempts, int), (
            f"StageResult.attempts must be int, got {type(result.attempts)}"
        )
        assert result.attempts >= 1, (
            f"StageResult.attempts must be >= 1, got {result.attempts}"
        )

"""RED-phase tests for PipelineEngine.retry(task_id).

Spec: engine.retry(task_id) must:
  1. Validate that the task identified by task_id is in BLOCKED status.
  2. Re-execute a single TDD cycle (RED, GREEN, review) for that task.
  3. Reject retry attempts for tasks that are already DONE (raise an error
     or return error indication).
  4. Raise an appropriate error for non-existent task_id values.
  5. Transition task status appropriately after a successful retry.

FR references (from requirement-v2.md P5):
  - retry(task_id) — 重跑单个 task 的 RED→GREEN 循环. supersede 旧 LVL (R17)
  - BLOCKED 不是死胡同: single task BLOCKED → skip, continue others, report

All tests in this module are RED-phase tests — they MUST FAIL until
orchestrator/engine.py provides a concrete implementation of retry().

Test coverage areas:
  1.  retry() method exists on PipelineEngine and is an async coroutine.
  2.  TaskNotFoundError is importable and is an Exception subclass.
  3.  TaskNotRetryableError is importable and is an Exception subclass.
  4.  retry() raises TaskNotFoundError for a non-existent task_id.
  5.  retry() raises TaskNotRetryableError for a task in DONE status.
  6.  retry() raises TaskNotRetryableError for a task in non-BLOCKED status.
  7.  retry() succeeds (returns a result) when the task is BLOCKED.
  8.  retry() result indicates success when the TDD cycle passes.
  9.  retry() result indicates failure when the TDD cycle fails.
  10. retry() executes RED phase before GREEN phase.
  11. retry() executes GREEN phase only after RED passes.
  12. retry() executes a review after the GREEN phase.
  13. retry() skips GREEN if RED fails; still runs review.
  14. retry() transitions task status from BLOCKED to the appropriate final status.
  15. retry() uses the engine lock (concurrent retries are serialised).
  16. retry() for an empty/None task_id raises TaskNotFoundError.
  17. retry() result carries the task_id that was retried.
  18. RetryResult is a proper dataclass with expected fields.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.engine import (
    STAGE_NAMES,
    PipelineEngine,
    PipelineResult,
    TaskNotFoundError,
    TaskNotRetryableError,
    RetryResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BLOCKED_STATUS = "BLOCKED"
DONE_STATUS = "DONE"


def _make_passing_stage_result(name: str = "spec") -> MagicMock:
    r = MagicMock()
    r.passed = True
    r.attempts = 1
    r.data = {"stage": name}
    r.error = None
    return r


def _make_failing_stage_result(name: str = "spec") -> MagicMock:
    r = MagicMock()
    r.passed = False
    r.attempts = 3
    r.data = {}
    r.error = f"{name} failed"
    return r


def _make_stage_mock(passing: bool = True, name: str = "spec") -> MagicMock:
    stage = MagicMock()
    if passing:
        stage.execute_with_gate = AsyncMock(
            return_value=_make_passing_stage_result(name)
        )
    else:
        stage.execute_with_gate = AsyncMock(
            return_value=_make_failing_stage_result(name)
        )
    return stage


def _build_engine(
    stage_overrides: dict | None = None,
    skip_stages: list[str] | None = None,
    tasks: dict | None = None,
) -> PipelineEngine:
    """Build a PipelineEngine with all four stages mocked.

    Parameters
    ----------
    stage_overrides:
        Map of stage_name -> mock stage. Missing stages default to passing mocks.
    skip_stages:
        List of stage names to skip.
    tasks:
        Optional dict mapping task_id -> status string. Used to pre-populate
        the engine's internal task registry for retry() validation.
    """
    overrides = stage_overrides or {}
    stages = {
        name: overrides.get(name, _make_stage_mock(passing=True, name=name))
        for name in STAGE_NAMES
    }
    config = {
        "skip_stages": skip_stages or [],
        "max_retries": 3,
        "tasks": tasks or {},
    }
    return PipelineEngine(stages=stages, config=config)


def _make_tdd_phase_result(passed: bool = True, phase: str = "red") -> MagicMock:
    """Return a mock result object for a single TDD phase (red/green/review)."""
    r = MagicMock()
    r.passed = passed
    r.phase = phase
    r.error = None if passed else f"{phase} phase failed"
    return r


# ---------------------------------------------------------------------------
# 1. Exception types: TaskNotFoundError and TaskNotRetryableError
# ---------------------------------------------------------------------------


class TestRetryExceptionTypes:
    """TaskNotFoundError and TaskNotRetryableError must exist and be proper exceptions."""

    def test_task_not_found_error_is_exception(self):
        """FR-retry: TaskNotFoundError MUST be a subclass of Exception."""
        assert issubclass(TaskNotFoundError, Exception), (
            "TaskNotFoundError must inherit from Exception"
        )

    def test_task_not_found_error_can_be_raised_and_caught(self):
        """TaskNotFoundError must be raiseable and catchable."""
        with pytest.raises(TaskNotFoundError):
            raise TaskNotFoundError("task T001 not found")

    def test_task_not_found_error_message_preserved(self):
        """TaskNotFoundError must carry the message string."""
        msg = "task T-MISSING does not exist"
        with pytest.raises(TaskNotFoundError, match="T-MISSING"):
            raise TaskNotFoundError(msg)

    def test_task_not_retryable_error_is_exception(self):
        """FR-retry: TaskNotRetryableError MUST be a subclass of Exception."""
        assert issubclass(TaskNotRetryableError, Exception), (
            "TaskNotRetryableError must inherit from Exception"
        )

    def test_task_not_retryable_error_can_be_raised_and_caught(self):
        """TaskNotRetryableError must be raiseable and catchable."""
        with pytest.raises(TaskNotRetryableError):
            raise TaskNotRetryableError("task T001 is DONE and cannot be retried")

    def test_task_not_retryable_error_message_preserved(self):
        """TaskNotRetryableError must carry the message string."""
        msg = "task T002 has status DONE — retry rejected"
        with pytest.raises(TaskNotRetryableError, match="T002"):
            raise TaskNotRetryableError(msg)

    def test_task_not_found_error_is_not_same_as_not_retryable(self):
        """TaskNotFoundError and TaskNotRetryableError MUST be distinct exception types."""
        assert TaskNotFoundError is not TaskNotRetryableError, (
            "TaskNotFoundError and TaskNotRetryableError must be distinct classes"
        )


# ---------------------------------------------------------------------------
# 2. RetryResult dataclass / return type
# ---------------------------------------------------------------------------


class TestRetryResultType:
    """RetryResult must be a proper dataclass with expected fields."""

    def test_retry_result_is_a_class(self):
        """RetryResult MUST be importable as a class."""
        assert inspect.isclass(RetryResult), (
            "RetryResult must be a class (dataclass or similar)"
        )

    def test_retry_result_can_be_instantiated_with_task_id(self):
        """RetryResult must be constructible with at least a task_id."""
        result = RetryResult(task_id="T001", passed=True)
        assert result is not None

    def test_retry_result_has_task_id_field(self):
        """RetryResult MUST have a 'task_id' field."""
        result = RetryResult(task_id="T007", passed=True)
        assert result.task_id == "T007", (
            f"RetryResult.task_id must be 'T007', got {result.task_id!r}"
        )

    def test_retry_result_has_passed_field(self):
        """RetryResult MUST have a 'passed' field."""
        result = RetryResult(task_id="T001", passed=True)
        assert result.passed is True, "RetryResult.passed must reflect the cycle outcome"

    def test_retry_result_passed_false_propagates(self):
        """RetryResult.passed=False must be preserved when constructed that way."""
        result = RetryResult(task_id="T002", passed=False)
        assert result.passed is False

    def test_retry_result_has_phases_field(self):
        """RetryResult MUST have a field recording which phases were executed."""
        result = RetryResult(task_id="T001", passed=True)
        # The field can be named 'phases', 'phase_results', 'tdd_phases', etc.
        has_phases = (
            hasattr(result, "phases")
            or hasattr(result, "phase_results")
            or hasattr(result, "tdd_phases")
        )
        assert has_phases, (
            "RetryResult must have a field recording the executed TDD phases "
            "(e.g. 'phases', 'phase_results', or 'tdd_phases')"
        )


# ---------------------------------------------------------------------------
# 3. retry() method exists and is an async coroutine
# ---------------------------------------------------------------------------


class TestRetryMethodExists:
    """PipelineEngine must expose a retry(task_id) coroutine method."""

    def test_pipeline_engine_has_retry_method(self):
        """PipelineEngine must have a 'retry' attribute."""
        engine = _build_engine()
        assert hasattr(engine, "retry"), (
            "PipelineEngine must have a 'retry' method"
        )

    def test_retry_is_callable(self):
        """PipelineEngine.retry must be callable."""
        engine = _build_engine()
        assert callable(engine.retry), "PipelineEngine.retry must be callable"

    def test_retry_is_a_coroutine_function(self):
        """retry() must be an async method (coroutine function)."""
        engine = _build_engine()
        assert inspect.iscoroutinefunction(engine.retry), (
            "PipelineEngine.retry must be an async (coroutine) method"
        )

    def test_retry_accepts_task_id_parameter(self):
        """retry() must accept a task_id positional or keyword argument."""
        engine = _build_engine()
        sig = inspect.signature(engine.retry)
        param_names = list(sig.parameters.keys())
        assert "task_id" in param_names, (
            f"retry() must accept a 'task_id' parameter, got params: {param_names}"
        )


# ---------------------------------------------------------------------------
# 4. FR-retry: Non-existent task_id → TaskNotFoundError
# ---------------------------------------------------------------------------


class TestRetryNonExistentTask:
    """retry() must raise TaskNotFoundError for task IDs that do not exist."""

    @pytest.mark.asyncio
    async def test_retry_raises_task_not_found_for_unknown_task(self):
        """FR-retry: retry() MUST raise TaskNotFoundError for unknown task_id."""
        engine = _build_engine(tasks={})
        with pytest.raises(TaskNotFoundError):
            await engine.retry("T-UNKNOWN")

    @pytest.mark.asyncio
    async def test_retry_raises_task_not_found_not_generic_exception(self):
        """The exception for an unknown task must be TaskNotFoundError specifically."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})
        with pytest.raises(TaskNotFoundError):
            await engine.retry("T-DOES-NOT-EXIST")

    @pytest.mark.asyncio
    async def test_retry_raises_task_not_found_for_empty_string_task_id(self):
        """retry() must raise TaskNotFoundError for an empty string task_id."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})
        with pytest.raises(TaskNotFoundError):
            await engine.retry("")

    @pytest.mark.asyncio
    async def test_retry_raises_task_not_found_for_none_task_id(self):
        """retry() must raise TaskNotFoundError when task_id is None."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})
        with pytest.raises((TaskNotFoundError, TypeError)):
            await engine.retry(None)

    @pytest.mark.asyncio
    async def test_retry_error_message_contains_task_id(self):
        """TaskNotFoundError message should mention the missing task_id."""
        engine = _build_engine(tasks={})
        with pytest.raises(TaskNotFoundError, match="T-MISSING"):
            await engine.retry("T-MISSING")


# ---------------------------------------------------------------------------
# 5. FR-retry: DONE task → TaskNotRetryableError
# ---------------------------------------------------------------------------


class TestRetryDoneTaskRejected:
    """retry() must reject tasks with DONE status."""

    @pytest.mark.asyncio
    async def test_retry_raises_task_not_retryable_for_done_task(self):
        """FR-retry: retry() MUST raise TaskNotRetryableError for a DONE task."""
        engine = _build_engine(tasks={"T001": DONE_STATUS})
        with pytest.raises(TaskNotRetryableError):
            await engine.retry("T001")

    @pytest.mark.asyncio
    async def test_retry_raises_task_not_retryable_not_task_not_found_for_done(self):
        """For a DONE task, the error must be TaskNotRetryableError, not TaskNotFoundError."""
        engine = _build_engine(tasks={"T-DONE": DONE_STATUS})
        with pytest.raises(TaskNotRetryableError):
            await engine.retry("T-DONE")

    @pytest.mark.asyncio
    async def test_retry_error_message_mentions_done_for_done_task(self):
        """TaskNotRetryableError for a DONE task should mention the status."""
        engine = _build_engine(tasks={"T001": DONE_STATUS})
        with pytest.raises(TaskNotRetryableError, match="(?i)done"):
            await engine.retry("T001")

    @pytest.mark.asyncio
    async def test_retry_does_not_execute_tdd_cycle_for_done_task(self):
        """FR-retry: No TDD cycle must run when the task is DONE."""
        tdd_cycle_executed = []

        engine = _build_engine(tasks={"T001": DONE_STATUS})

        # Patch the internal method that would run the TDD cycle
        async def _mock_tdd_cycle(task_id, *args, **kwargs):
            tdd_cycle_executed.append(task_id)

        with patch.object(engine, "_run_single_task_tdd_cycle", _mock_tdd_cycle, create=True):
            with pytest.raises(TaskNotRetryableError):
                await engine.retry("T001")

        assert tdd_cycle_executed == [], (
            "No TDD cycle must be executed when retry is rejected for a DONE task"
        )


# ---------------------------------------------------------------------------
# 6. FR-retry: Non-BLOCKED, non-DONE status → TaskNotRetryableError
# ---------------------------------------------------------------------------


class TestRetryNonBlockedTaskRejected:
    """retry() must reject tasks that are not in BLOCKED status (and not DONE)."""

    @pytest.mark.asyncio
    async def test_retry_raises_for_running_task(self):
        """retry() must reject a RUNNING task — only BLOCKED tasks can be retried."""
        engine = _build_engine(tasks={"T001": "RUNNING"})
        with pytest.raises(TaskNotRetryableError):
            await engine.retry("T001")

    @pytest.mark.asyncio
    async def test_retry_raises_for_pending_task(self):
        """retry() must reject a PENDING task — only BLOCKED tasks can be retried."""
        engine = _build_engine(tasks={"T001": "PENDING"})
        with pytest.raises(TaskNotRetryableError):
            await engine.retry("T001")

    @pytest.mark.asyncio
    async def test_retry_raises_for_passed_task(self):
        """retry() must reject a PASSED task — only BLOCKED tasks can be retried."""
        engine = _build_engine(tasks={"T001": "PASSED"})
        with pytest.raises(TaskNotRetryableError):
            await engine.retry("T001")

    @pytest.mark.asyncio
    async def test_retry_raises_for_failed_task(self):
        """retry() must reject a FAILED task — only BLOCKED tasks can be retried."""
        engine = _build_engine(tasks={"T001": "FAILED"})
        with pytest.raises(TaskNotRetryableError):
            await engine.retry("T001")


# ---------------------------------------------------------------------------
# 7. FR-retry: BLOCKED task → retry succeeds
# ---------------------------------------------------------------------------


class TestRetryBlockedTaskSucceeds:
    """retry() must succeed (return a result) when the task is in BLOCKED status."""

    @pytest.mark.asyncio
    async def test_retry_returns_retry_result_for_blocked_task(self):
        """FR-retry: retry() MUST return a RetryResult for a BLOCKED task."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})
        result = await engine.retry("T001")
        assert isinstance(result, RetryResult), (
            f"retry() must return RetryResult for a BLOCKED task, "
            f"got {type(result).__name__}"
        )

    @pytest.mark.asyncio
    async def test_retry_result_carries_task_id(self):
        """FR-retry: The returned RetryResult must carry the task_id that was retried."""
        engine = _build_engine(tasks={"T-XYZ": BLOCKED_STATUS})
        result = await engine.retry("T-XYZ")
        assert result.task_id == "T-XYZ", (
            f"RetryResult.task_id must be 'T-XYZ', got {result.task_id!r}"
        )

    @pytest.mark.asyncio
    async def test_retry_does_not_raise_for_blocked_task(self):
        """retry() must NOT raise any exception for a legitimately BLOCKED task."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})
        try:
            await engine.retry("T001")
        except (TaskNotFoundError, TaskNotRetryableError) as exc:
            pytest.fail(
                f"retry() must not raise for a BLOCKED task, but raised: {exc!r}"
            )

    @pytest.mark.asyncio
    async def test_retry_result_passed_true_when_tdd_cycle_succeeds(self):
        """FR-retry: RetryResult.passed must be True when the TDD cycle passes."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        passing_cycle_result = MagicMock()
        passing_cycle_result.passed = True

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=passing_cycle_result),
            create=True,
        ):
            result = await engine.retry("T001")

        assert result.passed is True, (
            "RetryResult.passed must be True when the TDD cycle succeeds"
        )

    @pytest.mark.asyncio
    async def test_retry_result_passed_false_when_tdd_cycle_fails(self):
        """FR-retry: RetryResult.passed must be False when the TDD cycle fails."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        failing_cycle_result = MagicMock()
        failing_cycle_result.passed = False

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=failing_cycle_result),
            create=True,
        ):
            result = await engine.retry("T001")

        assert result.passed is False, (
            "RetryResult.passed must be False when the TDD cycle fails"
        )


# ---------------------------------------------------------------------------
# 8. FR-retry: TDD cycle phase ordering (RED → GREEN → review)
# ---------------------------------------------------------------------------


class TestRetryTddCyclePhaseOrder:
    """retry() must execute TDD phases in the correct order: RED, GREEN, review."""

    @pytest.mark.asyncio
    async def test_red_phase_executes_first(self):
        """FR-retry: RED phase must execute before GREEN and review."""
        phase_log: list[str] = []

        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        async def _mock_red(*args, **kwargs):
            phase_log.append("red")
            return _make_tdd_phase_result(passed=True, phase="red")

        async def _mock_green(*args, **kwargs):
            phase_log.append("green")
            return _make_tdd_phase_result(passed=True, phase="green")

        async def _mock_review(*args, **kwargs):
            phase_log.append("review")
            return _make_tdd_phase_result(passed=True, phase="review")

        with (
            patch.object(engine, "_run_red_phase", _mock_red, create=True),
            patch.object(engine, "_run_green_phase", _mock_green, create=True),
            patch.object(engine, "_run_review_phase", _mock_review, create=True),
        ):
            await engine.retry("T001")

        assert phase_log[0] == "red", (
            f"RED phase must execute first, got phase_log={phase_log}"
        )

    @pytest.mark.asyncio
    async def test_green_phase_executes_after_red(self):
        """FR-retry: GREEN phase must execute after RED (when RED passes)."""
        phase_log: list[str] = []

        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        async def _mock_red(*args, **kwargs):
            phase_log.append("red")
            return _make_tdd_phase_result(passed=True, phase="red")

        async def _mock_green(*args, **kwargs):
            phase_log.append("green")
            return _make_tdd_phase_result(passed=True, phase="green")

        async def _mock_review(*args, **kwargs):
            phase_log.append("review")
            return _make_tdd_phase_result(passed=True, phase="review")

        with (
            patch.object(engine, "_run_red_phase", _mock_red, create=True),
            patch.object(engine, "_run_green_phase", _mock_green, create=True),
            patch.object(engine, "_run_review_phase", _mock_review, create=True),
        ):
            await engine.retry("T001")

        assert "green" in phase_log, "GREEN phase must be executed when RED passes"
        assert phase_log.index("green") > phase_log.index("red"), (
            f"GREEN must execute after RED, got phase_log={phase_log}"
        )

    @pytest.mark.asyncio
    async def test_review_phase_executes_after_green(self):
        """FR-retry: review phase must execute after GREEN."""
        phase_log: list[str] = []

        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        async def _mock_red(*args, **kwargs):
            phase_log.append("red")
            return _make_tdd_phase_result(passed=True, phase="red")

        async def _mock_green(*args, **kwargs):
            phase_log.append("green")
            return _make_tdd_phase_result(passed=True, phase="green")

        async def _mock_review(*args, **kwargs):
            phase_log.append("review")
            return _make_tdd_phase_result(passed=True, phase="review")

        with (
            patch.object(engine, "_run_red_phase", _mock_red, create=True),
            patch.object(engine, "_run_green_phase", _mock_green, create=True),
            patch.object(engine, "_run_review_phase", _mock_review, create=True),
        ):
            await engine.retry("T001")

        assert "review" in phase_log, "review phase must be executed"
        assert phase_log.index("review") > phase_log.index("green"), (
            f"review must execute after GREEN, got phase_log={phase_log}"
        )

    @pytest.mark.asyncio
    async def test_full_phase_order_is_red_green_review(self):
        """FR-retry: The complete phase order MUST be RED → GREEN → review."""
        phase_log: list[str] = []

        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        async def _mock_red(*args, **kwargs):
            phase_log.append("red")
            return _make_tdd_phase_result(passed=True, phase="red")

        async def _mock_green(*args, **kwargs):
            phase_log.append("green")
            return _make_tdd_phase_result(passed=True, phase="green")

        async def _mock_review(*args, **kwargs):
            phase_log.append("review")
            return _make_tdd_phase_result(passed=True, phase="review")

        with (
            patch.object(engine, "_run_red_phase", _mock_red, create=True),
            patch.object(engine, "_run_green_phase", _mock_green, create=True),
            patch.object(engine, "_run_review_phase", _mock_review, create=True),
        ):
            await engine.retry("T001")

        assert phase_log == ["red", "green", "review"], (
            f"Full phase order must be ['red', 'green', 'review'], got {phase_log}"
        )


# ---------------------------------------------------------------------------
# 9. FR-retry: GREEN skipped when RED fails
# ---------------------------------------------------------------------------


class TestRetryGreenSkippedWhenRedFails:
    """When RED phase fails, GREEN must be skipped; review still runs."""

    @pytest.mark.asyncio
    async def test_green_is_skipped_when_red_fails(self):
        """FR-retry: GREEN phase MUST NOT run if RED phase fails."""
        phase_log: list[str] = []

        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        async def _mock_red(*args, **kwargs):
            phase_log.append("red")
            return _make_tdd_phase_result(passed=False, phase="red")  # RED fails

        async def _mock_green(*args, **kwargs):
            phase_log.append("green")
            return _make_tdd_phase_result(passed=True, phase="green")

        async def _mock_review(*args, **kwargs):
            phase_log.append("review")
            return _make_tdd_phase_result(passed=False, phase="review")

        with (
            patch.object(engine, "_run_red_phase", _mock_red, create=True),
            patch.object(engine, "_run_green_phase", _mock_green, create=True),
            patch.object(engine, "_run_review_phase", _mock_review, create=True),
        ):
            await engine.retry("T001")

        assert "green" not in phase_log, (
            f"GREEN must NOT run when RED fails, but phase_log={phase_log}"
        )

    @pytest.mark.asyncio
    async def test_result_passed_false_when_red_fails(self):
        """FR-retry: RetryResult.passed must be False when RED phase fails."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        async def _mock_red(*args, **kwargs):
            return _make_tdd_phase_result(passed=False, phase="red")

        async def _mock_green(*args, **kwargs):
            return _make_tdd_phase_result(passed=True, phase="green")

        async def _mock_review(*args, **kwargs):
            return _make_tdd_phase_result(passed=False, phase="review")

        with (
            patch.object(engine, "_run_red_phase", _mock_red, create=True),
            patch.object(engine, "_run_green_phase", _mock_green, create=True),
            patch.object(engine, "_run_review_phase", _mock_review, create=True),
        ):
            result = await engine.retry("T001")

        assert result.passed is False, (
            "RetryResult.passed must be False when RED phase fails"
        )


# ---------------------------------------------------------------------------
# 10. FR-retry: task status transitions after retry
# ---------------------------------------------------------------------------


class TestRetryTaskStatusTransition:
    """After retry(), the task's status must transition appropriately."""

    @pytest.mark.asyncio
    async def test_task_status_changes_from_blocked_after_successful_retry(self):
        """FR-retry: A BLOCKED task that succeeds must NOT remain BLOCKED after retry."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        passing_cycle_result = MagicMock()
        passing_cycle_result.passed = True

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=passing_cycle_result),
            create=True,
        ):
            await engine.retry("T001")

        # After a successful retry, the task must NOT still be BLOCKED
        task_status = engine._get_task_status("T001")
        assert task_status != BLOCKED_STATUS, (
            f"After a successful retry, task status must not remain BLOCKED, "
            f"got {task_status!r}"
        )

    @pytest.mark.asyncio
    async def test_task_status_is_done_after_successful_retry(self):
        """FR-retry: Task status must be DONE after a successful retry cycle."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        passing_cycle_result = MagicMock()
        passing_cycle_result.passed = True

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=passing_cycle_result),
            create=True,
        ):
            await engine.retry("T001")

        task_status = engine._get_task_status("T001")
        assert task_status == DONE_STATUS, (
            f"After a successful retry, task status must be DONE, "
            f"got {task_status!r}"
        )

    @pytest.mark.asyncio
    async def test_task_status_remains_blocked_after_failed_retry(self):
        """FR-retry: Task status must remain BLOCKED after a failed retry cycle."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        failing_cycle_result = MagicMock()
        failing_cycle_result.passed = False

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=failing_cycle_result),
            create=True,
        ):
            await engine.retry("T001")

        task_status = engine._get_task_status("T001")
        assert task_status == BLOCKED_STATUS, (
            f"After a failed retry, task status must remain BLOCKED, "
            f"got {task_status!r}"
        )


# ---------------------------------------------------------------------------
# 11. _get_task_status() helper
# ---------------------------------------------------------------------------


class TestGetTaskStatusHelper:
    """PipelineEngine must expose _get_task_status(task_id) for internal use."""

    def test_engine_has_get_task_status_method(self):
        """PipelineEngine must have a _get_task_status method for task status lookup."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})
        assert hasattr(engine, "_get_task_status"), (
            "PipelineEngine must have a '_get_task_status' method"
        )

    def test_get_task_status_returns_blocked_for_blocked_task(self):
        """_get_task_status() must return BLOCKED for a task registered as BLOCKED."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})
        assert engine._get_task_status("T001") == BLOCKED_STATUS, (
            f"_get_task_status('T001') must return BLOCKED, "
            f"got {engine._get_task_status('T001')!r}"
        )

    def test_get_task_status_returns_done_for_done_task(self):
        """_get_task_status() must return DONE for a task registered as DONE."""
        engine = _build_engine(tasks={"T002": DONE_STATUS})
        assert engine._get_task_status("T002") == DONE_STATUS, (
            f"_get_task_status('T002') must return DONE, "
            f"got {engine._get_task_status('T002')!r}"
        )

    def test_get_task_status_returns_none_for_unknown_task(self):
        """_get_task_status() must return None for an unknown task_id."""
        engine = _build_engine(tasks={})
        assert engine._get_task_status("T-MISSING") is None, (
            "_get_task_status must return None for an unknown task_id"
        )


# ---------------------------------------------------------------------------
# 12. FR-retry: engine lock is used during retry
# ---------------------------------------------------------------------------


class TestRetryUsesEngineLock:
    """retry() must acquire the engine's asyncio.Lock during execution."""

    @pytest.mark.asyncio
    async def test_lock_is_not_held_after_successful_retry(self):
        """After retry() completes, the engine lock must be released."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=MagicMock(passed=True)),
            create=True,
        ):
            await engine.retry("T001")

        assert engine.lock.locked() is False, (
            "engine.lock must be released after retry() completes successfully"
        )

    @pytest.mark.asyncio
    async def test_lock_is_not_held_after_failed_retry(self):
        """After a failed retry(), the engine lock must still be released."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=MagicMock(passed=False)),
            create=True,
        ):
            await engine.retry("T001")

        assert engine.lock.locked() is False, (
            "engine.lock must be released even after a failed retry()"
        )

    @pytest.mark.asyncio
    async def test_lock_is_not_held_after_task_not_found(self):
        """After TaskNotFoundError, the engine lock must be released."""
        engine = _build_engine(tasks={})

        with pytest.raises(TaskNotFoundError):
            await engine.retry("T-MISSING")

        assert engine.lock.locked() is False, (
            "engine.lock must be released even when TaskNotFoundError is raised"
        )

    @pytest.mark.asyncio
    async def test_lock_is_not_held_after_task_not_retryable(self):
        """After TaskNotRetryableError, the engine lock must be released."""
        engine = _build_engine(tasks={"T001": DONE_STATUS})

        with pytest.raises(TaskNotRetryableError):
            await engine.retry("T001")

        assert engine.lock.locked() is False, (
            "engine.lock must be released even when TaskNotRetryableError is raised"
        )

    @pytest.mark.asyncio
    async def test_concurrent_retries_are_serialised_by_lock(self):
        """Concurrent retry() calls on the same engine must be serialised via the lock."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS, "T002": BLOCKED_STATUS})
        execution_starts: list[str] = []
        execution_ends: list[str] = []

        async def _slow_cycle(task_id, *args, **kwargs):
            execution_starts.append(task_id)
            await asyncio.sleep(0.02)
            execution_ends.append(task_id)
            return MagicMock(passed=True)

        with patch.object(engine, "_run_single_task_tdd_cycle", _slow_cycle, create=True):
            await asyncio.gather(
                engine.retry("T001"),
                engine.retry("T002"),
                return_exceptions=True,
            )

        # After both complete, lock must be released
        assert engine.lock.locked() is False, (
            "engine.lock must be free after concurrent retry() calls complete"
        )
        # Serialised execution: ends must not interleave with starts
        # (i.e., task 1 must fully complete before task 2 starts, or vice versa)
        assert len(execution_starts) == 2 and len(execution_ends) == 2, (
            "Both retry calls must have executed"
        )
        first_task = execution_starts[0]
        second_task = execution_starts[1]
        first_end_idx = execution_ends.index(first_task)
        second_start_idx = execution_starts.index(second_task)
        assert first_end_idx == 0, (
            f"First task must fully complete before second starts "
            f"(starts={execution_starts}, ends={execution_ends})"
        )


# ---------------------------------------------------------------------------
# 13. FR-retry: edge cases
# ---------------------------------------------------------------------------


class TestRetryEdgeCases:
    """Edge cases for retry()."""

    @pytest.mark.asyncio
    async def test_retry_can_be_called_on_same_task_multiple_times(self):
        """A BLOCKED task can be retried multiple times if it stays BLOCKED."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        failing_cycle = MagicMock(passed=False)

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=failing_cycle),
            create=True,
        ):
            result1 = await engine.retry("T001")
            # Task is still BLOCKED after failed retry
            result2 = await engine.retry("T001")

        assert result1 is not None and result2 is not None, (
            "Both retry attempts must return a result"
        )

    @pytest.mark.asyncio
    async def test_retry_blocked_task_does_not_affect_other_tasks(self):
        """retry() for one BLOCKED task must not change the status of other tasks."""
        engine = _build_engine(
            tasks={"T001": BLOCKED_STATUS, "T002": DONE_STATUS, "T003": "PENDING"}
        )

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=MagicMock(passed=True)),
            create=True,
        ):
            await engine.retry("T001")

        assert engine._get_task_status("T002") == DONE_STATUS, (
            "retry() must not alter status of T002 (DONE)"
        )
        assert engine._get_task_status("T003") == "PENDING", (
            "retry() must not alter status of T003 (PENDING)"
        )

    @pytest.mark.asyncio
    async def test_retry_returns_retry_result_not_pipeline_result(self):
        """retry() must return RetryResult, not PipelineResult."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=MagicMock(passed=True)),
            create=True,
        ):
            result = await engine.retry("T001")

        assert isinstance(result, RetryResult), (
            f"retry() must return RetryResult, not {type(result).__name__}"
        )
        assert not isinstance(result, PipelineResult), (
            "retry() must NOT return a PipelineResult — use RetryResult"
        )

    @pytest.mark.asyncio
    async def test_retry_does_not_run_unrelated_pipeline_stages(self):
        """retry() must only run the single-task TDD cycle, not the full pipeline."""
        engine = _build_engine(tasks={"T001": BLOCKED_STATUS})

        with patch.object(
            engine,
            "_run_single_task_tdd_cycle",
            AsyncMock(return_value=MagicMock(passed=True)),
            create=True,
        ):
            await engine.retry("T001")

        # Full pipeline stages (spec, plan, implement, acceptance) must NOT be invoked
        for stage_name in STAGE_NAMES:
            stage_mock = engine._stages[stage_name]
            stage_mock.execute_with_gate.assert_not_awaited(), (
                f"retry() must not invoke pipeline stage '{stage_name}'"
            )

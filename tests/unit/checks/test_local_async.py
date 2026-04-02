"""Unit tests for async LocalCheckStrategy — thread delegation wrapper.

T015 [FR-015] [FR-042] [FR-043]
Implement async thread delegation for tests_must_fail and tests_must_pass,
returning structured CheckResult objects; enforce common.py size below 150 lines.

FR-015: tests_must_fail and tests_must_pass MUST be async coroutines that
        delegate subprocess execution to a thread pool (non-blocking event loop).
FR-042: CheckResult MUST contain structured fields: success (bool), output (str),
        return_code (int), duration (float).
FR-043: common.py MUST remain under 150 lines.

Test areas:
  1.  tests_must_fail is an async coroutine method (inspect.iscoroutinefunction).
  2.  tests_must_pass is an async coroutine method (inspect.iscoroutinefunction).
  3.  CheckResult has required fields: success, output, return_code, duration.
  4.  CheckResult.success is bool.
  5.  CheckResult.return_code is int.
  6.  CheckResult.duration is float.
  7.  tests_must_fail returns a CheckResult (not bool) when awaited.
  8.  tests_must_pass returns a CheckResult (not bool) when awaited.
  9.  tests_must_fail returns CheckResult with success=True when tests fail (non-zero exit).
  10. tests_must_fail returns CheckResult with success=False when tests pass (zero exit).
  11. tests_must_pass returns CheckResult with success=True when tests pass (zero exit).
  12. tests_must_pass returns CheckResult with success=False when tests fail (non-zero exit).
  13. CheckResult.return_code reflects the subprocess exit code.
  14. CheckResult.duration is a non-negative float.
  15. Thread delegation: run_in_executor or asyncio.to_thread is used (not blocking call).
  16. tests_must_fail delegates to a thread pool, not direct blocking subprocess call.
  17. tests_must_pass delegates to a thread pool, not direct blocking subprocess call.
  18. FileNotFoundError returns CheckResult with success=False and meaningful output.
  19. TimeoutExpired returns CheckResult with success=False and timeout info in output.
  20. CheckResult.output contains subprocess stdout/stderr content.
  21. CheckResult fields are accessible as attributes (not dict).
  22. common.py module is under 150 lines (enforced by test).
  23. CheckResult is importable from orchestrator.checks.local.
  24. Duration is measured and > 0 for real subprocess calls.
  25. tests_must_pass with passing command yields success=True and return_code=0.

All tests MUST FAIL until orchestrator/checks/local.py is updated with async
coroutine methods returning CheckResult with success/return_code/duration fields.
"""

from __future__ import annotations

import asyncio
import inspect
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.checks.local import CheckResult, LocalCheckStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(
    command: str = "pytest tests/",
    max_retries: int = 0,
    backoff_base: float = 0.0,
) -> LocalCheckStrategy:
    """Construct a LocalCheckStrategy with test-friendly defaults."""
    return LocalCheckStrategy(
        command=command,
        max_retries=max_retries,
        backoff_base=backoff_base,
    )


def _make_completed_process(returncode: int, stdout: str = "", stderr: str = ""):
    """Return a fake CompletedProcess-like object."""
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ===========================================================================
# 1. Async coroutine signatures
# ===========================================================================


class TestAsyncCoroutineSignatures:
    """FR-015: tests_must_fail and tests_must_pass MUST be async coroutines."""

    def test_tests_must_fail_is_async_coroutine(self):
        """FR-015: tests_must_fail must be an async coroutine function."""
        assert inspect.iscoroutinefunction(LocalCheckStrategy.tests_must_fail), (
            "tests_must_fail must be declared as 'async def', "
            "got a regular (sync) method instead"
        )

    def test_tests_must_pass_is_async_coroutine(self):
        """FR-015: tests_must_pass must be an async coroutine function."""
        assert inspect.iscoroutinefunction(LocalCheckStrategy.tests_must_pass), (
            "tests_must_pass must be declared as 'async def', "
            "got a regular (sync) method instead"
        )

    def test_tests_must_fail_returns_coroutine_when_called(self):
        """Calling tests_must_fail on an instance must return a coroutine object."""
        strategy = _make_strategy()
        coro = strategy.tests_must_fail(task_id="T015", command="pytest tests/")
        is_coro = inspect.iscoroutine(coro)
        # Must close to avoid ResourceWarning
        coro.close()
        assert is_coro, (
            "tests_must_fail() must return a coroutine when called (not awaited)"
        )

    def test_tests_must_pass_returns_coroutine_when_called(self):
        """Calling tests_must_pass on an instance must return a coroutine object."""
        strategy = _make_strategy()
        coro = strategy.tests_must_pass(task_id="T015", command="pytest tests/")
        is_coro = inspect.iscoroutine(coro)
        coro.close()
        assert is_coro, (
            "tests_must_pass() must return a coroutine when called (not awaited)"
        )


# ===========================================================================
# 2. CheckResult structured fields
# ===========================================================================


class TestCheckResultStructuredFields:
    """FR-042: CheckResult MUST expose success, output, return_code, duration."""

    def test_check_result_has_success_field(self):
        """CheckResult must have a 'success' attribute."""
        result = CheckResult(success=True, output="ok", return_code=0, duration=0.1)
        assert result.success is True

    def test_check_result_has_output_field(self):
        """CheckResult must have an 'output' attribute."""
        result = CheckResult(success=True, output="1 passed", return_code=0, duration=0.1)
        assert result.output == "1 passed"

    def test_check_result_has_return_code_field(self):
        """CheckResult must have a 'return_code' attribute."""
        result = CheckResult(success=False, output="1 failed", return_code=1, duration=0.2)
        assert result.return_code == 1

    def test_check_result_has_duration_field(self):
        """CheckResult must have a 'duration' attribute."""
        result = CheckResult(success=True, output="", return_code=0, duration=1.23)
        assert result.duration == pytest.approx(1.23)

    def test_check_result_success_is_bool_true(self):
        """CheckResult.success must be bool True when tests passed."""
        result = CheckResult(success=True, output="", return_code=0, duration=0.0)
        assert type(result.success) is bool
        assert result.success is True

    def test_check_result_success_is_bool_false(self):
        """CheckResult.success must be bool False when tests failed."""
        result = CheckResult(success=False, output="", return_code=1, duration=0.0)
        assert type(result.success) is bool
        assert result.success is False

    def test_check_result_return_code_is_int(self):
        """CheckResult.return_code must be an int."""
        result = CheckResult(success=False, output="", return_code=1, duration=0.0)
        assert isinstance(result.return_code, int), (
            f"return_code must be int, got {type(result.return_code)}"
        )

    def test_check_result_duration_is_float(self):
        """CheckResult.duration must be a float."""
        result = CheckResult(success=True, output="", return_code=0, duration=0.5)
        assert isinstance(result.duration, (int, float)), (
            f"duration must be numeric (float), got {type(result.duration)}"
        )

    def test_check_result_return_code_zero_on_success(self):
        """CheckResult.return_code must be 0 when tests passed."""
        result = CheckResult(success=True, output="passed", return_code=0, duration=0.1)
        assert result.return_code == 0

    def test_check_result_return_code_nonzero_on_failure(self):
        """CheckResult.return_code must be non-zero when tests failed."""
        result = CheckResult(success=False, output="failed", return_code=2, duration=0.1)
        assert result.return_code != 0

    def test_check_result_fields_accessible_as_attributes(self):
        """All CheckResult fields must be accessible as object attributes (not dict)."""
        result = CheckResult(success=True, output="done", return_code=0, duration=0.3)
        # Must not raise AttributeError
        _ = result.success
        _ = result.output
        _ = result.return_code
        _ = result.duration


# ===========================================================================
# 3. Return type: async methods must return CheckResult, not bool
# ===========================================================================


class TestAsyncMethodsReturnCheckResult:
    """FR-042: Awaited async methods must return CheckResult instances."""

    @pytest.mark.asyncio
    async def test_tests_must_fail_returns_check_result_on_nonzero_exit(self):
        """FR-042: Awaited tests_must_fail must return a CheckResult, not bool."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1, stderr="AssertionError")

        with patch("subprocess.run", return_value=failing_proc):
            result = await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert isinstance(result, CheckResult), (
            f"tests_must_fail must return CheckResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_returns_check_result_on_zero_exit(self):
        """FR-042: Awaited tests_must_pass must return a CheckResult, not bool."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0, stdout="1 passed")

        with patch("subprocess.run", return_value=passing_proc):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert isinstance(result, CheckResult), (
            f"tests_must_pass must return CheckResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_tests_must_fail_result_not_bool(self):
        """tests_must_fail must return CheckResult, confirmed by type check."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc):
            result = await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert not isinstance(result, bool), (
            "tests_must_fail must return CheckResult, not bool"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_result_not_bool(self):
        """tests_must_pass must return CheckResult, confirmed by type check."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0)

        with patch("subprocess.run", return_value=passing_proc):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert not isinstance(result, bool), (
            "tests_must_pass must return CheckResult, not bool"
        )


# ===========================================================================
# 4. tests_must_fail async semantics
# ===========================================================================


class TestTestsMustFailAsyncSemantics:
    """FR-015: tests_must_fail async coroutine must return correct CheckResult."""

    @pytest.mark.asyncio
    async def test_tests_must_fail_success_true_when_tests_fail(self):
        """FR-015: tests_must_fail.success must be True when subprocess exits non-zero.

        In the RED phase, a non-zero exit confirms tests are correctly failing.
        """
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1, stderr="AssertionError")

        with patch("subprocess.run", return_value=failing_proc):
            result = await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert result.success is True, (
            "tests_must_fail.success must be True when tests fail (non-zero exit)"
        )

    @pytest.mark.asyncio
    async def test_tests_must_fail_success_false_when_tests_pass(self):
        """FR-015: tests_must_fail.success must be False when subprocess exits 0.

        If tests pass when they should fail, RED phase is not confirmed.
        """
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0, stdout="1 passed")

        with patch("subprocess.run", return_value=passing_proc):
            result = await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert result.success is False, (
            "tests_must_fail.success must be False when tests unexpectedly pass"
        )

    @pytest.mark.asyncio
    async def test_tests_must_fail_return_code_reflects_exit_code(self):
        """tests_must_fail.return_code must reflect the actual subprocess exit code."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc):
            result = await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert result.return_code == 1, (
            f"return_code must be 1, got {result.return_code}"
        )

    @pytest.mark.asyncio
    async def test_tests_must_fail_output_contains_stderr(self):
        """tests_must_fail.output must contain subprocess output."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(
            returncode=1, stderr="FAILED test_foo.py::test_bar"
        )

        with patch("subprocess.run", return_value=failing_proc):
            result = await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert "FAILED" in result.output or "test_foo" in result.output, (
            f"output must contain subprocess stderr; got: {result.output!r}"
        )

    @pytest.mark.asyncio
    async def test_tests_must_fail_duration_is_non_negative(self):
        """tests_must_fail.duration must be >= 0."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc):
            result = await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert result.duration >= 0, (
            f"duration must be non-negative, got {result.duration}"
        )


# ===========================================================================
# 5. tests_must_pass async semantics
# ===========================================================================


class TestTestsMustPassAsyncSemantics:
    """FR-015: tests_must_pass async coroutine must return correct CheckResult."""

    @pytest.mark.asyncio
    async def test_tests_must_pass_success_true_when_tests_pass(self):
        """FR-015: tests_must_pass.success must be True when subprocess exits 0."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0, stdout="1 passed")

        with patch("subprocess.run", return_value=passing_proc):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert result.success is True, (
            "tests_must_pass.success must be True when tests pass (exit 0)"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_success_false_when_tests_fail(self):
        """FR-015: tests_must_pass.success must be False when tests keep failing."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1, stderr="1 failed")

        with patch("subprocess.run", return_value=failing_proc):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert result.success is False, (
            "tests_must_pass.success must be False when tests fail"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_return_code_zero_on_success(self):
        """tests_must_pass.return_code must be 0 when tests pass."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0)

        with patch("subprocess.run", return_value=passing_proc):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert result.return_code == 0, (
            f"return_code must be 0 on success, got {result.return_code}"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_return_code_nonzero_on_failure(self):
        """tests_must_pass.return_code must reflect non-zero exit on failure."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=2)

        with patch("subprocess.run", return_value=failing_proc):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert result.return_code == 2, (
            f"return_code must be 2, got {result.return_code}"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_output_contains_stdout(self):
        """tests_must_pass.output must contain subprocess stdout."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0, stdout="5 passed in 0.5s")

        with patch("subprocess.run", return_value=passing_proc):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert "5 passed" in result.output, (
            f"output must contain stdout; got: {result.output!r}"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_duration_is_non_negative(self):
        """tests_must_pass.duration must be >= 0."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0)

        with patch("subprocess.run", return_value=passing_proc):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert result.duration >= 0, (
            f"duration must be non-negative, got {result.duration}"
        )


# ===========================================================================
# 6. Thread delegation (non-blocking event loop)
# ===========================================================================


class TestThreadDelegation:
    """FR-015: Subprocess execution must be delegated to a thread, not blocking the loop."""

    @pytest.mark.asyncio
    async def test_tests_must_fail_uses_thread_delegation(self):
        """FR-015: tests_must_fail must delegate subprocess to run_in_executor or asyncio.to_thread."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        loop = asyncio.get_event_loop()
        executor_calls = []

        original_run_in_executor = loop.run_in_executor

        async def tracking_run_in_executor(executor, func, *args):
            executor_calls.append((executor, func, args))
            return await original_run_in_executor(executor, func, *args)

        with patch("subprocess.run", return_value=failing_proc), \
             patch.object(loop, "run_in_executor", side_effect=tracking_run_in_executor):
            await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert len(executor_calls) >= 1, (
            "tests_must_fail must use loop.run_in_executor for thread delegation; "
            "no run_in_executor calls detected — tests_must_fail is likely blocking"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_uses_thread_delegation(self):
        """FR-015: tests_must_pass must delegate subprocess to run_in_executor or asyncio.to_thread."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0)

        loop = asyncio.get_event_loop()
        executor_calls = []

        original_run_in_executor = loop.run_in_executor

        async def tracking_run_in_executor(executor, func, *args):
            executor_calls.append((executor, func, args))
            return await original_run_in_executor(executor, func, *args)

        with patch("subprocess.run", return_value=passing_proc), \
             patch.object(loop, "run_in_executor", side_effect=tracking_run_in_executor):
            await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert len(executor_calls) >= 1, (
            "tests_must_pass must use loop.run_in_executor for thread delegation; "
            "no run_in_executor calls detected — tests_must_pass is likely blocking"
        )

    @pytest.mark.asyncio
    async def test_async_methods_do_not_call_subprocess_run_directly_on_event_loop(self):
        """FR-015: subprocess.run must NOT be called directly in the async function body.

        Direct subprocess.run in an async function blocks the event loop.
        Execution must be offloaded to a thread via run_in_executor or asyncio.to_thread.
        """
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        direct_subprocess_calls = []
        thread_pool_calls = []

        original_run_in_executor = asyncio.get_event_loop().run_in_executor

        def mock_subprocess_run(*args, **kwargs):
            # Track whether we're in a thread (not the main event loop thread)
            import threading
            thread_name = threading.current_thread().name
            if "ThreadPoolExecutor" in thread_name or "Thread" in thread_name:
                thread_pool_calls.append(True)
            else:
                direct_subprocess_calls.append(True)
            return failing_proc

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        # subprocess.run must not have been called directly on the event loop thread
        assert len(direct_subprocess_calls) == 0, (
            "subprocess.run was called directly on the event loop thread — "
            "this blocks the loop. Use run_in_executor or asyncio.to_thread."
        )


# ===========================================================================
# 7. Error handling in async context
# ===========================================================================


class TestAsyncErrorHandling:
    """FR-043: FileNotFoundError and TimeoutExpired must be caught in async context."""

    @pytest.mark.asyncio
    async def test_file_not_found_returns_check_result_with_success_false(self):
        """FR-043: FileNotFoundError must return CheckResult with success=False."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=FileNotFoundError("no such file")):
            result = await strategy.tests_must_fail(task_id="T015", command="nonexistent-cmd")

        assert isinstance(result, CheckResult), (
            "FileNotFoundError must still return CheckResult"
        )
        assert result.success is False, (
            "CheckResult.success must be False on FileNotFoundError"
        )

    @pytest.mark.asyncio
    async def test_file_not_found_output_describes_error(self):
        """FR-043: CheckResult.output must describe FileNotFoundError."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=FileNotFoundError("cmd not found")):
            result = await strategy.tests_must_fail(task_id="T015", command="bad-cmd")

        assert result.output, "output must not be empty on FileNotFoundError"
        output_lower = result.output.lower()
        assert any(
            keyword in output_lower
            for keyword in ("not found", "filenotfound", "no such file", "command")
        ), (
            f"output must describe missing command; got: {result.output!r}"
        )

    @pytest.mark.asyncio
    async def test_timeout_expired_returns_check_result_with_success_false(self):
        """FR-043: TimeoutExpired must return CheckResult with success=False."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=30)):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert isinstance(result, CheckResult), (
            "TimeoutExpired must still return CheckResult"
        )
        assert result.success is False, (
            "CheckResult.success must be False on TimeoutExpired"
        )

    @pytest.mark.asyncio
    async def test_timeout_expired_output_mentions_timeout(self):
        """FR-043: CheckResult.output must mention timeout on TimeoutExpired."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=30)):
            result = await strategy.tests_must_pass(task_id="T015", command="pytest tests/")

        assert result.output, "output must not be empty on TimeoutExpired"
        output_lower = result.output.lower()
        assert "timeout" in output_lower or "timed out" in output_lower, (
            f"output must mention timeout; got: {result.output!r}"
        )

    @pytest.mark.asyncio
    async def test_tests_must_pass_does_not_raise_on_file_not_found(self):
        """FR-043: tests_must_pass must not raise on FileNotFoundError."""
        strategy = _make_strategy(max_retries=0)

        # Must not raise
        with patch("subprocess.run", side_effect=FileNotFoundError("gone")):
            result = await strategy.tests_must_pass(task_id="T015", command="missing-cmd")

        assert result is not None

    @pytest.mark.asyncio
    async def test_tests_must_fail_does_not_raise_on_timeout(self):
        """FR-043: tests_must_fail must not raise on TimeoutExpired."""
        strategy = _make_strategy(max_retries=0)

        # Must not raise
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=5)):
            result = await strategy.tests_must_fail(task_id="T015", command="pytest tests/")

        assert result is not None


# ===========================================================================
# 8. common.py size constraint
# ===========================================================================


class TestCommonModuleSizeConstraint:
    """FR-043: orchestrator/checks/common.py MUST stay under 150 lines."""

    def test_common_py_exists(self):
        """orchestrator/checks/common.py must exist as a module file."""
        common_path = Path(__file__).parent.parent.parent.parent / "orchestrator" / "checks" / "common.py"
        assert common_path.exists(), (
            f"orchestrator/checks/common.py not found at {common_path}"
        )

    def test_common_py_is_importable(self):
        """orchestrator/checks/common.py must be importable without errors."""
        import importlib
        module = importlib.import_module("orchestrator.checks.common")
        assert module is not None

    def test_common_py_under_150_lines(self):
        """FR-043: common.py must be strictly under 150 lines total."""
        common_path = Path(__file__).parent.parent.parent.parent / "orchestrator" / "checks" / "common.py"
        lines = common_path.read_text(encoding="utf-8").splitlines()
        line_count = len(lines)
        assert line_count < 150, (
            f"orchestrator/checks/common.py has {line_count} lines — "
            f"must be strictly under 150 lines (current: {line_count})"
        )

    def test_common_py_line_count_not_zero(self):
        """common.py must be a non-empty file (at minimum a module docstring)."""
        common_path = Path(__file__).parent.parent.parent.parent / "orchestrator" / "checks" / "common.py"
        content = common_path.read_text(encoding="utf-8").strip()
        assert len(content) > 0, "common.py must not be empty"


# ===========================================================================
# 9. CheckResult constructor signature
# ===========================================================================


class TestCheckResultConstructorSignature:
    """CheckResult must accept success, output, return_code, duration parameters."""

    def test_check_result_accepts_success_output_return_code_duration(self):
        """CheckResult constructor must accept all four required keyword arguments."""
        # Must not raise TypeError
        result = CheckResult(
            success=True,
            output="all tests passed",
            return_code=0,
            duration=0.42,
        )
        assert result is not None

    def test_check_result_success_false_with_nonzero_return_code(self):
        """CheckResult with success=False and non-zero return_code."""
        result = CheckResult(success=False, output="1 failed", return_code=1, duration=0.1)
        assert result.success is False
        assert result.return_code == 1

    def test_check_result_duration_zero_is_valid(self):
        """CheckResult.duration=0.0 must be a valid value."""
        result = CheckResult(success=True, output="", return_code=0, duration=0.0)
        assert result.duration == 0.0

    def test_check_result_return_code_127_is_stored(self):
        """CheckResult.return_code can store any integer exit code."""
        result = CheckResult(success=False, output="command not found", return_code=127, duration=0.0)
        assert result.return_code == 127

    def test_check_result_large_output_is_stored(self):
        """CheckResult.output can store very long strings."""
        large_output = "x" * 100_000
        result = CheckResult(success=True, output=large_output, return_code=0, duration=0.1)
        assert len(result.output) == 100_000

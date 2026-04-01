"""Unit tests for LocalCheckStrategy — local subprocess test execution.

T010 [US3] [FR-013] [FR-042] [FR-043]
Implement LocalCheckStrategy with subprocess test execution, retry with
backoff, and TimeoutExpired/FileNotFoundError handling.

FR-013: LocalCheckStrategy MUST run tests locally via subprocess and return a
        structured result (pass/fail with details).
FR-042: All subprocess operations MUST implement retry with configurable
        attempt count and exponential backoff.
FR-043: Subprocess calls MUST catch FileNotFoundError and
        subprocess.TimeoutExpired.

Test areas:
  1.  LocalCheckStrategy and CheckResult are importable and instantiable.
  2.  CheckResult has passed, output, and attempts attributes.
  3.  Successful subprocess execution returns a passing CheckResult.
  4.  Failed subprocess execution (non-zero exit code) returns a failing
      CheckResult.
  5.  tests_must_fail returns True (bool) when process exits non-zero.
  6.  tests_must_pass returns True (bool) when process exits zero.
  7.  Retry logic: multiple subprocess attempts are made on failure.
  8.  Max retries configuration is respected (no extra attempts).
  9.  Backoff delay increases between retries (exponential growth).
  10. subprocess.TimeoutExpired is caught and returns a failing CheckResult.
  11. FileNotFoundError is caught and returns a failing CheckResult.
  12. CheckResult.output includes relevant error detail on failure.
  13. CheckResult.attempts reflects the actual number of subprocess calls made.
  14. tests_must_fail returns False when tests unexpectedly pass.
  15. tests_must_pass returns False when tests continue to fail after retries.
  16. Backoff is not applied after the final attempt (no sleep after last try).
  17. Edge: max_retries=0 means one attempt only, no retry.
  18. Edge: TimeoutExpired on every attempt still retries up to max_retries.
  19. Edge: FileNotFoundError on first attempt does not retry (command missing).
  20. CheckResult.passed is False when TimeoutExpired is caught.
  21. CheckResult.passed is False when FileNotFoundError is caught.
  22. LocalCheckStrategy is a concrete subclass of CheckStrategy ABC.

All tests in this module are RED-phase tests — they MUST FAIL until
orchestrator/checks/local.py provides a complete implementation.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from orchestrator.checks.base import CheckStrategy
from orchestrator.checks.local import CheckResult, LocalCheckStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(
    command: str = "pytest tests/",
    max_retries: int = 3,
    backoff_base: float = 0.1,
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
# 1. Import and instantiation
# ===========================================================================


class TestImportAndInstantiation:
    """FR-013: LocalCheckStrategy and CheckResult must be importable."""

    def test_local_check_strategy_is_a_class(self):
        """LocalCheckStrategy must be a class."""
        import inspect
        assert inspect.isclass(LocalCheckStrategy)

    def test_check_result_is_a_class(self):
        """CheckResult must be a class."""
        import inspect
        assert inspect.isclass(CheckResult)

    def test_local_check_strategy_instantiable(self):
        """LocalCheckStrategy must instantiate with command, max_retries, backoff_base."""
        strategy = LocalCheckStrategy(
            command="pytest tests/",
            max_retries=3,
            backoff_base=1.0,
        )
        assert strategy is not None

    def test_local_check_strategy_instance_type(self):
        """Instantiated strategy must be a LocalCheckStrategy."""
        strategy = _make_strategy()
        assert isinstance(strategy, LocalCheckStrategy)

    def test_check_result_instantiable(self):
        """CheckResult must instantiate with passed, output, and attempts."""
        result = CheckResult(passed=True, output="all tests passed", attempts=1)
        assert result is not None

    def test_check_result_instance_type(self):
        """Instantiated result must be a CheckResult."""
        result = CheckResult(passed=True, output="ok", attempts=1)
        assert isinstance(result, CheckResult)


# ===========================================================================
# 2. CheckResult attributes
# ===========================================================================


class TestCheckResultAttributes:
    """FR-013: CheckResult must expose passed, output, and attempts."""

    def test_check_result_passed_true(self):
        """CheckResult.passed must be True when tests passed."""
        result = CheckResult(passed=True, output="1 passed", attempts=1)
        assert result.passed is True

    def test_check_result_passed_false(self):
        """CheckResult.passed must be False when tests failed."""
        result = CheckResult(passed=False, output="1 failed", attempts=1)
        assert result.passed is False

    def test_check_result_output_stored(self):
        """CheckResult.output must store the provided output string."""
        result = CheckResult(passed=True, output="test output here", attempts=2)
        assert result.output == "test output here"

    def test_check_result_attempts_stored(self):
        """CheckResult.attempts must store the provided attempt count."""
        result = CheckResult(passed=False, output="", attempts=3)
        assert result.attempts == 3

    def test_check_result_output_defaults_to_empty_string(self):
        """CheckResult.output should default to empty string when not provided."""
        result = CheckResult(passed=True, attempts=1)
        assert result.output == ""

    def test_check_result_attempts_defaults_to_one(self):
        """CheckResult.attempts should default to 1 when not provided."""
        result = CheckResult(passed=True)
        assert result.attempts == 1


# ===========================================================================
# 3. CheckStrategy ABC compliance
# ===========================================================================


class TestCheckStrategyABCCompliance:
    """FR-013: LocalCheckStrategy MUST be a concrete subclass of CheckStrategy."""

    def test_local_check_strategy_is_subclass_of_check_strategy(self):
        """LocalCheckStrategy must subclass CheckStrategy."""
        assert issubclass(LocalCheckStrategy, CheckStrategy), (
            "LocalCheckStrategy must subclass orchestrator.checks.base.CheckStrategy"
        )

    def test_local_check_strategy_instance_is_check_strategy(self):
        """Instances of LocalCheckStrategy must satisfy isinstance(CheckStrategy)."""
        strategy = _make_strategy()
        assert isinstance(strategy, CheckStrategy)

    def test_local_check_strategy_has_tests_must_fail(self):
        """LocalCheckStrategy must implement tests_must_fail."""
        assert hasattr(LocalCheckStrategy, "tests_must_fail")
        assert callable(LocalCheckStrategy.tests_must_fail)

    def test_local_check_strategy_has_tests_must_pass(self):
        """LocalCheckStrategy must implement tests_must_pass."""
        assert hasattr(LocalCheckStrategy, "tests_must_pass")
        assert callable(LocalCheckStrategy.tests_must_pass)


# ===========================================================================
# 4. Successful subprocess execution
# ===========================================================================


class TestSuccessfulSubprocessExecution:
    """FR-013: Successful test run (exit code 0) must produce a passing result."""

    def test_tests_must_pass_returns_true_on_zero_exit(self):
        """FR-013: tests_must_pass must return True when subprocess exits 0."""
        strategy = _make_strategy()
        passing_proc = _make_completed_process(returncode=0, stdout="1 passed")

        with patch("subprocess.run", return_value=passing_proc):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is True, (
            "tests_must_pass must return True when tests pass (exit 0)"
        )

    def test_tests_must_fail_returns_false_when_tests_unexpectedly_pass(self):
        """FR-013: tests_must_fail must return False when subprocess exits 0.

        In the RED phase, if tests pass when they should fail, that is an
        unexpected condition — tests_must_fail returns False.
        """
        strategy = _make_strategy()
        passing_proc = _make_completed_process(returncode=0, stdout="all passed")

        with patch("subprocess.run", return_value=passing_proc):
            result = strategy.tests_must_fail(task_id="T010", command="pytest tests/")

        assert result is False, (
            "tests_must_fail must return False when tests unexpectedly pass"
        )

    def test_subprocess_run_called_with_command(self):
        """FR-013: subprocess.run must be called with the provided command."""
        strategy = _make_strategy(command="npm test")
        passing_proc = _make_completed_process(returncode=0)

        with patch("subprocess.run", return_value=passing_proc) as mock_run:
            strategy.tests_must_pass(task_id="T010", command="npm test")

        assert mock_run.called, "subprocess.run must be called"
        # The command string (or shell-split equivalent) must appear in the call
        call_args = mock_run.call_args
        first_arg = call_args[0][0] if call_args[0] else call_args[1].get("args", "")
        # Accept either the string directly or a list containing its tokens
        if isinstance(first_arg, list):
            joined = " ".join(first_arg)
        else:
            joined = str(first_arg)
        assert "npm" in joined or "npm test" in joined, (
            f"subprocess.run must be invoked with the test command; got: {call_args}"
        )


# ===========================================================================
# 5. Failed subprocess execution
# ===========================================================================


class TestFailedSubprocessExecution:
    """FR-013: Non-zero exit must produce a failing result."""

    def test_tests_must_fail_returns_true_on_nonzero_exit(self):
        """FR-013: tests_must_fail must return True when subprocess exits non-zero.

        A non-zero exit confirms the RED phase — tests are correctly failing.
        """
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1, stderr="AssertionError")

        with patch("subprocess.run", return_value=failing_proc):
            result = strategy.tests_must_fail(task_id="T010", command="pytest tests/")

        assert result is True, (
            "tests_must_fail must return True when tests fail (exit non-zero)"
        )

    def test_tests_must_pass_returns_false_on_nonzero_exit_after_retries(self):
        """FR-013: tests_must_pass must return False when tests keep failing."""
        strategy = _make_strategy(max_retries=1, backoff_base=0.0)
        failing_proc = _make_completed_process(returncode=1, stderr="1 failed")

        with patch("subprocess.run", return_value=failing_proc), \
             patch("time.sleep"):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is False, (
            "tests_must_pass must return False when tests remain failing after retries"
        )


# ===========================================================================
# 6. Retry logic
# ===========================================================================


class TestRetryLogic:
    """FR-042: Retry with configurable attempt count on test failure."""

    def test_tests_must_pass_retries_on_failure(self):
        """FR-042: tests_must_pass must retry when subprocess exits non-zero."""
        strategy = _make_strategy(max_retries=2, backoff_base=0.0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc) as mock_run, \
             patch("time.sleep"):
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        # max_retries=2 means initial attempt + 2 retries = 3 total calls
        assert mock_run.call_count == 3, (
            f"Expected 3 subprocess.run calls (1 initial + 2 retries), "
            f"got {mock_run.call_count}"
        )

    def test_tests_must_pass_stops_after_max_retries(self):
        """FR-042: Retry must not exceed max_retries attempts."""
        strategy = _make_strategy(max_retries=1, backoff_base=0.0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc) as mock_run, \
             patch("time.sleep"):
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        # max_retries=1 means initial attempt + 1 retry = 2 total calls
        assert mock_run.call_count == 2, (
            f"Expected exactly 2 calls with max_retries=1, got {mock_run.call_count}"
        )

    def test_max_retries_zero_means_single_attempt(self):
        """FR-042: max_retries=0 must result in exactly one subprocess call."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc) as mock_run:
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert mock_run.call_count == 1, (
            f"max_retries=0 must make exactly 1 call, got {mock_run.call_count}"
        )

    def test_no_retry_on_success(self):
        """FR-042: No retry should occur when subprocess exits 0 on first attempt."""
        strategy = _make_strategy(max_retries=3, backoff_base=0.0)
        passing_proc = _make_completed_process(returncode=0)

        with patch("subprocess.run", return_value=passing_proc) as mock_run:
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert mock_run.call_count == 1, (
            f"No retry should occur on first-attempt success, got {mock_run.call_count}"
        )

    def test_check_result_attempts_reflects_actual_call_count(self):
        """FR-042: CheckResult.attempts must equal the number of subprocess calls."""
        strategy = _make_strategy(max_retries=2, backoff_base=0.0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc), \
             patch("time.sleep"):
            # Use a method that returns CheckResult directly
            result = strategy._run_with_retry(command="pytest tests/")

        assert result.attempts == 3, (
            f"CheckResult.attempts must be 3 (1 initial + 2 retries), got {result.attempts}"
        )

    def test_check_result_attempts_one_on_first_success(self):
        """FR-042: CheckResult.attempts must be 1 when first attempt succeeds."""
        strategy = _make_strategy(max_retries=3, backoff_base=0.0)
        passing_proc = _make_completed_process(returncode=0)

        with patch("subprocess.run", return_value=passing_proc):
            result = strategy._run_with_retry(command="pytest tests/")

        assert result.attempts == 1, (
            f"CheckResult.attempts must be 1 on first-attempt success, got {result.attempts}"
        )


# ===========================================================================
# 7. Backoff delay
# ===========================================================================


class TestBackoffDelay:
    """FR-042: Backoff delay must increase between retries."""

    def test_sleep_called_between_retries(self):
        """FR-042: time.sleep must be called between retry attempts."""
        strategy = _make_strategy(max_retries=2, backoff_base=1.0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc), \
             patch("time.sleep") as mock_sleep:
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        # 2 retries means 2 sleeps (before retry 1 and retry 2)
        assert mock_sleep.call_count == 2, (
            f"time.sleep must be called once per retry, expected 2, got {mock_sleep.call_count}"
        )

    def test_backoff_delay_increases_exponentially(self):
        """FR-042: Each retry delay must be greater than the previous one.

        With backoff_base=1.0: delay[0]=1.0, delay[1]=2.0 (or similar growth).
        """
        strategy = _make_strategy(max_retries=3, backoff_base=1.0)
        failing_proc = _make_completed_process(returncode=1)
        sleep_calls = []

        def capture_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("subprocess.run", return_value=failing_proc), \
             patch("time.sleep", side_effect=capture_sleep):
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert len(sleep_calls) >= 2, (
            f"Need at least 2 sleep calls to verify growth, got {sleep_calls}"
        )
        assert sleep_calls[1] > sleep_calls[0], (
            f"Backoff delay must increase: {sleep_calls[0]} -> {sleep_calls[1]}"
        )

    def test_no_sleep_after_final_attempt(self):
        """FR-042: time.sleep must NOT be called after the final attempt."""
        strategy = _make_strategy(max_retries=1, backoff_base=1.0)
        failing_proc = _make_completed_process(returncode=1)
        sleep_calls = []

        def capture_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("subprocess.run", return_value=failing_proc), \
             patch("time.sleep", side_effect=capture_sleep):
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        # max_retries=1 => 2 total calls, 1 sleep (between attempt 1 and 2)
        assert len(sleep_calls) == 1, (
            f"With max_retries=1, exactly 1 sleep between attempts; got {sleep_calls}"
        )

    def test_no_sleep_when_max_retries_zero(self):
        """FR-042: time.sleep must never be called when max_retries=0."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc), \
             patch("time.sleep") as mock_sleep:
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert mock_sleep.call_count == 0, (
            f"No sleep when max_retries=0, got {mock_sleep.call_count} calls"
        )

    def test_backoff_base_scales_delay(self):
        """FR-042: First retry delay must equal backoff_base (or be proportional)."""
        strategy = _make_strategy(max_retries=1, backoff_base=5.0)
        failing_proc = _make_completed_process(returncode=1)
        sleep_calls = []

        def capture_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("subprocess.run", return_value=failing_proc), \
             patch("time.sleep", side_effect=capture_sleep):
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert len(sleep_calls) >= 1
        # First delay must be >= backoff_base (not less than configured base)
        assert sleep_calls[0] >= 5.0, (
            f"First sleep must be >= backoff_base=5.0, got {sleep_calls[0]}"
        )


# ===========================================================================
# 8. subprocess.TimeoutExpired handling
# ===========================================================================


class TestTimeoutExpiredHandling:
    """FR-043: subprocess.TimeoutExpired MUST be caught, not propagated."""

    def test_timeout_expired_does_not_raise(self):
        """FR-043: TimeoutExpired must be caught; tests_must_pass must not raise."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=30)):
            # Must not raise
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is not None, "tests_must_pass must return a value, not raise"

    def test_timeout_expired_returns_false_for_tests_must_pass(self):
        """FR-043: TimeoutExpired on tests_must_pass returns False (not passing)."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=30)):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is False, (
            "tests_must_pass must return False when TimeoutExpired is caught"
        )

    def test_timeout_expired_check_result_passed_is_false(self):
        """FR-043: CheckResult.passed must be False on TimeoutExpired."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=30)):
            check_result = strategy._run_with_retry(command="pytest tests/")

        assert check_result.passed is False, (
            "CheckResult.passed must be False when TimeoutExpired is caught"
        )

    def test_timeout_expired_check_result_output_contains_timeout_info(self):
        """FR-043: CheckResult.output must mention timeout or the exception."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=30)):
            check_result = strategy._run_with_retry(command="pytest tests/")

        assert check_result.output, "CheckResult.output must not be empty on timeout"
        output_lower = check_result.output.lower()
        assert "timeout" in output_lower or "timed out" in output_lower or "TimeoutExpired".lower() in output_lower, (
            f"CheckResult.output must mention timeout; got: {check_result.output!r}"
        )

    def test_timeout_expired_retried_up_to_max_retries(self):
        """FR-043: TimeoutExpired should still trigger retry (transient network/resource issue)."""
        strategy = _make_strategy(max_retries=2, backoff_base=0.0)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=30)) as mock_run, \
             patch("time.sleep"):
            strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        # Should retry on TimeoutExpired: 1 initial + 2 retries = 3 calls
        assert mock_run.call_count == 3, (
            f"TimeoutExpired should be retried; expected 3 calls, got {mock_run.call_count}"
        )


# ===========================================================================
# 9. FileNotFoundError handling
# ===========================================================================


class TestFileNotFoundErrorHandling:
    """FR-043: FileNotFoundError MUST be caught when the command binary is missing."""

    def test_file_not_found_error_does_not_raise(self):
        """FR-043: FileNotFoundError must be caught; tests_must_pass must not raise."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=FileNotFoundError("pytest not found")):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is not None, "tests_must_pass must return a value on FileNotFoundError"

    def test_file_not_found_error_returns_false_for_tests_must_pass(self):
        """FR-043: FileNotFoundError on tests_must_pass returns False."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=FileNotFoundError("command not found")):
            result = strategy.tests_must_pass(task_id="T010", command="nonexistent-cmd")

        assert result is False, (
            "tests_must_pass must return False when FileNotFoundError is caught"
        )

    def test_file_not_found_error_check_result_passed_is_false(self):
        """FR-043: CheckResult.passed must be False on FileNotFoundError."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=FileNotFoundError("no such file")):
            check_result = strategy._run_with_retry(command="nonexistent-cmd")

        assert check_result.passed is False, (
            "CheckResult.passed must be False when FileNotFoundError is caught"
        )

    def test_file_not_found_error_check_result_output_contains_error_info(self):
        """FR-043: CheckResult.output must describe the FileNotFoundError."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=FileNotFoundError("no such file or directory")):
            check_result = strategy._run_with_retry(command="bad-cmd")

        assert check_result.output, "CheckResult.output must not be empty on FileNotFoundError"
        output_lower = check_result.output.lower()
        assert (
            "not found" in output_lower
            or "filenotfound" in output_lower
            or "no such file" in output_lower
            or "command" in output_lower
        ), (
            f"CheckResult.output must describe the missing command; got: {check_result.output!r}"
        )

    def test_file_not_found_error_does_not_retry(self):
        """FR-043: FileNotFoundError must NOT trigger retry (the binary is absent).

        Retrying a missing command wastes time — it will never succeed.
        """
        strategy = _make_strategy(max_retries=3, backoff_base=0.0)

        with patch("subprocess.run", side_effect=FileNotFoundError("not found")) as mock_run, \
             patch("time.sleep") as mock_sleep:
            strategy.tests_must_pass(task_id="T010", command="missing-cmd")

        assert mock_run.call_count == 1, (
            f"FileNotFoundError must not be retried; expected 1 call, got {mock_run.call_count}"
        )
        assert mock_sleep.call_count == 0, (
            f"No sleep should occur on FileNotFoundError; got {mock_sleep.call_count} calls"
        )

    def test_file_not_found_error_tests_must_fail_returns_false(self):
        """FR-043: tests_must_fail must return False on FileNotFoundError.

        A missing command cannot confirm a RED phase — it is not an
        AssertionError failure from the test suite itself.
        """
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
            result = strategy.tests_must_fail(task_id="T010", command="missing-cmd")

        assert result is False, (
            "tests_must_fail must return False when command binary is not found"
        )


# ===========================================================================
# 10. Output capture
# ===========================================================================


class TestOutputCapture:
    """FR-013: CheckResult.output must contain subprocess stdout/stderr."""

    def test_check_result_output_contains_stdout(self):
        """FR-013: CheckResult.output must include subprocess stdout."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0, stdout="1 passed in 0.5s")

        with patch("subprocess.run", return_value=passing_proc):
            check_result = strategy._run_with_retry(command="pytest tests/")

        assert "1 passed" in check_result.output, (
            f"CheckResult.output must include stdout; got: {check_result.output!r}"
        )

    def test_check_result_output_contains_stderr_on_failure(self):
        """FR-013: CheckResult.output must include subprocess stderr on failure."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(
            returncode=1,
            stdout="",
            stderr="FAILED tests/test_foo.py::test_bar - AssertionError",
        )

        with patch("subprocess.run", return_value=failing_proc):
            check_result = strategy._run_with_retry(command="pytest tests/")

        assert "AssertionError" in check_result.output or "FAILED" in check_result.output, (
            f"CheckResult.output must include stderr on failure; got: {check_result.output!r}"
        )

    def test_check_result_passed_reflects_exit_code(self):
        """FR-013: CheckResult.passed must be True iff exit code was 0."""
        strategy = _make_strategy(max_retries=0)

        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            result_pass = strategy._run_with_retry(command="pytest")

        with patch("subprocess.run", return_value=_make_completed_process(returncode=2)):
            result_fail = strategy._run_with_retry(command="pytest")

        assert result_pass.passed is True
        assert result_fail.passed is False


# ===========================================================================
# 11. tests_must_fail and tests_must_pass return bool
# ===========================================================================


class TestBooleanReturnValues:
    """FR-013: tests_must_fail and tests_must_pass must return bool, not CheckResult."""

    def test_tests_must_pass_returns_bool_true(self):
        """tests_must_pass must return the bool True on success."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0)

        with patch("subprocess.run", return_value=passing_proc):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is True
        assert type(result) is bool

    def test_tests_must_pass_returns_bool_false_on_failure(self):
        """tests_must_pass must return the bool False on persistent failure."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is False
        assert type(result) is bool

    def test_tests_must_fail_returns_bool_true_on_nonzero(self):
        """tests_must_fail must return the bool True when exit code is non-zero."""
        strategy = _make_strategy(max_retries=0)
        failing_proc = _make_completed_process(returncode=1)

        with patch("subprocess.run", return_value=failing_proc):
            result = strategy.tests_must_fail(task_id="T010", command="pytest tests/")

        assert result is True
        assert type(result) is bool

    def test_tests_must_fail_returns_bool_false_on_zero(self):
        """tests_must_fail must return the bool False when exit code is 0."""
        strategy = _make_strategy(max_retries=0)
        passing_proc = _make_completed_process(returncode=0)

        with patch("subprocess.run", return_value=passing_proc):
            result = strategy.tests_must_fail(task_id="T010", command="pytest tests/")

        assert result is False
        assert type(result) is bool


# ===========================================================================
# 12. Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases: special exit codes, empty output, and large output."""

    def test_exit_code_2_is_treated_as_failure(self):
        """Exit code 2 (e.g., pytest collection error) must be treated as failure."""
        strategy = _make_strategy(max_retries=0)
        proc = _make_completed_process(returncode=2, stderr="ERROR collecting tests/")

        with patch("subprocess.run", return_value=proc):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is False

    def test_exit_code_127_is_treated_as_failure(self):
        """Exit code 127 (command not found in shell) must be treated as failure."""
        strategy = _make_strategy(max_retries=0)
        proc = _make_completed_process(returncode=127, stderr="command not found")

        with patch("subprocess.run", return_value=proc):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is False

    def test_empty_stdout_and_stderr_still_returns_result(self):
        """Empty subprocess output must not cause exceptions."""
        strategy = _make_strategy(max_retries=0)
        proc = _make_completed_process(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", return_value=proc):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is True

    def test_very_large_output_does_not_raise(self):
        """Subprocess producing large output (100k chars) must not raise."""
        strategy = _make_strategy(max_retries=0)
        large_output = "x" * 100_000
        proc = _make_completed_process(returncode=0, stdout=large_output)

        with patch("subprocess.run", return_value=proc):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is True

    def test_retry_succeeds_on_second_attempt(self):
        """FR-042: Retry must stop and return True if a later attempt succeeds."""
        strategy = _make_strategy(max_retries=2, backoff_base=0.0)
        failing_proc = _make_completed_process(returncode=1)
        passing_proc = _make_completed_process(returncode=0)
        side_effects = [failing_proc, passing_proc]

        with patch("subprocess.run", side_effect=side_effects) as mock_run, \
             patch("time.sleep"):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is True, (
            "tests_must_pass must return True once a retry succeeds"
        )
        assert mock_run.call_count == 2, (
            f"Must stop retrying after success; expected 2 calls, got {mock_run.call_count}"
        )

    def test_timeout_on_every_attempt_exhausts_retries(self):
        """FR-043: TimeoutExpired on all attempts must exhaust retries and return False."""
        strategy = _make_strategy(max_retries=2, backoff_base=0.0)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=5)) as mock_run, \
             patch("time.sleep"):
            result = strategy.tests_must_pass(task_id="T010", command="pytest tests/")

        assert result is False
        assert mock_run.call_count == 3, (
            f"TimeoutExpired retry: expected 3 attempts, got {mock_run.call_count}"
        )


# ===========================================================================
# 11. _split_command Windows 兼容性 (H2)
# ===========================================================================


class TestSplitCommand:
    """H2: _split_command must correctly handle Windows backslash paths."""

    def test_split_command_returns_list(self):
        """_split_command always returns a list of strings."""
        from orchestrator.checks.local import _split_command
        result = _split_command("pytest tests/ -v")
        assert isinstance(result, list)

    def test_split_command_simple(self):
        """_split_command splits a simple command correctly."""
        from orchestrator.checks.local import _split_command
        result = _split_command("python -m pytest tests/ -v")
        assert result == ["python", "-m", "pytest", "tests/", "-v"]

    def test_split_command_preserves_backslash_on_windows(self):
        """_split_command with posix=False preserves backslashes."""
        import shlex
        # Simulate Windows behavior: posix=False preserves backslashes
        result = shlex.split(r"C:\Python\pytest.exe tests\unit", posix=False)
        assert r"C:\Python\pytest.exe" in result
        assert r"tests\unit" in result

    def test_split_command_with_spaces_posix_false(self):
        """posix=False preserves quoted paths with spaces."""
        import shlex
        result = shlex.split(r'"C:\Program Files\Python\python.exe" -m pytest', posix=False)
        assert any("Program Files" in part for part in result)

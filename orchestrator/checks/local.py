"""LocalCheckStrategy — local subprocess test execution.

FR-013: LocalCheckStrategy executes tests locally via subprocess.
FR-042: Retry with configurable attempt count and backoff.
FR-043: Catch FileNotFoundError and subprocess.TimeoutExpired.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import time

from orchestrator.checks.base import CheckStrategy

_POSIX = sys.platform != "win32"


def _split_command(command: str) -> list[str]:
    """Split a shell command string into a list, respecting the current platform.

    On Windows, ``shlex.split`` runs with ``posix=False`` so that
    backslash-heavy paths (e.g. ``C:\\path\\to\\pytest``) are preserved.
    """
    return shlex.split(command, posix=_POSIX)


class CheckResult:
    """Structured result returned by LocalCheckStrategy methods.

    Attributes:
        passed: True if the test command exited with code 0.
        output: Combined stdout/stderr from the subprocess (or error message).
        attempts: Number of subprocess invocations actually made.
    """

    def __init__(self, passed: bool, output: str = "", attempts: int = 1):
        self.passed = passed
        self.output = output
        self.attempts = attempts


class LocalCheckStrategy(CheckStrategy):
    """Runs tests locally via subprocess with retry and backoff.

    Args:
        command: Default shell command to execute tests.
        max_retries: Number of *additional* attempts after the first failure.
            0 means exactly one attempt with no retry.
        backoff_base: Base delay in seconds for exponential backoff.
            Delay for retry *i* is ``backoff_base * 2**i``.
    """

    def __init__(
        self,
        command: str,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        timeout: int = 300,
    ):
        self._command = command
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._timeout = timeout  # H1: 子进程超时（秒），默认 5 分钟

    # ------------------------------------------------------------------
    # Internal: run with retry + backoff
    # ------------------------------------------------------------------

    def _run_with_retry(self, command: str) -> CheckResult:
        """Execute *command* via subprocess, retrying on transient failures.

        Retry is performed on non-zero exit codes and
        ``subprocess.TimeoutExpired``.  ``FileNotFoundError`` is **not**
        retried because the binary is permanently absent.

        Returns:
            A :class:`CheckResult` summarising the outcome.
        """
        total_attempts = self._max_retries + 1
        last_output = ""

        for attempt in range(total_attempts):
            try:
                proc = subprocess.run(
                    _split_command(command),
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,  # H1: 防止无限等待
                )
                output = (proc.stdout or "") + (proc.stderr or "")
                if proc.returncode == 0:
                    return CheckResult(
                        passed=True, output=output, attempts=attempt + 1
                    )
                last_output = output

            except subprocess.TimeoutExpired as exc:
                last_output = f"Command timed out after {exc.timeout}s: timeout"
                # Transient — allow retry to continue.

            except FileNotFoundError as exc:
                # Permanent — no point retrying a missing binary.
                return CheckResult(
                    passed=False,
                    output=f"Command not found: {exc}",
                    attempts=attempt + 1,
                )

            # Back off before next retry (skip after final attempt).
            if attempt < total_attempts - 1:
                delay = self._backoff_base * (2 ** attempt)
                time.sleep(delay)

        return CheckResult(
            passed=False, output=last_output, attempts=total_attempts
        )

    # ------------------------------------------------------------------
    # CheckStrategy interface
    # ------------------------------------------------------------------

    def tests_must_fail(self, task_id: str, command: str) -> bool:
        """Verify RED phase: the given test command must fail.

        Runs the command **once** (no retry).  Returns ``True`` only when
        the process exits with a non-zero code — confirming that the tests
        genuinely failed.  ``FileNotFoundError`` and ``TimeoutExpired``
        return ``False`` because they cannot confirm a real test failure.
        """
        try:
            proc = subprocess.run(
                _split_command(command),
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,  # H1: 防止无限等待
            )
            return proc.returncode != 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def tests_must_pass(self, task_id: str, command: str) -> bool:
        """Verify GREEN phase: the given test command must pass.

        Delegates to :meth:`_run_with_retry` so that transient failures
        (non-zero exit, ``TimeoutExpired``) are retried with exponential
        backoff.  Returns ``True`` only when the process exits 0.
        """
        result = self._run_with_retry(command)
        return result.passed

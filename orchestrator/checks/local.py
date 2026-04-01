"""LocalCheckStrategy — local subprocess test execution.

FR-013: LocalCheckStrategy executes tests locally via subprocess.
FR-042: Retry with configurable attempt count and backoff.
FR-043: Catch FileNotFoundError and subprocess.TimeoutExpired.

Stub only — implementation pending GREEN phase.
"""


class CheckResult:
    """Structured result returned by LocalCheckStrategy methods.

    Stub: no real implementation yet.
    """

    def __init__(self, passed: bool, output: str = "", attempts: int = 1):
        raise NotImplementedError("not implemented")


class LocalCheckStrategy:
    """Runs tests locally via subprocess with retry and backoff.

    Stub: no real implementation yet.
    """

    def __init__(self, command: str, max_retries: int = 3, backoff_base: float = 1.0):
        raise NotImplementedError("not implemented")

    def tests_must_fail(self, task_id: str, command: str) -> "CheckResult":
        """Verify RED phase: tests must fail (non-zero exit code)."""
        raise NotImplementedError("not implemented")

    def tests_must_pass(self, task_id: str, command: str) -> "CheckResult":
        """Verify GREEN phase: tests must pass (zero exit code)."""
        raise NotImplementedError("not implemented")

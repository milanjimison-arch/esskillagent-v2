"""Base check strategy interface.

FR-012: Defines the CheckStrategy ABC that all concrete check strategies
(LocalCheckStrategy, CICheckStrategy) must implement.

Strategy-based polymorphism replaces v1's dict mutation pattern (Pitfall #1).
"""

import abc


class CheckStrategy(abc.ABC):
    """Abstract base class for TDD phase verification strategies.

    Concrete implementations must provide both RED-phase and GREEN-phase
    verification logic. The two methods correspond to the two TDD phases:

    - tests_must_fail: Verifies the RED phase — newly written tests fail
      before implementation exists.
    - tests_must_pass: Verifies the GREEN phase — tests pass after
      implementation is complete.
    """

    @abc.abstractmethod
    def tests_must_fail(self, task_id: str, command: str) -> bool:
        """Verify the RED phase: the given test command must fail.

        Args:
            task_id: Unique identifier for the TDD task (e.g. "T005").
            command: Shell command to execute the test suite
                     (e.g. "pytest tests/unit/checks/test_base.py").

        Returns:
            True if the tests failed as expected (RED phase confirmed),
            False if the tests unexpectedly passed.
        """

    @abc.abstractmethod
    def tests_must_pass(self, task_id: str, command: str) -> bool:
        """Verify the GREEN phase: the given test command must pass.

        Args:
            task_id: Unique identifier for the TDD task (e.g. "T005").
            command: Shell command to execute the test suite
                     (e.g. "pytest tests/unit/checks/test_base.py").

        Returns:
            True if the tests passed as expected (GREEN phase confirmed),
            False if the tests are still failing.
        """

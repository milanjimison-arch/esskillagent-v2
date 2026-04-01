"""Unit tests for CheckStrategy ABC.

FR-012: System MUST provide a CheckStrategy abstract interface
with `tests_must_fail` and `tests_must_pass` methods.

SPEC-030 / SPEC-031: Both LocalCheckStrategy and CICheckStrategy
must satisfy this common interface for RED/GREEN TDD phases.

All tests in this module are RED-phase tests — they MUST FAIL until
orchestrator/checks/base.py implements CheckStrategy.
"""

import inspect
import pytest

from orchestrator.checks.base import CheckStrategy


class TestCheckStrategyIsABC:
    """FR-012: CheckStrategy MUST be an abstract base class."""

    def test_check_strategy_inherits_from_abc(self):
        """CheckStrategy must be registered as an ABC via abc.ABC or ABCMeta."""
        import abc
        assert issubclass(CheckStrategy, abc.ABC), (
            "CheckStrategy must subclass abc.ABC"
        )

    def test_check_strategy_cannot_be_instantiated_directly(self):
        """Attempting to instantiate CheckStrategy directly MUST raise TypeError."""
        with pytest.raises(TypeError):
            CheckStrategy()

    def test_check_strategy_is_a_class(self):
        """CheckStrategy must be a class, not a function or module."""
        assert inspect.isclass(CheckStrategy)


class TestCheckStrategyAbstractMethods:
    """FR-012: CheckStrategy MUST declare tests_must_fail and tests_must_pass
    as abstract methods."""

    def test_tests_must_fail_is_abstract(self):
        """tests_must_fail MUST be declared as an abstract method."""
        assert "tests_must_fail" in CheckStrategy.__abstractmethods__, (
            "tests_must_fail must be listed in __abstractmethods__"
        )

    def test_tests_must_pass_is_abstract(self):
        """tests_must_pass MUST be declared as an abstract method."""
        assert "tests_must_pass" in CheckStrategy.__abstractmethods__, (
            "tests_must_pass must be listed in __abstractmethods__"
        )

    def test_tests_must_fail_method_exists_on_class(self):
        """tests_must_fail must be defined on CheckStrategy."""
        assert hasattr(CheckStrategy, "tests_must_fail"), (
            "CheckStrategy must have a tests_must_fail method"
        )

    def test_tests_must_pass_method_exists_on_class(self):
        """tests_must_pass must be defined on CheckStrategy."""
        assert hasattr(CheckStrategy, "tests_must_pass"), (
            "CheckStrategy must have a tests_must_pass method"
        )

    def test_both_methods_are_in_abstractmethods(self):
        """Both abstract methods must be present; no unexpected extras."""
        expected = {"tests_must_fail", "tests_must_pass"}
        declared = set(CheckStrategy.__abstractmethods__)
        assert expected == declared, (
            f"Expected abstract methods {expected}, got {declared}"
        )


class TestCheckStrategyMethodSignatures:
    """The abstract methods must have the expected callable signatures."""

    def test_tests_must_fail_accepts_task_id_and_command(self):
        """tests_must_fail(task_id, command) — verifies RED phase.

        Signature: tests_must_fail(self, task_id: str, command: str) -> bool
        """
        sig = inspect.signature(CheckStrategy.tests_must_fail)
        params = list(sig.parameters.keys())
        assert "task_id" in params, (
            "tests_must_fail must accept a 'task_id' parameter"
        )
        assert "command" in params, (
            "tests_must_fail must accept a 'command' parameter"
        )

    def test_tests_must_pass_accepts_task_id_and_command(self):
        """tests_must_pass(task_id, command) — verifies GREEN phase.

        Signature: tests_must_pass(self, task_id: str, command: str) -> bool
        """
        sig = inspect.signature(CheckStrategy.tests_must_pass)
        params = list(sig.parameters.keys())
        assert "task_id" in params, (
            "tests_must_pass must accept a 'task_id' parameter"
        )
        assert "command" in params, (
            "tests_must_pass must accept a 'command' parameter"
        )

    def test_tests_must_fail_is_callable(self):
        """tests_must_fail must be a callable (method)."""
        assert callable(CheckStrategy.tests_must_fail)

    def test_tests_must_pass_is_callable(self):
        """tests_must_pass must be a callable (method)."""
        assert callable(CheckStrategy.tests_must_pass)


class TestConcreteSubclassCanBeInstantiated:
    """A concrete subclass implementing both abstract methods MUST be
    instantiable — this validates the ABC contract is correctly defined."""

    def test_concrete_subclass_implementing_both_methods_can_be_instantiated(self):
        """A subclass that overrides both abstract methods should instantiate
        without raising TypeError."""

        class ConcreteStrategy(CheckStrategy):
            def tests_must_fail(self, task_id: str, command: str) -> bool:
                return True

            def tests_must_pass(self, task_id: str, command: str) -> bool:
                return True

        instance = ConcreteStrategy()
        assert instance is not None

    def test_partial_subclass_missing_tests_must_fail_cannot_be_instantiated(self):
        """A subclass that only implements tests_must_pass (not tests_must_fail)
        MUST still raise TypeError on instantiation."""

        class PartialStrategy(CheckStrategy):
            def tests_must_pass(self, task_id: str, command: str) -> bool:
                return True

        with pytest.raises(TypeError):
            PartialStrategy()

    def test_partial_subclass_missing_tests_must_pass_cannot_be_instantiated(self):
        """A subclass that only implements tests_must_fail (not tests_must_pass)
        MUST still raise TypeError on instantiation."""

        class PartialStrategy(CheckStrategy):
            def tests_must_fail(self, task_id: str, command: str) -> bool:
                return True

        with pytest.raises(TypeError):
            PartialStrategy()

    def test_concrete_subclass_tests_must_fail_returns_value(self):
        """tests_must_fail on a concrete instance must be callable and
        return a value (verifies method is truly overridden, not abstract)."""

        class ConcreteStrategy(CheckStrategy):
            def tests_must_fail(self, task_id: str, command: str) -> bool:
                return False

            def tests_must_pass(self, task_id: str, command: str) -> bool:
                return True

        strategy = ConcreteStrategy()
        result = strategy.tests_must_fail(task_id="T001", command="pytest tests/")
        assert result is False

    def test_concrete_subclass_tests_must_pass_returns_value(self):
        """tests_must_pass on a concrete instance must be callable and
        return a value (verifies method is truly overridden, not abstract)."""

        class ConcreteStrategy(CheckStrategy):
            def tests_must_fail(self, task_id: str, command: str) -> bool:
                return False

            def tests_must_pass(self, task_id: str, command: str) -> bool:
                return True

        strategy = ConcreteStrategy()
        result = strategy.tests_must_pass(task_id="T001", command="pytest tests/")
        assert result is True

    def test_concrete_subclass_is_instance_of_check_strategy(self):
        """Instances of concrete subclasses must satisfy isinstance check
        against CheckStrategy (Liskov substitution principle)."""

        class ConcreteStrategy(CheckStrategy):
            def tests_must_fail(self, task_id: str, command: str) -> bool:
                return True

            def tests_must_pass(self, task_id: str, command: str) -> bool:
                return True

        instance = ConcreteStrategy()
        assert isinstance(instance, CheckStrategy)

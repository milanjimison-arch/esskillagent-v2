"""Unit tests for orchestrator/tdd/validator.py — parallel task validator.

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/tdd/validator.py provides a complete implementation.

Requirements covered:
  FR-VALIDATOR-01: ParallelTaskValidator class exists and is importable.
  FR-VALIDATOR-02: validate_tasks returns a ValidationResult.
  FR-VALIDATOR-03: detect_conflicts returns conflicting file_path values.
  FR-VALIDATOR-04: No file_path conflicts → parallel mode, is_parallel_safe=True.
  FR-VALIDATOR-05: Any file_path conflict → serial mode, is_parallel_safe=False.
  FR-VALIDATOR-06: Edge cases — empty list, single task, tasks without file_path.
  FR-VALIDATOR-07: ValidationResult fields: is_parallel_safe, conflicts, execution_mode.

Test areas:
  1.  validate_tasks: empty list → parallel safe, no conflicts.
  2.  validate_tasks: single task with file_path → parallel safe.
  3.  validate_tasks: two tasks with different file_paths → parallel safe.
  4.  validate_tasks: two tasks with same file_path → serial, not safe.
  5.  validate_tasks: three tasks — one pair conflicts → serial, not safe.
  6.  validate_tasks: execution_mode is "parallel" when safe.
  7.  validate_tasks: execution_mode is "serial" when not safe.
  8.  validate_tasks: conflicts list contains the duplicate file_path.
  9.  validate_tasks: conflicts list is empty when no conflicts.
  10. validate_tasks: tasks without file_path (None) are ignored in conflict detection.
  11. validate_tasks: only tasks with file_path=None, no conflicts → parallel safe.
  12. validate_tasks: mixed — some with file_path, some without, no duplicates → parallel.
  13. validate_tasks: three tasks all sharing one file_path → serial, conflict listed once.
  14. validate_tasks: two separate conflict pairs → both conflicting paths in conflicts.
  15. validate_tasks: returns a ValidationResult instance.
  16. detect_conflicts: empty list → empty conflict list.
  17. detect_conflicts: single task → empty conflict list.
  18. detect_conflicts: two tasks same file_path → returns that path.
  19. detect_conflicts: two tasks different file_paths → empty list.
  20. detect_conflicts: tasks supplied as dicts with "file_path" key → works.
  21. detect_conflicts: tasks supplied as objects with file_path attribute → works.
  22. detect_conflicts: None file_path values not treated as conflicts.
  23. detect_conflicts: large list (100 tasks, no duplicates) → empty list.
  24. detect_conflicts: large list (100 tasks, one duplicate) → one conflict path.
  25. ValidationResult: is_parallel_safe default is bool type.
  26. ValidationResult: conflicts default is a list.
  27. ValidationResult: execution_mode is exactly "parallel" or "serial", nothing else.
"""

from __future__ import annotations

import pytest

from orchestrator.tdd.validator import ParallelTaskValidator, ValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Task:
    """Minimal task object with a file_path attribute."""

    def __init__(self, file_path: str | None) -> None:
        self.file_path = file_path


def _task(file_path: str | None = None) -> _Task:
    return _Task(file_path=file_path)


def _dict_task(file_path: str | None = None) -> dict:
    return {"file_path": file_path}


# ===========================================================================
# 1. ValidationResult dataclass
# ===========================================================================


class TestValidationResult:
    """FR-VALIDATOR-07: ValidationResult has correct fields and types."""

    def test_is_parallel_safe_is_bool(self):
        """FR-VALIDATOR-07: is_parallel_safe field exists and is a bool."""
        result = ValidationResult(is_parallel_safe=True, conflicts=[], execution_mode="parallel")
        assert result.is_parallel_safe is True

    def test_conflicts_is_list(self):
        """FR-VALIDATOR-07: conflicts field exists and is a list."""
        result = ValidationResult(is_parallel_safe=True, conflicts=[], execution_mode="parallel")
        assert isinstance(result.conflicts, list)

    def test_execution_mode_is_str(self):
        """FR-VALIDATOR-07: execution_mode field exists and is a string."""
        result = ValidationResult(is_parallel_safe=True, conflicts=[], execution_mode="parallel")
        assert isinstance(result.execution_mode, str)


# ===========================================================================
# 2. validate_tasks — no-conflict (parallel) paths
# ===========================================================================


class TestValidateTasksParallel:
    """FR-VALIDATOR-02, FR-VALIDATOR-04: safe cases return parallel mode."""

    def setup_method(self):
        self.validator = ParallelTaskValidator()

    def test_empty_list_is_parallel_safe(self):
        """FR-VALIDATOR-04: empty task list has no conflicts — parallel safe."""
        result = self.validator.validate_tasks([])
        assert result.is_parallel_safe is True

    def test_empty_list_execution_mode_is_parallel(self):
        """FR-VALIDATOR-06: empty task list produces execution_mode 'parallel'."""
        result = self.validator.validate_tasks([])
        assert result.execution_mode == "parallel"

    def test_empty_list_conflicts_is_empty(self):
        """FR-VALIDATOR-06: empty task list produces no conflicts."""
        result = self.validator.validate_tasks([])
        assert result.conflicts == []

    def test_single_task_with_file_path_is_parallel_safe(self):
        """FR-VALIDATOR-04: one task cannot conflict with itself."""
        result = self.validator.validate_tasks([_task("orchestrator/config.py")])
        assert result.is_parallel_safe is True

    def test_single_task_execution_mode_is_parallel(self):
        """FR-VALIDATOR-04: single task produces execution_mode 'parallel'."""
        result = self.validator.validate_tasks([_task("file.py")])
        assert result.execution_mode == "parallel"

    def test_two_tasks_different_file_paths_are_parallel_safe(self):
        """FR-VALIDATOR-04: two tasks writing different files — no conflict."""
        tasks = [_task("module/a.py"), _task("module/b.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.is_parallel_safe is True

    def test_two_tasks_different_paths_execution_mode_parallel(self):
        """FR-VALIDATOR-04: two non-conflicting tasks → execution_mode 'parallel'."""
        tasks = [_task("x.py"), _task("y.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.execution_mode == "parallel"

    def test_two_tasks_different_paths_conflicts_empty(self):
        """FR-VALIDATOR-04: two non-conflicting tasks → conflicts == []."""
        tasks = [_task("x.py"), _task("y.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.conflicts == []

    def test_tasks_with_none_file_path_only_parallel_safe(self):
        """FR-VALIDATOR-06: tasks with file_path=None cannot conflict."""
        tasks = [_task(None), _task(None)]
        result = self.validator.validate_tasks(tasks)
        assert result.is_parallel_safe is True

    def test_tasks_with_none_file_path_execution_mode_parallel(self):
        """FR-VALIDATOR-06: tasks with file_path=None → execution_mode 'parallel'."""
        tasks = [_task(None), _task(None), _task(None)]
        result = self.validator.validate_tasks(tasks)
        assert result.execution_mode == "parallel"

    def test_mixed_none_and_distinct_paths_parallel_safe(self):
        """FR-VALIDATOR-06: None file_path + distinct file paths → parallel."""
        tasks = [_task(None), _task("a.py"), _task("b.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.is_parallel_safe is True

    def test_returns_validation_result_instance(self):
        """FR-VALIDATOR-02: validate_tasks returns a ValidationResult object."""
        result = self.validator.validate_tasks([])
        assert isinstance(result, ValidationResult)


# ===========================================================================
# 3. validate_tasks — conflict (serial) paths
# ===========================================================================


class TestValidateTasksSerial:
    """FR-VALIDATOR-02, FR-VALIDATOR-05: conflicting cases return serial mode."""

    def setup_method(self):
        self.validator = ParallelTaskValidator()

    def test_two_tasks_same_file_path_not_parallel_safe(self):
        """FR-VALIDATOR-05: two tasks sharing a file_path → is_parallel_safe=False."""
        tasks = [_task("shared/module.py"), _task("shared/module.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.is_parallel_safe is False

    def test_two_tasks_same_file_path_execution_mode_serial(self):
        """FR-VALIDATOR-05: conflict → execution_mode == 'serial'."""
        tasks = [_task("shared/module.py"), _task("shared/module.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.execution_mode == "serial"

    def test_two_tasks_same_file_path_conflict_listed(self):
        """FR-VALIDATOR-05: conflicting file_path appears in result.conflicts."""
        tasks = [_task("shared/module.py"), _task("shared/module.py")]
        result = self.validator.validate_tasks(tasks)
        assert "shared/module.py" in result.conflicts

    def test_three_tasks_one_conflict_pair_serial(self):
        """FR-VALIDATOR-05: three tasks where two share a path → serial."""
        tasks = [_task("a.py"), _task("b.py"), _task("a.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.is_parallel_safe is False
        assert result.execution_mode == "serial"

    def test_three_tasks_one_conflict_path_in_conflicts(self):
        """FR-VALIDATOR-05: conflicting path is recorded even among non-conflicts."""
        tasks = [_task("a.py"), _task("b.py"), _task("a.py")]
        result = self.validator.validate_tasks(tasks)
        assert "a.py" in result.conflicts
        assert "b.py" not in result.conflicts

    def test_three_tasks_all_same_path_conflict_listed_once(self):
        """FR-VALIDATOR-05: when three tasks share one path, it appears once in conflicts."""
        tasks = [_task("dup.py"), _task("dup.py"), _task("dup.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.conflicts.count("dup.py") == 1

    def test_two_separate_conflict_pairs_both_listed(self):
        """FR-VALIDATOR-05: two independent conflict pairs → both paths in conflicts."""
        tasks = [
            _task("alpha.py"),
            _task("beta.py"),
            _task("alpha.py"),
            _task("beta.py"),
        ]
        result = self.validator.validate_tasks(tasks)
        assert "alpha.py" in result.conflicts
        assert "beta.py" in result.conflicts

    def test_conflict_with_none_file_path_not_triggered(self):
        """FR-VALIDATOR-06: None file_path values do not count as conflicts
        even when multiple tasks have file_path=None."""
        tasks = [_task(None), _task(None), _task("real.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.is_parallel_safe is True

    def test_execution_mode_is_serial_not_other_string(self):
        """FR-VALIDATOR-05: execution_mode for conflict is exactly 'serial'."""
        tasks = [_task("x.py"), _task("x.py")]
        result = self.validator.validate_tasks(tasks)
        assert result.execution_mode == "serial"
        assert result.execution_mode != "SERIAL"
        assert result.execution_mode != "Serial"


# ===========================================================================
# 4. detect_conflicts
# ===========================================================================


class TestDetectConflicts:
    """FR-VALIDATOR-03: detect_conflicts returns only conflicting file paths."""

    def setup_method(self):
        self.validator = ParallelTaskValidator()

    def test_empty_list_returns_empty(self):
        """FR-VALIDATOR-03: no tasks → no conflicts."""
        assert self.validator.detect_conflicts([]) == []

    def test_single_task_returns_empty(self):
        """FR-VALIDATOR-03: one task cannot conflict with itself."""
        assert self.validator.detect_conflicts([_task("a.py")]) == []

    def test_two_different_paths_returns_empty(self):
        """FR-VALIDATOR-03: two tasks with unique paths → no conflicts."""
        tasks = [_task("a.py"), _task("b.py")]
        assert self.validator.detect_conflicts(tasks) == []

    def test_two_same_paths_returns_that_path(self):
        """FR-VALIDATOR-03: two tasks sharing a path → that path returned."""
        tasks = [_task("dup.py"), _task("dup.py")]
        conflicts = self.validator.detect_conflicts(tasks)
        assert "dup.py" in conflicts

    def test_three_tasks_one_duplicate_returns_one_conflict(self):
        """FR-VALIDATOR-03: three tasks, two sharing a path → one conflict entry."""
        tasks = [_task("a.py"), _task("b.py"), _task("a.py")]
        conflicts = self.validator.detect_conflicts(tasks)
        assert "a.py" in conflicts
        assert "b.py" not in conflicts

    def test_duplicate_path_listed_once_even_if_three_tasks_share_it(self):
        """FR-VALIDATOR-03: a path appearing in 3 tasks is listed once, not thrice."""
        tasks = [_task("dup.py")] * 3
        conflicts = self.validator.detect_conflicts(tasks)
        assert conflicts.count("dup.py") == 1

    def test_none_file_paths_not_returned_as_conflicts(self):
        """FR-VALIDATOR-06: None values are excluded from conflict detection."""
        tasks = [_task(None), _task(None)]
        assert self.validator.detect_conflicts(tasks) == []

    def test_dict_tasks_with_file_path_key(self):
        """FR-VALIDATOR-06: tasks supplied as dicts also work."""
        tasks = [_dict_task("shared.py"), _dict_task("shared.py")]
        conflicts = self.validator.detect_conflicts(tasks)
        assert "shared.py" in conflicts

    def test_dict_tasks_no_conflict(self):
        """FR-VALIDATOR-06: dict tasks with unique paths → no conflicts."""
        tasks = [_dict_task("a.py"), _dict_task("b.py")]
        assert self.validator.detect_conflicts(tasks) == []

    def test_dict_tasks_none_file_path_not_conflict(self):
        """FR-VALIDATOR-06: dict tasks with None file_path not treated as conflict."""
        tasks = [_dict_task(None), _dict_task(None)]
        assert self.validator.detect_conflicts(tasks) == []

    def test_large_list_no_duplicates_returns_empty(self):
        """FR-VALIDATOR-06: 100 tasks with unique paths → no conflicts."""
        tasks = [_task(f"module_{i}.py") for i in range(100)]
        assert self.validator.detect_conflicts(tasks) == []

    def test_large_list_one_duplicate_returns_one_path(self):
        """FR-VALIDATOR-06: 100 unique tasks + one duplicate → one conflict path."""
        tasks = [_task(f"module_{i}.py") for i in range(99)]
        tasks.append(_task("module_0.py"))  # duplicate of the first
        conflicts = self.validator.detect_conflicts(tasks)
        assert "module_0.py" in conflicts
        assert len(conflicts) == 1

    def test_returns_list_type(self):
        """FR-VALIDATOR-03: detect_conflicts always returns a list."""
        result = self.validator.detect_conflicts([])
        assert isinstance(result, list)


# ===========================================================================
# 5. Integration: validate_tasks + detect_conflicts consistency
# ===========================================================================


class TestValidatorIntegration:
    """FR-VALIDATOR-02..05: validate_tasks and detect_conflicts are consistent."""

    def setup_method(self):
        self.validator = ParallelTaskValidator()

    def test_conflicts_from_validate_match_detect_conflicts(self):
        """FR-VALIDATOR-03,05: result.conflicts equals detect_conflicts output."""
        tasks = [_task("shared.py"), _task("shared.py"), _task("other.py")]
        result = self.validator.validate_tasks(tasks)
        direct_conflicts = self.validator.detect_conflicts(tasks)
        assert sorted(result.conflicts) == sorted(direct_conflicts)

    def test_no_conflicts_validate_and_detect_both_empty(self):
        """FR-VALIDATOR-04,03: when no conflicts, both sources agree."""
        tasks = [_task("a.py"), _task("b.py")]
        result = self.validator.validate_tasks(tasks)
        direct = self.validator.detect_conflicts(tasks)
        assert result.conflicts == []
        assert direct == []
        assert result.is_parallel_safe is True

    def test_serial_fallback_when_detect_conflicts_non_empty(self):
        """FR-VALIDATOR-05: whenever detect_conflicts returns paths,
        validate_tasks must return execution_mode='serial'."""
        tasks = [_task("collision.py"), _task("safe.py"), _task("collision.py")]
        direct_conflicts = self.validator.detect_conflicts(tasks)
        assert len(direct_conflicts) > 0

        result = self.validator.validate_tasks(tasks)
        assert result.execution_mode == "serial"
        assert result.is_parallel_safe is False

    def test_execution_mode_exactly_one_of_two_values(self):
        """FR-VALIDATOR-04,05: execution_mode is always 'parallel' or 'serial'."""
        for tasks in [
            [],
            [_task("a.py")],
            [_task("a.py"), _task("b.py")],
            [_task("a.py"), _task("a.py")],
        ]:
            result = self.validator.validate_tasks(tasks)
            assert result.execution_mode in ("parallel", "serial"), (
                f"Unexpected execution_mode {result.execution_mode!r} for {tasks}"
            )

    def test_is_parallel_safe_false_iff_execution_mode_serial(self):
        """FR-VALIDATOR-04,05: is_parallel_safe and execution_mode are in sync."""
        conflict_tasks = [_task("x.py"), _task("x.py")]
        safe_tasks = [_task("x.py"), _task("y.py")]

        conflict_result = self.validator.validate_tasks(conflict_tasks)
        assert conflict_result.is_parallel_safe is False
        assert conflict_result.execution_mode == "serial"

        safe_result = self.validator.validate_tasks(safe_tasks)
        assert safe_result.is_parallel_safe is True
        assert safe_result.execution_mode == "parallel"

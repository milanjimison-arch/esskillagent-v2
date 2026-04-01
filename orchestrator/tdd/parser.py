"""Task parser and parallel validator for the TDD pipeline.

FR-021: Em-dash primary strategy for task line parsing.
FR-022: [P] without file_path rejection.
FR-023: "in src/" fallback with non-canonical warning.
FR-024: Non-canonical format warning with line number.
FR-025: Phase grouping and validate_parallel_group() with overlap detection.
"""
from __future__ import annotations


def parse_tasks(task_text: str) -> object:
    """Parse a tasks markdown block into structured task objects with phase groups.

    Args:
        task_text: Raw markdown text containing task lines.

    Returns:
        A ParseResult containing tasks and any warnings/errors.

    Raises:
        ValueError: When a [P] task is missing a file_path.
    """
    raise NotImplementedError("parse_tasks is not yet implemented")


def validate_parallel_group(tasks: list) -> list:
    """Validate a group of parallel tasks for file_path overlap.

    Detects overlapping file_path values within a [P] group and demotes
    the conflicting tasks to serial execution.

    Args:
        tasks: A list of Task objects all marked with parallel=True.

    Returns:
        A list of Task objects where overlapping tasks have parallel=False.
    """
    raise NotImplementedError("validate_parallel_group is not yet implemented")

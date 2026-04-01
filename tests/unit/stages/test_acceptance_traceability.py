"""RED-phase tests for traceability matrix generation in the acceptance stage.

Covers:
  FR-TRACE-001: generate_traceability_matrix maps each FR to its implementing
                tasks and corresponding tests.
  FR-TRACE-002: FRs with no implementing task or no test are flagged as
                "unimplemented" in the acceptance report.
  FR-TRACE-003: The traceability matrix can be output as a structured report
                (JSON-serialisable dict and Markdown).

User Story 3 (Acceptance Stage with Traceability) acceptance scenarios:
  1. Given completed artifacts, when acceptance stage runs, a traceability
     matrix is generated mapping each FR to its tasks and tests.
  2. Given a matrix where FR-005 has no implementing task, FR-005 is flagged
     as "unimplemented".
  3. Given all FRs covered and all tests pass, acceptance stage reports success
     with a full traceability report.

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/stages/acceptance.py provides concrete implementations of
TraceabilityEntry, TraceabilityMatrix, and generate_traceability_matrix.
"""

from __future__ import annotations

import json

import pytest

from orchestrator.stages.acceptance import (
    ACCEPTANCE_SUB_STEPS,
    AcceptanceStage,
    TraceabilityEntry,
    TraceabilityMatrix,
    generate_traceability_matrix,
)


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _full_frs() -> list[str]:
    """A representative list of FR identifiers."""
    return ["FR-001", "FR-002", "FR-003", "FR-004", "FR-005"]


def _full_task_map() -> dict[str, list[str]]:
    """Every FR has at least one implementing task."""
    return {
        "FR-001": ["task-spec-generation"],
        "FR-002": ["task-checkpoint-persistence"],
        "FR-003": ["task-report-output"],
        "FR-004": ["task-review-gate"],
        "FR-005": ["task-traceability-matrix"],
    }


def _full_test_map() -> dict[str, list[str]]:
    """Every FR has at least one corresponding test."""
    return {
        "FR-001": ["tests/unit/stages/test_spec.py::test_spec_run"],
        "FR-002": ["tests/unit/stages/test_base.py::test_checkpoint_persisted"],
        "FR-003": ["tests/unit/stages/test_acceptance_traceability.py::test_to_dict"],
        "FR-004": ["tests/unit/stages/test_base.py::test_review_gate"],
        "FR-005": ["tests/unit/stages/test_acceptance_traceability.py::test_unimplemented"],
    }


def _get_entry(matrix_dict: dict, fr_id: str) -> dict:
    """Return the matrix entry for fr_id; assert presence with a clear message."""
    assert fr_id in matrix_dict, (
        f"FR '{fr_id}' must appear in the traceability matrix, "
        f"but it was not found. Matrix keys: {list(matrix_dict.keys())}"
    )
    return matrix_dict[fr_id]


# ---------------------------------------------------------------------------
# TraceabilityEntry — basic construction and fields
# ---------------------------------------------------------------------------


class TestTraceabilityEntry:
    """FR-TRACE-001: TraceabilityEntry must hold fr_id, tasks, and tests."""

    def test_FR_TRACE_001_entry_stores_fr_id(self):
        """FR-TRACE-001: TraceabilityEntry MUST expose the FR identifier."""
        entry = TraceabilityEntry(
            fr_id="FR-001",
            tasks=["task-a"],
            tests=["tests/test_a.py"],
        )
        assert entry.fr_id == "FR-001"

    def test_FR_TRACE_001_entry_stores_tasks_list(self):
        """FR-TRACE-001: TraceabilityEntry MUST expose the list of implementing tasks."""
        entry = TraceabilityEntry(
            fr_id="FR-002",
            tasks=["task-checkpoint", "task-persist"],
            tests=["tests/test_checkpoint.py"],
        )
        assert entry.tasks == ["task-checkpoint", "task-persist"]

    def test_FR_TRACE_001_entry_stores_tests_list(self):
        """FR-TRACE-001: TraceabilityEntry MUST expose the list of corresponding tests."""
        entry = TraceabilityEntry(
            fr_id="FR-003",
            tasks=["task-report"],
            tests=["tests/test_report.py::test_json", "tests/test_report.py::test_md"],
        )
        assert entry.tests == [
            "tests/test_report.py::test_json",
            "tests/test_report.py::test_md",
        ]

    def test_FR_TRACE_001_entry_accepts_empty_tasks(self):
        """FR-TRACE-001: TraceabilityEntry MUST accept an empty tasks list (unimplemented FR)."""
        entry = TraceabilityEntry(fr_id="FR-999", tasks=[], tests=[])
        assert entry.tasks == []

    def test_FR_TRACE_001_entry_accepts_empty_tests(self):
        """FR-TRACE-001: TraceabilityEntry with no tests must not raise on construction."""
        entry = TraceabilityEntry(fr_id="FR-999", tasks=["task-x"], tests=[])
        assert entry.tests == []

    def test_FR_TRACE_001_entry_fr_id_is_string(self):
        """FR-TRACE-001: fr_id MUST be a string."""
        entry = TraceabilityEntry(fr_id="FR-007", tasks=[], tests=[])
        assert isinstance(entry.fr_id, str)

    def test_FR_TRACE_001_entry_tasks_is_list(self):
        """FR-TRACE-001: tasks MUST be a list."""
        entry = TraceabilityEntry(fr_id="FR-007", tasks=["t1"], tests=[])
        assert isinstance(entry.tasks, list)

    def test_FR_TRACE_001_entry_tests_is_list(self):
        """FR-TRACE-001: tests MUST be a list."""
        entry = TraceabilityEntry(fr_id="FR-007", tasks=[], tests=["test_x.py"])
        assert isinstance(entry.tests, list)

    def test_FR_TRACE_001_entry_preserves_fr_id_value(self):
        """FR-TRACE-001: fr_id MUST equal the value passed to the constructor."""
        entry = TraceabilityEntry(fr_id="FR-042", tasks=[], tests=[])
        assert entry.fr_id == "FR-042", (
            f"fr_id must be 'FR-042', got {entry.fr_id!r}"
        )

    def test_FR_TRACE_001_entry_preserves_tasks_values(self):
        """FR-TRACE-001: tasks MUST equal the list passed to the constructor."""
        tasks = ["task-alpha", "task-beta"]
        entry = TraceabilityEntry(fr_id="FR-001", tasks=tasks, tests=[])
        assert entry.tasks == tasks, (
            f"tasks must be {tasks!r}, got {entry.tasks!r}"
        )

    def test_FR_TRACE_001_entry_preserves_tests_values(self):
        """FR-TRACE-001: tests MUST equal the list passed to the constructor."""
        tests = ["tests/test_x.py", "tests/test_y.py"]
        entry = TraceabilityEntry(fr_id="FR-001", tasks=[], tests=tests)
        assert entry.tests == tests, (
            f"tests must be {tests!r}, got {entry.tests!r}"
        )


# ---------------------------------------------------------------------------
# generate_traceability_matrix — happy path
# ---------------------------------------------------------------------------


class TestGenerateTraceabilityMatrixHappyPath:
    """FR-TRACE-001: generate_traceability_matrix maps FRs → tasks → tests."""

    def test_FR_TRACE_001_returns_traceability_matrix_instance(self):
        """FR-TRACE-001: generate_traceability_matrix MUST return a TraceabilityMatrix."""
        matrix = generate_traceability_matrix(
            frs=_full_frs(),
            task_map=_full_task_map(),
            test_map=_full_test_map(),
        )
        assert isinstance(matrix, TraceabilityMatrix)

    def test_FR_TRACE_001_matrix_covers_all_frs(self):
        """FR-TRACE-001: The returned matrix MUST contain an entry for every FR provided."""
        frs = _full_frs()
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map=_full_task_map(),
            test_map=_full_test_map(),
        )
        matrix_dict = matrix.to_dict()
        for fr in frs:
            assert fr in matrix_dict, (
                f"FR '{fr}' must appear in the traceability matrix, "
                f"but it was not found. Matrix keys: {list(matrix_dict.keys())}"
            )

    def test_FR_TRACE_001_entry_tasks_match_task_map(self):
        """FR-TRACE-001: Each FR's tasks in the matrix MUST match the task_map input."""
        task_map = _full_task_map()
        matrix = generate_traceability_matrix(
            frs=_full_frs(),
            task_map=task_map,
            test_map=_full_test_map(),
        )
        matrix_dict = matrix.to_dict()
        for fr, expected_tasks in task_map.items():
            entry = _get_entry(matrix_dict, fr)
            entry_tasks = entry.get("tasks")
            assert entry_tasks == expected_tasks, (
                f"Tasks for {fr} must be {expected_tasks!r}, got {entry_tasks!r}"
            )

    def test_FR_TRACE_001_entry_tests_match_test_map(self):
        """FR-TRACE-001: Each FR's tests in the matrix MUST match the test_map input."""
        test_map = _full_test_map()
        matrix = generate_traceability_matrix(
            frs=_full_frs(),
            task_map=_full_task_map(),
            test_map=test_map,
        )
        matrix_dict = matrix.to_dict()
        for fr, expected_tests in test_map.items():
            entry = _get_entry(matrix_dict, fr)
            entry_tests = entry.get("tests")
            assert entry_tests == expected_tests, (
                f"Tests for {fr} must be {expected_tests!r}, got {entry_tests!r}"
            )

    def test_FR_TRACE_001_matrix_entry_count_equals_fr_count(self):
        """FR-TRACE-001: The matrix MUST have exactly as many entries as there are FRs."""
        frs = _full_frs()
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map=_full_task_map(),
            test_map=_full_test_map(),
        )
        matrix_dict = matrix.to_dict()
        assert len(matrix_dict) == len(frs), (
            f"Expected {len(frs)} matrix entries, got {len(matrix_dict)}"
        )

    def test_FR_TRACE_001_preserves_fr_order(self):
        """FR-TRACE-001: The matrix MUST preserve the input FR ordering."""
        frs = ["FR-003", "FR-001", "FR-002"]
        task_map = {fr: ["task"] for fr in frs}
        test_map = {fr: ["test.py"] for fr in frs}
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map=task_map,
            test_map=test_map,
        )
        matrix_dict = matrix.to_dict()
        assert list(matrix_dict.keys()) == frs, (
            f"Matrix must preserve FR order {frs}, got {list(matrix_dict.keys())}"
        )


# ---------------------------------------------------------------------------
# generate_traceability_matrix — unimplemented FR detection (FR-TRACE-002)
# ---------------------------------------------------------------------------


class TestGenerateTraceabilityMatrixUnimplemented:
    """FR-TRACE-002: FRs with no task or no test are flagged as unimplemented."""

    def test_FR_TRACE_002_fr_with_no_task_is_unimplemented(self):
        """FR-TRACE-002: An FR absent from task_map MUST appear in unimplemented_frs()."""
        frs = ["FR-001", "FR-002", "FR-005"]
        # FR-005 intentionally has no task
        task_map = {"FR-001": ["task-a"], "FR-002": ["task-b"]}
        test_map = {
            "FR-001": ["test_a.py"],
            "FR-002": ["test_b.py"],
            "FR-005": ["test_e.py"],
        }
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map=task_map,
            test_map=test_map,
        )
        unimplemented = matrix.unimplemented_frs()
        assert "FR-005" in unimplemented, (
            "FR-005 has no implementing task and MUST be in unimplemented_frs(), "
            f"got: {unimplemented}"
        )

    def test_FR_TRACE_002_fr_with_no_test_is_unimplemented(self):
        """FR-TRACE-002: An FR absent from test_map MUST appear in unimplemented_frs()."""
        frs = ["FR-001", "FR-002", "FR-005"]
        task_map = {
            "FR-001": ["task-a"],
            "FR-002": ["task-b"],
            "FR-005": ["task-e"],  # has a task but no test
        }
        test_map = {"FR-001": ["test_a.py"], "FR-002": ["test_b.py"]}
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map=task_map,
            test_map=test_map,
        )
        unimplemented = matrix.unimplemented_frs()
        assert "FR-005" in unimplemented, (
            "FR-005 has no corresponding test and MUST be in unimplemented_frs(), "
            f"got: {unimplemented}"
        )

    def test_FR_TRACE_002_fr_with_empty_task_list_is_unimplemented(self):
        """FR-TRACE-002: An FR mapped to an empty task list MUST be unimplemented."""
        frs = ["FR-001", "FR-002"]
        task_map = {"FR-001": ["task-a"], "FR-002": []}  # FR-002 empty tasks
        test_map = {"FR-001": ["test_a.py"], "FR-002": ["test_b.py"]}
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map=task_map,
            test_map=test_map,
        )
        unimplemented = matrix.unimplemented_frs()
        assert "FR-002" in unimplemented, (
            "FR-002 has an empty task list and MUST be in unimplemented_frs(), "
            f"got: {unimplemented}"
        )

    def test_FR_TRACE_002_fr_with_empty_test_list_is_unimplemented(self):
        """FR-TRACE-002: An FR mapped to an empty test list MUST be unimplemented."""
        frs = ["FR-001", "FR-002"]
        task_map = {"FR-001": ["task-a"], "FR-002": ["task-b"]}
        test_map = {"FR-001": ["test_a.py"], "FR-002": []}  # FR-002 empty tests
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map=task_map,
            test_map=test_map,
        )
        unimplemented = matrix.unimplemented_frs()
        assert "FR-002" in unimplemented, (
            "FR-002 has an empty test list and MUST be in unimplemented_frs(), "
            f"got: {unimplemented}"
        )

    def test_FR_TRACE_002_fully_covered_fr_is_not_unimplemented(self):
        """FR-TRACE-002: An FR with tasks AND tests MUST NOT appear in unimplemented_frs()."""
        frs = ["FR-001"]
        task_map = {"FR-001": ["task-a"]}
        test_map = {"FR-001": ["test_a.py"]}
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map=task_map,
            test_map=test_map,
        )
        unimplemented = matrix.unimplemented_frs()
        assert "FR-001" not in unimplemented, (
            "FR-001 has both tasks and tests and MUST NOT be in unimplemented_frs(), "
            f"got: {unimplemented}"
        )

    def test_FR_TRACE_002_all_unimplemented_when_maps_empty(self):
        """FR-TRACE-002: When both maps are empty, every FR MUST be unimplemented."""
        frs = ["FR-001", "FR-002", "FR-003"]
        matrix = generate_traceability_matrix(frs=frs, task_map={}, test_map={})
        unimplemented = matrix.unimplemented_frs()
        for fr in frs:
            assert fr in unimplemented, (
                f"{fr} must be unimplemented when maps are empty, "
                f"got unimplemented={unimplemented}"
            )

    def test_FR_TRACE_002_no_unimplemented_when_all_covered(self):
        """FR-TRACE-002: When every FR has tasks and tests, unimplemented_frs() MUST be empty."""
        matrix = generate_traceability_matrix(
            frs=_full_frs(),
            task_map=_full_task_map(),
            test_map=_full_test_map(),
        )
        unimplemented = matrix.unimplemented_frs()
        assert unimplemented == [], (
            f"All FRs are covered; unimplemented_frs() must return [], got {unimplemented}"
        )

    def test_FR_TRACE_002_unimplemented_frs_returns_list(self):
        """FR-TRACE-002: unimplemented_frs() MUST return a list."""
        matrix = generate_traceability_matrix(
            frs=_full_frs(),
            task_map=_full_task_map(),
            test_map=_full_test_map(),
        )
        result = matrix.unimplemented_frs()
        assert isinstance(result, list), (
            f"unimplemented_frs() must return a list, got {type(result)}"
        )

    def test_FR_TRACE_002_unimplemented_frs_contains_only_strings(self):
        """FR-TRACE-002: Every element in unimplemented_frs() MUST be a string FR ID."""
        frs = ["FR-001", "FR-002"]
        task_map = {}
        test_map = {}
        matrix = generate_traceability_matrix(frs=frs, task_map=task_map, test_map=test_map)
        unimplemented = matrix.unimplemented_frs()
        for item in unimplemented:
            assert isinstance(item, str), (
                f"Each unimplemented FR ID must be a string, got {type(item)}: {item!r}"
            )

    def test_FR_TRACE_002_both_task_and_test_missing_flags_once(self):
        """FR-TRACE-002: An FR missing both task and test MUST appear exactly once
        in unimplemented_frs() (no duplicate entries)."""
        frs = ["FR-007"]
        matrix = generate_traceability_matrix(frs=frs, task_map={}, test_map={})
        unimplemented = matrix.unimplemented_frs()
        assert unimplemented.count("FR-007") == 1, (
            "FR-007 missing both task and test must appear exactly once, "
            f"got count={unimplemented.count('FR-007')} in {unimplemented}"
        )


# ---------------------------------------------------------------------------
# TraceabilityMatrix.to_dict — structured JSON-serialisable output (FR-TRACE-003)
# ---------------------------------------------------------------------------


class TestTraceabilityMatrixToDict:
    """FR-TRACE-003: to_dict() must return a JSON-serialisable structured dict."""

    def test_FR_TRACE_003_to_dict_returns_dict(self):
        """FR-TRACE-003: to_dict() MUST return a dict."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_dict()
        assert isinstance(result, dict), (
            f"to_dict() must return a dict, got {type(result)}"
        )

    def test_FR_TRACE_003_to_dict_is_json_serialisable(self):
        """FR-TRACE-003: to_dict() output MUST be serialisable to JSON without error."""
        matrix = generate_traceability_matrix(
            frs=_full_frs(),
            task_map=_full_task_map(),
            test_map=_full_test_map(),
        )
        result = matrix.to_dict()
        # Should not raise
        serialised = json.dumps(result)
        assert isinstance(serialised, str) and len(serialised) > 0

    def test_FR_TRACE_003_to_dict_each_entry_has_tasks_key(self):
        """FR-TRACE-003: Each FR's dict entry MUST contain a 'tasks' key."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert "tasks" in entry, (
            "Each FR entry in to_dict() must contain a 'tasks' key"
        )

    def test_FR_TRACE_003_to_dict_each_entry_has_tests_key(self):
        """FR-TRACE-003: Each FR's dict entry MUST contain a 'tests' key."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert "tests" in entry, (
            "Each FR entry in to_dict() must contain a 'tests' key"
        )

    def test_FR_TRACE_003_to_dict_each_entry_has_status_key(self):
        """FR-TRACE-003: Each FR's dict entry MUST contain a 'status' key indicating
        whether it is 'implemented' or 'unimplemented'."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert "status" in entry, (
            "Each FR entry in to_dict() must contain a 'status' key"
        )

    def test_FR_TRACE_003_implemented_fr_has_status_implemented(self):
        """FR-TRACE-003: A fully covered FR MUST have status 'implemented'."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        status = entry.get("status")
        assert status == "implemented", (
            f"FR-001 is fully covered; status must be 'implemented', got {status!r}"
        )

    def test_FR_TRACE_003_unimplemented_fr_has_status_unimplemented(self):
        """FR-TRACE-003: An FR with no task or test MUST have status 'unimplemented'."""
        matrix = generate_traceability_matrix(
            frs=["FR-005"],
            task_map={},
            test_map={},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-005")
        status = entry.get("status")
        assert status == "unimplemented", (
            f"FR-005 has no tasks/tests; status must be 'unimplemented', got {status!r}"
        )

    def test_FR_TRACE_003_to_dict_tasks_values_are_lists(self):
        """FR-TRACE-003: The 'tasks' value for each FR entry MUST be a list."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a", "task-b"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert isinstance(entry.get("tasks"), list), (
            f"'tasks' must be a list, got {type(entry.get('tasks'))}"
        )

    def test_FR_TRACE_003_to_dict_tests_values_are_lists(self):
        """FR-TRACE-003: The 'tests' value for each FR entry MUST be a list."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py", "test_b.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert isinstance(entry.get("tests"), list), (
            f"'tests' must be a list, got {type(entry.get('tests'))}"
        )

    def test_FR_TRACE_003_to_dict_correct_task_values(self):
        """FR-TRACE-003: to_dict() tasks values MUST match the input task_map."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-alpha", "task-beta"]},
            test_map={"FR-001": ["test_x.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert entry.get("tasks") == ["task-alpha", "task-beta"], (
            f"tasks must be ['task-alpha', 'task-beta'], got {entry.get('tasks')!r}"
        )

    def test_FR_TRACE_003_to_dict_correct_test_values(self):
        """FR-TRACE-003: to_dict() tests values MUST match the input test_map."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-x"]},
            test_map={"FR-001": ["tests/unit/test_alpha.py", "tests/unit/test_beta.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert entry.get("tests") == [
            "tests/unit/test_alpha.py",
            "tests/unit/test_beta.py",
        ], (
            f"tests values mismatch; got {entry.get('tests')!r}"
        )


# ---------------------------------------------------------------------------
# TraceabilityMatrix.to_markdown — Markdown report output (FR-TRACE-003)
# ---------------------------------------------------------------------------


class TestTraceabilityMatrixToMarkdown:
    """FR-TRACE-003: to_markdown() must return a valid Markdown string."""

    def test_FR_TRACE_003_to_markdown_returns_string(self):
        """FR-TRACE-003: to_markdown() MUST return a str."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_markdown()
        assert isinstance(result, str), (
            f"to_markdown() must return a str, got {type(result)}"
        )

    def test_FR_TRACE_003_to_markdown_non_empty(self):
        """FR-TRACE-003: to_markdown() MUST return a non-empty string."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_markdown()
        assert result.strip() != "", "to_markdown() must not return an empty string"

    def test_FR_TRACE_003_to_markdown_contains_fr_id(self):
        """FR-TRACE-003: The Markdown output MUST include the FR identifiers."""
        matrix = generate_traceability_matrix(
            frs=["FR-001", "FR-002"],
            task_map={"FR-001": ["task-a"], "FR-002": ["task-b"]},
            test_map={"FR-001": ["test_a.py"], "FR-002": ["test_b.py"]},
        )
        result = matrix.to_markdown()
        assert "FR-001" in result, "to_markdown() must contain FR-001"
        assert "FR-002" in result, "to_markdown() must contain FR-002"

    def test_FR_TRACE_003_to_markdown_contains_task_names(self):
        """FR-TRACE-003: The Markdown output MUST include implementing task names."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-traceability"]},
            test_map={"FR-001": ["test_trace.py"]},
        )
        result = matrix.to_markdown()
        assert "task-traceability" in result, (
            "to_markdown() must include the task name 'task-traceability'"
        )

    def test_FR_TRACE_003_to_markdown_contains_test_names(self):
        """FR-TRACE-003: The Markdown output MUST include corresponding test names."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["tests/unit/test_feature.py"]},
        )
        result = matrix.to_markdown()
        assert "tests/unit/test_feature.py" in result, (
            "to_markdown() must include the test path"
        )

    def test_FR_TRACE_003_to_markdown_flags_unimplemented_fr(self):
        """FR-TRACE-003: The Markdown output MUST visibly flag unimplemented FRs."""
        matrix = generate_traceability_matrix(
            frs=["FR-005"],
            task_map={},
            test_map={},
        )
        result = matrix.to_markdown()
        assert "unimplemented" in result.lower(), (
            "to_markdown() must include the word 'unimplemented' for FR-005 "
            f"which has no tasks or tests"
        )

    def test_FR_TRACE_003_to_markdown_has_header_row(self):
        """FR-TRACE-003: The Markdown table MUST include a header row with at least
        FR, Tasks, and Tests columns."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_markdown()
        result_lower = result.lower()
        assert "fr" in result_lower, "Markdown header must contain 'FR' column label"
        assert "task" in result_lower, "Markdown header must contain 'task' column label"
        assert "test" in result_lower, "Markdown header must contain 'test' column label"


# ---------------------------------------------------------------------------
# Edge cases: empty FRs list, single FR, large list
# ---------------------------------------------------------------------------


class TestGenerateTraceabilityMatrixEdgeCases:
    """Edge cases for generate_traceability_matrix."""

    def test_FR_TRACE_001_empty_frs_returns_empty_matrix(self):
        """FR-TRACE-001: An empty FR list MUST produce an empty matrix."""
        matrix = generate_traceability_matrix(frs=[], task_map={}, test_map={})
        result = matrix.to_dict()
        assert result == {}, (
            f"Empty FR list must yield an empty matrix dict, got {result}"
        )

    def test_FR_TRACE_002_empty_frs_no_unimplemented(self):
        """FR-TRACE-002: An empty FR list MUST yield no unimplemented FRs."""
        matrix = generate_traceability_matrix(frs=[], task_map={}, test_map={})
        assert matrix.unimplemented_frs() == []

    def test_FR_TRACE_001_single_fr_fully_covered(self):
        """FR-TRACE-001: A single fully covered FR produces a one-entry matrix."""
        matrix = generate_traceability_matrix(
            frs=["FR-001"],
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": ["test_a.py"]},
        )
        result = matrix.to_dict()
        assert len(result) == 1, (
            f"Expected exactly 1 matrix entry, got {len(result)}"
        )
        assert "FR-001" in result, (
            f"FR-001 must be present in the matrix, got keys: {list(result.keys())}"
        )

    def test_FR_TRACE_001_extra_keys_in_task_map_are_ignored(self):
        """FR-TRACE-001: Keys in task_map that are not in the frs list MUST NOT
        appear in the matrix output."""
        frs = ["FR-001"]
        task_map = {"FR-001": ["task-a"], "FR-999": ["task-ghost"]}
        test_map = {"FR-001": ["test_a.py"]}
        matrix = generate_traceability_matrix(frs=frs, task_map=task_map, test_map=test_map)
        result = matrix.to_dict()
        assert "FR-999" not in result, (
            "FR-999 is not in the frs list and must not appear in the matrix"
        )

    def test_FR_TRACE_001_multiple_tasks_per_fr(self):
        """FR-TRACE-001: Multiple tasks per FR must all appear in the matrix entry."""
        frs = ["FR-001"]
        tasks = ["task-alpha", "task-beta", "task-gamma"]
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map={"FR-001": tasks},
            test_map={"FR-001": ["test_x.py"]},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert entry.get("tasks") == tasks, (
            f"Expected tasks={tasks!r}, got {entry.get('tasks')!r}"
        )

    def test_FR_TRACE_001_multiple_tests_per_fr(self):
        """FR-TRACE-001: Multiple tests per FR must all appear in the matrix entry."""
        frs = ["FR-001"]
        tests = ["tests/unit/test_a.py", "tests/unit/test_b.py", "tests/e2e/test_c.py"]
        matrix = generate_traceability_matrix(
            frs=frs,
            task_map={"FR-001": ["task-a"]},
            test_map={"FR-001": tests},
        )
        result = matrix.to_dict()
        entry = _get_entry(result, "FR-001")
        assert entry.get("tests") == tests, (
            f"Expected tests={tests!r}, got {entry.get('tests')!r}"
        )

    def test_FR_TRACE_001_large_fr_list_all_covered(self):
        """FR-TRACE-001: A large list of FRs (50+) must all appear in the matrix."""
        frs = [f"FR-{i:03d}" for i in range(1, 51)]
        task_map = {fr: [f"task-{fr.lower()}"] for fr in frs}
        test_map = {fr: [f"test_{fr.lower()}.py"] for fr in frs}
        matrix = generate_traceability_matrix(frs=frs, task_map=task_map, test_map=test_map)
        result = matrix.to_dict()
        assert len(result) == 50, (
            f"Expected 50 matrix entries, got {len(result)}"
        )
        for fr in frs:
            assert fr in result, (
                f"FR '{fr}' must be in the matrix, "
                f"got keys: {list(result.keys())[:5]}..."
            )


# ---------------------------------------------------------------------------
# AcceptanceStage integration: run() includes traceability in data
# ---------------------------------------------------------------------------


class TestAcceptanceStageTraceabilityIntegration:
    """FR-TRACE-001/002/003: AcceptanceStage.run() must execute the traceability
    sub-step and include the traceability report in the returned StageResult data."""

    @pytest.mark.asyncio
    async def test_FR_TRACE_001_run_result_data_contains_traceability_key(self):
        """FR-TRACE-001: AcceptanceStage.run() MUST include a 'traceability' key
        in StageResult.data after executing the traceability sub-step."""
        from orchestrator.stages.base import StageResult
        from unittest.mock import MagicMock

        store = MagicMock()
        stage = AcceptanceStage(store=store)
        result = await stage.run()

        assert isinstance(result, StageResult)
        assert "traceability" in result.data, (
            "AcceptanceStage.run() must include a 'traceability' key in result.data "
            f"after running the traceability sub-step. Got keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_FR_TRACE_001_traceability_data_is_dict(self):
        """FR-TRACE-001: The 'traceability' value in run() result.data MUST be a dict."""
        from unittest.mock import MagicMock

        store = MagicMock()
        stage = AcceptanceStage(store=store)
        result = await stage.run()

        traceability = result.data.get("traceability")
        assert isinstance(traceability, dict), (
            "AcceptanceStage.run() result.data['traceability'] must be a dict, "
            f"got {type(traceability)}"
        )

    @pytest.mark.asyncio
    async def test_FR_TRACE_002_run_result_data_contains_unimplemented_key(self):
        """FR-TRACE-002: AcceptanceStage.run() MUST include an 'unimplemented_frs'
        key in StageResult.data to surface any flagged FRs."""
        from unittest.mock import MagicMock

        store = MagicMock()
        stage = AcceptanceStage(store=store)
        result = await stage.run()

        assert "unimplemented_frs" in result.data, (
            "AcceptanceStage.run() must include 'unimplemented_frs' in result.data. "
            f"Got keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_FR_TRACE_002_unimplemented_frs_is_list(self):
        """FR-TRACE-002: result.data['unimplemented_frs'] MUST be a list."""
        from unittest.mock import MagicMock

        store = MagicMock()
        stage = AcceptanceStage(store=store)
        result = await stage.run()

        unimplemented = result.data.get("unimplemented_frs")
        assert isinstance(unimplemented, list), (
            "AcceptanceStage.run() result.data['unimplemented_frs'] must be a list, "
            f"got {type(unimplemented)}"
        )

    @pytest.mark.asyncio
    async def test_FR_TRACE_003_run_result_data_contains_traceability_report_key(self):
        """FR-TRACE-003: AcceptanceStage.run() MUST include a 'traceability_report'
        key containing the structured Markdown or JSON report string."""
        from unittest.mock import MagicMock

        store = MagicMock()
        stage = AcceptanceStage(store=store)
        result = await stage.run()

        assert "traceability_report" in result.data, (
            "AcceptanceStage.run() must include 'traceability_report' in result.data "
            f"for downstream consumers. Got keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_FR_TRACE_003_traceability_report_is_string(self):
        """FR-TRACE-003: result.data['traceability_report'] MUST be a non-empty string."""
        from unittest.mock import MagicMock

        store = MagicMock()
        stage = AcceptanceStage(store=store)
        result = await stage.run()

        report = result.data.get("traceability_report")
        assert isinstance(report, str) and report.strip() != "", (
            "AcceptanceStage.run() traceability_report must be a non-empty string, "
            f"got {report!r}"
        )

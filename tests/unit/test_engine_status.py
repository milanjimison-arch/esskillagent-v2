"""RED-phase tests for PipelineEngine.status().

Task: T013 — engine.status(): aggregate pipeline state from store, display
      stage completion, task counts by status, active warnings, handle
      no-active-pipeline case.

Key requirements:
  1. Aggregate pipeline state from the store (get current pipeline status)
  2. Display stage completion info (which stages are done: spec, plan,
     implement, acceptance)
  3. Task counts by status (e.g., pending, in_progress, done, failed)
  4. Active warnings (collect and return any warnings)
  5. Handle no-active-pipeline case gracefully (return appropriate response
     when no pipeline is active)

All tests in this module are RED-phase tests — they MUST FAIL until
orchestrator/engine.py provides a concrete implementation of status().

Test coverage areas:
  1.  status() method exists on PipelineEngine and is an async coroutine.
  2.  StatusResult is importable and is a class (dataclass/frozen).
  3.  StatusResult has a 'pipeline_id' field.
  4.  StatusResult has a 'stage_completions' field mapping stage names to bool.
  5.  StatusResult has a 'task_counts' field mapping status strings to int.
  6.  StatusResult has a 'warnings' field (tuple/sequence of strings).
  7.  StatusResult has an 'active' field (bool indicating pipeline is running).
  8.  status() returns StatusResult with active=False when no pipeline active.
  9.  status() returns StatusResult with active=True when pipeline is active.
  10. status() returns empty stage_completions when no pipeline active.
  11. status() returns stage completion flags from the store.
  12. status() counts tasks by status (pending, in_progress, done, failed).
  13. status() returns zero counts for statuses with no tasks.
  14. status() returns empty warnings when no warnings are present.
  15. status() aggregates active warnings from the store.
  16. status() with all four stages completed marks all stages as done.
  17. status() returns pipeline_id=None when no pipeline active.
  18. status() is serialisable — all fields are plain Python types.
  19. StatusResult is immutable (frozen dataclass).
  20. status() queries the store for pipeline state.
"""

from __future__ import annotations

import dataclasses
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.engine import PipelineEngine, STAGE_NAMES, StatusResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_engine(
    stage_overrides: dict | None = None,
    skip_stages: list[str] | None = None,
    config: dict | None = None,
    store: object | None = None,
) -> PipelineEngine:
    """Build a PipelineEngine with all four stages mocked and an optional store."""
    default_config: dict = {
        "skip_stages": skip_stages or [],
        "max_retries": 3,
    }
    if config:
        default_config.update(config)

    overrides = stage_overrides or {}

    def _make_passing_stage_mock(name: str) -> MagicMock:
        stage = MagicMock()
        result = MagicMock()
        result.passed = True
        result.attempts = 1
        result.data = {"stage": name}
        result.error = None
        stage.execute_with_gate = AsyncMock(return_value=result)
        return stage

    stages = {
        name: overrides.get(name, _make_passing_stage_mock(name))
        for name in STAGE_NAMES
    }

    engine = PipelineEngine(stages=stages, config=default_config)
    if store is not None:
        engine._store = store
    return engine


def _make_mock_store(
    pipeline_id: str | None = "pipeline-001",
    active: bool = True,
    completed_stages: list[str] | None = None,
    tasks: list[dict] | None = None,
    warnings: list[str] | None = None,
) -> MagicMock:
    """Return a mock store that returns configurable pipeline state."""
    store = MagicMock(name="MockStore")

    completed_stages = completed_stages or []
    tasks = tasks or []
    warnings = warnings or []

    # get_active_pipeline_id() returns the current pipeline id or None
    store.get_active_pipeline_id = AsyncMock(
        return_value=pipeline_id if active else None
    )

    # list_completed_stages(pipeline_id) returns list of stage name strings
    store.list_completed_stages = AsyncMock(return_value=list(completed_stages))

    # list_tasks(pipeline_id) returns list of dicts with at least a 'status' key
    store.list_tasks = AsyncMock(return_value=list(tasks))

    # list_warnings(pipeline_id) returns list of warning strings
    store.list_warnings = AsyncMock(return_value=list(warnings))

    return store


# ---------------------------------------------------------------------------
# 1. Method existence and return type
# ---------------------------------------------------------------------------


class TestStatusMethodExists:
    """status() must exist on PipelineEngine and be an async coroutine."""

    def test_status_method_exists_on_engine(self):
        """T013: PipelineEngine must have a 'status' method."""
        engine = _build_engine()
        assert hasattr(engine, "status"), (
            "PipelineEngine must have a 'status' method"
        )

    def test_status_is_callable(self):
        """T013: status must be callable."""
        engine = _build_engine()
        assert callable(engine.status), "PipelineEngine.status must be callable"

    def test_status_is_a_coroutine_function(self):
        """T013: status must be an async coroutine function."""
        engine = _build_engine()
        assert inspect.iscoroutinefunction(engine.status), (
            "PipelineEngine.status must be an async coroutine function"
        )


# ---------------------------------------------------------------------------
# 2. StatusResult class structure
# ---------------------------------------------------------------------------


class TestStatusResultClass:
    """StatusResult must be a class and have required fields."""

    def test_status_result_is_a_class(self):
        """T013: StatusResult must be a class."""
        assert inspect.isclass(StatusResult)

    def test_status_result_has_pipeline_id_field(self):
        """T013: StatusResult must have a 'pipeline_id' field."""
        fields = {f.name for f in dataclasses.fields(StatusResult)}
        assert "pipeline_id" in fields, (
            "StatusResult must have a 'pipeline_id' field"
        )

    def test_status_result_has_active_field(self):
        """T013: StatusResult must have an 'active' bool field."""
        fields = {f.name for f in dataclasses.fields(StatusResult)}
        assert "active" in fields, "StatusResult must have an 'active' field"

    def test_status_result_has_stage_completions_field(self):
        """T013: StatusResult must have a 'stage_completions' field."""
        fields = {f.name for f in dataclasses.fields(StatusResult)}
        assert "stage_completions" in fields, (
            "StatusResult must have a 'stage_completions' field"
        )

    def test_status_result_has_task_counts_field(self):
        """T013: StatusResult must have a 'task_counts' field."""
        fields = {f.name for f in dataclasses.fields(StatusResult)}
        assert "task_counts" in fields, (
            "StatusResult must have a 'task_counts' field"
        )

    def test_status_result_has_warnings_field(self):
        """T013: StatusResult must have a 'warnings' field."""
        fields = {f.name for f in dataclasses.fields(StatusResult)}
        assert "warnings" in fields, "StatusResult must have a 'warnings' field"

    def test_status_result_is_immutable(self):
        """T013: StatusResult must be a frozen dataclass (immutable)."""
        instance = StatusResult(
            pipeline_id=None,
            active=False,
            stage_completions={},
            task_counts={},
            warnings=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            instance.active = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. No-active-pipeline case
# ---------------------------------------------------------------------------


class TestStatusNoPipelineActive:
    """status() must handle the case where no pipeline is currently active."""

    @pytest.mark.asyncio
    async def test_status_returns_status_result_when_no_pipeline(self):
        """T013: status() must return a StatusResult even with no active pipeline."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert isinstance(result, StatusResult), (
            f"status() must return StatusResult, got {type(result).__name__}"
        )

    @pytest.mark.asyncio
    async def test_status_active_false_when_no_pipeline(self):
        """T013: StatusResult.active must be False when no pipeline is active."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.active is False, (
            "StatusResult.active must be False when no pipeline is active"
        )

    @pytest.mark.asyncio
    async def test_status_pipeline_id_none_when_no_pipeline(self):
        """T013: StatusResult.pipeline_id must be None when no pipeline is active."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.pipeline_id is None, (
            "StatusResult.pipeline_id must be None when no pipeline is active"
        )

    @pytest.mark.asyncio
    async def test_status_empty_stage_completions_when_no_pipeline(self):
        """T013: stage_completions must be empty when no pipeline is active."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert len(result.stage_completions) == 0, (
            "stage_completions must be empty when no pipeline is active, "
            f"got: {result.stage_completions}"
        )

    @pytest.mark.asyncio
    async def test_status_empty_task_counts_when_no_pipeline(self):
        """T013: task_counts must be empty when no pipeline is active."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert len(result.task_counts) == 0, (
            "task_counts must be empty when no pipeline is active, "
            f"got: {result.task_counts}"
        )

    @pytest.mark.asyncio
    async def test_status_empty_warnings_when_no_pipeline(self):
        """T013: warnings must be empty when no pipeline is active."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert len(result.warnings) == 0, (
            "warnings must be empty when no pipeline is active, "
            f"got: {result.warnings}"
        )


# ---------------------------------------------------------------------------
# 4. Active pipeline — basic fields
# ---------------------------------------------------------------------------


class TestStatusActivePipeline:
    """status() must correctly reflect an active pipeline's state."""

    @pytest.mark.asyncio
    async def test_status_active_true_when_pipeline_exists(self):
        """T013: StatusResult.active must be True when a pipeline is active."""
        store = _make_mock_store(active=True, pipeline_id="pipeline-001")
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.active is True, (
            "StatusResult.active must be True when a pipeline is active"
        )

    @pytest.mark.asyncio
    async def test_status_pipeline_id_matches_store(self):
        """T013: StatusResult.pipeline_id must match the active pipeline id."""
        store = _make_mock_store(active=True, pipeline_id="pipeline-xyz")
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.pipeline_id == "pipeline-xyz", (
            f"Expected pipeline_id='pipeline-xyz', got {result.pipeline_id!r}"
        )

    @pytest.mark.asyncio
    async def test_status_returns_status_result_type_when_active(self):
        """T013: status() must return a StatusResult when a pipeline is active."""
        store = _make_mock_store(active=True, pipeline_id="pipeline-001")
        engine = _build_engine(store=store)
        result = await engine.status()
        assert isinstance(result, StatusResult)


# ---------------------------------------------------------------------------
# 5. Stage completion display
# ---------------------------------------------------------------------------


class TestStatusStageCompletions:
    """status() must aggregate which stages have completed."""

    @pytest.mark.asyncio
    async def test_status_all_stages_false_when_none_completed(self):
        """T013: When no stages are complete, all stage_completions are False."""
        store = _make_mock_store(
            active=True, pipeline_id="p1", completed_stages=[]
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        for stage in STAGE_NAMES:
            assert result.stage_completions.get(stage) is False, (
                f"stage '{stage}' must be False when not completed, "
                f"got {result.stage_completions.get(stage)!r}"
            )

    @pytest.mark.asyncio
    async def test_status_spec_complete_marks_spec_true(self):
        """T013: When spec is done, stage_completions['spec'] must be True."""
        store = _make_mock_store(
            active=True, pipeline_id="p1", completed_stages=["spec"]
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.stage_completions.get("spec") is True, (
            "stage_completions['spec'] must be True after spec completes"
        )

    @pytest.mark.asyncio
    async def test_status_incomplete_stages_marked_false(self):
        """T013: Stages not in the completed list must be False."""
        store = _make_mock_store(
            active=True, pipeline_id="p1", completed_stages=["spec"]
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        for stage in ("plan", "implement", "acceptance"):
            assert result.stage_completions.get(stage) is False, (
                f"stage '{stage}' must be False since it has not completed"
            )

    @pytest.mark.asyncio
    async def test_status_all_stages_complete(self):
        """T013: When all stages complete, all stage_completions are True."""
        store = _make_mock_store(
            active=True,
            pipeline_id="p1",
            completed_stages=list(STAGE_NAMES),
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        for stage in STAGE_NAMES:
            assert result.stage_completions.get(stage) is True, (
                f"stage '{stage}' must be True when all stages are complete"
            )

    @pytest.mark.asyncio
    async def test_status_stage_completions_keys_are_all_stage_names(self):
        """T013: stage_completions must contain a key for every stage name."""
        store = _make_mock_store(
            active=True, pipeline_id="p1", completed_stages=["spec", "plan"]
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        for stage in STAGE_NAMES:
            assert stage in result.stage_completions, (
                f"stage_completions must include key '{stage}'"
            )

    @pytest.mark.asyncio
    async def test_status_partial_stage_completion(self):
        """T013: Partial completion is correctly reflected."""
        store = _make_mock_store(
            active=True,
            pipeline_id="p1",
            completed_stages=["spec", "plan"],
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.stage_completions["spec"] is True
        assert result.stage_completions["plan"] is True
        assert result.stage_completions["implement"] is False
        assert result.stage_completions["acceptance"] is False


# ---------------------------------------------------------------------------
# 6. Task counts by status
# ---------------------------------------------------------------------------


class TestStatusTaskCounts:
    """status() must aggregate task counts grouped by status."""

    @pytest.mark.asyncio
    async def test_status_task_counts_empty_when_no_tasks(self):
        """T013: task_counts must be empty (or all zeros) when no tasks exist."""
        store = _make_mock_store(active=True, pipeline_id="p1", tasks=[])
        engine = _build_engine(store=store)
        result = await engine.status()
        total = sum(result.task_counts.values())
        assert total == 0, (
            f"task_counts total must be 0 when no tasks exist, got {result.task_counts}"
        )

    @pytest.mark.asyncio
    async def test_status_counts_pending_tasks(self):
        """T013: task_counts must count tasks with status 'pending'."""
        tasks = [
            {"task_id": "T1", "status": "pending"},
            {"task_id": "T2", "status": "pending"},
        ]
        store = _make_mock_store(active=True, pipeline_id="p1", tasks=tasks)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.task_counts.get("pending", 0) == 2, (
            f"Expected 2 pending tasks, got {result.task_counts.get('pending', 0)}"
        )

    @pytest.mark.asyncio
    async def test_status_counts_done_tasks(self):
        """T013: task_counts must count tasks with status 'done'."""
        tasks = [
            {"task_id": "T1", "status": "done"},
            {"task_id": "T2", "status": "done"},
            {"task_id": "T3", "status": "done"},
        ]
        store = _make_mock_store(active=True, pipeline_id="p1", tasks=tasks)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.task_counts.get("done", 0) == 3, (
            f"Expected 3 done tasks, got {result.task_counts.get('done', 0)}"
        )

    @pytest.mark.asyncio
    async def test_status_counts_failed_tasks(self):
        """T013: task_counts must count tasks with status 'failed'."""
        tasks = [
            {"task_id": "T1", "status": "failed"},
        ]
        store = _make_mock_store(active=True, pipeline_id="p1", tasks=tasks)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.task_counts.get("failed", 0) == 1, (
            f"Expected 1 failed task, got {result.task_counts.get('failed', 0)}"
        )

    @pytest.mark.asyncio
    async def test_status_counts_in_progress_tasks(self):
        """T013: task_counts must count tasks with status 'in_progress'."""
        tasks = [
            {"task_id": "T1", "status": "in_progress"},
            {"task_id": "T2", "status": "in_progress"},
        ]
        store = _make_mock_store(active=True, pipeline_id="p1", tasks=tasks)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.task_counts.get("in_progress", 0) == 2, (
            f"Expected 2 in_progress tasks, got {result.task_counts.get('in_progress', 0)}"
        )

    @pytest.mark.asyncio
    async def test_status_counts_mixed_status_tasks(self):
        """T013: task_counts correctly groups tasks of multiple statuses."""
        tasks = [
            {"task_id": "T1", "status": "done"},
            {"task_id": "T2", "status": "done"},
            {"task_id": "T3", "status": "pending"},
            {"task_id": "T4", "status": "failed"},
            {"task_id": "T5", "status": "in_progress"},
        ]
        store = _make_mock_store(active=True, pipeline_id="p1", tasks=tasks)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert result.task_counts.get("done", 0) == 2
        assert result.task_counts.get("pending", 0) == 1
        assert result.task_counts.get("failed", 0) == 1
        assert result.task_counts.get("in_progress", 0) == 1

    @pytest.mark.asyncio
    async def test_status_total_task_counts_match_total_tasks(self):
        """T013: Sum of all task_counts values must equal total task count."""
        tasks = [
            {"task_id": "T1", "status": "done"},
            {"task_id": "T2", "status": "pending"},
            {"task_id": "T3", "status": "failed"},
        ]
        store = _make_mock_store(active=True, pipeline_id="p1", tasks=tasks)
        engine = _build_engine(store=store)
        result = await engine.status()
        assert sum(result.task_counts.values()) == 3, (
            f"Sum of task_counts must be 3, got {sum(result.task_counts.values())}"
        )

    @pytest.mark.asyncio
    async def test_status_absent_status_returns_zero_not_keyerror(self):
        """T013: Querying an absent status key returns 0 (not KeyError)."""
        tasks = [{"task_id": "T1", "status": "done"}]
        store = _make_mock_store(active=True, pipeline_id="p1", tasks=tasks)
        engine = _build_engine(store=store)
        result = await engine.status()
        # 'pending' is not in the task list — must not raise; default to 0
        assert result.task_counts.get("pending", 0) == 0


# ---------------------------------------------------------------------------
# 7. Active warnings
# ---------------------------------------------------------------------------


class TestStatusWarnings:
    """status() must aggregate active warnings from the store."""

    @pytest.mark.asyncio
    async def test_status_no_warnings_returns_empty_sequence(self):
        """T013: warnings must be an empty sequence when none are present."""
        store = _make_mock_store(active=True, pipeline_id="p1", warnings=[])
        engine = _build_engine(store=store)
        result = await engine.status()
        assert len(result.warnings) == 0, (
            f"warnings must be empty when none present, got {result.warnings}"
        )

    @pytest.mark.asyncio
    async def test_status_single_warning_returned(self):
        """T013: A single warning from the store is returned in warnings."""
        store = _make_mock_store(
            active=True,
            pipeline_id="p1",
            warnings=["spec agent timed out, using cached output"],
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        assert len(result.warnings) == 1, (
            f"Expected 1 warning, got {len(result.warnings)}"
        )
        assert "spec agent timed out" in result.warnings[0], (
            f"Expected warning text to contain 'spec agent timed out', "
            f"got {result.warnings[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_status_multiple_warnings_returned(self):
        """T013: Multiple warnings are all returned in the warnings field."""
        warnings = [
            "spec agent timed out",
            "review score below threshold",
            "task T003 retried 2 times",
        ]
        store = _make_mock_store(
            active=True, pipeline_id="p1", warnings=warnings
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        assert len(result.warnings) == 3, (
            f"Expected 3 warnings, got {len(result.warnings)}: {result.warnings}"
        )

    @pytest.mark.asyncio
    async def test_status_warnings_are_strings(self):
        """T013: Every warning in the warnings sequence must be a string."""
        store = _make_mock_store(
            active=True,
            pipeline_id="p1",
            warnings=["warning one", "warning two"],
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        for w in result.warnings:
            assert isinstance(w, str), (
                f"All warnings must be strings, got {type(w).__name__}: {w!r}"
            )

    @pytest.mark.asyncio
    async def test_status_warnings_preserve_order(self):
        """T013: Warnings are returned in the same order as provided by store."""
        warnings = ["first warning", "second warning", "third warning"]
        store = _make_mock_store(
            active=True, pipeline_id="p1", warnings=warnings
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        assert list(result.warnings) == warnings, (
            f"Warnings must preserve order. Expected {warnings}, "
            f"got {list(result.warnings)}"
        )


# ---------------------------------------------------------------------------
# 8. Result serialisability
# ---------------------------------------------------------------------------


class TestStatusResultSerialisation:
    """StatusResult must be fully serialisable with plain Python types."""

    @pytest.mark.asyncio
    async def test_status_result_fields_are_plain_types(self):
        """T013: All fields of StatusResult must use plain Python types."""
        store = _make_mock_store(
            active=True,
            pipeline_id="p1",
            completed_stages=["spec"],
            tasks=[{"task_id": "T1", "status": "done"}],
            warnings=["a warning"],
        )
        engine = _build_engine(store=store)
        result = await engine.status()

        assert isinstance(result.pipeline_id, (str, type(None)))
        assert isinstance(result.active, bool)
        assert isinstance(result.stage_completions, dict)
        assert isinstance(result.task_counts, dict)
        assert hasattr(result.warnings, "__iter__")
        for w in result.warnings:
            assert isinstance(w, str)

    @pytest.mark.asyncio
    async def test_status_result_can_be_converted_to_dict(self):
        """T013: StatusResult fields must support dataclasses.asdict()."""
        store = _make_mock_store(
            active=True,
            pipeline_id="p1",
            completed_stages=[],
            tasks=[],
            warnings=[],
        )
        engine = _build_engine(store=store)
        result = await engine.status()
        d = dataclasses.asdict(result)
        assert "pipeline_id" in d
        assert "active" in d
        assert "stage_completions" in d
        assert "task_counts" in d
        assert "warnings" in d


# ---------------------------------------------------------------------------
# 9. Store interaction
# ---------------------------------------------------------------------------


class TestStatusStoreInteraction:
    """status() must query the store for pipeline state."""

    @pytest.mark.asyncio
    async def test_status_queries_active_pipeline_id(self):
        """T013: status() must call store.get_active_pipeline_id()."""
        store = _make_mock_store(active=True, pipeline_id="p1")
        engine = _build_engine(store=store)
        await engine.status()
        store.get_active_pipeline_id.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_status_queries_completed_stages_when_pipeline_active(self):
        """T013: status() must call store.list_completed_stages() when pipeline is active."""
        store = _make_mock_store(active=True, pipeline_id="p1")
        engine = _build_engine(store=store)
        await engine.status()
        store.list_completed_stages.assert_awaited()

    @pytest.mark.asyncio
    async def test_status_queries_tasks_when_pipeline_active(self):
        """T013: status() must call store.list_tasks() when pipeline is active."""
        store = _make_mock_store(active=True, pipeline_id="p1")
        engine = _build_engine(store=store)
        await engine.status()
        store.list_tasks.assert_awaited()

    @pytest.mark.asyncio
    async def test_status_queries_warnings_when_pipeline_active(self):
        """T013: status() must call store.list_warnings() when pipeline is active."""
        store = _make_mock_store(active=True, pipeline_id="p1")
        engine = _build_engine(store=store)
        await engine.status()
        store.list_warnings.assert_awaited()

    @pytest.mark.asyncio
    async def test_status_does_not_query_stages_when_no_pipeline(self):
        """T013: status() must NOT query stages when no pipeline is active."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        await engine.status()
        store.list_completed_stages.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_status_does_not_query_tasks_when_no_pipeline(self):
        """T013: status() must NOT query tasks when no pipeline is active."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        await engine.status()
        store.list_tasks.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_status_does_not_query_warnings_when_no_pipeline(self):
        """T013: status() must NOT query warnings when no pipeline is active."""
        store = _make_mock_store(active=False, pipeline_id=None)
        engine = _build_engine(store=store)
        await engine.status()
        store.list_warnings.assert_not_awaited()

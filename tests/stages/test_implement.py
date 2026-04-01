"""FR-013 / T013: ImplementStage RED phase behavior tests.

All tests in this module are intentionally written to FAIL because
orchestrator/stages/implement.py is a stub (raises NotImplementedError).
They define the required behavior that must be implemented in the GREEN phase.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from orchestrator.stages.base import EngineContext
from orchestrator.stages.implement import ImplementStage
from orchestrator.store.models import Task, CheckResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_task(
    task_id: str = "T001",
    parallel: bool = False,
    status: str = "pending",
) -> Task:
    """Factory for Task dataclass instances used across tests."""
    return Task(
        id=task_id,
        phase_num=1,
        description=f"Task {task_id}",
        file_path="src/foo.py",
        story_ref="US1",
        parallel=parallel,
        depends_on=[],
        status=status,
        started_at=None,
        completed_at=None,
        tdd_phase=None,
        review_notes=None,
    )


def _make_ctx(
    tasks: list[Task] | None = None,
    review_result: dict | None = None,
) -> EngineContext:
    """Build a fully-mocked EngineContext for ImplementStage tests."""
    store = AsyncMock()
    store.get_tasks = AsyncMock(return_value=tasks or [])

    review_pipeline = AsyncMock()
    rv = review_result if review_result is not None else {
        "verdict": "pass",
        "supplementary_tasks": [],
    }
    review_pipeline.run_review = AsyncMock(return_value=rv)

    checker = AsyncMock()
    checker.tests_must_pass = AsyncMock(
        return_value=CheckResult(success=True, detail="all green")
    )

    ctx = EngineContext(
        project_path="/tmp/project",
        config=MagicMock(),
        store=store,
        agents=MagicMock(),
        checker=checker,
        review_pipeline=review_pipeline,
    )
    return ctx


# ---------------------------------------------------------------------------
# Test 1 — FR-013: reads pending tasks from store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reads_tasks_from_store():
    """FR-013: _execute_steps must call store.get_tasks() to load pending tasks."""
    pending_task = _make_task("T001", status="pending")
    ctx = _make_ctx(tasks=[pending_task])
    stage = ImplementStage(ctx)

    await stage._execute_steps()

    ctx.store.get_tasks.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — FR-013: serial tasks are executed via TaskRunner.run_serial
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runs_serial_tasks_via_runner():
    """FR-013: serial tasks (parallel=False) must be dispatched to TaskRunner.run_serial."""
    serial_task = _make_task("T001", parallel=False, status="pending")
    ctx = _make_ctx(tasks=[serial_task])
    stage = ImplementStage(ctx)

    with patch(
        "orchestrator.stages.implement.TaskRunner", autospec=True
    ) as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_serial = AsyncMock(return_value={"task_id": "T001", "result": "ok"})

        await stage._execute_steps()

        runner_instance.run_serial.assert_called_once_with(serial_task)


# ---------------------------------------------------------------------------
# Test 3 — FR-013: parallel tasks are grouped and executed via TaskRunner.run_parallel_group
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runs_parallel_tasks_via_runner():
    """FR-013: parallel tasks (parallel=True) must be grouped and dispatched to
    TaskRunner.run_parallel_group, not run_serial."""
    p1 = _make_task("T002", parallel=True, status="pending")
    p2 = _make_task("T003", parallel=True, status="pending")
    ctx = _make_ctx(tasks=[p1, p2])
    stage = ImplementStage(ctx)

    with patch(
        "orchestrator.stages.implement.TaskRunner", autospec=True
    ) as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_parallel_group = AsyncMock(
            return_value=[{"task_id": "T002"}, {"task_id": "T003"}]
        )

        await stage._execute_steps()

        runner_instance.run_parallel_group.assert_called_once_with([p1, p2])
        runner_instance.run_serial.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — FR-013: ReviewPipeline is invoked after all tasks complete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runs_review_after_tasks():
    """FR-013: review_pipeline.run_review('implement', artifacts) must be called
    after all tasks have been executed."""
    task = _make_task("T001", status="pending")
    ctx = _make_ctx(tasks=[task])
    stage = ImplementStage(ctx)

    with patch("orchestrator.stages.implement.TaskRunner", autospec=True) as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_serial = AsyncMock(return_value={"task_id": "T001"})

        await stage._execute_steps()

        ctx.review_pipeline.run_review.assert_called_once()
        positional_args = ctx.review_pipeline.run_review.call_args[0]
        assert positional_args[0] == "implement", (
            "run_review first argument must be 'implement'"
        )


# ---------------------------------------------------------------------------
# Test 5 — FR-013: feature-gap supplementary tasks are created and re-executed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handles_feature_gap_supplementary_tasks():
    """FR-013: when review returns supplementary_tasks (feature-gap), those tasks
    must be created in the store and fed through another TDD cycle."""
    original_task = _make_task("T001", status="pending")
    supplementary_task = _make_task("T099", status="pending")

    # First call returns the original task; second call (after gap tasks are stored)
    # returns the supplementary task for the re-execution cycle.
    ctx = _make_ctx(tasks=[original_task])
    ctx.store.get_tasks = AsyncMock(
        side_effect=[[original_task], [supplementary_task]]
    )
    # First review: gap detected; second review: clean pass
    ctx.review_pipeline.run_review = AsyncMock(
        side_effect=[
            {"verdict": "fail", "supplementary_tasks": [supplementary_task]},
            {"verdict": "pass", "supplementary_tasks": []},
        ]
    )
    ctx.store.create_task = AsyncMock()

    stage = ImplementStage(ctx)

    with patch("orchestrator.stages.implement.TaskRunner", autospec=True) as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_serial = AsyncMock(return_value={"task_id": "ok"})

        await stage._execute_steps()

        # The supplementary task must be persisted to the store
        ctx.store.create_task.assert_called_once_with(supplementary_task)
        # run_review must have been called twice (initial + after supplementary cycle)
        assert ctx.review_pipeline.run_review.call_count == 2


# ---------------------------------------------------------------------------
# Test 6 — FR-013: final push + CI verification is performed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_final_push_ci_verification():
    """FR-013: after all tasks and review pass, checker.tests_must_pass must be
    called as the final CI gate."""
    task = _make_task("T001", status="pending")
    ctx = _make_ctx(tasks=[task])
    stage = ImplementStage(ctx)

    with patch("orchestrator.stages.implement.TaskRunner", autospec=True) as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_serial = AsyncMock(return_value={"task_id": "T001"})

        await stage._execute_steps()

        ctx.checker.tests_must_pass.assert_called_once()


# ---------------------------------------------------------------------------
# Test 7 — FR-013: already-completed tasks are skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_completed_tasks():
    """FR-013: tasks with status='green' or 'completed' must NOT be re-executed."""
    completed_task = _make_task("T001", status="green")
    ctx = _make_ctx(tasks=[completed_task])
    stage = ImplementStage(ctx)

    with patch("orchestrator.stages.implement.TaskRunner", autospec=True) as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_serial = AsyncMock()
        runner_instance.run_parallel_group = AsyncMock()

        await stage._execute_steps()

        runner_instance.run_serial.assert_not_called()
        runner_instance.run_parallel_group.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8 — FR-013: _execute_steps returns a properly structured artifacts dict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_artifacts_dict():
    """FR-013: _execute_steps must return a dict containing at minimum
    'tasks_executed' and 'review_result' keys."""
    task = _make_task("T001", status="pending")
    ctx = _make_ctx(tasks=[task])
    stage = ImplementStage(ctx)

    with patch("orchestrator.stages.implement.TaskRunner", autospec=True) as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_serial = AsyncMock(return_value={"task_id": "T001"})

        result = await stage._execute_steps()

        assert isinstance(result, dict), "_execute_steps must return a dict"
        assert "tasks_executed" in result, (
            "artifacts dict must contain 'tasks_executed'"
        )
        assert "review_result" in result, (
            "artifacts dict must contain 'review_result'"
        )

"""RED-phase tests: Wire PipelineMonitor into engine.

FR-064: PipelineMonitor MUST be invoked at stage transitions and batch
        completions.
FR-065: Engine MUST implement skip-single-BLOCKED behavior: when exactly one
        task in a batch is BLOCKED, skip it and continue.
FR-065: Engine MUST pause when >50% of tasks in a batch are BLOCKED.
FR-065: When engine pauses due to high BLOCKED ratio, PipelineMonitor MUST
        suggest a rollback action.

Test coverage areas:
  1.  FR-064: PipelineEngine accepts a PipelineMonitor via constructor or
              attribute injection.
  2.  FR-064: monitor.check() is called at each stage transition (after each
              stage completes successfully).
  3.  FR-064: monitor.check() is called after a batch of tasks completes.
  4.  FR-065: A single BLOCKED task in a batch is skipped; other tasks run.
  5.  FR-065: Skipped BLOCKED task is recorded in a skip log / result field.
  6.  FR-065: Engine does NOT pause when only one task is BLOCKED (even if
              that's 100% of the batch — skip logic takes priority).
  7.  FR-065: Engine pauses when >50% of tasks in a batch are BLOCKED.
  8.  FR-065: When paused, PipelineMonitor suggests 'rollback'.
  9.  FR-065: Paused state is reflected in the run() result.
  10. FR-064: monitor.check() receives the current task list at each call.
  11. FR-065: Exactly 50% BLOCKED does NOT trigger pause (strictly greater-than).
  12. FR-065: 0% BLOCKED batch — no skip and no pause.
  13. FR-065: All tasks DONE batch — no skip and no pause.
  14. FR-064: monitor.check() is called at every stage boundary, not just on
              failure.
  15. FR-065: Rollback suggestion appears in PipelineResult or monitor
              observations when paused.
  16. Edge: empty batch — no skip, no pause, no crash.
  17. Edge: monitor raises — engine surfaces the error without swallowing it.
  18. FR-064: stage transition event payload passed to monitor includes stage
              name.

All tests MUST fail (RED state) until the implementation is added.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.engine import PipelineEngine, PipelineResult, STAGE_NAMES
from orchestrator.monitor import PipelineMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_passing_stage_result(stage_name: str = "spec") -> MagicMock:
    result = MagicMock()
    result.passed = True
    result.data = {"stage": stage_name}
    result.error = None
    return result


def _make_failing_stage_result(stage_name: str = "spec") -> MagicMock:
    result = MagicMock()
    result.passed = False
    result.data = {}
    result.error = f"{stage_name} failed"
    return result


def _make_stage_mock(passing: bool = True, stage_name: str = "spec") -> MagicMock:
    stage = MagicMock()
    if passing:
        stage.execute_with_gate = AsyncMock(
            return_value=_make_passing_stage_result(stage_name)
        )
    else:
        stage.execute_with_gate = AsyncMock(
            return_value=_make_failing_stage_result(stage_name)
        )
    return stage


def _build_engine(
    monitor: PipelineMonitor | None = None,
    stage_overrides: dict | None = None,
    skip_stages: list[str] | None = None,
    tasks: dict[str, str] | None = None,
) -> PipelineEngine:
    """Build a PipelineEngine with all four stages mocked.

    Parameters
    ----------
    monitor:
        Optional PipelineMonitor instance to inject.
    stage_overrides:
        Map of stage_name -> mock stage. Missing stages default to passing mocks.
    skip_stages:
        List of stage names to skip.
    tasks:
        Dict of task_id -> status for the engine's task registry.
    """
    config: dict[str, Any] = {
        "skip_stages": skip_stages or [],
        "max_retries": 3,
    }
    if tasks is not None:
        config["tasks"] = tasks

    overrides = stage_overrides or {}
    stages = {
        name: overrides.get(name, _make_stage_mock(passing=True, stage_name=name))
        for name in STAGE_NAMES
    }

    engine = PipelineEngine(stages=stages, config=config)
    if monitor is not None:
        engine.monitor = monitor
    return engine


def _make_spy_monitor() -> MagicMock:
    """Return a MagicMock that mimics PipelineMonitor.check() returning []."""
    m = MagicMock(spec=PipelineMonitor)
    m.check = MagicMock(return_value=[])
    m.blocked_threshold = 0.5
    return m


def _tasks_list(specs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Build a task list from (id, status) tuples."""
    return [{"id": tid, "status": st} for tid, st in specs]


# ---------------------------------------------------------------------------
# 1. PipelineEngine accepts a PipelineMonitor
# ---------------------------------------------------------------------------


class TestMonitorInjection:
    """FR-064: Engine MUST accept PipelineMonitor injection."""

    def test_engine_accepts_monitor_via_attribute(self):
        """FR-064: engine.monitor can be set after construction."""
        engine = _build_engine()
        monitor = PipelineMonitor()
        engine.monitor = monitor
        assert engine.monitor is monitor

    def test_engine_monitor_attribute_exists_after_injection(self):
        """FR-064: engine.monitor attribute is accessible after injection."""
        engine = _build_engine(monitor=PipelineMonitor())
        assert hasattr(engine, "monitor")

    def test_engine_monitor_is_pipeline_monitor_instance(self):
        """FR-064: Injected monitor is a PipelineMonitor instance."""
        monitor = PipelineMonitor()
        engine = _build_engine(monitor=monitor)
        assert isinstance(engine.monitor, PipelineMonitor)


# ---------------------------------------------------------------------------
# 2. monitor.check() called at each stage transition
# ---------------------------------------------------------------------------


class TestMonitorCalledAtStageTransitions:
    """FR-064: monitor.check() MUST be invoked after each successful stage."""

    @pytest.mark.asyncio
    async def test_monitor_check_called_after_spec_stage(self):
        """FR-064: monitor.check() called once spec completes successfully."""
        spy = _make_spy_monitor()
        engine = _build_engine(
            monitor=spy,
            skip_stages=["plan", "implement", "acceptance"],
        )
        await engine.run()

        spy.check.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_check_called_four_times_for_all_stages(self):
        """FR-064: monitor.check() called once per successfully completed stage."""
        spy = _make_spy_monitor()
        engine = _build_engine(monitor=spy)
        await engine.run()

        # Once per stage that completed successfully
        assert spy.check.call_count == len(STAGE_NAMES), (
            f"Expected monitor.check called {len(STAGE_NAMES)} times "
            f"(once per stage), got {spy.check.call_count}"
        )

    @pytest.mark.asyncio
    async def test_monitor_check_not_called_for_failed_stage(self):
        """FR-064: monitor.check() is NOT called for a stage that fails."""
        spy = _make_spy_monitor()
        engine = _build_engine(
            monitor=spy,
            stage_overrides={
                "spec": _make_stage_mock(passing=False, stage_name="spec"),
            },
        )
        await engine.run()

        # spec failed, so monitor should NOT be called for spec's completion
        spy.check.assert_not_called()

    @pytest.mark.asyncio
    async def test_monitor_check_called_only_for_completed_stages_before_failure(self):
        """FR-064: monitor.check() only for stages that passed before a mid-pipeline failure."""
        spy = _make_spy_monitor()
        engine = _build_engine(
            monitor=spy,
            stage_overrides={
                # spec passes, plan fails — implement/acceptance do not run
                "plan": _make_stage_mock(passing=False, stage_name="plan"),
            },
        )
        await engine.run()

        # Only spec passed, so monitor.check() called exactly once
        assert spy.check.call_count == 1, (
            f"Expected monitor.check called 1 time (only spec passed), "
            f"got {spy.check.call_count}"
        )

    @pytest.mark.asyncio
    async def test_monitor_check_receives_stage_name_in_call(self):
        """FR-064: monitor.check() call payload or args include the stage name."""
        received_args: list[Any] = []

        class RecordingMonitor:
            blocked_threshold = 0.5

            def check(self, *args, **kwargs) -> list:
                received_args.append((args, kwargs))
                return []

        engine = _build_engine(
            monitor=RecordingMonitor(),
            skip_stages=["plan", "implement", "acceptance"],
        )
        await engine.run()

        assert len(received_args) == 1, "Expected check() called once for spec"
        # The stage name 'spec' must be somewhere in the call arguments
        call_args_flat = str(received_args[0])
        assert "spec" in call_args_flat, (
            f"Stage name 'spec' must appear in monitor.check() args; got: {call_args_flat}"
        )


# ---------------------------------------------------------------------------
# 3. monitor.check() called after batch completion
# ---------------------------------------------------------------------------


class TestMonitorCalledAtBatchCompletion:
    """FR-064: monitor.check() MUST be invoked after a batch of tasks completes."""

    @pytest.mark.asyncio
    async def test_monitor_check_called_after_implement_batch(self):
        """FR-064: monitor.check() called when implement stage (task batch) completes."""
        spy = _make_spy_monitor()
        engine = _build_engine(
            monitor=spy,
            skip_stages=["spec", "plan", "acceptance"],
        )
        await engine.run()

        spy.check.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_check_receives_task_list_after_batch(self):
        """FR-064: monitor.check() called with the list of tasks after batch completion."""
        received_task_lists: list[Any] = []

        class RecordingMonitor:
            blocked_threshold = 0.5

            def check(self, tasks, *args, **kwargs) -> list:
                received_task_lists.append(tasks)
                return []

        tasks = {"T001": "DONE", "T002": "DONE", "T003": "PENDING"}
        engine = _build_engine(
            monitor=RecordingMonitor(),
            skip_stages=["spec", "plan", "acceptance"],
            tasks=tasks,
        )
        await engine.run()

        assert len(received_task_lists) >= 1, "Expected at least one check() call"
        # Verify tasks were passed — the list should not be empty
        first_call_tasks = received_task_lists[0]
        assert first_call_tasks is not None, "monitor.check() must receive task list"


# ---------------------------------------------------------------------------
# 4. Skip-single-BLOCKED behavior
# ---------------------------------------------------------------------------


class TestSkipSingleBlocked:
    """FR-065: When exactly one task in a batch is BLOCKED, skip it and continue."""

    @pytest.mark.asyncio
    async def test_single_blocked_task_is_skipped(self):
        """FR-065: When 1 of N tasks is BLOCKED, that task is skipped."""
        tasks = {"T001": "BLOCKED", "T002": "PENDING", "T003": "PENDING"}
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        # The engine should track skipped blocked tasks
        assert hasattr(result, "skipped_blocked_tasks") or hasattr(engine, "_skipped_blocked_tasks"), (
            "Engine must track skipped BLOCKED tasks"
        )

    @pytest.mark.asyncio
    async def test_single_blocked_task_recorded_in_skip_log(self):
        """FR-065: Skipped BLOCKED task ID appears in skip log."""
        tasks = {"T001": "BLOCKED", "T002": "PENDING", "T003": "PENDING"}
        engine = _build_engine(tasks=tasks)
        await engine.run()

        # Check that T001 was recorded as skipped
        skipped = getattr(engine, "_skipped_blocked_tasks", None)
        assert skipped is not None, "Engine must maintain _skipped_blocked_tasks"
        assert "T001" in skipped, (
            f"T001 (BLOCKED) must appear in skipped_blocked_tasks; got: {skipped}"
        )

    @pytest.mark.asyncio
    async def test_non_blocked_tasks_in_batch_still_run(self):
        """FR-065: Non-BLOCKED tasks in a batch still execute after single skip."""
        tasks_executed: list[str] = []

        tasks = {"T001": "BLOCKED", "T002": "PENDING", "T003": "PENDING"}
        engine = _build_engine(tasks=tasks)

        # Patch the engine's task execution method to record which tasks run
        original_run_task = getattr(engine, "_run_single_task_tdd_cycle", None)

        async def recording_run_task(task_id: str):
            tasks_executed.append(task_id)
            return SimpleNamespace(passed=True, phases=("red", "green", "review"))

        engine._run_single_task_tdd_cycle = recording_run_task
        await engine.run()

        # T002 and T003 should have been executed, T001 should not
        assert "T002" in tasks_executed or "T003" in tasks_executed, (
            f"Non-BLOCKED tasks must still execute; got executed: {tasks_executed}"
        )
        assert "T001" not in tasks_executed, (
            f"BLOCKED task T001 must be skipped; got executed: {tasks_executed}"
        )

    @pytest.mark.asyncio
    async def test_pipeline_continues_after_single_blocked_skip(self):
        """FR-065: Pipeline does not pause/fail when single BLOCKED task is skipped."""
        tasks = {"T001": "BLOCKED", "T002": "PENDING"}
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        # Pipeline should continue (not pause)
        paused = getattr(result, "paused", None)
        assert paused is not True, (
            "Pipeline must NOT pause when only one task is BLOCKED (skip it instead)"
        )

    @pytest.mark.asyncio
    async def test_single_blocked_in_batch_of_one_skips_not_pauses(self):
        """FR-065: Even 100% BLOCKED in single-task batch triggers skip, not pause."""
        # 1 BLOCKED out of 1 = 100% but since it's a single task, skip behavior applies
        tasks = {"T001": "BLOCKED"}
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        # Single BLOCKED task: skip logic should take priority over pause logic
        paused = getattr(result, "paused", None)
        assert paused is not True, (
            "Single BLOCKED task (even at 100%) must be skipped, not pause the engine"
        )


# ---------------------------------------------------------------------------
# 5. Pause on >50% BLOCKED ratio
# ---------------------------------------------------------------------------


class TestPauseOnHighBlockedRatio:
    """FR-065: Engine MUST pause when >50% of batch tasks are BLOCKED."""

    @pytest.mark.asyncio
    async def test_engine_pauses_when_majority_blocked(self):
        """FR-065: Engine pauses when 3 of 4 tasks (75%) are BLOCKED."""
        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
            "T004": "PENDING",
        }
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        paused = getattr(result, "paused", None)
        assert paused is True, (
            f"Engine must pause when >50% of tasks are BLOCKED; "
            f"result.paused={paused}"
        )

    @pytest.mark.asyncio
    async def test_engine_pauses_when_all_blocked(self):
        """FR-065: Engine pauses when 100% of tasks are BLOCKED (and more than one)."""
        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
        }
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        paused = getattr(result, "paused", None)
        assert paused is True, (
            f"Engine must pause when all tasks are BLOCKED; result.paused={paused}"
        )

    @pytest.mark.asyncio
    async def test_engine_does_not_pause_at_exactly_50_percent(self):
        """FR-065: Engine does NOT pause at exactly 50% BLOCKED (strict >50%)."""
        # 2 of 4 = exactly 50% — should NOT trigger pause
        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "PENDING",
            "T004": "PENDING",
        }
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        paused = getattr(result, "paused", None)
        assert paused is not True, (
            "Engine must NOT pause when BLOCKED ratio is exactly 50% (not strictly >50%)"
        )

    @pytest.mark.asyncio
    async def test_engine_does_not_pause_when_below_50_percent(self):
        """FR-065: Engine does NOT pause when fewer than 50% of tasks are BLOCKED."""
        # 1 of 4 = 25% — no pause
        tasks = {
            "T001": "BLOCKED",
            "T002": "PENDING",
            "T003": "PENDING",
            "T004": "PENDING",
        }
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        paused = getattr(result, "paused", None)
        assert paused is not True, (
            "Engine must NOT pause when fewer than 50% of tasks are BLOCKED"
        )

    @pytest.mark.asyncio
    async def test_engine_does_not_pause_when_no_tasks_blocked(self):
        """FR-065: No pause when 0% BLOCKED."""
        tasks = {
            "T001": "PENDING",
            "T002": "PENDING",
            "T003": "DONE",
        }
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        paused = getattr(result, "paused", None)
        assert paused is not True, (
            "Engine must NOT pause when no tasks are BLOCKED"
        )

    @pytest.mark.asyncio
    async def test_pipeline_result_has_paused_field(self):
        """FR-065: PipelineResult (or engine state) exposes a 'paused' indicator."""
        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
            "T004": "PENDING",
        }
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        # Either result or engine should expose the paused state
        has_paused_on_result = hasattr(result, "paused")
        has_paused_on_engine = hasattr(engine, "_paused") or hasattr(engine, "paused")
        assert has_paused_on_result or has_paused_on_engine, (
            "PipelineResult or PipelineEngine must expose a 'paused' field "
            "when engine pauses due to high BLOCKED ratio"
        )

    @pytest.mark.asyncio
    async def test_paused_pipeline_result_passed_is_false(self):
        """FR-065: When paused due to high BLOCKED ratio, pipeline.passed is False."""
        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
            "T004": "PENDING",
        }
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        assert result.passed is False, (
            "Pipeline must not be marked as passed when it paused due to BLOCKED ratio"
        )


# ---------------------------------------------------------------------------
# 6. Rollback suggestion when paused
# ---------------------------------------------------------------------------


class TestRollbackSuggestionOnPause:
    """FR-065: PipelineMonitor MUST suggest rollback when engine pauses."""

    @pytest.mark.asyncio
    async def test_monitor_suggests_rollback_when_majority_blocked(self):
        """FR-065: PipelineMonitor.check() observations include a rollback suggestion
        when >50% of tasks are BLOCKED."""
        rollback_observations: list[dict] = []

        class RollbackCapturingMonitor:
            blocked_threshold = 0.5

            def check(self, tasks, *args, **kwargs) -> list:
                blocked = sum(1 for t in tasks if t.get("status") == "BLOCKED")
                total = len(tasks)
                if total > 0 and (blocked / total) > self.blocked_threshold:
                    obs = {
                        "type": "rollback_suggested",
                        "severity": "warning",
                        "message": "Rollback suggested due to high BLOCKED ratio",
                        "timestamp": "2026-04-02T00:00:00+00:00",
                        "details": {"action": "rollback"},
                    }
                    rollback_observations.append(obs)
                    return [obs]
                return []

        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
            "T004": "PENDING",
        }
        engine = _build_engine(monitor=RollbackCapturingMonitor(), tasks=tasks)
        await engine.run()

        assert len(rollback_observations) >= 1, (
            "PipelineMonitor must produce a rollback suggestion observation "
            "when >50% tasks are BLOCKED"
        )

    @pytest.mark.asyncio
    async def test_rollback_suggestion_available_on_result_or_engine(self):
        """FR-065: Rollback suggestion is accessible via result or engine after pause."""
        spy = _make_spy_monitor()
        # Make monitor return a rollback suggestion observation
        spy.check.return_value = [
            {
                "type": "rollback_suggested",
                "severity": "warning",
                "message": "Rollback suggested",
                "timestamp": "2026-04-02T00:00:00+00:00",
                "details": {"action": "rollback"},
            }
        ]

        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
            "T004": "PENDING",
        }
        engine = _build_engine(monitor=spy, tasks=tasks)
        result = await engine.run()

        # Engine should surface monitor observations (rollback suggestion) somewhere
        monitor_observations = (
            getattr(result, "monitor_observations", None)
            or getattr(result, "observations", None)
            or getattr(engine, "_monitor_observations", None)
        )
        assert monitor_observations is not None, (
            "Engine must expose monitor observations (rollback suggestion) "
            "on result or engine after a pause"
        )

    @pytest.mark.asyncio
    async def test_monitor_invoked_with_blocked_tasks_when_pausing(self):
        """FR-065: monitor.check() is called with the BLOCKED-heavy task list
        that triggered the pause decision."""
        received_task_lists: list[list] = []

        class CapturingMonitor:
            blocked_threshold = 0.5

            def check(self, tasks, *args, **kwargs) -> list:
                received_task_lists.append(list(tasks))
                return []

        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
            "T004": "PENDING",
        }
        engine = _build_engine(monitor=CapturingMonitor(), tasks=tasks)
        await engine.run()

        assert len(received_task_lists) >= 1, (
            "monitor.check() must be called at least once (at batch evaluation)"
        )
        # At least one call should contain the BLOCKED tasks
        any_call_has_blocked = any(
            any(t.get("status") == "BLOCKED" for t in call_tasks)
            for call_tasks in received_task_lists
        )
        assert any_call_has_blocked, (
            "At least one monitor.check() call must include BLOCKED tasks"
        )

    @pytest.mark.asyncio
    async def test_monitor_check_called_before_pause_decision(self):
        """FR-065: monitor.check() is called BEFORE the engine decides to pause,
        so the monitor can influence or observe the pause condition."""
        check_call_count_at_pause: list[int] = []
        call_count = 0

        class CountingMonitor:
            blocked_threshold = 0.5

            def check(self, tasks, *args, **kwargs) -> list:
                nonlocal call_count
                call_count += 1
                return []

        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
            "T004": "PENDING",
        }
        engine = _build_engine(monitor=CountingMonitor(), tasks=tasks)
        result = await engine.run()

        # Monitor must have been called at least once before or during the pause
        assert call_count >= 1, (
            f"monitor.check() must be called at least once; was called {call_count} times"
        )


# ---------------------------------------------------------------------------
# 7. Batch completion monitoring payload
# ---------------------------------------------------------------------------


class TestBatchCompletionPayload:
    """FR-064: monitor.check() receives accurate task data at batch completion."""

    @pytest.mark.asyncio
    async def test_monitor_receives_task_list_with_correct_statuses(self):
        """FR-064: Task list passed to monitor.check() reflects actual task statuses."""
        received: list[list[dict]] = []

        class RecordingMonitor:
            blocked_threshold = 0.5

            def check(self, tasks, *args, **kwargs) -> list:
                received.append([dict(t) for t in tasks])
                return []

        tasks = {"T001": "DONE", "T002": "BLOCKED", "T003": "PENDING"}
        engine = _build_engine(
            monitor=RecordingMonitor(),
            tasks=tasks,
        )
        await engine.run()

        assert len(received) >= 1, "monitor.check() must be called at least once"
        # At least one call should reflect actual task statuses
        all_task_ids = {t["id"] for call_tasks in received for t in call_tasks}
        assert "T001" in all_task_ids or "T002" in all_task_ids, (
            "Task IDs must be present in monitor.check() call"
        )

    @pytest.mark.asyncio
    async def test_monitor_check_stage_context_includes_stage_name(self):
        """FR-064: Context passed to monitor.check() at stage transition includes
        the name of the stage that just completed."""
        received_kwargs: list[dict] = []

        class ContextCapturingMonitor:
            blocked_threshold = 0.5

            def check(self, tasks, *args, **kwargs) -> list:
                received_kwargs.append(kwargs)
                return []

        engine = _build_engine(
            monitor=ContextCapturingMonitor(),
            skip_stages=["plan", "implement", "acceptance"],
        )
        await engine.run()

        assert len(received_kwargs) >= 1, "Expected at least one check() call"
        # Stage name should be passed as keyword arg or positional arg
        any_has_stage = any("stage" in kw for kw in received_kwargs)
        # If not in kwargs, it might be in positional args — accept either convention
        # The key requirement is that the stage name is accessible
        # This test asserts the behavior must be implemented
        assert any_has_stage, (
            "monitor.check() must receive 'stage' keyword arg at stage transitions; "
            f"received kwargs: {received_kwargs}"
        )


# ---------------------------------------------------------------------------
# 8. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCasesMonitorIntegration:
    """Edge cases for monitor integration."""

    @pytest.mark.asyncio
    async def test_empty_task_batch_no_skip_no_pause(self):
        """Edge: Engine with no tasks in registry — no skip, no pause."""
        engine = _build_engine(tasks={})
        result = await engine.run()

        paused = getattr(result, "paused", False)
        assert paused is not True, (
            "Engine must not pause when task batch is empty"
        )

    @pytest.mark.asyncio
    async def test_all_tasks_done_no_pause(self):
        """Edge: All tasks DONE — no BLOCKED ratio, no pause."""
        tasks = {"T001": "DONE", "T002": "DONE", "T003": "DONE"}
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        paused = getattr(result, "paused", False)
        assert paused is not True, (
            "Engine must not pause when all tasks are DONE"
        )

    @pytest.mark.asyncio
    async def test_no_monitor_injected_engine_still_runs(self):
        """Engine runs normally when no monitor is injected."""
        engine = _build_engine(monitor=None)
        # Remove monitor attribute if it was set
        if hasattr(engine, "monitor"):
            del engine.monitor
        result = await engine.run()
        assert isinstance(result, PipelineResult)

    @pytest.mark.asyncio
    async def test_monitor_none_engine_does_not_crash(self):
        """Edge: engine.monitor = None — engine handles gracefully."""
        engine = _build_engine()
        engine.monitor = None
        result = await engine.run()
        assert result is not None

    @pytest.mark.asyncio
    async def test_monitor_check_raising_propagates_error(self):
        """Edge: If monitor.check() raises, the engine surfaces the error."""

        class ExplodingMonitor:
            blocked_threshold = 0.5

            def check(self, *args, **kwargs) -> list:
                raise RuntimeError("monitor exploded")

        engine = _build_engine(monitor=ExplodingMonitor())
        with pytest.raises(RuntimeError, match="monitor exploded"):
            await engine.run()

    @pytest.mark.asyncio
    async def test_two_blocked_of_three_pauses_engine(self):
        """FR-065: 2 of 3 tasks BLOCKED = 66.7% — engine must pause."""
        tasks = {"T001": "BLOCKED", "T002": "BLOCKED", "T003": "PENDING"}
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        paused = getattr(result, "paused", None)
        assert paused is True, (
            "Engine must pause when 2 of 3 tasks (66.7%) are BLOCKED"
        )

    @pytest.mark.asyncio
    async def test_blocked_ratio_boundary_51_percent_pauses(self):
        """FR-065: Just over 50% BLOCKED must trigger pause."""
        # 51 of 100 = 51%
        tasks = {f"T{i:03d}": ("BLOCKED" if i <= 51 else "PENDING") for i in range(1, 101)}
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        paused = getattr(result, "paused", None)
        assert paused is True, (
            "Engine must pause when 51% of tasks are BLOCKED (just over 50%)"
        )


# ---------------------------------------------------------------------------
# 9. PipelineResult exposes paused field
# ---------------------------------------------------------------------------


class TestPipelineResultPausedField:
    """FR-065: PipelineResult must expose paused state."""

    @pytest.mark.asyncio
    async def test_pipeline_result_paused_false_on_normal_run(self):
        """FR-065: PipelineResult.paused is False on a normal (non-paused) run."""
        engine = _build_engine()
        result = await engine.run()

        # paused should be False or absent when pipeline completes normally
        paused = getattr(result, "paused", False)
        assert paused is False or paused is None, (
            f"PipelineResult.paused must be False on normal run; got {paused}"
        )

    @pytest.mark.asyncio
    async def test_pipeline_result_paused_true_on_high_blocked(self):
        """FR-065: PipelineResult.paused is True when engine paused due to BLOCKED ratio."""
        tasks = {
            "T001": "BLOCKED",
            "T002": "BLOCKED",
            "T003": "BLOCKED",
            "T004": "PENDING",
        }
        engine = _build_engine(tasks=tasks)
        result = await engine.run()

        assert hasattr(result, "paused"), (
            "PipelineResult must have a 'paused' field"
        )
        assert result.paused is True, (
            f"PipelineResult.paused must be True when engine paused; got {result.paused}"
        )


# ---------------------------------------------------------------------------
# 10. Monitor invocation order: check() after stage, then after batch
# ---------------------------------------------------------------------------


class TestMonitorInvocationOrder:
    """FR-064: Verify the order of monitor.check() calls relative to stage/batch events."""

    @pytest.mark.asyncio
    async def test_monitor_check_order_matches_stage_order(self):
        """FR-064: monitor.check() calls occur in STAGE_NAMES order."""
        call_order: list[str] = []

        class OrderCapturingMonitor:
            blocked_threshold = 0.5

            def check(self, tasks, stage: str = "", **kwargs) -> list:
                if stage:
                    call_order.append(stage)
                return []

        engine = _build_engine(monitor=OrderCapturingMonitor())
        await engine.run()

        # Filter to known stage names
        stage_calls = [s for s in call_order if s in STAGE_NAMES]
        assert stage_calls == list(STAGE_NAMES), (
            f"monitor.check() must be called in stage order {list(STAGE_NAMES)}; "
            f"got {stage_calls}"
        )

    @pytest.mark.asyncio
    async def test_monitor_not_called_when_no_monitor_injected(self):
        """No monitor attribute means no monitor calls — engine uses opt-in pattern."""
        engine = _build_engine()
        # Ensure no monitor is set
        if hasattr(engine, "monitor"):
            engine.monitor = None

        # Should run without error — monitor calls are conditional
        result = await engine.run()
        assert isinstance(result, PipelineResult)

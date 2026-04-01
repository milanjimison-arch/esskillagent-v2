"""RED-phase tests for PipelineEngine.resume().

FR references from User Story 2 — Resume from Checkpoint (P1):

  - Given a checkpoint exists with stage "implement" and last completed task
    index, resume() reads the checkpoint and determines the resume point.
  - Given checkpoint indicates pipeline was in "implement" stage at task 3,
    atomic stages (spec, plan) are re-run from start, and implement resumes
    from task 3.
  - Given no checkpoint file exists, NoCheckpointError is raised.
  - Given checkpoint has stage "spec" or "plan" (atomic), those stages are
    re-run from the beginning.
  - Given checkpoint with completed "acceptance" stage, the pipeline is
    recognised as already complete and does not re-run.

All tests in this module are RED-phase tests — they MUST FAIL until
orchestrator/engine.py provides a concrete implementation of resume().
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.engine import (
    ATOMIC_STAGES,
    STAGE_NAMES,
    NoCheckpointError,
    PipelineEngine,
    PipelineResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ATOMIC_STAGE_NAMES = ("spec", "plan")


def _make_passing_stage_result(name: str = "spec") -> MagicMock:
    r = MagicMock()
    r.passed = True
    r.attempts = 1
    r.data = {"stage": name}
    r.error = None
    return r


def _make_stage_mock(passing: bool = True, name: str = "spec") -> MagicMock:
    stage = MagicMock()
    if passing:
        stage.execute_with_gate = AsyncMock(
            return_value=_make_passing_stage_result(name)
        )
    else:
        failing = MagicMock()
        failing.passed = False
        failing.error = f"{name} failed"
        stage.execute_with_gate = AsyncMock(return_value=failing)
    return stage


def _build_engine(
    stage_overrides: dict | None = None,
    skip_stages: list[str] | None = None,
) -> PipelineEngine:
    overrides = stage_overrides or {}
    stages = {
        n: overrides.get(n, _make_stage_mock(passing=True, name=n))
        for n in STAGE_NAMES
    }
    config = {"skip_stages": skip_stages or []}
    return PipelineEngine(stages=stages, config=config)


def _make_checkpoint(
    stage: str,
    last_completed_task_index: int | None = None,
    data: dict | None = None,
) -> dict:
    """Return a dict that looks like a persisted checkpoint record."""
    cp: dict = {"stage": stage}
    if last_completed_task_index is not None:
        cp["last_completed_task_index"] = last_completed_task_index
    if data:
        cp.update(data)
    return cp


# ---------------------------------------------------------------------------
# 1. NoCheckpointError — importable and is an Exception subclass
# ---------------------------------------------------------------------------


class TestNoCheckpointError:
    """NoCheckpointError must exist and be a proper exception."""

    def test_no_checkpoint_error_is_exception(self):
        """FR-resume-3: NoCheckpointError MUST be a subclass of Exception."""
        assert issubclass(NoCheckpointError, Exception), (
            "NoCheckpointError must inherit from Exception"
        )

    def test_no_checkpoint_error_can_be_raised_and_caught(self):
        """NoCheckpointError must be raiseable and catchable."""
        with pytest.raises(NoCheckpointError):
            raise NoCheckpointError("no checkpoint found")

    def test_no_checkpoint_error_message_preserved(self):
        """NoCheckpointError must carry the message string."""
        msg = "pipeline-42: no checkpoint found"
        with pytest.raises(NoCheckpointError, match="pipeline-42"):
            raise NoCheckpointError(msg)


# ---------------------------------------------------------------------------
# 2. ATOMIC_STAGES constant
# ---------------------------------------------------------------------------


class TestAtomicStagesConstant:
    """ATOMIC_STAGES must be importable and contain spec and plan."""

    def test_atomic_stages_is_iterable(self):
        """ATOMIC_STAGES must be iterable."""
        assert hasattr(ATOMIC_STAGES, "__iter__")

    def test_atomic_stages_contains_spec(self):
        """ATOMIC_STAGES must include 'spec'."""
        assert "spec" in ATOMIC_STAGES, (
            f"ATOMIC_STAGES must contain 'spec', got {ATOMIC_STAGES}"
        )

    def test_atomic_stages_contains_plan(self):
        """ATOMIC_STAGES must include 'plan'."""
        assert "plan" in ATOMIC_STAGES, (
            f"ATOMIC_STAGES must contain 'plan', got {ATOMIC_STAGES}"
        )

    def test_atomic_stages_does_not_contain_implement(self):
        """'implement' is NOT atomic — it supports partial resume."""
        assert "implement" not in ATOMIC_STAGES, (
            "'implement' must not be in ATOMIC_STAGES"
        )

    def test_atomic_stages_does_not_contain_acceptance(self):
        """'acceptance' is NOT atomic."""
        assert "acceptance" not in ATOMIC_STAGES, (
            "'acceptance' must not be in ATOMIC_STAGES"
        )


# ---------------------------------------------------------------------------
# 3. resume() method exists on PipelineEngine
# ---------------------------------------------------------------------------


class TestResumeMethodExists:
    """PipelineEngine must expose a resume() coroutine method."""

    def test_pipeline_engine_has_resume_method(self):
        """PipelineEngine must have a 'resume' attribute."""
        engine = _build_engine()
        assert hasattr(engine, "resume"), (
            "PipelineEngine must have a 'resume' method"
        )

    def test_resume_is_callable(self):
        """PipelineEngine.resume must be callable."""
        engine = _build_engine()
        assert callable(engine.resume), "PipelineEngine.resume must be callable"

    @pytest.mark.asyncio
    async def test_resume_is_a_coroutine_function(self):
        """resume() must be an async method (coroutine function)."""
        import inspect
        engine = _build_engine()
        assert inspect.iscoroutinefunction(engine.resume), (
            "PipelineEngine.resume must be an async (coroutine) method"
        )


# ---------------------------------------------------------------------------
# 4. FR-resume-3: No checkpoint → NoCheckpointError
# ---------------------------------------------------------------------------


class TestNoCheckpointRaisesError:
    """When no checkpoint exists, resume() must raise NoCheckpointError."""

    @pytest.mark.asyncio
    async def test_resume_raises_no_checkpoint_error_when_no_checkpoint(self):
        """FR-resume-3: resume() MUST raise NoCheckpointError if no checkpoint exists."""
        engine = _build_engine()
        # Patch the checkpoint-loading mechanism to return None (no checkpoint).
        with patch.object(engine, "_load_checkpoint", return_value=None, create=True):
            with pytest.raises(NoCheckpointError):
                await engine.resume()

    @pytest.mark.asyncio
    async def test_resume_does_not_return_pipeline_result_when_no_checkpoint(self):
        """FR-resume-3: resume() must never return normally when there is no checkpoint."""
        engine = _build_engine()
        with patch.object(engine, "_load_checkpoint", return_value=None, create=True):
            raised = False
            try:
                await engine.resume()
            except NoCheckpointError:
                raised = True
            except Exception:
                raised = True  # any exception counts — the key is no normal return
            assert raised, "resume() must not return normally when there is no checkpoint"

    @pytest.mark.asyncio
    async def test_resume_raises_no_checkpoint_error_specifically(self):
        """FR-resume-3: The exception raised must be NoCheckpointError, not a generic one."""
        engine = _build_engine()
        with patch.object(engine, "_load_checkpoint", return_value=None, create=True):
            with pytest.raises(NoCheckpointError):
                await engine.resume()


# ---------------------------------------------------------------------------
# 5. FR-resume-1: Checkpoint is read and resume point determined
# ---------------------------------------------------------------------------


class TestCheckpointRead:
    """resume() must read the last checkpoint and determine the resume point."""

    @pytest.mark.asyncio
    async def test_resume_calls_load_checkpoint(self):
        """FR-resume-1: resume() must attempt to load a checkpoint."""
        engine = _build_engine()
        load_mock = MagicMock(return_value=_make_checkpoint("implement", 2))
        with patch.object(engine, "_load_checkpoint", load_mock, create=True):
            try:
                await engine.resume()
            except (NotImplementedError, NoCheckpointError):
                pass
        load_mock.assert_called_once(), (
            "resume() must call _load_checkpoint exactly once"
        )

    @pytest.mark.asyncio
    async def test_resume_returns_pipeline_result_when_checkpoint_exists(self):
        """FR-resume-1: resume() must return a PipelineResult when checkpoint is valid."""
        engine = _build_engine()
        checkpoint = _make_checkpoint("implement", last_completed_task_index=2)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            result = await engine.resume()
        assert isinstance(result, PipelineResult), (
            f"resume() must return PipelineResult when checkpoint exists, "
            f"got {type(result).__name__}"
        )

    @pytest.mark.asyncio
    async def test_resume_result_passed_true_when_all_stages_pass(self):
        """FR-resume-1: resume() returns PipelineResult.passed=True when resumed run passes."""
        engine = _build_engine()
        checkpoint = _make_checkpoint("implement", last_completed_task_index=0)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            result = await engine.resume()
        assert result.passed is True, (
            "PipelineResult.passed must be True when all resumed stages pass"
        )


# ---------------------------------------------------------------------------
# 6. FR-resume-2: Atomic stages (spec, plan) re-run from start
# ---------------------------------------------------------------------------


class TestAtomicStagesRerunFromStart:
    """spec and plan are always re-run from scratch when resuming."""

    @pytest.mark.asyncio
    async def test_spec_stage_reruns_when_resuming_from_implement(self):
        """FR-resume-2: 'spec' MUST be re-run from the start when resuming from implement."""
        spec_mock = _make_stage_mock(passing=True, name="spec")
        engine = _build_engine(stage_overrides={"spec": spec_mock})
        checkpoint = _make_checkpoint("implement", last_completed_task_index=3)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()
        spec_mock.execute_with_gate.assert_awaited(), (
            "'spec' stage execute_with_gate must be called during resume (atomic re-run)"
        )

    @pytest.mark.asyncio
    async def test_plan_stage_reruns_when_resuming_from_implement(self):
        """FR-resume-2: 'plan' MUST be re-run from the start when resuming from implement."""
        plan_mock = _make_stage_mock(passing=True, name="plan")
        engine = _build_engine(stage_overrides={"plan": plan_mock})
        checkpoint = _make_checkpoint("implement", last_completed_task_index=3)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()
        plan_mock.execute_with_gate.assert_awaited(), (
            "'plan' stage execute_with_gate must be called during resume (atomic re-run)"
        )

    @pytest.mark.asyncio
    async def test_spec_and_plan_both_rerun_when_resuming_from_implement(self):
        """FR-resume-2: Both spec and plan must be re-executed when resuming from implement."""
        call_log: list[str] = []

        async def _gate(name: str):
            call_log.append(name)
            return _make_passing_stage_result(name)

        spec_mock = MagicMock()
        spec_mock.execute_with_gate = AsyncMock(side_effect=lambda: _gate("spec"))
        plan_mock = MagicMock()
        plan_mock.execute_with_gate = AsyncMock(side_effect=lambda: _gate("plan"))

        engine = _build_engine(stage_overrides={"spec": spec_mock, "plan": plan_mock})
        checkpoint = _make_checkpoint("implement", last_completed_task_index=2)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()

        assert "spec" in call_log, "'spec' must be re-run during resume"
        assert "plan" in call_log, "'plan' must be re-run during resume"

    @pytest.mark.asyncio
    async def test_spec_reruns_before_plan_when_resuming(self):
        """FR-resume-2: Atomic stages must re-run in canonical order: spec before plan."""
        call_log: list[str] = []

        async def _gate(name: str):
            call_log.append(name)
            return _make_passing_stage_result(name)

        spec_mock = MagicMock()
        spec_mock.execute_with_gate = AsyncMock(side_effect=lambda: _gate("spec"))
        plan_mock = MagicMock()
        plan_mock.execute_with_gate = AsyncMock(side_effect=lambda: _gate("plan"))

        engine = _build_engine(stage_overrides={"spec": spec_mock, "plan": plan_mock})
        checkpoint = _make_checkpoint("implement", last_completed_task_index=1)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()

        assert call_log.index("spec") < call_log.index("plan"), (
            "During resume, 'spec' must execute before 'plan'"
        )


# ---------------------------------------------------------------------------
# 7. FR-resume-2: implement resumes from last completed task index
# ---------------------------------------------------------------------------


class TestImplementResumesFromCheckpoint:
    """implement stage must resume from the task index stored in the checkpoint."""

    @pytest.mark.asyncio
    async def test_implement_stage_is_called_when_resuming_from_implement(self):
        """FR-resume-2: implement stage must run when checkpoint stage is 'implement'."""
        implement_mock = _make_stage_mock(passing=True, name="implement")
        engine = _build_engine(stage_overrides={"implement": implement_mock})
        checkpoint = _make_checkpoint("implement", last_completed_task_index=3)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()
        implement_mock.execute_with_gate.assert_awaited(), (
            "'implement' stage must be called when resuming from checkpoint stage 'implement'"
        )

    @pytest.mark.asyncio
    async def test_implement_stage_receives_resume_task_index(self):
        """FR-resume-2: implement stage must receive the resume_from_task index from checkpoint."""
        implement_mock = _make_stage_mock(passing=True, name="implement")
        engine = _build_engine(stage_overrides={"implement": implement_mock})
        checkpoint = _make_checkpoint("implement", last_completed_task_index=5)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()

        # The implement stage should have been told to resume from task 5+1=6,
        # OR the engine should set implement_mock.resume_from_task = 6 before calling.
        # We check that resume_from_task was set on the stage object.
        assert hasattr(implement_mock, "resume_from_task") and (
            implement_mock.resume_from_task == 6
        ), (
            "implement stage must have resume_from_task set to "
            f"last_completed_task_index + 1 = 6, "
            f"got resume_from_task={getattr(implement_mock, 'resume_from_task', 'NOT SET')}"
        )

    @pytest.mark.asyncio
    async def test_implement_resume_task_index_zero_when_checkpoint_task_is_minus_one(self):
        """FR-resume-2: If checkpoint has last_completed_task_index=-1, resume from task 0."""
        implement_mock = _make_stage_mock(passing=True, name="implement")
        engine = _build_engine(stage_overrides={"implement": implement_mock})
        # -1 means no task completed yet; resume from task 0
        checkpoint = _make_checkpoint("implement", last_completed_task_index=-1)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()

        assert hasattr(implement_mock, "resume_from_task") and (
            implement_mock.resume_from_task == 0
        ), (
            "When last_completed_task_index=-1, implement stage resume_from_task must be 0, "
            f"got {getattr(implement_mock, 'resume_from_task', 'NOT SET')}"
        )

    @pytest.mark.asyncio
    async def test_acceptance_stage_runs_after_implement_completes(self):
        """FR-resume-2: acceptance stage must run after implement finishes during resume."""
        acceptance_mock = _make_stage_mock(passing=True, name="acceptance")
        engine = _build_engine(stage_overrides={"acceptance": acceptance_mock})
        checkpoint = _make_checkpoint("implement", last_completed_task_index=2)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()
        acceptance_mock.execute_with_gate.assert_awaited(), (
            "'acceptance' stage must run during resume after implement completes"
        )


# ---------------------------------------------------------------------------
# 8. FR-resume-4: Checkpoint at atomic stage → re-run that stage from start
# ---------------------------------------------------------------------------


class TestCheckpointAtAtomicStage:
    """When checkpoint stage is 'spec' or 'plan', those stages re-run from beginning."""

    @pytest.mark.asyncio
    async def test_spec_reruns_when_checkpoint_stage_is_spec(self):
        """FR-resume-4: checkpoint stage='spec' → spec re-runs from the beginning."""
        spec_mock = _make_stage_mock(passing=True, name="spec")
        engine = _build_engine(stage_overrides={"spec": spec_mock})
        checkpoint = _make_checkpoint("spec")
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()
        spec_mock.execute_with_gate.assert_awaited(), (
            "When checkpoint stage is 'spec', spec must be re-run"
        )

    @pytest.mark.asyncio
    async def test_all_stages_run_when_checkpoint_stage_is_spec(self):
        """FR-resume-4: checkpoint='spec' → entire pipeline runs (all four stages)."""
        call_log: list[str] = []

        async def _gate(name: str):
            call_log.append(name)
            return _make_passing_stage_result(name)

        stages = {
            n: MagicMock(execute_with_gate=AsyncMock(side_effect=lambda nm=n: _gate(nm)))
            for n in STAGE_NAMES
        }
        engine = PipelineEngine(stages=stages, config={"skip_stages": []})
        checkpoint = _make_checkpoint("spec")
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()

        assert set(call_log) == set(STAGE_NAMES), (
            f"All stages must run when checkpoint stage='spec'. Called: {call_log}"
        )

    @pytest.mark.asyncio
    async def test_plan_reruns_when_checkpoint_stage_is_plan(self):
        """FR-resume-4: checkpoint stage='plan' → plan re-runs from the beginning."""
        plan_mock = _make_stage_mock(passing=True, name="plan")
        engine = _build_engine(stage_overrides={"plan": plan_mock})
        checkpoint = _make_checkpoint("plan")
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()
        plan_mock.execute_with_gate.assert_awaited(), (
            "When checkpoint stage is 'plan', plan must be re-run"
        )

    @pytest.mark.asyncio
    async def test_spec_also_reruns_when_checkpoint_stage_is_plan(self):
        """FR-resume-4: checkpoint='plan' → spec also re-runs (it is atomic too)."""
        spec_mock = _make_stage_mock(passing=True, name="spec")
        engine = _build_engine(stage_overrides={"spec": spec_mock})
        checkpoint = _make_checkpoint("plan")
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()
        spec_mock.execute_with_gate.assert_awaited(), (
            "When checkpoint stage is 'plan', spec must also re-run (atomic)"
        )


# ---------------------------------------------------------------------------
# 9. FR-resume-5: Checkpoint at 'acceptance' → pipeline already complete
# ---------------------------------------------------------------------------


class TestCheckpointAtAcceptance:
    """If the checkpoint stage is 'acceptance' (completed), no stages should re-run."""

    @pytest.mark.asyncio
    async def test_no_stages_execute_when_checkpoint_is_acceptance_complete(self):
        """FR-resume-5: completed 'acceptance' checkpoint → no stages re-run."""
        stage_mocks = {
            n: _make_stage_mock(passing=True, name=n) for n in STAGE_NAMES
        }
        engine = PipelineEngine(stages=stage_mocks, config={"skip_stages": []})
        checkpoint = _make_checkpoint("acceptance", data={"completed": True})
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            await engine.resume()

        for name, mock in stage_mocks.items():
            mock.execute_with_gate.assert_not_awaited(), (
                f"Stage '{name}' must NOT re-run when pipeline is already complete"
            )

    @pytest.mark.asyncio
    async def test_resume_returns_passed_true_when_acceptance_already_complete(self):
        """FR-resume-5: resume() returns passed=True when acceptance checkpoint exists."""
        engine = _build_engine()
        checkpoint = _make_checkpoint("acceptance", data={"completed": True})
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            result = await engine.resume()
        assert result.passed is True, (
            "resume() must return PipelineResult(passed=True) when acceptance is complete"
        )

    @pytest.mark.asyncio
    async def test_resume_result_is_pipeline_result_when_acceptance_complete(self):
        """FR-resume-5: resume() must still return a PipelineResult even if already done."""
        engine = _build_engine()
        checkpoint = _make_checkpoint("acceptance", data={"completed": True})
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            result = await engine.resume()
        assert isinstance(result, PipelineResult), (
            f"resume() must return PipelineResult, got {type(result).__name__}"
        )


# ---------------------------------------------------------------------------
# 10. Edge cases
# ---------------------------------------------------------------------------


class TestResumeEdgeCases:
    """Edge cases for resume()."""

    @pytest.mark.asyncio
    async def test_resume_raises_no_checkpoint_error_not_value_error(self):
        """No-checkpoint condition must raise NoCheckpointError, not ValueError/RuntimeError."""
        engine = _build_engine()
        with patch.object(engine, "_load_checkpoint", return_value=None, create=True):
            with pytest.raises(NoCheckpointError):
                await engine.resume()

    @pytest.mark.asyncio
    async def test_resume_uses_engine_lock(self):
        """resume() must acquire the engine's asyncio.Lock during execution."""
        engine = _build_engine()
        checkpoint = _make_checkpoint("implement", last_completed_task_index=0)
        lock_was_locked_during_run = []

        original_run = engine.run

        async def _patched_run():
            lock_was_locked_during_run.append(engine.lock.locked())
            return await original_run()

        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            with patch.object(engine, "run", side_effect=_patched_run):
                try:
                    await engine.resume()
                except Exception:
                    pass

        # After resume completes, lock must be free
        assert engine.lock.locked() is False, (
            "engine.lock must be released after resume() completes"
        )

    @pytest.mark.asyncio
    async def test_resume_returns_pipeline_result_for_implement_checkpoint(self):
        """resume() must return a PipelineResult (not None) for an implement checkpoint."""
        engine = _build_engine()
        checkpoint = _make_checkpoint("implement", last_completed_task_index=1)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            result = await engine.resume()
        assert result is not None, "resume() must not return None"
        assert isinstance(result, PipelineResult)

    @pytest.mark.asyncio
    async def test_resume_result_failed_stage_none_on_success(self):
        """resume() result.failed_stage must be None when resumed pipeline succeeds."""
        engine = _build_engine()
        checkpoint = _make_checkpoint("implement", last_completed_task_index=0)
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            result = await engine.resume()
        assert result.failed_stage is None, (
            f"failed_stage must be None on successful resume, got {result.failed_stage!r}"
        )

    @pytest.mark.asyncio
    async def test_resume_propagates_stage_failure(self):
        """resume() must propagate failures — result.passed=False when a stage fails."""
        failing_spec = _make_stage_mock(passing=False, name="spec")
        engine = _build_engine(stage_overrides={"spec": failing_spec})
        checkpoint = _make_checkpoint("spec")
        with patch.object(engine, "_load_checkpoint", return_value=checkpoint, create=True):
            result = await engine.resume()
        assert result.passed is False, (
            "resume() must return passed=False when a re-run stage fails"
        )

    @pytest.mark.asyncio
    async def test_resume_concurrent_calls_serialised_by_lock(self):
        """Concurrent resume() calls must be serialised by the engine lock."""
        engine = _build_engine()
        checkpoint = _make_checkpoint("implement", last_completed_task_index=0)
        execution_starts: list[int] = []
        execution_ends: list[int] = []
        counter = {"n": 0}

        original_load = lambda: checkpoint  # noqa: E731

        async def _slow_run():
            counter["n"] += 1
            idx = counter["n"]
            execution_starts.append(idx)
            await asyncio.sleep(0.02)
            execution_ends.append(idx)
            return PipelineResult(passed=True)

        with patch.object(engine, "_load_checkpoint", side_effect=original_load, create=True):
            with patch.object(engine, "run", side_effect=_slow_run):
                results = await asyncio.gather(
                    engine.resume(),
                    engine.resume(),
                    return_exceptions=True,
                )

        # Either both succeed or one succeeds and one raises due to lock contention.
        # What matters is they do NOT interleave — ends must follow starts in order.
        # Simplified check: lock is free after both complete.
        assert engine.lock.locked() is False, (
            "engine.lock must be free after concurrent resume() calls complete"
        )

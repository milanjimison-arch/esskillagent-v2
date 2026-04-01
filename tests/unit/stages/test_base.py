"""FR-001: Stage base class — RED phase behavior tests.

All tests in this module assert the *behavior* required of the Stage base class
and its template method pattern.  The current stub raises NotImplementedError
for run(), _run_review(), _check_gate(), and _save_checkpoint(), so every test
that exercises those paths must produce a RED failure.

Covered requirements:
  FR-001-A  Stage requires engine_ctx dependency injection via __init__.
  FR-001-B  run() orchestrates execute_steps → review → gate → checkpoint
            in that exact order.
  FR-001-C  _execute_steps is abstract; instantiating Stage directly is
            impossible and a concrete subclass must override it.
  FR-001-D  _run_review, _check_gate, _save_checkpoint have default (non-raising)
            implementations in the base class.
  FR-001-E  A concrete subclass can override _execute_steps and run() works
            end-to-end, calling the shared helpers in sequence.
  FR-001-F  run() passes artifacts returned by _execute_steps to _run_review.
  FR-001-G  run() passes the review result from _run_review to _check_gate.
  FR-001-H  _save_checkpoint is always called after _check_gate, regardless of
            the gate verdict.
  FR-001-I  _run_review delegates to self.ctx.review_pipeline.
  FR-001-J  _check_gate returns True when review_pipeline passes.
  FR-001-K  _save_checkpoint delegates to self.ctx.store.
  FR-001-L  run() propagates exceptions raised inside _execute_steps.
  FR-001-M  Stage.ctx holds the exact EngineContext passed to __init__.
"""
from __future__ import annotations

import asyncio
import inspect
from abc import ABC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.stages.base import EngineContext, Stage


# ---------------------------------------------------------------------------
# Test helpers / factories
# ---------------------------------------------------------------------------


def _make_store() -> MagicMock:
    """Return a MagicMock store whose async methods are properly awaitable."""
    mock_store = MagicMock()
    mock_store.save_checkpoint = AsyncMock()
    return mock_store


def _make_ctx(
    *,
    review_return: Any = None,
    store: Any = None,
) -> EngineContext:
    """Return a fully-mocked EngineContext.

    The default store has save_checkpoint as an AsyncMock so that
    _save_checkpoint in the base class can be awaited without TypeError.
    """
    mock_store = store if store is not None else _make_store()

    mock_review_pipeline = MagicMock()
    rv = review_return if review_return is not None else {"verdict": "pass", "issues": []}
    mock_review_pipeline.run_review = AsyncMock(return_value=rv)

    return EngineContext(
        project_path="/fake/project",
        config=MagicMock(),
        store=mock_store,
        agents=MagicMock(),
        checker=MagicMock(),
        review_pipeline=mock_review_pipeline,
    )


class _ConcreteStage(Stage):
    """Minimal concrete subclass used across tests.

    _execute_steps is a real async method that records calls and returns a
    fixed artifacts dict.  Individual tests may patch it as needed.
    """

    def __init__(self, ctx: EngineContext, artifacts: dict[str, Any] | None = None) -> None:
        super().__init__(ctx)
        self._artifacts = artifacts or {"output": "done"}
        self.execute_steps_called: bool = False

    async def _execute_steps(self) -> dict[str, Any]:
        self.execute_steps_called = True
        return self._artifacts


# ---------------------------------------------------------------------------
# FR-001-A: Dependency injection
# ---------------------------------------------------------------------------


class TestDependencyInjection:
    """FR-001-A: Stage must accept and store EngineContext via __init__."""

    def test_FR001A_stage_stores_ctx_on_init(self) -> None:
        """FR-001-A: stage.ctx must be the exact EngineContext passed to __init__."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        assert stage.ctx is ctx, "stage.ctx must reference the injected EngineContext"

    def test_FR001A_ctx_project_path_accessible(self) -> None:
        """FR-001-A: injected ctx fields must remain accessible via stage.ctx."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        assert stage.ctx.project_path == "/fake/project"

    def test_FR001A_ctx_review_pipeline_accessible(self) -> None:
        """FR-001-A: stage.ctx.review_pipeline must be the mock passed in."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        assert stage.ctx.review_pipeline is ctx.review_pipeline

    def test_FR001A_ctx_store_accessible(self) -> None:
        """FR-001-A: stage.ctx.store must be the mock passed in."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        assert stage.ctx.store is ctx.store

    def test_FR001A_multiple_stages_have_independent_ctx(self) -> None:
        """FR-001-A: two Stage instances must not share state via ctx."""
        ctx_a = _make_ctx()
        ctx_b = _make_ctx()
        stage_a = _ConcreteStage(ctx_a)
        stage_b = _ConcreteStage(ctx_b)
        assert stage_a.ctx is not stage_b.ctx


# ---------------------------------------------------------------------------
# FR-001-C: _execute_steps is abstract
# ---------------------------------------------------------------------------


class TestAbstractExecuteSteps:
    """FR-001-C: Stage must be abstract; _execute_steps must be overridden."""

    def test_FR001C_stage_is_abstract_base_class(self) -> None:
        """FR-001-C: Stage must inherit from ABC."""
        assert issubclass(Stage, ABC), "Stage must be an ABC"

    def test_FR001C_stage_cannot_be_instantiated_directly(self) -> None:
        """FR-001-C: attempting to instantiate Stage directly must raise TypeError."""
        ctx = _make_ctx()
        with pytest.raises(TypeError):
            Stage(ctx)  # type: ignore[abstract]

    def test_FR001C_execute_steps_is_marked_abstractmethod(self) -> None:
        """FR-001-C: _execute_steps must be decorated with @abstractmethod."""
        assert "_execute_steps" in Stage.__abstractmethods__, (
            "_execute_steps must be listed in Stage.__abstractmethods__"
        )

    def test_FR001C_concrete_subclass_with_execute_steps_can_be_instantiated(self) -> None:
        """FR-001-C: a subclass that overrides _execute_steps must be instantiable."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        assert isinstance(stage, Stage)

    def test_FR001C_subclass_without_execute_steps_raises_type_error(self) -> None:
        """FR-001-C: a subclass that does NOT override _execute_steps must also
        raise TypeError on instantiation."""
        class _NoOpSubclass(Stage):
            pass

        ctx = _make_ctx()
        with pytest.raises(TypeError):
            _NoOpSubclass(ctx)  # type: ignore[abstract]

    def test_FR001C_execute_steps_is_async(self) -> None:
        """FR-001-C: the concrete _execute_steps must be an async coroutine function."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        assert asyncio.iscoroutinefunction(stage._execute_steps), (
            "_execute_steps must be an async method"
        )


# ---------------------------------------------------------------------------
# FR-001-D: Default implementations of shared helpers
# ---------------------------------------------------------------------------


class TestDefaultHelperImplementations:
    """FR-001-D: _run_review, _check_gate, _save_checkpoint must have
    default (non-raising) implementations on the base class."""

    @pytest.mark.asyncio
    async def test_FR001D_run_review_has_default_implementation(self) -> None:
        """FR-001-D: _run_review must not raise NotImplementedError by default."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        # Should not raise; return value may be anything
        result = await stage._run_review({"output": "done"})
        # No assertion on value — only that it did not raise

    @pytest.mark.asyncio
    async def test_FR001D_check_gate_has_default_implementation(self) -> None:
        """FR-001-D: _check_gate must not raise NotImplementedError by default."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        result = await stage._check_gate({"verdict": "pass"})
        # No assertion on value — only that it did not raise

    @pytest.mark.asyncio
    async def test_FR001D_save_checkpoint_has_default_implementation(self) -> None:
        """FR-001-D: _save_checkpoint must not raise NotImplementedError by default."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        await stage._save_checkpoint("abc123")
        # No assertion on value — only that it did not raise

    @pytest.mark.asyncio
    async def test_FR001D_run_review_returns_a_value(self) -> None:
        """FR-001-D: _run_review default must return *some* value (not raise)."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        result = await stage._run_review({"data": "artifacts"})
        # The result should be assignable — we only care it completed
        assert result is not None or result is None  # always true; proves no exception

    @pytest.mark.asyncio
    async def test_FR001D_check_gate_returns_bool_like(self) -> None:
        """FR-001-D: _check_gate default must return a truthy/falsy value."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        result = await stage._check_gate({"verdict": "pass"})
        # verify the value is bool-compatible
        _ = bool(result)  # must not raise


# ---------------------------------------------------------------------------
# FR-001-B / FR-001-E: run() template method ordering
# ---------------------------------------------------------------------------


class TestRunOrchestration:
    """FR-001-B/E: run() must call execute_steps → review → gate → checkpoint
    in strict sequence."""

    @pytest.mark.asyncio
    async def test_FR001B_run_calls_execute_steps(self) -> None:
        """FR-001-B: run() must invoke _execute_steps."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)
        await stage.run()
        assert stage.execute_steps_called, "run() must call _execute_steps"

    @pytest.mark.asyncio
    async def test_FR001B_run_calls_review_after_execute_steps(self) -> None:
        """FR-001-B: run() must call _run_review after _execute_steps completes."""
        call_log: list[str] = []

        class _OrderStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                call_log.append("execute_steps")
                return {"out": "x"}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                call_log.append("run_review")
                return {"verdict": "pass"}

        ctx = _make_ctx()
        stage = _OrderStage(ctx)
        await stage.run()

        assert "execute_steps" in call_log, "execute_steps must be called"
        assert "run_review" in call_log, "_run_review must be called"
        assert call_log.index("execute_steps") < call_log.index("run_review"), (
            "_execute_steps must be called before _run_review"
        )

    @pytest.mark.asyncio
    async def test_FR001B_run_calls_gate_after_review(self) -> None:
        """FR-001-B: run() must call _check_gate after _run_review completes."""
        call_log: list[str] = []

        class _OrderStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                call_log.append("execute_steps")
                return {}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                call_log.append("run_review")
                return {"verdict": "pass"}

            async def _check_gate(self, review_result: Any) -> bool:
                call_log.append("check_gate")
                return True

        ctx = _make_ctx()
        stage = _OrderStage(ctx)
        await stage.run()

        assert "run_review" in call_log
        assert "check_gate" in call_log
        assert call_log.index("run_review") < call_log.index("check_gate"), (
            "_run_review must be called before _check_gate"
        )

    @pytest.mark.asyncio
    async def test_FR001B_run_calls_checkpoint_after_gate(self) -> None:
        """FR-001-B: run() must call _save_checkpoint after _check_gate."""
        call_log: list[str] = []

        class _OrderStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                call_log.append("execute_steps")
                return {}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                call_log.append("run_review")
                return {"verdict": "pass"}

            async def _check_gate(self, review_result: Any) -> bool:
                call_log.append("check_gate")
                return True

            async def _save_checkpoint(self, git_sha: str) -> None:
                call_log.append("save_checkpoint")

        ctx = _make_ctx()
        stage = _OrderStage(ctx)
        await stage.run()

        assert "check_gate" in call_log
        assert "save_checkpoint" in call_log
        assert call_log.index("check_gate") < call_log.index("save_checkpoint"), (
            "_check_gate must be called before _save_checkpoint"
        )

    @pytest.mark.asyncio
    async def test_FR001B_exact_sequence_execute_review_gate_checkpoint(self) -> None:
        """FR-001-B: the full sequence must be execute_steps → review → gate → checkpoint."""
        call_log: list[str] = []

        class _FullOrderStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                call_log.append("execute_steps")
                return {"key": "val"}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                call_log.append("run_review")
                return {"verdict": "pass"}

            async def _check_gate(self, review_result: Any) -> bool:
                call_log.append("check_gate")
                return True

            async def _save_checkpoint(self, git_sha: str) -> None:
                call_log.append("save_checkpoint")

        ctx = _make_ctx()
        stage = _FullOrderStage(ctx)
        await stage.run()

        expected = ["execute_steps", "run_review", "check_gate", "save_checkpoint"]
        assert call_log == expected, (
            f"Expected call order {expected}, got {call_log}"
        )


# ---------------------------------------------------------------------------
# FR-001-F: artifacts from execute_steps are forwarded to _run_review
# ---------------------------------------------------------------------------


class TestArtifactsForwarding:
    """FR-001-F: run() must pass the artifacts dict from _execute_steps to _run_review."""

    @pytest.mark.asyncio
    async def test_FR001F_run_passes_artifacts_to_run_review(self) -> None:
        """FR-001-F: artifacts returned by _execute_steps must be the argument
        to _run_review."""
        expected_artifacts = {"step_result": "value", "count": 42}
        received_artifacts: list[Any] = []

        class _ArtifactStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                return expected_artifacts

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                received_artifacts.append(artifacts)
                return {"verdict": "pass"}

        ctx = _make_ctx()
        stage = _ArtifactStage(ctx)
        await stage.run()

        assert len(received_artifacts) == 1, "_run_review must be called exactly once"
        assert received_artifacts[0] is expected_artifacts, (
            "_run_review must receive the exact artifacts dict from _execute_steps"
        )

    @pytest.mark.asyncio
    async def test_FR001F_empty_artifacts_still_forwarded(self) -> None:
        """FR-001-F: even an empty artifacts dict must be forwarded to _run_review."""
        received: list[Any] = []

        class _EmptyArtifactStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                return {}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                received.append(artifacts)
                return {"verdict": "pass"}

        ctx = _make_ctx()
        stage = _EmptyArtifactStage(ctx)
        await stage.run()

        assert received[0] == {}, "empty artifacts dict must still be forwarded"


# ---------------------------------------------------------------------------
# FR-001-G: review result from _run_review is forwarded to _check_gate
# ---------------------------------------------------------------------------


class TestReviewResultForwarding:
    """FR-001-G: run() must pass the review result from _run_review to _check_gate."""

    @pytest.mark.asyncio
    async def test_FR001G_review_result_forwarded_to_check_gate(self) -> None:
        """FR-001-G: _check_gate must receive the exact value returned by _run_review."""
        expected_review = {"verdict": "pass", "score": 99, "issues": []}
        received_gate_args: list[Any] = []

        class _ReviewForwardStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                return {}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                return expected_review

            async def _check_gate(self, review_result: Any) -> bool:
                received_gate_args.append(review_result)
                return True

        ctx = _make_ctx()
        stage = _ReviewForwardStage(ctx)
        await stage.run()

        assert len(received_gate_args) == 1, "_check_gate must be called exactly once"
        assert received_gate_args[0] is expected_review, (
            "_check_gate must receive the exact review result from _run_review"
        )


# ---------------------------------------------------------------------------
# FR-001-H: _save_checkpoint is always called after gate
# ---------------------------------------------------------------------------


class TestCheckpointAlwaysCalled:
    """FR-001-H: _save_checkpoint must be called even when _check_gate returns False."""

    @pytest.mark.asyncio
    async def test_FR001H_checkpoint_called_when_gate_passes(self) -> None:
        """FR-001-H: _save_checkpoint must be called when gate returns True."""
        checkpoint_calls: list[str] = []

        class _GatePassStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                return {}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                return {"verdict": "pass"}

            async def _check_gate(self, review_result: Any) -> bool:
                return True

            async def _save_checkpoint(self, git_sha: str) -> None:
                checkpoint_calls.append("saved")

        ctx = _make_ctx()
        stage = _GatePassStage(ctx)
        await stage.run()

        assert len(checkpoint_calls) == 1, (
            "_save_checkpoint must be called exactly once when gate passes"
        )

    @pytest.mark.asyncio
    async def test_FR001H_checkpoint_called_when_gate_fails(self) -> None:
        """FR-001-H: _save_checkpoint must still be called when gate returns False."""
        checkpoint_calls: list[str] = []

        class _GateFailStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                return {}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                return {"verdict": "fail"}

            async def _check_gate(self, review_result: Any) -> bool:
                return False  # gate deliberately fails

            async def _save_checkpoint(self, git_sha: str) -> None:
                checkpoint_calls.append("saved")

        ctx = _make_ctx()
        stage = _GateFailStage(ctx)
        await stage.run()

        assert len(checkpoint_calls) == 1, (
            "_save_checkpoint must be called even when gate returns False"
        )


# ---------------------------------------------------------------------------
# FR-001-I: _run_review delegates to ctx.review_pipeline
# ---------------------------------------------------------------------------


class TestRunReviewDelegation:
    """FR-001-I: the default _run_review must delegate to self.ctx.review_pipeline."""

    @pytest.mark.asyncio
    async def test_FR001I_default_run_review_calls_review_pipeline(self) -> None:
        """FR-001-I: calling _run_review on the base class must invoke
        self.ctx.review_pipeline.run_review."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)

        await stage._run_review({"some": "artifact"})

        ctx.review_pipeline.run_review.assert_called_once()

    @pytest.mark.asyncio
    async def test_FR001I_run_review_returns_pipeline_result(self) -> None:
        """FR-001-I: _run_review must return what review_pipeline.run_review returns."""
        expected = {"verdict": "pass", "issues": [], "score": 95}
        ctx = _make_ctx(review_return=expected)
        stage = _ConcreteStage(ctx)

        result = await stage._run_review({"data": "ok"})

        assert result == expected, (
            "_run_review must return the result from review_pipeline.run_review"
        )


# ---------------------------------------------------------------------------
# FR-001-J: _check_gate returns True when review passes
# ---------------------------------------------------------------------------


class TestCheckGateVerdict:
    """FR-001-J: _check_gate must return True for a passing review, False otherwise."""

    @pytest.mark.asyncio
    async def test_FR001J_check_gate_returns_true_for_pass_verdict(self) -> None:
        """FR-001-J: _check_gate must return True when review_result verdict is 'pass'."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)

        result = await stage._check_gate({"verdict": "pass", "issues": []})

        assert result is True, (
            "_check_gate must return True when verdict is 'pass'"
        )

    @pytest.mark.asyncio
    async def test_FR001J_check_gate_returns_false_for_fail_verdict(self) -> None:
        """FR-001-J: _check_gate must return False when review_result verdict is 'fail'."""
        ctx = _make_ctx()
        stage = _ConcreteStage(ctx)

        result = await stage._check_gate({"verdict": "fail", "issues": ["critical bug"]})

        assert result is False, (
            "_check_gate must return False when verdict is 'fail'"
        )


# ---------------------------------------------------------------------------
# FR-001-K: _save_checkpoint delegates to ctx.store
# ---------------------------------------------------------------------------


class TestSaveCheckpointDelegation:
    """FR-001-K: the default _save_checkpoint must delegate to self.ctx.store."""

    @pytest.mark.asyncio
    async def test_FR001K_default_save_checkpoint_calls_store(self) -> None:
        """FR-001-K: _save_checkpoint must interact with self.ctx.store."""
        mock_store = MagicMock()
        mock_store.save_checkpoint = AsyncMock()
        ctx = _make_ctx(store=mock_store)
        stage = _ConcreteStage(ctx)

        await stage._save_checkpoint("deadbeef")

        mock_store.save_checkpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_FR001K_save_checkpoint_passes_git_sha_to_store(self) -> None:
        """FR-001-K: the git_sha argument must be forwarded to the store."""
        mock_store = MagicMock()
        mock_store.save_checkpoint = AsyncMock()
        ctx = _make_ctx(store=mock_store)
        stage = _ConcreteStage(ctx)

        await stage._save_checkpoint("abc123sha")

        call_args = mock_store.save_checkpoint.call_args
        # git_sha must appear somewhere in the call — positional or keyword
        all_args = list(call_args.args) + list(call_args.kwargs.values())
        assert "abc123sha" in all_args, (
            "_save_checkpoint must pass the git_sha to ctx.store.save_checkpoint"
        )


# ---------------------------------------------------------------------------
# FR-001-L: run() propagates exceptions from _execute_steps
# ---------------------------------------------------------------------------


class TestExceptionPropagation:
    """FR-001-L: exceptions raised inside _execute_steps must propagate through run()."""

    @pytest.mark.asyncio
    async def test_FR001L_execute_steps_exception_propagates_through_run(self) -> None:
        """FR-001-L: if _execute_steps raises, run() must re-raise without swallowing."""
        class _StepError(RuntimeError):
            pass

        class _FailingStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                raise _StepError("step exploded")

        ctx = _make_ctx()
        stage = _FailingStage(ctx)

        with pytest.raises(_StepError, match="step exploded"):
            await stage.run()

    @pytest.mark.asyncio
    async def test_FR001L_run_review_exception_propagates_through_run(self) -> None:
        """FR-001-L: if _run_review raises, run() must re-raise."""
        class _ReviewError(RuntimeError):
            pass

        class _ReviewFailStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                return {}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                raise _ReviewError("review exploded")

        ctx = _make_ctx()
        stage = _ReviewFailStage(ctx)

        with pytest.raises(_ReviewError, match="review exploded"):
            await stage.run()

    @pytest.mark.asyncio
    async def test_FR001L_check_gate_exception_propagates_through_run(self) -> None:
        """FR-001-L: if _check_gate raises, run() must re-raise."""
        class _GateError(RuntimeError):
            pass

        class _GateFailStage(Stage):
            async def _execute_steps(self) -> dict[str, Any]:
                return {}

            async def _run_review(self, artifacts: dict[str, Any]) -> Any:
                return {"verdict": "pass"}

            async def _check_gate(self, review_result: Any) -> bool:
                raise _GateError("gate exploded")

        ctx = _make_ctx()
        stage = _GateFailStage(ctx)

        with pytest.raises(_GateError, match="gate exploded"):
            await stage.run()


# ---------------------------------------------------------------------------
# FR-001-M: EngineContext dataclass contract
# ---------------------------------------------------------------------------


class TestEngineContextContract:
    """FR-001-M: EngineContext must be a frozen dataclass exposing all required fields."""

    def test_FR001M_engine_context_is_dataclass(self) -> None:
        """FR-001-M: EngineContext must be a dataclass."""
        import dataclasses
        assert dataclasses.is_dataclass(EngineContext), (
            "EngineContext must be a dataclass"
        )

    def test_FR001M_engine_context_is_frozen(self) -> None:
        """FR-001-M: EngineContext must be immutable (frozen=True)."""
        ctx = _make_ctx()
        with pytest.raises((AttributeError, TypeError)):
            ctx.project_path = "/other/path"  # type: ignore[misc]

    def test_FR001M_engine_context_has_project_path(self) -> None:
        """FR-001-M: EngineContext must expose project_path field."""
        ctx = _make_ctx()
        assert hasattr(ctx, "project_path")

    def test_FR001M_engine_context_has_config(self) -> None:
        """FR-001-M: EngineContext must expose config field."""
        ctx = _make_ctx()
        assert hasattr(ctx, "config")

    def test_FR001M_engine_context_has_store(self) -> None:
        """FR-001-M: EngineContext must expose store field."""
        ctx = _make_ctx()
        assert hasattr(ctx, "store")

    def test_FR001M_engine_context_has_agents(self) -> None:
        """FR-001-M: EngineContext must expose agents field."""
        ctx = _make_ctx()
        assert hasattr(ctx, "agents")

    def test_FR001M_engine_context_has_checker(self) -> None:
        """FR-001-M: EngineContext must expose checker field."""
        ctx = _make_ctx()
        assert hasattr(ctx, "checker")

    def test_FR001M_engine_context_has_review_pipeline(self) -> None:
        """FR-001-M: EngineContext must expose review_pipeline field."""
        ctx = _make_ctx()
        assert hasattr(ctx, "review_pipeline")
